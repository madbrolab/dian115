#!/usr/bin/env python3
# encoding: utf-8

__author__ = "ChenyangGao <https://chenyanggao.github.io>"
__all__ = [
    "update_abstract", "update_desc", "update_star", "update_label", "update_score", 
    "update_top", "update_show_play_long", "update_category_shortcut", "batch_unstar", 
    "update_name", "post_event", "batch_makedir", "copyfile", "renamefile", "transferfile", 
]
__doc__ = "这个模块提供了一些和修改文件或目录信息有关的函数"

from asyncio import Future as AsyncFuture
from collections.abc import (
    AsyncIterable, AsyncIterator, Callable, Coroutine, Iterable, 
    Iterator, Mapping, 
)
from concurrent.futures import Future
from functools import partial
from itertools import batched
from os import PathLike
from typing import overload, Any, Literal

from concurrenttools import conmap, run_as_thread, run_as_async
from iterutils import chunked, map as do_map, run_gen_step, as_gen_step, through
from p115pickcode import to_id

from ..client import check_response, P115Client, P115OpenClient
from ..type import P115URL


@overload
def update_abstract(
    client: str | PathLike | P115Client, 
    ids: Iterable[int | str], 
    /, 
    method: str, 
    value: Any, 
    batch_size: int = 10_000, 
    max_workers: None | int = None, 
    *, 
    async_: Literal[False] = False, 
    **request_kwargs, 
):
    ...
@overload
def update_abstract(
    client: str | PathLike | P115Client, 
    ids: Iterable[int | str] | AsyncIterable[int | str], 
    /, 
    method: str, 
    value: Any, 
    batch_size: int = 10_000, 
    max_workers: None | int = None, 
    *, 
    async_: Literal[True], 
    **request_kwargs, 
) -> Coroutine:
    ...
def update_abstract(
    client: str | PathLike | P115Client, 
    ids: Iterable[int | str] | AsyncIterable[int | str], 
    /, 
    method: str, 
    value: Any, 
    batch_size: int = 10_000, 
    max_workers: None | int = None, 
    *, 
    async_: Literal[False, True] = False, 
    **request_kwargs, 
):
    """批量设置文件或目录

    :param client: 115 客户端或 cookies
    :param ids: 一组文件或目录的 id 或 pickcode
    :param method: 方法名
    :param value: 要设置的值
    :param batch_size: 批次大小，分批次，每次提交的 id 数
    :param max_workers: 并发工作数，如果为 None 或者 <= 0，则自动确定
    :param async_: 是否异步
    :param request_kwargs: 其它请求参数
    """
    if isinstance(client, (str, PathLike)):
        client = P115Client(client, check_for_relogin=True)
    def gen_step():
        setter = partial(getattr(client, method), async_=async_, **request_kwargs)
        def call(batch, /):
            return check_response(setter(batch, value))
        yield through(conmap(
            call, 
            chunked(do_map(to_id, ids), batch_size), 
            max_workers=max_workers, 
            async_=async_, 
        ))
    return run_gen_step(gen_step, async_)


@overload
def update_desc(
    client: str | PathLike | P115Client, 
    ids: Iterable[int | str], 
    /, 
    desc: str = "", 
    batch_size: int = 10_000, 
    max_workers: None | int = None, 
    app: str = "web", 
    *, 
    async_: Literal[False] = False, 
    **request_kwargs, 
):
    ...
@overload
def update_desc(
    client: str | PathLike | P115Client, 
    ids: Iterable[int | str] | AsyncIterable[int | str], 
    /, 
    desc: str = "", 
    batch_size: int = 10_000, 
    max_workers: None | int = None, 
    app: str = "web", 
    *, 
    async_: Literal[True], 
    **request_kwargs, 
) -> Coroutine:
    ...
def update_desc(
    client: str | PathLike | P115Client, 
    ids: Iterable[int | str] | AsyncIterable[int | str], 
    /, 
    desc: str = "", 
    batch_size: int = 10_000, 
    max_workers: None | int = None, 
    app: str = "web", 
    *, 
    async_: Literal[False, True] = False, 
    **request_kwargs, 
):
    """批量给文件或目录设置备注，此举可更新此文件或目录的 mtime

    :param client: 115 客户端或 cookies
    :param ids: 一组文件或目录的 id 或 pickcode
    :param desc: 备注文本
    :param batch_size: 批次大小，分批次，每次提交的 id 数
    :param max_workers: 并发工作数，如果为 None 或者 <= 0，则自动确定
    :param app: 使用此设备的接口
    :param async_: 是否异步
    :param request_kwargs: 其它请求参数
    """
    if app in ("", "web", "desktop", "harmony"):
        method = "fs_desc_set"
    else:
        method = "fs_desc_set_app"
        request_kwargs["app"] = app
    return update_abstract(
        client, 
        ids, # type: ignore
        method=method, 
        value=desc, 
        batch_size=batch_size, 
        max_workers=max_workers, 
        async_=async_, # type: ignore
        **request_kwargs, 
    )


