#!/usr/bin/env python3
# encoding: utf-8

__author__ = "ChenyangGao <https://chenyanggao.github.io>"
__all__ = [
    "BEHAVIOR_TYPE_TO_NAME", "BEHAVIOR_NAME_TO_TYPE", "life_show", "iter_life_list", 
    "iter_life_behavior_once", "iter_life_behavior", "iter_life_behavior_list", 
]
__doc__ = "这个模块提供了一些和 115 生活操作事件有关的函数"

from asyncio import sleep as async_sleep
from collections.abc import AsyncIterator, Container, Coroutine, Iterator
from functools import partial
from itertools import cycle
from os import PathLike
from time import time, sleep
from typing import overload, Any, Final, Literal

from iterutils import run_gen_step_iter, with_iter_next, Yield

from ..client import check_response, P115Client


# 115 生活操作事件，默认在迭代时会被忽略的一些事件（都是一些浏览而不是改动的操作）
IGNORE_BEHAVIOR_TYPES: Final = frozenset((3, 4, 7, 8, 9, 10, 19))
#: 115 生活操作事件名称到类型的映射
BEHAVIOR_NAME_TO_TYPE: Final = {
    "upload_image_file": 1, 
    "upload_file": 2, 
    "star_image": 3, 
    "star_file": 4, 
    "move_image_file": 5, 
    "move_file": 6, 
    "browse_image": 7, 
    "browse_video": 8, 
    "browse_audio": 9, 
    "browse_document": 10, 
    "receive_files": 14, 
    "new_folder": 17, 
    "copy_folder": 18, 
    "folder_label": 19, 
    "folder_rename": 20, 
    "delete_file": 22, 
}
#: 115 生活操作事件类型到名称的映射
BEHAVIOR_TYPE_TO_NAME: Final = {v: k for k, v in BEHAVIOR_NAME_TO_TYPE.items()}


@overload
def life_show(
    client: str | PathLike | P115Client, 
    *, 
    async_: Literal[False] = False, 
    **request_kwargs, 
) -> dict:
    ...
@overload
def life_show(
    client: str | PathLike | P115Client, 
    *, 
    async_: Literal[True], 
    **request_kwargs, 
) -> Coroutine[Any, Any, dict]:
    ...
def life_show(
    client: str | PathLike | P115Client, 
    *, 
    async_: Literal[False, True] = False, 
    **request_kwargs, 
) -> dict | Coroutine[Any, Any, dict]:
    """确保 115 生活的事件列表为开启状态

    :param client: 115 客户端或 cookies
    :param async_: 是否异步
    :param request_kwargs: 其它请求参数

    :return: 接口返回值
    """
    if isinstance(client, (str, PathLike)):
        client = P115Client(client, check_for_relogin=True)
    return client.life_calendar_setoption(async_=async_, **request_kwargs)


@overload
def iter_life_list(
    client: str | PathLike | P115Client, 
    start_time: int | float = 0, 
    app: str = "web", 
    *, 
    async_: Literal[False] = False, 
    **request_kwargs, 
) -> Iterator[dict]:
    ...
@overload
def iter_life_list(
    client: str | PathLike | P115Client, 
    start_time: int | float = 0, 
    app: str = "web", 
    *, 
    async_: Literal[True], 
    **request_kwargs, 
) -> AsyncIterator[dict]:
    ...
