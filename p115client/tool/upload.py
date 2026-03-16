#!/usr/bin/env python3
# encoding: utf-8

from __future__ import annotations

__author__ = "ChenyangGao <https://chenyanggao.github.io>"
__all__ = [
    "upload_host_image", "iter_115_to_115", "iter_115_to_115_resume", 
    "sha1_for_check_existence", "upload_for_check_existence", 
    "upload_init", "P115MultipartUpload", 
]
__doc__ = "这个模块提供了一些和上传有关的函数"

from collections.abc import (
    AsyncIterable, AsyncIterator, Awaitable, Buffer, Iterable, Callable, 
    Coroutine, Iterator, 
)
from inspect import isawaitable
from itertools import count, dropwhile
from os import fsdecode, PathLike
from typing import cast, overload, Any, Literal

from asynctools import to_list
from concurrenttools import threadpool_map, taskgroup_map, Return
from dicttools import dict_map
from filewrap import SupportsRead
from http_request import SupportsGeturl
from iterutils import (
    as_gen_step, foreach, run_gen_step, run_gen_step_iter, 
    with_iter_next, YieldFrom, 
)
from p115oss import (
    oss_upload_init, oss_multipart_upload_init, oss_multipart_upload_complete, 
    oss_multipart_upload_url, oss_multipart_part_iter, oss_multipart_upload_part_iter, 
)
from p115pickcode import to_id
from yarl import URL

from ..client import check_response, P115Client, P115OpenClient
from ..type import P115URL
from ..tool import load_final_image
from .attr import normalize_attr_simple
from .download import iter_download_files
from .iterdir import iterdir, iter_files_with_path, unescape_115_charref


@overload
def upload_host_image(
    client: str | PathLike | P115Client, 
    file: ( Buffer | str | PathLike | URL | SupportsGeturl | 
            SupportsRead | Iterable[Buffer] ), 
    base_url: bool | str = False, 
    *, 
    async_: Literal[False] = False, 
    **request_kwargs, 
) -> P115URL:
    ...
@overload
def upload_host_image(
    client: str | PathLike | P115Client, 
    file: ( Buffer | str | PathLike | URL | SupportsGeturl | 
            SupportsRead | Iterable[Buffer] | AsyncIterable[Buffer] ), 
    base_url: bool | str = False, 
    *, 
    async_: Literal[True], 
    **request_kwargs, 
) -> Coroutine[P115URL, Any, Any]:
    ...
def upload_host_image(
    client: str | PathLike | P115Client, 
    file: ( Buffer | str | PathLike | URL | SupportsGeturl | 
            SupportsRead | Iterable[Buffer] | AsyncIterable[Buffer] ), 
    base_url: bool | str = False, 
    *, 
    async_: Literal[False, True] = False, 
    **request_kwargs, 
) -> P115URL | Coroutine[P115URL, Any, Any]:
    """上传图片，然后可作为图床使用

    .. caution::
        115 网盘允许图片最大到 50 MB

    :param client: 115 网盘客户端对象
    :param file: 待上传的文件
    :param base_url: 图片的基地址

        - 如果为 False，上传到 U_4_-1，获取一次性的图片链接，有效时间 1 小时
        - 如果为 True，上传到 U_4_-1，获取永久的图片链接
        - 如果为 str，上传到 U_12_0，视为 302 代理，会把 user_id、id、pickcode、sha1 和 size 作为查询参数拼接到其后

    :param async_: 是否异步
    :param request_kwargs: 其余请求参数

    :return: 图片链接
    """
    if isinstance(client, (str, PathLike)):
        client = P115Client(client, check_for_relogin=True)
    def gen_step():
        if isinstance(base_url, bool):
            resp = yield client.upload_file_image(
                file, # type: ignore
                filename="x.jpg", 
                async_=async_, # type: ignore
                **request_kwargs, 
            )
            check_response(resp)
            data = {
                "oss": resp["data"]["sha1"], 
                "sha1": resp["data"]["file_sha1"], 
                "size": int(resp["data"]["file_size"]), 
            }
            if base_url:
                resp = yield client.life_get_pic_url(
                    resp["data"]["sha1"], 
                    async_=async_, # type: ignore
                    **request_kwargs, 
                )
                check_response(resp)
                return P115URL(resp["data"][0]["json"].replace("&i=0", "&i=1"), data)
            url = resp["data"]["thumb_url"]
            return P115URL(url[:url.index("?")], data)
        resp = yield client.upload_file_sample(
            file, # type: ignore
            filename="x.jpg", 
            pid="U_12_0", 
            async_=async_, # type: ignore
            **request_kwargs, 
        )
        check_response(resp)
        data = resp["data"]
        url = base_url + "?&"["?" in base_url]
        return P115URL(
            url + f"user_id={client.user_id}&id={data["file_id"]}&pickcode={data["pick_code"]}&sha1={data["sha1"]}&size={data["file_size"]}", 
            resp["data"], 
        )
    return run_gen_step(gen_step, async_)


