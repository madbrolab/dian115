#!/usr/bin/env python3
# encoding: utf-8

__author__ = "ChenyangGao <https://chenyanggao.github.io>"
__all__ = [
    "iter_fs_files", "iter_fs_files_serialized", "iter_fs_files_threaded", 
    "iter_fs_files_asynchronized", 
]
__doc__ = "这个模块利用 P115Client.fs_files 方法做了一些封装"

from asyncio import (
    shield, sleep as async_sleep, wait_for, 
    Semaphore as AsyncSemaphore, Task, TaskGroup, 
)
from collections import deque
from collections.abc import AsyncIterator, Awaitable, Callable, Iterator
from concurrent.futures import Future, ThreadPoolExecutor
from copy import copy
from inspect import isawaitable
from itertools import cycle
from os import PathLike
from time import sleep, time
from typing import overload, Any, Final, Literal
from warnings import warn

from errno2 import errno
from http_response import get_status_code, is_timeouterror
from iterutils import run_gen_step_iter, Yield

from ..client import check_response, P115Client, P115OpenClient
from ..exception import throw, P115DataError, P115Warning


# get_webapi_origin: Final = cycle(("http://web.api.115.com", "https://webapi.115.com")).__next__
# get_proapi_origin: Final = cycle(("http://pro.api.115.com", "https://proapi.115.com")).__next__
get_webapi_origin: Final = lambda: "https://webapi.115.com"
get_proapi_origin: Final = lambda: "https://proapi.115.com"


@overload
def iter_fs_files(
    client: str | PathLike | P115Client | P115OpenClient, 
    payload: int | str | dict = 0, 
    /, 
    page_size: int = 7_000, 
    first_page_size: int = 0, 
    count: int = -1, 
    callback: None | Callable[[dict], Any] = None, 
    app: str = "web", 
    raise_for_changed_count: bool = False, 
    cooldown: None | float = None, 
    max_workers: None | int = None, 
    *, 
    async_: Literal[False] = False, 
    **request_kwargs, 
) -> Iterator[dict]:
    ...
@overload
def iter_fs_files(
    client: str | PathLike | P115Client | P115OpenClient, 
    payload: int | str | dict = 0, 
    /, 
    page_size: int = 7_000, 
    first_page_size: int = 0, 
    count: int = -1, 
    callback: None | Callable[[dict], Any] = None, 
    app: str = "web", 
    raise_for_changed_count: bool = False, 
    cooldown: None | float = None, 
    max_workers: None | int = None, 
    *, 
    async_: Literal[True], 
    **request_kwargs, 
) -> AsyncIterator[dict]:
    ...
def iter_fs_files(
    client: str | PathLike | P115Client | P115OpenClient, 
    payload: int | str | dict = 0, 
    /, 
    page_size: int = 7_000, 
    first_page_size: int = 0, 
    count: int = -1, 
    callback: None | Callable[[dict], Any] = None, 
    app: str = "web", 
    raise_for_changed_count: bool = False, 
    cooldown: None | float = None, 
    max_workers: None | int = None, 
    *, 
    async_: Literal[False, True] = False, 
    **request_kwargs, 
) -> AsyncIterator[dict] | Iterator[dict]:
    """拉取一个目录中的文件或目录的数据

    :param client: 115 网盘客户端对象
    :param payload: 目录的 id 或者详细的查询参数
    :param page_size: 分页大小，如果 <= 0，则自动确定
    :param first_page_size: 首次拉取的分页大小，如果 <= 0，则自动确定
    :param count: 文件总数
    :param callback: 回调函数，调用后，会获得一个值，会添加到返回值中，key 为 "callback"
    :param app: 使用此设备的接口
    :param raise_for_changed_count: 分批拉取时，发现总数发生变化后，是否报错
    :param cooldown: 冷却时间，单位为秒。如果为 None，则用默认值（非并发时为 0，并发时为 1）
    :param max_workers: 最大并发数，如果为 None 或 < 0 则自动确定，如果为 0 则单工作者惰性执行
    :param async_: 是否异步
    :param request_kwargs: 其它 http 请求参数，会传给具体的请求函数，默认的是 httpx，可用参数 request 进行设置

    :return: 迭代器，每次返回一次接口调用的结果
    """
    if max_workers == 0:
        request_kwargs["async_"] = async_
        method: Callable = iter_fs_files_serialized
    else:
        request_kwargs["max_workers"] = max_workers
        if async_:
            method = iter_fs_files_asynchronized
        else:
            method = iter_fs_files_threaded
    if cooldown is not None:
        request_kwargs["cooldown"] = cooldown
    return method(
        client, 
        payload, 
        page_size=page_size, 
        first_page_size=first_page_size, 
        count=count, 
        callback=callback, 
        app=app, 
        raise_for_changed_count=raise_for_changed_count, 
        **request_kwargs, 
    )