@overload
def update_star(
    client: str | PathLike | P115Client, 
    ids: Iterable[int | str], 
    /, 
    star: bool = True, 
    batch_size: int = 10_000, 
    max_workers: None | int = None, 
    app: str = "web", 
    *, 
    async_: Literal[False] = False, 
    **request_kwargs, 
):
    ...
@overload
def update_star(
    client: str | PathLike | P115Client, 
    ids: Iterable[int | str] | AsyncIterable[int | str], 
    /, 
    star: bool = True, 
    batch_size: int = 10_000, 
    max_workers: None | int = None, 
    app: str = "web", 
    *, 
    async_: Literal[True], 
    **request_kwargs, 
) -> Coroutine:
    ...
def update_star(
    client: str | PathLike | P115Client, 
    ids: Iterable[int | str] | AsyncIterable[int | str], 
    /, 
    star: bool = True, 
    batch_size: int = 10_000, 
    max_workers: None | int = None, 
    app: str = "web", 
    *, 
    async_: Literal[False, True] = False, 
    **request_kwargs, 
):
    """批量给文件或目录设置星标

    .. note::
        如果一批中有任何一个 id 已经被删除，则这一批直接失败报错

    :param client: 115 客户端或 cookies
    :param ids: 一组文件或目录的 id 或 pickcode
    :param star: 是否设置星标
    :param batch_size: 批次大小，分批次，每次提交的 id 数
    :param max_workers: 并发工作数，如果为 None 或者 <= 0，则自动确定
    :param app: 使用此设备的接口
    :param async_: 是否异步
    :param request_kwargs: 其它请求参数
    """
    if isinstance(client, (str, PathLike)):
        client = P115Client(client, check_for_relogin=True)
    if not isinstance(client, P115Client) or app == "open":
        method = "fs_star_set_open"
    elif app in ("", "web", "desktop", "harmony"):
        method = "fs_star_set"
    else:
        method = "fs_star_set_app"
        request_kwargs["app"] = app
    return update_abstract(
        client, 
        ids, # type: ignore
        method=method, 
        value=star, 
        batch_size=batch_size, 
        max_workers=max_workers, 
        async_=async_, # type: ignore
        **request_kwargs, 
    )


@overload
def update_label(
    client: str | PathLike | P115Client, 
    ids: Iterable[int | str], 
    /, 
    label: int | str = 1, 
    batch_size: int = 10_000, 
    max_workers: None | int = None, 
    app: str = "web", 
    *, 
    async_: Literal[False] = False, 
    **request_kwargs, 
):
    ...
@overload
def update_label(
    client: str | PathLike | P115Client, 
    ids: Iterable[int | str] | AsyncIterable[int | str], 
    /, 
    label: int | str = 1, 
    batch_size: int = 10_000, 
    max_workers: None | int = None, 
    app: str = "web", 
    *, 
    async_: Literal[True], 
    **request_kwargs, 
) -> Coroutine:
    ...
def update_label(
    client: str | PathLike | P115Client, 
    ids: Iterable[int | str] | AsyncIterable[int | str], 
    /, 
    label: int | str = 1, 
    batch_size: int = 10_000, 
    max_workers: None | int = None, 
    app: str = "web", 
    *, 
    async_: Literal[False, True] = False, 
    **request_kwargs, 
):
    """批量给文件或目录设置标签

    :param client: 115 客户端或 cookies
    :param ids: 一组文件或目录的 id 或 pickcode
    :param label: 标签 id，多个用逗号 "," 隔开，如果用一个根本不存在的 id，效果就是清空标签列表
    :param batch_size: 批次大小，分批次，每次提交的 id 数
    :param max_workers: 并发工作数，如果为 None 或者 <= 0，则自动确定
    :param app: 使用此设备的接口
    :param async_: 是否异步
    :param request_kwargs: 其它请求参数
    """
    if app in ("", "web", "desktop", "harmony"):
        method = "fs_label_set"
    else:
        method = "fs_label_set_app"
        request_kwargs["app"] = app
    return update_abstract(
        client, 
        ids, # type: ignore
        method=method, 
        value=label, 
        batch_size=batch_size, 
        max_workers=max_workers, 
        async_=async_, # type: ignore
        **request_kwargs, 
    )


@overload
def update_score(
    client: str | PathLike | P115Client, 
    ids: Iterable[int | str], 
    /, 
    score: int = 0, 
    batch_size: int = 10_000, 
    max_workers: None | int = None, 
    *, 
    async_: Literal[False] = False, 
    **request_kwargs, 
):
    ...