# TODO: 需要优化，减少代码量
# TODO: 支持 open 接口
# TODO: 再支持一个方法，目标 115 并不提供 client，只有 user_id 和 user_key
@overload
def iter_115_to_115(
    from_client: P115Client, 
    to_client: P115Client, 
    from_cid: int | str = 0, 
    to_pid: int | str = 0, 
    max_workers: int = 8, 
    with_root: bool = True, 
    use_iter_files: bool = False, 
    *, 
    async_: Literal[False] = False, 
    **request_kwargs, 
) -> Iterator[dict]:
    ...
@overload
def iter_115_to_115(
    from_client: P115Client, 
    to_client: P115Client, 
    from_cid: int | str = 0, 
    to_pid: int | str = 0, 
    max_workers: int = 8, 
    with_root: bool = True, 
    use_iter_files: bool = False, 
    *, 
    async_: Literal[True], 
    **request_kwargs, 
) -> AsyncIterator[dict]:
    ...
def iter_115_to_115(
    from_client: P115Client, 
    to_client: P115Client, 
    from_cid: int | str = 0, 
    to_pid: int | str = 0, 
    max_workers: int = 8, 
    with_root: bool = True, 
    use_iter_files: bool = False, 
    async_: Literal[False, True] = False, 
    **request_kwargs, 
) -> Iterator[dict] | AsyncIterator[dict]:
    """从 115 传到 115

    :param from_client: 来源 115 客户端对象
    :param to_client: 去向 115 客户端对象
    :param from_cid: 来源 115 的目录 id 或 pickcode
    :param to_pid: 去向 115 的父目录 id 或 pickcode
    :param max_workers: 最大并发数
    :param with_root: 是否保留 `from_cid` 对应的目录名（如果为 False，则会少 1 级目录）
    :param use_iter_files: 如果为 True，则调用 iter_files_with_path，否则调用 iter_download_files
    :param async_: 是否异步
    :param request_kwargs: 其它请求参数

    :return: 迭代器，产生转移结果，有 3 种类型："good"、"fail" 和 "skip"
    """
    from_cid = to_id(from_cid)
    to_pid = to_id(to_pid)
    @as_gen_step
    def upload(attr: dict, pid: int, /):
        @as_gen_step
        def read_range_bytes_or_hash(sign_check: str, /):
            if attr["is_collect"]:
                url = yield from_client.download_url(
                    attr["pickcode"], 
                    use_web_api=True, 
                    async_=async_, 
                    **request_kwargs, 
                )
            else:
                url = yield from_client.download_url(
                    attr["pickcode"], 
                    app="android", 
                    async_=async_, 
                    **request_kwargs, 
                )
            return from_client.request(
                url, 
                headers=dict(url["headers"], range="bytes="+sign_check), 
                parse=False, 
                async_=async_, 
                **request_kwargs, 
            )
        try:
            if not use_iter_files:
                resp = yield from_client.fs_supervision(
                    attr["pickcode"], 
                    async_=async_, 
                    **request_kwargs, 
                )
                check_response(resp)
                info = resp["data"]
                attr.update(
                    id=int(info["file_id"]), 
                    name=info["file_name"], 
                    sha1=info["file_sha1"], 
                    size=int(info["file_size"]), 
                    is_collect=int(info["is_collect"]), 
                    file_type=int(info["file_type"]), 
                )
                if attr["is_collect"] and attr["size"] >= 1024 * 1024 * 115:
                    return {"type": "skip", "attr": attr, "resp": None}
            resp = yield to_client.upload_file_init(
                filename=attr["name"], 
                filesize=attr["size"], 
                filesha1=attr["sha1"], 
                pid=pid, 
                read_range_bytes_or_hash=read_range_bytes_or_hash, 
                base_url=True, 
                async_=async_, 
                **request_kwargs, 
            )
            check_response(resp)
            if resp.get("statuscode"):
                return {"type": "fail", "attr": attr, "resp": resp}
            else:
                return {"type": "good", "attr": attr, "resp": resp}
        except BaseException as e:
            if isinstance(e, OSError) and len(e.args) == 2 and isinstance(e.args[1], dict):
                return {"type": "fail", "attr": attr, "resp": e.args[1], "exc": e}
            else:
                return {"type": "fail", "attr": attr, "resp": None, "exc": e}
    key_of_id = "id" if with_root else "parent_id"
    @as_gen_step
    def get_pid(attr: dict, /):
        if use_iter_files:
            if attr["is_collect"] and attr["size"] >= 1024 * 1024 * 115:
                return Return({"type": "skip", "attr": attr, "resp": None})
            if from_cid:
                dir_ = "/".join(a["name"] for a in dropwhile(
                    lambda a: a[key_of_id] != from_cid, 
                    attr["ancestors"][1:-1], 
                ))
            else:
                dir_ = "/".join(a["name"] for a in attr["ancestors"][1:-1])
        else:
            if from_cid:
                dir_ = "/".join(a["name"] for a in dropwhile(
                    lambda a: a[key_of_id] != from_cid, 
                    attr["dir_ancestors"][1:], 
                ))
            else:
                dir_ = attr["dirname"][1:]
        if dir_ in dir_to_cid:
            return dir_to_cid[dir_]
        else:
            resp = yield to_client.fs_makedirs_app(
                dir_, 
                to_pid, 
                async_=async_, 
                **request_kwargs, 
            )
            check_response(resp)
            pid = dir_to_cid[dir_] = resp["cid"]
            return pid
    dir_to_cid = {"": 0}
    if use_iter_files:
        it = iter_files_with_path(
            from_client, 
            from_cid, 
            normalize_attr=normalize_attr_simple, 
            async_=async_, 
            **request_kwargs, 
        )
    else:
        it = iter_download_files(
            from_client, 
            from_cid, 
            async_=async_, 
            **request_kwargs, 
        )
    if async_:
        return taskgroup_map(upload, it, arg_func=get_pid, max_workers=max_workers)
    else:
        return threadpool_map(upload, it, arg_func=get_pid, max_workers=max_workers)