@overload
def iter_fs_files_serialized(
    client: str | PathLike | P115Client | P115OpenClient, 
    payload: int | str | dict = 0, 
    /, 
    page_size: int = 7_000, 
    first_page_size: int = 0, 
    count: int = -1, 
    callback: None | Callable[[dict], Any] = None, 
    app: str = "web", 
    raise_for_changed_count: bool = False, 
    cooldown: float = 0, 
    *, 
    async_: Literal[False] = False, 
    **request_kwargs, 
) -> Iterator[dict]:
    ...
@overload
def iter_fs_files_serialized(
    client: str | PathLike | P115Client | P115OpenClient, 
    payload: int | str | dict = 0, 
    /, 
    page_size: int = 7_000, 
    first_page_size: int = 0, 
    count: int = -1, 
    callback: None | Callable[[dict], Any] = None, 
    app: str = "web", 
    raise_for_changed_count: bool = False, 
    cooldown: float = 0, 
    *, 
    async_: Literal[True], 
    **request_kwargs, 
) -> AsyncIterator[dict]:
    ...
def iter_fs_files_serialized(
    client: str | PathLike | P115Client | P115OpenClient, 
    payload: int | str | dict = 0, 
    /, 
    page_size: int = 7_000, 
    first_page_size: int = 0, 
    count: int = -1, 
    callback: None | Callable[[dict], Any] = None, 
    app: str = "web", 
    raise_for_changed_count: bool = False, 
    cooldown: float = 0, 
    *, 
    async_: Literal[False, True] = False, 
    **request_kwargs, 
) -> AsyncIterator[dict] | Iterator[dict]:
    """拉取一个目录中的文件或目录的数据

    :param client: 115 网盘客户端对象
    :param payload: 目录的 id 或者详细的查询参数
    :param page_size: 分页大小，如果 <= 0，则自动确定
    :param first_page_size: 首次拉取的分页大小，如果 <= 0，则自动确定
    :param count: 文件总数
    :param callback: 回调函数，调用后，会获得一个值，会添加到返回值中，key 为 "callback"
    :param app: 使用此设备的接口
    :param raise_for_changed_count: 分批拉取时，发现总数发生变化后，是否报错
    :param cooldown: 冷却时间，单位为秒
    :param async_: 是否异步
    :param request_kwargs: 其它 http 请求参数，会传给具体的请求函数，默认的是 httpx，可用参数 request 进行设置

    :return: 迭代器，每次返回一次接口调用的结果
    """
    if isinstance(client, (str, PathLike)):
        client = P115Client(client, check_for_relogin=True)
    if page_size <= 0:
        page_size = 7_000
    fs_files: Callable
    if not isinstance(client, P115Client) or app == "open":
        page_size = min(page_size, 1150)
        fs_files = client.fs_files_open
    elif app in ("", "web", "desktop", "harmony"):
        page_size = min(page_size, 1150)
        request_kwargs.setdefault("base_url", get_webapi_origin)
        fs_files = client.fs_files
    elif app == "aps":
        page_size = min(page_size, 1200)
        fs_files = client.fs_files_aps
    else:
        request_kwargs.setdefault("base_url", get_proapi_origin)
        request_kwargs["app"] = app
        fs_files = client.fs_files_app
    if first_page_size <= 0:
        first_page_size = page_size
    if isinstance(payload, (int, str)):
        payload = {"cid": client.to_id(payload)}
    payload = {
        "asc": 1, "cid": 0, "fc_mix": 1, "o": "user_ptime", "offset": 0, 
        "limit": first_page_size, "show_dir": 1, **payload, 
    }
    cid = int(payload["cid"])
    def gen_step():
        nonlocal count, first_page_size
        last_call_ts: float = 0
        while True:
            while True:
                try:
                    if cooldown > 0 and (delta := last_call_ts + cooldown - time()) > 0:
                        if async_:
                            yield async_sleep(delta)
                        else:
                            sleep(delta)
                        last_call_ts = time()
                    resp = yield fs_files(payload, async_=async_, **request_kwargs)
                    check_response(resp)
                except P115DataError:
                    if payload["limit"] <= 1150:
                        raise
                    payload["limit"] -= 1_000
                    if payload["limit"] < 1150:
                        payload["limit"] = 1150
                    continue
                if cid and int(resp["path"][-1]["cid"]) != cid:
                    if count < 0:
                        throw(errno.ENOTDIR, cid)
                    else:
                        throw(errno.ENOENT, cid)
                count_new = int(resp["count"])
                if count < 0:
                    count = count_new
                elif count != count_new:
                    message = f"cid={cid} detected count changes during iteration: {count} -> {count_new}"
                    if raise_for_changed_count:
                        throw(errno.EBUSY, message)
                    else:
                        warn(message, category=P115Warning)
                    count = count_new
                if callback is not None:
                    resp["callback"] = yield callback(resp)
                break
            yield Yield(resp)
            payload["offset"] += len(resp["data"])
            if payload["offset"] >= count:
                break
            if first_page_size != page_size:
                payload["limit"] = page_size
                first_page_size = page_size
    return run_gen_step_iter(gen_step, async_)