@overload
def update_score(
    client: str | PathLike | P115Client, 
    ids: Iterable[int | str] | AsyncIterable[int | str], 
    /, 
    score: int = 0, 
    batch_size: int = 10_000, 
    max_workers: None | int = None, 
    *, 
    async_: Literal[True], 
    **request_kwargs, 
) -> Coroutine:
    ...
def update_score(
    client: str | PathLike | P115Client, 
    ids: Iterable[int | str] | AsyncIterable[int | str], 
    /, 
    score: int = 0, 
    batch_size: int = 10_000, 
    max_workers: None | int = None, 
    *, 
    async_: Literal[False, True] = False, 
    **request_kwargs, 
):
    """批量给文件或目录设置分数

    :param client: 115 客户端或 cookies
    :param ids: 一组文件或目录的 id 或 pickcode
    :param score: 分数
    :param batch_size: 批次大小，分批次，每次提交的 id 数
    :param max_workers: 并发工作数，如果为 None 或者 <= 0，则自动确定
    :param async_: 是否异步
    :param request_kwargs: 其它请求参数
    """
    return update_abstract(
        client, 
        ids, # type: ignore
        method="fs_score_set", 
        value=score, 
        batch_size=batch_size, 
        max_workers=max_workers, 
        async_=async_, # type: ignore
        **request_kwargs, 
    )


@overload
def update_top(
    client: str | PathLike | P115Client, 
    ids: Iterable[int | str], 
    /, 
    top: bool = True, 
    batch_size: int = 10_000, 
    max_workers: None | int = None, 
    *, 
    async_: Literal[False] = False, 
    **request_kwargs, 
):
    ...
@overload
def update_top(
    client: str | PathLike | P115Client, 
    ids: Iterable[int | str] | AsyncIterable[int | str], 
    /, 
    top: bool = True, 
    batch_size: int = 10_000, 
    max_workers: None | int = None, 
    *, 
    async_: Literal[True], 
    **request_kwargs, 
) -> Coroutine:
    ...
def update_top(
    client: str | PathLike | P115Client, 
    ids: Iterable[int | str] | AsyncIterable[int | str], 
    /, 
    top: bool = True, 
    batch_size: int = 10_000, 
    max_workers: None | int = None, 
    *, 
    async_: Literal[False, True] = False, 
    **request_kwargs, 
):
    """批量给文件或目录设置置顶

    :param client: 115 客户端或 cookies
    :param ids: 一组文件或目录的 id 或 pickcode
    :param score: 分数
    :param batch_size: 批次大小，分批次，每次提交的 id 数
    :param max_workers: 并发工作数，如果为 None 或者 <= 0，则自动确定
    :param async_: 是否异步
    :param request_kwargs: 其它请求参数
    """
    return update_abstract(
        client, 
        ids, # type: ignore
        method="fs_top_set", 
        value=top, 
        batch_size=batch_size, 
        max_workers=max_workers, 
        async_=async_, # type: ignore
        **request_kwargs, 
    )


@overload
def update_show_play_long(
    client: str | PathLike | P115Client, 
    ids: Iterable[int | str], 
    /, 
    show: bool = True, 
    batch_size: int = 10_000, 
    max_workers: None | int = None, 
    app: str = "web", 
    *, 
    async_: Literal[False] = False, 
    **request_kwargs, 
):
    ...
@overload
def update_show_play_long(
    client: str | PathLike | P115Client, 
    ids: Iterable[int | str] | AsyncIterable[int | str], 
    /, 
    show: bool = True, 
    batch_size: int = 10_000, 
    max_workers: None | int = None, 
    app: str = "web", 
    *, 
    async_: Literal[True], 
    **request_kwargs, 
) -> Coroutine:
    ...
def update_show_play_long(
    client: str | PathLike | P115Client, 
    ids: Iterable[int | str] | AsyncIterable[int | str], 
    /, 
    show: bool = True, 
    batch_size: int = 10_000, 
    max_workers: None | int = None, 
    app: str = "web", 
    *, 
    async_: Literal[False, True] = False, 
    **request_kwargs, 
):
    """批量给目录设置显示时长

    :param client: 115 客户端或 cookies
    :param ids: 一组目录的 id 或 pickcode
    :param show: 是否显示时长
    :param batch_size: 批次大小，分批次，每次提交的 id 数
    :param max_workers: 并发工作数，如果为 None 或者 <= 0，则自动确定
    :param app: 使用此设备的接口
    :param async_: 是否异步
    :param request_kwargs: 其它请求参数
    """
    if app in ("", "web", "desktop", "harmony"):
        method = "fs_show_play_long_set"
    else:
        method = "fs_show_play_long_set_app"
        request_kwargs["app"] = app
    return update_abstract(
        client, 
        ids, # type: ignore
        method=method, 
        value=show, 
        batch_size=batch_size, 
        max_workers=max_workers, 
        async_=async_, # type: ignore
        **request_kwargs, 
    )


