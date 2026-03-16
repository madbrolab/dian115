#!/usr/bin/env python3
# encoding: utf-8

__author__ = "ChenyangGao <https://chenyanggao.github.io>"
__all__ = [
    "DirNode", "P115UID", "P115Cookies", "P115DictAttrLikeMixin", 
    "P115DictAttrLike", "P115ID", "P115StrID", "P115URL", 
]

from datetime import datetime, timedelta
from functools import cached_property
from http.cookiejar import CookieJar, Cookie
from http.cookies import BaseCookie, Morsel
from re import compile as re_compile
from time import time
from types import MappingProxyType
from typing import Any, Final, NamedTuple, Self

from cookietools import cookies_to_dict, cookies_to_str
from integer_tool import try_parse_int
from undefined import undefined

from .const import SSOENT_TO_APP


CRE_UID_FORMAT_match: Final = re_compile("(?P<user_id>[1-9][0-9]*)_(?P<login_ssoent>[A-Z][1-9][0-9]*)_(?P<login_timestamp>[1-9][0-9]{9,})").fullmatch
CRE_CID_FORMAT_match: Final = re_compile("[0-9a-f]{32}").fullmatch
CRE_SEID_FORMAT_match: Final = re_compile("[0-9a-f]{120}").fullmatch


class DirNode(NamedTuple):
    """用来保存某个 id 对应的 name 和 parent_id 的元组
    """
    name: str
    parent_id: int


class P115UID(str):

    def __init__(self, /, *a, **k):
        if m := CRE_UID_FORMAT_match(self):
            self.__dict__.update((k, try_parse_int(v)) for k, v in m.groupdict().items())

    def __repr__(self, /) -> str:
        cls = type(self)
        return f"{cls.__module__}.{cls.__qualname__}({super().__repr__()})"

    @cached_property
    def user_id(self, /) -> int:
        return 0

    @cached_property
    def login_ssoent(self, /) -> str:
        return ""

    @cached_property
    def login_timestamp(self, /) -> int:
        return 0


class P115Cookies(str):
    """cookies 的封装
    """
    __last_new_instance__ = None

    def __new__(cls, cookies, /):
        def predicate(_, val, /):
            domain: None | str = None
            if isinstance(val, Cookie):
                domain = val.domain
            elif isinstance(val, Morsel):
                domain = val["domain"]
            return not domain or domain == "115.com" or domain.endswith(".115.com")
        cookies = cookies_to_str(cookies, predicate)
        if cookies == cls.__last_new_instance__:
            return cls.__last_new_instance__
        else:
            inst = cls.__last_new_instance__ = super().__new__(cls, cookies)
            return inst

    def __deepcopy__(self, /, memo) -> Self:
        return self

    def __getattr__(self, attr: str, /):
        try:
            return self.mapping[attr]
        except KeyError as e:
            raise AttributeError(attr) from e

    def __getitem__(self, key, /): # type: ignore
        if isinstance(key, str):
            return self.mapping[key]
        return super().__getitem__(key)

    def __repr__(self, /) -> str:
        cls = type(self)
        return f"{cls.__module__}.{cls.__qualname__}({super().__repr__()})"

    def __setattr__(self, attr, value, /):
        raise TypeError("can't set attribute")

    @cached_property
    def mapping(self, /) -> MappingProxyType:
        return MappingProxyType(cookies_to_dict(self))

    @cached_property
    def uid(self, /) -> P115UID:
        "UID 字段"
        return P115UID(self.mapping.get("UID") or "")

    @cached_property
    def cid(self, /) -> str:
        "CID 字段"
        return self.mapping.get("CID") or ""

    @cached_property
    def kid(self, /) -> str:
        "KID 字段"
        return self.mapping.get("KID") or ""

    @cached_property
    def seid(self, /) -> str:
        "SEID 字段"
        return self.mapping.get("SEID") or ""

    @property
    def user_id(self, /) -> int:
        "用户 ID"
        return self.uid.user_id

    @property
    def login_ssoent(self, /) -> str:
        "登录设备标识"
        return self.uid.login_ssoent

    ssoent = login_ssoent

    @cached_property
    def login_app(self, /) -> None | str:
        "登录设备名"
        return SSOENT_TO_APP.get(self.login_ssoent)

    @property
    def app(self, /) -> None | str:
        "登录设备名"
        return self.login_app

    @property
    def login_timestamp(self, /) -> int:
        "登录时间戳"
        return self.uid.login_timestamp

    timestamp = login_timestamp

    @cached_property
    def datetime(self, /) -> datetime:
        "登录时间"
        return datetime.fromtimestamp(self.login_timestamp)

    @property
    def time_elapsed(self, /) -> float:
        "从登录到现在过了多少时间，单位：秒"
        return time() - self.login_timestamp

    @property
    def time_delta(self, /) -> timedelta:
        "从登录到现在过了多少时间"
        return datetime.now() - self.datetime

    @cached_property
    def is_well_formed(self, /) -> bool:
        "是否格式良好，即需要的字段都具备而且都符合格式"
        return (
            CRE_UID_FORMAT_match(self.uid) and 
            CRE_CID_FORMAT_match(self.cid) and 
            CRE_SEID_FORMAT_match(self.seid)
        ) is not None

    @cached_property
    def cookies(self, /) -> str:
        """115 登录的 cookies，包含 UID、CID、KID 和 SEID 这 4 个字段
        """
        cookies = f"UID={self.uid}; CID={self.cid}; SEID={self.seid}"
        if "KID" in self.mapping:
            cookies += f"; KID={self.mapping['KID']}"
        return cookies

    @classmethod
    def from_dict(cls, cookies: dict[str, str], /) -> Self:
        return cls("; ".join(f"{key}={val}" for key, val in cookies.items()))

    @classmethod
    def from_cookiejar(cls, cookiejar: CookieJar, /) -> Self:
        return cls("; ".join(
            f"{cookie.name}={cookie.value}" 
            for cookie in cookiejar 
            if not (domain := cookie.domain) or domain == "115.com" or domain.endswith(".115.com")
        ))

    @classmethod
    def from_simple_cookie(cls, cookies: BaseCookie, /) -> Self:
        return cls("; ".join(
            f"{name}={cookie.value}" 
            for name, cookie in cookies.items() 
            if not (domain := cookie["domain"]) or domain == "115.com" or domain.endswith(".115.com")
        ))


