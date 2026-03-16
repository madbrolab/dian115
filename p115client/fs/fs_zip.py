#!/usr/bin/env python3
# encoding: utf-8

from __future__ import annotations

__all__ = ["P115ZipPath", "P115ZipFileSystem"]

from collections.abc import (
    AsyncIterator, Coroutine, Iterable, Iterator, MutableMapping, 
)
from itertools import count
from os import PathLike
from posixpath import basename, dirname
from threading import Lock
from typing import overload, Any, Literal

from dictattr import AttrDict
from dicttools import dict_key_to_lower_update
from errno2 import errno
from iterutils import run_gen_step, run_gen_step_iter, with_iter_next, Yield

from ..client import check_response, P115Client
from ..exception import throw
from ..tool import extract_iter_files, extract_iterdir
from ..type import P115URL
from ..util import lock_as_async
from .fs_base import IDOrPathType, P115PathBase, P115FileSystemBase


# TODO: 尽量也要兼容 zipfile.Path 的接口
class P115ZipPath(P115PathBase):
    __slots__ = ("fs", "attr")
    fs: P115ZipFileSystem


class P115ZipFileSystem(P115FileSystemBase[P115ZipPath]):
    path_class = P115ZipPath

    def __init__(
        self, 
        /, 
        client: str | PathLike | P115Client, 
        pickcode: str, 
        refresh: bool = False, 
        id_to_readdir: None | int | dict[int, dict[int, MutableMapping]] = None, 
    ):
        super().__init__(client, refresh=refresh, id_to_readdir=id_to_readdir)
        self.pickcode = pickcode
        self._path_to_id: dict[str, int] = {"/": 0}
        self._id_to_path: dict[int, str] = {0: "/"}
        self._load_lock = Lock()

    @overload
    def id_to_path(
        self, 
        id: int, 
        /, 
        async_: Literal[False] = False, 
        **request_kwargs, 
    ) -> str:
        ...
    @overload
    def id_to_path(
        self, 
        id: int, 
        /, 
        async_: Literal[True], 
        **request_kwargs, 
    ) -> Coroutine[Any, Any, str]:
        ...
    def id_to_path(
        self, 
        id: int, 
        /, 
        async_: Literal[False, True] = False, 
        **request_kwargs, 
    ) -> str | Coroutine[Any, Any, str]:
        def gen_step():
            if not self.full_loaded:
                yield self.load(locked=True, async_=async_, **request_kwargs)
            try:
                return self._id_to_path[id]
            except KeyError:
                throw(errno.ENOENT, id)
        return run_gen_step(gen_step, async_)

    @overload
    def path_to_id(
        self, 
        path: str, 
        /, 
        async_: Literal[False] = False, 
        **request_kwargs, 
    ) -> int:
        ...
    @overload
    def path_to_id(
        self, 
        path: str, 
        /, 
        async_: Literal[True], 
        **request_kwargs, 
    ) -> Coroutine[Any, Any, int]:
        ...
    def path_to_id(
        self, 
        path: str, 
        /, 
        async_: Literal[False, True] = False, 
        **request_kwargs, 
    ) -> int | Coroutine[Any, Any, int]:
        def gen_step():
            if not self.full_loaded:
                yield self.load(locked=True, async_=async_, **request_kwargs)
            try:
                return self._path_to_id[path]
            except KeyError:
                throw(errno.ENOENT, path)
        return run_gen_step(gen_step, async_)

    @overload
    def extract(
        self, 
        /, 
        path: IDOrPathType = "", 
        to_pid: int | str = 0, 
        pid: None | int = None, 
        *, 
        async_: Literal[False] = False, 
        **request_kwargs, 
    ) -> int:
        ...
    @overload
    def extract(
        self, 
        /, 
        path: IDOrPathType = "", 
        to_pid: int | str = 0, 
        pid: None | int = None, 
        *, 
        async_: Literal[True], 
        **request_kwargs, 
    ) -> Coroutine[Any, Any, int]:
        ...
    def extract(
        self, 
        /, 
        path: IDOrPathType = "", 
        to_pid: int | str = 0, 
        pid: None | int = None, 
        *, 
        async_: Literal[False, True] = False, 
        **request_kwargs, 
    ) -> int | Coroutine[Any, Any, int]:
        """解压缩到网盘
        """
        def gen_step():
            payload = [
                ("pick_code", self.pickcode), 
                ("paths", "文件"), 
                ("to_pid", to_pid), 
            ]
            add_file = payload.append
            attr: MutableMapping = self.get_attr(path, pid=pid)
            if attr["id"]:
                add_file((
                    "extract_dir" if attr["is_dir"] else "extract_file", 
                    attr["path"].strip("/"), 
                ))
            else:
                for attr in self.readdir(0):
                    add_file((
                        "extract_dir[]" if attr["is_dir"] else "extract_file[]", 
                        attr["path"].strip("/"), 
                    ))
            resp = yield self.client.extract_add_file_app(
                payload, 
                async_=async_, 
                **request_kwargs, 
            )
            check_response(resp)
            return resp["data"]["extract_id"]
        return run_gen_step(gen_step, async_)

    @overload
    def extract_many(
        self, 
        /, 
        paths: Iterable[IDOrPathType], 
        to_pid: int | str = 0, 
        pid: None | int = None, 
        *, 
        async_: Literal[False] = False, 
        **request_kwargs, 
    ) -> int:
        ...
    @overload
    def extract_many(
        self, 
        /, 
        paths: Iterable[IDOrPathType], 
        to_pid: int | str = 0, 
        pid: None | int = None, 
        *, 
        async_: Literal[True], 
        **request_kwargs, 
    ) -> Coroutine[Any, Any, int]:
        ...
    def extract_many(
        self, 
        /, 
        paths: Iterable[IDOrPathType], 
        to_pid: int | str = 0, 
        pid: None | int = None, 
        *, 
        async_: Literal[False, True] = False, 
        **request_kwargs, 
    ) -> int | Coroutine[Any, Any, int]:
        """解压缩到网盘
        """
        def gen_step():
            payload = [
                ("pick_code", self.pickcode), 
                ("paths", "文件"), 
                ("to_pid", to_pid), 
            ]
            add_file = payload.append
            for p in paths:
                attr = self.get_attr(p, pid=pid)
                add_file((
                    "extract_dir[]" if attr["is_dir"] else "extract_file[]", 
                    attr["path"].strip("/"), 
                ))
            resp = yield self.client.extract_add_file_app(
                payload, 
                async_=async_, 
                **request_kwargs, 
            )
            check_response(resp)
            return resp["data"]["extract_id"]
        return run_gen_step(gen_step, async_)

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
        def gen_step():
            headers = request_kwargs["headers"] = dict(request_kwargs.get("headers") or ())
            dict_key_to_lower_update(headers)
            user_agent = headers.pop("user-agent", "")
            attr = yield self.get_attr(
                id_or_path, 
                pid=pid, 
                ensure_file=True, 
                async_=async_, 
                **request_kwargs, 
            )
            return self.client.extract_download_url(
                self.pickcode, 
                attr["path"], 
                user_agent=user_agent, 
                async_=async_, 
                **request_kwargs, 
            )
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
        """迭代获取目录内直属的文件或目录的信息
        """
        def gen_step():
            if not self.full_loaded:
                yield self.load(locked=True, async_=async_, **request_kwargs)
            if id:
                try:
                    attr = self.id_to_attr[id]
                except KeyError:
                    throw(errno.ENOENT, id)
                if not attr["is_dir"]:
                    throw(errno.ENOTDIR, attr)
                path = attr["path"]
            else:
                path = "/"
            with with_iter_next(extract_iterdir(
                self.client, 
                self.pickcode, 
                path, 
                async_=async_, 
                **request_kwargs, 
            )) as get_next:
                while True:
                    attr = yield get_next()
                    try:
                        attr["id"] = self._path_to_id[attr["path"]]
                    except KeyError:
                        continue
                    yield Yield(attr)
        return run_gen_step_iter(gen_step, async_)

    @overload
    def readdir(
        self, 
        id_or_path: IDOrPathType = "", 
        /, 
        pid: None | int = None, 
        refresh: None | bool = None, 
        *, 
        async_: Literal[False] = False, 
        **request_kwargs, 
    ) -> list[MutableMapping]:
        ...
    @overload
    def readdir(
        self, 
        id_or_path: IDOrPathType = "", 
        /, 
        pid: None | int = None, 
        refresh: None | bool = None, 
        *, 
        async_: Literal[True], 
        **request_kwargs, 
    ) -> Coroutine[Any, Any, list[MutableMapping]]:
        ...
    def readdir(
        self, 
        id_or_path: IDOrPathType = "", 
        /, 
        pid: None | int = None, 
        refresh: None | bool = None, 
        *, 
        async_: Literal[False, True] = False, 
        **request_kwargs, 
    ) -> list[MutableMapping] | Coroutine[Any, Any, list[MutableMapping]]:
        readdir = super().readdir
        def gen_step():
            if not self.full_loaded:
                yield self.load(locked=True, async_=async_, **request_kwargs)
            return readdir(
                id_or_path, 
                pid=pid, 
                refresh=refresh, 
                async_=async_, 
                **request_kwargs, 
            )
        return run_gen_step(gen_step, async_)

    @overload
    def load(
        self, 
        /, 
        locked: bool = True, 
        *, 
        async_: Literal[False] = False, 
        **request_kwargs, 
    ) -> None:
        ...
    @overload
    def load(
        self, 
        /, 
        locked: bool = False, 
        *, 
        async_: Literal[True], 
        **request_kwargs, 
    ) -> Coroutine[Any, Any, None]:
        ...
    def load(
        self, 
        /, 
        locked: bool = False, 
        *, 
        async_: Literal[False, True] = False, 
        **request_kwargs, 
    ) -> None | Coroutine[Any, Any, None]:
        """一次性加载整个压缩包中的文件列表
        """
        def gen_step():
            if locked:
                if async_:
                    async def request():
                        async with lock_as_async(self._load_lock):
                            if not self.full_loaded:
                                await self.load(async_=True, **request_kwargs)
                    yield request()
                else:
                    with self._load_lock:
                        if not self.full_loaded:
                            self.load(**request_kwargs)
                return
            path_to_id    = self._path_to_id
            id_to_path    = self._id_to_path
            id_to_dirnode = self.id_to_dirnode
            id_to_readdir = self.id_to_readdir
            id_to_attr    = self.id_to_attr
            get_id = count(1).__next__
            id_to_readdir[0] = {}
            def get_parent_id(path: str, /) -> int:
                dir_ = dirname(path)
                if dir_ == "/":
                    return 0
                try:
                    return path_to_id[dir_]
                except KeyError:
                    pid = get_parent_id(dir_)
                    cid = path_to_id[dir_] = get_id()
                    id_to_path[cid] = dir_
                    name = basename(dir_)
                    id_to_readdir[pid][cid] = id_to_attr[cid] = AttrDict({
                        "id": cid, 
                        "parent_id": pid, 
                        "name": name, 
                        "is_dir": True, 
                        "path": dir_, 
                    })
                    id_to_dirnode[cid] = (name, pid)
                    id_to_readdir[cid] = {}
                    return cid
            with with_iter_next(extract_iter_files(
                self.client, 
                self.pickcode, 
                async_=async_, 
                **request_kwargs, 
            )) as get_next:
                while True:
                    attr: MutableMapping = AttrDict((yield get_next()))
                    attr["parent_id"] = pid = get_parent_id(attr["path"])
                    attr["id"] = id = get_id()
                    attr["is_dir"] = False
                    id_to_readdir[pid][id]= id_to_attr[id] = attr
                    path = attr["path"]
                    id_to_path[id] = path
                    path_to_id[attr["path"]] = id
            self.full_loaded = True
        return run_gen_step(gen_step, async_)

# TODO: 增加接口，可用于检查文件是否已经云解压
# resp = check_response(client.extract_push_progress(pickcode))
# if resp["data"]["extract_status"]["unzip_status"] != 4:
#     raise OSError(errno.EIO, "file was not decompressed")
# TODO: 增加接口，可用于推送云解压，云解压进度，解压到文件夹进度等
# TODO: 参考 zipfile 模块的接口设计 namelist、filelist 等属性，以及其它的和 zipfile 兼容的接口
# TODO: 当文件特别多时，可以用 zipfile 等模块来读取文件列表