@overload
def update_category_shortcut(
    client: str | PathLike | P115Client, 
    ids: Iterable[int | str], 
    /, 
    set: bool = True, 
    batch_size: int = 10_000, 
    max_workers: None | int = None, 
    *, 
    async_: Literal[False] = False, 
    **request_kwargs, 
):
    ...
@overload
def update_category_shortcut(
    client: str | PathLike | P115Client, 
    ids: Iterable[int | str] | AsyncIterable[int | str], 
    /, 
    set: bool = True, 
    batch_size: int = 10_000, 
    max_workers: None | int = None, 
    *, 
    async_: Literal[True], 
    **request_kwargs, 
) -> Coroutine:
    ...
def update_category_shortcut(
    client: str | PathLike | P115Client, 
    ids: Iterable[int | str] | AsyncIterable[int | str], 
    /, 
    set: bool = True, 
    batch_size: int = 10_000, 
    max_workers: None | int = None, 
    *, 
    async_: Literal[False, True] = False, 
    **request_kwargs, 
):
    """批量给目录设置显示时长

    :param client: 115 客户端或 cookies
    :param ids: 一组目录的 id 或 pickcode
    :param set: 是否设为快捷入口
    :param batch_size: 批次大小，分批次，每次提交的 id 数
    :param max_workers: 并发工作数，如果为 None 或者 <= 0，则自动确定
    :param async_: 是否异步
    :param request_kwargs: 其它请求参数
    """
    return update_abstract(
        client, 
        ids, # type: ignore
        method="fs_category_shortcut_set", 
        value=set, 
        batch_size=batch_size, 
        max_workers=max_workers, 
        async_=async_, # type: ignore
        **request_kwargs, 
    )


@overload
def batch_unstar(
    client: str | PathLike | P115Client, 
    /, 
    batch_size: int = 10_000, 
    ensure_file: None | bool = None, 
    max_workers: None | int = None, 
    app: str = "web", 
    *, 
    async_: Literal[False] = False, 
    **request_kwargs, 
):
    ...
@overload
def batch_unstar(
    client: str | PathLike | P115Client, 
    /, 
    batch_size: int = 10_000, 
    ensure_file: None | bool = None, 
    max_workers: None | int = None, 
    app: str = "web", 
    *, 
    async_: Literal[True], 
    **request_kwargs, 
) -> Coroutine:
    ...
def batch_unstar(
    client: str | PathLike | P115Client, 
    /, 
    batch_size: int = 10_000, 
    ensure_file: None | bool = None, 
    max_workers: None | int = None, 
    app: str = "web", 
    *, 
    async_: Literal[False, True] = False, 
    **request_kwargs, 
):
    """批量对一批文件或目录取消星标

    :param client: 115 客户端或 cookies
    :param batch_size: 批次大小，分批次，每次提交的 id 数
    :param ensure_file: 是否确保为文件

        - True: 必须是文件
        - False: 必须是目录
        - None: 可以是目录或文件

    :param max_workers: 并发工作数，如果为 None 或者 <= 0，则自动确定
    :param app: 使用此设备的接口
    :param async_: 是否异步
    :param request_kwargs: 其它请求参数
    """
    if isinstance(client, (str, PathLike)):
        client = P115Client(client, check_for_relogin=True)
    def get_id(info: dict, /) -> int:
        for k in ("file_id", "category_id", "fid", "cid"):
            if k in info:
                return int(info[k])
        raise KeyError
    def gen_step():
        from .iterdir import _iter_fs_files
        yield update_star(
            client, 
            do_map(get_id, _iter_fs_files(
                client, 
                payload={
                    "cid": 0, "count_folders": 1, "cur": 0, "fc_mix": 0, 
                    "offset": 0, "show_dir": 1, "star": 1
                }, 
                ensure_file=ensure_file, 
                app=app, 
                cooldown=0.5, 
                async_=async_, 
                **request_kwargs, 
            )), 
            star=False, 
            batch_size=batch_size, 
            max_workers=max_workers, 
            app=app, 
            async_=async_, 
            **request_kwargs, 
        )
    return run_gen_step(gen_step, async_)


@overload
def update_name(
    client: str | PathLike | P115Client, 
    id_name_pairs: Iterable[tuple[int | str, str]], 
    /, 
    batch_size: int = 10_000, 
    post_event_type: None | Literal["doc", "img"] = "img", 
    app: str = "web", 
    *, 
    async_: Literal[False] = False, 
    **request_kwargs, 
) -> list[Future]:
    ...
