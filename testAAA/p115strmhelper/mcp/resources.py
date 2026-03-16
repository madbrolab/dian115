"""
MCP 资源定义与读取：p115://status, p115://storage, p115://fuse/status, p115://sync/history
"""

from asyncio import to_thread
from typing import Any, Dict, List

from orjson import dumps as orjson_dumps


RESOURCES: List[Dict[str, Any]] = [
    {
        "def": {
            "uri": "p115://status",
            "name": "插件运行状态",
            "mimeType": "application/json",
        }
    },
    {
        "def": {
            "uri": "p115://storage",
            "name": "存储空间信息",
            "mimeType": "application/json",
        }
    },
    {
        "def": {
            "uri": "p115://fuse/status",
            "name": "FUSE 挂载状态",
            "mimeType": "application/json",
        }
    },
    {
        "def": {
            "uri": "p115://sync/history",
            "name": "最近同步删除历史",
            "mimeType": "application/json",
        }
    },
]


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


async def read_resource(api: Any, uri: str) -> str:
    """
    根据 uri 返回资源内容 JSON 字符串。

    :param api: 插件 Api 实例。
    :param uri: 资源 URI，如 p115://status、p115://storage 等。
    :return: 资源内容的 JSON 字符串。
    """
    if uri == "p115://status":
        r = await to_thread(api.get_status_api)
        return _dump(r)
    if uri == "p115://storage":
        r = await to_thread(api.get_user_storage_status)
        return _dump(r)
    if uri == "p115://fuse/status":
        r = await to_thread(api.fuse_status_api)
        return _dump(r)
    if uri == "p115://sync/history":
        r = await to_thread(api.get_sync_del_history, 1, 20)
        return _dump(r)
    return orjson_dumps({"error": f"Unknown resource: {uri}"}).decode()
