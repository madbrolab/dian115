#!/usr/bin/env python3
# encoding: utf-8

from __future__ import annotations

__all__ = ["IDOrPathType", "P115PathBase", "P115FileSystemBase"]

from abc import ABC, abstractmethod
from asyncio import Lock as AsyncLock
from collections.abc import (
    AsyncIterable, AsyncIterator, Awaitable, Callable, Coroutine, 
    Iterable, Iterator, Mapping, MutableMapping, Sequence, 
)
from functools import partial
from io import BufferedReader, TextIOWrapper
from mimetypes import guess_type
from operator import itemgetter
from os import path as ospath, fsdecode, stat_result, PathLike
from posixpath import splitext
from re import compile as re_compile, escape as re_escape
from stat import S_IFDIR, S_IFREG
from threading import Lock
from time import time
from typing import (
    cast, overload, Any, ClassVar, Final, Literal, Self, TypedDict, 
)
from weakref import WeakValueDictionary

from cachedict import LRUDict
from download import download, download_async
from ed2k import ed2k_hash, ed2k_hash_async
from errno2 import errno
from filewrap import AsyncBufferedReader, AsyncTextIOWrapper
from glob_pattern import translate_iter
from hashtools import (
    HashObj, file_digest, file_mdigest, file_digest_async, file_mdigest_async, 
)
from httpfile import AsyncHTTPFileReader, HTTPFileReader
from id2dirnode import IdToDirnode
from iterdir import iterdir_generic, walk_generic
from iterutils import (
    map as do_map, run_gen_step, run_gen_step_iter, with_iter_next, 
    Yield, YieldFrom, 
)
from posixpatht import escape, joinpath, joins, normpath, path_is_dir_form, splits
from undefined import undefined, is_undefined, Undefined

from ..client import P115Client
from ..exception import throw
from ..type import P115URL


type IDOrPathType = int | str | Sequence[str] | Mapping | P115PathBase

ED2K_NAME_TRANSTAB: Final = dict(zip(b"/|", ("%2F", "%7C")))


class AncestorDict(TypedDict):
    id: int
    parent_id: int
    name: str


