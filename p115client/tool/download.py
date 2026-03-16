#!/usr/bin/env python3
# encoding: utf-8

__author__ = "ChenyangGao <https://chenyanggao.github.io>"
__all__ = [
    "get_pic_url", "batch_get_url", "iter_url_batches", "iter_files_with_url", 
    "iter_images_with_url", "iter_subtitles_with_url", "iter_subtitle_batches", 
    "make_db", "make_strm", "iter_download_nodes", "iter_download_files", 
    "get_remaining_open_count", 
]
__doc__ = "这个模块提供了一些和下载有关的函数"

from asyncio import (
    create_task, gather as async_gather, to_thread, 
    CancelledError as AsyncCancelledError, 
    Queue as AsyncQueue, TaskGroup, 
)
from collections import defaultdict
from collections.abc import (
    AsyncIterator, Callable, Coroutine, Iterable, Iterator, 
    Mapping, MutableMapping, Sequence, 
)
from concurrent.futures import CancelledError, ThreadPoolExecutor
from contextlib import contextmanager
from datetime import datetime
from functools import partial
from itertools import batched, chain, count, cycle, repeat
from math import inf
from os import (
    cpu_count, fsdecode, makedirs, remove, rmdir, scandir, 
    DirEntry, PathLike, 
)
from os.path import abspath, dirname, join as joinpath, normpath, splitext
from queue import SimpleQueue
from re import compile as re_compile
from sqlite3 import Connection, Cursor
from string import hexdigits
from sys import exc_info
from threading import Lock
from time import time
from typing import cast, overload, Any, Literal
from types import EllipsisType
from urllib.parse import urlsplit
from urllib.request import urlopen, Request
from uuid import uuid4
from warnings import warn

from asynctools import async_chain
from concurrenttools import conmap, run_as_thread
from dicttools import get_first
from encode_uri import encode_uri_component_loose
from iterutils import (
    chunked, map as do_map, chain_from_iterable, run_gen_step, 
    run_gen_step_iter, through, with_iter_next, Yield, YieldFrom, 
)
from orjson import loads
from p115pickcode import to_id

from ..client import check_response, P115Client, P115OpenClient, P115URL
from ..const import ID_TO_DIRNODE_CACHE
from ..exception import P115Warning
from ..util import reduce_image_url_layers
from .attr import normalize_attr, normalize_attr_simple
from .iterdir import (
    iterdir, iter_files, iter_files_shortcut, unescape_115_charref, 
)


@overload
def get_pic_url(
    client: str | PathLike | P115Client, 
    sha1: str, 
    *, 
    async_: Literal[False] = False, 
    **request_kwargs, 
) -> str:
    ...
@overload
def get_pic_url(
    client: str | PathLike | P115Client, 
    sha1: Iterable[str], 
    *, 
    async_: Literal[False] = False, 
    **request_kwargs, 
) -> list[str]:
    ...
@overload
def get_pic_url(
    client: str | PathLike | P115Client, 
    sha1: str, 
    *, 
    async_: Literal[True], 
    **request_kwargs, 
) -> Coroutine[Any, Any, str]:
    ...
@overload
def get_pic_url(
    client: str | PathLike | P115Client, 
    sha1: Iterable[str], 
    *, 
    async_: Literal[True], 
    **request_kwargs, 
) -> Coroutine[Any, Any, list[str]]:
    ...
def get_pic_url(
    client: str | PathLike | P115Client, 
    sha1: str | Iterable[str], 
    *, 
    _match_fhn_prefix=re_compile("^fhn[a-z]+_").match, 
    async_: Literal[False, True] = False, 
    **request_kwargs, 
) -> str | list[str] | Coroutine[Any, Any, str] | Coroutine[Any, Any, list[str]]:
    """单个或批量获取图片链接

    .. note::
        不仅限于图片，每个文件必须限制在 50 MB 以内（含）

    :param client: 115 客户端或 cookies
    :param sha1: 图片的 sha1 或 f"{bucket}_{object}"（`bucket` 是所在存储桶， `object`是对象 id）
    :param async_: 是否异步
    :param request_kwargs: 其它请求参数

    :return: 图片链接的单个或列表
    """
    def formalize_sha1(sha1):
        if len(sha1) == 40 and not sha1.strip(hexdigits):
            return sha1.upper()
        elif not _match_fhn_prefix(sha1):
            return "fhnfile_" + sha1
        return sha1
    if isinstance(client, (str, PathLike)):
        client = P115Client(client, check_for_relogin=True)
    def gen_step():
        if isinstance(sha1, str):
            resp = yield client.life_get_pic_url(
                formalize_sha1(sha1), 
                async_=async_, 
                **request_kwargs, 
            )
            check_response(resp)
            return resp["data"][0]["json"].replace("&i=0", "&i=1")
        else:
            resp = yield client.life_get_pic_url(
                tuple(map(formalize_sha1, sha1)), 
                async_=async_, 
                **request_kwargs, 
            )
            check_response(resp)
            return [u["json"].replace("&i=0", "&i=1") for u in resp["data"]]
    return run_gen_step(gen_step, async_)


# TODO: 之后加上并发拉取，以加快速度
# TODO: 为了避免拉了太多赶不上用，用队列来收集结果，队列长度有限，这样可以在队列满的时候阻塞工作者
@overload
def batch_get_url(
    client: str | PathLike | P115Client | P115OpenClient, 
    pickcode: int | str | Iterable[int | str], 
    user_agent: str = "", 
    app: str = "android", 
    *, 
    async_: Literal[False] = False, 
    **request_kwargs, 
) -> dict[int, P115URL]:
    ...
@overload
def batch_get_url(
    client: str | PathLike | P115Client | P115OpenClient, 
    pickcode: int | str | Iterable[int | str], 
    user_agent: str = "", 
    app: str = "android", 
    *, 
    async_: Literal[True], 
    **request_kwargs, 
) -> Coroutine[Any, Any, dict[int, P115URL]]:
    ...
def batch_get_url(
    client: str | PathLike | P115Client | P115OpenClient, 
    pickcode: int | str | Iterable[int | str], 
    user_agent: str = "", 
    app: str = "android", 
    *, 
    async_: Literal[False, True] = False, 
    **request_kwargs, 
) -> dict[int, P115URL] | Coroutine[Any, Any, dict[int, P115URL]]:
    """批量获取下载链接

    :param client: 115 客户端或 cookies
    :param pickcode: pickcode 或 id
    :param user_agent: "user-agent" 请求头的值
    :param app: 使用指定 app（设备）的接口
    :param async_: 是否异步
    :param request_kwargs: 其它请求参数

    :return: 字典，key 是文件 id，value 是下载链接，自动忽略所有无效项目
    """
    if isinstance(client, (str, PathLike)):
        client = P115Client(client, check_for_relogin=True)
    if headers := request_kwargs.get("headers"):
        request_kwargs["headers"] = dict(headers, **{"user-agent": user_agent})
    else:
        request_kwargs["headers"] = {"user-agent": user_agent}
    if isinstance(pickcode, (int, str)):
        pickcode = client.to_pickcode(pickcode)
    elif not isinstance(pickcode, str):
        pickcode = ",".join(map(client.to_pickcode, pickcode))
    if not isinstance(client, P115Client) or app == "open":
        get_download_urls: Callable = client.download_urls_open
    else:
        get_download_urls = client.download_urls
    return get_download_urls(pickcode, async_=async_, **request_kwargs)


@overload
def iter_url_batches(
    client: str | PathLike | P115Client | P115OpenClient, 
    pickcodes: Iterator[int | str], 
    user_agent: str = "", 
    batch_size: int = 10, 
    app: str = "android", 
    *, 
    async_: Literal[False] = False, 
    **request_kwargs, 
) -> Iterator[P115URL]:
    ...
@overload
def iter_url_batches(
    client: str | PathLike | P115Client | P115OpenClient, 
    pickcodes: Iterator[int | str], 
    user_agent: str = "", 
    batch_size: int = 10, 
    app: str = "android", 
    *, 
    async_: Literal[True], 
    **request_kwargs, 
) -> AsyncIterator[P115URL]:
    ...
def iter_url_batches(
    client: str | PathLike | P115Client | P115OpenClient, 
    pickcodes: Iterator[int | str], 
    user_agent: str = "", 
    batch_size: int = 10, 
    app: str = "android", 
    *, 
    async_: Literal[False, True] = False, 
    **request_kwargs, 
) -> Iterator[P115URL] | AsyncIterator[P115URL]:
    """批量获取下载链接

    .. attention::
        请确保所有的 pickcode 都是有效的，要么是现在存在的，要么是以前存在过被删除的。

        如果有目录的 pickcode 混在其中，则会自动排除。

    :param client: 115 客户端或 cookies
    :param pickcodes: 一个迭代器，产生 pickcode 或 id
    :param user_agent: "user-agent" 请求头的值
    :param batch_size: 每一个批次处理的个量
    :param app: 使用指定 app（设备）的接口
    :param async_: 是否异步
    :param request_kwargs: 其它请求参数

    :return: 字典，key 是文件 id，value 是下载链接，自动忽略所有无效项目
    """
    if isinstance(client, (str, PathLike)):
        client = P115Client(client, check_for_relogin=True)
    if headers := request_kwargs.get("headers"):
        request_kwargs["headers"] = dict(headers, **{"user-agent": user_agent})
    else:
        request_kwargs["headers"] = {"user-agent": user_agent}
    if batch_size <= 0:
        batch_size = 1
    def gen_step():
        if batch_size == 1:
            if not isinstance(client, P115Client) or app == "open":
                get_download_url: Callable = client.download_url_open
            else:
                get_download_url = partial(client.download_url, app=app)
            for pickcode in map(client.to_pickcode, pickcodes):
                yield Yield(get_download_url(
                    pickcode, 
                    async_=async_, 
                    **request_kwargs, 
                ))
        else:
            if not isinstance(client, P115Client) or app == "open":
                get_download_urls: Callable = client.download_urls_open
            else:
                get_download_urls = client.download_urls
            for pcs in batched(map(client.to_pickcode, pickcodes), batch_size):
                if urls := (yield get_download_urls(
                    ",".join(pcs), 
                    async_=async_, 
                    **request_kwargs, 
                )):
                    yield YieldFrom(urls.values())
    return run_gen_step_iter(gen_step, async_)