def iter_life_list(
    client: str | PathLike | P115Client, 
    start_time: int | float = 0, 
    app: str = "web", 
    *, 
    async_: Literal[False, True] = False, 
    **request_kwargs, 
) -> AsyncIterator[dict] | Iterator[dict]:
    """持续拉取 115 生活操作事件列表

    .. caution::
        115 并没有收集 复制文件 和 文件改名 的事件，以及第三方上传可能会没有 上传事件 ("upload_image_file" 和 "upload_file")

        也没有从回收站的还原文件或目录的事件，但是只要你还原了，以前相应的删除事件就会消失

    :param client: 115 客户端或 cookies
    :param start_time: 开始时间（不含），若为 0 则从上 1 秒开始
    :param app: 使用某个 app （设备）的接口
    :param async_: 是否异步
    :param request_kwargs: 其它请求参数

    :return: 迭代器，产生 115 生活操作事件日志数据字典
    """
    if isinstance(client, (str, PathLike)):
        client = P115Client(client, check_for_relogin=True)
    life_list = partial(client.life_list, app=app, **request_kwargs)
    life_behavior_detail = partial(client.life_behavior_detail_app, **request_kwargs)
    def gen_step():
        nonlocal start_time
        end_time = int(time())
        if start_time == 0:
            start_time = end_time - 2
        while True:
            resp = yield life_list({"show_type": 0, "start_time": start_time, "end_time": end_time}, async_=async_)
            data = check_response(resp)["data"]
            if data["count"]:
                for items in data["list"]:
                    if "items" not in items:
                        if start_time < items["update_time"] < end_time:
                            yield Yield(items)
                        continue
                    behavior_type = items["behavior_type"]
                    date = items["date"]
                    for item in items["items"]:
                        item["behavior_type"] = behavior_type
                        item["date"] = date
                        yield Yield(item)
                    if behavior_type.startswith("upload_") or items["total"] > len(items["items"]):
                        seen_items: set[str] = {item["id"] for item in items["items"]}
                        payload = {"offset": 0, "limit": 32, "type": behavior_type, "date": date}
                        while True:
                            resp = yield life_behavior_detail(payload, async_=async_)
                            for item in check_response(resp)["data"]["list"]:
                                if item["id"] in seen_items or item["update_time"] >= end_time:
                                    continue
                                elif item["update_time"] <= start_time:
                                    break
                                seen_items.add(item["id"])
                                item["behavior_type"] = behavior_type
                                item["date"] = date
                                yield Yield(item)
                            else:
                                if not resp["data"]["next_page"]:
                                    break
                                payload["offset"] += 32
                                continue
                            break
                start_time = data["list"][0]["update_time"]
            if (diff := time() - end_time) < 1:
                if async_:
                    yield async_sleep(1 - diff)
                else:
                    sleep(1 - diff)
            end_time = int(time())
    return run_gen_step_iter(gen_step, async_)


@overload
def iter_life_behavior_once(
    client: str | PathLike | P115Client, 
    from_id: int = 0, 
    from_time: float = 0, 
    type: str = "", 
    ignore_types: None | Container[int] = IGNORE_BEHAVIOR_TYPES, 
    date: str = "", 
    first_batch_size = 0, 
    app: str = "web", 
    cooldown: float = 0, 
    *, 
    async_: Literal[False] = False, 
    **request_kwargs, 
) -> Iterator[dict]:
    ...
@overload
def iter_life_behavior_once(
    client: str | PathLike | P115Client, 
    from_id: int = 0, 
    from_time: float = 0, 
    type: str = "", 
    ignore_types: None | Container[int] = IGNORE_BEHAVIOR_TYPES, 
    date: str = "", 
    first_batch_size = 0, 
    app: str = "web", 
    cooldown: float = 0, 
    *, 
    async_: Literal[True], 
    **request_kwargs, 
) -> AsyncIterator[dict]:
    ...
