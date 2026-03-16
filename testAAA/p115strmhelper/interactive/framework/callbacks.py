from dataclasses import dataclass
from typing import Tuple, Optional, Any

from app.log import logger


@dataclass
class Action:
    command: str
    view: Optional[str] = None
    value: Optional[Any] = None


def encode_action(session, action: Action, max_length: int = 64) -> str:
    """
    将 Action 编码
    :param session: 会话对象
    :param action: Action 对象
    :param max_length: 最大长度限制
    """
    from .registry import command_registry, view_registry

    command_def = command_registry.get_by_name(action.command)
    # 打印当前支持的全部命令
    # logger.debug(f"当前支持的命令: {command_registry._by_name.keys()}")
    # 打印当前支持的全部视图
    # logger.debug(f"当前支持的视图: {view_registry._by_name.keys()}")
    if not command_def:
        logger.warning(f"命令 '{action.command}' 未找到，无法编码。")
        return ""

    parts = [f"c:{command_def.code}"]
    if action.value is not None:
        parts.append(f"v:{action.value}")

    if action.view:
        view_def = view_registry.get_by_name(action.view)
        if view_def:
            parts.append(f"w:{view_def.code}")
        else:
            logger.warning(f"视图 '{action.view}' 未找到，无法编码。")
    # 组装回调数据
    action_str = "|".join(parts)

    callback_data = f"[PLUGIN]{session.plugin_id}|{session.session_id}|{action_str}"
    if len(callback_data.encode("utf-8")) > max_length:
        logger.warning(f"回调数据超长: {callback_data}")
    return callback_data


def decode_action(callback_text: str) -> Tuple[Optional[str], Optional[Action]]:
    """
    解码 Action
    :param callback_text: 回调文本
    """
    try:
        from .registry import command_registry, view_registry

        session_id, action_str = callback_text.split("|", 1)
        action_parts = {
            p.split(":", 1)[0]: p.split(":", 1)[1]
            for p in action_str.split("|")
            if ":" in p
        }

        cmd_code = action_parts.get("c")
        if not cmd_code:
            return session_id, None

        command_def = command_registry.get_by_code(cmd_code)
        if not command_def:
            return session_id, None

        view_name = None
        view_code = action_parts.get("w")
        view_def = view_registry.get_by_code(view_code) if view_code else None
        if view_def:
            view_name = view_def.name

        return session_id, Action(
            command=command_def.name, value=action_parts.get("v"), view=view_name
        )
    except Exception as e:
        logger.error(f"解码回调数据失败: '{callback_text}', 错误: {e}")
        return None, None
