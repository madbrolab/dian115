from collections import deque
from typing import Dict


class LifeTasksQueue:
    """
    生活事件等待队列
    """

    def __init__(self):
        self.data = deque()
        self.key = deque()

    def add(self, item: Dict) -> None:
        self.data.append(item)
        self.key.append(item["id"])

    def pop(self) -> Dict:
        self.key.popleft()
        return self.data.popleft()

    def exist(self, item: Dict) -> bool:
        return item["id"] in self.key and self.key[0] == item["id"]

    def inq(self, item: Dict) -> bool:
        return item["id"] in self.key

    def time_done(self, timestamp: int | float) -> bool:
        return timestamp >= self.data[0]["update_time"]

    def clear(self) -> None:
        self.data.clear()
        self.key.clear()
