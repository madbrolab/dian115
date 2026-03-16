#!/usr/bin/env python3
# encoding: utf-8

__author__ = "ChenyangGao <https://chenyanggao.github.io>"
__all__ = [
    "wish_info", "wish_make", "wish_answer", "wish_adopt", 
    "wish_del", "wish_iter", "wish_aid_iter", 
]

from collections.abc import AsyncIterator, Coroutine, Iterable, Iterator
from os import PathLike
from typing import overload, Any, Literal

from iterutils import run_gen_step, run_gen_step_iter, YieldFrom

from ..client import check_response, P115Client
from ..type import P115StrID


@overload
def wish_info(
    client: str | PathLike | P115Client, 
    wish_id: str, 
    *, 
    async_: Literal[False] = False, 
    **request_kwargs, 
) -> dict:
    ...
@overload
def wish_info(
    client: str | PathLike | P115Client, 
    wish_id: str, 
    *, 
    async_: Literal[True], 
    **request_kwargs, 
) -> Coroutine[Any, Any, dict]:
    ...
def wish_info(
    client: str | PathLike | P115Client, 
    wish_id: str, 
    *, 
    async_: Literal[False, True] = False, 
    **request_kwargs, 
) -> dict | Coroutine[Any, Any, dict]:
    """许愿树活动：许愿信息

    :param client: 115 客户端或 cookies
    :param wish_id: 许愿 id
    :param async_: 是否异步
    :param request_kwargs: 其它请求参数

    :return: 许愿信息
    """
    if isinstance(client, (str, PathLike)):
        client = P115Client(client)
    def gen_step():
        resp = yield client.act_xys_get_desire_info(
            wish_id, 
            async_=async_, 
            **request_kwargs, 
        )
        check_response(resp)
        return resp["data"]
    return run_gen_step(gen_step, async_)


@overload
def wish_make(
    client: str | PathLike | P115Client, 
    content: str = "随便许个愿", 
    size: int = 5, 
    *, 
    async_: Literal[False] = False, 
    **request_kwargs, 
) -> P115StrID:
    ...
@overload
def wish_make(
    client: str | PathLike | P115Client, 
    content: str = "随便许个愿", 
    size: int = 5, 
    *, 
    async_: Literal[True], 
    **request_kwargs, 
) -> Coroutine[Any, Any, P115StrID]:
    ...
def wish_make(
    client: str | PathLike | P115Client, 
    content: str = "随便许个愿", 
    size: int = 5, 
    *, 
    async_: Literal[False, True] = False, 
    **request_kwargs, 
) -> P115StrID | Coroutine[Any, Any, P115StrID]:
    """许愿树活动：创建许愿（许愿创建后需要等审核）

    :param client: 115 客户端或 cookies
    :param content: 许愿内容
    :param size: 答谢空间大小，单位是 GB
    :param async_: 是否异步
    :param request_kwargs: 其它请求参数

    :return: 许愿 id
    """
    if isinstance(client, (str, PathLike)):
        client = P115Client(client)
    def gen_step():
        resp = yield client.act_xys_wish(
            {"rewardSpace": size, "content": content}, 
            async_=async_, 
            **request_kwargs, 
        )
        check_response(resp)
        return P115StrID(resp["data"]["xys_id"], resp["data"])
    return run_gen_step(gen_step, async_)


@overload
def wish_answer(
    client: str | PathLike | P115Client, 
    wish_id: str, 
    content: str = "帮你助个愿", 
    file_ids: int | str | Iterable[int | str] = "", 
    *, 
    async_: Literal[False] = False, 
    **request_kwargs, 
) -> P115StrID:
    ...
@overload
def wish_answer(
    client: str | PathLike | P115Client, 
    wish_id: str, 
    content: str = "帮你助个愿", 
    file_ids: int | str | Iterable[int | str] = "", 
    *, 
    async_: Literal[True], 
    **request_kwargs, 
) -> Coroutine[Any, Any, P115StrID]:
    ...
def wish_answer(
    client: str | PathLike | P115Client, 
    wish_id: str, 
    content: str = "帮你助个愿", 
    file_ids: int | str | Iterable[int | str] = "", 
    *, 
    async_: Literal[False, True] = False, 
    **request_kwargs, 
) -> P115StrID | Coroutine[Any, Any, P115StrID]:
    """许愿树活动：创建助愿（助愿创建后需要等审核）

    .. note::
        如果从未调用过 `wish_info(client, wish_id)`，请先调用，否则会报参数错误

    :param client: 115 客户端或 cookies
    :param wish_id: 许愿 id
    :param content: 助愿内容
    :param file_ids: 文件在你的网盘的 id，多个用逗号 "," 隔开
    :param async_: 是否异步
    :param request_kwargs: 其它请求参数

    :return: 助愿 id
    """
    if isinstance(client, (str, PathLike)):
        client = P115Client(client)
    if not isinstance(file_ids, (int, str)):
        file_ids = ",".join(map(str, file_ids))
    def gen_step():
        resp = yield client.act_xys_aid_desire(
            {"id": wish_id, "content": content, "file_ids": file_ids}, 
            async_=async_, 
            **request_kwargs, 
        )
        check_response(resp)
        return P115StrID(resp["data"]["aid_id"], resp["data"])
    return run_gen_step(gen_step, async_)


@overload
def wish_adopt(
    client: str | PathLike | P115Client, 
    wish_id: str, 
    aid_id: int | str, 
    to_cid: int = 0, 
    *, 
    async_: Literal[False] = False, 
    **request_kwargs, 
) -> dict:
    ...
