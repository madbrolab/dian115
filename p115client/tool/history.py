#!/usr/bin/env python3
# encoding: utf-8

__author__ = "ChenyangGao <https://chenyanggao.github.io>"
__all__ = [
    "HISTORY_NAME_TO_TYPE", "HISTORY_TYPE_TO_NAME", 
    "iter_history_once", "iter_history", "iter_history_list", 
]
__doc__ = "这个模块提供了一些和 115 的历史记录有关的函数"

from asyncio import sleep as async_sleep
from collections.abc import AsyncIterator, Container, Iterator
from functools import partial
from itertools import cycle
from os import PathLike
from time import time, sleep
from typing import overload, Final, Literal

from iterutils import run_gen_step_iter, with_iter_next, Yield

from ..client import check_response, P115Client


#: 115 生活操作事件名称到类型的映射
HISTORY_NAME_TO_TYPE: Final = {
    "all": 0, 
    "offline_download": 2, 
    "browse_video": 3, 
    "upload": 4, 
    "receive": 7, 
    "move": 8, 
}
#: 115 生活操作事件类型到名称的映射
HISTORY_TYPE_TO_NAME: Final = {v: k for k, v in HISTORY_NAME_TO_TYPE.items()}


@overload
def iter_history_once(
    client: str | PathLike | P115Client, 
    from_id: int = 0, 
    from_time: float = 0, 
    type: int | str = 0, 
    ignore_types: None | Container[int] = None, 
    first_batch_size = 0, 
    app: str = "web", 
    cooldown: int | float = 0, 
    *, 
    async_: Literal[False] = False, 
    **request_kwargs, 
) -> Iterator[dict]:
    ...
@overload
def iter_history_once(
    client: str | PathLike | P115Client, 
    from_id: int = 0, 
    from_time: float = 0, 
    type: int | str = 0, 
    ignore_types: None | Container[int] = None, 
    first_batch_size = 0, 
    app: str = "web", 
    cooldown: int | float = 0, 
    *, 
    async_: Literal[True], 
    **request_kwargs, 
) -> AsyncIterator[dict]:
    ...
def iter_history_once(
    client: str | PathLike | P115Client, 
    from_id: int = 0, 
    from_time: float = 0, 
    type: int | str = 0, 
    ignore_types: None | Container[int] = None, 
    first_batch_size = 0, 
    app: str = "web", 
    cooldown: int | float = 0, 
    *, 
    async_: Literal[False, True] = False, 
    **request_kwargs, 
) -> AsyncIterator[dict] | Iterator[dict]:
    """拉取一组 115 的历史记录

    .. note::
        当你指定有 ``from_id != 0`` 时，如果 from_time 为 0，则自动重设为 -1

    :param client: 115 客户端或 cookies
    :param from_id: 开始的事件 id （不含）
    :param from_time: 开始时间（含），若为 0 则从当前时间开始，若 < 0 则从最早开始
    :param type: 拉取指定类型的历史记录（？？表示还未搞清楚），多个用逗号 "," 隔开

        - 全部: 0
        - ？？: 1
        - 离线下载: 2
        - 播放视频: 3
        - 上传: 4
        - ？？: 5
        - ？？: 6
        - 接收: 7
        - 移动: 8

    :param ignore_types: 一组要被忽略的操作事件类型代码，仅当 `type` 为空时生效
    :param first_batch_size: 首批的拉取数目
    :param app: 使用某个 app （设备）的接口
    :param cooldown: 冷却时间，大于 0 时，两次接口调用之间至少间隔这么多秒
    :param async_: 是否异步
    :param request_kwargs: 其它请求参数

    :return: 迭代器，产生 115 的历史记录数据字典
    """
    if isinstance(client, (str, PathLike)):
        client = P115Client(client, check_for_relogin=True)
    if app in ("", "web", "desktop", "harmony"):
        history_list = partial(client.fs_history_list, **request_kwargs)
    else:
        history_list = partial(client.fs_history_list_app, app=app, **request_kwargs)
    if first_batch_size <= 0:
        first_batch_size = 64 if from_time or from_id else 1150
    if from_id and not from_time:
        from_time = -1
    def gen_step():
        payload = {"type": type, "limit": first_batch_size, "offset": 0}
        seen: set[int] = set()
        seen_add = seen.add
        ts_last_call = time()
        resp = yield history_list(payload, async_=async_)
        events = check_response(resp)["data"]["list"]
        payload["limit"] = 1150
        offset = 0
        while events:
            for event in events:
                event_id = int(event["id"])
                if (from_id and event_id <= from_id or 
                    from_time and "update_time" in event and int(event["update_time"]) < from_time
                ):
                    return
                event_type = event["type"]
                if event_id not in seen:
                    if type or not ignore_types or event_type not in ignore_types:
                        event["event_name"] = HISTORY_TYPE_TO_NAME.get(event_type, "")
                        yield Yield(event)
                    seen_add(event_id)
            offset += len(events)
            if offset >= int(resp["data"]["total"]):
                return
            payload["offset"] = offset
            if cooldown > 0 and (delta := ts_last_call + cooldown - time()) > 0:
                if async_:
                    yield async_sleep(delta)
                else:
                    sleep(delta)
            ts_last_call = time()
            resp = yield history_list(payload, async_=async_)
            events = check_response(resp)["data"]["list"]
    return run_gen_step_iter(gen_step, async_)


