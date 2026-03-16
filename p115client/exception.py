#!/usr/bin/env python3
# encoding: utf-8

__all__ = [
    "P115Error", "P115Warning", "P115OSError", "P115AccessError", 
    "P115AuthenticationError", "P115BusyOSError", "P115DataError", 
    "P115OperationalError", "P115FileTooBig", "P115ExceededError", 
    "P115InvalidArgumentError", "P115NoSpaceError", "P115NotSupportedError", 
    "P115LoginError", "P115AccessTokenError", "P115OpenAppAuthLimitExceeded", 
    "error", "throw", "errno2error"
]

import warnings

from itertools import count
from collections.abc import Mapping
from functools import cached_property
from typing import Never

from errno2 import errno, errno2error as _errno2error


warnings.filterwarnings("always", category=UserWarning)
setattr(warnings, "formatwarning", lambda message, category, filename, lineno, line=None, _getid=count(1).__next__:
    f"\r\x1b[K\x1b[1;31;43m{category.__qualname__}\x1b[0m(\x1b[32m{_getid()}\x1b[0m) @ \x1b[3;4;34m{filename}\x1b[0m:\x1b[36m{lineno}\x1b[0m \x1b[5;31m➜\x1b[0m \x1b[1m{message}\x1b[0m\n"
)


class P115Error(Exception):
    """本模块的最基础异常类
    """


class P115Warning(P115Error, UserWarning):
    """本模块的最基础警示类
    """


class P115OSError(P115Error, OSError):
    """本模块的最基础输出输出异常类
    """
    def __getattr__(self, attr, /):
        try:
            return self[attr]
        except KeyError as e:
            raise AttributeError(attr) from e

    def __getitem__(self, key, /):
        message = self.message
        if isinstance(message, Mapping):
            return message[key]
        raise KeyError(key)

    @cached_property
    def message(self, /):
        if args := self.args:
            if len(args) >= 2 and isinstance(args[0], int):
                return args[1]
            return args[0]


class P115AuthenticationError(P115OSError):
    """当登录状态无效时抛出
    """


class P115BusyOSError(P115OSError):
    """当操作繁忙时抛出（115 网盘的复制、移动、删除、还原只允许最多一个操作进行中）
    """


class P115DataError(P115OSError):
    """当响应数据解析失败时抛出
    """


class P115OperationalError(P115OSError):
    """当接口使用方法错误时抛出，例如参数错误、空间不足、超出允许数量范围等
    """


class P115AccessError(P115OperationalError, PermissionError):
    """当不可访问时抛出，可能是文件被和谐了
    """


class P115FileTooBig(P115OperationalError, PermissionError):
    """文件过大
    """


class P115ExceededError(P115OperationalError, PermissionError):
    """超出允许数量范围
    """


class P115InvalidArgumentError(P115OperationalError, ValueError):
    """参数错误
    """


class P115NoSpaceError(P115OperationalError, PermissionError):
    """空间不足
    """


class P115NotSupportedError(P115OperationalError):
    """当调用不存在的接口或者接口不支持此操作时抛出
    """


class P115LoginError(P115AuthenticationError):
    """当登录失败时抛出
    """


class P115AccessTokenError(P115OSError, ValueError):
    """access_token 错误或者无效
    """


class P115OpenAppAuthLimitExceeded(P115AuthenticationError):
    """当授权应用数达到上限时抛出
    """


def error(*args, **kwds) -> BaseException:
    """构建异常

    .. tip::
        会根据传入的位置参数，做一些类型推断

        - 第 1 个位置参数，记作 `errcode`，大概是一个 `errno2.errno` 的枚举类型，不能成功推断则用 `errno2.errno.EIO`
        - 第 2 个位置参数（若第 1 个位置参数不满足上一条，则用此参数），记作 `exctype`，大概是一个 `P115Error` 类型或其子类型，不能成功推断则用 `P115OSError`

        假设剩余的所有没被提取的位置参数记作 `rargs`，最终构建的异常为 `exctype(errcode, *rargs, **kwds)`
    """
    if args and isinstance(args[0], errno):
        errcode = args[0]
        args = args[1:]
    else:
        errcode = errno.EIO
    if not (args and isinstance(args[0], type) and issubclass(args[0], BaseException)):
        args = errno2error.get(errcode, P115OSError), *args
    return errcode.error(*args, **kwds)


def throw(*args, **kwds) -> Never:
    """抛出异常

    .. tip::
        会根据传入的位置参数，做一些类型推断

        - 第 1 个位置参数，记作 `errcode`，大概是一个 `errno2.errno` 的枚举类型，不能成功推断则用 `errno2.errno.EIO`
        - 第 2 个位置参数（若第 1 个位置参数不满足上一条，则用此参数），记作 `exctype`，大概是一个 `P115Error` 类型或其子类型，不能成功推断则用 `P115OSError`

        假设剩余的所有没被提取的位置参数记作 `rargs`，最终抛出的异常为 `exctype(errcode, *rargs, **kwds)`
    """
    raise error(*args, **kwds)


#: errno 到的异常类的映射
errno2error: dict[errno, type[P115Error]] = {
    errno.EAUTH: P115AuthenticationError, 
    errno.EBUSY: P115BusyOSError, 
    errno.ENODATA: P115DataError, 
    errno.EACCES: P115AccessError, 
    errno.EFBIG: P115FileTooBig, 
    errno.ERANGE: P115ExceededError, 
    errno.EINVAL: P115InvalidArgumentError, 
    errno.ENOSPC: P115NoSpaceError, 
    errno.ENOTSUP: P115NotSupportedError, 
    errno.ENOSYS: P115NotSupportedError, 
}

_modns = globals()
for errcode, exctype in _errno2error.items():
    typename = "P115" + exctype.__name__
    if typename not in _modns:
        cls = _modns[typename] = type(typename, (P115OSError, exctype), {"__doc__": errcode.description})
        __all__.append(typename)
        errno2error[errcode] = cls


def __getattr__(attr: str, /) -> type[P115OSError]:
    raise AttributeError(attr)

