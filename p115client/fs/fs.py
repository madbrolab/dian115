#!/usr/bin/env python3
# encoding: utf-8

from __future__ import annotations

__all__ = ["P115Path", "P115FileSystem"]

from asyncio import Lock as AsyncLock
from collections.abc import (
    AsyncIterable, AsyncIterator, Coroutine, Iterable, 
    Iterator, MutableMapping, 
)
from os import PathLike
from threading import Lock
from typing import overload, Any, ClassVar, Literal, Self

from dictattr import AttrDict
from dicttools import dict_key_to_lower_update
from errno2 import errno
from filewrap import Buffer, SupportsRead
from http_request import SupportsGeturl
from iterutils import run_gen_step
from p115pickcode import is_valid_pickcode
from yarl import URL

from ..client import check_response, P115Client
from ..exception import throw, P115BusyOSError
from ..type import P115URL
from ..tool import get_attr, get_ancestors, iterdir, normalize_attr_simple
from ..util import call_with_lock
from .fs_base import IDOrPathType, P115PathBase, P115FileSystemBase, AncestorDict


class P115Path(P115PathBase):
    __slots__ = ("fs", "attr")
    fs: P115FileSystem

    @overload
    def copy(
        self, 
        /, 
        to_dir: IDOrPathType, 
        refresh: None | bool = False, 
        *, 
        async_: Literal[False] = False, 
        **request_kwargs, 
    ) -> dict:
        ...
    @overload
    def copy(
        self, 
        /, 
        to_dir: IDOrPathType, 
        refresh: None | bool = False, 
        *, 
        async_: Literal[True], 
        **request_kwargs, 
    ) -> Coroutine[Any, Any, dict]:
        ...
    def copy(
        self, 
        /, 
        to_dir: IDOrPathType, 
        refresh: None | bool = False, 
        *, 
        async_: Literal[False, True] = False, 
        **request_kwargs, 
    ) -> dict | Coroutine[Any, Any, dict]:
        return self.fs.copy(
            self, 
            to_dir=to_dir, 
            refresh=refresh, 
            async_=async_, 
            **request_kwargs, 
        )

    @overload
    def mkdir(
        self, 
        /, 
        name: str, 
        refresh: None | bool = False, 
        *, 
        async_: Literal[False] = False, 
        **request_kwargs, 
    ) -> Self:
        ...
    @overload
    def mkdir(
        self, 
        /, 
        name: str, 
        refresh: None | bool = False, 
        *, 
        async_: Literal[True], 
        **request_kwargs, 
    ) -> Coroutine[Any, Any, Self]:
        ...
    def mkdir(
        self, 
        /, 
        name: str, 
        refresh: None | bool = False, 
        *, 
        async_: Literal[False, True] = False, 
        **request_kwargs, 
    ) -> Self | Coroutine[Any, Any, Self]:
        def gen_step():
            if not self.is_dir():
                throw(errno.ENOTDIR, self.attr)
            attr = yield self.fs.mkdir(
                self, 
                name=name, 
                refresh=refresh, 
                async_=async_, 
                **request_kwargs, 
            )
            return type(self)(self.fs, attr)
        return run_gen_step(gen_step, async_)

    @overload
    def move(
        self, 
        /, 
        to_dir: IDOrPathType, 
        refresh: None | bool = False, 
        *, 
        async_: Literal[False] = False, 
        **request_kwargs, 
    ) -> Self:
        ...
    @overload
    def move(
        self, 
        /, 
        to_dir: IDOrPathType, 
        refresh: None | bool = False, 
        *, 
        async_: Literal[True], 
        **request_kwargs, 
    ) -> Coroutine[Any, Any, Self]:
        ...
    def move(
        self, 
        /, 
        to_dir: IDOrPathType, 
        refresh: None | bool = False, 
        *, 
        async_: Literal[False, True] = False, 
        **request_kwargs, 
    ) -> Self | Coroutine[Any, Any, Self]:
        def gen_step():
            yield self.fs.move(
                self, 
                to_dir=to_dir, 
                refresh=refresh, 
                async_=async_, 
                **request_kwargs, 
            )
            return self
        return run_gen_step(gen_step, async_)

    @overload
    def remove(
        self, 
        /, 
        refresh: None | bool = False, 
        *, 
        async_: Literal[False] = False, 
        **request_kwargs, 
    ) -> Self:
        ...
    @overload
    def remove(
        self, 
        /, 
        refresh: None | bool = False, 
        *, 
        async_: Literal[True], 
        **request_kwargs, 
    ) -> Coroutine[Any, Any, Self]:
        ...
    def remove(
        self, 
        /, 
        refresh: None | bool = False, 
        *, 
        async_: Literal[False, True] = False, 
        **request_kwargs, 
    ) -> Self | Coroutine[Any, Any, Self]:
        def gen_step():
            yield self.fs.remove(
                self, 
                refresh=refresh, 
                async_=async_, 
                **request_kwargs, 
            )
            return self
        return run_gen_step(gen_step, async_)

    @overload
    def rename(
        self, 
        /, 
        name: str, 
        refresh: None | bool = False, 
        *, 
        async_: Literal[False] = False, 
        **request_kwargs, 
    ) -> Self:
        ...
    @overload
    def rename(
        self, 
        /, 
        name: str, 
        refresh: None | bool = False, 
        *, 
        async_: Literal[True], 
        **request_kwargs, 
    ) -> Coroutine[Any, Any, Self]:
        ...
    def rename(
        self, 
        /, 
        name: str, 
        refresh: None | bool = False, 
        *, 
        async_: Literal[False, True] = False, 
        **request_kwargs, 
    ) -> Self | Coroutine[Any, Any, Self]:
        def gen_step():
            yield self.fs.rename(
                self, 
                name, 
                refresh=refresh, 
                async_=async_, # type: ignore
                **request_kwargs, 
            )
            return self
        return run_gen_step(gen_step, async_)


