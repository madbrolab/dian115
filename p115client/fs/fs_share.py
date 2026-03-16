#!/usr/bin/env python3
# encoding: utf-8

from __future__ import annotations

__all__ = ["P115SharePath", "P115ShareFileSystem"]

from collections.abc import (
    AsyncIterator, Coroutine, Iterable, Iterator, MutableMapping, 
)
from datetime import datetime
from functools import cached_property
from os import PathLike
from typing import overload, Any, ClassVar, Literal

from iterutils import run_gen_step

from ..client import check_response, P115Client
from ..type import P115URL
from ..tool import share_iterdir, normalize_attr_simple
from ..util import share_extract_payload
from .fs_base import IDOrPathType, P115PathBase, P115FileSystemBase


class P115SharePath(P115PathBase):
    __slots__ = ("fs", "attr")
    fs: P115ShareFileSystem

    @overload
    def receive(
        self, 
        /, 
        to_pid: int = 0, 
        *, 
        async_: Literal[False] = False, 
        **request_kwargs, 
    ) -> dict:
        ...
    @overload
    def receive(
        self, 
        /, 
        to_pid: int = 0, 
        *, 
        async_: Literal[True], 
        **request_kwargs, 
    ) -> Coroutine[Any, Any, dict]:
        ...
    def receive(
        self, 
        /, 
        to_pid: int = 0, 
        *, 
        async_: Literal[False, True] = False, 
        **request_kwargs, 
    ) -> dict | Coroutine[Any, Any, dict]:
        return self.fs.receive(
            {
                "share_code": self.share_code, 
                "receive_code": self.receive_code, 
                "file_id": self.id, 
                "cid": to_pid, 
            }, 
            async_=async_, 
            **request_kwargs, 
        )


class P115ShareFileSystem(P115FileSystemBase):
    path_class: ClassVar = P115SharePath

    def __init__(
        self, 
        /, 
        client: str | PathLike | P115Client, 
        share_code: str, 
        receive_code: None | str = None, 
        refresh: bool = False, 
        id_to_readdir: None | int | dict[int, dict[int, MutableMapping]] = None, 
    ):
        super().__init__(client, refresh=refresh, id_to_readdir=id_to_readdir)
        self.share_code = share_code
        self.receive_code = receive_code or ""

    @classmethod
    def from_url(
        cls, 
        /, 
        client: str | PathLike | P115Client, 
        url: str, 
        refresh: bool = False, 
        id_to_readdir: None | int | dict[int, dict[int, MutableMapping]] = None, 
    ) -> P115ShareFileSystem:
        return cls(
            client, 
            **share_extract_payload(url), 
            refresh=refresh, 
            id_to_readdir=id_to_readdir, 
        )

    @cached_property
    def create_time(self, /) -> datetime:
        "分享的创建时间"
        return datetime.fromtimestamp(self.create_timestamp)

    @cached_property
    def create_timestamp(self, /) -> int:
        "分享的创建时间"
        return int(self.share_info["create_time"])

    @cached_property
    def snap_id(self, /) -> int:
        "获取这个分享的 id"
        return int(self.share_info["snap_id"])

    @cached_property
    def share_user_id(self, /) -> int:
        "获取分享者的用户 id"
        return int(self.share_data["userinfo"]["user_id"])

    @property
    def share_data(self, /) -> dict:
        "获取分享的首页数据"
        return self.get_share_data()

    @property
    def share_info(self, /) -> dict:
        "获取分享信息"
        return self.share_data["share_info"]

    @overload
    def get_share_data(
        self, 
        /, 
        async_: Literal[False] = False, 
        **request_kwargs, 
    ) -> dict:
        ...
    @overload
    def get_share_data(
        self, 
        /, 
        async_: Literal[True], 
        **request_kwargs, 
    ) -> Coroutine[Any, Any, dict]:
        ...
    def get_share_data(
        self, 
        /, 
        async_: Literal[False, True] = False, 
        **request_kwargs, 
    ) -> dict | Coroutine[Any, Any, dict]:
        def gen_step():
            resp = yield self.client.share_snap(
                {
                    "share_code": self.share_code, 
                    "receive_code": self.receive_code, 
                    "limit": 1, 
                }, 
                async_=async_, 
                **request_kwargs, 
            )
            return resp["data"]
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
            id = yield self.get_id(
                id_or_path, 
                pid=pid, 
                refresh=refresh, 
                async_=async_, 
                **request_kwargs, 
            )
            return self.client.share_download_url(
                {
                    "share_code": self.share_code, 
                    "receive_code": self.receive_code, 
                    "file_id": id, 
                }, 
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
    ) -> Iterator[MutableMapping]:
        ...
    @overload
    def iterdir(
        self, 
        id: int, 
        /, 
        async_: Literal[True], 
        **request_kwargs, 
    ) -> AsyncIterator[MutableMapping]:
        ...
    def iterdir(
        self, 
        id: int, 
        /, 
        async_: Literal[False, True] = False, 
        **request_kwargs, 
    ) -> Iterator[MutableMapping] | AsyncIterator[MutableMapping]:
        return share_iterdir(
            self.client, 
            share_code=self.share_code, 
            receive_code=self.receive_code, 
            cid=id, 
            normalize_attr=normalize_attr_simple, 
            id_to_dirnode=self.id_to_dirnode, 
            async_=async_, 
            **request_kwargs, 
        )

    @overload
    def receive(
        self, 
        ids: int | str | Iterable[int | str], 
        /, 
        to_pid: int = 0, 
        *, 
        async_: Literal[False] = False, 
        **request_kwargs, 
    ) -> dict:
        ...
    @overload
    def receive(
        self, 
        ids: int | str | Iterable[int | str], 
        /, 
        to_pid: int = 0, 
        *, 
        async_: Literal[True], 
        **request_kwargs, 
    ) -> Coroutine[Any, Any, dict]:
        ...
    def receive(
        self, 
        ids: int | str | Iterable[int | str], 
        /, 
        to_pid: int = 0, 
        *, 
        async_: Literal[False, True] = False, 
        **request_kwargs, 
    ) -> dict | Coroutine[Any, Any, dict]:
        """接收分享文件到网盘

        :param ids: 要转存到文件 id（这些 id 归属分享链接）
        :param to_pid: 你的网盘的一个目录 id（这个 id 归属你的网盘）
        :param async_: 是否异步
        :param request_kwargs: 其它请求参数

        :return: 接口响应
        """
        return check_response(self.client.share_receive(
            {
                "share_code": self.share_code, 
                "receive_code": self.receive_code, 
                "file_id": ids if isinstance(ids, (int, str)) else ",".join(map(str, ids)), 
                "cid": to_pid, 
            }, 
            async_=async_, 
            **request_kwargs, 
        ))

# TODO: 如果是自己的分享，可以尝试获取分享码（增加一个方法，用来拉取分享码，增加一个方法，可以从自己的分享中查询某个分享的信息）
# TODO: 增加 search 方法
# TODO: share_download_url 增加 user_agent 参数（网页版接口可能需要？？？）
