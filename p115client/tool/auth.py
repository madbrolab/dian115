#!/usr/bin/env python3
# encoding: utf-8

__author__ = "ChenyangGao <https://chenyanggao.github.io>"
__all__ = ["deauth_open"]
__doc__ = "这个模块提供了一些和账号状况有关的函数"

from collections.abc import Callable, Coroutine
from os import PathLike
from typing import overload, Any, Literal

from iterutils import run_gen_step

from ..client import check_response, P115Client


@overload
def deauth_open(
    client: str | PathLike | P115Client, 
    predicate: None | Callable = None, 
    *, 
    async_: Literal[False] = False, 
    **request_kwargs, 
) -> None:
    ...
@overload
def deauth_open(
    client: str | PathLike | P115Client, 
    predicate: None | Callable = None, 
    *, 
    async_: Literal[True], 
    **request_kwargs, 
) -> Coroutine[Any, Any, None]:
    ...
def deauth_open(
    client: str | PathLike | P115Client, 
    predicate: None | Callable = None, 
    *, 
    async_: Literal[False, True] = False, 
    **request_kwargs, 
) -> None | Coroutine[Any, Any, None]:
    """批量解绑开放应用

    :param client: 115 客户端或 cookies
    :param predicate: 筛选条件
    :param async_: 是否异步
    :param request_kwargs: 其它请求参数
    """
    if isinstance(client, (str, PathLike)):
        client = P115Client(client, check_for_relogin=True)
    def gen_step():
        resp = yield client.login_open_auth_list(
            async_=async_, 
            **request_kwargs, 
        )
        check_response(resp)
        for info in filter(predicate, resp["data"]):
            yield client.login_open_deauth(
                info["auth_id"], 
                async_=async_, 
                **request_kwargs, 
            )
    return run_gen_step(gen_step, async_)