# TODO: 需要优化，减少代码量
# TODO: 支持一次性把所有文件找完，也支持慢慢处理（可能会风控）
# TODO: 支持 open 接口
@overload
def iter_115_to_115_resume(
    from_client: P115Client, 
    to_client: P115Client, 
    from_cid: int | str = 0, 
    to_pid: int | str = 0, 
    max_workers: int = 8, 
    with_root: bool = True, 
    *, 
    async_: Literal[False] = False, 
    **request_kwargs, 
) -> Iterator[dict]:
    ...
@overload
def iter_115_to_115_resume(
    from_client: P115Client, 
    to_client: P115Client, 
    from_cid: int | str = 0, 
    to_pid: int | str = 0, 
    max_workers: int = 8, 
    with_root: bool = True, 
    *, 
    async_: Literal[True], 
    **request_kwargs, 
) -> AsyncIterator[dict]:
    ...
def iter_115_to_115_resume(
    from_client: P115Client, 
    to_client: P115Client, 
    from_cid: int | str = 0, 
    to_pid: int | str = 0, 
    max_workers: int = 8, 
    with_root: bool = True, 
    *, 
    async_: Literal[False, True] = False, 
    **request_kwargs, 
) -> Iterator[dict] | AsyncIterator[dict]:
    """从 115 传到 115（可以跳过已经存在的文件）

    :param from_client: 来源 115 客户端对象
    :param to_client: 去向 115 客户端对象
    :param from_cid: 来源 115 的目录 id 或 pickcode（文件数最好控制在 100 万以内，太多的话，里面多个子文件夹分别传即可）
    :param to_pid: 去向 115 的父目录 id 或 pickcode
    :param max_workers: 最大并发数
    :param with_root: 是否保留 `from_cid` 对应的目录名（如果为 False，则会少 1 级目录）
    :param async_: 是否异步
    :param request_kwargs: 其它请求参数

    :return: 迭代器，产生转移结果，有 3 种类型："good"、"fail" 和 "skip"
    """
    from_cid = to_id(from_cid)
    to_pid = to_id(to_pid)
    @as_gen_step
    def upload(attr: dict, pid: int, /):
        @as_gen_step
        def read_range_bytes_or_hash(sign_check: str, /):
            if attr["is_collect"]:
                url = yield from_client.download_url(
                    attr["pickcode"], 
                    use_web_api=True, 
                    async_=async_, 
                    **request_kwargs, 
                )
            else:
                url = yield from_client.download_url(
                    attr["pickcode"], 
                    app="android", 
                    async_=async_, 
                    **request_kwargs, 
                )
            return from_client.request(
                url, 
                headers=dict(url["headers"], range="bytes="+sign_check), 
                parse=False, 
                async_=async_, 
                **request_kwargs, 
            )
        try:
            resp = yield to_client.upload_file_init(
                filename=attr["name"], 
                filesize=attr["size"], 
                filesha1=attr["sha1"], 
                pid=pid, 
                read_range_bytes_or_hash=read_range_bytes_or_hash, 
                base_url=True, 
                async_=async_, 
                **request_kwargs, 
            )
            check_response(resp)
            if resp.get("statuscode"):
                return {"type": "fail", "attr": attr, "resp": resp}
            else:
                return {"type": "good", "attr": attr, "resp": resp}
        except BaseException as e:
            if isinstance(e, OSError) and len(e.args) == 2 and isinstance(e.args[1], dict):
                return {"type": "fail", "attr": attr, "resp": e.args[1], "exc": e}
            else:
                return {"type": "fail", "attr": attr, "resp": None, "exc": e}
    dirt_to_cid: dict[tuple[str, ...], int] = {}
    key_of_id = "id" if with_root else "parent_id"
    @as_gen_step
    def get_pid(attr: dict, /):
        if attr["is_collect"] and attr["size"] >= 1024 * 1024 * 115:
            return Return({"type": "skip", "attr": attr, "resp": None})
        dirt = tuple(a["name"] for a in dropwhile(
            lambda a: a[key_of_id] != from_cid, 
            attr["ancestors"][1:-1], 
        ))
        try:
            return dirt_to_cid[dirt]
        except KeyError:
            pid = dirt_to_cid[()]
            for i, name in enumerate(dirt, 1):
                p_dirt = dirt[:i]
                if p_dirt in dirt_to_cid:
                    pid = dirt_to_cid[p_dirt]
                else:
                    resp = yield to_client.fs_mkdir(
                        name, 
                        pid, 
                        async_=async_, 
                        **request_kwargs, 
                    )
                    check_response(resp)
                    pid = dirt_to_cid[p_dirt] = int(resp["cid"])
            return pid
    def gen_step():
        from_files: Any = iter_files_with_path(
            from_client, 
            from_cid, 
            normalize_attr=normalize_attr_simple, 
            with_ancestors=True, 
            async_=async_, 
            **request_kwargs, 
        )
        if from_cid:
            resp = yield from_client.fs_file_skim(
                from_cid, 
                async_=async_, 
                **request_kwargs, 
            )
            check_response(resp)
            name = unescape_115_charref(resp["data"][0]["file_name"])
            resp = yield to_client.fs_mkdir(
                name, 
                to_pid, 
                async_=async_, 
                **request_kwargs, 
            )
            if resp.get("errno") == 20004:
                if "/" in name:
                    with with_iter_next(iterdir(
                        to_client, 
                        to_pid, 
                        normalize_attr=normalize_attr_simple, 
                        ensure_file=False, 
                        async_=async_, 
                        **request_kwargs, 
                    )) as get_next:
                        while True:
                            attr = yield get_next()
                            if attr["name"] == name:
                                to_cid = attr["id"]
                                break
                else:
                    resp = yield to_client.fs_makedirs_app(
                        name, 
                        to_pid, 
                        async_=async_, 
                        **request_kwargs, 
                    )
                    check_response(resp)
                    to_cid = int(resp["cid"])
                dirt_to_cid[()] = to_cid
                id_to_dirnode: dict[int, tuple[str, int]] = {}
                to_files: Any = iter_files_with_path(
                    to_client, 
                    to_cid, 
                    id_to_dirnode=id_to_dirnode, 
                    normalize_attr=normalize_attr_simple, 
                    with_ancestors=True, 
                    async_=async_, 
                    **request_kwargs, 
                )
                if async_:
                    from_files, to_files = yield to_list(
                        taskgroup_map(to_list, (from_files, to_files), max_workers=2))
                else:
                    from_files, to_files = threadpool_map(list, (from_files, to_files), max_workers=2)
                while to_cid:
                    _, to_cid = id_to_dirnode.pop(to_cid)
                cid_to_dirt: dict[int, tuple[str, ...]] = {}
                def get_dirt(cid: int, /) -> tuple[str, ...]:
                    if cid not in id_to_dirnode:
                        return ()
                    name, pid = id_to_dirnode[cid]
                    if pid in cid_to_dirt:
                        p_dirt = cid_to_dirt[pid]
                    else:
                        p_dirt = get_dirt(pid)
                    dirt = (*p_dirt, name)
                    dirt_to_cid[dirt] = cid
                    cid_to_dirt[cid] = dirt
                    return dirt
                for cid, (name, pid) in id_to_dirnode.items():
                    if cid not in cid_to_dirt:
                        get_dirt(cid)
                del cid_to_dirt, id_to_dirnode
                to_cid = dirt_to_cid[()]
                seen = {
                    tuple(a["name"] for a in dropwhile(
                        lambda a: a["parent_id"] != to_cid, 
                        attr["ancestors"][1:], 
                    )) for attr in to_files
                }
                from_files = [
                    attr for attr in from_files
                    if tuple(a["name"] for a in dropwhile(
                        lambda a: a["parent_id"] != from_cid, 
                        attr["ancestors"][1:], 
                    )) not in seen
                ]
                del to_files, seen
            else:
                check_response(resp)
                dirt_to_cid[()] = int(resp["cid"])
        else:
            dirt_to_cid[()] = 0
        if async_:
            return YieldFrom(taskgroup_map(
                upload, 
                from_files, 
                arg_func=get_pid, 
                max_workers=max_workers, 
            ))
        else:
            return YieldFrom(threadpool_map(
                upload, 
                from_files, 
                arg_func=get_pid, 
                max_workers=max_workers, 
            ))
    return run_gen_step_iter(gen_step, async_)


