#!/usr/bin/env python3
# encoding: utf-8

from __future__ import annotations

__all__ = ["check_response", "ClientRequestMixin", "P115OpenClient", "P115Client"]

from asyncio import Lock as AsyncLock
from base64 import b64encode
from collections import UserString
from collections.abc import (
    AsyncIterable, Awaitable, Buffer, Callable, Coroutine, 
    Iterable, Iterator, Mapping, MutableMapping, Sequence, 
)
from datetime import date, datetime, timedelta
from ensure import ensure_bytes
from functools import cached_property, partial
from hashlib import md5, sha1
from http.cookiejar import Cookie, CookieJar
from http.cookies import Morsel, BaseCookie
from inspect import isawaitable, iscoroutinefunction, signature, Signature
from itertools import count
from operator import itemgetter
from os import fsdecode, isatty, PathLike
from pathlib import Path, PurePath
from platform import system
from re import compile as re_compile, Match, MULTILINE
from string import digits
from sys import _getframe
from threading import Lock
from time import time
from typing import cast, overload, Any, Final, Literal, Self
from urllib.parse import parse_qsl, quote, unquote, urlencode, urlsplit
from uuid import uuid4
from warnings import warn

from argtools import argcount
from asynctools import ensure_async
from cookietools import cookies_to_dict, update_cookies
from dicttools import get_first, dict_update, dict_key_to_lower_merge, iter_items, KeyLowerDict
from errno2 import errno
from filewrap import SupportsRead
from http_request import complete_url as make_url, SupportsGeturl
from http_response import get_status_code
from httpfile import HTTPFileReader, AsyncHTTPFileReader
from iterutils import run_gen_step
from orjson import dumps, loads
from p115cipher import (
    rsa_encrypt, rsa_decrypt, ecdh_aes_encrypt, ecdh_aes_decrypt, 
    ecdh_encode_token, make_upload_payload, 
)
from p115oss import upload
from p115pickcode import get_stable_point, to_id, to_pickcode
from property import locked_cacheproperty
from startfile import startfile, startfile_async
from temporary import temp_globals
from yarl import URL

from .const import (
    _CACHE_DIR, CLIENT_API_METHODS_MAP, CLIENT_METHOD_API_MAP, 
    SSOENT_TO_APP, 
)
from .exception import (
    throw, P115OSError, P115Warning, P115AccessTokenError, 
    P115AuthenticationError, P115LoginError, P115OpenAppAuthLimitExceeded, 
    P115OperationalError, 
)
from .type import P115Cookies, P115URL
from .util import complete_url, share_extract_payload


CRE_SET_COOKIE: Final = re_compile(r"[0-9a-f]{32}=[0-9a-f]{32}.*")
CRE_COOKIES_UID_search: Final = re_compile(r"(?<=\bUID=)[^\s;]+").search
CRE_AREA_DATA_search: Final = re_compile(r"(?<=n=)\{[\s\S]+?\}(?=;)").search
# 替换表，用于半角转全角，包括了 Windows 中不允许出现在文件名中的字符
match system():
    case "Windows":
        NAME_TANSTAB_FULLWIDH = {c: chr(c+65248) for c in b"\\/:*?|><"}
    case "Darwin":
        NAME_TANSTAB_FULLWIDH = {ord("/"): ":", ord(":"): "："}
    case _:
        NAME_TANSTAB_FULLWIDH = {ord("/"): "／"}

_default_k_ec = {"k_ec": ecdh_encode_token(0).decode()}
_default_code_verifier = "0" * 64
_default_code_challenge = b64encode(md5(b"0" * 64).digest()).decode()
_default_code_challenge_method = "md5"


def expand_payload(
    payload: dict[str, Any] | Iterable[tuple[str, Any]], 
    prefix: str = "", 
    enum_seq: bool | int = False, 
    seq_types: type | tuple[type, ...] = (tuple, list), 
    map_types: type | tuple[type, ...] = dict, 
) -> Iterable[tuple[str, Any]]:
    if prefix:
        prefix = f"{prefix}["
    for k, v in iter_items(payload):
        if prefix and not k.startswith(prefix):
            k = f"{prefix}{k}]"
        if isinstance(v, seq_types):
            if isinstance(enum_seq, bool):
                if enum_seq:
                    enum_seq = 0
                else:
                    for v2 in v:
                        yield from expand_payload(v2, f"{k}[]")
                    continue
                for i, v2 in enumerate(v, enum_seq):
                    yield from expand_payload(v2, f"{k}[{i}]")
        elif isinstance(v, map_types):
            for k2, v2 in iter_items(v):
                yield from expand_payload(v2, f"{k}[{k2}]")
        else:
            yield k, v


def json_loads(content: Buffer, /):
    try:
        if isinstance(content, (bytes, bytearray, memoryview)):
            return loads(content)
        else:
            return loads(memoryview(content))
    except Exception:
        throw(errno.ENODATA, bytes(content))


def default_parse(_, content: Buffer, /):
    if not isinstance(content, (bytes, bytearray, memoryview)):
        content = memoryview(content)
    if content and content[0] + content[-1] not in (b"{}", b"[]", b'""'):
        try:
            content = ecdh_aes_decrypt(content, decompress=True)
        except Exception:
            pass
    return json_loads(memoryview(content))


def md5_secret_password(password: None | int | str = "670b14728ad9902aecba32e22fa4f6bd", /) -> str:
    if not password:
        return "670b14728ad9902aecba32e22fa4f6bd"
    if isinstance(password, str) and len(password) == 32:
        return password
    return md5(f"{password:>06}".encode("ascii")).hexdigest()


def get_request(
    async_: None | bool = None, 
    request_kwargs: None | dict = None, 
    self = None, 
) -> Callable:
    def iter_locals(depth_start: int = 1, /) -> Iterator[dict]:
        try:
            frame = _getframe(depth_start)
        except ValueError:
            return
        while frame:
            yield frame.f_locals
    def has_keyword_async(request: Callable | Signature, /) -> bool:
        if callable(request):
            try:
                request = signature(request)
            except (ValueError, TypeError):
                return False
        params = request.parameters
        param = params.get("async_")
        return bool(param and param.kind in (param.POSITIONAL_OR_KEYWORD, param.KEYWORD_ONLY))
    if request_kwargs is None:
        for f_locals in iter_locals(2):
            if "request_kwargs" in f_locals:
                request_kwargs = f_locals["request_kwargs"]
                break
    if async_ is None and request_kwargs:
        async_ = request_kwargs.get("async_")
    if async_ is None:
        for f_locals in iter_locals(2):
            if "async_" in f_locals:
                async_ = f_locals["async_"]
                break
    request: None | Callable = None
    if isinstance(self, ClientRequestMixin):
        request = self.request
        if async_ is not None:
            if request_kwargs is None:
                request = partial(request, async_=async_)
            else:
                request_kwargs["async_"] = async_
    else:
        if request_kwargs:
            request = request_kwargs.pop("request", None)
        if request is None:
            from httpcore_request import request
            request = cast(Callable, request)
        if async_ is not None and not iscoroutinefunction(request) and has_keyword_async(request):
            if request_kwargs is None:
                request = partial(request, async_=async_)
            else:
                request_kwargs["async_"] = async_
        if request_kwargs is None:
            request = partial(request, parse=default_parse)
        else:
            request_kwargs.setdefault("parse", default_parse)
    return request


def default_check_for_relogin(e: BaseException, /) -> bool:
    return get_status_code(e) == 405


def parse_upload_init_response(_, content: bytes, /) -> dict:
    data = ecdh_aes_decrypt(content, decompress=True)
    if not isinstance(data, (bytes, bytearray, memoryview)):
        data = memoryview(data)
    return json_loads(data)


@overload
def check_response(resp: dict, /) -> dict:
    ...
@overload
def check_response(resp: Awaitable[dict], /) -> Coroutine[Any, Any, dict]:
    ...
def check_response(resp: dict | Awaitable[dict], /) -> dict | Coroutine[Any, Any, dict]:
    """检测 115 的某个接口的响应，如果成功则直接返回，否则根据具体情况抛出一个异常，基本上是 OSError 的实例
    """
    def check(resp, /) -> dict:
        if not isinstance(resp, dict):
            raise P115OSError(errno.EIO, resp)
        if resp.get("state", True):
            return resp
        if code := get_first(resp, "errno", "errNo", "errcode", "errCode", "code", "msg_code", default=None):
            resp.setdefault("errno", code)
            if "error" not in resp:
                resp.setdefault("error", get_first(resp, "msg", "error_msg", "message", default=None))
            match code:
                # {"state": false, "errno": 99, "error": "请重新登录"}
                case 99:
                    raise P115LoginError(errno.EAUTH, resp)
                # {"state": false, "errno": 911, "error": "请验证账号"}
                case 911:
                    throw(errno.EAUTH, resp)
                # {"state": false, "errno": 1001, "error": "参数错误"}
                case 1001:
                    throw(errno.EINVAL, resp)
                # {"state": false, "errno": 10004, "error": "错误的链接"}
                case 10004:
                    throw(errno.EINVAL, resp)
                # {"state": false, "errno": 10014, "error": "云端目录不存在，请恢复后重新上传"}
                case 10014:
                    throw(errno.ENOENT, resp)
                # {"state": false, "errno": 20001, "error": "目录名称不能为空"}
                case 20001:
                    throw(errno.EINVAL, resp)
                # {"state": false, "errno": 20004, "error": "该目录名称已存在。"}
                case 20004:
                    throw(errno.EEXIST, resp)
                # {"state": false, "errno": 20009, "error": "父目录不存在。"}
                case 20009:
                    throw(errno.ENOENT, resp)
                # {"state": false, "errno": 20018, "error": "文件不存在或已删除。"}
                # {"state": false, "errno": 50015, "error": "文件不存在或已删除。"}
                # {"state": false, "errno": 90008, "error": "文件（夹）不存在或已经删除。"}
                # {"state": false, "errno": 430004, "error": "文件（夹）不存在或已删除。"}
                case 20018 | 50015 | 90008 | 430004:
                    throw(errno.ENOENT, resp)
                # {"state": false, "errno": 20020, "error": "后缀名不正确，请重新输入"}
                # {"state": false, "errno": 20021, "error": "后缀名不正确，请重新输入"}
                case 20020 | 20021:
                    throw(errno.EINVAL, resp)
                # {"state": false, "errno": 31001, "error": "所预览的文件不存在。"}
                case 31001:
                    throw(errno.ENOENT, resp)
                # {"state": false, "errno": 31004, "error": "文档未上传完整，请上传完成后再进行查看。"}
                case 31004:
                    throw(errno.ENOENT, resp)
                # {"state": false, "errno": 50003, "error": "很抱歉，该文件提取码不存在。"}
                case 50003:
                    throw(errno.ENOENT, resp)
                # {"state": false, "errno": 50038, "error": "下载失败，含违规内容"}
                case 50038:
                    throw(errno.EACCES, resp)
                # {"state": false, "errno": 91002, "error": "不能将文件复制到自身或其子目录下。"}
                case 91002:
                    throw(errno.ENOTSUP, resp)
                # {"state": false, "errno": 91004, "error": "操作的文件(夹)数量超过5万个"}
                case 91004:
                    throw(errno.ENOTSUP, resp)
                # {"state": false, "errno": 91005, "error": "空间不足，复制失败。"}
                case 91005:
                    throw(errno.ENOSPC, resp)
                # {"state": false, "errno": 231011, "error": "文件已删除，请勿重复操作"}
                case 231011:
                    throw(errno.ENOENT, resp)
                # {"state": false, "errno": 300104, "error": "文件超过200MB，暂不支持播放"}
                case 300104:
                    throw(errno.EFBIG, resp)
                # {"state": false, "errno": 320001, "error": "很抱歉,安全密钥不正确"}
                case 320001:
                    throw(errno.EINVAL, resp)
                # {"state": false, "errno": 590075, "error": "操作太频繁，请稍候再试"}
                case 590075:
                    throw(errno.EBUSY, resp)
                # {"state": false, "errno": 800001, "error": "目录不存在。"}
                case 800001:
                    throw(errno.ENOENT, resp)
                # {"state": false, "errno": 980006, "error": "404 Not Found"}
                case 980006:
                    throw(errno.ENOSYS, resp)
                # {"state": false, "errno": 990001, "error": "登陆超时，请重新登陆。"}
                case 990001:
                    # NOTE: 可能就是被下线了
                    throw(errno.EAUTH, resp)
                # {"state": false, "errno": 990002, "error": "参数错误。"}
                case 990002:
                    throw(errno.EINVAL, resp)
                # {"state": false, "errno": 990003, "error": "操作失败。"}
                case 990003:
                    raise P115OperationalError(errno.EIO, resp)
                # {"state": false, "errno": 990005, "error": "你的账号有类似任务正在处理，请稍后再试！"}
                case 990005:
                    throw(errno.EBUSY, resp)
                # {"state": false, "errno": 990009, "error": "删除[...]操作尚未执行完成，请稍后再试！"}
                # {"state": false, "errno": 990009, "error": "还原[...]操作尚未执行完成，请稍后再试！"}
                # {"state": false, "errno": 990009, "error": "复制[...]操作尚未执行完成，请稍后再试！"}
                # {"state": false, "errno": 990019, "error": "移动[...]操作尚未执行完成，请稍后再试！"}
                case 990009 | 990019:
                    throw(errno.EBUSY, resp)
                # {"state": false, "errno": 990023, "error": "操作的文件(夹)数量超过5万个"}
                case 990023:
                    throw(errno.ENOTSUP, resp)
                # {"state": 0, "errno": 40100000, "error": "参数错误！"}
                # {"state": 0, "errno": 40100000, "error": "参数缺失"}
                case 40100000:
                    throw(errno.EINVAL, resp)
                # {"state": 0, "errno": 40101004, "error": "IP登录异常,请稍候再登录！"}
                case 40101004:
                    raise P115LoginError(errno.EAUTH, resp)
                # {"state": 0, "errno": 40101017, "error": "用户验证失败！"}
                case 40101017:
                    throw(errno.EAUTH, resp)
                # {"state": 0, "errno": 40101032, "error": "请重新登录"}
                case 40101032:
                    raise P115LoginError(errno.EAUTH, resp)
                #################################################################
                # Reference: https://www.yuque.com/115yun/open/rnq0cbz8tt7cu43i #
                #################################################################
                # {"state": 0, "errno": 40110000, "error": "请求异常需要重试"}
                case 40110000:
                    raise P115OperationalError(errno.EAGAIN, resp)
                # {"state": 0, "errno": 40140100, "error": "client_id 错误"}
                case 40140100:
                    throw(errno.EINVAL, resp)
                # {"state": 0, "errno": 40140101, "error": "code_challenge 必填"}
                case 40140101:
                    throw(errno.EINVAL, resp)
                # {"state": 0, "errno": 40140102, "error": "code_challenge_method 必须是 sha256、sha1、md5 之一"}
                case 40140102:
                    throw(errno.EINVAL, resp)
                # {"state": 0, "errno": 40140103, "error": "sign 必填"}
                case 40140103:
                    throw(errno.EINVAL, resp)
                # {"state": 0, "errno": 40140104, "error": "sign 签名失败"}
                case 40140104:
                    throw(errno.EINVAL, resp)
                # {"state": 0, "errno": 40140105, "error": "生成二维码失败"}
                case 40140105:
                    raise P115OperationalError(errno.EIO, resp)
                # {"state": 0, "errno": 40140106, "error": "APP ID 无效"}
                case 40140106:
                    throw(errno.EINVAL, resp)
                # {"state": 0, "errno": 40140107, "error": "应用不存在"}
                case 40140107:
                    throw(errno.EINVAL, resp)
                # {"state": 0, "errno": 40140108, "error": "应用未审核通过"}
                case 40140108:
                    throw(errno.EINVAL, resp)
                # {"state": 0, "errno": 40140109, "error": "应用已被停用"}
                case 40140109:
                    throw(errno.EINVAL, resp)
                # {"state": 0, "errno": 40140110, "error": "应用已过期"}
                case 40140110:
                    throw(errno.EINVAL, resp)
                # {"state": 0, "errno": 40140111, "error": "APP Secret 错误"}
                case 40140111:
                    throw(errno.EINVAL, resp)
                # {"state": 0, "errno": 40140112, "error": "code_verifier 长度要求43~128位"}
                case 40140112:
                    throw(errno.EINVAL, resp)
                # {"state": 0, "errno": 40140113, "error": "code_verifier 验证失败"}
                case 40140113:
                    throw(errno.EINVAL, resp)
                # {"state": 0, "errno": 40140114, "error": "refresh_token 格式错误（防篡改）"}
                case 40140114:
                    throw(errno.EINVAL, resp)
                # {"state": 0, "errno": 40140115, "error": "refresh_token 签名校验失败（防篡改）"}
                case 40140115:
                    throw(errno.EINVAL, resp)
                # {"state": 0, "errno": 40140116, "error": "refresh_token 无效（已解除授权）"}
                case 40140116:
                    raise P115OperationalError(errno.EIO, resp)
                # {"state": 0, "errno": 40140117, "error": "access_token 刷新太频繁"}
                case 40140117:
                    throw(errno.EBUSY, resp)
                # {"state": 0, "errno": 40140118, "error": "开发者认证已过期"}
                case 40140118:
                    throw(errno.EINVAL, resp)
                # {"state": 0, "errno": 40140119, "error": "refresh_token 已过期"}
                case 40140119:
                    throw(errno.EINVAL, resp)
                # {"state": 0, "errno": 40140120, "error": "refresh_token 检验失败（防篡改）"}
                case 40140120:
                    throw(errno.EINVAL, resp)
                # {"state": 0, "errno": 40140121, "error": "access_token 刷新失败"}
                case 40140121:
                    throw(errno.EINVAL, resp)
                # {"state": 0, "errno": 40140122, "error": "超出授权应用个数上限"}
                case 40140122:
                    raise P115OpenAppAuthLimitExceeded(errno.EDQUOT, resp)
                # {"state": 0, "errno": 40140123, "error": "access_token 格式错误（防篡改）"}
                case 40140123:
                    raise P115AccessTokenError(errno.EINVAL, resp)
                # {"state": 0, "errno": 40140124, "error": "access_token 签名校验失败（防篡改）"}
                case 40140124:
                    raise P115AccessTokenError(errno.EINVAL, resp)
                # {"state": 0, "errno": 40140125, "error": "access_token 无效（已过期或者已解除授权）"}
                case 40140125:
                    raise P115AccessTokenError(errno.EINVAL, resp)
                # {"state": 0, "errno": 40140126, "error": "access_token 校验失败（防篡改）"}
                case 40140126:
                    raise P115AccessTokenError(errno.EINVAL, resp)
                # {"state": 0, "errno": 40140127, "error": "response_type 错误"}
                case 40140127:
                    throw(errno.EINVAL, resp)
                # {"state": 0, "errno": 40140128, "error": "redirect_uri 缺少协议"}
                case 40140128:
                    throw(errno.EINVAL, resp)
                # {"state": 0, "errno": 40140129, "error": "redirect_uri 缺少域名"}
                case 40140129:
                    throw(errno.EINVAL, resp)
                # {"state": 0, "errno": 40140130, "error": "没有配置重定向域名"}
                case 40140130:
                    throw(errno.EINVAL, resp)
                # {"state": 0, "errno": 40140131, "error": "redirect_uri 非法域名"}
                case 40140131:
                    throw(errno.EINVAL, resp)
                # {"state": 0, "errno": 40140132, "error": "grant_type 错误"}
                case 40140132:
                    throw(errno.EINVAL, resp)
                # {"state": 0, "errno": 40140133, "error": "client_secret 验证失败"}
                case 40140133:
                    throw(errno.EINVAL, resp)
                # {"state": 0, "errno": 40140134, "error": "授权码 code 验证失败"}
                case 40140134:
                    throw(errno.EINVAL, resp)
                # {"state": 0, "errno": 40140135, "error": "client_id 验证失败"}
                case 40140135:
                    throw(errno.EINVAL, resp)
                # {"state": 0, "errno": 40140136, "error": "redirect_uri 验证失败（防MITM）"}
                case 40140136:
                    throw(errno.EINVAL, resp)
                ##################################################
                case 50028:
                    throw(errno.EFBIG, resp)
                case 70004:
                    throw(errno.EISDIR, resp)
                case 70005 | 70008:
                    throw(errno.ENOENT, resp)
        elif error := resp.get("error"):
            if "文件不存在" in error or "目录不存在" in error:
                throw(errno.ENOENT, resp)
            elif "目录名称已存在" in error:
                throw(errno.EEXIST, resp)
            elif error == "更新的数据为空":
                throw(errno.EINVAL, resp)
        throw(errno.EIO, resp)
    if isinstance(resp, dict):
        return check(resp)
    elif isawaitable(resp):
        async def check_await() -> dict:
            return check(await resp)
        return check_await()
    throw(errno.EIO, resp)


class ClientRequestMixin:
    """混入类，部署了 HTTP 请求相关的属性和方法，并集成了一部分公共的静态方法和类方法
    """
    cookies_path: None | PurePath = None

    def _read_cookies(
        self, 
        /, 
        encoding: str = "latin-1", 
    ) -> P115Cookies:
        if cookies_path := self.__dict__.get("cookies_path"):
            try:
                with cookies_path.open("rb") as f:
                    cookies = str(f.read(), encoding)
                if cookies:
                    update_cookies(self.cookies, cookies_to_dict(cookies), domain=".115.com")
            except OSError:
                pass
        return self.cookies_str

    def _write_cookies(
        self, 
        cookies: None | str = None, 
        /, 
        encoding: str = "latin-1", 
    ):
        if cookies_path := self.__dict__.get("cookies_path"):
            if cookies is None:
                cookies = self.cookies_str
            cookies_bytes = bytes(cookies, encoding)
            with cookies_path.open("wb") as f:
                f.write(cookies_bytes)

    @property
    def cookies(self, /) -> BaseCookie:
        """请求所用的 Cookies 对象（同步和异步共用）
        """
        try:
            return self.__dict__["cookies"]
        except KeyError:
            cookies = self.__dict__["cookies"] = BaseCookie()
            return cookies

    @cookies.setter
    def cookies(
        self, 
        cookies: None | str | CookieJar | BaseCookie | Mapping[str, Any] | Iterable[Any] = None, 
        /, 
    ):
        """更新 cookies
        """
        cookie_store = self.cookies
        if cookies is None:
            cookie_store.clear()
            self._write_cookies("")
        elif isinstance(cookies, str):
            cookies = cookies_to_dict(cookies.strip().rstrip(";"))
        if not cookies:
            return
        cookies_old = self.cookies_str
        update_cookies(cookie_store, cookies, domain=".115.com")
        cookies_new = self.cookies_str
        try:
            if self.user_id != cookies_new.user_id:
                seen: set[str] = set()
                pop_key = self.__dict__.pop
                for cls in type(self).mro():
                    if not isinstance(cls, ClientRequestMixin):
                        seen.update(cls.__dict__)
                        continue
                    for key, val in cls.__dict__.items():
                        if key in seen:
                            continue
                        seen.add(key)
                        if isinstance(val, (cached_property, locked_cacheproperty)):
                            pop_key(key, None)
        except KeyError:
            pass
        if cookies_new != cookies_old:
            self._write_cookies(cookies_new)

    @property
    def cookies_str(self, /) -> P115Cookies:
        """所有 .115.com 域下的 cookie 值
        """
        return P115Cookies.from_simple_cookie(self.cookies)

    @locked_cacheproperty
    def headers(self, /) -> KeyLowerDict[str, str]:
        """请求头（同步和异步共用）
        """
        return KeyLowerDict[str, str]({
            "accept": "*/*", 
            "accept-encoding": "gzip, deflate, br, zstd", 
            "connection": "keep-alive", 
            "user-agent": "Mozilla/5.0", 
        })

    @locked_cacheproperty
    def user_id(self, /) -> int:
        if user_id := self.cookies_str.user_id:
            return user_id
        elif "authorization" in self.headers:
            resp = check_response(P115OpenClient.user_info_open(cast(P115OpenClient, self)))
            return int(resp["data"]["user_id"])
        else:
            return 0

    def request(
        self, 
        /, 
        url: str, 
        method: str = "GET", 
        payload: Any = None, 
        *, 
        ecdh_encrypt: bool = False, 
        request: None | Callable = None, 
        async_: Literal[False, True] = False, 
        **request_kwargs, 
    ):
        """执行网络请求

        :param url: HTTP 的请求链接
        :param method: HTTP 的请求方法
        :param payload: HTTP 的请求载体（如果 `method` 是 "POST"，则作为请求体，否则作为查询参数）
        :param ecdh_encrypt: 是否使用 ecdh 算法对请求体进行加密（返回值需要解密）
        :param request: HTTP 请求调用，如果为 None，则用默认设置
            如果传入调用，则必须至少能接受以下几个关键词参数：

            - url:     HTTP 的请求链接
            - method:  HTTP 的请求方法
            - params:  HTTP 的请求链接附加的查询参数
            - data:    HTTP 的请求体
            - json:    JSON 数据（往往未被序列化）作为请求体
            - files:   要用 multipart 上传的若干文件
            - headers: HTTP 的请求头
            - follow_redirects: 是否跟进重定向，默认值为 True
            - raise_for_status: 是否对响应码 >= 400 时抛出异常
            - cookies: 至少能接受 ``http.cookiejar.CookieJar`` 和 ``http.cookies.BaseCookie``，会因响应头的 "set-cookie" 而更新
            - parse:   解析 HTTP 响应的方法，默认会构建一个 Callable，会把响应的字节数据视为 JSON 进行反序列化解析

                - 如果为 None，则直接把响应对象返回
                - 如果为 ...(Ellipsis)，则把响应对象关闭后将其返回
                - 如果为 True，则根据响应头来确定把响应得到的字节数据解析成何种格式（反序列化），请求也会被自动关闭
                - 如果为 False，则直接返回响应得到的字节数据，请求也会被自动关闭
                - 如果为 Callable，则使用此调用来解析数据，接受 1-2 个位置参数，并把解析结果返回给 `request` 的调用者，请求也会被自动关闭
                    - 如果只接受 1 个位置参数，则把响应对象传给它
                    - 如果能接受 2 个位置参数，则把响应对象和响应得到的字节数据（响应体）传给它

        :param async_: 是否异步
        :param request_kwargs: 其余请求参数

        :return: 直接返回 `request` 执行请求后的返回值

        .. note:: 
            `request` 可以由不同的请求库来提供，下面是封装了一些模块

            1. `httpcore_request <https://pypi.org/project/httpcore_request/>`_，由 `httpcore <https://pypi.org/project/httpcore/>`_ 封装，支持同步和异步请求

                .. code:: python

                    from httpcore_request import request

            2. `httpx_request <https://pypi.org/project/httpx_request/>`_，由 `httpx <https://pypi.org/project/httpx/>`_ 封装，支持同步和异步请求

                .. code:: python

                    from httpx_request import request

            3. `http_client_request <https://pypi.org/project/http_client_request/>`_，由 `http.client <https://docs.python.org/3/library/http.client.html>`_ 封装，支持同步请求

                .. code:: python

                    from http_client_request import request

            4. `python-urlopen <https://pypi.org/project/python-urlopen/>`_，由 `urllib.request.urlopen <https://docs.python.org/3/library/urllib.request.html#urllib.request.urlopen>`_ 封装，支持同步请求

                .. code:: python

                    from urlopen import request

            5. `urllib3_request <https://pypi.org/project/urllib3_request/>`_，由 `urllib3 <https://pypi.org/project/urllib3/>`_ 封装，支持同步请求

                .. code:: python

                    from urllib3_request import request

            6. `requests_request <https://pypi.org/project/requests_request/>`_，由 `requests <https://pypi.org/project/requests/>`_ 封装，支持同步请求

                .. code:: python

                    from requests_request import request

            7. `aiohttp_client_request <https://pypi.org/project/aiohttp_client_request/>`_，由 `aiohttp <https://pypi.org/project/aiohttp/>`_ 封装，支持异步请求

                .. code:: python

                    from aiohttp_client_request import request

            8. `blacksheep_client_request <https://pypi.org/project/blacksheep_client_request/>`_，由 `blacksheep <https://pypi.org/project/blacksheep/>`_ 封装，支持异步请求

                .. code:: python

                    from blacksheep_client_request import request

            9. `asks_request <https://pypi.org/project/asks_request/>`_，由 `asks <https://pypi.org/project/asks/>`_ 封装，支持异步请求

                .. code:: python

                    from asks_request import request

            10. `pycurl_request <https://pypi.org/project/pycurl_request/>`_，由 `pycurl <https://pypi.org/project/pycurl/>`_ 封装，支持同步请求

                .. code:: python

                    from pycurl_request import request

            11. `curl_cffi_request <https://pypi.org/project/curl_cffi_request/>`_，由 `curl_cffi <https://pypi.org/project/curl_cffi/>`_ 封装，支持同步和异步请求

                .. code:: python

                    from curl_cffi_request import request

            12. `aiosonic_request <https://pypi.org/project/aiosonic_request/>`_，由 `aiosonic <https://pypi.org/project/aiosonic/>`_ 封装，支持异步请求

                .. code:: python

                    from aiosonic_request import request

            13. `tornado_client_request <https://pypi.org/project/tornado_client_request/>`_，由 `tornado <https://www.tornadoweb.org/en/latest/httpclient.html>`_ 封装，支持异步请求

                .. code:: python

                    from tornado_client_request import request
        """
        if payload is not None:
            if method.upper() == "POST":
                request_kwargs.setdefault("data", payload)
            else:
                request_kwargs.setdefault("params", payload)
        request_kwargs["request"] = request
        request_kwargs.setdefault("cookies", self.cookies)
        request = get_request(async_, request_kwargs)
        headers = request_kwargs["headers"] = dict_update(
            self.headers.copy(), 
            request_kwargs.get("headers") or (), 
        )
        if ecdh_encrypt and (data := request_kwargs.get("data")):
            url = make_url(url, params=_default_k_ec)
            if not isinstance(data, (Buffer, str, UserString)):
                data = urlencode(data)
            request_kwargs["data"] = ecdh_aes_encrypt(ensure_bytes(data) + b"&")
            headers["content-type"] = "application/x-www-form-urlencoded"
        return request(url=url, method=method, **request_kwargs)

    ########## Qrcode API ##########

    @overload
    def login_authorize_open(
        self: dict | ClientRequestMixin, 
        payload: None | dict = None, 
        /, 
        base_url: str | Callable[[], str] = "https://qrcodeapi.115.com", 
        *, 
        async_: Literal[False] = False, 
        **request_kwargs, 
    ) -> dict:
        ...
    @overload
    def login_authorize_open(
        self: dict | ClientRequestMixin, 
        payload: None | dict = None, 
        /, 
        base_url: str | Callable[[], str] = "https://qrcodeapi.115.com", 
        *, 
        async_: Literal[True], 
        **request_kwargs, 
    ) -> Coroutine[Any, Any, dict]:
        ...
    def login_authorize_open(
        self: dict | ClientRequestMixin, 
        payload: None | dict = None, 
        /, 
        base_url: str | Callable[[], str] = "https://qrcodeapi.115.com", 
        *, 
        async_: Literal[False, True] = False, 
        **request_kwargs, 
    ) -> dict | Coroutine[Any, Any, dict]:
        """授权码方式请求开放接口应用授权

        GET https://qrcodeapi.115.com/open/authorize

        .. admonition:: Reference

            https://www.yuque.com/115yun/open/okr2cq0wywelscpe#EiOrD

        .. note::
            可以作为 ``staticmethod`` 使用

        .. note::
            最多同时有 3 个授权登录，如果有新的授权加入，会先踢掉时间较早的那一个

        :payload:
            - client_id: int | str 💡 AppID
            - redirect_uri: str 💡 授权成功后重定向到指定的地址并附上授权码 code，需要先到 https://open.115.com/ 应用管理应用域名设置
            - response_type: str = "code" 💡 授权模式，固定为 code，表示授权码模式
            - state: int | str = <default> 💡 随机值，会通过 redirect_uri 原样返回，可用于验证以防 MITM 和 CSRF
        """
        api = complete_url("/open/authorize", base_url=base_url)
        if not isinstance(self, ClientRequestMixin):
            payload = self
        else:
            assert payload is not None
        payload = {"response_type": "code", **payload}
        def parse(resp, content, /):
            if get_status_code(resp) == 302:
                return {
                    "state": True, 
                    "url": resp.headers["location"], 
                    "data": dict(parse_qsl(urlsplit(resp.headers["location"]).query)), 
                    "headers": dict(resp.headers), 
                }
            else:
                return json_loads(content)
        request_kwargs["parse"] = parse
        request_kwargs["follow_redirects"] = False
        return get_request(async_, request_kwargs, self=self)(
            url=api, params=payload, **request_kwargs)

    @overload
    def login_authorize_access_token_open(
        self: dict | ClientRequestMixin, 
        payload: None | dict = None, 
        /, 
        base_url: str | Callable[[], str] = "https://qrcodeapi.115.com", 
        *, 
        async_: Literal[False] = False, 
        **request_kwargs, 
    ) -> dict:
        ...
    @overload
    def login_authorize_access_token_open(
        self: dict | ClientRequestMixin, 
        payload: None | dict = None, 
        /, 
        base_url: str | Callable[[], str] = "https://qrcodeapi.115.com", 
        *, 
        async_: Literal[True], 
        **request_kwargs, 
    ) -> Coroutine[Any, Any, dict]:
        ...
    def login_authorize_access_token_open(
        self: dict | ClientRequestMixin, 
        payload: None | dict = None, 
        /, 
        base_url: str | Callable[[], str] = "https://qrcodeapi.115.com", 
        *, 
        async_: Literal[False, True] = False, 
        **request_kwargs, 
    ) -> dict | Coroutine[Any, Any, dict]:
        """用授权码获取开放接口应用的 access_token

        POST https://qrcodeapi.115.com/open/authCodeToToken

        .. admonition:: Reference

            https://www.yuque.com/115yun/open/okr2cq0wywelscpe#JnDgl

        .. note::
            可以作为 ``staticmethod`` 使用
 
        :payload:
            - client_id: int | str 💡 AppID
            - client_secret: str 💡 AppSecret
            - code: str 💡 授权码，/open/authCodeToToken 重定向地址里面
            - redirect_uri: str 💡 与 /open/authCodeToToken 传的 redirect_uri 一致，可用于验证以防 MITM 和 CSRF
            - grant_type: str = "authorization_code" 💡 授权类型，固定为 authorization_code，表示授权码类型
        """
        api = complete_url("/open/authCodeToToken", base_url=base_url)
        if not isinstance(self, ClientRequestMixin):
            payload = self
        else:
            assert payload is not None
        payload = {"grant_type": "authorization_code", **payload}
        return get_request(async_, request_kwargs, self=self)(
            url=api, method="POST", data=payload, **request_kwargs)

    @overload
    def login_qrcode(
        self: str | dict | ClientRequestMixin, 
        payload: None | str | dict = None, 
        /, 
        app: str = "web", 
        base_url: str | Callable[[], str] = "https://qrcodeapi.115.com", 
        *, 
        async_: Literal[False] = False, 
        **request_kwargs, 
    ) -> bytes:
        ...
    @overload
    def login_qrcode(
        self: str | dict | ClientRequestMixin, 
        payload: None | str | dict = None, 
        /, 
        app: str = "web", 
        base_url: str | Callable[[], str] = "https://qrcodeapi.115.com", 
        *, 
        async_: Literal[True], 
        **request_kwargs, 
    ) -> Coroutine[Any, Any, bytes]:
        ...
    def login_qrcode(
        self: str | dict | ClientRequestMixin, 
        payload: None | str | dict = None, 
        /, 
        app: str = "web", 
        base_url: str | Callable[[], str] = "https://qrcodeapi.115.com", 
        *, 
        async_: Literal[False, True] = False, 
        **request_kwargs, 
    ) -> bytes | Coroutine[Any, Any, bytes]:
        """下载登录二维码图片

        GET https://qrcodeapi.115.com/api/1.0/web/1.0/qrcode

        .. note::
            可以作为 ``staticmethod`` 使用

        :param uid: 二维码的 uid

        :return: 图片的二进制数据（PNG 图片）
        """
        api = complete_url(f"/api/1.0/{app}/1.0/qrcode", base_url=base_url)
        if not isinstance(self, ClientRequestMixin):
            payload = self
        else:
            assert payload is not None
        if isinstance(payload, str):
            payload = {"uid": payload}
        request_kwargs.setdefault("parse", False)
        return get_request(async_, request_kwargs, self=self)(
            url=api, params=payload, **request_kwargs)

    @overload
    def login_qrcode_access_token_open(
        self: str | dict | ClientRequestMixin, 
        payload: None | str | dict = None, 
        /, 
        base_url: str | Callable[[], str] = "https://qrcodeapi.115.com", 
        *, 
        async_: Literal[False] = False, 
        **request_kwargs, 
    ) -> dict:
        ...
    @overload
    def login_qrcode_access_token_open(
        self: str | dict | ClientRequestMixin, 
        payload: None | str | dict = None, 
        /, 
        base_url: str | Callable[[], str] = "https://qrcodeapi.115.com", 
        *, 
        async_: Literal[True], 
        **request_kwargs, 
    ) -> Coroutine[Any, Any, dict]:
        ...
    def login_qrcode_access_token_open(
        self: str | dict | ClientRequestMixin, 
        payload: None | str | dict = None, 
        /, 
        base_url: str | Callable[[], str] = "https://qrcodeapi.115.com", 
        *, 
        async_: Literal[False, True] = False, 
        **request_kwargs, 
    ) -> dict | Coroutine[Any, Any, dict]:
        """绑定扫码并获取开放平台应用的 access_token 和 refresh_token

        POST https://qrcodeapi.115.com/open/deviceCodeToToken

        .. note::
            可以作为 ``staticmethod`` 使用

        .. admonition:: Reference

            https://www.yuque.com/115yun/open/shtpzfhewv5nag11#QCCVQ

        :payload:
            - uid: str
            - code_verifier: str = <default> 💡 默认字符串是 64 个 "0"
        """
        api = complete_url("/open/deviceCodeToToken", base_url=base_url)
        if not isinstance(self, ClientRequestMixin):
            payload = self
        else:
            assert payload is not None
        if isinstance(payload, str):
            payload = {"uid": payload, "code_verifier": _default_code_verifier}
        return get_request(async_, request_kwargs, self=self)(
            url=api, method="POST", data=payload, **request_kwargs)

    @overload
    def login_qrcode_scan(
        self, 
        payload: str | dict, 
        /, 
        base_url: str | Callable[[], str] = "https://qrcodeapi.115.com", 
        *, 
        async_: Literal[False] = False, 
        **request_kwargs, 
    ) -> dict:
        ...
    @overload
    def login_qrcode_scan(
        self, 
        payload: str | dict, 
        /, 
        base_url: str | Callable[[], str] = "https://qrcodeapi.115.com", 
        *, 
        async_: Literal[True], 
        **request_kwargs, 
    ) -> Coroutine[Any, Any, dict]:
        ...
    def login_qrcode_scan(
        self, 
        payload: str | dict, 
        /, 
        base_url: str | Callable[[], str] = "https://qrcodeapi.115.com", 
        *, 
        async_: Literal[False, True] = False, 
        **request_kwargs, 
    ) -> dict | Coroutine[Any, Any, dict]:
        """扫描二维码，payload 数据取自 `login_qrcode_token` 接口响应

        GET https://qrcodeapi.115.com/api/2.0/prompt.php

        :payload:
            - uid: str
        """
        api = complete_url("/api/2.0/prompt.php", base_url=base_url)
        if isinstance(payload, str):
            payload = {"uid": payload}
        return self.request(url=api, params=payload, async_=async_, **request_kwargs)

    @overload
    def login_qrcode_scan_cancel(
        self, 
        payload: str | dict, 
        /, 
        base_url: str | Callable[[], str] = "https://qrcodeapi.115.com", 
        *, 
        async_: Literal[False] = False, 
        **request_kwargs, 
    ) -> dict:
        ...
    @overload
    def login_qrcode_scan_cancel(
        self, 
        payload: str | dict, 
        /, 
        base_url: str | Callable[[], str] = "https://qrcodeapi.115.com", 
        *, 
        async_: Literal[True], 
        **request_kwargs, 
    ) -> Coroutine[Any, Any, dict]:
        ...
    def login_qrcode_scan_cancel(
        self, 
        payload: str | dict, 
        /, 
        base_url: str | Callable[[], str] = "https://qrcodeapi.115.com", 
        *, 
        async_: Literal[False, True] = False, 
        **request_kwargs, 
    ) -> dict | Coroutine[Any, Any, dict]:
        """取消扫描二维码，payload 数据取自 `login_qrcode_scan` 接口响应

        GET https://qrcodeapi.115.com/api/2.0/cancel.php

        :payload:
            - key: str
            - uid: str
            - client: int = 0
        """
        api = complete_url("/api/2.0/cancel.php", base_url=base_url)
        if isinstance(payload, str):
            payload = {"key": payload, "uid": payload, "client": 0}
        return self.request(url=api, params=payload, async_=async_, **request_kwargs)

    @overload
    def login_qrcode_scan_confirm(
        self, 
        payload: str | dict, 
        /, 
        base_url: str | Callable[[], str] = "https://qrcodeapi.115.com", 
        *, 
        async_: Literal[False] = False, 
        **request_kwargs, 
    ) -> dict:
        ...
    @overload
    def login_qrcode_scan_confirm(
        self, 
        payload: str | dict, 
        /, 
        base_url: str | Callable[[], str] = "https://qrcodeapi.115.com", 
        *, 
        async_: Literal[True], 
        **request_kwargs, 
    ) -> Coroutine[Any, Any, dict]:
        ...
    def login_qrcode_scan_confirm(
        self, 
        payload: str | dict, 
        /, 
        base_url: str | Callable[[], str] = "https://qrcodeapi.115.com", 
        *, 
        async_: Literal[False, True] = False, 
        **request_kwargs, 
    ) -> dict | Coroutine[Any, Any, dict]:
        """确认扫描二维码，payload 数据取自 `login_qrcode_scan` 接口响应

        GET https://qrcodeapi.115.com/api/2.0/slogin.php

        :payload:
            - key: str
            - uid: str
            - client: int = 0
        """
        api = complete_url("/api/2.0/slogin.php", base_url=base_url)
        if isinstance(payload, str):
            payload = {"key": payload, "uid": payload, "client": 0}
        return self.request(url=api, params=payload, async_=async_, **request_kwargs)

    @overload
    def login_qrcode_scan_result(
        self: str | ClientRequestMixin, 
        /, 
        uid: None | str = None, 
        app: str = "alipaymini", 
        base_url: str | Callable[[], str] = "https://qrcodeapi.115.com", 
        *, 
        async_: Literal[False] = False, 
        **request_kwargs, 
    ) -> dict:
        ...
    @overload
    def login_qrcode_scan_result(
        self: str | ClientRequestMixin, 
        /, 
        uid: None | str = None, 
        app: str = "alipaymini", 
        base_url: str | Callable[[], str] = "https://qrcodeapi.115.com", 
        *, 
        async_: Literal[True], 
        **request_kwargs, 
    ) -> Coroutine[Any, Any, dict]:
        ...
    def login_qrcode_scan_result(
        self: str | ClientRequestMixin, 
        /, 
        uid: None | str = None, 
        app: str = "alipaymini", 
        base_url: str | Callable[[], str] = "https://qrcodeapi.115.com", 
        *, 
        async_: Literal[False, True] = False, 
        **request_kwargs, 
    ) -> dict | Coroutine[Any, Any, dict]:
        """获取扫码登录的结果，包含 cookie

        POST https://qrcodeapi.115.com/app/1.0/{app}/1.0/login/qrcode/

        .. note::
            可以作为 ``staticmethod`` 使用

        .. note::
            如果报错“IP登录异常”，那么要到次日零点才能解禁，其中尤其是 `app="web"` 最容易遇到此问题

        :param uid: 扫码的 uid
        :param app: 绑定的 app
        :param request: 自定义请求函数
        :param async_: 是否异步
        :param request_kwargs: 其余请求参数

        :return: 接口返回值
        """
        if not isinstance(self, ClientRequestMixin):
            uid = self
        else:
            assert uid is not None
        request_kwargs.setdefault("cookies", None)
        if app == "desktop":
            app = "web"
        elif app in ("windows", "mac", "linux"):
            app = "os_" + app
        elif app in ("ios", "qios", "ipad", "qipad"):
            headers = request_kwargs["headers"] = dict(request_kwargs.get("headers", ()))
            match app:
                case "ios":
                    headers["user-agent"] = "UPhone/1.0.0"
                case "qios":
                    headers["user-agent"] = "OfficePhone/1.0.0"
                case "ipad":
                    headers["user-agent"] = "UPad/1.0.0"
                case "qipad":
                    headers["user-agent"] = "OfficePad/1.0.0"
            app = "ios"
        api = complete_url(f"/app/1.0/{app}/1.0/login/qrcode/", base_url=base_url)
        payload = {"account": uid}
        return get_request(async_, request_kwargs, self=self)(
            url=api, method="POST", data=payload, **request_kwargs)

    @overload
    def login_qrcode_scan_status(
        self: dict | ClientRequestMixin, 
        payload: None | dict = None, 
        /, 
        base_url: str | Callable[[], str] = "https://qrcodeapi.115.com", 
        *, 
        async_: Literal[False] = False, 
        **request_kwargs, 
    ) -> dict:
        ...
    @overload
    def login_qrcode_scan_status(
        self: dict | ClientRequestMixin, 
        payload: None | dict = None, 
        /, 
        base_url: str | Callable[[], str] = "https://qrcodeapi.115.com", 
        *, 
        async_: Literal[True], 
        **request_kwargs, 
    ) -> Coroutine[Any, Any, dict]:
        ...
    def login_qrcode_scan_status(
        self: dict | ClientRequestMixin, 
        payload: None | dict = None, 
        /, 
        base_url: str | Callable[[], str] = "https://qrcodeapi.115.com", 
        *, 
        async_: Literal[False, True] = False, 
        **request_kwargs, 
    ) -> dict | Coroutine[Any, Any, dict]:
        """获取二维码的状态（未扫描、已扫描、已登录、已取消、已过期等），payload 数据取自 `login_qrcode_token` 接口响应

        GET https://qrcodeapi.115.com/get/status/

        .. admonition:: Reference

            https://www.yuque.com/115yun/open/shtpzfhewv5nag11#lAsp2

        .. note::
            可以作为 ``staticmethod`` 使用

        :payload:
            - uid: str
            - time: int
            - sign: str
        """
        api = complete_url("/get/status/", base_url=base_url)
        if not isinstance(self, ClientRequestMixin):
            payload = self
        else:
            assert payload is not None
        return get_request(async_, request_kwargs, self=self)(
            url=api, params=payload, **request_kwargs)

    @overload
    def login_qrcode_token(
        self: None | ClientRequestMixin = None, 
        /, 
        app: str = "web", 
        base_url: str | Callable[[], str] = "https://qrcodeapi.115.com", 
        *, 
        async_: Literal[False] = False, 
        **request_kwargs, 
    ) -> dict:
        ...
    @overload
    def login_qrcode_token(
        self: None | ClientRequestMixin = None, 
        /, 
        app: str = "web", 
        base_url: str | Callable[[], str] = "https://qrcodeapi.115.com", 
        *, 
        async_: Literal[True], 
        **request_kwargs, 
    ) -> Coroutine[Any, Any, dict]:
        ...
    def login_qrcode_token(
        self: None | ClientRequestMixin = None, 
        /, 
        app: str = "web", 
        base_url: str | Callable[[], str] = "https://qrcodeapi.115.com", 
        *, 
        async_: Literal[False, True] = False, 
        **request_kwargs, 
    ) -> dict | Coroutine[Any, Any, dict]:
        """获取登录二维码，扫码可用

        GET https://qrcodeapi.115.com/api/1.0/web/1.0/token/

        .. note::
            可以作为 ``staticmethod`` 使用
        """
        api = complete_url(f"/api/1.0/{app}/1.0/token/", base_url=base_url)
        return get_request(async_, request_kwargs, self=self)(
            url=api, **request_kwargs)

    @overload
    def login_qrcode_token_open(
        self: int | str | dict | ClientRequestMixin, 
        payload: None | int | str | dict = None, 
        /, 
        base_url: str | Callable[[], str] = "https://qrcodeapi.115.com", 
        *, 
        async_: Literal[False] = False, 
        **request_kwargs, 
    ) -> dict:
        ...
    @overload
    def login_qrcode_token_open(
        self: int | str | dict | ClientRequestMixin, 
        payload: None | int | str | dict = None, 
        /, 
        base_url: str | Callable[[], str] = "https://qrcodeapi.115.com", 
        *, 
        async_: Literal[True], 
        **request_kwargs, 
    ) -> Coroutine[Any, Any, dict]:
        ...
    def login_qrcode_token_open(
        self: int | str | dict | ClientRequestMixin, 
        payload: None | int | str | dict = None, 
        /, 
        base_url: str | Callable[[], str] = "https://qrcodeapi.115.com", 
        *, 
        async_: Literal[False, True] = False, 
        **request_kwargs, 
    ) -> dict | Coroutine[Any, Any, dict]:
        """获取开放平台的登录二维码，扫码可用，采用 PKCE (Proof Key for Code Exchange)

        POST https://qrcodeapi.115.com/open/authDeviceCode

        .. admonition:: Reference

            https://www.yuque.com/115yun/open/shtpzfhewv5nag11#WzRhM

        .. note::
            可以作为 ``staticmethod`` 使用

        .. note::
            最多同时有 3 个授权登录，如果有新的授权加入，会先踢掉时间较早的那一个

        .. note::
            code_challenge 默认用的字符串为 64 个 0，hash 算法为 md5

        .. tip::
            如果仅仅想要检查 AppID 是否有效，可以用如下的代码：

            .. code:: python

                from p115client import P115Client

                app_id = 100195125
                response = P115Client.login_qrcode_token_open(app_id)
                if response["code"]:
                    print("无效 AppID:", app_id, "因为:", response["error"])
                else:
                    print("有效 AppID:", app_id)

        .. tip::
            如果想要罗列出所有可用的 AppID，可以用如下的代码：

            .. code:: python

                from itertools import count
                from p115client import P115Client

                get_qrcode_token = P115Client.login_qrcode_token_open
                for app_id in count(100195125, 2):
                    response = get_qrcode_token(app_id)
                    if not response["code"]:
                        print(app_id)

        :payload:
            - client_id: int | str 💡 AppID
            - code_challenge: str = <default> 💡 PKCE 相关参数，计算方式如下

                .. code:: python

                    from base64 import b64encode
                    from hashlib import sha256
                    from secrets import token_bytes

                    # code_verifier 可以是 43~128 位随机字符串
                    code_verifier = token_bytes(64).hex()
                    code_challenge = b64encode(sha256(code_verifier.encode()).digest()).decode()

            - code_challenge_method: str = <default> 💡 计算 `code_challenge` 的 hash 算法，支持 "md5", "sha1", "sha256"
        """
        api = complete_url("/open/authDeviceCode", base_url=base_url)
        if not isinstance(self, ClientRequestMixin):
            payload = self
        else:
            assert payload is not None
        if isinstance(payload, (int, str)):
            payload = {
                "client_id": payload, 
                "code_challenge": _default_code_challenge, 
                "code_challenge_method": _default_code_challenge_method, 
            }
        return get_request(async_, request_kwargs, self=self)(
            url=api, method="POST", data=payload, **request_kwargs)

    @overload
    def login_refresh_token_open(
        self: str | dict | ClientRequestMixin, 
        payload: None | str | dict = None, 
        /, 
        base_url: str | Callable[[], str] = "https://qrcodeapi.115.com", 
        *, 
        async_: Literal[False] = False, 
        **request_kwargs, 
    ) -> dict:
        ...
    @overload
    def login_refresh_token_open(
        self: str | dict | ClientRequestMixin, 
        payload: None | str | dict = None, 
        /, 
        base_url: str | Callable[[], str] = "https://qrcodeapi.115.com", 
        *, 
        async_: Literal[True], 
        **request_kwargs, 
    ) -> Coroutine[Any, Any, dict]:
        ...
    def login_refresh_token_open(
        self: str | dict | ClientRequestMixin, 
        payload: None | str | dict = None, 
        /, 
        base_url: str | Callable[[], str] = "https://qrcodeapi.115.com", 
        *, 
        async_: Literal[False, True] = False, 
        **request_kwargs, 
    ) -> dict | Coroutine[Any, Any, dict]:
        """用一个 refresh_token 去获取新的 access_token 和 refresh_token，然后原来的 refresh_token 作废

        POST https://qrcodeapi.115.com/open/refreshToken

        .. admonition:: Reference

            https://www.yuque.com/115yun/open/shtpzfhewv5nag11#ve54x

            https://www.yuque.com/115yun/open/opnx8yezo4at2be6

        .. note::
            可以作为 ``staticmethod`` 使用

        :payload:
            - refresh_token: str
        """
        api = complete_url("/open/refreshToken", base_url=base_url)
        if not isinstance(self, ClientRequestMixin):
            payload = self
        else:
            assert payload is not None
        if isinstance(payload, str):
            payload = {"refresh_token": payload}
        return get_request(async_, request_kwargs, self=self)(
            url=api, method="POST", data=payload, **request_kwargs)

    @overload
    @classmethod
    def login_with_qrcode(
        cls, 
        /, 
        app: None | str = "", 
        console_qrcode: bool = True, 
        base_url: str | Callable[[], str] = "https://qrcodeapi.115.com", 
        *, 
        async_: Literal[False] = False, 
        **request_kwargs, 
    ) -> dict:
        ...
    @overload
    @classmethod
    def login_with_qrcode(
        cls, 
        /, 
        app: None | str = "", 
        console_qrcode: bool = True, 
        base_url: str | Callable[[], str] = "https://qrcodeapi.115.com", 
        *, 
        async_: Literal[True], 
        **request_kwargs, 
    ) -> Coroutine[Any, Any, dict]:
        ...
    @classmethod
    def login_with_qrcode(
        cls, 
        /, 
        app: None | str = "", 
        console_qrcode: bool = True, 
        base_url: str | Callable[[], str] = "https://qrcodeapi.115.com", 
        *, 
        async_: Literal[False, True] = False, 
        **request_kwargs, 
    ) -> dict | Coroutine[Any, Any, dict]:
        """二维码扫码登录

        .. hint::
            仅获取响应，如果需要更新此 `client` 的 `cookies`，请直接用 `login` 方法

        :param app: 扫二维码后绑定的 `app` （或者叫 `device`）
        :param console_qrcode: 在命令行输出二维码，否则在浏览器中打开
        :param base_url: 接口的基地址
        :param async_: 是否异步
        :param request_kwargs: 其余请求参数

        :return: 响应信息，如果 `app` 为 None 或 ""，则返回二维码信息，否则返回绑定扫码后的信息（包含 cookies）

        -----

        :设备列表如下:

        +-------+----------+------------+----------------------+
        | No.   | ssoent   | app        | description          |
        +=======+==========+============+======================+
        | 01    | A1       | web        | 115生活_网页端       |
        +-------+----------+------------+----------------------+
        | --    | A1       | desktop    | 115浏览器            |
        +-------+----------+------------+----------------------+
        | --    | A2       | ?          | 未知: android        |
        +-------+----------+------------+----------------------+
        | --    | A3       | ?          | 未知: ios            |
        +-------+----------+------------+----------------------+
        | --    | A4       | ?          | 未知: ipad           |
        +-------+----------+------------+----------------------+
        | --    | B1       | ?          | 未知: android        |
        +-------+----------+------------+----------------------+
        | 02    | D1       | ios        | 115生活_苹果端       |
        +-------+----------+------------+----------------------+
        | 03    | D2       | bios       | 未知: ios            |
        +-------+----------+------------+----------------------+
        | 04    | D3       | 115ios     | 115_苹果端           |
        +-------+----------+------------+----------------------+
        | 05    | F1       | android    | 115生活_安卓端       |
        +-------+----------+------------+----------------------+
        | 06    | F2       | bandroid   | 未知: android        |
        +-------+----------+------------+----------------------+
        | 07    | F3       | 115android | 115_安卓端           |
        +-------+----------+------------+----------------------+
        | 08    | H1       | ipad       | 115生活_苹果平板端   |
        +-------+----------+------------+----------------------+
        | 09    | H2       | bipad      | 未知: ipad           |
        +-------+----------+------------+----------------------+
        | 10    | H3       | 115ipad    | 115_苹果平板端       |
        +-------+----------+------------+----------------------+
        | 11    | I1       | tv         | 115生活_安卓电视端   |
        +-------+----------+------------+----------------------+
        | 12    | I2       | apple_tv   | 115生活_苹果电视端   |
        +-------+----------+------------+----------------------+
        | 13    | M1       | qandriod   | 115管理_安卓端       |
        +-------+----------+------------+----------------------+
        | 14    | N1       | qios       | 115管理_苹果端       |
        +-------+----------+------------+----------------------+
        | 15    | O1       | qipad      | 115管理_苹果平板端   |
        +-------+----------+------------+----------------------+
        | 16    | P1       | os_windows | 115生活_Windows端    |
        +-------+----------+------------+----------------------+
        | 17    | P2       | os_mac     | 115生活_macOS端      |
        +-------+----------+------------+----------------------+
        | 18    | P3       | os_linux   | 115生活_Linux端      |
        +-------+----------+------------+----------------------+
        | 19    | R1       | wechatmini | 115生活_微信小程序端 |
        +-------+----------+------------+----------------------+
        | 20    | R2       | alipaymini | 115生活_支付宝小程序 |
        +-------+----------+------------+----------------------+
        | 21    | S1       | harmony    | 115_鸿蒙端           |
        +-------+----------+------------+----------------------+
        """
        def gen_step():
            resp = yield cls.login_qrcode_token(
                async_=async_, 
                base_url=base_url, 
                **request_kwargs, 
            )
            qrcode_token = resp["data"]
            login_uid = qrcode_token["uid"]
            qrcode = qrcode_token.pop("qrcode", "")
            if not qrcode:
                qrcode = "https://115.com/scan/dg-" + login_uid
            if console_qrcode:
                from qrcode import QRCode # type: ignore
                qr = QRCode(border=1)
                qr.add_data(qrcode)
                qr.print_ascii(tty=isatty(1))
            else:
                url = complete_url("/api/1.0/web/1.0/qrcode", base_url=base_url, query={"uid": login_uid})
                if async_:
                    yield startfile_async(url)
                else:
                    startfile(url)
            while True:
                try:
                    resp = yield cls.login_qrcode_scan_status(
                        qrcode_token, 
                        base_url=base_url, 
                        async_=async_, 
                        **request_kwargs, 
                    )
                except Exception:
                    continue
                match resp["data"].get("status"):
                    case 0:
                        print("[status=0] qrcode: waiting")
                    case 1:
                        print("[status=1] qrcode: scanned")
                    case 2:
                        print("[status=2] qrcode: signed in")
                        break
                    case -1:
                        raise P115LoginError(errno.EAUTH, "[status=-1] qrcode: expired")
                    case -2:
                        raise P115LoginError(errno.EAUTH, "[status=-2] qrcode: canceled")
                    case _:
                        raise P115LoginError(errno.EAUTH, f"qrcode: aborted with {resp!r}")
            if app:
                return cls.login_qrcode_scan_result(
                    login_uid, 
                    app=app, 
                    base_url=base_url, 
                    async_=async_, 
                    **request_kwargs, 
                )
            else:
                return qrcode_token
        return run_gen_step(gen_step, async_)

    @overload
    @classmethod
    def login_with_app_id(
        cls, 
        /, 
        app_id: int | str = 100195125, 
        console_qrcode: bool = True, 
        base_url: str | Callable[[], str] = "https://qrcodeapi.115.com", 
        *, 
        async_: Literal[False] = False, 
        **request_kwargs, 
    ) -> dict:
        ...
    @overload
    @classmethod
    def login_with_app_id(
        cls, 
        /, 
        app_id: int | str = 100195125, 
        console_qrcode: bool = True, 
        base_url: str | Callable[[], str] = "https://qrcodeapi.115.com", 
        *, 
        async_: Literal[True], 
        **request_kwargs, 
    ) -> Coroutine[Any, Any, dict]:
        ...
    @classmethod
    def login_with_app_id(
        cls, 
        /, 
        app_id: int | str = 100195125, 
        console_qrcode: bool = True, 
        base_url: str | Callable[[], str] = "https://qrcodeapi.115.com", 
        *, 
        async_: Literal[False, True] = False, 
        **request_kwargs, 
    ) -> dict | Coroutine[Any, Any, dict]:
        """二维码扫码登录开放平台

        :param console_qrcode: 在命令行输出二维码，否则在浏览器中打开
        :param async_: 是否异步
        :param request_kwargs: 其余请求参数

        :return: 响应信息
        """
        def gen_step():
            resp = yield cls.login_qrcode_token_open(
                app_id, 
                base_url=base_url, 
                async_=async_, 
                **request_kwargs, 
            )
            qrcode_token = resp["data"]
            login_uid = qrcode_token["uid"]
            qrcode = qrcode_token.pop("qrcode", "")
            if not qrcode:
                qrcode = "https://115.com/scan/dg-" + login_uid
            if console_qrcode:
                from qrcode import QRCode # type: ignore
                qr = QRCode(border=1)
                qr.add_data(qrcode)
                qr.print_ascii(tty=isatty(1))
            else:
                url = complete_url("/api/1.0/web/1.0/qrcode", base_url=base_url, query={"uid": login_uid})
                if async_:
                    yield startfile_async(url)
                else:
                    startfile(url)
            while True:
                try:
                    resp = yield cls.login_qrcode_scan_status(
                        qrcode_token, 
                        base_url=base_url, 
                        async_=async_, 
                        **request_kwargs, 
                    )
                except Exception:
                    continue
                match resp["data"].get("status"):
                    case 0:
                        print("[status=0] qrcode: waiting")
                    case 1:
                        print("[status=1] qrcode: scanned")
                    case 2:
                        print("[status=2] qrcode: signed in")
                        break
                    case -1:
                        raise P115LoginError(errno.EAUTH, "[status=-1] qrcode: expired")
                    case -2:
                        raise P115LoginError(errno.EAUTH, "[status=-2] qrcode: canceled")
                    case _:
                        raise P115LoginError(errno.EAUTH, f"qrcode: aborted with {resp!r}")
            return cls.login_qrcode_access_token_open(
                login_uid, 
                base_url=base_url, 
                async_=async_, 
                **request_kwargs, 
            )
        return run_gen_step(gen_step, async_)


class P115OpenClient(ClientRequestMixin):
    """115 的客户端对象

    .. admonition:: Reference

        https://www.yuque.com/115yun/open

    :param app_id_or_refresh_token: 申请到的 AppID 或 refresh_token

        - 如果是 int，视为 AppID
        - 如果是 str，如果可以解析为数字，则视为 AppID，否则视为 refresh_token

    :param console_qrcode: 当输入为 AppID 时，进行扫码。如果为 True，则在命令行输出二维码，否则在浏览器中打开
    """
    app_id: int | str
    refresh_token: str

    def __init__(
        self, 
        /, 
        app_id_or_refresh_token: int | str, 
        console_qrcode: bool = True, 
    ):
        self.init(
            app_id_or_refresh_token, 
            console_qrcode=console_qrcode, 
            instance=self, 
        )

    def __eq__(self, other, /) -> bool:
        return type(self) is type(other) and self.user_id == other.user_id

    def __hash__(self, /) -> int:
        return id(self)

    def __repr__(self, /) -> str:
        cls = type(self)
        if app_id := getattr(self, "app_id", 0):
            return f"<{cls.__module__}.{cls.__qualname__}({app_id=}) at {hex(id(self))}>"
        else:
            return f"<{cls.__module__}.{cls.__qualname__} at {hex(id(self))}>"

    @overload
    @classmethod
    def init(
        cls, 
        /, 
        app_id_or_refresh_token: int | str, 
        console_qrcode: bool = True, 
        instance: None | Self = None, 
        *, 
        async_: Literal[False] = False, 
        **request_kwargs, 
    ) -> P115OpenClient:
        ...
    @overload
    @classmethod
    def init(
        cls, 
        /, 
        app_id_or_refresh_token: int | str, 
        console_qrcode: bool = True, 
        instance: None | Self = None, 
        *, 
        async_: Literal[True], 
        **request_kwargs, 
    ) -> Coroutine[Any, Any, P115OpenClient]:
        ...
    @classmethod
    def init(
        cls, 
        /, 
        app_id_or_refresh_token: int | str, 
        console_qrcode: bool = True, 
        instance: None | Self = None, 
        *, 
        async_: Literal[False, True] = False, 
        **request_kwargs, 
    ) -> P115OpenClient | Coroutine[Any, Any, P115OpenClient]:
        def gen_step():
            if instance is None:
                self = cls.__new__(cls)
            else:
                self = instance
            if isinstance(app_id_or_refresh_token, str) and (
                app_id_or_refresh_token.startswith("0") or 
                app_id_or_refresh_token.strip(digits)
            ):
                resp = yield self.login_refresh_token_open(
                    app_id_or_refresh_token, 
                    async_=async_, 
                    **request_kwargs, 
                )
            else:
                app_id = self.app_id = app_id_or_refresh_token
                resp = yield self.login_with_app_id(
                    app_id, 
                    console_qrcode=console_qrcode, 
                    async_=async_, 
                    **request_kwargs, 
                )
            check_response(resp)
            data = resp["data"]
            self.refresh_token = data["refresh_token"]
            self.access_token = data["access_token"]
            return self
        return run_gen_step(gen_step, async_)

    @classmethod
    def from_token(cls, /, access_token: str, refresh_token: str) -> P115OpenClient:
        self = cls.__new__(cls)
        self.access_token = access_token
        self.refresh_token = refresh_token
        return self

    @property
    def access_token(self, /) -> str:
        try:
            return self.__dict__["access_token"]
        except KeyError as e:
            raise AttributeError("access_token") from e

    @access_token.setter
    def access_token(self, token, /):
        self.headers["authorization"] = "Bearer " + token
        self.__dict__["access_token"] = token

    @locked_cacheproperty
    def pickcode_stable_point(self, /) -> str:
        """获取 pickcode 的不动点

        .. todo::
            不动点可能和用户 id 有某种联系，但目前样本不足，难以推断，以后再尝试分析
        """
        user_id = str(self.user_id)
        pickcode_points_json = _CACHE_DIR / "pickcode_stable_points.json"
        try:
            cache = loads(pickcode_points_json.open("rb").read())
        except OSError:
            cache = {}
        if point := cache.get(user_id):
            return point
        else:
            resp = self.fs_files({"show_dir": 1, "limit": 1, "cid": 0})
            check_response(resp)
            info = resp["data"][0]
            point = cache[user_id] = get_stable_point(info["pc"])
            try:
                pickcode_points_json.open("wb").write(dumps(cache))
            except Exception:
                pass
            return point

    @overload
    def refresh_access_token(
        self, 
        /, 
        async_: Literal[False] = False, 
        **request_kwargs, 
    ) -> dict:
        ...
    @overload
    def refresh_access_token(
        self, 
        /, 
        async_: Literal[True], 
        **request_kwargs, 
    ) -> Coroutine[Any, Any, dict]:
        ...
    def refresh_access_token(
        self, 
        /, 
        async_: Literal[False, True] = False, 
        **request_kwargs, 
    ) -> dict | Coroutine[Any, Any, dict]:
        """更新 access_token 和 refresh_token （⚠️ 目前是 7200 秒内就要求刷新一次）
        """
        def gen_step():
            if refresh_token := getattr(self, "refresh_token", ""):
                resp = yield self.login_refresh_token_open(
                    refresh_token, 
                    async_=async_, 
                    **request_kwargs, 
                )
            elif hasattr(self, "login_with_open") and (app_id := getattr(self, "app_id", 0)):
                resp = yield self.login_with_open(
                    app_id, 
                    async_=async_, 
                    **request_kwargs, 
                )
            else:
                raise RuntimeError("no `refresh_token` or `app_id` provided")
            check_response(resp)
            data = resp["data"]
            self.refresh_token = data["refresh_token"]
            self.access_token = data["access_token"]
            return data
        return run_gen_step(gen_step, async_)

    ########## Download API ##########

    @overload
    def download_url(
        self, 
        pickcode: str, 
        /, 
        strict: bool = True, 
        user_agent: None | str = None, 
        *, 
        async_: Literal[False] = False, 
        **request_kwargs, 
    ) -> P115URL:
        ...
    @overload
    def download_url(
        self, 
        pickcode: str, 
        /, 
        strict: bool = True, 
        user_agent: None | str = None, 
        *, 
        async_: Literal[True], 
        **request_kwargs, 
    ) -> Coroutine[Any, Any, P115URL]:
        ...
    def download_url(
        self, 
        pickcode: str, 
        /, 
        strict: bool = True, 
        user_agent: None | str = None, 
        *, 
        async_: Literal[False, True] = False, 
        **request_kwargs, 
    ) -> P115URL | Coroutine[Any, Any, P115URL]:
        """获取文件的下载链接，此接口是对 `download_url_info` 的封装

        .. note::
            获取的直链中，部分查询参数的解释：

            - ``t``: 过期时间戳
            - ``u``: 用户 id
            - ``c``: 允许同时打开次数，如果为 0，则是无限次数
            - ``f``: 请求时要求携带请求头
                - 如果为空，则无要求
                - 如果为 1，则需要 user-agent（和请求直链时的一致）
                - 如果为 3，则需要 user-agent（和请求直链时的一致） 和 Cookie（由请求直链时的响应所返回的 Set-Cookie 响应头）

        :param pickcode: 提取码
        :param strict: 如果为 True，当目标是目录时，会抛出 IsADirectoryError 异常
        :param user_agent: 如果不为 None，则作为请求头 "user-agent" 的值
        :param async_: 是否异步
        :param request_kwargs: 其余请求参数

        :return: 下载链接
        """
        def gen_step():
            resp = yield self.download_url_info_open(
                pickcode, 
                user_agent=user_agent, 
                async_=async_, 
                **request_kwargs, 
            )
            resp["pickcode"] = pickcode
            check_response(resp)
            for fid, info in resp["data"].items():
                url = info["url"]
                if strict and not url:
                    throw(
                        errno.EISDIR, 
                        f"{fid} is a directory, with response {resp}", 
                    )
                return P115URL(
                    url["url"] if url else "", 
                    id=int(fid), 
                    pickcode=info["pick_code"], 
                    name=info["file_name"], 
                    size=int(info["file_size"]), 
                    sha1=info["sha1"], 
                    is_dir=not url, 
                    headers=resp["headers"], 
                )
            throw(
                errno.ENOENT, 
                f"no such pickcode: {pickcode!r}, with response {resp}", 
            )
        return run_gen_step(gen_step, async_)

    @overload
    def download_urls(
        self, 
        pickcodes: str | Iterable[str], 
        /, 
        strict: bool = True, 
        user_agent: None | str = None, 
        *, 
        async_: Literal[False] = False, 
        **request_kwargs, 
    ) -> dict[int, P115URL]:
        ...
    @overload
    def download_urls(
        self, 
        pickcodes: str | Iterable[str], 
        /, 
        strict: bool = True, 
        user_agent: None | str = None, 
        *, 
        async_: Literal[True], 
        **request_kwargs, 
    ) -> Coroutine[Any, Any, dict[int, P115URL]]:
        ...
    def download_urls(
        self, 
        pickcodes: str | Iterable[str], 
        /, 
        strict: bool = True, 
        user_agent: None | str = None, 
        *, 
        async_: Literal[False, True] = False, 
        **request_kwargs, 
    ) -> dict[int, P115URL] | Coroutine[Any, Any, dict[int, P115URL]]:
        """批量获取文件的下载链接，此接口是对 `download_url_info` 的封装

        .. note::
            获取的直链中，部分查询参数的解释：

            - ``t``: 过期时间戳
            - ``u``: 用户 id
            - ``c``: 允许同时打开次数，如果为 0，则是无限次数
            - ``f``: 请求时要求携带请求头
                - 如果为空，则无要求
                - 如果为 1，则需要 user-agent（和请求直链时的一致）
                - 如果为 3，则需要 user-agent（和请求直链时的一致） 和 Cookie（由请求直链时的响应所返回的 Set-Cookie 响应头）

        :param pickcodes: 提取码，多个用逗号 "," 隔开
        :param strict: 如果为 True，当目标是目录时，会直接忽略
        :param user_agent: 如果不为 None，则作为请求头 "user-agent" 的值
        :param async_: 是否异步
        :param request_kwargs: 其余请求参数

        :return: 一批下载链接
        """
        if not isinstance(pickcodes, str):
            pickcodes = ",".join(pickcodes)
        def gen_step():
            resp = yield self.download_url_info_open(
                pickcodes, 
                user_agent=user_agent, 
                async_=async_, 
                **request_kwargs, 
            )
            resp["pickcode"] = pickcodes
            urls: dict[int, P115URL] = {}
            if not resp["state"]:
                if resp.get("errno") != 50003:
                    check_response(resp)
            else:
                for fid, info in resp["data"].items():
                    url = info["url"]
                    if strict and not url:
                        continue
                    fid = int(fid)
                    urls[fid] = P115URL(
                        url["url"] if url else "", 
                        id=fid, 
                        pickcode=info["pick_code"], 
                        name=info["file_name"], 
                        size=int(info["file_size"]), 
                        sha1=info["sha1"], 
                        is_dir=not url, 
                        headers=resp["headers"], 
                    )
            return urls
        return run_gen_step(gen_step, async_)

    @overload
    def download_url_info(
        self, 
        payload: str | dict, 
        /, 
        base_url: str | Callable[[], str] = "https://proapi.115.com", 
        user_agent: None | str = None, 
        *, 
        async_: Literal[False] = False, 
        **request_kwargs, 
    ) -> dict:
        ...
    @overload
    def download_url_info(
        self, 
        payload: str | dict, 
        /, 
        base_url: str | Callable[[], str] = "https://proapi.115.com", 
        user_agent: None | str = None, 
        *, 
        async_: Literal[True], 
        **request_kwargs, 
    ) -> Coroutine[Any, Any, dict]:
        ...
    def download_url_info(
        self, 
        payload: str | dict, 
        /, 
        base_url: str | Callable[[], str] = "https://proapi.115.com", 
        user_agent: None | str = None, 
        *, 
        async_: Literal[False, True] = False, 
        **request_kwargs, 
    ) -> dict | Coroutine[Any, Any, dict]:
        """获取文件的下载链接

        POST https://proapi.115.com/open/ufile/downurl

        .. hint::
            相当于 `P115Client.download_url_app(app="chrome")`

        .. admonition:: Reference

            https://www.yuque.com/115yun/open/um8whr91bxb5997o

        :payload:
            - pick_code: str 💡 提取码，多个用逗号 "," 隔开
        """
        api = complete_url("/open/ufile/downurl", base_url)
        if isinstance(payload, str):
            payload = {"pick_code": payload}
        headers = request_kwargs["headers"] = dict(request_kwargs.get("headers") or ())
        if user_agent is None:
            headers.setdefault("user-agent", "")
        else:
            headers["user-agent"] = user_agent
        def parse(_, content: bytes, /) -> dict:
            json = json_loads(content)
            json["headers"] = headers
            return json
        request_kwargs.setdefault("parse", parse)
        return self.request(url=api, method="POST", data=payload, async_=async_, **request_kwargs)

    ########## File System API ##########

    @overload
    def fs_copy(
        self, 
        payload: int | str | Iterable[int | str] | dict, 
        /, 
        pid: int | str = 0, 
        base_url: str | Callable[[], str] = "https://proapi.115.com", 
        *, 
        async_: Literal[False] = False, 
        **request_kwargs, 
    ) -> dict:
        ...
    @overload
    def fs_copy(
        self, 
        payload: int | str | Iterable[int | str] | dict, 
        /, 
        pid: int | str = 0, 
        base_url: str | Callable[[], str] = "https://proapi.115.com", 
        *, 
        async_: Literal[True], 
        **request_kwargs, 
    ) -> Coroutine[Any, Any, dict]:
        ...
    def fs_copy(
        self, 
        payload: int | str | Iterable[int | str] | dict, 
        /, 
        pid: int | str = 0, 
        base_url: str | Callable[[], str] = "https://proapi.115.com", 
        *, 
        async_: Literal[False, True] = False, 
        **request_kwargs, 
    ) -> dict | Coroutine[Any, Any, dict]:
        """文件复制

        POST https://proapi.115.com/open/ufile/copy

        .. admonition:: Reference

            https://www.yuque.com/115yun/open/lvas49ar94n47bbk

        .. caution::
            ⚠️ 请不要并发执行，限制在 5 万个文件和目录以内

        :payload:
            - file_id: int | str 💡 文件或目录的 id，多个用逗号 "," 隔开
            - pid: int | str = 0 💡 父目录 id
            - nodupli: 0 | 1 = 0 💡 复制的文件在目标目录是否允许重复：0:可以 1:不可以
        """
        api = complete_url("/open/ufile/copy", base_url)
        if isinstance(payload, (int, str)):
            payload = {"file_id": payload}
        elif not isinstance(payload, dict):
            payload = {"file_id": ",".join(map(str, payload))}
        payload.setdefault("pid", pid) # type: ignore
        return self.request(url=api, method="POST", data=payload, async_=async_, **request_kwargs)

    @overload
    def fs_delete(
        self, 
        payload: int | str | dict | Iterable[int | str], 
        /, 
        base_url: str | Callable[[], str] = "https://proapi.115.com", 
        *, 
        async_: Literal[False] = False, 
        **request_kwargs, 
    ) -> dict:
        ...
    @overload
    def fs_delete(
        self, 
        payload: int | str | dict | Iterable[int | str], 
        /, 
        base_url: str | Callable[[], str] = "https://proapi.115.com", 
        *, 
        async_: Literal[True], 
        **request_kwargs, 
    ) -> Coroutine[Any, Any, dict]:
        ...
    def fs_delete(
        self, 
        payload: int | str | dict | Iterable[int | str], 
        /, 
        base_url: str | Callable[[], str] = "https://proapi.115.com", 
        *, 
        async_: Literal[False, True] = False, 
        **request_kwargs, 
    ) -> dict | Coroutine[Any, Any, dict]:
        """删除文件或目录

        POST https://proapi.115.com/open/ufile/delete

        .. admonition:: Reference

            https://www.yuque.com/115yun/open/kt04fu8vcchd2fnb

        .. caution::
            ⚠️ 请不要并发执行，限制在 5 万个文件和目录以内

        :payload:
            - file_ids: int | str 💡 文件或目录的 id，多个用逗号 "," 隔开
        """
        api = complete_url("/open/ufile/delete", base_url)
        if isinstance(payload, (int, str)):
            payload = {"file_ids": payload}
        elif not isinstance(payload, dict):
            payload = {"file_ids": ",".join(map(str, payload))}
        return self.request(url=api, method="POST", data=payload, async_=async_, **request_kwargs)

    @overload
    def fs_files(
        self, 
        payload: int | str | dict = 0, 
        /, 
        base_url: str | Callable[[], str] = "https://proapi.115.com", 
        *, 
        async_: Literal[False] = False, 
        **request_kwargs, 
    ) -> dict:
        ...
    @overload
    def fs_files(
        self, 
        payload: int | str | dict = 0, 
        /, 
        base_url: str | Callable[[], str] = "https://proapi.115.com", 
        *, 
        async_: Literal[True], 
        **request_kwargs, 
    ) -> Coroutine[Any, Any, dict]:
        ...
    def fs_files(
        self, 
        payload: int | str | dict = 0, 
        /, 
        base_url: str | Callable[[], str] = "https://proapi.115.com", 
        *, 
        async_: Literal[False, True] = False, 
        **request_kwargs, 
    ) -> dict | Coroutine[Any, Any, dict]:
        """获取目录中的文件列表和基本信息

        GET https://proapi.115.com/open/ufile/files

        .. hint::
            相当于 ``P115Client.fs_files_app()``

        .. admonition:: Reference

            https://www.yuque.com/115yun/open/kz9ft9a7s57ep868

        :payload:
            - cid: int | str = 0 💡 目录 id，对应 parent_id
            - limit: int = 32 💡 分页大小，最大值不一定，看数据量，7,000 应该总是安全的，10,000 有可能报错，但有时也可以 20,000 而成功
            - offset: int = 0 💡 分页开始的索引，索引从 0 开始计算

            - aid: int = 1 💡 area_id

                - 0: 会被视为 1
                - 1: 正常文件
                - 2: <unknown>
                - 3: <unknown>
                - 4: <unknown>
                - 5: <unknown>
                - 7: 回收站文件
                - 9: <unknown>
                - 12:瞬间文件
                - 15: <unknown>
                - 120: 彻底删除文件、简历附件
                - <其它>: 会被视为 0

            - asc: 0 | 1 = <default> 💡 是否升序排列。0:降序 1:升序
            - code: int | str = <default>
            - count_folders: 0 | 1 = 1 💡 统计文件数和目录数
            - cur: 0 | 1 = <default>   💡 是否只显示当前目录
            - custom_order: 0 | 1 | 2 = <default> 💡 是否使用记忆排序。如果指定了 "asc"、"fc_mix"、"o" 中其一，则此参数会被自动设置为 2

                - 0: 使用记忆排序（自定义排序失效） 
                - 1: 使用自定义排序（不使用记忆排序） 
                - 2: 自定义排序（非目录置顶）

            - date: str = <default> 💡 筛选日期
            - fc_mix: 0 | 1 = <default> 💡 是否目录和文件混合，如果为 0 则目录在前（目录置顶）
            - fields: str = <default>
            - for: str = <default> 💡 文件格式，例如 "doc"
            - hide_data: str = <default> 💡 是否返回文件数据
            - is_q: 0 | 1 = <default>
            - is_share: 0 | 1 = <default>
            - min_size: int = 0 💡 最小的文件大小
            - max_size: int = 0 💡 最大的文件大小
            - natsort: 0 | 1 = <default> 💡 是否执行自然排序(natural sorting)
            - nf: str = <default> 💡 不要显示文件（即仅显示目录），但如果 show_dir=0，则此参数无效
            - o: str = <default> 💡 用某字段排序（未定义的值会被视为 "user_utime"）

                - "file_name": 文件名
                - "file_size": 文件大小
                - "file_type": 文件种类
                - "user_etime": 事件时间（无效，效果相当于 "user_utime"）
                - "user_utime": 修改时间
                - "user_ptime": 创建时间（无效，效果相当于 "user_utime"）
                - "user_otime": 上一次打开时间（无效，效果相当于 "user_utime"）

            - qid: int = <default>
            - r_all: 0 | 1 = <default>
            - record_open_time: 0 | 1 = 1 💡 是否要记录目录的打开时间
            - scid: int | str = <default>
            - show_dir: 0 | 1 = 1 💡 是否显示目录
            - snap: 0 | 1 = <default>
            - source: str = <default>
            - sys_dir: int | str = <default> 💡 系统通用目录
            - star: 0 | 1 = <default> 💡 是否星标文件
            - stdir: 0 | 1 = <default> 💡 筛选文件时，是否显示目录：1:展示 0:不展示
            - suffix: str = <default> 💡 后缀名（优先级高于 `type`）
            - type: int = <default> 💡 文件类型

                - 0: 全部（仅当前目录）
                - 1: 文档
                - 2: 图片
                - 3: 音频
                - 4: 视频
                - 5: 压缩包
                - 6: 软件/应用
                - 7: 书籍
                - 8: 其它
                - 9: 相当于 8
                - 10: 相当于 8
                - 11: 相当于 8
                - 12: ？？？
                - 13: ？？？
                - 14: ？？？
                - 15: 图片和视频，相当于 2 和 4
                - >= 16: 相当于 8
        """
        api = complete_url("/open/ufile/files", base_url)
        if isinstance(payload, (int, str)):
            payload = {"cid": payload}
        payload = {
            "aid": 1, "count_folders": 1, "limit": 32, "offset": 0, 
            "record_open_time": 1, "show_dir": 1, "cid": 0, **payload, 
        }
        if payload.keys() & frozenset(("asc", "fc_mix", "o")):
            payload["custom_order"] = 2
        return self.request(url=api, params=payload, async_=async_, **request_kwargs)

    @overload
    def fs_info(
        self, 
        payload: int | str | dict, 
        /, 
        base_url: str | Callable[[], str] = "https://proapi.115.com", 
        method: str = "GET", 
        *, 
        async_: Literal[False] = False, 
        **request_kwargs, 
    ) -> dict:
        ...
    @overload
    def fs_info(
        self, 
        payload: int | str | dict, 
        /, 
        base_url: str | Callable[[], str] = "https://proapi.115.com", 
        method: str = "GET", 
        *, 
        async_: Literal[True], 
        **request_kwargs, 
    ) -> Coroutine[Any, Any, dict]:
        ...
    def fs_info(
        self, 
        payload: int | str | dict, 
        /, 
        base_url: str | Callable[[], str] = "https://proapi.115.com", 
        method: str = "GET", 
        *, 
        async_: Literal[False, True] = False, 
        **request_kwargs, 
    ) -> dict | Coroutine[Any, Any, dict]:
        """获取文件或目录详情

        GET https://proapi.115.com/open/folder/get_info

        .. note::
            支持 GET 和 POST 方法。`file_id` 和 `path` 需必传一个

        .. hint::
            部分相当于 ``P115Client.fs_category_get_app()``

        .. admonition:: Reference

            https://www.yuque.com/115yun/open/rl8zrhe2nag21dfw

        :payload:
            - file_id: int | str 💡 文件或目录的 id
            - path: str = <default> 💡 文件或目录的路径。分隔符支持 / 和 > 两种符号，最前面需分隔符开头，以分隔符分隔目录层级
        """
        api = complete_url("/open/folder/get_info", base_url)
        if isinstance(payload, int):
            payload = {"file_id": payload}
        elif isinstance(payload, str):
            if payload.startswith("0") or payload.strip(digits):
                if not payload.startswith(("/", ">")):
                    payload = "/" + payload
                payload = {"path": payload}
            else:
                payload = {"file_id": payload}
        if method.upper() == "POST":
            request_kwargs["data"] = payload
        else:
            request_kwargs["params"] = payload
        return self.request(url=api, method=method, async_=async_, **request_kwargs)

    @overload
    def fs_mkdir(
        self, 
        payload: str | dict, 
        /, 
        pid: int | str = 0, 
        base_url: str | Callable[[], str] = "https://proapi.115.com", 
        *, 
        async_: Literal[False] = False, 
        **request_kwargs, 
    ) -> dict:
        ...
    @overload
    def fs_mkdir(
        self, 
        payload: str | dict, 
        /, 
        pid: int | str = 0, 
        base_url: str | Callable[[], str] = "https://proapi.115.com", 
        *, 
        async_: Literal[True], 
        **request_kwargs, 
    ) -> Coroutine[Any, Any, dict]:
        ...
    def fs_mkdir(
        self, 
        payload: str | dict, 
        /, 
        pid: int | str = 0, 
        base_url: str | Callable[[], str] = "https://proapi.115.com", 
        *, 
        async_: Literal[False, True] = False, 
        **request_kwargs, 
    ) -> dict | Coroutine[Any, Any, dict]:
        """新建目录

        POST https://proapi.115.com/open/folder/add

        .. admonition:: Reference

            https://www.yuque.com/115yun/open/qur839kyx9cgxpxi

        :payload:
            - file_name: str 💡 新建目录名称，限制255个字符
            - pid: int | str = 0 💡 新建目录所在的父目录ID (根目录的ID为0)
        """
        api = complete_url("/open/folder/add", base_url)
        if isinstance(payload, str):
            payload = {"pid": pid, "file_name": payload}
        payload.setdefault("pid", pid)
        return self.request(url=api, method="POST", data=payload, async_=async_, **request_kwargs)

    @overload
    def fs_move(
        self, 
        payload: int | str | Iterable[int | str] | dict, 
        /, 
        pid: int | str = 0, 
        base_url: str | Callable[[], str] = "https://proapi.115.com", 
        *, 
        async_: Literal[False] = False, 
        **request_kwargs, 
    ) -> dict:
        ...
    @overload
    def fs_move(
        self, 
        payload: int | str | Iterable[int | str] | dict, 
        /, 
        pid: int | str = 0, 
        base_url: str | Callable[[], str] = "https://proapi.115.com", 
        *, 
        async_: Literal[True], 
        **request_kwargs, 
    ) -> Coroutine[Any, Any, dict]:
        ...
    def fs_move(
        self, 
        payload: int | str | Iterable[int | str] | dict, 
        /, 
        pid: int | str = 0, 
        base_url: str | Callable[[], str] = "https://proapi.115.com", 
        *, 
        async_: Literal[False, True] = False, 
        **request_kwargs, 
    ) -> dict | Coroutine[Any, Any, dict]:
        """文件移动

        POST https://proapi.115.com/open/ufile/move

        .. admonition:: Reference

            https://www.yuque.com/115yun/open/vc6fhi2mrkenmav2

        .. caution::
            ⚠️ 请不要并发执行，限制在 5 万个文件和目录以内

        :payload:
            - file_ids: int | str 💡 文件或目录的 id，多个用逗号 "," 隔开
            - to_cid: int | str = 0 💡 父目录 id
        """
        api = complete_url("/open/ufile/move", base_url)
        if isinstance(payload, (int, str)):
            payload = {"file_ids": payload}
        elif not isinstance(payload, dict):
            payload = {"file_ids": ",".join(map(str, payload))}
        payload.setdefault("to_cid", pid) # type: ignore
        return self.request(url=api, method="POST", data=payload, async_=async_, **request_kwargs)

    @overload
    def fs_rename(
        self, 
        payload: tuple[int | str, str] | dict, 
        /, 
        *, 
        async_: Literal[False] = False, 
        **request_kwargs, 
    ) -> dict:
        ...
    @overload
    def fs_rename(
        self, 
        payload: tuple[int | str, str] | dict, 
        /, 
        *, 
        async_: Literal[True], 
        **request_kwargs, 
    ) -> Coroutine[Any, Any, dict]:
        ...
    def fs_rename(
        self, 
        payload: tuple[int | str, str] | dict, 
        /, 
        *, 
        async_: Literal[False, True] = False, 
        **request_kwargs, 
    ) -> dict | Coroutine[Any, Any, dict]:
        """重命名文件或目录，此接口是对 `fs_update_open` 的封装

        :payload:
            - file_id: int | str 💡 文件 id
            - file_name: str     💡 文件名
        """
        if isinstance(payload, tuple):
            payload = {"file_id": payload[0], "file_name": payload[1]}
        return self.fs_update_open(payload, async_=async_, **request_kwargs)

    @overload
    def fs_search(
        self, 
        payload: str | dict = ".", 
        /, 
        base_url: str | Callable[[], str] = "https://proapi.115.com", 
        *, 
        async_: Literal[False] = False, 
        **request_kwargs, 
    ) -> dict:
        ...
    @overload
    def fs_search(
        self, 
        payload: str | dict = ".", 
        /, 
        base_url: str | Callable[[], str] = "https://proapi.115.com", 
        *, 
        async_: Literal[True], 
        **request_kwargs, 
    ) -> Coroutine[Any, Any, dict]:
        ...
    def fs_search(
        self, 
        payload: str | dict = ".", 
        /, 
        base_url: str | Callable[[], str] = "https://proapi.115.com", 
        *, 
        async_: Literal[False, True] = False, 
        **request_kwargs, 
    ) -> dict | Coroutine[Any, Any, dict]:
        """搜索文件或目录

        GET https://proapi.115.com/open/ufile/search

        .. attention::
            最多只能取回前 10,000 条数据，也就是 `limit + offset <= 10_000`，不过可以一次性取完

            不过就算正确设置了 `limit` 和 `offset`，并且总数据量大于 `limit + offset`，可能也不足 `limit`，这应该是 bug，也就是说，就算数据总量足够你也取不到足量

            它返回数据中的 `count` 字段的值表示总数据量（即使你只能取前 10,000 条），往往并不准确，最多能当作一个可参考的估计值

        .. note::
            这个方法似乎不支持仅搜索目录本身，搜索范围是从指定目录开始的整个目录树

        .. hint::
            相当于 ``P115Client.fs_search_app2()``

        .. admonition:: Reference

            https://www.yuque.com/115yun/open/ft2yelxzopusus38

        :payload:
            - aid: int = 1 💡 area_id

                - 0: 会被视为 1
                - 1: 正常文件
                - 2: <unknown>
                - 3: <unknown>
                - 4: <unknown>
                - 5: <unknown>
                - 7: 回收站文件
                - 9: <unknown>
                - 12:瞬间文件
                - 15: <unknown>
                - 120: 彻底删除文件、简历附件
                - <其它>: 会被视为 0

            - asc: 0 | 1 = <default> 💡 是否升序排列
            - cid: int | str = 0 💡 目录 id。cid=-1 时，表示不返回列表任何内容
            - count_folders: 0 | 1 = <default>
            - date: str = <default> 💡 筛选日期
            - fc: 0 | 1 = <default> 💡 只显示文件或目录。1:只显示目录 2:只显示文件
            - fc_mix: 0 | 1 = <default> 💡 是否目录和文件混合，如果为 0 则目录在前（目录置顶）
            - file_label: int | str = <default> 💡 标签 id
            - gte_day: str 💡 搜索结果匹配的开始时间；格式：YYYY-MM-DD
            - limit: int = 32 💡 一页大小，意思就是 page_size
            - lte_day: str 💡 搜索结果匹配的结束时间；格式：YYYY-MM-DD
            - o: str = <default> 💡 用某字段排序

                - "file_name": 文件名
                - "file_size": 文件大小
                - "file_type": 文件种类
                - "user_utime": 修改时间
                - "user_ptime": 创建时间
                - "user_otime": 上一次打开时间

            - offset: int = 0  💡 索引偏移，索引从 0 开始计算
            - search_value: str = "." 💡 搜索文本，可以是 sha1
            - source: str = <default>
            - star: 0 | 1 = <default> 💡 是否星标文件
            - suffix: str = <default> 💡 后缀名（优先级高于 `type`）
            - type: int = <default> 💡 文件类型

                - 0: 全部（仅当前目录）
                - 1: 文档
                - 2: 图片
                - 3: 音频
                - 4: 视频
                - 5: 压缩包
                - 6: 软件/应用
                - 7: 书籍
                - 99: 所有文件

            - version: str = <default> 💡 版本号，比如 3.1
        """
        api = complete_url("/open/ufile/search", base_url)
        if isinstance(payload, str):
            payload = {"search_value": payload}
        payload = {
            "aid": 1, "cid": 0, "limit": 32, "offset": 0, 
            "show_dir": 1, "search_value": ".", **payload, 
        }
        return self.request(url=api, params=payload, async_=async_, **request_kwargs)

    @overload
    def fs_star_set(
        self, 
        payload: int | str | Iterable[int | str] | dict, 
        /, 
        star: bool = True, 
        *, 
        async_: Literal[False] = False, 
        **request_kwargs, 
    ) -> dict:
        ...
    @overload
    def fs_star_set(
        self, 
        payload: int | str | Iterable[int | str] | dict, 
        /, 
        star: bool = True, 
        *, 
        async_: Literal[True], 
        **request_kwargs, 
    ) -> Coroutine[Any, Any, dict]:
        ...
    def fs_star_set(
        self, 
        payload: int | str | Iterable[int | str] | dict, 
        /, 
        star: bool = True, 
        *, 
        async_: Literal[False, True] = False, 
        **request_kwargs, 
    ) -> dict | Coroutine[Any, Any, dict]:
        """为文件或目录设置或取消星标，此接口是对 `fs_update_open` 的封装

        .. note::
            即使其中任何一个 id 目前已经被删除，也可以操作成功

        :payload:
            - file_id: int | str    💡 只能传入 1 个
            - file_id[0]: int | str 💡 如果有多个，则按顺序给出
            - file_id[1]: int | str
            - ...
            - star: 0 | 1 = 1
        """
        if isinstance(payload, (int, str)):
            payload = {"file_id": payload}
        elif not isinstance(payload, dict):
            payload = {f"file_id[{i}]": id for i, id in enumerate(payload)}
        payload.setdefault("star", int(star))
        return self.fs_update_open(payload, async_=async_, **request_kwargs)

    @overload
    def fs_video(
        self, 
        payload: str | dict, 
        /, 
        base_url: str | Callable[[], str] = "https://proapi.115.com", 
        *, 
        async_: Literal[False] = False, 
        **request_kwargs, 
    ) -> dict:
        ...
    @overload
    def fs_video(
        self, 
        payload: str | dict, 
        /, 
        base_url: str | Callable[[], str] = "https://proapi.115.com", 
        *, 
        async_: Literal[True], 
        **request_kwargs, 
    ) -> Coroutine[Any, Any, dict]:
        ...
    def fs_video(
        self, 
        payload: str | dict, 
        /, 
        base_url: str | Callable[[], str] = "https://proapi.115.com", 
        *, 
        async_: Literal[False, True] = False, 
        **request_kwargs, 
    ) -> dict | Coroutine[Any, Any, dict]:
        """获取视频在线播放地址（和视频文件相关数据）

        GET https://proapi.115.com/open/video/play

        .. admonition:: Reference

            https://www.yuque.com/115yun/open/hqglxv3cedi3p9dz

        .. hint::
            需切换音轨时，在请求返回的播放地址中增加请求参数 `&audio_track=${index}`，值就是接口响应中 `multitrack_list` 中某个成员的索引，从 0 开始计数

        :payload:
            - pick_code: str 💡 文件提取码
            - share_id: int | str = <default> 💡 共享 id，获取共享文件播放地址所需
        """
        api = complete_url("/open/video/play", base_url)
        if isinstance(payload, str):
            payload = {"pick_code": payload}
        return self.request(url=api, params=payload, async_=async_, **request_kwargs)

    @overload
    def fs_video_history(
        self, 
        payload: str | dict, 
        /, 
        base_url: str | Callable[[], str] = "https://proapi.115.com", 
        *, 
        async_: Literal[False] = False, 
        **request_kwargs, 
    ) -> dict:
        ...
    @overload
    def fs_video_history(
        self, 
        payload: str | dict, 
        /, 
        base_url: str | Callable[[], str] = "https://proapi.115.com", 
        *, 
        async_: Literal[True], 
        **request_kwargs, 
    ) -> Coroutine[Any, Any, dict]:
        ...
    def fs_video_history(
        self, 
        payload: str | dict, 
        /, 
        base_url: str | Callable[[], str] = "https://proapi.115.com", 
        *, 
        async_: Literal[False, True] = False, 
        **request_kwargs, 
    ) -> dict | Coroutine[Any, Any, dict]:
        """获取视频播放进度

        GET https://proapi.115.com/open/video/history

        .. admonition:: Reference

            https://www.yuque.com/115yun/open/gssqdrsq6vfqigag

        :payload:
            - pick_code: str 💡 文件提取码
        """
        api = complete_url("/open/video/history", base_url)
        if isinstance(payload, str):
            payload = {"pick_code": payload}
        return self.request(url=api, params=payload, async_=async_, **request_kwargs)

    @overload
    def fs_video_history_set(
        self, 
        payload: str | dict, 
        /, 
        base_url: str | Callable[[], str] = "https://proapi.115.com", 
        *, 
        async_: Literal[False] = False, 
        **request_kwargs, 
    ) -> dict:
        ...
    @overload
    def fs_video_history_set(
        self, 
        payload: str | dict, 
        /, 
        base_url: str | Callable[[], str] = "https://proapi.115.com", 
        *, 
        async_: Literal[True], 
        **request_kwargs, 
    ) -> Coroutine[Any, Any, dict]:
        ...
    def fs_video_history_set(
        self, 
        payload: str | dict, 
        /, 
        base_url: str | Callable[[], str] = "https://proapi.115.com", 
        *, 
        async_: Literal[False, True] = False, 
        **request_kwargs, 
    ) -> dict | Coroutine[Any, Any, dict]:
        """记忆视频播放进度

        POST https://proapi.115.com/open/video/history

        .. admonition:: Reference

            https://www.yuque.com/115yun/open/bshagbxv1gzqglg4

        :payload:
            - pick_code: str 💡 文件提取码
            - time: int = <default> 💡 视频播放进度时长 (单位秒)
            - watch_end: int = <default> 💡 视频是否播放播放完毕 0:未完毕 1:完毕
        """
        api = complete_url("/open/video/history", base_url)
        if isinstance(payload, str):
            payload = {"pick_code": payload}
        return self.request(url=api, method="POST", data=payload, async_=async_, **request_kwargs)

    @overload
    def fs_video_push(
        self, 
        payload: str | dict, 
        /, 
        base_url: str | Callable[[], str] = "https://proapi.115.com", 
        *, 
        async_: Literal[False] = False, 
        **request_kwargs, 
    ) -> dict:
        ...
    @overload
    def fs_video_push(
        self, 
        payload: str | dict, 
        /, 
        base_url: str | Callable[[], str] = "https://proapi.115.com", 
        *, 
        async_: Literal[True], 
        **request_kwargs, 
    ) -> Coroutine[Any, Any, dict]:
        ...
    def fs_video_push(
        self, 
        payload: str | dict, 
        /, 
        base_url: str | Callable[[], str] = "https://proapi.115.com", 
        *, 
        async_: Literal[False, True] = False, 
        **request_kwargs, 
    ) -> dict | Coroutine[Any, Any, dict]:
        """提交视频转码

        POST https://proapi.115.com/open/video/video_push

        .. admonition:: Reference

            https://www.yuque.com/115yun/open/nxt8r1qcktmg3oan

        :payload:
            - pick_code: str 💡 文件提取码
            - op: str = "vip_push" 💡 提交视频加速转码方式

                - "vip_push": 根据；vip 等级加速
                - "pay_push": 枫叶加速
        """
        api = complete_url("/open/video/video_push", base_url)
        if isinstance(payload, str):
            payload = {"pick_code": payload}
        payload.setdefault("op", "vip_push")
        return self.request(url=api, method="POST", data=payload, async_=async_, **request_kwargs)

    @overload
    def fs_video_subtitle(
        self, 
        payload: str | dict, 
        /, 
        base_url: str | Callable[[], str] = "https://proapi.115.com", 
        *, 
        async_: Literal[False] = False, 
        **request_kwargs, 
    ) -> dict:
        ...
    @overload
    def fs_video_subtitle(
        self, 
        payload: str | dict, 
        /, 
        base_url: str | Callable[[], str] = "https://proapi.115.com", 
        *, 
        async_: Literal[True], 
        **request_kwargs, 
    ) -> Coroutine[Any, Any, dict]:
        ...
    def fs_video_subtitle(
        self, 
        payload: str | dict, 
        /, 
        base_url: str | Callable[[], str] = "https://proapi.115.com", 
        *, 
        async_: Literal[False, True] = False, 
        **request_kwargs, 
    ) -> dict | Coroutine[Any, Any, dict]:
        """视频字幕列表

        GET https://proapi.115.com/open/video/subtitle

        .. admonition:: Reference

            https://www.yuque.com/115yun/open/nx076h3glapoyh7u

        :payload:
            - pick_code: str 💡 文件提取码
        """
        api = complete_url("/open/video/subtitle", base_url)
        if isinstance(payload, str):
            payload = {"pick_code": payload}
        return self.request(url=api, params=payload, async_=async_, **request_kwargs)

    @overload
    def fs_update(
        self, 
        payload: dict, 
        /, 
        base_url: str | Callable[[], str] = "https://proapi.115.com", 
        *, 
        async_: Literal[False] = False, 
        **request_kwargs, 
    ) -> dict:
        ...
    @overload
    def fs_update(
        self, 
        payload: dict, 
        /, 
        base_url: str | Callable[[], str] = "https://proapi.115.com", 
        *, 
        async_: Literal[True], 
        **request_kwargs, 
    ) -> Coroutine[Any, Any, dict]:
        ...
    def fs_update(
        self, 
        payload: dict, 
        /, 
        base_url: str | Callable[[], str] = "https://proapi.115.com", 
        *, 
        async_: Literal[False, True] = False, 
        **request_kwargs, 
    ) -> dict | Coroutine[Any, Any, dict]:
        """设置文件或目录（备注、标签、封面等）

        POST https://proapi.115.com/open/ufile/update

        .. hint::
            即使文件已经被删除，也可以操作成功

        .. admonition:: Reference

            https://www.yuque.com/115yun/open/gyrpw5a0zc4sengm

        :payload:
            - file_id: int | str    💡 只能传入 1 个
            - file_id[0]: int | str 💡 如果有多个，则按顺序给出
            - file_id[1]: int | str
            - ...
            - file_name: str = <default> 💡 文件名
            - star: 0 | 1 = <default> 💡 是否星标：0:取消星标 1:设置星标
            - ...
        """
        api = complete_url("/open/ufile/update", base_url)
        return self.request(url=api, method="POST", data=payload, async_=async_, **request_kwargs)

    ########## Offline API ##########

    @overload
    def offline_add_torrent(
        self, 
        payload: dict, 
        /, 
        base_url: str | Callable[[], str] = "https://proapi.115.com", 
        *, 
        async_: Literal[False] = False, 
        **request_kwargs, 
    ) -> dict:
        ...
    @overload
    def offline_add_torrent(
        self, 
        payload: dict, 
        /, 
        base_url: str | Callable[[], str] = "https://proapi.115.com", 
        *, 
        async_: Literal[True], 
        **request_kwargs, 
    ) -> Coroutine[Any, Any, dict]:
        ...
    def offline_add_torrent(
        self, 
        payload: dict, 
        /, 
        base_url: str | Callable[[], str] = "https://proapi.115.com", 
        *, 
        async_: Literal[False, True] = False, 
        **request_kwargs, 
    ) -> dict | Coroutine[Any, Any, dict]:
        """添加云下载 BT 任务

        POST https://proapi.115.com/open/offline/add_task_bt 

        .. admonition:: Reference

            https://www.yuque.com/115yun/open/svfe4unlhayvluly

        :payload:
            - info_hash: str 💡 种子文件的 info_hash
            - pick_code: str 💡 种子文件的提取码
            - save_path: str 💡 保存到 `wp_path_id` 对应目录下的相对路径
            - torrent_sha1: str 💡 种子文件的 sha1
            - wanted: str 💡 选择文件进行下载（是数字索引，从 0 开始计数，用 "," 分隔）
            - wp_path_id: int | str = <default> 💡 保存目标目录 id
        """
        api = complete_url("/open/offline/add_task_bt ", base_url)
        return self.request(url=api, method="POST", data=payload, async_=async_, **request_kwargs)

    @overload
    def offline_add_urls(
        self, 
        payload: str | Iterable[str] | dict, 
        /, 
        base_url: str | Callable[[], str] = "https://proapi.115.com", 
        *, 
        async_: Literal[False] = False, 
        **request_kwargs, 
    ) -> dict:
        ...
    @overload
    def offline_add_urls(
        self, 
        payload: str | Iterable[str] | dict, 
        /, 
        base_url: str | Callable[[], str] = "https://proapi.115.com", 
        *, 
        async_: Literal[True], 
        **request_kwargs, 
    ) -> Coroutine[Any, Any, dict]:
        ...
    def offline_add_urls(
        self, 
        payload: str | Iterable[str] | dict, 
        /, 
        base_url: str | Callable[[], str] = "https://proapi.115.com", 
        *, 
        async_: Literal[False, True] = False, 
        **request_kwargs, 
    ) -> dict | Coroutine[Any, Any, dict]:
        """添加云下载链接任务

        POST https://proapi.115.com/open/offline/add_task_urls

        .. admonition:: Reference

            https://www.yuque.com/115yun/open/zkyfq2499gdn3mty

        :payload:
            - urls: str 💡 链接，用 "\\n" 分隔，支持HTTP、HTTPS、FTP、磁力链和电驴链接
            - wp_path_id: int | str = <default> 💡 保存到目录的 id
        """
        api = complete_url("/open/offline/add_task_urls", base_url)
        if isinstance(payload, str):
            payload = {"urls": payload.strip("\n")}
        elif not isinstance(payload, dict):
            payload = {"urls": ",".join(payload)}
        return self.request(url=api, method="POST", data=payload, async_=async_, **request_kwargs)

    @overload
    def offline_clear(
        self, 
        payload: int | dict = 0, 
        /, 
        base_url: str | Callable[[], str] = "https://proapi.115.com", 
        *, 
        async_: Literal[False] = False, 
        **request_kwargs, 
    ) -> dict:
        ...
    @overload
    def offline_clear(
        self, 
        payload: int | dict = 0, 
        /, 
        base_url: str | Callable[[], str] = "https://proapi.115.com", 
        *, 
        async_: Literal[True], 
        **request_kwargs, 
    ) -> Coroutine[Any, Any, dict]:
        ...
    def offline_clear(
        self, 
        payload: int | dict = 0, 
        /, 
        base_url: str | Callable[[], str] = "https://proapi.115.com", 
        *, 
        async_: Literal[False, True] = False, 
        **request_kwargs, 
    ) -> dict | Coroutine[Any, Any, dict]:
        """清空云下载任务

        POST https://proapi.115.com/open/offline/clear_task

        .. admonition:: Reference

            https://www.yuque.com/115yun/open/uu5i4urb5ylqwfy4

        :payload:
            - flag: int = 0 💡 标识，用于对应某种情况

                - 0: 已完成
                - 1: 全部
                - 2: 已失败
                - 3: 进行中
                - 4: 已完成+删除源文件
                - 5: 全部+删除源文件
        """
        api = complete_url("/open/offline/clear_task", base_url)
        if isinstance(payload, int):
            payload = {"flag": payload}
        return self.request(url=api, method="POST", data=payload, async_=async_, **request_kwargs)

    @overload
    def offline_list(
        self, 
        payload: int | dict = 1, 
        /, 
        base_url: str | Callable[[], str] = "https://proapi.115.com", 
        *, 
        async_: Literal[False] = False, 
        **request_kwargs, 
    ) -> dict:
        ...
    @overload
    def offline_list(
        self, 
        payload: int | dict = 1, 
        /, 
        base_url: str | Callable[[], str] = "https://proapi.115.com", 
        *, 
        async_: Literal[True], 
        **request_kwargs, 
    ) -> Coroutine[Any, Any, dict]:
        ...
    def offline_list(
        self, 
        payload: int | dict = 1, 
        /, 
        base_url: str | Callable[[], str] = "https://proapi.115.com", 
        *, 
        async_: Literal[False, True] = False, 
        **request_kwargs, 
    ) -> dict | Coroutine[Any, Any, dict]:
        """获取用户云下载任务列表

        GET https://proapi.115.com/open/offline/get_task_list

        .. admonition:: Reference

            https://www.yuque.com/115yun/open/av2mluz7uwigz74k

        :payload:
            - page: int = 1
        """
        api = complete_url("/open/offline/get_task_list", base_url)
        if isinstance(payload, int):
            payload = {"page": payload}
        return self.request(url=api, params=payload, async_=async_, **request_kwargs)

    @overload
    def offline_quota_info(
        self, 
        /, 
        base_url: str | Callable[[], str] = "https://proapi.115.com", 
        *, 
        async_: Literal[False] = False, 
        **request_kwargs, 
    ) -> dict:
        ...
    @overload
    def offline_quota_info(
        self, 
        /, 
        base_url: str | Callable[[], str] = "https://proapi.115.com", 
        *, 
        async_: Literal[True], 
        **request_kwargs, 
    ) -> Coroutine[Any, Any, dict]:
        ...
    def offline_quota_info(
        self, 
        /, 
        base_url: str | Callable[[], str] = "https://proapi.115.com", 
        *, 
        async_: Literal[False, True] = False, 
        **request_kwargs, 
    ) -> dict | Coroutine[Any, Any, dict]:
        """获取云下载配额信息

        GET https://proapi.115.com/open/offline/get_quota_info

        .. admonition:: Reference

            https://www.yuque.com/115yun/open/gif2n3smh54kyg0p
        """
        api = complete_url("/open/offline/get_quota_info", base_url)
        return self.request(url=api, async_=async_, **request_kwargs)

    @overload
    def offline_remove(
        self, 
        payload: str | dict, 
        /, 
        base_url: str | Callable[[], str] = "https://proapi.115.com", 
        *, 
        async_: Literal[False] = False, 
        **request_kwargs, 
    ) -> dict:
        ...
    @overload
    def offline_remove(
        self, 
        payload: str | dict, 
        /, 
        base_url: str | Callable[[], str] = "https://proapi.115.com", 
        *, 
        async_: Literal[True], 
        **request_kwargs, 
    ) -> Coroutine[Any, Any, dict]:
        ...
    def offline_remove(
        self, 
        payload: str | dict, 
        /, 
        base_url: str | Callable[[], str] = "https://proapi.115.com", 
        *, 
        async_: Literal[False, True] = False, 
        **request_kwargs, 
    ) -> dict | Coroutine[Any, Any, dict]:
        """删除用户云下载任务

        POST https://proapi.115.com/open/offline/del_task

        .. admonition:: Reference

            https://www.yuque.com/115yun/open/pmgwc86lpcy238nw

        :payload:
            - info_hash: str 💡 待删除任务的 info_hash
            - del_source_file: 0 | 1 = <default> 💡 是否删除源文件 1:删除 0:不删除
        """
        api = complete_url("/open/offline/del_task", base_url)
        if isinstance(payload, str):
            payload = {"info_hash": payload}
        return self.request(api, method="POST", data=payload, async_=async_, **request_kwargs)

    @overload
    def offline_torrent_info(
        self, 
        payload: dict, 
        /, 
        base_url: str | Callable[[], str] = "https://proapi.115.com", 
        *, 
        async_: Literal[False] = False, 
        **request_kwargs, 
    ) -> dict:
        ...
    @overload
    def offline_torrent_info(
        self, 
        payload: dict, 
        /, 
        base_url: str | Callable[[], str] = "https://proapi.115.com", 
        *, 
        async_: Literal[True], 
        **request_kwargs, 
    ) -> Coroutine[Any, Any, dict]:
        ...
    def offline_torrent_info(
        self, 
        payload: dict, 
        /, 
        base_url: str | Callable[[], str] = "https://proapi.115.com", 
        *, 
        async_: Literal[False, True] = False, 
        **request_kwargs, 
    ) -> dict | Coroutine[Any, Any, dict]:
        """解析 BT 种子

        POST https://proapi.115.com/open/offline/torrent

        .. admonition:: Reference

            https://www.yuque.com/115yun/open/evez3u50cemoict1

        :payload:
            - torrent_sha1: str 💡 种子文件的 sha1
            - pick_code: str    💡 种子文件的提取码
        """
        api = complete_url("/open/offline/torrent", base_url)
        return self.request(url=api, method="POST", data=payload, async_=async_, **request_kwargs)

    ########## Recyclebin API ##########

    @overload
    def recyclebin_clean(
        self, 
        payload: int | str | Iterable[int | str] | dict = {}, 
        /, 
        base_url: str | Callable[[], str] = "https://proapi.115.com", 
        *, 
        async_: Literal[False] = False, 
        **request_kwargs, 
    ) -> dict:
        ...
    @overload
    def recyclebin_clean(
        self, 
        payload: int | str | Iterable[int | str] | dict = {}, 
        /, 
        base_url: str | Callable[[], str] = "https://proapi.115.com", 
        *, 
        async_: Literal[True], 
        **request_kwargs, 
    ) -> Coroutine[Any, Any, dict]:
        ...
    def recyclebin_clean(
        self, 
        payload: int | str | Iterable[int | str] | dict = {}, 
        /, 
        base_url: str | Callable[[], str] = "https://proapi.115.com", 
        *, 
        async_: Literal[False, True] = False, 
        **request_kwargs, 
    ) -> dict | Coroutine[Any, Any, dict]:
        """回收站：删除或清空

        POST https://proapi.115.com/open/rb/del

        .. admonition:: Reference

            https://www.yuque.com/115yun/open/gwtof85nmboulrce

        :payload:
            - tid: int | str 💡 多个用逗号 "," 隔开
        """
        api = complete_url("/open/rb/del", base_url)
        if isinstance(payload, (int, str)):
            payload = {"tid": payload}
        elif not isinstance(payload, dict):
            payload = {"tid": ",".join(map(str, payload))}
        return self.request(url=api, method="POST", data=payload, async_=async_, **request_kwargs)

    @overload
    def recyclebin_list(
        self, 
        payload: int | dict = 0, 
        /, 
        base_url: str | Callable[[], str] = "https://proapi.115.com", 
        *, 
        async_: Literal[False] = False, 
        **request_kwargs, 
    ) -> dict:
        ...
    @overload
    def recyclebin_list(
        self, 
        payload: int | dict = 0, 
        /, 
        base_url: str | Callable[[], str] = "https://proapi.115.com", 
        *, 
        async_: Literal[True], 
        **request_kwargs, 
    ) -> Coroutine[Any, Any, dict]:
        ...
    def recyclebin_list(
        self, 
        payload: int | dict = 0, 
        /, 
        base_url: str | Callable[[], str] = "https://proapi.115.com", 
        *, 
        async_: Literal[False, True] = False, 
        **request_kwargs, 
    ) -> dict | Coroutine[Any, Any, dict]:
        """回收站：列表

        GET https://proapi.115.com/open/rb/list

        .. admonition:: Reference

            https://www.yuque.com/115yun/open/bg7l4328t98fwgex

        :payload:
            - limit: int = 32
            - offset: int = 0
        """ 
        api = complete_url("/open/rb/list", base_url)
        if isinstance(payload, int):
            payload = {"limit": 32, "offset": payload}
        payload.setdefault("limit", 32)
        return self.request(url=api, params=payload, async_=async_, **request_kwargs)

    @overload
    def recyclebin_revert(
        self, 
        payload: int | str | Iterable[int | str] | dict, 
        /, 
        base_url: str | Callable[[], str] = "https://proapi.115.com", 
        *, 
        async_: Literal[False] = False, 
        **request_kwargs, 
    ) -> dict:
        ...
    @overload
    def recyclebin_revert(
        self, 
        payload: int | str | Iterable[int | str] | dict, 
        /, 
        base_url: str | Callable[[], str] = "https://proapi.115.com", 
        *, 
        async_: Literal[True], 
        **request_kwargs, 
    ) -> Coroutine[Any, Any, dict]:
        ...
    def recyclebin_revert(
        self, 
        payload: int | str | Iterable[int | str] | dict, 
        /, 
        base_url: str | Callable[[], str] = "https://proapi.115.com", 
        *, 
        async_: Literal[False, True] = False, 
        **request_kwargs, 
    ) -> dict | Coroutine[Any, Any, dict]:
        """回收站：还原

        POST https://proapi.115.com/open/rb/revert

        .. admonition:: Reference

            https://www.yuque.com/115yun/open/gq293z80a3kmxbaq

        .. caution::
            ⚠️ 请不要并发执行，限制在 5 万个文件和目录以内

        :payload:
            - tid: int | str 💡 多个用逗号 "," 隔开
        """
        api = complete_url("/open/rb/revert", base_url)
        if isinstance(payload, (int, str)):
            payload = {"tid": payload}
        elif not isinstance(payload, dict):
            payload = {"tid": ",".join(map(str, payload))}
        return self.request(url=api, method="POST", data=payload, async_=async_, **request_kwargs)

    ########## Upload API ##########

    @overload
    def upload_gettoken(
        self: None | ClientRequestMixin = None, 
        /, 
        base_url: str | Callable[[], str] = "https://proapi.115.com", 
        *, 
        async_: Literal[False] = False, 
        **request_kwargs, 
    ) -> dict:
        ...
    @overload
    def upload_gettoken(
        self: None | ClientRequestMixin = None, 
        /, 
        base_url: str | Callable[[], str] = "https://proapi.115.com", 
        *, 
        async_: Literal[True], 
        **request_kwargs, 
    ) -> Coroutine[Any, Any, dict]:
        ...
    def upload_gettoken(
        self: None | ClientRequestMixin = None, 
        /, 
        base_url: str | Callable[[], str] = "https://proapi.115.com", 
        *, 
        async_: Literal[False, True] = False, 
        **request_kwargs, 
    ) -> dict | Coroutine[Any, Any, dict]:
        """获取阿里云 OSS 的 token（上传凭证）

        GET https://proapi.115.com/open/upload/get_token

        .. admonition:: Reference

            https://www.yuque.com/115yun/open/kzacvzl0g7aiyyn4

        .. note::
            可以作为 ``staticmethod`` 使用
        """
        if isinstance(self, P115OpenClient):
            api = complete_url("/open/upload/get_token", base_url)
            return self.request(url=api, async_=async_, **request_kwargs)
        else:
            api = "https://uplb.115.com/3.0/gettoken.php"
            return get_request(async_, request_kwargs, self=self)(url=api, **request_kwargs)

    @overload
    def upload_init(
        self, 
        payload: dict, 
        /, 
        base_url: str | Callable[[], str] = "https://proapi.115.com", 
        *, 
        async_: Literal[False] = False, 
        **request_kwargs, 
    ) -> dict:
        ...
    @overload
    def upload_init(
        self, 
        payload: dict, 
        /, 
        base_url: str | Callable[[], str] = "https://proapi.115.com", 
        *, 
        async_: Literal[True], 
        **request_kwargs, 
    ) -> Coroutine[Any, Any, dict]:
        ...
    def upload_init(
        self, 
        payload: dict, 
        /, 
        base_url: str | Callable[[], str] = "https://proapi.115.com", 
        *, 
        async_: Literal[False, True] = False, 
        **request_kwargs, 
    ) -> dict | Coroutine[Any, Any, dict]:
        """初始化上传任务，可能秒传

        POST https://proapi.115.com/open/upload/init

        .. admonition:: Reference

            https://www.yuque.com/115yun/open/ul4mrauo5i2uza0q

        :payload:
            - file_name: str 💡 文件名
            - fileid: str 💡 文件的 sha1 值
            - file_size: int 💡 文件大小，单位是字节
            - target: str 💡 上传目标，格式为 f"U_{aid}_{pid}"
            - topupload: int = 0 💡 上传调度文件类型调度标记

                -  0: 单文件上传任务标识 1 条单独的文件上传记录
                -  1: 目录任务调度的第 1 个子文件上传请求标识 1 次目录上传记录
                -  2: 目录任务调度的其余后续子文件不作记作单独上传的上传记录 
                - -1: 没有该参数

            - sign_key: str = "" 💡 2 次验证时读取文件的范围
            - sign_val: str = "" 💡 2 次验证的签名值
        """
        api = complete_url("/open/upload/init", base_url)
        return self.request(url=api, method="POST", data=payload, async_=async_, **request_kwargs)

    @overload
    def upload_resume(
        self, 
        payload: dict | str, 
        /, 
        base_url: str | Callable[[], str] = "https://proapi.115.com", 
        *, 
        async_: Literal[False] = False, 
        **request_kwargs, 
    ) -> dict:
        ...
    @overload
    def upload_resume(
        self, 
        payload: dict | str, 
        /, 
        base_url: str | Callable[[], str] = "https://proapi.115.com", 
        *, 
        async_: Literal[True], 
        **request_kwargs, 
    ) -> Coroutine[Any, Any, dict]:
        ...
    def upload_resume(
        self, 
        payload: dict | str, 
        /, 
        base_url: str | Callable[[], str] = "https://proapi.115.com", 
        *, 
        async_: Literal[False, True] = False, 
        **request_kwargs, 
    ) -> dict | Coroutine[Any, Any, dict]:
        """获取恢复断点续传所需信息

        POST https://proapi.115.com/open/upload/resume

        .. admonition:: Reference

            https://www.yuque.com/115yun/open/tzvi9sbcg59msddz

        :payload:
            - pick_code: str 💡 上传任务 key
            - target: str    💡 上传目标，默认为 "U_1_0"，格式为 f"U_{aid}_{pid}"
            - fileid: str    💡 文件的 sha1 值（⚠️ 可以是任意值）
            - file_size: int 💡 文件大小，单位是字节（⚠️ 可以是任意值）
        """
        api = complete_url("/open/upload/resume", base_url)
        if isinstance(payload, str):
            payload = {"pick_code": payload}
        else:
            payload = dict(payload)
        payload.setdefault("fileid", "0" * 40)
        payload.setdefault("file_size", 1)
        payload.setdefault("target", "U_1_0")
        return self.request(url=api, method="POST", data=payload, async_=async_, **request_kwargs)

    @overload
    def upload_file_init(
        self, 
        /, 
        filename: str, 
        filesize: int, 
        filesha1: str, 
        read_range_bytes_or_hash: None | Callable[[str], str | Buffer] = None, 
        pid: int | str = 0, 
        *, 
        async_: Literal[False] = False, 
        **request_kwargs, 
    ) -> dict:
        ...
    @overload
    def upload_file_init(
        self, 
        /, 
        filename: str, 
        filesize: int, 
        filesha1: str, 
        read_range_bytes_or_hash: None | Callable[[str], str | Buffer] = None, 
        pid: int | str = 0, 
        *, 
        async_: Literal[True], 
        **request_kwargs, 
    ) -> Coroutine[Any, Any, dict]:
        ...
    def upload_file_init(
        self, 
        /, 
        filename: str, 
        filesize: int, 
        filesha1: str, 
        read_range_bytes_or_hash: None | Callable[[str], str | Buffer] = None, 
        pid: int | str = 0, 
        *, 
        async_: Literal[False, True] = False, 
        **request_kwargs, 
    ) -> dict | Coroutine[Any, Any, dict]:
        """初始化上传，可能秒传，此接口是对 `upload_init_open` 的封装

        .. note::
            - 文件大小 和 sha1 是必需的，只有 sha1 是没用的。
            - 如果文件大于等于 1 MB (1048576 B)，就需要 2 次检验一个范围哈希，就必须提供 `read_range_bytes_or_hash`

        :param filename: 文件名
        :param filesize: 文件大小
        :param filesha1: 文件的 sha1
        :param read_range_bytes_or_hash: 调用以获取 2 次验证的数据或计算 sha1，接受一个数据范围，格式符合:
            `HTTP Range Requests <https://developer.mozilla.org/en-US/docs/Web/HTTP/Range_requests>`_，
            返回值如果是 str，则视为计算好的 sha1，如果为 Buffer，则视为数据（之后会被计算 sha1）
        :param pid: 上传文件到此目录的 id，或者指定的 target（格式为 f"U_{aid}_{pid}"，但若 `aid != 1`，则会报参数错误）
        :param async_: 是否异步
        :param request_kwargs: 其余请求参数

        :return: 接口响应
        """
        def gen_step():
            if isinstance(pid, str) and pid.startswith("U_"):
                target = pid
            else:
                target = f"U_1_{pid}"
            payload = {
                "file_name": filename, 
                "fileid": filesha1.upper(), 
                "file_size": filesize, 
                "target": target, 
                "topupload": 1, 
            }
            resp = yield self.upload_init_open(
                payload, 
                async_=async_, 
                **request_kwargs, 
            )
            if not resp["state"]:
                return resp
            data = resp["data"]
            if data["status"] == 7:
                if read_range_bytes_or_hash is None:
                    raise ValueError("filesize >= 1 MB, thus need pass the `read_range_bytes_or_hash` argument")
                payload["sign_key"] = data["sign_key"]
                sign_check: str = data["sign_check"]
                content: str | Buffer
                if async_:
                    content = yield ensure_async(read_range_bytes_or_hash)(sign_check)
                else:
                    content = read_range_bytes_or_hash(sign_check)
                if isinstance(content, str):
                    payload["sign_val"] = content.upper()
                else:
                    payload["sign_val"] = sha1(content).hexdigest().upper()
                resp = yield self.upload_init_open(
                    payload, 
                    async_=async_, # type: ignore
                    **request_kwargs, 
                )
            resp["reuse"] = resp["data"].get("status") == 2
            return resp
        return run_gen_step(gen_step, async_)

    @overload
    def upload_file(
        self, 
        /, 
        file: Buffer | str | PathLike | URL | SupportsGeturl | SupportsRead, 
        pid: int | str = 0, 
        filename: str = "", 
        filesha1: str = "", 
        filesize: int = -1, 
        partsize: int = 0, 
        callback: None | dict = None, 
        upload_id: str = "", 
        endpoint: str = "http://oss-cn-shenzhen.aliyuncs.com", 
        *, 
        async_: Literal[False] = False, 
        **request_kwargs, 
    ) -> dict:
        ...
    @overload
    def upload_file(
        self, 
        /, 
        file: Buffer | str | PathLike | URL | SupportsGeturl | SupportsRead, 
        pid: int | str = 0, 
        filename: str = "", 
        filesha1: str = "", 
        filesize: int = -1, 
        partsize: int = 0, 
        callback: None | dict = None, 
        upload_id: str = "", 
        endpoint: str = "http://oss-cn-shenzhen.aliyuncs.com", 
        *, 
        async_: Literal[True], 
        **request_kwargs, 
    ) -> Coroutine[Any, Any, dict]:
        ...
    def upload_file(
        self, 
        /, 
        file: Buffer | str | PathLike | URL | SupportsGeturl | SupportsRead, 
        pid: int | str = 0, 
        filename: str = "", 
        filesha1: str = "", 
        filesize: int = -1, 
        partsize: int = 0, 
        callback: None | dict = None, 
        upload_id: str = "", 
        endpoint: str = "http://oss-cn-shenzhen.aliyuncs.com", 
        *, 
        async_: Literal[False, True] = False, 
        **request_kwargs, 
    ) -> dict | Coroutine[Any, Any, dict]:
        """上传文件

        .. note::
            如果提供了 ``callback``，则强制为分块上传。
            此时，最好提供一下 ``upload_id``，否则就是从头开始。
            此时可以省略 ``pid``、``filename``、``filesha1``、``filesize``、``partsize``

        .. caution::
            ``partsize > 0`` 时，不要把 ``partsize`` 设置得太小，起码得 10 MB (10485760) 以上

        :param file: 待上传的文件
        :param pid: 上传文件到此目录的 id 或 pickcode，或者指定的 target（格式为 f"U_{aid}_{pid}"，但若 `aid != 1`，则会报参数错误）
        :param filename: 文件名，如果为空，则会自动确定
        :param filesha1: 文件的 sha1，如果为空，则会自动确定
        :param filesize: 文件大小，如果为 -1，则会自动确定
        :param partsize: 分块上传的分块大小。如果为 0，则不做分块上传；如果 < 0，则会自动确定
        :param callback: 回调数据
        :param upload_id: 上传任务 id
        :param endpoint: 上传目的网址
        :param async_: 是否异步
        :param request_kwargs: 其余请求参数

        :return: 接口响应
        """
        request_kwargs["headers"] = dict(
            request_kwargs.get("headers") or (), 
            authorization=self.headers["authorization"], 
        )
        if isinstance(pid, str) and not pid.startswith("U_"):
            pid = self.to_id(pid)
        return upload(
            file=file, 
            pid=pid, 
            filename=filename, 
            filesha1=filesha1, 
            filesize=filesize, 
            partsize=partsize, 
            callback=callback, 
            upload_id=upload_id, 
            endpoint=endpoint, 
            async_=async_, 
            **request_kwargs, 
        )

    ########## User API ##########

    @overload
    def user_info(
        self, 
        /, 
        base_url: str | Callable[[], str] = "https://proapi.115.com", 
        *, 
        async_: Literal[False] = False, 
        **request_kwargs, 
    ) -> dict:
        ...
    @overload
    def user_info(
        self, 
        /, 
        base_url: str | Callable[[], str] = "https://proapi.115.com", 
        *, 
        async_: Literal[True], 
        **request_kwargs, 
    ) -> Coroutine[Any, Any, dict]:
        ...
    def user_info(
        self, 
        /, 
        base_url: str | Callable[[], str] = "https://proapi.115.com", 
        *, 
        async_: Literal[False, True] = False, 
        **request_kwargs, 
    ) -> dict | Coroutine[Any, Any, dict]:
        """获取用户信息

        GET https://proapi.115.com/open/user/info

        .. admonition:: Reference

            https://www.yuque.com/115yun/open/ot1litggzxa1czww
        """
        api = complete_url("/open/user/info", base_url)
        return self.request(url=api, async_=async_, **request_kwargs)

    ########## Other API ##########s

    @overload
    def vip_qr_url(
        self, 
        payload: int | dict, 
        /, 
        base_url: str | Callable[[], str] = "https://proapi.115.com", 
        *, 
        async_: Literal[False] = False, 
        **request_kwargs, 
    ) -> dict:
        ...
    @overload
    def vip_qr_url(
        self, 
        payload: int | dict, 
        /, 
        base_url: str | Callable[[], str] = "https://proapi.115.com", 
        *, 
        async_: Literal[True], 
        **request_kwargs, 
    ) -> Coroutine[Any, Any, dict]:
        ...
    def vip_qr_url(
        self, 
        payload: int | dict, 
        /, 
        base_url: str | Callable[[], str] = "https://proapi.115.com", 
        *, 
        async_: Literal[False, True] = False, 
        **request_kwargs, 
    ) -> dict | Coroutine[Any, Any, dict]:
        """获取产品列表地址（即引导用户扫码购买 115 的 VIP 服务，以获取提成）

        GET https://proapi.115.com/open/vip/qr_url

        .. admonition:: Reference

            https://www.yuque.com/115yun/open/cguk6qshgapwg4qn#oByvI

        :payload:
            - open_device: int
            - default_product_id: int = <default> 💡 打开产品列表默认选中的产品对应的产品id，如果没有则使用默认的产品顺序。

                - 月费: 5
                - 年费: 1
                - 尝鲜1天: 101
                - 长期VIP(长期): 24072401
                - 超级VIP: 24072402
        """
        api = complete_url("/open/vip/qr_url", base_url)
        if not isinstance(payload, dict):
            payload = {"open_device": payload}
        return self.request(url=api, params=payload, async_=async_, **request_kwargs)

    download_url_open = download_url
    download_urls_open = download_urls
    download_url_info_open = download_url_info
    fs_copy_open = fs_copy
    fs_delete_open = fs_delete
    fs_files_open = fs_files
    fs_info_open = fs_info
    fs_mkdir_open = fs_mkdir
    fs_move_open = fs_move
    fs_rename_open = fs_rename
    fs_search_open = fs_search
    fs_star_set_open = fs_star_set
    fs_video_open = fs_video
    fs_video_history_open = fs_video_history
    fs_video_history_set_open = fs_video_history_set
    fs_video_push_open = fs_video_push
    fs_video_subtitle_open = fs_video_subtitle
    fs_update_open = fs_update
    offline_add_torrent_open = offline_add_torrent
    offline_add_urls_open = offline_add_urls
    offline_clear_open = offline_clear
    offline_list_open = offline_list
    offline_quota_info_open = offline_quota_info
    offline_remove_open = offline_remove
    offline_torrent_info_open = offline_torrent_info
    recyclebin_clean_open = recyclebin_clean
    recyclebin_list_open = recyclebin_list
    recyclebin_revert_open = recyclebin_revert
    upload_gettoken_open = upload_gettoken
    upload_init_open = upload_init
    upload_resume_open = upload_resume
    user_info_open = user_info
    upload_file_init_open = upload_file_init
    upload_file_open = upload_file
    vip_qr_url_open = vip_qr_url

    to_id = staticmethod(to_id)

    def to_pickcode(
        self, 
        id: int | str, 
        /, 
        prefix: Literal["a", "b", "c", "d", "e", "fa", "fb", "fc", "fd", "fe"] = "a", 
    ) -> str:
        """把可能是 id 或 pickcode 的一律转换成 pickcode

        .. note::
            规定：空提取码 "" 对应的 id 是 0

        :param id: 可能是 id 或 pickcode
        :param prefix: 前缀

        :return: pickcode
        """
        return to_pickcode(id, self.pickcode_stable_point, prefix=prefix)


class P115Client(P115OpenClient):
    """115 的客户端对象

    .. note::
        目前允许 1 个用户同时登录多个开放平台应用（用 AppID 区别），也允许多次授权登录同 1 个应用

        目前最多同时有 3 个授权登录，如果有新的授权加入，会先踢掉时间较早的那一个

        目前不允许短时间内再次用 ``refresh_token`` 刷新 ``access_token``，但你可以用登录的方式再次授权登录以获取 ``access_token``，即可不受频率限制

        1 个 ``refresh_token`` 只能使用 1 次，可获取新的 ``refresh_token`` 和 ``access_token``，如果请求刷新时，发送成功但读取失败，可能导致 ``refresh_token`` 报废，这时需要重新授权登录

    :param cookies: 115 的 cookies，要包含 ``UID``、``CID``、``KID`` 和 ``SEID`` 等

        - 如果是 None，则会要求人工扫二维码登录
        - 如果是 str，则要求是格式正确的 cookies 字符串，例如 "UID=...; CID=...; KID=...; SEID=..."
        - 如果是 bytes 或 os.PathLike，则视为路径，当更新 cookies 时，也会往此路径写入文件，格式要求同上面的 `str`
        - 如果是 collections.abc.Mapping，则是一堆 cookie 的名称到值的映射
        - 如果是 collections.abc.Iterable，则其中每一条都视为单个 cookie

    :param check_for_relogin: 网页请求抛出异常时，判断是否要重新登录并重试

        - 如果为 False，则不重试
        - 如果为 True，则自动通过判断 HTTP 响应码为 405 时重新登录并重试
        - 如果为 collections.abc.Callable，则调用以判断，当返回值为 bool 类型且值为 True，或者值为 405 时重新登录，然后循环此流程，直到成功或不可重试

    :param ensure_cookies: 检查以确保 cookies 是有效的，如果失效，就重新登录
    :param app: 重新登录时人工扫二维码后绑定的 `app` （或者叫 `device`），如果不指定，则根据 cookies 的 UID 字段来确定，如果不能确定，则用 "qandroid"
    :param console_qrcode: 在命令行输出二维码，否则在浏览器中打开

    -----

    :设备列表如下:

    +-------+----------+------------+----------------------+
    | No.   | ssoent   | app        | description          |
    +=======+==========+============+======================+
    | 01    | A1       | web        | 115生活_网页端       |
    +-------+----------+------------+----------------------+
    | --    | A1       | desktop    | 115浏览器            |
    +-------+----------+------------+----------------------+
    | --    | A2       | ?          | 未知: android        |
    +-------+----------+------------+----------------------+
    | --    | A3       | ?          | 未知: ios            |
    +-------+----------+------------+----------------------+
    | --    | A4       | ?          | 未知: ipad           |
    +-------+----------+------------+----------------------+
    | --    | B1       | ?          | 未知: android        |
    +-------+----------+------------+----------------------+
    | 02    | D1       | ios        | 115生活_苹果端       |
    +-------+----------+------------+----------------------+
    | 03    | D2       | bios       | 未知: ios            |
    +-------+----------+------------+----------------------+
    | 04    | D3       | 115ios     | 115_苹果端           |
    +-------+----------+------------+----------------------+
    | 05    | F1       | android    | 115生活_安卓端       |
    +-------+----------+------------+----------------------+
    | 06    | F2       | bandroid   | 未知: android        |
    +-------+----------+------------+----------------------+
    | 07    | F3       | 115android | 115_安卓端           |
    +-------+----------+------------+----------------------+
    | 08    | H1       | ipad       | 115生活_苹果平板端   |
    +-------+----------+------------+----------------------+
    | 09    | H2       | bipad      | 未知: ipad           |
    +-------+----------+------------+----------------------+
    | 10    | H3       | 115ipad    | 115_苹果平板端       |
    +-------+----------+------------+----------------------+
    | 11    | I1       | tv         | 115生活_安卓电视端   |
    +-------+----------+------------+----------------------+
    | 12    | I2       | apple_tv   | 115生活_苹果电视端   |
    +-------+----------+------------+----------------------+
    | 13    | M1       | qandriod   | 115管理_安卓端       |
    +-------+----------+------------+----------------------+
    | 14    | N1       | qios       | 115管理_苹果端       |
    +-------+----------+------------+----------------------+
    | 15    | O1       | qipad      | 115管理_苹果平板端   |
    +-------+----------+------------+----------------------+
    | 16    | P1       | os_windows | 115生活_Windows端    |
    +-------+----------+------------+----------------------+
    | 17    | P2       | os_mac     | 115生活_macOS端      |
    +-------+----------+------------+----------------------+
    | 18    | P3       | os_linux   | 115生活_Linux端      |
    +-------+----------+------------+----------------------+
    | 19    | R1       | wechatmini | 115生活_微信小程序端 |
    +-------+----------+------------+----------------------+
    | 20    | R2       | alipaymini | 115生活_支付宝小程序 |
    +-------+----------+------------+----------------------+
    | 21    | S1       | harmony    | 115_鸿蒙端           |
    +-------+----------+------------+----------------------+
    """
    app_id: int | str
    refresh_token: str

    def __init__(
        self, 
        /, 
        cookies: None | str | PathLike | Mapping[str, str] | Iterable[Mapping | Cookie | Morsel] = None, 
        check_for_relogin: bool | Callable[[BaseException], bool | int] = False, 
        ensure_cookies: bool = False, 
        app: None | str = None, 
        console_qrcode: bool = True, 
    ):
        self.init(
            cookies=cookies, 
            check_for_relogin=check_for_relogin, 
            ensure_cookies=ensure_cookies, 
            app=app, 
            console_qrcode=console_qrcode, 
            instance=self, 
        )

    def __repr__(self, /) -> str:
        cls = type(self)
        if uid := self.cookies_str.uid:
            return f"<{cls.__module__}.{cls.__qualname__}(UID={uid!r}, app={self.login_app()!r}) at {hex(id(self))}>"
        return f"<{cls.__module__}.{cls.__qualname__} at {hex(id(self))}>"

    @locked_cacheproperty
    def user_key(self, /) -> str:
        user_id = str(self.user_id)
        userkey_points_json = _CACHE_DIR / "userkey_stable_points.json"
        try:
            cache = loads(userkey_points_json.open("rb").read())
        except OSError:
            cache = {}
        if point := cache.get(user_id):
            return point
        else:
            resp = self.upload_key()
            check_response(resp)
            point = cache[user_id] = resp["data"]["userkey"]
            try:
                userkey_points_json.open("wb").write(dumps(cache))
            except Exception:
                pass
            return point

    @overload # type: ignore
    @classmethod
    def init(
        cls, 
        /, 
        cookies: None | str | PathLike | Mapping[str, str] | Iterable[Mapping | Cookie | Morsel] = None, 
        check_for_relogin: bool | Callable[[BaseException], bool | int] = False, 
        ensure_cookies: bool = False, 
        app: None | str = None, 
        console_qrcode: bool = True, 
        instance: None | Self = None, 
        *, 
        async_: Literal[False] = False, 
        **request_kwargs, 
    ) -> P115Client:
        ...
    @overload
    @classmethod
    def init(
        cls, 
        /, 
        cookies: None | str | PathLike | Mapping[str, str] | Iterable[Mapping | Cookie | Morsel] = None, 
        check_for_relogin: bool | Callable[[BaseException], bool | int] = False, 
        ensure_cookies: bool = False, 
        app: None | str = None, 
        console_qrcode: bool = True, 
        instance: None | Self = None, 
        *, 
        async_: Literal[True], 
        **request_kwargs, 
    ) -> Coroutine[Any, Any, P115Client]:
        ...
    @classmethod
    def init(
        cls, 
        /, 
        cookies: None | str | PathLike | Mapping[str, str] | Iterable[Mapping | Cookie | Morsel] = None, 
        check_for_relogin: bool | Callable[[BaseException], bool | int] = False, 
        ensure_cookies: bool = False, 
        app: None | str = None, 
        console_qrcode: bool = True, 
        instance: None | Self = None, 
        *, 
        async_: Literal[False, True] = False, 
        **request_kwargs, 
    ) -> P115Client | Coroutine[Any, Any, P115Client]:
        def gen_step():
            if instance is None:
                self = cls.__new__(cls)
            else:
                self = instance
            if cookies is None:
                yield self.login(
                    app, 
                    console_qrcode=console_qrcode, 
                    async_=async_, 
                    **request_kwargs, 
                )
            else:
                if isinstance(cookies, PathLike):
                    if isinstance(cookies, PurePath) and hasattr(cookies, "open"):
                        self.cookies_path = cookies
                    else:
                        self.cookies_path = Path(fsdecode(cookies))
                    self._read_cookies()
                elif cookies:
                    setattr(self, "cookies", cookies)
                if ensure_cookies:
                    yield self.login(
                        app, 
                        console_qrcode=console_qrcode, 
                        async_=async_, 
                        **request_kwargs, 
                    )
            setattr(self, "check_for_relogin", check_for_relogin)
            return self
        return run_gen_step(gen_step, async_)

    @classmethod
    def from_path(
        cls, 
        /, 
        path: bytes | str | PathLike = Path("~/115-cookies.txt").expanduser(), 
        check_for_relogin: bool | Callable[[BaseException], bool | int] = False, 
    ) -> P115Client:
        if not isinstance(path, PurePath):
            path = Path(fsdecode(path))
        return cls(path, check_for_relogin=check_for_relogin)

    @locked_cacheproperty
    def request_lock(self, /) -> Lock:
        return Lock()

    @locked_cacheproperty
    def request_alock(self, /) -> AsyncLock:
        return AsyncLock()

    @property
    def check_for_relogin(self, /) -> None | Callable[[BaseException], bool | int]:
        return self.__dict__.get("check_for_relogin")

    @check_for_relogin.setter
    def check_for_relogin(self, call: None | bool | Callable[[BaseException], bool | int], /):
        if call is None:
            self.__dict__["check_for_relogin"] = None
        elif call is False:
            self.__dict__.pop("check_for_relogin", None)
        else:
            if call is True:
                call = default_check_for_relogin
            self.__dict__["check_for_relogin"] = call

    @overload
    def login(
        self, 
        /, 
        app: None | str = None, 
        console_qrcode: bool = True, 
        *, 
        async_: Literal[False] = False, 
        **request_kwargs, 
    ) -> Self:
        ...
    @overload
    def login(
        self, 
        /, 
        app: None | str = None, 
        console_qrcode: bool = True, 
        *, 
        async_: Literal[True], 
        **request_kwargs, 
    ) -> Coroutine[Any, Any, Self]:
        ...
    def login(
        self, 
        /, 
        app: None | str = None, 
        console_qrcode: bool = True, 
        async_: Literal[False, True] = False, 
        **request_kwargs, 
    ) -> Self | Coroutine[Any, Any, Self]:
        """扫码二维码登录，如果已登录则忽略

        :param app: 扫二维码后绑定的 `app` （或者叫 `device`），如果不指定，则根据 cookies 的 UID 字段来确定，如果不能确定，则用 "qandroid"
        :param console_qrcode: 在命令行输出二维码，否则在浏览器中打开
        :param async_: 是否异步
        :param request_kwargs: 其余请求参数

        :return: 返回对象本身

        -----

        :设备列表如下:

        +-------+----------+------------+----------------------+
        | No.   | ssoent   | app        | description          |
        +=======+==========+============+======================+
        | 01    | A1       | web        | 115生活_网页端       |
        +-------+----------+------------+----------------------+
        | --    | A1       | desktop    | 115浏览器            |
        +-------+----------+------------+----------------------+
        | --    | A2       | ?          | 未知: android        |
        +-------+----------+------------+----------------------+
        | --    | A3       | ?          | 未知: ios            |
        +-------+----------+------------+----------------------+
        | --    | A4       | ?          | 未知: ipad           |
        +-------+----------+------------+----------------------+
        | --    | B1       | ?          | 未知: android        |
        +-------+----------+------------+----------------------+
        | 02    | D1       | ios        | 115生活_苹果端       |
        +-------+----------+------------+----------------------+
        | 03    | D2       | bios       | 未知: ios            |
        +-------+----------+------------+----------------------+
        | 04    | D3       | 115ios     | 115_苹果端           |
        +-------+----------+------------+----------------------+
        | 05    | F1       | android    | 115生活_安卓端       |
        +-------+----------+------------+----------------------+
        | 06    | F2       | bandroid   | 未知: android        |
        +-------+----------+------------+----------------------+
        | 07    | F3       | 115android | 115_安卓端           |
        +-------+----------+------------+----------------------+
        | 08    | H1       | ipad       | 115生活_苹果平板端   |
        +-------+----------+------------+----------------------+
        | 09    | H2       | bipad      | 未知: ipad           |
        +-------+----------+------------+----------------------+
        | 10    | H3       | 115ipad    | 115_苹果平板端       |
        +-------+----------+------------+----------------------+
        | 11    | I1       | tv         | 115生活_安卓电视端   |
        +-------+----------+------------+----------------------+
        | 12    | I2       | apple_tv   | 115生活_苹果电视端   |
        +-------+----------+------------+----------------------+
        | 13    | M1       | qandriod   | 115管理_安卓端       |
        +-------+----------+------------+----------------------+
        | 14    | N1       | qios       | 115管理_苹果端       |
        +-------+----------+------------+----------------------+
        | 15    | O1       | qipad      | 115管理_苹果平板端   |
        +-------+----------+------------+----------------------+
        | 16    | P1       | os_windows | 115生活_Windows端    |
        +-------+----------+------------+----------------------+
        | 17    | P2       | os_mac     | 115生活_macOS端      |
        +-------+----------+------------+----------------------+
        | 18    | P3       | os_linux   | 115生活_Linux端      |
        +-------+----------+------------+----------------------+
        | 19    | R1       | wechatmini | 115生活_微信小程序端 |
        +-------+----------+------------+----------------------+
        | 20    | R2       | alipaymini | 115生活_支付宝小程序 |
        +-------+----------+------------+----------------------+
        | 21    | S1       | harmony    | 115_鸿蒙端           |
        +-------+----------+------------+----------------------+
        """
        def gen_step():
            nonlocal app
            status = yield self.login_status(async_=async_, **request_kwargs)
            if status:
                return self
            if not app:
                app = yield self.login_app(async_=async_, **request_kwargs)
            if not app:
                app = "alipaymini"
            resp = yield self.login_with_qrcode(
                app, 
                console_qrcode=console_qrcode, 
                async_=async_, 
                **request_kwargs, 
            )
            while True:
                try:
                    check_response(resp)
                    break
                except P115AuthenticationError:
                    print("login error:", resp)
                    resp = yield self.login_with_qrcode(
                        app, 
                        console_qrcode=console_qrcode, 
                        async_=async_, 
                        **request_kwargs, 
                    )
            setattr(self, "cookies", resp["data"]["cookie"])
            return self
        return run_gen_step(gen_step, async_)

    @overload
    def login_with_app(
        self, 
        /, 
        app: None | str = None, 
        *, 
        async_: Literal[False] = False, 
        **request_kwargs, 
    ) -> dict:
        ...
    @overload
    def login_with_app(
        self, 
        /, 
        app: None | str = None, 
        *, 
        async_: Literal[True], 
        **request_kwargs, 
    ) -> Coroutine[Any, Any, dict]:
        ...
    def login_with_app(
        self, 
        /, 
        app: None | str = None, 
        *, 
        async_: Literal[False, True] = False, 
        **request_kwargs, 
    ) -> dict | Coroutine[Any, Any, dict]:
        """执行一次自动扫登录二维码，然后绑定到指定设备

        :param app: 绑定的 `app` （或者叫 `device`），如果为 None 或 ""，则和当前 client 的登录设备相同
        :param async_: 是否异步
        :param request_kwargs: 其余请求参数

        :return: 响应信息，包含 cookies

        -----

        :设备列表如下:

        +-------+----------+------------+----------------------+
        | No.   | ssoent   | app        | description          |
        +=======+==========+============+======================+
        | 01    | A1       | web        | 115生活_网页端       |
        +-------+----------+------------+----------------------+
        | --    | A1       | desktop    | 115浏览器            |
        +-------+----------+------------+----------------------+
        | --    | A2       | ?          | 未知: android        |
        +-------+----------+------------+----------------------+
        | --    | A3       | ?          | 未知: ios            |
        +-------+----------+------------+----------------------+
        | --    | A4       | ?          | 未知: ipad           |
        +-------+----------+------------+----------------------+
        | --    | B1       | ?          | 未知: android        |
        +-------+----------+------------+----------------------+
        | 02    | D1       | ios        | 115生活_苹果端       |
        +-------+----------+------------+----------------------+
        | 03    | D2       | bios       | 未知: ios            |
        +-------+----------+------------+----------------------+
        | 04    | D3       | 115ios     | 115_苹果端           |
        +-------+----------+------------+----------------------+
        | 05    | F1       | android    | 115生活_安卓端       |
        +-------+----------+------------+----------------------+
        | 06    | F2       | bandroid   | 未知: android        |
        +-------+----------+------------+----------------------+
        | 07    | F3       | 115android | 115_安卓端           |
        +-------+----------+------------+----------------------+
        | 08    | H1       | ipad       | 115生活_苹果平板端   |
        +-------+----------+------------+----------------------+
        | 09    | H2       | bipad      | 未知: ipad           |
        +-------+----------+------------+----------------------+
        | 10    | H3       | 115ipad    | 115_苹果平板端       |
        +-------+----------+------------+----------------------+
        | 11    | I1       | tv         | 115生活_安卓电视端   |
        +-------+----------+------------+----------------------+
        | 12    | I2       | apple_tv   | 115生活_苹果电视端   |
        +-------+----------+------------+----------------------+
        | 13    | M1       | qandriod   | 115管理_安卓端       |
        +-------+----------+------------+----------------------+
        | 14    | N1       | qios       | 115管理_苹果端       |
        +-------+----------+------------+----------------------+
        | 15    | O1       | qipad      | 115管理_苹果平板端   |
        +-------+----------+------------+----------------------+
        | 16    | P1       | os_windows | 115生活_Windows端    |
        +-------+----------+------------+----------------------+
        | 17    | P2       | os_mac     | 115生活_macOS端      |
        +-------+----------+------------+----------------------+
        | 18    | P3       | os_linux   | 115生活_Linux端      |
        +-------+----------+------------+----------------------+
        | 19    | R1       | wechatmini | 115生活_微信小程序端 |
        +-------+----------+------------+----------------------+
        | 20    | R2       | alipaymini | 115生活_支付宝小程序 |
        +-------+----------+------------+----------------------+
        | 21    | S1       | harmony    | 115_鸿蒙端           |
        +-------+----------+------------+----------------------+
        """
        def gen_step():
            nonlocal app
            if not app:
                app = yield self.login_app(async_=async_, **request_kwargs)
            if not app:
                raise ValueError("can't determine the login app")
            uid: str = yield self.login_without_app(async_=async_, **request_kwargs)
            return self.login_qrcode_scan_result(
                uid, 
                app=app, 
                async_=async_, 
                **request_kwargs, 
            )
        return run_gen_step(gen_step, async_)

    @overload
    def login_without_app(
        self, 
        /, 
        show_warning: bool = False, 
        *, 
        async_: Literal[False] = False, 
        **request_kwargs, 
    ) -> str:
        ...
    @overload
    def login_without_app(
        self, 
        /, 
        show_warning: bool = False, 
        *, 
        async_: Literal[True], 
        **request_kwargs, 
    ) -> Coroutine[Any, Any, str]:
        ...
    def login_without_app(
        self, 
        /, 
        show_warning: bool = False, 
        *, 
        async_: Literal[False, True] = False, 
        **request_kwargs, 
    ) -> str | Coroutine[Any, Any, str]:
        """执行一次自动扫登录二维码，但不绑定设备，返回扫码的 uid，可用于之后绑定设备

        :param show_warning: 是否显示提示信息
        :param async_: 是否异步
        :param request_kwargs: 其余请求参数

        :return: 二维码的 uid
        """
        def gen_step():
            uid = check_response((yield self.login_qrcode_token( # type: ignore
                async_=async_, 
                **request_kwargs, 
            )))["data"]["uid"]
            resp = yield self.login_qrcode_scan(
                uid, 
                async_=async_, 
                **request_kwargs, 
            )
            check_response(resp)
            if show_warning:
                warn(f"qrcode scanned: {resp}", category=P115Warning)
            resp = yield self.login_qrcode_scan_confirm(
                uid, 
                async_=async_, 
                **request_kwargs, 
            )
            check_response(resp)
            return uid
        return run_gen_step(gen_step, async_)

    @overload
    def login_info_open(
        self, 
        /, 
        app_id: int | str = 100195125, 
        *, 
        async_: Literal[False] = False, 
        **request_kwargs, 
    ) -> dict:
        ...
    @overload
    def login_info_open(
        self, 
        /, 
        app_id: int | str = 100195125, 
        *, 
        async_: Literal[True], 
        **request_kwargs, 
    ) -> Coroutine[Any, Any, dict]:
        ...
    def login_info_open(
        self, 
        /, 
        app_id: int | str = 100195125, 
        *, 
        async_: Literal[False, True] = False, 
        **request_kwargs, 
    ) -> dict | Coroutine[Any, Any, dict]:
        """获取某个开放接口应用的信息（目前可获得名称和头像）

        :param app_id: AppID
        :param async_: 是否异步
        :param request_kwargs: 其余请求参数

        :return: 接口返回值
        """
        def gen_step():
            resp = yield self.login_qrcode_token_open(app_id, async_=async_, **request_kwargs)
            check_response(resp)
            login_uid = resp["data"]["uid"]
            resp = yield self.login_qrcode_scan(login_uid, async_=async_, **request_kwargs)
            check_response(resp)
            tip_txt = resp["data"]["tip_txt"]
            return {
                "app_id": app_id, 
                "name": tip_txt[:-10].removeprefix("\ufeff"), 
                "icon": resp["data"]["icon"], 
            }
        return run_gen_step(gen_step, async_)

    @overload
    def login_with_open(
        self, 
        /, 
        app_id: int | str = 100195125, 
        *, 
        show_warning: bool = False, 
        async_: Literal[False] = False, 
        **request_kwargs, 
    ) -> dict:
        ...
    @overload
    def login_with_open(
        self, 
        /, 
        app_id: int | str = 100195125, 
        *, 
        show_warning: bool = False, 
        async_: Literal[True], 
        **request_kwargs, 
    ) -> Coroutine[Any, Any, dict]:
        ...
    def login_with_open(
        self, 
        /, 
        app_id: int | str = 100195125, 
        *, 
        show_warning: bool = False, 
        async_: Literal[False, True] = False, 
        **request_kwargs, 
    ) -> dict | Coroutine[Any, Any, dict]:
        """登录某个开放接口应用

        .. note::
            同一个开放应用 id，最多同时有 2 个登入，如果有新的登录，则自动踢掉较早的那一个

        :param app_id: AppID
        :param show_warning: 是否显示提示信息
        :param async_: 是否异步
        :param request_kwargs: 其余请求参数

        :return: 接口返回值
        """
        def gen_step():
            resp = yield self.login_qrcode_token_open(app_id, async_=async_, **request_kwargs)
            check_response(resp)
            login_uid = resp["data"]["uid"]
            resp = yield self.login_qrcode_scan(login_uid, async_=async_, **request_kwargs)
            check_response(resp)
            if show_warning:
                warn(f"qrcode scanned: {resp}", category=P115Warning)
            resp = yield self.login_qrcode_scan_confirm(login_uid, async_=async_, **request_kwargs)
            check_response(resp)
            return self.login_qrcode_access_token_open(login_uid, async_=async_, **request_kwargs)
        return run_gen_step(gen_step, async_)

    @overload
    def login_another_app(
        self, 
        /, 
        app: None | str = None, 
        replace: bool | Self = False, 
        check_for_relogin: bool | Callable[[BaseException], bool | int] = False, 
        show_warning: bool = False, 
        *, 
        async_: Literal[False] = False, 
        **request_kwargs, 
    ) -> Self:
        ...
    @overload
    def login_another_app(
        self, 
        /, 
        app: None | str = None, 
        replace: bool | Self = False, 
        check_for_relogin: bool | Callable[[BaseException], bool | int] = False, 
        show_warning: bool = False, 
        *, 
        async_: Literal[True], 
        **request_kwargs, 
    ) -> Coroutine[Any, Any, Self]:
        ...
    def login_another_app(
        self, 
        /, 
        app: None | str = None, 
        replace: bool | Self = False, 
        check_for_relogin: bool | Callable[[BaseException], bool | int] = False, 
        show_warning: bool = False, 
        *, 
        async_: Literal[False, True] = False, 
        **request_kwargs, 
    ) -> Self | Coroutine[Any, Any, Self]:
        """登录某个设备（同一个设备可以有多个同时在线，但可以通过某些操作，把除了最近登录的那个都下线，也可以专门把最近登录那个也下线）

        .. hint::
            一个设备被新登录者下线，意味着这个 cookies 失效了，不能执行任何需要权限的操作

            但一个设备的新登录者，并不总是意味着把较早的登录者下线，一般需要触发某个检查机制后，才会把同一设备下除最近一次登录外的所有 cookies 失效

            所以你可以用一个设备的 cookies 专门用于扫码登录，获取另一个设备的 cookies 执行网盘操作，第 2 个 cookies 失效了，则用第 1 个 cookies 扫码，如此可避免单个 cookies 失效后，不能自动获取新的

        :param app: 要登录的 app，如果为 None，则用当前登录设备，如果无当前登录设备，则报错
        :param replace: 替换某个 client 对象的 cookie

            - 如果为 ``P115Client``, 则更新到此对象
            - 如果为 True，则更新到 `self`
            - 如果为 False，否则返回新的 ``P115Client`` 对象

        :param check_for_relogin: 网页请求抛出异常时，判断是否要重新登录并重试

            - 如果为 False，则不重试
            - 如果为 True，则自动通过判断 HTTP 响应码为 405 时重新登录并重试
            - 如果为 collections.abc.Callable，则调用以判断，当返回值为 bool 类型且值为 True，或者值为 405 时重新登录，然后循环此流程，直到成功或不可重试

        :param show_warning: 是否显示提示信息
        :param async_: 是否异步
        :param request_kwargs: 其余请求参数

        :return: 客户端实例

        -----

        :设备列表如下:

        +-------+----------+------------+----------------------+
        | No.   | ssoent   | app        | description          |
        +=======+==========+============+======================+
        | 01    | A1       | web        | 115生活_网页端       |
        +-------+----------+------------+----------------------+
        | --    | A1       | desktop    | 115浏览器            |
        +-------+----------+------------+----------------------+
        | --    | A2       | ?          | 未知: android        |
        +-------+----------+------------+----------------------+
        | --    | A3       | ?          | 未知: ios            |
        +-------+----------+------------+----------------------+
        | --    | A4       | ?          | 未知: ipad           |
        +-------+----------+------------+----------------------+
        | --    | B1       | ?          | 未知: android        |
        +-------+----------+------------+----------------------+
        | 02    | D1       | ios        | 115生活_苹果端       |
        +-------+----------+------------+----------------------+
        | 03    | D2       | bios       | 未知: ios            |
        +-------+----------+------------+----------------------+
        | 04    | D3       | 115ios     | 115_苹果端           |
        +-------+----------+------------+----------------------+
        | 05    | F1       | android    | 115生活_安卓端       |
        +-------+----------+------------+----------------------+
        | 06    | F2       | bandroid   | 未知: android        |
        +-------+----------+------------+----------------------+
        | 07    | F3       | 115android | 115_安卓端           |
        +-------+----------+------------+----------------------+
        | 08    | H1       | ipad       | 115生活_苹果平板端   |
        +-------+----------+------------+----------------------+
        | 09    | H2       | bipad      | 未知: ipad           |
        +-------+----------+------------+----------------------+
        | 10    | H3       | 115ipad    | 115_苹果平板端       |
        +-------+----------+------------+----------------------+
        | 11    | I1       | tv         | 115生活_安卓电视端   |
        +-------+----------+------------+----------------------+
        | 12    | I2       | apple_tv   | 115生活_苹果电视端   |
        +-------+----------+------------+----------------------+
        | 13    | M1       | qandriod   | 115管理_安卓端       |
        +-------+----------+------------+----------------------+
        | 14    | N1       | qios       | 115管理_苹果端       |
        +-------+----------+------------+----------------------+
        | 15    | O1       | qipad      | 115管理_苹果平板端   |
        +-------+----------+------------+----------------------+
        | 16    | P1       | os_windows | 115生活_Windows端    |
        +-------+----------+------------+----------------------+
        | 17    | P2       | os_mac     | 115生活_macOS端      |
        +-------+----------+------------+----------------------+
        | 18    | P3       | os_linux   | 115生活_Linux端      |
        +-------+----------+------------+----------------------+
        | 19    | R1       | wechatmini | 115生活_微信小程序端 |
        +-------+----------+------------+----------------------+
        | 20    | R2       | alipaymini | 115生活_支付宝小程序 |
        +-------+----------+------------+----------------------+
        | 21    | S1       | harmony    | 115_鸿蒙端           |
        +-------+----------+------------+----------------------+
        """
        def gen_step():
            nonlocal app
            if not app and isinstance(replace, P115Client):
                app = yield replace.login_app(async_=True)
            resp = yield self.login_with_app(
                app, 
                show_warning=show_warning, 
                async_=async_, 
                **request_kwargs, 
            )
            check_response(resp)
            cookies = resp["data"]["cookie"]
            ssoent = self.login_ssoent
            if isinstance(replace, P115Client):
                inst = replace
                setattr(inst, "cookies", cookies)
            elif replace:
                inst = self
                setattr(inst, "cookies", cookies)
            else:
                inst = type(self)(cookies, check_for_relogin=check_for_relogin)
            if self is not inst and ssoent == inst.login_ssoent:
                warn(f"login with the same ssoent {ssoent!r}, {self!r} will expire within 60 seconds", category=P115Warning)
            return inst
        return run_gen_step(gen_step, async_)

    @overload
    def login_another_open(
        self, 
        /, 
        app_id: int | str = 100195125, 
        *, 
        replace: Literal[True] | Self, 
        show_warning: bool = False, 
        async_: Literal[False] = False, 
        **request_kwargs, 
    ) -> Self:
        ...
    @overload
    def login_another_open(
        self, 
        /, 
        app_id: int | str = 100195125, 
        *, 
        replace: Literal[True] | Self, 
        show_warning: bool = False, 
        async_: Literal[True], 
        **request_kwargs, 
    ) -> Coroutine[Any, Any, Self]:
        ...
    @overload
    def login_another_open(
        self, 
        /, 
        app_id: int | str = 100195125, 
        *, 
        replace: Literal[False] = False, 
        show_warning: bool = False, 
        async_: Literal[False] = False, 
        **request_kwargs, 
    ) -> P115OpenClient:
        ...
    @overload
    def login_another_open(
        self, 
        /, 
        app_id: int | str = 100195125, 
        *, 
        replace: Literal[False] = False, 
        show_warning: bool = False, 
        async_: Literal[True], 
        **request_kwargs, 
    ) -> Coroutine[Any, Any, P115OpenClient]:
        ...
    def login_another_open(
        self, 
        /, 
        app_id: int | str = 100195125, 
        *, 
        replace: bool | Self = False, 
        show_warning: bool = False, 
        async_: Literal[False, True] = False, 
        **request_kwargs, 
    ) -> P115OpenClient | Coroutine[Any, Any, P115OpenClient] | Self | Coroutine[Any, Any, Self]:
        """登录某个开放接口应用

        :param app_id: AppID
        :param replace: 替换某个 client 对象的 `access_token` 和 `refresh_token`

            - 如果为 ``P115Client``, 则更新到此对象
            - 如果为 True，则更新到 `self`
            - 如果为 False，否则返回新的 ``P115Client`` 对象

        :param show_warning: 是否显示提示信息
        :param async_: 是否异步
        :param request_kwargs: 其余请求参数

        :return: 客户端实例
        """
        def gen_step():
            resp = yield self.login_with_open(
                app_id, 
                show_warning=show_warning, 
                async_=async_, 
                **request_kwargs, 
            )
            check_response(resp)
            data = resp["data"]
            if replace is False:
                inst: P115OpenClient | Self = P115OpenClient.from_token(data["access_token"], data["refresh_token"])
            else:
                if replace is True:
                    inst = self
                else:
                    inst = replace
                inst.refresh_token = data["refresh_token"]
                inst.access_token = data["access_token"]
            inst.app_id = app_id
            return inst
        return run_gen_step(gen_step, async_)

    @overload
    @classmethod
    def login_bind_app(
        cls, 
        /, 
        uid: str, 
        app: str = "alipaymini", 
        check_for_relogin: bool | Callable[[BaseException], bool | int] = False, 
        *, 
        async_: Literal[False] = False, 
        **request_kwargs, 
    ) -> Self:
        ...
    @overload
    @classmethod
    def login_bind_app(
        cls, 
        /, 
        uid: str, 
        app: str = "alipaymini", 
        check_for_relogin: bool | Callable[[BaseException], bool | int] = False, 
        *, 
        async_: Literal[True], 
        **request_kwargs, 
    ) -> Coroutine[Any, Any, Self]:
        ...
    @classmethod
    def login_bind_app(
        cls, 
        /, 
        uid: str, 
        app: str = "alipaymini", 
        check_for_relogin: bool | Callable[[BaseException], bool | int] = False, 
        *, 
        async_: Literal[False, True] = False, 
        **request_kwargs, 
    ) -> Self | Coroutine[Any, Any, Self]:
        """获取绑定到某个设备的 cookies

        .. hint::
            同一个设备可以有多个 cookies 同时在线

            其实只要你不主动去执行检查，这些 cookies 可以同时生效，只是看起来像“黑户”

        :param uid: 登录二维码的 uid
        :param app: 待绑定的设备名称
        :param check_for_relogin: 网页请求抛出异常时，判断是否要重新登录并重试

            - 如果为 False，则不重试
            - 如果为 True，则自动通过判断 HTTP 响应码为 405 时重新登录并重试
            - 如果为 collections.abc.Callable，则调用以判断，当返回值为 bool 类型且值为 True，或者值为 405 时重新登录，然后循环此流程，直到成功或不可重试

        :param async_: 是否异步
        :param request_kwargs: 其余请求参数

        :return: 新的实例

        -----

        :设备列表如下:

        +-------+----------+------------+----------------------+
        | No.   | ssoent   | app        | description          |
        +=======+==========+============+======================+
        | 01    | A1       | web        | 115生活_网页端       |
        +-------+----------+------------+----------------------+
        | --    | A1       | desktop    | 115浏览器            |
        +-------+----------+------------+----------------------+
        | --    | A2       | ?          | 未知: android        |
        +-------+----------+------------+----------------------+
        | --    | A3       | ?          | 未知: ios            |
        +-------+----------+------------+----------------------+
        | --    | A4       | ?          | 未知: ipad           |
        +-------+----------+------------+----------------------+
        | --    | B1       | ?          | 未知: android        |
        +-------+----------+------------+----------------------+
        | 02    | D1       | ios        | 115生活_苹果端       |
        +-------+----------+------------+----------------------+
        | 03    | D2       | bios       | 未知: ios            |
        +-------+----------+------------+----------------------+
        | 04    | D3       | 115ios     | 115_苹果端           |
        +-------+----------+------------+----------------------+
        | 05    | F1       | android    | 115生活_安卓端       |
        +-------+----------+------------+----------------------+
        | 06    | F2       | bandroid   | 未知: android        |
        +-------+----------+------------+----------------------+
        | 07    | F3       | 115android | 115_安卓端           |
        +-------+----------+------------+----------------------+
        | 08    | H1       | ipad       | 115生活_苹果平板端   |
        +-------+----------+------------+----------------------+
        | 09    | H2       | bipad      | 未知: ipad           |
        +-------+----------+------------+----------------------+
        | 10    | H3       | 115ipad    | 115_苹果平板端       |
        +-------+----------+------------+----------------------+
        | 11    | I1       | tv         | 115生活_安卓电视端   |
        +-------+----------+------------+----------------------+
        | 12    | I2       | apple_tv   | 115生活_苹果电视端   |
        +-------+----------+------------+----------------------+
        | 13    | M1       | qandriod   | 115管理_安卓端       |
        +-------+----------+------------+----------------------+
        | 14    | N1       | qios       | 115管理_苹果端       |
        +-------+----------+------------+----------------------+
        | 15    | O1       | qipad      | 115管理_苹果平板端   |
        +-------+----------+------------+----------------------+
        | 16    | P1       | os_windows | 115生活_Windows端    |
        +-------+----------+------------+----------------------+
        | 17    | P2       | os_mac     | 115生活_macOS端      |
        +-------+----------+------------+----------------------+
        | 18    | P3       | os_linux   | 115生活_Linux端      |
        +-------+----------+------------+----------------------+
        | 19    | R1       | wechatmini | 115生活_微信小程序端 |
        +-------+----------+------------+----------------------+
        | 20    | R2       | alipaymini | 115生活_支付宝小程序 |
        +-------+----------+------------+----------------------+
        | 21    | S1       | harmony    | 115_鸿蒙端           |
        +-------+----------+------------+----------------------+
        """
        def gen_step():
            resp = yield cls.login_qrcode_scan_result(
                uid, 
                app=app, 
                async_=async_, 
                **request_kwargs, 
            )
            check_response(resp)
            cookies = resp["data"]["cookie"]
            return cls(cookies, check_for_relogin=check_for_relogin)
        return run_gen_step(gen_step, async_)

    @overload
    def logout(
        self, 
        /, 
        async_: Literal[False] = False, 
        **request_kwargs, 
    ) -> Any:
        ...
    @overload
    def logout(
        self, 
        /, 
        async_: Literal[True], 
        **request_kwargs, 
    ) -> Coroutine[Any, Any, Any]:
        ...
    def logout(
        self, 
        /, 
        async_: Literal[False, True] = False, 
        **request_kwargs, 
    ) -> Any | Coroutine[Any, Any, Any]:
        """退出当前设备的登录状态
        """
        ssoent = self.login_ssoent
        if not ssoent:
            if async_:
                async def none():
                    return None
                return none()
            else:
                return None
        return self.logout_by_ssoent(ssoent, async_=async_, **request_kwargs)

    def request(
        self, 
        /, 
        url: str, 
        method: str = "GET", 
        payload: Any = None, 
        *, 
        ecdh_encrypt: bool = False, 
        fetch_cert_headers: None | Callable[..., Mapping] | Callable[..., Awaitable[Mapping]] = None, 
        revert_cert_headers: None | Callable[[Mapping], Any] = None, 
        request: None | Callable = None, 
        async_: Literal[False, True] = False, 
        **request_kwargs, 
    ):
        """执行网络请求

        :param url: HTTP 的请求链接
        :param method: HTTP 的请求方法
        :param payload: HTTP 的请求载体（如果 `method` 是 "POST"，则作为请求体，否则作为查询参数）
        :param ecdh_encrypt: 是否使用 ecdh 算法进行加密（返回值需要解密）
        :param fetch_cert_headers: 调用以获取认证信息头
        :param revert_cert_headers: 调用以退还认证信息头
        :param request: HTTP 请求调用，如果为 None，则用默认设置
            如果传入调用，则必须至少能接受以下几个关键词参数：

            - url:     HTTP 的请求链接
            - method:  HTTP 的请求方法
            - params:  HTTP 的请求链接附加的查询参数
            - data:    HTTP 的请求体
            - json:    JSON 数据（往往未被序列化）作为请求体
            - files:   要用 multipart 上传的若干文件
            - headers: HTTP 的请求头
            - follow_redirects: 是否跟进重定向，默认值为 True
            - raise_for_status: 是否对响应码 >= 400 时抛出异常
            - cookies: 至少能接受 ``http.cookiejar.CookieJar`` 和 ``http.cookies.BaseCookie``，会因响应头的 "set-cookie" 而更新
            - parse:   解析 HTTP 响应的方法，默认会构建一个 Callable，会把响应的字节数据视为 JSON 进行反序列化解析

                - 如果为 None，则直接把响应对象返回
                - 如果为 ...(Ellipsis)，则把响应对象关闭后将其返回
                - 如果为 True，则根据响应头来确定把响应得到的字节数据解析成何种格式（反序列化），请求也会被自动关闭
                - 如果为 False，则直接返回响应得到的字节数据，请求也会被自动关闭
                - 如果为 Callable，则使用此调用来解析数据，接受 1-2 个位置参数，并把解析结果返回给 `request` 的调用者，请求也会被自动关闭
                    - 如果只接受 1 个位置参数，则把响应对象传给它
                    - 如果能接受 2 个位置参数，则把响应对象和响应得到的字节数据（响应体）传给它

        :param async_: 是否异步
        :param request_kwargs: 其余请求参数

        :return: 直接返回 `request` 执行请求后的返回值

        .. note:: 
            `request` 可以由不同的请求库来提供，下面是封装了一些模块

            1. `httpcore_request <https://pypi.org/project/httpcore_request/>`_，由 `httpcore <https://pypi.org/project/httpcore/>`_ 封装，支持同步和异步请求

                .. code:: python

                    from httpcore_request import request

            2. `httpx_request <https://pypi.org/project/httpx_request/>`_，由 `httpx <https://pypi.org/project/httpx/>`_ 封装，支持同步和异步请求

                .. code:: python

                    from httpx_request import request

            3. `http_client_request <https://pypi.org/project/http_client_request/>`_，由 `http.client <https://docs.python.org/3/library/http.client.html>`_ 封装，支持同步请求

                .. code:: python

                    from http_client_request import request

            4. `python-urlopen <https://pypi.org/project/python-urlopen/>`_，由 `urllib.request.urlopen <https://docs.python.org/3/library/urllib.request.html#urllib.request.urlopen>`_ 封装，支持同步请求

                .. code:: python

                    from urlopen import request

            5. `urllib3_request <https://pypi.org/project/urllib3_request/>`_，由 `urllib3 <https://pypi.org/project/urllib3/>`_ 封装，支持同步请求

                .. code:: python

                    from urllib3_request import request

            6. `requests_request <https://pypi.org/project/requests_request/>`_，由 `requests <https://pypi.org/project/requests/>`_ 封装，支持同步请求

                .. code:: python

                    from requests_request import request

            7. `aiohttp_client_request <https://pypi.org/project/aiohttp_client_request/>`_，由 `aiohttp <https://pypi.org/project/aiohttp/>`_ 封装，支持异步请求

                .. code:: python

                    from aiohttp_client_request import request

            8. `blacksheep_client_request <https://pypi.org/project/blacksheep_client_request/>`_，由 `blacksheep <https://pypi.org/project/blacksheep/>`_ 封装，支持异步请求

                .. code:: python

                    from blacksheep_client_request import request

            9. `asks_request <https://pypi.org/project/asks_request/>`_，由 `asks <https://pypi.org/project/asks/>`_ 封装，支持异步请求

                .. code:: python

                    from asks_request import request

            10. `pycurl_request <https://pypi.org/project/pycurl_request/>`_，由 `pycurl <https://pypi.org/project/pycurl/>`_ 封装，支持同步请求

                .. code:: python

                    from pycurl_request import request

            11. `curl_cffi_request <https://pypi.org/project/curl_cffi_request/>`_，由 `curl_cffi <https://pypi.org/project/curl_cffi/>`_ 封装，支持同步和异步请求

                .. code:: python

                    from curl_cffi_request import request

            12. `aiosonic_request <https://pypi.org/project/aiosonic_request/>`_，由 `aiosonic <https://pypi.org/project/aiosonic/>`_ 封装，支持异步请求

                .. code:: python

                    from aiosonic_request import request

            13. `tornado_client_request <https://pypi.org/project/tornado_client_request/>`_，由 `tornado <https://www.tornadoweb.org/en/latest/httpclient.html>`_ 封装，支持同步和异步请求

                .. code:: python

                    from tornado_client_request import request
        """
        is_open_api = url.startswith("https://proapi.115.com/open/")
        if is_open_api:
            ecdh_encrypt = False
        if payload is not None:
            if method.upper() == "POST":
                request_kwargs.setdefault("data", payload)
            else:
                request_kwargs.setdefault("params", payload)
        request_kwargs["request"] = request
        request = get_request(async_, request_kwargs)
        check_for_relogin = self.check_for_relogin
        headers = dict(request_kwargs.get("headers") or ())
        need_to_check = callable(check_for_relogin)
        if need_to_check and fetch_cert_headers is None:
            if is_open_api:
                need_to_check = "authorization" not in headers
            else:
                need_to_check = "cookie" not in headers
        headers = request_kwargs["headers"] = dict_key_to_lower_merge(headers, self.headers)
        if is_open_api:
            headers["cookie"] = ""
        else:
            request_kwargs.setdefault("cookies", self.cookies)
        if ecdh_encrypt and (data := request_kwargs.get("data")):
            url = make_url(url, params=_default_k_ec)
            if not isinstance(data, (Buffer, str, UserString)):
                data = urlencode(data)
            request_kwargs["data"] = ecdh_aes_encrypt(ensure_bytes(data) + b"&")
            headers["content-type"] = "application/x-www-form-urlencoded"
        need_fetch_cert_first = False
        if fetch_cert_headers is not None:
            fetch_cert_headers_argcount = argcount(fetch_cert_headers)
            if async_:
                fetch_cert_headers = ensure_async(fetch_cert_headers)
            if fetch_cert_headers_argcount:
                fetch_cert_headers = cast(Callable, fetch_cert_headers)(async_)
            if revert_cert_headers is not None and async_:
                revert_cert_headers = ensure_async(revert_cert_headers)
            if is_open_api:
                need_fetch_cert_first = "authorization" not in headers
            else:
                need_fetch_cert_first = "cookie" not in headers
        def gen_step():
            cert_headers: None | Mapping = None
            if need_fetch_cert_first:
                cert_headers = yield cast(Callable, fetch_cert_headers)()
                headers.update(cert_headers)
            if async_:
                lock: Lock | AsyncLock = self.request_alock
            else:
                lock = self.request_lock
            if is_open_api:
                if "authorization" not in headers:
                    yield lock.acquire()
                    try:
                        yield self.login_another_open(
                            async_=async_, # type: ignore
                        )
                    finally:
                        lock.release()
            elif "cookie" not in headers:
                headers["cookie"] = self.cookies_str
            for i in count(0):
                try:
                    if fetch_cert_headers is None:
                        if is_open_api:
                            cert: str = headers["authorization"]
                        else:
                            cert = headers["cookie"]
                    resp = yield cast(Callable, request)(
                        url=url, 
                        method=method, 
                        **request_kwargs, 
                    )
                    if (
                        is_open_api and 
                        need_to_check and 
                        isinstance(resp, dict) and 
                        resp.get("code") in (40140123, 40140124, 40140125, 40140126)
                    ):
                        check_response(resp)
                except BaseException as e:
                    is_auth_error = isinstance(e, (P115AuthenticationError, P115LoginError))
                    not_access_token_error = not isinstance(e, P115AccessTokenError)
                    if (
                        cert_headers is not None and 
                        revert_cert_headers is not None and 
                        not is_auth_error and
                        get_status_code(e) != 405
                    ):
                        yield revert_cert_headers(cert_headers)
                    if not need_to_check:
                        raise
                    if not_access_token_error:
                        res = yield cast(Callable, check_for_relogin)(e)
                        if not res if isinstance(res, bool) else res != 405:
                            raise
                    if fetch_cert_headers is not None:
                        cert_headers = yield fetch_cert_headers()
                        headers.update(cert_headers)
                    elif is_open_api:
                        yield lock.acquire()
                        try:
                            access_token = self.access_token
                            if cert.capitalize().removeprefix("Bearer ") == access_token:
                                if i or is_auth_error or not_access_token_error:
                                    raise
                                warn(f"relogin to refresh token", category=P115Warning)
                                yield self.refresh_access_token(async_=async_)
                                cert = headers["authorization"] = "Bearer " + self.access_token
                            else:
                                cert = headers["authorization"] = "Bearer " + access_token
                        finally:
                            lock.release()
                    else:
                        yield lock.acquire()
                        try:
                            cookies_new: str = self.cookies_str
                            if cert == cookies_new:
                                if self.__dict__.get("cookies_path"):
                                    cookies_new = self._read_cookies() or ""
                                    if cert != cookies_new:
                                        headers["cookie"] = cookies_new
                                        continue
                                if i or is_auth_error:
                                    raise
                                m = CRE_COOKIES_UID_search(cert)
                                uid = "" if m is None else m[0]
                                if not uid:
                                    raise
                                warn(f"relogin to refresh cookies: UID={uid!r} app={self.login_app()!r}", category=P115Warning)
                                yield self.login_another_app(
                                    replace=True, 
                                    async_=async_, # type: ignore
                                )
                                cert = headers["cookie"] = self.cookies_str
                            else:
                                cert = headers["cookie"] = cookies_new
                        finally:
                            lock.release()
                else:
                    if cert_headers is not None and revert_cert_headers is not None:
                        yield revert_cert_headers(cert_headers)
                    return resp
        return run_gen_step(gen_step, async_)
 
    @overload
    def open(
        self, 
        /, 
        url: str | Callable[[], str], 
        start: int = 0, 
        seek_threshold: int = 1 << 20, 
        headers: None | Mapping = None, 
        http_file_reader_cls: None | type[HTTPFileReader] = None, 
        *, 
        async_: Literal[False] = False, 
    ) -> HTTPFileReader:
        ...
    @overload
    def open(
        self, 
        /, 
        url: str | Callable[[], str] | Callable[[], Awaitable[str]], 
        start: int = 0, 
        seek_threshold: int = 1 << 20, 
        headers: None | Mapping = None, 
        http_file_reader_cls: None | type[AsyncHTTPFileReader] = None, 
        *, 
        async_: Literal[True], 
    ) -> AsyncHTTPFileReader:
        ...
    def open(
        self, 
        /, 
        url: str | Callable[[], str] | Callable[[], Awaitable[str]], 
        start: int = 0, 
        seek_threshold: int = 1 << 20, 
        headers: None | Mapping = None, 
        http_file_reader_cls: None | type[HTTPFileReader] | type[AsyncHTTPFileReader] = None, 
        *, 
        async_: Literal[False, True] = False, 
    ) -> HTTPFileReader | AsyncHTTPFileReader:
        """打开下载链接，返回文件对象

        :param url: 115 文件的下载链接（可以从网盘、网盘上的压缩包内、分享链接中获取）

            - P115Client.download_url
            - P115Client.share_download_url
            - P115Client.extract_download_url

        :param start: 开始索引
        :param seek_threshold: 当向前 seek 的偏移量不大于此值时，调用 read 来移动文件位置（可避免重新建立连接）
        :param http_file_reader_cls: 返回的文件对象的类，需要是 `httpfile.HTTPFileReader` 的子类
        :param headers: 请求头
        :param async_: 是否异步

        :return: 返回打开的文件对象，可以读取字节数据
        """
        request_headers = self.headers.copy()
        if isinstance(url, P115URL):
            request_headers.update(url.get("headers") or ())
        if headers:
            request_headers.update(headers)
        if async_:
            if http_file_reader_cls is None:
                from httpfile import AsyncHTTPFileReader
                http_file_reader_cls = AsyncHTTPFileReader
            return http_file_reader_cls(
                url, # type: ignore
                headers=request_headers, 
                start=start, 
                seek_threshold=seek_threshold, 
            )
        else:
            if http_file_reader_cls is None:
                http_file_reader_cls = HTTPFileReader
            return http_file_reader_cls(
                url, # type: ignore
                headers=request_headers, 
                start=start, 
                seek_threshold=seek_threshold, 
            )

    ########## Activity API ##########

    @overload
    def act_xys_adopt(
        self, 
        payload: dict, 
        /, 
        app: str = "web", 
        base_url: str | Callable[[], str] = "https://act.115.com", 
        *, 
        async_: Literal[False] = False, 
        **request_kwargs, 
    ) -> dict:
        ...
    @overload
    def act_xys_adopt(
        self, 
        payload: dict, 
        /, 
        app: str = "web", 
        base_url: str | Callable[[], str] = "https://act.115.com", 
        *, 
        async_: Literal[True], 
        **request_kwargs, 
    ) -> Coroutine[Any, Any, dict]:
        ...
    def act_xys_adopt(
        self, 
        payload: dict, 
        /, 
        app: str = "web", 
        base_url: str | Callable[[], str] = "https://act.115.com", 
        *, 
        async_: Literal[False, True] = False, 
        **request_kwargs, 
    ) -> dict | Coroutine[Any, Any, dict]:
        """采纳助愿

        POST https://act.115.com/api/1.0/web/1.0/act2024xys/adopt

        :payload:
            - did: str 💡 许愿的 id
            - aid: int | str 💡 助愿的 id
            - to_cid: int = <default> 💡 助愿中的分享链接转存到你的网盘中目录的 id
        """
        api = complete_url(f"/api/1.0/{app}/1.0/act2024xys/adopt", base_url=base_url)
        return self.request(url=api, method="POST", data=payload, async_=async_, **request_kwargs)

    @overload
    def act_xys_aid_desire(
        self, 
        payload: dict, 
        /, 
        app: str = "web", 
        base_url: str | Callable[[], str] = "https://act.115.com", 
        *, 
        async_: Literal[False] = False, 
        **request_kwargs, 
    ) -> dict:
        ...
    @overload
    def act_xys_aid_desire(
        self, 
        payload: dict, 
        /, 
        app: str = "web", 
        base_url: str | Callable[[], str] = "https://act.115.com", 
        *, 
        async_: Literal[True], 
        **request_kwargs, 
    ) -> Coroutine[Any, Any, dict]:
        ...
    def act_xys_aid_desire(
        self, 
        payload: dict, 
        /, 
        app: str = "web", 
        base_url: str | Callable[[], str] = "https://act.115.com", 
        *, 
        async_: Literal[False, True] = False, 
        **request_kwargs, 
    ) -> dict | Coroutine[Any, Any, dict]:
        """创建助愿（如果提供 file_ids，则会创建一个分享链接）

        POST https://act.115.com/api/1.0/web/1.0/act2024xys/aid_desire

        :payload:
            - id: str 💡 许愿 id
            - content: str 💡 助愿文本，不少于 5 个字，不超过 500 个字
            - images: int | str = <default> 💡 图片文件在你的网盘的 id，多个用逗号 "," 隔开
            - file_ids: int | str = <default> 💡 文件在你的网盘的 id，多个用逗号 "," 隔开
        """
        api = complete_url(f"/api/1.0/{app}/1.0/act2024xys/aid_desire", base_url=base_url)
        return self.request(url=api, method="POST", data=payload, async_=async_, **request_kwargs)

    @overload
    def act_xys_aid_desire_del(
        self, 
        payload: int | str | dict, 
        /, 
        app: str = "web", 
        base_url: str | Callable[[], str] = "https://act.115.com", 
        *, 
        async_: Literal[False] = False, 
        **request_kwargs, 
    ) -> dict:
        ...
    @overload
    def act_xys_aid_desire_del(
        self, 
        payload: int | str | dict, 
        /, 
        app: str = "web", 
        base_url: str | Callable[[], str] = "https://act.115.com", 
        *, 
        async_: Literal[True], 
        **request_kwargs, 
    ) -> Coroutine[Any, Any, dict]:
        ...
    def act_xys_aid_desire_del(
        self, 
        payload: int | str | dict, 
        /, 
        app: str = "web", 
        base_url: str | Callable[[], str] = "https://act.115.com", 
        *, 
        async_: Literal[False, True] = False, 
        **request_kwargs, 
    ) -> dict | Coroutine[Any, Any, dict]:
        """删除助愿

        POST https://act.115.com/api/1.0/web/1.0/act2024xys/del_aid_desire

        :payload:
            - ids: int | str 💡 助愿的 id，多个用逗号 "," 隔开
        """
        api = complete_url(f"/api/1.0/{app}/1.0/act2024xys/del_aid_desire", base_url=base_url)
        if isinstance(payload, (int, str)):
            payload = {"ids": payload}
        return self.request(url=api, method="POST", data=payload, async_=async_, **request_kwargs)

    @overload
    def act_xys_desire_aid_list(
        self, 
        payload: str | dict, 
        /, 
        app: str = "web", 
        base_url: str | Callable[[], str] = "https://act.115.com", 
        *, 
        async_: Literal[False] = False, 
        **request_kwargs, 
    ) -> dict:
        ...
    @overload
    def act_xys_desire_aid_list(
        self, 
        payload: str | dict, 
        /, 
        app: str = "web", 
        base_url: str | Callable[[], str] = "https://act.115.com", 
        *, 
        async_: Literal[True], 
        **request_kwargs, 
    ) -> Coroutine[Any, Any, dict]:
        ...
    def act_xys_desire_aid_list(
        self, 
        payload: str | dict, 
        /, 
        app: str = "web", 
        base_url: str | Callable[[], str] = "https://act.115.com", 
        *, 
        async_: Literal[False, True] = False, 
        **request_kwargs, 
    ) -> dict | Coroutine[Any, Any, dict]:
        """获取许愿的助愿列表

        GET https://act.115.com/api/1.0/web/1.0/act2024xys/desire_aid_list

        :payload:
            - id: str         💡 许愿的 id
            - start: int = 0  💡 开始索引
            - page: int = 1   💡 第几页
            - limit: int = 10 💡 分页大小
            - sort: int | str = <default> 💡 排序
        """
        api = complete_url(f"/api/1.0/{app}/1.0/act2024xys/desire_aid_list", base_url=base_url)
        if isinstance(payload, str):
            payload = {"id": payload}
        payload = {"start": 0, "page": 1, "limit": 10, **payload}
        return self.request(url=api, params=payload, async_=async_, **request_kwargs)

    @overload
    def act_xys_get_act_info(
        self, 
        /, 
        app: str = "web", 
        base_url: str | Callable[[], str] = "https://act.115.com", 
        *, 
        async_: Literal[False] = False, 
        **request_kwargs, 
    ) -> dict:
        ...
    @overload
    def act_xys_get_act_info(
        self, 
        /, 
        app: str = "web", 
        base_url: str | Callable[[], str] = "https://act.115.com", 
        *, 
        async_: Literal[True], 
        **request_kwargs, 
    ) -> Coroutine[Any, Any, dict]:
        ...
    def act_xys_get_act_info(
        self, 
        /, 
        app: str = "web", 
        base_url: str | Callable[[], str] = "https://act.115.com", 
        *, 
        async_: Literal[False, True] = False, 
        **request_kwargs, 
    ) -> dict | Coroutine[Any, Any, dict]:
        """获取许愿树活动的信息

        GET https://act.115.com/api/1.0/web/1.0/act2024xys/get_act_info
        """
        api = complete_url(f"/api/1.0/{app}/1.0/act2024xys/get_act_info", base_url=base_url)
        return self.request(url=api, async_=async_, **request_kwargs)

    @overload
    def act_xys_get_desire_info(
        self, 
        payload: str | dict, 
        /, 
        app: str = "web", 
        base_url: str | Callable[[], str] = "https://act.115.com", 
        *, 
        async_: Literal[False] = False, 
        **request_kwargs, 
    ) -> dict:
        ...
    @overload
    def act_xys_get_desire_info(
        self, 
        payload: str | dict, 
        /, 
        app: str = "web", 
        base_url: str | Callable[[], str] = "https://act.115.com", 
        *, 
        async_: Literal[True], 
        **request_kwargs, 
    ) -> Coroutine[Any, Any, dict]:
        ...
    def act_xys_get_desire_info(
        self, 
        payload: str | dict, 
        /, 
        app: str = "web", 
        base_url: str | Callable[[], str] = "https://act.115.com", 
        *, 
        async_: Literal[False, True] = False, 
        **request_kwargs, 
    ) -> dict | Coroutine[Any, Any, dict]:
        """获取的许愿信息

        GET https://act.115.com/api/1.0/web/1.0/act2024xys/get_desire_info

        :payload:
            - id: str 💡 许愿的 id
        """
        api = complete_url(f"/api/1.0/{app}/1.0/act2024xys/get_desire_info", base_url=base_url)
        if isinstance(payload, str):
            payload = {"id": payload}
        return self.request(url=api, params=payload, async_=async_, **request_kwargs)

    @overload
    def act_xys_home_list(
        self, 
        /, 
        app: str = "web", 
        base_url: str | Callable[[], str] = "https://act.115.com", 
        *, 
        async_: Literal[False] = False, 
        **request_kwargs, 
    ) -> dict:
        ...
    @overload
    def act_xys_home_list(
        self, 
        /, 
        app: str = "web", 
        base_url: str | Callable[[], str] = "https://act.115.com", 
        *, 
        async_: Literal[True], 
        **request_kwargs, 
    ) -> Coroutine[Any, Any, dict]:
        ...
    def act_xys_home_list(
        self, 
        /, 
        app: str = "web", 
        base_url: str | Callable[[], str] = "https://act.115.com", 
        *, 
        async_: Literal[False, True] = False, 
        **request_kwargs, 
    ) -> dict | Coroutine[Any, Any, dict]:
        """首页的许愿树（随机刷新 15 条）

        GET https://act.115.com/api/1.0/web/1.0/act2024xys/home_list
        """
        api = complete_url(f"/api/1.0/{app}/1.0/act2024xys/home_list", base_url=base_url)
        return self.request(url=api, async_=async_, **request_kwargs)

    @overload
    def act_xys_my_aid_desire(
        self, 
        payload: int | str | dict = 0, 
        /, 
        app: str = "web", 
        base_url: str | Callable[[], str] = "https://act.115.com", 
        *, 
        async_: Literal[False] = False, 
        **request_kwargs, 
    ) -> dict:
        ...
    @overload
    def act_xys_my_aid_desire(
        self, 
        payload: int | str | dict = 0, 
        /, 
        app: str = "web", 
        base_url: str | Callable[[], str] = "https://act.115.com", 
        *, 
        async_: Literal[True], 
        **request_kwargs, 
    ) -> Coroutine[Any, Any, dict]:
        ...
    def act_xys_my_aid_desire(
        self, 
        payload: int | str | dict = 0, 
        /, 
        app: str = "web", 
        base_url: str | Callable[[], str] = "https://act.115.com", 
        *, 
        async_: Literal[False, True] = False, 
        **request_kwargs, 
    ) -> dict | Coroutine[Any, Any, dict]:
        """我的助愿列表

        GET https://act.115.com/api/1.0/web/1.0/act2024xys/my_aid_desire

        :payload:
            - type: 0 | 1 | 2 = 0 💡 类型

                - 0: 全部
                - 1: 进行中
                - 2: 已实现

            - start: int = 0  💡 开始索引
            - page: int = 1   💡 第几页
            - limit: int = 10 💡 分页大小
        """
        api = complete_url(f"/api/1.0/{app}/1.0/act2024xys/my_aid_desire", base_url=base_url)
        if isinstance(payload, (int, str)):
            payload = {"type": payload}
        payload = {"type": 0, "start": 0, "page": 1, "limit": 10, **payload}
        return self.request(url=api, params=payload, async_=async_, **request_kwargs)

    @overload
    def act_xys_my_desire(
        self, 
        payload: int | str | dict = 0, 
        /, 
        app: str = "web", 
        base_url: str | Callable[[], str] = "https://act.115.com", 
        *, 
        async_: Literal[False] = False, 
        **request_kwargs, 
    ) -> dict:
        ...
    @overload
    def act_xys_my_desire(
        self, 
        payload: int | str | dict = 0, 
        /, 
        app: str = "web", 
        base_url: str | Callable[[], str] = "https://act.115.com", 
        *, 
        async_: Literal[True], 
        **request_kwargs, 
    ) -> Coroutine[Any, Any, dict]:
        ...
    def act_xys_my_desire(
        self, 
        payload: int | str | dict = 0, 
        /, 
        app: str = "web", 
        base_url: str | Callable[[], str] = "https://act.115.com", 
        *, 
        async_: Literal[False, True] = False, 
        **request_kwargs, 
    ) -> dict | Coroutine[Any, Any, dict]:
        """我的许愿列表

        GET https://act.115.com/api/1.0/web/1.0/act2024xys/my_desire

        :payload:
            - type: 0 | 1 | 2 = 0 💡 类型

                - 0: 全部
                - 1: 进行中
                - 2: 已实现

            - start: int = 0  💡 开始索引
            - page: int = 1   💡 第几页
            - limit: int = 10 💡 分页大小
        """
        api = complete_url(f"/api/1.0/{app}/1.0/act2024xys/my_desire", base_url=base_url)
        if isinstance(payload, (int, str)):
            payload = {"type": payload}
        payload = {"type": 0, "start": 0, "page": 1, "limit": 10, **payload}
        return self.request(url=api, params=payload, async_=async_, **request_kwargs)

    @overload
    def act_xys_wish(
        self, 
        payload: str | dict, 
        /, 
        app: str = "web", 
        base_url: str | Callable[[], str] = "https://act.115.com", 
        *, 
        async_: Literal[False] = False, 
        **request_kwargs, 
    ) -> dict:
        ...
    @overload
    def act_xys_wish(
        self, 
        payload: str | dict, 
        /, 
        app: str = "web", 
        base_url: str | Callable[[], str] = "https://act.115.com", 
        *, 
        async_: Literal[True], 
        **request_kwargs, 
    ) -> Coroutine[Any, Any, dict]:
        ...
    def act_xys_wish(
        self, 
        payload: str | dict, 
        /, 
        app: str = "web", 
        base_url: str | Callable[[], str] = "https://act.115.com", 
        *, 
        async_: Literal[False, True] = False, 
        **request_kwargs, 
    ) -> dict | Coroutine[Any, Any, dict]:
        """创建许愿

        POST https://act.115.com/api/1.0/web/1.0/act2024xys/wish

        :payload:
            - content: str 💡 许愿文本，不少于 5 个字，不超过 500 个字
            - rewardSpace: int = 5 💡 奖励容量，单位是 GB
            - images: int | str = <default> 💡 图片文件在你的网盘的 id，多个用逗号 "," 隔开
        """
        api = complete_url(f"/api/1.0/{app}/1.0/act2024xys/wish", base_url=base_url)
        if isinstance(payload, str):
            payload = {"content": payload}
        payload.setdefault("rewardSpace", 5)
        return self.request(url=api, method="POST", data=payload, async_=async_, **request_kwargs)

    @overload
    def act_xys_wish_del(
        self, 
        payload: str | dict, 
        /, 
        app: str = "web", 
        base_url: str | Callable[[], str] = "https://act.115.com", 
        *, 
        async_: Literal[False] = False, 
        **request_kwargs, 
    ) -> dict:
        ...
    @overload
    def act_xys_wish_del(
        self, 
        payload: str | dict, 
        /, 
        app: str = "web", 
        base_url: str | Callable[[], str] = "https://act.115.com", 
        *, 
        async_: Literal[True], 
        **request_kwargs, 
    ) -> Coroutine[Any, Any, dict]:
        ...
    def act_xys_wish_del(
        self, 
        payload: str | dict, 
        /, 
        app: str = "web", 
        base_url: str | Callable[[], str] = "https://act.115.com", 
        *, 
        async_: Literal[False, True] = False, 
        **request_kwargs, 
    ) -> dict | Coroutine[Any, Any, dict]:
        """删除许愿

        POST https://act.115.com/api/1.0/web/1.0/act2024xys/del_wish

        :payload:
            - ids: str 💡 许愿的 id，多个用逗号 "," 隔开
        """
        api = complete_url(f"/api/1.0/{app}/1.0/act2024xys/del_wish", base_url=base_url)
        if isinstance(payload, str):
            payload = {"ids": payload}
        return self.request(url=api, method="POST", data=payload, async_=async_, **request_kwargs)

    ########## App API ##########

    @overload
    def app_area_list(
        self: None | ClientRequestMixin = None, 
        /, 
        base_url: str | Callable[[], str] = "https://cdnres.115.com", 
        *, 
        async_: Literal[False] = False, 
        **request_kwargs
    ) -> dict:
        ...
    @overload
    def app_area_list(
        self: None | ClientRequestMixin = None, 
        /, 
        base_url: str | Callable[[], str] = "https://cdnres.115.com", 
        *, 
        async_: Literal[True], 
        **request_kwargs
    ) -> Coroutine[Any, Any, dict]:
        ...
    def app_area_list(
        self: None | ClientRequestMixin = None, 
        /, 
        base_url: str | Callable[[], str] = "https://cdnres.115.com", 
        *, 
        async_: Literal[False, True] = False, 
        **request_kwargs
    ) -> dict | Coroutine[Any, Any, dict]:
        """获取地区编码列表

        GET https://cdnres.115.com/my/m_r/setting_new/js/ylmf_area.js

        .. note::
            可以作为 ``staticmethod`` 使用
        """
        api = complete_url("/my/m_r/setting_new/js/ylmf_area.js", base_url=base_url)
        def iter_area(data: dict, /) -> Iterator[tuple[int, str]]:
            for code, detail in data.items():
                if isinstance(code, str):
                    continue
                if isinstance(detail, dict):
                    yield code, detail["n"]
                    for key in ("c", "t"):
                        if key in detail and detail[key]:
                            yield from iter_area(detail[key])
                            break
                else:
                    yield code, detail
        def parse(_, content, /):
            data_str = cast(Match[str], CRE_AREA_DATA_search(content.decode("utf-8")))[0]
            data = eval(data_str, {"n": "n", "c": "c", "t": "t", "l": "l"})
            return {"state": True, "data": list(iter_area(data))}
        request_kwargs.setdefault("parse", parse)
        return get_request(async_, request_kwargs, self=self)(url=api, **request_kwargs)

    @overload
    def app_publick_key(
        self: None | ClientRequestMixin = None, 
        /, 
        app: str = "web", 
        base_url: str | Callable[[], str] = "https://passportapi.115.com", 
        *, 
        async_: Literal[False] = False, 
        **request_kwargs
    ) -> dict:
        ...
    @overload
    def app_publick_key(
        self: None | ClientRequestMixin = None, 
        /, 
        app: str = "web", 
        base_url: str | Callable[[], str] = "https://passportapi.115.com", 
        *, 
        async_: Literal[True], 
        **request_kwargs
    ) -> Coroutine[Any, Any, dict]:
        ...
    def app_publick_key(
        self: None | ClientRequestMixin = None, 
        /, 
        app: str = "web", 
        base_url: str | Callable[[], str] = "https://passportapi.115.com", 
        *, 
        async_: Literal[False, True] = False, 
        **request_kwargs
    ) -> dict | Coroutine[Any, Any, dict]:
        """获取 RSA 加密公钥，用于某些情况下的加密

        GET https://passportapi.115.com/app/1.0/web/1.0/login/getKey

        .. note::
            可以作为 ``staticmethod`` 使用

            返回的公钥是签名证书，并经过 BASE64 处理，可用下面步骤还原

            .. code::

                from base64 import b64decode
                from p115client import P115Client

                resp = P115Client.app_publick_key()
                perm = b64decode(resp["data"]["key"])

                # pip install pycryptodome
                from Crypto.PublicKey import RSA

                pubkey = RSA.import_key(perm)
                print(repr(pubkey))
        """
        api = complete_url(f"/app/1.0/{app}/1.0/login/getKey", base_url=base_url)
        return get_request(async_, request_kwargs, self=self)(url=api, **request_kwargs)

    @overload
    def app_version_list(
        self: None | ClientRequestMixin = None, 
        /, 
        base_url: str | Callable[[], str] = "https://appversion.115.com", 
        *, 
        async_: Literal[False] = False, 
        **request_kwargs
    ) -> dict:
        ...
    @overload
    def app_version_list(
        self: None | ClientRequestMixin = None, 
        /, 
        base_url: str | Callable[[], str] = "https://appversion.115.com", 
        *, 
        async_: Literal[True], 
        **request_kwargs
    ) -> Coroutine[Any, Any, dict]:
        ...
    def app_version_list(
        self: None | ClientRequestMixin = None, 
        /, 
        base_url: str | Callable[[], str] = "https://appversion.115.com", 
        *, 
        async_: Literal[False, True] = False, 
        **request_kwargs
    ) -> dict | Coroutine[Any, Any, dict]:
        """获取当前各平台最新版 115 app 下载链接

        GET https://appversion.115.com/1.0/web/1.0/api/chrome

        .. note::
            可以作为 ``staticmethod`` 使用
        """
        api = complete_url("/1.0/web/1.0/api/chrome", base_url=base_url)
        return get_request(async_, request_kwargs, self=self)(url=api, **request_kwargs)

    @overload
    def app_version_list2(
        self: None | ClientRequestMixin = None, 
        /, 
        base_url: str | Callable[[], str] = "https://appversion.115.com", 
        *, 
        async_: Literal[False] = False, 
        **request_kwargs
    ) -> dict:
        ...
    @overload
    def app_version_list2(
        self: None | ClientRequestMixin = None, 
        /, 
        base_url: str | Callable[[], str] = "https://appversion.115.com", 
        *, 
        async_: Literal[True], 
        **request_kwargs
    ) -> Coroutine[Any, Any, dict]:
        ...
    def app_version_list2(
        self: None | ClientRequestMixin = None, 
        /, 
        base_url: str | Callable[[], str] = "https://appversion.115.com", 
        *, 
        async_: Literal[False, True] = False, 
        **request_kwargs
    ) -> dict | Coroutine[Any, Any, dict]:
        """获取当前各平台最新版 115 app 下载链接

        GET https://appversion.115.com/1.0/web/1.0/api/getMultiVer

        .. note::
            可以作为 ``staticmethod`` 使用
        """
        api = complete_url("/1.0/web/1.0/api/getMultiVer", base_url=base_url)
        return get_request(async_, request_kwargs, self=self)(url=api, **request_kwargs)

    ########## Captcha System API ##########

    @overload
    def captcha_all(
        self, 
        /, 
        base_url: str | Callable[[], str] = "https://captchaapi.115.com", 
        *, 
        async_: Literal[False] = False, 
        **request_kwargs, 
    ) -> bytes:
        ...
    @overload
    def captcha_all(
        self, 
        /, 
        base_url: str | Callable[[], str] = "https://captchaapi.115.com", 
        *, 
        async_: Literal[True], 
        **request_kwargs, 
    ) -> Coroutine[Any, Any, bytes]:
        ...
    def captcha_all(
        self, 
        /, 
        base_url: str | Callable[[], str] = "https://captchaapi.115.com", 
        *, 
        async_: Literal[False, True] = False, 
        **request_kwargs, 
    ) -> bytes | Coroutine[Any, Any, bytes]:
        """返回一张包含 10 个汉字的图片，包含验证码中 4 个汉字（有相应的编号，从 0 到 9，计数按照从左到右，从上到下的顺序）

        GET https://captchaapi.115.com/?ct=index&ac=code&t=all
        """
        api = complete_url(base_url=base_url, query={"ct": "index", "ac": "code", "t": "all"})
        request_kwargs.setdefault("parse", False)
        return self.request(url=api, async_=async_, **request_kwargs)

    @overload
    def captcha_code(
        self, 
        /, 
        base_url: str | Callable[[], str] = "https://captchaapi.115.com", 
        *, 
        async_: Literal[False] = False, 
        **request_kwargs, 
    ) -> bytes:
        ...
    @overload
    def captcha_code(
        self, 
        /, 
        base_url: str | Callable[[], str] = "https://captchaapi.115.com", 
        *, 
        async_: Literal[True], 
        **request_kwargs, 
    ) -> Coroutine[Any, Any, bytes]:
        ...
    def captcha_code(
        self, 
        /, 
        base_url: str | Callable[[], str] = "https://captchaapi.115.com", 
        *, 
        async_: Literal[False, True] = False, 
        **request_kwargs, 
    ) -> bytes | Coroutine[Any, Any, bytes]:
        """更新验证码，并获取图片数据（含 4 个汉字）

        GET https://captchaapi.115.com/?ct=index&ac=code
        """
        api = complete_url(base_url=base_url, query={"ct": "index", "ac": "code"})
        request_kwargs.setdefault("parse", False)
        return self.request(url=api, async_=async_, **request_kwargs)

    @overload
    def captcha_sign(
        self, 
        /, 
        base_url: str | Callable[[], str] = "https://captchaapi.115.com", 
        *, 
        async_: Literal[False] = False, 
        **request_kwargs, 
    ) -> dict:
        ...
    @overload
    def captcha_sign(
        self, 
        /, 
        base_url: str | Callable[[], str] = "https://captchaapi.115.com", 
        *, 
        async_: Literal[True], 
        **request_kwargs, 
    ) -> Coroutine[Any, Any, dict]:
        ...
    def captcha_sign(
        self, 
        /, 
        base_url: str | Callable[[], str] = "https://captchaapi.115.com", 
        *, 
        async_: Literal[False, True] = False, 
        **request_kwargs, 
    ) -> dict | Coroutine[Any, Any, dict]:
        """获取验证码的签名字符串

        GET https://captchaapi.115.com/?ac=code&t=sign
        """
        api = complete_url(base_url=base_url, query={"ac": "code", "t": "sign"})
        return self.request(url=api, async_=async_, **request_kwargs)

    @overload
    def captcha_single(
        self, 
        payload: dict | int = 0, 
        /, 
        base_url: str | Callable[[], str] = "https://captchaapi.115.com", 
        *, 
        async_: Literal[False] = False, 
        **request_kwargs, 
    ) -> bytes:
        ...
    @overload
    def captcha_single(
        self, 
        payload: dict | int = 0, 
        /, 
        base_url: str | Callable[[], str] = "https://captchaapi.115.com", 
        *, 
        async_: Literal[True], 
        **request_kwargs, 
    ) -> Coroutine[Any, Any, bytes]:
        ...
    def captcha_single(
        self, 
        payload: dict | int = 0, 
        /, 
        base_url: str | Callable[[], str] = "https://captchaapi.115.com", 
        *, 
        async_: Literal[False, True] = False, 
        **request_kwargs, 
    ) -> bytes | Coroutine[Any, Any, bytes]:
        """10 个汉字单独的图片，包含验证码中 4 个汉字，编号从 0 到 9

        GET https://captchaapi.115.com/?ct=index&ac=code&t=single

        :payload:
            - id: int = 0
        """
        api = complete_url(base_url=base_url, query={"ct": "index", "ac": "code", "t": "single"})
        if not isinstance(payload, dict):
            payload = {"id": payload}
        request_kwargs.setdefault("parse", False)
        return self.request(url=api, async_=async_, **request_kwargs)

    @overload
    def captcha_verify(
        self, 
        payload: int | str | dict, 
        /, 
        base_url: str | Callable[[], str] = "https://webapi.115.com", 
        *, 
        async_: Literal[False] = False, 
        **request_kwargs, 
    ) -> dict:
        ...
    @overload
    def captcha_verify(
        self, 
        payload: int | str | dict, 
        /, 
        base_url: str | Callable[[], str] = "https://webapi.115.com", 
        *, 
        async_: Literal[True], 
        **request_kwargs, 
    ) -> Coroutine[Any, Any, dict]:
        ...
    def captcha_verify(
        self, 
        payload: int | str | dict, 
        /, 
        base_url: str | Callable[[], str] = "https://webapi.115.com", 
        *, 
        async_: Literal[False, True] = False, 
        **request_kwargs, 
    ) -> dict | Coroutine[Any, Any, dict]:
        """提交验证码

        POST https://webapi.115.com/user/captcha

        :payload:
            - code: int | str 💡 从 0 到 9 中选取 4 个数字的一种排列
            - sign: str = <default>     💡 来自 `captcha_sign` 接口的响应
            - ac: str = "security_code" 💡 默认就行，不要自行决定
            - type: str = "web"         💡 默认就行，不要自行决定
            - ctype: str = "web"        💡 需要和 type 相同
            - client: str = "web"       💡 需要和 type 相同
        """
        api = complete_url("/user/captcha", base_url=base_url)
        if isinstance(payload, (int, str)):
            payload = {"code": payload}
        payload = {"ac": "security_code", "type": "web", "ctype": "web", "client": "web", **payload}
        def gen_step():
            if "sign" not in payload:
                resp = yield self.captcha_sign(async_=async_)
                payload["sign"] = resp["sign"]
            return self.request(
                url=api, 
                method="POST", 
                data=payload, 
                async_=async_, 
                **request_kwargs, 
            )
        return run_gen_step(gen_step, async_)

    ########## Diary API ##########

    @overload
    def diary_add(
        self, 
        payload: str | dict | list, 
        /, 
        app: str = "web", 
        base_url: str | Callable[[], str] = "https://life.115.com", 
        *, 
        async_: Literal[False] = False, 
        **request_kwargs, 
    ) -> dict:
        ...
    @overload
    def diary_add(
        self, 
        payload: str | dict | list, 
        /, 
        app: str = "web", 
        base_url: str | Callable[[], str] = "https://life.115.com", 
        *, 
        async_: Literal[True], 
        **request_kwargs, 
    ) -> Coroutine[Any, Any, dict]:
        ...
    def diary_add(
        self, 
        payload: str | dict | list, 
        /, 
        app: str = "web", 
        base_url: str | Callable[[], str] = "https://life.115.com", 
        *, 
        async_: Literal[False, True] = False, 
        **request_kwargs, 
    ) -> dict | Coroutine[Any, Any, dict]:
        """新建日记

        POST https://life.115.com/api/1.0/web/1.0/diary/add

        :payload:
            - form[content]: str 💡 内容
            - form[subject]: int | str = <default> 💡 标题
            - form[user_time]: int | float = <default> 💡 时间戳，单位是秒
            - form[weather]: int = <default> 💡 天气
            - form[mood]: int = <default> 💡 心情
            - form[moods]: int | str = <default> 💡 心情，多个用逗号 "," 隔开
            - form[tags][]: str = <default> 💡 标签
            - ...
            - form[tags][0]: str = <default> 💡 标签
            - ...
            - form[index_image] = <default> 💡 封面图片链接
            - form[address]: str = <default>           💡 地点
            - form[location]: str = <default>          💡 地名
            - form[longitude]: float | str = <default> 💡 经度
            - form[latitude]: float | str = <default>  💡 纬度
            - form[mid]: str = <default>               💡 位置编码
            - form[maps]: list[dict] = <default>       💡 多个地图位置
            - form[maps][0][address]: str = <default>
            - form[maps][0][location]: str = <default>
            - form[maps][0][latitude]: float | str = <default>
            - form[maps][0][longitude] float | str = <default>
            - form[maps][0][mid]: str = <default>
            - ...
        """
        api = complete_url(f"/api/1.0/{app}/1.0/diary/add", base_url)
        now = int(time())
        if isinstance(payload, str):
            payload = {"form[content]": payload, "form[user_time]": now}
        elif isinstance(payload, dict):
            payload = dict(expand_payload(payload, prefix="form", enum_seq=True))
            payload.setdefault("form[user_time]", now)
        elif isinstance(payload, list):
            payload = [("form[user_time]", now), *expand_payload(payload, prefix="form")]
        return self.request(url=api, method="POST", data=payload, async_=async_, **request_kwargs)

    @overload
    def diary_del(
        self, 
        payload: int | str | dict, 
        /, 
        app: str = "web", 
        base_url: str | Callable[[], str] = "https://life.115.com", 
        *, 
        async_: Literal[False] = False, 
        **request_kwargs, 
    ) -> dict:
        ...
    @overload
    def diary_del(
        self, 
        payload: int | str | dict, 
        /, 
        app: str = "web", 
        base_url: str | Callable[[], str] = "https://life.115.com", 
        *, 
        async_: Literal[True], 
        **request_kwargs, 
    ) -> Coroutine[Any, Any, dict]:
        ...
    def diary_del(
        self, 
        payload: int | str | dict, 
        /, 
        app: str = "web", 
        base_url: str | Callable[[], str] = "https://life.115.com", 
        *, 
        async_: Literal[False, True] = False, 
        **request_kwargs, 
    ) -> dict | Coroutine[Any, Any, dict]:
        """删除日记

        POST https://life.115.com/api/1.0/web/1.0/diary/delete

        :payload:
            - diary_id: int | str 💡 日记 id
        """
        api = complete_url(f"/api/1.0/{app}/1.0/diary/delete", base_url)
        if isinstance(payload, (int, str)):
            payload = {"diary_id": payload}
        return self.request(url=api, method="POST", data=payload, async_=async_, **request_kwargs)

    @overload
    def diary_detail(
        self, 
        payload: int | str | dict, 
        /, 
        app: str = "web", 
        base_url: str | Callable[[], str] = "https://life.115.com", 
        *, 
        async_: Literal[False] = False, 
        **request_kwargs, 
    ) -> dict:
        ...
    @overload
    def diary_detail(
        self, 
        payload: int | str | dict, 
        /, 
        app: str = "web", 
        base_url: str | Callable[[], str] = "https://life.115.com", 
        *, 
        async_: Literal[True], 
        **request_kwargs, 
    ) -> Coroutine[Any, Any, dict]:
        ...
    def diary_detail(
        self, 
        payload: int | str | dict, 
        /, 
        app: str = "web", 
        base_url: str | Callable[[], str] = "https://life.115.com", 
        *, 
        async_: Literal[False, True] = False, 
        **request_kwargs, 
    ) -> dict | Coroutine[Any, Any, dict]:
        """获取日记详情

        GET https://life.115.com/api/1.0/web/1.0/diary/detail

        :payload:
            - diary_id: int | str 💡 日记 id
            - format: str = html
        """
        api = complete_url(f"/api/1.0/{app}/1.0/diary/detail", base_url)
        if isinstance(payload, (int, str)):
            payload = {"diary_id": payload}
        return self.request(url=api, params=payload, async_=async_, **request_kwargs)

    @overload
    def diary_detail2(
        self, 
        payload: int | str | dict, 
        /, 
        app: str = "web", 
        base_url: str | Callable[[], str] = "https://life.115.com", 
        *, 
        async_: Literal[False] = False, 
        **request_kwargs, 
    ) -> dict:
        ...
    @overload
    def diary_detail2(
        self, 
        payload: int | str | dict, 
        /, 
        app: str = "web", 
        base_url: str | Callable[[], str] = "https://life.115.com", 
        *, 
        async_: Literal[True], 
        **request_kwargs, 
    ) -> Coroutine[Any, Any, dict]:
        ...
    def diary_detail2(
        self, 
        payload: int | str | dict, 
        /, 
        app: str = "web", 
        base_url: str | Callable[[], str] = "https://life.115.com", 
        *, 
        async_: Literal[False, True] = False, 
        **request_kwargs, 
    ) -> dict | Coroutine[Any, Any, dict]:
        """获取日记详情

        GET https://life.115.com/api/1.0/web/1.0/life/diarydetail

        :payload:
            - diary_id: int | str 💡 日记 id
            - format: str = html
        """
        api = complete_url(f"/api/1.0/{app}/1.0/life/diarydetail", base_url)
        if isinstance(payload, (int, str)):
            payload = {"diary_id": payload}
        return self.request(url=api, params=payload, async_=async_, **request_kwargs)

    @overload
    def diary_edit(
        self, 
        payload: dict | list, 
        /, 
        app: str = "web", 
        base_url: str | Callable[[], str] = "https://life.115.com", 
        *, 
        async_: Literal[False] = False, 
        **request_kwargs, 
    ) -> dict:
        ...
    @overload
    def diary_edit(
        self, 
        payload: dict | list, 
        /, 
        app: str = "web", 
        base_url: str | Callable[[], str] = "https://life.115.com", 
        *, 
        async_: Literal[True], 
        **request_kwargs, 
    ) -> Coroutine[Any, Any, dict]:
        ...
    def diary_edit(
        self, 
        payload: dict | list, 
        /, 
        app: str = "web", 
        base_url: str | Callable[[], str] = "https://life.115.com", 
        *, 
        async_: Literal[False, True] = False, 
        **request_kwargs, 
    ) -> dict | Coroutine[Any, Any, dict]:
        """修改日记

        POST https://life.115.com/api/1.0/web/1.0/diary/edit

        :payload:
            - form[diary_id]: str 💡 日记 id
            - form[content]: str = <default> 💡 内容
            - form[subject]: int | str = <default> 💡 标题
            - form[user_time]: int | float = <default> 💡 时间戳，单位是秒
            - form[weather]: int = <default> 💡 天气
            - form[mood]: int = <default> 💡 心情
            - form[moods]: int | str = <default> 💡 心情，多个用逗号 "," 隔开
            - form[tags][]: str = <default> 💡 标签
            - ...
            - form[tags][0]: str = <default> 💡 标签
            - ...
            - form[index_image] = <default> 💡 封面图片链接
            - form[address]: str = <default>           💡 地点
            - form[location]: str = <default>          💡 地名
            - form[longitude]: float | str = <default> 💡 经度
            - form[latitude]: float | str = <default>  💡 纬度
            - form[mid]: str = <default>               💡 位置编码
            - form[maps]: list[dict] = <default>       💡 多个地图位置
            - form[maps][0][address]: str = <default>
            - form[maps][0][location]: str = <default>
            - form[maps][0][latitude]: float | str = <default>
            - form[maps][0][longitude] float | str = <default>
            - form[maps][0][mid]: str = <default>
            - ...
        """
        api = complete_url(f"/api/1.0/{app}/1.0/diary/edit", base_url)
        if isinstance(payload, dict):
            payload = dict(expand_payload(payload, prefix="form", enum_seq=True))
        elif isinstance(payload, list):
            payload = list(expand_payload(payload, prefix="form"))
        return self.request(url=api, method="POST", data=payload, async_=async_, **request_kwargs)

    @overload
    def diary_get_config(
        self, 
        /, 
        app: str = "web", 
        base_url: str | Callable[[], str] = "https://life.115.com", 
        *, 
        async_: Literal[False] = False, 
        **request_kwargs, 
    ) -> dict:
        ...
    @overload
    def diary_get_config(
        self, 
        /, 
        app: str = "web", 
        base_url: str | Callable[[], str] = "https://life.115.com", 
        *, 
        async_: Literal[True], 
        **request_kwargs, 
    ) -> Coroutine[Any, Any, dict]:
        ...
    def diary_get_config(
        self, 
        /, 
        app: str = "web", 
        base_url: str | Callable[[], str] = "https://life.115.com", 
        *, 
        async_: Literal[False, True] = False, 
        **request_kwargs, 
    ) -> dict | Coroutine[Any, Any, dict]:
        """获取日记可选项（例如天气、心情等）的取值集合

        GET https://life.115.com/api/1.0/web/1.0/diary/get_diary_config
        """
        api = complete_url(f"/api/1.0/{app}/1.0/diary/get_diary_config", base_url)
        return self.request(url=api, async_=async_, **request_kwargs)

    @overload
    def diary_get_latest_tags(
        self, 
        payload: int | str | dict = {}, 
        /, 
        app: str = "web", 
        base_url: str | Callable[[], str] = "https://life.115.com", 
        *, 
        async_: Literal[False] = False, 
        **request_kwargs, 
    ) -> dict:
        ...
    @overload
    def diary_get_latest_tags(
        self, 
        payload: int | str | dict = {}, 
        /, 
        app: str = "web", 
        base_url: str | Callable[[], str] = "https://life.115.com", 
        *, 
        async_: Literal[True], 
        **request_kwargs, 
    ) -> Coroutine[Any, Any, dict]:
        ...
    def diary_get_latest_tags(
        self, 
        payload: int | str | dict = {}, 
        /, 
        app: str = "web", 
        base_url: str | Callable[[], str] = "https://life.115.com", 
        *, 
        async_: Literal[False, True] = False, 
        **request_kwargs, 
    ) -> dict | Coroutine[Any, Any, dict]:
        """获取最近使用过的标签列表

        GET https://life.115.com/api/1.0/web/1.0/diary/getlatesttags

        :payload:
            - q: str = "" 💡 筛选关键词
            - color: 0 | 1 = <default>
            - limit: int = <default> 💡 最多返回数量，⚠️ 这个参数似乎无效
        """
        api = complete_url(f"/api/1.0/{app}/1.0/diary/getlatesttags", base_url)
        if isinstance(payload, int):
            payload = {"limit": payload}
        elif isinstance(payload, str):
            payload = {"q": payload}
        return self.request(url=api, params=payload, async_=async_, **request_kwargs)

    @overload
    def diary_get_tag_color(
        self, 
        payload: str | list | tuple | dict, 
        /, 
        app: str = "web", 
        base_url: str | Callable[[], str] = "https://life.115.com", 
        *, 
        async_: Literal[False] = False, 
        **request_kwargs, 
    ) -> dict:
        ...
    @overload
    def diary_get_tag_color(
        self, 
        payload: str | list | tuple | dict, 
        /, 
        app: str = "web", 
        base_url: str | Callable[[], str] = "https://life.115.com", 
        *, 
        async_: Literal[True], 
        **request_kwargs, 
    ) -> Coroutine[Any, Any, dict]:
        ...
    def diary_get_tag_color(
        self, 
        payload: str | list | tuple | dict, 
        /, 
        app: str = "web", 
        base_url: str | Callable[[], str] = "https://life.115.com", 
        *, 
        async_: Literal[False, True] = False, 
        **request_kwargs, 
    ) -> dict | Coroutine[Any, Any, dict]:
        """获取标签的颜色

        POST https://life.115.com/api/1.0/web/1.0/diary/gettagcolor

        :payload:
            - tags: str 💡 标签文本
            - tags[]: str
            - ...
            - tags[0]: str
            - tags[1]: str
            - ...
        """
        api = complete_url(f"/api/1.0/{app}/1.0/diary/gettagcolor", base_url)
        if not isinstance(payload, dict):
            if isinstance(payload, (list, tuple)):
                payload = [t if isinstance(t, (list, tuple)) else ("tags[]", str(t)) for t in payload]
            else:
                payload = {"tags": str(payload)}
        return self.request(url=api, method="POST", data=payload, async_=async_, **request_kwargs)

    @overload
    def diary_list(
        self, 
        payload: int | dict = 0, 
        /, 
        app: str = "web", 
        base_url: str | Callable[[], str] = "https://life.115.com", 
        *, 
        async_: Literal[False] = False, 
        **request_kwargs, 
    ) -> dict:
        ...
    @overload
    def diary_list(
        self, 
        payload: int | dict = 0, 
        /, 
        app: str = "web", 
        base_url: str | Callable[[], str] = "https://life.115.com", 
        *, 
        async_: Literal[True], 
        **request_kwargs, 
    ) -> Coroutine[Any, Any, dict]:
        ...
    def diary_list(
        self, 
        payload: int | dict = 0, 
        /, 
        app: str = "web", 
        base_url: str | Callable[[], str] = "https://life.115.com", 
        *, 
        async_: Literal[False, True] = False, 
        **request_kwargs, 
    ) -> dict | Coroutine[Any, Any, dict]:
        """获取日记列表，此接口是对 `life_glist` 的封装

        :payload:
            - start: int = 0 💡 开始索引，从 0 开始
            - limit: int = <default> 💡 分页大小
            - only_public: 0 | 1 = <default>
            - msg_note: 0 | 1 = <default>
            - option: 0 | 1 = <default>
        """
        if isinstance(payload, int):
            payload = {"start": payload}
        else:
            payload = dict(payload)
        payload.setdefault("type", 5)
        return self.life_glist(payload, app=app, base_url=base_url, async_=async_, **request_kwargs)

    @overload
    def diary_search(
        self, 
        payload: str | dict, 
        /, 
        app: str = "web", 
        base_url: str | Callable[[], str] = "https://life.115.com", 
        *, 
        async_: Literal[False] = False, 
        **request_kwargs, 
    ) -> dict:
        ...
    @overload
    def diary_search(
        self, 
        payload: str | dict, 
        /, 
        app: str = "web", 
        base_url: str | Callable[[], str] = "https://life.115.com", 
        *, 
        async_: Literal[True], 
        **request_kwargs, 
    ) -> Coroutine[Any, Any, dict]:
        ...
    def diary_search(
        self, 
        payload: str | dict, 
        /, 
        app: str = "web", 
        base_url: str | Callable[[], str] = "https://life.115.com", 
        *, 
        async_: Literal[False, True] = False, 
        **request_kwargs, 
    ) -> dict | Coroutine[Any, Any, dict]:
        """搜索日记

        GET https://life.115.com/api/1.0/web/1.0/diary/search

        :payload:
            - q: str 💡 关键词
            - start: int = 0 💡 开始索引，从 0 开始
            - limit: int = <default> 💡 分页大小
            - display_list: 0 | 1 = <default>
        """
        api = complete_url(f"/api/1.0/{app}/1.0/diary/search", base_url)
        if isinstance(payload, str):
            payload = {"q": payload}
        return self.request(url=api, params=payload, async_=async_, **request_kwargs)

    @overload
    def diary_settag(
        self, 
        payload: dict | list, 
        /, 
        app: str = "web", 
        base_url: str | Callable[[], str] = "https://life.115.com", 
        *, 
        async_: Literal[False] = False, 
        **request_kwargs, 
    ) -> dict:
        ...
    @overload
    def diary_settag(
        self, 
        payload: dict | list, 
        /, 
        app: str = "web", 
        base_url: str | Callable[[], str] = "https://life.115.com", 
        *, 
        async_: Literal[True], 
        **request_kwargs, 
    ) -> Coroutine[Any, Any, dict]:
        ...
    def diary_settag(
        self, 
        payload: dict | list, 
        /, 
        app: str = "web", 
        base_url: str | Callable[[], str] = "https://life.115.com", 
        *, 
        async_: Literal[False, True] = False, 
        **request_kwargs, 
    ) -> dict | Coroutine[Any, Any, dict]:
        """设置日记标签

        POST https://life.115.com/api/1.0/web/1.0/diary/settag

        :payload:
            - diary_id: int | str 💡 日记 id
            - tags: str
            - tags[]: str
            - ...
            - tags[0]: str
            - tags[1]: str
            - ...
        """
        api = complete_url(f"/api/1.0/{app}/1.0/diary/settag", base_url)
        return self.request(url=api, method="POST", data=payload, async_=async_, **request_kwargs)

    @overload
    def diary_settop(
        self, 
        payload: int | str | dict, 
        /, 
        app: str = "web", 
        base_url: str | Callable[[], str] = "https://life.115.com", 
        *, 
        async_: Literal[False] = False, 
        **request_kwargs, 
    ) -> dict:
        ...
    @overload
    def diary_settop(
        self, 
        payload: int | str | dict, 
        /, 
        app: str = "web", 
        base_url: str | Callable[[], str] = "https://life.115.com", 
        *, 
        async_: Literal[True], 
        **request_kwargs, 
    ) -> Coroutine[Any, Any, dict]:
        ...
    def diary_settop(
        self, 
        payload: int | str | dict, 
        /, 
        app: str = "web", 
        base_url: str | Callable[[], str] = "https://life.115.com", 
        *, 
        async_: Literal[False, True] = False, 
        **request_kwargs, 
    ) -> dict | Coroutine[Any, Any, dict]:
        """切换日记的置顶状态，此接口是对 `life_set_top` 的封装

        .. attention::
            这个接口会自动切换日记的置顶状态，但不支持手动指定是否置顶，只是在置顶和不置顶间来回切换。

        :payload:
            - relation_id: int | str 💡 日记 id
        """
        if isinstance(payload, (int, str)):
            payload = {"relation_id": payload}
        payload.setdefault("type", 5)
        return self.life_set_top(payload, app=app, base_url=base_url, async_=async_, **request_kwargs)

    ########## Download API ##########

    @overload
    def download_folders_app(
        self, 
        payload: str | dict, 
        /, 
        app: str = "chrome", 
        base_url: str | Callable[[], str] = "https://proapi.115.com", 
        *, 
        async_: Literal[False] = False, 
        **request_kwargs, 
    ) -> dict:
        ...
    @overload
    def download_folders_app(
        self, 
        payload: str | dict, 
        /, 
        app: str = "chrome", 
        base_url: str | Callable[[], str] = "https://proapi.115.com", 
        *, 
        async_: Literal[True], 
        **request_kwargs, 
    ) -> Coroutine[Any, Any, dict]:
        ...
    def download_folders_app(
        self, 
        payload: str | dict, 
        /, 
        app: str = "chrome", 
        base_url: str | Callable[[], str] = "https://proapi.115.com", 
        *, 
        async_: Literal[False, True] = False, 
        **request_kwargs, 
    ) -> dict | Coroutine[Any, Any, dict]:
        """获取待下载的目录列表

        GET https://proapi.115.com/app/chrome/downfolders

        :payload:
            - pickcode: str 💡 提取码
            - page: int = 1 💡 第几页
            - per_page: int = 5000 💡 每页大小，目前最大为 5000
        """
        if app == "chrome":
            api = complete_url("/app/chrome/downfolders", base_url)
        else:
            if app not in ("windows", "mac", "linux", "os_windows", "os_mac", "os_linux"):
                app = "os_windows"
            api = complete_url("/ufile/downfolders", base_url, app=app)
        if isinstance(payload, str):
            payload = {"pickcode": payload}
        payload = {"page": 1, "per_page": 5000, **payload}
        return self.request(url=api, params=payload, async_=async_, **request_kwargs)

    @overload
    def download_files_app(
        self, 
        payload: str | dict, 
        /, 
        app: str = "chrome", 
        base_url: str | Callable[[], str] = "https://proapi.115.com", 
        *, 
        async_: Literal[False] = False, 
        **request_kwargs, 
    ) -> dict:
        ...
    @overload
    def download_files_app(
        self, 
        payload: str | dict, 
        /, 
        app: str = "chrome", 
        base_url: str | Callable[[], str] = "https://proapi.115.com", 
        *, 
        async_: Literal[True], 
        **request_kwargs, 
    ) -> Coroutine[Any, Any, dict]:
        ...
    def download_files_app(
        self, 
        payload: str | dict, 
        /, 
        app: str = "chrome", 
        base_url: str | Callable[[], str] = "https://proapi.115.com", 
        *, 
        async_: Literal[False, True] = False, 
        **request_kwargs, 
    ) -> dict | Coroutine[Any, Any, dict]:
        """获取待下载的文件列表

        GET https://proapi.115.com/app/chrome/downfiles

        :payload:
            - pickcode: str 💡 提取码
            - page: int = 1 💡 第几页
            - per_page: int = 5000 💡 每页大小，目前最大为 5000
        """
        if app == "chrome":
            api = complete_url("/app/chrome/downfiles", base_url)
        else:
            if app not in ("windows", "mac", "linux", "os_windows", "os_mac", "os_linux"):
                app = "os_windows"
            api = complete_url("/ufile/downfiles", base_url, app=app)
        if isinstance(payload, str):
            payload = {"pickcode": payload}
        payload = {"page": 1, "per_page": 5000, **payload}
        return self.request(url=api, params=payload, async_=async_, **request_kwargs)

    @overload
    def download_downfolder_app(
        self, 
        payload: str | dict, 
        /, 
        app: str = "android", 
        base_url: str | Callable[[], str] = "https://proapi.115.com", 
        *, 
        async_: Literal[False] = False, 
        **request_kwargs, 
    ) -> dict:
        ...
    @overload
    def download_downfolder_app(
        self, 
        payload: str | dict, 
        /, 
        app: str = "android", 
        base_url: str | Callable[[], str] = "https://proapi.115.com", 
        *, 
        async_: Literal[True], 
        **request_kwargs, 
    ) -> Coroutine[Any, Any, dict]:
        ...
    def download_downfolder_app(
        self, 
        payload: str | dict, 
        /, 
        app: str = "android", 
        base_url: str | Callable[[], str] = "https://proapi.115.com", 
        *, 
        async_: Literal[False, True] = False, 
        **request_kwargs, 
    ) -> dict | Coroutine[Any, Any, dict]:
        """获取待下载的文件列表

        GET https://proapi.115.com/android/folder/downfolder

        .. caution::
            一次性拉完，当文件过多时，会报错

        :payload:
            - pickcode: str 💡 提取码
        """
        api = complete_url("/folder/downfolder", base_url=base_url, app=app)
        if isinstance(payload, str):
            payload = {"pickcode": payload}
        return self.request(url=api, params=payload, async_=async_, **request_kwargs)

    @overload
    def download_url(
        self, 
        pickcode: str, 
        /, 
        strict: bool = True, 
        user_agent: None | str = None, 
        app: str = "chrome", 
        *, 
        async_: Literal[False] = False, 
        **request_kwargs, 
    ) -> P115URL:
        ...
    @overload
    def download_url(
        self, 
        pickcode: str, 
        /, 
        strict: bool = True, 
        user_agent: None | str = None, 
        app: str = "chrome", 
        *, 
        async_: Literal[True], 
        **request_kwargs, 
    ) -> Coroutine[Any, Any, P115URL]:
        ...
    def download_url(
        self, 
        pickcode: str, 
        /, 
        strict: bool = True, 
        user_agent: None | str = None, 
        app: str = "chrome", 
        *, 
        async_: Literal[False, True] = False, 
        **request_kwargs, 
    ) -> P115URL | Coroutine[Any, Any, P115URL]:
        """获取文件的下载链接，此接口是对 `download_url_app` 的封装

        .. note::
            获取的直链中，部分查询参数的解释：

            - ``t``: 过期时间戳
            - ``u``: 用户 id
            - ``c``: 允许同时打开次数，如果为 0，则是无限次数
            - ``f``: 请求时要求携带请求头
                - 如果为空，则无要求
                - 如果为 1，则需要 user-agent（和请求直链时的一致）
                - 如果为 3，则需要 user-agent（和请求直链时的一致） 和 Cookie（由请求直链时的响应所返回的 Set-Cookie 响应头）

        :param pickcode: 提取码
        :param strict: 如果为 True，当目标是目录时，会抛出 IsADirectoryError 异常
        :param user_agent: 如果不为 None，则作为请求头 "user-agent" 的值
        :param app: 使用此设备的接口
        :param async_: 是否异步
        :param request_kwargs: 其余请求参数

        :return: 下载链接
        """
        def gen_step():
            if app == "web2":
                resp = yield self.download_url_web2(
                    pickcode, 
                    user_agent=user_agent, 
                    async_=async_, 
                    **request_kwargs, 
                )
                resp["pickcode"] = pickcode
                check_response(resp)
                url = resp["url"]
                return P115URL(
                    url, 
                    id=self.to_id(pickcode), 
                    pickcode=pickcode, 
                    name=unquote(urlsplit(url).path.rsplit("/", 1)[-1]), 
                    is_dir=False, 
                    headers=resp["headers"], 
                )
            elif app in ("web", "desktop", "harmony"):
                resp = yield self.download_url_web(
                    pickcode, 
                    user_agent=user_agent, 
                    async_=async_, 
                    **request_kwargs, 
                )
                resp["pickcode"] = pickcode
                try:
                    check_response(resp)
                except IsADirectoryError:
                    if strict:
                        raise
                return P115URL(
                    resp.get("file_url", ""), 
                    id=int(resp["file_id"]), 
                    pickcode=pickcode, 
                    name=resp["file_name"], 
                    size=int(resp["file_size"]), 
                    is_dir=not resp["state"], 
                    headers=resp["headers"], 
                )
            else:
                resp = yield self.download_url_app(
                    pickcode, 
                    user_agent=user_agent, 
                    app=app or "chrome", 
                    async_=async_, 
                    **request_kwargs, 
                )
                resp["pickcode"] = pickcode
                check_response(resp)
                if "url" in resp["data"]:
                    url = resp["data"]["url"]
                    return P115URL(
                        url, 
                        pickcode=pickcode, 
                        name=unquote(urlsplit(url).path.rsplit("/", 1)[-1]), 
                        is_dir=False, 
                        headers=resp["headers"], 
                    )
                for fid, info in resp["data"].items():
                    url = info["url"]
                    if strict and not url:
                        throw(
                            errno.EISDIR, 
                            f"{fid} is a directory, with response {resp}", 
                        )
                    return P115URL(
                        url["url"] if url else "", 
                        id=int(fid), 
                        pickcode=info["pick_code"], 
                        name=info["file_name"], 
                        size=int(info["file_size"]), 
                        sha1=info["sha1"], 
                        is_dir=not url, 
                        headers=resp["headers"], 
                    )
                throw(
                    errno.ENOENT, 
                    f"no such pickcode: {pickcode!r}, with response {resp}", 
                )
        return run_gen_step(gen_step, async_)

    @overload
    def download_urls(
        self, 
        pickcodes: str | Iterable[str], 
        /, 
        strict: bool = True, 
        user_agent: None | str = None, 
        *, 
        async_: Literal[False] = False, 
        **request_kwargs, 
    ) -> dict[int, P115URL]:
        ...
    @overload
    def download_urls(
        self, 
        pickcodes: str | Iterable[str], 
        /, 
        strict: bool = True, 
        user_agent: None | str = None, 
        *, 
        async_: Literal[True], 
        **request_kwargs, 
    ) -> Coroutine[Any, Any, dict[int, P115URL]]:
        ...
    def download_urls(
        self, 
        pickcodes: str | Iterable[str], 
        /, 
        strict: bool = True, 
        user_agent: None | str = None, 
        *, 
        async_: Literal[False, True] = False, 
        **request_kwargs, 
    ) -> dict[int, P115URL] | Coroutine[Any, Any, dict[int, P115URL]]:
        """批量获取文件的下载链接，此接口是对 `download_url_app` 的封装

        .. note::
            获取的直链中，部分查询参数的解释：

            - ``t``: 过期时间戳
            - ``u``: 用户 id
            - ``c``: 允许同时打开次数，如果为 0，则是无限次数
            - ``f``: 请求时要求携带请求头
                - 如果为空，则无要求
                - 如果为 1，则需要 user-agent（和请求直链时的一致）
                - 如果为 3，则需要 user-agent（和请求直链时的一致） 和 Cookie（由请求直链时的响应所返回的 Set-Cookie 响应头）

        :param pickcodes: 提取码，多个用逗号 "," 隔开
        :param strict: 如果为 True，当目标是目录时，会直接忽略
        :param user_agent: 如果不为 None，则作为请求头 "user-agent" 的值
        :param async_: 是否异步
        :param request_kwargs: 其余请求参数

        :return: 一批下载链接
        """
        if not isinstance(pickcodes, str):
            pickcodes = ",".join(pickcodes)
        def gen_step():
            resp = yield self.download_url_app(
                pickcodes, 
                user_agent=user_agent, 
                async_=async_, 
                **request_kwargs, 
            )
            resp["pickcode"] = pickcodes
            urls: dict[int, P115URL] = {}
            if not resp["state"]:
                if resp.get("errno") != 50003:
                    check_response(resp)
            else:
                for fid, info in resp["data"].items():
                    url = info["url"]
                    if strict and not url:
                        continue
                    fid = int(fid)
                    urls[fid] = P115URL(
                        url["url"] if url else "", 
                        id=fid, 
                        pickcode=info["pick_code"], 
                        name=info["file_name"], 
                        size=int(info["file_size"]), 
                        sha1=info["sha1"], 
                        is_dir=not url, 
                        headers=resp["headers"], 
                    )
            return urls
        return run_gen_step(gen_step, async_)

    @overload
    def download_url_app(
        self, 
        payload: str | dict, 
        /, 
        user_agent: None | str = None, 
        app: str = "chrome", 
        base_url: str | Callable[[], str] = "https://proapi.115.com", 
        *, 
        async_: Literal[False] = False, 
        **request_kwargs, 
    ) -> dict:
        ...
    @overload
    def download_url_app(
        self, 
        payload: str | dict, 
        /, 
        user_agent: None | str = None, 
        app: str = "chrome", 
        base_url: str | Callable[[], str] = "https://proapi.115.com", 
        *, 
        async_: Literal[True], 
        **request_kwargs, 
    ) -> Coroutine[Any, Any, dict]:
        ...
    def download_url_app(
        self, 
        payload: str | dict, 
        /, 
        user_agent: None | str = None, 
        app: str = "chrome", 
        base_url: str | Callable[[], str] = "https://proapi.115.com", 
        *, 
        async_: Literal[False, True] = False, 
        **request_kwargs, 
    ) -> dict | Coroutine[Any, Any, dict]:
        """获取文件的下载链接

        POST https://proapi.115.com/app/chrome/downurl

        .. note::
            `app` 为 "chrome" 时，支持一次获取多个提取码对应的下载链接，但是每多一个提取码，大概多耗时 50 ms，猜测服务端也是逐个从某个服务获取下载链接的。

            如果 `app` 为 "chrome"，则仅支持 `aid=1` 的提取码获取下载链接（以前是不限制 aid 的，这样甚至可以获取已经删除的文件的下载链接）；否则，还支持 `aid=12` 的下载链接。

        :payload:
            - pickcode: str 💡 如果 `app` 为 "chrome"，则可以接受多个，多个用逗号 "," 隔开
        """
        if app == "chrome":
            api = complete_url("/app/chrome/downurl", base_url)
            if isinstance(payload, str):
                payload = {"pickcode": payload}
        else:
            api = complete_url("/2.0/ufile/download", base_url=base_url, app=app)
            if isinstance(payload, str):
                payload = {"pick_code": payload}
            else:
                payload = {"pick_code": payload["pickcode"]}
        headers = request_kwargs["headers"] = dict(request_kwargs.get("headers") or ())
        if user_agent is None:
            headers.setdefault("user-agent", "")
        else:
            headers["user-agent"] = user_agent
        def parse(_, content: bytes, /) -> dict:
            json = json_loads(content)
            if json["state"]:
                json["data"] = json_loads(rsa_decrypt(json["data"]))
            json["headers"] = headers
            return json
        request_kwargs.setdefault("parse", parse)
        request_kwargs["data"] = {"data": rsa_encrypt(dumps(payload)).decode("ascii")}
        return self.request(
            url=api, 
            method="POST", 
            async_=async_, 
            **request_kwargs, 
        )

    @overload
    def download_url_web(
        self, 
        payload: str | dict, 
        /, 
        base_url: str | Callable[[], str] = "https://webapi.115.com", 
        user_agent: None | str = None, 
        *, 
        async_: Literal[False] = False, 
        **request_kwargs, 
    ) -> dict:
        ...
    @overload
    def download_url_web(
        self, 
        payload: str | dict, 
        /, 
        base_url: str | Callable[[], str] = "https://webapi.115.com", 
        user_agent: None | str = None, 
        *, 
        async_: Literal[True], 
        **request_kwargs, 
    ) -> Coroutine[Any, Any, dict]:
        ...
    def download_url_web(
        self, 
        payload: str | dict, 
        /, 
        base_url: str | Callable[[], str] = "https://webapi.115.com", 
        user_agent: None | str = None, 
        *, 
        async_: Literal[False, True] = False, 
        **request_kwargs, 
    ) -> dict | Coroutine[Any, Any, dict]:
        """获取文件的下载链接（网页版接口）

        GET https://webapi.115.com/files/download

        .. note::
            最大允许下载 200 MB 的文件，即使文件违规，或者 `aid=12`，也可以正常下载

        :payload:
            - pickcode: str
            - dl: int = <default>
        """
        api = complete_url("/files/download", base_url=base_url)
        if isinstance(payload, str):
            payload = {"pickcode": payload}
        headers = request_kwargs["headers"] = dict(request_kwargs.get("headers") or ())
        if user_agent is None:
            headers.setdefault("user-agent", "")
        else:
            headers["user-agent"] = user_agent
        def parse(resp, content: bytes, /) -> dict:
            json = json_loads(content)
            if "Set-Cookie" in resp.headers:
                if isinstance(resp.headers, Mapping):
                    match = CRE_SET_COOKIE.search(resp.headers["Set-Cookie"])
                    if match is not None:
                        headers["Cookie"] = match[0]
                else:
                    for k, v in reversed(resp.headers.items()):
                        if k == "Set-Cookie" and CRE_SET_COOKIE.match(v) is not None:
                            headers["Cookie"] = v
                            break
            json["headers"] = headers
            return json
        request_kwargs.setdefault("parse", parse)
        return self.request(url=api, params=payload, async_=async_, **request_kwargs)

    @overload
    def download_url_web2(
        self, 
        payload: str | dict, 
        /, 
        base_url: str | Callable[[], str] = "https://115.com", 
        user_agent: None | str = None, 
        *, 
        async_: Literal[False] = False, 
        **request_kwargs, 
    ) -> dict:
        ...
    @overload
    def download_url_web2(
        self, 
        payload: str | dict, 
        /, 
        base_url: str | Callable[[], str] = "https://115.com", 
        user_agent: None | str = None, 
        *, 
        async_: Literal[True], 
        **request_kwargs, 
    ) -> Coroutine[Any, Any, dict]:
        ...
    def download_url_web2(
        self, 
        payload: str | dict, 
        /, 
        base_url: str | Callable[[], str] = "https://115.com", 
        user_agent: None | str = None, 
        *, 
        async_: Literal[False, True] = False, 
        **request_kwargs, 
    ) -> dict | Coroutine[Any, Any, dict]:
        """获取文件的下载链接（网页版接口）

        GET https://115.com/?ct=download&ac=video

        .. note::
            最大允许下载 200 MB 的文件，即使文件已被删除，也可以正常下载

        :payload:
            - pickcode: str
        """
        api = complete_url(base_url=base_url, query={"ct": "download", "ac": "video"})
        if isinstance(payload, str):
            payload = {"pickcode": payload}
        headers = request_kwargs["headers"] = dict(request_kwargs.get("headers") or ())
        if user_agent is None:
            headers.setdefault("user-agent", "")
        else:
            headers["user-agent"] = user_agent
        def parse(resp, _: bytes, /) -> dict:
            if resp.status != 302:
                return {"state": False, "response": {"status": resp.status, "headers": dict(resp.headers)}}
            json = {"state": True, "url": resp.headers["location"]}
            if "Set-Cookie" in resp.headers:
                if isinstance(resp.headers, Mapping):
                    match = CRE_SET_COOKIE.search(resp.headers["Set-Cookie"])
                    if match is not None:
                        headers["Cookie"] = match[0]
                else:
                    for k, v in reversed(resp.headers.items()):
                        if k == "Set-Cookie" and CRE_SET_COOKIE.match(v) is not None:
                            headers["Cookie"] = v
                            break
            json["headers"] = headers
            return json
        request_kwargs.setdefault("parse", parse)
        request_kwargs.setdefault("follow_redirects", False)
        return self.request(url=api, params=payload, async_=async_, **request_kwargs)

    ########## Extraction API ##########

    @overload
    def extract_add_file(
        self, 
        payload: list | dict, 
        /, 
        base_url: str | Callable[[], str] = "https://webapi.115.com", 
        *, 
        async_: Literal[False] = False, 
        **request_kwargs, 
    ) -> dict:
        ...
    @overload
    def extract_add_file(
        self, 
        payload: list | dict, 
        /, 
        base_url: str | Callable[[], str] = "https://webapi.115.com", 
        *, 
        async_: Literal[True], 
        **request_kwargs, 
    ) -> Coroutine[Any, Any, dict]:
        ...
    def extract_add_file(
        self, 
        payload: list | dict, 
        /, 
        base_url: str | Callable[[], str] = "https://webapi.115.com", 
        *, 
        async_: Literal[False, True] = False, 
        **request_kwargs, 
    ) -> dict | Coroutine[Any, Any, dict]:
        """解压缩到某个目录，推荐直接用封装函数 `extract_file`

        POST https://webapi.115.com/files/add_extract_file

        :payload:
            - pick_code: str
            - extract_file: str = ""
            - extract_dir: str = ""
            - extract_file[]: str
            - extract_file[]: str
            - ...
            - to_pid: int | str = 0
            - paths: str = "文件"
        """
        api = complete_url("/files/add_extract_file", base_url=base_url)
        return self.request(url=api, method="POST", data=payload, async_=async_, **request_kwargs)

    @overload
    def extract_add_file_app(
        self, 
        payload: list | dict, 
        /, 
        app: str = "android", 
        base_url: str | Callable[[], str] = "https://proapi.115.com", 
        *, 
        async_: Literal[False] = False, 
        **request_kwargs, 
    ) -> dict:
        ...
    @overload
    def extract_add_file_app(
        self, 
        payload: list | dict, 
        /, 
        app: str = "android", 
        base_url: str | Callable[[], str] = "https://proapi.115.com", 
        *, 
        async_: Literal[True], 
        **request_kwargs, 
    ) -> Coroutine[Any, Any, dict]:
        ...
    def extract_add_file_app(
        self, 
        payload: list | dict, 
        /, 
        app: str = "android", 
        base_url: str | Callable[[], str] = "https://proapi.115.com", 
        *, 
        async_: Literal[False, True] = False, 
        **request_kwargs, 
    ) -> dict | Coroutine[Any, Any, dict]:
        """解压缩到某个目录，推荐直接用封装函数 `extract_file`

        POST https://proapi.115.com/android/2.0/ufile/add_extract_file

        :payload:
            - pick_code: str
            - extract_file: str = ""
            - extract_dir: str = ""
            - extract_file[]: str
            - extract_file[]: str
            - ...
            - to_pid: int | str = 0
            - paths: str = "文件"
        """
        api = complete_url("/2.0/ufile/add_extract_file", base_url=base_url, app=app)
        return self.request(url=api, method="POST", data=payload, async_=async_, **request_kwargs)

    @overload
    def extract_download_url(
        self, 
        /, 
        pickcode: str, 
        path: str, 
        user_agent: None | str = None, 
        app: str = "android", 
        *, 
        async_: Literal[False] = False, 
        **request_kwargs, 
    ) -> P115URL:
        ...
    @overload
    def extract_download_url(
        self, 
        /, 
        pickcode: str, 
        path: str, 
        user_agent: None | str = None, 
        app: str = "android", 
        *, 
        async_: Literal[True], 
        **request_kwargs, 
    ) -> Coroutine[Any, Any, P115URL]:
        ...
    def extract_download_url(
        self, 
        /, 
        pickcode: str, 
        path: str, 
        user_agent: None | str = None, 
        app: str = "android", 
        *, 
        async_: Literal[False, True] = False, 
        **request_kwargs, 
    ) -> P115URL | Coroutine[Any, Any, P115URL]:
        """获取压缩包中文件的下载链接

        :param pickcode: 压缩包的提取码
        :param path: 文件在压缩包中的路径
        :param user_agent: 如果不为 None，则作为请求头 "user-agent" 的值
        :param async_: 是否异步
        :param request_kwargs: 其余请求参数

        :return: 下载链接
        """
        path = path.rstrip("/")
        def gen_step():
            if app in ("", "web", "desktop", "harmony"):
                resp = yield self.extract_download_url_web(
                    {"pick_code": pickcode, "full_name": path.lstrip("/")}, 
                    user_agent=user_agent, 
                    async_=async_, 
                    **request_kwargs, 
                )
            else:
                resp = yield self.extract_download_url_app(
                    {"pick_code": pickcode, "full_name": path.lstrip("/")}, 
                    user_agent=user_agent, 
                    app=app, 
                    async_=async_, 
                    **request_kwargs, 
                )
            from posixpath import basename
            check_response(resp)
            data = resp["data"]
            url = quote(data["url"], safe=":/?&=%#")
            return P115URL(
                url, 
                name=basename(path), 
                path=path, 
                headers=resp["headers"], 
            )
        return run_gen_step(gen_step, async_)

    @overload
    def extract_download_url_app(
        self, 
        payload: dict, 
        /, 
        base_url: str | Callable[[], str] = "https://proapi.115.com", 
        user_agent: None | str = None, 
        app: str = "android", 
        *, 
        async_: Literal[False] = False, 
        **request_kwargs, 
    ) -> dict:
        ...
    @overload
    def extract_download_url_app(
        self, 
        payload: dict, 
        /, 
        base_url: str | Callable[[], str] = "https://proapi.115.com", 
        user_agent: None | str = None, 
        app: str = "android", 
        *, 
        async_: Literal[True], 
        **request_kwargs, 
    ) -> Coroutine[Any, Any, dict]:
        ...
    def extract_download_url_app(
        self, 
        payload: dict, 
        /, 
        base_url: str | Callable[[], str] = "https://proapi.115.com", 
        user_agent: None | str = None, 
        app: str = "android", 
        *, 
        async_: Literal[False, True] = False, 
        **request_kwargs, 
    ) -> dict | Coroutine[Any, Any, dict]:
        """获取压缩包中文件的下载链接

        GET https://proapi.115.com/android/2.0/ufile/extract_down_file

        :payload:
            - pick_code: str
            - full_name: str
            - dl: int = <default>
        """
        api = complete_url("/2.0/ufile/extract_down_file", base_url=base_url, app=app)
        headers = request_kwargs["headers"] = dict(request_kwargs.get("headers") or ())
        if user_agent is None:
            headers.setdefault("user-agent", "")
        else:
            headers["user-agent"] = user_agent
        def parse(_, content: bytes, /) -> dict:
            json = json_loads(content)
            json["headers"] = headers
            return json
        request_kwargs.setdefault("parse", parse)
        return self.request(url=api, params=payload, async_=async_, **request_kwargs)

    @overload
    def extract_download_url_web(
        self, 
        payload: dict, 
        /, 
        base_url: str | Callable[[], str] = "https://webapi.115.com", 
        user_agent: None | str = None, 
        *, 
        async_: Literal[False] = False, 
        **request_kwargs, 
    ) -> dict:
        ...
    @overload
    def extract_download_url_web(
        self, 
        payload: dict, 
        /, 
        base_url: str | Callable[[], str] = "https://webapi.115.com", 
        user_agent: None | str = None, 
        *, 
        async_: Literal[True], 
        **request_kwargs, 
    ) -> Coroutine[Any, Any, dict]:
        ...
    def extract_download_url_web(
        self, 
        payload: dict, 
        /, 
        base_url: str | Callable[[], str] = "https://webapi.115.com", 
        user_agent: None | str = None, 
        *, 
        async_: Literal[False, True] = False, 
        **request_kwargs, 
    ) -> dict | Coroutine[Any, Any, dict]:
        """获取压缩包中文件的下载链接

        GET https://webapi.115.com/files/extract_down_file

        :payload:
            - pick_code: str
            - full_name: str
        """
        api = complete_url("/files/extract_down_file", base_url=base_url)
        headers = request_kwargs["headers"] = dict(request_kwargs.get("headers") or ())
        if user_agent is None:
            headers.setdefault("user-agent", "")
        else:
            headers["user-agent"] = user_agent
        def parse(resp, content: bytes, /) -> dict:
            json = json_loads(content)
            if "Set-Cookie" in resp.headers:
                if isinstance(resp.headers, Mapping):
                    match = CRE_SET_COOKIE.search(resp.headers["Set-Cookie"])
                    if match is not None:
                        headers["Cookie"] = match[0]
                else:
                    for k, v in reversed(resp.headers.items()):
                        if k == "Set-Cookie" and CRE_SET_COOKIE.match(v) is not None:
                            headers["Cookie"] = v
                            break
            json["headers"] = headers
            return json
        request_kwargs.setdefault("parse", parse)
        return self.request(url=api, params=payload, async_=async_, **request_kwargs)

    @overload
    def extract_file(
        self, 
        /, 
        pickcode: str, 
        files: str | Iterable[str] = "", 
        dirs: str | Iterable[str] = "", 
        dirname: str = "", 
        *, 
        to_pid: int | str = 0, 
        async_: Literal[False] = False, 
        **request_kwargs, 
    ) -> dict:
        ...
    @overload
    def extract_file(
        self, 
        /, 
        pickcode: str, 
        files: str | Iterable[str] = "", 
        dirs: str | Iterable[str] = "", 
        dirname: str = "", 
        to_pid: int | str = 0, 
        *, 
        async_: Literal[True], 
        **request_kwargs, 
    ) -> Coroutine[Any, Any, dict]:
        ...
    def extract_file(
        self, 
        /, 
        pickcode: str, 
        files: str | Iterable[str] = "", 
        dirs: str | Iterable[str] = "", 
        dirname: str = "", 
        to_pid: int | str = 0, 
        *, 
        async_: Literal[False, True] = False, 
        **request_kwargs, 
    ) -> dict | Coroutine[Any, Any, dict]:
        """解压缩到某个目录，是对 `extract_add_file` 的封装，推荐使用

        :param pickcode: 压缩文件的提取码
        :param files:    待解压缩的文件路径（相对于 ``dirname``），如果以 "/" 结尾，则视为目录
        :param dirs:     待解压缩的文件路径（相对于 ``dirname``）
        :param dirname:  压缩包内路径，为空则是压缩包的根目录
        :param to_pid:   解压到网盘的目录 id
        :param async_:   是否异步
        :param request_kwargs: 其它请求参数

        :return: 接口响应，会返回一个 "extract_id"，需要你去轮询获取进度
        """
        dirname = dirname.strip("/")
        data = [
            ("pick_code", pickcode), 
            ("paths", "文件/" + dirname if dirname else "文件"), 
            ("to_pid", to_pid), 
        ]
        paths: list[str] = []
        add_path = paths.append
        if files:
            if isinstance(files, str):
                if files.strip("/"):
                    add_path(files)
            else:
                for p in files:
                    if p.strip("/"):
                        add_path(p)
        if dirs:
            if isinstance(dirs, str):
                if dirs.strip("/"):
                    add_path(dirs + "/")
            else:
                for p in dirs:
                    if p.strip("/"):
                        add_path(p + "/")
        def gen_step():
            if not paths:
                next_marker = ""
                while True:
                    resp = yield self.extract_list(
                        pickcode=pickcode, 
                        path=dirname, 
                        next_marker=next_marker, 
                        async_=async_, 
                        **request_kwargs, 
                    )
                    check_response(resp)
                    for p in resp["data"]["list"]:
                        if p["file_category"]:
                            add_path(p["file_name"])
                        else:
                            add_path(p["file_name"] + "/")
                    if not (next_marker := resp["data"].get("next_marker")):
                        break
            data.extend(
                ("extract_dir[]" if path.endswith("/") else "extract_file[]", path.strip("/")) 
                for path in paths
            )
            return self.extract_add_file(data, async_=async_, **request_kwargs)
        return run_gen_step(gen_step, async_)

    @overload
    def extract_file_app(
        self, 
        /, 
        pickcode: str, 
        files: str | Iterable[str] = "", 
        dirs: str | Iterable[str] = "", 
        dirname: str = "", 
        *, 
        to_pid: int | str = 0, 
        async_: Literal[False] = False, 
        **request_kwargs, 
    ) -> dict:
        ...
    @overload
    def extract_file_app(
        self, 
        /, 
        pickcode: str, 
        files: str | Iterable[str] = "", 
        dirs: str | Iterable[str] = "", 
        dirname: str = "", 
        to_pid: int | str = 0, 
        *, 
        async_: Literal[True], 
        **request_kwargs, 
    ) -> Coroutine[Any, Any, dict]:
        ...
    def extract_file_app(
        self, 
        /, 
        pickcode: str, 
        files: str | Iterable[str] = "", 
        dirs: str | Iterable[str] = "", 
        dirname: str = "", 
        to_pid: int | str = 0, 
        *, 
        async_: Literal[False, True] = False, 
        **request_kwargs, 
    ) -> dict | Coroutine[Any, Any, dict]:
        """解压缩到某个目录，是对 `extract_add_file_app` 的封装，推荐使用

        :param pickcode: 压缩文件的提取码
        :param files:    待解压缩的文件路径（相对于 ``dirname``），如果以 "/" 结尾，则视为目录
        :param dirs:     待解压缩的文件路径（相对于 ``dirname``）
        :param dirname:  压缩包内路径，为空则是压缩包的根目录
        :param to_pid:   解压到网盘的目录 id
        :param async_:   是否异步
        :param request_kwargs: 其它请求参数

        :return: 接口响应，会返回一个 "extract_id"，需要你去轮询获取进度
        """
        dirname = dirname.strip("/")
        data = [
            ("pick_code", pickcode), 
            ("paths", "文件/" + dirname if dirname else "文件"), 
            ("to_pid", to_pid), 
        ]
        paths: list[str] = []
        add_path = paths.append
        if files:
            if isinstance(files, str):
                if files.strip("/"):
                    add_path(files)
            else:
                for p in files:
                    if p.strip("/"):
                        add_path(p)
        if dirs:
            if isinstance(dirs, str):
                if dirs.strip("/"):
                    add_path(dirs + "/")
            else:
                for p in dirs:
                    if p.strip("/"):
                        add_path(p + "/")
        def gen_step():
            if not paths:
                next_marker = ""
                while True:
                    resp = yield self.extract_list_app(
                        pickcode=pickcode, 
                        path=dirname, 
                        next_marker=next_marker, 
                        async_=async_, 
                        **request_kwargs, 
                    )
                    check_response(resp)
                    for p in resp["data"]["list"]:
                        if p["file_category"]:
                            add_path(p["file_name"])
                        else:
                            add_path(p["file_name"] + "/")
                    if not (next_marker := resp["data"].get("next_marker")):
                        break
            data.extend(
                ("extract_dir[]" if path.endswith("/") else "extract_file[]", path.strip("/")) 
                for path in paths
            )
            return self.extract_add_file_app(data, async_=async_, **request_kwargs)
        return run_gen_step(gen_step, async_)

    @overload
    def extract_folders(
        self, 
        payload: dict, 
        /, 
        base_url: str | Callable[[], str] = "https://webapi.115.com", 
        *, 
        async_: Literal[False] = False, 
        **request_kwargs, 
    ) -> dict:
        ...
    @overload
    def extract_folders(
        self, 
        payload: dict, 
        /, 
        base_url: str | Callable[[], str] = "https://webapi.115.com", 
        *, 
        async_: Literal[True], 
        **request_kwargs, 
    ) -> Coroutine[Any, Any, dict]:
        ...
    def extract_folders(
        self, 
        payload: dict, 
        /, 
        base_url: str | Callable[[], str] = "https://webapi.115.com", 
        *, 
        async_: Literal[False, True] = False, 
        **request_kwargs, 
    ) -> dict | Coroutine[Any, Any, dict]:
        """获取压缩文件的文件列表（简略信息）

        GET https://webapi.115.com/files/extract_folders

        :payload:
            - pick_code: str 💡 压缩包文件的提取码
            - full_dir_name: str 💡 多个用逗号 "," 隔开
            - full_file_name: str = <default> 💡 多个用逗号 "," 隔开
        """
        api = complete_url("/files/extract_folders", base_url=base_url)
        return self.request(url=api, params=payload, async_=async_, **request_kwargs)

    @overload
    def extract_folders_app(
        self, 
        payload: dict, 
        /, 
        app: str = "android", 
        base_url: str | Callable[[], str] = "https://proapi.115.com", 
        *, 
        async_: Literal[False] = False, 
        **request_kwargs, 
    ) -> dict:
        ...
    @overload
    def extract_folders_app(
        self, 
        payload: dict, 
        /, 
        app: str = "android", 
        base_url: str | Callable[[], str] = "https://proapi.115.com", 
        *, 
        async_: Literal[True], 
        **request_kwargs, 
    ) -> Coroutine[Any, Any, dict]:
        ...
    def extract_folders_app(
        self, 
        payload: dict, 
        /, 
        app: str = "android", 
        base_url: str | Callable[[], str] = "https://proapi.115.com", 
        *, 
        async_: Literal[False, True] = False, 
        **request_kwargs, 
    ) -> dict | Coroutine[Any, Any, dict]:
        """获取压缩文件的文件列表（简略信息）

        GET https://proapi.115.com/android/2.0/ufile/extract_folders

        :payload:
            - pick_code: str 💡 压缩包文件的提取码
            - full_dir_name: str 💡 多个用逗号 "," 隔开
            - full_file_name: str = <default> 💡 多个用逗号 "," 隔开
        """
        api = complete_url("/2.0/ufile/extract_folders", base_url=base_url, app=app)
        return self.request(url=api, params=payload, async_=async_, **request_kwargs)

    @overload
    def extract_folders_post(
        self, 
        payload: dict, 
        /, 
        base_url: str | Callable[[], str] = "https://webapi.115.com", 
        *, 
        async_: Literal[False] = False, 
        **request_kwargs, 
    ) -> dict:
        ...
    @overload
    def extract_folders_post(
        self, 
        payload: dict, 
        /, 
        base_url: str | Callable[[], str] = "https://webapi.115.com", 
        *, 
        async_: Literal[True], 
        **request_kwargs, 
    ) -> Coroutine[Any, Any, dict]:
        ...
    def extract_folders_post(
        self, 
        payload: dict, 
        /, 
        base_url: str | Callable[[], str] = "https://webapi.115.com", 
        *, 
        async_: Literal[False, True] = False, 
        **request_kwargs, 
    ) -> dict | Coroutine[Any, Any, dict]:
        """获取压缩文件的文件列表是否可批量下载（最高支持1万的文件操作数量）

        POST https://webapi.115.com/files/extract_folders

        :payload:
            - pick_code: str 💡 压缩包文件的提取码
            - full_dir_name: str 💡 多个用逗号 "," 隔开
            - full_file_name: str = <default> 💡 多个用逗号 "," 隔开
        """
        api = complete_url("/files/extract_folders", base_url=base_url)
        return self.request(url=api, method="POST", data=payload, async_=async_, **request_kwargs)

    @overload
    def extract_folders_post_app(
        self, 
        payload: dict, 
        /, 
        app: str = "android", 
        base_url: str | Callable[[], str] = "https://proapi.115.com", 
        *, 
        async_: Literal[False] = False, 
        **request_kwargs, 
    ) -> dict:
        ...
    @overload
    def extract_folders_post_app(
        self, 
        payload: dict, 
        /, 
        app: str = "android", 
        base_url: str | Callable[[], str] = "https://proapi.115.com", 
        *, 
        async_: Literal[True], 
        **request_kwargs, 
    ) -> Coroutine[Any, Any, dict]:
        ...
    def extract_folders_post_app(
        self, 
        payload: dict, 
        /, 
        app: str = "android", 
        base_url: str | Callable[[], str] = "https://proapi.115.com", 
        *, 
        async_: Literal[False, True] = False, 
        **request_kwargs, 
    ) -> dict | Coroutine[Any, Any, dict]:
        """获取压缩文件的文件列表是否可批量下载（最高支持1万的文件操作数量）

        POST https://proapi.115.com/android/2.0/ufile/extract_folders

        :payload:
            - pick_code: str 💡 压缩包文件的提取码
            - full_dir_name: str 💡 多个用逗号 "," 隔开
            - full_file_name: str = <default> 💡 多个用逗号 "," 隔开
        """
        api = complete_url("/2.0/ufile/extract_folders", base_url=base_url, app=app)
        return self.request(url=api, method="POST", data=payload, async_=async_, **request_kwargs)

    @overload
    def extract_info(
        self, 
        payload: str | dict, 
        /, 
        base_url: str | Callable[[], str] = "https://webapi.115.com", 
        *, 
        async_: Literal[False] = False, 
        **request_kwargs, 
    ) -> dict:
        ...
    @overload
    def extract_info(
        self, 
        payload: str | dict, 
        /, 
        base_url: str | Callable[[], str] = "https://webapi.115.com", 
        *, 
        async_: Literal[True], 
        **request_kwargs, 
    ) -> Coroutine[Any, Any, dict]:
        ...
    def extract_info(
        self, 
        payload: str | dict, 
        /, 
        base_url: str | Callable[[], str] = "https://webapi.115.com", 
        *, 
        async_: Literal[False, True] = False, 
        **request_kwargs, 
    ) -> dict | Coroutine[Any, Any, dict]:
        """获取压缩文件的文件列表，推荐直接用封装函数 `extract_list`

        GET https://webapi.115.com/files/extract_info

        :payload:
            - pick_code: str
            - file_name: str = "" 💡 在压缩包中的相对路径
            - next_marker: str = ""
            - page_count: int | str = 999 💡 分页大小，介于 1-999
            - paths: str = "文件" 💡 省略即可
        """
        api = complete_url("/files/extract_info", base_url=base_url)
        if isinstance(payload, str):
            payload = {"pick_code": payload}
        payload = {"paths": "文件", "page_count": 999, "next_marker": "", "file_name": "", **payload}
        return self.request(url=api, params=payload, async_=async_, **request_kwargs)

    @overload
    def extract_info_app(
        self, 
        payload: str | dict, 
        /, 
        app: str = "android", 
        base_url: str | Callable[[], str] = "https://proapi.115.com", 
        *, 
        async_: Literal[False] = False, 
        **request_kwargs, 
    ) -> dict:
        ...
    @overload
    def extract_info_app(
        self, 
        payload: str | dict, 
        /, 
        app: str = "android", 
        base_url: str | Callable[[], str] = "https://proapi.115.com", 
        *, 
        async_: Literal[True], 
        **request_kwargs, 
    ) -> Coroutine[Any, Any, dict]:
        ...
    def extract_info_app(
        self, 
        payload: str | dict, 
        /, 
        app: str = "android", 
        base_url: str | Callable[[], str] = "https://proapi.115.com", 
        *, 
        async_: Literal[False, True] = False, 
        **request_kwargs, 
    ) -> dict | Coroutine[Any, Any, dict]:
        """获取压缩文件的文件列表，推荐直接用封装函数 `extract_list_app`

        GET https://proapi.115.com/android/2.0/ufile/extract_info

        :payload:
            - pick_code: str
            - file_name: str = "" 💡 在压缩包中的相对路径
            - next_marker: str = ""
            - page_count: int | str = 999 💡 分页大小，介于 1-999
            - paths: str = "文件" 💡 省略即可
        """
        api = complete_url("/2.0/ufile/extract_info", base_url=base_url, app=app)
        if isinstance(payload, str):
            payload = {"pick_code": payload}
        payload = {"paths": "文件", "page_count": 999, "next_marker": "", "file_name": "", **payload}
        return self.request(url=api, params=payload, async_=async_, **request_kwargs)

    @overload
    def extract_list(
        self, 
        /, 
        pickcode: str, 
        path: str = "", 
        next_marker: str = "", 
        page_count: int = 999, 
        base_url: str | Callable[[], str] = "https://webapi.115.com", 
        *, 
        async_: Literal[False] = False, 
        **request_kwargs, 
    ) -> dict:
        ...
    @overload
    def extract_list(
        self, 
        /, 
        pickcode: str, 
        path: str = "", 
        next_marker: str = "", 
        page_count: int = 999, 
        base_url: str | Callable[[], str] = "https://webapi.115.com", 
        *, 
        async_: Literal[True], 
        **request_kwargs, 
    ) -> Coroutine[Any, Any, dict]:
        ...
    def extract_list(
        self, 
        /, 
        pickcode: str, 
        path: str = "", 
        next_marker: str = "", 
        page_count: int = 999, 
        base_url: str | Callable[[], str] = "https://webapi.115.com", 
        *, 
        async_: Literal[False, True] = False, 
        **request_kwargs, 
    ) -> dict | Coroutine[Any, Any, dict]:
        """获取压缩文件的文件列表，此方法是对 `extract_info` 的封装，推荐使用

        :param pickcode: 压缩文件的提取码
        :param path: 压缩包内（目录）路径，为空则是压缩包的根目录
        :param next_marker: 翻页标记，用来获取下一页
        :param page_count: 这一页有多少条数据，范围在 ``[1, 999]``
        :param base_url: 接口的基地址
        :param async_: 是否异步
        :param request_kwargs: 其它请求参数

        :return: 接口响应
        """
        if not 1 <= page_count <= 999:
            page_count = 999
        payload = {
            "pick_code": pickcode, 
            "file_name": path.strip("/"), 
            "paths": "文件", 
            "next_marker": next_marker, 
            "page_count": page_count, 
        }
        return self.extract_info(
            payload, 
            base_url=base_url, 
            async_=async_, 
            **request_kwargs, 
        )

    @overload
    def extract_list_app(
        self, 
        /, 
        pickcode: str, 
        path: str, 
        next_marker: str, 
        page_count: int, 
        app: str = "android", 
        base_url: str | Callable[[], str] = "https://proapi.115.com", 
        *, 
        async_: Literal[False] = False, 
        **request_kwargs, 
    ) -> dict:
        ...
    @overload
    def extract_list_app(
        self, 
        /, 
        pickcode: str, 
        path: str, 
        next_marker: str, 
        page_count: int, 
        app: str = "android", 
        base_url: str | Callable[[], str] = "https://proapi.115.com", 
        *, 
        async_: Literal[True], 
        **request_kwargs, 
    ) -> Coroutine[Any, Any, dict]:
        ...
    def extract_list_app(
        self, 
        /, 
        pickcode: str, 
        path: str = "", 
        next_marker: str = "", 
        page_count: int = 999, 
        app: str = "android", 
        base_url: str | Callable[[], str] = "https://proapi.115.com", 
        *, 
        async_: Literal[False, True] = False, 
        **request_kwargs, 
    ) -> dict | Coroutine[Any, Any, dict]:
        """获取压缩文件的文件列表，此方法是对 `extract_info_app` 的封装，推荐使用

        :param pickcode: 压缩文件的提取码
        :param path: 压缩包内（目录）路径，为空则是压缩包的根目录
        :param next_marker: 翻页标记，用来获取下一页
        :param page_count: 这一页有多少条数据，范围在 ``[1, 999]``
        :param base_url: 接口的基地址
        :param async_: 是否异步
        :param request_kwargs: 其它请求参数

        :return: 接口响应
        """
        if not 1 <= page_count <= 999:
            page_count = 999
        payload = {
            "pick_code": pickcode, 
            "file_name": path.strip("/"), 
            "paths": "文件", 
            "next_marker": next_marker, 
            "page_count": page_count, 
        }
        return self.extract_info_app(
            payload, 
            app=app, 
            base_url=base_url, 
            async_=async_, 
            **request_kwargs, 
        )

    @overload
    def extract_progress(
        self, 
        payload: int | str | dict, 
        /, 
        base_url: str | Callable[[], str] = "https://webapi.115.com", 
        *, 
        async_: Literal[False] = False, 
        **request_kwargs, 
    ) -> dict:
        ...
    @overload
    def extract_progress(
        self, 
        payload: int | str | dict, 
        /, 
        base_url: str | Callable[[], str] = "https://webapi.115.com", 
        *, 
        async_: Literal[True], 
        **request_kwargs, 
    ) -> Coroutine[Any, Any, dict]:
        ...
    def extract_progress(
        self, 
        payload: int | str | dict, 
        /, 
        base_url: str | Callable[[], str] = "https://webapi.115.com", 
        *, 
        async_: Literal[False, True] = False, 
        **request_kwargs, 
    ) -> dict | Coroutine[Any, Any, dict]:
        """获取 解压缩到目录 任务的进度

        GET https://webapi.115.com/files/add_extract_file

        :payload:
            - extract_id: str
        """
        api = complete_url("/files/add_extract_file", base_url=base_url)
        if isinstance(payload, (int, str)):
            payload = {"extract_id": payload}
        return self.request(url=api, params=payload, async_=async_, **request_kwargs)

    @overload
    def extract_progress_app(
        self, 
        payload: int | str | dict, 
        /, 
        app: str = "android", 
        base_url: str | Callable[[], str] = "https://proapi.115.com", 
        *, 
        async_: Literal[False] = False, 
        **request_kwargs, 
    ) -> dict:
        ...
    @overload
    def extract_progress_app(
        self, 
        payload: int | str | dict, 
        /, 
        app: str = "android", 
        base_url: str | Callable[[], str] = "https://proapi.115.com", 
        *, 
        async_: Literal[True], 
        **request_kwargs, 
    ) -> Coroutine[Any, Any, dict]:
        ...
    def extract_progress_app(
        self, 
        payload: int | str | dict, 
        /, 
        app: str = "android", 
        base_url: str | Callable[[], str] = "https://proapi.115.com", 
        *, 
        async_: Literal[False, True] = False, 
        **request_kwargs, 
    ) -> dict | Coroutine[Any, Any, dict]:
        """获取 解压缩到目录 任务的进度

        GET https://proapi.115.com/android/2.0/ufile/add_extract_file

        :payload:
            - extract_id: str
        """
        api = complete_url("/2.0/ufile/add_extract_file", base_url=base_url, app=app)
        if isinstance(payload, (int, str)):
            payload = {"extract_id": payload}
        return self.request(url=api, params=payload, async_=async_, **request_kwargs)

    @overload
    def extract_push(
        self, 
        payload: str | dict, 
        /, 
        base_url: str | Callable[[], str] = "https://webapi.115.com", 
        *, 
        async_: Literal[False] = False, 
        **request_kwargs, 
    ) -> dict:
        ...
    @overload
    def extract_push(
        self, 
        payload: str | dict, 
        /, 
        base_url: str | Callable[[], str] = "https://webapi.115.com", 
        *, 
        async_: Literal[True], 
        **request_kwargs, 
    ) -> Coroutine[Any, Any, dict]:
        ...
    def extract_push(
        self, 
        payload: str | dict, 
        /, 
        base_url: str | Callable[[], str] = "https://webapi.115.com", 
        *, 
        async_: Literal[False, True] = False, 
        **request_kwargs, 
    ) -> dict | Coroutine[Any, Any, dict]:
        """推送一个解压缩任务给服务器，完成后，就可以查看压缩包的文件列表了

        .. warning::
            只能云解压 20GB 以内文件，不支持云解压分卷压缩包，只支持 .zip、.rar 和 .7z 等

        POST https://webapi.115.com/files/push_extract

        :payload:
            - pick_code: str
            - secret: str = "" 💡 解压密码
        """
        api = complete_url("/files/push_extract", base_url=base_url)
        if isinstance(payload, str):
            payload = {"pick_code": payload}
        return self.request(url=api, method="POST", data=payload, async_=async_, **request_kwargs)

    @overload
    def extract_push_app(
        self, 
        payload: str | dict, 
        /, 
        app: str = "android", 
        base_url: str | Callable[[], str] = "https://proapi.115.com", 
        *, 
        async_: Literal[False] = False, 
        **request_kwargs, 
    ) -> dict:
        ...
    @overload
    def extract_push_app(
        self, 
        payload: str | dict, 
        /, 
        app: str = "android", 
        base_url: str | Callable[[], str] = "https://proapi.115.com", 
        *, 
        async_: Literal[True], 
        **request_kwargs, 
    ) -> Coroutine[Any, Any, dict]:
        ...
    def extract_push_app(
        self, 
        payload: str | dict, 
        /, 
        app: str = "android", 
        base_url: str | Callable[[], str] = "https://proapi.115.com", 
        *, 
        async_: Literal[False, True] = False, 
        **request_kwargs, 
    ) -> dict | Coroutine[Any, Any, dict]:
        """推送一个解压缩任务给服务器，完成后，就可以查看压缩包的文件列表了

        .. warning::
            只能云解压 20GB 以内文件，不支持云解压分卷压缩包，只支持 .zip、.rar 和 .7z 等

        POST https://proapi.115.com/android/2.0/ufile/push_extract

        :payload:
            - pick_code: str
            - secret: str = "" 💡 解压密码
        """
        api = complete_url("/2.0/ufile/push_extract", base_url=base_url, app=app)
        if isinstance(payload, str):
            payload = {"pick_code": payload}
        return self.request(url=api, method="POST", data=payload, async_=async_, **request_kwargs)

    @overload
    def extract_push_progress(
        self, 
        payload: str | dict, 
        /, 
        base_url: str | Callable[[], str] = "https://webapi.115.com", 
        *, 
        async_: Literal[False] = False, 
        **request_kwargs, 
    ) -> dict:
        ...
    @overload
    def extract_push_progress(
        self, 
        payload: str | dict, 
        /, 
        base_url: str | Callable[[], str] = "https://webapi.115.com", 
        *, 
        async_: Literal[True], 
        **request_kwargs, 
    ) -> Coroutine[Any, Any, dict]:
        ...
    def extract_push_progress(
        self, 
        payload: str | dict, 
        /, 
        base_url: str | Callable[[], str] = "https://webapi.115.com", 
        *, 
        async_: Literal[False, True] = False, 
        **request_kwargs, 
    ) -> dict | Coroutine[Any, Any, dict]:
        """查询解压缩任务的进度

        GET https://webapi.115.com/files/push_extract

        :payload:
            - pick_code: str
        """
        api = complete_url("/files/push_extract", base_url=base_url)
        if isinstance(payload, str):
            payload = {"pick_code": payload}
        return self.request(url=api, params=payload, async_=async_, **request_kwargs)

    @overload
    def extract_push_progress_app(
        self, 
        payload: str | dict, 
        /, 
        app: str = "android", 
        base_url: str | Callable[[], str] = "https://proapi.115.com", 
        *, 
        async_: Literal[False] = False, 
        **request_kwargs, 
    ) -> dict:
        ...
    @overload
    def extract_push_progress_app(
        self, 
        payload: str | dict, 
        /, 
        app: str = "android", 
        base_url: str | Callable[[], str] = "https://proapi.115.com", 
        *, 
        async_: Literal[True], 
        **request_kwargs, 
    ) -> Coroutine[Any, Any, dict]:
        ...
    def extract_push_progress_app(
        self, 
        payload: str | dict, 
        /, 
        app: str = "android", 
        base_url: str | Callable[[], str] = "https://proapi.115.com", 
        *, 
        async_: Literal[False, True] = False, 
        **request_kwargs, 
    ) -> dict | Coroutine[Any, Any, dict]:
        """查询解压缩任务的进度

        GET https://proapi.115.com/android/2.0/ufile/push_extract

        :payload:
            - pick_code: str
        """
        api = complete_url("/2.0/ufile/push_extract", base_url=base_url, app=app)
        if isinstance(payload, str):
            payload = {"pick_code": payload}
        return self.request(url=api, params=payload, async_=async_, **request_kwargs)

    ########## File System API ##########

    @overload
    def fs_batch_edit(
        self, 
        payload: list | dict, 
        /, 
        base_url: str | Callable[[], str] = "https://webapi.115.com", 
        *, 
        async_: Literal[False] = False, 
        **request_kwargs, 
    ) -> dict:
        ...
    @overload
    def fs_batch_edit(
        self, 
        payload: list | dict, 
        /, 
        base_url: str | Callable[[], str] = "https://webapi.115.com", 
        *, 
        async_: Literal[True], 
        **request_kwargs, 
    ) -> Coroutine[Any, Any, dict]:
        ...
    def fs_batch_edit(
        self, 
        payload: list | dict, 
        /, 
        base_url: str | Callable[[], str] = "https://webapi.115.com", 
        *, 
        async_: Literal[False, True] = False, 
        **request_kwargs, 
    ) -> dict | Coroutine[Any, Any, dict]:
        """批量设置文件或目录（显示时长等）

        POST https://webapi.115.com/files/batch_edit

        :payload:
            - show_play_long[{fid}]: 0 | 1 = 1 💡 设置或取消显示时长
        """
        api = complete_url("/files/batch_edit", base_url=base_url)
        return self.request(url=api, method="POST", data=payload, async_=async_, **request_kwargs)

    @overload
    def fs_batch_edit_app(
        self, 
        payload: list | dict, 
        /, 
        app: str = "android", 
        base_url: str | Callable[[], str] = "https://proapi.115.com", 
        *, 
        async_: Literal[False] = False, 
        **request_kwargs, 
    ) -> dict:
        ...
    @overload
    def fs_batch_edit_app(
        self, 
        payload: list | dict, 
        /, 
        app: str = "android", 
        base_url: str | Callable[[], str] = "https://proapi.115.com", 
        *, 
        async_: Literal[True], 
        **request_kwargs, 
    ) -> Coroutine[Any, Any, dict]:
        ...
    def fs_batch_edit_app(
        self, 
        payload: list | dict, 
        /, 
        app: str = "android", 
        base_url: str | Callable[[], str] = "https://proapi.115.com", 
        *, 
        async_: Literal[False, True] = False, 
        **request_kwargs, 
    ) -> dict | Coroutine[Any, Any, dict]:
        """批量设置文件或目录（显示时长等）

        POST https://proapi.115.com/android/files/batch_edit

        :payload:
            - show_play_long[{fid}]: 0 | 1 = 1 💡 设置或取消显示时长
        """
        api = complete_url("/files/batch_edit", base_url=base_url, app=app)
        return self.request(url=api, method="POST", data=payload, async_=async_, **request_kwargs)

    @overload
    def fs_category_get(
        self, 
        payload: int | str | dict, 
        /, 
        base_url: str | Callable[[], str] = "https://webapi.115.com", 
        *, 
        async_: Literal[False] = False, 
        **request_kwargs, 
    ) -> dict:
        ...
    @overload
    def fs_category_get(
        self, 
        payload: int | str | dict, 
        /, 
        base_url: str | Callable[[], str] = "https://webapi.115.com", 
        *, 
        async_: Literal[True], 
        **request_kwargs, 
    ) -> Coroutine[Any, Any, dict]:
        ...
    def fs_category_get(
        self, 
        payload: int | str | dict, 
        /, 
        base_url: str | Callable[[], str] = "https://webapi.115.com", 
        *, 
        async_: Literal[False, True] = False, 
        **request_kwargs, 
    ) -> dict | Coroutine[Any, Any, dict]:
        """显示属性，可获取文件或目录的统计信息（提示：但得不到根目录的统计信息，所以 cid 为 0 时无意义）

        GET https://webapi.115.com/category/get

        :payload:
            - cid: int | str
            - aid: int = 1 💡 area_id

                - 0: 会被视为 1
                - 1: 正常文件
                - 2: <unknown>
                - 3: <unknown>
                - 4: <unknown>
                - 5: <unknown>
                - 7: 回收站文件
                - 9: <unknown>
                - 12:瞬间文件
                - 15: <unknown>
                - 120: 彻底删除文件、简历附件
                - <其它>: 会被视为 0

            - status: 0 | 1 = <default>
        """
        api = complete_url("/category/get", base_url=base_url)
        if isinstance(payload, (int, str)):
            payload = {"cid": payload}
        payload.setdefault("aid", 1)
        return self.request(url=api, params=payload, async_=async_, **request_kwargs)

    @overload
    def fs_category_get_app(
        self, 
        payload: int | str | dict, 
        /, 
        app: str = "android", 
        base_url: str | Callable[[], str] = "https://proapi.115.com", 
        *, 
        async_: Literal[False] = False, 
        **request_kwargs, 
    ) -> dict:
        ...
    @overload
    def fs_category_get_app(
        self, 
        payload: int | str | dict, 
        /, 
        app: str = "android", 
        base_url: str | Callable[[], str] = "https://proapi.115.com", 
        *, 
        async_: Literal[True], 
        **request_kwargs, 
    ) -> Coroutine[Any, Any, dict]:
        ...
    def fs_category_get_app(
        self, 
        payload: int | str | dict, 
        /, 
        app: str = "android", 
        base_url: str | Callable[[], str] = "https://proapi.115.com", 
        *, 
        async_: Literal[False, True] = False, 
        **request_kwargs, 
    ) -> dict | Coroutine[Any, Any, dict]:
        """显示属性，可获取文件或目录的统计信息（提示：但得不到根目录的统计信息，所以 cid 为 0 时无意义）

        GET https://proapi.115.com/android/2.0/category/get

        :payload:
            - cid: int | str
            - aid: int = 1 💡 area_id

                - 0: 会被视为 1
                - 1: 正常文件
                - 2: <unknown>
                - 3: <unknown>
                - 4: <unknown>
                - 5: <unknown>
                - 7: 回收站文件
                - 9: <unknown>
                - 12:瞬间文件
                - 15: <unknown>
                - 120: 彻底删除文件、简历附件
                - <其它>: 会被视为 0
        """
        api = complete_url("/2.0/category/get", base_url=base_url, app=app)
        if isinstance(payload, (int, str)):
            payload = {"cid": payload}
        payload.setdefault("aid", 1)
        return self.request(url=api, params=payload, async_=async_, **request_kwargs)

    @overload
    def fs_category_shortcut(
        self, 
        payload: int | str | dict = 0, 
        /, 
        base_url: str | Callable[[], str] = "https://webapi.115.com", 
        *, 
        async_: Literal[False] = False, 
        **request_kwargs, 
    ) -> dict:
        ...
    @overload
    def fs_category_shortcut(
        self, 
        payload: int | str | dict = 0, 
        /, 
        base_url: str | Callable[[], str] = "https://webapi.115.com", 
        *, 
        async_: Literal[True], 
        **request_kwargs, 
    ) -> Coroutine[Any, Any, dict]:
        ...
    def fs_category_shortcut(
        self, 
        payload: int | str | dict = 0, 
        /, 
        base_url: str | Callable[[], str] = "https://webapi.115.com", 
        *, 
        async_: Literal[False, True] = False, 
        **request_kwargs, 
    ) -> dict | Coroutine[Any, Any, dict]:
        """快捷入口列表（罗列所有的快捷入口）

        GET https://webapi.115.com/category/shortcut

        :payload:
            - offset: int = 0
            - limit: int = 1150
        """
        api = complete_url("/category/shortcut", base_url=base_url)
        if isinstance(payload, (int, str)):
            payload = {"offset": payload}
        payload = {"limit": 1150, "offset": 0, **payload}
        return self.request(url=api, params=payload, async_=async_, **request_kwargs)

    @overload
    def fs_category_shortcut_set(
        self, 
        payload: int | str | Iterable[int | str] | dict, 
        /, 
        set: bool = True, 
        base_url: str | Callable[[], str] = "https://webapi.115.com", 
        *, 
        async_: Literal[False] = False, 
        **request_kwargs, 
    ) -> dict:
        ...
    @overload
    def fs_category_shortcut_set(
        self, 
        payload: int | str | Iterable[int | str] | dict, 
        /, 
        set: bool = True, 
        base_url: str | Callable[[], str] = "https://webapi.115.com", 
        *, 
        async_: Literal[True], 
        **request_kwargs, 
    ) -> Coroutine[Any, Any, dict]:
        ...
    def fs_category_shortcut_set(
        self, 
        payload: int | str | Iterable[int | str] | dict, 
        /, 
        set: bool = True, 
        base_url: str | Callable[[], str] = "https://webapi.115.com", 
        *, 
        async_: Literal[False, True] = False, 
        **request_kwargs, 
    ) -> dict | Coroutine[Any, Any, dict]:
        """把一个目录设置或取消为快捷入口（快捷入口需要是目录）

        POST https://webapi.115.com/category/shortcut

        :payload:
            - file_id: int | str 目录 id，多个用逗号 "," 隔开
            - op: "add" | "delete" | "top" = "add" 操作代码

                - "add":    添加
                - "delete": 删除
                - "top":    置顶
        """
        api = complete_url("/category/shortcut", base_url=base_url)
        if isinstance(payload, (int, str)):
            payload = {"file_id": payload, "op": ("delete", "add")[set]}
        elif not isinstance(payload, dict):
            payload = {"file_id": ",".join(map(str, payload)), "op": ("delete", "add")[set]}
        else:
            payload = {"op": ("delete", "add")[set], **payload}
        return self.request(url=api, method="POST", data=payload, async_=async_, **request_kwargs)

    @overload
    def fs_copy(
        self, 
        payload: int | str | dict | Iterable[int | str], 
        /, 
        pid: int | str = 0, 
        base_url: str | Callable[[], str] = "https://webapi.115.com", 
        *, 
        async_: Literal[False] = False, 
        **request_kwargs, 
    ) -> dict:
        ...
    @overload
    def fs_copy(
        self, 
        payload: int | str | dict | Iterable[int | str], 
        /, 
        pid: int | str = 0, 
        base_url: str | Callable[[], str] = "https://webapi.115.com", 
        *, 
        async_: Literal[True], 
        **request_kwargs, 
    ) -> Coroutine[Any, Any, dict]:
        ...
    def fs_copy(
        self, 
        payload: int | str | dict | Iterable[int | str], 
        /, 
        pid: int | str = 0, 
        base_url: str | Callable[[], str] = "https://webapi.115.com", 
        *, 
        async_: Literal[False, True] = False, 
        **request_kwargs, 
    ) -> dict | Coroutine[Any, Any, dict]:
        """复制文件或目录

        POST https://webapi.115.com/files/copy

        .. caution::
            ⚠️ 请不要并发执行，限制在 5 万个文件和目录以内

        :payload:
            - fid: int | str 💡 文件或目录 id，只接受单个 id
            - fid[]: int | str
            - ...
            - fid[0]: int | str
            - fid[1]: int | str
            - ...
            - pid: int | str = 0 💡 目标目录 id
        """
        api = complete_url("/files/copy", base_url=base_url)
        if isinstance(payload, (int, str)):
            payload = {"fid": payload}
        elif not isinstance(payload, dict):
            payload = {f"fid[{i}]": fid for i, fid in enumerate(payload)}
        payload.setdefault("pid", pid)
        return self.request(url=api, method="POST", data=payload, async_=async_, **request_kwargs)

    @overload
    def fs_copy_app(
        self, 
        payload: int | str | dict | Iterable[int | str], 
        /, 
        pid: int | str = 0, 
        app: str = "android", 
        base_url: str | Callable[[], str] = "https://proapi.115.com", 
        *, 
        async_: Literal[False] = False, 
        **request_kwargs, 
    ) -> dict:
        ...
    @overload
    def fs_copy_app(
        self, 
        payload: int | str | dict | Iterable[int | str], 
        /, 
        pid: int | str = 0, 
        app: str = "android", 
        base_url: str | Callable[[], str] = "https://proapi.115.com", 
        *, 
        async_: Literal[True], 
        **request_kwargs, 
    ) -> Coroutine[Any, Any, dict]:
        ...
    def fs_copy_app(
        self, 
        payload: int | str | dict | Iterable[int | str], 
        /, 
        pid: int | str = 0, 
        app: str = "android", 
        base_url: str | Callable[[], str] = "https://proapi.115.com", 
        *, 
        async_: Literal[False, True] = False, 
        **request_kwargs, 
    ) -> dict | Coroutine[Any, Any, dict]:
        """复制文件或目录

        POST https://proapi.115.com/android/files/copy

        .. caution::
            ⚠️ 请不要并发执行，限制在 5 万个文件和目录以内

        :payload:
            - fid: int | str 💡 文件或目录的 id，多个用逗号 "," 隔开
            - pid: int | str = 0 💡 目标目录 id
        """
        api = complete_url("/files/copy", base_url=base_url, app=app)
        if isinstance(payload, (int, str)):
            payload = {"fid": payload}
        elif not isinstance(payload, dict):
            payload = {"fid": ",".join(map(str, payload))}
        payload.setdefault("pid", pid) # type: ignore
        return self.request(url=api, method="POST", data=payload, async_=async_, **request_kwargs)

    @overload
    def fs_cover_set(
        self, 
        payload: int | str | Iterable[int | str] | list[tuple] | dict, 
        /, 
        fid_cover: int | str = 0, 
        base_url: str | Callable[[], str] = "https://webapi.115.com", 
        *, 
        async_: Literal[False] = False, 
        **request_kwargs, 
    ) -> dict:
        ...
    @overload
    def fs_cover_set(
        self, 
        payload: int | str | Iterable[int | str] | list[tuple] | dict, 
        /, 
        fid_cover: int | str = 0, 
        base_url: str | Callable[[], str] = "https://webapi.115.com", 
        *, 
        async_: Literal[True], 
        **request_kwargs, 
    ) -> Coroutine[Any, Any, dict]:
        ...
    def fs_cover_set(
        self, 
        payload: int | str | Iterable[int | str] | list[tuple] | dict, 
        /, 
        fid_cover: int | str = 0, 
        base_url: str | Callable[[], str] = "https://webapi.115.com", 
        *, 
        async_: Literal[False, True] = False, 
        **request_kwargs, 
    ) -> dict | Coroutine[Any, Any, dict]:
        """修改封面，可以设置目录的封面，此接口是对 `fs_edit` 的封装
        """
        return self._fs_edit_set(
            payload, 
            "fid_cover", 
            default=fid_cover, 
            base_url=base_url, 
            async_=async_, 
            **request_kwargs, 
        )

    @overload
    def fs_cover_set_app(
        self, 
        payload: int | str | Iterable[int | str] | list[tuple] | dict, 
        /, 
        fid_cover: int | str, 
        app: str = "android", 
        base_url: str | Callable[[], str] = "https://proapi.115.com", 
        *, 
        async_: Literal[False] = False, 
        **request_kwargs, 
    ) -> dict:
        ...
    @overload
    def fs_cover_set_app(
        self, 
        payload: int | str | Iterable[int | str] | list[tuple] | dict, 
        /, 
        fid_cover: int | str, 
        app: str = "android", 
        base_url: str | Callable[[], str] = "https://proapi.115.com", 
        *, 
        async_: Literal[True], 
        **request_kwargs, 
    ) -> Coroutine[Any, Any, dict]:
        ...
    def fs_cover_set_app(
        self, 
        payload: int | str | Iterable[int | str] | list[tuple] | dict, 
        /, 
        fid_cover: int | str = 0, 
        app: str = "android", 
        base_url: str | Callable[[], str] = "https://proapi.115.com", 
        *, 
        async_: Literal[False, True] = False, 
        **request_kwargs, 
    ) -> dict | Coroutine[Any, Any, dict]:
        """修改封面，可以设置目录的封面，此接口是对 `fs_files_update_app` 的封装
        """
        return self._fs_edit_set_app(
            payload, 
            "fid_cover", 
            default=fid_cover, 
            app=app, 
            base_url=base_url, 
            async_=async_, 
            **request_kwargs, 
        )

    @overload
    def fs_delete(
        self, 
        payload: int | str | dict | Iterable[int | str], 
        /, 
        base_url: str | Callable[[], str] = "https://webapi.115.com", 
        *, 
        async_: Literal[False] = False, 
        **request_kwargs, 
    ) -> dict:
        ...
    @overload
    def fs_delete(
        self, 
        payload: int | str | dict | Iterable[int | str], 
        /, 
        base_url: str | Callable[[], str] = "https://webapi.115.com", 
        *, 
        async_: Literal[True], 
        **request_kwargs, 
    ) -> Coroutine[Any, Any, dict]:
        ...
    def fs_delete(
        self, 
        payload: int | str | dict | Iterable[int | str], 
        /, 
        base_url: str | Callable[[], str] = "https://webapi.115.com", 
        *, 
        async_: Literal[False, True] = False, 
        **request_kwargs, 
    ) -> dict | Coroutine[Any, Any, dict]:
        """删除文件或目录

        POST https://webapi.115.com/rb/delete

        .. caution::
            ⚠️ 请不要并发执行，限制在 5 万个文件和目录以内

        .. caution::
            删除和（从回收站）还原是互斥的，同时最多只允许执行一个操作

        .. caution::
            有超过 5 万个文件和文件夹时，不能直接执行删除。如果删除的只是文件，那么在接口响应时，涉及的文件，已经删除完毕；但如果是目录，那么接口响应时，后台可能还在执行，而删除是不可并发的，因此下一个删除任务执行失败时，只需要反复重试即可

        :payload:
            - fid: int | str 💡 文件或目录的 id，多个用逗号 "," 隔开
            - fid[]: int | str
            - ...
            - fid[0]: int | str
            - fid[1]: int | str
            - ...
            - ignore_warn: 0 | 1 = <default>
            - from: int = <default>
            - pid: int = <default>
        """
        api = complete_url("/rb/delete", base_url=base_url)
        if isinstance(payload, (int, str)):
            payload = {"fid": payload}
        elif not isinstance(payload, dict):
            payload = {f"fid[{i}]": fid for i, fid in enumerate(payload)}
        return self.request(url=api, method="POST", data=payload, async_=async_, **request_kwargs)

    @overload
    def fs_delete_app(
        self, 
        payload: int | str | dict | Iterable[int | str], 
        /, 
        app: str = "android", 
        base_url: str | Callable[[], str] = "https://proapi.115.com", 
        *, 
        async_: Literal[False] = False, 
        **request_kwargs, 
    ) -> dict:
        ...
    @overload
    def fs_delete_app(
        self, 
        payload: int | str | dict | Iterable[int | str], 
        /, 
        app: str = "android", 
        base_url: str | Callable[[], str] = "https://proapi.115.com", 
        *, 
        async_: Literal[True], 
        **request_kwargs, 
    ) -> Coroutine[Any, Any, dict]:
        ...
    def fs_delete_app(
        self, 
        payload: int | str | dict | Iterable[int | str], 
        /, 
        app: str = "android", 
        base_url: str | Callable[[], str] = "https://proapi.115.com", 
        *, 
        async_: Literal[False, True] = False, 
        **request_kwargs, 
    ) -> dict | Coroutine[Any, Any, dict]:
        """删除文件或目录

        POST https://proapi.115.com/android/rb/delete

        .. caution::
            ⚠️ 请不要并发执行，限制在 5 万个文件和目录以内

        .. caution::
            删除和（从回收站）还原是互斥的，同时最多只允许执行一个操作

        .. caution::
            有超过 5 万个文件和文件夹时，不能直接执行删除。如果删除的只是文件，那么在接口响应时，涉及的文件，已经删除完毕；但如果是目录，那么接口响应时，后台可能还在执行，而删除是不可并发的，因此下一个删除任务执行失败时，只需要反复重试即可

        .. note::
            此接口还能删除 `aid=12` 下的文件，且不会经过回收站（`aid=7`），而是彻底删除（`aid=120`）

            .. code:: python
                from pathlib import Path
                from itertools import batched
                from p115client import P115Client

                client = P115Client(Path("~/115-cookies.txt").expanduser())
                while True:
                    fids = [info["fid"] for info in client.fs_files({"aid": 12, "limit": 1150, "show_dir": 0})["data"]]
                    if not fids:
                        break
                    client.fs_delete_app(fids)

        :payload:
            - file_ids: int | str 💡 文件或目录的 id，多个用逗号 "," 隔开
            - user_id: int | str = <default> 💡 用户 id
        """
        api = complete_url("/rb/delete", base_url=base_url, app=app)
        if isinstance(payload, (int, str)):
            payload = {"file_ids": payload, "user_id": self.user_id}
        elif isinstance(payload, dict):
            payload = dict(payload, user_id=self.user_id)
        else:
            payload = {"file_ids": ",".join(map(str, payload)), "user_id": self.user_id}
        return self.request(url=api, method="POST", data=payload, async_=async_, **request_kwargs)

    @overload
    def fs_desc(
        self, 
        payload: int | str | dict, 
        /, 
        base_url: str | Callable[[], str] = "https://webapi.115.com", 
        *, 
        async_: Literal[False] = False, 
        **request_kwargs, 
    ) -> dict:
        ...
    @overload
    def fs_desc(
        self, 
        payload: int | str | dict, 
        /, 
        base_url: str | Callable[[], str] = "https://webapi.115.com", 
        *, 
        async_: Literal[True], 
        **request_kwargs, 
    ) -> Coroutine[Any, Any, dict]:
        ...
    def fs_desc(
        self, 
        payload: int | str | dict, 
        /, 
        base_url: str | Callable[[], str] = "https://webapi.115.com", 
        *, 
        async_: Literal[False, True] = False, 
        **request_kwargs, 
    ) -> dict | Coroutine[Any, Any, dict]:
        """获取文件或目录的备注

        GET https://webapi.115.com/files/desc

        :payload:
            - file_id: int | str
            - field: str = <default> 💡 可取示例值："pass"
            - compat: 0 | 1 = 1
            - new_html: 0 | 1 = <default>
        """
        api = complete_url("/files/desc", base_url=base_url)
        if isinstance(payload, (int, str)):
            payload = {"file_id": payload}
        payload = {"compat": 1, **payload}
        return self.request(url=api, params=payload, async_=async_, **request_kwargs)

    @overload
    def fs_desc_app(
        self, 
        payload: str | dict, 
        /, 
        app: str = "android", 
        base_url: str | Callable[[], str] = "https://proapi.115.com", 
        *, 
        async_: Literal[False] = False, 
        **request_kwargs, 
    ) -> dict:
        ...
    @overload
    def fs_desc_app(
        self, 
        payload: str | dict, 
        /, 
        app: str = "android", 
        base_url: str | Callable[[], str] = "https://proapi.115.com", 
        *, 
        async_: Literal[True], 
        **request_kwargs, 
    ) -> Coroutine[Any, Any, dict]:
        ...
    def fs_desc_app(
        self, 
        payload: str | dict, 
        /, 
        app: str = "android", 
        base_url: str | Callable[[], str] = "https://proapi.115.com", 
        *, 
        async_: Literal[False, True] = False, 
        **request_kwargs, 
    ) -> dict | Coroutine[Any, Any, dict]:
        """获取文件或目录的备注

        GET https://proapi.115.com/android/files/desc

        :payload:
            - file_id: int | str
            - field: str = <default> 💡 可取示例值："pass"
            - compat: 0 | 1 = 1
            - new_html: 0 | 1 = <default>
        """
        api = complete_url("/android/files/desc", base_url=base_url, app=app)
        if isinstance(payload, (int, str)):
            payload = {"file_id": payload}
        payload = {"compat": 1, **payload}
        return self.request(url=api, params=payload, async_=async_, **request_kwargs)

    @overload
    def fs_desc_set(
        self, 
        payload: int | str | Iterable[int | str] | list[tuple] | dict, 
        /, 
        desc: str = "", 
        base_url: str | Callable[[], str] = "https://webapi.115.com", 
        *, 
        async_: Literal[False] = False, 
        **request_kwargs, 
    ) -> dict:
        ...
    @overload
    def fs_desc_set(
        self, 
        payload: int | str | Iterable[int | str] | list[tuple] | dict, 
        /, 
        desc: str = "", 
        base_url: str | Callable[[], str] = "https://webapi.115.com", 
        *, 
        async_: Literal[True], 
        **request_kwargs, 
    ) -> Coroutine[Any, Any, dict]:
        ...
    def fs_desc_set(
        self, 
        payload: int | str | Iterable[int | str] | list[tuple] | dict, 
        /, 
        desc: str = "", 
        base_url: str | Callable[[], str] = "https://webapi.115.com", 
        *, 
        async_: Literal[False, True] = False, 
        **request_kwargs, 
    ) -> dict | Coroutine[Any, Any, dict]:
        """为文件或目录设置备注，最多允许 65535 个字节 (64 KB 以内)，此接口是对 `fs_edit` 的封装

        .. hint::
            修改文件备注会更新文件的更新时间，即使什么也没改或者改为空字符串
        """
        return self._fs_edit_set(
            payload, 
            "file_desc", 
            default=desc, 
            base_url=base_url, 
            async_=async_, 
            **request_kwargs, 
        )

    @overload
    def fs_desc_set_app(
        self, 
        payload: int | str | Iterable[int | str] | list[tuple] | dict, 
        /, 
        desc: str = "", 
        app: str = "android", 
        base_url: str | Callable[[], str] = "https://proapi.115.com", 
        *, 
        async_: Literal[False] = False, 
        **request_kwargs, 
    ) -> dict:
        ...
    @overload
    def fs_desc_set_app(
        self, 
        payload: int | str | Iterable[int | str] | list[tuple] | dict, 
        /, 
        desc: str = "", 
        app: str = "android", 
        base_url: str | Callable[[], str] = "https://proapi.115.com", 
        *, 
        async_: Literal[True], 
        **request_kwargs, 
    ) -> Coroutine[Any, Any, dict]:
        ...
    def fs_desc_set_app(
        self, 
        payload: int | str | Iterable[int | str] | list[tuple] | dict, 
        /, 
        desc: str = "", 
        app: str = "android", 
        base_url: str | Callable[[], str] = "https://proapi.115.com", 
        *, 
        async_: Literal[False, True] = False, 
        **request_kwargs, 
    ) -> dict | Coroutine[Any, Any, dict]:
        """为文件或目录设置备注，最多允许 65535 个字节 (64 KB 以内)，此接口是对 `fs_files_update_app` 的封装

        .. hint::
            修改文件备注会更新文件的更新时间，即使什么也没改或者改为空字符串
        """
        return self._fs_edit_set_app(
            payload, 
            "file_desc", 
            desc, 
            app=app, 
            base_url=base_url, 
            async_=async_, 
            **request_kwargs, 
        )

    @overload
    def fs_dir_getid(
        self, 
        payload: str | dict, 
        /, 
        base_url: str | Callable[[], str] = "https://webapi.115.com", 
        *, 
        async_: Literal[False] = False, 
        **request_kwargs, 
    ) -> dict:
        ...
    @overload
    def fs_dir_getid(
        self, 
        payload: str | dict, 
        /, 
        base_url: str | Callable[[], str] = "https://webapi.115.com", 
        *, 
        async_: Literal[True], 
        **request_kwargs, 
    ) -> Coroutine[Any, Any, dict]:
        ...
    def fs_dir_getid(
        self, 
        payload: str | dict, 
        /, 
        base_url: str | Callable[[], str] = "https://webapi.115.com", 
        *, 
        async_: Literal[False, True] = False, 
        **request_kwargs, 
    ) -> dict | Coroutine[Any, Any, dict]:
        """由路径获取对应的 id（但只能获取目录，不能获取文件）

        GET https://webapi.115.com/files/getid

        :payload:
            - path: str
        """
        api = complete_url("/files/getid", base_url=base_url)
        if isinstance(payload, str):
            payload = {"path": payload}
        return self.request(url=api, params=payload, async_=async_, **request_kwargs)

    @overload
    def fs_dir_getid_app(
        self, 
        payload: str | dict, 
        /, 
        app: str = "android", 
        base_url: str | Callable[[], str] = "https://proapi.115.com", 
        *, 
        async_: Literal[False] = False, 
        **request_kwargs, 
    ) -> dict:
        ...
    @overload
    def fs_dir_getid_app(
        self, 
        payload: str | dict, 
        /, 
        app: str = "android", 
        base_url: str | Callable[[], str] = "https://proapi.115.com", 
        *, 
        async_: Literal[True], 
        **request_kwargs, 
    ) -> Coroutine[Any, Any, dict]:
        ...
    def fs_dir_getid_app(
        self, 
        payload: str | dict, 
        /, 
        app: str = "android", 
        base_url: str | Callable[[], str] = "https://proapi.115.com", 
        *, 
        async_: Literal[False, True] = False, 
        **request_kwargs, 
    ) -> dict | Coroutine[Any, Any, dict]:
        """由路径获取对应的 id（但只能获取目录，不能获取文件）

        GET https://proapi.115.com/android/files/getid

        :payload:
            - path: str
        """
        api = complete_url("/files/getid", base_url=base_url, app=app)
        if isinstance(payload, str):
            payload = {"path": payload}
        return self.request(url=api, params=payload, async_=async_, **request_kwargs)

    @overload
    def fs_document(
        self, 
        payload: str | dict, 
        /, 
        base_url: str | Callable[[], str] = "https://webapi.115.com", 
        *, 
        async_: Literal[False] = False, 
        **request_kwargs, 
    ) -> dict:
        ...
    @overload
    def fs_document(
        self, 
        payload: str | dict, 
        /, 
        base_url: str | Callable[[], str] = "https://webapi.115.com", 
        *, 
        async_: Literal[True], 
        **request_kwargs, 
    ) -> Coroutine[Any, Any, dict]:
        ...
    def fs_document(
        self, 
        payload: str | dict, 
        /, 
        base_url: str | Callable[[], str] = "https://webapi.115.com", 
        *, 
        async_: Literal[False, True] = False, 
        **request_kwargs, 
    ) -> dict | Coroutine[Any, Any, dict]:
        """获取图片的各种链接

        GET https://webapi.115.com/files/document

        .. note::
            即使文件格式不正确或者是一个目录，也可返回一些信息（包括 parent_id）

        :payload:
            - pickcode: str
        """
        api = complete_url("/files/document", base_url=base_url)
        if isinstance(payload, str):
            payload = {"pickcode": payload}
        return self.request(url=api, params=payload, async_=async_, **request_kwargs)

    @overload
    def fs_document_app(
        self, 
        payload: str | dict, 
        /, 
        app: str = "android", 
        base_url: str | Callable[[], str] = "https://proapi.115.com", 
        *, 
        async_: Literal[False] = False, 
        **request_kwargs, 
    ) -> dict:
        ...
    @overload
    def fs_document_app(
        self, 
        payload: str | dict, 
        /, 
        app: str = "android", 
        base_url: str | Callable[[], str] = "https://proapi.115.com", 
        *, 
        async_: Literal[True], 
        **request_kwargs, 
    ) -> Coroutine[Any, Any, dict]:
        ...
    def fs_document_app(
        self, 
        payload: str | dict, 
        /, 
        app: str = "android", 
        base_url: str | Callable[[], str] = "https://proapi.115.com", 
        *, 
        async_: Literal[False, True] = False, 
        **request_kwargs, 
    ) -> dict | Coroutine[Any, Any, dict]:
        """获取图片的各种链接

        GET https://proapi.115.com/android/files/document

        .. note::
            即使文件格式不正确或者是一个目录，也可返回一些信息（包括 parent_id）

        :payload:
            - pickcode: str
        """
        api = complete_url("/files/document", base_url=base_url, app=app)
        if isinstance(payload, str):
            payload = {"pickcode": payload}
        return self.request(url=api, params=payload, async_=async_, **request_kwargs)

    @overload
    def fs_edit(
        self, 
        payload: list | dict, 
        /, 
        base_url: str | Callable[[], str] = "https://webapi.115.com", 
        *, 
        async_: Literal[False] = False, 
        **request_kwargs, 
    ) -> dict:
        ...
    @overload
    def fs_edit(
        self, 
        payload: list | dict, 
        /, 
        base_url: str | Callable[[], str] = "https://webapi.115.com", 
        *, 
        async_: Literal[True], 
        **request_kwargs, 
    ) -> Coroutine[Any, Any, dict]:
        ...
    def fs_edit(
        self, 
        payload: list | dict, 
        /, 
        base_url: str | Callable[[], str] = "https://webapi.115.com", 
        *, 
        async_: Literal[False, True] = False, 
        **request_kwargs, 
    ) -> dict | Coroutine[Any, Any, dict]:
        """设置文件或目录（备注、标签、封面等）

        POST https://webapi.115.com/files/edit

        :payload:
            - fid: int | str
            - fid[]: int | str
            - ...
            - file_desc: str = <default> 💡 可以用 html
            - file_label: int | str = <default> 💡 标签 id，多个用逗号 "," 隔开
            - fid_cover: int | str = <default>  💡 封面图片的文件 id，多个用逗号 "," 隔开，如果要删除，值设为 0 即可
            - show_play_long: 0 | 1 = <default> 💡 文件名称显示时长
            - ...
        """
        api = complete_url("/files/edit", base_url=base_url)
        return self.request(url=api, method="POST", data=payload, async_=async_, **request_kwargs)

    @overload
    def _fs_edit_set(
        self, 
        payload: int | str | Iterable[int | str] | list[tuple] | dict, 
        /, 
        attr: str, 
        default: Any = "", 
        base_url: str | Callable[[], str] = "https://webapi.115.com", 
        *, 
        async_: Literal[False] = False, 
        **request_kwargs, 
    ) -> dict:
        ...
    @overload
    def _fs_edit_set(
        self, 
        payload: int | str | Iterable[int | str] | list[tuple] | dict, 
        /, 
        attr: str, 
        default: Any = "", 
        base_url: str | Callable[[], str] = "https://webapi.115.com", 
        *, 
        async_: Literal[True], 
        **request_kwargs, 
    ) -> Coroutine[Any, Any, dict]:
        ...
    def _fs_edit_set(
        self, 
        payload: int | str | Iterable[int | str] | list[tuple] | dict, 
        /, 
        attr: str, 
        default: Any = "", 
        base_url: str | Callable[[], str] = "https://webapi.115.com", 
        *, 
        async_: Literal[False, True] = False, 
        **request_kwargs, 
    ) -> dict | Coroutine[Any, Any, dict]:
        """批量设置文件或目录（备注、标签、封面等），此接口是对 `fs_edit` 的封装
        """
        if isinstance(payload, (int, str)):
            payload = [("fid", payload), (attr, default)]
        elif isinstance(payload, list):
            if not any(a[0] == attr for a in payload):
                payload.append((attr, default))
        elif isinstance(payload, dict):
            payload.setdefault(attr, default)
        else:
            payload = [("fid[]", fid) for fid in payload]
            payload.append((attr, default))
        return self.fs_edit(payload, base_url=base_url, async_=async_, **request_kwargs)

    @overload
    def _fs_edit_set_app(
        self, 
        payload: int | str | Iterable[int | str] | list[tuple] | dict, 
        /, 
        attr: str, 
        default: Any = "", 
        app: str = "android", 
        base_url: str | Callable[[], str] = "https://proapi.115.com", 
        *, 
        async_: Literal[False] = False, 
        **request_kwargs, 
    ) -> dict:
        ...
    @overload
    def _fs_edit_set_app(
        self, 
        payload: int | str | Iterable[int | str] | list[tuple] | dict, 
        /, 
        attr: str, 
        default: Any = "", 
        app: str = "android", 
        base_url: str | Callable[[], str] = "https://proapi.115.com", 
        *, 
        async_: Literal[True], 
        **request_kwargs, 
    ) -> Coroutine[Any, Any, dict]:
        ...
    def _fs_edit_set_app(
        self, 
        payload: int | str | Iterable[int | str] | list[tuple] | dict, 
        /, 
        attr: str, 
        default: Any = "", 
        app: str = "android", 
        base_url: str | Callable[[], str] = "https://proapi.115.com", 
        *, 
        async_: Literal[False, True] = False, 
        **request_kwargs, 
    ) -> dict | Coroutine[Any, Any, dict]:
        """批量设置文件或目录（备注、标签、封面等），此接口是对 `fs_files_update_app` 的封装
        """
        if isinstance(payload, (int, str)):
            payload = [("file_id", payload), (attr, default)]
        elif isinstance(payload, list):
            if not any(a[0] == attr for a in payload):
                payload.append((attr, default))
        elif isinstance(payload, dict):
            payload.setdefault(attr, default)
        else:
            payload = [(f"file_id[{i}]", fid) for i, fid in enumerate(payload)]
            payload.append((attr, default))
        return self.fs_files_update_app(
            payload, 
            async_=async_, 
            app=app, 
            base_url=base_url, 
            **request_kwargs, 
        )

    @overload
    def fs_export_dir(
        self, 
        payload: int | str | dict, 
        /, 
        base_url: str | Callable[[], str] = "https://webapi.115.com", 
        *, 
        async_: Literal[False] = False, 
        **request_kwargs, 
    ) -> dict:
        ...
    @overload
    def fs_export_dir(
        self, 
        payload: int | str | dict, 
        /, 
        base_url: str | Callable[[], str] = "https://webapi.115.com", 
        *, 
        async_: Literal[True], 
        **request_kwargs, 
    ) -> Coroutine[Any, Any, dict]:
        ...
    def fs_export_dir(
        self, 
        payload: int | str | dict, 
        /, 
        base_url: str | Callable[[], str] = "https://webapi.115.com", 
        *, 
        async_: Literal[False, True] = False, 
        **request_kwargs, 
    ) -> dict | Coroutine[Any, Any, dict]:
        """导出目录树

        POST https://webapi.115.com/files/export_dir

        :payload:
            - file_ids: int | str   💡 多个用逗号 "," 隔开
            - target: str = "U_1_0" 💡 导出目录树到这个目录
            - layer_limit: int = <default> 💡 层级深度，自然数
        """
        api = complete_url("/files/export_dir", base_url=base_url)
        if isinstance(payload, (int, str)):
            payload = {"file_ids": payload}
        payload.setdefault("target", "U_1_0")
        return self.request(url=api, method="POST", data=payload, async_=async_, **request_kwargs)

    @overload
    def fs_export_dir_app(
        self, 
        payload: int | str | dict, 
        /, 
        app: str = "android", 
        base_url: str | Callable[[], str] = "https://proapi.115.com", 
        *, 
        async_: Literal[False] = False, 
        **request_kwargs, 
    ) -> dict:
        ...
    @overload
    def fs_export_dir_app(
        self, 
        payload: int | str | dict, 
        /, 
        app: str = "android", 
        base_url: str | Callable[[], str] = "https://proapi.115.com", 
        *, 
        async_: Literal[True], 
        **request_kwargs, 
    ) -> Coroutine[Any, Any, dict]:
        ...
    def fs_export_dir_app(
        self, 
        payload: int | str | dict, 
        /, 
        app: str = "android", 
        base_url: str | Callable[[], str] = "https://proapi.115.com", 
        *, 
        async_: Literal[False, True] = False, 
        **request_kwargs, 
    ) -> dict | Coroutine[Any, Any, dict]:
        """导出目录树

        POST https://proapi.115.com/android/2.0/ufile/export_dir

        :payload:
            - file_ids: int | str   💡 多个用逗号 "," 隔开
            - target: str = "U_1_0" 💡 导出目录树到这个目录
            - layer_limit: int = <default> 💡 层级深度，自然数
        """
        api = complete_url("/2.0/ufile/export_dir", base_url=base_url, app=app)
        if isinstance(payload, (int, str)):
            payload = {"file_ids": payload}
        payload.setdefault("target", "U_1_0")
        return self.request(url=api, method="POST", data=payload, async_=async_, **request_kwargs)

    @overload
    def fs_export_dir_status(
        self, 
        payload: int | str | dict = 0, 
        /, 
        base_url: str | Callable[[], str] = "https://webapi.115.com", 
        *, 
        async_: Literal[False] = False, 
        **request_kwargs, 
    ) -> dict:
        ...
    @overload
    def fs_export_dir_status(
        self, 
        payload: int | str | dict = 0, 
        /, 
        base_url: str | Callable[[], str] = "https://webapi.115.com", 
        *, 
        async_: Literal[True], 
        **request_kwargs, 
    ) -> Coroutine[Any, Any, dict]:
        ...
    def fs_export_dir_status(
        self, 
        payload: int | str | dict = 0, 
        /, 
        base_url: str | Callable[[], str] = "https://webapi.115.com", 
        *, 
        async_: Literal[False, True] = False, 
        **request_kwargs, 
    ) -> dict | Coroutine[Any, Any, dict]:
        """获取导出目录树的完成情况

        GET https://webapi.115.com/files/export_dir

        :payload:
            - export_id: int | str = 0 💡 任务 id
        """
        api = complete_url("/files/export_dir", base_url=base_url)
        if isinstance(payload, (int, str)):
            payload = {"export_id": payload}
        return self.request(url=api, params=payload, async_=async_, **request_kwargs)

    @overload
    def fs_export_dir_status_app(
        self, 
        payload: int | str | dict = 0, 
        /, 
        app: str = "android", 
        base_url: str | Callable[[], str] = "https://proapi.115.com", 
        *, 
        async_: Literal[False] = False, 
        **request_kwargs, 
    ) -> dict:
        ...
    @overload
    def fs_export_dir_status_app(
        self, 
        payload: int | str | dict = 0, 
        /, 
        app: str = "android", 
        base_url: str | Callable[[], str] = "https://proapi.115.com", 
        *, 
        async_: Literal[True], 
        **request_kwargs, 
    ) -> Coroutine[Any, Any, dict]:
        ...
    def fs_export_dir_status_app(
        self, 
        payload: int | str | dict = 0, 
        /, 
        app: str = "android", 
        base_url: str | Callable[[], str] = "https://proapi.115.com", 
        *, 
        async_: Literal[False, True] = False, 
        **request_kwargs, 
    ) -> dict | Coroutine[Any, Any, dict]:
        """获取导出目录树的完成情况

        GET https://proapi.115.com/android/2.0/ufile/export_dir

        :payload:
            - export_id: int | str = 0 💡 任务 id
        """
        api = complete_url("/2.0/ufile/export_dir", base_url=base_url, app=app)
        if isinstance(payload, (int, str)):
            payload = {"export_id": payload}
        return self.request(url=api, params=payload, async_=async_, **request_kwargs)

    @overload
    def fs_file(
        self, 
        payload: int | str | dict, 
        /, 
        base_url: str | Callable[[], str] = "https://webapi.115.com", 
        *, 
        async_: Literal[False] = False, 
        **request_kwargs, 
    ) -> dict:
        ...
    @overload
    def fs_file(
        self, 
        payload: int | str | dict, 
        /, 
        base_url: str | Callable[[], str] = "https://webapi.115.com", 
        *, 
        async_: Literal[True], 
        **request_kwargs, 
    ) -> Coroutine[Any, Any, dict]:
        ...
    def fs_file(
        self, 
        payload: int | str | dict, 
        /, 
        base_url: str | Callable[[], str] = "https://webapi.115.com", 
        *, 
        async_: Literal[False, True] = False, 
        **request_kwargs, 
    ) -> dict | Coroutine[Any, Any, dict]:
        """获取文件或目录的基本信息

        GET https://webapi.115.com/files/get_info

        .. caution::
            仅当文件的 aid 是 1（网盘文件）、12（瞬间文件） 或 120（永久删除文件） 时，才能用此接口获取信息，否则请用 `client.fs_file_skim` 或 `client.fs_supervision` 获取信息（只能获取比较简略的版本）。

            特别的，文件被移入回收站后，就不能用此接口获取信息了，除非将其还原或永久删除。

        :payload:
            - file_id: int | str 💡 文件或目录的 id，不能为 0，只能传 1 个 id，如果有多个只采用第一个
        """
        api = complete_url("/files/get_info", base_url=base_url)
        if isinstance(payload, (int, str)):
            payload = {"file_id": payload}
        return self.request(url=api, params=payload, async_=async_, **request_kwargs)

    @overload
    def fs_file_skim(
        self, 
        payload: int | str | Iterable[int | str] | dict, 
        /, 
        base_url: str | Callable[[], str] = "https://webapi.115.com", 
        method: str = "GET", 
        *, 
        async_: Literal[False] = False, 
        **request_kwargs, 
    ) -> dict:
        ...
    @overload
    def fs_file_skim(
        self, 
        payload: int | str | Iterable[int | str] | dict, 
        /, 
        base_url: str | Callable[[], str] = "https://webapi.115.com", 
        method: str = "GET", 
        *, 
        async_: Literal[True], 
        **request_kwargs, 
    ) -> Coroutine[Any, Any, dict]:
        ...
    def fs_file_skim(
        self, 
        payload: int | str | Iterable[int | str] | dict, 
        /, 
        base_url: str | Callable[[], str] = "https://webapi.115.com", 
        method: str = "GET", 
        *, 
        async_: Literal[False, True] = False, 
        **request_kwargs, 
    ) -> dict | Coroutine[Any, Any, dict]:
        """获取文件或目录的简略信息

        GET https://webapi.115.com/files/file

        .. note::
            如果需要查询到 id 特别多，请指定 `method="POST"`

        :payload:
            - file_id: int | str 💡 文件或目录的 id，不能为 0，多个用逗号 "," 隔开
        """
        api = complete_url("/files/file", base_url=base_url)
        if isinstance(payload, (int, str)):
            payload = {"file_id": payload}
        elif not isinstance(payload, dict):
            payload = {"file_id": ",".join(map(str, payload))}
        if method.upper() == "POST":
            request_kwargs["data"] = payload
        else:
            request_kwargs["params"] = payload
        return self.request(url=api, method=method, async_=async_, **request_kwargs)

    @overload
    def fs_files(
        self, 
        payload: int | str | dict = 0, 
        /, 
        base_url: str | Callable[[], str] = "https://webapi.115.com", 
        *, 
        async_: Literal[False] = False, 
        **request_kwargs, 
    ) -> dict:
        ...
    @overload
    def fs_files(
        self, 
        payload: int | str | dict = 0, 
        /, 
        base_url: str | Callable[[], str] = "https://webapi.115.com", 
        *, 
        async_: Literal[True], 
        **request_kwargs, 
    ) -> Coroutine[Any, Any, dict]:
        ...
    def fs_files(
        self, 
        payload: int | str | dict = 0, 
        /, 
        base_url: str | Callable[[], str] = "https://webapi.115.com", 
        *, 
        async_: Literal[False, True] = False, 
        **request_kwargs, 
    ) -> dict | Coroutine[Any, Any, dict]:
        """获取目录中的文件列表和基本信息

        GET https://webapi.115.com/files

        .. hint::
            指定如下条件中任一，且 cur = 0 （默认），即可遍历搜索所在目录树

            1. cid=0 且 star=1
            2. suffix 为非空的字符串
            3. type 为正整数
            4. show_dir=0 且 cur=0（或不指定 cur）

        .. hint::
            如果不指定或者指定的 cid 不存在，则会视为 cid=0 进行处理

            当指定 ``natsort=1`` 时，如果里面的数量较少时，可仅统计某个目录内的文件或目录总数，而不返回具体的文件信息

        .. hint::
            当一个 cookies 被另一个更新的登录所失效，并不意味着这个 cookies 就直接不可用了。

            如果你使用的是 `proapi` 下的接口，则会让你重新登录。但是 `webapi`、`aps` 等之下的接口，却依然可以正常使用。具体哪些失效，哪些还正常，请自行试验总结。这就意味着可以设计一种同一设备多 cookies 做池的分流策略。

        .. hint::
            对于普通的文件系统，我们只允许任何一个目录中不可有相同的名字，但是 115 网盘中却可能有重复：

            - 目录和文件同名：文件和目录同名在 115 中不算是一个冲突
            - 相同的目录名：转存可以导致同一目录下有多个相同名字的目录
            - 相同的文件名：转存、离线和上传等，可以导致同一目录下有多个相同名字的文件

        .. hint::
            如果文件或目录被置顶，会在整个文件列表的最前面

            在根目录下且 ``fc_mix=0`` 且是特殊名字 ("最近接收", "手机相册", "云下载", "我的时光记录")（即 ``sys_dir``），会在整个文件列表的最前面但在置顶之后，这时可从返回信息的 "sys_count" 字段知道数目

        .. note::
            当 ``type=1`` 时，``suffix_type`` 的取值的含义：

                - (不填): 全部
                - 1: 文字（word，即 doc 和 docx 等）
                - 2: 表格（excel，即 xls 和 xlsx 等）
                - 3: 演示（ppt，即 ppt 和 pptx 等）
                - 4: pdf
                - 5: txt
                - 6: xmind
                - 7: 其它

        :payload:
            - cid: int | str = 0 💡 目录 id，对应 parent_id
            - limit: int = 32 💡 分页大小，目前最大值是 1,150，以前是没限制的
            - offset: int = 0 💡 分页开始的索引，索引从 0 开始计算

            - aid: int = 1 💡 area_id

                - 0: 会被视为 1
                - 1: 正常文件
                - 2: <unknown>
                - 3: <unknown>
                - 4: <unknown>
                - 5: <unknown>
                - 7: 回收站文件
                - 9: <unknown>
                - 12:瞬间文件
                - 15: <unknown>
                - 120: 彻底删除文件、简历附件
                - <其它>: 会被视为 0

            - asc: 0 | 1 = <default> 💡 是否升序排列。0:降序 1:升序
            - code: int | str = <default>
            - count_folders: 0 | 1 = 1 💡 统计文件数和目录数，好像也可以写成 ``countfolders``
            - cur: 0 | 1 = <default> 💡 是否只搜索当前目录
            - custom_order: 0 | 1 = <default> 💡 启用自定义排序，如果指定了 "asc"、"fc_mix"、"o" 中其一，则此参数会被自动设置为 1

                - 0: 使用记忆排序（自定义排序失效） 
                - 1: 使用自定义排序（不使用记忆排序） 
                - 2: 自定义排序（非目录置顶）

            - date: str = <default> 💡 筛选日期
            - fc_mix: 0 | 1 = <default> 💡 是否目录和文件混合，如果为 0 则目录在前（目录置顶）
            - fields: str = <default>
            - hidden: 0 | 1 = <default>
            - is_q: 0 | 1 = <default>
            - is_share: 0 | 1 = <default>
            - last_utime: int = <default> 💡 需传入一个时间戳
            - min_size: int = 0 💡 最小的文件大小
            - max_size: int = 0 💡 最大的文件大小
            - natsort: 0 | 1 = <default> 💡 是否执行自然排序(natural sorting) 💡 natural sorting
            - nf: str = <default> 💡 不要显示文件（即仅显示目录），但如果 show_dir=0，则此参数无效
            - o: str = <default> 💡 用某字段排序

                - "file_name": 文件名
                - "file_size": 文件大小
                - "file_type": 文件种类
                - "user_utime": 修改时间
                - "user_ptime": 创建时间
                - "user_otime": 上一次打开时间

            - oof_token: str = <default>
            - qid: int | str = <default>
            - r_all: 0 | 1 = <default>
            - record_open_time: 0 | 1 = 1 💡 是否要记录目录的打开时间
            - scid: int | str = <default>
            - show_dir: 0 | 1 = 1 💡 是否显示目录，好像也可以写成 showdir
            - snap: 0 | 1 = <default>
            - source: str = <default>
            - sys_dir: int | str = <default>
            - star: 0 | 1 = <default> 💡 是否星标文件
            - stdir: 0 | 1 = <default> 💡 筛选文件时，是否显示目录：1:展示 0:不展示
            - suffix: str = <default> 💡 后缀名（优先级高于 `type`）
            - suffix_type: int = <default>
            - type: int = <default> 💡 文件类型

                - 0: 全部（仅当前目录）
                - 1: 文档
                - 2: 图片
                - 3: 音频
                - 4: 视频
                - 5: 压缩包
                - 6: 软件/应用
                - 7: 书籍
                - 8: 其它
                - 9: 相当于 8
                - 10: 相当于 8
                - 11: 相当于 8
                - 12: ？？？
                - 13: 相当于 3
                - 14: ？？？
                - 15: 图片和视频，相当于 2 和 4
                - 16: ？？？
                - 17~98: 相当于 8
                - 99: 所有文件
                - >=100: 相当于 8
        """
        api = complete_url("/files", base_url=base_url)
        if isinstance(payload, (int, str)):
            payload = {"cid": payload}
        payload = {
            "aid": 1, "count_folders": 1, "limit": 32, "offset": 0, 
            "record_open_time": 1, "show_dir": 1, "cid": 0, **payload, 
        }
        if payload.keys() & frozenset(("asc", "fc_mix", "o")):
            payload["custom_order"] = 1
        return self.request(url=api, params=payload, async_=async_, **request_kwargs)

    @overload
    def fs_files_app(
        self, 
        payload: int | str | dict = 0, 
        /, 
        app: str = "android", 
        base_url: str | Callable[[], str] = "https://proapi.115.com", 
        *, 
        async_: Literal[False] = False, 
        **request_kwargs, 
    ) -> dict:
        ...
    @overload
    def fs_files_app(
        self, 
        payload: int | str | dict = 0, 
        /, 
        app: str = "android", 
        base_url: str | Callable[[], str] = "https://proapi.115.com", 
        *, 
        async_: Literal[True], 
        **request_kwargs, 
    ) -> Coroutine[Any, Any, dict]:
        ...
    def fs_files_app(
        self, 
        payload: int | str | dict = 0, 
        /, 
        app: str = "android", 
        base_url: str | Callable[[], str] = "https://proapi.115.com", 
        *, 
        async_: Literal[False, True] = False, 
        **request_kwargs, 
    ) -> dict | Coroutine[Any, Any, dict]:
        """获取目录中的文件列表和基本信息

        GET https://proapi.115.com/android/2.0/ufile/files

        .. hint::
            如果要遍历获取所有文件，需要指定 show_dir=0 且 cur=0（或不指定 cur），这个接口并没有 type=99 时获取所有文件的意义

        .. note::
            如果 `app` 为 "wechatmini" 或 "alipaymini"，则相当于 ``P115Client.fs_files_app2()``

        .. caution::
            这个接口有些问题，当 custom_order=1 时：

                1. 如果设定 limit=1 可能会报错
                2. fc_mix 无论怎么设置，都和 fc_mix=0 的效果相同（即目录总是置顶），但设置为 custom_order=2 就好了

        .. hint::
            置顶无效，但可以知道是否置顶了。

            在根目录下且 fc_mix=0 且是特殊名字 ("最近接收", "手机相册", "云下载", "我的时光记录")，会在整个文件列表的最前面，这时可从返回信息的 "sys_count" 字段知道数目

        :payload:
            - cid: int | str = 0 💡 目录 id，对应 parent_id
            - limit: int = 32 💡 分页大小，最大值不一定，看数据量，7,000 应该总是安全的，10,000 有可能报错，但有时也可以 20,000 而成功
            - offset: int = 0 💡 分页开始的索引，索引从 0 开始计算

            - aid: int = 1 💡 area_id

                - 0: 会被视为 1
                - 1: 正常文件
                - 2: <unknown>
                - 3: <unknown>
                - 4: <unknown>
                - 5: <unknown>
                - 7: 回收站文件
                - 9: <unknown>
                - 12:瞬间文件
                - 15: <unknown>
                - 120: 彻底删除文件、简历附件
                - <其它>: 会被视为 0

            - asc: 0 | 1 = <default> 💡 是否升序排列。0:降序 1:升序
            - code: int | str = <default>
            - count_folders: 0 | 1 = 1 💡 统计文件数和目录数
            - cur: 0 | 1 = <default>   💡 是否只显示当前目录
            - custom_order: 0 | 1 | 2 = <default> 💡 是否使用记忆排序。如果指定了 "asc"、"fc_mix"、"o" 中其一，则此参数会被自动设置为 2

                - 0: 使用记忆排序（自定义排序失效） 
                - 1: 使用自定义排序（不使用记忆排序） 
                - 2: 自定义排序（非目录置顶）

            - date: str = <default> 💡 筛选日期
            - fc_mix: 0 | 1 = <default> 💡 是否目录和文件混合，如果为 0 则目录在前（目录置顶）
            - fields: str = <default>
            - for: str = <default> 💡 文件格式，例如 "doc"
            - hide_data: str = <default> 💡 是否返回文件数据
            - is_q: 0 | 1 = <default>
            - is_share: 0 | 1 = <default>
            - min_size: int = 0 💡 最小的文件大小
            - max_size: int = 0 💡 最大的文件大小
            - natsort: 0 | 1 = <default> 💡 是否执行自然排序(natural sorting)
            - nf: str = <default> 💡 不要显示文件（即仅显示目录），但如果 show_dir=0，则此参数无效
            - o: str = <default> 💡 用某字段排序（未定义的值会被视为 "user_utime"）

                - "file_name": 文件名
                - "file_size": 文件大小
                - "file_type": 文件种类
                - "user_etime": 事件时间（无效，效果相当于 "user_utime"）
                - "user_utime": 修改时间
                - "user_ptime": 创建时间（无效，效果相当于 "user_utime"）
                - "user_otime": 上一次打开时间（无效，效果相当于 "user_utime"）

            - r_all: 0 | 1 = <default>
            - record_open_time: 0 | 1 = 1 💡 是否要记录目录的打开时间
            - scid: int | str = <default>
            - show_dir: 0 | 1 = 1 💡 是否显示目录
            - snap: 0 | 1 = <default>
            - source: str = <default>
            - sys_dir: int | str = <default> 💡 系统通用目录
            - star: 0 | 1 = <default> 💡 是否星标文件
            - stdir: 0 | 1 = <default> 💡 筛选文件时，是否显示目录：1:展示 0:不展示
            - suffix: str = <default> 💡 后缀名（优先级高于 `type`）
            - type: int = <default> 💡 文件类型

                - 0: 全部（仅当前目录）
                - 1: 文档
                - 2: 图片
                - 3: 音频
                - 4: 视频
                - 5: 压缩包
                - 6: 软件/应用
                - 7: 书籍
                - 8: 其它
                - 9: 相当于 8
                - 10: 相当于 8
                - 11: 相当于 8
                - 12: ？？？
                - 13: ？？？
                - 14: ？？？
                - 15: 图片和视频，相当于 2 和 4
                - >= 16: 相当于 8
        """
        api = complete_url("/2.0/ufile/files", base_url=base_url, app=app)
        if isinstance(payload, (int, str)):
            payload = {"cid": payload}
        payload = {
            "aid": 1, "count_folders": 1, "limit": 32, "offset": 0, 
            "record_open_time": 1, "show_dir": 1, "cid": 0, **payload, 
        }
        if payload.keys() & frozenset(("asc", "fc_mix", "o")):
            payload["custom_order"] = 2
        return self.request(url=api, params=payload, async_=async_, **request_kwargs)

    @overload
    def fs_files_app2(
        self, 
        payload: int | str | dict = 0, 
        /, 
        app: str = "android", 
        base_url: str | Callable[[], str] = "https://proapi.115.com", 
        *, 
        async_: Literal[False] = False, 
        **request_kwargs, 
    ) -> dict:
        ...
    @overload
    def fs_files_app2(
        self, 
        payload: int | str | dict = 0, 
        /, 
        app: str = "android", 
        base_url: str | Callable[[], str] = "https://proapi.115.com", 
        *, 
        async_: Literal[True], 
        **request_kwargs, 
    ) -> Coroutine[Any, Any, dict]:
        ...
    def fs_files_app2(
        self, 
        payload: int | str | dict = 0, 
        /, 
        app: str = "android", 
        base_url: str | Callable[[], str] = "https://proapi.115.com", 
        *, 
        async_: Literal[False, True] = False, 
        **request_kwargs, 
    ) -> dict | Coroutine[Any, Any, dict]:
        """获取目录中的文件列表和基本信息

        GET https://proapi.115.com/android/files

        .. hint::
            如果要遍历获取所有文件，需要指定 show_dir=0 且 cur=0（或不指定 cur），这个接口并没有 type=99 时获取所有文件的意义

        .. caution::
            这个接口有些问题，当 custom_order=1 时：

                1. 如果设定 limit=1 可能会报错
                2. fc_mix 无论怎么设置，都和 fc_mix=0 的效果相同（即目录总是置顶），设置为 custom_order=2 也没用

        :payload:
            - cid: int | str = 0 💡 目录 id，对应 parent_id
            - limit: int = 32 💡 分页大小，最大值不一定，看数据量，7,000 应该总是安全的，10,000 有可能报错，但有时也可以 20,000 而成功
            - offset: int = 0 💡 分页开始的索引，索引从 0 开始计算

            - aid: int = 1 💡 area_id

                - 0: 会被视为 1
                - 1: 正常文件
                - 2: <unknown>
                - 3: <unknown>
                - 4: <unknown>
                - 5: <unknown>
                - 7: 回收站文件
                - 9: <unknown>
                - 12:瞬间文件
                - 15: <unknown>
                - 120: 彻底删除文件、简历附件
                - <其它>: 会被视为 0

            - asc: 0 | 1 = <default> 💡 是否升序排列。0:降序 1:升序
            - code: int | str = <default>
            - count_folders: 0 | 1 = 1 💡 统计文件数和目录数
            - cur: 0 | 1 = <default> 💡 是否只搜索当前目录
            - custom_order: 0 | 1 | 2 = <default> 💡 启用自定义排序，如果指定了 "asc"、"fc_mix"、"o" 中其一，则此参数会被自动设置为 2

                - 0: 使用记忆排序（自定义排序失效） 
                - 1: 使用自定义排序（不使用记忆排序） 
                - 2: 自定义排序（非目录置顶）
 
            - date: str = <default> 💡 筛选日期
            - fc_mix: 0 | 1 = <default> 💡 是否目录和文件混合，如果为 0 则目录在前（目录置顶）
            - fields: str = <default>
            - for: str = <default> 💡 文件格式，例如 "doc"
            - hide_data: str = <default> 💡 是否返回文件数据
            - is_q: 0 | 1 = <default>
            - is_share: 0 | 1 = <default>
            - min_size: int = 0 💡 最小的文件大小
            - max_size: int = 0 💡 最大的文件大小
            - natsort: 0 | 1 = <default> 💡 是否执行自然排序(natural sorting)
            - nf: str = <default> 💡 不要显示文件（即仅显示目录），但如果 show_dir=0，则此参数无效
            - o: str = <default> 💡 用某字段排序（未定义的值会被视为 "user_utime"）

                - "file_name": 文件名
                - "file_size": 文件大小
                - "file_type": 文件种类
                - "user_etime": 事件时间（无效，效果相当于 "user_utime"）
                - "user_utime": 修改时间
                - "user_ptime": 创建时间（无效，效果相当于 "user_utime"）
                - "user_otime": 上一次打开时间（无效，效果相当于 "user_utime"）

            - r_all: 0 | 1 = <default>
            - record_open_time: 0 | 1 = 1 💡 是否要记录目录的打开时间
            - scid: int | str = <default>
            - show_dir: 0 | 1 = 1 💡 是否显示目录
            - snap: 0 | 1 = <default>
            - source: str = <default>
            - sys_dir: int | str = <default>
            - star: 0 | 1 = <default> 💡 是否星标文件
            - stdir: 0 | 1 = <default> 💡 筛选文件时，是否显示目录：1:展示 0:不展示
            - suffix: str = <default> 💡 后缀名（优先级高于 `type`）
            - type: int = <default> 💡 文件类型

                - 0: 全部（仅当前目录）
                - 1: 文档
                - 2: 图片
                - 3: 音频
                - 4: 视频
                - 5: 压缩包
                - 6: 软件/应用
                - 7: 书籍
                - 8: 其它
                - 9: 相当于 8
                - 10: 相当于 8
                - 11: 相当于 8
                - 12: ？？？
                - 13: ？？？
                - 14: ？？？
                - 15: 图片和视频，相当于 2 和 4
                - >= 16: 相当于 8
        """
        api = complete_url("/files", base_url=base_url, app=app)
        if isinstance(payload, (int, str)):
            payload = {"cid": payload}
        payload = {
            "aid": 1, "count_folders": 1, "limit": 32, "offset": 0, 
            "record_open_time": 1, "show_dir": 1, "cid": 0, **payload, 
        }
        if payload.keys() & frozenset(("asc", "fc_mix", "o")):
            payload["custom_order"] = 2
        return self.request(url=api, params=payload, async_=async_, **request_kwargs)

    @overload
    def fs_files_aps(
        self, 
        payload: int | str | dict = 0, 
        /, 
        base_url: str | Callable[[], str] = "https://aps.115.com", 
        *, 
        async_: Literal[False] = False, 
        **request_kwargs, 
    ) -> dict:
        ...
    @overload
    def fs_files_aps(
        self, 
        payload: int | str | dict = 0, 
        /, 
        base_url: str | Callable[[], str] = "https://aps.115.com", 
        *, 
        async_: Literal[True], 
        **request_kwargs, 
    ) -> Coroutine[Any, Any, dict]:
        ...
    def fs_files_aps(
        self, 
        payload: int | str | dict = 0, 
        /, 
        base_url: str | Callable[[], str] = "https://aps.115.com", 
        *, 
        async_: Literal[False, True] = False, 
        **request_kwargs, 
    ) -> dict | Coroutine[Any, Any, dict]:
        """获取目录中的文件列表和基本信息

        GET https://aps.115.com/natsort/files.php

        .. caution::
            这个函数最多获取任何一种排序条件下的前 1201 条数据，当你的 `offset < 1201` 时，最多获取 `min(1201 - offset, limit)` 条数据

            `o` 参数无效，效果只等于 "file_name"，而 `fc_mix` 和 `asc` 可用。从技术上来讲最多获取 2402 个文件和 2402 个目录，即你可以通过 asc 取 0 或者 1，来最多获取两倍于数量上限的不同条目，然后通过指定 `show_dir=0&cur=1` 和 `show_dir=1&nf=1` 来分别只获取文件或目录。但如果有置顶的条目，置顶条目总是出现，因此会使能获取到的不同条目总数变少

            当 `offset` >= 1201 或 >= 当前条件下的条目总数时，则相当于 `offset=0&fc_mix=1`，且置顶项不会置顶，且最多获取 1200 条数据

        .. hint::
            文件或目录最多分别获取 max(1201, 2402 - 此类型被置顶的个数) 个，但对于文件，如果利用 type 或 suffix 进行筛选，则可以获得更多

            不过在我看来，只要一个目录内的节点数超过 2,400 个，则大概就没必要使用此接口

        :payload:
            - cid: int | str = 0 💡 目录 id，对应 parent_id
            - limit: int = 32 💡 分页大小，最大值是 1,200
            - offset: int = 0 💡 分页开始的索引，索引从 0 开始计算

            - aid: int = 1 💡 area_id

                - 0: 会被视为 1
                - 1: 正常文件
                - 2: <unknown>
                - 3: <unknown>
                - 4: <unknown>
                - 5: <unknown>
                - 7: 回收站文件
                - 9: <unknown>
                - 12:瞬间文件
                - 15: <unknown>
                - 120: 彻底删除文件、简历附件
                - <其它>: 会被视为 0

            - asc: 0 | 1 = <default> 💡 是否升序排列。0:降序 1:升序
            - code: int | str = <default>
            - count_folders: 0 | 1 = 1 💡 统计文件数和目录数
            - cur: 0 | 1 = <default> 💡 是否只搜索当前目录
            - custom_order: 0 | 1 = <default> 💡 启用自定义排序，如果指定了 "asc"、"fc_mix" 中其一，则此参数会被自动设置为 1

                - 0: 使用记忆排序（自定义排序失效） 
                - 1: 使用自定义排序（不使用记忆排序） 
                - 2: 自定义排序（非目录置顶）

            - date: str = <default> 💡 筛选日期
            - fc_mix: 0 | 1 = <default> 💡 是否目录和文件混合，如果为 0 则目录在前（目录置顶）
            - fields: str = <default>
            - hide_data: str = <default> 💡 是否返回文件数据
            - is_asc: 0 | 1 = <default>
            - is_q: 0 | 1 = <default>
            - is_share: 0 | 1 = <default>
            - min_size: int = 0 💡 最小的文件大小
            - max_size: int = 0 💡 最大的文件大小
            - natsort: 0 | 1 = <default>
            - order: str = <default>
            - r_all: 0 | 1 = <default>
            - record_open_time: 0 | 1 = 1 💡 是否要记录目录的打开时间
            - scid: int | str = <default>
            - show_dir: 0 | 1 = 1 💡 是否显示目录
            - snap: 0 | 1 = <default>
            - source: str = <default>
            - sys_dir: int | str = <default>
            - star: 0 | 1 = <default> 💡 是否星标文件
            - stdir: 0 | 1 = <default> 💡 筛选文件时，是否显示目录：1:展示 0:不展示
            - suffix: str = <default> 💡 后缀名（优先级高于 `type`）
            - type: int = <default> 💡 文件类型

                - 0: 全部（仅当前目录）
                - 1: 文档
                - 2: 图片
                - 3: 音频
                - 4: 视频
                - 5: 压缩包
                - 6: 软件/应用
                - 7: 书籍
                - 8: 其它
                - 9: 相当于 8
                - 10: 相当于 8
                - 11: 相当于 8
                - 12: ？？？
                - 13: 相当于 3
                - 14: ？？？
                - 15: 图片和视频，相当于 2 和 4
                - 16: ？？？
                - 17~98: 相当于 8
                - 99: 所有文件
                - >=100: 相当于 8
        """
        api = complete_url("/natsort/files.php", base_url=base_url)
        if isinstance(payload, (int, str)):
            payload = {"cid": payload}
        payload = {
            "aid": 1, "count_folders": 1, "limit": 32, "offset": 0, 
            "record_open_time": 1, "show_dir": 1, "cid": 0, **payload, 
        }
        if payload.keys() & frozenset(("asc", "fc_mix")):
            payload["custom_order"] = 1
        return self.request(url=api, params=payload, async_=async_, **request_kwargs)

    @overload
    def fs_files_blank_document(
        self, 
        payload: str | dict, 
        /, 
        base_url: str | Callable[[], str] = "https://webapi.115.com", 
        *, 
        async_: Literal[False] = False, 
        **request_kwargs, 
    ) -> dict:
        ...
    @overload
    def fs_files_blank_document(
        self, 
        payload: str | dict, 
        /, 
        base_url: str | Callable[[], str] = "https://webapi.115.com", 
        *, 
        async_: Literal[True], 
        **request_kwargs, 
    ) -> Coroutine[Any, Any, dict]:
        ...
    def fs_files_blank_document(
        self, 
        payload: str | dict, 
        /, 
        base_url: str | Callable[[], str] = "https://webapi.115.com", 
        *, 
        async_: Literal[False, True] = False, 
        **request_kwargs, 
    ) -> dict | Coroutine[Any, Any, dict]:
        """新建空白 office 文件

        POST https://webapi.115.com/files/blank_document

        :payload:
            - file_name: str      💡 文件名，不含后缀
            - pid: int | str = 0  💡 目录 id，对应 parent_id
            - type: 1 | 2 | 3 = 1 💡 1:Word文档(.docx) 2:Excel表格(.xlsx) 3:PPT文稿(.pptx)
        """
        api = complete_url("/files/blank_document", base_url=base_url)
        if isinstance(payload, str):
            payload = {"file_name": payload}
        payload = {"pid": 0, "type": 1, **payload}
        return self.request(url=api, method="POST", data=payload, async_=async_, **request_kwargs)

    @overload
    def fs_files_cover(
        self, 
        payload: int | str | dict, 
        /, 
        base_url: str | Callable[[], str] = "https://webapi.115.com", 
        *, 
        async_: Literal[False] = False, 
        **request_kwargs, 
    ) -> dict:
        ...
    @overload
    def fs_files_cover(
        self, 
        payload: int | str | dict, 
        /, 
        base_url: str | Callable[[], str] = "https://webapi.115.com", 
        *, 
        async_: Literal[True], 
        **request_kwargs, 
    ) -> Coroutine[Any, Any, dict]:
        ...
    def fs_files_cover(
        self, 
        payload: int | str | dict, 
        /, 
        base_url: str | Callable[[], str] = "https://webapi.115.com", 
        *, 
        async_: Literal[False, True] = False, 
        **request_kwargs, 
    ) -> dict | Coroutine[Any, Any, dict]:
        """查看是否有封面

        GET https://webapi.115.com/files/cover

        :payload:
            - file_id: int | str 💡 文件或目录 id
            - folder_as_file: 0 | 1 = <default>
        """
        api = complete_url("/files/cover", base_url=base_url)
        if isinstance(payload, (int, str)):
            payload = {"file_id": payload}
        return self.request(url=api, params=payload, async_=async_, **request_kwargs)

    @overload
    def fs_files_cover_set(
        self, 
        payload: int | str | dict, 
        /, 
        base_url: str | Callable[[], str] = "https://webapi.115.com", 
        *, 
        async_: Literal[False] = False, 
        **request_kwargs, 
    ) -> dict:
        ...
    @overload
    def fs_files_cover_set(
        self, 
        payload: int | str | dict, 
        /, 
        base_url: str | Callable[[], str] = "https://webapi.115.com", 
        *, 
        async_: Literal[True], 
        **request_kwargs, 
    ) -> Coroutine[Any, Any, dict]:
        ...
    def fs_files_cover_set(
        self, 
        payload: int | str | dict, 
        /, 
        base_url: str | Callable[[], str] = "https://webapi.115.com", 
        *, 
        async_: Literal[False, True] = False, 
        **request_kwargs, 
    ) -> dict | Coroutine[Any, Any, dict]:
        """是否生成封面

        POST https://webapi.115.com/files/cover

        :payload:
            - file_id: int | str 💡 文件或目录 id
            - show: 0 | 1 = 1
        """
        api = complete_url("/files/cover", base_url=base_url)
        if isinstance(payload, (int, str)):
            payload = {"file_id": payload}
        payload.setdefault("show", 1)
        return self.request(url=api, method="POST", data=payload, async_=async_, **request_kwargs)

    @overload
    def fs_files_image(
        self, 
        payload: int | str | dict, 
        /, 
        base_url: str | Callable[[], str] = "https://webapi.115.com", 
        *, 
        async_: Literal[False] = False, 
        **request_kwargs, 
    ) -> dict:
        ...
    @overload
    def fs_files_image(
        self, 
        payload: int | str | dict, 
        /, 
        base_url: str | Callable[[], str] = "https://webapi.115.com", 
        *, 
        async_: Literal[True], 
        **request_kwargs, 
    ) -> Coroutine[Any, Any, dict]:
        ...
    def fs_files_image(
        self, 
        payload: int | str | dict, 
        /, 
        base_url: str | Callable[[], str] = "https://webapi.115.com", 
        *, 
        async_: Literal[False, True] = False, 
        **request_kwargs, 
    ) -> dict | Coroutine[Any, Any, dict]:
        """获取目录中的图片列表和基本信息

        GET https://webapi.115.com/files/imglist

        .. danger::
            这个函数大概是有 bug 的，不推荐使用

        .. attention::
            只能获取直属于 `cid` 所在目录的图片，不会遍历整个目录树

        :payload:
            - cid: int | str     💡 目录 id，对应 parent_id
            - file_id: int | str 💡 不能是 0，可以不同于 `cid`，必须是任何一个有效的 id（单纯是被检查一下）
            - limit: int = <default> 💡 最多返回数量
            - offset: int = 0 💡 索引偏移，索引从 0 开始计算
            - is_asc: 0 | 1 = <default> 💡 是否升序排列
            - next: 0 | 1 = <default>
            - order: str = <default> 💡 用某字段排序

                - 文件名："file_name"
                - 文件大小："file_size"
                - 文件种类："file_type"
                - 修改时间："user_utime"
                - 创建时间："user_ptime"
                - 上一次打开时间："user_otime"
        """
        api = complete_url("/files/imglist", base_url=base_url)
        if isinstance(payload, (int, str)):
            payload = {"cid": payload}
        payload = {"limit": 32, "offset": 0, "cid": 0, **payload}
        if cid := payload.get("cid"):
            payload.setdefault("file_id", cid)
        return self.request(url=api, params=payload, async_=async_, **request_kwargs)

    @overload
    def fs_files_image_app(
        self, 
        payload: int | str | dict = 0, 
        /, 
        app: str = "android", 
        base_url: str | Callable[[], str] = "https://proapi.115.com", 
        *, 
        async_: Literal[False] = False, 
        **request_kwargs, 
    ) -> dict:
        ...
    @overload
    def fs_files_image_app(
        self, 
        payload: int | str | dict = 0, 
        /, 
        app: str = "android", 
        base_url: str | Callable[[], str] = "https://proapi.115.com", 
        *, 
        async_: Literal[True], 
        **request_kwargs, 
    ) -> Coroutine[Any, Any, dict]:
        ...
    def fs_files_image_app(
        self, 
        payload: int | str | dict = 0, 
        /, 
        app: str = "android", 
        base_url: str | Callable[[], str] = "https://proapi.115.com", 
        *, 
        async_: Literal[False, True] = False, 
        **request_kwargs, 
    ) -> dict | Coroutine[Any, Any, dict]:
        """获取目录中的图片列表和基本信息

        GET https://proapi.115.com/android/files/imglist

        :payload:
            - cid: int | str = 0 💡 目录 id，对应 parent_id
            - limit: int = 32    💡 一页大小，建议控制在 <= 9000，不然会报错
            - offset: int = 0    💡 索引偏移，索引从 0 开始计算

            - aid: int = 1 💡 area_id

                - 0: 会被视为 1
                - 1: 正常文件
                - 2: <unknown>
                - 3: <unknown>
                - 4: <unknown>
                - 5: <unknown>
                - 7: 回收站文件
                - 9: <unknown>
                - 12:瞬间文件
                - 15: <unknown>
                - 120: 彻底删除文件、简历附件
                - <其它>: 会被视为 0

            - asc: 0 | 1 = <default> 💡 是否升序排列
            - cur: 0 | 1 = <default> 💡 只罗列当前目录
            - o: str = <default> 💡 用某字段排序

                - 文件名："file_name"
                - 文件大小："file_size"
                - 文件种类："file_type"
                - 修改时间："user_utime"
                - 创建时间："user_ptime"
                - 上一次打开时间："user_otime"
        """
        api = complete_url("/files/imglist", base_url=base_url, app=app)
        if isinstance(payload, (int, str)):
            payload = {"cid": payload}
        payload = {"limit": 32, "offset": 0, "aid": 1, "cid": 0, **payload}
        return self.request(url=api, params=payload, async_=async_, **request_kwargs)

    @overload
    def fs_files_media_app(
        self, 
        payload: int | str | dict = 0, 
        /, 
        app: str = "android", 
        base_url: str | Callable[[], str] = "https://proapi.115.com", 
        *, 
        async_: Literal[False] = False, 
        **request_kwargs, 
    ) -> dict:
        ...
    @overload
    def fs_files_media_app(
        self, 
        payload: int | str | dict = 0, 
        /, 
        app: str = "android", 
        base_url: str | Callable[[], str] = "https://proapi.115.com", 
        *, 
        async_: Literal[True], 
        **request_kwargs, 
    ) -> Coroutine[Any, Any, dict]:
        ...
    def fs_files_media_app(
        self, 
        payload: int | str | dict = 0, 
        /, 
        app: str = "android", 
        base_url: str | Callable[[], str] = "https://proapi.115.com", 
        *, 
        async_: Literal[False, True] = False, 
        **request_kwargs, 
    ) -> dict | Coroutine[Any, Any, dict]:
        """获取目录中的文件列表和基本信息

        GET https://proapi.115.com/android/files/medialist

        :payload:
            - cid: int | str = 0 💡 目录 id，对应 parent_id
            - limit: int = 32    💡 一页大小，建议控制在 <= 9000，不然会报错
            - offset: int = 0    💡 索引偏移，索引从 0 开始计算

            - aid: int = 1 💡 area_id

                - 0: 会被视为 1
                - 1: 正常文件
                - 2: <unknown>
                - 3: <unknown>
                - 4: <unknown>
                - 5: <unknown>
                - 7: 回收站文件
                - 9: <unknown>
                - 12:瞬间文件
                - 15: <unknown>
                - 120: 彻底删除文件、简历附件
                - <其它>: 会被视为 0

            - asc: 0 | 1 = <default> 💡 是否升序排列
            - cur: 0 | 1 = <default> 💡 只罗列当前目录
            - o: str = <default> 💡 用某字段排序

                - 文件名："file_name"
                - 文件大小："file_size"
                - 文件种类："file_type"
                - 修改时间："user_utime"
                - 创建时间："user_ptime"
                - 上一次打开时间："user_otime"

            - type: int = 0 💡 文件类型

                - 0: 相当于 2
                - 1: 文档
                - 2: 图片
                - 3: 音频
                - 4: 视频
                - 5: 压缩包
                - 6: 软件/应用
                - 7: 书籍
                - ...: > 7 则相当于 1，< 0 则是全部文件
        """
        api = complete_url("/files/medialist", base_url=base_url, app=app)
        if isinstance(payload, (int, str)):
            payload = {"cid": payload}
        payload = {"limit": 32, "offset": 0, "aid": 1, "type": 0, "cid": 0, **payload}
        return self.request(url=api, params=payload, async_=async_, **request_kwargs)

    @overload
    def fs_files_second_type(
        self, 
        payload: Literal[1, 2, 3, 4, 5, 6, 7] | dict = 1, 
        /, 
        base_url: str | Callable[[], str] = "https://webapi.115.com", 
        *, 
        async_: Literal[False] = False, 
        **request_kwargs, 
    ) -> dict:
        ...
    @overload
    def fs_files_second_type(
        self, 
        payload: Literal[1, 2, 3, 4, 5, 6, 7] | dict = 1, 
        /, 
        base_url: str | Callable[[], str] = "https://webapi.115.com", 
        *, 
        async_: Literal[True], 
        **request_kwargs, 
    ) -> Coroutine[Any, Any, dict]:
        ...
    def fs_files_second_type(
        self, 
        payload: Literal[1, 2, 3, 4, 5, 6, 7] | dict = 1, 
        /, 
        base_url: str | Callable[[], str] = "https://webapi.115.com", 
        *, 
        async_: Literal[False, True] = False, 
        **request_kwargs, 
    ) -> dict | Coroutine[Any, Any, dict]:
        """获取目录中某个文件类型的扩展名的（去重）列表

        GET https://webapi.115.com/files/get_second_type

        :payload:
            - cid: int | str = 0 💡 目录 id，对应 parent_id
            - type: int = 1 💡 文件类型

                - 1: 文档
                - 2: 图片
                - 3: 音频
                - 4: 视频
                - 5: 压缩包
                - 6: 软件/应用
                - 7: 书籍

            - file_label: int | str = <default> 💡 标签 id，多个用逗号 "," 隔开
        """
        api = complete_url("/files/get_second_type", base_url=base_url)
        if isinstance(payload, int):
            payload = {"type": payload}
        payload = {"cid": 0, "type": 1, **payload}
        return self.request(url=api, params=payload, async_=async_, **request_kwargs)

    @overload
    def fs_files_second_type_app(
        self, 
        payload: Literal[1, 2, 3, 4, 5, 6, 7] | dict = 1, 
        /, 
        app: str = "android", 
        base_url: str | Callable[[], str] = "https://proapi.115.com", 
        *, 
        async_: Literal[False] = False, 
        **request_kwargs, 
    ) -> dict:
        ...
    @overload
    def fs_files_second_type_app(
        self, 
        payload: Literal[1, 2, 3, 4, 5, 6, 7] | dict = 1, 
        /, 
        app: str = "android", 
        base_url: str | Callable[[], str] = "https://proapi.115.com", 
        *, 
        async_: Literal[True], 
        **request_kwargs, 
    ) -> Coroutine[Any, Any, dict]:
        ...
    def fs_files_second_type_app(
        self, 
        payload: Literal[1, 2, 3, 4, 5, 6, 7] | dict = 1, 
        /, 
        app: str = "android", 
        base_url: str | Callable[[], str] = "https://proapi.115.com", 
        *, 
        async_: Literal[False, True] = False, 
        **request_kwargs, 
    ) -> dict | Coroutine[Any, Any, dict]:
        """获取目录中某个文件类型的扩展名的（去重）列表

        GET https://proapi.115.com/android/2.0/ufile/get_second_type

        :payload:
            - cid: int | str = 0 💡 目录 id，对应 parent_id
            - type: int = 1 💡 文件类型

                - 1: 文档
                - 2: 图片
                - 3: 音频
                - 4: 视频
                - 5: 压缩包
                - 6: 软件/应用
                - 7: 书籍

            - file_label: int | str = <default> 💡 标签 id，多个用逗号 "," 隔开
        """
        api = complete_url("/2.0/ufile/get_second_type", base_url=base_url, app=app)
        if isinstance(payload, int):
            payload = {"type": payload}
        payload = {"cid": 0, "type": 1, **payload}
        return self.request(url=api, params=payload, async_=async_, **request_kwargs)

    @overload
    def fs_files_update_app(
        self, 
        payload: int | str | tuple[int | str] | list | dict, 
        /, 
        app: str = "android", 
        base_url: str | Callable[[], str] = "https://proapi.115.com", 
        *, 
        async_: Literal[False] = False, 
        **request_kwargs, 
    ) -> dict:
        ...
    @overload
    def fs_files_update_app(
        self, 
        payload: int | str | tuple[int | str] | list | dict, 
        /, 
        app: str = "android", 
        base_url: str | Callable[[], str] = "https://proapi.115.com", 
        *, 
        async_: Literal[True], 
        **request_kwargs, 
    ) -> Coroutine[Any, Any, dict]:
        ...
    def fs_files_update_app(
        self, 
        payload: int | str | tuple[int | str] | list | dict, 
        /, 
        app: str = "android", 
        base_url: str | Callable[[], str] = "https://proapi.115.com", 
        *, 
        async_: Literal[False, True] = False, 
        **request_kwargs, 
    ) -> dict | Coroutine[Any, Any, dict]:
        """设置（若干个）文件或目录（名字、备注、标签等）

        POST https://proapi.115.com/android/files/update

        :payload:
            - file_id: int | str
            - file_id[]: int | str
            - ...
            - file_id[0]: int | str
            - file_id[1]: int | str
            - ...
            - file_desc: str = <default> 💡 可以用 html
            - file_label: int | str = <default> 💡 标签 id，多个用逗号 "," 隔开
            - file_name: str = <default>        💡 文件或目录名
            - fid_cover: int | str = <default>  💡 封面图片的文件 id，多个用逗号 "," 隔开，如果要删除，值设为 0 即可
            - show_play_long: 0 | 1 = <default> 💡 文件名称显示时长
            - ...
        """
        api = complete_url("/files/update", base_url=base_url, app=app)
        if isinstance(payload, (int, str)):
            payload = {"file_id": payload}
        elif isinstance(payload, tuple):
            payload = {f"file_id[i]": p for i, p in enumerate(payload)}
        return self.request(url=api, method="POST", data=payload, async_=async_, **request_kwargs)

    @overload
    def fs_folder_playlong(
        self, 
        payload: int | str | dict, 
        /, 
        base_url: str | Callable[[], str] = "https://aps.115.com", 
        *, 
        async_: Literal[False] = False, 
        **request_kwargs, 
    ) -> dict:
        ...
    @overload
    def fs_folder_playlong(
        self, 
        payload: int | str | dict, 
        /, 
        base_url: str | Callable[[], str] = "https://aps.115.com", 
        *, 
        async_: Literal[True], 
        **request_kwargs, 
    ) -> Coroutine[Any, Any, dict]:
        ...
    def fs_folder_playlong(
        self, 
        payload: int | str | dict, 
        /, 
        base_url: str | Callable[[], str] = "https://aps.115.com", 
        *, 
        async_: Literal[False, True] = False, 
        **request_kwargs, 
    ) -> dict | Coroutine[Any, Any, dict]:
        """获取目录内文件总的播放时长

        POST https://aps.115.com/getFolderPlaylong

        :payload:
            - folder_ids: int | str 💡 目录 id，多个用逗号 "," 隔开
        """
        api = complete_url("/getFolderPlaylong", base_url=base_url)
        if isinstance(payload, (int, str)):
            payload = {"folder_ids": payload}
        return self.request(url=api, method="POST", data=payload, async_=async_, **request_kwargs)

    @overload
    def fs_folder_playlong_set(
        self, 
        /, 
        ids: int | str | Iterable[int | str], 
        is_set: Literal[0, 1] = 1, 
        base_url: str | Callable[[], str] = "https://webapi.115.com", 
        *, 
        async_: Literal[False] = False, 
        **request_kwargs, 
    ) -> dict:
        ...
    @overload
    def fs_folder_playlong_set(
        self, 
        /, 
        ids: int | str | Iterable[int | str], 
        is_set: Literal[0, 1] = 1, 
        base_url: str | Callable[[], str] = "https://webapi.115.com", 
        *, 
        async_: Literal[True], 
        **request_kwargs, 
    ) -> Coroutine[Any, Any, dict]:
        ...
    def fs_folder_playlong_set(
        self, 
        /, 
        ids: int | str | Iterable[int | str], 
        is_set: Literal[0, 1] = 1, 
        base_url: str | Callable[[], str] = "https://webapi.115.com", 
        *, 
        async_: Literal[False, True] = False, 
        **request_kwargs, 
    ) -> dict | Coroutine[Any, Any, dict]:
        """显示或取消目录内文件总的播放时长，此接口是对 `fs_batch_edit` 的封装

        :param ids: 一个或多个文件或目录的 id
        :param is_set: 是否显示时长

        :return: 返回成功状态
        """
        if isinstance(ids, (int, str)):
            payload = {f"show_play_long[{ids}]": is_set}
        else:
            payload = {f"show_play_long[{id}]": is_set for id in ids}
        return self.fs_batch_edit(payload, base_url=base_url, async_=async_, **request_kwargs)

    @overload
    def fs_folder_update_app(
        self, 
        payload: dict, 
        /, 
        app: str = "android", 
        base_url: str | Callable[[], str] = "https://proapi.115.com", 
        *, 
        async_: Literal[False] = False, 
        **request_kwargs, 
    ) -> dict:
        ...
    @overload
    def fs_folder_update_app(
        self, 
        payload: dict, 
        /, 
        app: str = "android", 
        base_url: str | Callable[[], str] = "https://proapi.115.com", 
        *, 
        async_: Literal[True], 
        **request_kwargs, 
    ) -> Coroutine[Any, Any, dict]:
        ...
    def fs_folder_update_app(
        self, 
        payload: dict, 
        /, 
        app: str = "android", 
        base_url: str | Callable[[], str] = "https://proapi.115.com", 
        *, 
        async_: Literal[False, True] = False, 
        **request_kwargs, 
    ) -> dict | Coroutine[Any, Any, dict]:
        """设置文件或目录，或者创建目录

        POST https://proapi.115.com/android/folder/update

        .. note::
            如果提供了 `cid` 和 `name`，则表示对 `cid` 对应的文件或目录进行改名，否则创建目录

        :payload:
            - name: str 💡 名字
            - pid: int | str = 0 💡 在此目录 id 下创建目录
            - aid: int = 1 💡 area_id
            - cid: int = <default> 💡 文件或目录的 id，优先级高于 `pid`
            - user_id: int | str = <default> 💡 用户 id
            - ...
        """
        api = complete_url("/folder/update", base_url=base_url, app=app)
        payload = {"aid": 1, "pid": 0, "user_id": self.user_id, **payload}
        return self.request(url=api, method="POST", data=payload, async_=async_, **request_kwargs)

    @overload
    def fs_hide(
        self, 
        payload: int | str | Iterable[int | str] | dict, 
        /, 
        base_url: str | Callable[[], str] = "https://webapi.115.com", 
        *, 
        async_: Literal[False] = False, 
        **request_kwargs, 
    ) -> dict:
        ...
    @overload
    def fs_hide(
        self, 
        payload: int | str | Iterable[int | str] | dict, 
        /, 
        base_url: str | Callable[[], str] = "https://webapi.115.com", 
        *, 
        async_: Literal[True], 
        **request_kwargs, 
    ) -> Coroutine[Any, Any, dict]:
        ...
    def fs_hide(
        self, 
        payload: int | str | Iterable[int | str] | dict, 
        /, 
        base_url: str | Callable[[], str] = "https://webapi.115.com", 
        *, 
        async_: Literal[False, True] = False, 
        **request_kwargs, 
    ) -> dict | Coroutine[Any, Any, dict]:
        """隐藏或者取消隐藏某些文件或目录

        POST https://webapi.115.com/files/hiddenfiles

        :payload:
            - fid[0]: int | str
            - fid[1]: int | str
            - ...
            - hidden: 0 | 1 = 1
        """
        api = complete_url("/files/hiddenfiles", base_url=base_url)
        if isinstance(payload, (int, str)):
            payload = {"fid[0]": payload}
        elif not isinstance(payload, dict):
            payload = {f"fid[{i}]": f for i, f in enumerate(payload)}
        payload.setdefault("hidden", 1)
        return self.request(url=api, method="POST", data=payload, async_=async_, **request_kwargs)

    @overload
    def fs_hide_app(
        self, 
        payload: int | str | Iterable[int | str] | dict, 
        /, 
        app: str = "android", 
        base_url: str | Callable[[], str] = "https://proapi.115.com", 
        *, 
        async_: Literal[False] = False, 
        **request_kwargs, 
    ) -> dict:
        ...
    @overload
    def fs_hide_app(
        self, 
        payload: int | str | Iterable[int | str] | dict, 
        /, 
        app: str = "android", 
        base_url: str | Callable[[], str] = "https://proapi.115.com", 
        *, 
        async_: Literal[True], 
        **request_kwargs, 
    ) -> Coroutine[Any, Any, dict]:
        ...
    def fs_hide_app(
        self, 
        payload: int | str | Iterable[int | str] | dict, 
        /, 
        app: str = "android", 
        base_url: str | Callable[[], str] = "https://proapi.115.com", 
        *, 
        async_: Literal[False, True] = False, 
        **request_kwargs, 
    ) -> dict | Coroutine[Any, Any, dict]:
        """隐藏或者取消隐藏某些文件或目录

        POST https://proapi.115.com/android/files/hiddenfiles

        :payload:
            - fid: int | str 💡 文件或目录的 id，多个用逗号 "," 隔开
            - hidden: 0 | 1 = 1
        """
        api = complete_url("/files/hiddenfiles", base_url=base_url, app=app)
        if isinstance(payload, (int, str)):
            payload = {"fid[0]": payload}
        elif not isinstance(payload, dict):
            payload = {"fid": ",".join(map(str, payload))}
        payload.setdefault("hidden", 1) # type: ignore
        return self.request(url=api, method="POST", data=payload, async_=async_, **request_kwargs)

    @overload
    def fs_hidden_switch(
        self, 
        payload: bool | int | str | dict = False, 
        /, 
        base_url: str | Callable[[], str] = "https://115.com", 
        *, 
        async_: Literal[False] = False, 
        **request_kwargs, 
    ) -> dict:
        ...
    @overload
    def fs_hidden_switch(
        self, 
        payload: bool | int | str | dict = False, 
        /, 
        base_url: str | Callable[[], str] = "https://115.com", 
        *, 
        async_: Literal[True], 
        **request_kwargs, 
    ) -> Coroutine[Any, Any, dict]:
        ...
    def fs_hidden_switch(
        self, 
        payload: bool | int | str | dict = False, 
        /, 
        base_url: str | Callable[[], str] = "https://115.com", 
        *, 
        async_: Literal[False, True] = False, 
        **request_kwargs, 
    ) -> dict | Coroutine[Any, Any, dict]:
        """切换隐藏模式

        POST https://115.com/?ct=hiddenfiles&ac=switching

        .. tip::
            开启隐藏模式时，需要提供安全密钥，关闭时则不需要

        .. tip::
            这个接口必须提供安全密钥。如果不提供，则默认使用 "000000"，在不必要的情况下，完全可以把安全密钥设为这个值

        .. note::
            这个接口会返回一个 "token" 字段，可以提供给某些接口，作为通过安全密钥验证的凭证

        :payload:
            - safe_pwd: str = "000000" 💡 安全密钥
            - show: 0 | 1 = <default>  💡 是否开启隐藏模式：0:关闭 1:开启
            - valid_type: int = <default>
        """
        api = complete_url(base_url=base_url, query={"ct": "hiddenfiles", "ac": "switching"})
        if payload in (0, 1):
            payload = {"show": int(cast(int, payload))}
        elif isinstance(payload, (int, str)):
            payload = {"show": 1, "safe_pwd": f"{payload:>06}"}
        payload["safe_pwd"] = format(payload.get("safe_pwd") or "", ">06")
        return self.request(url=api, method="POST", data=payload, async_=async_, **request_kwargs)

    @overload
    def fs_hidden_switch_app(
        self, 
        payload: bool | int | str | dict = False, 
        /, 
        app: str = "android", 
        base_url: str | Callable[[], str] = "https://proapi.115.com", 
        *, 
        async_: Literal[False] = False, 
        **request_kwargs, 
    ) -> dict:
        ...
    @overload
    def fs_hidden_switch_app(
        self, 
        payload: bool | int | str | dict = False, 
        /, 
        app: str = "android", 
        base_url: str | Callable[[], str] = "https://proapi.115.com", 
        *, 
        async_: Literal[True], 
        **request_kwargs, 
    ) -> Coroutine[Any, Any, dict]:
        ...
    def fs_hidden_switch_app(
        self, 
        payload: bool | int | str | dict = False, 
        /, 
        app: str = "android", 
        base_url: str | Callable[[], str] = "https://proapi.115.com", 
        *, 
        async_: Literal[False, True] = False, 
        **request_kwargs, 
    ) -> dict | Coroutine[Any, Any, dict]:
        """切换隐藏模式

        GET https://proapi.115.com/android/files/hiddenswitch

        .. note::
            可以在设置中的【账号安全/安全密钥】页面下，关闭【文件(隐藏模式/清空删除回收站)】的按钮，就不需要传安全密钥了

        :payload:
            - safe_pwd: str = "000000" 💡 安全密钥，值为实际安全密钥的 md5 哈希值
            - show: 0 | 1 = <default>  💡 是否开启隐藏模式：0:关闭 1:开启
            - token: str = <default>   💡 令牌，调用 `P115client.user_security_key_check()` 获得，可以不传
        """
        api = complete_url("/files/hiddenswitch", base_url=base_url, app=app)
        if payload in (0, 1):
            payload = {"show": int(cast(int, payload))}
        elif isinstance(payload, (int, str)):
            payload = {"show": 1, "safe_pwd": payload}
        payload["safe_pwd"] = md5_secret_password(payload.get("safe_pwd"))
        return self.request(url=api, params=payload, async_=async_, **request_kwargs)

    @overload
    def fs_history(
        self, 
        payload: str | dict, 
        /, 
        base_url: str | Callable[[], str] = "https://webapi.115.com", 
        *, 
        async_: Literal[False] = False, 
        **request_kwargs, 
    ) -> dict:
        ...
    @overload
    def fs_history(
        self, 
        payload: str | dict, 
        /, 
        base_url: str | Callable[[], str] = "https://webapi.115.com", 
        *, 
        async_: Literal[True], 
        **request_kwargs, 
    ) -> Coroutine[Any, Any, dict]:
        ...
    def fs_history(
        self, 
        payload: str | dict, 
        /, 
        base_url: str | Callable[[], str] = "https://webapi.115.com", 
        *, 
        async_: Literal[False, True] = False, 
        **request_kwargs, 
    ) -> dict | Coroutine[Any, Any, dict]:
        """获取文件的观看历史，主要用于视频

        GET https://webapi.115.com/files/history

        :payload:
            - pick_code: str
            - fetch: str = "one"
            - category: int = 1
            - share_id: int | str = <default>
        """
        api = complete_url("/files/history", base_url=base_url)
        if isinstance(payload, str):
            payload = {"pick_code": payload}
        payload = {"category": 1, "fetch": "one", **payload}
        return self.request(url=api, params=payload, async_=async_, **request_kwargs)

    fs_video_history = fs_history

    @overload
    def fs_history_app(
        self, 
        payload: str | dict, 
        /, 
        app: str = "android", 
        base_url: str | Callable[[], str] = "https://proapi.115.com", 
        *, 
        async_: Literal[False] = False, 
        **request_kwargs, 
    ) -> dict:
        ...
    @overload
    def fs_history_app(
        self, 
        payload: str | dict, 
        /, 
        app: str = "android", 
        base_url: str | Callable[[], str] = "https://proapi.115.com", 
        *, 
        async_: Literal[True], 
        **request_kwargs, 
    ) -> Coroutine[Any, Any, dict]:
        ...
    def fs_history_app(
        self, 
        payload: str | dict, 
        /, 
        app: str = "android", 
        base_url: str | Callable[[], str] = "https://proapi.115.com", 
        *, 
        async_: Literal[False, True] = False, 
        **request_kwargs, 
    ) -> dict | Coroutine[Any, Any, dict]:
        """获取历史记录

        GET https://proapi.115.com/android/history

        :payload:
            - pick_code: str
            - fetch: str = "one"
            - category: int = 1
            - share_id: int | str = <default>
        """
        api = complete_url("/history", base_url=base_url, app=app)
        if isinstance(payload, str):
            payload = {"pick_code": payload}
        payload = {"category": 1, "action": "get_one", **payload}
        return self.request(url=api, params=payload, async_=async_, **request_kwargs)

    fs_video_history_app = fs_history_app

    @overload
    def fs_history_clean(
        self, 
        payload: int | str | dict = 0, 
        /, 
        base_url: str | Callable[[], str] = "https://webapi.115.com", 
        *, 
        async_: Literal[False] = False, 
        **request_kwargs, 
    ) -> dict:
        ...
    @overload
    def fs_history_clean(
        self, 
        payload: int | str | dict = 0, 
        /, 
        base_url: str | Callable[[], str] = "https://webapi.115.com", 
        *, 
        async_: Literal[True], 
        **request_kwargs, 
    ) -> Coroutine[Any, Any, dict]:
        ...
    def fs_history_clean(
        self, 
        payload: int | str | dict = 0, 
        /, 
        base_url: str | Callable[[], str] = "https://webapi.115.com", 
        *, 
        async_: Literal[False, True] = False, 
        **request_kwargs, 
    ) -> dict | Coroutine[Any, Any, dict]:
        """清空历史记录

        POST https://webapi.115.com/history/clean

        :payload:
            - type: int | str = 0 💡 类型（？？表示还未搞清楚），多个用逗号 "," 隔开

                - 全部: 0
                - ？？: 1（大概和接收有关）
                - 离线下载: 2
                - 播放视频: 3
                - 上传: 4
                - ？？: 5
                - ？？: 6（似乎是一些在离线、转存等过程中有重名的目录）
                - 接收: 7
                - 移动: 8

            - with_file: 0 | 1 = 0 💡 是否同时删除文件
        """
        api = complete_url("/history/clean", base_url=base_url)
        if isinstance(payload, (int, str)):
            payload = {"type": payload}
        payload = {"with_file": 0, "type": 0, **payload}
        return self.request(url=api, method="POST", data=payload, async_=async_, **request_kwargs)

    @overload
    def fs_history_delete(
        self, 
        payload: int | str | dict, 
        /, 
        base_url: str | Callable[[], str] = "https://webapi.115.com", 
        *, 
        async_: Literal[False] = False, 
        **request_kwargs, 
    ) -> dict:
        ...
    @overload
    def fs_history_delete(
        self, 
        payload: int | str | dict, 
        /, 
        base_url: str | Callable[[], str] = "https://webapi.115.com", 
        *, 
        async_: Literal[True], 
        **request_kwargs, 
    ) -> Coroutine[Any, Any, dict]:
        ...
    def fs_history_delete(
        self, 
        payload: int | str | dict, 
        /, 
        base_url: str | Callable[[], str] = "https://webapi.115.com", 
        *, 
        async_: Literal[False, True] = False, 
        **request_kwargs, 
    ) -> dict | Coroutine[Any, Any, dict]:
        """删除历史记录

        POST https://webapi.115.com/history/delete

        :payload:
            - id: int | str 💡 多个用逗号 "," 隔开
            - with_file: 0 | 1 = 0
        """
        api = complete_url("/history/delete", base_url=base_url)
        if isinstance(payload, (int, str)):
            payload = {"id": payload}
        payload.setdefault("with_file", 0)
        return self.request(url=api, method="POST", data=payload, async_=async_, **request_kwargs)

    @overload
    def fs_history_delete_app(
        self, 
        payload: int | str | dict, 
        /, 
        app: str = "android", 
        base_url: str | Callable[[], str] = "https://proapi.115.com", 
        *, 
        async_: Literal[False] = False, 
        **request_kwargs, 
    ) -> dict:
        ...
    @overload
    def fs_history_delete_app(
        self, 
        payload: int | str | dict, 
        /, 
        app: str = "android", 
        base_url: str | Callable[[], str] = "https://proapi.115.com", 
        *, 
        async_: Literal[True], 
        **request_kwargs, 
    ) -> Coroutine[Any, Any, dict]:
        ...
    def fs_history_delete_app(
        self, 
        payload: int | str | dict, 
        /, 
        app: str = "android", 
        base_url: str | Callable[[], str] = "https://proapi.115.com", 
        *, 
        async_: Literal[False, True] = False, 
        **request_kwargs, 
    ) -> dict | Coroutine[Any, Any, dict]:
        """删除历史记录

        POST https://proapi.115.com/android/history/delete

        :payload:
            - id: int | str 💡 多个用逗号 "," 隔开
            - with_file: 0 | 1 = 0
        """
        api = complete_url("/history/delete", base_url=base_url, app=app)
        if isinstance(payload, (int, str)):
            payload = {"id": payload}
        payload.setdefault("with_file", 0)
        return self.request(url=api, method="POST", data=payload, async_=async_, **request_kwargs)

    @overload
    def fs_history_clean_app(
        self, 
        payload: int | str | dict = 0, 
        /, 
        app: str = "android", 
        base_url: str | Callable[[], str] = "https://proapi.115.com", 
        *, 
        async_: Literal[False] = False, 
        **request_kwargs, 
    ) -> dict:
        ...
    @overload
    def fs_history_clean_app(
        self, 
        payload: int | str | dict = 0, 
        /, 
        app: str = "android", 
        base_url: str | Callable[[], str] = "https://proapi.115.com", 
        *, 
        async_: Literal[True], 
        **request_kwargs, 
    ) -> Coroutine[Any, Any, dict]:
        ...
    def fs_history_clean_app(
        self, 
        payload: int | str | dict = 0, 
        /, 
        app: str = "android", 
        base_url: str | Callable[[], str] = "https://proapi.115.com", 
        *, 
        async_: Literal[False, True] = False, 
        **request_kwargs, 
    ) -> dict | Coroutine[Any, Any, dict]:
        """清空历史记录

        POST https://proapi.115.com/android/history/clean

        :payload:
            - type: int | str = 0 💡 类型（？？表示还未搞清楚），多个用逗号 "," 隔开

                - 全部: 0
                - ？？: 1（大概和接收有关）
                - 离线下载: 2
                - 播放视频: 3
                - 上传: 4
                - ？？: 5
                - ？？: 6（似乎是一些在离线、转存等过程中有重名的目录）
                - 接收: 7
                - 移动: 8

            - with_file: 0 | 1 = 0
        """
        api = complete_url("/history/clean", base_url=base_url, app=app)
        if isinstance(payload, (int, str)):
            payload = {"type": payload}
        payload = {"with_file": 0, "type": 0, **payload}
        return self.request(url=api, method="POST", data=payload, async_=async_, **request_kwargs)

    @overload
    def fs_history_list(
        self, 
        payload: int | str | dict = 0, 
        /, 
        base_url: str | Callable[[], str] = "https://webapi.115.com", 
        *, 
        async_: Literal[False] = False, 
        **request_kwargs, 
    ) -> dict:
        ...
    @overload
    def fs_history_list(
        self, 
        payload: int | str | dict = 0, 
        /, 
        base_url: str | Callable[[], str] = "https://webapi.115.com", 
        *, 
        async_: Literal[True], 
        **request_kwargs, 
    ) -> Coroutine[Any, Any, dict]:
        ...
    def fs_history_list(
        self, 
        payload: int | str | dict = 0, 
        /, 
        base_url: str | Callable[[], str] = "https://webapi.115.com", 
        *, 
        async_: Literal[False, True] = False, 
        **request_kwargs, 
    ) -> dict | Coroutine[Any, Any, dict]:
        """历史记录列表

        GET https://webapi.115.com/history/list

        :payload:
            - offset: int = 0
            - limit: int = 1150
            - played_end: 0 | 1 = <default> 💡 是否已经播放完
            - type: int = <default> 💡 类型（？？表示还未搞清楚），多个用逗号 "," 隔开

                - 全部: 0
                - ？？: 1（大概和接收有关）
                - 离线下载: 2
                - 播放视频: 3
                - 上传: 4
                - ？？: 5
                - ？？: 6（似乎是一些在离线、转存等过程中有重名的目录）
                - 接收: 7
                - 移动: 8
        """
        api = complete_url("/history/list", base_url=base_url)
        if isinstance(payload, (int, str)):
            payload = {"offset": payload}
        payload = {"limit": 1150, "offset": 0, **payload}
        return self.request(url=api, params=payload, async_=async_, **request_kwargs)

    @overload
    def fs_history_list_app(
        self, 
        payload: int | str | dict = 0, 
        /, 
        app: str = "android", 
        base_url: str | Callable[[], str] = "https://proapi.115.com", 
        *, 
        async_: Literal[False] = False, 
        **request_kwargs, 
    ) -> dict:
        ...
    @overload
    def fs_history_list_app(
        self, 
        payload: int | str | dict = 0, 
        /, 
        app: str = "android", 
        base_url: str | Callable[[], str] = "https://proapi.115.com", 
        *, 
        async_: Literal[True], 
        **request_kwargs, 
    ) -> Coroutine[Any, Any, dict]:
        ...
    def fs_history_list_app(
        self, 
        payload: int | str | dict = 0, 
        /, 
        app: str = "android", 
        base_url: str | Callable[[], str] = "https://proapi.115.com", 
        *, 
        async_: Literal[False, True] = False, 
        **request_kwargs, 
    ) -> dict | Coroutine[Any, Any, dict]:
        """历史记录列表

        GET https://proapi.115.com/android/history/list

        :payload:
            - offset: int = 0
            - limit: int = 1150
            - played_end: 0 | 1 = <default>
            - type: int = <default> 💡 类型（？？表示还未搞清楚），多个用逗号 "," 隔开

                - 全部: 0
                - ？？: 1（大概和接收有关）
                - 离线下载: 2
                - 播放视频: 3
                - 上传: 4
                - ？？: 5
                - ？？: 6（似乎是一些在离线、转存等过程中有重名的目录）
                - 接收: 7
                - 移动: 8
        """
        api = complete_url("/history/list", base_url=base_url, app=app)
        if isinstance(payload, (int, str)):
            payload = {"offset": payload}
        payload = {"limit": 1150, "offset": 0, **payload}
        return self.request(url=api, params=payload, async_=async_, **request_kwargs)

    @overload
    def fs_history_move_target_list(
        self, 
        payload: int | str | dict = 0, 
        /, 
        base_url: str | Callable[[], str] = "https://webapi.115.com", 
        *, 
        async_: Literal[False] = False, 
        **request_kwargs, 
    ) -> dict:
        ...
    @overload
    def fs_history_move_target_list(
        self, 
        payload: int | str | dict = 0, 
        /, 
        base_url: str | Callable[[], str] = "https://webapi.115.com", 
        *, 
        async_: Literal[True], 
        **request_kwargs, 
    ) -> Coroutine[Any, Any, dict]:
        ...
    def fs_history_move_target_list(
        self, 
        payload: int | str | dict = 0, 
        /, 
        base_url: str | Callable[[], str] = "https://webapi.115.com", 
        *, 
        async_: Literal[False, True] = False, 
        **request_kwargs, 
    ) -> dict | Coroutine[Any, Any, dict]:
        """最近移动记录

        GET https://webapi.115.com/history/move_target_list

        .. tip::
            使用这个方法，甚至可以随时获取近期有文件移入的目录，可以部分代替 115 生活的移动事件的使用

        :payload:
            - cid: int | str = 0 💡 目录 id，对应 parent_id
            - limit: int = 1150 💡 分页大小，最大值不一定，看数据量，7,000 应该总是安全的，10,000 有可能报错，但有时也可以 20,000 而成功
            - offset: int = 0 💡 分页开始的索引，索引从 0 开始计算

            - aid: int = 1 💡 area_id

                - 0: 会被视为 1
                - 1: 正常文件
                - 2: <unknown>
                - 3: <unknown>
                - 4: <unknown>
                - 5: <unknown>
                - 7: 回收站文件
                - 9: <unknown>
                - 12:瞬间文件
                - 15: <unknown>
                - 120: 彻底删除文件、简历附件
                - <其它>: 会被视为 0

            - asc: 0 | 1 = <default> 💡 是否升序排列。0:降序 1:升序
            - custom_order: 0 | 1 | 2 = <default> 💡 是否使用记忆排序。如果指定了 "asc"、"fc_mix"、"o" 中其一，则此参数会被自动设置为 2

                - 0: 使用记忆排序（自定义排序失效） 
                - 1: 使用自定义排序（不使用记忆排序） 
                - 2: 自定义排序（非目录置顶）

            - date: str = <default> 💡 筛选日期
            - min_size: int = 0 💡 最小的文件大小
            - max_size: int = 0 💡 最大的文件大小
            - natsort: 0 | 1 = <default> 💡 是否执行自然排序(natural sorting)
            - nf: str = <default> 💡 不要显示文件（即仅显示目录），但如果 show_dir=0，则此参数无效
            - o: str = <default> 💡 用某字段排序（未定义的值会被视为 "user_utime"）

                - "file_name": 文件名
                - "file_size": 文件大小
                - "file_type": 文件种类
                - "user_etime": 事件时间（无效，效果相当于 "user_utime"）
                - "user_utime": 修改时间
                - "user_ptime": 创建时间（无效，效果相当于 "user_utime"）
                - "user_otime": 上一次打开时间（无效，效果相当于 "user_utime"）

            - qid: int = <default>
            - search_value: str = <default> 💡 搜索文本
            - show_dir: 0 | 1 = 1 💡 是否显示目录
            - snap: 0 | 1 = <default>
            - source: str = <default>
        """
        api = complete_url("/history/move_target_list", base_url=base_url)
        if isinstance(payload, (int, str)):
            payload = {"offset": payload}
        payload = {"cid": 0, "limit": 1150, "offset": 0, "aid": 1, "show_dir": 1, **payload}
        return self.request(url=api, params=payload, async_=async_, **request_kwargs)

    @overload
    def fs_history_receive_list(
        self, 
        payload: int | str | dict = 0, 
        /, 
        base_url: str | Callable[[], str] = "https://webapi.115.com", 
        *, 
        async_: Literal[False] = False, 
        **request_kwargs, 
    ) -> dict:
        ...
    @overload
    def fs_history_receive_list(
        self, 
        payload: int | str | dict = 0, 
        /, 
        base_url: str | Callable[[], str] = "https://webapi.115.com", 
        *, 
        async_: Literal[True], 
        **request_kwargs, 
    ) -> Coroutine[Any, Any, dict]:
        ...
    def fs_history_receive_list(
        self, 
        payload: int | str | dict = 0, 
        /, 
        base_url: str | Callable[[], str] = "https://webapi.115.com", 
        *, 
        async_: Literal[False, True] = False, 
        **request_kwargs, 
    ) -> dict | Coroutine[Any, Any, dict]:
        """接收列表

        GET https://webapi.115.com/history/receive_list

        :payload:
            - offset: int = 0
            - limit: int = 1150
        """
        api = complete_url("/history/receive_list", base_url=base_url)
        if isinstance(payload, (int, str)):
            payload = {"offset": payload}
        payload = {"limit": 1150, "offset": 0, **payload}
        return self.request(url=api, params=payload, async_=async_, **request_kwargs)

    @overload
    def fs_history_receive_list_app(
        self, 
        payload: int | str | dict = 0, 
        /, 
        app: str = "android", 
        base_url: str | Callable[[], str] = "https://proapi.115.com", 
        *, 
        async_: Literal[False] = False, 
        **request_kwargs, 
    ) -> dict:
        ...
    @overload
    def fs_history_receive_list_app(
        self, 
        payload: int | str | dict = 0, 
        /, 
        app: str = "android", 
        base_url: str | Callable[[], str] = "https://proapi.115.com", 
        *, 
        async_: Literal[True], 
        **request_kwargs, 
    ) -> Coroutine[Any, Any, dict]:
        ...
    def fs_history_receive_list_app(
        self, 
        payload: int | str | dict = 0, 
        /, 
        app: str = "android", 
        base_url: str | Callable[[], str] = "https://proapi.115.com", 
        *, 
        async_: Literal[False, True] = False, 
        **request_kwargs, 
    ) -> dict | Coroutine[Any, Any, dict]:
        """接收列表

        GET https://proapi.115.com/android/history/receive_list

        :payload:
            - offset: int = 0
            - limit: int = 1150
        """
        api = complete_url("/history/receive_list", base_url=base_url, app=app)
        if isinstance(payload, (int, str)):
            payload = {"offset": payload}
        payload = {"limit": 1150, "offset": 0, **payload}
        return self.request(url=api, params=payload, async_=async_, **request_kwargs)

    @overload
    def fs_history_set(
        self, 
        payload: str | dict, 
        /, 
        base_url: str | Callable[[], str] = "https://webapi.115.com", 
        *, 
        async_: Literal[False] = False, 
        **request_kwargs, 
    ) -> dict:
        ...
    @overload
    def fs_history_set(
        self, 
        payload: str | dict, 
        /, 
        base_url: str | Callable[[], str] = "https://webapi.115.com", 
        *, 
        async_: Literal[True], 
        **request_kwargs, 
    ) -> Coroutine[Any, Any, dict]:
        ...
    def fs_history_set(
        self, 
        payload: str | dict, 
        /, 
        base_url: str | Callable[[], str] = "https://webapi.115.com", 
        *, 
        async_: Literal[False, True] = False, 
        **request_kwargs, 
    ) -> dict | Coroutine[Any, Any, dict]:
        """更新文件的观看历史，主要用于视频

        POST https://webapi.115.com/files/history

        :payload:
            - pick_code: str     💡 文件的提取码
            - op: str = "update" 💡 操作类型，具体有哪些还需要再研究
            - category: int = 1
            - definition: int = <default> 💡 视频清晰度
            - share_id: int | str = <default>
            - time: int = <default> 💡 播放时间点（用来向服务器同步播放进度）
            - watch_end: int = <default> 💡 视频是否播放播放完毕 0:未完毕 1:完毕
            - ...（其它未找全的参数）
        """
        api = complete_url("/files/history", base_url=base_url)
        if isinstance(payload, str):
            payload = {"pick_code": payload}
        payload = {"category": 1, "op": "update", **payload}
        return self.request(url=api, method="POST", data=payload, async_=async_, **request_kwargs)

    fs_video_history_set = fs_history_set

    @overload
    def fs_history_set_app(
        self, 
        payload: str | dict, 
        /, 
        app: str = "android", 
        base_url: str | Callable[[], str] = "https://proapi.115.com", 
        *, 
        async_: Literal[False] = False, 
        **request_kwargs, 
    ) -> dict:
        ...
    @overload
    def fs_history_set_app(
        self, 
        payload: str | dict, 
        /, 
        app: str = "android", 
        base_url: str | Callable[[], str] = "https://proapi.115.com", 
        *, 
        async_: Literal[True], 
        **request_kwargs, 
    ) -> Coroutine[Any, Any, dict]:
        ...
    def fs_history_set_app(
        self, 
        payload: str | dict, 
        /, 
        app: str = "android", 
        base_url: str | Callable[[], str] = "https://proapi.115.com", 
        *, 
        async_: Literal[False, True] = False, 
        **request_kwargs, 
    ) -> dict | Coroutine[Any, Any, dict]:
        """更新文件的观看历史，主要用于视频

        POST https://proapi.115.com/android/history

        :payload:
            - pick_code: str     💡 文件的提取码
            - op: str = "update" 💡 操作类型，具体有哪些还需要再研究
            - category: int = 1
            - definition: int = <default> 💡 视频清晰度
            - share_id: int | str = <default>
            - time: int = <default> 💡 播放时间点（用来向服务器同步播放进度）
            - watch_end: int = <default> 💡 视频是否播放播放完毕 0:未完毕 1:完毕
            - ...（其它未找全的参数）
        """
        api = complete_url("/files/hiddenswitch", base_url=base_url, app=app)
        if isinstance(payload, str):
            payload = {"pick_code": payload}
        payload = {"category": 1, "op": "update", **payload}
        return self.request(url=api, method="POST", data=payload, async_=async_, **request_kwargs)

    fs_video_history_set_app = fs_history_set_app

    @overload
    def fs_image(
        self, 
        payload: str | dict, 
        /, 
        base_url: str | Callable[[], str] = "https://webapi.115.com", 
        *, 
        async_: Literal[False] = False, 
        **request_kwargs, 
    ) -> dict:
        ...
    @overload
    def fs_image(
        self, 
        payload: str | dict, 
        /, 
        base_url: str | Callable[[], str] = "https://webapi.115.com", 
        *, 
        async_: Literal[True], 
        **request_kwargs, 
    ) -> Coroutine[Any, Any, dict]:
        ...
    def fs_image(
        self, 
        payload: str | dict, 
        /, 
        base_url: str | Callable[[], str] = "https://webapi.115.com", 
        *, 
        async_: Literal[False, True] = False, 
        **request_kwargs, 
    ) -> dict | Coroutine[Any, Any, dict]:
        """获取图片的各种链接

        GET https://webapi.115.com/files/image

        :payload:
            - pickcode: str
        """
        api = complete_url("/files/image", base_url=base_url)
        if isinstance(payload, str):
            payload = {"pickcode": payload}
        return self.request(url=api, params=payload, async_=async_, **request_kwargs)

    @overload
    def fs_imagedata(
        self, 
        payload: str | dict, 
        /, 
        base_url: str | Callable[[], str] = "https://imgjump.115.com", 
        *, 
        async_: Literal[False] = False, 
        **request_kwargs, 
    ) -> dict:
        ...
    @overload
    def fs_imagedata(
        self, 
        payload: str | dict, 
        /, 
        base_url: str | Callable[[], str] = "https://imgjump.115.com", 
        *, 
        async_: Literal[True], 
        **request_kwargs, 
    ) -> Coroutine[Any, Any, dict]:
        ...
    def fs_imagedata(
        self, 
        payload: str | dict, 
        /, 
        base_url: str | Callable[[], str] = "https://imgjump.115.com", 
        *, 
        async_: Literal[False, True] = False, 
        **request_kwargs, 
    ) -> dict | Coroutine[Any, Any, dict]:
        """获取图片的分辨率等信息

        POST https://imgjump.115.com/getimgdata_url

        :payload:
            - imgurl: str 💡 图片的访问链接
        """
        api = complete_url("/getimgdata_url", base_url=base_url)
        if isinstance(payload, str):
            payload = {"imgurl": payload}
        return self.request(url=api, method="POST", data=payload, async_=async_, **request_kwargs)

    @overload
    def fs_index_info(
        self, 
        payload: Literal[0, 1] | bool | dict = 0, 
        /, 
        base_url: str | Callable[[], str] = "https://webapi.115.com", 
        *, 
        async_: Literal[False] = False, 
        **request_kwargs, 
    ) -> dict:
        ...
    @overload
    def fs_index_info(
        self, 
        payload: Literal[0, 1] | bool | dict, 
        /, 
        base_url: str | Callable[[], str] = "https://webapi.115.com", 
        *, 
        async_: Literal[True], 
        **request_kwargs, 
    ) -> Coroutine[Any, Any, dict]:
        ...
    def fs_index_info(
        self, 
        payload: Literal[0, 1] | bool | dict = 0, 
        /, 
        base_url: str | Callable[[], str] = "https://webapi.115.com", 
        *, 
        async_: Literal[False, True] = False, 
        **request_kwargs, 
    ) -> dict | Coroutine[Any, Any, dict]:
        """获取当前已用空间、可用空间、登录设备等信息

        GET https://webapi.115.com/files/index_info

        :payload:
            - count_space_nums: 0 | 1 = 0 💡 是否获取明细：0:包含各种类型文件的数量统计 1:包含登录设备列表
        """
        api = complete_url("/files/index_info", base_url=base_url)
        if not isinstance(payload, dict):
            payload = {"count_space_nums": int(payload)}
        return self.request(url=api, params=payload, async_=async_, **request_kwargs)

    @overload
    def fs_label_add(
        self, 
        payload: str | Iterable[str] | dict | list[tuple], 
        /, 
        base_url: str | Callable[[], str] = "https://webapi.115.com", 
        *, 
        async_: Literal[False] = False, 
        **request_kwargs, 
    ) -> dict:
        ...
    @overload
    def fs_label_add(
        self, 
        payload: str | Iterable[str] | dict | list[tuple], 
        /, 
        base_url: str | Callable[[], str] = "https://webapi.115.com", 
        *, 
        async_: Literal[True], 
        **request_kwargs, 
    ) -> Coroutine[Any, Any, dict]:
        ...
    def fs_label_add(
        self, 
        payload: str | Iterable[str] | dict | list[tuple], 
        /, 
        base_url: str | Callable[[], str] = "https://webapi.115.com", 
        *, 
        async_: Literal[False, True] = False, 
        **request_kwargs, 
    ) -> dict | Coroutine[Any, Any, dict]:
        """添加标签（可以接受多个）

        POST https://webapi.115.com/label/add_multi

        :payload:
            - name: str 💡 格式为 "{label_name}" 或 "{label_name}\x07{color}"，例如 "tag\x07#FF0000"（中间有个 "\\x07"）
            - name[]: str
            - ...
        """
        api = complete_url("/label/add_multi", base_url=base_url)
        if isinstance(payload, str):
            payload = [("name[]", payload)]
        elif not isinstance(payload, dict) or not isinstance(payload, list) and payload and not isinstance(payload[0], tuple):
            payload = [("name[]", label) for label in payload if label]
        return self.request(url=api, method="POST", data=payload, async_=async_, **request_kwargs)

    @overload
    def fs_label_add_app(
        self, 
        payload: str | Iterable[str] | dict | list[tuple], 
        /, 
        app: str = "android", 
        base_url: str | Callable[[], str] = "https://proapi.115.com", 
        *, 
        async_: Literal[False] = False, 
        **request_kwargs, 
    ) -> dict:
        ...
    @overload
    def fs_label_add_app(
        self, 
        payload: str | Iterable[str] | dict | list[tuple], 
        /, 
        app: str = "android", 
        base_url: str | Callable[[], str] = "https://proapi.115.com", 
        *, 
        async_: Literal[True], 
        **request_kwargs, 
    ) -> Coroutine[Any, Any, dict]:
        ...
    def fs_label_add_app(
        self, 
        payload: str | Iterable[str] | dict | list[tuple], 
        /, 
        app: str = "android", 
        base_url: str | Callable[[], str] = "https://proapi.115.com", 
        *, 
        async_: Literal[False, True] = False, 
        **request_kwargs, 
    ) -> dict | Coroutine[Any, Any, dict]:
        """添加标签（可以接受多个）

        POST https://proapi.115.com/android/label/add_multi

        :payload:
            - name: str 💡 格式为 "{label_name}" 或 "{label_name}\x07{color}"，例如 "tag\x07#FF0000"（中间有个 "\\x07"）
            - name[]: str
            - ...
        """
        api = complete_url("/label/add_multi", base_url=base_url, app=app)
        if isinstance(payload, str):
            payload = [("name[]", payload)]
        elif not isinstance(payload, dict) or not isinstance(payload, list) and payload and not isinstance(payload[0], tuple):
            payload = [("name[]", label) for label in payload if label]
        return self.request(url=api, method="POST", data=payload, async_=async_, **request_kwargs)

    @overload
    def fs_label_del(
        self, 
        payload: int | str | dict, 
        /, 
        base_url: str | Callable[[], str] = "https://webapi.115.com", 
        *, 
        async_: Literal[False] = False, 
        **request_kwargs, 
    ) -> dict:
        ...
    @overload
    def fs_label_del(
        self, 
        payload: int | str | dict, 
        /, 
        base_url: str | Callable[[], str] = "https://webapi.115.com", 
        *, 
        async_: Literal[True], 
        **request_kwargs, 
    ) -> Coroutine[Any, Any, dict]:
        ...
    def fs_label_del(
        self, 
        payload: int | str | dict, 
        /, 
        base_url: str | Callable[[], str] = "https://webapi.115.com", 
        *, 
        async_: Literal[False, True] = False, 
        **request_kwargs, 
    ) -> dict | Coroutine[Any, Any, dict]:
        """删除标签

        POST https://webapi.115.com/label/delete

        :payload:
            - id: int | str 💡 标签 id，多个用逗号 "," 隔开
        """
        api = complete_url("/label/delete", base_url=base_url)
        if isinstance(payload, (int, str)):
            payload = {"id": payload}
        return self.request(url=api, method="POST", data=payload, async_=async_, **request_kwargs)

    @overload
    def fs_label_del_app(
        self, 
        payload: int | str | dict, 
        /, 
        app: str = "android", 
        base_url: str | Callable[[], str] = "https://proapi.115.com", 
        *, 
        async_: Literal[False] = False, 
        **request_kwargs, 
    ) -> dict:
        ...
    @overload
    def fs_label_del_app(
        self, 
        payload: int | str | dict, 
        /, 
        app: str = "android", 
        base_url: str | Callable[[], str] = "https://proapi.115.com", 
        *, 
        async_: Literal[True], 
        **request_kwargs, 
    ) -> Coroutine[Any, Any, dict]:
        ...
    def fs_label_del_app(
        self, 
        payload: int | str | dict, 
        /, 
        app: str = "android", 
        base_url: str | Callable[[], str] = "https://proapi.115.com", 
        *, 
        async_: Literal[False, True] = False, 
        **request_kwargs, 
    ) -> dict | Coroutine[Any, Any, dict]:
        """删除标签

        POST https://proapi.115.com/android/label/delete

        :payload:
            - id: int | str 💡 标签 id，多个用逗号 "," 隔开
        """
        api = complete_url("/label/delete", base_url=base_url, app=app)
        if isinstance(payload, (int, str)):
            payload = {"id": payload}
        return self.request(url=api, method="POST", data=payload, async_=async_, **request_kwargs)

    @overload
    def fs_label_edit(
        self, 
        payload: dict, 
        /, 
        base_url: str | Callable[[], str] = "https://webapi.115.com", 
        *, 
        async_: Literal[False] = False, 
        **request_kwargs, 
    ) -> dict:
        ...
    @overload
    def fs_label_edit(
        self, 
        payload: dict, 
        /, 
        base_url: str | Callable[[], str] = "https://webapi.115.com", 
        *, 
        async_: Literal[True], 
        **request_kwargs, 
    ) -> Coroutine[Any, Any, dict]:
        ...
    def fs_label_edit(
        self, 
        payload: dict, 
        /, 
        base_url: str | Callable[[], str] = "https://webapi.115.com", 
        *, 
        async_: Literal[False, True] = False, 
        **request_kwargs, 
    ) -> dict | Coroutine[Any, Any, dict]:
        """编辑标签

        POST https://webapi.115.com/label/edit

        :payload:
            - id: int | str 💡 标签 id
            - name: str = <default>  💡 标签名
            - color: str = <default> 💡 标签颜色，支持 css 颜色语法
            - sort: int = <default>  💡 序号
        """
        api = complete_url("/label/edit", base_url=base_url)
        return self.request(url=api, method="POST", data=payload, async_=async_, **request_kwargs)

    @overload
    def fs_label_edit_app(
        self, 
        payload: dict, 
        /, 
        app: str = "android", 
        base_url: str | Callable[[], str] = "https://proapi.115.com", 
        *, 
        async_: Literal[False] = False, 
        **request_kwargs, 
    ) -> dict:
        ...
    @overload
    def fs_label_edit_app(
        self, 
        payload: dict, 
        /, 
        app: str = "android", 
        base_url: str | Callable[[], str] = "https://proapi.115.com", 
        *, 
        async_: Literal[True], 
        **request_kwargs, 
    ) -> Coroutine[Any, Any, dict]:
        ...
    def fs_label_edit_app(
        self, 
        payload: dict, 
        /, 
        app: str = "android", 
        base_url: str | Callable[[], str] = "https://proapi.115.com", 
        *, 
        async_: Literal[False, True] = False, 
        **request_kwargs, 
    ) -> dict | Coroutine[Any, Any, dict]:
        """编辑标签

        POST https://proapi.115.com/android/label/edit

        :payload:
            - id: int | str 💡 标签 id
            - name: str = <default>  💡 标签名
            - color: str = <default> 💡 标签颜色，支持 css 颜色语法
            - sort: int = <default>  💡 序号
        """
        api = complete_url("/label/edit", base_url=base_url, app=app)
        return self.request(url=api, method="POST", data=payload, async_=async_, **request_kwargs)

    @overload
    def fs_label_list(
        self, 
        payload: str | dict = "", 
        /, 
        base_url: str | Callable[[], str] = "https://webapi.115.com", 
        *, 
        async_: Literal[False] = False, 
        **request_kwargs, 
    ) -> dict:
        ...
    @overload
    def fs_label_list(
        self, 
        payload: str | dict = "", 
        /, 
        base_url: str | Callable[[], str] = "https://webapi.115.com", 
        *, 
        async_: Literal[True], 
        **request_kwargs, 
    ) -> Coroutine[Any, Any, dict]:
        ...
    def fs_label_list(
        self, 
        payload: str | dict = "", 
        /, 
        base_url: str | Callable[[], str] = "https://webapi.115.com", 
        *, 
        async_: Literal[False, True] = False, 
        **request_kwargs, 
    ) -> dict | Coroutine[Any, Any, dict]:
        """罗列标签列表（如果要获取做了标签的文件列表，用 `fs_search` 接口）

        GET https://webapi.115.com/label/list

        :payload:
            - offset: int = 0 💡 索引偏移，从 0 开始
            - limit: int = 11500 💡 最多返回数量
            - keyword: str = <default> 💡 搜索关键词
            - sort: "name" | "update_time" | "create_time" = <default> 💡 排序字段

                - 名称: "name"
                - 添加时间: "create_time"
                - 修改时间: "update_time"

            - order: "asc" | "desc" = <default> 💡 排序顺序："asc"(升序), "desc"(降序)
        """
        api = complete_url("/label/list", base_url=base_url)
        if isinstance(payload, str):
            payload = {"keyword": payload}
        payload = {"offset": 0, "limit": 11500, **payload}
        return self.request(url=api, params=payload, async_=async_, **request_kwargs)

    @overload
    def fs_label_list_app(
        self, 
        payload: str | dict = "", 
        /, 
        app: str = "android", 
        base_url: str | Callable[[], str] = "https://proapi.115.com", 
        *, 
        async_: Literal[False] = False, 
        **request_kwargs, 
    ) -> dict:
        ...
    @overload
    def fs_label_list_app(
        self, 
        payload: str | dict = "", 
        /, 
        app: str = "android", 
        base_url: str | Callable[[], str] = "https://proapi.115.com", 
        *, 
        async_: Literal[True], 
        **request_kwargs, 
    ) -> Coroutine[Any, Any, dict]:
        ...
    def fs_label_list_app(
        self, 
        payload: str | dict = "", 
        /, 
        app: str = "android", 
        base_url: str | Callable[[], str] = "https://proapi.115.com", 
        *, 
        async_: Literal[False, True] = False, 
        **request_kwargs, 
    ) -> dict | Coroutine[Any, Any, dict]:
        """罗列标签列表（如果要获取做了标签的文件列表，用 `fs_search` 接口）

        GET https://proapi.115.com/android/label/list

        :payload:
            - offset: int = 0 💡 索引偏移，从 0 开始
            - limit: int = 11500 💡 最多返回数量
            - keyword: str = <default> 💡 搜索关键词
            - sort: "name" | "update_time" | "create_time" = <default> 💡 排序字段

                - 名称: "name"
                - 创建时间: "create_time"
                - 更新时间: "update_time"

            - order: "asc" | "desc" = <default> 💡 排序顺序："asc"(升序), "desc"(降序)
        """
        api = complete_url("/label/list", base_url=base_url, app=app)
        if isinstance(payload, str):
            payload = {"keyword": payload}
        payload = {"offset": 0, "limit": 11500, **payload}
        return self.request(url=api, params=payload, async_=async_, **request_kwargs)

    @overload
    def fs_label_set(
        self, 
        payload: int | str | Iterable[int | str] | list[tuple] | dict, 
        /, 
        label: int | str = "", 
        base_url: str | Callable[[], str] = "https://webapi.115.com", 
        *, 
        async_: Literal[False] = False, 
        **request_kwargs, 
    ) -> dict:
        ...
    @overload
    def fs_label_set(
        self, 
        payload: int | str | Iterable[int | str] | list[tuple] | dict, 
        /, 
        label: int | str = "", 
        base_url: str | Callable[[], str] = "https://webapi.115.com", 
        *, 
        async_: Literal[True], 
        **request_kwargs, 
    ) -> Coroutine[Any, Any, dict]:
        ...
    def fs_label_set(
        self, 
        payload: int | str | Iterable[int | str] | list[tuple] | dict, 
        /, 
        label: int | str = "", 
        base_url: str | Callable[[], str] = "https://webapi.115.com", 
        *, 
        async_: Literal[False, True] = False, 
        **request_kwargs, 
    ) -> dict | Coroutine[Any, Any, dict]:
        """为文件或目录设置标签，此接口是对 `fs_edit` 的封装

        .. attention::
            这个接口会把标签列表进行替换，而不是追加

        .. hint::
            为单个文件或目录，设置一个不存在的标签 id，比如 1，会清空标签，但可产生事件（批量设置时无事件，可能是 bug）

            .. code:: python

                client.fs_label_set(id, 1)
        """
        return self._fs_edit_set(
            payload, 
            "file_label", 
            default=label, 
            base_url=base_url, 
            async_=async_, 
            **request_kwargs, 
        )

    @overload
    def fs_label_set_app(
        self, 
        payload: int | str | Iterable[int | str] | list[tuple] | dict, 
        /, 
        label: int | str = "", 
        app: str = "android", 
        base_url: str | Callable[[], str] = "https://proapi.115.com", 
        *, 
        async_: Literal[False] = False, 
        **request_kwargs, 
    ) -> dict:
        ...
    @overload
    def fs_label_set_app(
        self, 
        payload: int | str | Iterable[int | str] | list[tuple] | dict, 
        /, 
        label: int | str = "", 
        app: str = "android", 
        base_url: str | Callable[[], str] = "https://proapi.115.com", 
        *, 
        async_: Literal[True], 
        **request_kwargs, 
    ) -> Coroutine[Any, Any, dict]:
        ...
    def fs_label_set_app(
        self, 
        payload: int | str | Iterable[int | str] | list[tuple] | dict, 
        /, 
        label: int | str = "", 
        app: str = "android", 
        base_url: str | Callable[[], str] = "https://proapi.115.com", 
        *, 
        async_: Literal[False, True] = False, 
        **request_kwargs, 
    ) -> dict | Coroutine[Any, Any, dict]:
        """为文件或目录设置标签，此接口是对 `fs_files_update_app` 的封装

        .. attention::
            这个接口会把标签列表进行替换，而不是追加
        """
        return self._fs_edit_set_app(
            payload, 
            "file_label", 
            default=label, 
            app=app, 
            base_url=base_url, 
            async_=async_, 
            **request_kwargs, 
        )

    @overload
    def fs_label_batch(
        self, 
        payload: dict, 
        /, 
        base_url: str | Callable[[], str] = "https://webapi.115.com", 
        *, 
        async_: Literal[False] = False, 
        **request_kwargs, 
    ) -> dict:
        ...
    @overload
    def fs_label_batch(
        self, 
        payload: dict, 
        /, 
        base_url: str | Callable[[], str] = "https://webapi.115.com", 
        *, 
        async_: Literal[True], 
        **request_kwargs, 
    ) -> Coroutine[Any, Any, dict]:
        ...
    def fs_label_batch(
        self, 
        payload: dict, 
        /, 
        base_url: str | Callable[[], str] = "https://webapi.115.com", 
        *, 
        async_: Literal[False, True] = False, 
        **request_kwargs, 
    ) -> dict | Coroutine[Any, Any, dict]:
        """批量设置标签

        POST https://webapi.115.com/files/batch_label

        :payload:
            - action: "add" | "remove" | "reset" | "replace" 💡 操作名

                - "add": 添加
                - "remove": 移除
                - "reset": 重设
                - "replace": 替换

            - file_ids: int | str 💡 文件或目录 id，多个用逗号 "," 隔开
            - file_label: int | str = <default> 💡 标签 id，多个用逗号 "," 隔开
            - file_label[{file_label}]: int | str = <default> 💡 action 为 replace 时使用此参数，file_label[{原标签id}]: {目标标签id}，例如 file_label[123]: 456，就是把 id 是 123 的标签替换为 id 是 456 的标签
        """
        api = complete_url("/files/batch_label", base_url=base_url)
        return self.request(url=api, method="POST", data=payload, async_=async_, **request_kwargs)

    @overload
    def fs_label_batch_app(
        self, 
        payload: dict, 
        /, 
        app: str = "android", 
        base_url: str | Callable[[], str] = "https://proapi.115.com", 
        *, 
        async_: Literal[False] = False, 
        **request_kwargs, 
    ) -> dict:
        ...
    @overload
    def fs_label_batch_app(
        self, 
        payload: dict, 
        /, 
        app: str = "android", 
        base_url: str | Callable[[], str] = "https://proapi.115.com", 
        *, 
        async_: Literal[True], 
        **request_kwargs, 
    ) -> Coroutine[Any, Any, dict]:
        ...
    def fs_label_batch_app(
        self, 
        payload: dict, 
        /, 
        app: str = "android", 
        base_url: str | Callable[[], str] = "https://proapi.115.com", 
        *, 
        async_: Literal[False, True] = False, 
        **request_kwargs, 
    ) -> dict | Coroutine[Any, Any, dict]:
        """批量设置标签

        POST https://proapi.115.com/android/files/batch_label

        :payload:
            - action: "add" | "remove" | "reset" | "replace" 💡 操作名

                - "add": 添加
                - "remove": 移除
                - "reset": 重设
                - "replace": 替换

            - file_ids: int | str 💡 文件或目录 id，多个用逗号 "," 隔开
            - file_label: int | str = <default> 💡 标签 id，多个用逗号 "," 隔开
            - file_label[{file_label}]: int | str = <default> 💡 action 为 replace 时使用此参数，file_label[{原标签id}]: {目标标签id}，例如 file_label[123]: 456，就是把 id 是 123 的标签替换为 id 是 456 的标签
        """
        api = complete_url("/android/files/batch_label", base_url=base_url, app=app)
        return self.request(url=api, method="POST", data=payload, async_=async_, **request_kwargs)

    @overload
    def fs_makedirs_app(
        self, 
        payload: str | dict, 
        /, 
        pid: int | str = 0, 
        app: str = "chrome", 
        base_url: str | Callable[[], str] = "https://proapi.115.com", 
        *, 
        async_: Literal[False] = False, 
        **request_kwargs, 
    ) -> dict:
        ...
    @overload
    def fs_makedirs_app(
        self, 
        payload: str | dict, 
        /, 
        pid: int | str = 0, 
        app: str = "chrome", 
        base_url: str | Callable[[], str] = "https://proapi.115.com", 
        *, 
        async_: Literal[True], 
        **request_kwargs, 
    ) -> Coroutine[Any, Any, dict]:
        ...
    def fs_makedirs_app(
        self, 
        payload: str | dict, 
        /, 
        pid: int | str = 0, 
        app: str = "chrome", 
        base_url: str | Callable[[], str] = "https://proapi.115.com", 
        *, 
        async_: Literal[False, True] = False, 
        **request_kwargs, 
    ) -> dict | Coroutine[Any, Any, dict]:
        """新建目录（会尝试创建所有的中间节点）

        POST http://proapi.115.com/app/chrome/add_path

        .. note::
            1. 目录层级最多 25 级（不算文件节点的话）
            2. 名字不能包含 3 个字符之一 "<>，如果包含，则会被替换为 _

        .. attention::
            这个方法并不产生 115 生活的操作事件

        :payload:
            - path: str
            - parent_id: int | str = 0
        """
        if app == "chrome":
            api = complete_url("/app/chrome/add_path", base_url)
        else:
            api = complete_url("/2.0/ufile/add_path", base_url=base_url, app=app)
        if isinstance(payload, str):
            payload = {"path": payload}
        payload.setdefault("parent_id", pid)
        return self.request(url=api, method="POST", data=payload, async_=async_, **request_kwargs)

    @overload
    def fs_mkdir(
        self, 
        payload: str | dict, 
        /, 
        pid: int | str = 0, 
        base_url: str | Callable[[], str] = "https://webapi.115.com", 
        *, 
        async_: Literal[False] = False, 
        **request_kwargs, 
    ) -> dict:
        ...
    @overload
    def fs_mkdir(
        self, 
        payload: str | dict, 
        /, 
        pid: int | str = 0, 
        base_url: str | Callable[[], str] = "https://webapi.115.com", 
        *, 
        async_: Literal[True], 
        **request_kwargs, 
    ) -> Coroutine[Any, Any, dict]:
        ...
    def fs_mkdir(
        self, 
        payload: str | dict, 
        /, 
        pid: int | str = 0, 
        base_url: str | Callable[[], str] = "https://webapi.115.com", 
        *, 
        async_: Literal[False, True] = False, 
        **request_kwargs, 
    ) -> dict | Coroutine[Any, Any, dict]:
        """新建目录

        POST https://webapi.115.com/files/add

        .. note::
            1. 目录层级最多 25 级（不算文件节点的话）
            2. 名字不能包含 3 个字符之一 "<>，但是文件可以通过上传来突破此限制

        :payload:
            - cname: str
            - pid: int | str = 0
        """
        api = complete_url("/files/add", base_url=base_url)
        if isinstance(payload, str):
            payload = {"cname": payload}
        payload.setdefault("pid", pid)
        return self.request(url=api, method="POST", data=payload, async_=async_, **request_kwargs)

    @overload
    def fs_mkdir_app(
        self, 
        payload: dict | str, 
        /, 
        pid: int | str = 0, 
        app: str = "android", 
        base_url: str | Callable[[], str] = "https://proapi.115.com", 
        *, 
        async_: Literal[False] = False, 
        **request_kwargs, 
    ) -> dict:
        ...
    @overload
    def fs_mkdir_app(
        self, 
        payload: dict | str, 
        /, 
        pid: int | str = 0, 
        app: str = "android", 
        base_url: str | Callable[[], str] = "https://proapi.115.com", 
        *, 
        async_: Literal[True], 
        **request_kwargs, 
    ) -> Coroutine[Any, Any, dict]:
        ...
    def fs_mkdir_app(
        self, 
        payload: dict | str, 
        /, 
        pid: int | str = 0, 
        app: str = "android", 
        base_url: str | Callable[[], str] = "https://proapi.115.com", 
        *, 
        async_: Literal[False, True] = False, 
        **request_kwargs, 
    ) -> dict | Coroutine[Any, Any, dict]:
        """新建目录，此接口是对 `fs_folder_update_app` 的封装

        :payload:
            - name: str    💡 名字
            - pid: int | str = 0 💡 上级目录的 id
        """
        if isinstance(payload, str):
            payload = {"name": payload}
        payload.setdefault("pid", pid)
        return self.fs_folder_update_app(
            payload, 
            app=app, 
            base_url=base_url, 
            async_=async_, 
            **request_kwargs, 
        )

    @overload
    def fs_move(
        self, 
        payload: int | str | dict | Iterable[int | str], 
        /, 
        pid: int | str = 0, 
        base_url: str | Callable[[], str] = "https://webapi.115.com", 
        *, 
        async_: Literal[False] = False, 
        **request_kwargs, 
    ) -> dict:
        ...
    @overload
    def fs_move(
        self, 
        payload: int | str | dict | Iterable[int | str], 
        /, 
        pid: int | str = 0, 
        base_url: str | Callable[[], str] = "https://webapi.115.com", 
        *, 
        async_: Literal[True], 
        **request_kwargs, 
    ) -> Coroutine[Any, Any, dict]:
        ...
    def fs_move(
        self, 
        payload: int | str | dict | Iterable[int | str], 
        /, 
        pid: int | str = 0, 
        base_url: str | Callable[[], str] = "https://webapi.115.com", 
        *, 
        async_: Literal[False, True] = False, 
        **request_kwargs, 
    ) -> dict | Coroutine[Any, Any, dict]:
        """移动文件或目录

        POST https://webapi.115.com/files/move

        .. caution::
            ⚠️ 请不要并发执行，限制在 5 万个文件和目录以内

        .. caution::
            你可以把文件或目录移动到其它目录 id 下，即使是不存在的 id

            因此，我定义了一个概念，悬空节点，此节点的 aid=1，但它有一个祖先节点，要么不存在，要么 aid != 1

            你可以用 ``P115Client.tool_space()`` 方法，使用【校验空间】功能，把所有悬空节点找出来，放到根目录下的【修复文件】目录，此接口一天只能用一次

        :payload:
            - fid: int | str 💡 文件或目录 id，只接受单个 id
            - fid[]: int | str
            - ...
            - fid[0]: int | str
            - fid[1]: int | str
            - ...
            - pid: int | str = 0 💡 目标目录 id
            - move_proid: str = <default> 💡 任务 id
        """
        api = complete_url("/files/move", base_url=base_url)
        if isinstance(payload, (int, str)):
            payload = {"fid": payload}
        elif not isinstance(payload, dict):
            payload = {f"fid[{i}]": fid for i, fid in enumerate(payload)}
        payload.setdefault("pid", pid)
        return self.request(url=api, method="POST", data=payload, async_=async_, **request_kwargs)

    @overload
    def fs_move_app(
        self, 
        payload: int | str | dict | Iterable[int | str], 
        /, 
        pid: int | str = 0, 
        app: str = "android", 
        base_url: str | Callable[[], str] = "https://proapi.115.com", 
        *, 
        async_: Literal[False] = False, 
        **request_kwargs, 
    ) -> dict:
        ...
    @overload
    def fs_move_app(
        self, 
        payload: int | str | dict | Iterable[int | str], 
        /, 
        pid: int | str = 0, 
        app: str = "android", 
        base_url: str | Callable[[], str] = "https://proapi.115.com", 
        *, 
        async_: Literal[True], 
        **request_kwargs, 
    ) -> Coroutine[Any, Any, dict]:
        ...
    def fs_move_app(
        self, 
        payload: int | str | dict | Iterable[int | str], 
        /, 
        pid: int | str = 0, 
        app: str = "android", 
        base_url: str | Callable[[], str] = "https://proapi.115.com", 
        *, 
        async_: Literal[False, True] = False, 
        **request_kwargs, 
    ) -> dict | Coroutine[Any, Any, dict]:
        """移动文件或目录

        POST https://proapi.115.com/android/files/move

        .. caution::
            ⚠️ 请不要并发执行，限制在 5 万个文件和目录以内

        :payload:
            - ids: int | str    💡 文件或目录 id，多个用逗号 "," 隔开
            - to_cid: int | str 💡 目标目录 id
            - user_id: int | str = <default> 💡 用户 id
        """
        api = complete_url("/files/move", base_url=base_url, app=app)
        if isinstance(payload, (int, str)):
            payload = {"ids": payload}
        elif not isinstance(payload, dict):
            payload = {"ids": ",".join(map(str, payload))}
        payload = {"to_cid": pid, "user_id": self.user_id, **payload}
        return self.request(url=api, method="POST", data=payload, async_=async_, **request_kwargs)

    @overload
    def fs_move_progress(
        self, 
        payload: int | str | dict, 
        /, 
        base_url: str | Callable[[], str] = "https://webapi.115.com", 
        *, 
        async_: Literal[False] = False, 
        **request_kwargs, 
    ) -> dict:
        ...
    @overload
    def fs_move_progress(
        self, 
        payload: int | str | dict, 
        /, 
        base_url: str | Callable[[], str] = "https://webapi.115.com", 
        *, 
        async_: Literal[True], 
        **request_kwargs, 
    ) -> Coroutine[Any, Any, dict]:
        ...
    def fs_move_progress(
        self, 
        payload: int | str | dict, 
        /, 
        base_url: str | Callable[[], str] = "https://webapi.115.com", 
        *, 
        async_: Literal[False, True] = False, 
        **request_kwargs, 
    ) -> dict | Coroutine[Any, Any, dict]:
        """移动任务的进度

        GET https://webapi.115.com/files/move_progress

        :payload:
            - move_proid: str = <default> 💡 任务 id
        """
        api = complete_url("/files/move_progress", base_url=base_url)
        if isinstance(payload, (int, str)):
            payload = {"move_proid": payload}
        return self.request(url=api, params=payload, async_=async_, **request_kwargs)

    @overload
    def fs_music(
        self, 
        payload: str | dict, 
        /, 
        base_url: str | Callable[[], str] = "https://webapi.115.com", 
        *, 
        async_: Literal[False] = False, 
        **request_kwargs, 
    ) -> dict:
        ...
    @overload
    def fs_music(
        self, 
        payload: str | dict, 
        /, 
        base_url: str | Callable[[], str] = "https://webapi.115.com", 
        *, 
        async_: Literal[True], 
        **request_kwargs, 
    ) -> Coroutine[Any, Any, dict]:
        ...
    def fs_music(
        self, 
        payload: str | dict, 
        /, 
        base_url: str | Callable[[], str] = "https://webapi.115.com", 
        *, 
        async_: Literal[False, True] = False, 
        **request_kwargs, 
    ) -> dict | Coroutine[Any, Any, dict]:
        """获取音乐信息（其实只有一个下载链接）

        GET https://webapi.115.com/files/music

        :payload:
            - pickcode: str 💡 提取码
            - topic_id: int = <default>
            - music_id: int = <default>
            - download: int = <default>
        """
        api = complete_url("/files/music", base_url=base_url)
        if isinstance(payload, str):
            payload = {"pickcode": payload}
        request_kwargs.setdefault("follow_redirects", False)
        return self.request(url=api, params=payload, async_=async_, **request_kwargs)

    @overload
    def fs_music_app(
        self, 
        payload: str | dict, 
        /, 
        app: str = "android", 
        base_url: str | Callable[[], str] = "https://proapi.115.com", 
        *, 
        async_: Literal[False] = False, 
        **request_kwargs, 
    ) -> dict:
        ...
    @overload
    def fs_music_app(
        self, 
        payload: str | dict, 
        /, 
        app: str = "android", 
        base_url: str | Callable[[], str] = "https://proapi.115.com", 
        *, 
        async_: Literal[True], 
        **request_kwargs, 
    ) -> Coroutine[Any, Any, dict]:
        ...
    def fs_music_app(
        self, 
        payload: str | dict, 
        /, 
        app: str = "android", 
        base_url: str | Callable[[], str] = "https://proapi.115.com", 
        *, 
        async_: Literal[False, True] = False, 
        **request_kwargs, 
    ) -> dict | Coroutine[Any, Any, dict]:
        """获取音乐信息

        GET https://proapi.115.com/android/music/musicplay

        .. note::
            即使文件格式不正确或者过大（超过 200 MB），也可返回一些信息（包括 parent_id），但如果是目录则信息匮乏（但由此也可判定一个目录）

        :payload:
            - pickcode: str 💡 提取码
            - music_id: int = <default>
            - topic_id: int = <default>
        """
        api = complete_url("/music/musicplay", base_url=base_url, app=app)
        if isinstance(payload, str):
            payload = {"pickcode": payload}
        return self.request(url=api, params=payload, async_=async_, **request_kwargs)

    @overload
    def fs_music_file_exist(
        self, 
        payload: str | dict, 
        /, 
        base_url: str | Callable[[], str] = "https://webapi.115.com", 
        *, 
        async_: Literal[False] = False, 
        **request_kwargs, 
    ) -> dict:
        ...
    @overload
    def fs_music_file_exist(
        self, 
        payload: str | dict, 
        /, 
        base_url: str | Callable[[], str] = "https://webapi.115.com", 
        *, 
        async_: Literal[True], 
        **request_kwargs, 
    ) -> Coroutine[Any, Any, dict]:
        ...
    def fs_music_file_exist(
        self, 
        payload: str | dict, 
        /, 
        base_url: str | Callable[[], str] = "https://webapi.115.com", 
        *, 
        async_: Literal[False, True] = False, 
        **request_kwargs, 
    ) -> dict | Coroutine[Any, Any, dict]:
        """检查音乐文件是否存在

        GET https://webapi.115.com/files/music_file_exist

        :payload:
            - pickcode: str 💡 提取码
            - topic_id: int = <default>
            - music_id: int = <default>
            - download: int = <default>
        """
        api = complete_url("/files/music_file_exist", base_url=base_url)
        if isinstance(payload, str):
            payload = {"pickcode": payload}
        return self.request(url=api, params=payload, async_=async_, **request_kwargs)

    @overload
    def fs_music_fond_list(
        self, 
        /, 
        base_url: str | Callable[[], str] = "https://webapi.115.com", 
        *, 
        async_: Literal[False] = False, 
        **request_kwargs, 
    ) -> dict:
        ...
    @overload
    def fs_music_fond_list(
        self, 
        /, 
        base_url: str | Callable[[], str] = "https://webapi.115.com", 
        *, 
        async_: Literal[True], 
        **request_kwargs, 
    ) -> Coroutine[Any, Any, dict]:
        ...
    def fs_music_fond_list(
        self, 
        /, 
        base_url: str | Callable[[], str] = "https://webapi.115.com", 
        *, 
        async_: Literal[False, True] = False, 
        **request_kwargs, 
    ) -> dict | Coroutine[Any, Any, dict]:
        """罗列星标听单

        GET https://webapi.115.com/files/music_fond_list
        """
        api = complete_url("/files/music_fond_list", base_url=base_url)
        return self.request(url=api, async_=async_, **request_kwargs)

    @overload
    def fs_music_fond_list_app(
        self, 
        /, 
        app: str = "android", 
        base_url: str | Callable[[], str] = "https://proapi.115.com", 
        *, 
        async_: Literal[False] = False, 
        **request_kwargs, 
    ) -> dict:
        ...
    @overload
    def fs_music_fond_list_app(
        self, 
        /, 
        app: str = "android", 
        base_url: str | Callable[[], str] = "https://proapi.115.com", 
        *, 
        async_: Literal[True], 
        **request_kwargs, 
    ) -> Coroutine[Any, Any, dict]:
        ...
    def fs_music_fond_list_app(
        self, 
        /, 
        app: str = "android", 
        base_url: str | Callable[[], str] = "https://proapi.115.com", 
        *, 
        async_: Literal[False, True] = False, 
        **request_kwargs, 
    ) -> dict | Coroutine[Any, Any, dict]:
        """罗列星标听单

        GET https://proapi.115.com/android/music/music_fond_list
        """
        api = complete_url("/music/music_fond_list", base_url=base_url, app=app)
        return self.request(url=api, async_=async_, **request_kwargs)

    @overload
    def fs_music_fond_set(
        self, 
        payload: int | dict, 
        /, 
        base_url: str | Callable[[], str] = "https://webapi.115.com", 
        *, 
        async_: Literal[False] = False, 
        **request_kwargs, 
    ) -> dict:
        ...
    @overload
    def fs_music_fond_set(
        self, 
        payload: int | dict, 
        /, 
        base_url: str | Callable[[], str] = "https://webapi.115.com", 
        *, 
        async_: Literal[True], 
        **request_kwargs, 
    ) -> Coroutine[Any, Any, dict]:
        ...
    def fs_music_fond_set(
        self, 
        payload: int | dict, 
        /, 
        base_url: str | Callable[[], str] = "https://webapi.115.com", 
        *, 
        async_: Literal[False, True] = False, 
        **request_kwargs, 
    ) -> dict | Coroutine[Any, Any, dict]:
        """给听单加减星标

        POST https://webapi.115.com/files/music_topic_fond

        :payload:
            - topic_id: int
            - fond: 0 | 1 = 1
        """
        api = complete_url("/files/music_topic_fond", base_url=base_url)
        if isinstance(payload, int):
            payload = {"topic_id": payload}
        payload.setdefault("fond", 1)
        return self.request(url=api, method="POST", data=payload, async_=async_, **request_kwargs)

    @overload
    def fs_music_include_list(
        self, 
        payload: int | dict = 0, 
        /, 
        base_url: str | Callable[[], str] = "https://webapi.115.com", 
        *, 
        async_: Literal[False] = False, 
        **request_kwargs, 
    ) -> dict:
        ...
    @overload
    def fs_music_include_list(
        self, 
        payload: int | dict = 0, 
        /, 
        base_url: str | Callable[[], str] = "https://webapi.115.com", 
        *, 
        async_: Literal[True], 
        **request_kwargs, 
    ) -> Coroutine[Any, Any, dict]:
        ...
    def fs_music_include_list(
        self, 
        payload: int | dict = 0, 
        /, 
        base_url: str | Callable[[], str] = "https://webapi.115.com", 
        *, 
        async_: Literal[False, True] = False, 
        **request_kwargs, 
    ) -> dict | Coroutine[Any, Any, dict]:
        """包含音乐的目录列表（专属文件）

        GET https://webapi.115.com/files/include_music_list

        :payload:
            - asc: 0 | 1 = 0
            - limit: int = 1150
            - offset: int = 0
            - order: str = "user_etime"
        """
        api = complete_url("/files/include_music_list", base_url=base_url)
        if isinstance(payload, int):
            payload = {"offset": payload}
        payload = {"asc": 0, "limit": 1150, "order": "user_etime", **payload}
        return self.request(url=api, params=payload, async_=async_, **request_kwargs)

    @overload
    def fs_music_include_list_app(
        self, 
        payload: int | dict = 0, 
        /, 
        app: str = "android", 
        base_url: str | Callable[[], str] = "https://proapi.115.com", 
        *, 
        async_: Literal[False] = False, 
        **request_kwargs, 
    ) -> dict:
        ...
    @overload
    def fs_music_include_list_app(
        self, 
        payload: int | dict = 0, 
        /, 
        app: str = "android", 
        base_url: str | Callable[[], str] = "https://proapi.115.com", 
        *, 
        async_: Literal[True], 
        **request_kwargs, 
    ) -> Coroutine[Any, Any, dict]:
        ...
    def fs_music_include_list_app(
        self, 
        payload: int | dict = 0, 
        /, 
        app: str = "android", 
        base_url: str | Callable[[], str] = "https://proapi.115.com", 
        *, 
        async_: Literal[False, True] = False, 
        **request_kwargs, 
    ) -> dict | Coroutine[Any, Any, dict]:
        """包含音乐的目录列表（专属文件）

        GET https://proapi.115.com/android/music/include_music_list

        :payload:
            - asc: 0 | 1 = 0
            - limit: int = 1150
            - offset: int = 0
            - order: str = "user_etime"
        """
        api = complete_url("/music/include_music_list", base_url=base_url, app=app)
        if isinstance(payload, int):
            payload = {"offset": payload}
        payload = {"asc": 0, "limit": 1150, "order": "user_etime", **payload}
        return self.request(url=api, params=payload, async_=async_, **request_kwargs)

    @overload
    def fs_music_info(
        self, 
        payload: str | dict, 
        /, 
        base_url: str | Callable[[], str] = "https://webapi.115.com", 
        *, 
        async_: Literal[False] = False, 
        **request_kwargs, 
    ) -> dict:
        ...
    @overload
    def fs_music_info(
        self, 
        payload: str | dict, 
        /, 
        base_url: str | Callable[[], str] = "https://webapi.115.com", 
        *, 
        async_: Literal[True], 
        **request_kwargs, 
    ) -> Coroutine[Any, Any, dict]:
        ...
    def fs_music_info(
        self, 
        payload: str | dict, 
        /, 
        base_url: str | Callable[[], str] = "https://webapi.115.com", 
        *, 
        async_: Literal[False, True] = False, 
        **request_kwargs, 
    ) -> dict | Coroutine[Any, Any, dict]:
        """获取音乐封面等信息

        GET https://webapi.115.com/files/music_info

        :payload:
            - pickcode: str 💡 提取码
        """
        api = complete_url("/files/music_info", base_url=base_url)
        if isinstance(payload, str):
            payload = {"pickcode": payload}
        return self.request(url=api, params=payload, async_=async_, **request_kwargs)

    @overload
    def fs_music_info_app(
        self, 
        payload: str | dict, 
        /, 
        app: str = "android", 
        base_url: str | Callable[[], str] = "https://proapi.115.com", 
        *, 
        async_: Literal[False] = False, 
        **request_kwargs, 
    ) -> dict:
        ...
    @overload
    def fs_music_info_app(
        self, 
        payload: str | dict, 
        /, 
        app: str = "android", 
        base_url: str | Callable[[], str] = "https://proapi.115.com", 
        *, 
        async_: Literal[True], 
        **request_kwargs, 
    ) -> Coroutine[Any, Any, dict]:
        ...
    def fs_music_info_app(
        self, 
        payload: str | dict, 
        /, 
        app: str = "android", 
        base_url: str | Callable[[], str] = "https://proapi.115.com", 
        *, 
        async_: Literal[False, True] = False, 
        **request_kwargs, 
    ) -> dict | Coroutine[Any, Any, dict]:
        """获取音乐封面等信息

        GET https://proapi.115.com/android/music/musicdetail

        :payload:
            - pickcode: str 💡 提取码
        """
        api = complete_url("/music/musicdetail", base_url=base_url, app=app)
        if isinstance(payload, str):
            payload = {"pickcode": payload}
        return self.request(url=api, params=payload, async_=async_, **request_kwargs)

    @overload
    def fs_music_list(
        self, 
        payload: int | dict = 1, 
        /, 
        base_url: str | Callable[[], str] = "https://webapi.115.com", 
        *, 
        async_: Literal[False] = False, 
        **request_kwargs, 
    ) -> dict:
        ...
    @overload
    def fs_music_list(
        self, 
        payload: int | dict = 1, 
        /, 
        base_url: str | Callable[[], str] = "https://webapi.115.com", 
        *, 
        async_: Literal[True], 
        **request_kwargs, 
    ) -> Coroutine[Any, Any, dict]:
        ...
    def fs_music_list(
        self, 
        payload: int | dict = 1, 
        /, 
        base_url: str | Callable[[], str] = "https://webapi.115.com", 
        *, 
        async_: Literal[False, True] = False, 
        **request_kwargs, 
    ) -> dict | Coroutine[Any, Any, dict]:
        """罗列听单中的文件

        GET https://webapi.115.com/files/music_list

        :payload:
            - topic_id: int = 1 💡 听单 id。-1:星标 1:最近听过 2:最近接收 678469:临时听单(?)
            - start: int = 0
            - limit: int = 1150
        """
        api = complete_url("/files/music_list", base_url=base_url)
        if isinstance(payload, int):
            payload = {"topic_id": payload}
        payload = {"start": 0, "limit": 1150, "topic_id": 1, **payload}
        return self.request(url=api, params=payload, async_=async_, **request_kwargs)

    @overload
    def fs_music_list_app(
        self, 
        payload: int | dict = 1, 
        /, 
        app: str = "android", 
        base_url: str | Callable[[], str] = "https://proapi.115.com", 
        *, 
        async_: Literal[False] = False, 
        **request_kwargs, 
    ) -> dict:
        ...
    @overload
    def fs_music_list_app(
        self, 
        payload: int | dict = 1, 
        /, 
        app: str = "android", 
        base_url: str | Callable[[], str] = "https://proapi.115.com", 
        *, 
        async_: Literal[True], 
        **request_kwargs, 
    ) -> Coroutine[Any, Any, dict]:
        ...
    def fs_music_list_app(
        self, 
        payload: int | dict = 1, 
        /, 
        app: str = "android", 
        base_url: str | Callable[[], str] = "https://proapi.115.com", 
        *, 
        async_: Literal[False, True] = False, 
        **request_kwargs, 
    ) -> dict | Coroutine[Any, Any, dict]:
        """罗列听单中的文件

        GET https://proapi.115.com/android/music/music_list

        :payload:
            - topic_id: int = 1 💡 听单 id。-1:星标 1:最近听过 2:最近接收 678469:临时听单(?)
            - start: int = 0
            - limit: int = 1150
        """
        api = complete_url("/music/music_list", base_url=base_url, app=app)
        if isinstance(payload, int):
            payload = {"topic_id": payload}
        payload = {"start": 0, "limit": 1150, "topic_id": 1, **payload}
        return self.request(url=api, params=payload, async_=async_, **request_kwargs)

    @overload
    def fs_music_new(
        self, 
        payload: int | dict = 1, 
        /, 
        base_url: str | Callable[[], str] = "https://webapi.115.com", 
        *, 
        async_: Literal[False] = False, 
        **request_kwargs, 
    ) -> dict:
        ...
    @overload
    def fs_music_new(
        self, 
        payload: int | dict = 1, 
        /, 
        base_url: str | Callable[[], str] = "https://webapi.115.com", 
        *, 
        async_: Literal[True], 
        **request_kwargs, 
    ) -> Coroutine[Any, Any, dict]:
        ...
    def fs_music_new(
        self, 
        payload: int | dict = 1, 
        /, 
        base_url: str | Callable[[], str] = "https://webapi.115.com", 
        *, 
        async_: Literal[False, True] = False, 
        **request_kwargs, 
    ) -> dict | Coroutine[Any, Any, dict]:
        """罗列听单或听单中的文件

        GET https://webapi.115.com/files/musicnew

        :payload:
            - topic_id: int = 1 💡 听单 id。-1:星标 1:最近听过 2:最近接收 678469:临时听单(?)
            - type: 0 | 1 = 0   💡 类型：0:文件 1:目录
            - start: int = 0
            - limit: int = 1150
        """
        api = complete_url("/files/musicnew", base_url=base_url)
        if isinstance(payload, int):
            payload = {"topic_id": payload}
        payload = {"start": 0, "limit": 1150, "type": 0, "topic_id": 1, **payload}
        return self.request(url=api, params=payload, async_=async_, **request_kwargs)

    @overload
    def fs_music_new_app(
        self, 
        payload: int | dict = 1, 
        /, 
        app: str = "android", 
        base_url: str | Callable[[], str] = "https://proapi.115.com", 
        *, 
        async_: Literal[False] = False, 
        **request_kwargs, 
    ) -> dict:
        ...
    @overload
    def fs_music_new_app(
        self, 
        payload: int | dict = 1, 
        /, 
        app: str = "android", 
        base_url: str | Callable[[], str] = "https://proapi.115.com", 
        *, 
        async_: Literal[True], 
        **request_kwargs, 
    ) -> Coroutine[Any, Any, dict]:
        ...
    def fs_music_new_app(
        self, 
        payload: int | dict = 1, 
        /, 
        app: str = "android", 
        base_url: str | Callable[[], str] = "https://proapi.115.com", 
        *, 
        async_: Literal[False, True] = False, 
        **request_kwargs, 
    ) -> dict | Coroutine[Any, Any, dict]:
        """罗列听单或听单中的文件

        GET https://proapi.115.com/android/music/musicnew

        :payload:
            - topic_id: int = 1 💡 听单 id。-1:星标 1:最近听过 2:最近接收 678469:临时听单(?)
            - type: 0 | 1 = 0   💡 类型：0:文件 1:目录
        """
        api = complete_url("/music/musicnew", base_url=base_url, app=app)
        if isinstance(payload, int):
            payload = {"topic_id": payload}
        payload = {"type": 0, "topic_id": 1, **payload}
        return self.request(url=api, params=payload, async_=async_, **request_kwargs)

    @overload
    def fs_music_set(
        self, 
        payload: int | dict, 
        /, 
        base_url: str | Callable[[], str] = "https://webapi.115.com", 
        *, 
        async_: Literal[False] = False, 
        **request_kwargs, 
    ) -> dict:
        ...
    @overload
    def fs_music_set(
        self, 
        payload: int | dict, 
        /, 
        base_url: str | Callable[[], str] = "https://webapi.115.com", 
        *, 
        async_: Literal[True], 
        **request_kwargs, 
    ) -> Coroutine[Any, Any, dict]:
        ...
    def fs_music_set(
        self, 
        payload: int | dict, 
        /, 
        base_url: str | Callable[[], str] = "https://webapi.115.com", 
        *, 
        async_: Literal[False, True] = False, 
        **request_kwargs, 
    ) -> dict | Coroutine[Any, Any, dict]:
        """从听单添加或移除音乐，或者给音乐加减星标

        POST https://webapi.115.com/files/music

        :payload:
            - file_id: int      💡 文件 id，多个用逗号 "," 隔开（op 为 "add" 和 "delete" 时需要）
            - music_id: int = 1 💡 音乐 id（op 为 "fond" 时需要）
            - topic_id: int = 1 💡 听单 id
            - op: str = "add"   💡 操作类型："add": 添加到听单, "delete": 从听单删除, "fond": 设置星标
            - fond: 0 | 1 = 1   💡 是否星标（op 为 "fond" 时需要），这个星标和 music_id 有关，和 file_id 无关
        """
        api = complete_url("/files/music", base_url=base_url)
        if isinstance(payload, int):
            payload = {"file_id": payload}
        payload = {"op": "add", "fond": 1, "music_id": 1, "topic_id": 1, **payload}
        return self.request(url=api, method="POST", data=payload, async_=async_, **request_kwargs)

    @overload
    def fs_music_status(
        self, 
        payload: str | dict, 
        /, 
        base_url: str | Callable[[], str] = "https://webapi.115.com", 
        *, 
        async_: Literal[False] = False, 
        **request_kwargs, 
    ) -> dict:
        ...
    @overload
    def fs_music_status(
        self, 
        payload: str | dict, 
        /, 
        base_url: str | Callable[[], str] = "https://webapi.115.com", 
        *, 
        async_: Literal[True], 
        **request_kwargs, 
    ) -> Coroutine[Any, Any, dict]:
        ...
    def fs_music_status(
        self, 
        payload: str | dict, 
        /, 
        base_url: str | Callable[[], str] = "https://webapi.115.com", 
        *, 
        async_: Literal[False, True] = False, 
        **request_kwargs, 
    ) -> dict | Coroutine[Any, Any, dict]:
        """音乐状态

        GET https://webapi.115.com/files/music_status

        :payload:
            - pickcode: str 💡 提取码
        """
        api = complete_url("/files/music_status", base_url=base_url)
        if isinstance(payload, str):
            payload = {"pickcode": payload}
        return self.request(url=api, params=payload, async_=async_, **request_kwargs)

    @overload
    def fs_music_topic_listnew(
        self, 
        payload: int | dict = 0, 
        /, 
        base_url: str | Callable[[], str] = "https://webapi.115.com", 
        *, 
        async_: Literal[False] = False, 
        **request_kwargs, 
    ) -> dict:
        ...
    @overload
    def fs_music_topic_listnew(
        self, 
        payload: int | dict = 0, 
        /, 
        base_url: str | Callable[[], str] = "https://webapi.115.com", 
        *, 
        async_: Literal[True], 
        **request_kwargs, 
    ) -> Coroutine[Any, Any, dict]:
        ...
    def fs_music_topic_listnew(
        self, 
        payload: int | dict = 0, 
        /, 
        base_url: str | Callable[[], str] = "https://webapi.115.com", 
        *, 
        async_: Literal[False, True] = False, 
        **request_kwargs, 
    ) -> dict | Coroutine[Any, Any, dict]:
        """罗列听单

        GET https://webapi.115.com/files/music_topic_listnew

        .. caution::
            似乎查询参数并没有效果

        :payload:
            - fond: 0 | 1 = 0   💡 是否星标
            - start: int = 0    💡 开始索引
            - limit: int = 1150 💡 最多返回数量
            - hidden: 0 | 1 = 0
        """
        api = complete_url("/files/music_topic_listnew", base_url=base_url)
        if isinstance(payload, int):
            payload = {"start": payload}
        payload = {"fond": 0, "hidden": 0, "limit": 1150, "start": 0, **payload}
        return self.request(url=api, params=payload, async_=async_, **request_kwargs)

    @overload
    def fs_music_topic_listnew_app(
        self, 
        payload: int | dict = 0, 
        /, 
        app: str = "android", 
        base_url: str | Callable[[], str] = "https://proapi.115.com", 
        *, 
        async_: Literal[False] = False, 
        **request_kwargs, 
    ) -> dict:
        ...
    @overload
    def fs_music_topic_listnew_app(
        self, 
        payload: int | dict = 0, 
        /, 
        app: str = "android", 
        base_url: str | Callable[[], str] = "https://proapi.115.com", 
        *, 
        async_: Literal[True], 
        **request_kwargs, 
    ) -> Coroutine[Any, Any, dict]:
        ...
    def fs_music_topic_listnew_app(
        self, 
        payload: int | dict = 0, 
        /, 
        app: str = "android", 
        base_url: str | Callable[[], str] = "https://proapi.115.com", 
        *, 
        async_: Literal[False, True] = False, 
        **request_kwargs, 
    ) -> dict | Coroutine[Any, Any, dict]:
        """罗列听单

        GET https://proapi.115.com/android/music/musiclistnew

        .. caution::
            似乎查询参数并没有效果

        :payload:
            - fond: 0 | 1 = 0   💡 是否星标
            - start: int = 0    💡 开始索引
            - limit: int = 1150 💡 最多返回数量
        """
        api = complete_url("/music/musiclistnew", base_url=base_url, app=app)
        if isinstance(payload, int):
            payload = {"start": payload}
        payload = {"fond": 0, "limit": 1150, "start": 0, **payload}
        return self.request(url=api, params=payload, async_=async_, **request_kwargs)

    @overload
    def fs_music_topic_set(
        self, 
        payload: str | dict, 
        /, 
        base_url: str | Callable[[], str] = "https://webapi.115.com", 
        *, 
        async_: Literal[False] = False, 
        **request_kwargs, 
    ) -> dict:
        ...
    @overload
    def fs_music_topic_set(
        self, 
        payload: str | dict, 
        /, 
        base_url: str | Callable[[], str] = "https://webapi.115.com", 
        *, 
        async_: Literal[True], 
        **request_kwargs, 
    ) -> Coroutine[Any, Any, dict]:
        ...
    def fs_music_topic_set(
        self, 
        payload: str | dict, 
        /, 
        base_url: str | Callable[[], str] = "https://webapi.115.com", 
        *, 
        async_: Literal[False, True] = False, 
        **request_kwargs, 
    ) -> dict | Coroutine[Any, Any, dict]:
        """修改听单

        POST https://webapi.115.com/files/music_topic

        :payload:
            - op: "edit" | "delete" | "add" 💡 操作类型："edit":改名 "delete":删除 "add":添加
            - topic_id: int = <default> 💡 听单 id（op 不为 "add" 时需要）
            - topic_name: str = <default> 💡 听单名字（op 为 "add" 和 "edit" 时需要）
        """
        api = complete_url("/files/music_topic", base_url=base_url)
        if isinstance(payload, str):
            payload = {"op": "add", "topic_name": payload}
        return self.request(url=api, method="POST", data=payload, async_=async_, **request_kwargs)

    @overload
    def fs_order_set(
        self, 
        payload: str | dict, 
        /, 
        base_url: str | Callable[[], str] = "https://webapi.115.com", 
        *, 
        async_: Literal[False] = False, 
        **request_kwargs, 
    ) -> dict:
        ...
    @overload
    def fs_order_set(
        self, 
        payload: str | dict, 
        /, 
        base_url: str | Callable[[], str] = "https://webapi.115.com", 
        *, 
        async_: Literal[True], 
        **request_kwargs, 
    ) -> Coroutine[Any, Any, dict]:
        ...
    def fs_order_set(
        self, 
        payload: str | dict, 
        /, 
        base_url: str | Callable[[], str] = "https://webapi.115.com", 
        *, 
        async_: Literal[False, True] = False, 
        **request_kwargs, 
    ) -> dict | Coroutine[Any, Any, dict]:
        """设置某个目录内文件的默认排序

        POST https://webapi.115.com/files/order

        :payload:
            - user_order: str 💡 用某字段排序

                - "file_name": 文件名
                - "file_size": 文件大小
                - "file_type": 文件种类
                - "user_utime": 修改时间
                - "user_ptime": 创建时间
                - "user_otime": 上一次打开时间

            - file_id: int | str = 0 💡 目录 id，对应 parent_id
            - user_asc: 0 | 1 = <default> 💡 是否升序排列
            - fc_mix: 0 | 1 = <default> 💡 是否目录和文件混合，如果为 0 则目录在前（目录置顶）
            - module: str = <default> 💡 "label_search" 表示用于搜索的排序
        """
        api = complete_url("/files/order", base_url=base_url)
        if isinstance(payload, str):
            payload = {"user_order": payload}
        payload = {"file_id": 0, "user_asc": 1, "user_order": "user_ptime", **payload}
        return self.request(url=api, method="POST", data=payload, async_=async_, **request_kwargs)

    @overload
    def fs_order_set_app(
        self, 
        payload: str | dict, 
        /, 
        app: str = "android", 
        base_url: str | Callable[[], str] = "https://proapi.115.com", 
        *, 
        async_: Literal[False] = False, 
        **request_kwargs, 
    ) -> dict:
        ...
    @overload
    def fs_order_set_app(
        self, 
        payload: str | dict, 
        /, 
        app: str = "android", 
        base_url: str | Callable[[], str] = "https://proapi.115.com", 
        *, 
        async_: Literal[True], 
        **request_kwargs, 
    ) -> Coroutine[Any, Any, dict]:
        ...
    def fs_order_set_app(
        self, 
        payload: str | dict, 
        /, 
        app: str = "android", 
        base_url: str | Callable[[], str] = "https://proapi.115.com", 
        *, 
        async_: Literal[False, True] = False, 
        **request_kwargs, 
    ) -> dict | Coroutine[Any, Any, dict]:
        """设置某个目录内文件的默认排序

        POST https://proapi.115.com/android/2.0/ufile/order

        .. error::
            这个接口暂时并不能正常工作，应该是参数构造有问题，暂时请用 ``P115Client.fs_order_set()``

        :payload:
            - user_order: str 💡 用某字段排序

                - "file_name": 文件名
                - "file_size": 文件大小
                - "file_type": 文件种类
                - "user_utime": 修改时间
                - "user_ptime": 创建时间
                - "user_otime": 上一次打开时间

            - file_id: int | str = 0 💡 目录 id，对应 parent_id
            - user_asc: 0 | 1 = <default> 💡 是否升序排列
            - fc_mix: 0 | 1 = <default> 💡 是否目录和文件混合，如果为 0 则目录在前（目录置顶）
            - module: str = <default> 💡 "label_search" 表示用于搜索的排序
        """
        api = complete_url("/2.0/ufile/order", base_url=base_url, app=app)
        if isinstance(payload, str):
            payload = {"user_order": payload}
        payload = {"file_id": 0, "user_asc": 1, "user_order": "user_ptime", **payload}
        return self.request(url=api, method="POST", data=payload, async_=async_, **request_kwargs)

    @overload
    def fs_preview(
        self, 
        payload: str | dict, 
        /, 
        base_url: str | Callable[[], str] = "https://webapi.115.com", 
        *, 
        async_: Literal[False] = False, 
        **request_kwargs, 
    ) -> dict:
        ...
    @overload
    def fs_preview(
        self, 
        payload: str | dict, 
        /, 
        base_url: str | Callable[[], str] = "https://webapi.115.com", 
        *, 
        async_: Literal[True], 
        **request_kwargs, 
    ) -> Coroutine[Any, Any, dict]:
        ...
    def fs_preview(
        self, 
        payload: str | dict, 
        /, 
        base_url: str | Callable[[], str] = "https://webapi.115.com", 
        *, 
        async_: Literal[False, True] = False, 
        **request_kwargs, 
    ) -> dict | Coroutine[Any, Any, dict]:
        """文档预览

        POST  https://webapi.115.com/files/preview

        :payload:
            - pickcode: str 💡 提取码
        """
        api = complete_url("/files/preview", base_url=base_url)
        if isinstance(payload, str):
            payload = {"pickcode": payload}
        return self.request(url=api, method="POST", data=payload, async_=async_, **request_kwargs)

    @overload
    def fs_rename(
        self, 
        payload: tuple[int | str, str] | dict | Iterable[tuple[int | str, str]], 
        /, 
        base_url: str | Callable[[], str] = "https://webapi.115.com", 
        *, 
        async_: Literal[False] = False, 
        **request_kwargs, 
    ) -> dict:
        ...
    @overload
    def fs_rename(
        self, 
        payload: tuple[int | str, str] | dict | Iterable[tuple[int | str, str]], 
        /, 
        base_url: str | Callable[[], str] = "https://webapi.115.com", 
        *, 
        async_: Literal[True], 
        **request_kwargs, 
    ) -> Coroutine[Any, Any, dict]:
        ...
    def fs_rename(
        self, 
        payload: tuple[int | str, str] | dict | Iterable[tuple[int | str, str]], 
        /, 
        base_url: str | Callable[[], str] = "https://webapi.115.com", 
        *, 
        async_: Literal[False, True] = False, 
        **request_kwargs, 
    ) -> dict | Coroutine[Any, Any, dict]:
        """重命名文件或目录

        POST https://webapi.115.com/files/batch_rename

        :payload:
            - files_new_name[{file_id}]: str 💡 值为新的文件名（basename）
        """
        api = complete_url("/files/batch_rename", base_url=base_url)
        if isinstance(payload, tuple) and len(payload) == 2 and isinstance(payload[0], (int, str)):
            payload = {f"files_new_name[{payload[0]}]": payload[1]}
        elif not isinstance(payload, dict):
            payload = {f"files_new_name[{fid}]": name for fid, name in payload}
        return self.request(url=api, method="POST", data=payload, async_=async_, **request_kwargs)

    @overload
    def fs_rename_app(
        self, 
        payload: tuple[int | str, str] | dict | Iterable[tuple[int | str, str]], 
        /, 
        app: str = "android", 
        base_url: str | Callable[[], str] = "https://proapi.115.com", 
        *, 
        async_: Literal[False] = False, 
        **request_kwargs, 
    ) -> dict:
        ...
    @overload
    def fs_rename_app(
        self, 
        payload: tuple[int | str, str] | dict | Iterable[tuple[int | str, str]], 
        /, 
        app: str = "android", 
        base_url: str | Callable[[], str] = "https://proapi.115.com", 
        *, 
        async_: Literal[True], 
        **request_kwargs, 
    ) -> Coroutine[Any, Any, dict]:
        ...
    def fs_rename_app(
        self, 
        payload: tuple[int | str, str] | dict | Iterable[tuple[int | str, str]], 
        /, 
        app: str = "android", 
        base_url: str | Callable[[], str] = "https://proapi.115.com", 
        *, 
        async_: Literal[False, True] = False, 
        **request_kwargs, 
    ) -> dict | Coroutine[Any, Any, dict]:
        """重命名文件或目录

        POST https://proapi.115.com/android/files/batch_rename

        :payload:
            - files_new_name[{file_id}]: str 💡 值为新的文件名（basename）
        """
        api = complete_url("/files/batch_rename", base_url=base_url, app=app)
        if isinstance(payload, tuple) and len(payload) == 2 and isinstance(payload[0], (int, str)):
            payload = {f"files_new_name[{payload[0]}]": payload[1]}
        elif not isinstance(payload, dict):
            payload = {f"files_new_name[{fid}]": name for fid, name in payload}
        return self.request(url=api, method="POST", data=payload, async_=async_, **request_kwargs)

    @overload
    def fs_rename_set_names(
        self, 
        payload: dict | list[tuple[str, str | int]], 
        /, 
        base_url: str | Callable[[], str] = "https://aps.115.com", 
        *, 
        async_: Literal[False] = False, 
        **request_kwargs, 
    ) -> dict:
        ...
    @overload
    def fs_rename_set_names(
        self, 
        payload: dict | list[tuple[str, str | int]], 
        /, 
        base_url: str | Callable[[], str] = "https://aps.115.com", 
        *, 
        async_: Literal[True], 
        **request_kwargs, 
    ) -> Coroutine[Any, Any, dict]:
        ...
    def fs_rename_set_names(
        self, 
        payload: dict | list[tuple[str, str | int]], 
        /, 
        base_url: str | Callable[[], str] = "https://aps.115.com", 
        *, 
        async_: Literal[False, True] = False, 
        **request_kwargs, 
    ) -> dict | Coroutine[Any, Any, dict]:
        """提交模拟批量重命名请求（提示：较为复杂，自己抓包研究）

        POST https://aps.115.com/rename/set_names.php
        """
        api = complete_url("/rename/set_names.php", base_url=base_url)
        return self.request(url=api, method="POST", data=payload, async_=async_, **request_kwargs)

    @overload
    def fs_rename_reset_names(
        self, 
        payload: dict | list[tuple[str, str | int]], 
        /, 
        base_url: str | Callable[[], str] = "https://aps.115.com", 
        *, 
        async_: Literal[False] = False, 
        **request_kwargs, 
    ) -> dict:
        ...
    @overload
    def fs_rename_reset_names(
        self, 
        payload: dict | list[tuple[str, str | int]], 
        /, 
        base_url: str | Callable[[], str] = "https://aps.115.com", 
        *, 
        async_: Literal[True], 
        **request_kwargs, 
    ) -> Coroutine[Any, Any, dict]:
        ...
    def fs_rename_reset_names(
        self, 
        payload: dict | list[tuple[str, str | int]], 
        /, 
        base_url: str | Callable[[], str] = "https://aps.115.com", 
        *, 
        async_: Literal[False, True] = False, 
        **request_kwargs, 
    ) -> dict | Coroutine[Any, Any, dict]:
        """获取批量重命名的模拟结果（提示：较为复杂，自己抓包研究）

        POST https://aps.115.com/rename/reset_names.php
        """
        api = complete_url("/rename/reset_names.php", base_url=base_url)
        return self.request(url=api, method="POST", data=payload, async_=async_, **request_kwargs)

    @overload
    def fs_repeat_sha1(
        self, 
        payload: int | str | dict, 
        /, 
        base_url: str | Callable[[], str] = "https://webapi.115.com", 
        *, 
        async_: Literal[False] = False, 
        **request_kwargs, 
    ) -> dict:
        ...
    @overload
    def fs_repeat_sha1(
        self, 
        payload: int | str | dict, 
        /, 
        base_url: str | Callable[[], str] = "https://webapi.115.com", 
        *, 
        async_: Literal[True], 
        **request_kwargs, 
    ) -> Coroutine[Any, Any, dict]:
        ...
    def fs_repeat_sha1(
        self, 
        payload: int | str | dict, 
        /, 
        base_url: str | Callable[[], str] = "https://webapi.115.com", 
        *, 
        async_: Literal[False, True] = False, 
        **request_kwargs, 
    ) -> dict | Coroutine[Any, Any, dict]:
        """查找重复文件（罗列除此以外的 sha1 相同的文件）

        GET https://webapi.115.com/files/get_repeat_sha

        :payload:
            - file_id: int | str
            - offset: int = 0
            - limit: int = 1150
            - source: str = ""
        """
        api = complete_url("/files/get_repeat_sha", base_url=base_url)
        if isinstance(payload, (int, str)):
            payload = {"file_id": payload}
        payload = {"offset": 0, "limit": 1150, **payload}
        return self.request(url=api, params=payload, async_=async_, **request_kwargs)

    @overload
    def fs_repeat_sha1_app(
        self, 
        payload: int | str | dict, 
        /, 
        app: str = "android", 
        base_url: str | Callable[[], str] = "https://proapi.115.com", 
        *, 
        async_: Literal[False] = False, 
        **request_kwargs, 
    ) -> dict:
        ...
    @overload
    def fs_repeat_sha1_app(
        self, 
        payload: int | str | dict, 
        /, 
        app: str = "android", 
        base_url: str | Callable[[], str] = "https://proapi.115.com", 
        *, 
        async_: Literal[True], 
        **request_kwargs, 
    ) -> Coroutine[Any, Any, dict]:
        ...
    def fs_repeat_sha1_app(
        self, 
        payload: int | str | dict, 
        /, 
        app: str = "android", 
        base_url: str | Callable[[], str] = "https://proapi.115.com", 
        *, 
        async_: Literal[False, True] = False, 
        **request_kwargs, 
    ) -> dict | Coroutine[Any, Any, dict]:
        """查找重复文件（罗列除此以外的 sha1 相同的文件）

        GET https://proapi.115.com/android/2.0/ufile/get_repeat_sha

        :payload:
            - file_id: int | str
            - offset: int = 0
            - limit: int = 1150
            - source: str = ""
        """
        api = complete_url("/2.0/ufile/get_repeat_sha", base_url=base_url, app=app)
        if isinstance(payload, (int, str)):
            payload = {"file_id": payload}
        payload = {"offset": 0, "limit": 1150, **payload}
        return self.request(url=api, params=payload, async_=async_, **request_kwargs)

    @overload
    def fs_score_set(
        self, 
        file_id: int | str | Iterable[int | str], 
        /, 
        score: int = 0, 
        base_url: str | Callable[[], str] = "https://webapi.115.com", 
        *, 
        async_: Literal[False] = False, 
        **request_kwargs, 
    ) -> dict:
        ...
    @overload
    def fs_score_set(
        self, 
        file_id: int | str | Iterable[int | str], 
        /, 
        score: int = 0, 
        base_url: str | Callable[[], str] = "https://webapi.115.com", 
        *, 
        async_: Literal[True], 
        **request_kwargs, 
    ) -> Coroutine[Any, Any, dict]:
        ...
    def fs_score_set(
        self, 
        file_id: int | str | Iterable[int | str], 
        /, 
        score: int = 0, 
        base_url: str | Callable[[], str] = "https://webapi.115.com", 
        *, 
        async_: Literal[False, True] = False, 
        **request_kwargs, 
    ) -> dict | Coroutine[Any, Any, dict]:
        """给文件或目录评分

        POST https://webapi.115.com/files/score

        :payload:
            - file_id: int | str 💡 文件或目录 id，多个用逗号 "," 隔开
            - score: int = 0     💡 0 为删除评分
        """
        api = complete_url("/files/score", base_url=base_url)
        if not isinstance(file_id, (int, str)):
            file_id = ",".join(map(str, file_id))
        payload = {"file_id": file_id, "score": score}
        return self.request(url=api, method="POST", data=payload, async_=async_, **request_kwargs)

    @overload
    def fs_search(
        self, 
        payload: str | dict = ".", 
        /, 
        base_url: str | Callable[[], str] = "https://webapi.115.com", 
        *, 
        async_: Literal[False] = False, 
        **request_kwargs, 
    ) -> dict:
        ...
    @overload
    def fs_search(
        self, 
        payload: str | dict = ".", 
        /, 
        base_url: str | Callable[[], str] = "https://webapi.115.com", 
        *, 
        async_: Literal[True], 
        **request_kwargs, 
    ) -> Coroutine[Any, Any, dict]:
        ...
    def fs_search(
        self, 
        payload: str | dict = ".", 
        /, 
        base_url: str | Callable[[], str] = "https://webapi.115.com", 
        *, 
        async_: Literal[False, True] = False, 
        **request_kwargs, 
    ) -> dict | Coroutine[Any, Any, dict]:
        """搜索文件或目录

        GET https://webapi.115.com/files/search

        .. attention::
            最多只能取回前 10,000 条数据，也就是 `limit + offset <= 10_000`，不过可以一次性取完

            不过就算正确设置了 `limit` 和 `offset`，并且总数据量大于 `limit + offset`，可能也不足 `limit`，这应该是 bug，也就是说，就算数据总量足够你也取不到足量

            它返回数据中的 `count` 字段的值表示总数据量（即使你只能取前 10,000 条），往往并不准确，最多能当作一个可参考的估计值

            这个接口实际上不支持在查询中直接设置排序，只能由 ``P115Client.fs_order_set()`` 设置

        .. note::
            搜索接口甚至可以把上级 id 关联错误的文件或目录都搜索出来。一般是因为把文件或目录移动到了一个不存在的 id 下，你可以用某些关键词把他们搜索出来，然后移动到一个存在的目录中，就可以恢复他们了，或者使用 ``P115Client.tool_space()`` 接口来批量恢复

        .. important::
            一般使用的话，要提供 "search_value" 或 "file_label"，不然返回数据里面看不到任何一条数据，即使你指定了其它参数

            下面指定的很多参数其实是一点效果都没有的，具体可以实际验证

        :payload:
            - aid: int = 1 💡 area_id

                - 0: 会被视为 1
                - 1: 正常文件
                - 2: <unknown>
                - 3: <unknown>
                - 4: <unknown>
                - 5: <unknown>
                - 7: 回收站文件
                - 9: <unknown>
                - 12:瞬间文件
                - 15: <unknown>
                - 120: 彻底删除文件、简历附件
                - <其它>: 会被视为 0

            - asc: 0 | 1 = <default> 💡 是否升序排列
            - cid: int | str = 0 💡 目录 id，对应 parent_id
            - count_folders: 0 | 1 = <default> 💡 是否统计目录数，这样就会增加 "folder_count" 和 "file_count" 字段作为统计
            - date: str = <default> 💡 筛选日期，格式为 YYYY-MM-DD（或者 YYYY-MM 或 YYYY），具体可以看文件信息中的 "t" 字段的值
            - fc: 0 | 1 = <default> 💡 只显示文件或目录。1:只显示目录 2:只显示文件
            - fc_mix: 0 | 1 = <default> 💡 是否目录和文件混合，如果为 0 则目录在前（目录置顶）
            - file_label: int | str = <default> 💡 标签 id
            - gte_day: str 💡 搜索结果匹配的开始时间；格式：YYYY-MM-DD
            - limit: int = 32 💡 一页大小，意思就是 page_size
            - lte_day: str 💡 搜索结果匹配的结束时间；格式：YYYY-MM-DD
            - o: str = <default> 💡 用某字段排序

                - "file_name": 文件名
                - "file_size": 文件大小
                - "file_type": 文件种类
                - "user_utime": 修改时间
                - "user_ptime": 创建时间
                - "user_otime": 上一次打开时间

            - offset: int = 0  💡 索引偏移，索引从 0 开始计算
            - search_value: str = "." 💡 搜索文本，可以是 sha1
            - source: str = <default> 💡 来源
            - star: 0 | 1 = <default> 💡 是否打星标
            - suffix: str = <default> 💡 文件后缀（扩展名），优先级高于 `type`
            - type: int = <default>   💡 文件类型

                - 0: 全部（仅当前目录）
                - 1: 文档
                - 2: 图片
                - 3: 音频
                - 4: 视频
                - 5: 压缩包
                - 6: 软件/应用
                - 7: 书籍
                - 99: 所有文件
        """
        api = complete_url("/files/search", base_url=base_url)
        if isinstance(payload, str):
            payload = {"search_value": payload}
        payload = {
            "aid": 1, "cid": 0, "limit": 32, "offset": 0, 
            "show_dir": 1, "search_value": ".", **payload, 
        }
        return self.request(url=api, params=payload, async_=async_, **request_kwargs)

    @overload
    def fs_search_app(
        self, 
        payload: str | dict = ".", 
        /, 
        app: str = "android", 
        base_url: str | Callable[[], str] = "https://proapi.115.com", 
        *, 
        async_: Literal[False] = False, 
        **request_kwargs, 
    ) -> dict:
        ...
    @overload
    def fs_search_app(
        self, 
        payload: str | dict = ".", 
        /, 
        app: str = "android", 
        base_url: str | Callable[[], str] = "https://proapi.115.com", 
        *, 
        async_: Literal[True], 
        **request_kwargs, 
    ) -> Coroutine[Any, Any, dict]:
        ...
    def fs_search_app(
        self, 
        payload: str | dict = ".", 
        /, 
        app: str = "android", 
        base_url: str | Callable[[], str] = "https://proapi.115.com", 
        *, 
        async_: Literal[False, True] = False, 
        **request_kwargs, 
    ) -> dict | Coroutine[Any, Any, dict]:
        """搜索文件或目录

        GET https://proapi.115.com/android/2.0/ufile/search

        .. attention::
            最多只能取回前 10,000 条数据，也就是 `limit + offset <= 10_000`，不过可以一次性取完

            不过就算正确设置了 `limit` 和 `offset`，并且总数据量大于 `limit + offset`，可能也不足 `limit`，这应该是 bug，也就是说，就算数据总量足够你也取不到足量

            它返回数据中的 `count` 字段的值表示总数据量（即使你只能取前 10,000 条），往往并不准确，最多能当作一个可参考的估计值

        :payload:
            - aid: int = 1 💡 area_id

                - 0: 会被视为 1
                - 1: 正常文件
                - 2: <unknown>
                - 3: <unknown>
                - 4: <unknown>
                - 5: <unknown>
                - 7: 回收站文件
                - 9: <unknown>
                - 12:瞬间文件
                - 15: <unknown>
                - 120: 彻底删除文件、简历附件
                - <其它>: 会被视为 0

            - asc: 0 | 1 = <default> 💡 是否升序排列
            - cid: int | str = 0 💡 目录 id。cid=-1 时，表示不返回列表任何内容
            - count_folders: 0 | 1 = <default>
            - date: str = <default> 💡 筛选日期
            - fc: 0 | 1 = <default> 💡 只显示文件或目录。1:只显示目录 2:只显示文件
            - fc_mix: 0 | 1 = <default> 💡 是否目录和文件混合，如果为 0 则目录在前（目录置顶）
            - file_label: int | str = <default> 💡 标签 id
            - gte_day: str 💡 搜索结果匹配的开始时间；格式：YYYY-MM-DD
            - limit: int = 32 💡 一页大小，意思就是 page_size
            - lte_day: str 💡 搜索结果匹配的结束时间；格式：YYYY-MM-DD
            - o: str = <default> 💡 用某字段排序

                - "file_name": 文件名
                - "file_size": 文件大小
                - "file_type": 文件种类
                - "user_utime": 修改时间
                - "user_ptime": 创建时间
                - "user_otime": 上一次打开时间

            - offset: int = 0  💡 索引偏移，索引从 0 开始计算
            - search_value: str = "." 💡 搜索文本，可以是 sha1
            - source: str = <default>
            - star: 0 | 1 = <default> 💡 是否星标文件
            - suffix: str = <default> 💡 后缀名（优先级高于 `type`）
            - type: int = <default> 💡 文件类型

                - 0: 全部（仅当前目录）
                - 1: 文档
                - 2: 图片
                - 3: 音频
                - 4: 视频
                - 5: 压缩包
                - 6: 软件/应用
                - 7: 书籍
                - 99: 所有文件

            - version: str = <default> 💡 版本号，比如 3.1
        """
        api = complete_url("/2.0/ufile/search", base_url=base_url, app=app)
        if isinstance(payload, str):
            payload = {"search_value": payload}
        payload = {
            "aid": 1, "cid": 0, "limit": 32, "offset": 0, 
            "show_dir": 1, "search_value": ".", **payload, 
        }
        return self.request(url=api, params=payload, async_=async_, **request_kwargs)

    @overload
    def fs_search_app2(
        self, 
        payload: str | dict = ".", 
        /, 
        app: str = "android", 
        base_url: str | Callable[[], str] = "https://proapi.115.com", 
        *, 
        async_: Literal[False] = False, 
        **request_kwargs, 
    ) -> dict:
        ...
    @overload
    def fs_search_app2(
        self, 
        payload: str | dict = ".", 
        /, 
        app: str = "android", 
        base_url: str | Callable[[], str] = "https://proapi.115.com", 
        *, 
        async_: Literal[True], 
        **request_kwargs, 
    ) -> Coroutine[Any, Any, dict]:
        ...
    def fs_search_app2(
        self, 
        payload: str | dict = ".", 
        /, 
        app: str = "android", 
        base_url: str | Callable[[], str] = "https://proapi.115.com", 
        *, 
        async_: Literal[False, True] = False, 
        **request_kwargs, 
    ) -> dict | Coroutine[Any, Any, dict]:
        """搜索文件或目录

        GET https://proapi.115.com/android/files/search

        .. attention::
            最多只能取回前 10,000 条数据，也就是 `limit + offset <= 10_000`，不过可以一次性取完

            不过就算正确设置了 `limit` 和 `offset`，并且总数据量大于 `limit + offset`，可能也不足 `limit`，这应该是 bug，也就是说，就算数据总量足够你也取不到足量

            它返回数据中的 `count` 字段的值表示总数据量（即使你只能取前 10,000 条），往往并不准确，最多能当作一个可参考的估计值

        :payload:
            - aid: int = 1 💡 area_id

                - 0: 会被视为 1
                - 1: 正常文件
                - 2: <unknown>
                - 3: <unknown>
                - 4: <unknown>
                - 5: <unknown>
                - 7: 回收站文件
                - 9: <unknown>
                - 12:瞬间文件
                - 15: <unknown>
                - 120: 彻底删除文件、简历附件
                - <其它>: 会被视为 0

            - asc: 0 | 1 = <default> 💡 是否升序排列
            - cid: int | str = 0 💡 目录 id。cid=-1 时，表示不返回列表任何内容
            - count_folders: 0 | 1 = <default>
            - date: str = <default> 💡 筛选日期
            - fc: 0 | 1 = <default> 💡 只显示文件或目录。1:只显示目录 2:只显示文件
            - fc_mix: 0 | 1 = <default> 💡 是否目录和文件混合，如果为 0 则目录在前（目录置顶）
            - file_label: int | str = <default> 💡 标签 id
            - gte_day: str 💡 搜索结果匹配的开始时间；格式：YYYY-MM-DD
            - limit: int = 32 💡 一页大小，意思就是 page_size
            - lte_day: str 💡 搜索结果匹配的结束时间；格式：YYYY-MM-DD
            - o: str = <default> 💡 用某字段排序

                - "file_name": 文件名
                - "file_size": 文件大小
                - "file_type": 文件种类
                - "user_utime": 修改时间
                - "user_ptime": 创建时间
                - "user_otime": 上一次打开时间

            - offset: int = 0  💡 索引偏移，索引从 0 开始计算
            - search_value: str = "." 💡 搜索文本，可以是 sha1
            - source: str = <default>
            - star: 0 | 1 = <default> 💡 是否星标文件
            - suffix: str = <default> 💡 后缀名（优先级高于 `type`）
            - type: int = <default> 💡 文件类型

                - 0: 全部（仅当前目录）
                - 1: 文档
                - 2: 图片
                - 3: 音频
                - 4: 视频
                - 5: 压缩包
                - 6: 软件/应用
                - 7: 书籍
                - 99: 所有文件

            - version: str = <default> 💡 版本号，比如 3.1
        """
        api = complete_url("/files/search", base_url=base_url, app=app)
        if isinstance(payload, str):
            payload = {"search_value": payload}
        payload = {
            "aid": 1, "cid": 0, "limit": 32, "offset": 0, 
            "show_dir": 1, "search_value": ".", **payload, 
        }
        return self.request(url=api, params=payload, async_=async_, **request_kwargs)

    @overload
    def fs_shasearch(
        self, 
        payload: str | dict, 
        /, 
        base_url: str | Callable[[], str] = "https://webapi.115.com", 
        *, 
        async_: Literal[False] = False, 
        **request_kwargs, 
    ) -> dict:
        ...
    @overload
    def fs_shasearch(
        self, 
        payload: str | dict, 
        /, 
        base_url: str | Callable[[], str] = "https://webapi.115.com", 
        *, 
        async_: Literal[True], 
        **request_kwargs, 
    ) -> Coroutine[Any, Any, dict]:
        ...
    def fs_shasearch(
        self, 
        payload: str | dict, 
        /, 
        base_url: str | Callable[[], str] = "https://webapi.115.com", 
        *, 
        async_: Literal[False, True] = False, 
        **request_kwargs, 
    ) -> dict | Coroutine[Any, Any, dict]:
        """通过 sha1 搜索文件

        GET https://webapi.115.com/files/shasearch

        .. note::
            这是个非常早期的接口，高级功能请直接使用 `client.fs_search`。这个方法最多只能获得一条记录，并且不支持指定搜索目录，而且当未搜索到时，返回的信息为 '{"state": false, "error": "文件错误"}'

        :payload:
            - sha1: str
        """
        api = complete_url("/files/shasearch", base_url=base_url)
        if isinstance(payload, str):
            payload = {"sha1": payload}
        return self.request(url=api, params=payload, async_=async_, **request_kwargs)

    @overload
    def fs_show_play_long_set(
        self, 
        payload: int | str | Iterable[int | str] | list[tuple] | dict, 
        /, 
        show: bool = True, 
        base_url: str | Callable[[], str] = "https://webapi.115.com", 
        *, 
        async_: Literal[False] = False, 
        **request_kwargs, 
    ) -> dict:
        ...
    @overload
    def fs_show_play_long_set(
        self, 
        payload: int | str | Iterable[int | str] | list[tuple] | dict, 
        /, 
        show: bool = True, 
        base_url: str | Callable[[], str] = "https://webapi.115.com", 
        *, 
        async_: Literal[True], 
        **request_kwargs, 
    ) -> Coroutine[Any, Any, dict]:
        ...
    def fs_show_play_long_set(
        self, 
        payload: int | str | Iterable[int | str] | list[tuple] | dict, 
        /, 
        show: bool = True, 
        base_url: str | Callable[[], str] = "https://webapi.115.com", 
        *, 
        async_: Literal[False, True] = False, 
        **request_kwargs, 
    ) -> dict | Coroutine[Any, Any, dict]:
        """为目录设置显示时长，此接口是对 `fs_edit` 的封装
        """
        return self._fs_edit_set(
            payload, 
            "show_play_long", 
            default=int(show), 
            base_url=base_url, 
            async_=async_, 
            **request_kwargs, 
        )

    @overload
    def fs_show_play_long_set_app(
        self, 
        payload: int | str | Iterable[int | str] | list[tuple] | dict, 
        /, 
        show: bool = True, 
        app: str = "android", 
        base_url: str | Callable[[], str] = "https://proapi.115.com", 
        *, 
        async_: Literal[False] = False, 
        **request_kwargs, 
    ) -> dict:
        ...
    @overload
    def fs_show_play_long_set_app(
        self, 
        payload: int | str | Iterable[int | str] | list[tuple] | dict, 
        /, 
        show: bool = True, 
        app: str = "android", 
        base_url: str | Callable[[], str] = "https://proapi.115.com", 
        *, 
        async_: Literal[True], 
        **request_kwargs, 
    ) -> Coroutine[Any, Any, dict]:
        ...
    def fs_show_play_long_set_app(
        self, 
        payload: int | str | Iterable[int | str] | list[tuple] | dict, 
        /, 
        show: bool = True, 
        app: str = "android", 
        base_url: str | Callable[[], str] = "https://proapi.115.com", 
        *, 
        async_: Literal[False, True] = False, 
        **request_kwargs, 
    ) -> dict | Coroutine[Any, Any, dict]:
        """为目录设置显示时长，此接口是对 `fs_files_update_app` 的封装
        """
        return self._fs_edit_set_app(
            payload, 
            "show_play_long", 
            default=int(show), 
            app=app, 
            base_url=base_url, 
            async_=async_, 
            **request_kwargs, 
        )

    @overload
    def fs_space_report(
        self, 
        payload: str | dict = "", 
        /, 
        base_url: str | Callable[[], str] = "https://webapi.115.com", 
        *, 
        async_: Literal[False] = False, 
        **request_kwargs, 
    ) -> dict:
        ...
    @overload
    def fs_space_report(
        self, 
        payload: str | dict = "", 
        /, 
        base_url: str | Callable[[], str] = "https://webapi.115.com", 
        *, 
        async_: Literal[True], 
        **request_kwargs, 
    ) -> Coroutine[Any, Any, dict]:
        ...
    def fs_space_report(
        self, 
        payload: str | dict = "", 
        /, 
        base_url: str | Callable[[], str] = "https://webapi.115.com", 
        *, 
        async_: Literal[False, True] = False, 
        **request_kwargs, 
    ) -> dict | Coroutine[Any, Any, dict]:
        """获取数据报告（截至月末数据，分组聚合）

        GET https://webapi.115.com/user/report

        :payload:
            - month: str 💡 年月，格式为 YYYYMM
        """
        api = complete_url("/user/report", base_url=base_url)
        if not payload:
            now = datetime.now()
            year, month = now.year, now.month
            if month == 1:
                ym = f"{year-1}12"
            else:
                ym = f"{year}{month-1:02d}"
            payload = {"month": ym}
        elif isinstance(payload, str):
            payload = {"month": payload}
        return self.request(url=api, params=payload, async_=async_, **request_kwargs)

    @overload
    def fs_space_summury(
        self, 
        /, 
        base_url: str | Callable[[], str] = "https://webapi.115.com", 
        *, 
        async_: Literal[False] = False, 
        **request_kwargs, 
    ) -> dict:
        ...
    @overload
    def fs_space_summury(
        self, 
        /, 
        base_url: str | Callable[[], str] = "https://webapi.115.com", 
        *, 
        async_: Literal[True], 
        **request_kwargs, 
    ) -> Coroutine[Any, Any, dict]:
        ...
    def fs_space_summury(
        self, 
        /, 
        base_url: str | Callable[[], str] = "https://webapi.115.com", 
        *, 
        async_: Literal[False, True] = False, 
        **request_kwargs, 
    ) -> dict | Coroutine[Any, Any, dict]:
        """获取数据报告（当前数据，分组聚合）

        POST https://webapi.115.com/user/space_summury
        """
        api = complete_url("/user/space_summury", base_url=base_url)
        return self.request(url=api, method="POST", async_=async_, **request_kwargs)

    @overload
    def fs_star_set(
        self, 
        payload: int | str | Iterable[int | str] | dict, 
        /, 
        star: bool = True, 
        base_url: str | Callable[[], str] = "https://webapi.115.com", 
        *, 
        async_: Literal[False] = False, 
        **request_kwargs, 
    ) -> dict:
        ...
    @overload
    def fs_star_set(
        self, 
        payload: int | str | Iterable[int | str] | dict, 
        /, 
        star: bool = True, 
        base_url: str | Callable[[], str] = "https://webapi.115.com", 
        *, 
        async_: Literal[True], 
        **request_kwargs, 
    ) -> Coroutine[Any, Any, dict]:
        ...
    def fs_star_set(
        self, 
        payload: int | str | Iterable[int | str] | dict, 
        /, 
        star: bool = True, 
        base_url: str | Callable[[], str] = "https://webapi.115.com", 
        *, 
        async_: Literal[False, True] = False, 
        **request_kwargs, 
    ) -> dict | Coroutine[Any, Any, dict]:
        """为文件或目录设置或取消星标

        POST https://webapi.115.com/files/star

        .. note::
            如果其中任何一个 id 目前已经被删除，则会直接返回错误信息

        :payload:
            - file_id: int | str 💡 文件或目录 id，多个用逗号 "," 隔开
            - star: 0 | 1 = 1
        """
        api = complete_url("/files/star", base_url=base_url)
        if isinstance(payload, (int, str)):
            payload = {"file_id": payload, "star": int(star)}
        elif not isinstance(payload, dict):
            payload = {"file_id": ",".join(map(str, payload)), "star": int(star)}
        else:
            payload = {"star": int(star), **payload}
        return self.request(url=api, method="POST", data=payload, async_=async_, **request_kwargs)

    @overload
    def fs_star_set_app(
        self, 
        payload: int | str | Iterable[int | str] | dict, 
        /, 
        star: bool = True, 
        app: str = "android", 
        base_url: str | Callable[[], str] = "https://proapi.115.com", 
        *, 
        async_: Literal[False] = False, 
        **request_kwargs, 
    ) -> dict:
        ...
    @overload
    def fs_star_set_app(
        self, 
        payload: int | str | Iterable[int | str] | dict, 
        /, 
        star: bool = True, 
        app: str = "android", 
        base_url: str | Callable[[], str] = "https://proapi.115.com", 
        *, 
        async_: Literal[True], 
        **request_kwargs, 
    ) -> Coroutine[Any, Any, dict]:
        ...
    def fs_star_set_app(
        self, 
        payload: int | str | Iterable[int | str] | dict, 
        /, 
        star: bool = True, 
        app: str = "android", 
        base_url: str | Callable[[], str] = "https://proapi.115.com", 
        *, 
        async_: Literal[False, True] = False, 
        **request_kwargs, 
    ) -> dict | Coroutine[Any, Any, dict]:
        """为文件或目录设置或取消星标

        POST https://proapi.115.com/android/files/star

        .. note::
            如果其中任何一个 id 目前已经被删除，则会直接返回错误信息

        :payload:
            - ids: int | str 💡 文件或目录 id，多个用逗号 "," 隔开
            - star: 0 | 1 = 1
            - user_id: int | str = <default> 💡 用户 id
        """
        api = complete_url("/files/star", base_url=base_url, app=app)
        if isinstance(payload, (int, str)):
            payload = {"ids": payload, "star": int(star)}
        elif not isinstance(payload, dict):
            payload = {"ids": ",".join(map(str, payload)), "star": int(star)}
        else:
            payload = {"star": int(star), **payload}
        payload["user_id"] = self.user_id
        return self.request(url=api, method="POST", data=payload, async_=async_, **request_kwargs)

    @overload
    def fs_storage_info(
        self, 
        /, 
        base_url: str | Callable[[], str] = "https://115.com", 
        *, 
        async_: Literal[False] = False, 
        **request_kwargs, 
    ) -> dict:
        ...
    @overload
    def fs_storage_info(
        self, 
        /, 
        base_url: str | Callable[[], str] = "https://115.com", 
        *, 
        async_: Literal[True], 
        **request_kwargs, 
    ) -> Coroutine[Any, Any, dict]:
        ...
    def fs_storage_info(
        self, 
        /, 
        base_url: str | Callable[[], str] = "https://115.com", 
        *, 
        async_: Literal[False, True] = False, 
        **request_kwargs, 
    ) -> dict | Coroutine[Any, Any, dict]:
        """获取使用空间的统计数据（最简略，如需更详细，请用 `fs.user_space_info()`）

        GET https://115.com/index.php?ct=ajax&ac=get_storage_info
        """
        api = complete_url("/index.php", base_url=base_url, query={"ct": "ajax", "ac": "get_storage_info"})
        return self.request(url=api, async_=async_, **request_kwargs)

    @overload
    def fs_supervision(
        self, 
        payload: str | dict, 
        /, 
        base_url: str | Callable[[], str] = "https://webapi.115.com", 
        *, 
        async_: Literal[False] = False, 
        **request_kwargs, 
    ) -> dict:
        ...
    @overload
    def fs_supervision(
        self, 
        payload: str | dict, 
        /, 
        base_url: str | Callable[[], str] = "https://webapi.115.com", 
        *, 
        async_: Literal[True], 
        **request_kwargs, 
    ) -> Coroutine[Any, Any, dict]:
        ...
    def fs_supervision(
        self, 
        payload: str | dict, 
        /, 
        base_url: str | Callable[[], str] = "https://webapi.115.com", 
        *, 
        async_: Literal[False, True] = False, 
        **request_kwargs, 
    ) -> dict | Coroutine[Any, Any, dict]:
        """通过 pickcode 获取文件信息

        POST https://webapi.115.com/files/supervision

        :payload:
            - pickcode: str
            - preview_type: str = "file" 💡 file:文件 doc:文档 video:视频 music:音乐 pic:图片
            - module: int = 10
        """
        api = complete_url("/files/supervision", base_url=base_url)
        if isinstance(payload, str):
            payload = {"pickcode": payload}
        payload = {"preview_type": "file", "module": 10, **payload}
        return self.request(url=api, method="POST", data=payload, async_=async_, **request_kwargs)

    @overload
    def fs_supervision_app(
        self, 
        payload: str | dict, 
        /, 
        app: str = "android", 
        base_url: str | Callable[[], str] = "https://proapi.115.com", 
        *, 
        async_: Literal[False] = False, 
        **request_kwargs, 
    ) -> dict:
        ...
    @overload
    def fs_supervision_app(
        self, 
        payload: str | dict, 
        /, 
        app: str = "android", 
        base_url: str | Callable[[], str] = "https://proapi.115.com", 
        *, 
        async_: Literal[True], 
        **request_kwargs, 
    ) -> Coroutine[Any, Any, dict]:
        ...
    def fs_supervision_app(
        self, 
        payload: str | dict, 
        /, 
        app: str = "android", 
        base_url: str | Callable[[], str] = "https://proapi.115.com", 
        *, 
        async_: Literal[False, True] = False, 
        **request_kwargs, 
    ) -> dict | Coroutine[Any, Any, dict]:
        """通过 pickcode 获取文件信息

        POST https://proapi.115.com/android/files/supervision

        :payload:
            - pickcode: str
            - preview_type: str = "file" 💡 file:文件 doc:文档 video:视频 music:音乐 pic:图片
            - module: int = 10
        """
        api = complete_url("/files/supervision", base_url=base_url, app=app)
        if isinstance(payload, str):
            payload = {"pickcode": payload}
        payload = {"preview_type": "file", "module": 10, **payload}
        return self.request(url=api, method="POST", data=payload, async_=async_, **request_kwargs)

    @overload
    def fs_sys_dir(
        self, 
        payload: int | dict = 0, 
        /, 
        app: str = "android", 
        base_url: str | Callable[[], str] = "https://proapi.115.com", 
        *, 
        async_: Literal[False] = False, 
        **request_kwargs, 
    ) -> dict:
        ...
    @overload
    def fs_sys_dir(
        self, 
        payload: int | dict = 0, 
        /, 
        app: str = "android", 
        base_url: str | Callable[[], str] = "https://proapi.115.com", 
        *, 
        async_: Literal[True], 
        **request_kwargs, 
    ) -> Coroutine[Any, Any, dict]:
        ...
    def fs_sys_dir(
        self, 
        payload: int | dict = 0, 
        /, 
        app: str = "android", 
        base_url: str | Callable[[], str] = "https://proapi.115.com", 
        *, 
        async_: Literal[False, True] = False, 
        **request_kwargs, 
    ) -> dict | Coroutine[Any, Any, dict]:
        """获取系统目录（在根目录下，使用 `fs_files` 接口罗列时，数目体现在返回值的 `sys_count` 字段）

        GET https://proapi.115.com/android/files/getpackage

        :payload:
            - sys_dir: int 💡 0:最近接收 1:手机相册 2:云下载 3:我的时光记录 4,10,20,21,22,30,40,50,60,70:(未知)
        """
        api = complete_url("/files/getpackage", base_url=base_url, app=app)
        if isinstance(payload, int):
            payload = {"sys_dir": payload}
        return self.request(url=api, params=payload, async_=async_, **request_kwargs)

    @overload
    def fs_top_set(
        self, 
        payload: int | str | Iterable[int | str] | dict, 
        /, 
        top: bool = True, 
        base_url: str | Callable[[], str] = "https://webapi.115.com", 
        *, 
        async_: Literal[False] = False, 
        **request_kwargs, 
    ) -> dict:
        ...
    @overload
    def fs_top_set(
        self, 
        payload: int | str | Iterable[int | str] | dict, 
        /, 
        top: bool = True, 
        base_url: str | Callable[[], str] = "https://webapi.115.com", 
        *, 
        async_: Literal[True], 
        **request_kwargs, 
    ) -> Coroutine[Any, Any, dict]:
        ...
    def fs_top_set(
        self, 
        payload: int | str | Iterable[int | str] | dict, 
        /, 
        top: bool = True, 
        base_url: str | Callable[[], str] = "https://webapi.115.com", 
        *, 
        async_: Literal[False, True] = False, 
        **request_kwargs, 
    ) -> dict | Coroutine[Any, Any, dict]:
        """文件或目录置顶

        POST https://webapi.115.com/files/top

        :payload:
            - file_id: int | str 💡 文件或目录的 id，多个用逗号 "," 隔开
            - top: 0 | 1 = 1
        """
        api = complete_url("/files/top", base_url=base_url)
        if isinstance(payload, (int, str)):
            payload = {"file_id": payload, "top": int(top)}
        elif not isinstance(payload, dict):
            payload = {"file_id": ",".join(map(str, payload)), "top": int(top)}
        else:
            payload = {"top": int(top), **payload}
        return self.request(url=api, method="POST", data=payload, async_=async_, **request_kwargs)

    @overload
    def fs_video(
        self, 
        payload: str | dict, 
        /, 
        base_url: str | Callable[[], str] = "https://webapi.115.com", 
        *, 
        async_: Literal[False] = False, 
        **request_kwargs, 
    ) -> dict:
        ...
    @overload
    def fs_video(
        self, 
        payload: str | dict, 
        /, 
        base_url: str | Callable[[], str] = "https://webapi.115.com", 
        *, 
        async_: Literal[True], 
        **request_kwargs, 
    ) -> Coroutine[Any, Any, dict]:
        ...
    def fs_video(
        self, 
        payload: str | dict, 
        /, 
        base_url: str | Callable[[], str] = "https://webapi.115.com", 
        *, 
        async_: Literal[False, True] = False, 
        **request_kwargs, 
    ) -> dict | Coroutine[Any, Any, dict]:
        """获取视频信息和 m3u8 链接列表

        GET https://webapi.115.com/files/video

        .. caution::
            `local` 在有些视频上不起作用，无论如何，都相当于 `local=0`，可能是因为文件超过 200 MB

            但如果 `local=1` 有效，则返回仅可得到下载链接，key 为 "download_url"

        .. important::
            仅这几种设备可用：`harmony`, `web`, `desktop`, **wechatmini**, **alipaymini**, **tv**

            但是如果要获取 m3u8 文件，则要提供 web 设备的 cookies，否则返回空数据

        .. note::
            如果返回信息中有 "queue_url"，则可用于查询转码状态

            如果视频从未被转码过，则会自动推送转码

        :payload:
            - pickcode: str 💡 提取码
            - share_id: int | str = <default> 💡 分享 id
            - local: 0 | 1 = <default> 💡 是否本地，如果为 1，则不包括 m3u8
        """
        api = complete_url("/files/video", base_url=base_url)
        if isinstance(payload, str):
            payload = {"pickcode": payload}
        return self.request(url=api, params=payload, async_=async_, **request_kwargs)

    @overload
    def fs_video_app(
        self, 
        payload: str | dict, 
        /, 
        app: str = "android", 
        base_url: str | Callable[[], str] = "https://proapi.115.com", 
        *, 
        async_: Literal[False] = False, 
        **request_kwargs, 
    ) -> dict:
        ...
    @overload
    def fs_video_app(
        self, 
        payload: str | dict, 
        /, 
        app: str = "android", 
        base_url: str | Callable[[], str] = "https://proapi.115.com", 
        *, 
        async_: Literal[True], 
        **request_kwargs, 
    ) -> Coroutine[Any, Any, dict]:
        ...
    def fs_video_app(
        self, 
        payload: str | dict, 
        /, 
        app: str = "android", 
        base_url: str | Callable[[], str] = "https://proapi.115.com", 
        *, 
        async_: Literal[False, True] = False, 
        **request_kwargs, 
    ) -> dict | Coroutine[Any, Any, dict]:
        """获取视频信息和 m3u8 链接列表

        POST https://proapi.115.com/android/2.0/video/play

        .. important::
            仅这几种设备可用：`115android`, `115ios`, `115ipad`, `android`, `ios`, `qandroid`, `qios`, **wechatmini**, **alipaymini**, **tv**

        :payload:
            - pickcode: str 💡 提取码
            - share_id: int | str = <default> 💡 分享 id
            - local: 0 | 1 = <default> 💡 是否本地，如果为 1，则不包括 m3u8
            - user_id: int | str = <default> 💡 用户 id
        """
        api = complete_url("/2.0/video/play", base_url=base_url, app=app)
        if isinstance(payload, str):
            payload = {"pickcode": payload, "user_id": self.user_id}
        else:
            payload = dict(payload, user_id=self.user_id)
        def parse(_, content: bytes, /) -> dict:
            json = json_loads(content)
            if json["state"] or json.get("errno") == 409:
                json["data"] = json_loads(rsa_decrypt(json["data"]))
            return json
        request_kwargs.setdefault("parse", parse)
        request_kwargs["data"] = {"data": rsa_encrypt(dumps(payload)).decode("ascii")}
        return self.request(
            url=api, 
            method="POST", 
            async_=async_, 
            **request_kwargs, 
        )

    @overload
    def fs_video_def_set(
        self, 
        payload: int | str | dict, 
        /, 
        base_url: str | Callable[[], str] = "https://webapi.115.com", 
        *, 
        async_: Literal[False] = False, 
        **request_kwargs, 
    ) -> dict:
        ...
    @overload
    def fs_video_def_set(
        self, 
        payload: int | str | dict, 
        /, 
        base_url: str | Callable[[], str] = "https://webapi.115.com", 
        *, 
        async_: Literal[True], 
        **request_kwargs, 
    ) -> Coroutine[Any, Any, dict]:
        ...
    def fs_video_def_set(
        self, 
        payload: int | str | dict, 
        /, 
        base_url: str | Callable[[], str] = "https://webapi.115.com", 
        *, 
        async_: Literal[False, True] = False, 
        **request_kwargs, 
    ) -> dict | Coroutine[Any, Any, dict]:
        """切换视频清晰度

        .. caution::
            暂时没搞清楚调用了以后，到底有什么效果，所以建议不要用，除非你知道

        GET https://webapi.115.com/files/video_def

        :payload:
            - definition: str
        """
        api = complete_url("/files/video_def", base_url=base_url)
        if isinstance(payload, (int, str)):
            payload = {"definition": payload}
        return self.request(url=api, method="POST", data=payload, async_=async_, **request_kwargs)

    @overload
    def fs_video_m3u8(
        self, 
        /, 
        pickcode: str, 
        definition: int = 0, 
        base_url: str | Callable[[], str] = "https://115.com", 
        *, 
        async_: Literal[False] = False, 
        **request_kwargs, 
    ) -> bytes:
        ...
    @overload
    def fs_video_m3u8(
        self, 
        /, 
        pickcode: str, 
        definition: int = 0, 
        base_url: str | Callable[[], str] = "https://115.com", 
        *, 
        async_: Literal[True], 
        **request_kwargs, 
    ) -> Coroutine[Any, Any, bytes]:
        ...
    def fs_video_m3u8(
        self, 
        /, 
        pickcode: str, 
        definition: int = 0, 
        base_url: str | Callable[[], str] = "https://115.com", 
        *, 
        async_: Literal[False, True] = False, 
        **request_kwargs, 
    ) -> bytes | Coroutine[Any, Any, bytes]:
        """获取视频的 m3u8 文件列表，此接口必须使用 web 的 cookies

        GET https://115.com/api/video/m3u8/{pickcode}.m3u8?definition={definition}

        .. attention::
            这个接口只支持 web 的 cookies，其它设备会返回空数据，而且获取得到的 m3u8 里的链接，也是 m3u8，会绑定前一次请求时的 user-agent

        :param pickcode: 视频文件的 pickcode
        :param definition: 画质，默认列出所有画质。但可进行筛选，常用的为：
            - 0: 各种分辨率（默认）
            - 1: SD 标清（约为 480p）
            - 3: HD 超清（约为 720p）
            - 4: UD 1080P（约为 1080p）
            - 5: BD 4K
            - 100: 原画（尺寸和原始的相同）
        :param async_: 是否异步
        :param request_kwargs: 其余请求参数

        :return: 接口返回值
        """
        api = complete_url(f"/api/video/m3u8/{pickcode}.m3u8", base_url=base_url, query={"definition": definition})
        request_kwargs.setdefault("parse", False)
        return self.request(url=api, async_=async_, **request_kwargs)

    @overload
    def fs_video_subtitle(
        self, 
        payload: str | dict, 
        /, 
        base_url: str | Callable[[], str] = "https://webapi.115.com", 
        *, 
        async_: Literal[False] = False, 
        **request_kwargs, 
    ) -> dict:
        ...
    @overload
    def fs_video_subtitle(
        self, 
        payload: str | dict, 
        /, 
        base_url: str | Callable[[], str] = "https://webapi.115.com", 
        *, 
        async_: Literal[True], 
        **request_kwargs, 
    ) -> Coroutine[Any, Any, dict]:
        ...
    def fs_video_subtitle(
        self, 
        payload: str | dict, 
        /, 
        base_url: str | Callable[[], str] = "https://webapi.115.com", 
        *, 
        async_: Literal[False, True] = False, 
        **request_kwargs, 
    ) -> dict | Coroutine[Any, Any, dict]:
        """获取视频字幕

        GET https://webapi.115.com/movies/subtitle

        :payload:
            - pickcode: str
        """
        api = complete_url("/movies/subtitle", base_url=base_url)
        if isinstance(payload, str):
            payload = {"pickcode": payload}
        return self.request(url=api, params=payload, async_=async_, **request_kwargs)

    @overload
    def fs_video_subtitle_app(
        self, 
        payload: str | dict, 
        /, 
        app: str = "android", 
        base_url: str | Callable[[], str] = "https://proapi.115.com", 
        *, 
        async_: Literal[False] = False, 
        **request_kwargs, 
    ) -> dict:
        ...
    @overload
    def fs_video_subtitle_app(
        self, 
        payload: str | dict, 
        /, 
        app: str = "android", 
        base_url: str | Callable[[], str] = "https://proapi.115.com", 
        *, 
        async_: Literal[True], 
        **request_kwargs, 
    ) -> Coroutine[Any, Any, dict]:
        ...
    def fs_video_subtitle_app(
        self, 
        payload: str | dict, 
        /, 
        app: str = "android", 
        base_url: str | Callable[[], str] = "https://proapi.115.com", 
        *, 
        async_: Literal[False, True] = False, 
        **request_kwargs, 
    ) -> dict | Coroutine[Any, Any, dict]:
        """获取视频字幕

        GET https://proapi.115.com/android/2.0/video/subtitle

        :payload:
            - pickcode: str
        """
        api = complete_url("/2.0/video/subtitle", base_url=base_url, app=app)
        if isinstance(payload, str):
            payload = {"pickcode": payload}
        return self.request(url=api, params=payload, async_=async_, **request_kwargs)

    @overload
    def fs_video_transcode(
        self, 
        payload: dict | str, 
        /, 
        app: str = "web", 
        base_url: str | Callable[[], str] = "https://transcode.115.com", 
        *, 
        async_: Literal[False] = False, 
        **request_kwargs, 
    ) -> dict:
        ...
    @overload
    def fs_video_transcode(
        self, 
        payload: dict | str, 
        /, 
        app: str = "web", 
        base_url: str | Callable[[], str] = "https://transcode.115.com", 
        *, 
        async_: Literal[True], 
        **request_kwargs, 
    ) -> Coroutine[Any, Any, dict]:
        ...
    def fs_video_transcode(
        self, 
        payload: dict | str, 
        /, 
        app: str = "web", 
        base_url: str | Callable[[], str] = "https://transcode.115.com", 
        *, 
        async_: Literal[False, True] = False, 
        **request_kwargs, 
    ) -> dict | Coroutine[Any, Any, dict]:
        """获取视频的转码进度

        GET https://transcode.115.com/api/1.0/android/1.0/trans_code/check_transcode_job

        :payload:
            - sha1: str
            - priority: int = 100 💡 优先级
        """
        api = complete_url(f"/api/1.0/{app}/1.0/trans_code/check_transcode_job", base_url=base_url)
        if isinstance(payload, str):
            payload = {"sha1": payload}
        payload.setdefault("priority", 100)
        return self.request(url=api, params=payload, async_=async_, **request_kwargs)

    ########## Life API ##########

    @overload
    def life_batch_delete(
        self, 
        payload: Iterable[dict] | dict, 
        /, 
        app: str = "web", 
        base_url: str | Callable[[], str] = "https://life.115.com", 
        *, 
        async_: Literal[False] = False, 
        **request_kwargs, 
    ) -> dict:
        ...
    @overload
    def life_batch_delete(
        self, 
        payload: Iterable[dict] | dict, 
        /, 
        app: str = "web", 
        base_url: str | Callable[[], str] = "https://life.115.com", 
        *, 
        async_: Literal[True], 
        **request_kwargs, 
    ) -> Coroutine[Any, Any, dict]:
        ...
    def life_batch_delete(
        self, 
        payload: Iterable[dict] | dict, 
        /, 
        app: str = "web", 
        base_url: str | Callable[[], str] = "https://life.115.com", 
        *, 
        async_: Literal[False, True] = False, 
        **request_kwargs, 
    ) -> dict | Coroutine[Any, Any, dict]:
        """批量删除操作历史：批量删除 115 生活事件列表

        POST https://life.115.com/api/1.0/web/1.0/life/life_batch_delete

        :payload:
            - delete_data: str 💡 JSON array，每条数据格式为 {"relation_id": str, "behavior_type": str}
        """
        api = complete_url(f"/api/1.0/{app}/1.0/life/life_batch_delete", base_url=base_url)
        if not isinstance(payload, dict):
            payload = {"delete_data": (b"[%s]" % b",".join(map(dumps, payload))).decode("utf-8")}
        return self.request(
            url=api, 
            method="POST", 
            data=payload, 
            async_=async_, 
            **request_kwargs, 
        )

    @overload
    def life_behavior_detail(
        self, 
        payload: str | dict = "", 
        /, 
        base_url: str | Callable[[], str] = "https://webapi.115.com", 
        *, 
        async_: Literal[False] = False, 
        **request_kwargs, 
    ) -> dict:
        ...
    @overload
    def life_behavior_detail(
        self, 
        payload: str | dict = "", 
        /, 
        base_url: str | Callable[[], str] = "https://webapi.115.com", 
        *, 
        async_: Literal[True], 
        **request_kwargs, 
    ) -> Coroutine[Any, Any, dict]:
        ...
    def life_behavior_detail(
        self, 
        payload: str | dict = "", 
        /, 
        base_url: str | Callable[[], str] = "https://webapi.115.com", 
        *,
        async_: Literal[False, True] = False, 
        **request_kwargs, 
    ) -> dict | Coroutine[Any, Any, dict]:
        """获取 life_list 操作记录明细

        GET https://webapi.115.com/behavior/detail

        .. attention::
            这个接口最多能拉取前 10_000 条数据，且响应速度也较差，请优先使用 ``P115Client.life_behavior_detail_app()``

        .. caution::
            缺乏下面这些事件：

            - 复制文件
            - 文件改名
            - 从回收站还原文件或目录

        :payload:
            - type: str = "" 💡 操作类型，若不指定则是全部

                - "upload_image_file": 1 💡 上传图片
                - "upload_file":       2 💡 上传文件或目录（不包括图片）
                - "star_image":        3 💡 给图片设置星标
                - "star_file":         4 💡 给文件或目录设置星标（不包括图片）
                - "move_image_file":   5 💡 移动图片
                - "move_file":         6 💡 移动文件或目录（不包括图片）
                - "browse_image":      7 💡 浏览图片
                - "browse_video":      8 💡 浏览视频
                - "browse_audio":      9 💡 浏览音频
                - "browse_document":  10 💡 浏览文档
                - "receive_files":    14 💡 接收文件
                - "new_folder":       17 💡 新增目录
                - "copy_folder":      18 💡 复制目录
                - "folder_label":     19 💡 目录设置标签
                - "folder_rename":    20 💡 目录改名
                - "delete_file":      22 💡 删除文件或目录
                - "copy_file":         ? 💡 复制文件（未实现）
                - "rename_file":       ? 💡 文件改名（未实现）

            - limit: int = 32          💡 最大值为 1_000
            - offset: int = 0
            - date: str = <default>    💡 日期，格式为 'YYYY-MM-DD'，若指定则只拉取这一天的数据
        """
        api = complete_url("/behavior/detail", base_url=base_url)
        if isinstance(payload, str):
            payload = {"type": payload}
        payload = {"limit": 32, "offset": 0, **payload}
        return self.request(url=api, params=payload, async_=async_, **request_kwargs)

    @overload
    def life_behavior_detail_app(
        self, 
        payload: str | dict = "", 
        /, 
        app: str = "android", 
        base_url: str | Callable[[], str] = "https://proapi.115.com", 
        *, 
        async_: Literal[False] = False, 
        **request_kwargs, 
    ) -> dict:
        ...
    @overload
    def life_behavior_detail_app(
        self, 
        payload: str | dict = "", 
        /, 
        app: str = "android", 
        base_url: str | Callable[[], str] = "https://proapi.115.com", 
        *, 
        async_: Literal[True], 
        **request_kwargs, 
    ) -> Coroutine[Any, Any, dict]:
        ...
    def life_behavior_detail_app(
        self, 
        payload: str | dict = "", 
        /, 
        app: str = "android", 
        base_url: str | Callable[[], str] = "https://proapi.115.com", 
        *,
        async_: Literal[False, True] = False, 
        **request_kwargs, 
    ) -> dict | Coroutine[Any, Any, dict]:
        """获取 life_list 操作记录明细

        GET https://proapi.115.com/android/behavior/detail

        .. caution::
            缺乏下面这些事件：

            - 复制文件
            - 文件改名
            - 从回收站还原文件或目录

        :payload:
            - type: str = "" 💡 操作类型

                - "upload_image_file": 1 💡 上传图片
                - "upload_file":       2 💡 上传文件或目录（不包括图片）
                - "star_image":        3 💡 给图片设置星标
                - "star_file":         4 💡 给文件或目录设置星标（不包括图片）
                - "move_image_file":   5 💡 移动图片
                - "move_file":         6 💡 移动文件或目录（不包括图片）
                - "browse_image":      7 💡 浏览图片
                - "browse_video":      8 💡 浏览视频
                - "browse_audio":      9 💡 浏览音频
                - "browse_document":  10 💡 浏览文档
                - "receive_files":    14 💡 接收文件
                - "new_folder":       17 💡 新增目录
                - "copy_folder":      18 💡 复制目录
                - "folder_label":     19 💡 目录设置标签
                - "folder_rename":    20 💡 目录改名
                - "delete_file":      22 💡 删除文件或目录
                - "copy_file":         ? 💡 复制文件（未实现）
                - "rename_file":       ? 💡 文件改名（未实现）

            - limit: int = 32          💡 最大值为 1_000
            - offset: int = 0
            - date: str = <default>    💡 日期，格式为 YYYY-MM-DD，若指定则只拉取这一天的数据
        """
        api = complete_url("/behavior/detail", base_url=base_url, app=app)
        if isinstance(payload, str):
            payload = {"type": payload}
        payload = {"limit": 32, "offset": 0, **payload}
        return self.request(url=api, params=payload, async_=async_, **request_kwargs)

    @overload
    def life_behavior_doc_post_app(
        self, 
        payload: int | str | Iterable[int | str] | dict, 
        /, 
        app: str = "android", 
        base_url: str | Callable[[], str] = "https://proapi.115.com", 
        *, 
        async_: Literal[False] = False, 
        **request_kwargs, 
    ) -> dict:
        ...
    @overload
    def life_behavior_doc_post_app(
        self, 
        payload: int | str | Iterable[int | str] | dict, 
        /, 
        app: str = "android", 
        base_url: str | Callable[[], str] = "https://proapi.115.com", 
        *, 
        async_: Literal[True], 
        **request_kwargs, 
    ) -> Coroutine[Any, Any, dict]:
        ...
    def life_behavior_doc_post_app(
        self, 
        payload: int | str | Iterable[int | str] | dict, 
        /, 
        app: str = "android", 
        base_url: str | Callable[[], str] = "https://proapi.115.com", 
        *, 
        async_: Literal[False, True] = False, 
        **request_kwargs, 
    ) -> dict | Coroutine[Any, Any, dict]:
        """推送事件：浏览文档 "browse_document"

        POST https://proapi.115.com/android/files/doc_behavior

        :payload:
            - file_id: int | str
            - file_id[0]: int | str
            - file_id[1]: int | str
            - ...
        """
        api = complete_url("/files/doc_behavior", base_url=base_url, app=app)
        if isinstance(payload, (int, str)):
            payload = {"file_id": payload}
        elif not isinstance(payload, dict):
            payload = {f"file_id[{i}]": fid for i, fid in enumerate(payload)}
        return self.request(url=api, method="POST", data=payload, async_=async_, **request_kwargs)

    @overload
    def life_behavior_img_post_app(
        self, 
        payload: int | str | Iterable[int | str] | dict, 
        /, 
        app: str = "android", 
        base_url: str | Callable[[], str] = "https://proapi.115.com", 
        *, 
        async_: Literal[False] = False, 
        **request_kwargs, 
    ) -> dict:
        ...
    @overload
    def life_behavior_img_post_app(
        self, 
        payload: int | str | Iterable[int | str] | dict, 
        /, 
        app: str = "android", 
        base_url: str | Callable[[], str] = "https://proapi.115.com", 
        *, 
        async_: Literal[True], 
        **request_kwargs, 
    ) -> Coroutine[Any, Any, dict]:
        ...
    def life_behavior_img_post_app(
        self, 
        payload: int | str | Iterable[int | str] | dict, 
        /, 
        app: str = "android", 
        base_url: str | Callable[[], str] = "https://proapi.115.com", 
        *, 
        async_: Literal[False, True] = False, 
        **request_kwargs, 
    ) -> dict | Coroutine[Any, Any, dict]:
        """推送事件：浏览图片 "browse_image"

        POST https://proapi.115.com/android/files/img_behavior

        :payload:
            - file_id: int | str
            - file_id[0]: int | str
            - file_id[1]: int | str
            - ...
        """
        api = complete_url("/files/img_behavior", base_url=base_url, app=app)
        if isinstance(payload, (int, str)):
            payload = {"file_id": payload}
        elif not isinstance(payload, dict):
            payload = {f"file_id[{i}]": fid for i, fid in enumerate(payload)}
        return self.request(url=api, method="POST", data=payload, async_=async_, **request_kwargs)

    @overload
    def life_calendar_getoption(
        self, 
        /, 
        app: str = "web", 
        base_url: str | Callable[[], str] = "https://life.115.com", 
        *, 
        async_: Literal[False] = False, 
        **request_kwargs, 
    ) -> dict:
        ...
    @overload
    def life_calendar_getoption(
        self, 
        /, 
        app: str = "web", 
        base_url: str | Callable[[], str] = "https://life.115.com", 
        *, 
        async_: Literal[True], 
        **request_kwargs, 
    ) -> Coroutine[Any, Any, dict]:
        ...
    def life_calendar_getoption(
        self, 
        /, 
        app: str = "web", 
        base_url: str | Callable[[], str] = "https://life.115.com", 
        *, 
        async_: Literal[False, True] = False, 
        **request_kwargs, 
    ) -> dict | Coroutine[Any, Any, dict]:
        """获取 115 生活的开关设置

        GET https://life.115.com/api/1.0/web/1.0/calendar/getoption

        .. hint::
            app 可以是任意字符串，服务器并不做检查。其他可用 app="web" 的接口可能皆是如此
        """
        api = complete_url(f"/api/1.0/{app}/1.0/calendar/getoption", base_url=base_url)
        return self.request(url=api, async_=async_, **request_kwargs)

    @overload
    def life_calendar_getoption2(
        self, 
        /, 
        app: str = "web", 
        base_url: str | Callable[[], str] = "https://life.115.com", 
        *, 
        async_: Literal[False] = False, 
        **request_kwargs, 
    ) -> dict:
        ...
    @overload
    def life_calendar_getoption2(
        self, 
        /, 
        app: str = "web", 
        base_url: str | Callable[[], str] = "https://life.115.com", 
        *, 
        async_: Literal[True], 
        **request_kwargs, 
    ) -> Coroutine[Any, Any, dict]:
        ...
    def life_calendar_getoption2(
        self, 
        /, 
        app: str = "web", 
        base_url: str | Callable[[], str] = "https://life.115.com", 
        *, 
        async_: Literal[False, True] = False, 
        **request_kwargs, 
    ) -> dict | Coroutine[Any, Any, dict]:
        """获取 115 生活的开关设置

        GET https://life.115.com/api/1.0/web/1.0/calendar/recent_operations_getoption
        """
        api = complete_url(f"/api/1.0/{app}/1.0/calendar/recent_operations_getoption", base_url=base_url)
        return self.request(url=api, async_=async_, **request_kwargs)

    @overload
    def life_calendar_setoption(
        self, 
        payload: Literal[0, 1] | dict = 1, 
        /, 
        app: str = "web", 
        base_url: str | Callable[[], str] = "https://life.115.com", 
        *, 
        async_: Literal[False] = False, 
        **request_kwargs, 
    ) -> dict:
        ...
    @overload
    def life_calendar_setoption(
        self, 
        payload: Literal[0, 1] | dict = 1, 
        /, 
        app: str = "web", 
        base_url: str | Callable[[], str] = "https://life.115.com", 
        *, 
        async_: Literal[True], 
        **request_kwargs, 
    ) -> Coroutine[Any, Any, dict]:
        ...
    def life_calendar_setoption(
        self, 
        payload: Literal[0, 1] | dict = 1, 
        /, 
        app: str = "web", 
        base_url: str | Callable[[], str] = "https://life.115.com", 
        *, 
        async_: Literal[False, True] = False, 
        **request_kwargs, 
    ) -> dict | Coroutine[Any, Any, dict]:
        """设置 115 生活的开关选项

        POST https://life.115.com/api/1.0/web/1.0/calendar/setoption

        :payload:
            - locus: 0 | 1 = 1     💡 开启或关闭最近记录
            - open_life: 0 | 1 = 1 💡 显示或关闭
            - birthday: 0 | 1 = <default>
            - holiday: 0 | 1 = <default>
            - lunar: 0 | 1 = <default>
            - view: 0 | 1 = <default>
            - diary: 0 | 1 = <default>
            - del_notice_item: 0 | 1 = <default>
            - first_week: 0 | 1 = <default>
        """
        api = complete_url(f"/api/1.0/{app}/1.0/calendar/setoption", base_url=base_url)
        if isinstance(payload, dict):
            payload = {"locus": 1, "open_life": 1, **payload}
        else:
            payload = {"locus": 1, "open_life": payload}
        return self.request(url=api, method="POST", data=payload, async_=async_, **request_kwargs)

    @overload
    def life_calendar_setoption2(
        self, 
        payload: Literal[0, 1] | dict = 1, 
        /, 
        app: str = "web", 
        base_url: str | Callable[[], str] = "https://life.115.com", 
        *, 
        async_: Literal[False] = False, 
        **request_kwargs, 
    ) -> dict:
        ...
    @overload
    def life_calendar_setoption2(
        self, 
        payload: Literal[0, 1] | dict = 1, 
        /, 
        app: str = "web", 
        base_url: str | Callable[[], str] = "https://life.115.com", 
        *, 
        async_: Literal[True], 
        **request_kwargs, 
    ) -> Coroutine[Any, Any, dict]:
        ...
    def life_calendar_setoption2(
        self, 
        payload: Literal[0, 1] | dict = 1, 
        /, 
        app: str = "web", 
        base_url: str | Callable[[], str] = "https://life.115.com", 
        *, 
        async_: Literal[False, True] = False, 
        **request_kwargs, 
    ) -> dict | Coroutine[Any, Any, dict]:
        """设置 115 生活的开关选项

        POST https://life.115.com/api/1.0/web/1.0/calendar/recent_operations_setoption

        :payload:
            - locus: 0 | 1 = 1     💡 开启或关闭最近记录
            - open_life: 0 | 1 = 1 💡 显示或关闭
            - birthday: 0 | 1 = <default>
            - holiday: 0 | 1 = <default>
            - lunar: 0 | 1 = <default>
            - view: 0 | 1 = <default>
            - diary: 0 | 1 = <default>
            - del_notice_item: 0 | 1 = <default>
            - first_week: 0 | 1 = <default>
        """
        api = complete_url(f"/api/1.0/{app}/1.0/calendar/recent_operations_setoption", base_url=base_url)
        if isinstance(payload, dict):
            payload = {"locus": 1, "open_life": 1, **payload}
        else:
            payload = {"locus": 1, "open_life": payload}
        return self.request(url=api, method="POST", data=payload, async_=async_, **request_kwargs)

    @overload
    def life_cdlist(
        self, 
        payload: int | dict = {}, 
        /, 
        app: str = "web", 
        base_url: str | Callable[[], str] = "https://life.115.com", 
        *, 
        async_: Literal[False] = False, 
        **request_kwargs, 
    ) -> dict:
        ...
    @overload
    def life_cdlist(
        self, 
        payload: int | dict = {}, 
        /, 
        app: str = "web", 
        base_url: str | Callable[[], str] = "https://life.115.com", 
        *, 
        async_: Literal[True], 
        **request_kwargs, 
    ) -> Coroutine[Any, Any, dict]:
        ...
    def life_cdlist(
        self, 
        payload: int | dict = {}, 
        /, 
        app: str = "web", 
        base_url: str | Callable[[], str] = "https://life.115.com", 
        *, 
        async_: Literal[False, True] = False, 
        **request_kwargs, 
    ) -> dict | Coroutine[Any, Any, dict]:
        """获取节假日等

        GET https://life.115.com/api/1.0/web/1.0/life/cdlist

        :payload:
            - start_time: int = <default>    💡 开始时间戳，单位是秒，默认为当年第一天零点
            - end_time: int = <default>      💡 开始时间戳，单位是秒，默认为次年第一天零点前一秒
            - holiday: 0 | 1 = <default>     💡 是否显示节假日
            - only_public: 0 | 1 = <default>
        """
        api = complete_url(f"/api/1.0/{app}/1.0/life/cdlist", base_url)
        if isinstance(payload, int):
            payload = {"end_time": payload}
        else:
            payload = dict(payload)
        if "start_time" not in payload:
            this_year = date.today().year
            payload["start_time"] = int(datetime(this_year, 1, 1).timestamp())
        if "end_time" not in payload:
            this_year = datetime.fromtimestamp(int(payload["start_time"])).year
            payload["end_time"] = int(datetime(this_year + 1, 1, 1).timestamp()) - 1
        return self.request(url=api, params=payload, async_=async_, **request_kwargs)

    @overload
    def life_get_pic_url(
        self, 
        payload: str | tuple[str, ...] | dict | list, 
        /, 
        app: str = "web", 
        base_url: str | Callable[[], str] = "https://life.115.com", 
        *, 
        async_: Literal[False] = False, 
        **request_kwargs, 
    ) -> dict:
        ...
    @overload
    def life_get_pic_url(
        self, 
        payload: str | tuple[str, ...] | dict | list, 
        /, 
        app: str = "web", 
        base_url: str | Callable[[], str] = "https://life.115.com", 
        *, 
        async_: Literal[True], 
        **request_kwargs, 
    ) -> Coroutine[Any, Any, dict]:
        ...
    def life_get_pic_url(
        self, 
        payload: str | tuple[str, ...] | dict | list, 
        /, 
        app: str = "web", 
        base_url: str | Callable[[], str] = "https://life.115.com", 
        *, 
        async_: Literal[False, True] = False, 
        **request_kwargs, 
    ) -> dict | Coroutine[Any, Any, dict]:
        """批量获取图片的预览图链接

        POST https://life.115.com/api/1.0/web/1.0/imgload/get_pic_url

        .. hint::
            这个接口获取的链接似乎长久有效，而且支持任何文件（只要有人上传过），但限制文件大小在 50 MB 以内

        .. tip::
            在获得的链接最后加上一个 ``&i=1``，就可以获取原始尺寸（但不一定是原图）

        :payload:
            - rs: str 💡 图片的 sha1 （必须大写）或者 f"{oss_bucket}_{oss_object}"（由 `upload_file_image` 接口的响应获得），后者跳转次数更少、响应更快
            - rs[]: str
            - ...
            - rs[0]: str
            - rs[1]: str
            - ...
            - module: int = <default>
            - file_names[]: str = <default>
            - ...
            - type[]: int = <default>
            - ...
        """
        api = complete_url(f"/api/1.0/{app}/1.0/imgload/get_pic_url", base_url=base_url)
        if isinstance(payload, str):
            payload = {"rs": payload}
        elif isinstance(payload, tuple):
            payload = [("rs[]", s) for s in payload]
        return self.request(
            url=api, 
            method="POST", 
            data=payload, 
            async_=async_, 
            **request_kwargs, 
        )

    @overload
    def life_clear_history(
        self, 
        payload: int | dict = 0, 
        /, 
        app: str = "web", 
        base_url: str | Callable[[], str] = "https://life.115.com", 
        *, 
        async_: Literal[False] = False, 
        **request_kwargs, 
    ) -> dict:
        ...
    @overload
    def life_clear_history(
        self, 
        payload: int | dict = 0, 
        /, 
        app: str = "web", 
        base_url: str | Callable[[], str] = "https://life.115.com", 
        *, 
        async_: Literal[True], 
        **request_kwargs, 
    ) -> Coroutine[Any, Any, dict]:
        ...
    def life_clear_history(
        self, 
        payload: int | dict = 0, 
        /, 
        app: str = "web", 
        base_url: str | Callable[[], str] = "https://life.115.com", 
        *, 
        async_: Literal[False, True] = False, 
        **request_kwargs, 
    ) -> dict | Coroutine[Any, Any, dict]:
        """清空操作历史：清空 115 生活事件列表

        POST https://life.115.com/api/1.0/web/1.0/life/life_clear_history

        :payload:
            - tab_type: 0 | 1 = <default>
        """
        api = complete_url(f"/api/1.0/{app}/1.0/life/life_clear_history", base_url=base_url)
        if isinstance(payload, int):
            payload = {"tab_type": 0}
        return self.request(url=api, method="POST", data=payload, async_=async_, **request_kwargs)

    @overload
    def life_glist(
        self, 
        payload: int | dict = 0, 
        /, 
        app: str = "web", 
        base_url: str | Callable[[], str] = "https://life.115.com", 
        *, 
        async_: Literal[False] = False, 
        **request_kwargs, 
    ) -> dict:
        ...
    @overload
    def life_glist(
        self, 
        payload: int | dict = 0, 
        /, 
        app: str = "web", 
        base_url: str | Callable[[], str] = "https://life.115.com", 
        *, 
        async_: Literal[True], 
        **request_kwargs, 
    ) -> Coroutine[Any, Any, dict]:
        ...
    def life_glist(
        self, 
        payload: int | dict = 0, 
        /, 
        app: str = "web", 
        base_url: str | Callable[[], str] = "https://life.115.com", 
        *, 
        async_: Literal[False, True] = False, 
        **request_kwargs, 
    ) -> dict | Coroutine[Any, Any, dict]:
        """获取备忘（记录/笔记/记事）、日记或日程的列表

        GET https://life.115.com/api/1.0/web/1.0/life/glist

        .. note::
            返回数据列表中，每一条都有个 `"type"` 字段，这个和请求参数里面的 `"type"` 含义并不同

            - 2: 备忘
            - 3: 日程
            - 4: 瞬间
            - 5: 日记

        :payload:
            - start: int = 0 💡 开始索引，从 0 开始
            - limit: int = <default> 💡 分页大小
            - type: int = 8 💡 分类：1,6:瞬间 2:日记+日程 3:备忘 4,7:瞬间+备忘 5:日记 8:所有（日记+备忘+日程）
            - only_public: 0 | 1 = <default>
            - msg_note: 0 | 1 = <default>
            - option: 0 | 1 = <default>
        """
        api = complete_url(f"/api/1.0/{app}/1.0/life/glist", base_url)
        if isinstance(payload, int):
            payload = {"start": payload}
        else:
            payload = dict(payload)
        payload.setdefault("type", 8)
        return self.request(url=api, params=payload, async_=async_, **request_kwargs)

    @overload
    def life_has_data(
        self, 
        payload: int | dict = {}, 
        /, 
        app: str = "web", 
        base_url: str | Callable[[], str] = "https://life.115.com", 
        *, 
        async_: Literal[False] = False, 
        **request_kwargs, 
    ) -> dict:
        ...
    @overload
    def life_has_data(
        self, 
        payload: int | dict = {}, 
        /, 
        app: str = "web", 
        base_url: str | Callable[[], str] = "https://life.115.com", 
        *, 
        async_: Literal[True], 
        **request_kwargs, 
    ) -> Coroutine[Any, Any, dict]:
        ...
    def life_has_data(
        self, 
        payload: int | dict = {}, 
        /, 
        app: str = "web", 
        base_url: str | Callable[[], str] = "https://life.115.com", 
        *, 
        async_: Literal[False, True] = False, 
        **request_kwargs, 
    ) -> dict | Coroutine[Any, Any, dict]:
        """获取有数据的那几天零点的时间戳

        GET https://life.115.com/api/1.0/web/1.0/life/life_has_data

        :payload:
            - end_time: int = <default>
            - show_note_cal: 0 | 1 = <default>
            - start_time: int = <default>
        """
        api = complete_url(f"/api/1.0/{app}/1.0/life/life_has_data", base_url=base_url)
        if isinstance(payload, int):
            payload = {"start_time": payload}
        return self.request(url=api, params=payload, async_=async_, **request_kwargs)

    @overload
    def life_list(
        self, 
        payload: int | str | dict = 0, 
        /, 
        app: str = "web", 
        base_url: str | Callable[[], str] = "https://life.115.com", 
        *, 
        async_: Literal[False] = False, 
        **request_kwargs, 
    ) -> dict:
        ...
    @overload
    def life_list(
        self, 
        payload: int | str | dict = 0, 
        /, 
        app: str = "web", 
        base_url: str | Callable[[], str] = "https://life.115.com", 
        *, 
        async_: Literal[True], 
        **request_kwargs, 
    ) -> Coroutine[Any, Any, dict]:
        ...
    def life_list(
        self, 
        payload: int | str | dict = 0, 
        /, 
        app: str = "web", 
        base_url: str | Callable[[], str] = "https://life.115.com", 
        *, 
        async_: Literal[False, True] = False, 
        **request_kwargs, 
    ) -> dict | Coroutine[Any, Any, dict]:
        """罗列登录和增删改操作记录（最新几条）

        GET https://life.115.com/api/1.0/web/1.0/life/life_list

        .. note::
            为了实现分页拉取，需要指定 last_data 参数。只要上次返回的数据不为空，就会有这个值，直接使用即可

        .. hint::
            引用：https://cdnres.115.com/life/m_r/web/static_v11.0/homepage/lifetime.js

            - 'upload_file'          => '上传文件'   💡 上传文件(非图片) 文件类
            - 'upload_image_file'    => '上传图片'   💡 上传文件(图片)   文件类
            - 'backup_album'         => '备份相册'   💡 备份相册         文件类
            - 'sync_communication'   => '同步通讯录' 💡 同步通讯录       文件类
            - 'receive_files'        => '接收文件'   💡 接收文件         文件类
            - 'star_file'            => '星标文件'   💡 星标文件         文件类
            - 'radar_sharing'        => '雷达分享'   💡 雷达分享         文件类
            - 'file_search'          => '文件搜索'   💡 文件搜索         文件类
            - 'move_file'            => '移动文件'   💡 移动文件(非图片) 文件类
            - 'move_image_file'      => '移动图片'   💡 移动文件(图片)   文件类
            - 'browse_document'      => '浏览文档'   💡 浏览文档         信息预览类
            - 'browse_video'         => '浏览视频'   💡 浏览视频         信息预览类
            - 'browse_audio'         => '浏览音频'   💡 浏览音频         信息预览类
            - 'browse_image'         => '浏览图片'   💡 浏览图片         信息预览类
            - 'publish_record'       => '发布记录'   💡 发布记录         信息发布类
            - 'publish_calendar'     => '发布日程'   💡 发布日程         信息发布类
            - 'publish_home'         => '发布传说'   💡 发布传说         信息发布类
            - 'account_security'     => '账号安全'   💡 账号安全         账号安全类

            一些筛选条件::

                - 全部：type=0
                - 上传文件：type=1&file_behavior_type=1
                - 浏览文件：type=1&file_behavior_type=2
                - 星标文件：type=1&file_behavior_type=3
                - 移动文件：type=1&file_behavior_type=4
                - 目录：type=1&file_behavior_type=5
                - 备份：type=1&file_behavior_type=6
                - 删除文件：type=1&file_behavior_type=7
                - 账号安全：type=2
                - 通讯录：type=3
                - 其他：type=99

            一些类型分类::

                .. code:: python

                    {
                        'file':['upload_file', 'upload_image_file', 'backup_album', 'sync_communication', 
                                'receive_files', 'star_file', 'radar_sharing', 'file_search', 'move_file', 
                                'move_image_file', 'star_image', 'del_photo_image', 'del_similar_image', 
                                'generate_smart_albums', 'new_person_albums', 'del_person_albums', 
                                'generate_photo_story', 'share_photo', 'folder_rename', 'folder_label', 
                                'new_folder', 'copy_folder', 'delete_file'],
                        'review':['browse_video', 'browse_document', 'browse_audio', 'browse_image'],
                        'edit':['publish_record', 'publish_calendar', 'publish_home'],
                        'safe':['account_security'],
                        'cloud':[],
                        'share': ['share_contact']
                    }

        :payload:
            - start: int = 0
            - limit: int = 1_000
            - check_num: int = <default> 💡 选中记录数
            - del_data: str = <default> 💡 JSON array，删除时传给接口数据
            - end_time: int = <default> 💡 结束时间戳
            - file_behavior_type: int | str = <default> 💡 筛选类型，有多个则用逗号 ',' 隔开

                - 💡 0: 所有
                - 💡 1: 上传
                - 💡 2: 浏览
                - 💡 3: 星标
                - 💡 4: 移动
                - 💡 5: 标签
                - 💡 6: <UNKNOWN>
                - 💡 7: 删除

            - isPullData: 'true' | 'false' = <default> 💡 是否下拉加载数据
            - isShow: 0 | 1 = <default> 💡 是否显示
            - last_data: str = <default> 💡 JSON object, e.g. '{"last_time":1700000000,"last_count":1,"total_count":200}'
            - mode: str = <default> 💡 操作模式

                - 💡 "show" 展示列表模式
                - 💡 "select": 批量操作模式

            - selectedRecords: str = <default> 💡 JSON array，选中记录 id 数组
            - show_note_cal: 0 | 1 = <default>
            - show_type: int = 0 💡 筛选类型，有多个则用逗号 ',' 隔开

                - 💡 0: 所有
                - 💡 1: 增、删、改、移动、上传、接收、设置标签等文件系统操作
                - 💡 2: 浏览文件
                - 💡 3: <UNKNOWN>
                - 💡 4: account_security

            - start_time: int = <default> 💡 开始时间戳
            - tab_type: int = <default>
            - total_count: int = <default> 💡 列表所有项数
            - type: int = <default> 💡 类型
        """
        api = complete_url(f"/api/1.0/{app}/1.0/life/life_list", base_url=base_url)
        if isinstance(payload, (int, str)):
            payload = {"start": payload}
        payload = {"limit": 1_000, "show_type": 0, "start": 0, **payload}
        return self.request(url=api, params=payload, async_=async_, **request_kwargs)

    @overload
    def life_list2(
        self, 
        payload: int | str | dict = 0, 
        /, 
        app: str = "web", 
        base_url: str | Callable[[], str] = "https://life.115.com", 
        *, 
        async_: Literal[False] = False, 
        **request_kwargs, 
    ) -> dict:
        ...
    @overload
    def life_list2(
        self, 
        payload: int | str | dict = 0, 
        /, 
        app: str = "web", 
        base_url: str | Callable[[], str] = "https://life.115.com", 
        *, 
        async_: Literal[True], 
        **request_kwargs, 
    ) -> Coroutine[Any, Any, dict]:
        ...
    def life_list2(
        self, 
        payload: int | str | dict = 0, 
        /, 
        app: str = "web", 
        base_url: str | Callable[[], str] = "https://life.115.com", 
        *, 
        async_: Literal[False, True] = False, 
        **request_kwargs, 
    ) -> dict | Coroutine[Any, Any, dict]:
        """罗列登录和增删改操作记录（最新几条）

        GET https://life.115.com/api/1.0/web/1.0/life/recent_operations

        .. note::
            为了实现分页拉取，需要指定 last_data 参数。只要上次返回的数据不为空，就会有这个值，直接使用即可

        .. hint::
            引用：https://cdnres.115.com/life/m_r/web/static_v11.0/homepage/lifetime.js

            - 'upload_file'          => '上传文件'   💡 上传文件(非图片) 文件类
            - 'upload_image_file'    => '上传图片'   💡 上传文件(图片)   文件类
            - 'backup_album'         => '备份相册'   💡 备份相册         文件类
            - 'sync_communication'   => '同步通讯录' 💡 同步通讯录       文件类
            - 'receive_files'        => '接收文件'   💡 接收文件         文件类
            - 'star_file'            => '星标文件'   💡 星标文件         文件类
            - 'radar_sharing'        => '雷达分享'   💡 雷达分享         文件类
            - 'file_search'          => '文件搜索'   💡 文件搜索         文件类
            - 'move_file'            => '移动文件'   💡 移动文件(非图片) 文件类
            - 'move_image_file'      => '移动图片'   💡 移动文件(图片)   文件类
            - 'browse_document'      => '浏览文档'   💡 浏览文档         信息预览类
            - 'browse_video'         => '浏览视频'   💡 浏览视频         信息预览类
            - 'browse_audio'         => '浏览音频'   💡 浏览音频         信息预览类
            - 'browse_image'         => '浏览图片'   💡 浏览图片         信息预览类
            - 'publish_record'       => '发布记录'   💡 发布记录         信息发布类
            - 'publish_calendar'     => '发布日程'   💡 发布日程         信息发布类
            - 'publish_home'         => '发布传说'   💡 发布传说         信息发布类
            - 'account_security'     => '账号安全'   💡 账号安全         账号安全类

            一些筛选条件::

                - 全部：type=0
                - 上传文件：type=1&file_behavior_type=1
                - 浏览文件：type=1&file_behavior_type=2
                - 星标文件：type=1&file_behavior_type=3
                - 移动文件：type=1&file_behavior_type=4
                - 目录：type=1&file_behavior_type=5
                - 备份：type=1&file_behavior_type=6
                - 删除文件：type=1&file_behavior_type=7
                - 账号安全：type=2
                - 通讯录：type=3
                - 其他：type=99

            一些类型分类::

                .. code:: python

                    {
                        'file':['upload_file', 'upload_image_file', 'backup_album', 'sync_communication', 
                                'receive_files', 'star_file', 'radar_sharing', 'file_search', 'move_file', 
                                'move_image_file', 'star_image', 'del_photo_image', 'del_similar_image', 
                                'generate_smart_albums', 'new_person_albums', 'del_person_albums', 
                                'generate_photo_story', 'share_photo', 'folder_rename', 'folder_label', 
                                'new_folder', 'copy_folder', 'delete_file'],
                        'review':['browse_video', 'browse_document', 'browse_audio', 'browse_image'],
                        'edit':['publish_record', 'publish_calendar', 'publish_home'],
                        'safe':['account_security'],
                        'cloud':[],
                        'share': ['share_contact']
                    }

        :payload:
            - start: int = 0
            - limit: int = 1_000
            - check_num: int = <default> 💡 选中记录数
            - del_data: str = <default> 💡 JSON array，删除时传给接口数据
            - end_time: int = <default> 💡 结束时间戳
            - file_behavior_type: int | str = <default> 💡 筛选类型，有多个则用逗号 ',' 隔开

                - 💡 0: 所有
                - 💡 1: 上传
                - 💡 2: 浏览
                - 💡 3: 星标
                - 💡 4: 移动
                - 💡 5: 标签
                - 💡 6: <UNKNOWN>
                - 💡 7: 删除

            - isPullData: 'true' | 'false' = <default> 💡 是否下拉加载数据
            - isShow: 0 | 1 = <default> 💡 是否显示
            - last_data: str = <default> 💡 JSON object, e.g. '{"last_time":1700000000,"last_count":1,"total_count":200}'
            - mode: str = <default> 💡 操作模式

                - 💡 "show" 展示列表模式
                - 💡 "select": 批量操作模式

            - selectedRecords: str = <default> 💡 JSON array，选中记录 id 数组
            - show_note_cal: 0 | 1 = <default>
            - show_type: int = 0 💡 筛选类型，有多个则用逗号 ',' 隔开

                - 💡 0: 所有
                - 💡 1: 增、删、改、移动、上传、接收、设置标签等文件系统操作
                - 💡 2: 浏览文件
                - 💡 3: <UNKNOWN>
                - 💡 4: account_security

            - start_time: int = <default> 💡 开始时间戳
            - tab_type: int = <default>
            - total_count: int = <default> 💡 列表所有项数
            - type: int = <default> 💡 类型
        """
        api = complete_url(f"/api/1.0/{app}/1.0/life/recent_operations", base_url=base_url)
        if isinstance(payload, (int, str)):
            payload = {"start": payload}
        payload = {"limit": 1_000, "show_type": 0, "start": 0, **payload}
        return self.request(url=api, params=payload, async_=async_, **request_kwargs)

    @overload
    def life_recent_browse(
        self, 
        payload: int | dict = 0, 
        /, 
        app: str = "web", 
        base_url: str | Callable[[], str] = "https://life.115.com", 
        *, 
        async_: Literal[False] = False, 
        **request_kwargs, 
    ) -> dict:
        ...
    @overload
    def life_recent_browse(
        self, 
        payload: int | dict = 0, 
        /, 
        app: str = "web", 
        base_url: str | Callable[[], str] = "https://life.115.com", 
        *, 
        async_: Literal[True], 
        **request_kwargs, 
    ) -> Coroutine[Any, Any, dict]:
        ...
    def life_recent_browse(
        self, 
        payload: int | dict = 0, 
        /, 
        app: str = "web", 
        base_url: str | Callable[[], str] = "https://life.115.com", 
        *, 
        async_: Literal[False, True] = False, 
        **request_kwargs, 
    ) -> dict | Coroutine[Any, Any, dict]:
        """获取最近浏览记录

        GET https://life.115.com/api/1.0/web/1.0/life/recent_browse

        :payload:
            - start: int = 0
            - limit: int = 1000
        """
        api = complete_url(f"/api/1.0/{app}/1.0/life/recent_browse", base_url=base_url)
        if isinstance(payload, int):
            payload = {"start": payload}
        payload.setdefault("limit", 1000)
        return self.request(url=api, params=payload, async_=async_, **request_kwargs)

    @overload
    def life_set_top(
        self, 
        payload: dict, 
        /, 
        app: str = "web", 
        base_url: str | Callable[[], str] = "https://life.115.com", 
        *, 
        async_: Literal[False] = False, 
        **request_kwargs, 
    ) -> dict:
        ...
    @overload
    def life_set_top(
        self, 
        payload: dict, 
        /, 
        app: str = "web", 
        base_url: str | Callable[[], str] = "https://life.115.com", 
        *, 
        async_: Literal[True], 
        **request_kwargs, 
    ) -> Coroutine[Any, Any, dict]:
        ...
    def life_set_top(
        self, 
        payload: dict, 
        /, 
        app: str = "web", 
        base_url: str | Callable[[], str] = "https://life.115.com", 
        *, 
        async_: Literal[False, True] = False, 
        **request_kwargs, 
    ) -> dict | Coroutine[Any, Any, dict]:
        """切换备忘（记录/笔记/记事）、日记或日程的置顶状态

        GET https://life.115.com/api/1.0/web/1.0/life/set_top

        .. attention::
            这个接口会自动切换记录的置顶状态，但不支持手动指定是否置顶，只是在置顶和不置顶间来回切换。

        :payload:
            - relation_id: int | str 💡 备忘、日程或日记的 id
            - type: int 💡 分类：2:备忘 3:日程 4:瞬间 5:日记
        """
        api = complete_url(f"/api/1.0/{app}/1.0/life/set_top", base_url)
        return self.request(url=api, params=payload, async_=async_, **request_kwargs)

    ########## Login API ##########

    @overload
    def login_app(
        self, 
        /, 
        async_: Literal[False] = False, 
        **request_kwargs, 
    ) -> None | str:
        ...
    @overload
    def login_app(
        self, 
        /, 
        async_: Literal[True], 
        **request_kwargs, 
    ) -> Coroutine[Any, Any, None | str]:
        ...
    def login_app(
        self, 
        /, 
        async_: Literal[False, True] = False, 
        **request_kwargs, 
    ) -> None | str | Coroutine[Any, Any, None | str]:
        """获取当前的登录设备名，如果为 None，说明未能获得
        """
        def gen_step():
            ssoent = self.login_ssoent
            if not ssoent:
                return None
            if ssoent in SSOENT_TO_APP:
                return SSOENT_TO_APP[ssoent]
            device = yield self.login_device(async_=async_, **request_kwargs)
            if device is None:
                return None
            return device["icon"]
        return run_gen_step(gen_step, async_)

    @overload
    def login_open_auth_detail(
        self, 
        payload: int | str | dict, 
        /, 
        app: str = "web", 
        base_url: str | Callable[[], str] = "https://qrcodeapi.115.com", 
        *, 
        async_: Literal[False] = False, 
        **request_kwargs, 
    ) -> dict:
        ...
    @overload
    def login_open_auth_detail(
        self, 
        payload: int | str | dict, 
        /, 
        app: str = "web", 
        base_url: str | Callable[[], str] = "https://qrcodeapi.115.com", 
        *, 
        async_: Literal[True], 
        **request_kwargs, 
    ) -> Coroutine[Any, Any, dict]:
        ...
    def login_open_auth_detail(
        self, 
        payload: int | str | dict, 
        /, 
        app: str = "web", 
        base_url: str | Callable[[], str] = "https://qrcodeapi.115.com", 
        *, 
        async_: Literal[False, True] = False, 
        **request_kwargs, 
    ) -> dict | Coroutine[Any, Any, dict]:
        """获取某个开放应用的授权信息

        GET https://qrcodeapi.115.com/app/1.0/web/1.0/user/getAppAuthDetail

        :payload:
            - auth_id: int | str 💡 授权 id
        """
        api = complete_url(f"/app/1.0/{app}/1.0/user/getAppAuthDetail", base_url=base_url)
        if isinstance(payload, (int, str)):
            payload = {"auth_id": payload}
        return self.request(url=api, params=payload, async_=async_, **request_kwargs)

    @overload
    def login_open_auth_list(
        self, 
        /, 
        app: str = "web", 
        base_url: str | Callable[[], str] = "https://qrcodeapi.115.com", 
        *, 
        async_: Literal[False] = False, 
        **request_kwargs, 
    ) -> dict:
        ...
    @overload
    def login_open_auth_list(
        self, 
        /, 
        app: str = "web", 
        base_url: str | Callable[[], str] = "https://qrcodeapi.115.com", 
        *, 
        async_: Literal[True], 
        **request_kwargs, 
    ) -> Coroutine[Any, Any, dict]:
        ...
    def login_open_auth_list(
        self, 
        /, 
        app: str = "web", 
        base_url: str | Callable[[], str] = "https://qrcodeapi.115.com", 
        *, 
        async_: Literal[False, True] = False, 
        **request_kwargs, 
    ) -> dict | Coroutine[Any, Any, dict]:
        """获取所有授权的开放应用的列表

        GET https://qrcodeapi.115.com/app/1.0/web/1.0/user/getAppAuthList
        """
        api = complete_url(f"/app/1.0/{app}/1.0/user/getAppAuthList", base_url=base_url)
        return self.request(url=api, async_=async_, **request_kwargs)

    @overload
    def login_open_deauth(
        self, 
        payload: int | str | dict, 
        /, 
        app: str = "web", 
        base_url: str | Callable[[], str] = "https://qrcodeapi.115.com", 
        *, 
        async_: Literal[False] = False, 
        **request_kwargs, 
    ) -> dict:
        ...
    @overload
    def login_open_deauth(
        self, 
        payload: int | str | dict, 
        /, 
        app: str = "web", 
        base_url: str | Callable[[], str] = "https://qrcodeapi.115.com", 
        *, 
        async_: Literal[True], 
        **request_kwargs, 
    ) -> Coroutine[Any, Any, dict]:
        ...
    def login_open_deauth(
        self, 
        payload: int | str | dict, 
        /, 
        app: str = "web", 
        base_url: str | Callable[[], str] = "https://qrcodeapi.115.com", 
        *, 
        async_: Literal[False, True] = False, 
        **request_kwargs, 
    ) -> dict | Coroutine[Any, Any, dict]:
        """取消某个开放应用的授权

        GET https://qrcodeapi.115.com/app/1.0/web/1.0/user/deauthApp

        :payload:
            - auth_id: int | str 💡 授权 id
        """
        api = complete_url(f"/app/1.0/{app}/1.0/user/deauthApp", base_url=base_url)
        if isinstance(payload, (int, str)):
            payload = {"auth_id": payload}
        return self.request(url=api, method="POST", data=payload, async_=async_, **request_kwargs)

    @overload
    def login_check_sso(
        self, 
        /, 
        app: str = "web", 
        base_url: str | Callable[[], str] = "https://qrcodeapi.115.com", 
        *, 
        async_: Literal[False] = False, 
        **request_kwargs, 
    ) -> dict:
        ...
    @overload
    def login_check_sso(
        self, 
        /, 
        app: str = "web", 
        base_url: str | Callable[[], str] = "https://qrcodeapi.115.com", 
        *, 
        async_: Literal[True], 
        **request_kwargs, 
    ) -> Coroutine[Any, Any, dict]:
        ...
    def login_check_sso(
        self, 
        /, 
        app: str = "web", 
        base_url: str | Callable[[], str] = "https://qrcodeapi.115.com", 
        *, 
        async_: Literal[False, True] = False, 
        **request_kwargs, 
    ) -> dict | Coroutine[Any, Any, dict]:
        """检查当前 cookies 的登录状态信息，并且自最近一次登录的 60 秒后，使当前设备下除最近一次登录外的所有 cookies 失效

        GET https://qrcodeapi.115.com/app/1.0/web/1.0/check/sso
        """
        api = complete_url(f"/app/1.0/{app}/1.0/check/sso", base_url=base_url)
        return self.request(url=api, async_=async_, **request_kwargs)

    @overload
    def login_device(
        self, 
        /, 
        async_: Literal[False] = False, 
        **request_kwargs, 
    ) -> None | dict:
        ...
    @overload
    def login_device(
        self, 
        /, 
        async_: Literal[True], 
        **request_kwargs, 
    ) -> Coroutine[Any, Any, None | dict]:
        ...
    def login_device(
        self, 
        /, 
        async_: Literal[False, True] = False, 
        **request_kwargs, 
    ) -> None | dict | Coroutine[Any, Any, None | dict]:
        """获取当前的登录设备的信息，如果为 None，也不代表当前的 cookies 被下线，只能说明有更晚的登录到同一设备
        """
        def parse(_, content: bytes, /) -> None | dict:
            login_devices = json_loads(content)
            if not login_devices["state"]:
                return None
            return next(filter(cast(Callable, itemgetter("is_current")), login_devices["data"]["list"]), None)
        request_kwargs.setdefault("parse", parse)
        return self.login_devices(async_=async_, **request_kwargs)

    @overload
    def login_devices(
        self, 
        /, 
        app: str = "web", 
        base_url: str | Callable[[], str] = "https://qrcodeapi.115.com", 
        *, 
        async_: Literal[False] = False, 
        **request_kwargs, 
    ) -> dict:
        ...
    @overload
    def login_devices(
        self, 
        /, 
        app: str = "web", 
        base_url: str | Callable[[], str] = "https://qrcodeapi.115.com", 
        *, 
        async_: Literal[True], 
        **request_kwargs, 
    ) -> Coroutine[Any, Any, dict]:
        ...
    def login_devices(
        self, 
        /, 
        app: str = "web", 
        base_url: str | Callable[[], str] = "https://qrcodeapi.115.com", 
        *, 
        async_: Literal[False, True] = False, 
        **request_kwargs, 
    ) -> dict | Coroutine[Any, Any, dict]:
        """获取所有的已登录设备的信息，不过当前的 cookies 必须是登录状态（未退出或未失效）

        GET https://qrcodeapi.115.com/app/1.0/web/1.0/login_log/login_devices
        """
        api = complete_url(f"/app/1.0/{app}/1.0/login_log/login_devices", base_url=base_url)
        return self.request(url=api, async_=async_, **request_kwargs)

    @overload
    def login_info(
        self, 
        /, 
        app: str = "android", 
        base_url: str | Callable[[], str] = "https://proapi.115.com", 
        *, 
        async_: Literal[False] = False, 
        **request_kwargs, 
    ) -> dict:
        ...
    @overload
    def login_info(
        self, 
        /, 
        app: str = "android", 
        base_url: str | Callable[[], str] = "https://proapi.115.com", 
        *, 
        async_: Literal[True], 
        **request_kwargs, 
    ) -> Coroutine[Any, Any, dict]:
        ...
    def login_info(
        self, 
        /, 
        app: str = "android", 
        base_url: str | Callable[[], str] = "https://proapi.115.com", 
        *, 
        async_: Literal[False, True] = False, 
        **request_kwargs, 
    ) -> dict | Coroutine[Any, Any, dict]:
        """获取登录信息

        GET https://proapi.115.com/android/2.0/login_info
        """
        api = complete_url("/2.0/login_info", base_url=base_url, app=app)
        return self.request(url=api, async_=async_, **request_kwargs)

    @overload
    def login_log(
        self, 
        payload: dict = {}, 
        /, 
        app: str = "web", 
        base_url: str | Callable[[], str] = "https://qrcodeapi.115.com", 
        *, 
        async_: Literal[False] = False, 
        **request_kwargs, 
    ) -> dict:
        ...
    @overload
    def login_log(
        self, 
        payload: dict = {}, 
        /, 
        app: str = "web", 
        base_url: str | Callable[[], str] = "https://qrcodeapi.115.com", 
        *, 
        async_: Literal[True], 
        **request_kwargs, 
    ) -> Coroutine[Any, Any, dict]:
        ...
    def login_log(
        self, 
        payload: dict = {}, 
        /, 
        app: str = "web", 
        base_url: str | Callable[[], str] = "https://qrcodeapi.115.com", 
        *, 
        async_: Literal[False, True] = False, 
        **request_kwargs, 
    ) -> dict | Coroutine[Any, Any, dict]:
        """获取登录信息日志列表

        GET https://qrcodeapi.115.com/app/1.0/web/1.0/login_log/log

        :payload:
            - start: int = 0
            - limit: int = 100
        """
        api = complete_url(f"/app/1.0/{app}/1.0/login_log/log", base_url=base_url)
        payload = {"start": 0, "limit": 100, **payload}
        return self.request(url=api, params=payload, async_=async_, **request_kwargs)

    @overload
    def login_online(
        self, 
        /, 
        app: str = "web", 
        base_url: str | Callable[[], str] = "https://qrcodeapi.115.com", 
        *, 
        async_: Literal[False] = False, 
        **request_kwargs, 
    ) -> dict:
        ...
    @overload
    def login_online(
        self, 
        /, 
        app: str = "web", 
        base_url: str | Callable[[], str] = "https://qrcodeapi.115.com", 
        *, 
        async_: Literal[True], 
        **request_kwargs, 
    ) -> Coroutine[Any, Any, dict]:
        ...
    def login_online(
        self, 
        /, 
        app: str = "web", 
        base_url: str | Callable[[], str] = "https://qrcodeapi.115.com", 
        *, 
        async_: Literal[False, True] = False, 
        **request_kwargs, 
    ) -> dict | Coroutine[Any, Any, dict]:
        """当前登录的设备总数和最近登录的设备

        GET https://qrcodeapi.115.com/app/1.0/web/1.0/login_log/login_online
        """
        api = complete_url(f"/app/1.0/{app}/1.0/login_log/login_online", base_url=base_url)
        return self.request(url=api, async_=async_, **request_kwargs)

    @overload
    def login_status(
        self, 
        /, 
        base_url: str | Callable[[], str] = "https://my.115.com", 
        *, 
        async_: Literal[False] = False, 
        **request_kwargs, 
    ) -> bool:
        ...
    @overload
    def login_status(
        self, 
        /, 
        base_url: str | Callable[[], str] = "https://my.115.com", 
        *, 
        async_: Literal[True], 
        **request_kwargs, 
    ) -> Coroutine[Any, Any, bool]:
        ...
    def login_status(
        self, 
        /, 
        base_url: str | Callable[[], str] = "https://my.115.com", 
        *, 
        async_: Literal[False, True] = False, 
        **request_kwargs, 
    ) -> bool | Coroutine[Any, Any, bool]:
        """检查是否已登录

        GET https://my.115.com/?ct=guide&ac=status
        """
        api = complete_url(base_url=base_url, query={"ct": "guide", "ac": "status"})
        def parse(_, content: bytes, /) -> bool:
            try:
                return json_loads(content)["state"]
            except:
                return False
        request_kwargs.setdefault("parse", parse)
        return self.request(url=api, async_=async_, **request_kwargs)

    @property
    def login_ssoent(self, /) -> str:
        """获取当前的登录设备 ssoent，如果为空，说明未能获得（会直接获取 Cookies 中名为 UID 字段的值，所以即使能获取，也不能说明登录未失效）
        """
        return self.cookies_str.login_ssoent

    ########## Logout API ##########

    @overload
    def logout_by_app(
        self, 
        /, 
        app: None | str = None, 
        base_url: str | Callable[[], str] = "https://qrcodeapi.115.com", 
        *, 
        async_: Literal[False] = False, 
        **request_kwargs, 
    ) -> None:
        ...
    @overload
    def logout_by_app(
        self, 
        /, 
        app: None | str = None, 
        base_url: str | Callable[[], str] = "https://qrcodeapi.115.com", 
        *, 
        async_: Literal[True], 
        **request_kwargs, 
    ) -> Coroutine[Any, Any, None]:
        ...
    def logout_by_app(
        self, 
        /, 
        app: None | str = None, 
        base_url: str | Callable[[], str] = "https://qrcodeapi.115.com", 
        *, 
        async_: Literal[False, True] = False, 
        **request_kwargs, 
    ) -> None | Coroutine[Any, Any, None]:
        """退出登录状态（可以把某个客户端下线，所有已登录设备可从 `login_devices` 获取）

        GET https://qrcodeapi.115.com/app/1.0/{app}/1.0/logout/logout

        :param app: 退出登录的 app

        -----

        :设备列表如下:

        +-------+----------+------------+----------------------+
        | No.   | ssoent   | app        | description          |
        +=======+==========+============+======================+
        | 01    | A1       | web        | 115生活_网页端       |
        +-------+----------+------------+----------------------+
        | --    | A1       | desktop    | 115浏览器            |
        +-------+----------+------------+----------------------+
        | --    | A2       | ?          | 未知: android        |
        +-------+----------+------------+----------------------+
        | --    | A3       | ?          | 未知: ios            |
        +-------+----------+------------+----------------------+
        | --    | A4       | ?          | 未知: ipad           |
        +-------+----------+------------+----------------------+
        | --    | B1       | ?          | 未知: android        |
        +-------+----------+------------+----------------------+
        | 02    | D1       | ios        | 115生活_苹果端       |
        +-------+----------+------------+----------------------+
        | 03    | D2       | bios       | 未知: ios            |
        +-------+----------+------------+----------------------+
        | 04    | D3       | 115ios     | 115_苹果端           |
        +-------+----------+------------+----------------------+
        | 05    | F1       | android    | 115生活_安卓端       |
        +-------+----------+------------+----------------------+
        | 06    | F2       | bandroid   | 未知: android        |
        +-------+----------+------------+----------------------+
        | 07    | F3       | 115android | 115_安卓端           |
        +-------+----------+------------+----------------------+
        | 08    | H1       | ipad       | 115生活_苹果平板端   |
        +-------+----------+------------+----------------------+
        | 09    | H2       | bipad      | 未知: ipad           |
        +-------+----------+------------+----------------------+
        | 10    | H3       | 115ipad    | 115_苹果平板端       |
        +-------+----------+------------+----------------------+
        | 11    | I1       | tv         | 115生活_安卓电视端   |
        +-------+----------+------------+----------------------+
        | 12    | I2       | apple_tv   | 115生活_苹果电视端   |
        +-------+----------+------------+----------------------+
        | 13    | M1       | qandriod   | 115管理_安卓端       |
        +-------+----------+------------+----------------------+
        | 14    | N1       | qios       | 115管理_苹果端       |
        +-------+----------+------------+----------------------+
        | 15    | O1       | qipad      | 115管理_苹果平板端   |
        +-------+----------+------------+----------------------+
        | 16    | P1       | os_windows | 115生活_Windows端    |
        +-------+----------+------------+----------------------+
        | 17    | P2       | os_mac     | 115生活_macOS端      |
        +-------+----------+------------+----------------------+
        | 18    | P3       | os_linux   | 115生活_Linux端      |
        +-------+----------+------------+----------------------+
        | 19    | R1       | wechatmini | 115生活_微信小程序端 |
        +-------+----------+------------+----------------------+
        | 20    | R2       | alipaymini | 115生活_支付宝小程序 |
        +-------+----------+------------+----------------------+
        | 21    | S1       | harmony    | 115_鸿蒙端           |
        +-------+----------+------------+----------------------+
        """
        def gen_step():
            nonlocal app
            if app is None:
                app = yield self.login_app(async_=async_)
            if app == "desktop":
                app = "web"
            api = complete_url(f"/app/1.0/{app}/1.0/logout/logout", base_url=base_url)
            request_kwargs.setdefault("parse", lambda *a: None)
            return self.request(url=api, async_=async_, **request_kwargs)
        return run_gen_step(gen_step, async_)

    @overload
    def logout_by_ssoent(
        self, 
        payload: None | str | dict = None, 
        /, 
        app: str = "web", 
        base_url: str | Callable[[], str] = "https://qrcodeapi.115.com", 
        *, 
        async_: Literal[False] = False, 
        **request_kwargs, 
    ) -> dict:
        ...
    @overload
    def logout_by_ssoent(
        self, 
        payload: None | str | dict = None, 
        /, 
        app: str = "web", 
        base_url: str | Callable[[], str] = "https://qrcodeapi.115.com", 
        *, 
        async_: Literal[True], 
        **request_kwargs, 
    ) -> Coroutine[Any, Any, dict]:
        ...
    def logout_by_ssoent(
        self, 
        payload: None | str | dict = None, 
        /, 
        app: str = "web", 
        base_url: str | Callable[[], str] = "https://qrcodeapi.115.com", 
        *, 
        async_: Literal[False, True] = False, 
        **request_kwargs, 
    ) -> dict | Coroutine[Any, Any, dict]:
        """退出登录状态（可以把某个客户端下线，所有已登录设备可从 `login_devices` 获取）

        POST https://qrcodeapi.115.com/app/1.0/web/1.0/logout/mange

        :payload:
            - ssoent: str

        -----

        :设备列表如下:

        +-------+----------+------------+----------------------+
        | No.   | ssoent   | app        | description          |
        +=======+==========+============+======================+
        | 01    | A1       | web        | 115生活_网页端       |
        +-------+----------+------------+----------------------+
        | --    | A1       | desktop    | 115浏览器            |
        +-------+----------+------------+----------------------+
        | --    | A2       | ?          | 未知: android        |
        +-------+----------+------------+----------------------+
        | --    | A3       | ?          | 未知: ios            |
        +-------+----------+------------+----------------------+
        | --    | A4       | ?          | 未知: ipad           |
        +-------+----------+------------+----------------------+
        | --    | B1       | ?          | 未知: android        |
        +-------+----------+------------+----------------------+
        | 02    | D1       | ios        | 115生活_苹果端       |
        +-------+----------+------------+----------------------+
        | 03    | D2       | bios       | 未知: ios            |
        +-------+----------+------------+----------------------+
        | 04    | D3       | 115ios     | 115_苹果端           |
        +-------+----------+------------+----------------------+
        | 05    | F1       | android    | 115生活_安卓端       |
        +-------+----------+------------+----------------------+
        | 06    | F2       | bandroid   | 未知: android        |
        +-------+----------+------------+----------------------+
        | 07    | F3       | 115android | 115_安卓端           |
        +-------+----------+------------+----------------------+
        | 08    | H1       | ipad       | 115生活_苹果平板端   |
        +-------+----------+------------+----------------------+
        | 09    | H2       | bipad      | 未知: ipad           |
        +-------+----------+------------+----------------------+
        | 10    | H3       | 115ipad    | 115_苹果平板端       |
        +-------+----------+------------+----------------------+
        | 11    | I1       | tv         | 115生活_安卓电视端   |
        +-------+----------+------------+----------------------+
        | 12    | I2       | apple_tv   | 115生活_苹果电视端   |
        +-------+----------+------------+----------------------+
        | 13    | M1       | qandriod   | 115管理_安卓端       |
        +-------+----------+------------+----------------------+
        | 14    | N1       | qios       | 115管理_苹果端       |
        +-------+----------+------------+----------------------+
        | 15    | O1       | qipad      | 115管理_苹果平板端   |
        +-------+----------+------------+----------------------+
        | 16    | P1       | os_windows | 115生活_Windows端    |
        +-------+----------+------------+----------------------+
        | 17    | P2       | os_mac     | 115生活_macOS端      |
        +-------+----------+------------+----------------------+
        | 18    | P3       | os_linux   | 115生活_Linux端      |
        +-------+----------+------------+----------------------+
        | 19    | R1       | wechatmini | 115生活_微信小程序端 |
        +-------+----------+------------+----------------------+
        | 20    | R2       | alipaymini | 115生活_支付宝小程序 |
        +-------+----------+------------+----------------------+
        | 21    | S1       | harmony    | 115_鸿蒙端           |
        +-------+----------+------------+----------------------+
        """
        api = complete_url(f"/app/1.0/{app}/1.0/logout/mange", base_url=base_url)
        if payload is None:
            payload = {"ssoent": self.login_ssoent or ""}
        elif isinstance(payload, str):
            payload = {"ssoent": payload}
        return self.request(url=api, method="POST", data=payload, async_=async_, **request_kwargs)

    ########## Message API ##########

    @overload
    def msg_contacts_ls(
        self, 
        payload: int | str | dict = 0, 
        /, 
        base_url: str | Callable[[], str] = "https://pmsg.115.com", 
        *, 
        async_: Literal[False] = False, 
        **request_kwargs, 
    ) -> dict:
        ...
    @overload
    def msg_contacts_ls(
        self, 
        payload: int | str | dict = 0, 
        /, 
        base_url: str | Callable[[], str] = "https://pmsg.115.com", 
        *, 
        async_: Literal[True], 
        **request_kwargs, 
    ) -> Coroutine[Any, Any, dict]:
        ...
    def msg_contacts_ls(
        self, 
        payload: int | str | dict = 0, 
        /, 
        base_url: str | Callable[[], str] = "https://pmsg.115.com", 
        *, 
        async_: Literal[False, True] = False, 
        **request_kwargs, 
    ) -> dict | Coroutine[Any, Any, dict]:
        """获取提示消息

        GET https://pmsg.115.com/api/1.0/app/1.0/contact/ls

        :payload:
            - limit: int = 115
            - skip: int = 0
            - t: 0 | 1 = 1
        """
        api = complete_url("/api/1.0/app/1.0/contact/ls", base_url=base_url)
        if isinstance(payload, (int, str)):
            payload = {"skip": payload}
        payload = {"limit": 115, "t": 1, "skip": 0, **payload}
        return self.request(url=api, params=payload, async_=async_, **request_kwargs)

    @overload
    def msg_contacts_notice(
        self, 
        /, 
        base_url: str | Callable[[], str] = "https://msg.115.com", 
        *, 
        async_: Literal[False] = False, 
        **request_kwargs, 
    ) -> dict:
        ...
    @overload
    def msg_contacts_notice(
        self, 
        /, 
        base_url: str | Callable[[], str] = "https://msg.115.com", 
        *, 
        async_: Literal[True], 
        **request_kwargs, 
    ) -> Coroutine[Any, Any, dict]:
        ...
    def msg_contacts_notice(
        self, 
        /, 
        base_url: str | Callable[[], str] = "https://msg.115.com", 
        *, 
        async_: Literal[False, True] = False, 
        **request_kwargs, 
    ) -> dict | Coroutine[Any, Any, dict]:
        """获取提示消息

        GET https://msg.115.com/?ct=contacts&ac=notice&client=web
        """
        api = complete_url(base_url=base_url, query={"ct": "contacts", "ac": "notice", "client": "web"})
        return self.request(url=api, async_=async_, **request_kwargs)

    @overload
    def msg_get_websocket_host(
        self, 
        /, 
        base_url: str | Callable[[], str] = "https://msg.115.com", 
        *, 
        async_: Literal[False] = False, 
        **request_kwargs, 
    ) -> dict:
        ...
    @overload
    def msg_get_websocket_host(
        self, 
        /, 
        base_url: str | Callable[[], str] = "https://msg.115.com", 
        *, 
        async_: Literal[True], 
        **request_kwargs, 
    ) -> Coroutine[Any, Any, dict]:
        ...
    def msg_get_websocket_host(
        self, 
        /, 
        base_url: str | Callable[[], str] = "https://msg.115.com", 
        *, 
        async_: Literal[False, True] = False, 
        **request_kwargs, 
    ) -> dict | Coroutine[Any, Any, dict]:
        """获取 websocket 链接

        GET https://msg.115.com/?ct=im&ac=get_websocket_host

        .. note::
            用返回数据构造链接，可由此监听 websocket 消息

            `wss://{server}/?uid={user_id}&session={session_id}&client_version=100&client_type=5&sequence_id=0&source=web&device_id=0000000000000000000000000000000000000000`
        """
        api = complete_url(base_url=base_url, query={"ct": "im", "ac": "get_websocket_host"})
        return self.request(url=api, async_=async_, **request_kwargs)

    ########## Multimedia API ##########

    @overload
    def multimedia_collection_listen(
        self, 
        payload: int | dict = 0, 
        /, 
        base_url: str | Callable[[], str] = "https://webapi.115.com", 
        *, 
        async_: Literal[False] = False, 
        **request_kwargs, 
    ) -> dict:
        ...
    @overload
    def multimedia_collection_listen(
        self, 
        payload: int | dict = 0, 
        /, 
        base_url: str | Callable[[], str] = "https://webapi.115.com", 
        *, 
        async_: Literal[True], 
        **request_kwargs, 
    ) -> Coroutine[Any, Any, dict]:
        ...
    def multimedia_collection_listen(
        self, 
        payload: int | dict = 0, 
        /, 
        base_url: str | Callable[[], str] = "https://webapi.115.com", 
        *, 
        async_: Literal[False, True] = False, 
        **request_kwargs, 
    ) -> dict | Coroutine[Any, Any, dict]:
        """我听：自建听单（合集）列表

        GET https://webapi.115.com/multimedia/collection_listen

        .. todo::
            暂不清楚 `sort` 字段各个取值的含义

        :payload:
            - channel_id: int = 1
            - limit: int = 32
            - offset: int = 0
            - sort: int = <default> 💡 排序依据
            - asc: 0 | 1 = <default> 💡 是否升序排列
        """
        api = complete_url("/multimedia/collection_listen", base_url=base_url)
        if isinstance(payload, int):
            payload = {"offset": payload}
        payload = {"channel_id": 1, "limit": 32, **payload}
        return self.request(url=api, params=payload, async_=async_, **request_kwargs)

    @overload
    def multimedia_collection_listen_set(
        self, 
        payload: int | dict, 
        /, 
        base_url: str | Callable[[], str] = "https://webapi.115.com", 
        *, 
        async_: Literal[False] = False, 
        **request_kwargs, 
    ) -> dict:
        ...
    @overload
    def multimedia_collection_listen_set(
        self, 
        payload: int | dict, 
        /, 
        base_url: str | Callable[[], str] = "https://webapi.115.com", 
        *, 
        async_: Literal[True], 
        **request_kwargs, 
    ) -> Coroutine[Any, Any, dict]:
        ...
    def multimedia_collection_listen_set(
        self, 
        payload: int | dict, 
        /, 
        base_url: str | Callable[[], str] = "https://webapi.115.com", 
        *, 
        async_: Literal[False, True] = False, 
        **request_kwargs, 
    ) -> dict | Coroutine[Any, Any, dict]:
        """我听：设置听单（合集）

        POST https://webapi.115.com/multimedia/collection_listen

        :payload:
            - multimedia_id: int 💡 专辑（详情） id
            - channel_id: int = 1
            - collection: 0 | 1 = 1 💡 是否设为合集：0:取消 1:设置（设为合集后，该内容将出现在【自建听单】列表中）
        """
        api = complete_url("/multimedia/collection_listen", base_url=base_url)
        if isinstance(payload, int):
            payload = {"multimedia_id": payload}
        payload = {"channel_id": 1, "collection": 1, **payload}
        return self.request(url=api, method="POST", data=payload, async_=async_, **request_kwargs)

    @overload
    def multimedia_collection_watch(
        self, 
        payload: int | dict = 0, 
        /, 
        base_url: str | Callable[[], str] = "https://webapi.115.com", 
        *, 
        async_: Literal[False] = False, 
        **request_kwargs, 
    ) -> dict:
        ...
    @overload
    def multimedia_collection_watch(
        self, 
        payload: int | dict = 0, 
        /, 
        base_url: str | Callable[[], str] = "https://webapi.115.com", 
        *, 
        async_: Literal[True], 
        **request_kwargs, 
    ) -> Coroutine[Any, Any, dict]:
        ...
    def multimedia_collection_watch(
        self, 
        payload: int | dict = 0, 
        /, 
        base_url: str | Callable[[], str] = "https://webapi.115.com", 
        *, 
        async_: Literal[False, True] = False, 
        **request_kwargs, 
    ) -> dict | Coroutine[Any, Any, dict]:
        """我看：自建合集列表

        GET https://webapi.115.com/multimedia/collection_watch

        .. todo::
            暂不清楚 `sort` 字段各个取值的含义

        :payload:
            - channel_id: int = 5
            - limit: int = 32
            - offset: int = 0
            - sort: int = <default> 💡 排序依据
            - asc: 0 | 1 = <default> 💡 是否升序排列
        """
        api = complete_url("/multimedia/collection_watch", base_url=base_url)
        if isinstance(payload, int):
            payload = {"offset": payload}
        payload = {"channel_id": 5, "limit": 32, **payload}
        return self.request(url=api, params=payload, async_=async_, **request_kwargs)

    @overload
    def multimedia_collection_watch_set(
        self, 
        payload: int | dict, 
        /, 
        base_url: str | Callable[[], str] = "https://webapi.115.com", 
        *, 
        async_: Literal[False] = False, 
        **request_kwargs, 
    ) -> dict:
        ...
    @overload
    def multimedia_collection_watch_set(
        self, 
        payload: int | dict, 
        /, 
        base_url: str | Callable[[], str] = "https://webapi.115.com", 
        *, 
        async_: Literal[True], 
        **request_kwargs, 
    ) -> Coroutine[Any, Any, dict]:
        ...
    def multimedia_collection_watch_set(
        self, 
        payload: int | dict, 
        /, 
        base_url: str | Callable[[], str] = "https://webapi.115.com", 
        *, 
        async_: Literal[False, True] = False, 
        **request_kwargs, 
    ) -> dict | Coroutine[Any, Any, dict]:
        """我看：设置合集

        POST https://webapi.115.com/multimedia/collection_watch

        :payload:
            - multimedia_id: int 💡 专辑（详情） id
            - channel_id: int = 5
            - collection: 0 | 1 = 1 💡 是否设为合集：0:取消 1:设置（设为合集后，该内容将出现在自建合集列表中）
        """
        api = complete_url("/multimedia/collection_watch", base_url=base_url)
        if isinstance(payload, int):
            payload = {"multimedia_id": payload}
        payload = {"channel_id": 5, "collection": 1, **payload}
        return self.request(url=api, method="POST", data=payload, async_=async_, **request_kwargs)

    @overload
    def multimedia_listen(
        self, 
        payload: int | dict = 0, 
        /, 
        base_url: str | Callable[[], str] = "https://webapi.115.com", 
        *, 
        async_: Literal[False] = False, 
        **request_kwargs, 
    ) -> dict:
        ...
    @overload
    def multimedia_listen(
        self, 
        payload: int | dict = 0, 
        /, 
        base_url: str | Callable[[], str] = "https://webapi.115.com", 
        *, 
        async_: Literal[True], 
        **request_kwargs, 
    ) -> Coroutine[Any, Any, dict]:
        ...
    def multimedia_listen(
        self, 
        payload: int | dict = 0, 
        /, 
        base_url: str | Callable[[], str] = "https://webapi.115.com", 
        *, 
        async_: Literal[False, True] = False, 
        **request_kwargs, 
    ) -> dict | Coroutine[Any, Any, dict]:
        """我听：专辑（详情）列表 或 专辑（详情）的基本信息和文件列表

        GET https://webapi.115.com/multimedia/listen

        .. note::
            - 指定 `multimedia_id`，则罗列此专辑（详情）的基本信息和文件列表
            - 指定 `parent_id`，则罗列关联此 id 的专辑（详情）列表
            - 都不指定，则罗列所有专辑（详情）列表

        .. todo::
            暂不清楚 `sort` 字段各个取值的含义

        .. todo::
            暂不清楚 `date` 字段的格式要求

        .. todo::
            应该还可以选择【维度】和【时间区间】，但是目前 115 的网页版还未完成此功能

        .. note::
            一个 multimedia_id 对应的专辑被称为详情，如果它还关联到其它 multimedia_id，也就是它们的 parent_id，或者被主动【设为合集】，称为合集

        :payload:
            - channel_id: int = 1
            - parent_id: int = <default> 💡 关联的专辑（详情） id
            - multimedia_id: int = <default> 💡 专辑（详情） id
            - limit: int = <default> 💡 最多返回数量
            - offset: int = <default> 💡 索引偏移，索引从 0 开始计算
            - sort: int = <default> 💡 排序依据
            - asc: 0 | 1 = <default> 💡 是否升序排列
            - visit_type: int = <default> 💡 已知：0:全部 1:已听 2:未听
            - type_id: int = <default> 💡 分类 id
            - related_name: str = <default> 💡 相关人员名称
            - collection: 0 | 1 = <default> 💡 内容类型：<default>:全部 0:属性 1:合集
            - date: str = <default> 💡 日期、月份或者年份
        """
        api = complete_url("/multimedia/listen", base_url=base_url)
        if isinstance(payload, int):
            payload = {"multimedia_id": payload}
        payload = {"channel_id": 1, "limit": 32, **payload}
        return self.request(url=api, params=payload, async_=async_, **request_kwargs)

    @overload
    def multimedia_listen_update(
        self, 
        payload: dict, 
        /, 
        base_url: str | Callable[[], str] = "https://webapi.115.com", 
        *, 
        async_: Literal[False] = False, 
        **request_kwargs, 
    ) -> dict:
        ...
    @overload
    def multimedia_listen_update(
        self, 
        payload: dict, 
        /, 
        base_url: str | Callable[[], str] = "https://webapi.115.com", 
        *, 
        async_: Literal[True], 
        **request_kwargs, 
    ) -> Coroutine[Any, Any, dict]:
        ...
    def multimedia_listen_update(
        self, 
        payload: dict | list, 
        /, 
        base_url: str | Callable[[], str] = "https://webapi.115.com", 
        *, 
        async_: Literal[False, True] = False, 
        **request_kwargs, 
    ) -> dict | Coroutine[Any, Any, dict]:
        """我听：更新专辑（详情）

        POST https://webapi.115.com/multimedia/listen

        :payload:
            - multimedia_id: int 💡 专辑（详情） id
            - channel_id: int = 1
            - parent_id: int = <default> 💡 关联的专辑（详情） id（作为当前专辑（详情）的上级）
            - custom_sort: int = <default> 💡 自定义排序
            - title: str = <default> 💡 标题
            - description: str = <default> 💡 简介
            - cover: str = <default> 💡 封面图片的提取码
            - country: str = <default> 💡 国家/地区
            - language: str = <default> 💡 语言，多个用逗号 "," 隔开
            - release_date: str = <default> 💡 发行日期，格式为 YYYY-MM-DD
            - type_id: int | str = <default> 💡 类型 id
            - type_id[]: int | str
            - ...
            - type_id[0]: int | str
            - type_id[1]: int | str
            - ...
            - related_id[][{related_id}]: str 💡 相关人员，是 id 到 名字 的映射关系
            - ...
            - rating[1]: int | float | str = <default> 💡 评分：豆瓣
            - rating[2]: int | float | str = <default> 💡 评分：猫眼
            - rating[3]: int | float | str = <default> 💡 评分：烂番茄
            - rating[4]: int | float | str = <default> 💡 评分：优酷
            - rating[5]: int | float | str = <default> 💡 评分：115
            - rating[6]: int | float | str = <default> 💡 评分：IMDB
            - extra_info: str = <default> 💡 附加信息，是一个 JSON object 序列化为字符串，初始值为 '{"version":"","timbre":"","track":"","scene":""}'
            - is_delete: 0 | 1 = <default> 💡 是否删除
        """
        api = complete_url("/multimedia/listen", base_url=base_url)
        if isinstance(payload, dict):
            payload.setdefault("channel_id", 1)
        return self.request(url=api, method="POST", data=payload, async_=async_, **request_kwargs)

    @overload
    def multimedia_watch(
        self, 
        payload: int | dict = 0, 
        /, 
        base_url: str | Callable[[], str] = "https://webapi.115.com", 
        *, 
        async_: Literal[False] = False, 
        **request_kwargs, 
    ) -> dict:
        ...
    @overload
    def multimedia_watch(
        self, 
        payload: int | dict = 0, 
        /, 
        base_url: str | Callable[[], str] = "https://webapi.115.com", 
        *, 
        async_: Literal[True], 
        **request_kwargs, 
    ) -> Coroutine[Any, Any, dict]:
        ...
    def multimedia_watch(
        self, 
        payload: int | dict = 0, 
        /, 
        base_url: str | Callable[[], str] = "https://webapi.115.com", 
        *, 
        async_: Literal[False, True] = False, 
        **request_kwargs, 
    ) -> dict | Coroutine[Any, Any, dict]:
        """我看：专辑（详情）列表 或 专辑（详情）的基本信息和文件列表

        GET https://webapi.115.com/multimedia/watch

        .. note::
            - 指定 `multimedia_id`，则罗列此专辑（详情）的基本信息和文件列表
            - 指定 `parent_id`，则罗列关联此 id 的专辑（详情）列表
            - 都不指定，则罗列所有专辑（详情）列表

        .. todo::
            暂不清楚 `sort` 字段各个取值的含义

        .. todo::
            暂不清楚 `date` 字段的格式要求

        .. todo::
            应该还可以选择【维度】和【时间区间】，但是目前 115 的网页版还未完成此功能

        .. note::
            一个 multimedia_id 对应的专辑被称为详情，如果它还关联到其它 multimedia_id，也就是它们的 parent_id，或者被主动【设为合集】，称为合集

        :payload:
            - channel_id: int = 5
            - parent_id: int = <default> 💡 关联的专辑（详情） id
            - multimedia_id: int = <default> 💡 专辑（详情） id
            - limit: int = <default> 💡 最多返回数量
            - offset: int = <default> 💡 索引偏移，索引从 0 开始计算
            - sort: int = <default> 💡 排序依据
            - asc: 0 | 1 = <default> 💡 是否升序排列
            - visit_type: int = <default> 💡 已知：0:全部 1:已看 2:未看
            - type_id: int = <default> 💡 分类 id
            - related_name: str = <default> 💡 相关人员名称
            - collection: 0 | 1 = <default> 💡 内容类型：<default>:全部 0:详情 1:合集
            - date: str = <default> 💡 日期、月份或者年份
            - keyword: str = <default> 💡 搜索关键词
        """
        api = complete_url("/multimedia/watch", base_url=base_url)
        if isinstance(payload, int):
            payload = {"multimedia_id": payload}
        payload = {"channel_id": 5, "limit": 32, **payload}
        return self.request(url=api, params=payload, async_=async_, **request_kwargs)

    @overload
    def multimedia_watch_update(
        self, 
        payload: dict, 
        /, 
        base_url: str | Callable[[], str] = "https://webapi.115.com", 
        *, 
        async_: Literal[False] = False, 
        **request_kwargs, 
    ) -> dict:
        ...
    @overload
    def multimedia_watch_update(
        self, 
        payload: dict, 
        /, 
        base_url: str | Callable[[], str] = "https://webapi.115.com", 
        *, 
        async_: Literal[True], 
        **request_kwargs, 
    ) -> Coroutine[Any, Any, dict]:
        ...
    def multimedia_watch_update(
        self, 
        payload: dict | list, 
        /, 
        base_url: str | Callable[[], str] = "https://webapi.115.com", 
        *, 
        async_: Literal[False, True] = False, 
        **request_kwargs, 
    ) -> dict | Coroutine[Any, Any, dict]:
        """我看：更新专辑（详情）

        POST https://webapi.115.com/multimedia/watch

        :payload:
            - multimedia_id: int 💡 专辑（详情） id
            - channel_id: int = 5
            - parent_id: int = <default> 💡 关联的专辑（详情） id（作为当前专辑（详情）的上级）
            - custom_sort: int = <default> 💡 自定义排序
            - title: str = <default> 💡 标题
            - description: str = <default> 💡 简介
            - cover: str = <default> 💡 封面图片的提取码
            - country: str = <default> 💡 国家/地区
            - language: str = <default> 💡 语言，多个用逗号 "," 隔开
            - release_date: str = <default> 💡 发行日期，格式为 YYYY-MM-DD
            - type_id: int | str = <default> 💡 类型 id
            - type_id[]: int | str
            - ...
            - type_id[0]: int | str
            - type_id[1]: int | str
            - ...
            - related_id[][{related_id}]: str 💡 相关人员，是 id 到 名字 的映射关系
            - ...
            - rating[1]: int | float | str = <default> 💡 评分：豆瓣
            - rating[2]: int | float | str = <default> 💡 评分：猫眼
            - rating[3]: int | float | str = <default> 💡 评分：烂番茄
            - rating[4]: int | float | str = <default> 💡 评分：优酷
            - rating[5]: int | float | str = <default> 💡 评分：115
            - rating[6]: int | float | str = <default> 💡 评分：IMDB
            - extra_info: str = <default> 💡 附加信息，是一个 JSON object 序列化为字符串，初始值为 '{"version":"","timbre":"","track":"","scene":""}'
            - is_delete: 0 | 1 = <default> 💡 是否删除
        """
        api = complete_url("/multimedia/watch", base_url=base_url)
        if isinstance(payload, dict):
            payload.setdefault("channel_id", 5)
        return self.request(url=api, method="POST", data=payload, async_=async_, **request_kwargs)

    @overload
    def multimedia_recent_listen(
        self, 
        payload: int | dict = 0, 
        /, 
        base_url: str | Callable[[], str] = "https://webapi.115.com", 
        *, 
        async_: Literal[False] = False, 
        **request_kwargs, 
    ) -> dict:
        ...
    @overload
    def multimedia_recent_listen(
        self, 
        payload: int | dict = 0, 
        /, 
        base_url: str | Callable[[], str] = "https://webapi.115.com", 
        *, 
        async_: Literal[True], 
        **request_kwargs, 
    ) -> Coroutine[Any, Any, dict]:
        ...
    def multimedia_recent_listen(
        self, 
        payload: int | dict = 0, 
        /, 
        base_url: str | Callable[[], str] = "https://webapi.115.com", 
        *, 
        async_: Literal[False, True] = False, 
        **request_kwargs, 
    ) -> dict | Coroutine[Any, Any, dict]:
        """我听：【最近在听】列表

        GET https://webapi.115.com/multimedia/recent_listen

        :payload:
            - channel_id: int = 1
            - limit: int = 32
            - offset: int = 0
        """
        api = complete_url("/multimedia/recent_listen", base_url=base_url)
        if isinstance(payload, int):
            payload = {"offset": payload}
        payload = {"channel_id": 1, "limit": 32, **payload}
        return self.request(url=api, params=payload, async_=async_, **request_kwargs)

    @overload
    def multimedia_recent_listen_update(
        self, 
        payload: dict = {}, 
        /, 
        base_url: str | Callable[[], str] = "https://webapi.115.com", 
        *, 
        async_: Literal[False] = False, 
        **request_kwargs, 
    ) -> dict:
        ...
    @overload
    def multimedia_recent_listen_update(
        self, 
        payload: dict = {}, 
        /, 
        base_url: str | Callable[[], str] = "https://webapi.115.com", 
        *, 
        async_: Literal[True], 
        **request_kwargs, 
    ) -> Coroutine[Any, Any, dict]:
        ...
    def multimedia_recent_listen_update(
        self, 
        payload: dict = {}, 
        /, 
        base_url: str | Callable[[], str] = "https://webapi.115.com", 
        *, 
        async_: Literal[False, True] = False, 
        **request_kwargs, 
    ) -> dict | Coroutine[Any, Any, dict]:
        """我听：更新【最近在听】

        POST https://webapi.115.com/multimedia/recent_listen

        .. note::
            目前仅支持 clear 操作，即 清空所有记录

        :payload:
            - channel_id: int = 1
            - action: str = "clear"
        """
        api = complete_url("/multimedia/recent_listen", base_url=base_url)
        payload = {"channel_id": 1, "action": "clear", **payload}
        return self.request(url=api, method="POST", data=payload, async_=async_, **request_kwargs)

    @overload
    def multimedia_recent_watch(
        self, 
        payload: int | dict = 0, 
        /, 
        base_url: str | Callable[[], str] = "https://webapi.115.com", 
        *, 
        async_: Literal[False] = False, 
        **request_kwargs, 
    ) -> dict:
        ...
    @overload
    def multimedia_recent_watch(
        self, 
        payload: int | dict = 0, 
        /, 
        base_url: str | Callable[[], str] = "https://webapi.115.com", 
        *, 
        async_: Literal[True], 
        **request_kwargs, 
    ) -> Coroutine[Any, Any, dict]:
        ...
    def multimedia_recent_watch(
        self, 
        payload: int | dict = 0, 
        /, 
        base_url: str | Callable[[], str] = "https://webapi.115.com", 
        *, 
        async_: Literal[False, True] = False, 
        **request_kwargs, 
    ) -> dict | Coroutine[Any, Any, dict]:
        """我看：【最近观看】列表

        GET https://webapi.115.com/multimedia/recent_watch

        :payload:
            - channel_id: int = 5
            - limit: int = 32
            - offset: int = 0
        """
        api = complete_url("/multimedia/recent_watch", base_url=base_url)
        if isinstance(payload, int):
            payload = {"offset": payload}
        payload = {"channel_id": 5, "limit": 32, **payload}
        return self.request(url=api, params=payload, async_=async_, **request_kwargs)

    @overload
    def multimedia_recent_watch_update(
        self, 
        payload: dict = {}, 
        /, 
        base_url: str | Callable[[], str] = "https://webapi.115.com", 
        *, 
        async_: Literal[False] = False, 
        **request_kwargs, 
    ) -> dict:
        ...
    @overload
    def multimedia_recent_watch_update(
        self, 
        payload: dict = {}, 
        /, 
        base_url: str | Callable[[], str] = "https://webapi.115.com", 
        *, 
        async_: Literal[True], 
        **request_kwargs, 
    ) -> Coroutine[Any, Any, dict]:
        ...
    def multimedia_recent_watch_update(
        self, 
        payload: dict = {}, 
        /, 
        base_url: str | Callable[[], str] = "https://webapi.115.com", 
        *, 
        async_: Literal[False, True] = False, 
        **request_kwargs, 
    ) -> dict | Coroutine[Any, Any, dict]:
        """我听：更新【最近观看】

        POST https://webapi.115.com/multimedia/recent_watch

        .. note::
            目前仅支持 clear 操作，即 清空所有记录

        :payload:
            - channel_id: int = 5
            - action: str = "clear"
        """
        api = complete_url("/multimedia/recent_watch", base_url=base_url)
        payload = {"channel_id": 5, "action": "clear", **payload}
        return self.request(url=api, method="POST", data=payload, async_=async_, **request_kwargs)

    @overload
    def multimedia_relate_file(
        self, 
        payload: dict, 
        /, 
        base_url: str | Callable[[], str] = "https://webapi.115.com", 
        *, 
        async_: Literal[False] = False, 
        **request_kwargs, 
    ) -> dict:
        ...
    @overload
    def multimedia_relate_file(
        self, 
        payload: dict, 
        /, 
        base_url: str | Callable[[], str] = "https://webapi.115.com", 
        *, 
        async_: Literal[True], 
        **request_kwargs, 
    ) -> Coroutine[Any, Any, dict]:
        ...
    def multimedia_relate_file(
        self, 
        payload: dict, 
        /, 
        base_url: str | Callable[[], str] = "https://webapi.115.com", 
        *, 
        async_: Literal[False, True] = False, 
        **request_kwargs, 
    ) -> dict | Coroutine[Any, Any, dict]:
        """我听&我看：罗列专辑（详情）的关联文件

        GET https://webapi.115.com/multimedia/relate_file

        :payload:
            - multimedia_id: int 💡 专辑（详情） id
            - channel_id: int = 1 💡 频道 id，已知：1:音乐 5:视频
            - limit: int = 32
            - offset: int = 0
            - o: "custom_sort" | "file_name" | "file_size" | "created_time" = <default> 💡 排序依据
            - asc: 0 | 1 = <default> 💡 是否升序排列
        """
        api = complete_url("/multimedia/relate_file", base_url=base_url)
        payload = {"channel_id": 1, "limit": 32, **payload}
        return self.request(url=api, params=payload, async_=async_, **request_kwargs)

    @overload
    def multimedia_relate_file_update(
        self, 
        payload: dict, 
        /, 
        base_url: str | Callable[[], str] = "https://webapi.115.com", 
        *, 
        async_: Literal[False] = False, 
        **request_kwargs, 
    ) -> dict:
        ...
    @overload
    def multimedia_relate_file_update(
        self, 
        payload: dict, 
        /, 
        base_url: str | Callable[[], str] = "https://webapi.115.com", 
        *, 
        async_: Literal[True], 
        **request_kwargs, 
    ) -> Coroutine[Any, Any, dict]:
        ...
    def multimedia_relate_file_update(
        self, 
        payload: dict, 
        /, 
        base_url: str | Callable[[], str] = "https://webapi.115.com", 
        *, 
        async_: Literal[False, True] = False, 
        **request_kwargs, 
    ) -> dict | Coroutine[Any, Any, dict]:
        """我听&我看：更新专辑（详情）的关联文件

        POST https://webapi.115.com/multimedia/relate_file

        .. note::
            指定 `multimedia_id` 时，则针对相应的专辑（详情）进行文件增删；未指定时，则自动创建新的专辑（详情）

        :payload:
            - file_ids: int | str 💡 文件 id，多个用逗号 "," 隔开
            - op: str = "relate" 💡 已知："relate":添加 "delete":删除 "update":更新
            - channel_id: int = 1 💡 频道 id，已知：1:音乐 5:视频
            - multimedia_id: int = <default> 💡 专辑（详情） id
            - one_by_one: 0 | 1 = <default> 💡 （未指定 `multimedia_id` 时生效）是否分别创建专辑（详情）：0:为所选文件创建为一个详情页 1:为每个文件创建单独的详情页
            - visited: 0 | 1 = <default> 💡 是否标记为访问过
        """
        api = complete_url("/multimedia/relate_file", base_url=base_url)
        payload = {"channel_id": 1, "action": "clear", **payload}
        return self.request(url=api, method="POST", data=payload, async_=async_, **request_kwargs)

    @overload
    def multimedia_related(
        self, 
        payload: int | dict = 1, 
        /, 
        base_url: str | Callable[[], str] = "https://webapi.115.com", 
        *, 
        async_: Literal[False] = False, 
        **request_kwargs, 
    ) -> dict:
        ...
    @overload
    def multimedia_related(
        self, 
        payload: int | dict = 1, 
        /, 
        base_url: str | Callable[[], str] = "https://webapi.115.com", 
        *, 
        async_: Literal[True], 
        **request_kwargs, 
    ) -> Coroutine[Any, Any, dict]:
        ...
    def multimedia_related(
        self, 
        payload: int | dict = 1, 
        /, 
        base_url: str | Callable[[], str] = "https://webapi.115.com", 
        *, 
        async_: Literal[False, True] = False, 
        **request_kwargs, 
    ) -> dict | Coroutine[Any, Any, dict]:
        """我听&我看：人员列表

        GET https://webapi.115.com/multimedia/related

        :payload:
            - channel_id: int = 1 💡 频道 id，已知：1:音乐 5:视频
        """
        api = complete_url("/multimedia/related", base_url=base_url)
        if isinstance(payload, int):
            payload = {"channel_id": payload}
        else:
            payload.setdefault("channel_id", 1)
        return self.request(url=api, params=payload, async_=async_, **request_kwargs)

    @overload
    def multimedia_related_update(
        self, 
        payload: dict, 
        /, 
        base_url: str | Callable[[], str] = "https://webapi.115.com", 
        *, 
        async_: Literal[False] = False, 
        **request_kwargs, 
    ) -> dict:
        ...
    @overload
    def multimedia_related_update(
        self, 
        payload: dict, 
        /, 
        base_url: str | Callable[[], str] = "https://webapi.115.com", 
        *, 
        async_: Literal[True], 
        **request_kwargs, 
    ) -> Coroutine[Any, Any, dict]:
        ...
    def multimedia_related_update(
        self, 
        payload: dict, 
        /, 
        base_url: str | Callable[[], str] = "https://webapi.115.com", 
        *, 
        async_: Literal[False, True] = False, 
        **request_kwargs, 
    ) -> dict | Coroutine[Any, Any, dict]:
        """我听&我看：更新人员

        GET https://webapi.115.com/multimedia/related

        .. note::
            未指定 `related_id` 时，则是添加（此时需要指定 `related_name`）；指定时，则是修改

        .. todo::
            暂不支持删除人员

        :payload:
            - related_name: str 💡 相关人员名字
            - channel_id: int = 1 💡 频道 id，已知：1:音乐 5:视频
            - related_id: int = <default> 💡 相关人员 id
        """
        api = complete_url("/multimedia/related", base_url=base_url)
        return self.request(url=api, method="POST", data=payload, async_=async_, **request_kwargs)

    @overload
    def multimedia_type(
        self, 
        payload: int | dict = 1, 
        /, 
        base_url: str | Callable[[], str] = "https://webapi.115.com", 
        *, 
        async_: Literal[False] = False, 
        **request_kwargs, 
    ) -> dict:
        ...
    @overload
    def multimedia_type(
        self, 
        payload: int | dict = 1, 
        /, 
        base_url: str | Callable[[], str] = "https://webapi.115.com", 
        *, 
        async_: Literal[True], 
        **request_kwargs, 
    ) -> Coroutine[Any, Any, dict]:
        ...
    def multimedia_type(
        self, 
        payload: int | dict = 1, 
        /, 
        base_url: str | Callable[[], str] = "https://webapi.115.com", 
        *, 
        async_: Literal[False, True] = False, 
        **request_kwargs, 
    ) -> dict | Coroutine[Any, Any, dict]:
        """我听&我看：分类列表

        GET https://webapi.115.com/multimedia/type

        :payload:
            - channel_id: int = 1 💡 频道 id，已知：1:音乐 5:视频
            - parent_id: int = <default>
        """
        api = complete_url("/multimedia/type", base_url=base_url)
        if isinstance(payload, int):
            payload = {"channel_id": payload}
        else:
            payload.setdefault("channel_id", 1)
        return self.request(url=api, params=payload, async_=async_, **request_kwargs)

    @overload
    def multimedia_type_update(
        self, 
        payload: dict, 
        /, 
        base_url: str | Callable[[], str] = "https://webapi.115.com", 
        *, 
        async_: Literal[False] = False, 
        **request_kwargs, 
    ) -> dict:
        ...
    @overload
    def multimedia_type_update(
        self, 
        payload: dict, 
        /, 
        base_url: str | Callable[[], str] = "https://webapi.115.com", 
        *, 
        async_: Literal[True], 
        **request_kwargs, 
    ) -> Coroutine[Any, Any, dict]:
        ...
    def multimedia_type_update(
        self, 
        payload: dict, 
        /, 
        base_url: str | Callable[[], str] = "https://webapi.115.com", 
        *, 
        async_: Literal[False, True] = False, 
        **request_kwargs, 
    ) -> dict | Coroutine[Any, Any, dict]:
        """我听&我看：更新分类

        GET https://webapi.115.com/multimedia/type

        .. note::
            目前支持创建最多 3 级分类，`parent_id=0` 时为 1 级分类

        .. note::
            未指定 `type_id` 时，则是添加（此时需要指定 `type_name`）；指定时，则是修改

        .. todo::
            暂不支持删除分类

        :payload:
            - channel_id: int = 1 💡 频道 id，已知：1:音乐 5:视频
            - parent_id: int = <default> 💡 上级分类 id
            - type_id: int = <default> 💡 分类 id
            - type_name: str = <default> 💡 分类名称
            - sort: int = <default> 💡 序号
        """
        api = complete_url("/multimedia/type", base_url=base_url)
        return self.request(url=api, method="POST", data=payload, async_=async_, **request_kwargs)

    ########## Note API ##########

    @overload
    def note_bookmark_list(
        self, 
        payload: int | str | dict = "", 
        /, 
        base_url: str | Callable[[], str] = "https://bookmark.115.com", 
        *, 
        async_: Literal[False] = False, 
        **request_kwargs, 
    ) -> dict:
        ...
    @overload
    def note_bookmark_list(
        self, 
        payload: int | str | dict = "", 
        /, 
        base_url: str | Callable[[], str] = "https://bookmark.115.com", 
        *, 
        async_: Literal[True], 
        **request_kwargs, 
    ) -> Coroutine[Any, Any, dict]:
        ...
    def note_bookmark_list(
        self, 
        payload: int | str | dict = "", 
        /, 
        base_url: str | Callable[[], str] = "https://bookmark.115.com", 
        *, 
        async_: Literal[False, True] = False, 
        **request_kwargs, 
    ) -> dict | Coroutine[Any, Any, dict]:
        """罗列书签（网址收藏夹）

        GET https://bookmark.115.com/api/bookmark_list.php

        .. note::
            这个接口支持 GET 和 POST 请求方法

        :payload:
            - search_value: str = ""
            - parent_id: int = 0
            - limit: int = 1150
            - offset: int = 0
        """
        api = complete_url("/api/bookmark_list.php", base_url=base_url)
        if isinstance(payload, int):
            payload = {"offset": payload}
        elif isinstance(payload, str):
            payload = {"search_value": payload}
        payload.setdefault("limit", 1150)
        if request_kwargs.get("method", "").upper() == "POST":
            return self.request(url=api, data=payload, async_=async_, **request_kwargs)
        else:
            return self.request(url=api, params=payload, async_=async_, **request_kwargs)

    @overload
    def note_cate_add(
        self, 
        payload: str | dict, 
        /, 
        base_url: str | Callable[[], str] = "https://note.115.com", 
        *, 
        async_: Literal[False] = False, 
        **request_kwargs, 
    ) -> dict:
        ...
    @overload
    def note_cate_add(
        self, 
        payload: str | dict, 
        /, 
        base_url: str | Callable[[], str] = "https://note.115.com", 
        *, 
        async_: Literal[True], 
        **request_kwargs, 
    ) -> Coroutine[Any, Any, dict]:
        ...
    def note_cate_add(
        self, 
        payload: str | dict, 
        /, 
        base_url: str | Callable[[], str] = "https://note.115.com", 
        *, 
        async_: Literal[False, True] = False, 
        **request_kwargs, 
    ) -> dict | Coroutine[Any, Any, dict]:
        """添加记录分类

        POST https://note.115.com/?ct=note&ac=addcate

        :payload:
            - cname: str 💡 最多允许 20 个字符
        """
        api = complete_url(base_url=base_url, query={"ct": "note", "ac": "addcate"})
        if isinstance(payload, str):
            payload = {"cname": payload}
        return self.request(url=api, method="POST", data=payload, async_=async_, **request_kwargs)

    @overload
    def note_cate_del(
        self, 
        payload: int | dict, 
        /, 
        base_url: str | Callable[[], str] = "https://note.115.com", 
        *, 
        async_: Literal[False] = False, 
        **request_kwargs, 
    ) -> dict:
        ...
    @overload
    def note_cate_del(
        self, 
        payload: int | dict, 
        /, 
        base_url: str | Callable[[], str] = "https://note.115.com", 
        *, 
        async_: Literal[True], 
        **request_kwargs, 
    ) -> Coroutine[Any, Any, dict]:
        ...
    def note_cate_del(
        self, 
        payload: int | dict, 
        /, 
        base_url: str | Callable[[], str] = "https://note.115.com", 
        *, 
        async_: Literal[False, True] = False, 
        **request_kwargs, 
    ) -> dict | Coroutine[Any, Any, dict]:
        """删除记录分类

        POST https://note.115.com/?ct=note&ac=delcate

        :payload:
            - cid: int 💡 分类 id
            - action: str = <default>
        """
        api = complete_url(base_url=base_url, query={"ct": "note", "ac": "delcate"})
        if isinstance(payload, int):
            payload = {"cid": payload}
        return self.request(url=api, method="POST", data=payload, async_=async_, **request_kwargs)

    @overload
    def note_cate_update(
        self, 
        payload: dict, 
        /, 
        base_url: str | Callable[[], str] = "https://note.115.com", 
        *, 
        async_: Literal[False] = False, 
        **request_kwargs, 
    ) -> dict:
        ...
    @overload
    def note_cate_update(
        self, 
        payload: dict, 
        /, 
        base_url: str | Callable[[], str] = "https://note.115.com", 
        *, 
        async_: Literal[True], 
        **request_kwargs, 
    ) -> Coroutine[Any, Any, dict]:
        ...
    def note_cate_update(
        self, 
        payload: dict, 
        /, 
        base_url: str | Callable[[], str] = "https://note.115.com", 
        *, 
        async_: Literal[False, True] = False, 
        **request_kwargs, 
    ) -> dict | Coroutine[Any, Any, dict]:
        """改名记录分类

        POST https://note.115.com/?ct=note&ac=upcate

        :payload:
            - cid: int   💡 分类 id
            - cname: str 💡 分类名，最多 20 个字符
        """
        api = complete_url(base_url=base_url, query={"ct": "node", "ac": "upcate"})
        return self.request(url=api, method="POST", data=payload, async_=async_, **request_kwargs)

    @overload
    def note_cate_list(
        self, 
        payload: bool | dict = True, 
        /, 
        base_url: str | Callable[[], str] = "https://note.115.com", 
        *, 
        async_: Literal[False] = False, 
        **request_kwargs, 
    ) -> dict:
        ...
    @overload
    def note_cate_list(
        self, 
        payload: bool | dict = True, 
        /, 
        base_url: str | Callable[[], str] = "https://note.115.com", 
        *, 
        async_: Literal[True], 
        **request_kwargs, 
    ) -> Coroutine[Any, Any, dict]:
        ...
    def note_cate_list(
        self, 
        payload: bool | dict = True, 
        /, 
        base_url: str | Callable[[], str] = "https://note.115.com", 
        *, 
        async_: Literal[False, True] = False, 
        **request_kwargs, 
    ) -> dict | Coroutine[Any, Any, dict]:
        """获取记录分类列表

        GET https://note.115.com/?ct=note&ac=cate

        :payload:
            - has_picknews: 0 | 1 = 1 💡 是否显示 id 为负数的分类
        """
        api = complete_url(base_url=base_url, query={"ct": "note", "ac": "cate"})
        if isinstance(payload, bool):
            payload = {"has_picknews": int(payload)}
        return self.request(url=api, params=payload, async_=async_, **request_kwargs)

    @overload
    def note_cate_list2(
        self, 
        payload: bool | dict = True, 
        /, 
        base_url: str | Callable[[], str] = "https://note.115.com", 
        *, 
        async_: Literal[False] = False, 
        **request_kwargs, 
    ) -> dict:
        ...
    @overload
    def note_cate_list2(
        self, 
        payload: bool | dict = True, 
        /, 
        base_url: str | Callable[[], str] = "https://note.115.com", 
        *, 
        async_: Literal[True], 
        **request_kwargs, 
    ) -> Coroutine[Any, Any, dict]:
        ...
    def note_cate_list2(
        self, 
        payload: bool | dict = True, 
        /, 
        base_url: str | Callable[[], str] = "https://note.115.com", 
        *, 
        async_: Literal[False, True] = False, 
        **request_kwargs, 
    ) -> dict | Coroutine[Any, Any, dict]:
        """获取记录分类列表

        GET https://note.115.com/api/2.0/api.php?ac=get_category

        :payload:
            - has_picknews: 0 | 1 = 1 💡 是否显示 id 为负数的分类
            - is_all: 0 | 1 = <default> 💡 是否显示全部
            - has_msg: 0 | 1 = <default>
        """
        api = complete_url("/api/2.0/api.php", base_url=base_url, query={"ac": "get_category"})
        if isinstance(payload, bool):
            payload = {"has_picknews": int(payload)}
        return self.request(url=api, params=payload, async_=async_, **request_kwargs)

    @overload
    def note_del(
        self, 
        payload: int | str | Iterable[int | str] | dict, 
        /, 
        base_url: str | Callable[[], str] = "https://note.115.com", 
        *, 
        async_: Literal[False] = False, 
        **request_kwargs, 
    ) -> dict:
        ...
    @overload
    def note_del(
        self, 
        payload: int | str | Iterable[int | str] | dict, 
        /, 
        base_url: str | Callable[[], str] = "https://note.115.com", 
        *, 
        async_: Literal[True], 
        **request_kwargs, 
    ) -> Coroutine[Any, Any, dict]:
        ...
    def note_del(
        self, 
        payload: int | str | Iterable[int | str] | dict, 
        /, 
        base_url: str | Callable[[], str] = "https://note.115.com", 
        *, 
        async_: Literal[False, True] = False, 
        **request_kwargs, 
    ) -> dict | Coroutine[Any, Any, dict]:
        """删除记录

        POST https://note.115.com/?ct=note&ac=delete

        :payload:
            - nid: int | str 💡 记录 id，多个用逗号 "," 隔开
        """
        api = complete_url(base_url=base_url, query={"ct": "note", "ac": "delete"})
        if isinstance(payload, (int, str)):
            payload = {"nid": payload}
        elif not isinstance(payload, dict):
            payload = {"nid": ",".join(map(str, payload))}
        return self.request(url=api, method="POST", data=payload, async_=async_, **request_kwargs)

    @overload
    def note_del2(
        self, 
        payload: int | str | Iterable[int | str] | dict, 
        /, 
        base_url: str | Callable[[], str] = "https://note.115.com", 
        *, 
        async_: Literal[False] = False, 
        **request_kwargs, 
    ) -> dict:
        ...
    @overload
    def note_del2(
        self, 
        payload: int | str | Iterable[int | str] | dict, 
        /, 
        base_url: str | Callable[[], str] = "https://note.115.com", 
        *, 
        async_: Literal[True], 
        **request_kwargs, 
    ) -> Coroutine[Any, Any, dict]:
        ...
    def note_del2(
        self, 
        payload: int | str | Iterable[int | str] | dict, 
        /, 
        base_url: str | Callable[[], str] = "https://note.115.com", 
        *, 
        async_: Literal[False, True] = False, 
        **request_kwargs, 
    ) -> dict | Coroutine[Any, Any, dict]:
        """删除记录

        POST https://note.115.com/api/2.0/api.php?ac=note_delete

        :payload:
            - nid: int | str 💡 记录 id，多个用逗号 "," 隔开
        """
        api = complete_url("/api/2.0/api.php", base_url=base_url, query={"ac": "note_delete"})
        if isinstance(payload, (int, str)):
            payload = {"nid": payload}
        elif not isinstance(payload, dict):
            payload = {"nid": ",".join(map(str, payload))}
        return self.request(url=api, method="POST", data=payload, async_=async_, **request_kwargs)

    @overload
    def note_detail(
        self, 
        payload: int | dict, 
        /, 
        base_url: str | Callable[[], str] = "https://note.115.com", 
        *, 
        async_: Literal[False] = False, 
        **request_kwargs, 
    ) -> dict:
        ...
    @overload
    def note_detail(
        self, 
        payload: int | dict, 
        /, 
        base_url: str | Callable[[], str] = "https://note.115.com", 
        *, 
        async_: Literal[True], 
        **request_kwargs, 
    ) -> Coroutine[Any, Any, dict]:
        ...
    def note_detail(
        self, 
        payload: int | dict, 
        /, 
        base_url: str | Callable[[], str] = "https://note.115.com", 
        *, 
        async_: Literal[False, True] = False, 
        **request_kwargs, 
    ) -> dict | Coroutine[Any, Any, dict]:
        """获取备忘（记录/笔记/记事）数据

        GET https://note.115.com/?ct=note&ac=detail

        :payload:
            - nid: int 💡 记录 id
        """
        api = complete_url(base_url=base_url, query={"ct": "note", "ac": "detail"})
        if isinstance(payload, int):
            payload = {"nid": payload}
        return self.request(url=api, params=payload, async_=async_, **request_kwargs)

    @overload
    def note_detail2(
        self, 
        payload: int | dict, 
        /, 
        base_url: str | Callable[[], str] = "https://note.115.com", 
        *, 
        async_: Literal[False] = False, 
        **request_kwargs, 
    ) -> dict:
        ...
    @overload
    def note_detail2(
        self, 
        payload: int | dict, 
        /, 
        base_url: str | Callable[[], str] = "https://note.115.com", 
        *, 
        async_: Literal[True], 
        **request_kwargs, 
    ) -> Coroutine[Any, Any, dict]:
        ...
    def note_detail2(
        self, 
        payload: int | dict, 
        /, 
        base_url: str | Callable[[], str] = "https://note.115.com", 
        *, 
        async_: Literal[False, True] = False, 
        **request_kwargs, 
    ) -> dict | Coroutine[Any, Any, dict]:
        """获取备忘（记录/笔记/记事）数据

        GET https://note.115.com/api/2.0/api.php?ac=note_detail

        :payload:
            - nid: int 💡 记录 id
            - has_picknews: 0 | 1 = <default>
            - is_html: 0 | 1 = <default>
            - copy: 0 | 1 = <default>
        """
        api = complete_url("/api/2.0/api.php", base_url=base_url, query={"ac": "note_detail"})
        if isinstance(payload, int):
            payload = {"nid": payload}
        return self.request(url=api, params=payload, async_=async_, **request_kwargs)

    @overload
    def note_edit_attaches(
        self, 
        payload: dict, 
        /, 
        base_url: str | Callable[[], str] = "https://note.115.com", 
        *, 
        async_: Literal[False] = False, 
        **request_kwargs, 
    ) -> dict:
        ...
    @overload
    def note_edit_attaches(
        self, 
        payload: dict, 
        /, 
        base_url: str | Callable[[], str] = "https://note.115.com", 
        *, 
        async_: Literal[True], 
        **request_kwargs, 
    ) -> Coroutine[Any, Any, dict]:
        ...
    def note_edit_attaches(
        self, 
        payload: dict, 
        /, 
        base_url: str | Callable[[], str] = "https://note.115.com", 
        *, 
        async_: Literal[False, True] = False, 
        **request_kwargs, 
    ) -> dict | Coroutine[Any, Any, dict]:
        """给记录修改附件

        POST https://note.115.com/?ct=note&ac=edit_attaches

        .. attention::
            每个附件的大小必须控制在 200 MB 以内，这也是网页版所允许的单次下载的最大文件

        :payload:
            - nid: int 💡 记录 id
            - pickcodes: str 💡 附件的提取码，多个用逗号 "," 隔开
            - op: "add" | "del" | "save" = "add" 💡 操作类型："add":添加 "del":去除 "save":置换
        """
        api = complete_url(base_url=base_url, query={"ct": "note", "ac": "edit_attaches"})
        return self.request(url=api, method="POST", data=payload, async_=async_, **request_kwargs)

    @overload
    def note_fav_list(
        self, 
        payload: int | dict = 0, 
        /, 
        base_url: str | Callable[[], str] = "https://note.115.com", 
        *, 
        async_: Literal[False] = False, 
        **request_kwargs, 
    ) -> dict:
        ...
    @overload
    def note_fav_list(
        self, 
        payload: int | dict = 0, 
        /, 
        base_url: str | Callable[[], str] = "https://note.115.com", 
        *, 
        async_: Literal[True], 
        **request_kwargs, 
    ) -> Coroutine[Any, Any, dict]:
        ...
    def note_fav_list(
        self, 
        payload: int | dict = 0, 
        /, 
        base_url: str | Callable[[], str] = "https://note.115.com", 
        *, 
        async_: Literal[False, True] = False, 
        **request_kwargs, 
    ) -> dict | Coroutine[Any, Any, dict]:
        """获取星标备忘（记录/笔记/记事）列表

        GET https://note.115.com/?ct=note&ac=get_fav_note_list

        :payload:
            - start: int = 0    💡 开始索引，从 0 开始
            - limit: int = 1150 💡 最多返回数量
        """
        api = complete_url(base_url=base_url, query={"ct": "note", "ac": "get_fav_note_list"})
        if isinstance(payload, int):
            payload = {"start": payload}
        payload = {"limit": 1150, "start": 0, **payload}
        return self.request(url=api, params=payload, async_=async_, **request_kwargs)

    @overload
    def note_fav_set(
        self, 
        payload: int | dict, 
        /, 
        base_url: str | Callable[[], str] = "https://note.115.com", 
        *, 
        async_: Literal[False] = False, 
        **request_kwargs, 
    ) -> dict:
        ...
    @overload
    def note_fav_set(
        self, 
        payload: int | dict, 
        /, 
        base_url: str | Callable[[], str] = "https://note.115.com", 
        *, 
        async_: Literal[True], 
        **request_kwargs, 
    ) -> Coroutine[Any, Any, dict]:
        ...
    def note_fav_set(
        self, 
        payload: int | dict, 
        /, 
        base_url: str | Callable[[], str] = "https://note.115.com", 
        *, 
        async_: Literal[False, True] = False, 
        **request_kwargs, 
    ) -> dict | Coroutine[Any, Any, dict]:
        """给记录添加或去除星标

        POST https://note.115.com/?ct=note&ac=fav

        :payload:
            - note_id: int 💡 记录 id
            - op: "add" | "del" = "add" 💡 操作类型："add":添加 "del":去除
        """
        api = complete_url(base_url=base_url, query={"ct": "note", "ac": "fav"})
        if isinstance(payload, int):
            payload = {"note_id": payload}
        payload.setdefault("op", "add")
        return self.request(url=api, method="POST", data=payload, async_=async_, **request_kwargs)

    @overload
    def note_get_pic_url(
        self, 
        payload: str | tuple[str, ...] | dict | list, 
        /, 
        base_url: str | Callable[[], str] = "https://note.115.com", 
        *, 
        async_: Literal[False] = False, 
        **request_kwargs, 
    ) -> dict:
        ...
    @overload
    def note_get_pic_url(
        self, 
        payload: str | tuple[str, ...] | dict | list, 
        /, 
        base_url: str | Callable[[], str] = "https://note.115.com", 
        *, 
        async_: Literal[True], 
        **request_kwargs, 
    ) -> Coroutine[Any, Any, dict]:
        ...
    def note_get_pic_url(
        self, 
        payload: str | tuple[str, ...] | dict | list, 
        /, 
        base_url: str | Callable[[], str] = "https://note.115.com", 
        *, 
        async_: Literal[False, True] = False, 
        **request_kwargs, 
    ) -> dict | Coroutine[Any, Any, dict]:
        """批量获取图片的预览图链接

        POST https://note.115.com?ct=note&ac=get_pic_url

        .. hint::
            这个接口获取的链接似乎长久有效，而且支持任何文件（只要有人上传过），但限制文件大小在 50 MB 以内

        :payload:
            - rs: str 💡 图片的 sha1 （必须大写）或者 f"{oss_bucket}_{oss_object}"（由 `upload_file_image` 接口的响应获得），后者跳转次数更少、响应更快
            - rs[]: str
            - ...
            - rs[0]: str
            - rs[1]: str
            - ...
            - module: int = <default>
            - file_names[]: str = <default>
            - ...
            - type[]: int = <default>
            - ...
        """
        api = complete_url(base_url=base_url, query={"ct": "note", "ac": "get_pic_url"})
        if isinstance(payload, str):
            payload = {"rs": payload}
        elif isinstance(payload, tuple):
            payload = [("rs[]", s) for s in payload]
        return self.request(
            url=api, 
            method="POST", 
            data=payload, 
            async_=async_, 
            **request_kwargs, 
        )

    @overload
    def note_get_pic_url2(
        self, 
        payload: str | tuple[str, ...] | dict | list, 
        /, 
        base_url: str | Callable[[], str] = "https://note.115.com", 
        *, 
        async_: Literal[False] = False, 
        **request_kwargs, 
    ) -> dict:
        ...
    @overload
    def note_get_pic_url2(
        self, 
        payload: str | tuple[str, ...] | dict | list, 
        /, 
        base_url: str | Callable[[], str] = "https://note.115.com", 
        *, 
        async_: Literal[True], 
        **request_kwargs, 
    ) -> Coroutine[Any, Any, dict]:
        ...
    def note_get_pic_url2(
        self, 
        payload: str | tuple[str, ...] | dict | list, 
        /, 
        base_url: str | Callable[[], str] = "https://note.115.com", 
        *, 
        async_: Literal[False, True] = False, 
        **request_kwargs, 
    ) -> dict | Coroutine[Any, Any, dict]:
        """批量获取图片的预览图链接

        POST https://note.115.com/api/2.0/api.php?ac=get_pic_url

        .. hint::
            这个接口获取的链接似乎长久有效，而且支持任何文件（只要有人上传过），但限制文件大小在 50 MB 以内

        :payload:
            - rs: str 💡 图片的 sha1 （必须大写）或者 f"{oss_bucket}_{oss_object}"（由 `upload_file_image` 接口的响应获得），后者跳转次数更少、响应更快
            - rs[]: str
            - ...
            - rs[0]: str
            - rs[1]: str
            - ...
            - module: int = <default>
            - file_names[]: str = <default>
            - ...
            - type[]: int = <default>
            - ...
        """
        api = complete_url("/api/2.0/api.php", base_url=base_url, query={"ac": "get_pic_url"})
        if isinstance(payload, str):
            payload = {"rs": payload}
        elif isinstance(payload, tuple):
            payload = [("rs[]", s) for s in payload]
        return self.request(
            url=api, 
            method="POST", 
            data=payload, 
            async_=async_, 
            **request_kwargs, 
        )

    @overload
    def note_is_fav(
        self, 
        payload: int | str | Iterable[int | str] |dict, 
        /, 
        base_url: str | Callable[[], str] = "https://note.115.com", 
        *, 
        async_: Literal[False] = False, 
        **request_kwargs, 
    ) -> dict:
        ...
    @overload
    def note_is_fav(
        self, 
        payload: int | str | Iterable[int | str] |dict, 
        /, 
        base_url: str | Callable[[], str] = "https://note.115.com", 
        *, 
        async_: Literal[True], 
        **request_kwargs, 
    ) -> Coroutine[Any, Any, dict]:
        ...
    def note_is_fav(
        self, 
        payload: int | str | Iterable[int | str] |dict, 
        /, 
        base_url: str | Callable[[], str] = "https://note.115.com", 
        *, 
        async_: Literal[False, True] = False, 
        **request_kwargs, 
    ) -> dict | Coroutine[Any, Any, dict]:
        """检查记录是否被星标

        .. note::
            这个接口支持 GET 和 POST 请求方法

        GET https://note.115.com/api/2.0/api.php?ac=is_fav

        :payload:
            - note_id: int | str 💡 多个用逗号隔开
        """
        api = complete_url("/api/2.0/api.php", base_url=base_url, query={"ac": "is_fav"})
        if isinstance(payload, (int, str)):
            payload = {"note_id": payload}
        elif not isinstance(payload, dict):
            payload = {"note_id": ",".join(map(str, payload))}
        if request_kwargs.get("method", "").upper() == "POST":
            return self.request(url=api, data=payload, async_=async_, **request_kwargs)
        else:
            return self.request(url=api, params=payload, async_=async_, **request_kwargs)

    @overload
    def note_list(
        self, 
        payload: int | dict = 0, 
        /, 
        base_url: str | Callable[[], str] = "https://note.115.com", 
        *, 
        async_: Literal[False] = False, 
        **request_kwargs, 
    ) -> dict:
        ...
    @overload
    def note_list(
        self, 
        payload: int | dict = 0, 
        /, 
        base_url: str | Callable[[], str] = "https://note.115.com", 
        *, 
        async_: Literal[True], 
        **request_kwargs, 
    ) -> Coroutine[Any, Any, dict]:
        ...
    def note_list(
        self, 
        payload: int | dict = 0, 
        /, 
        base_url: str | Callable[[], str] = "https://note.115.com", 
        *, 
        async_: Literal[False, True] = False, 
        **request_kwargs, 
    ) -> dict | Coroutine[Any, Any, dict]:
        """获取备忘（记录/笔记/记事）列表

        GET https://note.115.com/?ct=note

        :payload:
            - ac: "" | "all" = "all"  💡 如果为 "all"，则显示完整信息，如果为 ""，则显示简要信息（只有标题，没有内容文本）
            - start: int = 0          💡 开始索引，从 0 开始
            - page_size: int = 1150   💡 分页大小，相当于 `limit`
            - cid: int = 0            💡 分类 id：0:全部 -10:云收藏 -15:消息备忘
            - has_picknews: 0 | 1 = 1 💡 是否显示 id 为负数的分类
            - keyword: str = <default>
            - recently: 0 | 1 = <default> 💡 是否为最近
        """
        api = complete_url(base_url=base_url, query={"ct": "note"})
        if isinstance(payload, int):
            payload = {"start": payload}
        payload = {"ac": "all", "cid": 0, "has_picknews": 1, "page_size": 1150, "start": 0, **payload}
        return self.request(url=api, params=payload, async_=async_, **request_kwargs)

    @overload
    def note_list2(
        self, 
        payload: int | dict = 0, 
        /, 
        base_url: str | Callable[[], str] = "https://note.115.com", 
        *, 
        async_: Literal[False] = False, 
        **request_kwargs, 
    ) -> dict:
        ...
    @overload
    def note_list2(
        self, 
        payload: int | dict = 0, 
        /, 
        base_url: str | Callable[[], str] = "https://note.115.com", 
        *, 
        async_: Literal[True], 
        **request_kwargs, 
    ) -> Coroutine[Any, Any, dict]:
        ...
    def note_list2(
        self, 
        payload: int | dict = 0, 
        /, 
        base_url: str | Callable[[], str] = "https://note.115.com", 
        *, 
        async_: Literal[False, True] = False, 
        **request_kwargs, 
    ) -> dict | Coroutine[Any, Any, dict]:
        """获取备忘（记录/笔记/记事）列表

        GET https://note.115.com/api/2.0/api.php?ac=note_list

        :payload:
            - start: int = 0    💡 开始索引，从 0 开始
            - limit: int = 1150 💡 分页大小
            - cid: int = 0      💡 分类 id：0:全部 -10:云收藏 -15:消息备忘
            - only_public: 0 | 1 = <default>
            - msg_note: 0 | 1 = <default>
        """
        api = complete_url("/api/2.0/api.php", base_url=base_url, query={"ac": "note_list"})
        if isinstance(payload, int):
            payload = {"start": payload}
        payload = {"cid": 0, "has_picknews": 1, "page_size": 1150, "start": 0, **payload}
        return self.request(url=api, params=payload, async_=async_, **request_kwargs)

    @overload
    def note_save(
        self, 
        payload: str | dict | list, 
        /, 
        base_url: str | Callable[[], str] = "https://note.115.com", 
        *, 
        async_: Literal[False] = False, 
        **request_kwargs, 
    ) -> dict:
        ...
    @overload
    def note_save(
        self, 
        payload: str | dict | list, 
        /, 
        base_url: str | Callable[[], str] = "https://note.115.com", 
        *, 
        async_: Literal[True], 
        **request_kwargs, 
    ) -> Coroutine[Any, Any, dict]:
        ...
    def note_save(
        self, 
        payload: str | dict | list, 
        /, 
        base_url: str | Callable[[], str] = "https://note.115.com", 
        *, 
        async_: Literal[False, True] = False, 
        **request_kwargs, 
    ) -> dict | Coroutine[Any, Any, dict]:
        """保存备忘（记录/笔记/记事）

        POST https://note.115.com/?ct=note&ac=save

        :payload:
            - nid: int = <default>       💡 记录 id，如果提供就是更新，否则就是新建
            - content: str = <default>   💡 记录的文本，最多 50000 个字符
            - title: str = <default>     💡 标题，最多 927 个字节，可以为空
            - cid: int = 0               💡 分类 id
            - is_html: 0 | 1 = 0         💡 是否 HTML，如果为 1，则会自动加上标签（例如 <p>），以使内容成为合法的 HTML
            - pickcodes: str = <default> 💡 附件的提取码，多个用逗号 "," 隔开
            - tags: str = <default>      💡 标签文本
            - tags[]: str = <default>    💡 标签文本（多个用 "[]" 后缀）
            - ...
            - tags[0]: str = <default>   💡 标签文本（多个用 "[0]","[1]",... 后缀）
            - tags[1]: str = <default>   💡 标签文本
            - ...
            - toc_ids: int | str = <default>
        """
        api = complete_url(base_url=base_url, query={"ct": "note", "ac": "save"})
        if isinstance(payload, str):
            payload = {"content": payload}
        return self.request(url=api, method="POST", data=payload, async_=async_, **request_kwargs)

    @overload
    def note_save2(
        self, 
        payload: str | dict | list, 
        /, 
        base_url: str | Callable[[], str] = "https://note.115.com", 
        *, 
        async_: Literal[False] = False, 
        **request_kwargs, 
    ) -> dict:
        ...
    @overload
    def note_save2(
        self, 
        payload: str | dict | list, 
        /, 
        base_url: str | Callable[[], str] = "https://note.115.com", 
        *, 
        async_: Literal[True], 
        **request_kwargs, 
    ) -> Coroutine[Any, Any, dict]:
        ...
    def note_save2(
        self, 
        payload: str | dict | list, 
        /, 
        base_url: str | Callable[[], str] = "https://note.115.com", 
        *, 
        async_: Literal[False, True] = False, 
        **request_kwargs, 
    ) -> dict | Coroutine[Any, Any, dict]:
        """编辑备忘（记录/笔记/记事）

        POST https://note.115.com/api/2.0/api.php?ac=note_edit

        :payload:
            - nid: int = <default>       💡 记录 id，如果提供就是更新，否则就是新建
            - content: str = <default>   💡 记录的文本，最多 50000 个字符
            - title: str = <default>     💡 标题，最多 927 个字节，可以为空
            - cid: int = <default>       💡 分类 id
            - is_html: 0 | 1 = <default> 💡 是否 HTML，如果为 1，则会自动加上标签（例如 <p>），以使内容成为合法的 HTML
            - pickcodes: str = <default> 💡 附件的提取码，多个用逗号 "," 隔开
            - tags: str = <default>      💡 标签文本
            - tags[]: str = <default>    💡 标签文本（多个用 "[]" 后缀）
            - ...
            - tags[0]: str = <default>   💡 标签文本（多个用 "[0]","[1]",... 后缀）
            - tags[1]: str = <default>   💡 标签文本
            - ...
        """
        api = complete_url("/api/2.0/api.php", base_url=base_url, query={"ac": "note_edit"})
        if isinstance(payload, str):
            payload = {"content": payload}
        return self.request(url=api, method="POST", data=payload, async_=async_, **request_kwargs)

    @overload
    def note_search(
        self, 
        payload: str | dict, 
        /, 
        base_url: str | Callable[[], str] = "https://note.115.com", 
        *, 
        async_: Literal[False] = False, 
        **request_kwargs, 
    ) -> dict:
        ...
    @overload
    def note_search(
        self, 
        payload: str | dict, 
        /, 
        base_url: str | Callable[[], str] = "https://note.115.com", 
        *, 
        async_: Literal[True], 
        **request_kwargs, 
    ) -> Coroutine[Any, Any, dict]:
        ...
    def note_search(
        self, 
        payload: str | dict, 
        /, 
        base_url: str | Callable[[], str] = "https://note.115.com", 
        *, 
        async_: Literal[False, True] = False, 
        **request_kwargs, 
    ) -> dict | Coroutine[Any, Any, dict]:
        """搜索备忘（记录/笔记/记事）

        .. note::
            这个接口支持 GET 和 POST 请求方法

        GET https://note.115.com/api/2.0/api.php?ac=search

        :payload:
            - q: str 💡 搜索词
            - start: int = 0          💡 开始索引，从 0 开始
            - limit: int = 1150       💡 最多返回数量
            - count: int = <default>
            - cid: int = 0            💡 分类 id
            - has_picknews: 0 | 1 = 1 💡 是否显示 id 为负数的分类
            - create_time1: str = <default>
            - create_time2: str = <default>
            - start_time: str = <default>    💡 开始日期，格式为 YYYY-MM-DD
            - end_time: str = <default>      💡 结束日期（含），格式为 YYYY-MM-DD
            - tag_arr: str = <default>    💡 标签文本
            - tag_arr[]: str = <default>  💡 标签文本（多个用 "[]" 后缀）
            - ...
            - tag_arr[0]: str = <default> 💡 标签文本（多个用 "[0]","[1]",... 后缀）
            - tag_arr[1]: str = <default> 💡 标签文本
            - ...
        """
        api = complete_url("/api/2.0/api.php", base_url=base_url, query={"ac": "search"})
        if isinstance(payload, str):
            payload = {"q": payload}
        payload = {"has_picknews": 1, "limit": 1150, "start": 0, **payload}
        if request_kwargs.get("method", "").upper() == "POST":
            return self.request(url=api, data=payload, async_=async_, **request_kwargs)
        else:
            return self.request(url=api, params=payload, async_=async_, **request_kwargs)

    @overload
    def note_set_cate(
        self, 
        payload: dict, 
        /, 
        base_url: str | Callable[[], str] = "https://note.115.com", 
        *, 
        async_: Literal[False] = False, 
        **request_kwargs, 
    ) -> dict:
        ...
    @overload
    def note_set_cate(
        self, 
        payload: dict, 
        /, 
        base_url: str | Callable[[], str] = "https://note.115.com", 
        *, 
        async_: Literal[True], 
        **request_kwargs, 
    ) -> Coroutine[Any, Any, dict]:
        ...
    def note_set_cate(
        self, 
        payload: dict, 
        /, 
        base_url: str | Callable[[], str] = "https://note.115.com", 
        *, 
        async_: Literal[False, True] = False, 
        **request_kwargs, 
    ) -> dict | Coroutine[Any, Any, dict]:
        """修改记录的分类

        POST https://note.115.com/?ct=note&ac=update_note_cate

        :payload:
            - cid: int 💡 分类 id
            - nid: int | str 💡 记录 id，多个用逗号 "," 隔开
        """
        api = complete_url(base_url=base_url, query={"ct": "note", "ac": "update_note_cate"})
        return self.request(url=api, method="POST", data=payload, async_=async_, **request_kwargs)

    @overload
    def note_set_cate2(
        self, 
        payload: dict, 
        /, 
        base_url: str | Callable[[], str] = "https://note.115.com", 
        *, 
        async_: Literal[False] = False, 
        **request_kwargs, 
    ) -> dict:
        ...
    @overload
    def note_set_cate2(
        self, 
        payload: dict, 
        /, 
        base_url: str | Callable[[], str] = "https://note.115.com", 
        *, 
        async_: Literal[True], 
        **request_kwargs, 
    ) -> Coroutine[Any, Any, dict]:
        ...
    def note_set_cate2(
        self, 
        payload: dict, 
        /, 
        base_url: str | Callable[[], str] = "https://note.115.com", 
        *, 
        async_: Literal[False, True] = False, 
        **request_kwargs, 
    ) -> dict | Coroutine[Any, Any, dict]:
        """修改记录的分类

        POST https://note.115.com/api/2.0/api.php?ac=set_note_cate

        :payload:
            - cid: int 💡 分类 id
            - nid: int | str 💡 记录 id，多个用逗号 "," 隔开
        """
        api = complete_url("/api/2.0/api.php", base_url=base_url, query={"ac": "set_note_cate"})
        return self.request(url=api, method="POST", data=payload, async_=async_, **request_kwargs)

    @overload
    def note_set_tag(
        self, 
        payload: dict, 
        /, 
        base_url: str | Callable[[], str] = "https://note.115.com", 
        *, 
        async_: Literal[False] = False, 
        **request_kwargs, 
    ) -> dict:
        ...
    @overload
    def note_set_tag(
        self, 
        payload: dict, 
        /, 
        base_url: str | Callable[[], str] = "https://note.115.com", 
        *, 
        async_: Literal[True], 
        **request_kwargs, 
    ) -> Coroutine[Any, Any, dict]:
        ...
    def note_set_tag(
        self, 
        payload: dict, 
        /, 
        base_url: str | Callable[[], str] = "https://note.115.com", 
        *, 
        async_: Literal[False, True] = False, 
        **request_kwargs, 
    ) -> dict | Coroutine[Any, Any, dict]:
        """修改记录的标签

        POST https://note.115.com/api/2.0/api.php?ac=set_tag

        :payload:
            - nid: int    💡 记录 id
            - tags: str   💡 标签文本
            - tags[]: str 💡 标签文本（多个用 "[]" 后缀）
            - ...
            - tags[0]: str 💡 标签文本（多个用 "[0]","[1]",... 后缀）
            - tags[1]: str 💡 标签文本
            - ...
            - has_picknews: 0 | 1 = <default>
        """
        api = complete_url("/api/2.0/api.php", base_url=base_url, query={"ac": "set_tag"})
        return self.request(url=api, method="POST", data=payload, async_=async_, **request_kwargs)

    @overload
    def note_tag_color(
        self, 
        payload: str | Iterable[str] | dict, 
        /, 
        base_url: str | Callable[[], str] = "https://note.115.com", 
        *, 
        async_: Literal[False] = False, 
        **request_kwargs, 
    ) -> dict:
        ...
    @overload
    def note_tag_color(
        self, 
        payload: str | Iterable[str] | dict, 
        /, 
        base_url: str | Callable[[], str] = "https://note.115.com", 
        *, 
        async_: Literal[True], 
        **request_kwargs, 
    ) -> Coroutine[Any, Any, dict]:
        ...
    def note_tag_color(
        self, 
        payload: str | Iterable[str] | dict, 
        /, 
        base_url: str | Callable[[], str] = "https://note.115.com", 
        *, 
        async_: Literal[False, True] = False, 
        **request_kwargs, 
    ) -> dict | Coroutine[Any, Any, dict]:
        """上传标签，返回标签并提供颜色

        POST https://note.115.com/api/2.0/api.php?ac=get_tag_color

        :payload:
            - tags: str = <default>    💡 标签文本
            - tags[]: str = <default>  💡 标签文本（多个用 "[]" 后缀）
            - ...
            - tags[0]: str = <default> 💡 标签文本（多个用 "[0]","[1]",... 后缀）
            - tags[1]: str = <default> 💡 标签文本
            - ...
        """
        api = complete_url("/api/2.0/api.php", base_url=base_url, query={"ac": "get_tag_color"})
        if isinstance(payload, str):
            payload = {"tags": payload}
        elif payload and not isinstance(payload, dict) and not (isinstance(payload, Sequence) and not isinstance(payload[0], str)):
            payload = {f"tags[{i}]": t for i, t in enumerate(payload)}
        return self.request(url=api, method="POST", data=payload, async_=async_, **request_kwargs)

    @overload
    def note_tag_latest(
        self, 
        payload: str | dict = "", 
        /, 
        base_url: str | Callable[[], str] = "https://note.115.com", 
        *, 
        async_: Literal[False] = False, 
        **request_kwargs, 
    ) -> dict:
        ...
    @overload
    def note_tag_latest(
        self, 
        payload: str | dict = "", 
        /, 
        base_url: str | Callable[[], str] = "https://note.115.com", 
        *, 
        async_: Literal[True], 
        **request_kwargs, 
    ) -> Coroutine[Any, Any, dict]:
        ...
    def note_tag_latest(
        self, 
        payload: str | dict = "", 
        /, 
        base_url: str | Callable[[], str] = "https://note.115.com", 
        *, 
        async_: Literal[False, True] = False, 
        **request_kwargs, 
    ) -> dict | Coroutine[Any, Any, dict]:
        """获取最近使用的标签

        .. note::
            这个接口支持 GET 和 POST 请求方法

        GET https://note.115.com/api/2.0/api.php?ac=get_latest_tags

        :payload:
            - q: str = ""                💡 搜索词
            - is_return_color: 0 | 1 = 1 💡 是否返回颜色
            - limit: int = 1150          💡 最多返回数量
        """
        api = complete_url("/api/2.0/api.php", base_url=base_url, query={"ac": "get_latest_tags"})
        if isinstance(payload, str):
            payload = {"q": payload}
        payload = {"is_return_color": 1, "limit": 1150, **payload}
        return self.request(url=api, params=payload, async_=async_, **request_kwargs)

    @overload
    def note_user_setting(
        self, 
        /, 
        base_url: str | Callable[[], str] = "https://note.115.com", 
        *, 
        async_: Literal[False] = False, 
        **request_kwargs, 
    ) -> dict:
        ...
    @overload
    def note_user_setting(
        self, 
        /, 
        base_url: str | Callable[[], str] = "https://note.115.com", 
        *, 
        async_: Literal[True], 
        **request_kwargs, 
    ) -> Coroutine[Any, Any, dict]:
        ...
    def note_user_setting(
        self, 
        /, 
        base_url: str | Callable[[], str] = "https://note.115.com", 
        *, 
        async_: Literal[False, True] = False, 
        **request_kwargs, 
    ) -> dict | Coroutine[Any, Any, dict]:
        """获取记录的列表展示的配置(目前只有【每页数量设置】）

        GET https://note.115.com/?ct=note&ac=get_user_setting
        """
        api = complete_url(base_url=base_url, query={"ct": "note", "ac": "get_user_setting"})
        return self.request(url=api, async_=async_, **request_kwargs)

    @overload
    def note_user_setting_set(
        self, 
        payload: int | dict, 
        /, 
        base_url: str | Callable[[], str] = "https://note.115.com", 
        *, 
        async_: Literal[False] = False, 
        **request_kwargs, 
    ) -> dict:
        ...
    @overload
    def note_user_setting_set(
        self, 
        payload: int | dict, 
        /, 
        base_url: str | Callable[[], str] = "https://note.115.com", 
        *, 
        async_: Literal[True], 
        **request_kwargs, 
    ) -> Coroutine[Any, Any, dict]:
        ...
    def note_user_setting_set(
        self, 
        payload: int | dict, 
        /, 
        base_url: str | Callable[[], str] = "https://note.115.com", 
        *, 
        async_: Literal[False, True] = False, 
        **request_kwargs, 
    ) -> dict | Coroutine[Any, Any, dict]:
        """修改记录的列表展示的配置

        POST https://note.115.com/?ct=note&ac=set_user_setting

        :payload:
            - note_page_size: 20 | 25 | 50 | 100 💡 每页数量设置
        """
        api = complete_url(base_url=base_url, query={"ct": "note", "ac": "set_user_setting"})
        if isinstance(payload, int):
            payload = {"note_page_size": payload}
        return self.request(url=api, method="POST", data=payload, async_=async_, **request_kwargs)

    ########## Offline Download API ##########

    @overload
    def _offline_web_request(
        self, 
        payload: dict = {}, 
        /, 
        ac: str = "", 
        method: str = "POST", 
        base_url: str | Callable[[], str] = "https://lixian.115.com", 
        *, 
        async_: Literal[False] = False, 
        **request_kwargs, 
    ) -> dict:
        ...
    @overload
    def _offline_web_request(
        self, 
        payload: dict = {}, 
        /, 
        ac: str = "", 
        method: str = "POST", 
        base_url: str | Callable[[], str] = "https://lixian.115.com", 
        *, 
        async_: Literal[True], 
        **request_kwargs, 
    ) -> Coroutine[Any, Any, dict]:
        ...
    def _offline_web_request(
        self, 
        payload: dict = {}, 
        /, 
        ac: str = "", 
        method: str = "POST", 
        base_url: str | Callable[[], str] = "https://lixian.115.com", 
        *, 
        async_: Literal[False, True] = False, 
        **request_kwargs, 
    ) -> dict | Coroutine[Any, Any, dict]:
        api = complete_url("/web/lixian/", base_url=base_url)
        if ac:
            payload["ac"] = ac
        if method.upper() == "POST":
            request_kwargs["data"] = payload
        else:
            request_kwargs["params"] = payload
        return self.request(
            url=api, 
            method=method, 
            async_=async_, 
            **request_kwargs, 
        )

    @overload
    def _offline_lixian_request(
        self, 
        payload: dict = {}, 
        /, 
        ac: str = "", 
        method: str = "POST", 
        base_url: str | Callable[[], str] = "https://lixian.115.com", 
        *, 
        async_: Literal[False] = False, 
        **request_kwargs, 
    ) -> dict:
        ...
    @overload
    def _offline_lixian_request(
        self, 
        payload: dict = {}, 
        /, 
        ac: str = "", 
        method: str = "POST", 
        base_url: str | Callable[[], str] = "https://lixian.115.com", 
        *, 
        async_: Literal[True], 
        **request_kwargs, 
    ) -> Coroutine[Any, Any, dict]:
        ...
    def _offline_lixian_request(
        self, 
        payload: dict = {}, 
        /, 
        ac: str = "", 
        method: str = "POST", 
        base_url: str | Callable[[], str] = "https://lixian.115.com", 
        *, 
        async_: Literal[False, True] = False, 
        **request_kwargs, 
    ) -> dict | Coroutine[Any, Any, dict]:
        api = complete_url("/lixian/", base_url=base_url)
        if ac:
            payload["ac"] = ac
        if method.upper() == "POST":
            request_kwargs["data"] = payload
            request_kwargs.setdefault("ecdh_encrypt", True)
        else:
            request_kwargs["params"] = payload
        return self.request(
            url=api, 
            method=method, 
            async_=async_, 
            **request_kwargs, 
        )

    @overload
    def _offline_lixianssp_request(
        self, 
        payload: dict = {}, 
        /, 
        ac: str = "", 
        base_url: str | Callable[[], str] = "https://lixian.115.com", 
        *, 
        async_: Literal[False] = False, 
        **request_kwargs, 
    ) -> dict:
        ...
    @overload
    def _offline_lixianssp_request(
        self, 
        payload: dict = {}, 
        /, 
        ac: str = "", 
        base_url: str | Callable[[], str] = "https://lixian.115.com", 
        *, 
        async_: Literal[True], 
        **request_kwargs, 
    ) -> Coroutine[Any, Any, dict]:
        ...
    def _offline_lixianssp_request(
        self, 
        payload: dict = {}, 
        /, 
        ac: str = "", 
        base_url: str | Callable[[], str] = "https://lixian.115.com", 
        *, 
        async_: Literal[False, True] = False, 
        **request_kwargs, 
    ) -> dict | Coroutine[Any, Any, dict]:
        api = complete_url("/lixianssp/", base_url=base_url)
        request_kwargs["method"] = "POST"
        for k, v in payload.items():
            payload[k] = str(v)
        if ac:
            payload["ac"] = ac
        payload["app_ver"] = "99.99.99.99"
        request_kwargs["headers"] = {
            **(request_kwargs.get("headers") or {}), 
            "user-agent": "Mozilla/5.0 115disk/99.99.99.99 115Browser/99.99.99.99 115wangpan_android/99.99.99.99", 
        }
        request_kwargs["ecdh_encrypt"] = False
        def parse(_, content: bytes, /) -> dict:
            json = json_loads(content)
            if data := json.get("data"):
                try:
                    json["data"] = json_loads(rsa_decrypt(data))
                except Exception:
                    pass
            return json
        request_kwargs.setdefault("parse", parse)
        return self.request(
            url=api, 
            data={"data": rsa_encrypt(dumps(payload)).decode("ascii")}, 
            async_=async_, 
            **request_kwargs, 
        )

    @overload
    def _offline_request(
        self, 
        payload: dict = {}, 
        /, 
        ac: str = "", 
        method: str = "POST", 
        type: Literal["", "web", "ssp"] = "web", 
        base_url: str | Callable[[], str] = "https://lixian.115.com", 
        *, 
        async_: Literal[False] = False, 
        **request_kwargs, 
    ) -> dict:
        ...
    @overload
    def _offline_request(
        self, 
        payload: dict = {}, 
        /, 
        ac: str = "", 
        method: str = "POST", 
        type: Literal["", "web", "ssp"] = "web", 
        base_url: str | Callable[[], str] = "https://lixian.115.com", 
        *, 
        async_: Literal[True], 
        **request_kwargs, 
    ) -> Coroutine[Any, Any, dict]:
        ...
    def _offline_request(
        self, 
        payload: dict = {}, 
        /, 
        ac: str = "", 
        method: str = "POST", 
        type: Literal["", "web", "ssp"] = "web", 
        base_url: str | Callable[[], str] = "https://lixian.115.com", 
        *, 
        async_: Literal[False, True] = False, 
        **request_kwargs, 
    ) -> dict | Coroutine[Any, Any, dict]:
        match type:
            case "web":
                call: Callable = self._offline_web_request
            case "ssp":
                call = self._offline_lixianssp_request
            case _:
                call = self._offline_lixian_request
        return call(
            payload, 
            ac, 
            method=method, 
            base_url=base_url, 
            async_=async_, 
            **request_kwargs, 
        )

    @overload # type: ignore
    def offline_add_torrent(
        self, 
        payload: str | dict, 
        /, 
        method: str = "POST", 
        type: Literal["", "web", "ssp"] = "ssp", 
        base_url: str | Callable[[], str] = "https://lixian.115.com", 
        *, 
        async_: Literal[False] = False, 
        **request_kwargs, 
    ) -> dict:
        ...
    @overload
    def offline_add_torrent(
        self, 
        payload: str | dict, 
        /, 
        method: str = "POST", 
        type: Literal["", "web", "ssp"] = "ssp", 
        base_url: str | Callable[[], str] = "https://lixian.115.com", 
        *, 
        async_: Literal[True], 
        **request_kwargs, 
    ) -> Coroutine[Any, Any, dict]:
        ...
    def offline_add_torrent(
        self, 
        payload: str | dict, 
        /, 
        method: str = "POST", 
        type: Literal["", "web", "ssp"] = "ssp", 
        base_url: str | Callable[[], str] = "https://lixian.115.com", 
        *, 
        async_: Literal[False, True] = False, 
        **request_kwargs, 
    ) -> dict | Coroutine[Any, Any, dict]:
        """添加一个种子作为离线任务

        POST https://lixian.115.com/lixianssp/?ac=add_task_bt

        .. note::
            `client.offline_add_torrent(info_hash)` 相当于 `client.offline_add_url(f"magnet:?xt=urn:btih:{info_hash}")`

            但此接口的优势是允许选择要下载的文件

        :payload:
            - info_hash: str 💡 种子文件的 info_hash
            - wanted: str = <default> 💡 选择文件进行下载（是数字索引，从 0 开始计数，用 "," 分隔）
            - savepath: str = <default> 💡 保存到 `wp_path_id` 对应目录下的相对路径
            - wp_path_id: int | str = <default> 💡 保存到目录的 id
        """
        if isinstance(payload, str):
            payload = {"info_hash": payload}
        return self._offline_request(
            payload, 
            "add_task_bt", 
            method=method, 
            type=type, 
            base_url=base_url, 
            async_=async_, 
            **request_kwargs, 
        )

    @overload
    def offline_add_url(
        self, 
        payload: str | dict, 
        /, 
        method: str = "POST", 
        type: Literal["", "web", "ssp"] = "ssp", 
        base_url: str | Callable[[], str] = "https://lixian.115.com", 
        *, 
        async_: Literal[False] = False, 
        **request_kwargs, 
    ) -> dict:
        ...
    @overload
    def offline_add_url(
        self, 
        payload: str | dict, 
        /, 
        method: str = "POST", 
        type: Literal["", "web", "ssp"] = "ssp", 
        base_url: str | Callable[[], str] = "https://lixian.115.com", 
        *, 
        async_: Literal[True], 
        **request_kwargs, 
    ) -> Coroutine[Any, Any, dict]:
        ...
    def offline_add_url(
        self, 
        payload: str | dict, 
        /, 
        method: str = "POST", 
        type: Literal["", "web", "ssp"] = "ssp", 
        base_url: str | Callable[[], str] = "https://lixian.115.com", 
        *, 
        async_: Literal[False, True] = False, 
        **request_kwargs, 
    ) -> dict | Coroutine[Any, Any, dict]:
        """添加一个离线任务

        POST https://lixian.115.com/lixianssp/?ac=add_task_url

        :payload:
            - url: str 💡 链接，支持HTTP、HTTPS、FTP、磁力链和电驴链接
            - savepath: str = <default> 💡 保存到目录下的相对路径
            - wp_path_id: int | str = <default> 💡 保存到目录的 id
        """
        if isinstance(payload, str):
            payload = {"url": payload}
        return self._offline_request(
            payload, 
            "add_task_url", 
            method=method, 
            type=type, 
            base_url=base_url, 
            async_=async_, 
            **request_kwargs, 
        )

    @overload # type: ignore
    def offline_add_urls(
        self, 
        payload: str | Iterable[str] | dict, 
        /, 
        method: str = "POST", 
        type: Literal["", "web", "ssp"] = "ssp", 
        base_url: str | Callable[[], str] = "https://lixian.115.com", 
        *, 
        async_: Literal[False] = False, 
        **request_kwargs, 
    ) -> dict:
        ...
    @overload
    def offline_add_urls(
        self, 
        payload: str | Iterable[str] | dict, 
        /, 
        method: str = "POST", 
        type: Literal["", "web", "ssp"] = "ssp", 
        base_url: str | Callable[[], str] = "https://lixian.115.com", 
        *, 
        async_: Literal[True], 
        **request_kwargs, 
    ) -> Coroutine[Any, Any, dict]:
        ...
    def offline_add_urls(
        self, 
        payload: str | Iterable[str] | dict, 
        /, 
        method: str = "POST", 
        type: Literal["", "web", "ssp"] = "ssp", 
        base_url: str | Callable[[], str] = "https://lixian.115.com", 
        *, 
        async_: Literal[False, True] = False, 
        **request_kwargs, 
    ) -> dict | Coroutine[Any, Any, dict]:
        """添加一组离线任务

        POST https://lixian.115.com/lixianssp/?ac=add_task_urls

        :payload:
            - url: str    💡 链接，支持HTTP、HTTPS、FTP、磁力链和电驴链接
            - url[0]: str 💡 链接，支持HTTP、HTTPS、FTP、磁力链和电驴链接
            - url[1]: str
            - ...
            - savepath: str = <default> 💡 保存到目录下的相对路径
            - wp_path_id: int | str = <default> 💡 保存到目录的 id
        """
        if isinstance(payload, str):
            payload = payload.strip("\n").split("\n")
        if not isinstance(payload, dict):
            payload = {f"url[{i}]": url for i, url in enumerate(payload) if url}
            if not payload:
                raise ValueError("no `url` specified")
        return self._offline_request(
            payload, 
            "add_task_urls", 
            method=method, 
            type=type, 
            base_url=base_url, 
            async_=async_, 
            **request_kwargs, 
        )

    @overload # type: ignore
    def offline_clear(
        self, 
        payload: int | dict = 0, 
        /, 
        method: str = "POST", 
        type: Literal["", "web", "ssp"] = "web", 
        base_url: str | Callable[[], str] = "https://lixian.115.com", 
        *, 
        async_: Literal[False] = False, 
        **request_kwargs, 
    ) -> dict:
        ...
    @overload
    def offline_clear(
        self, 
        payload: int | dict = 0, 
        /, 
        method: str = "POST", 
        type: Literal["", "web", "ssp"] = "web", 
        base_url: str | Callable[[], str] = "https://lixian.115.com", 
        *, 
        async_: Literal[True], 
        **request_kwargs, 
    ) -> Coroutine[Any, Any, dict]:
        ...
    def offline_clear(
        self, 
        payload: int | dict = 0, 
        /, 
        method: str = "POST", 
        type: Literal["", "web", "ssp"] = "web", 
        base_url: str | Callable[[], str] = "https://lixian.115.com", 
        *, 
        async_: Literal[False, True] = False, 
        **request_kwargs, 
    ) -> dict | Coroutine[Any, Any, dict]:
        """清空离线任务列表

        POST https://lixian.115.com/lixian/?ac=task_clear

        :payload:
            - flag: int = 0 💡 标识，用于对应某种情况

                - 0: 已完成
                - 1: 全部
                - 2: 已失败
                - 3: 进行中
                - 4: 已完成+删除源文件
                - 5: 全部+删除源文件
        """
        if isinstance(payload, int):
            payload = {"flag": payload}
        return self._offline_request(
            payload, 
            "task_clear", 
            method=method, 
            type=type, 
            base_url=base_url, 
            async_=async_, 
            **request_kwargs, 
        )

    @overload
    def offline_download_path(
        self, 
        /, 
        base_url: str | Callable[[], str] = "https://webapi.115.com", 
        *, 
        async_: Literal[False] = False, 
        **request_kwargs, 
    ) -> dict:
        ...
    @overload
    def offline_download_path(
        self, 
        /, 
        base_url: str | Callable[[], str] = "https://webapi.115.com", 
        *, 
        async_: Literal[True], 
        **request_kwargs, 
    ) -> Coroutine[Any, Any, dict]:
        ...
    def offline_download_path(
        self, 
        /, 
        base_url: str | Callable[[], str] = "https://webapi.115.com", 
        *, 
        async_: Literal[False, True] = False, 
        **request_kwargs, 
    ) -> dict | Coroutine[Any, Any, dict]:
        """获取当前默认的离线下载到的目录信息（可能有多个）

        GET https://webapi.115.com/offine/downpath
        """
        api = complete_url("/offine/downpath", base_url=base_url)
        return self.request(url=api, async_=async_, **request_kwargs)

    @overload
    def offline_download_path_set(
        self, 
        payload: int | str | dict, 
        /, 
        base_url: str | Callable[[], str] = "https://webapi.115.com", 
        *, 
        async_: Literal[False] = False, 
        **request_kwargs, 
    ) -> dict:
        ...
    @overload
    def offline_download_path_set(
        self, 
        payload: int | str | dict, 
        /, 
        base_url: str | Callable[[], str] = "https://webapi.115.com", 
        *, 
        async_: Literal[True], 
        **request_kwargs, 
    ) -> Coroutine[Any, Any, dict]:
        ...
    def offline_download_path_set(
        self, 
        payload: int | str | dict, 
        /, 
        base_url: str | Callable[[], str] = "https://webapi.115.com", 
        *, 
        async_: Literal[False, True] = False, 
        **request_kwargs, 
    ) -> dict | Coroutine[Any, Any, dict]:
        """设置默认选择的离线下载到的目录信息

        POST https://webapi.115.com/offine/downpath

        :payload:
            - file_id: int | str 💡 目录 id
        """
        api = complete_url("/offine/downpath", base_url=base_url)
        if isinstance(payload, (int, str)):
            payload = {"file_id": payload}
        return self.request(url=api, method="POST", data=payload, async_=async_, **request_kwargs)

    @overload # type: ignore
    def offline_list(
        self, 
        payload: int | dict = 1, 
        /, 
        method: str = "GET", 
        type: Literal["", "web", "ssp"] = "web", 
        base_url: str | Callable[[], str] = "https://lixian.115.com", 
        *, 
        async_: Literal[False] = False, 
        **request_kwargs, 
    ) -> dict:
        ...
    @overload
    def offline_list(
        self, 
        payload: int | dict = 1, 
        /, 
        method: str = "GET", 
        type: Literal["", "web", "ssp"] = "web", 
        base_url: str | Callable[[], str] = "https://lixian.115.com", 
        *, 
        async_: Literal[True], 
        **request_kwargs, 
    ) -> Coroutine[Any, Any, dict]:
        ...
    def offline_list(
        self, 
        payload: int | dict = 1, 
        /, 
        method: str = "GET", 
        type: Literal["", "web", "ssp"] = "web", 
        base_url: str | Callable[[], str] = "https://lixian.115.com", 
        *, 
        async_: Literal[False, True] = False, 
        **request_kwargs, 
    ) -> dict | Coroutine[Any, Any, dict]:
        """获取当前的离线任务列表

        GET https://lixian.115.com/lixian/?ac=task_lists

        :payload:
            - page: int = 1
            - page_size: int = 30
            - stat: int = <default> 💡 已知：9:已失败 11:已完成 12:进行中
        """
        if isinstance(payload, int):
            payload = {"page": payload}
        payload.setdefault("page_size", 30)
        return self._offline_request(
            payload, 
            "task_lists", 
            method=method, 
            type=type, 
            base_url=base_url, 
            async_=async_, 
            **request_kwargs, 
        )

    @overload # type: ignore
    def offline_quota_info(
        self, 
        /, 
        method: str = "GET", 
        type: Literal["", "web", "ssp"] = "web", 
        base_url: str | Callable[[], str] = "https://lixian.115.com", 
        *, 
        async_: Literal[False] = False, 
        **request_kwargs, 
    ) -> dict:
        ...
    @overload
    def offline_quota_info(
        self, 
        /, 
        method: str = "GET", 
        type: Literal["", "web", "ssp"] = "web", 
        base_url: str | Callable[[], str] = "https://lixian.115.com", 
        *, 
        async_: Literal[True], 
        **request_kwargs, 
    ) -> Coroutine[Any, Any, dict]:
        ...
    def offline_quota_info(
        self, 
        /, 
        method: str = "GET", 
        type: Literal["", "web", "ssp"] = "web", 
        base_url: str | Callable[[], str] = "https://lixian.115.com", 
        *, 
        async_: Literal[False, True] = False, 
        **request_kwargs, 
    ) -> dict | Coroutine[Any, Any, dict]:
        """获取当前离线配额信息（简略）

        GET https://lixian.115.com/lixian/?ac=get_quota_info
        """
        return self._offline_request(
            ac="get_quota_info", 
            method=method, 
            type=type, 
            base_url=base_url, 
            async_=async_, 
            **request_kwargs, 
        )

    @overload
    def offline_quota_package_array(
        self, 
        /, 
        method: str = "GET", 
        type: Literal["", "web", "ssp"] = "web", 
        base_url: str | Callable[[], str] = "https://lixian.115.com", 
        *, 
        async_: Literal[False] = False, 
        **request_kwargs, 
    ) -> dict:
        ...
    @overload
    def offline_quota_package_array(
        self, 
        /, 
        method: str = "GET", 
        type: Literal["", "web", "ssp"] = "web", 
        base_url: str | Callable[[], str] = "https://lixian.115.com", 
        *, 
        async_: Literal[True], 
        **request_kwargs, 
    ) -> Coroutine[Any, Any, dict]:
        ...
    def offline_quota_package_array(
        self, 
        /, 
        method: str = "GET", 
        type: Literal["", "web", "ssp"] = "web", 
        base_url: str | Callable[[], str] = "https://lixian.115.com", 
        *, 
        async_: Literal[False, True] = False, 
        **request_kwargs, 
    ) -> dict | Coroutine[Any, Any, dict]:
        """获取当前离线配额信息（详细）

        GET https://lixian.115.com/lixian/?ac=get_quota_package_array
        """
        return self._offline_request(
            ac="get_quota_package_array", 
            method=method, 
            type=type, 
            base_url=base_url, 
            async_=async_, 
            **request_kwargs, 
        )

    @overload
    def offline_quota_package_info(
        self, 
        /, 
        method: str = "GET", 
        type: Literal["", "web", "ssp"] = "web", 
        base_url: str | Callable[[], str] = "https://lixian.115.com", 
        *, 
        async_: Literal[False] = False, 
        **request_kwargs, 
    ) -> dict:
        ...
    @overload
    def offline_quota_package_info(
        self, 
        /, 
        method: str = "GET", 
        type: Literal["", "web", "ssp"] = "web", 
        base_url: str | Callable[[], str] = "https://lixian.115.com", 
        *, 
        async_: Literal[True], 
        **request_kwargs, 
    ) -> Coroutine[Any, Any, dict]:
        ...
    def offline_quota_package_info(
        self, 
        /, 
        method: str = "GET", 
        type: Literal["", "web", "ssp"] = "web", 
        base_url: str | Callable[[], str] = "https://lixian.115.com", 
        *, 
        async_: Literal[False, True] = False, 
        **request_kwargs, 
    ) -> dict | Coroutine[Any, Any, dict]:
        """获取当前离线配额信息（详细）

        GET https://lixian.115.com/lixian/?ac=get_quota_package_info
        """
        return self._offline_request(
            ac="get_quota_package_info", 
            method=method, 
            type=type, 
            base_url=base_url, 
            async_=async_, 
            **request_kwargs, 
        )

    @overload # type: ignore
    def offline_remove(
        self, 
        payload: str | Iterable[str] | dict, 
        /, 
        method: str = "POST", 
        type: Literal["", "web", "ssp"] = "web", 
        base_url: str | Callable[[], str] = "https://lixian.115.com", 
        *, 
        async_: Literal[False] = False, 
        **request_kwargs, 
    ) -> dict:
        ...
    @overload
    def offline_remove(
        self, 
        payload: str | Iterable[str] | dict, 
        /, 
        method: str = "POST", 
        type: Literal["", "web", "ssp"] = "web", 
        base_url: str | Callable[[], str] = "https://lixian.115.com", 
        *, 
        async_: Literal[True], 
        **request_kwargs, 
    ) -> Coroutine[Any, Any, dict]:
        ...
    def offline_remove(
        self, 
        payload: str | Iterable[str] | dict, 
        /, 
        method: str = "POST", 
        type: Literal["", "web", "ssp"] = "web", 
        base_url: str | Callable[[], str] = "https://lixian.115.com", 
        *, 
        async_: Literal[False, True] = False, 
        **request_kwargs, 
    ) -> dict | Coroutine[Any, Any, dict]:
        """删除一组离线任务（无论是否已经完成）

        POST https://lixian.115.com/lixian/?ac=task_del

        :payload:
            - hash[0]: str
            - hash[1]: str
            - ...
            - flag: 0 | 1 = <default> 💡 是否删除源文件
        """
        if isinstance(payload, str):
            payload = {"hash[0]": payload}
        elif not isinstance(payload, dict):
            payload = {f"hash[{i}]": hash for i, hash in enumerate(payload)}
            if not payload:
                raise ValueError("no `hash` (info_hash) specified")
        return self._offline_request(
            payload, 
            "task_del", 
            method=method, 
            type=type, 
            base_url=base_url, 
            async_=async_, 
            **request_kwargs, 
        )

    @overload
    def offline_restart(
        self, 
        payload: str | dict, 
        /, 
        method: str = "POST", 
        type: Literal["", "web", "ssp"] = "web", 
        base_url: str | Callable[[], str] = "https://lixian.115.com", 
        *, 
        async_: Literal[False] = False, 
        **request_kwargs, 
    ) -> dict:
        ...
    @overload
    def offline_restart(
        self, 
        payload: str | dict, 
        /, 
        method: str = "POST", 
        type: Literal["", "web", "ssp"] = "web", 
        base_url: str | Callable[[], str] = "https://lixian.115.com", 
        *, 
        async_: Literal[True], 
        **request_kwargs, 
    ) -> Coroutine[Any, Any, dict]:
        ...
    def offline_restart(
        self, 
        payload: str | dict, 
        /, 
        method: str = "POST", 
        type: Literal["", "web", "ssp"] = "web", 
        base_url: str | Callable[[], str] = "https://lixian.115.com", 
        *, 
        async_: Literal[False, True] = False, 
        **request_kwargs, 
    ) -> dict | Coroutine[Any, Any, dict]:
        """重试用户云下载任务

        POST https://lixian.115.com/lixian/?ac=restart

        :payload:
            - info_hash: str 💡 待重试任务的 info_hash
        """
        if isinstance(payload, str):
            payload = {"info_hash": payload}
        return self._offline_request(
            payload, 
            "restart", 
            method=method, 
            type=type, 
            base_url=base_url, 
            async_=async_, 
            **request_kwargs, 
        )

    @overload
    def offline_sign(
        self, 
        /, 
        base_url: str | Callable[[], str] = "https://115.com", 
        *, 
        async_: Literal[False] = False, 
        **request_kwargs, 
    ) -> dict:
        ...
    @overload
    def offline_sign(
        self, 
        /, 
        base_url: str | Callable[[], str] = "https://115.com", 
        *, 
        async_: Literal[True], 
        **request_kwargs, 
    ) -> Coroutine[Any, Any, dict]:
        ...
    def offline_sign(
        self, 
        /, 
        base_url: str | Callable[[], str] = "https://115.com", 
        *, 
        async_: Literal[False, True] = False, 
        **request_kwargs, 
    ) -> dict | Coroutine[Any, Any, dict]:
        """获取 sign 和 time 字段（各个添加任务的接口需要），以及其它信息

        GET https://115.com/?ct=offline&ac=space
        """
        api = complete_url(base_url=base_url, query={"ct": "offline", "ac": "space"})
        return self.request(url=api, async_=async_, **request_kwargs)

    @overload
    def offline_sign_app(
        self, 
        /, 
        app: str = "android", 
        base_url: str | Callable[[], str] = "https://proapi.115.com", 
        *, 
        async_: Literal[False] = False, 
        **request_kwargs, 
    ) -> dict:
        ...
    @overload
    def offline_sign_app(
        self, 
        /, 
        app: str = "android", 
        base_url: str | Callable[[], str] = "https://proapi.115.com", 
        *, 
        async_: Literal[True], 
        **request_kwargs, 
    ) -> Coroutine[Any, Any, dict]:
        ...
    def offline_sign_app(
        self, 
        /, 
        app: str = "android", 
        base_url: str | Callable[[], str] = "https://proapi.115.com", 
        *, 
        async_: Literal[False, True] = False, 
        **request_kwargs, 
    ) -> dict | Coroutine[Any, Any, dict]:
        """获取 sign 和 time 字段（各个添加任务的接口需要）

        GET https://proapi.115.com/android/files/offlinesign
        """
        api = complete_url("/files/offlinesign", base_url=base_url, app=app)
        return self.request(url=api, async_=async_, **request_kwargs)

    @overload
    def offline_task_cnt(
        self, 
        payload: dict | int = 0, 
        /, 
        method: str = "GET", 
        type: Literal["", "web", "ssp"] = "web", 
        base_url: str | Callable[[], str] = "https://lixian.115.com", 
        *, 
        async_: Literal[False] = False, 
        **request_kwargs, 
    ) -> dict:
        ...
    @overload
    def offline_task_cnt(
        self, 
        payload: dict | int = 0, 
        /, 
        method: str = "GET", 
        type: Literal["", "web", "ssp"] = "web", 
        base_url: str | Callable[[], str] = "https://lixian.115.com", 
        *, 
        async_: Literal[True], 
        **request_kwargs, 
    ) -> Coroutine[Any, Any, dict]:
        ...
    def offline_task_cnt(
        self, 
        payload: dict | int = 0, 
        /, 
        method: str = "GET", 
        type: Literal["", "web", "ssp"] = "web", 
        base_url: str | Callable[[], str] = "https://lixian.115.com", 
        *, 
        async_: Literal[False, True] = False, 
        **request_kwargs, 
    ) -> dict | Coroutine[Any, Any, dict]:
        """获取当前正在运行的离线任务数

        GET https://lixian.115.com/lixian/?ac=get_task_cnt

        :payload:
            - flag: int = 0
        """
        if isinstance(payload, int):
            payload = {"flag": payload}
        return self._offline_request(
            payload, 
            "get_task_cnt", 
            method=method, 
            type=type, 
            base_url=base_url, 
            async_=async_, 
            **request_kwargs, 
        )

    @overload
    def offline_task_count(
        self, 
        payload: dict | int = 0, 
        /, 
        method: str = "GET", 
        type: Literal["", "web", "ssp"] = "web", 
        base_url: str | Callable[[], str] = "https://lixian.115.com", 
        *, 
        async_: Literal[False] = False, 
        **request_kwargs, 
    ) -> dict:
        ...
    @overload
    def offline_task_count(
        self, 
        payload: dict | int = 0, 
        /, 
        method: str = "GET", 
        type: Literal["", "web", "ssp"] = "web", 
        base_url: str | Callable[[], str] = "https://lixian.115.com", 
        *, 
        async_: Literal[True], 
        **request_kwargs, 
    ) -> Coroutine[Any, Any, dict]:
        ...
    def offline_task_count(
        self, 
        payload: dict | int = 0, 
        /, 
        method: str = "GET", 
        type: Literal["", "web", "ssp"] = "web", 
        base_url: str | Callable[[], str] = "https://lixian.115.com", 
        *, 
        async_: Literal[False, True] = False, 
        **request_kwargs, 
    ) -> dict | Coroutine[Any, Any, dict]:
        """获取当前各种类型任务的计数

        GET https://lixian.115.com/lixian/?ac=get_task_cnt

        :payload:
            - stat: int = 0 💡 这个参数似乎没什么作用
        """
        if isinstance(payload, int):
            payload = {"stat": payload}
        return self._offline_request(
            payload, 
            "task_count", 
            method=method, 
            type=type, 
            base_url=base_url, 
            async_=async_, 
            **request_kwargs, 
        )

    @overload # type: ignore
    def offline_torrent_info(
        self, 
        payload: str | dict, 
        /, 
        method: str = "GET", 
        type: Literal["", "web", "ssp"] = "web", 
        base_url: str | Callable[[], str] = "https://lixian.115.com", 
        *, 
        async_: Literal[False] = False, 
        **request_kwargs, 
    ) -> dict:
        ...
    @overload
    def offline_torrent_info(
        self, 
        payload: str | dict, 
        /, 
        method: str = "GET", 
        type: Literal["", "web", "ssp"] = "web", 
        base_url: str | Callable[[], str] = "https://lixian.115.com", 
        *, 
        async_: Literal[True], 
        **request_kwargs, 
    ) -> Coroutine[Any, Any, dict]:
        ...
    def offline_torrent_info(
        self, 
        payload: str | dict, 
        /, 
        method: str = "GET", 
        type: Literal["", "web", "ssp"] = "web", 
        base_url: str | Callable[[], str] = "https://lixian.115.com", 
        *, 
        async_: Literal[False, True] = False, 
        **request_kwargs, 
    ) -> dict | Coroutine[Any, Any, dict]:
        """查看种子的文件列表等信息

        GET https://lixian.115.com/lixian/?ac=torrent

        :payload:
            - sha1: str
        """
        if isinstance(payload, str):
            payload = {"sha1": payload}
        return self._offline_request(
            payload, 
            "torrent", 
            method=method, 
            type=type, 
            base_url=base_url, 
            async_=async_, 
            **request_kwargs, 
        )

    @overload
    def offline_upload_torrent_path(
        self, 
        payload: dict | int = 1, 
        /, 
        method: str = "GET", 
        type: Literal["", "web", "ssp"] = "web", 
        base_url: str | Callable[[], str] = "https://lixian.115.com", 
        *, 
        async_: Literal[False] = False, 
        **request_kwargs, 
    ) -> dict:
        ...
    @overload
    def offline_upload_torrent_path(
        self, 
        payload: dict | int = 1, 
        /, 
        method: str = "GET", 
        type: Literal["", "web", "ssp"] = "web", 
        base_url: str | Callable[[], str] = "https://lixian.115.com", 
        *, 
        async_: Literal[True], 
        **request_kwargs, 
    ) -> Coroutine[Any, Any, dict]:
        ...
    def offline_upload_torrent_path(
        self, 
        payload: dict | int = 1, 
        /, 
        method: str = "GET", 
        type: Literal["", "web", "ssp"] = "web", 
        base_url: str | Callable[[], str] = "https://lixian.115.com", 
        *, 
        async_: Literal[False, True] = False, 
        **request_kwargs, 
    ) -> dict | Coroutine[Any, Any, dict]:
        """获取当前的种子上传到的目录，当你添加种子任务后，这个种子会在此目录中保存

        GET https://lixian.115.com/lixian/?ac=get_id

        :payload:
            - torrent: int = 1
        """
        if isinstance(payload, int):
            payload = {"torrent": payload}
        return self._offline_request(
            payload, 
            "get_id", 
            method=method, 
            type=type, 
            base_url=base_url, 
            async_=async_, 
            **request_kwargs, 
        )

    ########## Photo API ##########

    @overload
    def photo_album(
        self, 
        payload: int | str | dict, 
        /, 
        base_url: str | Callable[[], str] = "https://webapi.115.com", 
        *, 
        async_: Literal[False] = False, 
        **request_kwargs, 
    ) -> dict:
        ...
    @overload
    def photo_album(
        self, 
        payload: int | str | dict, 
        /, 
        base_url: str | Callable[[], str] = "https://webapi.115.com", 
        *, 
        async_: Literal[True], 
        **request_kwargs, 
    ) -> Coroutine[Any, Any, dict]:
        ...
    def photo_album(
        self, 
        payload: int | str | dict, 
        /, 
        base_url: str | Callable[[], str] = "https://webapi.115.com", 
        *, 
        async_: Literal[False, True] = False, 
        **request_kwargs, 
    ) -> dict | Coroutine[Any, Any, dict]:
        """获取相册信息

        GET https://webapi.115.com/photo/album

        :payload:
            - album_id: int | str 💡 相册 id，如果为 -1，则是【默认加密相册】
        """
        api = complete_url("/photo/album", base_url=base_url)
        if isinstance(payload, (int, str)):
            payload = {"album_id": payload}
        return self.request(url=api, params=payload, async_=async_, **request_kwargs)

    @overload
    def photo_album_add(
        self, 
        payload: str | dict, 
        /, 
        base_url: str | Callable[[], str] = "https://webapi.115.com", 
        *, 
        async_: Literal[False] = False, 
        **request_kwargs, 
    ) -> dict:
        ...
    @overload
    def photo_album_add(
        self, 
        payload: str | dict, 
        /, 
        base_url: str | Callable[[], str] = "https://webapi.115.com", 
        *, 
        async_: Literal[True], 
        **request_kwargs, 
    ) -> Coroutine[Any, Any, dict]:
        ...
    def photo_album_add(
        self, 
        payload: str | dict, 
        /, 
        base_url: str | Callable[[], str] = "https://webapi.115.com", 
        *, 
        async_: Literal[False, True] = False, 
        **request_kwargs, 
    ) -> dict | Coroutine[Any, Any, dict]:
        """新建相册

        POST https://webapi.115.com/photo/albumadd

        :payload:
            - album_name: str = <default> 💡 相册名称
            - album_desc: str = <default> 💡 相册描述
            - is_secret: 0 | 1 = <default> 💡 是否加密
        """
        api = complete_url("/photo/albumadd", base_url=base_url)
        if isinstance(payload, str):
            payload = {"album_name": payload}
        return self.request(url=api, method="POST", data=payload, async_=async_, **request_kwargs)

    @overload
    def photo_album_group(
        self, 
        payload: dict = {}, 
        /, 
        base_url: str | Callable[[], str] = "https://webapi.115.com", 
        *, 
        async_: Literal[False] = False, 
        **request_kwargs, 
    ) -> dict:
        ...
    @overload
    def photo_album_group(
        self, 
        payload: dict = {}, 
        /, 
        base_url: str | Callable[[], str] = "https://webapi.115.com", 
        *, 
        async_: Literal[True], 
        **request_kwargs, 
    ) -> Coroutine[Any, Any, dict]:
        ...
    def photo_album_group(
        self, 
        payload: dict = {}, 
        /, 
        base_url: str | Callable[[], str] = "https://webapi.115.com", 
        *, 
        async_: Literal[False, True] = False, 
        **request_kwargs, 
    ) -> dict | Coroutine[Any, Any, dict]:
        """获取相册分组

        GET https://webapi.115.com/photo/albumgroup

        :payload:
            - home_page: 0 | 1 = 1
            - limit: int = 100
        """
        api = complete_url("/photo/albumgroup", base_url=base_url)
        payload = {"home_page": 1, "limit": 100, **payload}
        return self.request(url=api, params=payload, async_=async_, **request_kwargs)

    @overload
    def photo_album_list(
        self, 
        payload: int | dict, 
        /, 
        base_url: str | Callable[[], str] = "https://webapi.115.com", 
        *, 
        async_: Literal[False] = False, 
        **request_kwargs, 
    ) -> dict:
        ...
    @overload
    def photo_album_list(
        self, 
        payload: int | dict, 
        /, 
        base_url: str | Callable[[], str] = "https://webapi.115.com", 
        *, 
        async_: Literal[True], 
        **request_kwargs, 
    ) -> Coroutine[Any, Any, dict]:
        ...
    def photo_album_list(
        self, 
        payload: int | dict, 
        /, 
        base_url: str | Callable[[], str] = "https://webapi.115.com", 
        *, 
        async_: Literal[False, True] = False, 
        **request_kwargs, 
    ) -> dict | Coroutine[Any, Any, dict]:
        """获取相册列表

        GET https://webapi.115.com/photo/albumlist

        :payload:
            - offset: int = 0   💡 开始索引，从 0 开始
            - limit: int = 9999 💡 最多返回数量
            - album_type: int = 1💡 相册类型。已知：

                - 1: 个人相册
                - 5: 应用相册
                - 6: 加密相册
        """
        api = complete_url("/photo/albumlist", base_url=base_url)
        if isinstance(payload, int):
            payload = {"offset": payload}
        payload = {"album_type": 1, "limit": 9999, "offset": 0, **payload}
        return self.request(url=api, params=payload, async_=async_, **request_kwargs)

    @overload
    def photo_album_update(
        self, 
        payload: dict, 
        /, 
        base_url: str | Callable[[], str] = "https://webapi.115.com", 
        *, 
        async_: Literal[False] = False, 
        **request_kwargs, 
    ) -> dict:
        ...
    @overload
    def photo_album_update(
        self, 
        payload: dict, 
        /, 
        base_url: str | Callable[[], str] = "https://webapi.115.com", 
        *, 
        async_: Literal[True], 
        **request_kwargs, 
    ) -> Coroutine[Any, Any, dict]:
        ...
    def photo_album_update(
        self, 
        payload: dict, 
        /, 
        base_url: str | Callable[[], str] = "https://webapi.115.com", 
        *, 
        async_: Literal[False, True] = False, 
        **request_kwargs, 
    ) -> dict | Coroutine[Any, Any, dict]:
        """更新相册

        POST https://webapi.115.com/photo/album

        :payload:
            - album_id: int | str 💡 相册 id，如果为 -1，则是【默认加密相册】
            - album_name: str = <default> 💡 相册名称
            - album_desc: str = <default> 💡 相册描述
            - album_state: 0 | 1 = <default> 💡 是否删除：0:保留 1:删除
            - is_secret: 0 | 1 = <default> 💡 是否加密
        """
        api = complete_url("/photo/album", base_url=base_url)
        return self.request(url=api, method="POST", data=payload, async_=async_, **request_kwargs)

    @overload
    def photo_bind(
        self, 
        payload: dict, 
        /, 
        base_url: str | Callable[[], str] = "https://webapi.115.com", 
        *, 
        async_: Literal[False] = False, 
        **request_kwargs, 
    ) -> dict:
        ...
    @overload
    def photo_bind(
        self, 
        payload: dict, 
        /, 
        base_url: str | Callable[[], str] = "https://webapi.115.com", 
        *, 
        async_: Literal[True], 
        **request_kwargs, 
    ) -> Coroutine[Any, Any, dict]:
        ...
    def photo_bind(
        self, 
        payload: dict, 
        /, 
        base_url: str | Callable[[], str] = "https://webapi.115.com", 
        *, 
        async_: Literal[False, True] = False, 
        **request_kwargs, 
    ) -> dict | Coroutine[Any, Any, dict]:
        """图片到相册的关联

        POST https://webapi.115.com/photo/photo

        .. note::
            虽然被认为是图片的格式很多（你可以用这个方法 `client.fs_files_second_type({"type": 2})` 获得网盘中的所有图片格式），但仅支持以下格式图片添加到相册：jpg,jpeg,png,gif,svg,webp,heic,bmp,dng

        .. caution::
            目前好像仅支持把图片添加到相册，却不支持从中移除

        :payload:
            - to_album_id: int | str 💡 相册 id，如果为 -1，则添加到【默认加密相册】
            - file_ids: int | str 💡 文件 id，多个用逗号 "," 隔开
            - action: str = "addtoalbum" 💡 动作。"addtoalbum":添加到相册
        """
        api = complete_url("/photo/photo", base_url=base_url)
        payload.setdefault("action", "addtoalbum")
        return self.request(url=api, method="POST", data=payload, async_=async_, **request_kwargs)

    @overload
    def photo_list(
        self, 
        payload: int | dict, 
        /, 
        base_url: str | Callable[[], str] = "https://webapi.115.com", 
        *, 
        async_: Literal[False] = False, 
        **request_kwargs, 
    ) -> dict:
        ...
    @overload
    def photo_list(
        self, 
        payload: int | dict, 
        /, 
        base_url: str | Callable[[], str] = "https://webapi.115.com", 
        *, 
        async_: Literal[True], 
        **request_kwargs, 
    ) -> Coroutine[Any, Any, dict]:
        ...
    def photo_list(
        self, 
        payload: int | dict, 
        /, 
        base_url: str | Callable[[], str] = "https://webapi.115.com", 
        *, 
        async_: Literal[False, True] = False, 
        **request_kwargs, 
    ) -> dict | Coroutine[Any, Any, dict]:
        """获取图片列表

        GET https://webapi.115.com/photo/photolist

        :payload:
            - offset: int = 0   💡 开始索引，从 0 开始
            - limit: int = 1150 💡 最多返回数量
            - album_id: int | str = <default> 💡 相册 id。如果为 -1，则是【默认加密相册】；如果不指定，则是所有相册
            - key_word: str = <default>
            - type: int = <default>
            - tr: str = <default> 💡 时间线，是一个日期，格式为 YYYYMMDD
            - order: str = <default> 💡 排序依据，例如 "add_time"
            - is_asc: 0 | 1 = <default> 💡 是否升序排列
        """
        api = complete_url("/photo/photolist", base_url=base_url)
        if isinstance(payload, int):
            payload = {"offset": payload}
        payload.setdefault("limit", 1150)
        return self.request(url=api, params=payload, async_=async_, **request_kwargs)

    @overload
    def photo_sharealbum(
        self, 
        payload: int | str | dict, 
        /, 
        base_url: str | Callable[[], str] = "https://webapi.115.com", 
        *, 
        async_: Literal[False] = False, 
        **request_kwargs, 
    ) -> dict:
        ...
    @overload
    def photo_sharealbum(
        self, 
        payload: int | str | dict, 
        /, 
        base_url: str | Callable[[], str] = "https://webapi.115.com", 
        *, 
        async_: Literal[True], 
        **request_kwargs, 
    ) -> Coroutine[Any, Any, dict]:
        ...
    def photo_sharealbum(
        self, 
        payload: int | str | dict, 
        /, 
        base_url: str | Callable[[], str] = "https://webapi.115.com", 
        *, 
        async_: Literal[False, True] = False, 
        **request_kwargs, 
    ) -> dict | Coroutine[Any, Any, dict]:
        """获取共享相册信息

        GET https://webapi.115.com/photo/sharealbum

        :payload:
            - album_id: int | str 💡 相册 id
        """
        api = complete_url("/photo/sharealbum", base_url=base_url)
        if isinstance(payload, (int, str)):
            payload = {"album_id": payload}
        return self.request(url=api, params=payload, async_=async_, **request_kwargs)

    @overload
    def photo_sharealbum_add(
        self, 
        payload: str | dict, 
        /, 
        base_url: str | Callable[[], str] = "https://webapi.115.com", 
        *, 
        async_: Literal[False] = False, 
        **request_kwargs, 
    ) -> dict:
        ...
    @overload
    def photo_sharealbum_add(
        self, 
        payload: str | dict, 
        /, 
        base_url: str | Callable[[], str] = "https://webapi.115.com", 
        *, 
        async_: Literal[True], 
        **request_kwargs, 
    ) -> Coroutine[Any, Any, dict]:
        ...
    def photo_sharealbum_add(
        self, 
        payload: str | dict, 
        /, 
        base_url: str | Callable[[], str] = "https://webapi.115.com", 
        *, 
        async_: Literal[False, True] = False, 
        **request_kwargs, 
    ) -> dict | Coroutine[Any, Any, dict]:
        """新建共享相册

        POST https://webapi.115.com/photo/sharealbumadd

        :payload:
            - album_name: str = <default> 💡 相册名称
            - album_desc: str = <default> 💡 相册描述
        """
        api = complete_url("/photo/sharealbumadd", base_url=base_url)
        if isinstance(payload, str):
            payload = {"album_name": payload}
        return self.request(url=api, method="POST", data=payload, async_=async_, **request_kwargs)

    @overload
    def photo_sharealbum_list(
        self, 
        payload: int | dict, 
        /, 
        base_url: str | Callable[[], str] = "https://webapi.115.com", 
        *, 
        async_: Literal[False] = False, 
        **request_kwargs, 
    ) -> dict:
        ...
    @overload
    def photo_sharealbum_list(
        self, 
        payload: int | dict, 
        /, 
        base_url: str | Callable[[], str] = "https://webapi.115.com", 
        *, 
        async_: Literal[True], 
        **request_kwargs, 
    ) -> Coroutine[Any, Any, dict]:
        ...
    def photo_sharealbum_list(
        self, 
        payload: int | dict, 
        /, 
        base_url: str | Callable[[], str] = "https://webapi.115.com", 
        *, 
        async_: Literal[False, True] = False, 
        **request_kwargs, 
    ) -> dict | Coroutine[Any, Any, dict]:
        """获取共享相册列表

        GET https://webapi.115.com/photo/sharealbumlist

        :payload:
            - offset: int = 0   💡 开始索引，从 0 开始
            - limit: int = 1150 💡 最多返回数量
            - is_asc: 0 | 1 = <default> 💡 是否升序排列
            - order: str = <default> 💡 排序依据，例如 "update_time"
        """
        api = complete_url("/photo/sharealbumlist", base_url=base_url)
        if isinstance(payload, int):
            payload = {"offset": payload}
        payload = {"limit": 1150, "offset": 0, **payload}
        return self.request(url=api, params=payload, async_=async_, **request_kwargs)

    @overload
    def photo_sharealbum_member(
        self, 
        payload: int | dict, 
        /, 
        base_url: str | Callable[[], str] = "https://webapi.115.com", 
        *, 
        async_: Literal[False] = False, 
        **request_kwargs, 
    ) -> dict:
        ...
    @overload
    def photo_sharealbum_member(
        self, 
        payload: int | dict, 
        /, 
        base_url: str | Callable[[], str] = "https://webapi.115.com", 
        *, 
        async_: Literal[True], 
        **request_kwargs, 
    ) -> Coroutine[Any, Any, dict]:
        ...
    def photo_sharealbum_member(
        self, 
        payload: int | dict, 
        /, 
        base_url: str | Callable[[], str] = "https://webapi.115.com", 
        *, 
        async_: Literal[False, True] = False, 
        **request_kwargs, 
    ) -> dict | Coroutine[Any, Any, dict]:
        """获取共享相册的成员用户列表

        GET https://webapi.115.com/photo/sharealbummember

        :payload:
            - album_id: int | str = <default> 💡 相册 id
            - order: str = <default> 💡 排序依据，例如 "join_time"
            - is_asc: 0 | 1 = <default> 💡 是否升序排列
        """
        api = complete_url("/photo/sharealbummember", base_url=base_url)
        if isinstance(payload, int):
            payload = {"album_id": payload}
        return self.request(url=api, params=payload, async_=async_, **request_kwargs)

    @overload
    def photo_sharealbum_record_list(
        self, 
        payload: int | dict, 
        /, 
        base_url: str | Callable[[], str] = "https://webapi.115.com", 
        *, 
        async_: Literal[False] = False, 
        **request_kwargs, 
    ) -> dict:
        ...
    @overload
    def photo_sharealbum_record_list(
        self, 
        payload: int | dict, 
        /, 
        base_url: str | Callable[[], str] = "https://webapi.115.com", 
        *, 
        async_: Literal[True], 
        **request_kwargs, 
    ) -> Coroutine[Any, Any, dict]:
        ...
    def photo_sharealbum_record_list(
        self, 
        payload: int | dict, 
        /, 
        base_url: str | Callable[[], str] = "https://webapi.115.com", 
        *, 
        async_: Literal[False, True] = False, 
        **request_kwargs, 
    ) -> dict | Coroutine[Any, Any, dict]:
        """获取共享相册的操作记录列表

        GET https://webapi.115.com/photo/sharealbumrecordlist

        :payload:
            - offset: int = 0     💡 开始索引，从 0 开始
            - limit: int = 1150   💡 最多返回数量
            - album_id: int | str = <default> 💡 相册 id
        """
        api = complete_url("/photo/sharealbumrecordlist", base_url=base_url)
        if isinstance(payload, int):
            payload = {"offset": payload}
        payload = {"limit": 1150, "offset": 0, **payload}
        return self.request(url=api, params=payload, async_=async_, **request_kwargs)

    @overload
    def photo_sharealbum_record_update(
        self, 
        payload: dict, 
        /, 
        base_url: str | Callable[[], str] = "https://webapi.115.com", 
        *, 
        async_: Literal[False] = False, 
        **request_kwargs, 
    ) -> dict:
        ...
    @overload
    def photo_sharealbum_record_update(
        self, 
        payload: dict, 
        /, 
        base_url: str | Callable[[], str] = "https://webapi.115.com", 
        *, 
        async_: Literal[True], 
        **request_kwargs, 
    ) -> Coroutine[Any, Any, dict]:
        ...
    def photo_sharealbum_record_update(
        self, 
        payload: dict, 
        /, 
        base_url: str | Callable[[], str] = "https://webapi.115.com", 
        *, 
        async_: Literal[False, True] = False, 
        **request_kwargs, 
    ) -> dict | Coroutine[Any, Any, dict]:
        """在共享相册中增加或删除 1 条记录

        POST https://webapi.115.com/photo/sharealbumrecord

        :payload:
            - album_id: int | str 💡 相册 id
            - action: "add" | "del" 💡 操作。"add":添加记录 "del":删除记录
            - record_id: int | str = <default> 💡 记录 id
            - record_content: str = <default> 💡 记录的描述文本
            - file_ids: int | str = <default> 💡 记录关联的（在网盘中的）文件 id，多个用逗号 "," 隔开
        """
        api = complete_url("/photo/sharealbumrecord", base_url=base_url)
        return self.request(url=api, method="POST", data=payload, async_=async_, **request_kwargs)

    @overload
    def photo_sharealbum_update(
        self, 
        payload: dict, 
        /, 
        base_url: str | Callable[[], str] = "https://webapi.115.com", 
        *, 
        async_: Literal[False] = False, 
        **request_kwargs, 
    ) -> dict:
        ...
    @overload
    def photo_sharealbum_update(
        self, 
        payload: dict, 
        /, 
        base_url: str | Callable[[], str] = "https://webapi.115.com", 
        *, 
        async_: Literal[True], 
        **request_kwargs, 
    ) -> Coroutine[Any, Any, dict]:
        ...
    def photo_sharealbum_update(
        self, 
        payload: dict, 
        /, 
        base_url: str | Callable[[], str] = "https://webapi.115.com", 
        *, 
        async_: Literal[False, True] = False, 
        **request_kwargs, 
    ) -> dict | Coroutine[Any, Any, dict]:
        """更新共享相册

        POST https://webapi.115.com/photo/sharealbum

        :payload:
            - album_id: int | str 💡 相册 id
            - album_name: str = <default>  💡 相册名称
            - album_desc: str = <default>  💡 相册描述
            - album_cover: str = <default> 💡 相册封面，图片的 sha1 值
            - album_state: 0 | 1 = <default> 💡 是否删除：0:保留 1:删除
            - is_top: 0 | 1 = <default> 💡 是否置顶
            - user_nick_name: str = <default> 💡 用户昵称
        """
        api = complete_url("/photo/sharealbum", base_url=base_url)
        return self.request(url=api, method="POST", data=payload, async_=async_, **request_kwargs)

    @overload
    def photo_share_list(
        self, 
        payload: int | dict, 
        /, 
        base_url: str | Callable[[], str] = "https://webapi.115.com", 
        *, 
        async_: Literal[False] = False, 
        **request_kwargs, 
    ) -> dict:
        ...
    @overload
    def photo_share_list(
        self, 
        payload: int | dict, 
        /, 
        base_url: str | Callable[[], str] = "https://webapi.115.com", 
        *, 
        async_: Literal[True], 
        **request_kwargs, 
    ) -> Coroutine[Any, Any, dict]:
        ...
    def photo_share_list(
        self, 
        payload: int | dict, 
        /, 
        base_url: str | Callable[[], str] = "https://webapi.115.com", 
        *, 
        async_: Literal[False, True] = False, 
        **request_kwargs, 
    ) -> dict | Coroutine[Any, Any, dict]:
        """获取共享相册的图片列表

        GET https://webapi.115.com/photo/sharephotolist

        :payload:
            - offset: int = 0   💡 开始索引，从 0 开始
            - limit: int = 1150 💡 最多返回数量
            - album_id: int | str = <default> 💡 相册 id
            - record_id: int | str = <default> 💡 操作记录 id
            - key_word: str = <default>
            - type: int = <default>
            - tr: str = <default> 💡 时间线，是一个日期，格式为 YYYYMMDD
            - order: str = <default> 💡 排序依据，例如 "add_time"
            - is_asc: 0 | 1 = <default> 💡 是否升序排列
        """
        api = complete_url("/photo/sharephotolist", base_url=base_url)
        if isinstance(payload, int):
            payload = {"offset": payload}
        payload.setdefault("limit", 1150)
        return self.request(url=api, params=payload, async_=async_, **request_kwargs)

    @overload
    def photo_share_remove(
        self, 
        payload: dict, 
        /, 
        base_url: str | Callable[[], str] = "https://webapi.115.com", 
        *, 
        async_: Literal[False] = False, 
        **request_kwargs, 
    ) -> dict:
        ...
    @overload
    def photo_share_remove(
        self, 
        payload: dict, 
        /, 
        base_url: str | Callable[[], str] = "https://webapi.115.com", 
        *, 
        async_: Literal[True], 
        **request_kwargs, 
    ) -> Coroutine[Any, Any, dict]:
        ...
    def photo_share_remove(
        self, 
        payload: dict, 
        /, 
        base_url: str | Callable[[], str] = "https://webapi.115.com", 
        *, 
        async_: Literal[False, True] = False, 
        **request_kwargs, 
    ) -> dict | Coroutine[Any, Any, dict]:
        """把共享相册的图片移除

        POST https://webapi.115.com/photo/sharephoto

        :payload:
            - album_id: int | str 💡 相册 id
            - photo_ids: int | str = <default> 💡 （在相册中的）图片 id，多个用逗号 "," 隔开
        """
        api = complete_url("/photo/sharephoto", base_url=base_url)
        return self.request(url=api, method="POST", data=payload, async_=async_, **request_kwargs)

    @overload
    def photo_share_save(
        self, 
        payload: dict, 
        /, 
        base_url: str | Callable[[], str] = "https://webapi.115.com", 
        *, 
        async_: Literal[False] = False, 
        **request_kwargs, 
    ) -> dict:
        ...
    @overload
    def photo_share_save(
        self, 
        payload: dict, 
        /, 
        base_url: str | Callable[[], str] = "https://webapi.115.com", 
        *, 
        async_: Literal[True], 
        **request_kwargs, 
    ) -> Coroutine[Any, Any, dict]:
        ...
    def photo_share_save(
        self, 
        payload: dict, 
        /, 
        base_url: str | Callable[[], str] = "https://webapi.115.com", 
        *, 
        async_: Literal[False, True] = False, 
        **request_kwargs, 
    ) -> dict | Coroutine[Any, Any, dict]:
        """把共享相册的图片保存到照片库

        POST https://webapi.115.com/photo/sharephotosave

        :payload:
            - album_id: int | str 💡 相册 id
            - photo_ids: int | str = <default> 💡 （在相册中的）图片 id，多个用逗号 "," 隔开
        """
        api = complete_url("/photo/sharephotosave", base_url=base_url)
        return self.request(url=api, method="POST", data=payload, async_=async_, **request_kwargs)

    @overload
    def photo_share_timeline(
        self, 
        payload: int | dict, 
        /, 
        base_url: str | Callable[[], str] = "https://webapi.115.com", 
        *, 
        async_: Literal[False] = False, 
        **request_kwargs, 
    ) -> dict:
        ...
    @overload
    def photo_share_timeline(
        self, 
        payload: int | dict, 
        /, 
        base_url: str | Callable[[], str] = "https://webapi.115.com", 
        *, 
        async_: Literal[True], 
        **request_kwargs, 
    ) -> Coroutine[Any, Any, dict]:
        ...
    def photo_share_timeline(
        self, 
        payload: int | dict, 
        /, 
        base_url: str | Callable[[], str] = "https://webapi.115.com", 
        *, 
        async_: Literal[False, True] = False, 
        **request_kwargs, 
    ) -> dict | Coroutine[Any, Any, dict]:
        """获取共享相册的时间线列表，然后你可以通过 `client.photo_share_list` 获取对应时间线的图片列表

        GET https://webapi.115.com/photo/sharephototimeline

        :payload:
            - offset: int = 0    💡 开始索引，从 0 开始
            - limit: int = 99999 💡 最多返回数量
            - album_id: int | str = <default> 💡 相册 id。如果为 -1，则是【默认加密相册】；如果不指定，则是所有相册
            - key_word: str = <default>
        """
        api = complete_url("/photo/sharephototimeline", base_url=base_url)
        if isinstance(payload, int):
            payload = {"offset": payload}
        payload.setdefault("limit", 99999)
        return self.request(url=api, params=payload, async_=async_, **request_kwargs)

    @overload
    def photo_timeline(
        self, 
        payload: int | dict, 
        /, 
        base_url: str | Callable[[], str] = "https://webapi.115.com", 
        *, 
        async_: Literal[False] = False, 
        **request_kwargs, 
    ) -> dict:
        ...
    @overload
    def photo_timeline(
        self, 
        payload: int | dict, 
        /, 
        base_url: str | Callable[[], str] = "https://webapi.115.com", 
        *, 
        async_: Literal[True], 
        **request_kwargs, 
    ) -> Coroutine[Any, Any, dict]:
        ...
    def photo_timeline(
        self, 
        payload: int | dict, 
        /, 
        base_url: str | Callable[[], str] = "https://webapi.115.com", 
        *, 
        async_: Literal[False, True] = False, 
        **request_kwargs, 
    ) -> dict | Coroutine[Any, Any, dict]:
        """获取时间线列表，然后你可以通过 `client.photo_list` 获取对应时间线的图片列表

        GET https://webapi.115.com/photo/phototimeline

        :payload:
            - offset: int = 0    💡 开始索引，从 0 开始
            - limit: int = 99999 💡 最多返回数量
            - album_id: int | str = <default> 💡 相册 id。如果为 -1，则是【默认加密相册】；如果不指定，则是所有相册
            - key_word: str = <default>
        """
        api = complete_url("/photo/phototimeline", base_url=base_url)
        if isinstance(payload, int):
            payload = {"offset": payload}
        payload.setdefault("limit", 99999)
        return self.request(url=api, params=payload, async_=async_, **request_kwargs)

    ########## Recyclebin API ##########

    @overload
    def recyclebin_clean(
        self, 
        payload: int | str | Iterable[int | str] | dict = "", 
        /, 
        base_url: str | Callable[[], str] = "https://webapi.115.com", 
        *, 
        async_: Literal[False] = False, 
        **request_kwargs, 
    ) -> dict:
        ...
    @overload
    def recyclebin_clean(
        self, 
        payload: int | str | Iterable[int | str] | dict = "", 
        /, 
        base_url: str | Callable[[], str] = "https://webapi.115.com", 
        *, 
        async_: Literal[True], 
        **request_kwargs, 
    ) -> Coroutine[Any, Any, dict]:
        ...
    def recyclebin_clean(
        self, 
        payload: int | str | Iterable[int | str] | dict = "", 
        /, 
        base_url: str | Callable[[], str] = "https://webapi.115.com", 
        *, 
        async_: Literal[False, True] = False, 
        **request_kwargs, 
    ) -> dict | Coroutine[Any, Any, dict]:
        """回收站：删除或清空

        POST https://webapi.115.com/rb/secret_del

        .. note::
            只要不指定 `tid`，就会清空回收站

        .. note::
            可以在设置中的【账号安全/安全密钥】页面下，关闭【文件(隐藏模式/清空删除回收站)】的按钮，就不需要传安全密钥了

        :payload:
            - tid: int | str = "" 💡 多个用逗号 "," 隔开
            - password: int | str = "000000" 💡 安全密钥，是 6 位数字
        """
        api = complete_url("/rb/secret_del", base_url=base_url)
        if isinstance(payload, (int, str)):
            payload = {"tid": payload}
        elif not isinstance(payload, dict):
            payload = {"tid": ",".join(map(str, payload))}
        payload.setdefault("password", format(payload.get("password") or "", ">06"))
        return self.request(url=api, method="POST", data=payload, async_=async_, **request_kwargs)

    @overload
    def recyclebin_clean2(
        self, 
        payload: int | str | Iterable[int | str] | dict = "", 
        /, 
        base_url: str | Callable[[], str] = "https://webapi.115.com", 
        *, 
        async_: Literal[False] = False, 
        **request_kwargs, 
    ) -> dict:
        ...
    @overload
    def recyclebin_clean2(
        self, 
        payload: int | str | Iterable[int | str] | dict = "", 
        /, 
        base_url: str | Callable[[], str] = "https://webapi.115.com", 
        *, 
        async_: Literal[True], 
        **request_kwargs, 
    ) -> Coroutine[Any, Any, dict]:
        ...
    def recyclebin_clean2(
        self, 
        payload: int | str | Iterable[int | str] | dict = "", 
        /, 
        base_url: str | Callable[[], str] = "https://webapi.115.com", 
        *, 
        async_: Literal[False, True] = False, 
        **request_kwargs, 
    ) -> dict | Coroutine[Any, Any, dict]:
        """回收站：删除或清空

        POST https://webapi.115.com/rb/clean

        .. note::
            如果没有指定任一 `rid`，就是清空回收站

        .. tip::
            这个接口必须提供安全密钥。如果不提供，则默认使用 "000000"，在不必要的情况下，完全可以把安全密钥设为这个值

        :payload:
            - rid[0]: int | str
            - rid[1]: int | str
            - ...
            - password: int | str = "000000" 💡 安全密钥
        """
        api = complete_url("/rb/clean", base_url=base_url)
        if isinstance(payload, (int, str)):
            payload = {"rid[0]": payload}
        elif not isinstance(payload, dict):
            payload = {f"rid[{i}]": rid for i, rid in enumerate(payload)}
        payload["password"] = format(payload.get("password") or "", ">06")
        return self.request(url=api, method="POST", data=payload, async_=async_, **request_kwargs)

    @overload
    def recyclebin_clean_app(
        self, 
        payload: int | str | Iterable[int | str] | dict = "", 
        /, 
        app: str = "android", 
        base_url: str | Callable[[], str] = "https://proapi.115.com", 
        *, 
        async_: Literal[False] = False, 
        **request_kwargs, 
    ) -> dict:
        ...
    @overload
    def recyclebin_clean_app(
        self, 
        payload: int | str | Iterable[int | str] | dict = "", 
        /, 
        app: str = "android", 
        base_url: str | Callable[[], str] = "https://proapi.115.com", 
        *, 
        async_: Literal[True], 
        **request_kwargs, 
    ) -> Coroutine[Any, Any, dict]:
        ...
    def recyclebin_clean_app(
        self, 
        payload: int | str | Iterable[int | str] | dict = "", 
        /, 
        app: str = "android", 
        base_url: str | Callable[[], str] = "https://proapi.115.com", 
        *, 
        async_: Literal[False, True] = False, 
        **request_kwargs, 
    ) -> dict | Coroutine[Any, Any, dict]:
        """回收站：删除或清空

        POST https://proapi.115.com/android/rb/secret_del

        .. note::
            只要不指定 `tid`，就会清空回收站

        .. note::
            可以在设置中的【账号安全/安全密钥】页面下，关闭【文件(隐藏模式/清空删除回收站)】的按钮，就不需要传安全密钥了

        :payload:
            - tid: int | str = "" 💡 多个用逗号 "," 隔开
            - password: int | str = "000000" 💡 安全密钥，是 6 位数字
            - user_id: int | str = <default> 💡 用户 id
        """
        api = complete_url("/rb/secret_del", base_url=base_url, app=app)
        if isinstance(payload, (int, str)):
            payload = {"tid": payload}
        elif not isinstance(payload, dict):
            payload = {"tid": ",".join(map(str, payload))}
        payload = {
            "user_id": self.user_id, 
            "password": format(payload.get("password") or "", ">06"), 
            **payload, 
        }
        return self.request(url=api, method="POST", data=payload, async_=async_, **request_kwargs)

    @overload
    def recyclebin_info(
        self, 
        payload: int | str | dict, 
        /, 
        base_url: str | Callable[[], str] = "https://webapi.115.com", 
        *, 
        async_: Literal[False] = False, 
        **request_kwargs, 
    ) -> dict:
        ...
    @overload
    def recyclebin_info(
        self, 
        payload: int | str | dict, 
        /, 
        base_url: str | Callable[[], str] = "https://webapi.115.com", 
        *, 
        async_: Literal[True], 
        **request_kwargs, 
    ) -> Coroutine[Any, Any, dict]:
        ...
    def recyclebin_info(
        self, 
        payload: int | str | dict, 
        /, 
        base_url: str | Callable[[], str] = "https://webapi.115.com", 
        *, 
        async_: Literal[False, True] = False, 
        **request_kwargs, 
    ) -> dict | Coroutine[Any, Any, dict]:
        """回收站：文件信息

        POST https://webapi.115.com/rb/rb_info

        :payload:
            - rid: int | str
        """
        api = complete_url("/rb/rb_info", base_url=base_url)
        if isinstance(payload, (int, str)):
            payload = {"rid": payload}
        return self.request(url=api, params=payload, async_=async_, **request_kwargs)

    @overload
    def recyclebin_list(
        self, 
        payload: int | dict = 0, 
        /, 
        base_url: str | Callable[[], str] = "https://webapi.115.com", 
        *, 
        async_: Literal[False] = False, 
        **request_kwargs, 
    ) -> dict:
        ...
    @overload
    def recyclebin_list(
        self, 
        payload: int | dict = 0, 
        /, 
        base_url: str | Callable[[], str] = "https://webapi.115.com", 
        *, 
        async_: Literal[True], 
        **request_kwargs, 
    ) -> Coroutine[Any, Any, dict]:
        ...
    def recyclebin_list(
        self, 
        payload: int | dict = 0, 
        /, 
        base_url: str | Callable[[], str] = "https://webapi.115.com", 
        *, 
        async_: Literal[False, True] = False, 
        **request_kwargs, 
    ) -> dict | Coroutine[Any, Any, dict]:
        """回收站：列表

        GET https://webapi.115.com/rb

        :payload:
            - aid: int = 7 💡 area_id

                - 0: 会被视为 1
                - 1: 正常文件
                - 2: <unknown>
                - 3: <unknown>
                - 4: <unknown>
                - 5: <unknown>
                - 7: 回收站文件
                - 9: <unknown>
                - 12:瞬间文件
                - 15: <unknown>
                - 120: 彻底删除文件、简历附件
                - <其它>: 会被视为 0

            - cid: int | str = 0
            - limit: int = 32
            - offset: int = 0
            - source: str = <default>
        """ 
        api = complete_url("/rb", base_url=base_url)
        if isinstance(payload, int):
            payload = {"offset": payload}
        payload = {"aid": 7, "cid": 0, "limit": 32, "offset": 0, **payload}
        return self.request(url=api, params=payload, async_=async_, **request_kwargs)

    @overload
    def recyclebin_list_app(
        self, 
        payload: int | dict = 0, 
        /, 
        app: str = "android", 
        base_url: str | Callable[[], str] = "https://proapi.115.com", 
        *, 
        async_: Literal[False] = False, 
        **request_kwargs, 
    ) -> dict:
        ...
    @overload
    def recyclebin_list_app(
        self, 
        payload: int | dict = 0, 
        /, 
        app: str = "android", 
        base_url: str | Callable[[], str] = "https://proapi.115.com", 
        *, 
        async_: Literal[True], 
        **request_kwargs, 
    ) -> Coroutine[Any, Any, dict]:
        ...
    def recyclebin_list_app(
        self, 
        payload: int | dict = 0, 
        /, 
        app: str = "android", 
        base_url: str | Callable[[], str] = "https://proapi.115.com", 
        *, 
        async_: Literal[False, True] = False, 
        **request_kwargs, 
    ) -> dict | Coroutine[Any, Any, dict]:
        """回收站：列表

        GET https://proapi.115.com/android/rb

        :payload:
            - aid: int = 7 💡 area_id

                - 0: 会被视为 1
                - 1: 正常文件
                - 2: <unknown>
                - 3: <unknown>
                - 4: <unknown>
                - 5: <unknown>
                - 7: 回收站文件
                - 9: <unknown>
                - 12:瞬间文件
                - 15: <unknown>
                - 120: 彻底删除文件、简历附件
                - <其它>: 会被视为 0

            - cid: int | str = 0
            - limit: int = 32
            - offset: int = 0
            - source: str = <default>
        """ 
        api = complete_url("/rb", base_url=base_url, app=app)
        if isinstance(payload, int):
            payload = {"offset": payload}
        payload = {"aid": 7, "cid": 0, "limit": 32, "offset": 0, **payload}
        return self.request(url=api, params=payload, async_=async_, **request_kwargs)

    @overload
    def recyclebin_revert(
        self, 
        payload: int | str | Iterable[int | str] | dict, 
        /, 
        base_url: str | Callable[[], str] = "https://webapi.115.com", 
        *, 
        async_: Literal[False] = False, 
        **request_kwargs, 
    ) -> dict:
        ...
    @overload
    def recyclebin_revert(
        self, 
        payload: int | str | Iterable[int | str] | dict, 
        /, 
        base_url: str | Callable[[], str] = "https://webapi.115.com", 
        *, 
        async_: Literal[True], 
        **request_kwargs, 
    ) -> Coroutine[Any, Any, dict]:
        ...
    def recyclebin_revert(
        self, 
        payload: int | str | Iterable[int | str] | dict, 
        /, 
        base_url: str | Callable[[], str] = "https://webapi.115.com", 
        *, 
        async_: Literal[False, True] = False, 
        **request_kwargs, 
    ) -> dict | Coroutine[Any, Any, dict]:
        """回收站：还原

        POST https://webapi.115.com/rb/revert

        .. caution::
            ⚠️ 请不要并发执行，限制在 5 万个文件和目录以内

        :payload:
            - rid[0]: int | str
            - rid[1]: int | str
            - ...
        """
        api = complete_url("/rb/revert", base_url=base_url)
        if isinstance(payload, (int, str)):
            payload = {"rid[0]": payload}
        elif not isinstance(payload, dict):
            payload = {f"rid[{i}]": rid for i, rid in enumerate(payload)}
        return self.request(url=api, method="POST", data=payload, async_=async_, **request_kwargs)

    @overload
    def recyclebin_revert_app(
        self, 
        payload: int | str | Iterable[int | str] | dict, 
        /, 
        app: str = "android", 
        base_url: str | Callable[[], str] = "https://proapi.115.com", 
        *, 
        async_: Literal[False] = False, 
        **request_kwargs, 
    ) -> dict:
        ...
    @overload
    def recyclebin_revert_app(
        self, 
        payload: int | str | Iterable[int | str] | dict, 
        /, 
        app: str = "android", 
        base_url: str | Callable[[], str] = "https://proapi.115.com", 
        *, 
        async_: Literal[True], 
        **request_kwargs, 
    ) -> Coroutine[Any, Any, dict]:
        ...
    def recyclebin_revert_app(
        self, 
        payload: int | str | Iterable[int | str] | dict, 
        /, 
        app: str = "android", 
        base_url: str | Callable[[], str] = "https://proapi.115.com", 
        *, 
        async_: Literal[False, True] = False, 
        **request_kwargs, 
    ) -> dict | Coroutine[Any, Any, dict]:
        """回收站：还原

        POST https://proapi.115.com/android/rb/revert

        .. caution::
            ⚠️ 请不要并发执行，限制在 5 万个文件和目录以内

        :payload:
            - tid: int | str 💡 多个用逗号 "," 隔开
            - user_id: int | str = <default> 💡 用户 id
        """
        api = complete_url("/rb/revert", base_url=base_url, app=app)
        if isinstance(payload, (int, str)):
            payload = {"tid": payload}
        elif not isinstance(payload, dict):
            payload = {"tid": ",".join(map(str, payload))}
        payload.setdefault("user_id", self.user_id)
        return self.request(url=api, method="POST", data=payload, async_=async_, **request_kwargs)

    ########## Share API ##########

    @overload
    def share_access_user_list(
        self, 
        payload: str | dict, 
        /, 
        base_url: str | Callable[[], str] = "https://webapi.115.com", 
        *, 
        async_: Literal[False] = False, 
        **request_kwargs, 
    ) -> dict:
        ...
    @overload
    def share_access_user_list(
        self, 
        payload: str | dict, 
        /, 
        base_url: str | Callable[[], str] = "https://webapi.115.com", 
        *, 
        async_: Literal[True], 
        **request_kwargs, 
    ) -> Coroutine[Any, Any, dict]:
        ...
    def share_access_user_list(
        self, 
        payload: str | dict, 
        /, 
        base_url: str | Callable[[], str] = "https://webapi.115.com", 
        *, 
        async_: Literal[False, True] = False, 
        **request_kwargs, 
    ) -> dict | Coroutine[Any, Any, dict]:
        """访问账号列表

        GET https://webapi.115.com/share/access_user_list

        :payload:
            - share_code: str
        """
        api = complete_url("/share/access_user_list", base_url=base_url)
        if isinstance(payload, str):
            payload = {"share_code": payload}
        return self.request(url=api, params=payload, async_=async_, **request_kwargs)

    @overload
    def share_activate(
        self, 
        payload: str | dict, 
        /, 
        base_url: str | Callable[[], str] = "https://webapi.115.com", 
        *, 
        async_: Literal[False] = False, 
        **request_kwargs, 
    ) -> dict:
        ...
    @overload
    def share_activate(
        self, 
        payload: str | dict, 
        /, 
        base_url: str | Callable[[], str] = "https://webapi.115.com", 
        *, 
        async_: Literal[True], 
        **request_kwargs, 
    ) -> Coroutine[Any, Any, dict]:
        ...
    def share_activate(
        self, 
        payload: str | dict, 
        /, 
        base_url: str | Callable[[], str] = "https://webapi.115.com", 
        *, 
        async_: Literal[False, True] = False, 
        **request_kwargs, 
    ) -> dict | Coroutine[Any, Any, dict]:
        """激活分享

        POST https://webapi.115.com/share/activeshare

        :payload:
            - share_code: str
        """
        api = complete_url("/share/activeshare", base_url=base_url)
        if isinstance(payload, str):
            payload = {"share_code": payload}
        return self.request(url=api, method="POST", data=payload, async_=async_, **request_kwargs)

    @overload
    def share_batch_renewal_long_skip(
        self, 
        payload: str | dict, 
        /, 
        base_url: str | Callable[[], str] = "https://webapi.115.com", 
        *, 
        async_: Literal[False] = False, 
        **request_kwargs, 
    ) -> dict:
        ...
    @overload
    def share_batch_renewal_long_skip(
        self, 
        payload: str | dict, 
        /, 
        base_url: str | Callable[[], str] = "https://webapi.115.com", 
        *, 
        async_: Literal[True], 
        **request_kwargs, 
    ) -> Coroutine[Any, Any, dict]:
        ...
    def share_batch_renewal_long_skip(
        self, 
        payload: str | dict, 
        /, 
        base_url: str | Callable[[], str] = "https://webapi.115.com", 
        *, 
        async_: Literal[False, True] = False, 
        **request_kwargs, 
    ) -> dict | Coroutine[Any, Any, dict]:
        """将免登录下载链接设为长期

        POST https://webapi.115.com/share/batch_renewal_long_skip

        .. attention::
            链接必须开启免登录下载，并且需年费及以上 VIP 会员

        :payload:
            - share_code: str
        """
        api = complete_url("/share/batch_renewal_long_skip", base_url=base_url)
        if isinstance(payload, str):
            payload = {"share_code": payload}
        return self.request(url=api, method="POST", data=payload, async_=async_, **request_kwargs)

    @overload
    def share_downlist(
        self, 
        payload: dict, 
        /, 
        base_url: str | Callable[[], str] = "https://webapi.115.com", 
        *, 
        async_: Literal[False] = False, 
        **request_kwargs, 
    ) -> dict:
        ...
    @overload
    def share_downlist(
        self, 
        payload: dict, 
        /, 
        base_url: str | Callable[[], str] = "https://webapi.115.com", 
        *, 
        async_: Literal[True], 
        **request_kwargs, 
    ) -> Coroutine[Any, Any, dict]:
        ...
    def share_downlist(
        self, 
        payload: dict, 
        /, 
        base_url: str | Callable[[], str] = "https://webapi.115.com", 
        *, 
        async_: Literal[False, True] = False, 
        **request_kwargs, 
    ) -> dict | Coroutine[Any, Any, dict]:
        """获取分享链接的某个目录中可下载的文件的列表（只含文件，不含目录，任意深度，简略信息）

        GET https://webapi.115.com/share/downlist

        .. attention::
            cid 不能为 0

        :payload:
            - share_code: str
            - receive_code: str
            - cid: int | str
        """
        api = complete_url("/share/downlist", base_url=base_url)
        return self.request(url=api, params=payload, async_=async_, **request_kwargs)

    @overload
    def share_downlist_app(
        self, 
        payload: dict, 
        /, 
        app: str = "", 
        base_url: str | Callable[[], str] = "https://proapi.115.com", 
        *, 
        async_: Literal[False] = False, 
        **request_kwargs, 
    ) -> dict:
        ...
    @overload
    def share_downlist_app(
        self, 
        payload: dict, 
        /, 
        app: str = "", 
        base_url: str | Callable[[], str] = "https://proapi.115.com", 
        *, 
        async_: Literal[True], 
        **request_kwargs, 
    ) -> Coroutine[Any, Any, dict]:
        ...
    def share_downlist_app(
        self, 
        payload: dict, 
        /, 
        app: str = "", 
        base_url: str | Callable[[], str] = "https://proapi.115.com", 
        *, 
        async_: Literal[False, True] = False, 
        **request_kwargs, 
    ) -> dict | Coroutine[Any, Any, dict]:
        """获取分享链接的某个目录中可下载的文件的列表（只含文件，不含目录，任意深度，简略信息）

        GET https://proapi.115.com/app/share/downlist

        .. attention::
            cid 不能为 0

        :payload:
            - share_code: str
            - receive_code: str
            - cid: int | str
        """
        if app:
            api = complete_url("/2.0/share/downlist", base_url=base_url, app=app)
        else:
            api = complete_url("/app/share/downlist", base_url)
        return self.request(url=api, params=payload, async_=async_, **request_kwargs)

    @overload
    def share_download_url(
        self, 
        payload: int | str | dict, 
        /, 
        url: str = "", 
        strict: bool = True, 
        app: str = "", 
        *, 
        async_: Literal[False] = False, 
        **request_kwargs, 
    ) -> P115URL:
        ...
    @overload
    def share_download_url(
        self, 
        payload: int | str | dict, 
        /, 
        url: str = "", 
        strict: bool = True, 
        app: str = "", 
        *, 
        async_: Literal[True], 
        **request_kwargs, 
    ) -> Coroutine[Any, Any, P115URL]:
        ...
    def share_download_url(
        self, 
        payload: int | str | dict, 
        /, 
        url: str = "", 
        strict: bool = True, 
        app: str = "", 
        *, 
        async_: Literal[False, True] = False, 
        **request_kwargs, 
    ) -> P115URL | Coroutine[Any, Any, P115URL]:
        """获取分享链接中某个文件的下载链接

        :param payload: 请求参数，如果为 int 或 str，则视为 `file_id`

            - file_id: int | str 💡 文件 id
            - receive_code: str  💡 接收码（也就是密码）
            - share_code: str    💡 分享码

        :param url: 分享链接，如果提供的话，会被拆解并合并到 `payload` 中，优先级较高
        :param strict: 如果为 True，当目标是目录时，会抛出 IsADirectoryError 异常
        :param app: 使用此设备的接口
        :param async_: 是否异步
        :param request_kwargs: 其余请求参数

        :return: 下载链接
        """
        if isinstance(payload, (int, str)):
            payload = {"file_id": payload}
        else:
            payload = dict(payload)
        if url:
            share_payload = share_extract_payload(url)
            payload["share_code"] = share_payload["share_code"]
            payload["receive_code"] = share_payload["receive_code"] or ""
        def gen_step():
            if app in ("web", "desktop", "harmony"):
                resp = yield self.share_download_url_web(payload, async_=async_, **request_kwargs)
            else:
                resp = yield self.share_download_url_app(payload, app=app, async_=async_, **request_kwargs)
            check_response(resp)
            info = resp["data"]
            file_id = payload["file_id"]
            if not info:
                throw(
                    errno.ENOENT, 
                    f"no such id: {file_id!r}, with response {resp}", 
                )
            url = info["url"]
            if strict and not url:
                throw(
                    errno.EISDIR, 
                    f"{file_id} is a directory, with response {resp}", 
                )
            return P115URL(
                url["url"] if url else "", 
                id=int(info["fid"]), 
                name=info["fn"], 
                size=int(info["fs"]), 
                sha1=info.get("sha1", ""), 
                is_dir=not url, 
            )
        return run_gen_step(gen_step, async_)

    @overload
    def share_download_url_app(
        self, 
        payload: dict, 
        /, 
        app: str = "", 
        base_url: str | Callable[[], str] = "https://proapi.115.com", 
        *, 
        async_: Literal[False] = False, 
        **request_kwargs, 
    ) -> dict:
        ...
    @overload
    def share_download_url_app(
        self, 
        payload: dict, 
        /, 
        app: str = "", 
        base_url: str | Callable[[], str] = "https://proapi.115.com", 
        *, 
        async_: Literal[True], 
        **request_kwargs, 
    ) -> Coroutine[Any, Any, dict]:
        ...
    def share_download_url_app(
        self, 
        payload: dict, 
        /, 
        app: str = "", 
        base_url: str | Callable[[], str] = "https://proapi.115.com", 
        *, 
        async_: Literal[False, True] = False, 
        **request_kwargs, 
    ) -> dict | Coroutine[Any, Any, dict]:
        """获取分享链接中某个文件的下载链接

        POST https://proapi.115.com/app/share/downurl

        :payload:
            - file_id: int | str
            - receive_code: str
            - share_code: str
        """
        if app:
            api = complete_url("/2.0/share/downurl", base_url=base_url, app=app)
            return self.request(url=api, params=payload, async_=async_, **request_kwargs)
        else:
            api = complete_url("/app/share/downurl", base_url)
            def parse(resp, content: bytes, /) -> dict:
                resp = json_loads(content)
                if resp["state"]:
                    resp["data"] = json_loads(rsa_decrypt(resp["data"]))
                return resp
            request_kwargs.setdefault("parse", parse)
            payload = {"data": rsa_encrypt(dumps(payload)).decode()}
            return self.request(url=api, method="POST", data=payload, async_=async_, **request_kwargs)

    @overload
    def share_download_url_web(
        self, 
        payload: dict, 
        /, 
        base_url: str | Callable[[], str] = "https://webapi.115.com", 
        *, 
        async_: Literal[False] = False, 
        **request_kwargs, 
    ) -> dict:
        ...
    @overload
    def share_download_url_web(
        self, 
        payload: dict, 
        /, 
        base_url: str | Callable[[], str] = "https://webapi.115.com", 
        *, 
        async_: Literal[True], 
        **request_kwargs, 
    ) -> Coroutine[Any, Any, dict]:
        ...
    def share_download_url_web(
        self, 
        payload: dict, 
        /, 
        base_url: str | Callable[[], str] = "https://webapi.115.com", 
        *, 
        async_: Literal[False, True] = False, 
        **request_kwargs, 
    ) -> dict | Coroutine[Any, Any, dict]:
        """获取分享链接中某个文件的下载链接（网页版接口）

        GET https://webapi.115.com/share/downurl

        .. note::
            最大允许下载 200 MB 的文件

        :payload:
            - file_id: int | str
            - receive_code: str
            - share_code: str
        """
        api = complete_url("/share/downurl", base_url=base_url)
        return self.request(url=api, params=payload, async_=async_, **request_kwargs)

    @overload
    def share_info(
        self, 
        payload: str | dict, 
        /, 
        base_url: str | Callable[[], str] = "https://webapi.115.com", 
        *, 
        async_: Literal[False] = False, 
        **request_kwargs, 
    ) -> dict:
        ...
    @overload
    def share_info(
        self, 
        payload: str | dict, 
        /, 
        base_url: str | Callable[[], str] = "https://webapi.115.com", 
        *, 
        async_: Literal[True], 
        **request_kwargs, 
    ) -> Coroutine[Any, Any, dict]:
        ...
    def share_info(
        self, 
        payload: str | dict, 
        /, 
        base_url: str | Callable[[], str] = "https://webapi.115.com", 
        *, 
        async_: Literal[False, True] = False, 
        **request_kwargs, 
    ) -> dict | Coroutine[Any, Any, dict]:
        """获取（自己的）分享信息

        GET https://webapi.115.com/share/shareinfo

        :payload:
            - share_code: str
        """
        api = complete_url("/share/shareinfo", base_url=base_url)
        if isinstance(payload, str):
            payload = {"share_code": payload}
        return self.request(url=api, params=payload, async_=async_, **request_kwargs)

    @overload
    def share_info_app(
        self, 
        payload: str | dict, 
        /, 
        app: str = "android", 
        base_url: str | Callable[[], str] = "https://proapi.115.com", 
        *, 
        async_: Literal[False] = False, 
        **request_kwargs, 
    ) -> dict:
        ...
    @overload
    def share_info_app(
        self, 
        payload: str | dict, 
        /, 
        app: str = "android", 
        base_url: str | Callable[[], str] = "https://proapi.115.com", 
        *, 
        async_: Literal[True], 
        **request_kwargs, 
    ) -> Coroutine[Any, Any, dict]:
        ...
    def share_info_app(
        self, 
        payload: str | dict, 
        /, 
        app: str = "android", 
        base_url: str | Callable[[], str] = "https://proapi.115.com", 
        *, 
        async_: Literal[False, True] = False, 
        **request_kwargs, 
    ) -> dict | Coroutine[Any, Any, dict]:
        """获取（自己的）分享信息

        GET https://proapi.115.com/android/2.0/share/shareinfo

        :payload:
            - share_code: str
        """
        api = complete_url("/2.0/share/shareinfo", base_url=base_url, app=app)
        if isinstance(payload, str):
            payload = {"share_code": payload}
        return self.request(url=api, params=payload, async_=async_, **request_kwargs)

    @overload
    def share_list(
        self, 
        payload: int | dict = 0, 
        /, 
        base_url: str | Callable[[], str] = "https://webapi.115.com", 
        *, 
        async_: Literal[False] = False, 
        **request_kwargs, 
    ) -> dict:
        ...
    @overload
    def share_list(
        self, 
        payload: int | dict = 0, 
        /, 
        base_url: str | Callable[[], str] = "https://webapi.115.com", 
        *, 
        async_: Literal[True], 
        **request_kwargs, 
    ) -> Coroutine[Any, Any, dict]:
        ...
    def share_list(
        self, 
        payload: int | dict = 0, 
        /, 
        base_url: str | Callable[[], str] = "https://webapi.115.com", 
        *, 
        async_: Literal[False, True] = False, 
        **request_kwargs, 
    ) -> dict | Coroutine[Any, Any, dict]:
        """罗列（自己的）分享信息列表

        GET https://webapi.115.com/share/slist

        .. todo::
            暂时不清楚 order 有哪些取值

        :payload:
            - limit: int = 32
            - offset: int = 0
            - order: str = <default> 💡 排序依据，例如 "create_time"
            - asc: 0 | 1 = <default> 💡 是否升序排列
            - show_cancel_share: 0 | 1 = 0
        """
        api = complete_url("/share/slist", base_url=base_url)
        if isinstance(payload, int):
            payload = {"offset": payload}
        payload = {"limit": 32, "offset": 0, **payload}
        return self.request(url=api, params=payload, async_=async_, **request_kwargs)

    @overload
    def share_list_app(
        self, 
        payload: int | dict = 0, 
        /, 
        app: str = "android", 
        base_url: str | Callable[[], str] = "https://proapi.115.com", 
        *, 
        async_: Literal[False] = False, 
        **request_kwargs, 
    ) -> dict:
        ...
    @overload
    def share_list_app(
        self, 
        payload: int | dict = 0, 
        /, 
        app: str = "android", 
        base_url: str | Callable[[], str] = "https://proapi.115.com", 
        *, 
        async_: Literal[True], 
        **request_kwargs, 
    ) -> Coroutine[Any, Any, dict]:
        ...
    def share_list_app(
        self, 
        payload: int | dict = 0, 
        /, 
        app: str = "android", 
        base_url: str | Callable[[], str] = "https://proapi.115.com", 
        *, 
        async_: Literal[False, True] = False, 
        **request_kwargs, 
    ) -> dict | Coroutine[Any, Any, dict]:
        """罗列（自己的）分享信息列表

        GET https://proapi.115.com/android/2.0/share/slist

        :payload:
            - limit: int = 32
            - offset: int = 0
        """
        api = complete_url("/2.0/share/slist", base_url=base_url, app=app)
        if isinstance(payload, int):
            payload = {"offset": payload}
        payload = {"limit": 32, "offset": 0, **payload}
        return self.request(url=api, params=payload, async_=async_, **request_kwargs)

    @overload
    def share_notlogin_dl_quota(
        self, 
        /, 
        base_url: str | Callable[[], str] = "https://webapi.115.com", 
        *, 
        async_: Literal[False] = False, 
        **request_kwargs, 
    ) -> dict:
        ...
    @overload
    def share_notlogin_dl_quota(
        self, 
        /, 
        base_url: str | Callable[[], str] = "https://webapi.115.com", 
        *, 
        async_: Literal[True], 
        **request_kwargs, 
    ) -> Coroutine[Any, Any, dict]:
        ...
    def share_notlogin_dl_quota(
        self, 
        /, 
        base_url: str | Callable[[], str] = "https://webapi.115.com", 
        *, 
        async_: Literal[False, True] = False, 
        **request_kwargs, 
    ) -> dict | Coroutine[Any, Any, dict]:
        """免登录下载流量配额

        GET https://webapi.115.com/user/notlogin_dl_quota
        """
        api = complete_url("/user/notlogin_dl_quota", base_url=base_url)
        return self.request(url=api, async_=async_, **request_kwargs)

    @overload
    def share_notlogin_dl_quota_app(
        self, 
        /, 
        app: str = "android", 
        base_url: str | Callable[[], str] = "https://proapi.115.com", 
        *, 
        async_: Literal[False] = False, 
        **request_kwargs, 
    ) -> dict:
        ...
    @overload
    def share_notlogin_dl_quota_app(
        self, 
        /, 
        app: str = "android", 
        base_url: str | Callable[[], str] = "https://proapi.115.com", 
        *, 
        async_: Literal[True], 
        **request_kwargs, 
    ) -> Coroutine[Any, Any, dict]:
        ...
    def share_notlogin_dl_quota_app(
        self, 
        /, 
        app: str = "android", 
        base_url: str | Callable[[], str] = "https://proapi.115.com", 
        *, 
        async_: Literal[False, True] = False, 
        **request_kwargs, 
    ) -> dict | Coroutine[Any, Any, dict]:
        """免登录下载流量配额

        GET https://proapi.115.com/android/2.0/user/notlogin_dl_quota
        """
        api = complete_url("/2.0/user/notlogin_dl_quota", base_url=base_url, app=app)
        return self.request(url=api, async_=async_, **request_kwargs)

    @overload
    def share_receive(
        self, 
        payload: dict, 
        /, 
        base_url: str | Callable[[], str] = "https://webapi.115.com", 
        *, 
        async_: Literal[False] = False, 
        **request_kwargs, 
    ) -> dict:
        ...
    @overload
    def share_receive(
        self, 
        payload: dict, 
        /, 
        base_url: str | Callable[[], str] = "https://webapi.115.com", 
        *, 
        async_: Literal[True], 
        **request_kwargs, 
    ) -> Coroutine[Any, Any, dict]:
        ...
    def share_receive(
        self, 
        payload: dict, 
        /, 
        base_url: str | Callable[[], str] = "https://webapi.115.com", 
        *, 
        async_: Literal[False, True] = False, 
        **request_kwargs, 
    ) -> dict | Coroutine[Any, Any, dict]:
        """接收分享链接的某些文件或目录

        POST https://webapi.115.com/share/receive

        :payload:
            - share_code: str
            - receive_code: str
            - file_id: int | str         💡 有多个时，用逗号 "," 分隔
            - cid: int | str = <default> 💡 这是你网盘的目录 cid，如果不指定则用默认
            - is_check: 0 | 1 = <default>
        """
        api = complete_url("/share/receive", base_url=base_url)
        return self.request(url=api, method="POST", data=payload, async_=async_, **request_kwargs)

    @overload
    def share_receive_app(
        self, 
        payload: dict, 
        /, 
        app: str = "android", 
        base_url: str | Callable[[], str] = "https://proapi.115.com", 
        *, 
        async_: Literal[False] = False, 
        **request_kwargs, 
    ) -> dict:
        ...
    @overload
    def share_receive_app(
        self, 
        payload: dict, 
        /, 
        app: str = "android", 
        base_url: str | Callable[[], str] = "https://proapi.115.com", 
        *, 
        async_: Literal[True], 
        **request_kwargs, 
    ) -> Coroutine[Any, Any, dict]:
        ...
    def share_receive_app(
        self, 
        payload: dict, 
        /, 
        app: str = "android", 
        base_url: str | Callable[[], str] = "https://proapi.115.com", 
        *, 
        async_: Literal[False, True] = False, 
        **request_kwargs, 
    ) -> dict | Coroutine[Any, Any, dict]:
        """接收分享链接的某些文件或目录

        POST https://proapi.115.com/android/2.0/share/receive

        :payload:
            - share_code: str
            - receive_code: str
            - file_id: int | str         💡 有多个时，用逗号 "," 分隔
            - cid: int | str = <default> 💡 这是你网盘的目录 cid，如果不指定则用默认
            - is_check: 0 | 1 = <default>
        """
        api = complete_url("/2.0/share/receive", base_url=base_url, app=app)
        return self.request(url=api, method="POST", data=payload, async_=async_, **request_kwargs)

    @overload
    def share_recvcode(
        self, 
        payload: str | dict, 
        /, 
        base_url: str | Callable[[], str] = "https://webapi.115.com", 
        *, 
        async_: Literal[False] = False, 
        **request_kwargs, 
    ) -> dict:
        ...
    @overload
    def share_recvcode(
        self, 
        payload: str | dict, 
        /, 
        base_url: str | Callable[[], str] = "https://webapi.115.com", 
        *, 
        async_: Literal[True], 
        **request_kwargs, 
    ) -> Coroutine[Any, Any, dict]:
        ...
    def share_recvcode(
        self, 
        payload: str | dict, 
        /, 
        base_url: str | Callable[[], str] = "https://webapi.115.com", 
        *, 
        async_: Literal[False, True] = False, 
        **request_kwargs, 
    ) -> dict | Coroutine[Any, Any, dict]:
        """取消访问码

        GET https://webapi.115.com/share/recvcode

        :payload:
            - share_code: str
            - action: str = "cancel"
        """
        api = complete_url("/share/recvcode", base_url=base_url)
        if isinstance(payload, str):
            payload = {"share_code": payload}
        payload.setdefault("action", "cancel")
        return self.request(url=api, params=payload, async_=async_, **request_kwargs)

    @overload
    def share_recvcode_app(
        self, 
        payload: str | dict, 
        /, 
        app: str = "android", 
        base_url: str | Callable[[], str] = "https://proapi.115.com", 
        *, 
        async_: Literal[False] = False, 
        **request_kwargs, 
    ) -> dict:
        ...
    @overload
    def share_recvcode_app(
        self, 
        payload: str | dict, 
        /, 
        app: str = "android", 
        base_url: str | Callable[[], str] = "https://proapi.115.com", 
        *, 
        async_: Literal[True], 
        **request_kwargs, 
    ) -> Coroutine[Any, Any, dict]:
        ...
    def share_recvcode_app(
        self, 
        payload: str | dict, 
        /, 
        app: str = "android", 
        base_url: str | Callable[[], str] = "https://proapi.115.com", 
        *, 
        async_: Literal[False, True] = False, 
        **request_kwargs, 
    ) -> dict | Coroutine[Any, Any, dict]:
        """取消访问码

        GET https://proapi.115.com/android/2.0/share/recvcode

        :payload:
            - share_code: str
            - action: str = "cancel"
        """
        api = complete_url("/2.0/share/recvcode", base_url=base_url, app=app)
        if isinstance(payload, str):
            payload = {"share_code": payload}
        payload.setdefault("action", "cancel")
        return self.request(url=api, params=payload, async_=async_, **request_kwargs)

    @overload
    def share_send(
        self, 
        payload: int | str | dict, 
        /, 
        base_url: str | Callable[[], str] = "https://webapi.115.com", 
        *, 
        async_: Literal[False] = False, 
        **request_kwargs, 
    ) -> dict:
        ...
    @overload
    def share_send(
        self, 
        payload: int | str | dict, 
        /, 
        base_url: str | Callable[[], str] = "https://webapi.115.com", 
        *, 
        async_: Literal[True], 
        **request_kwargs, 
    ) -> Coroutine[Any, Any, dict]:
        ...
    def share_send(
        self, 
        payload: int | str | dict, 
        /, 
        base_url: str | Callable[[], str] = "https://webapi.115.com", 
        *, 
        async_: Literal[False, True] = False, 
        **request_kwargs, 
    ) -> dict | Coroutine[Any, Any, dict]:
        """创建（自己的）分享

        POST https://webapi.115.com/share/send

        :payload:
            - file_ids: int | str 💡 文件列表，有多个用逗号 "," 隔开
            - is_asc: 0 | 1 = 1 💡 是否升序排列
            - order: str = "file_name" 💡 用某字段排序

                - "file_name": 文件名
                - "file_size": 文件大小
                - "file_type": 文件种类
                - "user_utime": 修改时间
                - "user_ptime": 创建时间
                - "user_otime": 上一次打开时间

            - ignore_warn: 0 | 1 = 1 💡 忽略信息提示，传 1 就行了
        """
        api = complete_url("/share/send", base_url=base_url)
        if isinstance(payload, (int, str)):
            payload = {"file_ids": payload}
        payload = {"ignore_warn": 1, "is_asc": 1, "order": "file_name", **payload}
        return self.request(url=api, method="POST", data=payload, async_=async_, **request_kwargs)

    @overload
    def share_send_app(
        self, 
        payload: int | str | dict, 
        /, 
        app: str = "android", 
        base_url: str | Callable[[], str] = "https://proapi.115.com", 
        *, 
        async_: Literal[False] = False, 
        **request_kwargs, 
    ) -> dict:
        ...
    @overload
    def share_send_app(
        self, 
        payload: int | str | dict, 
        /, 
        app: str = "android", 
        base_url: str | Callable[[], str] = "https://proapi.115.com", 
        *, 
        async_: Literal[True], 
        **request_kwargs, 
    ) -> Coroutine[Any, Any, dict]:
        ...
    def share_send_app(
        self, 
        payload: int | str | dict, 
        /, 
        app: str = "android", 
        base_url: str | Callable[[], str] = "https://proapi.115.com", 
        *, 
        async_: Literal[False, True] = False, 
        **request_kwargs, 
    ) -> dict | Coroutine[Any, Any, dict]:
        """创建（自己的）分享

        POST https://proapi.115.com/android/2.0/share/send

        :payload:
            - file_ids: int | str 💡 文件列表，有多个用逗号 "," 隔开
            - is_asc: 0 | 1 = 1 💡 是否升序排列
            - order: str = "file_name" 💡 用某字段排序

                - "file_name": 文件名
                - "file_size": 文件大小
                - "file_type": 文件种类
                - "user_utime": 修改时间
                - "user_ptime": 创建时间
                - "user_otime": 上一次打开时间

            - ignore_warn: 0 | 1 = 1 💡 忽略信息提示，传 1 就行了
        """
        api = complete_url("/2.0/share/send", base_url=base_url, app=app)
        if isinstance(payload, (int, str)):
            payload = {"file_ids": payload}
        payload = {"ignore_warn": 1, "is_asc": 1, "order": "file_name", **payload}
        return self.request(url=api, method="POST", data=payload, async_=async_, **request_kwargs)

    @overload
    def share_search(
        self, 
        payload: dict, 
        /, 
        base_url: str | Callable[[], str] = "https://webapi.115.com", 
        *, 
        async_: Literal[False] = False, 
        **request_kwargs, 
    ) -> dict:
        ...
    @overload
    def share_search(
        self, 
        payload: dict, 
        /, 
        base_url: str | Callable[[], str] = "https://webapi.115.com", 
        *, 
        async_: Literal[True], 
        **request_kwargs, 
    ) -> Coroutine[Any, Any, dict]:
        ...
    def share_search(
        self, 
        payload: dict, 
        /, 
        base_url: str | Callable[[], str] = "https://webapi.115.com", 
        *, 
        async_: Literal[False, True] = False, 
        **request_kwargs, 
    ) -> dict | Coroutine[Any, Any, dict]:
        """从分享链接搜索文件或目录

        GET https://webapi.115.com/share/search

        .. attention::
            最多只能取回前 10,000 条数据，也就是 `limit + offset <= 10_000`，不过可以一次性取完

        :payload:
            - share_code: str    💡 分享码
            - receive_code: str  💡 接收码（即密码）
            - cid: int | str = 0 💡 目录 id，对应 parent_id
            - limit: int = 32    💡 一页大小，意思就是 page_size
            - offset: int = 0   💡 索引偏移，索引从 0 开始计算
            - search_value: str = "." 💡 搜索文本，仅支持搜索文件名
            - suffix: str = <default> 💡 文件后缀（扩展名），优先级高于 `type`
            - type: int = <default>   💡 文件类型

                - 0: 全部
                - 1: 文档
                - 2: 图片
                - 3: 音频
                - 4: 视频
                - 5: 压缩包
                - 6: 软件/应用
                - 7: 书籍
                - 99: 所有文件
        """
        api = complete_url("/share/search", base_url=base_url)
        payload = {"cid": 0, "limit": 32, "offset": 0, "search_value": ".", **payload}
        return self.request(url=api, params=payload, async_=async_, **request_kwargs)

    @overload
    def share_skip_login_check(
        self, 
        payload: dict, 
        /, 
        base_url: str | Callable[[], str] = "https://webapi.115.com", 
        *, 
        async_: Literal[False] = False, 
        **request_kwargs, 
    ) -> dict:
        ...
    @overload
    def share_skip_login_check(
        self, 
        payload: dict, 
        /, 
        base_url: str | Callable[[], str] = "https://webapi.115.com", 
        *, 
        async_: Literal[True], 
        **request_kwargs, 
    ) -> Coroutine[Any, Any, dict]:
        ...
    def share_skip_login_check(
        self, 
        payload: dict, 
        /, 
        base_url: str | Callable[[], str] = "https://webapi.115.com", 
        *, 
        async_: Literal[False, True] = False, 
        **request_kwargs, 
    ) -> dict | Coroutine[Any, Any, dict]:
        """检查是否可免登录下载

        POST https://webapi.115.com/share/is_skip_login

        :payload:
            - share_code: str        💡 分享码
            - receive_code: str      💡 接收码（访问密码）
            - file_id: int | str = 1 💡 文件 id（可以随便填一个非 0 的值）
        """
        api = complete_url("/share/is_skip_login", base_url=base_url)
        payload.setdefault("file_id", 1)
        return self.request(url=api, method="POST", data=payload, async_=async_, **request_kwargs)

    @overload
    def share_skip_login_down(
        self, 
        payload: str | dict, 
        /, 
        base_url: str | Callable[[], str] = "https://webapi.115.com", 
        *, 
        async_: Literal[False] = False, 
        **request_kwargs, 
    ) -> dict:
        ...
    @overload
    def share_skip_login_down(
        self, 
        payload: str | dict, 
        /, 
        base_url: str | Callable[[], str] = "https://webapi.115.com", 
        *, 
        async_: Literal[True], 
        **request_kwargs, 
    ) -> Coroutine[Any, Any, dict]:
        ...
    def share_skip_login_down(
        self, 
        payload: str | dict, 
        /, 
        base_url: str | Callable[[], str] = "https://webapi.115.com", 
        *, 
        async_: Literal[False, True] = False, 
        **request_kwargs, 
    ) -> dict | Coroutine[Any, Any, dict]:
        """开启或关闭免登录下载

        POST https://webapi.115.com/share/skip_login_down

        :payload:
            - share_code: str       💡 分享码
            - skip_login: 0 | 1 = 1 💡 是否开启
        """
        api = complete_url("/share/skip_login_down", base_url=base_url)
        if isinstance(payload, str):
            payload = {"share_code": payload}
        payload.setdefault("skip_login", 1)
        return self.request(url=api, method="POST", data=payload, async_=async_, **request_kwargs)

    @overload
    def share_skip_login_download_url(
        self: int | str | dict | ClientRequestMixin, 
        payload: None | int | str | dict = None, 
        /, 
        url: str = "", 
        strict: bool = True, 
        app: str = "", 
        *, 
        async_: Literal[False] = False, 
        **request_kwargs, 
    ) -> P115URL:
        ...
    @overload
    def share_skip_login_download_url(
        self: int | str | dict | ClientRequestMixin, 
        payload: None | int | str | dict = None, 
        /, 
        url: str = "", 
        strict: bool = True, 
        app: str = "", 
        *, 
        async_: Literal[True], 
        **request_kwargs, 
    ) -> Coroutine[Any, Any, P115URL]:
        ...
    def share_skip_login_download_url(
        self: int | str | dict | ClientRequestMixin, 
        payload: None | int | str | dict = None, 
        /, 
        url: str = "", 
        strict: bool = True, 
        app: str = "", 
        *, 
        async_: Literal[False, True] = False, 
        **request_kwargs, 
    ) -> P115URL | Coroutine[Any, Any, P115URL]:
        """获取分享链接中某个文件的下载链接

        .. note::
            可以作为 ``staticmethod`` 使用

        :param payload: 请求参数，如果为 int 或 str，则视为 `file_id`

            - file_id: int | str 💡 文件 id
            - receive_code: str  💡 接收码（访问密码）
            - share_code: str    💡 分享码

        :param url: 分享链接，如果提供的话，会被拆解并合并到 `payload` 中，优先级较高
        :param strict: 如果为 True，当目标是目录时，会抛出 IsADirectoryError 异常
        :param app: 使用此设备的接口
        :param async_: 是否异步
        :param request_kwargs: 其余请求参数

        :return: 下载链接
        """
        if not isinstance(self, ClientRequestMixin):
            payload = self
            self = {}
        else:
            assert payload is not None
        if not isinstance(payload, dict):
            payload = {"file_id": payload}
        if url:
            share_payload = share_extract_payload(url)
            payload["share_code"] = share_payload["share_code"]
            payload["receive_code"] = share_payload["receive_code"] or ""
        cls: type[P115Client] = __class__ # type: ignore
        def gen_step():
            if app in ("web", "desktop", "harmony"):
                resp = yield cls.share_skip_login_download_url_web(
                    self, payload, async_=async_, **request_kwargs)
            else:
                resp = yield cls.share_skip_login_download_url_app(
                    self, payload, app=app, async_=async_, **request_kwargs)
            check_response(resp)
            info = resp["data"]
            file_id = payload["file_id"]
            if not info:
                throw(
                    errno.ENOENT, 
                    f"no such id: {file_id!r}, with response {resp}", 
                )
            url = info["url"]
            if strict and not url:
                throw(
                    errno.EISDIR, 
                    f"{file_id} is a directory, with response {resp}", 
                )
            return P115URL(
                url["url"] if url else "", 
                id=int(info["fid"]), 
                name=info["fn"], 
                size=int(info["fs"]), 
                sha1=info.get("sha1", ""), 
                is_dir=not url, 
            )
        return run_gen_step(gen_step, async_)

    @overload
    def share_skip_login_download_url_app(
        self: dict | ClientRequestMixin, 
        payload: None | dict = None, 
        /, 
        app: str = "", 
        base_url: str | Callable[[], str] = "https://proapi.115.com", 
        *, 
        async_: Literal[False] = False, 
        **request_kwargs, 
    ) -> dict:
        ...
    @overload
    def share_skip_login_download_url_app(
        self: dict | ClientRequestMixin, 
        payload: None | dict = None, 
        /, 
        app: str = "", 
        base_url: str | Callable[[], str] = "https://proapi.115.com", 
        *, 
        async_: Literal[True], 
        **request_kwargs, 
    ) -> Coroutine[Any, Any, dict]:
        ...
    def share_skip_login_download_url_app(
        self: dict | ClientRequestMixin, 
        payload: None | dict = None, 
        /, 
        app: str = "", 
        base_url: str | Callable[[], str] = "https://proapi.115.com", 
        *, 
        async_: Literal[False, True] = False, 
        **request_kwargs, 
    ) -> dict | Coroutine[Any, Any, dict]:
        """获取免登录下载链接

        POST https://proapi.115.com/app/share/skip_login_downurl

        .. note::
            可以作为 ``staticmethod`` 使用

        :payload:
            - file_id: int | str
            - receive_code: str
            - share_code: str
        """
        if isinstance(self, dict):
            payload = self
        else:
            assert payload is not None
        if app:
            api = complete_url("/2.0/share/skip_login_downurl", base_url=base_url, app=app)
        else:
            api = complete_url("/app/share/skip_login_downurl", base_url)
            def parse(resp, content: bytes, /) -> dict:
                resp = json_loads(content)
                if resp["state"]:
                    resp["data"] = json_loads(rsa_decrypt(resp["data"]))
                return resp
            request_kwargs.setdefault("parse", parse)
            payload = {"data": rsa_encrypt(dumps(payload)).decode()}
        return get_request(async_, request_kwargs, self=self)(
            url=api, method="POST", data=payload, **request_kwargs)

    @overload
    def share_skip_login_download_url_web(
        self: dict | ClientRequestMixin, 
        payload: None | dict = None, 
        /, 
        base_url: str | Callable[[], str] = "https://webapi.115.com", 
        *, 
        async_: Literal[False] = False, 
        **request_kwargs, 
    ) -> dict:
        ...
    @overload
    def share_skip_login_download_url_web(
        self: dict | ClientRequestMixin, 
        payload: None | dict = None, 
        /, 
        base_url: str | Callable[[], str] = "https://webapi.115.com", 
        *, 
        async_: Literal[True], 
        **request_kwargs, 
    ) -> Coroutine[Any, Any, dict]:
        ...
    def share_skip_login_download_url_web(
        self: dict | ClientRequestMixin, 
        payload: None | dict = None, 
        /, 
        base_url: str | Callable[[], str] = "https://webapi.115.com", 
        *, 
        async_: Literal[False, True] = False, 
        **request_kwargs, 
    ) -> dict | Coroutine[Any, Any, dict]:
        """获取免登录下载链接

        POST https://webapi.115.com/share/skip_login_downurl

        .. note::
            可以作为 ``staticmethod`` 使用

        :payload:
            - share_code: str    💡 分享码
            - receive_code: str  💡 接收码（访问密码）
            - file_id: int | str 💡 文件 id
        """
        api = complete_url("/share/skip_login_downurl", base_url=base_url)
        if isinstance(self, dict):
            payload = self
        else:
            assert payload is not None
        return get_request(async_, request_kwargs, self=self)(
            url=api, method="POST", data=payload, **request_kwargs)

    @overload
    def share_skip_login_down_first(
        self, 
        payload: str | dict, 
        /, 
        base_url: str | Callable[[], str] = "https://webapi.115.com", 
        *, 
        async_: Literal[False] = False, 
        **request_kwargs, 
    ) -> dict:
        ...
    @overload
    def share_skip_login_down_first(
        self, 
        payload: str | dict, 
        /, 
        base_url: str | Callable[[], str] = "https://webapi.115.com", 
        *, 
        async_: Literal[True], 
        **request_kwargs, 
    ) -> Coroutine[Any, Any, dict]:
        ...
    def share_skip_login_down_first(
        self, 
        payload: str | dict, 
        /, 
        base_url: str | Callable[[], str] = "https://webapi.115.com", 
        *, 
        async_: Literal[False, True] = False, 
        **request_kwargs, 
    ) -> dict | Coroutine[Any, Any, dict]:
        """免登录下载信息

        GET https://webapi.115.com/share/skip_login_down_first

        :payload:
            - share_code: str 💡 分享码
        """
        api = complete_url("/share/skip_login_down_first", base_url=base_url)
        if isinstance(payload, str):
            payload = {"share_code": payload}
        return self.request(url=api, params=payload, async_=async_, **request_kwargs)

    @overload
    def share_skip_login_down_details(
        self, 
        payload: str | dict = "", 
        /, 
        base_url: str | Callable[[], str] = "https://webapi.115.com", 
        *, 
        async_: Literal[False] = False, 
        **request_kwargs, 
    ) -> dict:
        ...
    @overload
    def share_skip_login_down_details(
        self, 
        payload: str | dict = "", 
        /, 
        base_url: str | Callable[[], str] = "https://webapi.115.com", 
        *, 
        async_: Literal[True], 
        **request_kwargs, 
    ) -> Coroutine[Any, Any, dict]:
        ...
    def share_skip_login_down_details(
        self, 
        payload: str | dict = "", 
        /, 
        base_url: str | Callable[[], str] = "https://webapi.115.com", 
        *, 
        async_: Literal[False, True] = False, 
        **request_kwargs, 
    ) -> dict | Coroutine[Any, Any, dict]:
        """流量消耗明细

        GET https://webapi.115.com/share/skip_login_down_details

        :payload:
            - start_time: str = <default> 💡 开始时间，格式为 "YYYY-MM-DD hh:mm:ss"，默认为今天零点
            - end_time: str = <default>   💡 结束时间（含），默认为明天零点
            - share_code: str = ""        💡 分享码，如果为空则统计所有分享
            - offset: int = 0
            - limit: int = 32
        """
        api = complete_url("/share/skip_login_down_details", base_url=base_url)
        today = date.today()
        default_start_time = f"{today} 00:00:00"
        default_end_time = f"{today + timedelta(days=1)} 00:00:00"
        if isinstance(payload, str):
            payload = {"start_time": payload or default_start_time}
        payload = {"share_code": "", "limit": 32, "offset": 0, "start_time": default_start_time, "end_time": default_end_time, **payload}
        return self.request(url=api, params=payload, async_=async_, **request_kwargs)

    @overload
    def share_snap(
        self: dict | ClientRequestMixin, 
        payload: None | dict = None, 
        /, 
        base_url: str | Callable[[], str] = "https://webapi.115.com", 
        *, 
        async_: Literal[False] = False, 
        **request_kwargs, 
    ) -> dict:
        ...
    @overload
    def share_snap(
        self: dict | ClientRequestMixin, 
        payload: None | dict = None, 
        /, 
        base_url: str | Callable[[], str] = "https://webapi.115.com", 
        *, 
        async_: Literal[True], 
        **request_kwargs, 
    ) -> Coroutine[Any, Any, dict]:
        ...
    def share_snap(
        self: dict | ClientRequestMixin, 
        payload: None | dict = None, 
        /, 
        base_url: str | Callable[[], str] = "https://webapi.115.com", 
        *, 
        async_: Literal[False, True] = False, 
        **request_kwargs, 
    ) -> dict | Coroutine[Any, Any, dict]:
        """获取分享链接的某个目录中的文件和子目录的列表（包含详细信息）

        GET https://webapi.115.com/share/snap

        .. note::
            可以作为 ``staticmethod`` 使用

            如果是登录状态，且查看自己的分享时，则可以不提供 receive_code，而且即使还在审核中，也能获取文件列表

        .. caution::
            虽然可以不登录即可获取数据，但是一旦过于频繁，会封禁 IP 一段时间

        :payload:
            - share_code: str
            - receive_code: str
            - cid: int | str = 0
            - limit: int = 32
            - offset: int = 0
            - asc: 0 | 1 = <default> 💡 是否升序排列
            - o: str = <default> 💡 用某字段排序

                - "file_name": 文件名
                - "file_size": 文件大小
                - "user_ptime": 创建时间/修改时间
        """
        api = complete_url("/share/snap", base_url=base_url)
        if isinstance(self, dict):
            payload = self
        else:
            assert payload is not None
        payload = {"cid": 0, "limit": 32, "offset": 0, **payload}
        return get_request(async_, request_kwargs, self=self)(
            url=api, params=payload, **request_kwargs)

    @overload
    def share_snap_app(
        self, 
        payload: dict, 
        /, 
        app: str = "android", 
        base_url: str | Callable[[], str] = "https://proapi.115.com", 
        *, 
        async_: Literal[False] = False, 
        **request_kwargs, 
    ) -> dict:
        ...
    @overload
    def share_snap_app(
        self, 
        payload: dict, 
        /, 
        app: str = "android", 
        base_url: str | Callable[[], str] = "https://proapi.115.com", 
        *, 
        async_: Literal[True], 
        **request_kwargs, 
    ) -> Coroutine[Any, Any, dict]:
        ...
    def share_snap_app(
        self, 
        payload: dict, 
        /, 
        app: str = "android", 
        base_url: str | Callable[[], str] = "https://proapi.115.com", 
        *, 
        async_: Literal[False, True] = False, 
        **request_kwargs, 
    ) -> dict | Coroutine[Any, Any, dict]:
        """获取分享链接的某个目录中的文件和子目录的列表（包含详细信息）

        GET https://proapi.115.com/android/2.0/share/snap

        .. caution::
            这个接口必须登录使用，并且对于其它人的网盘文件，每个目录中最多获取前 1000 条（但获取自己的资源正常）

        :payload:
            - share_code: str
            - receive_code: str
            - cid: int | str = 0
            - limit: int = 32
            - offset: int = 0
            - asc: 0 | 1 = <default> 💡 是否升序排列
            - o: str = <default> 💡 用某字段排序

                - "file_name": 文件名
                - "file_size": 文件大小
                - "user_ptime": 创建时间/修改时间
        """
        api = complete_url("/2.0/share/snap", base_url=base_url, app=app)
        payload = {"cid": 0, "limit": 32, "offset": 0, **payload}
        return self.request(url=api, params=payload, async_=async_, **request_kwargs)

    @overload
    def share_update(
        self, 
        payload: dict, 
        /, 
        base_url: str | Callable[[], str] = "https://webapi.115.com", 
        *, 
        async_: Literal[False] = False, 
        **request_kwargs, 
    ) -> dict:
        ...
    @overload
    def share_update(
        self, 
        payload: dict, 
        /, 
        base_url: str | Callable[[], str] = "https://webapi.115.com", 
        *, 
        async_: Literal[True], 
        **request_kwargs, 
    ) -> Coroutine[Any, Any, dict]:
        ...
    def share_update(
        self, 
        payload: dict, 
        /, 
        base_url: str | Callable[[], str] = "https://webapi.115.com", 
        *, 
        async_: Literal[False, True] = False, 
        **request_kwargs, 
    ) -> dict | Coroutine[Any, Any, dict]:
        """变更（自己的）分享的配置（例如改访问密码，取消分享）

        POST https://webapi.115.com/share/updateshare

        :payload:
            - share_code: str
            - receive_code: str = <default>         💡 接收码（访问密码）
            - share_duration: int = <default>       💡 分享天数: n（填入指定天数），-1(长期)
            - is_custom_code: 0 | 1 = <default>     💡 用户自定义口令（不用管）
            - auto_fill_recvcode: 0 | 1 = <default> 💡 分享链接自动填充口令（不用管）
            - auto_renewal: 0 | 1 = <default>       💡 是否自动续期
            - share_channel: int = <default>        💡 分享渠道代码（不用管）
            - action: str = <default>               💡 操作: "cancel":取消分享 "delete":删除分享
            - skip_login_down_flow_limit: "" | int  = <default> 💡 设置免登录下载限制流量，如果为 "" 则不限，单位: 字节
            - access_user_ids = int | str = <default> 💡 设置访问账号，多个用逗号 "," 隔开
            - receive_user_limit: int = <default> 💡 接收次数
            - reset_receive_user: 0 | 1 = <default> 💡 重置接收次数
        """
        api = complete_url("/share/updateshare", base_url=base_url)
        return self.request(url=api, method="POST", data=payload, async_=async_, **request_kwargs)

    @overload
    def share_update_app(
        self, 
        payload: dict, 
        /, 
        app: str = "android", 
        base_url: str | Callable[[], str] = "https://proapi.115.com", 
        *, 
        async_: Literal[False] = False, 
        **request_kwargs, 
    ) -> dict:
        ...
    @overload
    def share_update_app(
        self, 
        payload: dict, 
        /, 
        app: str = "android", 
        base_url: str | Callable[[], str] = "https://proapi.115.com", 
        *, 
        async_: Literal[True], 
        **request_kwargs, 
    ) -> Coroutine[Any, Any, dict]:
        ...
    def share_update_app(
        self, 
        payload: dict, 
        /, 
        app: str = "android", 
        base_url: str | Callable[[], str] = "https://proapi.115.com", 
        *, 
        async_: Literal[False, True] = False, 
        **request_kwargs, 
    ) -> dict | Coroutine[Any, Any, dict]:
        """变更（自己的）分享的配置（例如改访问密码，取消分享）

        POST https://proapi.115.com/android/2.0/share/updateshare

        :payload:
            - share_code: str
            - receive_code: str = <default>         💡 接收码（访问密码）
            - share_duration: int = <default>       💡 分享天数: n（填入指定天数），-1(长期)
            - is_custom_code: 0 | 1 = <default>     💡 用户自定义口令（不用管）
            - auto_fill_recvcode: 0 | 1 = <default> 💡 分享链接自动填充口令（不用管）
            - share_channel: int = <default>        💡 分享渠道代码（不用管）
            - action: str = <default>               💡 操作: "cancel":取消分享 "delete":删除分享
            - skip_login_down_flow_limit: "" | int  = <default> 💡 设置免登录下载限制流量，如果为 "" 则不限，单位: 字节
            - access_user_ids = int | str = <default> 💡 设置访问账号，多个用逗号 "," 隔开
            - receive_user_limit: int = <default> 💡 接收次数
            - reset_receive_user: 0 | 1 = <default> 💡 重置接收次数
        """
        api = complete_url("/2.0/share/updateshare", base_url=base_url, app=app)
        return self.request(url=api, method="POST", data=payload, async_=async_, **request_kwargs)

    ########## Tool API ##########

    @overload
    def tool_clear_empty_folder(
        self, 
        /, 
        base_url: str | Callable[[], str] = "https://115.com", 
        *, 
        async_: Literal[False] = False, 
        **request_kwargs, 
    ) -> dict:
        ...
    @overload
    def tool_clear_empty_folder(
        self, 
        /, 
        base_url: str | Callable[[], str] = "https://115.com", 
        *, 
        async_: Literal[True], 
        **request_kwargs, 
    ) -> Coroutine[Any, Any, dict]:
        ...
    def tool_clear_empty_folder(
        self, 
        /, 
        base_url: str | Callable[[], str] = "https://115.com", 
        *, 
        async_: Literal[False, True] = False, 
        **request_kwargs, 
    ) -> dict | Coroutine[Any, Any, dict]:
        """删除空目录

        GET https://115.com/?ct=tool&ac=clear_empty_folder
        """
        api = complete_url(base_url=base_url, query={"ct": "tool", "ac": "clear_empty_folder"})
        return self.request(url=api, async_=async_, **request_kwargs)

    @overload
    def tool_repeat(
        self, 
        payload: int | str | dict, 
        /, 
        base_url: str | Callable[[], str] = "https://aps.115.com", 
        *, 
        async_: Literal[False] = False, 
        **request_kwargs, 
    ) -> dict:
        ...
    @overload
    def tool_repeat(
        self, 
        payload: int | str | dict, 
        /, 
        base_url: str | Callable[[], str] = "https://aps.115.com", 
        *, 
        async_: Literal[True], 
        **request_kwargs, 
    ) -> Coroutine[Any, Any, dict]:
        ...
    def tool_repeat(
        self, 
        payload: int | str | dict, 
        /, 
        base_url: str | Callable[[], str] = "https://aps.115.com", 
        *, 
        async_: Literal[False, True] = False, 
        **request_kwargs, 
    ) -> dict | Coroutine[Any, Any, dict]:
        """开始一键排重任务

        POST https://aps.115.com/repeat/repeat.php

        :payload:
            - folder_id: int | str 💡 目录 id，对应 parent_id
        """
        api = complete_url("/repeat/repeat.php", base_url=base_url)
        if isinstance(payload, (int, str)):
            payload = {"folder_id": payload}
        return self.request(url=api, method="POST", data=payload, async_=async_, **request_kwargs)

    @overload
    def tool_repeat_delete(
        self, 
        payload: dict, 
        /, 
        base_url: str | Callable[[], str] = "https://aps.115.com", 
        *, 
        async_: Literal[False] = False, 
        **request_kwargs, 
    ) -> dict:
        ...
    @overload
    def tool_repeat_delete(
        self, 
        payload: dict, 
        /, 
        base_url: str | Callable[[], str] = "https://aps.115.com", 
        *, 
        async_: Literal[True], 
        **request_kwargs, 
    ) -> Coroutine[Any, Any, dict]:
        ...
    def tool_repeat_delete(
        self, 
        payload: dict, 
        /, 
        base_url: str | Callable[[], str] = "https://aps.115.com", 
        *, 
        async_: Literal[False, True] = False, 
        **request_kwargs, 
    ) -> dict | Coroutine[Any, Any, dict]:
        """删除重复文件

        POST https://aps.115.com/repeat/repeat_delete.php

        :payload:
            - filter_field: "parents" | "file_name" | "" | "" = <default> 💡 保留条件（1. 用于批量删除）

                - "file_name": 文件名（按长度）
                - "parents": 所在目录路径（按长度）
                - "user_utime": 操作时间
                - "user_ptime": 创建时间

            - filter_order: "asc" | "desc" = <default> 💡 排序（2. 用于批量删除）

                - "asc": 升序，从小到大，取最小
                - "desc": 降序，从大到小，取最大

            - batch: 0 | 1 = <default> 💡 是否批量操作（3. 用于批量删除）
            - sha1s[{sha1}]: int | str = <default> 💡 文件 id，多个用逗号 "," 隔开（1. 用于手动指定删除对象）
        """
        api = complete_url("/repeat/repeat_delete.php", base_url=base_url)
        return self.request(url=api, method="POST", data=payload, async_=async_, **request_kwargs)

    @overload
    def tool_repeat_delete_status(
        self, 
        /, 
        base_url: str | Callable[[], str] = "https://aps.115.com", 
        *, 
        async_: Literal[False] = False, 
        **request_kwargs, 
    ) -> dict:
        ...
    @overload
    def tool_repeat_delete_status(
        self, 
        /, 
        base_url: str | Callable[[], str] = "https://aps.115.com", 
        *, 
        async_: Literal[True], 
        **request_kwargs, 
    ) -> Coroutine[Any, Any, dict]:
        ...
    def tool_repeat_delete_status(
        self, 
        /, 
        base_url: str | Callable[[], str] = "https://aps.115.com", 
        *, 
        async_: Literal[False, True] = False, 
        **request_kwargs, 
    ) -> dict | Coroutine[Any, Any, dict]:
        """删除重复文件进度和统计信息（status 为 False 表示进行中，为 True 表示完成）

        GET https://aps.115.com/repeat/delete_status.php
        """
        api = complete_url("/repeat/delete_status.php", base_url=base_url)
        return self.request(url=api, async_=async_, **request_kwargs)

    @overload
    def tool_repeat_list(
        self, 
        payload: int | dict = 0, 
        /, 
        base_url: str | Callable[[], str] = "https://aps.115.com", 
        *, 
        async_: Literal[False] = False, 
        **request_kwargs, 
    ) -> dict:
        ...
    @overload
    def tool_repeat_list(
        self, 
        payload: int | dict = 0, 
        /, 
        base_url: str | Callable[[], str] = "https://aps.115.com", 
        *, 
        async_: Literal[True], 
        **request_kwargs, 
    ) -> Coroutine[Any, Any, dict]:
        ...
    def tool_repeat_list(
        self, 
        payload: int | dict = 0, 
        /, 
        base_url: str | Callable[[], str] = "https://aps.115.com", 
        *, 
        async_: Literal[False, True] = False, 
        **request_kwargs, 
    ) -> dict | Coroutine[Any, Any, dict]:
        """获取重复文件列表

        GET https://aps.115.com/repeat/repeat_list.php

        :payload:
            - s: int = 0 💡 offset，从 0 开始
            - l: int = 100 💡 limit
        """
        api = complete_url("/repeat/repeat_list.php", base_url=base_url)
        if isinstance(payload, int):
            payload = {"l": 100, "s": payload}
        else:
            payload = {"s": 0, "l": 100, **payload}
        return self.request(url=api, params=payload, async_=async_, **request_kwargs)

    @overload
    def tool_repeat_status(
        self, 
        /, 
        base_url: str | Callable[[], str] = "https://aps.115.com", 
        *, 
        async_: Literal[False] = False, 
        **request_kwargs, 
    ) -> dict:
        ...
    @overload
    def tool_repeat_status(
        self, 
        /, 
        base_url: str | Callable[[], str] = "https://aps.115.com", 
        *, 
        async_: Literal[True], 
        **request_kwargs, 
    ) -> Coroutine[Any, Any, dict]:
        ...
    def tool_repeat_status(
        self, 
        /, 
        base_url: str | Callable[[], str] = "https://aps.115.com", 
        *, 
        async_: Literal[False, True] = False, 
        **request_kwargs, 
    ) -> dict | Coroutine[Any, Any, dict]:
        """查询一键排重任务进度和统计信息（status 为 False 表示进行中，为 True 表示完成）

        GET https://aps.115.com/repeat/repeat_status.php
        """
        api = complete_url("/repeat/repeat_status.php", base_url=base_url)
        return self.request(url=api, async_=async_, **request_kwargs)

    @overload
    def tool_space(
        self, 
        /, 
        base_url: str | Callable[[], str] = "https://115.com", 
        *, 
        async_: Literal[False] = False, 
        **request_kwargs, 
    ) -> dict:
        ...
    @overload
    def tool_space(
        self, 
        /, 
        base_url: str | Callable[[], str] = "https://115.com", 
        *, 
        async_: Literal[True], 
        **request_kwargs, 
    ) -> Coroutine[Any, Any, dict]:
        ...
    def tool_space(
        self, 
        /, 
        base_url: str | Callable[[], str] = "https://115.com", 
        *, 
        async_: Literal[False, True] = False, 
        **request_kwargs, 
    ) -> dict | Coroutine[Any, Any, dict]:
        """检验空间

        GET https://115.com/?ct=tool&ac=space

        .. hint::
            1. 校验空间需全局进行扫描，请谨慎操作;
            2. 扫描出无父目录的文件将统一放入到"/修复文件"的目录中;
            3. "/修复文件"的目录若超过存放文件数量限制，将创建多个目录存放，避免无法操作。
            4. 此接口一天只能使用一次
        """
        api = complete_url(base_url=base_url, query={"ct": "tool", "ac": "space"})
        return self.request(url=api, async_=async_, **request_kwargs)

    ########## Upload API ##########

    @overload
    def upload_info(
        self, 
        /, 
        base_url: str | Callable[[], str] = "https://proapi.115.com", 
        *, 
        async_: Literal[False] = False, 
        **request_kwargs, 
    ) -> dict:
        ...
    @overload
    def upload_info(
        self, 
        /, 
        base_url: str | Callable[[], str] = "https://proapi.115.com", 
        *, 
        async_: Literal[True], 
        **request_kwargs, 
    ) -> Coroutine[Any, Any, dict]:
        ...
    def upload_info(
        self, 
        /, 
        base_url: str | Callable[[], str] = "https://proapi.115.com", 
        *, 
        async_: Literal[False, True] = False, 
        **request_kwargs, 
    ) -> dict | Coroutine[Any, Any, dict]:
        """获取和上传有关的信息，其中 "user_id" 和 "userkey" 是至关重要的

        GET https://proapi.115.com/app/uploadinfo
        """
        api = complete_url("/app/uploadinfo", base_url)
        return self.request(url=api, async_=async_, **request_kwargs)

    @overload
    def upload_init(
        self, 
        payload: dict, 
        /, 
        base_url: str | Callable[[], str] = "https://uplb.115.com", 
        *, 
        async_: Literal[False] = False, 
        **request_kwargs, 
    ) -> dict:
        ...
    @overload
    def upload_init(
        self, 
        payload: dict, 
        /, 
        base_url: str | Callable[[], str] = "https://uplb.115.com", 
        *, 
        async_: Literal[True], 
        **request_kwargs, 
    ) -> Coroutine[Any, Any, dict]:
        ...
    def upload_init(
        self, 
        payload: dict, 
        /, 
        base_url: str | Callable[[], str] = "https://uplb.115.com", 
        *, 
        async_: Literal[False, True] = False, 
        **request_kwargs, 
    ) -> dict | Coroutine[Any, Any, dict]:
        """初始化上传任务，可能秒传

        POST https://uplb.115.com/4.0/initupload.php

        .. caution::
            这个接口，偶尔会返回 HTTP 401 错误，你只需要再次重试即可

        :payload:
            - fileid: str           💡 文件的 sha1
            - filename: str         💡 文件名
            - filesize: int         💡 文件大小
            - target: str = "U_1_0" 💡 保存目标，格式为 f"U_{aid}_{pid}"
            - sign_key: str = ""    💡 2 次验证的 key
            - sign_val: str = ""    💡 2 次验证的值
            - topupload: int | str = "true" 💡 上传调度文件类型调度标记
            - userid: int | str = <default> 💡 用户 id
            - userkey: str = <default> 💡 用户的 key
        """
        api = complete_url("/4.0/initupload.php", base_url=base_url)
        payload = {
            "appid": 0, 
            "target": "U_1_0", 
            "sign_key": "", 
            "sign_val": "", 
            "topupload": "true", 
            **payload, 
            "appversion": "99.99.99.99", 
        }
        if "userid" not in payload:
            payload["userid"] = self.user_id
        if "userkey" not in payload:
            payload["userkey"] = self.user_key
        request_kwargs["headers"] = dict_update(
            dict(request_kwargs.get("headers") or ()), 
            {
                "content-type": "application/x-www-form-urlencoded", 
                "user-agent": "Mozilla/5.0 115disk/99.99.99.99 115Browser/99.99.99.99 115wangpan_android/99.99.99.99", 
            }, 
        )
        request_kwargs.update(make_upload_payload(payload))
        def parse_upload_init_response(_, content: bytes, /) -> dict:
            data = ecdh_aes_decrypt(content, decompress=True)
            return json_loads(data)
        request_kwargs.setdefault("parse", parse_upload_init_response)
        return self.request(url=api, method="POST", async_=async_, **request_kwargs)

    @overload
    def upload_key(
        self, 
        /, 
        app: str = "android", 
        base_url: str | Callable[[], str] = "https://proapi.115.com", 
        *, 
        async_: Literal[False] = False, 
        **request_kwargs, 
    ) -> dict:
        ...
    @overload
    def upload_key(
        self, 
        /, 
        app: str = "android", 
        base_url: str | Callable[[], str] = "https://proapi.115.com", 
        *, 
        async_: Literal[True], 
        **request_kwargs, 
    ) -> Coroutine[Any, Any, dict]:
        ...
    def upload_key(
        self, 
        /, 
        app: str = "android", 
        base_url: str | Callable[[], str] = "https://proapi.115.com", 
        *, 
        async_: Literal[False, True] = False, 
        **request_kwargs, 
    ) -> dict | Coroutine[Any, Any, dict]:
        """获取 user_key

        GET https://proapi.115.com/android/2.0/user/upload_key
        """
        api = complete_url("/2.0/user/upload_key", base_url=base_url, app=app)
        def gen_step():
            resp = yield self.request(url=api, async_=async_, **request_kwargs)
            if resp["state"]:
                self.user_key = resp["data"]["userkey"]
            return resp
        return run_gen_step(gen_step, async_)

    @overload
    def upload_resume(
        self, 
        payload: dict | str, 
        /, 
        base_url: str | Callable[[], str] = "https://uplb.115.com", 
        *, 
        async_: Literal[False] = False, 
        **request_kwargs, 
    ) -> dict:
        ...
    @overload
    def upload_resume(
        self, 
        payload: dict | str, 
        /, 
        base_url: str | Callable[[], str] = "https://uplb.115.com", 
        *, 
        async_: Literal[True], 
        **request_kwargs, 
    ) -> Coroutine[Any, Any, dict]:
        ...
    def upload_resume(
        self, 
        payload: dict | str, 
        /, 
        base_url: str | Callable[[], str] = "https://uplb.115.com", 
        *, 
        async_: Literal[False, True] = False, 
        **request_kwargs, 
    ) -> dict | Coroutine[Any, Any, dict]:
        """获取恢复断点续传所需信息

        POST https://uplb.115.com/3.0/resumeupload.php

        :payload:
            - fileid: str   💡 文件的 sha1 值
            - filesize: int 💡 文件大小，单位是字节
            - target: str   💡 上传目标，默认为 "U_1_0"，格式为 f"U_{aid}_{pid}"
            - pickcode: str 💡 提取码
            - userid: int = <default> 💡 用户 id
        """
        api = complete_url("/3.0/resumeupload.php", base_url=base_url)
        if isinstance(payload, str):
            payload = {"pickcode": payload}
        else:
            payload = dict(payload)
        payload.setdefault("fileid", "0" * 40)
        payload.setdefault("filesize", 1)
        payload.setdefault("target", "U_1_0")
        if "userid" not in payload:
            payload["userid"] = self.user_id
        return self.request(url=api, method="POST", data=payload, async_=async_, **request_kwargs)

    @overload
    def upload_avatar(
        self, 
        /, 
        file: ( Buffer | str | PathLike | URL | SupportsGeturl | 
                SupportsRead | Iterable[Buffer] ), 
        app: str = "web", 
        base_url: str | Callable[[], str] = "https://ictxl.115.com", 
        *, 
        async_: Literal[False] = False, 
        **request_kwargs, 
    ) -> dict:
        ...
    @overload
    def upload_avatar(
        self, 
        /, 
        file: ( Buffer | str | PathLike | URL | SupportsGeturl | 
                SupportsRead | Iterable[Buffer] | AsyncIterable[Buffer] ), 
        app: str = "web", 
        base_url: str | Callable[[], str] = "https://ictxl.115.com", 
        *, 
        async_: Literal[True], 
        **request_kwargs, 
    ) -> Coroutine[Any, Any, dict]:
        ...
    def upload_avatar(
        self, 
        /, 
        file: ( Buffer | str | PathLike | URL | SupportsGeturl | 
                SupportsRead | Iterable[Buffer] | AsyncIterable[Buffer] ), 
        app: str = "web", 
        base_url: str | Callable[[], str] = "https://ictxl.115.com", 
        *, 
        async_: Literal[False, True] = False, 
        **request_kwargs, 
    ) -> dict | Coroutine[Any, Any, dict]:
        """上传一张图片，可用于作为头像（图片时效性很短，请尽快使用）

        POST https://ictxl.115.com/app/1.1/web/1.2/upload/set_avatar

        .. attention::
            此接口采用 multi-part 上传，其实是可以一次传多个文件的，但我做的封装只允许传一张图片。

            一次接口调用的上传流量，算上分片分隔符，大概是不能超过 32 MB，需要进一步测验。

        :param file: 待上传的文件
        :param app: 使用此设备的接口
        :param base_url: 接口的基地址
        :param async_: 是否异步
        :param request_kwargs: 其余请求参数

        :return: 接口响应
        """
        api = complete_url(f"/app/1.1/{app}/1.2/upload/set_avatar", base_url=base_url)
        if isinstance(file, str):
            file = open(file, "rb")
        return self.request(url=api, method="POST", files={"file": ("a.jpg", file)}, async_=async_, **request_kwargs)

    @overload
    def upload_image(
        self, 
        /, 
        file: ( Buffer | str | PathLike | URL | SupportsGeturl | 
                SupportsRead | Iterable[Buffer] ), 
        app: str = "web", 
        base_url: str | Callable[[], str] = "https://credentials.115.com", 
        *, 
        async_: Literal[False] = False, 
        **request_kwargs, 
    ) -> dict:
        ...
    @overload
    def upload_image(
        self, 
        /, 
        file: ( Buffer | str | PathLike | URL | SupportsGeturl | 
                SupportsRead | Iterable[Buffer] | AsyncIterable[Buffer] ), 
        app: str = "web", 
        base_url: str | Callable[[], str] = "https://credentials.115.com", 
        *, 
        async_: Literal[True], 
        **request_kwargs, 
    ) -> Coroutine[Any, Any, dict]:
        ...
    def upload_image(
        self, 
        /, 
        file: ( Buffer | str | PathLike | URL | SupportsGeturl | 
                SupportsRead | Iterable[Buffer] | AsyncIterable[Buffer] ), 
        app: str = "web", 
        base_url: str | Callable[[], str] = "https://credentials.115.com", 
        *, 
        async_: Literal[False, True] = False, 
        **request_kwargs, 
    ) -> dict | Coroutine[Any, Any, dict]:
        """上传一张图片，可用于作为证件照

        POST https://credentials.115.com/api/1.0/web/1.0/credentials/upload_images

        .. attention::
            此接口采用 multi-part 上传，其实是可以一次传多个文件的，但我做的封装只允许传一张图片，最大允许传 10 MB

        :param file: 待上传的文件
        :param app: 使用此设备的接口
        :param base_url: 接口的基地址
        :param async_: 是否异步
        :param request_kwargs: 其余请求参数

        :return: 接口响应
        """
        api = complete_url(f"/api/1.0/{app}/1.0/credentials/upload_images", base_url=base_url)
        if isinstance(file, str):
            file = open(file, "rb")
        return self.request(url=api, method="POST", files={"image": ("a.jpg", file)}, async_=async_, **request_kwargs)

    @overload
    def upload_image_init(
        self, 
        payload: str | dict, 
        /, 
        base_url: str | Callable[[], str] = "https://uplb.115.com", 
        *, 
        async_: Literal[False] = False, 
        **request_kwargs, 
    ) -> dict:
        ...
    @overload
    def upload_image_init(
        self, 
        payload: str | dict, 
        /, 
        base_url: str | Callable[[], str] = "https://uplb.115.com", 
        *, 
        async_: Literal[True], 
        **request_kwargs, 
    ) -> Coroutine[Any, Any, dict]:
        ...
    def upload_image_init(
        self, 
        payload: str | dict, 
        /, 
        base_url: str | Callable[[], str] = "https://uplb.115.com", 
        *, 
        async_: Literal[False, True] = False, 
        **request_kwargs, 
    ) -> dict | Coroutine[Any, Any, dict]:
        """网页端的上传图片接口的初始化

        POST https://uplb.115.com/3.0/imginitupload.php

        .. caution::
            此接口不支持秒传，最大支持上传 50 MB 的文件，上传成功后不占用空间

        .. caution::
            通过扩展名来识别，仅支持以下格式图片(jpg,jpeg,png,gif,svg,webp,heic,bmp,dng)

        .. note::
            `target` 随便设置，例如 "U_4_-1"、"U_5_-2"

        :payload:
            - filename: str = <default> 💡 文件名，默认为一个新的 uuid4 对象的字符串表示
            - target: str = "U_4_-1" 💡 上传目标，格式为 f"U_{aid}_{pid}"
            - filesize: int | str = <default> 💡 图片大小
            - height: int = <default> 💡 图片高度
            - width: int = <default>  💡 图片宽度
        """
        api = complete_url("/3.0/imginitupload.php", base_url=base_url)
        if isinstance(payload, str):
            payload = {"filename": payload}
        elif "filename" not in payload:
            payload["filename"] = str(uuid4()) + ".jpg"
        payload.setdefault("target", "U_4_-1")
        return self.request(url=api, method="POST", data=payload, async_=async_, **request_kwargs)

    @overload
    def upload_sample_init(
        self, 
        payload: str | dict, 
        /, 
        base_url: str | Callable[[], str] = "https://uplb.115.com", 
        *, 
        async_: Literal[False] = False, 
        **request_kwargs, 
    ) -> dict:
        ...
    @overload
    def upload_sample_init(
        self, 
        payload: str | dict, 
        /, 
        base_url: str | Callable[[], str] = "https://uplb.115.com", 
        *, 
        async_: Literal[True], 
        **request_kwargs, 
    ) -> Coroutine[Any, Any, dict]:
        ...
    def upload_sample_init(
        self, 
        payload: str | dict, 
        /, 
        base_url: str | Callable[[], str] = "https://uplb.115.com", 
        *, 
        async_: Literal[False, True] = False, 
        **request_kwargs, 
    ) -> dict | Coroutine[Any, Any, dict]:
        """网页端的上传接口的初始化

        POST https://uplb.115.com/3.0/sampleinitupload.php

        .. caution::
            此接口不支持秒传

        :payload:
            - filename: str = <default> 💡 文件名，默认为一个新的 uuid4 对象的字符串表示
            - target: str = "U_1_0" 💡 上传目标，格式为 f"U_{aid}_{pid}"
            - path: str = <default> 💡 保存目录，是在 `target` 对应目录下的相对路径，默认为 `target` 所对应目录本身
            - filesize: int | str = <default> 💡 文件大小
        """
        api = complete_url("/3.0/sampleinitupload.php", base_url=base_url)
        if isinstance(payload, str):
            payload = {"filename": payload}
        elif "filename" not in payload:
            payload["filename"] = str(uuid4())
        payload.setdefault("target", "U_1_0")
        return self.request(url=api, method="POST", data=payload, async_=async_, **request_kwargs)

    @overload
    def upload_file_image_init(
        self, 
        /, 
        filename: str = "", 
        pid: int | str = "U_4_-1", 
        base_url: str | Callable[[], str] = "https://uplb.115.com", 
        *, 
        async_: Literal[False] = False, 
        **request_kwargs, 
    ) -> dict:
        ...
    @overload
    def upload_file_image_init(
        self, 
        /, 
        filename: str = "", 
        pid: int | str = "U_4_-1", 
        base_url: str | Callable[[], str] = "https://uplb.115.com", 
        *, 
        async_: Literal[True], 
        **request_kwargs, 
    ) -> Coroutine[Any, Any, dict]:
        ...
    def upload_file_image_init(
        self, 
        /, 
        filename: str = "", 
        pid: int | str = "U_4_-1", 
        base_url: str | Callable[[], str] = "https://uplb.115.com", 
        *, 
        async_: Literal[False, True] = False, 
        **request_kwargs, 
    ) -> dict | Coroutine[Any, Any, dict]:
        """网页端的上传图片接口的初始化，不会秒传，此接口是对 `upload_image_init` 的封装

        .. caution::
            通过扩展名来识别，仅支持以下格式图片(jpg,jpeg,png,gif,svg,webp,heic,bmp,dng)

        :param filename: 文件名，默认为一个新的 uuid4 对象的字符串表示
        :param pid: 上传文件到此目录的 id 或 pickcode，或者指定的 target（格式为 f"U_{aid}_{pid}"）
        :param base_url: 接口的基地址
        :param async_: 是否异步
        :param request_kwargs: 其它请求参数
        """
        if isinstance(pid, str) and pid.startswith("U_"):
            target = pid
        else:
            target = f"U_1_{pid}"
        payload = {"filename": filename or str(uuid4())+".jpg", "target": target}
        return self.upload_image_init(payload, async_=async_, base_url=base_url, **request_kwargs)

    @overload
    def upload_file_sample_init(
        self, 
        /, 
        filename: str = "", 
        dirname: str = "", 
        pid: int | str = 0, 
        base_url: str | Callable[[], str] = "https://uplb.115.com", 
        *, 
        async_: Literal[False] = False, 
        **request_kwargs, 
    ) -> dict:
        ...
    @overload
    def upload_file_sample_init(
        self, 
        /, 
        filename: str = "", 
        dirname: str = "", 
        pid: int | str = 0, 
        base_url: str | Callable[[], str] = "https://uplb.115.com", 
        *, 
        async_: Literal[True], 
        **request_kwargs, 
    ) -> Coroutine[Any, Any, dict]:
        ...
    def upload_file_sample_init(
        self, 
        /, 
        filename: str = "", 
        dirname: str = "", 
        pid: int | str = 0, 
        base_url: str | Callable[[], str] = "https://uplb.115.com", 
        *, 
        async_: Literal[False, True] = False, 
        **request_kwargs, 
    ) -> dict | Coroutine[Any, Any, dict]:
        """网页端的上传接口的初始化，不会秒传，此接口是对 `upload_sample_init` 的封装

        :param filename: 文件名，默认为一个新的 uuid4 对象的字符串表示
        :param dirname: 保存目录，是在 `pid` 对应目录下的相对路径，默认为 `pid` 所对应目录本身
        :param pid: 上传文件到此目录的 id 或 pickcode，或者指定的 target（格式为 f"U_{aid}_{pid}"）
        :param base_url: 接口的基地址
        :param async_: 是否异步
        :param request_kwargs: 其它请求参数
        """
        if isinstance(pid, str) and pid.startswith("U_"):
            target = pid
        else:
            target = f"U_1_{pid}"
        payload = {"filename": filename or str(uuid4()), "path": dirname, "target": target}
        return self.upload_sample_init(payload, async_=async_, base_url=base_url, **request_kwargs)

    @overload # type: ignore
    def upload_gettoken(
        self: None | ClientRequestMixin = None, 
        /, 
        base_url: str | Callable[[], str] = "https://uplb.115.com", 
        *, 
        async_: Literal[False] = False, 
        **request_kwargs, 
    ) -> dict:
        ...
    @overload
    def upload_gettoken(
        self: None | ClientRequestMixin = None, 
        /, 
        base_url: str | Callable[[], str] = "https://uplb.115.com", 
        *, 
        async_: Literal[True], 
        **request_kwargs, 
    ) -> Coroutine[Any, Any, dict]:
        ...
    def upload_gettoken(
        self: None | ClientRequestMixin = None, 
        /, 
        base_url: str | Callable[[], str] = "https://uplb.115.com", 
        *, 
        async_: Literal[False, True] = False, 
        **request_kwargs, 
    ) -> dict | Coroutine[Any, Any, dict]:
        """获取阿里云 OSS 的 token（上传凭证）

        GET https://uplb.115.com/3.0/gettoken.php

        .. note::
            可以作为 ``staticmethod`` 使用
        """
        api = complete_url("/3.0/gettoken.php", base_url=base_url)
        return get_request(async_, request_kwargs, self=self)(url=api, **request_kwargs)

    @overload
    def upload_url(
        self: None | ClientRequestMixin = None, 
        /, 
        base_url: str | Callable[[], str] = "https://uplb.115.com", 
        *, 
        async_: Literal[False] = False, 
        **request_kwargs, 
    ) -> dict:
        ...
    @overload
    def upload_url(
        self: None | ClientRequestMixin = None, 
        /, 
        base_url: str | Callable[[], str] = "https://uplb.115.com", 
        *, 
        async_: Literal[True], 
        **request_kwargs, 
    ) -> Coroutine[Any, Any, dict]:
        ...
    def upload_url(
        self: None | ClientRequestMixin = None, 
        /, 
        base_url: str | Callable[[], str] = "https://uplb.115.com", 
        *, 
        async_: Literal[False, True] = False, 
        **request_kwargs, 
    ) -> dict | Coroutine[Any, Any, dict]:
        """获取用于上传的一些 http 接口，此接口具有一定幂等性，请求一次，然后把响应记下来即可

        GET https://uplb.115.com/3.0/getuploadinfo.php

        .. note::
            可以作为 ``staticmethod`` 使用

        :response:
            - endpoint: 此接口用于上传文件到阿里云 OSS 
            - gettokenurl: 上传前需要用此接口获取 token
        """
        api = complete_url("/3.0/getuploadinfo.php", base_url=base_url)
        return get_request(async_, request_kwargs, self=self)(url=api, **request_kwargs)

    # NOTE: 下列是关于上传功能的封装方法

    @overload
    def upload_file_init(
        self, 
        /, 
        filename: str, 
        filesize: int, 
        filesha1: str, 
        read_range_bytes_or_hash: None | Callable[[str], str | Buffer] = None, 
        pid: int | str = 0, 
        *, 
        async_: Literal[False] = False, 
        **request_kwargs, 
    ) -> dict:
        ...
    @overload
    def upload_file_init(
        self, 
        /, 
        filename: str, 
        filesize: int, 
        filesha1: str, 
        read_range_bytes_or_hash: None | Callable[[str], str | Buffer] = None, 
        pid: int | str = 0, 
        *, 
        async_: Literal[True], 
        **request_kwargs, 
    ) -> Coroutine[Any, Any, dict]:
        ...
    def upload_file_init(
        self, 
        /, 
        filename: str, 
        filesize: int, 
        filesha1: str, 
        read_range_bytes_or_hash: None | Callable[[str], str | Buffer] = None, 
        pid: int | str = 0, 
        *, 
        async_: Literal[False, True] = False, 
        **request_kwargs, 
    ) -> dict | Coroutine[Any, Any, dict]:
        """初始化上传，可能秒传，此接口是对 `upload_init` 的封装

        .. note::
            - 文件大小 和 sha1 是必需的，只有 sha1 是没用的。
            - 如果文件大于等于 1 MB (1048576 B)，就需要 2 次检验一个范围哈希，就必须提供 `read_range_bytes_or_hash`

        :param filename: 文件名
        :param filesize: 文件大小
        :param filesha1: 文件的 sha1
        :param read_range_bytes_or_hash: 调用以获取 2 次验证的数据或计算 sha1，接受一个数据范围，格式符合:
            `HTTP Range Requests <https://developer.mozilla.org/en-US/docs/Web/HTTP/Range_requests>`_，
            返回值如果是 str，则视为计算好的 sha1，如果为 Buffer，则视为数据（之后会被计算 sha1）
        :param pid: 上传文件到此目录的 id，或者指定的 target（格式为 f"U_{aid}_{pid}"，但这里的 `aid` 无论如何取值，都视为 1）
        :param async_: 是否异步
        :param request_kwargs: 其余请求参数

        :return: 接口响应
        """
        def gen_step():
            if isinstance(pid, str) and pid.startswith("U_"):
                target = pid
            else:
                target = f"U_1_{pid}"
            payload = {
                "filename": filename, 
                "fileid": filesha1.upper(), 
                "filesize": filesize, 
                "target": target, 
            }
            resp = yield self.upload_init(
                payload, 
                async_=async_, 
                **request_kwargs, 
            )
            status = resp["status"]
            if status == 7:
                if read_range_bytes_or_hash is None:
                    raise ValueError("filesize >= 1 MB, thus need pass the `read_range_bytes_or_hash` argument")
                payload["sign_key"] = resp["sign_key"]
                sign_check: str = resp["sign_check"]
                content: str | Buffer
                if async_:
                    content = yield ensure_async(read_range_bytes_or_hash)(sign_check)
                else:
                    content = read_range_bytes_or_hash(sign_check)
                if isinstance(content, str):
                    payload["sign_val"] = content.upper()
                else:
                    payload["sign_val"] = sha1(content).hexdigest().upper()
                resp = yield self.upload_init(
                    payload, 
                    async_=async_, # type: ignore
                    **request_kwargs, 
                )
                status = resp["status"]
            resp["reuse"] = status == 2
            resp["state"] = status in (1, 2)
            return resp
        return run_gen_step(gen_step, async_)

    @overload
    def upload_file_image(
        self, 
        /, 
        file: ( Buffer | str | PathLike | URL | SupportsGeturl | 
                SupportsRead | Iterable[Buffer] ), 
        pid: int | str = "U_4_-1", 
        filename: str = "", 
        *, 
        async_: Literal[False] = False, 
        **request_kwargs, 
    ) -> dict:
        ...
    @overload
    def upload_file_image(
        self, 
        /, 
        file: ( Buffer | str | PathLike | URL | SupportsGeturl | 
                SupportsRead | Iterable[Buffer] | AsyncIterable[Buffer] ), 
        pid: int | str = "U_4_-1", 
        filename: str = "", 
        *, 
        async_: Literal[True], 
        **request_kwargs, 
    ) -> Coroutine[Any, Any, dict]:
        ...
    def upload_file_image(
        self, 
        /, 
        file: ( Buffer | str | PathLike | URL | SupportsGeturl | 
                SupportsRead | Iterable[Buffer] | AsyncIterable[Buffer] ), 
        pid: int | str = "U_4_-1", 
        filename: str = "", 
        *, 
        async_: Literal[False, True] = False, 
        **request_kwargs, 
    ) -> dict | Coroutine[Any, Any, dict]:
        """网页端的上传图片接口

        .. caution::
            不支持秒传，但也不必传文件大小和 sha1，最大支持上传 50 MB 的文件

        :param file: 待上传的文件
        :param pid: 上传文件到此目录的 id 或 pickcode，或者指定的 target（格式为 f"U_{aid}_{pid}"）
        :param filename: 文件名，如果为空，则会自动确定
        :param async_: 是否异步
        :param request_kwargs: 其余请求参数

        :return: 接口响应
        """
        if isinstance(pid, str) and not pid.startswith("U_"):
            pid = self.to_id(pid)
        def gen_step():
            nonlocal file, filename
            if not isinstance(file, (Buffer, SupportsRead)):
                path = file
                is_url: None | bool = None
                if isinstance(path, str):
                    is_url = path.startswith(("http://", "https://"))
                elif isinstance(path, (URL, SupportsGeturl)):
                    is_url = True
                    if isinstance(path, URL):
                        path = str(path)
                    else:
                        path = path.geturl()
                elif isinstance(path, PathLike):
                    is_url = False
                    path = fsdecode(path)
                if is_url is not None:
                    path = cast(str, path)
                    if is_url:
                        if async_:
                            from httpfile import AsyncHTTPFileReader
                            async def process():
                                return await AsyncHTTPFileReader.new(
                                    cast(str, path), 
                                    headers={"user-agent": "", "accept-encoding": "identity"}, 
                                )
                            file = yield process()
                        else:
                            from httpfile import HTTPFileReader
                            file = HTTPFileReader(
                                path, headers={"user-agent": "", "accept-encoding": "identity"})
                        file = cast(HTTPFileReader, file)
                        if not filename:
                            filename = file.name
                    else:
                        file = open(path, "rb")
                    if not filename:
                        if is_url:
                            from posixpath import basename
                            from urllib.parse import unquote
                            filename = basename(unquote(urlsplit(path).path))
                        else:
                            from os.path import basename
                            filename = basename(path)
                elif isinstance(file, SupportsRead):
                    if not filename:
                        from os.path import basename
                        filename = getattr(file, "name", "")
                        filename = basename(filename)
            resp = yield self.upload_file_image_init(
                filename, 
                pid=pid, 
                async_=async_, 
                **request_kwargs, 
            )
            def parse(_, content: bytes):
                data = json_loads(content)
                data["oss_info"] = resp
                return data
            request_kwargs.setdefault("parse", parse)
            return self.request(
                url=resp["host"], 
                method="POST", 
                data={
                    "name": filename, 
                    "key": resp["object"], 
                    "policy": resp["policy"], 
                    "OSSAccessKeyId": resp["accessid"], 
                    "success_action_status": "200", 
                    "callback": resp["callback"], 
                    "signature": resp["signature"], 
                }, 
                files={"file": file}, 
                async_=async_, 
                **request_kwargs, 
            )
        return run_gen_step(gen_step, async_)

    @overload
    def upload_file_sample(
        self, 
        /, 
        file: ( Buffer | str | PathLike | URL | SupportsGeturl | 
                SupportsRead | Iterable[Buffer] ), 
        pid: int | str = 0, 
        filename: str = "", 
        dirname: str = "", 
        *, 
        async_: Literal[False] = False, 
        **request_kwargs, 
    ) -> dict:
        ...
    @overload
    def upload_file_sample(
        self, 
        /, 
        file: ( Buffer | str | PathLike | URL | SupportsGeturl | 
                SupportsRead | Iterable[Buffer] | AsyncIterable[Buffer] ), 
        pid: int | str = 0, 
        filename: str = "", 
        dirname: str = "", 
        *, 
        async_: Literal[True], 
        **request_kwargs, 
    ) -> Coroutine[Any, Any, dict]:
        ...
    def upload_file_sample(
        self, 
        /, 
        file: ( Buffer | str | PathLike | URL | SupportsGeturl | 
                SupportsRead | Iterable[Buffer] | AsyncIterable[Buffer] ), 
        pid: int | str = 0, 
        filename: str = "", 
        dirname: str = "", 
        *, 
        async_: Literal[False, True] = False, 
        **request_kwargs, 
    ) -> dict | Coroutine[Any, Any, dict]:
        """网页端的上传接口

        .. caution::
            不支持秒传，但也不必传文件大小和 sha1

        .. note::
            只要上传后的 `aid` 或 `area_id` 不为 1，则不占用空间，这是 `upload_file` 所不能的（因为即使指定了 "U_{aid}_{pid}"，也会忽略其中的 `aid`，强行视为 1）

        .. note::
            通过 ``pid``，支持随意指定上传目标。特别是当格式为 f"U_{aid}_{pid}"，允许其中的 ``aid != 1`` 和 ``pid < 0``（可能有特殊指代）。
            这里有一些特殊的位置：

            - ``U_0_{n}``: 等同于 ``pid="U_1_0"``，无论 ``n`` 是什么值
            - ``U_1_-11``: 上传附件到根目录下的 "记录文件"
            - ``U_3_-6``: 上传附件到根目录下的 "消息文件"
            - ``U_3_-15``: 上传封面到临时目录，等同于 ``pid="U_15_0"``
            - ``U_3_-24``: 上传文件到根目录下的 "手机备份"
            - ``U_3_{n}``: ``n`` 可取 -1,-2,-3,-4,-5,-8,-9,-10,-12,-13，等同于 ``pid="U_120_0"``
            - ``U_{a}_{n}``: ``n`` 可取 0 或所有 ``aid=1`` 的文件或目录的 id，则上传目标为 ``aid=a, cid=n``

        .. caution::
            如果最终的 ``aid`` 为 1 或 15，则剩余网盘空间会减掉上传文件的大小。
            尽量不要使 ``aid=15``，因为这会导致白白占掉空间，不能删除，也不能正常下载。

        :param file: 待上传的文件
        :param pid: 上传文件到此目录的 id 或 pickcode，或者指定的 target（格式为 f"U_{aid}_{pid}"）
        :param filename: 文件名，如果为空，则会自动确定
        :param dirname: 保存目录，是在 `pid` 对应目录下的相对路径，默认为 `pid` 所对应目录本身
        :param async_: 是否异步
        :param request_kwargs: 其余请求参数

        :return: 接口响应
        """
        if isinstance(pid, str) and not pid.startswith("U_"):
            pid = self.to_id(pid)
        def gen_step():
            nonlocal file, filename
            if not isinstance(file, (Buffer, SupportsRead)):
                path = file
                is_url: None | bool = None
                if isinstance(path, str):
                    is_url = path.startswith(("http://", "https://"))
                elif isinstance(path, (URL, SupportsGeturl)):
                    is_url = True
                    if isinstance(path, URL):
                        path = str(path)
                    else:
                        path = path.geturl()
                elif isinstance(path, PathLike):
                    is_url = False
                    path = fsdecode(path)
                if is_url is not None:
                    path = cast(str, path)
                    if is_url:
                        if async_:
                            from httpfile import AsyncHTTPFileReader
                            async def process():
                                return await AsyncHTTPFileReader.new(
                                    cast(str, path), 
                                    headers={"user-agent": "", "accept-encoding": "identity"}, 
                                )
                            file = yield process()
                        else:
                            from httpfile import HTTPFileReader
                            file = HTTPFileReader(
                                path, headers={"user-agent": "", "accept-encoding": "identity"})
                        file = cast(HTTPFileReader, file)
                        if not filename:
                            filename = file.name
                    else:
                        file = open(path, "rb")
                    if not filename:
                        if is_url:
                            from posixpath import basename
                            from urllib.parse import unquote
                            filename = basename(unquote(urlsplit(path).path))
                        else:
                            from os.path import basename
                            filename = basename(path)
                elif isinstance(file, SupportsRead):
                    if not filename:
                        from os.path import basename
                        filename = getattr(file, "name", "")
                        filename = basename(filename)
            resp = yield self.upload_file_sample_init(
                filename, 
                dirname=dirname, 
                pid=pid, 
                async_=async_, 
                **request_kwargs, 
            )
            def parse(_, content: bytes):
                data = json_loads(content)
                data["oss_info"] = resp
                return data
            request_kwargs.setdefault("parse", parse)
            return self.request(
                url=resp["host"], 
                method="POST", 
                data={
                    "name": filename, 
                    "key": resp["object"], 
                    "policy": resp["policy"], 
                    "OSSAccessKeyId": resp["accessid"], 
                    "success_action_status": "200", 
                    "callback": resp["callback"], 
                    "signature": resp["signature"], 
                }, 
                files={"file": file}, 
                async_=async_, 
                **request_kwargs, 
            )
        return run_gen_step(gen_step, async_)

    @overload
    def upload_file(
        self, 
        /, 
        file: Buffer | str | PathLike | URL | SupportsGeturl | SupportsRead, 
        pid: int | str = 0, 
        filename: str = "", 
        filesha1: str = "", 
        filesize: int = -1, 
        partsize: int = 0, 
        callback: None | dict = None, 
        upload_id: str = "", 
        endpoint: str = "http://oss-cn-shenzhen.aliyuncs.com", 
        *, 
        async_: Literal[False] = False, 
        **request_kwargs, 
    ) -> dict:
        ...
    @overload
    def upload_file(
        self, 
        /, 
        file: Buffer | str | PathLike | URL | SupportsGeturl | SupportsRead, 
        pid: int | str = 0, 
        filename: str = "", 
        filesha1: str = "", 
        filesize: int = -1, 
        partsize: int = 0, 
        callback: None | dict = None, 
        upload_id: str = "", 
        endpoint: str = "http://oss-cn-shenzhen.aliyuncs.com", 
        *, 
        async_: Literal[True], 
        **request_kwargs, 
    ) -> Coroutine[Any, Any, dict]:
        ...
    def upload_file(
        self, 
        /, 
        file: Buffer | str | PathLike | URL | SupportsGeturl | SupportsRead, 
        pid: int | str = 0, 
        filename: str = "", 
        filesha1: str = "", 
        filesize: int = -1, 
        partsize: int = 0, 
        callback: None | dict = None, 
        upload_id: str = "", 
        endpoint: str = "http://oss-cn-shenzhen.aliyuncs.com", 
        *, 
        async_: Literal[False, True] = False, 
        **request_kwargs, 
    ) -> dict | Coroutine[Any, Any, dict]:
        """上传文件

        .. note::
            如果提供了 ``callback``，则强制为分块上传。
            此时，最好提供一下 ``upload_id``，否则就是从头开始。
            此时可以省略 ``pid``、``filename``、``filesha1``、``filesize``、``user_id``、``user_key``、``partsize``

        .. caution::
            ``partsize > 0`` 时，不要把 ``partsize`` 设置得太小，起码得 10 MB (10485760) 以上

        .. note::
            这个文件无论把文件传到哪，都会占用空间。这里有一些特殊的位置：

            - ``U_3_-8``: 此时 ``aid=120``，会平白占用空间，根本不能回收，所以要慎用
            - ``U_3_-9``: 此时 ``aid=12``，可以通过 ``fs_delete_app`` 删除上传后的文件 id 来释放空间

        :param file: 待上传的文件
        :param pid: 上传文件到此目录的 id 或 pickcode，或者指定的 target（格式为 f"U_{aid}_{pid}"，但这里的 `aid` 无论如何取值，都视为 1）
        :param filename: 文件名，如果为空，则会自动确定
        :param filesha1: 文件的 sha1，如果为空，则会自动确定
        :param filesize: 文件大小，如果为 -1，则会自动确定
        :param partsize: 分块上传的分块大小。如果为 0，则不做分块上传；如果 < 0，则会自动确定
        :param callback: 回调数据
        :param upload_id: 上传任务 id
        :param endpoint: 上传目的网址
        :param async_: 是否异步
        :param request_kwargs: 其余请求参数

        :return: 接口响应
        """
        if isinstance(pid, str) and not pid.startswith("U_"):
            pid = self.to_id(pid)
        return upload(
            file=file, 
            pid=pid, 
            filename=filename, 
            filesha1=filesha1, 
            filesize=filesize, 
            user_id=self.user_id, 
            user_key=self.user_key, 
            partsize=partsize, 
            callback=callback, 
            upload_id=upload_id, 
            endpoint=endpoint, 
            async_=async_, 
            **request_kwargs, 
        )

    ########## User API ##########

    @overload
    def user_base_info(
        self, 
        /, 
        app: str = "web", 
        base_url: str | Callable[[], str] = "https://qrcodeapi.115.com", 
        *, 
        async_: Literal[False] = False, 
        **request_kwargs, 
    ) -> dict:
        ...
    @overload
    def user_base_info(
        self, 
        /, 
        app: str = "web", 
        base_url: str | Callable[[], str] = "https://qrcodeapi.115.com", 
        *, 
        async_: Literal[True], 
        **request_kwargs, 
    ) -> Coroutine[Any, Any, dict]:
        ...
    def user_base_info(
        self, 
        /, 
        app: str = "web", 
        base_url: str | Callable[[], str] = "https://qrcodeapi.115.com", 
        *, 
        async_: Literal[False, True] = False, 
        **request_kwargs, 
    ) -> dict | Coroutine[Any, Any, dict]:
        """获取用户的基本信息

        GET https://qrcodeapi.115.com/app/1.0/web/1.0/user/base_info
        """
        api = complete_url(f"/app/1.0/{app}/1.0/user/base_info", base_url=base_url)
        return self.request(url=api, async_=async_, **request_kwargs)

    @overload
    def user_card(
        self, 
        /, 
        app: str = "android", 
        base_url: str | Callable[[], str] = "https://proapi.115.com", 
        *, 
        async_: Literal[False] = False, 
        **request_kwargs, 
    ) -> dict:
        ...
    @overload
    def user_card(
        self, 
        /, 
        app: str = "android", 
        base_url: str | Callable[[], str] = "https://proapi.115.com", 
        *, 
        async_: Literal[True], 
        **request_kwargs, 
    ) -> Coroutine[Any, Any, dict]:
        ...
    def user_card(
        self, 
        /, 
        app: str = "android", 
        base_url: str | Callable[[], str] = "https://proapi.115.com", 
        *, 
        async_: Literal[False, True] = False, 
        **request_kwargs, 
    ) -> dict | Coroutine[Any, Any, dict]:
        """获取用户信息

        GET https://proapi.115.com/android/user/card
        """
        api = complete_url("/user/card", base_url=base_url, app=app)
        return self.request(url=api, async_=async_, **request_kwargs)

    @overload
    def user_count_space_nums(
        self, 
        /, 
        app: str = "android", 
        base_url: str | Callable[[], str] = "https://proapi.115.com", 
        *, 
        async_: Literal[False] = False, 
        **request_kwargs, 
    ) -> dict:
        ...
    @overload
    def user_count_space_nums(
        self, 
        /, 
        app: str = "android", 
        base_url: str | Callable[[], str] = "https://proapi.115.com", 
        *, 
        async_: Literal[True], 
        **request_kwargs, 
    ) -> Coroutine[Any, Any, dict]:
        ...
    def user_count_space_nums(
        self, 
        /, 
        app: str = "android", 
        base_url: str | Callable[[], str] = "https://proapi.115.com", 
        *, 
        async_: Literal[False, True] = False, 
        **request_kwargs, 
    ) -> dict | Coroutine[Any, Any, dict]:
        """获取当前已用空间、可用空间、登录设备等信息

        GET https://proapi.115.com/android/2.0/user/count_space_nums
        """
        api = complete_url("/2.0/user/count_space_nums", base_url=base_url, app=app)
        return self.request(url=api, async_=async_, **request_kwargs)

    @overload
    def user_face_code(
        self: None | ClientRequestMixin = None, 
        /, 
        base_url: str | Callable[[], str] = "https://my.115.com", 
        *, 
        async_: Literal[False] = False, 
        **request_kwargs, 
    ) -> dict:
        ...
    @overload
    def user_face_code(
        self: None | ClientRequestMixin = None, 
        /, 
        base_url: str | Callable[[], str] = "https://my.115.com", 
        *, 
        async_: Literal[True], 
        **request_kwargs, 
    ) -> Coroutine[Any, Any, dict]:
        ...
    def user_face_code(
        self: None | ClientRequestMixin = None, 
        /, 
        base_url: str | Callable[[], str] = "https://my.115.com", 
        *, 
        async_: Literal[False, True] = False, 
        **request_kwargs, 
    ) -> dict | Coroutine[Any, Any, dict]:
        """获取表情包

        GET https://my.115.com/api/face_code.js

        .. note::
            可以作为 ``staticmethod`` 使用
        """
        api = complete_url("/api/face_code.js", base_url=base_url)
        request_kwargs.setdefault("parse", lambda _, b, /: default_parse(_, b[25:-1]))
        return get_request(async_, request_kwargs, self=self)(url=api, **request_kwargs)

    @overload
    def user_fingerprint(
        self, 
        /, 
        base_url: str | Callable[[], str] = "https://webapi.115.com", 
        *, 
        async_: Literal[False] = False, 
        **request_kwargs, 
    ) -> dict:
        ...
    @overload
    def user_fingerprint(
        self, 
        /, 
        base_url: str | Callable[[], str] = "https://webapi.115.com", 
        *, 
        async_: Literal[True], 
        **request_kwargs, 
    ) -> Coroutine[Any, Any, dict]:
        ...
    def user_fingerprint(
        self, 
        /, 
        base_url: str | Callable[[], str] = "https://webapi.115.com", 
        *, 
        async_: Literal[False, True] = False, 
        **request_kwargs, 
    ) -> dict | Coroutine[Any, Any, dict]:
        """获取截图时嵌入的水印

        GET https://webapi.115.com/user/fingerprint
        """
        api = complete_url("/user/fingerprint", base_url=base_url)
        return self.request(url=api, async_=async_, **request_kwargs)

    @overload # type: ignore
    def user_info(
        self: int | str | dict | ClientRequestMixin = 11500, 
        payload: None | int | str | dict = None, 
        /, 
        base_url: str | Callable[[], str] = "https://my.115.com", 
        *, 
        async_: Literal[False] = False, 
        **request_kwargs, 
    ) -> dict:
        ...
    @overload
    def user_info(
        self: int | str | dict | ClientRequestMixin = 11500, 
        payload: None | int | str | dict = None, 
        /, 
        base_url: str | Callable[[], str] = "https://my.115.com", 
        *, 
        async_: Literal[True], 
        **request_kwargs, 
    ) -> Coroutine[Any, Any, dict]:
        ...
    def user_info(
        self: int | str | dict | ClientRequestMixin = 11500, 
        payload: None | int | str | dict = None, 
        /, 
        base_url: str | Callable[[], str] = "https://my.115.com", 
        *, 
        async_: Literal[False, True] = False, 
        **request_kwargs, 
    ) -> dict | Coroutine[Any, Any, dict]:
        """获取用户信息

        GET https://my.115.com/proapi/3.0/index.php?method=user_info

        .. note::
            可以作为 ``staticmethod`` 使用，但必须指定查询参数 ``uid``

        :payload:
            - uid: int | str
        """
        api = complete_url("/proapi/3.0/index.php", base_url=base_url, query={"method": "user_info"})
        if not isinstance(self, ClientRequestMixin):
            payload = self
        elif payload is None:
            if isinstance(self, P115OpenClient):
                payload = self.user_id
            else:
                raise ValueError("no payload provided")
        if not isinstance(payload, dict):
            payload = {"uid": payload}
        return get_request(async_, request_kwargs, self=self)(
            url=api, params=payload, **request_kwargs)

    @overload
    def user_info_set(
        self, 
        payload: dict, 
        /, 
        base_url: str | Callable[[], str] = "https://my.115.com", 
        *, 
        async_: Literal[False] = False, 
        **request_kwargs, 
    ) -> dict:
        ...
    @overload
    def user_info_set(
        self, 
        payload: dict, 
        /, 
        base_url: str | Callable[[], str] = "https://my.115.com", 
        *, 
        async_: Literal[True], 
        **request_kwargs, 
    ) -> Coroutine[Any, Any, dict]:
        ...
    def user_info_set(
        self, 
        payload: dict, 
        /, 
        base_url: str | Callable[[], str] = "https://my.115.com", 
        *, 
        async_: Literal[False, True] = False, 
        **request_kwargs, 
    ) -> dict | Coroutine[Any, Any, dict]:
        """更新用户信息

        POST https://my.115.com/proapi/3.0/index.php?method=set_user

        :payload:
            - user_name: str = <default> 💡 网名（1-15 个中英文字符，15天允许修改一次网名）
            - gender: -1 | 0 | 1 = <default> 💡 性别。-1:未知 0:女 1:男
            - calendar_type: 0 | 1 = <default> 💡 日历类型。0:公历 1:农历
            - birthday: str = <default> 💡 生日，格式为 年-月-日（不需要补前 0，初始值为 0-0-0）
            - height: int = <default> 💡 身高
            - weight: int = <default> 💡 体重
            - blood_type: "A" | "B" | "C" | "D" | "O" = <default> 💡 血型。A:A型 B:B型 C:AB型 O:O型 D:其它
            - is_marry: int = <default> 💡 感情

                - 0: 保密
                - 1: 单身
                - 2: 恋爱中
                - 3: 已婚
                - 4: 分居
                - 5: 离异
                - 9: 请选择

            - education: int = <default> 💡 学历

                - -1: 选择学历
                -  0: 初中
                -  1: 高中
                -  2: 中专
                -  3: 大专
                -  4: 本科
                -  5: 硕士
                -  6: 博士及以上

            - job: int = <default> 💡 职业

                - -1: 选择职业
                -  1: 计算机/互联网/通信
                -  2: 生产/工艺/制造
                -  3: 医疗/护理/制药
                -  4: 金融/银行/投资/保险
                -  5: 商业/服务业/个体经营
                -  6: 文化/广告/传媒
                -  7: 娱乐/艺术/表演
                -  8: 律师/法务
                -  9: 教育/培训
                - 10: 公务员/行政/事业单位
                - 11: 模特
                - 12: 空姐
                - 13: 学生
                - 14: 其他职业

            - salary: str = <default> 💡 收入

                - ""
                - "2千-3千"
                - "3千-4.5千"
                - "4.5千-6千"
                - "7千-8千"
                - "8千-1万"
                - "1万以下"
                - "1万-2万"
                - "2万-3万"
                - "3万-4万"
                - "4万-5万"
                - "5万以上"

            - location_birth: int = <default> 💡 家乡。填 115 给出的地区编码，初始值为 0
            - location: int = <default> 💡 现居地。填 115 给出的地区编码，初始值为 0
            - location_link: int = <default> 💡 快递地址。填 115 给出的地区编码，初始值为 0
            - address: str = <default> 💡 输入详细街道地址
            - wechat: str = <default> 💡 微信
            - weibo: str = <default> 💡 微博
            - alipay: str = <default> 💡 支付宝
            - pub_mobile: str = <default> 💡 电话
            - pub_email: str = <default> 💡 邮箱
            - homepage: str = <default> 💡 个人网站
            - like_celeb: str = <default> 💡 最喜欢的名人
            - like_music: str = <default> 💡 最喜欢的音乐
            - like_animal: str = <default> 💡 最喜欢的动物
            - like_book: str = <default> 💡 最喜欢的书籍
            - like_video: str = <default> 💡 最喜欢的视频
            - interest: str = <default> 💡 兴趣爱好
        """
        api = complete_url("/proapi/3.0/index.php", base_url=base_url, query={"method": "set_user"})
        return self.request(url=api, method="POST", data=payload, async_=async_, **request_kwargs)

    @overload
    def user_interests_list(
        self, 
        /, 
        base_url: str | Callable[[], str] = "https://my.115.com", 
        *, 
        async_: Literal[False] = False, 
        **request_kwargs, 
    ) -> dict:
        ...
    @overload
    def user_interests_list(
        self, 
        /, 
        base_url: str | Callable[[], str] = "https://my.115.com", 
        *, 
        async_: Literal[True], 
        **request_kwargs, 
    ) -> Coroutine[Any, Any, dict]:
        ...
    def user_interests_list(
        self, 
        /, 
        base_url: str | Callable[[], str] = "https://my.115.com", 
        *, 
        async_: Literal[False, True] = False, 
        **request_kwargs, 
    ) -> dict | Coroutine[Any, Any, dict]:
        """用户兴趣列表

        GET https://my.115.com/proapi/3.0/index.php?method=get_interests_list
        """
        api = complete_url("/proapi/3.0/index.php", base_url=base_url, query={"method": "get_interests_list"})
        return self.request(url=api, async_=async_, **request_kwargs)

    @overload
    def user_my(
        self, 
        /, 
        base_url: str | Callable[[], str] = "https://my.115.com", 
        *, 
        async_: Literal[False] = False, 
        **request_kwargs, 
    ) -> dict:
        ...
    @overload
    def user_my(
        self, 
        /, 
        base_url: str | Callable[[], str] = "https://my.115.com", 
        *, 
        async_: Literal[True], 
        **request_kwargs, 
    ) -> Coroutine[Any, Any, dict]:
        ...
    def user_my(
        self, 
        /, 
        base_url: str | Callable[[], str] = "https://my.115.com", 
        *, 
        async_: Literal[False, True] = False, 
        **request_kwargs, 
    ) -> dict | Coroutine[Any, Any, dict]:
        """获取此用户信息

        GET https://my.115.com/?ct=ajax&ac=
        """
        api = complete_url(base_url=base_url, query={"ct": "ajax", "ac": "nav"})
        return self.request(url=api, async_=async_, **request_kwargs)

    @overload
    def user_my_info(
        self, 
        /, 
        base_url: str | Callable[[], str] = "https://my.115.com", 
        *, 
        async_: Literal[False] = False, 
        **request_kwargs, 
    ) -> dict:
        ...
    @overload
    def user_my_info(
        self, 
        /, 
        base_url: str | Callable[[], str] = "https://my.115.com", 
        *, 
        async_: Literal[True], 
        **request_kwargs, 
    ) -> Coroutine[Any, Any, dict]:
        ...
    def user_my_info(
        self, 
        /, 
        base_url: str | Callable[[], str] = "https://my.115.com", 
        *, 
        async_: Literal[False, True] = False, 
        **request_kwargs, 
    ) -> dict | Coroutine[Any, Any, dict]:
        """获取此用户信息（更全）

        GET https://my.115.com/?ct=ajax&ac=get_user_aq
        """
        api = complete_url(base_url=base_url, query={"ct": "ajax", "ac": "get_user_aq"})
        return self.request(url=api, async_=async_, **request_kwargs)

    @overload
    def user_points_balance(
        self, 
        /, 
        app: str = "web", 
        base_url: str | Callable[[], str] = "https://points.115.com", 
        *, 
        async_: Literal[False] = False, 
        **request_kwargs, 
    ) -> dict:
        ...
    @overload
    def user_points_balance(
        self, 
        /, 
        app: str = "web", 
        base_url: str | Callable[[], str] = "https://points.115.com", 
        *, 
        async_: Literal[True], 
        **request_kwargs, 
    ) -> Coroutine[Any, Any, dict]:
        ...
    def user_points_balance(
        self, 
        /, 
        app: str = "web", 
        base_url: str | Callable[[], str] = "https://points.115.com", 
        *, 
        async_: Literal[False, True] = False, 
        **request_kwargs, 
    ) -> dict | Coroutine[Any, Any, dict]:
        """剩余的签到积分

        GET https://points.115.com/api/1.0/web/1.0/user/balance
        """
        api = complete_url(f"/api/1.0/{app}/1.0/user/balance", base_url=base_url)
        return self.request(url=api, async_=async_, **request_kwargs)

    @overload
    def user_points_sign(
        self, 
        /, 
        app: str = "android", 
        base_url: str | Callable[[], str] = "https://proapi.115.com", 
        *, 
        async_: Literal[False] = False, 
        **request_kwargs, 
    ) -> dict:
        ...
    @overload
    def user_points_sign(
        self, 
        /, 
        app: str = "android", 
        base_url: str | Callable[[], str] = "https://proapi.115.com", 
        *, 
        async_: Literal[True], 
        **request_kwargs, 
    ) -> Coroutine[Any, Any, dict]:
        ...
    def user_points_sign(
        self, 
        /, 
        app: str = "android", 
        base_url: str | Callable[[], str] = "https://proapi.115.com", 
        *, 
        async_: Literal[False, True] = False, 
        **request_kwargs, 
    ) -> dict | Coroutine[Any, Any, dict]:
        """获取签到信息

        GET https://proapi.115.com/android/2.0/user/points_sign
        """
        api = complete_url("/2.0/user/points_sign", base_url=base_url, app=app)
        return self.request(url=api, async_=async_, **request_kwargs)

    @overload
    def user_points_sign_post(
        self, 
        /, 
        app: str = "android", 
        base_url: str | Callable[[], str] = "https://proapi.115.com", 
        *, 
        async_: Literal[False] = False, 
        **request_kwargs, 
    ) -> dict:
        ...
    @overload
    def user_points_sign_post(
        self, 
        /, 
        app: str = "android", 
        base_url: str | Callable[[], str] = "https://proapi.115.com", 
        *, 
        async_: Literal[True], 
        **request_kwargs, 
    ) -> Coroutine[Any, Any, dict]:
        ...
    def user_points_sign_post(
        self, 
        /, 
        app: str = "android", 
        base_url: str | Callable[[], str] = "https://proapi.115.com", 
        *, 
        async_: Literal[False, True] = False, 
        **request_kwargs, 
    ) -> dict | Coroutine[Any, Any, dict]:
        """每日签到（注意：不要用 web，即浏览器，的 cookies，会失败）

        POST https://proapi.115.com/android/2.0/user/points_sign
        """
        api = complete_url("/2.0/user/points_sign", base_url=base_url, app=app)
        t = int(time())
        payload = {
            "token": sha1(b"%d-Points_Sign@#115-%d" % (self.user_id, t)).hexdigest(), 
            "token_time": t, 
        }
        return self.request(url=api, method="POST", data=payload, async_=async_, **request_kwargs)

    @overload
    def user_points_transaction(
        self, 
        payload: int | dict = 0, 
        /, 
        app: str = "web", 
        base_url: str | Callable[[], str] = "https://points.115.com", 
        *, 
        async_: Literal[False] = False, 
        **request_kwargs, 
    ) -> dict:
        ...
    @overload
    def user_points_transaction(
        self, 
        payload: int | dict = 0, 
        /, 
        app: str = "web", 
        base_url: str | Callable[[], str] = "https://points.115.com", 
        *, 
        async_: Literal[True], 
        **request_kwargs, 
    ) -> Coroutine[Any, Any, dict]:
        ...
    def user_points_transaction(
        self, 
        payload: int | dict = 0, 
        /, 
        app: str = "web", 
        base_url: str | Callable[[], str] = "https://points.115.com", 
        *, 
        async_: Literal[False, True] = False, 
        **request_kwargs, 
    ) -> dict | Coroutine[Any, Any, dict]:
        """签到记录

        GET https://points.115.com/api/1.0/web/1.0/user/transaction

        payload:
            - start: int = 0
            - limit: int = 32
            - month: str = <default> 💡 月份，格式为 YYYYMM
        """
        api = complete_url(f"/api/1.0/{app}/1.0/user/transaction", base_url=base_url)
        if isinstance(payload, int):
            payload = {"start": payload}
        payload.setdefault("limit", 32)
        return self.request(url=api, params=payload, async_=async_, **request_kwargs)

    @overload
    def user_public(
        self, 
        /, 
        base_url: str | Callable[[], str] = "https://my.115.com", 
        *, 
        async_: Literal[False] = False, 
        **request_kwargs, 
    ) -> dict:
        ...
    @overload
    def user_public(
        self, 
        /, 
        base_url: str | Callable[[], str] = "https://my.115.com", 
        *, 
        async_: Literal[True], 
        **request_kwargs, 
    ) -> Coroutine[Any, Any, dict]:
        ...
    def user_public(
        self, 
        /, 
        base_url: str | Callable[[], str] = "https://my.115.com", 
        *, 
        async_: Literal[False, True] = False, 
        **request_kwargs, 
    ) -> dict | Coroutine[Any, Any, dict]:
        """用户隐私设置

        GET https://my.115.com/proapi/3.0/index.php?method=get_public
        """
        api = complete_url("/proapi/3.0/index.php", base_url=base_url, query={"method": "get_public"})
        return self.request(url=api, async_=async_, **request_kwargs)

    @overload
    def user_public_set(
        self, 
        payload: dict | str, 
        /, 
        base_url: str | Callable[[], str] = "https://my.115.com", 
        *, 
        async_: Literal[False] = False, 
        **request_kwargs, 
    ) -> dict:
        ...
    @overload
    def user_public_set(
        self, 
        payload: dict | str, 
        /, 
        base_url: str | Callable[[], str] = "https://my.115.com", 
        *, 
        async_: Literal[True], 
        **request_kwargs, 
    ) -> Coroutine[Any, Any, dict]:
        ...
    def user_public_set(
        self, 
        payload: dict | str, 
        /, 
        base_url: str | Callable[[], str] = "https://my.115.com", 
        *, 
        async_: Literal[False, True] = False, 
        **request_kwargs, 
    ) -> dict | Coroutine[Any, Any, dict]:
        """设置用户隐私

        POST https://my.115.com/proapi/3.0/index.php?method=set_public

        :payload:
            - column: str 💡 隐私项
            - open: 0 | 1 = 1 💡 是否公开可见
        """
        api = complete_url("/proapi/3.0/index.php", base_url=base_url, query={"method": "set_public"})
        if isinstance(payload, str):
            payload = {"column": payload}
        payload.setdefault("open", 1)
        return self.request(url=api, method="POST", data=payload, async_=async_, **request_kwargs)

    @overload
    def user_security_key_check(
        self, 
        payload: int | str | dict = "", 
        /, 
        app="android", 
        base_url: str | Callable[[], str] = "https://passportapi.115.com", 
        *, 
        async_: Literal[False] = False, 
        **request_kwargs, 
    ) -> dict:
        ...
    @overload
    def user_security_key_check(
        self, 
        payload: int | str | dict = "", 
        /, 
        app="android", 
        base_url: str | Callable[[], str] = "https://passportapi.115.com", 
        *, 
        async_: Literal[True], 
        **request_kwargs, 
    ) -> Coroutine[Any, Any, dict]:
        ...
    def user_security_key_check(
        self, 
        payload: int | str | dict = "", 
        /, 
        app="android", 
        base_url: str | Callable[[], str] = "https://passportapi.115.com", 
        *, 
        async_: Literal[False, True] = False, 
        **request_kwargs, 
    ) -> dict | Coroutine[Any, Any, dict]:
        """获取安全密钥对应的 token，可以提供给某些接口，作为通过安全密钥验证的凭证

        POST https://passportapi.115.com/app/1.0/android/1.0/user/security_key_check

        :payload:
            - passwd: int | str = "000000" 💡 安全密钥，值为实际安全密钥的 md5 哈希值
        """
        api = complete_url(f"/app/1.0/{app}/1.0/user/security_key_check", base_url=base_url)
        if isinstance(payload, (int, str)):
            payload = {"passwd": payload}
        payload["passwd"] = md5_secret_password(payload.get("passwd"))
        return self.request(url=api, method="POST", data=payload, async_=async_, **request_kwargs)

    @overload
    def user_setting(
        self, 
        /, 
        base_url: str | Callable[[], str] = "https://115.com", 
        *, 
        async_: Literal[False] = False, 
        **request_kwargs, 
    ) -> dict:
        ...
    @overload
    def user_setting(
        self, 
        /, 
        base_url: str | Callable[[], str] = "https://115.com", 
        *, 
        async_: Literal[True], 
        **request_kwargs, 
    ) -> Coroutine[Any, Any, dict]:
        ...
    def user_setting(
        self, 
        /, 
        base_url: str | Callable[[], str] = "https://115.com", 
        *, 
        async_: Literal[False, True] = False, 
        **request_kwargs, 
    ) -> dict | Coroutine[Any, Any, dict]:
        """获取此账户的设置

        GET https://115.com/?ac=setting&even=saveedit&is_wl_tpl=1
        """
        api = complete_url(base_url=base_url, query={"ac": "setting", "even": "saveedit", "is_wl_tpl": 1})
        return self.request(url=api, async_=async_, **request_kwargs)

    @overload
    def user_setting2(
        self, 
        /, 
        base_url: str | Callable[[], str] = "https://115.com", 
        *, 
        async_: Literal[False] = False, 
        **request_kwargs, 
    ) -> dict:
        ...
    @overload
    def user_setting2(
        self, 
        /, 
        base_url: str | Callable[[], str] = "https://115.com", 
        *, 
        async_: Literal[True], 
        **request_kwargs, 
    ) -> Coroutine[Any, Any, dict]:
        ...
    def user_setting2(
        self, 
        /, 
        base_url: str | Callable[[], str] = "https://115.com", 
        *, 
        async_: Literal[False, True] = False, 
        **request_kwargs, 
    ) -> dict | Coroutine[Any, Any, dict]:
        """获取此账户的设置

        GET https://115.com/?ct=user_setting&ac=get
        """
        api = complete_url(base_url=base_url, query={"ct": "user_setting", "ac": "get"})
        return self.request(url=api, async_=async_, **request_kwargs)

    @overload
    def user_setting_set(
        self, 
        payload: dict, 
        /, 
        base_url: str | Callable[[], str] = "https://115.com", 
        *, 
        async_: Literal[False] = False, 
        **request_kwargs, 
    ) -> dict:
        ...
    @overload
    def user_setting_set(
        self, 
        payload: dict, 
        /, 
        base_url: str | Callable[[], str] = "https://115.com", 
        *, 
        async_: Literal[True], 
        **request_kwargs, 
    ) -> Coroutine[Any, Any, dict]:
        ...
    def user_setting_set(
        self, 
        payload: dict, 
        /, 
        base_url: str | Callable[[], str] = "https://115.com", 
        *, 
        async_: Literal[False, True] = False, 
        **request_kwargs, 
    ) -> dict | Coroutine[Any, Any, dict]:
        """修改此账户的网页版设置（提示：较为复杂，自己抓包研究）

        POST https://115.com/?ac=setting&even=saveedit&is_wl_tpl=1
        """
        api = complete_url(base_url=base_url, query={"ct": "setting", "even": "saveedit", "is_wl_tpl": 1})
        return self.request(url=api, method="POST", data=payload, async_=async_, **request_kwargs)

    @overload
    def user_setting_web(
        self, 
        /, 
        base_url: str | Callable[[], str] = "https://webapi.115.com", 
        *, 
        async_: Literal[False] = False, 
        **request_kwargs, 
    ) -> dict:
        ...
    @overload
    def user_setting_web(
        self, 
        /, 
        base_url: str | Callable[[], str] = "https://webapi.115.com", 
        *, 
        async_: Literal[True], 
        **request_kwargs, 
    ) -> Coroutine[Any, Any, dict]:
        ...
    def user_setting_web(
        self, 
        /, 
        base_url: str | Callable[[], str] = "https://webapi.115.com", 
        *, 
        async_: Literal[False, True] = False, 
        **request_kwargs, 
    ) -> dict | Coroutine[Any, Any, dict]:
        """获取此账户的 app 版设置（提示：较为复杂，自己抓包研究）

        GET https://webapi.115.com/user/setting
        """
        api = complete_url("/user/setting", base_url=base_url)
        return self.request(url=api, async_=async_, **request_kwargs)

    @overload
    def user_setting_web_set(
        self, 
        payload: dict, 
        /, 
        base_url: str | Callable[[], str] = "https://webapi.115.com", 
        *, 
        async_: Literal[False] = False, 
        **request_kwargs, 
    ) -> dict:
        ...
    @overload
    def user_setting_web_set(
        self, 
        payload: dict, 
        /, 
        base_url: str | Callable[[], str] = "https://webapi.115.com", 
        *, 
        async_: Literal[True], 
        **request_kwargs, 
    ) -> Coroutine[Any, Any, dict]:
        ...
    def user_setting_web_set(
        self, 
        payload: dict, 
        /, 
        base_url: str | Callable[[], str] = "https://webapi.115.com", 
        *, 
        async_: Literal[False, True] = False, 
        **request_kwargs, 
    ) -> dict | Coroutine[Any, Any, dict]:
        """获取（并可修改）此账户的网页版设置（提示：较为复杂，自己抓包研究）

        POST https://webapi.115.com/user/setting
        """
        api = complete_url("/user/setting", base_url=base_url)
        return self.request(url=api, method="POST", data=payload, async_=async_, **request_kwargs)

    @overload
    def user_setting_app(
        self, 
        /, 
        app: str = "android", 
        base_url: str | Callable[[], str] = "https://proapi.115.com", 
        *, 
        async_: Literal[False] = False, 
        **request_kwargs, 
    ) -> dict:
        ...
    @overload
    def user_setting_app(
        self, 
        /, 
        app: str = "android", 
        base_url: str | Callable[[], str] = "https://proapi.115.com", 
        *, 
        async_: Literal[True], 
        **request_kwargs, 
    ) -> Coroutine[Any, Any, dict]:
        ...
    def user_setting_app(
        self, 
        /, 
        app: str = "android", 
        base_url: str | Callable[[], str] = "https://proapi.115.com", 
        *, 
        async_: Literal[False, True] = False, 
        **request_kwargs, 
    ) -> dict | Coroutine[Any, Any, dict]:
        """获取此账户的 app 版设置（提示：较为复杂，自己抓包研究）

        GET https://proapi.115.com/android/1.0/user/setting
        """
        api = complete_url("/1.0/user/setting", base_url=base_url, app=app)
        return self.request(url=api, async_=async_, **request_kwargs)

    @overload
    def user_setting_app_set(
        self, 
        payload: dict, 
        /, 
        app: str = "android", 
        base_url: str | Callable[[], str] = "https://proapi.115.com", 
        *, 
        async_: Literal[False] = False, 
        **request_kwargs, 
    ) -> dict:
        ...
    @overload
    def user_setting_app_set(
        self, 
        payload: dict, 
        /, 
        app: str = "android", 
        base_url: str | Callable[[], str] = "https://proapi.115.com", 
        *, 
        async_: Literal[True], 
        **request_kwargs, 
    ) -> Coroutine[Any, Any, dict]:
        ...
    def user_setting_app_set(
        self, 
        payload: dict, 
        /, 
        app: str = "android", 
        base_url: str | Callable[[], str] = "https://proapi.115.com", 
        *, 
        async_: Literal[False, True] = False, 
        **request_kwargs, 
    ) -> dict | Coroutine[Any, Any, dict]:
        """获取（并可修改）此账户的网页版设置（提示：较为复杂，自己抓包研究）

        POST https://proapi.115.com/android/1.0/user/setting
        """
        api = complete_url("/1.0/user/setting", base_url=base_url, app=app)
        return self.request(url=api, method="POST", data=payload, async_=async_, **request_kwargs)

    @overload
    def user_sign(
        self, 
        /, 
        base_url: str | Callable[[], str] = "https://q.115.com", 
        *, 
        async_: Literal[False] = False, 
        **request_kwargs, 
    ) -> dict:
        ...
    @overload
    def user_sign(
        self, 
        /, 
        base_url: str | Callable[[], str] = "https://q.115.com", 
        *, 
        async_: Literal[True], 
        **request_kwargs, 
    ) -> Coroutine[Any, Any, dict]:
        ...
    def user_sign(
        self, 
        /, 
        base_url: str | Callable[[], str] = "https://q.115.com", 
        *, 
        async_: Literal[False, True] = False, 
        **request_kwargs, 
    ) -> dict | Coroutine[Any, Any, dict]:
        """个性签名

        GET https://q.115.com/home/setting/sign
        """
        api = complete_url("/home/setting/sign", base_url=base_url)
        return self.request(url=api, async_=async_, **request_kwargs)

    @overload
    def user_sign_set(
        self, 
        payload: dict | str, 
        /, 
        base_url: str | Callable[[], str] = "https://q.115.com", 
        *, 
        async_: Literal[False] = False, 
        **request_kwargs, 
    ) -> dict:
        ...
    @overload
    def user_sign_set(
        self, 
        payload: dict | str, 
        /, 
        base_url: str | Callable[[], str] = "https://q.115.com", 
        *, 
        async_: Literal[True], 
        **request_kwargs, 
    ) -> Coroutine[Any, Any, dict]:
        ...
    def user_sign_set(
        self, 
        payload: dict | str, 
        /, 
        base_url: str | Callable[[], str] = "https://q.115.com", 
        *, 
        async_: Literal[False, True] = False, 
        **request_kwargs, 
    ) -> dict | Coroutine[Any, Any, dict]:
        """修改个性签名

        POST https://q.115.com/ajax_users/save_sign

        :payload:
            - content: str 💡 个性签名，支持 HTML
        """
        api = complete_url("/ajax_users/save_sign", base_url=base_url)
        if isinstance(payload, str):
            payload = {"content": payload}
        return self.request(url=api, method="POST", data=payload, async_=async_, **request_kwargs)

    @overload
    def user_space_info(
        self, 
        /, 
        app: str = "android", 
        base_url: str | Callable[[], str] = "https://proapi.115.com", 
        *, 
        async_: Literal[False] = False, 
        **request_kwargs, 
    ) -> dict:
        ...
    @overload
    def user_space_info(
        self, 
        /, 
        app: str = "android", 
        base_url: str | Callable[[], str] = "https://proapi.115.com", 
        *, 
        async_: Literal[True], 
        **request_kwargs, 
    ) -> Coroutine[Any, Any, dict]:
        ...
    def user_space_info(
        self, 
        /, 
        app: str = "android", 
        base_url: str | Callable[[], str] = "https://proapi.115.com", 
        *, 
        async_: Literal[False, True] = False, 
        **request_kwargs, 
    ) -> dict | Coroutine[Any, Any, dict]:
        """获取使用空间的统计数据（较为简略，如需更详细，请用 ``P115Client.fs_index_info()``）

        GET https://proapi.115.com/android/user/space_info
        """
        api = complete_url("/user/space_info", base_url=base_url, app=app)
        return self.request(url=api, async_=async_, **request_kwargs)

    @overload
    def user_teen_mode_state(
        self, 
        /, 
        app: str = "web", 
        base_url: str | Callable[[], str] = "https://passportapi.115.com", 
        *, 
        async_: Literal[False] = False, 
        **request_kwargs, 
    ) -> dict:
        ...
    @overload
    def user_teen_mode_state(
        self, 
        /, 
        app: str = "web", 
        base_url: str | Callable[[], str] = "https://passportapi.115.com", 
        *, 
        async_: Literal[True], 
        **request_kwargs, 
    ) -> Coroutine[Any, Any, dict]:
        ...
    def user_teen_mode_state(
        self, 
        /, 
        app: str = "web", 
        base_url: str | Callable[[], str] = "https://passportapi.115.com", 
        *, 
        async_: Literal[False, True] = False, 
        **request_kwargs, 
    ) -> dict | Coroutine[Any, Any, dict]:
        """获取青少年（未成年）模式状态

        GET https://passportapi.115.com/app/1.0/web/1.0/user/teen_mode_state
        """
        api = complete_url(f"/app/1.0/{app}/1.0/user/teen_mode_state", base_url=base_url)
        return self.request(url=api, async_=async_, **request_kwargs)

    @overload
    def user_teen_mode_state_set(
        self, 
        payload: bool | dict = True, 
        /, 
        app: str = "web", 
        base_url: str | Callable[[], str] = "https://passportapi.115.com", 
        *, 
        async_: Literal[False] = False, 
        **request_kwargs, 
    ) -> dict:
        ...
    @overload
    def user_teen_mode_state_set(
        self, 
        payload: bool | dict = True, 
        /, 
        app: str = "web", 
        base_url: str | Callable[[], str] = "https://passportapi.115.com", 
        *, 
        async_: Literal[True], 
        **request_kwargs, 
    ) -> Coroutine[Any, Any, dict]:
        ...
    def user_teen_mode_state_set(
        self, 
        payload: bool | dict = True, 
        /, 
        app: str = "web", 
        base_url: str | Callable[[], str] = "https://passportapi.115.com", 
        *, 
        async_: Literal[False, True] = False, 
        **request_kwargs, 
    ) -> dict | Coroutine[Any, Any, dict]:
        """开关青少年（未成年）模式状态

        POST https://passportapi.115.com/app/1.0/android/1.0/user/teen_mode_set_state

        :payload:
            - state: 0 | 1 💡 是否开启
            - passwd: str = "0000" 💡 密码（4 位数字），需要经过 md5 签名处理，`md5(f"{passwd}{user_id}62454aa2c6fd4".encode("ascii")).hexdigest()`
        """
        api = complete_url(f"/app/1.0/{app}/1.0/user/teen_mode_set_state", base_url=base_url)
        if isinstance(payload, bool):
            payload = {"state": int(payload), "passwd": "0000"}
        else:
            payload.setdefault("passwd", "0000")
        if len(str(passwd := payload.get("passwd"))):
            payload["passwd"] = md5(f"{passwd:>04}{self.user_id}62454aa2c6fd4".encode("ascii")).hexdigest()
        return self.request(url=api, method="POST", data=payload, async_=async_, **request_kwargs)

    @overload
    def user_vip_check_spw(
        self, 
        /, 
        app: str = "android", 
        base_url: str | Callable[[], str] = "https://proapi.115.com", 
        *, 
        async_: Literal[False] = False, 
        **request_kwargs, 
    ) -> dict:
        ...
    @overload
    def user_vip_check_spw(
        self, 
        /, 
        app: str = "android", 
        base_url: str | Callable[[], str] = "https://proapi.115.com", 
        *, 
        async_: Literal[True], 
        **request_kwargs, 
    ) -> Coroutine[Any, Any, dict]:
        ...
    def user_vip_check_spw(
        self, 
        /, 
        app: str = "android", 
        base_url: str | Callable[[], str] = "https://proapi.115.com", 
        *, 
        async_: Literal[False, True] = False, 
        **request_kwargs, 
    ) -> dict | Coroutine[Any, Any, dict]:
        """获取用户积分、余额等信息

        GET https://proapi.115.com/android/vip/check_spw
        """
        api = complete_url("/vip/check_spw", base_url=base_url, app=app)
        return self.request(url=api, async_=async_, **request_kwargs)

    @overload
    def user_vip_limit(
        self, 
        payload: int | dict = 2, 
        /, 
        base_url: str | Callable[[], str] = "https://webapi.115.com", 
        *, 
        async_: Literal[False] = False, 
        **request_kwargs, 
    ) -> dict:
        ...
    @overload
    def user_vip_limit(
        self, 
        payload: int | dict = 2, 
        /, 
        base_url: str | Callable[[], str] = "https://webapi.115.com", 
        *, 
        async_: Literal[True], 
        **request_kwargs, 
    ) -> Coroutine[Any, Any, dict]:
        ...
    def user_vip_limit(
        self, 
        payload: int | dict = 2, 
        /, 
        base_url: str | Callable[[], str] = "https://webapi.115.com", 
        *, 
        async_: Literal[False, True] = False, 
        **request_kwargs, 
    ) -> dict | Coroutine[Any, Any, dict]:
        """获取 vip 的某些限制

        GET https://webapi.115.com/user/vip_limit

        :payload:
            - feature: int = 2
        """
        api = complete_url("/user/vip_limit", base_url=base_url)
        if isinstance(payload, int):
            payload = {"feature": payload}
        return self.request(url=api, params=payload, async_=async_, **request_kwargs)

    ########## User Share API ##########

    @overload
    def usershare_action(
        self, 
        payload: int | dict, 
        /, 
        base_url: str | Callable[[], str] = "https://webapi.115.com", 
        *, 
        async_: Literal[False] = False, 
        **request_kwargs, 
    ) -> dict:
        ...
    @overload
    def usershare_action(
        self, 
        payload: int | dict, 
        /, 
        base_url: str | Callable[[], str] = "https://webapi.115.com", 
        *, 
        async_: Literal[True], 
        **request_kwargs, 
    ) -> Coroutine[Any, Any, dict]:
        ...
    def usershare_action(
        self, 
        payload: int | dict, 
        /, 
        base_url: str | Callable[[], str] = "https://webapi.115.com", 
        *, 
        async_: Literal[False, True] = False, 
        **request_kwargs, 
    ) -> dict | Coroutine[Any, Any, dict]:
        """获取共享动态列表

        GET https://webapi.115.com/usershare/action

        :payload:
            - share_id: int | str
            - offset: int = 0
            - limit: int = 32
        """
        api = complete_url("/usershare/action", base_url=base_url)
        if isinstance(payload, int):
            payload = {"share_id": payload}
        payload = {"limit": 32, "offset": 0, **payload}
        return self.request(url=api, params=payload, async_=async_, **request_kwargs)

    @overload
    def usershare_invite(
        self, 
        payload: int | str | dict, 
        /, 
        base_url: str | Callable[[], str] = "https://webapi.115.com", 
        *, 
        async_: Literal[False] = False, 
        **request_kwargs, 
    ) -> dict:
        ...
    @overload
    def usershare_invite(
        self, 
        payload: int | str | dict, 
        /, 
        base_url: str | Callable[[], str] = "https://webapi.115.com", 
        *, 
        async_: Literal[True], 
        **request_kwargs, 
    ) -> Coroutine[Any, Any, dict]:
        ...
    def usershare_invite(
        self, 
        payload: int | str | dict, 
        /, 
        base_url: str | Callable[[], str] = "https://webapi.115.com", 
        *, 
        async_: Literal[False, True] = False, 
        **request_kwargs, 
    ) -> dict | Coroutine[Any, Any, dict]:
        """获取共享链接

        POST https://webapi.115.com/usershare/invite

        :payload:
            - share_id: int | str
        """
        api = complete_url("/usershare/invite", base_url=base_url)
        if isinstance(payload, (int, str)):
            payload = {"share_id": payload}
        return self.request(url=api, method="POST", data=payload, async_=async_, **request_kwargs)

    @overload
    def usershare_list(
        self, 
        payload: int | str | dict = 0, 
        /, 
        base_url: str | Callable[[], str] = "https://webapi.115.com", 
        *, 
        async_: Literal[False] = False, 
        **request_kwargs, 
    ) -> dict:
        ...
    @overload
    def usershare_list(
        self, 
        payload: int | str | dict = 0, 
        /, 
        base_url: str | Callable[[], str] = "https://webapi.115.com", 
        *, 
        async_: Literal[True], 
        **request_kwargs, 
    ) -> Coroutine[Any, Any, dict]:
        ...
    def usershare_list(
        self, 
        payload: int | str | dict = 0, 
        /, 
        base_url: str | Callable[[], str] = "https://webapi.115.com", 
        *, 
        async_: Literal[False, True] = False, 
        **request_kwargs, 
    ) -> dict | Coroutine[Any, Any, dict]:
        """共享列表

        GET https://webapi.115.com/usershare/list

        :payload:
            - offset: int = 0
            - limit: int = 1150
            - type: "all" | "others" | "mine" = "all" 💡 类型：all:全部共享 others:他人共享 mine:我共享的
        """
        api = complete_url("/usershare/list", base_url=base_url)
        if isinstance(payload, (int, str)):
            payload = {"offset": payload}
        payload = {"limit": 1150, "offset": 0, "type": "all", **payload}
        return self.request(url=api, params=payload, async_=async_, **request_kwargs)

    @overload
    def usershare_list_app(
        self, 
        payload: int | str | dict = 0, 
        /, 
        app: str = "android", 
        base_url: str | Callable[[], str] = "https://proapi.115.com", 
        *, 
        async_: Literal[False] = False, 
        **request_kwargs, 
    ) -> dict:
        ...
    @overload
    def usershare_list_app(
        self, 
        payload: int | str | dict = 0, 
        /, 
        app: str = "android", 
        base_url: str | Callable[[], str] = "https://proapi.115.com", 
        *, 
        async_: Literal[True], 
        **request_kwargs, 
    ) -> Coroutine[Any, Any, dict]:
        ...
    def usershare_list_app(
        self, 
        payload: int | str | dict = 0, 
        /, 
        app: str = "android", 
        base_url: str | Callable[[], str] = "https://proapi.115.com", 
        *, 
        async_: Literal[False, True] = False, 
        **request_kwargs, 
    ) -> dict | Coroutine[Any, Any, dict]:
        """共享列表

        GET https://proapi.115.com/android/2.0/usershare/list

        :payload:
            - offset: int = 0
            - limit: int = 1150
            - type: "all" | "others" | "mine" = "all" 💡 类型：all:全部共享 others:他人共享 mine:我共享的
        """
        api = complete_url("/2.0/usershare/list", base_url=base_url, app=app)
        if isinstance(payload, (int, str)):
            payload = {"offset": payload}
        payload = {"limit": 1150, "offset": 0, "type": "all", **payload}
        return self.request(url=api, params=payload, async_=async_, **request_kwargs)

    @overload
    def usershare_member(
        self, 
        payload: int | dict, 
        /, 
        base_url: str | Callable[[], str] = "https://webapi.115.com", 
        *, 
        async_: Literal[False] = False, 
        **request_kwargs, 
    ) -> dict:
        ...
    @overload
    def usershare_member(
        self, 
        payload: int | dict, 
        /, 
        base_url: str | Callable[[], str] = "https://webapi.115.com", 
        *, 
        async_: Literal[True], 
        **request_kwargs, 
    ) -> Coroutine[Any, Any, dict]:
        ...
    def usershare_member(
        self, 
        payload: int | dict, 
        /, 
        base_url: str | Callable[[], str] = "https://webapi.115.com", 
        *, 
        async_: Literal[False, True] = False, 
        **request_kwargs, 
    ) -> dict | Coroutine[Any, Any, dict]:
        """某共享的成员信息

        GET https://webapi.115.com/usershare/member

        :payload:
            - share_id: int | str
            - action: "member_list" | "member_info" | "noticeset" = "member_list"
            - notice_set: 0 | 1 = <default> 💡 action 为 "noticeset" 时可以设置
        """
        api = complete_url("/usershare/member", base_url=base_url)
        if isinstance(payload, int):
            payload = {"share_id": payload}
        payload.setdefault("action", "member_list")
        return self.request(url=api, params=payload, async_=async_, **request_kwargs)

    @overload
    def usershare_share(
        self, 
        payload: int | str | dict, 
        /, 
        base_url: str | Callable[[], str] = "https://webapi.115.com", 
        *, 
        async_: Literal[False] = False, 
        **request_kwargs, 
    ) -> dict:
        ...
    @overload
    def usershare_share(
        self, 
        payload: int | str | dict, 
        /, 
        base_url: str | Callable[[], str] = "https://webapi.115.com", 
        *, 
        async_: Literal[True], 
        **request_kwargs, 
    ) -> Coroutine[Any, Any, dict]:
        ...
    def usershare_share(
        self, 
        payload: int | str | dict, 
        /, 
        base_url: str | Callable[[], str] = "https://webapi.115.com", 
        *, 
        async_: Literal[False, True] = False, 
        **request_kwargs, 
    ) -> dict | Coroutine[Any, Any, dict]:
        """设置共享

        POST https://webapi.115.com/usershare/share

        :payload:
            - file_id: int | str     💡 文件或目录的 id
            - share_opt: 1 | 2 = 1   💡 1: 设置 2: 取消
            - ignore_warn: 0 | 1 = 0
            - safe_pwd: str = ""
        """
        api = complete_url("/usershare/share", base_url=base_url)
        if isinstance(payload, (int, str)):
            payload = {"file_id": payload}
        payload = {"ignore_warn": 0, "share_opt": 1, "safe_pwd": "", **payload}
        return self.request(url=api, method="POST", data=payload, async_=async_, **request_kwargs)

     ########## Extension API ##########

    @overload
    def get_fs(
        self, 
        arg: None = None, 
        /, 
        refresh: bool = False, 
        id_to_readdir: None | int | dict[int, dict[int, MutableMapping]] = None, 
    ) -> P115FileSystem:
        ...
    @overload
    def get_fs(
        self, 
        arg: int, 
        /, 
        refresh: bool = False, 
        id_to_readdir: None | int | dict[int, dict[int, MutableMapping]] = None, 
    ) -> P115ZipFileSystem:
        ...
    @overload
    def get_fs(
        self, 
        arg: str, 
        /, 
        refresh: bool = False, 
        id_to_readdir: None | int | dict[int, dict[int, MutableMapping]] = None, 
    ) -> P115ShareFileSystem:
        ...
    def get_fs(
        self, 
        arg: None | int | str = None, 
        /, 
        refresh: bool = False, 
        id_to_readdir: None | int | dict[int, dict[int, MutableMapping]] = None, 
    ) -> P115FileSystemBase:
        if arg is None:
            return P115FileSystem(self, refresh=refresh, id_to_readdir=id_to_readdir)
        elif isinstance(arg, int):
            return P115ZipFileSystem(self, self.to_pickcode(arg), refresh=refresh, id_to_readdir=id_to_readdir)
        else:
            return P115ShareFileSystem(self, arg, refresh=refresh, id_to_readdir=id_to_readdir)


with temp_globals():
    CRE_CLIENT_API_search: Final = re_compile(r"^ +((?:GET|POST|PUT|DELETE|PATCH) .*)", MULTILINE).search
    for name in dir(P115Client):
        method = getattr(P115Client, name)
        if not (callable(method) and method.__doc__):
            continue
        match = CRE_CLIENT_API_search(method.__doc__)
        if match is not None:
            api = match[1]
            name = "P115Client." + name
            CLIENT_METHOD_API_MAP[name] = api
            try:
                CLIENT_API_METHODS_MAP[api].append(name)
            except KeyError:
                CLIENT_API_METHODS_MAP[api] = [name]


from .fs import P115FileSystemBase, P115FileSystem, P115ShareFileSystem, P115ZipFileSystem

# TODO: 支持对接口调用进行频率统计，默认就会开启，配置项目：1. 允许记录多少条或者多大时间窗口，默认记录最近 10 条（无限时间窗口） 2. 可以设置一个 key 函数，默认用 (url, method) 为 key 3. 数据和统计由单独的对象来承载，就行 headers 和 cookies 属性那样，可以被随意查看，这个对象由各种配置项目，可以随意修改，client初始化时候支持传入此对象 4. 可以修改时间窗口和数量限制 5. 可以获取数据，就像字典一样使用 dict[key, list[timestamp]] 6. 有一些做好的统计方法，你也可以自己来执行统计 7. 即使有些历史数据被移除，有些统计方法可以持续更新，覆盖从早到现在的所有数据，比如 加总、计数
# TODO: 有些方法需要被移走，例如 open, hash, ed2k 等，这些方法完全可以单独使用，没必要专门给 client 提供，client 类必须是必要的，非必要的方法一律移除
# TODO: 增加一个 __eq__ 方法，只要 user_id 相等即可
# TODO: 删除、复制、移动、还原似乎是不可同时进行的？