@overload
def wish_adopt(
    client: str | PathLike | P115Client, 
    wish_id: str, 
    aid_id: int | str, 
    to_cid: int = 0, 
    *, 
    async_: Literal[True], 
    **request_kwargs, 
) -> Coroutine[Any, Any, dict]:
    ...
def wish_adopt(
    client: str | PathLike | P115Client, 
    wish_id: str, 
    aid_id: int | str, 
    to_cid: int = 0, 
    *, 
    async_: Literal[False, True] = False, 
    **request_kwargs, 
) -> dict | Coroutine[Any, Any, dict]:
    """许愿树活动：采纳助愿

    :param client: 115 客户端或 cookies
    :param wish_id: 许愿 id
    :param aid_id: 助愿 id
    :param to_cid: 助愿的分享文件保存到你的网盘中目录的 id
    :param async_: 是否异步
    :param request_kwargs: 其它请求参数

    :return: 接口的返回信息
    """
    if isinstance(client, (str, PathLike)):
        client = P115Client(client)
    return check_response(client.act_xys_adopt(
        {"did": wish_id, "aid": aid_id, "to_cid": to_cid}, 
        async_=async_, 
        **request_kwargs, 
    ))


@overload
def wish_del(
    client: str | PathLike | P115Client, 
    wish_id: str | Iterable[str], 
    *, 
    async_: Literal[False] = False, 
    **request_kwargs, 
) -> dict:
    ...
@overload
def wish_del(
    client: str | PathLike | P115Client, 
    wish_id: str | Iterable[str], 
    *, 
    async_: Literal[True], 
    **request_kwargs, 
) -> Coroutine[Any, Any, dict]:
    ...
def wish_del(
    client: str | PathLike | P115Client, 
    wish_id: str | Iterable[str], 
    *, 
    async_: Literal[False, True] = False, 
    **request_kwargs, 
) -> dict | Coroutine[Any, Any, dict]:
    """许愿树活动：删除许愿

    :param client: 115 客户端或 cookies
    :param wish_id: 许愿 id
    :param async_: 是否异步
    :param request_kwargs: 其它请求参数

    :return: 接口的返回信息
    """
    if isinstance(client, (str, PathLike)):
        client = P115Client(client)
    if not isinstance(wish_id, str):
        wish_id = ",".join(wish_id)
    return check_response(client.act_xys_wish_del(
        wish_id, 
        async_=async_, 
        **request_kwargs, 
    ))


@overload
def wish_iter(
    client: str | PathLike | P115Client, 
    type: int = 0, 
    page_size: int = 1_000, 
    *, 
    async_: Literal[False] = False, 
    **request_kwargs, 
) -> Iterator[dict]:
    ...
@overload
def wish_iter(
    client: str | PathLike | P115Client, 
    type: int = 0, 
    page_size: int = 1_000, 
    *, 
    async_: Literal[True], 
    **request_kwargs, 
) -> AsyncIterator[dict]:
    ...
def wish_iter(
    client: str | PathLike | P115Client, 
    type: int = 0, 
    page_size: int = 1_000, 
    *, 
    async_: Literal[False, True] = False, 
    **request_kwargs, 
) -> Iterator[dict] | AsyncIterator[dict]:
    """许愿树活动：罗列我的许愿列表

    :param client: 115 客户端或 cookies
    :param type: 类型

        - 0: 全部
        - 1: 进行中
        - 2: 已实现

    :param page_size: 分页大小
    :param async_: 是否异步
    :param request_kwargs: 其它请求参数

    :return: 迭代器，逐个返回许愿许愿信息
    """
    if isinstance(client, (str, PathLike)):
        client = P115Client(client)
    if page_size <= 0:
        page_size = 1_000
    def gen_step():
        payload: dict = {"type": type, "limit": page_size, "page": 1}
        while True:
            resp = yield client.act_xys_my_desire(
                payload, 
                async_=async_, 
                **request_kwargs, 
            )
            check_response(resp)
            ls = resp["data"]["list"]
            yield YieldFrom(ls)
            if not ls:
                break
            payload["page"] += 1
    return run_gen_step_iter(gen_step, async_)


@overload
def wish_aid_iter(
    client: str | PathLike | P115Client, 
    wish_id: str, 
    page_size: int = 1_000, 
    *, 
    async_: Literal[False] = False, 
    **request_kwargs, 
) -> Iterator[dict]:
    ...
@overload
def wish_aid_iter(
    client: str | PathLike | P115Client, 
    wish_id: str, 
    page_size: int = 1_000, 
    *, 
    async_: Literal[True], 
    **request_kwargs, 
) -> AsyncIterator[dict]:
    ...
def wish_aid_iter(
    client: str | PathLike | P115Client, 
    wish_id: str, 
    page_size: int = 1_000, 
    *, 
    async_: Literal[False, True] = False, 
    **request_kwargs, 
) -> Iterator[dict] | AsyncIterator[dict]:
    """许愿树活动：许愿的助愿列表

    :param client: 115 客户端或 cookies
    :param wish_id: 许愿 id
    :param page_size: 分页大小
    :param async_: 是否异步
    :param request_kwargs: 其它请求参数

    :return: 迭代器，逐个返回助愿信息
    """
    if isinstance(client, (str, PathLike)):
        client = P115Client(client)
    if page_size <= 0:
        page_size = 1_000
    def gen_step():
        payload: dict = {"id": wish_id, "limit": page_size, "page": 1}
        while True:
            resp = yield client.act_xys_desire_aid_list(
                payload, 
                async_=async_, 
                **request_kwargs, 
            )
            check_response(resp)
            ls = resp["data"]["list"]
            yield YieldFrom(ls)
            if not ls:
                break
            payload["page"] += 1
    return run_gen_step_iter(gen_step, async_)

# TODO: 再实现一个漂流瓶