@overload
def iter_files_with_url(
    client: str | PathLike | P115Client | P115OpenClient, 
    cid: int | str | Mapping = 0, 
    suffixes: None | str | Iterable[str] = None, 
    type: Literal[1, 2, 3, 4, 5, 6, 7, 99] = 99, 
    cur: Literal[0, 1] = 0, 
    with_ancestors: bool = False, 
    with_path: bool = False, 
    use_star: None | bool = False, 
    escape: None | bool | Callable[[str], str] = True, 
    normalize_attr: Callable[[dict], dict] = normalize_attr, 
    id_to_dirnode: None | EllipsisType | MutableMapping[int, tuple[str, int]] = None, 
    app: str = "web", 
    raise_for_changed_count: bool = False, 
    user_agent: str = "", 
    *, 
    async_: Literal[False] = False, 
    **request_kwargs, 
) -> Iterator[dict]:
    ...
@overload
def iter_files_with_url(
    client: str | PathLike | P115Client | P115OpenClient, 
    cid: int | str | Mapping = 0, 
    suffixes: None | str | Iterable[str] = None, 
    type: Literal[1, 2, 3, 4, 5, 6, 7, 99] = 99, 
    cur: Literal[0, 1] = 0, 
    with_ancestors: bool = False, 
    with_path: bool = False, 
    use_star: None | bool = False, 
    escape: None | bool | Callable[[str], str] = True, 
    normalize_attr: Callable[[dict], dict] = normalize_attr, 
    id_to_dirnode: None | EllipsisType | MutableMapping[int, tuple[str, int]] = None, 
    app: str = "web", 
    raise_for_changed_count: bool = False, 
    user_agent: str = "", 
    *, 
    async_: Literal[True], 
    **request_kwargs, 
) -> AsyncIterator[dict]:
    ...
def iter_files_with_url(
    client: str | PathLike | P115Client | P115OpenClient, 
    cid: int | str | Mapping = 0, 
    suffixes: None | str | Iterable[str] = None, 
    type: Literal[1, 2, 3, 4, 5, 6, 7, 99] = 99, 
    cur: Literal[0, 1] = 0, 
    with_ancestors: bool = False, 
    with_path: bool = False, 
    use_star: None | bool = False, 
    escape: None | bool | Callable[[str], str] = True, 
    normalize_attr: Callable[[dict], dict] = normalize_attr, 
    id_to_dirnode: None | EllipsisType | MutableMapping[int, tuple[str, int]] = None, 
    app: str = "web", 
    raise_for_changed_count: bool = False, 
    user_agent: str = "", 
    *, 
    async_: Literal[False, True] = False, 
    **request_kwargs, 
) -> Iterator[dict] | AsyncIterator[dict]:
    """获取文件信息和下载链接

    :param client: 115 客户端或 cookies
    :param cid: 目录 id 或 pickcode
    :param suffixes: 扩展名，可以有多个，最前面的 "." 可以省略
    :param type: 文件类型

        - 1: 文档
        - 2: 图片
        - 3: 音频
        - 4: 视频
        - 5: 压缩包
        - 6: 应用
        - 7: 书籍
        - 99: 仅文件

    :param cur: 仅当前目录。0: 否（将遍历子目录树上所有叶子节点），1: 是
    :param with_ancestors: 文件信息中是否要包含 "ancestors"
    :param with_path: 文件信息中是否要包含 "path"
    :param use_star: 获取目录信息时，是否允许使用星标 （如果为 None，则采用流处理，否则采用批处理）
    :param escape: 对文件名进行转义

        - 如果为 None，则不处理；否则，这个函数用来对文件名中某些符号进行转义，例如 "/" 等
        - 如果为 True，则使用 `posixpatht.escape`，会对文件名中 "/"，或单独出现的 "." 和 ".." 用 "\\" 进行转义
        - 如果为 False，则使用 `posix_escape_name` 函数对名字进行转义，会把文件名中的 "/" 转换为 "|"
        - 如果为 Callable，则用你所提供的调用，以或者转义后的名字

    :param normalize_attr: 把数据进行转换处理，使之便于阅读
    :param id_to_dirnode: 字典，保存 id 到对应文件的 ``(name, parent_id)`` 元组的字典
    :param app: 使用指定 app（设备）的接口
    :param raise_for_changed_count: 分批拉取时，发现总数发生变化后，是否报错
    :param user_agent: "user-agent" 请求头的值
    :param async_: 是否异步
    :param request_kwargs: 其它请求参数

    :return: 迭代器，产生文件信息，并增加一个 "url" 作为下载链接
    """
    if isinstance(cid, Mapping):
        cid = cast(int | str, get_first(cid, "id", "pickcode"))
    if isinstance(client, (str, PathLike)):
        client = P115Client(client, check_for_relogin=True)
    params = dict(
        cur=cur, 
        with_ancestors=with_ancestors, 
        with_path=with_path, 
        use_star=use_star, 
        escape=escape, 
        normalize_attr=normalize_attr, 
        id_to_dirnode=id_to_dirnode, 
        raise_for_changed_count=raise_for_changed_count, 
        async_=async_, 
        **request_kwargs, 
    )
    if not isinstance(client, P115Client) or app == "open":
        get_url: Callable[..., P115URL] = client.download_url_open
    elif app in ("", "web", "desktop", "harmony"):
        get_url = client.download_url
    else:
        get_url = partial(client.download_url, app=app)
    cid = to_id(cid)
    def gen_step():
        if suffixes is None:
            it = iter_files(
                client, 
                cid, 
                type=type, 
                app=app, 
                **params, # type: ignore
            )
        elif isinstance(suffixes, str):
            it = iter_files(
                client, 
                cid, 
                suffix=suffixes, 
                app=app, 
                **params, # type: ignore
            )
        else:
            for suffix in suffixes:
                yield YieldFrom(
                    iter_files_with_url(
                        client, 
                        cid, 
                        suffixes=suffix, 
                        app=app, 
                        user_agent=user_agent, 
                        **params, # type: ignore
                    )
                )
            return
        if headers := request_kwargs.get("headers"):
            request_kwargs["headers"] = dict(headers, **{"user-agent": user_agent})
        else:
            request_kwargs["headers"] = {"user-agent": user_agent}
        with with_iter_next(it) as get_next:
            while True:
                attr = yield get_next()
                if attr.get("is_collect", False):
                    if attr["size"] < 1024 * 1024 * 115:
                        attr["url"] = yield get_url(
                            attr["pickcode"], 
                            use_web_api=True, 
                            async_=async_, 
                            **request_kwargs, 
                        )
                    else:
                        warn(f"unable to get url for {attr!r}", category=P115Warning)
                else:
                    attr["url"] = yield get_url(
                        attr["pickcode"], 
                        async_=async_, 
                        **request_kwargs, 
                    )
                yield Yield(attr)
    return run_gen_step_iter(gen_step, async_)


@overload
def iter_images_with_url(
    client: str | PathLike | P115Client | P115OpenClient, 
    cid: int | str | Mapping = 0, 
    suffixes: None | str | Iterable[str] = None, 
    cur: Literal[0, 1] = 0, 
    with_ancestors: bool = False, 
    with_path: bool = False, 
    use_star: None | bool = False, 
    escape: None | bool | Callable[[str], str] = True, 
    normalize_attr: Callable[[dict], dict] = normalize_attr, 
    id_to_dirnode: None | EllipsisType | MutableMapping[int, tuple[str, int]] = None, 
    app: str = "web", 
    raise_for_changed_count: bool = False, 
    *, 
    async_: Literal[False] = False, 
    **request_kwargs, 
) -> Iterator[dict]:
    ...
@overload
def iter_images_with_url(
    client: str | PathLike | P115Client | P115OpenClient, 
    cid: int | str | Mapping = 0, 
    suffixes: None | str | Iterable[str] = None, 
    cur: Literal[0, 1] = 0, 
    with_ancestors: bool = False, 
    with_path: bool = False, 
    use_star: None | bool = False, 
    escape: None | bool | Callable[[str], str] = True, 
    normalize_attr: Callable[[dict], dict] = normalize_attr, 
    id_to_dirnode: None | EllipsisType | MutableMapping[int, tuple[str, int]] = None, 
    app: str = "web", 
    raise_for_changed_count: bool = False, 
    *, 
    async_: Literal[True], 
    **request_kwargs, 
) -> AsyncIterator[dict]:
    ...