def iter_life_behavior_once(
    client: str | PathLike | P115Client, 
    from_id: int = 0, 
    from_time: float = 0, 
    type: str = "", 
    ignore_types: None | Container[int] = IGNORE_BEHAVIOR_TYPES, 
    date: str = "", 
    first_batch_size = 0, 
    app: str = "web", 
    cooldown: float = 0, 
    *, 
    async_: Literal[False, True] = False, 
    **request_kwargs, 
) -> AsyncIterator[dict] | Iterator[dict]:
    """拉取一组 115 生活操作事件

    .. note::
        当你指定有 ``from_id != 0`` 时，如果 from_time 为 0，则自动重设为 -1

    .. caution::
        115 并没有收集 复制文件 和 文件改名 的事件，以及第三方上传可能会没有 上传事件 ("upload_image_file" 和 "upload_file")

        也没有从回收站的还原文件或目录的事件，但是只要你还原了，以前相应的删除事件就会消失

    :param client: 115 客户端或 cookies
    :param from_id: 开始的事件 id （不含）
    :param from_time: 开始时间（含），若为 0 则从当前时间开始，若 < 0 则从最早开始
    :param type: 指定拉取的操作事件名称，若不指定则是全部
    :param ignore_types: 一组要被忽略的操作事件类型代码，仅当 `type` 为空时生效
    :param date: 日期，格式为 YYYY-MM-DD，若指定则只拉取这一天的数据
    :param first_batch_size: 首批的拉取数目
    :param app: 使用某个 app （设备）的接口
    :param cooldown: 冷却时间，大于 0 时，两次接口调用之间至少间隔这么多秒
    :param async_: 是否异步
    :param request_kwargs: 其它请求参数

    :return: 迭代器，产生 115 生活操作事件日志数据字典
    """
    if isinstance(client, (str, PathLike)):
        client = P115Client(client, check_for_relogin=True)
    if app in ("", "web", "desktop", "harmony"):
        life_behavior_detail = partial(client.life_behavior_detail, **request_kwargs)
    else:
        life_behavior_detail = partial(client.life_behavior_detail_app, app=app, **request_kwargs)
    if first_batch_size <= 0:
        first_batch_size = 64 if from_time or from_id else 1000
    if from_id and not from_time:
        from_time = -1
    def gen_step():
        payload = {"type": type, "date": date, "limit": first_batch_size, "offset": 0}
        seen: set[str] = set()
        seen_add = seen.add
        ts_last_call = time()
        resp = yield life_behavior_detail(payload, async_=async_)
        events = check_response(resp)["data"]["list"]
        payload["limit"] = 1000
        offset = 0
        while events:
            for event in events:
                if (from_id and int(event["id"]) <= from_id or 
                    from_time and "update_time" in event and int(event["update_time"]) < from_time
                ):
                    return
                event_type = event["type"]
                fid = event["file_id"]
                if fid not in seen:
                    if type or not ignore_types or event_type not in ignore_types:
                        event["event_name"] = BEHAVIOR_TYPE_TO_NAME.get(event_type, "")
                        yield Yield(event)
                    seen_add(fid)
            offset += len(events)
            if offset >= int(resp["data"]["count"]):
                return
            payload["offset"] = offset
            if cooldown > 0 and (delta := ts_last_call + cooldown - time()) > 0:
                if async_:
                    yield async_sleep(delta)
                else:
                    sleep(delta)
            ts_last_call = time()
            resp = yield life_behavior_detail(payload, async_=async_)
            events = check_response(resp)["data"]["list"]
    return run_gen_step_iter(gen_step, async_)


@overload
def iter_life_behavior(
    client: str | PathLike | P115Client, 
    from_id: int = 0, 
    from_time: float = 0, 
    type: str = "", 
    ignore_types: None | Container[int] = IGNORE_BEHAVIOR_TYPES, 
    app: str = "web", 
    cooldown: float = 0, 
    interval: int | float = 0, 
    *, 
    async_: Literal[False] = False, 
    **request_kwargs, 
) -> Iterator[dict]:
    ...
@overload
def iter_life_behavior(
    client: str | PathLike | P115Client, 
    from_id: int = 0, 
    from_time: float = 0, 
    type: str = "", 
    ignore_types: None | Container[int] = IGNORE_BEHAVIOR_TYPES, 
    app: str = "web", 
    cooldown: float = 0, 
    interval: int | float = 0, 
    *, 
    async_: Literal[True], 
    **request_kwargs, 
) -> AsyncIterator[dict]:
    ...
