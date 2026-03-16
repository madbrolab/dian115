import time
from copy import deepcopy
from dataclasses import dataclass, field
from typing import Any, Dict, Optional, TypeVar

from app.schemas.types import MessageChannel


@dataclass
class BaseView:
    """
    视图模型的通用基类。
    """

    # 视图名称
    name: Optional[str] = None
    # 上一个视图名称
    previous_view: Optional[str] = None
    # 页码
    page: int = 0
    # 总页数
    total_pages: int = 0
    # 刷新
    refresh: bool = False


@dataclass
class BaseMessage:
    """
    消息模型的通用基类。
    """

    # 消息类型
    channel: Optional[MessageChannel] = None
    # 来源名
    source: Optional[str] = None
    # 用户 ID
    userid: Optional[int] = None
    # 用户名
    username: Optional[str] = None
    # 原始消息 ID
    original_message_id: Optional[int] = None
    # 原始聊天 ID
    original_chat_id: Optional[int] = None


@dataclass
class BaseBusiness:
    """
    业务模型的通用基类。
    """

    pass


@dataclass
class BaseSession:
    """
    Session 模型的通用基类。
    """

    # 会话 ID，用于唯一标识每个用户在每个聊天中的会话
    session_id: str
    # 插件 ID，用于标识当前会话所属的插件
    plugin_id: str
    # 默认视图名称（用于兜底）
    default_view: str = "start"

    # 会话的最后活动时间戳
    last_active: float = field(default_factory=time.time, init=False)
    # 历史记录，用于保存视图时的状态，如页码等
    history: Optional[Dict] = field(default_factory=dict)

    # 页面数据
    view: BaseView = field(default_factory=BaseView)
    # 业务数据
    business: BaseBusiness = field(default_factory=BaseBusiness)
    # 消息上下文，包含频道、来源、用户等信息
    message: BaseMessage = field(default_factory=BaseMessage)

    def get_delete_message_data(self) -> Dict[str, Any]:
        """
        获取删除消息的数据。
        """
        return {
            "channel": self.message.channel,
            "source": self.message.source,
            "message_id": self.message.original_message_id,
            "chat_id": self.message.original_chat_id,
        }

    def update_message_context(self, event_data: Dict[str, Any]):
        """
        更新消息上下文信息。
        :param event_data: 字典，包含事件数据，必须包含 'channel', 'source', 'userid' 或 'user' 字段。
        """
        self.message.channel = event_data.get("channel")
        self.message.source = event_data.get("source")
        self.message.userid = event_data.get("userid") or event_data.get("user")
        self.message.username = event_data.get("username") or event_data.get("user")
        self.message.original_message_id = event_data.get("original_message_id")
        self.message.original_chat_id = event_data.get("original_chat_id")
        self.message.original_message_text = event_data.get("text")
        self.update_activity()

    def update_activity(self):
        """
        更新会话的最后活动时间戳。
        """
        self.last_active = time.time()

    def go_to(self, view: str):
        """
        切换到指定的视图，并保存当前状态到历史记录。
        :param view: 要切换到的视图名称。
        """
        # 如果没有历史记录且当前视图是默认视图，则不进行任何操作，默认视图是初始化
        if not self.history and view == self.default_view:
            self.view.name = view
            return
        history_key = str(deepcopy(self.view.name))
        history_value = deepcopy(self.view)
        self.history.update({history_key: history_value})
        self.view.previous_view = self.view.name
        self.view.name = view
        self.view.page = 0
        self.view.total_pages = 0

    def go_back(self, view: Optional[str] = None):
        """
        返回到历史记录
        :param view: 要返回的视图名称。
        """
        if not view:
            view = self.view.previous_view or "start"

        history_view_data = self.history.get(view)

        if not history_view_data:
            # 如果没有指定视图或历史记录中没有该视图，则回到起始页
            view = self.default_view

        self.view.name = view

        if history_view_data:
            self.view = history_view_data

        # 强制刷新恢复成false
        if hasattr(self.view, "refresh"):
            self.view.refresh = False

    def page_next(self):
        """
        翻到下一页。
        """
        if self.view.total_pages > 0 and self.view.page < self.view.total_pages - 1:
            self.view.page += 1

    def page_prev(self):
        """
        翻到上一页。
        """
        if self.view.page > 0:
            self.view.page -= 1

    def refresh_view(self):
        """
        刷新当前视图。
        """
        self.view.refresh = True


TSession = TypeVar("TSession", bound=BaseSession)