def iter_images_with_url(
    client: str | PathLike | P115Client | P115OpenClient, 
    cid: int | str | Mapping = 0, 
    suffixes: None | str | Iterable[str] = None, 
    cur: Literal[0, 1] = 0, 
    with_ancestors: bool = False, 
    with_path: bool = False, 
    use_star: None | bool = False, 
    escape: None | bool | Callable[[str], str] = True, 
    normalize_attr: Callable[[dict], dict] = normalize_attr, 
    id_to_dirnode: None | EllipsisType | MutableMapping[int, tuple[str, int]] = None, 
    app: str = "web", 
    raise_for_changed_count: bool = False, 
    *, 
    async_: Literal[False, True] = False, 
    **request_kwargs, 
) -> Iterator[dict] | AsyncIterator[dict]:
    """获取图片文件信息和下载链接

    .. attention::
        请不要把不能被 115 识别为图片的文件扩展名放在 `suffixes` 参数中传入，这只是浪费时间，最后也只能获得普通的下载链接

    :param client: 115 客户端或 cookies
    :param cid: 目录 id 或 pickcode
    :param suffixes: 扩展名，可以有多个，最前面的 "." 可以省略（请确保扩展名确实能被 115 认为是图片，否则会因为不能批量获取到链接而浪费一些时间再去单独生成下载链接）；如果不传（默认），则会获取所有图片
    :param cur: 仅当前目录。0: 否（将遍历子目录树上所有叶子节点），1: 是
    :param with_ancestors: 文件信息中是否要包含 "ancestors"
    :param with_path: 文件信息中是否要包含 "path"
    :param use_star: 获取目录信息时，是否允许使用星标 （如果为 None，则采用流处理，否则采用批处理）
    :param escape: 对文件名进行转义

        - 如果为 None，则不处理；否则，这个函数用来对文件名中某些符号进行转义，例如 "/" 等
        - 如果为 True，则使用 `posixpatht.escape`，会对文件名中 "/"，或单独出现的 "." 和 ".." 用 "\\" 进行转义
        - 如果为 False，则使用 `posix_escape_name` 函数对名字进行转义，会把文件名中的 "/" 转换为 "|"
        - 如果为 Callable，则用你所提供的调用，以或者转义后的名字

    :param normalize_attr: 把数据进行转换处理，使之便于阅读
    :param id_to_dirnode: 字典，保存 id 到对应文件的 ``(name, parent_id)`` 元组的字典
    :param app: 使用指定 app（设备）的接口
    :param raise_for_changed_count: 分批拉取时，发现总数发生变化后，是否报错
    :param async_: 是否异步
    :param request_kwargs: 其它请求参数

    :return: 迭代器，产生文件信息，并增加一个 "url" 作为下载链接
    """
    if isinstance(cid, Mapping):
        cid = cast(int | str, get_first(cid, "id", "pickcode"))
    if isinstance(client, (str, PathLike)):
        client = P115Client(client, check_for_relogin=True)
    params = dict(
        cur=cur, 
        with_ancestors=with_ancestors, 
        with_path=with_path, 
        use_star=use_star, 
        escape=escape, 
        normalize_attr=normalize_attr, 
        id_to_dirnode=id_to_dirnode, 
        raise_for_changed_count=raise_for_changed_count, 
        async_=async_, 
        **request_kwargs
    )
    if not isinstance(client, P115Client) or app == "open":
        get_url: Callable[..., P115URL] = client.download_url_open
    elif app in ("", "web", "desktop", "harmony"):
        get_url = client.download_url
    else:
        get_url = partial(client.download_url, app=app)
    cid = to_id(cid)
    def gen_step():
        if suffixes is None:
            it = iter_files(
                client, 
                cid, 
                type=2, 
                app=app, 
                **params, # type: ignore
            )
        elif isinstance(suffixes, str):
            it = iter_files(
                client, 
                cid, 
                suffix=suffixes, 
                app=app, 
                **params, # type: ignore
            )
        else:
            for suffix in suffixes:
                yield YieldFrom(
                    iter_images_with_url(
                        client, 
                        cid, 
                        suffixes=suffix, 
                        app=app, 
                        **params, # type: ignore
                    )
                )
            return
        with with_iter_next(it) as get_next:
            while True:
                attr = yield get_next()
                try:
                    attr["url"] = reduce_image_url_layers(attr["thumb"])
                except KeyError:
                    if attr.get("is_collect", False):
                        if attr["size"] < 1024 * 1024 * 115:
                            attr["url"] = yield get_url(
                                attr["pickcode"], 
                                use_web_api=True, 
                                async_=async_, 
                                **request_kwargs, 
                            )
                        else:
                            warn(f"unable to get url for {attr!r}", category=P115Warning)
                    else:
                        attr["url"] = yield get_url(
                            attr["pickcode"], 
                            async_=async_, 
                            **request_kwargs, 
                        )
                yield Yield(attr)
    return run_gen_step_iter(gen_step, async_)


@overload
def iter_subtitles_with_url(
    client: str | PathLike | P115Client | P115OpenClient, 
    cid: int | str | Mapping = 0, 
    suffixes: str | Iterable[str] = (".srt", ".ass", ".ssa"), 
    cur: Literal[0, 1] = 0, 
    with_ancestors: bool = False, 
    with_path: bool = False, 
    use_star: None | bool = False, 
    escape: None | bool | Callable[[str], str] = True, 
    normalize_attr: Callable[[dict], dict] = normalize_attr, 
    id_to_dirnode: None | EllipsisType | MutableMapping[int, tuple[str, int]] = None, 
    app: str = "web", 
    raise_for_changed_count: bool = False, 
    *, 
    async_: Literal[False] = False, 
    **request_kwargs, 
) -> Iterator[dict]:
    ...
@overload
def iter_subtitles_with_url(
    client: str | PathLike | P115Client | P115OpenClient, 
    cid: int | str | Mapping = 0, 
    suffixes: str | Iterable[str] = (".srt", ".ass", ".ssa"), 
    cur: Literal[0, 1] = 0, 
    with_ancestors: bool = False, 
    with_path: bool = False, 
    use_star: None | bool = False, 
    escape: None | bool | Callable[[str], str] = True, 
    normalize_attr: Callable[[dict], dict] = normalize_attr, 
    id_to_dirnode: None | EllipsisType | MutableMapping[int, tuple[str, int]] = None, 
    app: str = "web", 
    raise_for_changed_count: bool = False, 
    *, 
    async_: Literal[True], 
    **request_kwargs, 
) -> AsyncIterator[dict]:
    ...
