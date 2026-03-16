#!/usr/bin/env python3
# encoding: utf-8

__author__ = "ChenyangGao <https://chenyanggao.github.io>"
__all__ = [
    "parse_export_dir_as_dict_iter", "parse_export_dir_as_path_iter", 
    "parse_export_dir_as_patht_iter", "export_dir", "export_dir_result", 
    "export_dir_parse_iter", 
]
__doc__ = "这个模块提供了一些和导出目录树有关的函数"

from asyncio import sleep as async_sleep
from collections.abc import (
    AsyncIterable, AsyncIterator, Callable, Coroutine, Iterable, Iterator, 
)
from functools import partial
from io import BufferedReader, TextIOWrapper
from itertools import count
from os import PathLike
from re import compile as re_compile
from time import sleep, time
from typing import cast, overload, Any, Final, IO, Literal

from asynctools import ensure_async, ensure_aiter
from filewrap import AsyncBufferedReader, AsyncTextIOWrapper
from iterutils import (
    backgroud_loop, context, run_gen_step, run_gen_step_iter, 
    Yield, YieldFrom, 
)
from p115pickcode import to_id

from ..client import check_response, P115Client


CRE_TREE_PREFIX_match: Final = re_compile(r"^(?:\| )+\|-(.*)").match


@overload
def parse_export_dir_as_dict_iter(
    file: bytes | str | PathLike | Iterable[bytes | str], 
    /, 
    encoding: str = "utf-16", 
    close_file: bool = False, 
    *, 
    async_: Literal[False] = False, 
) -> Iterator[dict]:
    ...
@overload
def parse_export_dir_as_dict_iter(
    file: bytes | str | PathLike | Iterable[bytes | str] | AsyncIterable[bytes | str], 
    /, 
    encoding: str = "utf-16", 
    close_file: bool = False, 
    *, 
    async_: Literal[True], 
) -> AsyncIterator[dict]:
    ...
def parse_export_dir_as_dict_iter(
    file: bytes | str | PathLike | Iterable[bytes | str] | AsyncIterable[bytes | str], 
    /, 
    encoding: str = "utf-16", 
    close_file: bool = False, 
    *, 
    async_: Literal[False, True] = False, 
) -> Iterator[dict] | AsyncIterator[dict]:
    """解析 115 导出的目录树（可通过 P115Client.fs_export_dir 提交导出任务）

    :param file: 文件路径、打开的文件或者迭代器（每次返回一行）
    :param encoding: 字符编码，对字节数据使用，转换为字符串
    :param close_file: 结束（包括异常退出）时尝试关闭 `file`
    :param async_: 是否异步

    :return: 把每一行解析为一个字典，迭代返回，格式为

        .. code:: python

            {
                "key":        int, # 序号
                "parent_key": int, # 上级目录的序号
                "depth":      int, # 深度
                "name":       str, # 名字
            }
    """
    if isinstance(file, (bytes, str, PathLike)):
        file = open(file, encoding=encoding)
        close_file = True
    def gen_step():
        it = ensure_aiter(file, threaded=True) if async_ else file
        do_next: Callable = anext if async_ else next # type: ignore
        stack: list[dict] = [{"key": 0, "parent_key": 0, "depth": 0, "name": ""}]
        push = stack.append
        root = yield do_next(it, None)
        if not root:
            return
        try:
            depth = 0
            for i in count(1):
                line = yield do_next(it)
                if not isinstance(line, str):
                    line = str(line, encoding)
                m = CRE_TREE_PREFIX_match(line)
                if m is None:
                    stack[depth]["name"] += "\n" + line[:-1]
                    continue
                else:
                    yield Yield(stack[depth])
                name = m[1]
                depth = (len(line) - len(name)) // 2 - 1
                item = {
                    "key": i, 
                    "parent_key": stack[depth-1]["key"], 
                    "depth": depth, 
                    "name": name, 
                }
                try:
                    stack[depth] = item
                except IndexError:
                    push(item)
        except (StopIteration, StopAsyncIteration):
            if depth:
                yield Yield(stack[depth])
        finally:
            if close_file:
                if async_:
                    if callable(aclose := getattr(file, "aclose", None)):
                        yield aclose()
                    elif callable(close := getattr(file, "close", None)):
                        yield ensure_async(close, threaded=True)
                elif callable(close := getattr(file, "close", None)):
                    close()
    return run_gen_step_iter(gen_step, async_)


