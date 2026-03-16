"""
MCP 工具定义与执行：包装插件 Api 的 tools + 非 Api 暴露的 INTERNAL_TOOLS，同步调用用 to_thread
"""

from asyncio import to_thread
from typing import Any, Dict, List

from orjson import dumps as orjson_dumps

from ..helper.clean import Cleaner
from ..schemas.browse import BrowseDirParams
from ..schemas.fuse import FuseMountPayload
from ..schemas.offline import AddOfflineTaskPayload, OfflineTasksPayload
from ..schemas.strm_api import ManualTransferPayload

# 工具定义列表：每项 {"def": { name, description, inputSchema } }，handler 在 run_tool 的 handlers 中
TOOLS: List[Dict[str, Any]] = []

# 非 Api 暴露的 tools：不经过 api.py，直接依赖 servicer，每项 {"def": {...}, "handler": async (servicer, arguments) -> Any}
INTERNAL_TOOLS: List[Dict[str, Any]] = []


def _dump(obj: Any) -> str:
    """
    将对象序列化为 JSON 字符串。

    :param obj: 支持 model_dump()、dict() 或普通可序列化对象。
    :return: UTF-8 JSON 字符串。
    """
    if hasattr(obj, "model_dump"):
        return orjson_dumps(obj.model_dump(), default=str).decode()
    if hasattr(obj, "dict"):
        return orjson_dumps(obj.dict(), default=str).decode()
    return orjson_dumps(obj, default=str).decode()


async def run_tool(
    api: Any, servicer: Any, name: str, arguments: Dict[str, Any]
) -> str:
    """
    根据 name 调用对应 handler（Api 或 INTERNAL_TOOLS），返回 JSON 字符串结果。

    :param api: 插件 Api 实例，供包装 Api 的 tools 使用。
    :param servicer: 插件 ServiceHelper 实例。
    :param name: 工具名称。
    :param arguments: 工具参数字典。
    :return: 序列化后的 JSON 字符串（成功为结果，失败为含 error 的 dict）。
    """
    internal_handlers = {t["def"]["name"]: t["handler"] for t in INTERNAL_TOOLS}
    if name in internal_handlers:
        if servicer is None:
            return _dump({"error": "Internal tools require servicer"})
        try:
            result = await internal_handlers[name](servicer, arguments)
            return _dump(result)
        except Exception as e:
            return _dump({"error": str(e)})

    handlers = {
        "get_plugin_status": _get_plugin_status,
        "get_storage_status": _get_storage_status,
        "browse_directory": _browse_directory,
        "trigger_full_sync": _trigger_full_sync,
        "trigger_share_sync": _trigger_share_sync,
        "add_share_transfer": _add_share_transfer,
        "manual_pan_transfer": _manual_pan_transfer,
        "get_offline_tasks": _get_offline_tasks,
        "add_offline_task": _add_offline_task,
        "clear_id_path_cache": _clear_id_path_cache,
        "clear_increment_skip_cache": _clear_increment_skip_cache,
        "get_sync_delete_history": _get_sync_delete_history,
        "fuse_mount": _fuse_mount,
        "fuse_unmount": _fuse_unmount,
        "get_fuse_status": _get_fuse_status,
        "trigger_full_sync_db": _trigger_full_sync_db,
        "check_life_event_status": _check_life_event_status,
    }
    fn = handlers.get(name)
    if not fn:
        return _dump({"error": f"Unknown tool: {name}"})
    try:
        result = await fn(api, arguments)
        return _dump(result)
    except Exception as e:
        return _dump({"error": str(e)})


async def _get_plugin_status(api: Any, _: Dict) -> Any:
    """
    :param api: 插件 Api 实例。
    :param _: 未使用参数。
    :return: 插件状态响应。
    """
    return await to_thread(api.get_status_api)


async def _get_storage_status(api: Any, _: Dict) -> Any:
    """
    :param api: 插件 Api 实例。
    :param _: 未使用参数。
    :return: 115 存储空间信息。
    """
    return await to_thread(api.get_user_storage_status)


async def _browse_directory(api: Any, args: Dict) -> Any:
    """
    :param api: 插件 Api 实例。
    :param args: 含 path、is_local。
    :return: 目录浏览结果。
    """
    params = BrowseDirParams(
        path=args.get("path", "/"), is_local=args.get("is_local", False)
    )
    return await to_thread(api.browse_dir_api, params)