def iter_subtitles_with_url(
    client: str | PathLike | P115Client | P115OpenClient, 
    cid: int | str | Mapping = 0, 
    suffixes: str | Iterable[str] = (".srt", ".ass", ".ssa"), 
    cur: Literal[0, 1] = 0, 
    with_ancestors: bool = False, 
    with_path: bool = False, 
    use_star: None | bool = False, 
    escape: None | bool | Callable[[str], str] = True, 
    normalize_attr: Callable[[dict], dict] = normalize_attr, 
    id_to_dirnode: None | EllipsisType | MutableMapping[int, tuple[str, int]] = None, 
    app: str = "web", 
    raise_for_changed_count: bool = False, 
    *, 
    async_: Literal[False, True] = False, 
    **request_kwargs, 
) -> Iterator[dict] | AsyncIterator[dict]:
    """获取字幕文件信息和下载链接

    .. caution::
        这个函数运行时，会把相关文件以 1,000 为一批，同一批次复制到同一个新建的目录，在批量获取链接后，自动把目录删除到回收站。

    .. attention::
        目前看来 115 只支持：".srt", ".ass", ".ssa"

        请不要把不能被 115 识别为字幕的文件扩展名放在 `suffixes` 参数中传入，这只是浪费时间，最后也只能获得普通的下载链接

    :param client: 115 客户端或 cookies
    :param cid: 目录 id 或 pickcode
    :param suffixes: 扩展名，可以有多个，最前面的 "." 可以省略（请确保扩展名确实能被 115 认为是字幕，否则会因为不能批量获取到链接而浪费一些时间再去单独生成下载链接）
    :param cur: 仅当前目录。0: 否（将遍历子目录树上所有叶子节点），1: 是
    :param with_ancestors: 文件信息中是否要包含 "ancestors"
    :param with_path: 文件信息中是否要包含 "path"
    :param use_star: 获取目录信息时，是否允许使用星标 （如果为 None，则采用流处理，否则采用批处理）
    :param escape: 对文件名进行转义

        - 如果为 None，则不处理；否则，这个函数用来对文件名中某些符号进行转义，例如 "/" 等
        - 如果为 True，则使用 `posixpatht.escape`，会对文件名中 "/"，或单独出现的 "." 和 ".." 用 "\\" 进行转义
        - 如果为 False，则使用 `posix_escape_name` 函数对名字进行转义，会把文件名中的 "/" 转换为 "|"
        - 如果为 Callable，则用你所提供的调用，以或者转义后的名字

    :param normalize_attr: 把数据进行转换处理，使之便于阅读
    :param id_to_dirnode: 字典，保存 id 到对应文件的 ``(name, parent_id)`` 元组的字典
    :param app: 使用指定 app（设备）的接口
    :param raise_for_changed_count: 分批拉取时，发现总数发生变化后，是否报错
    :param async_: 是否异步
    :param request_kwargs: 其它请求参数

    :return: 迭代器，产生文件信息，并增加一个 "url" 作为下载链接
    """
    if isinstance(cid, Mapping):
        cid = cast(int | str, get_first(cid, "id", "pickcode"))
    if isinstance(client, (str, PathLike)):
        client = P115Client(client, check_for_relogin=True)
    if not isinstance(client, P115Client) or app == "open":
        get_url: Callable[..., P115URL] = client.download_url_open
        fs_mkdir: Callable = client.fs_mkdir_open
        fs_copy: Callable = client.fs_copy_open
        fs_delete: Callable = client.fs_delete_open
        fs_video_subtitle: Callable = client.fs_video_subtitle_open
    elif app in ("", "web", "desktop", "harmony"):
        get_url = client.download_url
        fs_mkdir = client.fs_mkdir
        fs_copy = client.fs_copy
        fs_delete = client.fs_delete
        fs_video_subtitle = client.fs_video_subtitle
    else:
        get_url = partial(client.download_url, app=app)
        fs_mkdir = partial(client.fs_mkdir_app, app=app)
        fs_copy = partial(client.fs_copy_app, app=app)
        fs_delete = partial(client.fs_delete_app, app=app)
        fs_video_subtitle = partial(client.fs_video_subtitle_app, app=app)
    from .iterdir import _iter_fs_files
    cid = to_id(cid)
    def gen_step():
        nonlocal suffixes
        if isinstance(suffixes, str):
            suffixes = suffixes,
        do_chain: Callable = async_chain.from_iterable if async_ else chain.from_iterable
        do_next: Callable = anext if async_ else next
        with with_iter_next(chunked(do_chain(
            iter_files(
                client, 
                cid, 
                suffix=suffix, 
                cur=cur, 
                with_ancestors=with_ancestors, 
                with_path=with_path, 
                use_star=use_star, 
                escape=escape, 
                normalize_attr=normalize_attr, 
                id_to_dirnode=id_to_dirnode, 
                app=app, 
                raise_for_changed_count=raise_for_changed_count, 
                async_=async_, # type: ignore
                **request_kwargs, 
            )
            for suffix in suffixes
        ), 1000)) as get_next:
            while True:
                items: tuple[dict] = yield get_next()
                resp = yield fs_mkdir(
                    f"subtitle-{uuid4()}", 
                    async_=async_, 
                    **request_kwargs, 
                )
                check_response(resp)
                try:
                    if "cid" in resp:
                        scid = resp["cid"]
                    else:
                        data = resp["data"]
                        if "category_id" in data:
                            scid = data["category_id"]
                        else:
                            scid = data["file_id"]
                    resp = yield fs_copy(
                        (attr["id"] for attr in items), 
                        pid=scid, 
                        async_=async_, 
                        **request_kwargs, 
                    )
                    check_response(resp)
                    attr = yield do_next(_iter_fs_files(
                        client, 
                        scid, 
                        page_size=1, 
                        normalize_attr=normalize_attr_simple, 
                        app=app, 
                        async_=async_, 
                        **request_kwargs, 
                    ))
                    resp = yield fs_video_subtitle(
                        attr["pickcode"], 
                        async_=async_, 
                        **request_kwargs, 
                    )
                    subtitles = {
                        info["sha1"]: info["url"]
                        for info in resp["data"]["list"] 
                        if info.get("file_id")
                    }
                finally:
                    yield fs_delete(scid, async_=async_, **request_kwargs)
                if subtitles:
                    for attr in items:
                        attr["url"] = subtitles[attr["sha1"]]
                        yield Yield(attr)
                else:
                    for attr in items:
                        if attr.get("is_collect", False):
                            if attr["size"] < 1024 * 1024 * 115:
                                attr["url"] = yield get_url(
                                    attr["pickcode"], 
                                    use_web_api=True, 
                                    async_=async_, 
                                    **request_kwargs, 
                                )
                            else:
                                warn(f"unable to get url for {attr!r}", category=P115Warning)
                        else:
                            attr["url"] = yield get_url(
                                attr["pickcode"], 
                                async_=async_, 
                                **request_kwargs, 
                            )
                        yield Yield(attr)
    return run_gen_step_iter(gen_step, async_)


@overload
def iter_subtitle_batches(
    client: str | PathLike | P115Client | P115OpenClient, 
    file_ids: Iterable[int | str], 
    batch_size: int = 1_000, 
    app: str = "web", 
    *, 
    async_: Literal[False] = False, 
    **request_kwargs, 
) -> Iterator[dict]:
    ...
@overload
def iter_subtitle_batches(
    client: str | PathLike | P115Client | P115OpenClient, 
    file_ids: Iterable[int | str], 
    batch_size: int = 1_000, 
    app: str = "web", 
    *, 
    async_: Literal[True], 
    **request_kwargs, 
) -> AsyncIterator[dict]:
    ...
def iter_subtitle_batches(
    client: str | PathLike | P115Client | P115OpenClient, 
    file_ids: Iterable[int | str], 
    batch_size: int = 1_000, 
    app: str = "web", 
    *, 
    async_: Literal[False, True] = False, 
    **request_kwargs, 
) -> Iterator[dict] | AsyncIterator[dict]:
    """批量获取字幕文件的信息和下载链接

    .. caution::
        这个函数运行时，会把相关文件以 1,000 为一批，同一批次复制到同一个新建的目录，在批量获取链接后，自动把目录删除到回收站。

    .. attention::
        目前看来 115 只支持：".srt"、".ass"、".ssa"，如果不能被 115 识别为字幕，将会被自动略过

    :param client: 115 客户端或 cookies
    :param file_ids: 一组文件的 id 或 pickcode
    :param batch_size: 每一个批次处理的个量
    :param async_: 是否异步
    :param request_kwargs: 其它请求参数

    :return: 迭代器，产生文件信息，并增加一个 "url" 作为下载链接，文件信息中的 file_id 是复制所得的文件信息，不是原来文件的 id
    """
    if isinstance(client, (str, PathLike)):
        client = P115Client(client, check_for_relogin=True)
    if batch_size <= 0:
        batch_size = 1_000
    if not isinstance(client, P115Client) or app == "open":
        fs_mkdir: Callable = client.fs_mkdir_open
        fs_copy: Callable = client.fs_copy_open
        fs_delete: Callable = client.fs_delete_open
        fs_video_subtitle: Callable = client.fs_video_subtitle_open
    elif app in ("", "web", "desktop", "harmony"):
        fs_mkdir = client.fs_mkdir
        fs_copy = client.fs_copy
        fs_delete = client.fs_delete
        fs_video_subtitle = client.fs_video_subtitle
    else:
        fs_mkdir = partial(client.fs_mkdir_app, app=app)
        fs_copy = partial(client.fs_copy_app, app=app)
        fs_delete = partial(client.fs_delete_app, app=app)
        fs_video_subtitle = partial(client.fs_video_subtitle_app, app=app)
    from .iterdir import _iter_fs_files
    def gen_step():
        do_next: Callable = anext if async_ else next
        for ids in batched(map(to_id, file_ids), batch_size):
            try:
                resp = yield fs_mkdir(
                    f"subtitle-{uuid4()}", 
                    async_=async_, 
                    **request_kwargs, 
                )
                check_response(resp)
                scid = resp["cid"]
                resp = yield fs_copy(
                    ids, 
                    pid=scid, 
                    async_=async_, 
                    **request_kwargs, 
                )
                check_response(resp)
                attr = yield do_next(_iter_fs_files(
                    client, 
                    scid, 
                    page_size=1, 
                    normalize_attr=normalize_attr_simple, 
                    app=app, 
                    async_=async_, 
                    **request_kwargs, 
                ))
                resp = yield fs_video_subtitle(
                    attr["pickcode"], 
                    async_=async_, 
                    **request_kwargs, 
                )
                check_response(resp)
                yield YieldFrom(
                    filter(lambda info: "file_id" in info, resp["data"]["list"])
                )
            except (StopIteration, StopAsyncIteration):
                pass
            finally:
                yield fs_delete(scid, async_=async_, **request_kwargs)
    return run_gen_step_iter(gen_step, async_)


# TODO: 实现 p115updatedb 的逻辑，但多了一个 user_id 字段
# TODO: 分成 2 部分拉取（并发），1. 拉取目录 iter_dirs 2. 拉取文件 iter_files+normalize_attr_simple
# TODO: 支持增量更新，根据 mtime 逆序排列进行比对
# TODO: 允许只拉取 1 级
# TODO: 这个函数可以作为 p115dav 的基础
# TODO: 首先判断数据库里面有没有这个id（存活），如果没有就直接并发拉，如果有则序列拉（随时终止）
# TODO: 不需要 event 表？
@overload
def make_db(
    client: str | PathLike | P115Client, 
    dbfile: str | PathLike | Connection | Cursor = "p115updatedb.db", 
    cid: int | str | Mapping = 0, 
    recursive: bool = True, 
    max_workers: None | int = None, 
    app: str = "android", 
    *, 
    async_: Literal[False] = False, 
    **request_kwargs, 
) -> dict:
    ...
