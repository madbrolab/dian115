from re import search

__all__ = [
    "PanPathNotFound",
    "U115NoCheckInException",
    "PanDataNotInDb",
    "CanNotFindPathToCid",
    "PathNotInKey",
    "DownloadValidationFail",
    "FileItemKeyMiss",
    "ItertreeInternalError",
    "NotifyExceptionFormatter",
]


class NotifyExceptionFormatter:
    """
    将异常格式化为适合通知展示的简短描述
    """

    @staticmethod
    def format_exception_for_notify(exc: BaseException, max_length: int = 400) -> str:
        """
        将异常格式化为适合通知展示的简短描述

        :param exc: 异常对象
        :param max_length: 最大长度
        :return: 格式化后的异常描述
        """
        e = exc

        code = getattr(e, "code", None) or getattr(e, "status_code", None)
        reason = getattr(e, "reason", None)
        message = getattr(e, "message", None)
        if code is not None or reason or message:
            code_s = f"HTTP {code}" if code is not None else "请求错误"
            reason_s = str(reason).strip() if reason else ""
            msg_s = str(message).strip() if message else ""
            if reason_s and msg_s:
                return f"{code_s}（{reason_s}）：{msg_s}"
            if reason_s:
                return f"{code_s}（{reason_s}）"
            if msg_s:
                return f"{code_s}：{msg_s}"
            return code_s

        s = str(e).strip()
        if not s:
            return type(e).__name__

        code_m = search(r"\bcode=(\d+)", s)
        reason_m = search(r"reason='([^']*)'", s)
        msg_m = search(r"message='([^']*)'", s)
        if code_m or reason_m or msg_m:
            code = code_m.group(1) if code_m else None
            reason = reason_m.group(1) if reason_m else ""
            message = msg_m.group(1) if msg_m else ""
            code_s = f"HTTP {code}" if code else "请求错误"
            if reason and message:
                return f"{code_s}（{reason}）：{message}"
            if reason:
                return f"{code_s}（{reason}）"
            if message:
                return f"{code_s}：{message}"
            return code_s

        for sep in ("response_body=", "headers=", "request=", "response="):
            if sep in s:
                s = s.split(sep)[0].strip()
        if not s:
            return "网络或接口返回异常，请查看日志"

        lines = [line.strip() for line in s.splitlines() if line.strip()]
        if lines:
            for line in reversed(lines):
                if line.startswith("File ") or line.startswith("  File "):
                    continue
                if ":" in line or line.startswith(type(e).__name__):
                    s = line
                    break
            else:
                s = lines[-1]

        type_name = type(e).__name__
        if not s.startswith(type_name) and not s.startswith(type_name + ":"):
            if e.args and str(e.args[0]).strip():
                msg = str(e.args[0]).strip()
                if len(msg) <= max_length:
                    s = f"{type_name}: {msg}"
                else:
                    s = f"{type_name}: {msg[: max_length - len(type_name) - 2]}…"
            else:
                s = type_name if not s else s

        return s[:max_length].rstrip() if len(s) > max_length else s


class PanPathNotFound(FileNotFoundError):
    """
    网盘路径不存在
    """


class U115NoCheckInException(Exception):
    """
    115 Open 未登录
    """


class PanDataNotInDb(Exception):
    """
    网盘数据未在数据库内
    """


class CanNotFindPathToCid(Exception):
    """
    无法找到路径对应的 cid
    """


class PathNotInKey(ValueError):
    """
    键中不包含 Path 项
    """


class DownloadValidationFail(Exception):
    """
    下载后的文件未能通过验证
    """

    pass


class FileItemKeyMiss(Exception):
    """
    文件数据不完整
    """

    pass


class ItertreeInternalError(Exception):
    """
    网盘目录树迭代（__itertree）内部错误
    """

    pass