@overload
def update_name(
    client: str | PathLike | P115Client, 
    id_name_pairs: Iterable[tuple[int | str, str]], 
    /, 
    batch_size: int = 10_000, 
    post_event_type: None | Literal["doc", "img"] = "img", 
    app: str = "web", 
    *, 
    async_: Literal[True], 
    **request_kwargs, 
) -> Coroutine[Any, Any, list[AsyncFuture]]:
    ...
def update_name(
    client: str | PathLike | P115Client, 
    id_name_pairs: Iterable[tuple[int | str, str]], 
    /, 
    batch_size: int = 10_000, 
    post_event_type: None | Literal["doc", "img"] = "img", 
    app: str = "web", 
    *, 
    async_: Literal[False, True] = False, 
    **request_kwargs, 
) -> list[Future] | Coroutine[Any, Any, list[AsyncFuture]]:
    """批量给文件或目录设置名字

    :param client: 115 客户端或 cookies
    :param id_name_pairs: 一堆文件或目录的 id 到新名字的元组
    :param batch_size: 批次大小，分批次，每次提交的任务数
    :param post_event_type: 推送事件类型，如果为 None，则不推送
    :param app: 使用此设备的接口
    :param async_: 是否异步
    :param request_kwargs: 其它请求参数

    :return: 返回推送事件的 Future 对象列表（因为是并发执行的）
    """
    if isinstance(client, (str, PathLike)):
        client = P115Client(client, check_for_relogin=True)
    if app in ("", "web", "desktop", "harmony"):
        method: Callable = client.fs_rename
    else:
        method = client.fs_rename_app
        request_kwargs["app"] = app
    if async_:
        run: Callable = run_as_async
    else:
        run = run_as_thread
    def gen_step():
        futures: list = []
        for batch in batched(id_name_pairs, batch_size):
            resp = yield method(
                batch, 
                async_=async_, 
                **request_kwargs, 
            )
            check_response(resp)
            if post_event_type and resp["data"]:
                futures.append(run(
                    post_event, 
                    client, 
                    resp["data"].keys(), 
                    type=post_event_type, 
                    batch_size=batch_size, 
                    max_workers=1, 
                    app=app, 
                    async_=async_, 
                    **request_kwargs, 
                ))
        return futures
    return run_gen_step(gen_step, async_)


# TODO: 是否能批量推送 "browse_audio" 或 "browse_video" 事件？
@overload
def post_event(
    client: str | PathLike | P115Client, 
    ids: Iterable[int | str], 
    /, 
    type: Literal["doc", "img"] = "doc", 
    batch_size: int = 10_000, 
    max_workers: None | int = None, 
    app: str = "android", 
    *, 
    async_: Literal[False] = False, 
    **request_kwargs, 
) -> None:
    ...
@overload
def post_event(
    client: str | PathLike | P115Client, 
    ids: Iterable[int | str] | AsyncIterable[int | str], 
    /, 
    type: Literal["doc", "img"] = "doc", 
    batch_size: int = 10_000, 
    max_workers: None | int = None, 
    app: str = "android", 
    *, 
    async_: Literal[True], 
    **request_kwargs, 
) -> Coroutine:
    ...
def post_event(
    client: str | PathLike | P115Client, 
    ids: Iterable[int | str] | AsyncIterable[int | str], 
    /, 
    type: Literal["doc", "img"] = "doc", 
    batch_size: int = 10_000, 
    max_workers: None | int = None, 
    app: str = "android", 
    *, 
    async_: Literal[False, True] = False, 
    **request_kwargs, 
) -> None | Coroutine:
    """批量将文件或目录推送事件

    :param client: 115 客户端或 cookies
    :param ids: 一组文件或目录的 id 或 pickcode
    :param type: 事件类型

        - "doc": 推送 "browse_document" 事件
        - "img": 推送 "browse_image" 事件

    :param batch_size: 批次大小，分批次，每次提交的 id 数
    :param max_workers: 并发工作数，如果为 None 或者 <= 0，则自动确定
    :param app: 使用此设备的接口
    :param async_: 是否异步
    :param request_kwargs: 其它请求参数
    """
    if isinstance(client, (str, PathLike)):
        client = P115Client(client, check_for_relogin=True)
    if type == "doc":
        post = client.life_behavior_doc_post_app
    else:
        post = client.life_behavior_img_post_app
    def call(batch, /):
        return check_response(post(
            batch, 
            app=app, 
            async_=async_, 
            request_kwargs=request_kwargs, 
        ))
    def gen_step():
        yield through(conmap(
            call, 
            chunked(do_map(to_id, ids), batch_size), 
            max_workers=max_workers, 
            async_=async_, 
        ))
    return run_gen_step(gen_step, async_)


@overload
def batch_makedir(
    client: str | PathLike | P115Client, 
    pairs: Iterable[str | tuple[int | str, str]], 
    /, 
    pid: int | str = 0, 
    contain_dir: bool = False, 
    max_workers: None | int = None, 
    *, 
    async_: Literal[False] = False, 
    **request_kwargs, 
) -> Iterator[tuple[str | tuple[int | str, str], dict]]:
    ...