def iter_fs_files_threaded(
    client: str | PathLike | P115Client | P115OpenClient, 
    payload: int | str | dict = 0, 
    /, 
    page_size: int = 7_000, 
    first_page_size: int = 0, 
    count: int = -1, 
    callback: None | Callable[[dict], Any] = None, 
    app: str = "web", 
    raise_for_changed_count: bool = False, 
    cooldown: float = 1, 
    max_workers: None | int = None, 
    **request_kwargs, 
) -> Iterator[dict]:
    """多线程并发拉取一个目录中的文件或目录的数据

    :param client: 115 网盘客户端对象
    :param payload: 目录的 id、pickcode 或者详细的查询参数
    :param page_size: 分页大小，如果 <= 0，则自动确定
    :param first_page_size: 第 1 次拉取的分页大小，如果指定此参数，则会等待这次请求返回，才会开始后续，也即非并发
    :param count: 文件总数
    :param callback: 回调函数，调用后，会获得一个值，会添加到返回值中，key 为 "callback"
    :param app: 使用此设备的接口
    :param raise_for_changed_count: 分批拉取时，发现总数发生变化后，是否报错
    :param cooldown: 冷却时间，单位为秒
    :param max_workers: 最大工作线程数，如果为 None，则自动确定
    :param request_kwargs: 其它 http 请求参数，会传给具体的请求函数，默认的是 httpx，可用参数 request 进行设置

    :return: 迭代器
    """
    if isinstance(client, (str, PathLike)):
        client = P115Client(client, check_for_relogin=True)
    if page_size <= 0:
        page_size = 7_000
    fs_files: Callable[..., Awaitable[dict]]
    if not isinstance(client, P115Client) or app == "open":
        page_size = min(page_size, 1150)
        fs_files = client.fs_files_open
    elif app in ("", "web", "desktop", "harmony"):
        page_size = min(page_size, 1150)
        request_kwargs.setdefault("base_url", get_webapi_origin)
        fs_files = client.fs_files
    elif app == "aps":
        page_size = min(page_size, 1200)
        fs_files = client.fs_files_aps
    else:
        request_kwargs.setdefault("base_url", get_proapi_origin)
        request_kwargs["app"] = app
        fs_files = client.fs_files_app
    if isinstance(payload, (int, str)):
        payload = {"cid": client.to_id(payload)}
    if first_page_size <= 0:
        first_page_size = page_size
    payload = {
        "asc": 1, "cid": 0, "fc_mix": 1, "o": "user_ptime", "offset": 0, 
        "limit": first_page_size, "show_dir": 1, **payload, 
    }
    cid = int(payload["cid"])
    def get_files(payload: dict, /):
        nonlocal count
        resp = fs_files(payload, **request_kwargs)
        check_response(resp)
        if cid and int(resp["path"][-1]["cid"]) != cid:
            if count < 0:
                throw(errno.ENOTDIR, cid)
            else:
                throw(errno.ENOENT, cid)
        count_new = int(resp["count"])
        if count < 0:
            count = count_new
        elif count != count_new:
            message = f"cid={cid} detected count changes during iteration: {count} -> {count_new}"
            if raise_for_changed_count:
                throw(errno.EBUSY, message)
            else:
                warn(message, category=P115Warning)
            count = count_new
        if callback is not None:
            resp["callback"] = callback(resp)
        return resp
    dq: deque[tuple[Future, int]] = deque()
    push, pop = dq.append, dq.popleft
    if max_workers is not None and max_workers <= 0:
        max_workers = None
    executor = ThreadPoolExecutor(max_workers=max_workers)
    submit = executor.submit
    last_call_ts: int | float = 0
    def make_future(args: None | dict = None, /) -> Future:
        nonlocal last_call_ts
        if args is None:
            args = copy(payload)
        last_call_ts = time()
        return submit(get_files, args)
    try:
        future = make_future()
        payload["limit"] = page_size
        offset = payload["offset"]
        while True:
            try:
                if first_page_size == page_size:
                    resp = future.result(max(0, last_call_ts + cooldown - time()))
                else:
                    resp = future.result()
                    first_page_size = page_size
            except TimeoutError:
                payload["offset"] += page_size
                if count < 0 or payload["offset"] < count:
                    push((make_future(), payload["offset"]))
            except BaseException as e:
                if get_status_code(e) >= 400 or not is_timeouterror(e):
                    raise
                future = make_future({**payload, "offset": offset})
            else:
                yield resp
                reach_end = offset != resp["offset"] or count >= 0 and offset + len(resp["data"]) >= count
                will_continue = False
                while dq:
                    future, offset = pop()
                    if count < 0 or offset < count:
                        will_continue = True
                        break
                    future.cancel()
                if will_continue:
                    continue
                elif reach_end:
                    break
                else:
                    offset = payload["offset"] = payload["offset"] + page_size
                    if count >= 0 and offset >= count:
                        break
                    future = make_future()
    finally:
        executor.shutdown(False, cancel_futures=True)