@overload
def sha1_for_check_existence(
    client: str | PathLike | P115Client, 
    sha1: str, 
    *, 
    async_: Literal[False] = False, 
    **request_kwargs, 
) -> bool:
    ...
@overload
def sha1_for_check_existence(
    client: str | PathLike | P115Client, 
    sha1: str, 
    *, 
    async_: Literal[True], 
    **request_kwargs, 
) -> Coroutine[Any, Any, bool]:
    ...
def sha1_for_check_existence(
    client: str | PathLike | P115Client, 
    sha1: str, 
    *, 
    async_: Literal[False, True] = False, 
    **request_kwargs, 
) -> bool | Coroutine[Any, Any, bool]:
    """判断某个文件（用 `sha1` 唯一确定）是否存在于 115 网盘上（但不一定在你自己的网盘中）

    :param client: 115 客户端或 cookies
    :param sha1: 文件的 sha1 哈希值
    :param async_: 是否异步
    :param request_kwargs: 其它请求参数

    :return: 是否存在文件
    """
    if isinstance(client, (str, PathLike)):
        client = P115Client(client, check_for_relogin=True)
    def gen_step():
        resp = yield client.note_get_pic_url(sha1, async_=async_, **request_kwargs)
        check_response(resp)
        ret = yield load_final_image(resp["data"][0], async_=async_)
        return ret != 404
    return run_gen_step(gen_step, async_)