@overload
def batch_makedir(
    client: str | PathLike | P115Client, 
    pairs: Iterable[str | tuple[int | str, str]], 
    /, 
    pid: int | str = 0, 
    contain_dir: bool = False, 
    max_workers: None | int = None, 
    *, 
    async_: Literal[True], 
    **request_kwargs, 
) -> AsyncIterator[tuple[str | tuple[int | str, str], dict]]:
    ...
def batch_makedir(
    client: str | PathLike | P115Client, 
    pairs: Iterable[str | tuple[int | str, str]], 
    /, 
    pid: int | str = 0, 
    contain_dir: bool = False, 
    max_workers: None | int = None, 
    *, 
    async_: Literal[False, True] = False, 
    **request_kwargs, 
) -> Iterator[tuple[str | tuple[int | str, str], dict]] | AsyncIterator[tuple[str | tuple[int | str, str], dict]]:
    """批量创建目录

    :param client: 115 客户端或 cookies
    :param pairs: 一系列的 **名字或相对路径** 或者 (**目录的 id 或 pickcode**, **名字或相对路径**) 的 2 元组
    :param pid: 目录的 id 或 pickcode，如果输入的是 **名字或相对路径**，则创建在此目录下
    :param contain_dir: 如果为 True，则要创建的是相对路径，否则就是一个文件（即使其中包含 "/"）
    :param max_workers: 并发工作数，如果为 None 或者 <= 0，则自动确定
    :param async_: 是否异步
    :param request_kwargs: 其它请求参数

    :return: 迭代器，产生 (**每项输入**, **相应的接口响应**) 的 2 元组
    """
    if isinstance(client, (str, PathLike)):
        client = P115Client(client, check_for_relogin=True)
    pid = to_id(pid)
    if contain_dir:
        makedir = client.fs_makedirs_app
    else:
        makedir = client.fs_mkdir_app
    @as_gen_step
    def call[T: (str, tuple[int | str, str])](pair: T, /):
        if isinstance(pair, tuple):
            cid, name = pair
            cid = to_id(cid)
        else:
            cid = pid
            name = pair
        return pair, (yield makedir(name, pid=cid, async_=async_, **request_kwargs))
    return conmap(
        call, 
        pairs, 
        max_workers=max_workers, 
        async_=async_, 
    )


@overload
def copyfile(
    client: str | PathLike | P115Client | P115OpenClient, 
    id: int | str | Mapping, 
    /, 
    name: str = "", 
    pid: None | int | str = None, 
    app: str = "web", 
    *, 
    async_: Literal[False] = False, 
    **request_kwargs, 
) -> dict:
    ...
@overload
def copyfile(
    client: str | PathLike | P115Client | P115OpenClient, 
    id: int | str | Mapping, 
    /, 
    name: str = "", 
    pid: None | int | str = None, 
    app: str = "web", 
    *, 
    async_: Literal[True], 
    **request_kwargs, 
) -> Coroutine[Any, Any, dict]:
    ...
def copyfile(
    client: str | PathLike | P115Client | P115OpenClient, 
    id: int | str | Mapping, 
    /, 
    name: str = "", 
    pid: None | int | str = None, 
    app: str = "web", 
    *, 
    async_: Literal[False, True] = False, 
    **request_kwargs, 
) -> dict | Coroutine[Any, Any, dict]:
    """复制文件到目标目录下

    .. note::
        如果复制后的文件名相同，则使用复制接口，否则使用上传接口

    :param client: 115 客户端或 cookies
    :param id: 文件的 id、pickcode 或信息字典
    :param name: 复制后的新名字，如果为空则名字相同
    :param pid: 目录的 id 或 pickcode，如果为 None，则在同一目录下
    :param app: 使用指定 app（设备）的接口
    :param async_: 是否异步
    :param request_kwargs: 其它请求参数

    :return: 接口响应信息
    """
    if isinstance(client, (str, PathLike)):
        client = P115Client(client, check_for_relogin=True)
    if not isinstance(client, P115Client) or app == "open":
        get_url: Callable = client.download_url_open
        fs_copy: Callable = client.fs_copy_open
        upload_file_init: Callable = client.upload_file_init_open
    else:
        get_url = client.download_url
        upload_file_init = client.upload_file_init
        if app in ("", "web", "desktop", "harmony"):
            fs_copy = client.fs_copy
        else:
            if isinstance(id, Mapping):
                get_url = partial(get_url, app=app)
            fs_copy = partial(client.fs_copy_app, app=app)
    def gen_step():
        nonlocal pid, name
        url: None | P115URL = None
        if isinstance(id, Mapping):
            attr: Mapping = id
        else:
            url = yield get_url(
                client.to_pickcode(id), 
                async_=async_, 
                **request_kwargs, 
            )
            attr = url.__dict__
        if pid is None:
            pid = attr["parent_id"]
        else:
            pid = client.to_id(pid)
        if not name:
            name = attr["name"]
        if attr["name"] == name:
            if pid == attr["parent_id"]:
                return {"state": True}
            return check_response(fs_copy(attr["id"], pid=pid, async_=async_, **request_kwargs))
        else:
            @as_gen_step
            def read_range_bytes_or_hash(sign_check: str, /):
                nonlocal url
                if url is None:
                    url = yield get_url(
                        attr.get("pickcode") or client.to_pickcode(attr["id"]), 
                        async_=async_, 
                        **request_kwargs, 
                    )
                return client.request(
                    url, 
                    async_=async_, 
                    **{
                        **request_kwargs, 
                        "headers": {**url.headers, "range": "bytes="+sign_check}, 
                        "parse": False, 
                    }
                )
            return check_response(upload_file_init(
                filename=name, 
                filesha1=attr["sha1"], 
                filesize=attr["size"], 
                read_range_bytes_or_hash=read_range_bytes_or_hash, 
                pid=pid, 
                async_=async_, 
                **request_kwargs, 
            ))
    return run_gen_step(gen_step, async_)


