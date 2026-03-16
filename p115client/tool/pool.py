#!/usr/bin/env python3
# encoding: utf-8

from __future__ import annotations

__author__ = "ChenyangGao <https://chenyanggao.github.io>"
__all__ = [
    "generate_auth_factory", "generate_cookies_factory", "generate_client_factory", 
    "make_pool", "auth_pool", "cookies_pool", "client_pool", "call_wrap_with_pool", 
]
__doc__ = "这个模块提供了一些和 cookies 池有关的函数"

from asyncio import Lock as AsyncLock
from collections.abc import Callable, Iterable, Mapping
from functools import partial, total_ordering, update_wrapper
from heapq import heappop, heappush, heapify
from itertools import cycle, repeat
from math import inf, isinf
from os import PathLike
from threading import Lock
from time import time

from http_response import get_status_code, is_timeouterror
from iterutils import run_gen_step

from ..client import check_response, P115Client
from ..exception import P115OSError, P115AuthenticationError, P115LoginError


@total_ordering
class ComparedWithID[T]:
    value: T

    def __new__(cls, value: T | ComparedWithID[T], /):
        if isinstance(value, ComparedWithID):
            return value
        else:
            self = super().__new__(cls)
            self.value = value
            return self

    def __eq__(self, other, /) -> bool:
        if isinstance(other, ComparedWithID):
            return id(self) == id(other.value)
        return id(self) == id(other)

    def __lt__(self, other, /) -> bool:
        if isinstance(other, ComparedWithID):
            return id(self) < id(other.value)
        return id(self) < id(other)

    def __repr__(self, /) -> str:
        return f"{type(self).__qualname__}({self.value!r})"


def generate_auth_factory(
    client: str | PathLike | P115Client, 
    app_ids: Iterable[int], 
    **request_kwargs, 
) -> Callable:
    """利用一个已登录设备的 cookies，产生若干开放应用的 access_token

    :param client: 115 客户端或 cookies
    :param app_ids: 一组开放应用的 AppID
    :param request_kwargs: 其它请求参数

    :return: 函数，调用以返回一个字典，包含 authorization 请求头
    """
    if isinstance(client, (str, PathLike)):
        client = P115Client(client, check_for_relogin=True)
    login = client.login_with_open
    get_app_id = cycle(app_ids).__next__
    def make_cookies(async_: bool = False):
        def gen_step():
            while True:
                app_id = get_app_id()
                try:
                    resp = yield login(
                        get_app_id(), 
                        async_=async_, # type: ignore
                        **request_kwargs, 
                    )
                except Exception as e:
                    if not is_timeouterror(e):
                        raise
                check_response(resp)
                return {
                    "authorization": "Bearer " + resp["data"]["access_token"], 
                    "app_id": str(app_id), 
                }
        return run_gen_step(gen_step, async_)
    return make_cookies


def generate_cookies_factory(
    client: str | PathLike | P115Client, 
    app: str | Iterable[str] = "", 
    **request_kwargs, 
) -> Callable:
    """利用一个已登录设备的 cookies，产生另一个设备的若干 cookies

    :param client: 115 客户端或 cookies
    :param app: 自动扫码后绑定的 app（多个则传入一组 app 的可迭代对象）
    :param request_kwargs: 其它请求参数

    :return: 函数，调用以返回一个字典，包含 cookie 请求头
    """
    if isinstance(client, (str, PathLike)):
        client = P115Client(client, check_for_relogin=True)
    if isinstance(app, str):
        if app:
            if app == client.login_app():
                raise ValueError(f"same login device (app={app!r}) will cause conflicts")
        else:
            app = "tv" if client.login_ssoent == "R2" else "alipaymini"
        get_app = repeat(app).__next__
    else:
        app = tuple(app)
        if client.login_app() in app:
            raise ValueError(f"same login device (app={app!r}) will cause conflicts")
        elif not app:
            app = "tv" if client.login_ssoent == "R2" else "alipaymini"
            get_app = repeat(app).__next__
        else:
            get_app = cycle(app).__next__
    login = client.login_with_app
    def make_cookies(async_: bool = False):
        def gen_step():
            while True:
                app = get_app()
                try:
                    resp = yield login(
                        app, 
                        async_=async_, # type: ignore
                        **request_kwargs, 
                    )
                except Exception as e:
                    if not is_timeouterror(e):
                        raise
                check_response(resp)
                return {
                    "cookie": "; ".join(f"{k}={v}" for k, v in resp["data"]["cookie"].items()), 
                    "app": app, 
                }
        return run_gen_step(gen_step, async_)
    return make_cookies


