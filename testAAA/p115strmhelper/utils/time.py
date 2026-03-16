__all__ = ["TimeUtils"]


from datetime import datetime
from email.utils import formatdate
from time import time


class TimeUtils:
    """
    时间 工具类
    """

    @staticmethod
    def timestamp2isoformat(ts: None | float | datetime = None, /) -> str:
        if ts is None:
            dt = datetime.now()
        elif isinstance(ts, datetime):
            dt = ts
        else:
            dt = datetime.fromtimestamp(ts)
        return dt.astimezone().isoformat()

    @staticmethod
    def timestamp2gmtformat(ts: None | float | datetime = None, /) -> str:
        if ts is None:
            ts = time()
        elif isinstance(ts, datetime):
            ts = ts.timestamp()
        return formatdate(ts, usegmt=True)