@overload
def renamefile(
    client: str | PathLike | P115Client | P115OpenClient, 
    id: int | str | Mapping, 
    /, 
    name: str = "", 
    pid: None | int | str = None, 
    app: str = "web", 
    *, 
    async_: Literal[False] = False, 
    **request_kwargs, 
) -> dict:
    ...
@overload
def renamefile(
    client: str | PathLike | P115Client | P115OpenClient, 
    id: int | str | Mapping, 
    /, 
    name: str = "", 
    pid: None | int | str = None, 
    app: str = "web", 
    *, 
    async_: Literal[True], 
    **request_kwargs, 
) -> Coroutine[Any, Any, dict]:
    ...
def renamefile(
    client: str | PathLike | P115Client | P115OpenClient, 
    id: int | str | Mapping, 
    /, 
    name: str = "", 
    pid: None | int | str = None, 
    app: str = "web", 
    *, 
    async_: Literal[False, True] = False, 
    **request_kwargs, 
) -> dict | Coroutine[Any, Any, dict]:
    """移动文件到目标目录下

    .. note::
        如果移动后的文件名相同或扩展名相同，则使用移动接口，否则使用上传接口

    :param client: 115 客户端或 cookies
    :param id: 文件的 id、pickcode 或信息字典
    :param name: 移动后的新名字，如果为空则名字相同
    :param pid: 目录的 id 或 pickcode，如果为 None，则不进行移动
    :param app: 使用指定 app（设备）的接口
    :param async_: 是否异步
    :param request_kwargs: 其它请求参数

    :return: 接口响应信息
    """
    if isinstance(client, (str, PathLike)):
        client = P115Client(client, check_for_relogin=True)
    if not isinstance(client, P115Client) or app == "open":
        get_url: Callable = client.download_url_open
        fs_move: Callable = client.fs_move_open
        upload_file_init: Callable = client.upload_file_init_open
        fs_delete: Callable = client.fs_delete_open
        fs_rename: Callable = client.fs_rename_open
    else:
        get_url = client.download_url
        upload_file_init = client.upload_file_init
        if app in ("", "web", "desktop", "harmony"):
            fs_move = client.fs_move
            fs_delete = client.fs_delete
            fs_rename = client.fs_rename
        else:
            if isinstance(id, Mapping):
                get_url = partial(get_url, app=app)
            fs_move = partial(client.fs_move_app, app=app)
            fs_delete = partial(client.fs_delete_app, app=app)
            fs_rename = partial(client.fs_rename_app, app=app)
    def gen_step():
        nonlocal pid, name
        url: None | P115URL = None
        if isinstance(id, Mapping):
            attr: Mapping = id
        else:
            url = yield get_url(
                client.to_pickcode(id), 
                async_=async_, 
                **request_kwargs, 
            )
            attr = url.__dict__
        if pid is None:
            pid = attr["parent_id"]
        else:
            pid = client.to_id(pid)
        if not name:
            name = attr["name"]
        is_same_name = attr["name"] == name
        is_same_ext = attr["name"].rpartition(".")[-1] == name.rpartition(".")[-1]
        if is_same_name or is_same_ext:
            if pid == attr["parent_id"]:
                if is_same_name:
                    return {"state": True}
            else:
                resp = yield check_response(fs_move(attr["id"], pid=pid, async_=async_, **request_kwargs))
                check_response(resp)
                if is_same_name:
                    return resp
            return check_response(fs_rename((attr["id"], name), async_=async_, **request_kwargs))
        else:
            @as_gen_step
            def read_range_bytes_or_hash(sign_check: str, /):
                nonlocal url
                if url is None:
                    url = yield get_url(
                        attr.get("pickcode") or client.to_pickcode(attr["id"]), 
                        async_=async_, 
                        **request_kwargs, 
                    )
                return client.request(
                    url, 
                    async_=async_, 
                    **{
                        **request_kwargs, 
                        "headers": {**url.headers, "range": "bytes="+sign_check}, 
                        "parse": False, 
                    }
                )
            resp = yield upload_file_init(
                filename=name, 
                filesha1=attr["sha1"], 
                filesize=attr["size"], 
                read_range_bytes_or_hash=read_range_bytes_or_hash, 
                pid=pid, 
                async_=async_, 
                **request_kwargs, 
            )
            check_response(resp)
            return check_response(fs_delete(attr["id"], async_=async_, **request_kwargs))
    return run_gen_step(gen_step, async_)