@overload
def parse_export_dir_as_path_iter(
    file: bytes | str | PathLike | Iterable[bytes | str], 
    /, 
    encoding: str = "utf-16", 
    escape: None | bool | Callable[[str], str] = True, 
    close_file: bool = False, 
    *, 
    async_: Literal[False] = False, 
) -> Iterator[str]:
    ...
@overload
def parse_export_dir_as_path_iter(
    file: bytes | str | PathLike | Iterable[bytes | str] | AsyncIterable[bytes | str], 
    /, 
    encoding: str = "utf-16", 
    escape: None | bool | Callable[[str], str] = True, 
    close_file: bool = False, 
    *, 
    async_: Literal[True], 
) -> AsyncIterator[str]:
    ...
def parse_export_dir_as_path_iter(
    file: bytes | str | PathLike | Iterable[bytes | str] | AsyncIterable[bytes | str], 
    /, 
    encoding: str = "utf-16", 
    escape: None | bool | Callable[[str], str] = True, 
    close_file: bool = False, 
    *, 
    async_: Literal[False, True] = False, 
) -> Iterator[str] | AsyncIterator[str]:
    """解析 115 导出的目录树（可通过 P115Client.fs_export_dir 提交导出任务）

    :param file: 文件路径、打开的文件或者迭代器（每次返回一行）
    :param encoding: 字符编码，对字节数据使用，转换为字符串
    :param escape: 对文件名进行转义

        - 如果为 None，则不处理；否则，这个函数用来对文件名中某些符号进行转义，例如 "/" 等
        - 如果为 True，则使用 `posixpatht.escape`，会对文件名中 "/"，或单独出现的 "." 和 ".." 用 "\\" 进行转义
        - 如果为 False，则使用 `posix_escape_name` 函数对名字进行转义，会把文件名中的 "/" 转换为 "|"
        - 如果为 Callable，则用你所提供的调用，以或者转义后的名字

    :param close_file: 结束（包括异常退出）时尝试关闭 `file`
    :param async_: 是否异步

    :return: 把每一行解析为一个路径，并逐次迭代返回
    """
    if isinstance(file, (bytes, str, PathLike)):
        file = open(file, encoding=encoding)
        close_file = True
    if isinstance(escape, bool):
        if escape:
            from posixpatht import escape
        else:
            from p115client.util import posix_escape_name as escape
    escape = cast(None | Callable[[str], str], escape)
    def gen_step():
        it = ensure_aiter(file, threaded=True) if async_ else file
        do_next: Callable = anext if async_ else next # type: ignore
        root = yield do_next(it, None)
        if not root:
            return
        if not isinstance(root, str):
            root = str(root, encoding)
        root = root.removesuffix("\n")[3:]
        if root == "根目录":
            stack = [""]
            root = "/"
        else:
            if escape is not None:
                root = escape(root)
            root = "/" + root
            stack = [root]
        push = stack.append
        try:
            depth = 0
            while True:
                line = yield do_next(it)
                if not isinstance(line, str):
                    line = str(line, encoding)
                m = CRE_TREE_PREFIX_match(line)
                if m is None:
                    stack[depth] += "\n" + line[:-1]
                    continue
                elif depth:
                    yield Yield(stack[depth])
                else:
                    yield Yield(root)
                name = m[1]
                depth = (len(line) - len(name)) // 2 - 1
                if escape is not None:
                    name = escape(name)
                path = stack[depth-1] + "/" + name
                try:
                    stack[depth] = path
                except IndexError:
                    push(path)
        except (StopIteration, StopAsyncIteration):
            if depth:
                yield Yield(stack[depth])
        finally:
            if close_file:
                if async_:
                    if callable(aclose := getattr(file, "aclose", None)):
                        yield aclose()
                    elif callable(close := getattr(file, "close", None)):
                        yield ensure_async(close, threaded=True)
                elif callable(close := getattr(file, "close", None)):
                    close()
    return run_gen_step_iter(gen_step, async_)


@overload
def parse_export_dir_as_patht_iter(
    file: bytes | str | PathLike | Iterable[bytes | str], 
    /, 
    encoding: str = "utf-16", 
    close_file: bool = False, 
    *, 
    async_: Literal[False] = False, 
) -> Iterator[list[str]]:
    ...
@overload
def parse_export_dir_as_patht_iter(
    file: bytes | str | PathLike | Iterable[bytes | str] | AsyncIterable[bytes | str], 
    /, 
    encoding: str = "utf-16", 
    close_file: bool = False, 
    *, 
    async_: Literal[True], 
) -> AsyncIterator[list[str]]:
    ...