class P115PathBase:
    __slots__ = ("fs", "attr")

    def __init__(
        self, 
        /, 
        fs: P115FileSystemBase, 
        attr: int | str | Mapping, 
    ):
        self.fs = fs
        if isinstance(attr, int):
            attr = {"id": attr}
        elif isinstance(attr, str):
            attr = {"path": attr}
        else:
            assert "id" in attr or "path" in attr or "parent_id" in attr and "name" in attr
        self.attr = attr

    def __contains__(self, child: int | str, /) -> bool:
        """判断是否有某个子节点
        """
        return self.has_child(child)

    def __eq__(self, path, /) -> bool:
        return type(self) is type(path) and self.fs == path.fs and self.id == path.id

    def __fspath__(self, /) -> str:
        return self.path

    def __getattr__(self, attr, /):
        try:
            return self[attr]
        except KeyError as e:
            raise AttributeError(attr) from e

    def __getitem__(self, key, /):
        try:
            return self.attr[key]
        except KeyError:
            if key in ("id", "parent_id", "name", "is_dir"):
                return self.get_attr()[key]
            raise

    def __hash__(self, /) -> int:
        return id(self)

    def __aiter__(self, /) -> AsyncIterator[Self]:
        """获取所有子节点
        """
        return self.iterdir(async_=True)

    def __iter__(self, /) -> Iterator[Self]:
        """获取所有子节点
        """
        return self.iterdir()

    def __len__(self, /) -> int:
        """如果是文件，则返回其大小，如果是目录，则返回其中文件数
        """
        return self.get_length()

    def __repr__(self, /) -> str:
        cls = type(self)
        return f"{cls.__module__}.{cls.__qualname__}(fs={self.fs!r}, attr={self.attr!r})"

    def __str__(self, /) -> str:
        return self.path

    def __truediv__(self, path: str, /) -> Self:
        return self.joinpath(path)

    @property
    def id(self, /) -> int:
        """
        """
        return self["id"]

    @property
    def ancestors(self, /) -> list[AncestorDict]:
        """
        """
        return self.get_ancestors()

    @property
    def media_type(self, /) -> None | str:
        """
        """
        if self.is_dir():
            return None
        return guess_type(self.name)[0] or "application/octet-stream"

    @property
    def parent(self, /) -> Self:
        """
        """
        return self.get_parent()

    @property
    def parents(self, /) -> list[Self]:
        """
        """
        return self.get_parents()

    @property
    def parts(self, /) -> list[str]:
        """
        """
        return ["/", *map(escape, self.patht[1:])]

    @property
    def path(self, /) -> str:
        """
        """
        return self.get_path()

    @property
    def patht(self, /) -> list[str]:
        """
        """
        return self.get_patht()

    @property
    def root(self, /) -> Self:
        """
        """
        return type(self)(self.fs, {"id": 0})

    @property
    def stem(self, /) -> str:
        """
        """
        return splitext(self.name)[0]

    @property
    def suffix(self, /) -> str:
        """
        """
        return splitext(self.name)[1]

    @property
    def suffixes(self, /) -> list[str]:
        """
        """
        return ["." + part for part in self.name.lstrip(".").split(".")]

    @overload
    def download(
        self, 
        /, 
        path: bytes | str | PathLike = "", 
        mode: Literal["a", "w", "x", "i"] = "a", 
        refresh: None | bool = None, 
        *, 
        async_: Literal[False] = False, 
        **request_kwargs, 
    ) -> tuple[str, int]:
        ...
    @overload
    def download(
        self, 
        /, 
        path: bytes | str | PathLike = "", 
        mode: Literal["a", "w", "x", "i"] = "a", 
        refresh: None | bool = None, 
        *, 
        async_: Literal[True], 
        **request_kwargs, 
    ) -> Coroutine[Any, Any, tuple[str, int]]:
        ...
    def download(
        self, 
        /, 
        path: bytes | str | PathLike = "", 
        mode: Literal["a", "w", "x", "i"] = "a", 
        refresh: None | bool = None, 
        *, 
        async_: Literal[False, True] = False, 
        **request_kwargs, 
    ) -> tuple[str, int] | Coroutine[Any, Any, tuple[str, int]]:
        return self.fs.download(
            self, 
            path=path, 
            mode=mode, 
            refresh=refresh, 
            async_=async_, 
            **request_kwargs, 
        )

    @overload
    def exists(
        self, 
        /, 
        refresh: None | bool = None, 
        *, 
        async_: Literal[False] = False, 
        **request_kwargs, 
    ) -> bool:
        ...
    @overload
    def exists(
        self, 
        /, 
        refresh: None | bool = None, 
        *, 
        async_: Literal[True], 
        **request_kwargs, 
    ) -> Coroutine[Any, Any, bool]:
        ...
    def exists(
        self, 
        /, 
        refresh: None | bool = None, 
        *, 
        async_: Literal[False, True] = False, 
        **request_kwargs, 
    ) -> bool | Coroutine[Any, Any, bool]:
        return self.fs.exists(
            self, 
            refresh=refresh, 
            async_=async_, 
            **request_kwargs, 
        )

    @overload
    def get_attr(
        self, 
        /, 
        refresh: None | bool = None, 
        *, 
        async_: Literal[False] = False, 
        **request_kwargs, 
    ) -> Mapping:
        ...
    @overload
    def get_attr(
        self, 
        /, 
        refresh: None | bool = None, 
        *, 
        async_: Literal[True], 
        **request_kwargs, 
    ) -> Coroutine[Any, Any, Mapping]:
        ...
    def get_attr(
        self, 
        /, 
        refresh: None | bool = None, 
        *, 
        async_: Literal[False, True] = False, 
        **request_kwargs, 
    ) -> Mapping | Coroutine[Any, Any, Mapping]:
        def gen_step():
            attr = yield self.fs.get_attr(
                self, 
                refresh=refresh, 
                async_=async_, 
                **request_kwargs, 
            )
            self.attr = attr
            return attr
        return run_gen_step(gen_step, async_)

    @overload
    def get_ancestors(
        self, 
        /, 
        refresh: None | bool = None, 
        *, 
        async_: Literal[False] = False, 
        **request_kwargs, 
    ) -> list[AncestorDict]:
        ...
    @overload
    def get_ancestors(
        self, 
        /, 
        refresh: None | bool = None, 
        *, 
        async_: Literal[True], 
        **request_kwargs, 
    ) -> Coroutine[Any, Any, list[AncestorDict]]:
        ...
    def get_ancestors(
        self, 
        /, 
        refresh: None | bool = None, 
        *, 
        async_: Literal[False, True] = False, 
        **request_kwargs, 
    ) -> list[AncestorDict] | Coroutine[Any, Any, list[AncestorDict]]:
        return self.fs.get_ancestors(
            self, 
            refresh=refresh, 
            async_=async_, 
            **request_kwargs, 
        )

    @overload
    def get_length(
        self, 
        /, 
        refresh: None | bool = None, 
        *, 
        async_: Literal[False] = False, 
        **request_kwargs, 
    ) -> int:
        ...
    @overload
    def get_length(
        self, 
        /, 
        refresh: None | bool = None, 
        *, 
        async_: Literal[True], 
        **request_kwargs, 
    ) -> Coroutine[Any, Any, int]:
        ...
    def get_length(
        self, 
        /, 
        refresh: None | bool = None, 
        *, 
        async_: Literal[False, True] = False, 
        **request_kwargs, 
    ) -> int | Coroutine[Any, Any, int]:
        def gen_step():
            attr = yield self.get_attr(
                refresh=False, 
                async_=async_, 
                **request_kwargs, 
            )
            if attr["is_dir"]:
                return self.fs.dirlen(
                    self, 
                    refresh=refresh, 
                    async_=async_, 
                    **request_kwargs, 
                )
            else:
                return attr["size"]
        return run_gen_step(gen_step, async_)

    @overload
    def get_parent(
        self, 
        /, 
        refresh: None | bool = None, 
        *, 
        async_: Literal[False] = False, 
        **request_kwargs, 
    ) -> Self:
        ...
    @overload
    def get_parent(
        self, 
        /, 
        refresh: None | bool = None, 
        *, 
        async_: Literal[True], 
        **request_kwargs, 
    ) -> Coroutine[Any, Any, Self]:
        ...
    def get_parent(
        self, 
        /, 
        refresh: None | bool = None, 
        *, 
        async_: Literal[False, True] = False, 
        **request_kwargs, 
    ) -> Self | Coroutine[Any, Any, Self]:
        def gen_step():
            parent_id = yield self.fs.get_parent_id(
                self, 
                refresh=refresh, 
                async_=async_, 
                **request_kwargs, 
            )
            return type(self)(self.fs, {"id": parent_id})
        return run_gen_step(gen_step, async_)

    @overload
    def get_parents(
        self, 
        /, 
        refresh: None | bool = None, 
        *, 
        async_: Literal[False] = False, 
        **request_kwargs, 
    ) -> list[Self]:
        ...
    @overload
    def get_parents(
        self, 
        /, 
        refresh: None | bool = None, 
        *, 
        async_: Literal[True], 
        **request_kwargs, 
    ) -> Coroutine[Any, Any, list[Self]]:
        ...
    def get_parents(
        self, 
        /, 
        refresh: None | bool = None, 
        *, 
        async_: Literal[False, True] = False, 
        **request_kwargs, 
    ) -> list[Self] | Coroutine[Any, Any, list[Self]]:
        def gen_step():
            ancestors: list[AncestorDict] = yield self.get_ancestors(
                refresh=refresh, 
                async_=async_, 
                **request_kwargs, 
            )
            cls = type(self)
            fs = self.fs
            return [cls(fs, {"id": a["id"]}) for a in reversed(ancestors[:-1])]
        return run_gen_step(gen_step, async_)

    @overload
    def get_path(
        self, 
        /, 
        refresh: None | bool = None, 
        *, 
        async_: Literal[False] = False, 
        **request_kwargs, 
    ) -> str:
        ...
    @overload
    def get_path(
        self, 
        /, 
        refresh: None | bool = None, 
        *, 
        async_: Literal[True], 
        **request_kwargs, 
    ) -> Coroutine[Any, Any, str]:
        ...
    def get_path(
        self, 
        /, 
        refresh: None | bool = None, 
        *, 
        async_: Literal[False, True] = False, 
        **request_kwargs, 
    ) -> str | Coroutine[Any, Any, str]:
        return self.fs.get_path(
            self, 
            refresh=refresh, 
            async_=async_, 
            **request_kwargs, 
        )

    @overload
    def get_patht(
        self, 
        /, 
        refresh: None | bool = None, 
        *, 
        async_: Literal[False] = False, 
        **request_kwargs, 
    ) -> list[str]:
        ...
    @overload
    def get_patht(
        self, 
        /, 
        refresh: None | bool = None, 
        *, 
        async_: Literal[True], 
        **request_kwargs, 
    ) -> Coroutine[Any, Any, list[str]]:
        ...
    def get_patht(
        self, 
        /, 
        refresh: None | bool = None, 
        *, 
        async_: Literal[False, True] = False, 
        **request_kwargs, 
    ) -> list[str] | Coroutine[Any, Any, list[str]]:
        return self.fs.get_patht(
            self, 
            refresh=refresh, 
            async_=async_, 
            **request_kwargs, 
        )

    @overload
    def get_url(
        self, 
        /, 
        refresh: None | bool = None, 
        *, 
        async_: Literal[False] = False, 
        **request_kwargs, 
    ) -> str:
        ...
    @overload
    def get_url(
        self, 
        /, 
        refresh: None | bool = None, 
        *, 
        async_: Literal[True], 
        **request_kwargs, 
    ) -> Coroutine[Any, Any, str]:
        ...
    def get_url(
        self, 
        /, 
        refresh: None | bool = None, 
        *, 
        async_: Literal[False, True] = False, 
        **request_kwargs, 
    ) -> str | Coroutine[Any, Any, str]:
        return self.fs.get_url(
            self, 
            refresh=refresh, 
            async_=async_, 
            **request_kwargs, 
        )

    @overload
    def glob(
        self, 
        /, 
        pattern: str = "*", 
        ignore_case: bool = False, 
        allow_escaped_slash: bool = True, 
        refresh: None | bool = None, 
        *, 
        async_: Literal[False] = False, 
        **request_kwargs, 
    ) -> Iterator[Self]:
        ...
    @overload
    def glob(
        self, 
        /, 
        pattern: str = "*", 
        ignore_case: bool = False, 
        allow_escaped_slash: bool = True, 
        refresh: None | bool = None, 
        *, 
        async_: Literal[True], 
        **request_kwargs, 
    ) -> AsyncIterator[Self]:
        ...
    def glob(
        self, 
        /, 
        pattern: str = "*", 
        ignore_case: bool = False, 
        allow_escaped_slash: bool = True, 
        refresh: None | bool = None, 
        *, 
        async_: Literal[False, True] = False, 
        **request_kwargs, 
    ) -> Iterator[Self] | AsyncIterator[Self]:
        return self.wrap_path_iter(self.fs.glob(
            pattern, 
            dirname=self, 
            ignore_case=ignore_case, 
            allow_escaped_slash=allow_escaped_slash, 
            refresh=refresh, 
            async_=async_, 
            **request_kwargs, 
        ))

    @overload
    def has_child(
        self, 
        /, 
        child: int | str, 
        refresh: None | bool = None, 
        *, 
        async_: Literal[False] = False, 
        **request_kwargs, 
    ) -> bool:
        ...
    @overload
    def has_child(
        self, 
        /, 
        child: int | str, 
        refresh: None | bool = None, 
        *, 
        async_: Literal[True], 
        **request_kwargs, 
    ) -> Coroutine[Any, Any, bool]:
        ...
    def has_child(
        self, 
        /, 
        child: int | str, 
        refresh: None | bool = None, 
        *, 
        async_: Literal[False, True] = False, 
        **request_kwargs, 
    ) -> bool | Coroutine[Any, Any, bool]:
        return self.fs.has_child(
            child, 
            self, 
            refresh=refresh, 
            async_=async_, 
            **request_kwargs, 
        )

    @overload
    def hash[T](
        self, 
        /, 
        digest: str | HashObj | Callable[[], HashObj] | Callable[[], Callable[[bytes, T], T]] = "md5", 
        start: int = 0, 
        stop: None | int = None, 
        *, 
        async_: Literal[False] = False, 
        **request_kwargs, 
    ) -> tuple[int, HashObj | T]:
        ...
    @overload
    def hash[T](
        self, 
        /, 
        digest: str | HashObj | Callable[[], HashObj] | Callable[[], Callable[[bytes, T], T]] | Callable[[], Callable[[bytes, T], Awaitable[T]]] = "md5", 
        start: int = 0, 
        stop: None | int = None, 
        *, 
        async_: Literal[True], 
        **request_kwargs, 
    ) -> Coroutine[Any, Any, tuple[int, HashObj | T]]:
        ...
    def hash[T](
        self, 
        /, 
        digest: str | HashObj | Callable[[], HashObj] | Callable[[], Callable[[bytes, T], T]] | Callable[[], Callable[[bytes, T], Awaitable[T]]] = "md5", 
        start: int = 0, 
        stop: None | int = None, 
        *, 
        async_: Literal[False, True] = False, 
        **request_kwargs, 
    ) -> tuple[int, HashObj | T] | Coroutine[Any, Any, tuple[int, HashObj | T]]:
        return self.fs.hash(
            self, 
            digest=digest, # type: ignore
            start=start, 
            stop=stop, 
            async_=async_, # type: ignore
            **request_kwargs, 
        )

    @overload
    def hashes[T](
        self, 
        /, 
        digest: str | HashObj | Callable[[], HashObj] | Callable[[], Callable[[bytes, T], T]] = "md5", 
        *digests: str | HashObj | Callable[[], HashObj] | Callable[[], Callable[[bytes, T], T]], 
        start: int = 0, 
        stop: None | int = None, 
        async_: Literal[False] = False, 
        **request_kwargs, 
    ) -> tuple[int, list[HashObj | T]]:
        ...
    @overload
    def hashes[T](
        self, 
        /, 
        digest: str | HashObj | Callable[[], HashObj] | Callable[[], Callable[[bytes, T], T]] | Callable[[], Callable[[bytes, T], Awaitable[T]]] = "md5", 
        *digests: str | HashObj | Callable[[], HashObj] | Callable[[], Callable[[bytes, T], T]] | Callable[[], Callable[[bytes, T], Awaitable[T]]], 
        start: int = 0, 
        stop: None | int = None, 
        async_: Literal[True], 
        **request_kwargs, 
    ) -> Coroutine[Any, Any, tuple[int, list[HashObj | T]]]:
        ...
    def hashes[T](
        self, 
        /, 
        digest: str | HashObj | Callable[[], HashObj] | Callable[[], Callable[[bytes, T], T]] | Callable[[], Callable[[bytes, T], Awaitable[T]]] = "md5", 
        *digests: str | HashObj | Callable[[], HashObj] | Callable[[], Callable[[bytes, T], T]] | Callable[[], Callable[[bytes, T], Awaitable[T]]], 
        start: int = 0, 
        stop: None | int = None, 
        async_: Literal[False, True] = False, 
        **request_kwargs, 
    ) -> tuple[int, list[HashObj | T]] | Coroutine[Any, Any, tuple[int, list[HashObj | T]]]:
        return self.fs.hashes(
            self, 
            digest, # type: ignore
            *digests, # type: ignore
            start=start, 
            stop=stop, 
            async_=async_, # type: ignore
            **request_kwargs, 
        )

    def inode(self, /) -> int:
        return self.id

    def is_absolute(self, /) -> bool:
        return True

    @overload
    def is_dir(
        self, 
        /, 
        async_: Literal[False] = False, 
        **request_kwargs, 
    ) -> bool:
        ...
    @overload
    def is_dir(
        self, 
        /, 
        async_: Literal[True], 
        **request_kwargs, 
    ) -> Coroutine[Any, Any, bool]:
        ...
    def is_dir(
        self, 
        /, 
        async_: Literal[False, True] = False, 
        **request_kwargs, 
    ) -> bool | Coroutine[Any, Any, bool]:
        def gen_step():
            attr = yield self.get_attr(
                refresh=False, 
                async_=async_, 
                **request_kwargs, 
            )
            return attr["is_dir"]
        return run_gen_step(gen_step, async_)

    @overload
    def is_empty(
        self, 
        /, 
        refresh: None | bool = None, 
        *, 
        async_: Literal[False] = False, 
        **request_kwargs, 
    ) -> bool:
        ...
    @overload
    def is_empty(
        self, 
        /, 
        refresh: None | bool = None, 
        *, 
        async_: Literal[True], 
        **request_kwargs, 
    ) -> Coroutine[Any, Any, bool]:
        ...
    def is_empty(
        self, 
        /, 
        refresh: None | bool = None, 
        *, 
        async_: Literal[False, True] = False, 
        **request_kwargs, 
    ) -> bool | Coroutine[Any, Any, bool]:
        return self.fs.is_empty(
            self, 
            refresh=refresh, 
            async_=async_, 
            **request_kwargs, 
        )

    @overload
    def is_file(
        self, 
        /, 
        async_: Literal[False] = False, 
        **request_kwargs, 
    ) -> bool:
        ...
    @overload
    def is_file(
        self, 
        /, 
        async_: Literal[True], 
        **request_kwargs, 
    ) -> Coroutine[Any, Any, bool]:
        ...
    def is_file(
        self, 
        /, 
        async_: Literal[False, True] = False, 
        **request_kwargs, 
    ) -> bool | Coroutine[Any, Any, bool]:
        def gen_step():
            is_dir = yield self.is_dir(async_=async_, **request_kwargs)
            return not is_dir
        return run_gen_step(gen_step, async_)

    def is_symlink(self, /) -> bool:
        return False

    @overload
    def isdir(
        self, 
        /, 
        *, 
        async_: Literal[False] = False, 
        **request_kwargs, 
    ) -> bool:
        ...
    @overload
    def isdir(
        self, 
        /, 
        *, 
        async_: Literal[True], 
        **request_kwargs, 
    ) -> Coroutine[Any, Any, bool]:
        ...
    def isdir(
        self, 
        /, 
        *, 
        async_: Literal[False, True] = False, 
        **request_kwargs, 
    ) -> bool | Coroutine[Any, Any, bool]:
        return self.fs.isdir(
            self, 
            async_=async_, 
            **request_kwargs, 
        )

    @overload
    def isfile(
        self, 
        /, 
        *, 
        async_: Literal[False] = False, 
        **request_kwargs, 
    ) -> bool:
        ...
    @overload
    def isfile(
        self, 
        /, 
        *, 
        async_: Literal[True], 
        **request_kwargs, 
    ) -> Coroutine[Any, Any, bool]:
        ...
    def isfile(
        self, 
        /, 
        *, 
        async_: Literal[False, True] = False, 
        **request_kwargs, 
    ) -> bool | Coroutine[Any, Any, bool]:
        return self.fs.isfile(
            self, 
            async_=async_, 
            **request_kwargs, 
        )

    @overload
    def iter(
        self, 
        /, 
        topdown: None | bool = True, 
        min_depth: int = 1, 
        max_depth: int = 1, 
        predicate: None | Callable[[Mapping], Literal[None, 1, False, True]] = None, 
        onerror: bool | Callable[[OSError], bool] = True, 
        refresh: None | bool = None, 
        *, 
        async_: Literal[False] = False, 
        **request_kwargs, 
    ) -> Iterator[Self]:
        ...
    @overload
    def iter(
        self, 
        /, 
        topdown: None | bool = True, 
        min_depth: int = 1, 
        max_depth: int = 1, 
        predicate: None | Callable[[Mapping], Literal[None, 1, False, True]] = None, 
        onerror: bool | Callable[[OSError], bool] = True, 
        refresh: None | bool = None, 
        *, 
        async_: Literal[True], 
        **request_kwargs, 
    ) -> AsyncIterator[Self]:
        ...
    def iter(
        self, 
        /, 
        topdown: None | bool = True, 
        min_depth: int = 1, 
        max_depth: int = 1, 
        predicate: None | Callable[[Mapping], Literal[None, 1, False, True]] = None, 
        onerror: bool | Callable[[OSError], bool] = True, 
        refresh: None | bool = None, 
        *, 
        async_: Literal[False, True] = False, 
        **request_kwargs, 
    ) -> Iterator[Self] | AsyncIterator[Self]:
        return self.wrap_path_iter(self.fs.iter(
            self,  
            topdown=topdown, 
            min_depth=min_depth, 
            max_depth=max_depth, 
            predicate=predicate, 
            onerror=onerror, 
            refresh=refresh, 
            async_=async_, # type: ignore
            **request_kwargs, 
        ))

    @overload
    def iterdir(
        self, 
        /, 
        refresh: None | bool = None, 
        *, 
        async_: Literal[False] = False, 
        **request_kwargs, 
    ) -> Iterator[Self]:
        ...
    @overload
    def iterdir(
        self, 
        /, 
        refresh: None | bool = None, 
        *, 
        async_: Literal[True], 
        **request_kwargs, 
    ) -> AsyncIterator[Self]:
        ...
    def iterdir(
        self, 
        /, 
        refresh: None | bool = None, 
        *, 
        async_: Literal[False, True] = False, 
        **request_kwargs, 
    ) -> Iterator[Self] | AsyncIterator[Self]:
        def gen_step():
            children = yield self.fs.readdir(
                self, 
                refresh=refresh, 
                async_=async_, 
                **request_kwargs, 
            )
            path_class = type(self)
            fs = self.fs
            return YieldFrom(path_class(fs, a) for a in children)
        return run_gen_step_iter(gen_step, async_)

    @overload
    def join(
        self, 
        /, 
        *names: str, 
        refresh: None | bool = None, 
        async_: Literal[False] = False, 
        **request_kwargs, 
    ) -> Self:
        ...
    @overload
    def join(
        self, 
        /, 
        *names: str, 
        refresh: None | bool = None, 
        async_: Literal[True], 
        **request_kwargs, 
    ) -> Coroutine[Any, Any, Self]:
        ...
    def join(
        self, 
        /, 
        *names: str, 
        refresh: None | bool = None, 
        async_: Literal[False, True] = False, 
        **request_kwargs, 
    ) -> Self | Coroutine[Any, Any, Self]:
        return self.joinpath(
            joins(names), 
            refresh=refresh, 
            async_=async_, 
            **request_kwargs, 
        )

    @overload
    def joinpath(
        self, 
        /, 
        *paths: str, 
        refresh: None | bool = None, 
        async_: Literal[False] = False, 
        **request_kwargs, 
    ) -> Self:
        ...
    @overload
    def joinpath(
        self, 
        /, 
        *paths: str, 
        refresh: None | bool = None, 
        async_: Literal[True], 
        **request_kwargs, 
    ) -> Coroutine[Any, Any, Self]:
        ...
    def joinpath(
        self, 
        /, 
        *paths: str, 
        refresh: None | bool = None, 
        async_: Literal[False, True] = False, 
        **request_kwargs, 
    ) -> Self | Coroutine[Any, Any, Self]:
        def gen_step():
            if not paths:
                return self
            path_new = normpath(joinpath(*paths))
            if not path_new:
                return self
            elif path_new == "/":
                return self.root
            path = yield self.get_path(
                refresh=refresh, 
                async_=async_, 
                **request_kwargs, 
            )
            if path == path_new:
                return self
            return type(self)(self.fs, {"path": joinpath(path, path_new)})
        return run_gen_step(gen_step, async_)

    @overload
    def match(
        self, 
        /, 
        path_pattern: str, 
        ignore_case: bool = False, 
        allow_escaped_slash: bool = True, 
        refresh: None | bool = None, 
        *, 
        async_: Literal[False] = False, 
        **request_kwargs, 
    ) -> bool:
        ...
    @overload
    def match(
        self, 
        /, 
        path_pattern: str, 
        ignore_case: bool = False, 
        allow_escaped_slash: bool = True, 
        refresh: None | bool = None, 
        *, 
        async_: Literal[True], 
        **request_kwargs, 
    ) -> bool:
        ...
    def match(
        self, 
        /, 
        path_pattern: str, 
        ignore_case: bool = False, 
        allow_escaped_slash: bool = True, 
        refresh: None | bool = None, 
        *, 
        async_: Literal[False, True] = False, 
        **request_kwargs, 
    ) -> bool | Coroutine[Any, Any, bool]:
        def gen_step():
            pattern = "(?%s:%s)" % (
                "i"[:ignore_case], 
                "".join(
                    "(?:/%s)?" % pat if typ == "dstar" else "/" + pat 
                    for pat, typ, _ in translate_iter(
                        path_pattern, 
                        allow_escaped_slash=allow_escaped_slash, 
                    )
                ), 
            )
            path = yield self.get_path(
                refresh=refresh, 
                async_=async_, 
                **request_kwargs, 
            )
            return re_compile(pattern).fullmatch(path) is not None
        return run_gen_step(gen_step, async_)

    @overload
    def open(
        self, 
        /, 
        mode: Literal["rb", "br"] = "rb", 
        buffering: None | int = None, 
        encoding: None | str = None, 
        errors: None | str = None, 
        newline: None | str = None, 
        start: int = 0, 
        seek_threshold: int = 1 << 20, 
        http_file_reader_cls: None | type[HTTPFileReader] = None, 
        refresh: None | bool = None, 
        *, 
        async_: Literal[False] = False, 
        **request_kwargs, 
    ) -> HTTPFileReader | BufferedReader:
        ...
    @overload
    def open(
        self, 
        /, 
        mode: Literal["r", "rt", "tr"], 
        buffering: None | int = None, 
        encoding: None | str = None, 
        errors: None | str = None, 
        newline: None | str = None, 
        start: int = 0, 
        seek_threshold: int = 1 << 20, 
        http_file_reader_cls: None | type[HTTPFileReader] = None, 
        refresh: None | bool = None, 
        *, 
        async_: Literal[False] = False, 
        **request_kwargs, 
    ) -> TextIOWrapper:
        ...
    @overload
    def open(
        self, 
        /, 
        mode: Literal["rb", "br"] = "rb", 
        buffering: None | int = None, 
        encoding: None | str = None, 
        errors: None | str = None, 
        newline: None | str = None, 
        start: int = 0, 
        seek_threshold: int = 1 << 20, 
        http_file_reader_cls: None | type[AsyncHTTPFileReader] = None, 
        refresh: None | bool = None, 
        *, 
        async_: Literal[True], 
        **request_kwargs, 
    ) -> AsyncHTTPFileReader | AsyncBufferedReader:
        ...
    @overload
    def open(
        self, 
        /, 
        mode: Literal["r", "rt", "tr"], 
        buffering: None | int = None, 
        encoding: None | str = None, 
        errors: None | str = None, 
        newline: None | str = None, 
        start: int = 0, 
        seek_threshold: int = 1 << 20, 
        http_file_reader_cls: None | type[AsyncHTTPFileReader] = None, 
        refresh: None | bool = None, 
        *, 
        async_: Literal[True], 
        **request_kwargs, 
    ) -> AsyncTextIOWrapper:
        ...
    def open(
        self, 
        /, 
        mode: Literal["r", "rt", "tr", "rb", "br"] = "rb", 
        buffering: None | int = None, 
        encoding: None | str = None, 
        errors: None | str = None, 
        newline: None | str = None, 
        start: int = 0, 
        seek_threshold: int = 1 << 20, 
        http_file_reader_cls: None | type[HTTPFileReader] | type[AsyncHTTPFileReader] = None, 
        refresh: None | bool = None, 
        *, 
        async_: Literal[False, True] = False, 
        **request_kwargs, 
    ) -> HTTPFileReader | BufferedReader | TextIOWrapper | AsyncHTTPFileReader | AsyncBufferedReader | AsyncTextIOWrapper:
        return self.fs.open(
            self, 
            mode=mode, # type: ignore
            buffering=buffering, 
            encoding=encoding, 
            errors=errors, 
            newline=newline, 
            start=start, 
            seek_threshold=seek_threshold, 
            http_file_reader_cls=http_file_reader_cls, 
            refresh=refresh, 
            async_=async_, # type: ignore
            **request_kwargs, 
        )

    @overload
    def read(
        self, 
        /, 
        start: None | int = None, 
        stop: None | int | Undefined = undefined, 
        *, 
        async_: Literal[False] = False, 
        **request_kwargs, 
    ) -> bytes:
        ...
    @overload
    def read(
        self, 
        /, 
        start: None | int = None, 
        stop: None | int | Undefined = undefined, 
        *, 
        async_: Literal[True], 
        **request_kwargs, 
    ) -> Coroutine[Any, Any, bytes]:
        ...
    def read(
        self, 
        /, 
        start: None | int = None, 
        stop: None | int | Undefined = undefined, 
        *, 
        async_: Literal[False, True] = False, 
        **request_kwargs, 
    ) -> bytes | Coroutine[Any, Any, bytes]:
        return self.fs.read(
            self, 
            start, 
            stop, 
            async_=async_, 
            **request_kwargs, 
        )

    @overload
    def read_range(
        self, 
        /, 
        bytes_range: str = "0-", 
        *, 
        async_: Literal[False] = False, 
        **request_kwargs, 
    ) -> bytes:
        ...
    @overload
    def read_range(
        self, 
        /, 
        bytes_range: str = "0-", 
        *, 
        async_: Literal[True], 
        **request_kwargs, 
    ) -> Coroutine[Any, Any, bytes]:
        ...
    def read_range(
        self, 
        /, 
        bytes_range: str = "0-", 
        *, 
        async_: Literal[False, True] = False, 
        **request_kwargs, 
    ) -> bytes | Coroutine[Any, Any, bytes]:
        return self.fs.read_range(
            self, 
            bytes_range, 
            async_=async_, 
            **request_kwargs, 
        )

    @overload
    def read_block(
        self, 
        /, 
        size: int = 0, 
        offset: int = 0, 
        *, 
        async_: Literal[False] = False, 
        **request_kwargs, 
    ) -> bytes:
        ...
    @overload
    def read_block(
        self, 
        /, 
        size: int = 0, 
        offset: int = 0, 
        *, 
        async_: Literal[True], 
        **request_kwargs, 
    ) -> Coroutine[Any, Any, bytes]:
        ...
    def read_block(
        self, 
        /, 
        size: int = 0, 
        offset: int = 0, 
        *, 
        async_: Literal[False, True] = False, 
        **request_kwargs, 
    ) -> bytes | Coroutine[Any, Any, bytes]:
        return self.fs.read_block(
            self, 
            size, 
            offset, 
            async_=async_, 
            **request_kwargs, 
        )

    @overload
    def read_text(
        self, 
        /, 
        encoding: None | str = None, 
        errors: None | str = None, 
        newline: None | str = None, 
        *, 
        async_: Literal[False] = False, 
        **request_kwargs, 
    ) -> str:
        ...
    @overload
    def read_text(
        self, 
        /, 
        encoding: None | str = None, 
        errors: None | str = None, 
        newline: None | str = None, 
        *, 
        async_: Literal[True], 
        **request_kwargs, 
    ) -> Coroutine[Any, Any, str]:
        ...
    def read_text(
        self, 
        /, 
        encoding: None | str = None, 
        errors: None | str = None, 
        newline: None | str = None, 
        *, 
        async_: Literal[False, True] = False, 
        **request_kwargs, 
    ) -> str | Coroutine[Any, Any, str]:
        return self.fs.read_text(
            self, 
            encoding=encoding, 
            errors=errors, 
            newline=newline, 
            async_=async_, 
            **request_kwargs, 
        )

    @overload
    def rglob(
        self, 
        /, 
        pattern: str = "", 
        ignore_case: bool = False, 
        allow_escaped_slash: bool = True, 
        refresh: None | bool = None, 
        *, 
        async_: Literal[False] = False, 
        **request_kwargs, 
    ) -> Iterator[Self]:
        ...
    @overload
    def rglob(
        self, 
        /, 
        pattern: str = "", 
        ignore_case: bool = False, 
        allow_escaped_slash: bool = True, 
        refresh: None | bool = None, 
        *, 
        async_: Literal[True], 
        **request_kwargs, 
    ) -> AsyncIterator[Self]:
        ...
    def rglob(
        self, 
        /, 
        pattern: str = "", 
        ignore_case: bool = False, 
        allow_escaped_slash: bool = True, 
        refresh: None | bool = None, 
        *, 
        async_: Literal[False, True] = False, 
        **request_kwargs, 
    ) -> Iterator[Self] | AsyncIterator[Self]:
        return self.wrap_path_iter(self.fs.rglob(
            pattern, 
            dirname=self, 
            ignore_case=ignore_case, 
            allow_escaped_slash=allow_escaped_slash, 
            refresh=refresh, 
            async_=async_, 
            **request_kwargs, 
        ))

    @overload
    def stat(
        self, 
        /, 
        async_: Literal[False] = False, 
        **request_kwargs, 
    ) -> stat_result:
        ...
    @overload
    def stat(
        self, 
        /, 
        async_: Literal[True], 
        **request_kwargs, 
    ) -> Coroutine[Any, Any, stat_result]:
        ...
    def stat(
        self, 
        /, 
        async_: Literal[False, True] = False, 
        **request_kwargs, 
    ) -> stat_result | Coroutine[Any, Any, stat_result]:
        return self.fs.stat(self, async_=async_, **request_kwargs)

    @overload
    def walk(
        self, 
        /, 
        topdown: None | bool = True, 
        min_depth: int = 1, 
        max_depth: int = -1, 
        onerror: bool | Callable[[OSError], bool] = True, 
        refresh: None | bool = None, 
        *, 
        async_: Literal[False] = False, 
        **request_kwargs, 
    ) -> Iterator[tuple[Self, list[Self], list[Self]]]:
        ...
    @overload
    def walk(
        self, 
        /, 
        topdown: None | bool = True, 
        min_depth: int = 1, 
        max_depth: int = -1, 
        onerror: bool | Callable[[OSError], bool] = True, 
        refresh: None | bool = None, 
        *, 
        async_: Literal[True], 
        **request_kwargs, 
    ) -> AsyncIterator[tuple[Self, list[Self], list[Self]]]:
        ...
    def walk(
        self, 
        /, 
        topdown: None | bool = True, 
        min_depth: int = 1, 
        max_depth: int = -1, 
        onerror: bool | Callable[[OSError], bool] = True, 
        refresh: None | bool = None, 
        *, 
        async_: Literal[False, True] = False, 
        **request_kwargs, 
    ) -> Iterator[tuple[Self, list[Self], list[Self]]] | AsyncIterator[tuple[Self, list[Self], list[Self]]]:
        def gen_step():
            path_class = type(self)
            fs = self.fs
            with with_iter_next(self.fs.walk(
                self, 
                topdown=topdown, 
                min_depth=min_depth, 
                max_depth=max_depth, 
                onerror=onerror, 
                refresh=refresh, 
                async_=async_, 
                **request_kwargs, 
            )) as get_next:
                parent, dirs, files = yield get_next()
                yield (
                    path_class(fs, parent), 
                    [path_class(fs, a) for a in dirs], 
                    [path_class(fs, a) for a in files], 
                )
        return run_gen_step(gen_step, async_)

    def with_name(self, name: str, /) -> Self:
        assert name
        return type(self)(self.fs, {"name": name, "parent_id": self.parent_id})

    def with_stem(self, stem: str, /) -> Self:
        return self.with_name(stem + self.suffix)

    def with_suffix(self, suffix: str, /) -> Self:
        return self.with_name(self.stem + suffix)

    @overload
    def wrap_path_iter(
        self, 
        /, 
        path_iter: Iterable[int | str | Mapping], 
    ) -> Iterator[Self]:
        ...
    @overload
    def wrap_path_iter(
        self, 
        /, 
        path_iter: AsyncIterable[int | str | Mapping], 
    ) -> AsyncIterator[Self]:
        ...
    def wrap_path_iter(
        self, 
        /, 
        path_iter: Iterable[int | str | Mapping] | AsyncIterable[int | str | Mapping], 
    ) -> Iterator[Self] | AsyncIterator[Self]:
        path_class = type(self)
        fs = self.fs
        return do_map(lambda a, /: path_class(fs, a), path_iter)