@overload
def upload_for_check_existence(
    client: str | PathLike | P115Client | P115OpenClient, 
    sha1: str, 
    size: int, 
    *, 
    async_: Literal[False] = False, 
    **request_kwargs, 
) -> bool:
    ...
@overload
def upload_for_check_existence(
    client: str | PathLike | P115Client | P115OpenClient, 
    sha1: str, 
    size: int, 
    *, 
    async_: Literal[True], 
    **request_kwargs, 
) -> Coroutine[Any, Any, bool]:
    ...
def upload_for_check_existence(
    client: str | PathLike | P115Client | P115OpenClient, 
    sha1: str, 
    size: int, 
    *, 
    async_: Literal[False, True] = False, 
    **request_kwargs, 
) -> bool | Coroutine[Any, Any, bool]:
    """通过秒传接口，判断某个文件（用 `sha1` 和 `size` 唯一确定）是否存在于 115 网盘上（但不一定在你自己的网盘中）

    :param client: 115 客户端或 cookies
    :param sha1: 文件的 sha1 哈希值
    :param size: 文件大小
    :param async_: 是否异步
    :param request_kwargs: 其它请求参数

    :return: 是否存在文件
    """
    if isinstance(client, (str, PathLike)):
        client = P115Client(client, check_for_relogin=True)
    def gen_step():
        if isinstance(client, P115Client):
            resp = yield client.upload_init(
                {"fileid": sha1.upper(), "filesize": size, "filename": "?"}, 
                async_=async_, 
                **request_kwargs, 
            )
        else:
            resp = yield client.upload_init_open(
                {"fileid": sha1.upper(), "file_size": size, "file_name": "?", "target": "U_1_0"}, 
                async_=async_, 
                **request_kwargs, 
            )
            resp = resp["data"]
        return resp["status"] in (2, 7)
    return run_gen_step(gen_step, async_)


@overload
def upload_init(
    client: str | PathLike | P115Client | P115OpenClient, 
    file: Buffer | str | PathLike | URL | SupportsGeturl | SupportsRead, 
    pid: int | str = 0, 
    filename: str = "", 
    filesha1: str = "", 
    filesize: int = -1, 
    endpoint: str = "http://oss-cn-shenzhen.aliyuncs.com", 
    *, 
    async_: Literal[False] = False, 
    **request_kwargs, 
) -> dict:
    ...
@overload
def upload_init(
    client: str | PathLike | P115Client | P115OpenClient, 
    file: Buffer | str | PathLike | URL | SupportsGeturl | SupportsRead, 
    pid: int | str = 0, 
    filename: str = "", 
    filesha1: str = "", 
    filesize: int = -1, 
    endpoint: str = "http://oss-cn-shenzhen.aliyuncs.com", 
    *, 
    async_: Literal[True], 
    **request_kwargs, 
) -> Coroutine[Any, Any, dict]:
    ...
def upload_init(
    client: str | PathLike | P115Client | P115OpenClient, 
    file: Buffer | str | PathLike | URL | SupportsGeturl | SupportsRead, 
    pid: int | str = 0, 
    filename: str = "", 
    filesha1: str = "", 
    filesize: int = -1, 
    endpoint: str = "http://oss-cn-shenzhen.aliyuncs.com", 
    *, 
    async_: Literal[False, True] = False, 
    **request_kwargs, 
) -> dict | Coroutine[Any, Any, dict]:
    """准备上传，获取必要信息，可能秒传成功

    :param client: 115 客户端或 cookies
    :param file: 待上传的文件或其路径
    :param pid: 上传文件到目录的 id 或 pickcode
    :param filename: 文件名，若为空则自动确定
    :param filesha1: 文件的 sha1 哈希值，若为空则自动计算
    :param filesize: 文件大小，若为负数则自动计算
    :param endpoint: 上传目的网址
    :param async_: 是否异步
    :param request_kwargs: 其它请求参数

    :return: 响应信息，如果有字段 "reuse" 为 True，则说明秒传成功
    """
    if isinstance(client, (str, PathLike)):
        client = P115Client(client, check_for_relogin=True)
    if isinstance(client, P115Client):
        return oss_upload_init(
            file=file, 
            pid=to_id(pid), 
            filename=filename, 
            filesha1=filesha1, 
            filesize=filesize, 
            user_id=client.user_id, 
            user_key=client.user_key, 
            endpoint=endpoint, 
            async_=async_, 
            **request_kwargs, 
        )
    else:
        request_kwargs["headers"] = dict(
            request_kwargs.get("headers") or (), 
            authorization=client.headers["authorization"], 
        )
        return oss_upload_init(
            file=file, 
            pid=to_id(pid), 
            filename=filename, 
            filesha1=filesha1, 
            filesize=filesize, 
            endpoint=endpoint, 
            async_=async_, 
            **request_kwargs, 
        )