def parse_export_dir_as_patht_iter(
    file: bytes | str | PathLike | Iterable[bytes | str] | AsyncIterable[bytes | str], 
    /, 
    encoding: str = "utf-16", 
    close_file: bool = False, 
    *, 
    async_: Literal[False, True] = False, 
) -> Iterator[list[str]] | AsyncIterator[list[str]]:
    """解析 115 导出的目录树（可通过 P115Client.fs_export_dir 提交导出任务）

    :param file: 文件路径、打开的文件或者迭代器（每次返回一行）
    :param encoding: 字符编码，对字节数据使用，转换为字符串
    :param close_file: 结束（包括异常退出）时尝试关闭 `file`
    :param async_: 是否异步

    :return: 把每一行解析为一个名字列表，并逐次迭代返回
    """
    if isinstance(file, (bytes, str, PathLike)):
        file = open(file, encoding=encoding)
        close_file = True
    def gen_step():
        it = ensure_aiter(file, threaded=True) if async_ else file
        do_next: Callable = anext if async_ else next # type: ignore
        root = yield do_next(it, None)
        if not root:
            return
        if not isinstance(root, str):
            root = str(root, encoding)
        root = root.removesuffix("\n")[3:]
        stack = [""]
        from_top_root = root == "根目录"
        if not from_top_root:
            stack.append(root)
        push = stack.append
        try:
            depth = len(stack) - 1
            while True:
                line = yield do_next(it)
                if not isinstance(line, str):
                    line = str(line, encoding)
                m = CRE_TREE_PREFIX_match(line)
                if m is None:
                    stack[depth] += "\n" + line[:-1]
                    continue
                else:
                    yield Yield(stack[:depth+1])
                name = m[1]
                depth = (len(line) - len(name)) // 2 - from_top_root
                try:
                    stack[depth] = name
                except IndexError:
                    push(name)
        except (StopIteration, StopAsyncIteration):
            if depth:
                yield Yield(stack[:depth+1])
        finally:
            if close_file:
                if async_:
                    if callable(aclose := getattr(file, "aclose", None)):
                        yield aclose()
                    elif callable(close := getattr(file, "close", None)):
                        yield ensure_async(close, threaded=True)
                elif callable(close := getattr(file, "close", None)):
                    close()
    return run_gen_step_iter(gen_step, async_)


@overload
def export_dir(
    client: str | PathLike | P115Client, 
    export_file_ids: int | str | Iterable[int | str], 
    target_pid: int | str = 0, 
    layer_limit: int = 0, 
    *, 
    async_: Literal[False] = False, 
    **request_kwargs, 
) -> int:
    ...
@overload
def export_dir(
    client: str | PathLike | P115Client, 
    export_file_ids: int | str | Iterable[int | str], 
    target_pid: int | str = 0, 
    layer_limit: int = 0, 
    *, 
    async_: Literal[True], 
    **request_kwargs, 
) -> Coroutine[Any, Any, int]:
    ...
def export_dir(
    client: str | PathLike | P115Client, 
    export_file_ids: int | str | Iterable[int | str], 
    target_pid: int | str = 0, 
    layer_limit: int = 0, 
    *, 
    async_: Literal[False, True] = False, 
    **request_kwargs, 
) -> int | Coroutine[Any, Any, int]:
    """导出目录树

    :param client: 115 客户端或 cookies
    :param export_file_ids: 待导出的目录 id 或 pickcode
    :param target_pid: 导出到的目标目录 id 或 pickcode
    :param layer_limit: 层级深度，小于等于 0 时不限
    :param async_: 是否异步
    :param request_kwargs: 其它请求参数

    :return: 返回任务 id，可用 `P115Client.fs_export_dir_status` 查询进度
    """
    if not isinstance(client, P115Client):
        client = P115Client(client, check_for_relogin=True)
    def gen_step():
        nonlocal export_file_ids, target_pid
        if isinstance(export_file_ids, int):
            pass
        elif isinstance(export_file_ids, str):
            if "," not in export_file_ids:
                export_file_ids = to_id(export_file_ids)
        else:
            export_file_ids = ",".join(str(to_id(eid)) for eid in export_file_ids)
        target_pid = to_id(target_pid)
        payload = {"file_ids": export_file_ids, "target": f"U_0_{target_pid}"}
        if layer_limit > 0:
            payload["layer_limit"] = layer_limit
        resp = yield client.fs_export_dir(payload, async_=async_, **request_kwargs)
        return check_response(resp)["data"]["export_id"]
    return run_gen_step(gen_step, async_)