@overload
def make_db(
    client: str | PathLike | P115Client, 
    dbfile: str | PathLike | Connection | Cursor = "p115updatedb.db", 
    cid: int | str | Mapping = 0, 
    recursive: bool = True, 
    max_workers: None | int = None, 
    app: str = "android", 
    *, 
    async_: Literal[True], 
    **request_kwargs, 
) -> Coroutine[Any, Any, dict]:
    ...
def make_db(
    client: str | PathLike | P115Client, 
    dbfile: str | PathLike | Connection | Cursor = "p115updatedb.db", 
    cid: int | str | Mapping = 0, 
    recursive: bool = True, 
    max_workers: None | int = None, 
    app: str = "android", 
    *, 
    async_: Literal[False, True] = False, 
    **request_kwargs, 
) -> dict | Coroutine[Any, Any, dict]:
    """对某个目录执行一次拉取，以更新 SQLite 数据

    :param client: 115 客户端或 cookies
    :param dbfile: 数据库路径或连接
    :param cid: 目录 id 或 pickcode
    :param recursive: 如果为 True，则拉取所有以之为祖先（先驱）节点的节点信息；否则，拉取所有以之为父（前驱）节点的节点信息
    :param max_workers: 最大并发数，如果为 None 或 < 0 则自动确定，如果为 0 则单工作者惰性执行
    :param app: 使用指定 app（设备）的接口
    :param async_: 是否异步
    :param request_kwargs: 其它请求参数

    :return: 一些统计信息
    """
    from .updatedb import _init_client
    init_sql = """\
-- 修改日志模式为 WAL (write-ahead-log)
PRAGMA journal_mode = WAL;

-- 创建表
CREATE TABLE IF NOT EXISTS data (
    id INTEGER NOT NULL PRIMARY KEY,      -- id
    parent_id INTEGER NOT NULL DEFAULT 0, -- 上级目录 id
    name TEXT NOT NULL DEFAULT '',        -- 名字
    sha1 TEXT NOT NULL DEFAULT '',        -- 文件的 sha1 哈希值
    size INTEGER NOT NULL DEFAULT 0,      -- 文件大小
    pickcode TEXT NOT NULL DEFAULT '',    -- 提取码
    ctime INTEGER NOT NULL DEFAULT 0,     -- 创建时间戳
    mtime INTEGER NOT NULL DEFAULT 0,     -- 更新时间戳
    is_dir INTEGER NOT NULL DEFAULT 0,    -- 是否目录
    type INTEGER NOT NULL DEFAULT 0,      -- 文件类型，目录 <=> type=0
    user_id INTEGER NOT NULL,             -- 用户 id
    extra BLOB DEFAULT NULL,              -- 其它信息
    is_alive INTEGER NOT NULL DEFAULT 1 CHECK(is_alive IN (0, 1)), -- 是否存活（存活即是不是删除状态）
    created_at TIMESTAMP DEFAULT (unixepoch('subsec')), -- 创建时间
    updated_at TIMESTAMP DEFAULT (unixepoch('subsec'))  -- 更新时间
);

-- 创建索引
CREATE INDEX IF NOT EXISTS idx_data_pid ON data(parent_id);
CREATE INDEX IF NOT EXISTS idx_data_tid ON data(top_id);
CREATE INDEX IF NOT EXISTS idx_data_mtime ON data(mtime);
CREATE INDEX IF NOT EXISTS idx_data_utime ON data(updated_at);

-- data 表发生更新
DROP TRIGGER IF EXISTS trg_data_update;
CREATE TRIGGER trg_data_update
AFTER UPDATE ON data
FOR EACH ROW
BEGIN
    UPDATE data SET updated_at = unixepoch('subsec') WHERE id = NEW.id;
END;"""
    client, con = _init_client(client, dbfile, init_sql)
    raise NotImplementedError


# TODO: 支持只拉取 1 级
# TODO: 需要更多的简化
@overload
def make_strm(
    client: str | PathLike | P115Client, 
    cid: int | str | Mapping = 0, 
    save_dir: bytes | str | PathLike = ".", 
    base_url: str = "", 
    with_root: None | bool = None, 
    without_suffix: bool = True, 
    clean: bool = True, 
    replace: bool = True, 
    predicate: None | Literal[1, 2, 3, 4, 5, 6, 7] | str | tuple[str, ...] | Callable[[dict], bool] = 4, 
    id_to_dirnode: None | EllipsisType | MutableMapping[int, tuple[str, int]] = None, 
    path_already: bool = False, 
    app: str = "android", 
    max_workers: None | int = None, 
    *, 
    async_: Literal[False] = False, 
    **request_kwargs, 
) -> dict:
    ...
@overload
def make_strm(
    client: str | PathLike | P115Client, 
    cid: int | str | Mapping = 0, 
    save_dir: bytes | str | PathLike = ".", 
    base_url: str = "", 
    with_root: None | bool = None, 
    without_suffix: bool = True, 
    clean: bool = True, 
    replace: bool = True, 
    predicate: None | Literal[1, 2, 3, 4, 5, 6, 7] | str | tuple[str, ...] | Callable[[dict], bool] = 4, 
    id_to_dirnode: None | EllipsisType | MutableMapping[int, tuple[str, int]] = None, 
    path_already: bool = False, 
    app: str = "android", 
    max_workers: None | int = None, 
    *, 
    async_: Literal[True], 
    **request_kwargs, 
) -> Coroutine[Any, Any, dict]:
    ...