async def _trigger_full_sync(api: Any, _: Dict) -> Any:
    """
    :param api: 插件 Api 实例。
    :param _: 未使用参数。
    :return: 全量同步触发结果。
    """
    return await to_thread(api.trigger_full_sync_api)


async def _trigger_share_sync(api: Any, _: Dict) -> Any:
    """
    :param api: 插件 Api 实例。
    :param _: 未使用参数。
    :return: 分享同步触发结果。
    """
    return await to_thread(api.trigger_share_sync_api)


async def _add_share_transfer(api: Any, args: Dict) -> Any:
    """
    :param api: 插件 Api 实例。
    :param args: 含 share_url。
    :return: 添加分享转存结果。
    """
    return await to_thread(api.add_transfer_share, args.get("share_url", ""))


async def _manual_pan_transfer(api: Any, args: Dict) -> Any:
    """
    :param api: 插件 Api 实例。
    :param args: 含 path（网盘路径）。
    :return: 手动整理触发结果。
    """
    payload = ManualTransferPayload(path=args.get("path", ""))
    return await to_thread(api.manual_transfer_api, payload)


async def _get_offline_tasks(api: Any, args: Dict) -> Any:
    """
    :param api: 插件 Api 实例。
    :param args: 含 page、limit。
    :return: 离线任务列表。
    """
    payload = OfflineTasksPayload(page=args.get("page", 1), limit=args.get("limit", 10))
    return await to_thread(api.offline_tasks_api, payload)


async def _add_offline_task(api: Any, args: Dict) -> Any:
    """
    :param api: 插件 Api 实例。
    :param args: 含 links、path。
    :return: 添加离线任务结果。
    """
    payload = AddOfflineTaskPayload(links=args.get("links", []), path=args.get("path"))
    return await to_thread(api.add_offline_task_api, payload)


async def _clear_id_path_cache(api: Any, _: Dict) -> Any:
    """
    :param api: 插件 Api 实例。
    :param _: 未使用参数。
    :return: 清理结果。
    """
    return await to_thread(api.clear_id_path_cache_api)


async def _clear_increment_skip_cache(api: Any, _: Dict) -> Any:
    """
    :param api: 插件 Api 实例。
    :param _: 未使用参数。
    :return: 清理结果。
    """
    return await to_thread(api.clear_increment_skip_cache_api)


async def _get_sync_delete_history(api: Any, args: Dict) -> Any:
    """
    :param api: 插件 Api 实例。
    :param args: 含 page、limit。
    :return: 同步删除历史。
    """
    return await to_thread(
        api.get_sync_del_history,
        args.get("page", 1),
        args.get("limit", 20),
    )


async def _fuse_mount(api: Any, args: Dict) -> Any:
    """
    :param api: 插件 Api 实例。
    :param args: 含 mountpoint、readdir_ttl。
    :return: FUSE 挂载结果。
    """
    payload = FuseMountPayload(
        mountpoint=args.get("mountpoint", ""),
        readdir_ttl=float(args.get("readdir_ttl", 60)),
    )
    return await to_thread(api.fuse_mount_api, payload)


async def _fuse_unmount(api: Any, _: Dict) -> Any:
    """
    :param api: 插件 Api 实例。
    :param _: 未使用参数。
    :return: FUSE 卸载结果。
    """
    return await to_thread(api.fuse_unmount_api)


async def _get_fuse_status(api: Any, _: Dict) -> Any:
    """
    :param api: 插件 Api 实例。
    :param _: 未使用参数。
    :return: FUSE 挂载状态。
    """
    return await to_thread(api.fuse_status_api)


async def _trigger_full_sync_db(api: Any, _: Dict) -> Any:
    """
    :param api: 插件 Api 实例。
    :param _: 未使用参数。
    :return: 全量同步数据库触发结果。
    """
    return await to_thread(api.trigger_full_sync_db_api)


async def _check_life_event_status(api: Any, _: Dict) -> Any:
    """
    :param api: 插件 Api 实例。
    :param _: 未使用参数。
    :return: 生活事件线程状态与调试信息。
    """
    return await to_thread(api.check_life_event_status_api)


async def _clear_recyclebin_internal(servicer: Any, _: Dict) -> Any:
    """
    清空 115 回收站（非 Api 暴露，仅 MCP 内部 tool）。

    :param servicer: 插件 ServiceHelper 实例。
    :param _: 未使用参数。
    :return: 结果 dict。
    """
    if not servicer or not servicer.client:
        return {"error": "115 客户端未初始化"}
    cleaner = Cleaner(servicer.client)
    await to_thread(cleaner.clear_recyclebin)
    return {"msg": "回收站已清空"}