@overload
def export_dir_result(
    client: str | PathLike | P115Client, 
    export_id: int | str, 
    timeout: None | int | float = None, 
    check_interval: int | float = 1, 
    *, 
    async_: Literal[False] = False, 
    **request_kwargs, 
) -> dict:
    ...
@overload
def export_dir_result(
    client: str | PathLike | P115Client, 
    export_id: int | str, 
    timeout: None | int | float = None, 
    check_interval: int | float = 1, 
    *, 
    async_: Literal[True], 
    **request_kwargs, 
) -> Coroutine[Any, Any, dict]:
    ...
def export_dir_result(
    client: str | PathLike | P115Client, 
    export_id: int | str, 
    timeout: None | int | float = None, 
    check_interval: int | float = 1, 
    *, 
    async_: Literal[False, True] = False, 
    **request_kwargs, 
) -> dict | Coroutine[Any, Any, dict]:
    """获取导出目录树的结果

    .. attention::
        如果指定超时时间为正数，则会在过期时抛出 TimeoutError，但这并不会取消远程正在执行的任务，而 115 同时只允许运行一个导出目录树的任务，所以如果要开始下一个导出任务，还需要此任务完成或者被 115 自动超时取消

    :param client: 115 客户端或 cookies
    :param export_id: 任务 id，由 `P115Client.fs_export_dir` 接口调用产生
    :param timeout: 超时秒数，如果为 None 或 小于等于 0，则相当于 float("inf")，即永不超时
    :param check_interval: 两次轮询之间的等待秒数，如果 <= 0，则不等待
    :param async_: 是否异步
    :param request_kwargs: 其它请求参数

    :return: 接口返回结果，格式为

        .. code:: python

            {
                "export_id": str, # 任务 id
                "file_id":   str, # 导出文件的 id
                "file_name": str, # 导出文件的名字
                "pick_code": str  # 导出文件的提取码
            }
    """
    if not isinstance(client, P115Client):
        client = P115Client(client, check_for_relogin=True)
    if check_interval < 0:
        check_interval = 0
    def gen_step():
        nonlocal timeout
        if timeout is None or timeout <= 0:
            timeout = float("inf")
        do_sleep: Callable = async_sleep if async_ else sleep # type: ignore
        expired_t = time() + timeout
        while True:
            resp = yield client.fs_export_dir_status(
                export_id, 
                async_=async_, 
                **request_kwargs, 
            )
            if data := check_response(resp)["data"]:
                return data
            remaining_seconds = expired_t - time()
            if remaining_seconds <= 0:
                raise TimeoutError(export_id)
            if check_interval:
                yield do_sleep(min(check_interval, remaining_seconds))
    return run_gen_step(gen_step, async_)


@overload
def export_dir_parse_iter(
    client: str | PathLike | P115Client, 
    export_file_ids: int | str | Iterable[int | str] = 0, 
    export_id: int | str = 0, 
    target_pid: int | str = 0, 
    layer_limit: int = 0, 
    parse_iter: None | Callable[[IO[bytes]], Iterator] = None, 
    delete: bool = True, 
    timeout: None | int | float = None, 
    check_interval: int | float = 1, 
    show_clock: bool | Callable[[], Any] = False, 
    clock_interval: int | float = 0.05, 
    *, 
    async_: Literal[False] = False, 
    **request_kwargs, 
) -> Iterator:
    ...
@overload
def export_dir_parse_iter(
    client: str | PathLike | P115Client, 
    export_file_ids: int | str | Iterable[int | str] = 0, 
    export_id: int | str = 0, 
    target_pid: int | str = 0, 
    layer_limit: int = 0, 
    parse_iter: None | Callable[[IO[bytes]], AsyncIterator] = None, 
    delete: bool = True, 
    timeout: None | int | float = None, 
    check_interval: int | float = 1, 
    show_clock: bool | Callable[[], Any] = False, 
    clock_interval: int | float = 0.05, 
    *, 
    async_: Literal[True], 
    **request_kwargs, 
) -> AsyncIterator:
    ...
