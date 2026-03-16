from threading import Lock
from time import monotonic, sleep
from typing import Dict, List, Any

IOS_UA = (
    "Mozilla/5.0 (iPhone; CPU iPhone OS 17_5_1 like Mac OS X) "
    "AppleWebKit/605.1.15 (KHTML, like Gecko) Mobile/15E148 115wangpan_ios/36.2.20"
)


def get_ios_ua_app(app: bool = True) -> Dict[str, str]:
    """
    获取 IOS 设备的 header（UA）和 APP
    """
    kwargs: Dict[str, Any] = {
        "headers": {"user-agent": IOS_UA},
    }
    if app:
        kwargs["app"] = "ios"
    return kwargs


class RateLimiter:
    """
    速率限制器，基于滑动时间窗口的流控工具类
    """

    def __init__(self, max_calls: int = 2, time_window: float = 1.0, name: str = ""):
        """
        初始化速率限制器

        :param max_calls: 时间窗口内最大调用次数，默认2次
        :param time_window: 时间窗口大小（秒），默认1.0秒
        :param name: 限流器名称，用于日志输出，默认为空
        """
        self.max_calls = max_calls
        self.time_window = time_window
        self.name = name
        self._lock = Lock()
        self._call_times: List[float] = []

    def acquire(self):
        """
        获取调用许可，如果超过限制会阻塞等待直到满足条件
        """
        now = monotonic()
        with self._lock:
            self._call_times = [
                t for t in self._call_times if now - t < self.time_window
            ]

            if len(self._call_times) >= self.max_calls:
                oldest_call = min(self._call_times)
                wait_time = self.time_window - (now - oldest_call)
                if wait_time > 0:
                    sleep(wait_time)
                    now = monotonic()
                    self._call_times = [
                        t for t in self._call_times if now - t < self.time_window
                    ]
            self._call_times.append(now)