def generate_client_factory(
    client: str | PathLike | P115Client, 
    app: str | Iterable[str] = "", 
    **request_kwargs, 
) -> Callable:
    """利用一个已登录设备的 client，产生另一个设备的若干 client

    :param client: 115 客户端或 cookies
    :param app: 自动扫码后绑定的 app（多个则传入一组 app 的可迭代对象）
    :param request_kwargs: 其它请求参数

    :return: 函数，调用以返回一个 client
    """
    if isinstance(client, (str, PathLike)):
        client = P115Client(client, check_for_relogin=True)
    cls = type(client)
    call = generate_cookies_factory(client, app, **request_kwargs)
    def make_client(async_: bool = False):
        def gen_step():
            headers = yield call(async_=async_)
            return cls(headers["cookie"])
        return run_gen_step(gen_step, async_)
    return make_client


def make_pool[T](
    generate_factory: Callable, 
    heap: None | list[tuple[float, T | ComparedWithID[T]]] = None, 
    cooldown_time: int | float = 1, 
    live_time: int | float = inf, 
    lock: bool = True, 
    **request_kwargs, 
) -> Callable:
    """创建池

    :param generate_factory: 产生值的工厂函数
    :param heap: 最小堆，可以包含一组初始值，各是一个元组，包含（上一次获取时刻, 值）
    :param cooldown_time: 值的冷却时间
    :param live_time: 值的存活时间，默认是无穷大
    :param lock: 是否需要锁
    :param request_kwargs: 其它请求参数

    :return: 返回一个函数，调用后返回一个元组，包含 值 和 一个调用以在完成后把 值 返还池中
    """
    generate = generate_factory(**request_kwargs)
    if heap is None:
        heap_: list[tuple[float,  ComparedWithID[T]]] = []
    else:
        for i, (a, b) in enumerate(heap):
            heap[i] = (a, ComparedWithID(b))
        heapify(heap)
        heap_ = heap # type: ignore
    def get_value(async_: bool = False):
        def call():
            now = time()
            if not isinf(live_time):
                watermark = now - live_time
                while heap_:
                    if heap_[0][0] > watermark:
                        break
                    heappop(heap_)
            if heap_ and heap_[0][0] + cooldown_time <= now:
                _, val = heappop(heap_)
                value = val.value
            else:
                if async_:
                    value = yield generate(async_=True)
                else:
                    value = generate()
                val = ComparedWithID(value)
            return value, partial(heappush, heap_, (time(), val))
        return run_gen_step(call, async_)
    if not lock:
        setattr(get_value, "heap", heap_)
        return get_value
    lock_sync = Lock()
    lock_async = AsyncLock()
    def locked_get_value(async_: bool = False):
        if async_:
            async def async_locked_get_value():
                async with lock_async:
                    return await get_value(async_=True)
            return async_locked_get_value
        else:
            def locked_get_value():
                with lock_sync:
                    return get_value()
            return locked_get_value
    setattr(locked_get_value, "heap", heap_)
    return locked_get_value


def auth_pool(
    client: str | PathLike | P115Client, 
    app_ids: Iterable[int], 
    heap: None | list[tuple[float, dict | ComparedWithID[dict]]] = None, 
    cooldown_time: int | float = 1, 
    live_time: int | float = 7000, 
    lock: bool = False, 
    **request_kwargs, 
) -> Callable:
    """authorization 请求头池

    :param client: 115 客户端或 cookies
    :param app_ids: 一组开放应用的 AppID
    :param heap: 最小堆，可以包含一组初始值，各是一个元组，包含（上一次获取时刻, 值）
    :param cooldown_time: 值的冷却时间
    :param live_time: 值的存活时间，默认是无穷大
    :param lock: 锁，如果不需要锁，传入 False
    :param request_kwargs: 其它请求参数

    :return: 返回一个函数，调用后返回一个元组，包含值 和 一个调用（以在完成后把值返还池中）
    """
    return make_pool(
        generate_auth_factory, 
        client=client, 
        app_ids=app_ids, 
        heap=heap, 
        cooldown_time=cooldown_time, 
        live_time=live_time, 
        lock=lock, 
        **request_kwargs, 
    )