class P115FileSystemBase[P115PathType: P115PathBase](ABC):
    STAT_MODE: ClassVar[int] = 0o444
    NO_INCREMENT: ClassVar[bool] = True
    path_class: ClassVar[type[P115PathType]]
    id: int = 0
    refresh: bool = False
    full_loaded: bool = False

    def __init__(
        self, 
        /, 
        client: str | PathLike | P115Client, 
        refresh: bool = False, 
        id_to_readdir: None | int | dict[int, dict[int, MutableMapping]] = None, 
    ):
        if isinstance(client, (str, PathLike)):
            client = P115Client(client, check_for_relogin=True)
        self.client: P115Client = client
        self.refresh = refresh
        if id_to_readdir is None:
            id_to_readdir = {}
        elif isinstance(id_to_readdir, int):
            maxsize = id_to_readdir
            if maxsize <= 0:
                id_to_readdir = {}
            else:
                id_to_readdir = LRUDict(maxsize)
        self.id_to_readdir: dict[int, dict[int, MutableMapping]] = id_to_readdir
        self.id_to_attr: MutableMapping[int, MutableMapping] = WeakValueDictionary()
        self.id_to_dirnode = IdToDirnode()
        self._pid_name_to_attr: MutableMapping[tuple[int, str], MutableMapping] = WeakValueDictionary()
        self._readdir_locks: LRUDict[int, Any] = LRUDict(1024, default_factory=Lock)
        self._readdir_alocks: LRUDict[int, Any] = LRUDict(1024, default_factory=AsyncLock)

    def __contains__(self, id_or_path: IDOrPathType, /) -> bool:
        return self.exists(id_or_path)

    def __eq__(self, other, /) -> bool:
        return type(self) is type(other) and self.client == other.client

    def __getitem__(self, id_or_path: IDOrPathType, /) -> P115PathType:
        return self.as_path(id_or_path)

    def __hash__(self, /) -> int:
        return id(self)

    def __itruediv__(self, id_or_path: IDOrPathType, /) -> Self:
        self.chdir(id_or_path)
        return self

    def __repr__(self, /) -> str:
        cls = type(self)
        return f"<{cls.__module__}.{cls.__qualname__}(client={self.client!r}, id={self.id!r}) at {hex(id(self))}>"

    @property
    def user_id(self, /) -> int:
        return self.client.user_id

    @overload
    @abstractmethod
    def iterdir(
        self, 
        id: int, 
        /, 
        async_: Literal[False] = False, 
        **request_kwargs, 
    ) -> Iterable[MutableMapping]:
        ...
    @overload
    @abstractmethod
    def iterdir(
        self, 
        id: int, 
        /, 
        async_: Literal[True], 
        **request_kwargs, 
    ) -> AsyncIterable[MutableMapping]:
        ...
    @abstractmethod
    def iterdir(
        self, 
        id: int, 
        /, 
        async_: Literal[False, True] = False, 
        **request_kwargs, 
    ) -> Iterable[MutableMapping] | AsyncIterable[MutableMapping]:
        """迭代获取某个目录下直属的文件或目录的信息，并且需要负责更新 `self.id_to_dirnode`
        """

    @overload
    def as_path(
        self, 
        id_or_path: IDOrPathType = "", 
        /, 
        pid: None | int = None, 
        ensure_file: None | bool = None, 
        refresh: None | bool = None, 
        *, 
        async_: Literal[False] = False, 
        **request_kwargs, 
    ) -> P115PathType:
        ...
    @overload
    def as_path(
        self, 
        id_or_path: IDOrPathType = "", 
        /, 
        pid: None | int = None, 
        ensure_file: None | bool = None, 
        refresh: None | bool = None, 
        *, 
        async_: Literal[True], 
        **request_kwargs, 
    ) -> Coroutine[Any, Any, P115PathType]:
        ...
    def as_path(
        self, 
        id_or_path: IDOrPathType = "", 
        /, 
        pid: None | int = None, 
        ensure_file: None | bool = None, 
        refresh: None | bool = None, 
        *, 
        async_: Literal[False, True] = False, 
        **request_kwargs, 
    ) -> P115PathType | Coroutine[Any, Any, P115PathType]:
        """获取对应的路径对象
        """
        if refresh is None:
            refresh = self.refresh
        def gen_step():
            nonlocal id_or_path
            path_class = type(self).path_class
            if isinstance(id_or_path, P115PathBase):
                id_or_path = id_or_path.attr
            if not refresh and isinstance(id_or_path, Mapping):
                return path_class(self, id_or_path)
            attr = yield self.get_attr(
                id_or_path, 
                pid=pid, 
                ensure_file=ensure_file, 
                refresh=refresh, 
                async_=async_, 
                **request_kwargs, 
            )
            return path_class(self, attr)
        return run_gen_step(gen_step, async_)

    def attr_to_stat(self, attr: Mapping, /) -> stat_result:
        is_dir = attr["is_dir"]
        return stat_result((
            (S_IFDIR if is_dir else S_IFREG) | type(self).STAT_MODE, # mode
            cast(int, attr["id"]), # ino
            cast(int, attr["parent_id"]), # dev
            1, # nlink
            0, # uid
            0, # gid
            0 if is_dir else attr["size"], # size
            cast(float, attr.get("atime", 0)), # atime
            cast(float, attr.get("mtime", 0)), # mtime
            cast(float, attr.get("ctime", 0)), # ctime
        ))

    @overload
    def chdir(
        self, 
        id_or_path: IDOrPathType = 0, 
        /, 
        pid: None | int = None, 
        *, 
        async_: Literal[False] = False, 
        **request_kwargs, 
    ) -> int:
        ...
    @overload
    def chdir(
        self, 
        id_or_path: IDOrPathType = 0, 
        /, 
        pid: None | int = None, 
        *, 
        async_: Literal[True], 
        **request_kwargs, 
    ) -> Coroutine[Any, Any, int]:
        ...
    def chdir(
        self, 
        id_or_path: IDOrPathType = 0, 
        /, 
        pid: None | int = None, 
        *, 
        async_: Literal[False, True] = False, 
        **request_kwargs, 
    ) -> int | Coroutine[Any, Any, int]:
        """切换工作目录
        """
        def gen_step():
            nonlocal id_or_path
            if isinstance(id_or_path, int):
                id = id_or_path
            else:
                if isinstance(id_or_path, P115PathBase):
                    id_or_path = id_or_path.attr
                if isinstance(id_or_path, Mapping) and "id" in id_or_path:
                    id = id_or_path["id"]
                else:
                    attr = yield self.get_attr(
                        id_or_path, 
                        pid=pid, 
                        ensure_file=False, 
                        async_=async_, 
                        **request_kwargs, 
                    )
                    id = attr["id"]
            self.id = id
            return id
        return run_gen_step(gen_step, async_)

    @overload
    def dirlen(
        self, 
        id_or_path: IDOrPathType = "", 
        /, 
        pid: None | int = None, 
        refresh: None | bool = None, 
        *, 
        async_: Literal[False] = False, 
        **request_kwargs, 
    ) -> int:
        ...
    @overload
    def dirlen(
        self, 
        id_or_path: IDOrPathType = "", 
        /, 
        pid: None | int = None, 
        refresh: None | bool = None, 
        *, 
        async_: Literal[True], 
        **request_kwargs, 
    ) -> Coroutine[Any, Any, int]:
        ...
    def dirlen(
        self, 
        id_or_path: IDOrPathType = "", 
        /, 
        pid: None | int = None, 
        refresh: None | bool = None, 
        *, 
        async_: Literal[False, True] = False, 
        **request_kwargs, 
    ) -> int | Coroutine[Any, Any, int]:
        """获取目录直属的文件和目录个数
        """
        def gen_step():
            children = yield self.readdir(
                id_or_path, 
                pid=pid, 
                refresh=refresh, 
                async_=async_, 
                **request_kwargs, 
            )
            return len(children)
        return run_gen_step(gen_step, async_)

    @overload
    def download(
        self, 
        id_or_path: IDOrPathType, 
        /, 
        path: bytes | str | PathLike = "", 
        mode: Literal["a", "w", "x", "i"] = "a", 
        pid: None | int = None, 
        refresh: None | bool = None, 
        *, 
        async_: Literal[False] = False, 
        **request_kwargs, 
    ) -> tuple[str, int]:
        ...
    @overload
    def download(
        self, 
        id_or_path: IDOrPathType, 
        /, 
        path: bytes | str | PathLike = "", 
        mode: Literal["a", "w", "x", "i"] = "a", 
        pid: None | int = None, 
        refresh: None | bool = None, 
        *, 
        async_: Literal[True], 
        **request_kwargs, 
    ) -> Coroutine[Any, Any, tuple[str, int]]:
        ...
    def download(
        self, 
        id_or_path: IDOrPathType, 
        /, 
        path: bytes | str | PathLike = "", 
        mode: Literal["a", "w", "x", "i"] = "a", 
        pid: None | int = None, 
        refresh: None | bool = None, 
        *, 
        async_: Literal[False, True] = False, 
        **request_kwargs, 
    ) -> tuple[str, int] | Coroutine[Any, Any, tuple[str, int]]:
        """下载文件到本地

        :param id_or_path: 文件在 115 网盘上的 id 或路径
        :param path: 本地文件路径
        :param mode: 写入模式
            - a: append，如果文件不存在则创建，存在则追加（断点续传），返回一个任务
            - w: write， 如果文件不存在则创建，存在则覆盖
            - x: exists，如果文件不存在则创建，存在则报错 FileExistsError
            - i: ignore，如果文件不存在则创建，存在则忽略
        :param pid: 相对路径的根目录 id
        :param refresh: 是否刷新数据
        :param async_: 是否异步
        :param request_kwargs: 其它请求参数

        :return: 写入的文件路径和字节数
        """
        def gen_step():
            nonlocal path
            attr = yield self.get_attr(
                id_or_path, 
                pid=pid, 
                refresh=refresh, 
                async_=async_, 
                **request_kwargs, 
            )
            if attr["is_dir"]:
                throw(errno.EISDIR, attr)
            path = fsdecode(path)
            if not path:
                path = attr["name"]
            if ospath.lexists(path):
                if mode == "x":
                    throw(errno.EEXIST, f"file already exists: {path!r}")
                elif mode == "i" or mode == "a" and ospath.getsize(path) == attr["size"]:
                    return path, 0
            url = yield self.get_url(attr, async_=async_, **request_kwargs)
            kwargs: dict = {
                "url": url, 
                "file": path, 
                "headers": url.get("headers"),  
                "resume": mode == "a", 
            }
            if async_:
                progress = yield download_async(**kwargs)
            else:
                progress = download(**kwargs)
            return path, progress.downloaded
        return run_gen_step(gen_step, async_)

    @overload
    def ed2k(
        self, 
        id_or_path: IDOrPathType, 
        /, 
        name: str = "", 
        pid: None | int = None, 
        *, 
        async_: Literal[False] = False, 
        **request_kwargs, 
    ) -> str:
        ...
    @overload
    def ed2k(
        self, 
        id_or_path: IDOrPathType, 
        /, 
        name: str = "", 
        pid: None | int = None, 
        *, 
        async_: Literal[True], 
        **request_kwargs, 
    ) -> Coroutine[Any, Any, str]:
        ...
    def ed2k(
        self, 
        id_or_path: IDOrPathType, 
        /, 
        name: str = "", 
        pid: None | int = None, 
        *, 
        async_: Literal[False, True] = False, 
        **request_kwargs, 
    ) -> str | Coroutine[Any, Any, str]:
        def gen_step():
            nonlocal name
            url = yield self.get_url(
                id_or_path, 
                pid=pid, 
                async_=async_, 
                **request_kwargs, 
            )
            if not name:
                name = url.get("name", "")
            name = name.translate(ED2K_NAME_TRANSTAB)
            if async_:
                async def request():
                    async with self.open(url, "rb", async_=True) as file:
                        return await ed2k_hash_async(file)
                size, hash = yield request()
            else:
                with self.open(url, "rb") as file:
                    size, hash = ed2k_hash(file)
            return f"ed2k://|file|{name}|{size}|{hash}|/"
        return run_gen_step(gen_step, async_)

    @overload
    def exists(
        self, 
        id_or_path: IDOrPathType = "", 
        /, 
        pid: None | int = None, 
        refresh: None | bool = None, 
        *, 
        async_: Literal[False] = False, 
        **request_kwargs, 
    ) -> bool:
        ...
    @overload
    def exists(
        self, 
        id_or_path: IDOrPathType = "", 
        /, 
        pid: None | int = None, 
        refresh: None | bool = None, 
        *, 
        async_: Literal[True], 
        **request_kwargs, 
    ) -> Coroutine[Any, Any, bool]:
        ...
    def exists(
        self, 
        id_or_path: IDOrPathType = "", 
        /, 
        pid: None | int = None, 
        refresh: None | bool = None, 
        *, 
        async_: Literal[False, True] = False, 
        **request_kwargs, 
    ) -> bool | Coroutine[Any, Any, bool]:
        def gen_step():
            try:
                yield self.get_attr(
                    id_or_path, 
                    pid=pid, 
                    refresh=refresh, 
                    async_=async_, 
                    **request_kwargs, 
                )
                return True
            except FileNotFoundError:
                return False
        return run_gen_step(gen_step, async_)

    def getcid(self, /) -> int:
        return self.id

    @overload
    def getcwd(
        self, 
        /, 
        refresh: None | bool = None, 
        *, 
        async_: Literal[False] = False, 
        **request_kwargs, 
    ) -> str:
        ...
    @overload
    def getcwd(
        self, 
        /, 
        refresh: None | bool = None, 
        *, 
        async_: Literal[True], 
        **request_kwargs, 
    ) -> Coroutine[Any, Any, str]:
        ...
    def getcwd(
        self, 
        /, 
        refresh: None | bool = None, 
        *, 
        async_: Literal[False, True] = False, 
        **request_kwargs, 
    ) -> str | Coroutine[Any, Any, str]:
        return self.get_path(
            self.id, 
            refresh=refresh, 
            async_=async_, 
            **request_kwargs, 
        )

    def _get_root_attr(self, /) -> MutableMapping:
        return {"id": 0, "parent_id": 0, "name": "", "is_dir": True, "size": 0}

    @overload
    def _get_attr_by_id(
        self, 
        id: int, 
        /, 
        refresh: None | bool = None, 
        *, 
        async_: Literal[False] = False, 
        **request_kwargs, 
    ) -> MutableMapping:
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
    ) -> Coroutine[Any, Any, MutableMapping]:
        ...
    def _get_attr_by_id(
        self, 
        id: int, 
        /, 
        refresh: None | bool = None, 
        *, 
        async_: Literal[False, True] = False, 
        **request_kwargs, 
    ) -> MutableMapping | Coroutine[Any, Any, MutableMapping]:
        if refresh is None:
            refresh = self.refresh
        def gen_step():
            if id == 0:
                return self._get_root_attr()
            attr = self.id_to_attr.get(id)
            if not refresh and attr:
                return attr
            if self.full_loaded and self.NO_INCREMENT:
                if not attr:
                    throw(errno.EIO, id)
            if attr:
                it: Any = self.readdir(
                    attr["parent_id"], 
                    refresh=refresh, 
                    async_=async_, 
                    **request_kwargs, 
                )
            else:
                it = self.iter(
                    0, 
                    topdown=None, 
                    max_depth=-1, 
                    refresh=refresh, 
                    async_=async_, 
                    **request_kwargs, 
                )
            with with_iter_next(it) as get_next:
                while True:
                    attr = yield get_next()
                    if attr["id"] == id:
                        return attr
            throw(errno.EIO, id)
        return run_gen_step(gen_step, async_)

    @overload
    def _get_attr_by_path(
        self, 
        path: str | Sequence[str], 
        /, 
        ensure_file: None | bool = None, 
        pid: None | int = None, 
        refresh: None | bool = None, 
        *, 
        async_: Literal[False] = False, 
        **request_kwargs, 
    ) -> MutableMapping:
        ...
    @overload
    def _get_attr_by_path(
        self, 
        path: str | Sequence[str], 
        /, 
        ensure_file: None | bool = None, 
        pid: None | int = None, 
        refresh: None | bool = None, 
        *, 
        async_: Literal[True], 
        **request_kwargs, 
    ) -> Coroutine[Any, Any, MutableMapping]:
        ...
    def _get_attr_by_path(
        self, 
        path: str | Sequence[str], 
        /, 
        ensure_file: None | bool = None, 
        pid: None | int = None, 
        refresh: None | bool = None, 
        *, 
        async_: Literal[False, True] = False, 
        **request_kwargs, 
    ) -> MutableMapping | Coroutine[Any, Any, MutableMapping]:
        if refresh is None:
            refresh = self.refresh
        def gen_step():
            nonlocal path, pid, ensure_file
            if pid is None:
                pid = self.id
            patht: Sequence[str]
            if isinstance(path, str):
                if ensure_file is None and path_is_dir_form(path):
                    ensure_file = False
                patht, go_up = splits(path)
            else:
                patht, go_up = path, 0
            if patht and not patht[0]:
                pid = 0
                patht = patht[1:]
            get_parent_id = self.get_parent_id
            while pid and go_up:
                pid = yield get_parent_id(
                    pid, 
                    refresh=refresh, 
                    async_=async_, 
                    **request_kwargs, 
                )
            if not patht:
                if ensure_file:
                    throw(errno.ENOENT, path)
                if not pid:
                    return self._get_root_attr()
                return self.get_attr(
                    pid, 
                    ensure_file=ensure_file, 
                    refresh=refresh, 
                    async_=async_, 
                    **request_kwargs, 
                )
            get_id = self.id_to_dirnode.get_id
            readdir = self.readdir
            for name in patht[:-1]:
                if not refresh:
                    try:
                        pid = get_id([name], parent_id=pid)
                        continue
                    except KeyError:
                        pass
                found = False
                for attr in (yield readdir(
                    pid, 
                    refresh=refresh, 
                    async_=async_, 
                    **request_kwargs, 
                )):
                    if attr["is_dir"] and attr["name"] == name:
                        pid = attr["id"]
                        found = True
                if not found:
                    throw(errno.ENOENT, path)
            name = patht[-1]
            if not refresh and pid in self.id_to_readdir:
                attr = self._pid_name_to_attr.get((pid, name))
                if attr and attr["parent_id"] == pid and attr["name"] == name:
                    return attr
                else:
                    self._pid_name_to_attr.pop((pid, name), None)
                    throw(errno.ENOENT, path)
            for attr in (yield readdir(
                pid, 
                refresh=refresh, 
                async_=async_, 
                **request_kwargs, 
            )):
                if attr["name"] == name:
                    if ensure_file is None or ensure_file ^ attr["is_dir"]:
                        return attr
            throw(errno.ENOENT, path)
        return run_gen_step(gen_step, async_)

    @overload
    def get_attr(
        self, 
        id_or_path: IDOrPathType = "", 
        /, 
        ensure_file: None | bool = None, 
        pid: None | int = None, 
        refresh: None | bool = None, 
        *, 
        async_: Literal[False] = False, 
        **request_kwargs, 
    ) -> MutableMapping:
        ...
    @overload
    def get_attr(
        self, 
        id_or_path: IDOrPathType = "", 
        /, 
        ensure_file: None | bool = None, 
        pid: None | int = None, 
        refresh: None | bool = None, 
        *, 
        async_: Literal[True], 
        **request_kwargs, 
    ) -> Coroutine[Any, Any, MutableMapping]:
        ...
    def get_attr(
        self, 
        id_or_path: IDOrPathType = "", 
        /, 
        ensure_file: None | bool = None, 
        pid: None | int = None, 
        refresh: None | bool = None, 
        *, 
        async_: Literal[False, True] = False, 
        **request_kwargs, 
    ) -> MutableMapping | Coroutine[Any, Any, MutableMapping]:
        if pid is None:
            pid = self.id
        if refresh is None:
            refresh = self.refresh
        def gen_step():
            nonlocal id_or_path, ensure_file, pid
            if isinstance(id_or_path, P115PathBase):
                id_or_path = id_or_path.attr
            if isinstance(id_or_path, Mapping):
                attr = id_or_path
                if "id" in attr:
                    id_or_path = attr["id"]
                elif "path" in attr:
                    id_or_path = attr["path"]
                else:
                    id_or_path = [attr["name"]]
                if "parent_id" in attr:
                    pid = attr["parent_id"]
                if "is_dir" in attr:
                    ensure_file = not attr["is_dir"]
            if isinstance(id_or_path, int):
                return (yield self._get_attr_by_id(
                    id_or_path, 
                    refresh=refresh, 
                    async_=async_, 
                    **request_kwargs, 
                ))
            return self._get_attr_by_path(
                cast(str | Sequence[str], id_or_path), 
                ensure_file=ensure_file, 
                pid=pid, 
                refresh=refresh, 
                async_=async_, 
                **request_kwargs, 
            )
        return run_gen_step(gen_step, async_)

    @overload
    def get_ancestors(
        self, 
        id_or_path: IDOrPathType = "", 
        /, 
        pid: None | int = None, 
        refresh: None | bool = None, 
        *, 
        async_: Literal[False] = False, 
        **request_kwargs, 
    ) -> list[AncestorDict]:
        ...
    @overload
    def get_ancestors(
        self, 
        id_or_path: IDOrPathType = "", 
        /, 
        pid: None | int = None, 
        refresh: None | bool = None, 
        *, 
        async_: Literal[True], 
        **request_kwargs, 
    ) -> Coroutine[Any, Any, list[AncestorDict]]:
        ...
    def get_ancestors(
        self, 
        id_or_path: IDOrPathType = "", 
        /, 
        pid: None | int = None, 
        refresh: None | bool = None, 
        *, 
        async_: Literal[False, True] = False, 
        **request_kwargs, 
    ) -> list[AncestorDict] | Coroutine[Any, Any, list[AncestorDict]]:
        if pid is None:
            pid = self.id
        if refresh is None:
            refresh = self.refresh
        def gen_step():
            nonlocal id_or_path, pid
            if isinstance(id_or_path, P115PathBase):
                id_or_path = id_or_path.attr
            if isinstance(id_or_path, Mapping):
                attr = id_or_path
                if "id" in attr:
                    id_or_path = attr["id"]
                elif "path" in attr:
                    id_or_path = attr["path"]
                else:
                    id_or_path = [attr["name"]]
                if "parent_id" in attr:
                    pid = attr["parent_id"]
                if not refresh and pid == 0 and "id" in attr and "name" in attr:
                    return [
                        {"id": 0, "parent_id": 0, "name": ""}, 
                        {"id": attr["id"], "parent_id": pid, "name": attr["name"]}, 
                    ]
            if id_or_path == 0:
                return [{"id": 0, "parent_id": 0, "name": ""}]
            attr = yield self.get_attr(
                id_or_path, 
                pid=pid, 
                refresh=refresh, 
                async_=async_, 
                **request_kwargs, 
            )
            pid = attr["parent_id"]
            pancestors: None | list[AncestorDict] = None
            if not refresh:
                try:
                    pancestors = self.id_to_dirnode.get_ancestors(pid)
                except KeyError:
                    pass
            if pancestors is None:
                pancestors = yield self._get_ancestors_by_cid(
                    pid, 
                    refresh=refresh, 
                    async_=async_, 
                    **request_kwargs, 
                )
                pancestors = cast(list[AncestorDict], pancestors)
            pancestors.append({"id": attr["id"], "parent_id": pid, "name": attr["name"]})
            return pancestors
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
            attr = yield self.get_attr(
                cid, 
                refresh=refresh, 
                async_=async_, 
                **request_kwargs, 
            )
            ancestors: list[AncestorDict] = yield self._get_ancestors_by_cid(
                attr["parent_id"], 
                refresh=refresh, 
                async_=async_, 
                **request_kwargs, 
            )
            ancestors.append({
                "id": attr["id"], 
                "parent_id": attr["parent_id"], 
                "name": attr["name"], 
            })
            return ancestors
        return run_gen_step(gen_step, async_)

    @overload
    def get_id(
        self, 
        id_or_path: IDOrPathType = "", 
        /, 
        pid: None | int = None, 
        refresh: None | bool = None, 
        *, 
        async_: Literal[False] = False, 
        **request_kwargs, 
    ) -> int:
        ...
    @overload
    def get_id(
        self, 
        id_or_path: IDOrPathType = "", 
        /, 
        pid: None | int = None, 
        refresh: None | bool = None, 
        *, 
        async_: Literal[True], 
        **request_kwargs, 
    ) -> Coroutine[Any, Any, int]:
        ...
    def get_id(
        self, 
        id_or_path: IDOrPathType = "", 
        /, 
        pid: None | int = None, 
        refresh: None | bool = None, 
        *, 
        async_: Literal[False, True] = False, 
        **request_kwargs, 
    ) -> int | Coroutine[Any, Any, int]:
        if refresh is None:
            refresh = self.refresh
        def gen_step():
            nonlocal id_or_path, pid
            if isinstance(id_or_path, int):
                return id_or_path
            if isinstance(id_or_path, P115PathBase):
                id_or_path = id_or_path.attr
            if isinstance(id_or_path, Mapping):
                attr = id_or_path
                if "id" in attr:
                    return attr["id"]
                elif "path" in attr:
                    id_or_path = attr["path"]
                else:
                    id_or_path = [attr["name"]]
                if "parent_id" in attr:
                    pid = attr["parent_id"]
            if pid is None:
                pid = self.id
            id_or_path = cast(str | Sequence[str], id_or_path)
            if isinstance(id_or_path, str):
                path = id_or_path
                if id_or_path == "/":
                    return 0
                elif path in ("", "."):
                    return pid
            else:
                if not id_or_path:
                    return pid
                elif len(id_or_path) == 1 and not id_or_path[0]:
                    return 0
            patht: Sequence[str]
            if not refresh:
                try:
                    if isinstance(id_or_path, str):
                        patht, go_up = splits(id_or_path)
                        while pid and go_up:
                            pid = self.id_to_dirnode.get_parent_id(pid)
                            go_up -= 1
                    else:
                        patht = id_or_path
                    return self.id_to_dirnode.get_id(patht, pid)
                except KeyError:
                    pass
            attr = yield self.get_attr(
                id_or_path, 
                pid=pid, 
                refresh=refresh, 
                async_=async_, 
                **request_kwargs, 
            )
            return attr["id"]
        return run_gen_step(gen_step, async_)

    @overload
    def get_parent_id(
        self, 
        id_or_path: IDOrPathType = "", 
        /, 
        pid: None | int = None, 
        refresh: None | bool = None, 
        *, 
        async_: Literal[False] = False, 
        **request_kwargs, 
    ) -> list[dict]:
        ...
    @overload
    def get_parent_id(
        self, 
        id_or_path: IDOrPathType = "", 
        /, 
        pid: None | int = None, 
        refresh: None | bool = None, 
        *, 
        async_: Literal[True], 
        **request_kwargs, 
    ) -> Coroutine[Any, Any, list[dict]]:
        ...
    def get_parent_id(
        self, 
        id_or_path: IDOrPathType = "", 
        /, 
        pid: None | int = None, 
        refresh: None | bool = None, 
        *, 
        async_: Literal[False, True] = False, 
        **request_kwargs, 
    ) -> list[dict] | Coroutine[Any, Any, list[dict]]:
        if refresh is None:
            refresh = self.refresh
        def gen_step():
            nonlocal id_or_path, pid
            if isinstance(id_or_path, P115PathBase):
                id_or_path = id_or_path.attr
            if isinstance(id_or_path, Mapping):
                attr = id_or_path
                if "id" in attr:
                    id_or_path = attr["id"]
                elif "path" in attr:
                    id_or_path = attr["path"]
                else:
                    id_or_path = [attr["name"]]
                if "parent_id" in attr:
                    pid = attr["parent_id"]
            if pid is None:
                pid = self.id
            if not refresh and isinstance(id_or_path, int):
                try:
                    return self.id_to_dirnode.get_parent_id(id_or_path)
                except KeyError:
                    pass
            attr = yield self.get_attr(
                id_or_path, 
                pid=pid, 
                refresh=refresh, 
                async_=async_, 
                **request_kwargs, 
            )
            return attr["parent_id"]
        return run_gen_step(gen_step, async_)

    @overload
    def get_path(
        self, 
        id_or_path: IDOrPathType = "", 
        /, 
        pid: None | int = None, 
        refresh: None | bool = None, 
        *, 
        async_: Literal[False] = False, 
        **request_kwargs, 
    ) -> str:
        ...
    @overload
    def get_path(
        self, 
        id_or_path: IDOrPathType = "", 
        /, 
        pid: None | int = None, 
        refresh: None | bool = None, 
        *, 
        async_: Literal[True], 
        **request_kwargs, 
    ) -> Coroutine[Any, Any, str]:
        ...
    def get_path(
        self, 
        id_or_path: IDOrPathType = "", 
        /, 
        pid: None | int = None, 
        refresh: None | bool = None, 
        *, 
        async_: Literal[False, True] = False, 
        **request_kwargs, 
    ) -> str | Coroutine[Any, Any, str]:
        def gen_step():
            patht: list[str] = yield self.get_patht(
                id_or_path, 
                pid=pid, 
                refresh=refresh, 
                async_=async_, 
                **request_kwargs, 
            )
            return joins(patht)
        return run_gen_step(gen_step, async_)

    @overload
    def get_patht(
        self, 
        id_or_path: IDOrPathType = "", 
        /, 
        pid: None | int = None, 
        refresh: None | bool = None, 
        *, 
        async_: Literal[False] = False, 
        **request_kwargs, 
    ) -> list[str]:
        ...
    @overload
    def get_patht(
        self, 
        id_or_path: IDOrPathType = "", 
        /, 
        pid: None | int = None, 
        refresh: None | bool = None, 
        *, 
        async_: Literal[True], 
        **request_kwargs, 
    ) -> Coroutine[Any, Any, list[str]]:
        ...
    def get_patht(
        self, 
        id_or_path: IDOrPathType = "", 
        /, 
        pid: None | int = None, 
        refresh: None | bool = None, 
        *, 
        async_: Literal[False, True] = False, 
        **request_kwargs, 
    ) -> list[str] | Coroutine[Any, Any, list[str]]:
        if refresh is None:
            refresh = self.refresh
        def gen_step():
            nonlocal id_or_path, pid
            if isinstance(id_or_path, P115PathBase):
                id_or_path = id_or_path.attr
            if isinstance(id_or_path, Mapping):
                attr = id_or_path
                if "id" in attr:
                    id_or_path = attr["id"]
                elif "path" in attr:
                    id_or_path = attr["path"]
                else:
                    id_or_path = [attr["name"]]
                if "parent_id" in attr:
                    pid = attr["parent_id"]
            if isinstance(id_or_path, int):
                id = id_or_path
                if id == 0:
                    return [""]
                if not refresh:
                    try:
                        return self.id_to_dirnode.get_patht(id)
                    except KeyError:
                        pass
                ancestors = yield self.get_ancestors(
                    id, 
                    refresh=refresh, 
                    async_=async_, 
                    **request_kwargs, 
                )
                return [a["name"] for a in ancestors]
            if pid is None:
                pid = self.id
            id_or_path = cast(str | Sequence[str], id_or_path)
            if isinstance(id_or_path, str):
                id_or_path, go_up = splits(id_or_path)
            else:
                go_up = 0
            if id_or_path and not id_or_path[0]:
                return id_or_path
            if pid == 0:
                patht = [""]
                go_up = 0
            else:
                patht = yield self.get_patht(
                    pid, 
                    refresh=refresh, 
                    async_=async_, 
                    **request_kwargs, 
                )
            if go_up:
                if len(patht) <= go_up:
                    patht = [""]
                else:
                    patht = patht[:-go_up]
            if id_or_path:
                patht.extend(id_or_path)
            return patht
        return run_gen_step(gen_step, async_)

    @overload
    def glob(
        self, 
        /, 
        pattern: str = "*", 
        top: IDOrPathType = "", 
        ignore_case: bool = False, 
        allow_escaped_slash: bool = True, 
        pid: None | int = None, 
        refresh: None | bool = None, 
        *, 
        async_: Literal[False] = False, 
        **request_kwargs, 
    ) -> Iterator[Mapping]:
        ...
    @overload
    def glob(
        self, 
        /, 
        pattern: str = "*", 
        top: IDOrPathType = "", 
        ignore_case: bool = False, 
        allow_escaped_slash: bool = True, 
        pid: None | int = None, 
        refresh: None | bool = None, 
        *, 
        async_: Literal[True], 
        **request_kwargs, 
    ) -> AsyncIterator[Mapping]:
        ...
    def glob(
        self, 
        /, 
        pattern: str = "*", 
        top: IDOrPathType = "", 
        ignore_case: bool = False, 
        allow_escaped_slash: bool = True, 
        pid: None | int = None, 
        refresh: None | bool = None, 
        *, 
        async_: Literal[False, True] = False, 
        **request_kwargs, 
    ) -> Iterator[Mapping] | AsyncIterator[Mapping]:
        if pattern == "*":
            return self.iter(
                top, 
                pid=pid, 
                refresh=refresh, 
                async_=async_, 
                **request_kwargs, 
            )
        elif len(pattern) >= 2 and not pattern.strip("*"):
            return self.iter(
                top, 
                max_depth=-1, 
                pid=pid, 
                refresh=refresh, 
                async_=async_, 
                **request_kwargs, 
            )
        def gen_step():
            nonlocal pattern, pid
            if not pattern:
                try:
                    yield Yield(self.get_attr(
                        top, 
                        pid=pid, 
                        refresh=refresh, 
                        async_=async_, 
                        **request_kwargs, 
                    ))
                except FileNotFoundError:
                    pass
                return
            elif not pattern.lstrip("/"):
                return Yield(self.get_attr(0))
            splitted_pats = tuple(translate_iter(
                pattern, 
                allow_escaped_slash=allow_escaped_slash, 
            ))
            if pattern.startswith("/"):
                attr = self.get_attr(0)
                pid = 0
                dirname = "/"
            else:
                attr = yield self.get_attr(
                    top, 
                    pid=pid, 
                    refresh=refresh, 
                    async_=async_, 
                    **request_kwargs, 
                )
                pid = cast(int, attr["id"])
                dirname = self.get_path(attr)
            i = 0
            subpath = ""
            if ignore_case:
                if any(typ == "dstar" for _, typ, _ in splitted_pats):
                    pattern = "".join(
                        "(?:/%s)?" % pat if typ == "dstar" else "/" + pat 
                        for pat, typ, _ in splitted_pats
                    )
                    if dirname != "/":
                        pattern = re_escape(dirname) + pattern
                    match = re_compile("(?i:%s)" % pattern).fullmatch
                    yield YieldFrom(self.iter(
                        attr, 
                        max_depth=-1, 
                        predicate=lambda a: match(self.get_path(a)) is not None, 
                        refresh=refresh, 
                        async_=async_, 
                        **request_kwargs, 
                    ))
                    return
            else:
                typ = None
                for i, (pat, typ, orig) in enumerate(splitted_pats):
                    if typ != "orig":
                        break
                    subpath = joinpath(subpath, orig)
                if typ == "orig":
                    try:
                        yield Yield(self.get_attr(
                            subpath, 
                            pid=pid, 
                            refresh=refresh, 
                            async_=async_, 
                            **request_kwargs, 
                        ))
                    except FileNotFoundError:
                        pass
                    return
                elif typ == "dstar" and i + 1 == len(splitted_pats):
                    return YieldFrom(self.iter(
                        subpath, 
                        pid=pid, 
                        max_depth=-1, 
                        refresh=refresh, 
                        async_=async_, 
                        **request_kwargs, 
                    ))
                if any(typ == "dstar" for _, typ, _ in splitted_pats[i:]):
                    pattern = "".join(
                        "(?:/%s)?" % pat if typ == "dstar" else "/" + pat 
                        for pat, typ, _ in splitted_pats[i:]
                    )
                    if dirname != "/":
                        pattern = re_escape(dirname) + pattern
                    match = re_compile(pattern).fullmatch
                    return YieldFrom(self.iter(
                        subpath, 
                        pid=pid, 
                        max_depth=-1, 
                        predicate=lambda a: match(self.get_path(a)) is not None, 
                        refresh=refresh, 
                        async_=async_, 
                        **request_kwargs, 
                    ))
            cref_cache: dict[int, Callable] = {}
            if subpath:
                try:
                    attr = yield self.get_attr(
                        subpath, 
                        pid=pid, 
                        refresh=refresh, 
                        async_=async_, 
                        **request_kwargs, 
                    )
                except FileNotFoundError:
                    return
            if not attr["is_dir"]:
                return
            def glob_step_match(attr: Mapping, i: int):
                j = i + 1
                at_end = j == len(splitted_pats)
                pat, typ, orig = splitted_pats[i]
                if typ == "orig":
                    try:
                        subattr = yield self.get_attr(
                            orig, 
                            pid=attr["id"], 
                            refresh=refresh, 
                            async_=async_, 
                            **request_kwargs, 
                        )
                    except FileNotFoundError:
                        return
                    if at_end:
                        yield Yield(subattr)
                    elif subattr["is_dir"]:
                        yield from glob_step_match(subattr, j)
                elif typ == "star":
                    if at_end:
                        yield YieldFrom(self.iter(
                            attr, 
                            refresh=refresh, 
                            async_=async_, 
                            **request_kwargs, 
                        ))
                    else:
                        subattrs = yield self.readdir(
                            attr, 
                            refresh=refresh, 
                            async_=async_, 
                            **request_kwargs, 
                        )
                        for subattr in subattrs:
                            if subattr["is_dir"]:
                                yield from glob_step_match(subattr, j)
                else:
                    subattrs = yield self.readdir(
                        attr, 
                        refresh=refresh, 
                        async_=async_, 
                        **request_kwargs, 
                    )
                    for subattr in subattrs:
                        try:
                            cref = cref_cache[i]
                        except KeyError:
                            if ignore_case:
                                pat = "(?i:%s)" % pat
                            cref = cref_cache[i] = re_compile(pat).fullmatch
                        if cref(subattr["name"]):
                            if at_end:
                                yield Yield(subattr)
                            elif subattr["is_dir"]:
                                yield from glob_step_match(subattr, j)
            yield from glob_step_match(attr, i)
        return run_gen_step_iter(gen_step, async_)

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
    ) -> str:
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
    ) -> Coroutine[Any, Any, str]:
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
    ) -> str | Coroutine[Any, Any, str]:
        def gen_step():
            attr = yield self.get_attr(
                id_or_path, 
                pid=pid, 
                ensure_file=True, 
                refresh=refresh, 
                async_=async_, 
                **request_kwargs, 
            )
            if attr["is_dir"]:
                throw(errno.EISDIR, attr)
            return attr["url"]
        return run_gen_step(gen_step, async_)

    @overload
    def has_child(
        self, 
        /, 
        child: int | str, 
        parent: IDOrPathType = "", 
        pid: None | int = None, 
        refresh: None | bool = None, 
        *, 
        async_: Literal[False] = False, 
        **request_kwargs, 
    ) -> bool:
        ...
    @overload
    def has_child(
        self, 
        /, 
        child: int | str, 
        parent: IDOrPathType = "", 
        pid: None | int = None, 
        refresh: None | bool = None, 
        *, 
        async_: Literal[True], 
        **request_kwargs, 
    ) -> Coroutine[Any, Any, bool]:
        ...
    def has_child(
        self, 
        /, 
        child: int | str, 
        parent: IDOrPathType = "", 
        pid: None | int = None, 
        refresh: None | bool = None, 
        *, 
        async_: Literal[False, True] = False, 
        **request_kwargs, 
    ) -> bool | Coroutine[Any, Any, bool]:
        """检查目录中是否存在某个文件或目录
        """
        def gen_step():
            attr = yield self.get_attr(
                parent, 
                pid=pid, 
                refresh=refresh, 
                async_=async_, 
                **request_kwargs, 
            )
            if not attr["is_dir"]:
                return False
            try:
                child_attr = yield self.get_attr(
                    child if isinstance(child, int) else [child], 
                    pid=attr["id"], 
                    refresh=refresh, 
                    async_=async_, 
                    **request_kwargs, 
                )
            except FileNotFoundError:
                return False
            return attr["id"] == child_attr["parent_id"]
        return run_gen_step(gen_step, async_)

    @overload
    def hash[T](
        self, 
        id_or_path: IDOrPathType = "", 
        /, 
        digest: str | HashObj | Callable[[], HashObj] | Callable[[], Callable[[bytes, T], T]] = "md5", 
        start: int = 0, 
        size: None | int = None, 
        pid: None | int = None, 
        refresh: None | bool = None, 
        *, 
        async_: Literal[False] = False, 
        **request_kwargs, 
    ) -> tuple[int, HashObj | T]:
        ...
    @overload
    def hash[T](
        self, 
        id_or_path: IDOrPathType = "", 
        /, 
        digest: str | HashObj | Callable[[], HashObj] | Callable[[], Callable[[bytes, T], T]] | Callable[[], Callable[[bytes, T], Awaitable[T]]] = "md5", 
        start: int = 0, 
        size: None | int = None, 
        pid: None | int = None, 
        refresh: None | bool = None, 
        *, 
        async_: Literal[True], 
        **request_kwargs, 
    ) -> Coroutine[Any, Any, tuple[int, HashObj | T]]:
        ...
    def hash[T](
        self, 
        id_or_path: IDOrPathType = "", 
        /, 
        digest: str | HashObj | Callable[[], HashObj] | Callable[[], Callable[[bytes, T], T]] | Callable[[], Callable[[bytes, T], Awaitable[T]]] = "md5", 
        start: int = 0, 
        size: None | int = None, 
        pid: None | int = None, 
        refresh: None | bool = None, 
        *, 
        async_: Literal[False, True] = False, 
        **request_kwargs, 
    ) -> tuple[int, HashObj | T] | Coroutine[Any, Any, tuple[int, HashObj | T]]:
        def gen_step():
            if async_:
                async def request():
                    async with self.open(
                        id_or_path, 
                        mode="rb", 
                        start=start, 
                        pid=pid, 
                        refresh=refresh, 
                        async_=True, 
                        **request_kwargs, 
                    ) as file:
                        return await file_digest_async(file, digest, stop=size)
                return request()
            else:
                with self.open(
                    id_or_path, 
                    mode="rb", 
                    start=start, 
                    pid=pid, 
                    refresh=refresh, 
                    **request_kwargs, 
                ) as file:
                    return file_digest(file, digest, stop=size)
        return run_gen_step(gen_step, async_)

    @overload
    def hashes[T](
        self, 
        id_or_path: IDOrPathType = "", 
        /, 
        digest: str | HashObj | Callable[[], HashObj] | Callable[[], Callable[[bytes, T], T]] = "md5", 
        *digests: str | HashObj | Callable[[], HashObj] | Callable[[], Callable[[bytes, T], T]], 
        start: int = 0, 
        size: None | int = None, 
        pid: None | int = None, 
        refresh: None | bool = None, 
        async_: Literal[False] = False, 
        **request_kwargs, 
    ) -> tuple[int, list[HashObj | T]]:
        ...
    @overload
    def hashes[T](
        self, 
        id_or_path: IDOrPathType = "", 
        /, 
        digest: str | HashObj | Callable[[], HashObj] | Callable[[], Callable[[bytes, T], T]] | Callable[[], Callable[[bytes, T], Awaitable[T]]] = "md5", 
        *digests: str | HashObj | Callable[[], HashObj] | Callable[[], Callable[[bytes, T], T]] | Callable[[], Callable[[bytes, T], Awaitable[T]]], 
        start: int = 0, 
        size: None | int = None, 
        pid: None | int = None, 
        refresh: None | bool = None, 
        async_: Literal[True], 
        **request_kwargs, 
    ) -> Coroutine[Any, Any, tuple[int, list[HashObj | T]]]:
        ...
    def hashes[T](
        self, 
        id_or_path: IDOrPathType = "", 
        /, 
        digest: str | HashObj | Callable[[], HashObj] | Callable[[], Callable[[bytes, T], T]] | Callable[[], Callable[[bytes, T], Awaitable[T]]] = "md5", 
        *digests: str | HashObj | Callable[[], HashObj] | Callable[[], Callable[[bytes, T], T]] | Callable[[], Callable[[bytes, T], Awaitable[T]]], 
        start: int = 0, 
        size: None | int = None, 
        pid: None | int = None, 
        refresh: None | bool = None, 
        async_: Literal[False, True] = False, 
        **request_kwargs, 
    ) -> tuple[int, list[HashObj | T]] | Coroutine[Any, Any, tuple[int, list[HashObj | T]]]:
        def gen_step():
            if async_:
                async def request():
                    async with self.open(
                        id_or_path, 
                        mode="rb", 
                        start=start, 
                        pid=pid, 
                        refresh=refresh, 
                        async_=True, 
                        **request_kwargs, 
                    ) as file:
                        return await file_mdigest_async(file, digest, *digests, stop=size)
                return request()
            else:
                with self.open(
                    id_or_path, 
                    mode="rb", 
                    start=start, 
                    pid=pid, 
                    refresh=refresh, 
                    **request_kwargs, 
                ) as file:
                    return file_mdigest(file, digest, *digests, stop=size)
        return run_gen_step(gen_step, async_)

    @overload
    def is_empty(
        self, 
        id_or_path: IDOrPathType = "", 
        /, 
        pid: None | int = None, 
        refresh: None | bool = None, 
        *, 
        async_: Literal[False] = False, 
        **request_kwargs, 
    ) -> bool:
        ...
    @overload
    def is_empty(
        self, 
        id_or_path: IDOrPathType = "", 
        /, 
        pid: None | int = None, 
        refresh: None | bool = None, 
        *, 
        async_: Literal[True], 
        **request_kwargs, 
    ) -> Coroutine[Any, Any, bool]:
        ...
    def is_empty(
        self, 
        id_or_path: IDOrPathType = "", 
        /, 
        pid: None | int = None, 
        refresh: None | bool = None, 
        *, 
        async_: Literal[False, True] = False, 
        **request_kwargs, 
    ) -> bool | Coroutine[Any, Any, bool]:
        """是否为空文件、空目录或者不存在
        """
        def gen_step():
            try:
                attr = yield self.get_attr(
                    id_or_path, 
                    pid=pid, 
                    refresh=False, 
                    async_=async_, 
                    **request_kwargs, 
                )
            except FileNotFoundError:
                return True
            if attr["is_dir"]:
                count_children = yield self.dirlen(
                    id_or_path, 
                    pid=pid, 
                    refresh=refresh, 
                    async_=async_, 
                    **request_kwargs, 
                )
                return count_children == 0
            else:
                return attr["size"] == 0
        return run_gen_step(gen_step, async_)

    @overload
    def isdir(
        self, 
        id_or_path: IDOrPathType = "", 
        /, 
        pid: None | int = None, 
        *, 
        async_: Literal[False] = False, 
        **request_kwargs, 
    ) -> bool:
        ...
    @overload
    def isdir(
        self, 
        id_or_path: IDOrPathType = "", 
        /, 
        pid: None | int = None, 
        *, 
        async_: Literal[True], 
        **request_kwargs, 
    ) -> Coroutine[Any, Any, bool]:
        ...
    def isdir(
        self, 
        id_or_path: IDOrPathType = "", 
        /, 
        pid: None | int = None, 
        *, 
        async_: Literal[False, True] = False, 
        **request_kwargs, 
    ) -> bool | Coroutine[Any, Any, bool]:
        def gen_step():
            try:
                attr = yield self.get_attr(
                    id_or_path, 
                    pid=pid, 
                    refresh=False, 
                    async_=async_, 
                    **request_kwargs, 
                )
                return attr["is_dir"]
            except FileNotFoundError:
                return False
        return run_gen_step(gen_step, async_)

    @overload
    def isfile(
        self, 
        id_or_path: IDOrPathType = "", 
        /, 
        pid: None | int = None, 
        *, 
        async_: Literal[False] = False, 
        **request_kwargs, 
    ) -> bool:
        ...
    @overload
    def isfile(
        self, 
        id_or_path: IDOrPathType = "", 
        /, 
        pid: None | int = None, 
        *, 
        async_: Literal[True], 
        **request_kwargs, 
    ) -> Coroutine[Any, Any, bool]:
        ...
    def isfile(
        self, 
        id_or_path: IDOrPathType = "", 
        /, 
        pid: None | int = None, 
        *, 
        async_: Literal[False, True] = False, 
        **request_kwargs, 
    ) -> bool | Coroutine[Any, Any, bool]:
        def gen_step():
            try:
                attr = yield self.get_attr(
                    id_or_path, 
                    pid=pid, 
                    refresh=False, 
                    async_=async_, 
                    **request_kwargs, 
                )
                return not attr["is_dir"]
            except FileNotFoundError:
                return False
        return run_gen_step(gen_step, async_)

    @overload
    def iter(
        self, 
        top: IDOrPathType = "", 
        /, 
        topdown: None | bool = True, 
        min_depth: int = 1, 
        max_depth: int = 1, 
        predicate: None | Callable[[Mapping], Literal[None, 1, False, True]] = None, 
        onerror: bool | Callable[[OSError], bool] = True, 
        pid: None | int = None, 
        refresh: None | bool = None, 
        *, 
        async_: Literal[False] = False, 
        **request_kwargs, 
    ) -> Iterator[MutableMapping]:
        ...
    @overload
    def iter(
        self, 
        top: IDOrPathType = "", 
        /, 
        topdown: None | bool = True, 
        min_depth: int = 1, 
        max_depth: int = 1, 
        predicate: None | Callable[[Mapping], Literal[None, 1, False, True]] = None, 
        onerror: bool | Callable[[OSError], bool] = True, 
        pid: None | int = None, 
        refresh: None | bool = None, 
        *, 
        async_: Literal[True], 
        **request_kwargs, 
    ) -> AsyncIterator[MutableMapping]:
        ...
    def iter(
        self, 
        top: IDOrPathType = "", 
        /, 
        topdown: None | bool = True, 
        min_depth: int = 1, 
        max_depth: int = 1, 
        predicate: None | Callable[[Mapping], Literal[None, 1, False, True]] = None, 
        onerror: bool | Callable[[OSError], bool] = True, 
        pid: None | int = None, 
        refresh: None | bool = None, 
        *, 
        async_: Literal[False, True] = False, 
        **request_kwargs, 
    ) -> Iterator[MutableMapping] | AsyncIterator[MutableMapping]:
        def gen_step():
            try:
                attr = yield self.get_attr(
                    top, 
                    pid=pid, 
                    refresh=refresh, 
                    async_=async_, 
                    **request_kwargs, 
                )
            except OSError as e:
                if callable(onerror):
                    yield onerror(e)
                elif onerror:
                    raise
                return
            if min_depth <= 0:
                yield attr
            yield YieldFrom(iterdir_generic(
                attr, 
                iterdir=partial(self.readdir, refresh=refresh, async_=async_, **request_kwargs), 
                topdown=topdown, 
                min_depth=min_depth, 
                max_depth=max_depth, 
                isdir=itemgetter("is_dir"), 
                predicate=predicate, 
                onerror=onerror, 
                async_=async_, 
            ))
            if attr["id"] == 0:
                self.full_loaded = True
        return run_gen_step_iter(gen_step, async_)

    @overload
    def listdir(
        self, 
        id_or_path: IDOrPathType = "", 
        /, 
        pid: None | int = None, 
        refresh: None | bool = None, 
        *, 
        async_: Literal[False] = False, 
        **request_kwargs, 
    ) -> list[P115PathType]:
        ...
    @overload
    def listdir(
        self, 
        id_or_path: IDOrPathType = "", 
        /, 
        pid: None | int = None, 
        refresh: None | bool = None, 
        *, 
        async_: Literal[True], 
        **request_kwargs, 
    ) -> Coroutine[Any, Any, list[P115PathType]]:
        ...
    def listdir(
        self, 
        id_or_path: IDOrPathType = "", 
        /, 
        pid: None | int = None, 
        refresh: None | bool = None, 
        *, 
        async_: Literal[False, True] = False, 
        **request_kwargs, 
    ) -> list[P115PathType] | Coroutine[Any, Any, list[P115PathType]]:
        def gen_step():
            children = yield self.readdir(
                id_or_path, 
                pid=pid, 
                refresh=refresh, 
                async_=async_, 
                **request_kwargs, 
            ) 
            path_class = type(self).path_class
            return [path_class(self, attr) for attr in children]
        return run_gen_step(gen_step, async_)

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
        if pid is None:
            pid = self.id
        if refresh is None:
            refresh = self.refresh
        if not id_or_path:
            id_or_path = pid
        def gen_step():
            if isinstance(id_or_path, int):
                id = id_or_path
            else:
                id = yield self.get_id(
                    id_or_path, 
                    pid=pid, 
                    refresh=refresh, 
                    ensure_file=False, 
                    async_=async_, 
                    **request_kwargs, 
                )
            id_to_readdir = self.id_to_readdir
            children = id_to_readdir.get(id)
            if refresh or not id_to_readdir or children is None:
                if children is None:
                    children = {}
                if async_:
                    lock: Any = self._readdir_alocks[id]
                else:
                    lock = self._readdir_locks[id]
                timeout = 0.1 # 100 ms
                start_t = time()
                yield lock.acquire()
                try:
                    if time() - start_t >= timeout:
                        children_new = id_to_readdir.get(id)
                        if children_new is not None:
                            return list(children_new.values())
                    with with_iter_next(self.iterdir(
                        id, 
                        async_=async_, 
                        **request_kwargs, 
                    )) as get_next:
                        while True:
                            attr = yield get_next()
                            fid = attr["id"]
                            try:
                                children[fid].update(attr)
                            except KeyError:
                                children[fid] = attr
                finally:
                    lock.release()
                id_to_readdir[id] = children
                self._pid_name_to_attr.update(((id, attr["name"]), attr) for attr in children.values())
                self.id_to_attr.update(children)
            return list(children.values())
        return run_gen_step(gen_step, async_)

    @overload
    def open(
        self, 
        id_or_path: IDOrPathType, 
        /, 
        mode: Literal["rb", "br"] = "rb", 
        buffering: None | int = None, 
        encoding: None | str = None, 
        errors: None | str = None, 
        newline: None | str = None, 
        start: int = 0, 
        seek_threshold: int = 1 << 20, 
        http_file_reader_cls: None | type[HTTPFileReader] = None, 
        pid: None | int = None, 
        refresh: None | bool = None, 
        *, 
        async_: Literal[False] = False, 
        **request_kwargs, 
    ) -> HTTPFileReader | BufferedReader:
        ...
    @overload
    def open(
        self, 
        id_or_path: IDOrPathType, 
        /, 
        mode: Literal["r", "rt", "tr"], 
        buffering: None | int = None, 
        encoding: None | str = None, 
        errors: None | str = None, 
        newline: None | str = None, 
        start: int = 0, 
        seek_threshold: int = 1 << 20, 
        http_file_reader_cls: None | type[HTTPFileReader] = None, 
        pid: None | int = None, 
        refresh: None | bool = None, 
        *, 
        async_: Literal[False] = False, 
        **request_kwargs, 
    ) -> TextIOWrapper:
        ...
    @overload
    def open(
        self, 
        id_or_path: IDOrPathType, 
        /, 
        mode: Literal["rb", "br"] = "rb", 
        buffering: None | int = None, 
        encoding: None | str = None, 
        errors: None | str = None, 
        newline: None | str = None, 
        start: int = 0, 
        seek_threshold: int = 1 << 20, 
        http_file_reader_cls: None | type[AsyncHTTPFileReader] = None, 
        pid: None | int = None, 
        refresh: None | bool = None, 
        *, 
        async_: Literal[True], 
        **request_kwargs, 
    ) -> AsyncHTTPFileReader | AsyncBufferedReader:
        ...
    @overload
    def open(
        self, 
        id_or_path: IDOrPathType, 
        /, 
        mode: Literal["r", "rt", "tr"], 
        buffering: None | int = None, 
        encoding: None | str = None, 
        errors: None | str = None, 
        newline: None | str = None, 
        start: int = 0, 
        seek_threshold: int = 1 << 20, 
        http_file_reader_cls: None | type[AsyncHTTPFileReader] = None, 
        pid: None | int = None, 
        refresh: None | bool = None, 
        *, 
        async_: Literal[True], 
        **request_kwargs, 
    ) -> AsyncTextIOWrapper:
        ...
    def open(
        self, 
        id_or_path: IDOrPathType, 
        /, 
        mode: Literal["r", "rt", "tr", "rb", "br"] = "rb", 
        buffering: None | int = None, 
        encoding: None | str = None, 
        errors: None | str = None, 
        newline: None | str = None, 
        start: int = 0, 
        seek_threshold: int = 1 << 20, 
        http_file_reader_cls: None | type[HTTPFileReader] | type[AsyncHTTPFileReader] = None, 
        pid: None | int = None, 
        refresh: None | bool = None, 
        *, 
        async_: Literal[False, True] = False, 
        **request_kwargs, 
    ) -> HTTPFileReader | BufferedReader | TextIOWrapper | AsyncHTTPFileReader | AsyncBufferedReader | AsyncTextIOWrapper:
        """打开一个文件，仅用于读取
        """
        if mode not in ("r", "rt", "tr", "rb", "br"):
            throw(errno.EINVAL, f"invalid (or unsupported) mode: {mode!r}")
        def gen_step():
            url = yield self.get_url(
                id_or_path, 
                pid=pid, 
                refresh=refresh, 
                async_=async_, 
                **request_kwargs, 
            )
            file = yield self.client.open(
                url, 
                start=start, 
                seek_threshold=seek_threshold, 
                http_file_reader_cls=http_file_reader_cls, 
                **request_kwargs, 
            )
            return file.wrap(
                text_mode="b" not in mode, 
                buffering=buffering, 
                encoding=encoding, 
                errors=errors, 
                newline=newline, 
            )
        return run_gen_step(gen_step, async_)

    @overload
    def read(
        self, 
        id_or_path: IDOrPathType = "", 
        /, 
        start: None | int = None, 
        stop: None | int | Undefined = undefined, 
        pid: None | int = None, 
        refresh: None | bool = None, 
        *, 
        async_: Literal[False] = False, 
        **request_kwargs, 
    ) -> bytes:
        ...
    @overload
    def read(
        self, 
        id_or_path: IDOrPathType = "", 
        /, 
        start: None | int = None, 
        stop: None | int | Undefined = undefined, 
        pid: None | int = None, 
        refresh: None | bool = None, 
        *, 
        async_: Literal[True], 
        **request_kwargs, 
    ) -> Coroutine[Any, Any, bytes]:
        ...
    def read(
        self, 
        id_or_path: IDOrPathType = "", 
        /, 
        start: None | int = None, 
        stop: None | int | Undefined = undefined, 
        pid: None | int = None, 
        refresh: None | bool = None, 
        *, 
        async_: Literal[False, True] = False, 
        **request_kwargs, 
    ) -> bytes | Coroutine[Any, Any, bytes]:
        """
        """
        def gen_step():
            nonlocal id_or_path, start, stop
            if is_undefined(stop):
                start, stop = 0, start
            elif start is None:
                start = 0
            if stop is None:
                if start < 0:
                    bytes_range = str(start)
                else:
                    bytes_range = f"{start}-"
            else:
                if start < 0 or stop < 0:
                    attr = id_or_path = yield self.get_attr(
                        id_or_path, 
                        pid=pid, 
                        refresh=refresh, 
                        ensure_file=True, 
                        async_=async_, 
                        **request_kwargs, 
                    )
                    size = cast(int, attr["size"])
                    if start < 0:
                        start += size
                        if start < 0:
                            start = 0
                    if stop < 0:
                        stop += size
                    elif stop > size:
                        stop = size
                if start >= stop:
                    return b""
                bytes_range = f"{start}-{stop-1}"
            return self.read_range(
                id_or_path, 
                bytes_range, 
                pid=pid, 
                refresh=refresh, 
                async_=async_, 
                **request_kwargs, 
            )
        return run_gen_step(gen_step, async_)

    @overload
    def read_range(
        self, 
        id_or_path: IDOrPathType = "", 
        /, 
        bytes_range: str = "0-", 
        pid: None | int = None, 
        refresh: None | bool = None, 
        *, 
        async_: Literal[False] = False, 
        **request_kwargs, 
    ) -> bytes:
        ...
    @overload
    def read_range(
        self, 
        id_or_path: IDOrPathType = "", 
        /, 
        bytes_range: str = "0-", 
        pid: None | int = None, 
        refresh: None | bool = None, 
        *, 
        async_: Literal[True], 
        **request_kwargs, 
    ) -> Coroutine[Any, Any, bytes]:
        ...
    def read_range(
        self, 
        id_or_path: IDOrPathType = "", 
        /, 
        bytes_range: str = "0-", 
        pid: None | int = None, 
        refresh: None | bool = None, 
        *, 
        async_: Literal[False, True] = False, 
        **request_kwargs, 
    ) -> bytes | Coroutine[Any, Any, bytes]:
        def gen_step():
            url = yield self.get_url(
                id_or_path, 
                pid=pid, 
                refresh=refresh, 
                async_=async_, 
                **request_kwargs, 
            )
            headers = request_kwargs["headers"] = dict(request_kwargs.get("headers") or ())
            if isinstance(url, P115URL):
                headers.update(url.get("headers") or ())
            headers["accept-encoding"] = "identity"
            headers["range"] = "bytes=" + bytes_range
            request_kwargs["parse"] = False
            return self.client.request(
                url, 
                async_=async_, 
                **request_kwargs, 
            )
        return run_gen_step(gen_step, async_)

    @overload
    def read_block(
        self, 
        id_or_path: IDOrPathType = "", 
        /, 
        start: int = 0, 
        size: None | int = None, 
        pid: None | int = None, 
        refresh: None | bool = None, 
        *, 
        async_: Literal[False] = False, 
        **request_kwargs, 
    ) -> bytes:
        ...
    @overload
    def read_block(
        self, 
        id_or_path: IDOrPathType = "", 
        /, 
        start: int = 0, 
        size: None | int = None, 
        pid: None | int = None, 
        refresh: None | bool = None, 
        *, 
        async_: Literal[True], 
        **request_kwargs, 
    ) -> Coroutine[Any, Any, bytes]:
        ...
    def read_block(
        self, 
        id_or_path: IDOrPathType = "", 
        /, 
        start: int = 0, 
        size: None | int = None, 
        pid: None | int = None, 
        refresh: None | bool = None, 
        *, 
        async_: Literal[False, True] = False, 
        **request_kwargs, 
    ) -> bytes | Coroutine[Any, Any, bytes]:
        """
        """
        def gen_step():
            if size is None:
                stop = None
            elif size <= 0:
                return b""
            else:
                stop = start + size
                if start < 0 and stop >= 0:
                    stop = None
            return (yield self.read(
                id_or_path, 
                start=start, 
                stop=stop, 
                pid=pid, 
                refresh=refresh, 
                async_=async_, # type: ignore
                **request_kwargs, 
            ))
        return run_gen_step(gen_step, async_)

    @overload
    def read_text(
        self, 
        id_or_path: IDOrPathType = "", 
        /, 
        encoding: None | str = None, 
        errors: None | str = None, 
        newline: None | str = None, 
        pid: None | int = None, 
        refresh: None | bool = None, 
        *, 
        async_: Literal[False] = False, 
        **request_kwargs, 
    ) -> str:
        ...
    @overload
    def read_text(
        self, 
        id_or_path: IDOrPathType = "", 
        /, 
        encoding: None | str = None, 
        errors: None | str = None, 
        newline: None | str = None, 
        pid: None | int = None, 
        refresh: None | bool = None, 
        *, 
        async_: Literal[True], 
        **request_kwargs, 
    ) -> Coroutine[Any, Any, str]:
        ...
    def read_text(
        self, 
        id_or_path: IDOrPathType = "", 
        /, 
        encoding: None | str = None, 
        errors: None | str = None, 
        newline: None | str = None, 
        pid: None | int = None, 
        refresh: None | bool = None, 
        *, 
        async_: Literal[False, True] = False, 
        **request_kwargs, 
    ) -> str | Coroutine[Any, Any, str]:
        def gen_step():
            file = yield self.open(
                id_or_path, 
                mode="r", 
                encoding=encoding, 
                errors=errors, 
                newline=newline, 
                pid=pid, 
                refresh=refresh, 
                async_=async_, # type: ignore
                **request_kwargs, 
            )
            return file.read()
        return run_gen_step(gen_step, async_)

    @overload
    def rglob(
        self, 
        /, 
        pattern: str = "", 
        dirname: IDOrPathType = "", 
        ignore_case: bool = False, 
        allow_escaped_slash: bool = True, 
        pid: None | int = None, 
        refresh: None | bool = None, 
        *, 
        async_: Literal[False] = False, 
        **request_kwargs, 
    ) -> Iterator[Mapping]:
        ...
    @overload
    def rglob(
        self, 
        /, 
        pattern: str = "", 
        dirname: IDOrPathType = "", 
        ignore_case: bool = False, 
        allow_escaped_slash: bool = True, 
        pid: None | int = None, 
        refresh: None | bool = None, 
        *, 
        async_: Literal[True], 
        **request_kwargs, 
    ) -> AsyncIterator[Mapping]:
        ...
    def rglob(
        self, 
        /, 
        pattern: str = "", 
        dirname: IDOrPathType = "", 
        ignore_case: bool = False, 
        allow_escaped_slash: bool = True, 
        pid: None | int = None, 
        refresh: None | bool = None, 
        *, 
        async_: Literal[False, True] = False, 
        **request_kwargs, 
    ) -> Iterator[Mapping] | AsyncIterator[Mapping]:
        if not pattern:
            return self.iter(
                dirname, 
                max_depth=-1, 
                pid=pid, 
                refresh=refresh, 
                async_=async_, 
                **request_kwargs, 
            )
        if pattern.startswith("/"):
            pattern = joinpath("/", "**", pattern.lstrip("/"))
        else:
            pattern = joinpath("**", pattern)
        return self.glob(
            pattern, 
            dirname=dirname, 
            ignore_case=ignore_case, 
            allow_escaped_slash=allow_escaped_slash, 
            pid=pid, 
            refresh=refresh, 
            async_=async_, 
            **request_kwargs, 
        )

    @overload
    def stat(
        self, 
        id_or_path: IDOrPathType = "", 
        /, 
        pid: None | int = None, 
        refresh: None | bool = None, 
        *, 
        async_: Literal[False] = False, 
        **request_kwargs, 
    ) -> stat_result:
        ...
    @overload
    def stat(
        self, 
        id_or_path: IDOrPathType = "", 
        /, 
        pid: None | int = None, 
        refresh: None | bool = None, 
        *, 
        async_: Literal[True], 
        **request_kwargs, 
    ) -> Coroutine[Any, Any, stat_result]:
        ...
    def stat(
        self, 
        id_or_path: IDOrPathType = "", 
        /, 
        pid: None | int = None, 
        refresh: None | bool = None, 
        *, 
        async_: Literal[False, True] = False, 
        **request_kwargs, 
    ) -> stat_result | Coroutine[Any, Any, stat_result]:
        "检查文件或目录的属性，就像 `os.stat`"
        def gen_step():
            attr = yield self.get_attr(
                id_or_path, 
                pid=pid, 
                refresh=refresh, 
                async_=async_, 
                **request_kwargs, 
            )
            return self.attr_to_stat(attr)
        return run_gen_step(gen_step, async_)

    @overload
    def walk(
        self, 
        top: IDOrPathType = "", 
        /, 
        topdown: None | bool = True, 
        min_depth: int = 1, 
        max_depth: int = -1, 
        onerror: bool | Callable[[OSError], bool] = True, 
        pid: None | int = None, 
        refresh: None | bool = None, 
        *, 
        async_: Literal[False] = False, 
        **request_kwargs, 
    ) -> Iterator[tuple[MutableMapping, list[MutableMapping], list[MutableMapping]]]:
        ...
    @overload
    def walk(
        self, 
        top: IDOrPathType = "", 
        /, 
        topdown: None | bool = True, 
        min_depth: int = 1, 
        max_depth: int = -1, 
        onerror: bool | Callable[[OSError], bool] = True, 
        pid: None | int = None, 
        refresh: None | bool = None, 
        *, 
        async_: Literal[True], 
        **request_kwargs, 
    ) -> AsyncIterator[tuple[MutableMapping, list[MutableMapping], list[MutableMapping]]]:
        ...
    def walk(
        self, 
        top: IDOrPathType = "", 
        /, 
        topdown: None | bool = True, 
        min_depth: int = 1, 
        max_depth: int = -1, 
        onerror: bool | Callable[[OSError], bool] = True, 
        pid: None | int = None, 
        refresh: None | bool = None, 
        *, 
        async_: Literal[False, True] = False, 
        **request_kwargs, 
    ) -> Iterator[tuple[MutableMapping, list[MutableMapping], list[MutableMapping]]] | AsyncIterator[tuple[MutableMapping, list[MutableMapping], list[MutableMapping]]]:
        def gen_step():
            try:
                attr = yield self.get_attr(
                    top, 
                    pid=pid, 
                    refresh=refresh, 
                    async_=async_, 
                    **request_kwargs, 
                )
            except OSError as e:
                if callable(onerror):
                    yield onerror(e)
                elif onerror:
                    raise
                return 
            yield YieldFrom(walk_generic(
                attr, 
                iterdir=partial(self.readdir, refresh=refresh, async_=async_, **request_kwargs), 
                topdown=topdown, 
                min_depth=min_depth, 
                max_depth=max_depth, 
                isdir=itemgetter("is_dir"), 
                onerror=onerror, 
                async_=async_, 
            ))
            if attr["id"] == 0:
                self.full_loaded = True
        return run_gen_step_iter(gen_step, async_)

# TODO: 增加方法 id_to_path 和 path_to_id 以加快查询速度
# TODO: 尽量先用数据库查一下，再去做下一步（如果不确定是不是目录，先用数据库查一下，成功就ok，不行再另外搞）
# TODO: 有时还需要路径到 id 到映射，或者 id_to_dirnode 中 name 到 id 到映射
# TODO: 如果是 NO_INCREMENT，那么自动构建 id 和 path 之间的映射，否则只构建 pid_to_names 的映射
# TODO: id_to_dirnode 在并发写入时，会有 database is locked 的问题