class P115DictAttrLikeMixin:

    def __getattr__(self, attr: str, /):
        try:
            return self.__dict__[attr]
        except KeyError as e:
            raise AttributeError(attr) from e

    def __delitem__(self, key: str, /):
        del self.__dict__[key]

    def __getitem__(self, key, /):
        try:
            if isinstance(key, str):
                return self.__dict__[key]
        except KeyError:
            return super().__getitem__(key) # type: ignore

    def __setitem__(self, key: str, val, /):
        self.__dict__[key] = val

    def __repr__(self, /) -> str:
        cls = type(self)
        if (module := cls.__module__) not in ("__main__", "builtins"):
            name = cls.__qualname__
        else:
            name = f"{module}.{cls.__qualname__}"
        return f"{name}({super().__repr__()}, {self.__dict__!r})"

    @property
    def mapping(self, /) -> dict[str, Any]:
        return self.__dict__

    def get(self, key, /, default=None):
        return self.__dict__.get(key, default)

    def items(self, /):
        return self.__dict__.items()

    def keys(self, /):
        return self.__dict__.keys()

    def values(self, /):
        return self.__dict__.values()


class P115DictAttrLike(P115DictAttrLikeMixin):

    def __new__(cls, val: Any = undefined, /, *args, **kwds):
        if val is undefined:
            return super().__new__(cls)
        else:
            return super().__new__(cls, val) # type: ignore

    def __init__(self, val: Any = undefined, /, *args, **kwds):
        self.__dict__.update(*args, **kwds)

    @classmethod
    def of(cls, val: Any = undefined, /, ns: None | dict = None) -> Self:
        if val is undefined:
            self = cls.__new__(cls)
        else:
            self = cls.__new__(cls, val)
        if ns is not None:
            self.__dict__ = ns
        return self

    @classmethod
    def derive(cls, base: type, name: str = "", /, **ns) -> type[Self]:
        return type(name, (cls, base), ns)

    @classmethod
    def derive_backend(cls, base: type, name: str = "", /, **ns) -> type[Self]:
        return type(name, (base, cls), ns)


class P115ID(P115DictAttrLike, int):
    """整数 id 的封装
    """
    def __str__(self, /) -> str:
        return int.__repr__(self)


class P115StrID(P115DictAttrLike, str):
    """字符串 id 的封装
    """


class P115URL(P115DictAttrLike, str):
    """下载链接的封装
    """
    def geturl(self, /) -> str:
        return str(self)

    url = property(geturl)