@overload
def iter_history(
    client: str | PathLike | P115Client, 
    from_id: int = 0, 
    from_time: float = 0, 
    type: int | str = 0, 
    ignore_types: None | Container[int] = None, 
    app: str = "web", 
    cooldown: int | float = 0, 
    interval: int | float = 0, 
    *, 
    async_: Literal[False] = False, 
    **request_kwargs, 
) -> Iterator[dict]:
    ...
@overload
def iter_history(
    client: str | PathLike | P115Client, 
    from_id: int = 0, 
    from_time: float = 0, 
    type: int | str = 0, 
    ignore_types: None | Container[int] = None, 
    app: str = "web", 
    cooldown: int | float = 0, 
    interval: int | float = 0, 
    *, 
    async_: Literal[True], 
    **request_kwargs, 
) -> AsyncIterator[dict]:
    ...
def iter_history(
    client: str | PathLike | P115Client, 
    from_id: int = 0, 
    from_time: float = 0, 
    type: int | str = 0, 
    ignore_types: None | Container[int] = None, 
    app: str = "web", 
    cooldown: int | float = 0, 
    interval: int | float = 0, 
    *, 
    async_: Literal[False, True] = False, 
    **request_kwargs, 
) -> AsyncIterator[dict] | Iterator[dict]:
    """持续拉取 115 的历史记录

    .. note::
        当你指定有 ``from_id != 0`` 时，如果 from_time 为 0，则自动重设为 -1

    :param client: 115 客户端或 cookies
    :param from_id: 开始的事件 id （不含）
    :param from_time: 开始时间（含），若为 0 则从当前时间开始，若 < 0 则从最早开始
    :param type: 拉取指定类型的历史记录（？？表示还未搞清楚），多个用逗号 "," 隔开

        - 全部: 0
        - ？？: 1
        - 离线下载: 2
        - 播放视频: 3
        - 上传: 4
        - ？？: 5
        - ？？: 6
        - 接收: 7
        - 移动: 8

    :param ignore_types: 一组要被忽略的操作事件类型代码，仅当 `type` 为空时生效
    :param cooldown: 冷却时间，大于 0 时，两次接口调用之间至少间隔这么多秒
    :param interval: 两个批量拉取之间的睡眠时间间隔，如果小于等于 0，则不睡眠
    :param app: 使用某个 app （设备）的接口
    :param async_: 是否异步
    :param request_kwargs: 其它请求参数

    :return: 迭代器，产生 115 的历史记录数据字典
    """
    if isinstance(client, (str, PathLike)):
        client = P115Client(client, check_for_relogin=True)
    if from_id and not from_time:
        from_time = -1
    def gen_step():
        nonlocal from_time, from_id
        if from_time == 0:
            from_time = time()
        first_loop = True
        while True:
            if first_loop:
                first_loop = False
            elif interval > 0:
                if async_:
                    yield async_sleep(interval)
                else:
                    sleep(interval)
            with with_iter_next(iter_history_once(
                client, 
                from_id=from_id, 
                from_time=from_time, 
                type=type, 
                app=app, 
                cooldown=cooldown, 
                async_=async_, 
                **request_kwargs, 
            )) as get_next:
                sub_first_loop = True
                while True:
                    event = yield get_next()
                    if sub_first_loop:
                        from_id = int(event["id"])
                        if "update_time" in event:
                            from_time = int(event["update_time"])
                        else:
                            from_time = 0
                        sub_first_loop = False
                    if not type and ignore_types and event["type"] in ignore_types:
                        continue
                    yield Yield(event)
    return run_gen_step_iter(gen_step, async_)