async def _clear_receive_path_internal(servicer: Any, _: Dict) -> Any:
    """
    清空 115 最近接收（非 Api 暴露，仅 MCP 内部 tool）。

    :param servicer: 插件 ServiceHelper 实例。
    :param _: 未使用参数。
    :return: 结果 dict。
    """
    if not servicer or not servicer.client:
        return {"error": "115 客户端未初始化"}
    cleaner = Cleaner(servicer.client)
    await to_thread(cleaner.clear_receive_path)
    return {"msg": "最近接收已清空"}


# 填充 TOOLS 列表供 tools/list 返回
TOOLS.extend(
    [
        {
            "def": {
                "name": "get_plugin_status",
                "description": "获取插件运行状态",
                "inputSchema": {"type": "object", "properties": {}},
            }
        },
        {
            "def": {
                "name": "get_storage_status",
                "description": "获取115存储空间信息",
                "inputSchema": {"type": "object", "properties": {}},
            }
        },
        {
            "def": {
                "name": "browse_directory",
                "description": "浏览115网盘/本地目录",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "path": {"type": "string", "description": "目录路径"},
                        "is_local": {"type": "boolean", "description": "是否本地目录"},
                    },
                },
            }
        },
        {
            "def": {
                "name": "trigger_full_sync",
                "description": "触发全量同步",
                "inputSchema": {"type": "object", "properties": {}},
            }
        },
        {
            "def": {
                "name": "trigger_share_sync",
                "description": "触发分享同步",
                "inputSchema": {"type": "object", "properties": {}},
            }
        },
        {
            "def": {
                "name": "add_share_transfer",
                "description": "添加分享转存",
                "inputSchema": {
                    "type": "object",
                    "properties": {"share_url": {"type": "string"}},
                },
            }
        },
        {
            "def": {
                "name": "manual_pan_transfer",
                "description": "手动触发网盘整理",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "path": {"type": "string", "description": "网盘路径"}
                    },
                },
            }
        },
        {
            "def": {
                "name": "get_offline_tasks",
                "description": "获取离线下载任务列表",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "page": {"type": "integer"},
                        "limit": {"type": "integer"},
                    },
                },
            }
        },
        {
            "def": {
                "name": "add_offline_task",
                "description": "添加离线下载任务",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "links": {"type": "array", "items": {"type": "string"}},
                        "path": {"type": "string"},
                    },
                },
            }
        },
        {
            "def": {
                "name": "clear_id_path_cache",
                "description": "清理路径ID缓存",
                "inputSchema": {"type": "object", "properties": {}},
            }
        },
        {
            "def": {
                "name": "clear_increment_skip_cache",
                "description": "清理增量同步跳过缓存",
                "inputSchema": {"type": "object", "properties": {}},
            }
        },
        {
            "def": {
                "name": "get_sync_delete_history",
                "description": "获取同步删除历史",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "page": {"type": "integer"},
                        "limit": {"type": "integer"},
                    },
                },
            }
        },
        {
            "def": {
                "name": "fuse_mount",
                "description": "挂载 FUSE",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "mountpoint": {"type": "string"},
                        "readdir_ttl": {"type": "number"},
                    },
                },
            }
        },
        {
            "def": {
                "name": "fuse_unmount",
                "description": "卸载 FUSE",
                "inputSchema": {"type": "object", "properties": {}},
            }
        },
        {
            "def": {
                "name": "get_fuse_status",
                "description": "获取 FUSE 挂载状态",
                "inputSchema": {"type": "object", "properties": {}},
            }
        },
        {
            "def": {
                "name": "trigger_full_sync_db",
                "description": "触发全量同步数据库",
                "inputSchema": {"type": "object", "properties": {}},
            }
        },
        {
            "def": {
                "name": "check_life_event_status",
                "description": "检查生活事件线程状态与调试信息",
                "inputSchema": {"type": "object", "properties": {}},
            }
        },
    ]
)

# 非 Api 暴露的 tools：仅 MCP 使用，直接依赖 servicer
INTERNAL_TOOLS.extend(
    [
        {
            "def": {
                "name": "clear_recyclebin",
                "description": "清空 115 回收站",
                "inputSchema": {"type": "object", "properties": {}},
            },
            "handler": _clear_recyclebin_internal,
        },
        {
            "def": {
                "name": "clear_receive_path",
                "description": "清空 115 最近接收",
                "inputSchema": {"type": "object", "properties": {}},
            },
            "handler": _clear_receive_path_internal,
        },
    ]
)