class P115FileSystem(P115FileSystemBase[P115Path]):
    STAT_MODE: ClassVar = 0o777
    NO_INCREMENT: ClassVar = False
    path_class: ClassVar = P115Path
    """对 115 网盘模拟文件系统的操作

    :param client: 115 客户端或 cookies
    :param refresh: 是否总是刷新，如果是，则不使用缓存
    :param id_to_readdir: 缓存用的字典，映射目录 id 到在此目录中的文件或目录的另一个字典，后者是文件或目录的 id 到它的信息字典的字典
    """
    def __init__(
        self, 
        /, 
        client: str | PathLike | P115Client, 
        refresh: bool = False, 
        id_to_readdir: None | int | dict[int, dict[int, MutableMapping]] = None, 
    ):
        super().__init__(client, refresh=refresh, id_to_readdir=id_to_readdir)
        self._fs_lock = Lock()
        self._fs_alock = AsyncLock()

    @overload
    def _get_attr_by_id(
        self, 
        id: int, 
        /, 
        refresh: None | bool = None, 
        *, 
        async_: Literal[False] = False, 
        **request_kwargs, 
    ) -> AttrDict:
        ...
    @overload
    def _get_attr_by_id(
        self, 
        id: int, 
        /, 
        refresh: None | bool = None, 
        *, 
        async_: Literal[True], 
        **request_kwargs, 
    ) -> Coroutine[Any, Any, AttrDict]:
        ...
    def _get_attr_by_id(
        self, 
        id: int, 
        /, 
        refresh: None | bool = None, 
        *, 
        async_: Literal[False, True] = False, 
        **request_kwargs, 
    ) -> AttrDict | Coroutine[Any, Any, AttrDict]:
        if refresh is None:
            refresh = self.refresh
        def gen_step():
            if id == 0:
                return self._get_root_attr()
            id_to_attr = self.id_to_attr
            if not refresh:
                if attr := id_to_attr.get(id):
                    return attr
            attr = yield get_attr(
                self.client, 
                id, 
                async_=async_, 
                **request_kwargs, 
            )
            if attr_old := id_to_attr.get(id):
                attr_old.update(attr)
                if id_to_readdir := self.id_to_readdir:
                    if attr_old["parent_id"] != attr["parent_id"]:
                        try:
                            id_to_readdir[attr_old["parent_id"]].pop(id, None)
                        except KeyError:
                            pass
                        try:
                            id_to_readdir[attr["parent_id"]][id] = attr_old
                        except KeyError:
                            pass
                attr = attr_old
            else:
                id_to_attr[id] = attr
            return attr
        return run_gen_step(gen_step, async_)

    @overload
    def _get_ancestors_by_cid(
        self, 
        cid: int = 0, 
        /, 
        refresh: None | bool = False, 
        *, 
        async_: Literal[False] = False, 
        **request_kwargs, 
    ) -> list[AncestorDict]:
        ...
    @overload
    def _get_ancestors_by_cid(
        self, 
        cid: int = 0, 
        /, 
        refresh: None | bool = False, 
        *, 
        async_: Literal[True], 
        **request_kwargs, 
    ) -> Coroutine[Any, Any, list[AncestorDict]]:
        ...
    def _get_ancestors_by_cid(
        self, 
        cid: int = 0, 
        /, 
        refresh: None | bool = False, 
        *, 
        async_: Literal[False, True] = False, 
        **request_kwargs, 
    ) -> list[AncestorDict] | Coroutine[Any, Any, list[AncestorDict]]:
        """获取某个目录 id 对应的祖先节点信息（包括自身）
        """
        def gen_step():
            if cid == 0:
                return [{"id": 0, "parent_id": 0, "name": ""}]
            if not refresh:
                try:
                    return self.id_to_dirnode.get_ancestors(cid)
                except KeyError:
                    pass
            return (yield get_ancestors(
                self.client, 
                cid, 
                id_to_dirnode=self.id_to_dirnode, 
                ensure_file=False, 
                refresh=True, 
                async_=async_, 
                **request_kwargs, 
            ))
        return run_gen_step(gen_step, async_)

    @overload
    def iterdir(
        self, 
        id: int, 
        /, 
        async_: Literal[False] = False, 
        **request_kwargs, 
    ) -> Iterator[dict]:
        ...
    @overload
    def iterdir(
        self, 
        id: int, 
        /, 
        async_: Literal[True], 
        **request_kwargs, 
    ) -> AsyncIterator[dict]:
        ...
    def iterdir(
        self, 
        id: int, 
        /, 
        async_: Literal[False, True] = False, 
        **request_kwargs, 
    ) -> Iterator[dict] | AsyncIterator[dict]:
        return iterdir(
            self.client, 
            id, 
            normalize_attr=normalize_attr_simple, 
            id_to_dirnode=self.id_to_dirnode, 
            async_=async_, 
            **request_kwargs, 
        )

    @overload
    def get_url(
        self, 
        id_or_path: IDOrPathType, 
        /, 
        pid: None | int = None, 
        refresh: None | bool = None, 
        *, 
        async_: Literal[False] = False, 
        **request_kwargs, 
    ) -> P115URL:
        ...
    @overload
    def get_url(
        self, 
        id_or_path: IDOrPathType, 
        /, 
        pid: None | int = None, 
        refresh: None | bool = None, 
        *, 
        async_: Literal[True], 
        **request_kwargs, 
    ) -> Coroutine[Any, Any, P115URL]:
        ...
    def get_url(
        self, 
        id_or_path: IDOrPathType, 
        /, 
        pid: None | int = None, 
        refresh: None | bool = None, 
        *, 
        async_: Literal[False, True] = False, 
        **request_kwargs, 
    ) -> P115URL | Coroutine[Any, Any, P115URL]:
        "获取下载链接"
        if refresh is None:
            refresh = self.refresh
        def gen_step():
            headers = request_kwargs["headers"] = dict(request_kwargs.get("headers") or ())
            dict_key_to_lower_update(headers)
            user_agent = headers.pop("user-agent", "")
            app = "android"
            if isinstance(id_or_path, int):
                pickcode = self.client.to_pickcode(id_or_path)
            elif isinstance(id_or_path, str) and is_valid_pickcode(id_or_path):
                pickcode = id_or_path
            else:
                attr = yield self.get_attr(
                    id_or_path, 
                    pid=pid, 
                    refresh=refresh, 
                    async_=async_, 
                    **request_kwargs, 
                )
                if attr["is_dir"]:
                    throw(errno.EISDIR, attr)
                pickcode = attr["pickcode"]
                if attr.get("is_collect", False):
                    if attr["size"] <= 1024 * 1024 * 200:
                        app = "web"
                    else:
                        raise throw(errno.EIO, f"file {id_or_path!r} has been censored")
            return self.client.download_url(
                pickcode, 
                user_agent=user_agent, 
                app=app, 
                async_=async_, 
                **request_kwargs, 
            )
        return run_gen_step(gen_step, async_)

    @overload
    def copy(
        self, 
        id_or_path: IDOrPathType, 
        /, 
        to_dir: IDOrPathType = "", 
        pid: None | int = None, 
        refresh: None | bool = None, 
        *, 
        async_: Literal[False] = False, 
        **request_kwargs, 
    ) -> dict:
        ...
    @overload
    def copy(
        self, 
        id_or_path: IDOrPathType, 
        /, 
        to_dir: IDOrPathType = "", 
        pid: None | int = None, 
        refresh: None | bool = None, 
        *, 
        async_: Literal[True], 
        **request_kwargs, 
    ) -> Coroutine[Any, Any, dict]:
        ...
    def copy(
        self, 
        id_or_path: IDOrPathType, 
        /, 
        to_dir: IDOrPathType = "", 
        pid: None | int = None, 
        refresh: None | bool = None, 
        *, 
        async_: Literal[False, True] = False, 
        **request_kwargs, 
    ) -> dict | Coroutine[Any, Any, dict]:
        """复制文件或目录
        """
        def gen_step():
            id = yield self.get_id(
                id_or_path, 
                pid=pid, 
                refresh=refresh, 
                async_=async_, 
                **request_kwargs, 
            )
            to_cid = yield self.get_id(
                to_dir, 
                pid=pid, 
                refresh=refresh, 
                async_=async_, 
                **request_kwargs, 
            )
            lock = self._fs_alock if async_ else self._fs_lock
            while True:
                resp = yield call_with_lock(
                    lock, 
                    self.client.fs_copy_app, 
                    id, 
                    pid=to_cid, 
                    async_=async_, 
                    **request_kwargs, 
                )
                try:
                    check_response(resp)
                    self.id_to_readdir.pop(to_cid, None)
                    return resp
                except P115BusyOSError:
                    continue
        return run_gen_step(gen_step, async_)

    @overload
    def mkdir(
        self, 
        id_or_path: IDOrPathType, 
        /, 
        name: str, 
        pid: None | int = None, 
        refresh: None | bool = None, 
        *, 
        async_: Literal[False] = False, 
        **request_kwargs, 
    ) -> AttrDict:
        ...
    @overload
    def mkdir(
        self, 
        id_or_path: IDOrPathType, 
        /, 
        name: str, 
        pid: None | int = None, 
        refresh: None | bool = None, 
        *, 
        async_: Literal[True], 
        **request_kwargs, 
    ) -> Coroutine[Any, Any, AttrDict]:
        ...
    def mkdir(
        self, 
        id_or_path: IDOrPathType, 
        /, 
        name: str, 
        pid: None | int = None, 
        refresh: None | bool = None, 
        *, 
        async_: Literal[False, True] = False, 
        **request_kwargs, 
    ) -> AttrDict | Coroutine[Any, Any, AttrDict]:
        "创建目录"
        def gen_step():
            cid = yield self.get_id(
                id_or_path, 
                pid=pid, 
                refresh=refresh, 
                async_=async_, 
                **request_kwargs, 
            )
            resp = yield self.client.fs_mkdir_app(
                name, 
                pid=cid, 
                async_=async_, 
                **request_kwargs, 
            )
            check_response(resp)
            info = resp["data"]
            fid = int(info["category_id"])
            cname = info["category_name"]
            attr: dict = AttrDict(
                id=fid, 
                parent_id=cid, 
                is_dir=True, 
                name=cname, 
                pickcode=info["pick_code"], 
                ctime=int(info["ptime"]), 
                mtime=int(info["utime"]), 
            )
            children = self.id_to_readdir.get(cid)
            if children is not None:
                children[fid] = self.id_to_attr[fid] = attr
                self._pid_name_to_attr[(cid, attr["name"])] = attr
                self.id_to_dirnode[fid] = (cname, cid)
            return attr
        return run_gen_step(gen_step, async_)

    @overload
    def move(
        self, 
        id_or_path: IDOrPathType, 
        /, 
        to_dir: IDOrPathType = "", 
        pid: None | int = None, 
        refresh: None | bool = None, 
        *, 
        async_: Literal[False] = False, 
        **request_kwargs, 
    ) -> AttrDict:
        ...
    @overload
    def move(
        self, 
        id_or_path: IDOrPathType, 
        /, 
        to_dir: IDOrPathType = "", 
        pid: None | int = None, 
        refresh: None | bool = None, 
        *, 
        async_: Literal[True], 
        **request_kwargs, 
    ) -> Coroutine[Any, Any, AttrDict]:
        ...
    def move(
        self, 
        id_or_path: IDOrPathType, 
        /, 
        to_dir: IDOrPathType = "", 
        pid: None | int = None, 
        refresh: None | bool = None, 
        *, 
        async_: Literal[False, True] = False, 
        **request_kwargs, 
    ) -> AttrDict | Coroutine[Any, Any, AttrDict]:
        "移动文件或目录"
        def gen_step():
            attr = yield self.get_attr(
                id_or_path, 
                pid=pid, 
                refresh=refresh, 
                async_=async_, 
                **request_kwargs, 
            )
            fid = attr["id"]
            to_cid = yield self.get_id(
                to_dir, 
                pid=pid, 
                refresh=refresh, 
                async_=async_, 
                **request_kwargs, 
            )
            lock = self._fs_alock if async_ else self._fs_lock
            while True:
                resp = yield call_with_lock(
                    lock, 
                    self.client.fs_move_app, 
                    fid, 
                    pid=to_cid, 
                    async_=async_, 
                    **request_kwargs, 
                )
                try:
                    check_response(resp)
                    id_to_readdir = self.id_to_readdir
                    try:
                        id_to_readdir[attr["parent_id"]].pop(fid)
                    except KeyError:
                        pass
                    attr["parent_id"] = to_cid
                    try:
                        id_to_readdir[to_cid][fid] = attr
                    except KeyError:
                        pass
                    if attr["is_dir"]:
                        self.id_to_dirnode[fid] = (attr["name"], to_cid)
                    return attr
                except P115BusyOSError:
                    continue
        return run_gen_step(gen_step, async_)

    @overload
    def remove(
        self, 
        id_or_path: IDOrPathType, 
        /, 
        pid: None | int = None, 
        refresh: None | bool = None, 
        *, 
        async_: Literal[False] = False, 
        **request_kwargs, 
    ) -> AttrDict:
        ...
    @overload
    def remove(
        self, 
        id_or_path: IDOrPathType, 
        /, 
        pid: None | int = None, 
        refresh: None | bool = None, 
        *, 
        async_: Literal[True], 
        **request_kwargs, 
    ) -> Coroutine[Any, Any, AttrDict]:
        ...
    def remove(
        self, 
        id_or_path: IDOrPathType, 
        /, 
        pid: None | int = None, 
        refresh: None | bool = None, 
        *, 
        async_: Literal[False, True] = False, 
        **request_kwargs, 
    ) -> AttrDict | Coroutine[Any, Any, AttrDict]:
        "删除文件或目录"
        def gen_step():
            attr = yield self.get_attr(
                id_or_path, 
                pid=pid, 
                refresh=refresh, 
                async_=async_, 
                **request_kwargs, 
            )
            fid = attr["id"]
            lock = self._fs_alock if async_ else self._fs_lock
            while True:
                resp = yield call_with_lock(
                    lock, 
                    self.client.fs_delete_app, 
                    fid, 
                    async_=async_, 
                    **request_kwargs, 
                )
                try:
                    check_response(resp)
                    self.id_to_dirnode.pop(fid, None)
                    self.id_to_attr.pop(fid, None)
                    self.id_to_readdir.pop(fid, None)
                    try:
                        cid = attr["parent_id"]
                        self.id_to_readdir[cid].pop(fid, None)
                    except KeyError:
                        pass
                    return attr
                except P115BusyOSError:
                    continue
        return run_gen_step(gen_step, async_)

    @overload
    def rename(
        self, 
        id_or_path: IDOrPathType, 
        /, 
        name: str, 
        pid: None | int = None, 
        refresh: None | bool = None, 
        *, 
        async_: Literal[False] = False, 
        **request_kwargs, 
    ) -> AttrDict:
        ...
    @overload
    def rename(
        self, 
        id_or_path: IDOrPathType, 
        /, 
        name: str, 
        pid: None | int = None, 
        refresh: None | bool = None, 
        *, 
        async_: Literal[True], 
        **request_kwargs, 
    ) -> Coroutine[Any, Any, AttrDict]:
        ...
    def rename(
        self, 
        id_or_path: IDOrPathType, 
        /, 
        name: str, 
        pid: None | int = None, 
        refresh: None | bool = None, 
        *, 
        async_: Literal[False, True] = False, 
        **request_kwargs, 
    ) -> AttrDict | Coroutine[Any, Any, AttrDict]:
        """重命名文件或路径
        """
        assert name
        def gen_step():
            attr = yield self.get_attr(
                id_or_path, 
                pid=pid, 
                refresh=refresh, 
                async_=async_, 
                **request_kwargs, 
            )
            fid = attr["id"]
            resp = yield self.client.fs_rename_app(
                (fid, name), 
                async_=async_, 
                **request_kwargs, 
            )
            check_response(resp)
            if data := resp["data"]:
                attr["name"] = data[str(fid)]
            return attr
        return run_gen_step(gen_step, async_)

    @overload
    def upload(
        self, 
        id_or_path: IDOrPathType, 
        /, 
        file: ( Buffer | str | PathLike | URL | SupportsGeturl | 
                SupportsRead | Iterable[Buffer] ) = b"", 
        filename: str = "", 
        filesha1: str = "", 
        filesize: int = -1, 
        pid: None | int = None, 
        refresh: None | bool = None, 
        *, 
        async_: Literal[False] = False, 
        **request_kwargs, 
    ) -> AttrDict:
        ...
    @overload
    def upload(
        self, 
        id_or_path: IDOrPathType, 
        /, 
        file: ( Buffer | str | PathLike | URL | SupportsGeturl | 
                SupportsRead | Iterable[Buffer] | AsyncIterable[Buffer] ) = b"", 
        filename: str = "", 
        filesha1: str = "", 
        filesize: int = -1, 
        pid: None | int = None, 
        refresh: None | bool = None, 
        *, 
        async_: Literal[True], 
        **request_kwargs, 
    ) -> Coroutine[Any, Any, AttrDict]:
        ...
    def upload(
        self, 
        id_or_path: IDOrPathType, 
        /, 
        file: ( Buffer | str | PathLike | URL | SupportsGeturl | 
                SupportsRead | Iterable[Buffer] | AsyncIterable[Buffer] ) = b"", 
        filename: str = "", 
        filesha1: str = "", 
        filesize: int = -1, 
        pid: None | int = None, 
        refresh: None | bool = None, 
        *, 
        async_: Literal[False, True] = False, 
        **request_kwargs, 
    ) -> AttrDict | Coroutine[Any, Any, AttrDict]:
        "上传文件到目录"
        def gen_step():
            attr = yield self.get_attr(
                id_or_path, 
                pid=pid, 
                refresh=refresh, 
                async_=async_, 
                **request_kwargs, 
            )
            if not attr["is_dir"]:
                throw(errno.ENOTDIR, attr)
            cid = attr["id"]
            if isinstance(file, (Buffer, str, PathLike, URL, SupportsGeturl, SupportsRead)):
                resp = yield self.client.upload_file(
                    file, 
                    pid=cid, 
                    filename=filename, 
                    filesha1=filesha1, 
                    filesize=filesize, 
                    partsize=10485760, 
                    async_=async_, 
                    **request_kwargs, 
                )
                check_response(resp)
                if resp.get("request") == "upload":
                    info = resp["data"]
                    attr = AttrDict(
                        id=int(info["id"]), 
                        parent_id=cid, 
                        name=info["filename"], 
                        is_dir=False, 
                        sha1=info["filesha1"], 
                        size=int(info["filesize"]), 
                        pickcode=info["pickcode"], 
                    )
                else:
                    info = resp["data"]
                    attr = AttrDict(
                        id=int(info["file_id"]), 
                        parent_id=cid, 
                        name=info["file_name"], 
                        is_dir=False, 
                        sha1=info["sha1"], 
                        size=int(info["file_size"]), 
                        pickcode=info["pick_code"], 
                    )
            else:
                resp = yield self.client.upload_file_sample(
                    file, # type: ignore
                    filename=filename, 
                    pid=cid, 
                    async_=async_, # type: ignore
                    **request_kwargs, 
                )
                check_response(resp)
                info = resp["data"]
                ctime = int(info["file_ptime"])
                attr = AttrDict(
                    id=int(info["file_id"]), 
                    parent_id=cid, 
                    name=info["file_name"], 
                    is_dir=False, 
                    sha1=info["sha1"], 
                    size=int(info["file_size"]), 
                    pickcode=info["pick_code"], 
                    ctime=ctime, 
                    mtime=ctime, 
                )
            children = self.id_to_readdir.get(cid)
            if children is not None:
                fid = attr["id"]
                children[fid] = self.id_to_attr[fid] = attr
                self._pid_name_to_attr[(cid, attr["name"])] = attr
            return attr
        return run_gen_step(gen_step, async_)

# TODO: 实现 search 方法，以及可以设定 desc、label 等
# TODO: 允许手动指定一个 escape 方法
# TODO: 增加多种方法: copy_many, move_many, rename_many, remove_many
# TODO: 增加方法 copyfile、renamefile，可以改变用不同名字
# TODO: 增加方法，moves，可以改名和移动，且文件的后缀名可以不同
# TODO: 增加方法，copys，如果是目录，复制不可改名，但是文件则可以，而且后缀可以不同