def cookies_pool(
    client: str | PathLike | P115Client, 
    app: str | Iterable[str] = "", 
    heap: None | list[tuple[float, dict | ComparedWithID[dict]]] = None, 
    cooldown_time: int | float = 1, 
    live_time: int | float = inf, 
    lock: bool = False, 
    **request_kwargs, 
) -> Callable:
    """cookie 请求头池

    :param client: 115 客户端或 cookies
    :param app: 自动扫码后绑定的 app（多个则传入一组 app 的可迭代对象）
    :param heap: 最小堆，可以包含一组初始值，各是一个元组，包含（上一次获取时刻, 值）
    :param cooldown_time: 值的冷却时间
    :param live_time: 值的存活时间，默认是无穷大
    :param lock: 锁，如果不需要锁，传入 False
    :param request_kwargs: 其它请求参数

    :return: 返回一个函数，调用后返回一个元组，包含值 和 一个调用（以在完成后把值返还池中）
    """
    return make_pool(
        generate_cookies_factory, 
        client=client, 
        app=app, 
        heap=heap, 
        cooldown_time=cooldown_time, 
        live_time=live_time, 
        lock=lock, 
        **request_kwargs, 
    )


def client_pool(
    client: str | PathLike | P115Client, 
    app: str | Iterable[str] = "", 
    heap: None | list[tuple[float, P115Client | ComparedWithID[P115Client]]] = None, 
    cooldown_time: int | float = 1, 
    live_time: int | float = inf, 
    lock: bool = False, 
    **request_kwargs, 
) -> Callable:
    """client 池

    :param client: 115 客户端或 cookies
    :param app: 自动扫码后绑定的 app（多个则传入一组 app 的可迭代对象）
    :param heap: 最小堆，可以包含一组初始值，各是一个元组，包含（上一次获取时刻, 值）
    :param cooldown_time: 值的冷却时间
    :param live_time: 值的存活时间，默认是无穷大
    :param lock: 锁，如果不需要锁，传入 False
    :param request_kwargs: 其它请求参数

    :return: 返回一个函数，调用后返回一个元组，包含值 和 一个调用（以在完成后把值返还池中）
    """
    return make_pool(
        generate_client_factory, 
        client=client, 
        app=app, 
        heap=heap, 
        cooldown_time=cooldown_time, 
        live_time=live_time, 
        lock=lock, 
        **request_kwargs, 
    )


def call_wrap_with_pool(get_cert_headers: Callable, /, func: Callable) -> Callable:
    """包装函数，用认证信息请求头的分发池执行请求

    :param get_cert_headers: 获取认证信息的请求头的函数
    :param func: 执行请求的函数
    """
    def wrapper(
        *args, 
        headers: None | Mapping = None, 
        async_: bool = False, 
        **kwds, 
    ):
        def gen_step():
            nonlocal headers
            while True:
                if async_:
                    cert, revert = yield get_cert_headers(async_=True)
                else:
                    cert, revert = get_cert_headers()
                try:
                    if isinstance(cert, Mapping):
                        if headers:
                            headers = dict(headers, **cert)
                        else:
                            headers = cert
                        if async_:
                            resp = yield func(*args, headers=headers, async_=True, **kwds)
                        else:
                            resp = func(*args, headers=headers, **kwds)
                    elif async_:
                        resp = yield func(cert, *args, headers=headers, async_=True, **kwds)
                    else:
                        resp = func(cert, *args, headers=headers, **kwds)
                    if not isinstance(resp, dict) or resp.get("errno") != 40101004:
                        revert()
                    return resp
                except BaseException as e:
                    if isinstance(e, P115OSError) and e.args[1].get("errno") == 40101004:
                        raise
                    if not isinstance(e, (P115AuthenticationError, P115LoginError)) and get_status_code(e) != 405:
                        revert()
                        raise
        return run_gen_step(gen_step, async_)
    return update_wrapper(wrapper, func)


# TODO: 需要完整的类型签名
# TODO: 池子可以被导出，下次继续使用
# TODO: 支持多个不同设备的 cookies 组成池，以及刷新（自己刷新自己，或者由另一个 cookies 辅助刷新）