async def iter_fs_files_asynchronized(
    client: str | PathLike | P115Client | P115OpenClient, 
    payload: int | str | dict = 0, 
    /, 
    page_size: int = 7_000, 
    first_page_size: int = 0, 
    count: int = -1, 
    callback: None | Callable[[dict], Any] = None, 
    app: str = "web", 
    raise_for_changed_count: bool = False, 
    cooldown: float = 1, 
    max_workers: None | int = None, 
    **request_kwargs, 
) -> AsyncIterator[dict]:
    """异步并发拉取一个目录中的文件或目录的数据

    :param client: 115 网盘客户端对象
    :param payload: 目录的 id、pickcode 或者详细的查询参数
    :param page_size: 分页大小，如果 <= 0，则自动确定
    :param first_page_size: 第 1 次拉取的分页大小，如果指定此参数，则会等待这次请求返回，才会开始后续，也即非并发
    :param count: 文件总数
    :param callback: 回调函数，调用后，会获得一个值，会添加到返回值中，key 为 "callback"
    :param app: 使用此设备的接口
    :param raise_for_changed_count: 分批拉取时，发现总数发生变化后，是否报错
    :param cooldown: 冷却时间，单位为秒
    :param max_workers: 最大工作协程数，如果为 None 或 <= 0，则为 64
    :param request_kwargs: 其它 http 请求参数，会传给具体的请求函数，默认的是 httpx，可用参数 request 进行设置

    :return: 异步迭代器
    """
    if isinstance(client, (str, PathLike)):
        client = P115Client(client, check_for_relogin=True)
    if page_size <= 0:
        page_size = 7_000
    fs_files: Callable[..., Awaitable[dict]]
    if not isinstance(client, P115Client) or app == "open":
        page_size = min(page_size, 1150)
        fs_files = client.fs_files_open
    elif app in ("", "web", "desktop", "harmony"):
        page_size = min(page_size, 1150)
        request_kwargs.setdefault("base_url", get_webapi_origin)
        fs_files = client.fs_files
    elif app == "aps":
        page_size = min(page_size, 1200)
        fs_files = client.fs_files_aps
    else:
        request_kwargs.setdefault("base_url", get_proapi_origin)
        request_kwargs["app"] = app
        fs_files = client.fs_files_app
    if first_page_size <= 0:
        first_page_size = page_size
    if isinstance(payload, (int, str)):
        payload = {"cid": client.to_id(payload)}
    payload = {
        "asc": 1, "cid": 0, "fc_mix": 1, "o": "user_ptime", "offset": 0, 
        "limit": first_page_size, "show_dir": 1, **payload, 
    }
    cid = int(payload["cid"])
    if max_workers is None or max_workers <= 0:
        max_workers = 64
    sema = AsyncSemaphore(max_workers)
    async def get_files(payload: dict, /):
        nonlocal count
        async with sema:
            resp = await fs_files(payload, async_=True, **request_kwargs)
        check_response(resp)
        if cid and int(resp["path"][-1]["cid"]) != cid:
            if count < 0:
                throw(errno.ENOTDIR, cid)
            else:
                throw(errno.ENOENT, cid)
        count_new = int(resp["count"])
        if count < 0:
            count = count_new
        elif count != count_new:
            message = f"cid={cid} detected count changes during iteration: {count} -> {count_new}"
            if raise_for_changed_count:
                throw(errno.EBUSY, message)
            else:
                warn(message, category=P115Warning)
            count = count_new
        if callback is not None:
            ret = callback(resp)
            if isawaitable(ret):
                ret = await ret
            resp["callback"] = ret
        return resp
    dq: deque[tuple[Task, int]] = deque()
    push, pop = dq.append, dq.popleft
    async with TaskGroup() as tg:
        create_task = tg.create_task
        last_call_ts: float = 0
        def make_task(args: None | dict = None, /) -> Task:
            nonlocal last_call_ts
            if args is None:
                args = copy(payload)
            last_call_ts = time()
            return create_task(get_files(args))
        task   = make_task()
        payload["limit"] = page_size
        offset = payload["offset"]
        while True:
            try:
                if first_page_size == page_size:
                    resp = await wait_for(shield(task), max(0, last_call_ts + cooldown - time()))
                else:
                    resp = await task
                    first_page_size = page_size
            except TimeoutError:
                payload["offset"] += page_size
                if count < 0 or payload["offset"] < count:
                    push((make_task(), payload["offset"]))
            except BaseException as e:
                if get_status_code(e) >= 400 or not is_timeouterror(e):
                    raise
                task = make_task({**payload, "offset": offset})
            else:
                yield resp
                reach_end = offset != resp["offset"] or count >= 0 and offset + len(resp["data"]) >= count
                will_continue = False
                while dq:
                    task, offset = pop()
                    if count < 0 or offset < count:
                        will_continue = True
                        break
                    task.cancel()
                if will_continue:
                    continue
                elif reach_end:
                    break
                else:
                    offset = payload["offset"] = payload["offset"] + page_size
                    if count >= 0 and offset >= count:
                        break
                    task = make_task()

# TODO: 这个模块对外暴露，应该只有一个 iter_fs_files，其它接口，fs_files 部分由外部传入
# TODO: 移除 callback 参数