def export_dir_parse_iter(
    client: str | PathLike | P115Client, 
    export_file_ids: int | str | Iterable[int | str] = 0, 
    export_id: int | str = 0, 
    target_pid: int | str = 0, 
    layer_limit: int = 0, 
    parse_iter: None | Callable[[IO[bytes]], Iterator] | Callable[[IO[bytes]], AsyncIterator] = None, 
    delete: bool = True, 
    timeout: None | int | float = None, 
    check_interval: int | float = 1, 
    show_clock: bool | Callable[[], Any] = False, 
    clock_interval: int | float = 0.05, 
    *, 
    async_: Literal[False, True] = False, 
    **request_kwargs, 
) -> Iterator | AsyncIterator:
    """导出目录树到文件，读取文件并解析后返回迭代器，关闭后自动删除导出的文件

    :param client: 115 客户端或 cookies
    :param export_file_ids: 待导出的目录 id、pickcode 或 路径（如果有多个，需传入可迭代对象）
    :param export_id: 优先级高于 `export_file_ids`，之前提交的 `export_dir` 任务的 id，如果是 str，则视为导出的目录树文件的提取码（因此无需导出）
    :param target_pid: 导出到的目标目录 id 或 pickcode
    :param layer_limit: 层级深度，小于等于 0 时不限
    :param parse_iter: 解析打开的二进制文件，返回可迭代对象
    :param delete: 最终删除目录树文件（如果 export_id 为 str（即提取码），则这个值不生效，必不删除）
    :param timeout: 导出任务的超时秒数，如果为 None 或 小于等于 0，则相当于 float("inf")，即永不超时
    :param check_interval: 导出任务的状态，两次轮询之间的等待秒数，如果 <= 0，则不等待
    :param show_clock: 是否在等待导出目录树时，显示时钟。如果为 True，则显示默认的时钟，如果为 Callable，则作为自定义时钟进行调用（无参数）
    :param clock_interval: 更新时钟的时间间隔
    :param async_: 是否异步
    :param request_kwargs: 其它请求参数

    :return: 解析导出文件的迭代器
    """
    if not isinstance(client, P115Client):
        client = P115Client(client, check_for_relogin=True)
    if parse_iter is None:
        if async_:
            parse_iter = partial(parse_export_dir_as_path_iter, async_=True)
        else:
            parse_iter = parse_export_dir_as_path_iter
    get_url = client.download_url
    def gen_step():
        nonlocal export_id, delete
        if not export_id:
            export_id = yield export_dir(
                client, 
                export_file_ids=export_file_ids, 
                target_pid=target_pid, 
                layer_limit=layer_limit, 
                async_=async_, 
                **request_kwargs, 
            )
        if isinstance(export_id, int):
            if not show_clock:
                result: dict = yield export_dir_result(
                    client, 
                    export_id, 
                    timeout=timeout, 
                    check_interval=check_interval, 
                    async_=async_, 
                    **request_kwargs, 
                )
            else:
                result = yield context(
                    lambda *_: export_dir_result(
                        client, 
                        export_id, 
                        timeout=timeout, 
                        check_interval=check_interval, 
                        async_=async_, 
                        **request_kwargs, 
                    ), 
                    backgroud_loop(
                        None if show_clock is True else show_clock, 
                        interval=clock_interval, 
                        async_=async_, # type: ignore
                    ), 
                    async_=async_, # type: ignore
                )
            pickcode = result["pick_code"]
        else:
            pickcode = export_id
            delete = False
        try:
            try:
                url: str = yield get_url(
                    pickcode, 
                    use_web_api=True, 
                    async_=async_, 
                    **request_kwargs, 
                )
            except OSError:
                url = yield get_url(
                    pickcode, 
                    async_=async_, 
                    **request_kwargs, 
                )
            file = client.open(url, async_=async_) # type: ignore
            try:
                if async_:
                    file_wrapper: IO = AsyncTextIOWrapper(AsyncBufferedReader(file), encoding="utf-16", newline="\n")
                else:
                    file_wrapper = TextIOWrapper(BufferedReader(file), encoding="utf-16", newline="\n")
                yield YieldFrom(parse_iter(file_wrapper)) # type: ignore
            finally:
                if async_:
                    if callable(aclose := getattr(file, "aclose", None)):
                        yield aclose()
                    elif callable(close := getattr(file, "close", None)):
                        yield ensure_async(close, threaded=True)
                elif callable(close := getattr(file, "close", None)):
                    close()
        finally:
            if delete:
                yield client.fs_delete(
                    cast(str, result["file_id"]), 
                    async_=async_, # type: ignore
                    **request_kwargs, 
                )
    return run_gen_step_iter(gen_step, async_)

