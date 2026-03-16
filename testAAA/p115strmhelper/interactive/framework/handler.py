from typing import Dict, List

from app.log import logger

from .callbacks import Action
from .registry import command_registry
from .schemas import TSession


class BaseActionHandler:
    """
    处理器基类
    """

    def process(self, session: TSession, action: Action) -> List[Dict]:
        """
        处理动作
        """
        command_def = command_registry.get_by_name(action.command)
        if not command_def:
            logger.warning(f"未找到命令 '{action.command}' 的处理器。")
            return []
        try:
            handler_method = getattr(self, command_def.handler_name)
            return handler_method(session, action) or []
        except Exception as e:
            logger.error(f"处理命令 '{action.command}' 时发生错误: {e}", exc_info=True)
            return [{"type": "error_message", "text": "处理请求时发生内部错误。"}]