def make_strm(
    client: str | PathLike | P115Client, 
    cid: int | str | Mapping = 0, 
    save_dir: bytes | str | PathLike = ".", 
    base_url: str = "", 
    with_root: None | bool = None, 
    without_suffix: bool = True, 
    clean: bool = True, 
    replace: bool = True, 
    predicate: None | Literal[1, 2, 3, 4, 5, 6, 7] | str | tuple[str, ...] | Callable[[dict], bool] = 4, 
    id_to_dirnode: None | EllipsisType | MutableMapping[int, tuple[str, int]] = None, 
    path_already: bool = False, 
    app: str = "android", 
    max_workers: None | int = None, 
    *, 
    async_: Literal[False, True] = False, 
    **request_kwargs, 
) -> dict | Coroutine[Any, Any, dict]:
    """拉取目录树，保存到 .strm 文件

    :param client: 115 客户端或 cookies
    :param cid: 目录 id 或 pickcode
    :param save_dir: 本地的保存目录，默认是当前工作目录
    :param base_url: STRM 链接（或者说 302 服务）的基地址
    :param with_root: 是否保留根

        - 如果为 True，则在 ``save_dir`` 保留从根目录 / 开始的目录结构
        - 如果为 False，则在 ``save_dir`` 保留从拉取目录开始的目录结构
        - 如果为 None，则在 ``save_dir`` 下创建一个和 ``cid`` 目录名字相同的目录作为 ``save_dir``，然后保留从拉取目录开始的目录结构

    :param without_suffix: 是否去除原来的扩展名

        - 如果为 True，则去掉原来的扩展名后再拼接
        - 如果为 False，则直接用 ".strm" 拼接到原来的路径后面

    :param clean: 是否清理 ``save_dir``，如果为 True，则删除所有不包含本次更新所涉及到的 .strm 文件和相应目录
    :param replace: 遇到路径下有 .strm 文件时是否替换
    :param predicate: 断言，断言为真的文件才会生成 .strm 文件

        - 如果为 None，则不进行筛选
        - 如果为整数，则筛选某一类型的文件

            - 1: 文档
            - 2: 图片
            - 3: 音频
            - 4: 视频
            - 5: 压缩包
            - 6: 应用
            - 7: 书籍

        - 如果是 str 或元组，则是后缀或一组后缀，筛选这些后缀的文件
        - 如果是 Callable，则逐个对获取到的文件信息调用它，返回值为 True 才保留
 
    :param id_to_dirnode: 字典，保存 id 到对应文件的 ``(name, parent_id)`` 元组的字典
    :param path_already: 如果为 True，则说明 ``id_to_dirnode`` 中已经具备构建路径所需要的目录节点，所以不会再去拉取目录节点的信息
    :param app: 使用指定 app（设备）的接口
    :param max_workers: 最大并发数，用户拉取目录树，但写入本地文件仍然是单线程的（经过测试如此效率更高）
    :param async_: 是否异步
    :param request_kwargs: 其它请求参数

    :return: 一些统计信息
    """
    if isinstance(cid, Mapping):
        cid = cast(int | str, get_first(cid, "id", "pickcode"))
    if isinstance(client, (str, PathLike)):
        client = P115Client(client, check_for_relogin=True)
    user_id = client.user_id
    base_url = base_url.rstrip("/")
    if base_url.startswith("//"):
        base_url = "http:" + base_url
        is_url = True
    else:
        is_url = bool(urlsplit(base_url).scheme)
    save_dir = abspath(fsdecode(save_dir))
    mode = "w" if replace else "x"
    prefix_length = -1
    upserts: list[str] = []
    ignores: list[str] = []
    removes: list[str] = []
    errors: list[OSError] = []
    count_errors: dict[str, int] = defaultdict(int)
    push = list.append
    oserror_flag = False
    @contextmanager
    def collect_oserror():
        nonlocal oserror_flag
        oserror_flag = False
        try:
            yield 
        except OSError as e:
            oserror_flag = True
            push(errors, e)
            count_errors[type(e).__qualname__] += 1
    if clean:
        seen: set[str] = set()
        add_to_seen = seen.add
        def do_clean():
            nonlocal save_dir
            save_dir = cast(str, save_dir)
            with collect_oserror():
                stack = [scandir(save_dir)]
            if oserror_flag:
                return
            if not stack: return
            ancestors: list[str | PathLike] = [save_dir]
            caches: list[list[DirEntry]] = [[]]
            is_dir = DirEntry.is_dir
            t = i = 0
            b = 1
            while i >= 0:
                cache = caches[i]
                for entry in stack[i]:
                    if is_dir(entry, follow_symlinks=False):
                        i += 1
                        with collect_oserror():
                            try:
                                scanit = scandir(entry)
                                stack[i] = scanit
                                ancestors[i] = entry
                                caches[i] = []
                            except IndexError:
                                push(stack, scanit)
                                push(ancestors, entry)
                                push(caches, [])
                        if oserror_flag:
                            t |= b
                            continue
                        b <<= 1
                        break
                    path = entry.path
                    if path in seen:
                        t |= b
                    elif path.endswith(".strm"):
                        with collect_oserror():
                            remove(entry)
                            push(removes, path)
                    else:
                        push(cache, entry)
                else:
                    pred = t & b
                    if not pred:
                        for entry in cache:
                            with collect_oserror():
                                remove(entry)
                                push(removes, entry.path)
                        with collect_oserror():
                            rmdir(ancestors[i])
                    t &= ~b
                    i -= 1
                    b >>= 1
                    if pred:
                        t |= b
    def normalize_path(attr: Mapping, /) -> str:
        nonlocal prefix_length, save_dir, clean
        if prefix_length < 0:
            if cid:
                prefix_length = sum(len(a["name"]) + 1 for a in attr["top_ancestors"]) - 1
                if with_root:
                    save_dir = joinpath(save_dir, *(a["name"] for a in attr["top_ancestors"][1:]))
                elif with_root is None:
                    save_dir = joinpath(save_dir, attr["top_ancestors"][-1]["name"])
            else:
                prefix_length = 0
            try:
                rmdir(save_dir)
                clean = False
            except FileNotFoundError:
                clean = False
            except OSError:
                pass
        path: str = attr["path"]
        if prefix_length:
            path = path[prefix_length:]
        if without_suffix:
            path = splitext(path)[0]
        path = joinpath(cast(str, save_dir), normpath("." + path + ".strm"))
        if clean:
            add_to_seen(path)
        return path
    params: dict = {
        "cid": cid, 
        "max_workers": max_workers, 
        "with_path": True, 
        "id_to_dirnode": id_to_dirnode, 
        "path_already": path_already, 
    }
    if isinstance(predicate, (int, str)):
        params["is_skim"] = False
        if isinstance(predicate, int):
            params["type"] = predicate
        else:
            params["suffix"] = predicate
        predicate = None
    elif isinstance(predicate, tuple):
        suffixes = predicate
        predicate = lambda attr: attr["name"].endswith(suffixes)
    cid = to_id(cid)
    def gen_step():
        files: Iterator[dict] | AsyncIterator[dict] = iter_files_shortcut(
            client, 
            **params, 
            app=app, 
            async_=async_, 
            **request_kwargs, 
        )
        if predicate is not None:
            from iterutils import filter
            files = filter(predicate, files)
        start_t = time()
        with with_iter_next(files) as get_next:
            while True:
                attr = yield get_next()
                path = attr["path"]
                if is_url:
                    url = f"{base_url}/{encode_uri_component_loose(path, quote_slash=False)}?user_id={user_id}&id={attr['id']}&pickcode={attr['pickcode']}&&sha1={attr['sha1']}&size={attr['size']}"
                else:
                    url = base_url + path
                path = normalize_path(attr)
                with collect_oserror():
                    try:
                        file = open(path, mode, encoding="utf-8")
                    except FileNotFoundError:
                        makedirs(dirname(path), exist_ok=True)
                        file = open(path, mode, encoding="utf-8")
                    except FileExistsError:
                        push(ignores, path)
                        continue
                if oserror_flag:
                    push(ignores, path)
                    continue
                with file:
                    file.write(url)
                    push(upserts, path)
        if clean:
            clean_start_t = time()
            if async_:
                yield to_thread(do_clean)
            else:
                do_clean()
        stop_t = time()
        result = {
            "upserts": upserts, 
            "ignores": ignores, 
            "removes": removes, 
            "errors": errors, 
            "total": len(upserts) + len(ignores) + len(removes), 
            "count_upserts": len(upserts), 
            "count_ignores": len(ignores), 
            "count_removes": len(removes), 
            "count_errors": count_errors, 
            "start_time": start_t, 
            "start_time_str": str(datetime.fromtimestamp(start_t)), 
            "stop_time": stop_t, 
            "stop_time_str": str(datetime.fromtimestamp(stop_t)), 
            "elapsed_seconds": stop_t - start_t, 
        }
        if clean:
            result["elapsed_seconds_of_cleaning"] = stop_t - clean_start_t
        return result
    return run_gen_step(gen_step, async_)


# TODO: 如果拉取 max_page 时发现，还存在下一页，则依然需要继续拉取
@overload
def iter_download_nodes(
    client: str | PathLike | P115Client, 
    pickcode: str | int | Mapping = "", 
    files: bool = True, 
    ensure_name: bool = False, 
    id_to_dirnode: None | EllipsisType | MutableMapping[int, tuple[str, int]] = ..., 
    max_workers: None | int = 0, 
    max_page: int | None = 0, 
    app: str = "android", 
    *, 
    async_: Literal[False] = False, 
    **request_kwargs, 
) -> Iterator[dict]:
    ...
@overload
def iter_download_nodes(
    client: str | PathLike | P115Client, 
    pickcode: str | int | Mapping = "", 
    files: bool = True, 
    ensure_name: bool = False, 
    id_to_dirnode: None | EllipsisType | MutableMapping[int, tuple[str, int]] = ..., 
    max_workers: None | int = 0, 
    max_page: int | None = 0, 
    app: str = "android", 
    *, 
    async_: Literal[True], 
    **request_kwargs, 
) -> AsyncIterator[dict]:
    ...