@overload
def iter_history_list(
    client: str | PathLike | P115Client, 
    from_id: int = 0, 
    from_time: float = 0, 
    type: int | str = 0, 
    ignore_types: None | Container[int] = None, 
    app: str = "web", 
    cooldown: int | float = 0, 
    *, 
    async_: Literal[False] = False, 
    **request_kwargs, 
) -> Iterator[dict]:
    ...
@overload
def iter_history_list(
    client: str | PathLike | P115Client, 
    from_id: int = 0, 
    from_time: float = 0, 
    type: int | str = 0, 
    ignore_types: None | Container[int] = None, 
    app: str = "web", 
    cooldown: int | float = 0, 
    *, 
    async_: Literal[True], 
    **request_kwargs, 
) -> AsyncIterator[dict]:
    ...
def iter_history_list(
    client: str | PathLike | P115Client, 
    from_id: int = 0, 
    from_time: float = 0, 
    type: int | str = 0, 
    ignore_types: None | Container[int] = None, 
    app: str = "web", 
    cooldown: int | float = 0, 
    *, 
    async_: Literal[False, True] = False, 
    **request_kwargs, 
) -> AsyncIterator[dict] | Iterator[dict]:
    """持续拉取 115 的历史记录

    .. note::
        当你指定有 ``from_id != 0`` 时，如果 from_time 为 0，则自动重设为 -1

    :param client: 115 客户端或 cookies
    :param from_id: 开始的事件 id （不含）
    :param from_time: 开始时间（含），若为 0 则从当前时间开始，若 < 0 则从最早开始
    :param type: 拉取指定类型的历史记录（？？表示还未搞清楚），多个用逗号 "," 隔开

        - 全部: 0
        - ？？: 1
        - 离线下载: 2
        - 播放视频: 3
        - 上传: 4
        - ？？: 5
        - ？？: 6
        - 接收: 7
        - 移动: 8

    :param ignore_types: 一组要被忽略的操作事件类型代码，仅当 `type` 为空时生效
    :param cooldown: 冷却时间，大于 0 时，两次接口调用之间至少间隔这么多秒
    :param app: 使用某个 app （设备）的接口
    :param async_: 是否异步
    :param request_kwargs: 其它请求参数

    :return: 迭代器，产生 115 的历史记录数据字典
    """
    if isinstance(client, (str, PathLike)):
        client = P115Client(client, check_for_relogin=True)
    if from_id and not from_time:
        from_time = -1
    def gen_step():
        nonlocal from_time, from_id
        if from_time == 0:
            from_time = time()
        while True:
            ls: list[dict] = []
            push = ls.append
            with with_iter_next(iter_history_once(
                client, 
                from_id=from_id, 
                from_time=from_time, 
                type=type, 
                app=app, 
                cooldown=cooldown, 
                async_=async_, 
                **request_kwargs, 
            )) as get_next:
                first_loop = True
                while True:
                    event = yield get_next()
                    if first_loop:
                        from_id = int(event["id"])
                        if "update_time" in event:
                            from_time = int(event["update_time"])
                        else:
                            from_time = 0
                        first_loop = False
                    if not type and ignore_types and event["type"] in ignore_types:
                        continue
                    push(event)
            yield Yield(ls)
    return run_gen_step_iter(gen_step, async_)

