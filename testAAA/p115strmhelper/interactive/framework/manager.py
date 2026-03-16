import hashlib
import threading
import time
from typing import Any, Dict, Optional, Type, Generic

from .schemas import TSession


class BaseSessionManager(Generic[TSession]):
    """
    Session 管理器的通用基类。
    """

    def __init__(self, session_class: Type[TSession]):
        """
        初始化 Session 管理器。
        :param session_class: 会话类，必须是 BaseSession 的子类。
        """
        self._sessions: Dict[str, TSession] = {}
        self._lock = threading.Lock()
        self.TIMEOUT_SECONDS = 600
        self.session_class = session_class

    def set_timeout(self, minutes: int):
        """
        设置会话超时时间（分钟）。
        """
        self.TIMEOUT_SECONDS = minutes * 60

    @staticmethod
    def _generate_session_id(event_data: Dict[str, Any]) -> str:
        """
        为每个用户在每个聊天中生成一个唯一的、简短的会话ID。
        :param event_data: 字典，包含事件数据，必须包含 'channel', 'source', 'userid' 或 'user' 字段。
        """
        channel = event_data.get("channel")
        source = event_data.get("source")
        userid = event_data.get("userid") or event_data.get("user")
        if not userid:
            raise ValueError("需要 userid 或 user 字段来生成会话 ID")
        original_id = f"{channel}:{source}:{userid}"
        return hashlib.md5(original_id.encode()).hexdigest()[:8]

    def get_or_create(self, event_data: Dict[str, Any], plugin_id: str) -> TSession:
        """
        获取或创建一个会话。
        """
        session_id = self._generate_session_id(event_data)
        with self._lock:
            session = self._sessions.get(session_id)
            if not session or (
                time.time() - session.last_active > self.TIMEOUT_SECONDS
            ):
                session = self.session_class(session_id=session_id, plugin_id=plugin_id)
                self._sessions[session_id] = session
            if hasattr(session, "update_message_context"):
                session.update_message_context(event_data)
            else:
                session.update_activity()
            session.plugin_id = plugin_id
            return session

    def get(self, session_id: str) -> Optional[TSession]:
        """
        根据会话 ID 获取会话，如果会话存在且未超时，则返回该会话。
        :param session_id: 会话 ID
        """
        with self._lock:
            session = self._sessions.get(session_id)
            if session and (time.time() - session.last_active <= self.TIMEOUT_SECONDS):
                session.update_activity()
                return session
            return None

    def end(self, session_id: str):
        """
        结束会话，移除会话记录。
        :param session_id: 会话 ID
        """
        with self._lock:
            self._sessions.pop(session_id, None)

    def cleanup(self):
        """
        清理过期的会话。
        """
        now = time.time()
        with self._lock:
            # 找出所有过期的会话
            expired_keys = [
                sid
                for sid, s in self._sessions.items()
                if now - s.last_active > self.TIMEOUT_SECONDS
            ]
            for key in expired_keys:
                self._sessions.pop(key, None)
