from dataclasses import dataclass
from typing import Dict, Callable

from app.log import logger


@dataclass
class CommandDefinition:
    """
    命令的定义数据类，用于注册和查找命令。
    """

    # 命令的名称
    name: str
    # 命令的短码
    code: str
    # 绑定的处理器方法名，自动从装饰器函数名获取
    handler_name: str


class CommandRegistry:
    """
    一个独立的命令注册表，用于注册和查找命令。
    """

    def __init__(self):
        """
        初始化命令注册表。
        """
        self._by_name: Dict[str, CommandDefinition] = {}
        self._by_code: Dict[str, CommandDefinition] = {}

    def command(self, name: str, code: str):
        """
        命令装饰器，用于注册命令。
        :param name: 命令名称
        :param code: 命令短码
        """

        def decorator(func: Callable):
            """
            命令装饰器函数，用于注册命令。
            :param func: 处理器函数
            """
            handler_name = func.__name__
            if name in self._by_name:
                raise ValueError(f"命令 '{name}' 已被注册。")
            if code in self._by_code:
                raise ValueError(f"命令短码 '{code}' 已被注册。")
            command_def = CommandDefinition(
                name=name, code=code, handler_name=handler_name
            )
            logger.debug(f"注册 command 命令: {name} ({code}) -> {handler_name}")
            self._by_name[name] = command_def
            self._by_code[code] = command_def
            return func

        return decorator

    def get_by_name(self, name: str) -> CommandDefinition | None:
        """
        根据命令名称获取命令定义。
        :param name: 命令名称
        """
        cmd_def = self._by_name.get(name)
        if cmd_def:
            logger.debug(f"获取命令定义: {name} -> {cmd_def.handler_name}")
        else:
            logger.warning(f"未找到命令定义: {name}")
        return cmd_def

    def get_by_code(self, code: str) -> CommandDefinition | None:
        """
        根据命令短码获取命令定义。
        :param code: 命令短码
        """
        cmd_def = self._by_code.get(code)
        if cmd_def:
            logger.debug(f"获取命令定义: {code} -> {cmd_def.handler_name}")
        else:
            logger.warning(f"未找到命令定义: {code}")
        return cmd_def

    def clear(self):
        """
        清空所有已注册的命令。
        """
        self._by_name.clear()
        self._by_code.clear()
        logger.debug("已清空所有注册的命令。")


@dataclass
class ViewDefinition:
    """
    视图的定义数据类，用于注册和查找视图。
    """

    # 视图的名称
    name: str
    # 视图的短码
    code: str
    # 绑定的渲染器方法名，自动从装饰器函数名获取
    renderer_name: str


class ViewRegistry:
    """
    一个独立的视图注册表，用于注册和查找视图。
    """

    def __init__(self):
        """
        初始化视图注册表。
        """
        self._by_name: Dict[str, ViewDefinition] = {}
        self._by_code: Dict[str, ViewDefinition] = {}

    def view(self, name: str, code: str):
        """
        视图装饰器，用于注册视图。
        :param name: 视图名称
        :param code: 视图短码
        """

        def decorator(func: Callable):
            """
            视图装饰器函数，用于注册视图。
            :param func: 渲染器函数
            """
            renderer_name = func.__name__
            if name in self._by_name:
                raise ValueError(f"视图 '{name}' 已被注册。")
            if code in self._by_code:
                raise ValueError(f"视图短码 '{code}' 已被注册。")
            view_def = ViewDefinition(name=name, code=code, renderer_name=renderer_name)
            logger.debug(f"注册 view 视窗: {name} ({code}) -> {renderer_name}")
            self._by_name[name] = view_def
            self._by_code[code] = view_def
            return func

        return decorator

    def get_by_name(self, name: str) -> ViewDefinition | None:
        """
        根据视图名称获取视图定义。
        :param name: 视图名称
        """
        view_def = self._by_name.get(name)
        if view_def:
            logger.debug(f"获取视图定义: {name} -> {view_def.renderer_name}")
        else:
            logger.warning(f"未找到视图定义: {name}")
        return view_def

    def get_by_code(self, code: str) -> ViewDefinition | None:
        """
        根据视图短码获取视图定义。
        :param code: 视图短码
        """
        view_def = self._by_code.get(code)
        if view_def:
            logger.debug(f"获取视图定义: {code} -> {view_def.renderer_name}")
        else:
            logger.warning(f"未找到视图定义: {code}")
        return view_def

    def clear(self):
        """
        清空所有已注册的命令。
        """
        self._by_name.clear()
        self._by_code.clear()
        logger.debug("已清空所有注册的视图。")


# # 创建全局的命令和视图注册表实例
command_registry = CommandRegistry()
view_registry = ViewRegistry()