@overload
def transferfile(
    client_from: str | PathLike | P115Client | P115OpenClient, 
    client_to: str | PathLike | P115Client | P115OpenClient, 
    id: int | str | Mapping, 
    /, 
    name: str = "", 
    pid: int | str = 0, 
    app: str = "web", 
    *, 
    async_: Literal[False] = False, 
    **request_kwargs, 
) -> dict:
    ...
@overload
def transferfile(
    client_from: str | PathLike | P115Client | P115OpenClient, 
    client_to: str | PathLike | P115Client | P115OpenClient, 
    id: int | str | Mapping, 
    /, 
    name: str = "", 
    pid: int | str = 0, 
    app: str = "web", 
    *, 
    async_: Literal[True], 
    **request_kwargs, 
) -> Coroutine[Any, Any, dict]:
    ...
def transferfile(
    client_from: str | PathLike | P115Client | P115OpenClient, 
    client_to: str | PathLike | P115Client | P115OpenClient, 
    id: int | str | Mapping, 
    /, 
    name: str = "", 
    pid: int | str = 0, 
    app: str = "web", 
    *, 
    async_: Literal[False, True] = False, 
    **request_kwargs, 
) -> dict | Coroutine[Any, Any, dict]:
    """从一个 115 网盘，转移文件到另一个 115 网盘

    :param client_from: 115 客户端或 cookies，文件来自这个网盘
    :param client_to: 115 客户端或 cookies，文件去往这个网盘
    :param id: 文件的 id、pickcode 或信息字典，关联在 `client_from`
    :param name: 复制后的新名字，如果为空则名字相同，关联在 `client_to`
    :param pid: 目录的 id 或 pickcode，，关联在 `client_to`
    :param app: 使用指定 app（设备）的接口
    :param async_: 是否异步
    :param request_kwargs: 其它请求参数

    :return: 接口响应信息
    """
    if isinstance(client_from, (str, PathLike)):
        client_from = P115Client(client_from, check_for_relogin=True)
    if isinstance(client_to, (str, PathLike)):
        client_to = P115Client(client_to, check_for_relogin=True)
    if not isinstance(client_from, P115Client) or app == "open":
        get_url: Callable = client_from.download_url_open
    else:
        get_url = client_from.download_url
        if isinstance(id, Mapping):
            get_url = partial(get_url, app=app)
    if not isinstance(client_to, P115Client) or app == "open":
        upload_file_init: Callable = client_to.upload_file_init_open
    else:
        upload_file_init = client_to.upload_file_init
    def gen_step():
        nonlocal pid, name
        url: None | P115URL = None
        if isinstance(id, Mapping):
            attr: Mapping = id
        else:
            url = yield get_url(
                client_from.to_pickcode(id), 
                async_=async_, 
                **request_kwargs, 
            )
            attr = url.__dict__
        pid = client_to.to_id(pid)
        if not name:
            name = attr["name"]
        @as_gen_step
        def read_range_bytes_or_hash(sign_check: str, /):
            nonlocal url
            if url is None:
                url = yield get_url(
                    attr.get("pickcode") or client_from.to_pickcode(attr["id"]), 
                    async_=async_, 
                    **request_kwargs, 
                )
            return client_to.request(
                url, 
                async_=async_, 
                **{
                    **request_kwargs, 
                    "headers": {**url.headers, "range": "bytes="+sign_check}, 
                    "parse": False, 
                }
            )
        return check_response(upload_file_init(
            filename=name, 
            filesha1=attr["sha1"], 
            filesize=attr["size"], 
            read_range_bytes_or_hash=read_range_bytes_or_hash, 
            pid=pid, 
            async_=async_, 
            **request_kwargs, 
        ))
    return run_gen_step(gen_step, async_)

# TODO: 上面这些，有些要支持 open 接口