class P115MultipartUpload:
    """待分块上传对象

    :param url: HTTP 请求链接，包含存储桶和对象的名字
    :param path: 待上传的文件路径
    :param callback: 回调数据
    :param upload_id: 上传任务 id

    下面是一个上传的例子，会在命令行显示进度条

    .. code::

        from pathlib import Path
        from p115client import P115Client
        from p115client.tool import P115MultipartUpload

        client = P115Client(Path("~/115-cookies.txt").expanduser())

        # NOTE: 待上传文件的路径（同样也支持 URL）
        path = "/path/to/file"

        uploader = P115MultipartUpload.from_path(path, user_id=client.user_id, user_key=client.user_key)
        # NOTE: 返回字典说明秒传成功
        if isinstance(uploader, dict):
            print(uploader)
        else:
            from os.path import getsize
            # NOTE: 你可以随意指定其它各种进度条模块，或者自己写的函数
            from tqdm import tqdm

            # NOTE: 文件总大小需要你自己获取，`reporthook`只做增量推送
            with tqdm(total=getsize(path), unit="B", unit_scale=True, desc="Uploading") as t:
                # NOTE: `iter_upload` 支持其它请求模块，例如 urllib3
                #     from urllib3_request import request
                #     uploader.iter_upload(request=request)
                for _ in uploader.iter_upload(reporthook=t.update):
                    pass
            print(uploader.complete())

    你也可以自己写一个进度条

    .. code::

        from collections import deque
        from time import perf_counter

        def make_reporthook(total: None | int = None):
            dq: deque[tuple[int, float]] = deque(maxlen=64)
            push = dq.append
            read_num = 0
            push((read_num, perf_counter()))
            while True:
                read_num += yield
                cur_t = perf_counter()
                speed = (read_num - dq[0][0]) / 1024 / 1024 / (cur_t - dq[0][1])
                if total:
                    percentage = read_num / total * 100
                    print(f"\\r\\x1b[K{read_num} / {total} | {speed:.2f} MB/s | {percentage:.2f} %", end="", flush=True)
                else:
                    print(f"\\r\\x1b[K{read_num} | {speed:.2f} MB/s", end="", flush=True)
                push((read_num, cur_t))

    然后像下面这样使用

    .. code::

        for _ in uploader.iter_upload(reporthook=make_reporthook(getsize(path)).send):
            pass
    """
    __slots__ = ("url", "path", "callback", "upload_id", "_result")

    def __init__(
        self, 
        /, 
        url: str, 
        path: str | PathLike | URL | SupportsGeturl, 
        callback: dict, 
        upload_id: str = "", 
    ):
        self.url = url
        if isinstance(path, PathLike):
            path = fsdecode(path)
        elif isinstance(path, URL):
            path = str(path)
        elif isinstance(path, SupportsGeturl):
            path = path.geturl()
        self.path = cast(str, path)
        self.callback = callback
        if not upload_id:
            upload_id = oss_multipart_upload_init(url)
        self.upload_id = upload_id
        self._result = None

    def __repr__(self, /) -> str:
        cls = type(self)
        mod = cls.__module__
        name = cls.__qualname__
        url = self.url
        path = self.path
        callback = self.callback
        upload_id = self.upload_id
        return f"{mod}.{name}({url=!r}, {path=!r}, {callback=!r}, {upload_id=!r})"

    @overload
    @classmethod
    def from_path(
        cls, 
        /, 
        path: str | PathLike | URL | SupportsGeturl, 
        pid: int | str = 0, 
        filename: str = "", 
        filesha1: str = "", 
        filesize: int = -1, 
        user_id: int | str = "", 
        user_key: str = "", 
        endpoint: str = "http://oss-cn-shenzhen.aliyuncs.com", 
        *, 
        async_: Literal[False] = False, 
        **request_kwargs, 
    ) -> dict | P115MultipartUpload:
        ...
    @overload
    @classmethod
    def from_path(
        cls, 
        /, 
        path: str | PathLike | URL | SupportsGeturl, 
        pid: int | str = 0, 
        filename: str = "", 
        filesha1: str = "", 
        filesize: int = -1, 
        user_id: int | str = "", 
        user_key: str = "", 
        endpoint: str = "http://oss-cn-shenzhen.aliyuncs.com", 
        *, 
        async_: Literal[True], 
        **request_kwargs, 
    ) -> Coroutine[Any, Any, dict | P115MultipartUpload]:
        ...
    @classmethod
    def from_path(
        cls, 
        /, 
        path: str | PathLike | URL | SupportsGeturl, 
        pid: int | str = 0, 
        filename: str = "", 
        filesha1: str = "", 
        filesize: int = -1, 
        user_id: int | str = "", 
        user_key: str = "", 
        endpoint: str = "http://oss-cn-shenzhen.aliyuncs.com", 
        *, 
        async_: Literal[False, True] = False, 
        **request_kwargs, 
    ) -> dict | P115MultipartUpload | Coroutine[Any, Any, dict | P115MultipartUpload]:
        """准备上传，获取必要信息，可能秒传成功

        :param path: 待上传的文件路径
        :param pid: 上传文件到目录的 id 或 pickcode
        :param filename: 文件名，若为空则自动确定
        :param filesha1: 文件的 sha1 哈希值，若为空则自动计算
        :param filesize: 文件大小，若为负数则自动计算
        :param user_id: 用户 id
        :param user_key: 用户的 key
        :param endpoint: 上传目的网址
        :param async_: 是否异步
        :param request_kwargs: 其它请求参数

        :return: 秒传成功的响应或者待分块上传对象
        """
        def gen_step():
            if user_id and user_key:
                resp = yield oss_upload_init(
                    file=path, 
                    pid=to_id(pid), 
                    filename=filename, 
                    filesha1=filesha1, 
                    filesize=filesize, 
                    user_id=user_id, 
                    user_key=user_key, 
                    endpoint=endpoint, 
                    async_=async_, 
                    **request_kwargs, 
                )
            else:
                try:
                    headers = request_kwargs["headers"]
                except KeyError as e:
                    raise TypeError(f"{cls.from_path!r} missing 1 required keyword-only argument: 'headers'") from e
                headers = request_kwargs["headers"] = dict_map(headers or (), key=str.lower)
                if "authorization" in headers:
                    resp = yield oss_upload_init(
                        file=path, 
                        pid=to_id(pid), 
                        filename=filename, 
                        filesha1=filesha1, 
                        filesize=filesize, 
                        endpoint=endpoint, 
                        async_=async_, 
                        **request_kwargs, 
                    )
                elif "cookie" in headers:
                    client = P115Client(headers["cookie"])
                    resp = yield oss_upload_init(
                        file=path, 
                        pid=to_id(pid), 
                        filename=filename, 
                        filesha1=filesha1, 
                        filesize=filesize, 
                        user_id=client.user_id, 
                        user_key=client.user_key, 
                        endpoint=endpoint, 
                        async_=async_, 
                        **request_kwargs, 
                    )
                else:
                    raise ValueError("please provide the request header: 'authorization' or 'cookie'")
            check_response(resp)
            if resp["reuse"]:
                return resp
            data = resp["data"]
            url = data["url"]
            upload_id = yield oss_multipart_upload_init(
                url, 
                async_=async_, 
                **request_kwargs, 
            )
            return cls(url, path, data["callback"], upload_id)
        return run_gen_step(gen_step, async_)

    @property
    def completed(self, /) -> bool:
        "是否已完成"
        return bool(self._result)

    @property
    def result(self, /) -> None | dict:
        "完成后的结果"
        return self._result

    @property
    def succeeded(self, /) -> bool:
        "结果是否成功"
        return bool(self._result and self._result["state"])

    @overload
    def complete(
        self, 
        /, 
        parts: None | list[dict] = None, 
        *, 
        async_: Literal[False] = False, 
        **request_kwargs, 
    ) -> dict:
        ...
    @overload
    def complete(
        self, 
        /, 
        parts: None | list[dict] = None, 
        *, 
        async_: Literal[True], 
        **request_kwargs, 
    ) -> Coroutine[Any, Any, dict]:
        ...
    def complete(
        self, 
        /, 
        parts: None | list[dict] = None, 
        *, 
        async_: Literal[False, True] = False, 
        **request_kwargs, 
    ) -> dict | Coroutine[Any, Any, dict]:
        """完成分块上传

        :param parts: 分块信息列表
        :param async_: 是否异步
        :param request_kwargs: 其它请求参数

        :return: 接口响应
        """
        if self.completed:
            raise RuntimeError("already completed")
        def gen_step():
            nonlocal parts
            if parts is None:
                parts = yield self.list_parts(async_=async_, **request_kwargs)
            resp = self._result = yield oss_multipart_upload_complete(
                self.url, 
                self.callback, 
                self.upload_id, 
                parts=parts, 
                async_=async_, 
                **request_kwargs, 
            )
            return resp
        return run_gen_step(gen_step, async_)

    @overload
    def list_parts(
        self, 
        /, 
        async_: Literal[False] = False, 
        **request_kwargs, 
    ) -> list[dict]:
        ...
    @overload
    def list_parts(
        self, 
        /, 
        async_: Literal[True], 
        **request_kwargs, 
    ) -> Coroutine[Any, Any, list[dict]]:
        ...
    def list_parts(
        self, 
        /, 
        async_: Literal[False, True] = False, 
        **request_kwargs, 
    ) -> list[dict] | Coroutine[Any, Any, list[dict]]:
        """罗列已上传的分块信息

        :param async_: 是否异步
        :param request_kwargs: 其它请求参数

        :return: 分块信息列表
        """
        def gen_step():
            parts: list[dict] = []
            yield foreach(
                parts.append, 
                oss_multipart_part_iter(
                    self.url, 
                    self.upload_id, 
                    async_=async_, 
                    **request_kwargs, 
                ), 
            )
            return parts
        return run_gen_step(gen_step, async_)

    @overload
    def upload_url(
        self, 
        /, 
        part_number: int = 1, 
        *, 
        async_: Literal[False] = False, 
        **request_kwargs, 
    ) -> tuple[str, dict]:
        ...
    @overload
    def upload_url(
        self, 
        /, 
        part_number: int = 1, 
        *, 
        async_: Literal[True], 
        **request_kwargs, 
    ) -> Coroutine[Any, Any, tuple[str, dict]]:
        ...
    def upload_url(
        self, 
        /, 
        part_number: int = 1, 
        *, 
        async_: Literal[False, True] = False, 
        **request_kwargs, 
    ) -> tuple[str, dict] | Coroutine[Any, Any, tuple[str, dict]]:
        """获取分块上传的链接和请求头

        .. caution::
            这个接口只用来获取上传链接和请求头，并不会做实际的上传

        :param part_number: 分块编号（从 1 开始）
        :param async_: 是否异步
        :param request_kwargs: 其它请求参数

        :return: 上传链接 和 请求头 的 2 元组
        """
        return oss_multipart_upload_url(
            self.url, 
            self.upload_id, 
            part_number, 
            async_=async_, 
            **request_kwargs, 
        )

    @overload
    def iter_upload(
        self, 
        /, 
        partsize: int = 10485760, 
        reporthook: None | Callable[[int], Any] = None, 
        opener: None | Callable[[str, int], SupportsRead | Iterable[Buffer]] = None, 
        *, 
        async_: Literal[False] = False, 
        **request_kwargs, 
    ) -> Iterator[dict]:
        ...
    @overload
    def iter_upload(
        self, 
        /, 
        partsize: int = 10485760, 
        reporthook: None | Callable[[int], Any] = None, 
        opener: None | Callable[[str, int], SupportsRead | Awaitable[SupportsRead] | Iterable[Buffer] | AsyncIterable[Buffer]] = None, 
        *, 
        async_: Literal[True], 
        **request_kwargs, 
    ) -> AsyncIterator[dict]:
        ...
    def iter_upload(
        self, 
        /, 
        partsize: int = 10485760, 
        reporthook: None | Callable[[int], Any] = None, 
        opener: (
            None | 
            Callable[[str, int], SupportsRead | Iterable[Buffer]] | 
            Callable[[str, int], SupportsRead | Awaitable[SupportsRead] | Iterable[Buffer] | AsyncIterable[Buffer]]
        ) = None, 
        *, 
        async_: Literal[False, True] = False, 
        **request_kwargs, 
    ) -> Iterator[dict] | AsyncIterator[dict]:
        """逐个上传分块

        .. attention::
            上传完成后，并不会提交，请手动调用 ``.complete()`` 方法

        .. note::
            - 可随意搭配请求模块: 指定 ``request`` 参数
            - 可随意搭配进度条: 指定 ``reporthook`` 参数
            - 可随意搭配文件打开器: 指定 ``opener`` 参数

        .. note::
            如果想把把上传过程外包出去，由其它任何工具完成，则调用 ``upload_url(part_number)`` 方法获得指定分块的上传链接和带签名请求头

            或者调用 ``iter_upload_url(part_number_start)`` 创建一个迭代器，从某个分块编号开始，获得一系列的上传链接和带签名请求头

        :param partsize: 分块大小
        :param reporthook: 回调函数，可以用来统计已上传的数据量或者展示进度条
        :param opener: 打开文件路径（本地路径或 URL）并从指定位置开始，如果为 None，则用默认方式
        :param async_: 是否异步
        :param request_kwargs: 其它请求参数

        :return: 迭代器，产生各个刚上传完成的分块信息
        """
        def gen_step():
            parts = yield self.list_parts(async_=async_, **request_kwargs)
            skipsize = sum(p["Size"] for p in parts)
            if reporthook is not None:
                reporthook(skipsize)
            path = self.path
            if opener is not None:
                file = opener(path, skipsize)
                if async_ and isawaitable(file):
                    file = yield file
            elif path.startswith(("http://", "https://")):
                if async_:
                    from httpfile import AsyncHTTPFileReader
                    async def process():
                        return await AsyncHTTPFileReader.new(path, start=skipsize)
                    file = yield process()
                else:
                    from httpfile import HTTPFileReader
                    file = HTTPFileReader(path, start=skipsize)
            else:
                file = open(path, "rb")
                if skipsize:
                    file.seek(skipsize)
            file = cast(SupportsRead | Iterable[Buffer] | AsyncIterable[Buffer], file)
            try:
                yield YieldFrom(oss_multipart_upload_part_iter(
                    url=self.url, 
                    file=file, # type: ignore
                    upload_id=self.upload_id, 
                    partsize=partsize, 
                    part_number_start=len(parts)+1, 
                    reporthook=reporthook, 
                    async_=async_, # type: ignore
                    **request_kwargs, 
                ))
            finally:
                if async_:
                    if hasattr(file, "aclose"):
                        yield file.aclose()
                    elif hasattr(file, "close"):
                        ret = file.close()
                        if isawaitable(ret):
                            yield ret
                elif hasattr(file, "close"):
                    file.close()
        return run_gen_step_iter(gen_step, async_)

    def iter_upload_url(
        self, 
        /, 
        part_number_start: int = 1, 
        headers: None | dict[str, str] = None, 
    ) -> Iterator[tuple[str, dict]]:
        """逐个获取上传链接和请求头

        .. caution::
            这个接口只用来获取上传链接和请求头，并不会做实际的上传，而且也不会判断总共有多少个分块，而是无限生成

        :param part_number_start: 开始的分块编号，从 1 开始
        :param headers: 默认的请求头，会被扩展

        :return: 迭代器，产生上传链接和请求头（带签名）
        """
        if part_number_start <= 0:
            part_number_start = 1
        get_url = self.upload_url
        for part_number in count(part_number_start):
            yield get_url(part_number, headers=headers)

# TODO: 增加一个工具函数，用于从某个本地目录下载到网盘目录，允许提供自定义的进度条调用
# TODO: 增加一个工具函数，用于在两个115网盘之间的转移，允许提供自定义的进度条调用