def iter_download_nodes(
    client: str | PathLike | P115Client, 
    pickcode: str | int | Mapping = "", 
    files: bool = True, 
    ensure_name: bool = False, 
    id_to_dirnode: None | EllipsisType | MutableMapping[int, tuple[str, int]] = ..., 
    max_workers: None | int = 0, 
    max_page: int | None = 0, 
    app: str = "android", 
    *, 
    async_: Literal[False, True] = False, 
    **request_kwargs, 
) -> Iterator[dict] | AsyncIterator[dict]:
    """获取一个目录内所有的文件或者目录的信息（简略）

    .. caution::
        不要在不确定的情况下，给 ``max_page`` 设置一个特别大的值，这会大致大量无用的请求，导致服务器繁忙，响应效率低下    

        对于 ``x`` 个文件或目录，相应的 ``d, r = divmod(x, 5000); max_page += (r > 0)``，或者 ``max_page = -(-x // 5000)``

    :param client: 115 客户端或 cookies
    :param pickcode: 目录的 pickcode 或 id
    :param files: 如果为 True，则只获取文件，否则只获取目录
    :param ensure_name: 确保返回数据中有 "name" 字段
    :param id_to_dirnode: 字典，保存 id 到对应文件的 ``(name, parent_id)`` 元组的字典
    :param max_workers: 最大并发数，如果为 None 或 < 0 则自动确定，如果为 0 则单工作者惰性执行
    :param max_page: 要拉取的最大页码（页码从 1 开始计数）

        - 如果为 None，则页码从小到大拉取，并会尝试获取总文件数，当获取到后且还在运行中，则从后往前拉取
        - 如果 > 0，则页码从大到小拉取
        - 如果 <= 0，则页码从小到大拉取

    :param app: 使用指定 app（设备）的接口
    :param async_: 是否异步
    :param request_kwargs: 其它请求参数

    :return: 迭代器，产生文件或者目录的简略信息
    """
    if isinstance(pickcode, Mapping):
        pickcode = cast(str | int, get_first(pickcode, "pickcode", "id"))
    if isinstance(client, (str, PathLike)):
        client = P115Client(client, check_for_relogin=True)
    if max_workers is None or max_workers <= 0:
        max_workers = 20 if async_ else min(32, (cpu_count() or 1) + 4)
    if files:
        get_nodes = client.download_files_app
    else:
        ensure_name = False
        get_nodes = client.download_folders_app
        if id_to_dirnode is None:
            id_to_dirnode = ID_TO_DIRNODE_CACHE[client.user_id]
    file_skim = client.fs_file_skim
    def ensure_names(attrs: Sequence[dict], /):
        if not (ensure_name and attrs):
            return attrs
        def request(attrs: Sequence[dict], /):
            resp = yield file_skim(
                (a["id"] for a in attrs), 
                method="POST", 
                async_=async_, 
                **request_kwargs, 
            )
            if resp.get("error") == "文件不存在":
                return attrs
            check_response(resp)
            nodes = {
                int(node["file_id"]): (
                    ("name", unescape_115_charref(node["file_name"])), 
                    ("sha1", node["sha1"]), 
                ) for node in resp["data"]
            }
            for attr in attrs:
                if items := nodes.get(attr["id"]):
                    attr.update(items)
            return attrs
        return run_gen_step(request(attrs), async_)
    def parse(_, content: bytes, /) -> dict:
        resp = loads(content)
        check_response(resp)
        data = resp["data"]
        if attrs := data["list"]:
            if files:
                for i, info in enumerate(attrs):
                    attrs[i] = {
                        "is_dir": False, 
                        "id": to_id(info["pc"]), 
                        "pickcode": info["pc"], 
                        "parent_id": int(info["pid"]), 
                        "size": info["fs"], 
                    }
            else:
                for i, info in enumerate(attrs):
                    attrs[i] = {
                        "is_dir": True, 
                        "id": int(info["fid"]), 
                        "name": info["fn"], 
                        "parent_id": int(info["pid"]), 
                    }
                if id_to_dirnode is not ... and id_to_dirnode is not None:
                    for attr in attrs:
                        id_to_dirnode[attr["id"]] = (attr["name"], attr["parent_id"])
        return data
    kwargs = {
        **request_kwargs, 
        "parse": parse, 
    }
    if max_workers == 1:
        def iter_list(pickcode: str, /):
            if max_page and max_page > 0:
                cnt: Iterable[int] = range(1, max_page + 1)
            else:
                cnt = count(1)
            for i in cnt:
                resp: dict = yield get_nodes(
                    {"pickcode": pickcode, "page": i}, 
                    app=app, 
                    async_=async_, 
                    **kwargs, 
                )
                yield Yield(resp["list"])
                if not resp["has_next_page"]:
                    break
    else:
        def set_max_page(page: int, /):
            nonlocal max_page
            max_page = page
            for i, p in enumerate(task_page):
                task = task_list[i]
                if task and p > page:
                    task.cancel()
                    countdown(i)
        if max_page and max_page > 0:
            from_first = False
            next_page = iter(range(max_page, 0, -1)).__next__
        elif max_page is None:
            from_first = True
            max_page = 0
            cid = to_id(pickcode)
            if async_:
                task: Any = create_task(client.fs_category_get_app(cid, app=app, async_=True, **request_kwargs))
            else:
                task = run_as_thread(client.fs_category_get_app, cid, app=app, **request_kwargs)
            def callback(fu, /):
                nonlocal task
                try:
                    resp = fu.result()
                    if files:
                        count = int(resp["count"])
                    else:
                        count = int(resp["folder_count"])
                    set_max_page(-(-count // 5000))
                finally:
                    task = None
            task.add_done_callback(callback)
            def next_page_iter():
                nonlocal from_first
                for i in count(1):
                    yield i
                    if max_page and task is None:
                        break
                from_first = False
                for i in range(cast(int, max_page), i, -1):
                    yield i
            next_page = next_page_iter().__next__
        else:
            if max_page < 0:
                max_page = 0
            from_first = True
            next_page = count(1).__next__
        sentinel = object()
        if async_:
            q: AsyncQueue | SimpleQueue = AsyncQueue()
        else:
            q = SimpleQueue()
            lock = Lock()
        get, put = q.get, q.put_nowait
        task_list: list = []
        task_page: list[int] = []
        task_ids: set[int] = set()
        discard_task_id = task_ids.discard
        def countdown(task_id, /):
            task_list[task_id] = None
            discard_task_id(task_id)
            if not task_ids:
                put(sentinel)
        def request(task_id, pickcode: str, /):
            try:
                while True:
                    if async_:
                        page = next_page()
                    else:
                        with lock:
                            page = next_page()
                    if max_page and page > max_page:
                        if from_first:
                            break
                        else:
                            continue
                    task_page[task_id] = page
                    resp: dict = yield get_nodes(
                        {"pickcode": pickcode, "page": page}, 
                        app=app, 
                        async_=async_, 
                        **kwargs, 
                    )
                    put(resp["list"])
                    if not resp["has_next_page"]:
                        set_max_page(page)
            except StopIteration:
                pass
            except BaseException as e:
                put(e)
            finally:
                countdown(task_id)
        def iter_list(pickcode: str, /):
            if async_:
                n = cast(int, max_workers)
                task_group = TaskGroup()
                yield task_group.__aenter__()
                create_task = task_group.create_task
                submit: Callable = lambda f, /, *a, **k: create_task(f(*a, **k))
                shutdown: Callable = lambda: task_group.__aexit__(*exc_info())
            else:
                executor = ThreadPoolExecutor(max_workers)
                n = executor._max_workers
                submit = executor.submit
                shutdown = lambda: executor.shutdown(False, cancel_futures=True)
            try:
                task_ids.update(range(n))
                task_list.extend(repeat(None, n))
                task_page.extend(repeat(0, n))
                for i in range(n):
                    task_list[i] = submit(run_gen_step, request(i, pickcode), async_)
                while True:
                    if async_:
                        resp = yield get()
                    else:
                        resp = get()
                    if resp is sentinel:
                        break
                    elif isinstance(resp, (CancelledError, AsyncCancelledError)):
                        continue
                    elif isinstance(resp, BaseException):
                        raise resp
                    yield Yield(resp)
            finally:
                yield shutdown()
    def gen_step(pickcode, /):
        it = run_gen_step_iter(iter_list(pickcode), async_)
        if ensure_name:
            it = conmap(ensure_names, it, max_workers=max_workers, async_=async_)
        return chain_from_iterable(it, async_=async_) # type: ignore
    if pickcode := client.to_pickcode(pickcode):
        return gen_step(pickcode)
    else:
        def chain():
            pickcodes: list[str] = []
            add_pickcode = pickcodes.append
            with with_iter_next(iterdir(
                client, 
                ensure_file=None if files else False, 
                app=app, 
                normalize_attr=normalize_attr_simple, 
                id_to_dirnode=id_to_dirnode, 
                raise_for_changed_count=True, 
                async_=async_, 
                **request_kwargs, 
            )) as get_next:
                while True:
                    attr = yield get_next()
                    if attr["is_dir"]:
                        if not files:
                            yield Yield(attr)
                        add_pickcode(attr["pickcode"])
                    elif files:
                        yield Yield(attr)
            for pickcode in pickcodes:
                yield YieldFrom(gen_step(pickcode))
        return run_gen_step_iter(chain, async_)


@overload
def iter_download_files(
    client: str | PathLike | P115Client, 
    cid: int | str | Mapping = 0, 
    ensure_name: bool = False, 
    escape: None | bool | Callable[[str], str] = True, 
    with_ancestors: bool = False, 
    id_to_dirnode: None | EllipsisType | MutableMapping[int, tuple[str, int]] = None, 
    path_already: bool = False, 
    max_workers: None | int = 0, 
    max_files: int | None = 0, 
    max_dirs: int | None = 0, 
    app: str = "android", 
    *, 
    async_: Literal[False] = False, 
    **request_kwargs, 
) -> Iterator[dict]:
    ...
@overload
def iter_download_files(
    client: str | PathLike | P115Client, 
    cid: int | str | Mapping = 0, 
    ensure_name: bool = False, 
    escape: None | bool | Callable[[str], str] = True, 
    with_ancestors: bool = False, 
    id_to_dirnode: None | EllipsisType | MutableMapping[int, tuple[str, int]] = None, 
    path_already: bool = False, 
    max_workers: None | int = 0, 
    max_files: int | None = 0, 
    max_dirs: int | None = 0, 
    app: str = "android", 
    *, 
    async_: Literal[True], 
    **request_kwargs, 
) -> AsyncIterator[dict]:
    ...
def iter_download_files(
    client: str | PathLike | P115Client, 
    cid: int | str | Mapping = 0, 
    ensure_name: bool = False, 
    escape: None | bool | Callable[[str], str] = True, 
    with_ancestors: bool = False, 
    id_to_dirnode: None | EllipsisType | MutableMapping[int, tuple[str, int]] = None, 
    path_already: bool = False, 
    max_workers: None | int = 0, 
    max_files: int | None = 0, 
    max_dirs: int | None = 0, 
    app: str = "android", 
    *, 
    async_: Literal[False, True] = False, 
    **request_kwargs, 
) -> Iterator[dict] | AsyncIterator[dict]:
    """获取一个目录内所有的文件信息，不包括目录

    :param client: 115 客户端或 cookies
    :param cid: 目录 id 或 pickcode
    :param ensure_name: 确保返回数据中有 "name" 字段
    :param escape: 对文件名进行转义

        - 如果为 None，则不处理；否则，这个函数用来对文件名中某些符号进行转义，例如 "/" 等
        - 如果为 True，则使用 `posixpatht.escape`，会对文件名中 "/"，或单独出现的 "." 和 ".." 用 "\\" 进行转义
        - 如果为 False，则使用 `posix_escape_name` 函数对名字进行转义，会把文件名中的 "/" 转换为 "|"
        - 如果为 Callable，则用你所提供的调用，以或者转义后的名字

    :param with_ancestors: 文件信息中是否要包含 "ancestors"
    :param id_to_dirnode: 字典，保存 id 到对应文件的 ``(name, parent_id)`` 元组的字典
    :param path_already: 如果为 True，则说明 id_to_dirnode 中已经具备构建路径所需要的目录节点，所以不会再去拉取目录节点的信息
    :param max_workers: 最大并发数，如果为 None 或 < 0 则自动确定，如果为 0 则单工作者惰性执行
    :param max_files: 估计最大存在的文件数，<= 0 时则无限
    :param max_dirs: 估计最大存在的目录数，<= 0 时则无限
    :param app: 使用指定 app（设备）的接口
    :param async_: 是否异步
    :param request_kwargs: 其它请求参数

    :return: 迭代器，产生文件的简略信息
    """
    if isinstance(cid, Mapping):
        cid = cast(int | str, get_first(cid, "id", "pickcode"))
    if isinstance(client, (str, PathLike)):
        client = P115Client(client, check_for_relogin=True)
    if id_to_dirnode is None:
        id_to_dirnode = ID_TO_DIRNODE_CACHE[client.user_id]
    elif id_to_dirnode is ...:
        id_to_dirnode = {}
        path_already = False
    from .iterdir import make_path_binder
    bind = make_path_binder(
        id_to_dirnode, 
        escape=escape, 
        with_ancestors=with_ancestors, 
        key_of_path="path" if ensure_name else "dirname", 
        key_of_ancestors="ancestors" if ensure_name else "dir_ancestors", 
    )
    top_id = cid = to_id(cid)
    top_ancestors: list[dict]
    top_path: str
    top_prefix_len: int = 0
    def update_attr(attr: dict, /):
        nonlocal top_ancestors, top_path, top_prefix_len
        if not top_prefix_len:
            if cid:
                top_path = bind.get_path(top_id) # type: ignore
                if with_ancestors:
                    top_ancestors = bind.get_ancestors(top_id) # type: ignore
                top_prefix_len = len(top_path) + 1
            else:
                top_ancestors = [{"id": 0, "parent_id": 0, "name": ""}]
                top_path = "/"
                top_prefix_len = 1
        attr["top_id"] = top_id
        attr["top_path"] = top_path
        if with_ancestors:
            attr["top_ancestors"] = top_ancestors
        try:
            bind(attr)
            if ensure_name:
                attr["relpath"] = attr["path"][top_prefix_len:]
            else:
                attr["rel_dirname"] = attr["dirname"][top_prefix_len:]
        except KeyError:
            pass
        return attr
    if path_already:
        def iter_nonroot(pickcode: str, /):
            return do_map(update_attr, iter_download_nodes(
                client, 
                pickcode, 
                files=True, 
                ensure_name=ensure_name, 
                max_workers=max_workers, 
                max_page=max_files and -(-max_files // 5000), 
                app=app, 
                async_=async_, 
                **request_kwargs, 
            ))
    else:
        class BoolRaise:
            def __init__(self, /, exception):
                self.exception = exception
            def __bool__(self, /):
                raise self.exception
        path_not_already: bool | BoolRaise = True
        def set_path_already(fu, /):
            nonlocal path_not_already
            if isinstance(fu, BaseException):
                exc = fu
            else:
                exc = fu.exception()
            if exc is None:
                path_not_already = False
            else:
                path_not_already = BoolRaise(exc)
        def gen_step(pickcode: str, /):
            nonlocal path_already
            path_already = False
            def load_ancestors(pickcode: str, /):
                return through(iter_download_nodes(
                    client, 
                    pickcode, 
                    files=False, 
                    id_to_dirnode=id_to_dirnode, 
                    max_workers=max_workers, 
                    max_page=max_dirs and -(-max_dirs // 5000), 
                    app=app, 
                    async_=async_, 
                    **request_kwargs, 
                ))
            if async_:
                task: Any = create_task(load_ancestors(pickcode))
            else:
                task = run_as_thread(load_ancestors, pickcode)
            if cid:
                from .attr import get_ancestors
                def update_top():
                    return (yield get_ancestors(
                        client, 
                        cid, 
                        id_to_dirnode=id_to_dirnode, 
                        ensure_file=False, 
                        app=app, 
                        async_=async_, 
                        **request_kwargs, 
                    ))
                if async_:
                    task2 = async_gather(run_gen_step(update_top, True), task)
                    task2.add_done_callback(set_path_already)
                else:
                    task0 = run_as_thread(run_gen_step, update_top, False)
                    def done_callback(fu, /):
                        try:
                            task0.result()
                        except BaseException as e:
                            set_path_already(e)
                        else:
                            set_path_already(fu)
                    task.add_done_callback(done_callback)
            else:
                task.add_done_callback(set_path_already)
            cache: list[dict] = []
            add_to_cache = cache.append
            with with_iter_next(iter_download_nodes(
                client, 
                pickcode, 
                files=True, 
                ensure_name=ensure_name, 
                max_workers=max_workers, 
                max_page=max_files and -(-max_files // 5000), 
                app=app, 
                async_=async_, 
                **request_kwargs, 
            )) as get_next:
                while path_not_already:
                    add_to_cache((yield get_next()))
                if cache:
                    yield YieldFrom(do_map(update_attr, cache))
                    cache.clear()
                while True:
                    yield Yield(update_attr((yield get_next())))
            if cache:
                if async_:
                    yield task
                else:
                    task.result()
                bool(path_not_already)
                yield YieldFrom(do_map(update_attr, cache))
        def iter_nonroot(pickcode: str, /):
            return run_gen_step_iter(gen_step(pickcode), async_)
    if cid:
        return iter_nonroot(client.to_pickcode(cid))
    else:
        def iter_root():
            pickcodes: list[str] = []
            add_pickcode = pickcodes.append
            with with_iter_next(iterdir(
                client, 
                id_to_dirnode=id_to_dirnode, 
                app=app, 
                raise_for_changed_count=True, 
                async_=async_, 
                **request_kwargs, 
            )) as get_next:
                while True:
                    attr = yield get_next()
                    if attr["is_dir"]:
                        add_pickcode(attr["pickcode"])
                    else:
                        attr = {
                            "parent_id": attr["parent_id"], 
                            "pickcode": attr["pickcode"], 
                            "size": attr["size"], 
                        }
                        yield Yield(update_attr(attr))
            for pickcode in pickcodes:
                yield YieldFrom(iter_nonroot(pickcode))
        return run_gen_step_iter(iter_root, async_)


@overload
def get_remaining_open_count(
    client: str | PathLike | P115Client | P115OpenClient, 
    app: str = "android", 
    *, 
    async_: Literal[False] = False, 
    **request_kwargs, 
) -> int:
    ...
@overload
def get_remaining_open_count(
    client: str | PathLike | P115Client | P115OpenClient, 
    app: str = "android", 
    *, 
    async_: Literal[True], 
    **request_kwargs, 
) -> Coroutine[Any, Any, int]:
    ...
def get_remaining_open_count(
    client: str | PathLike | P115Client | P115OpenClient, 
    app: str = "android", 
    *, 
    async_: Literal[False, True] = False, 
    **request_kwargs, 
) -> int | Coroutine[Any, Any, int]:
    """获取剩余的可打开下载链接数

    .. note::
        假设总数是 n，通常总数是 10，偶尔会调整，如果已经有 m 个被打开的链接，则返回的数字是 n-m

    :param client: 115 客户端或 cookies
    :param app: 使用指定 app（设备）的接口
    :param async_: 是否异步
    :param request_kwargs: 其它请求参数

    :return: 个数
    """
    if isinstance(client, (str, PathLike)):
        client = P115Client(client, check_for_relogin=True)
    if not isinstance(client, P115Client) or app == "open":
        get_url: Callable[..., P115URL] = client.download_url_open
    elif app in ("", "web", "desktop", "harmony"):
        get_url = client.download_url
    else:
        get_url = partial(client.download_url, app=app)
    def gen_step():
        cache: list = []
        add_to_cache = cache.append
        try:
            if isinstance(client, P115OpenClient):
                it: Iterator[dict] | AsyncIterator[dict] = iter_files(
                    client, 
                    type=4, 
                    app=app, 
                    async_=async_, # type: ignore
                    **request_kwargs, 
                )
            else:
                it = iter_download_nodes(
                    client, 
                    app=app, 
                    async_=async_, 
                    **request_kwargs, 
                )
            with with_iter_next(it) as get_next:
                while True:
                    attr = yield get_next()
                    if attr["size"] <= 1024 * 1024 * 200:
                        continue
                    try:
                        url = yield get_url(attr["pickcode"], async_=async_)
                    except FileNotFoundError:
                        continue
                    request = Request(url, headers={"user-agent": ""})
                    if async_:
                        file = yield to_thread(urlopen, request)
                    else:
                        file = urlopen(request)
                    add_to_cache(file)
        finally:
            for f in cache:
                f.close()
            return len(cache)
    return run_gen_step(gen_step, async_)

# TODO: 增加一个工具函数，用于从某个网上目录下载到本地目录，允许提供自定义的进度条调用