def iter_life_behavior(
    client: str | PathLike | P115Client, 
    from_id: int = 0, 
    from_time: float = 0, 
    type: str = "", 
    ignore_types: None | Container[int] = IGNORE_BEHAVIOR_TYPES, 
    app: str = "web", 
    cooldown: float = 0, 
    interval: int | float = 0, 
    *, 
    async_: Literal[False, True] = False, 
    **request_kwargs, 
) -> AsyncIterator[dict] | Iterator[dict]:
    """持续拉取 115 生活操作事件

    .. note::
        当你指定有 ``from_id != 0`` 时，如果 from_time 为 0，则自动重设为 -1

    .. caution::
        115 并没有收集 复制文件 和 文件改名 的事件，以及第三方上传可能会没有 上传事件 ("upload_image_file" 和 "upload_file")

        也没有从回收站的还原文件或目录的事件，但是只要你还原了，以前相应的删除事件就会消失

    :param client: 115 客户端或 cookies
    :param from_id: 开始的事件 id （不含）
    :param from_time: 开始时间（含），若为 0 则从当前时间开始，若 < 0 则从最早开始
    :param type: 指定拉取的操作事件名称
    :param ignore_types: 一组要被忽略的操作事件类型代码，仅当 `type` 为空时生效
    :param cooldown: 冷却时间，大于 0 时，两次接口调用之间至少间隔这么多秒
    :param interval: 两个批量拉取之间的睡眠时间间隔，如果小于等于 0，则不睡眠
    :param app: 使用某个 app （设备）的接口
    :param async_: 是否异步
    :param request_kwargs: 其它请求参数

    :return: 迭代器，产生 115 生活操作事件日志数据字典
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
            with with_iter_next(iter_life_behavior_once(
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
def iter_life_behavior_list(
    client: str | PathLike | P115Client, 
    from_id: int = 0, 
    from_time: float = 0, 
    type: str = "", 
    ignore_types: None | Container[int] = IGNORE_BEHAVIOR_TYPES, 
    app: str = "web", 
    cooldown: float = 0, 
    *, 
    async_: Literal[False] = False, 
    **request_kwargs, 
) -> Iterator[list[dict]]:
    ...
@overload
def iter_life_behavior_list(
    client: str | PathLike | P115Client, 
    from_id: int = 0, 
    from_time: float = 0, 
    type: str = "", 
    ignore_types: None | Container[int] = IGNORE_BEHAVIOR_TYPES, 
    app: str = "web", 
    cooldown: float = 0, 
    *, 
    async_: Literal[True], 
    **request_kwargs, 
) -> AsyncIterator[list[dict]]:
    ...
def iter_life_behavior_list(
    client: str | PathLike | P115Client, 
    from_id: int = 0, 
    from_time: float = 0, 
    type: str = "", 
    ignore_types: None | Container[int] = IGNORE_BEHAVIOR_TYPES, 
    app: str = "web", 
    cooldown: float = 0, 
    *, 
    async_: Literal[False, True] = False, 
    **request_kwargs, 
) -> AsyncIterator[list[dict]] | Iterator[list[dict]]:
    """持续拉取 115 生活操作事件列表

    .. note::
        当你指定有 ``from_id != 0`` 时，如果 from_time 为 0，则自动重设为 -1

    .. caution::
        115 并没有收集 复制文件 和 文件改名 的事件，以及第三方上传可能会没有 上传事件 ("upload_image_file" 和 "upload_file")

        也没有从回收站的还原文件或目录的事件，但是只要你还原了，以前相应的删除事件就会消失

    :param client: 115 客户端或 cookies
    :param from_id: 开始的事件 id （不含）
    :param from_time: 开始时间（含），若为 0 则从当前时间开始，若 < 0 则从最早开始
    :param type: 指定拉取的操作事件名称
    :param ignore_types: 一组要被忽略的操作事件类型代码，仅当 `type` 为空时生效
    :param app: 使用某个 app （设备）的接口
    :param cooldown: 冷却时间，大于 0 时，两次接口调用之间至少间隔这么多秒
    :param async_: 是否异步
    :param request_kwargs: 其它请求参数

    :return: 迭代器，产生 115 生活操作事件日志数据字典
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
            with with_iter_next(iter_life_behavior_once(
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

