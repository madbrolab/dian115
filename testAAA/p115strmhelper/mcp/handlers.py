"""
MCP JSON-RPC 方法分发：initialize, tools/list, tools/call, resources/list, resources/read
"""

from typing import Any, Dict, Optional

from .tools import INTERNAL_TOOLS, TOOLS, run_tool
from .resources import RESOURCES, read_resource


async def dispatch_rpc(
    api: Any,
    servicer: Any,
    method: Optional[str],
    params: Dict[str, Any],
    request_id: Any,
) -> Optional[Dict]:
    """
    根据 method 调用对应逻辑，返回 JSON-RPC 响应体（dict），供上层序列化为 JSON。

    :param api: 插件 Api 实例。
    :param servicer: 插件 ServiceHelper 实例。
    :param method: JSON-RPC 方法名，如 initialize、tools/list、tools/call 等。
    :param params: 方法参数（dict）。
    :param request_id: 请求 id，原样带回响应。
    :return: 响应体 dict，或 None（不向客户端回写时）。
    """
    if not method:
        return {
            "jsonrpc": "2.0",
            "id": request_id,
            "error": {"code": -32600, "message": "Invalid Request"},
        }

    if method == "initialize":
        return {
            "jsonrpc": "2.0",
            "id": request_id,
            "result": {
                "protocolVersion": "2024-11-05",
                "capabilities": {
                    "tools": {"listChanged": False},
                    "resources": {"subscribe": False, "listChanged": False},
                },
                "serverInfo": {"name": "P115StrmHelper", "version": "1.0.0"},
            },
        }

    if method == "tools/list":
        all_defs = [t["def"] for t in TOOLS] + [t["def"] for t in INTERNAL_TOOLS]
        return {
            "jsonrpc": "2.0",
            "id": request_id,
            "result": {"tools": all_defs},
        }

    if method == "tools/call":
        name = (params or {}).get("name")
        arguments = (params or {}).get("arguments") or {}
        if not name:
            return {
                "jsonrpc": "2.0",
                "id": request_id,
                "error": {"code": -32602, "message": "Missing tool name"},
            }
        content = await run_tool(api, servicer, name, arguments)
        return {
            "jsonrpc": "2.0",
            "id": request_id,
            "result": {
                "content": [{"type": "text", "text": content}],
                "isError": False,
            },
        }

    if method == "resources/list":
        return {
            "jsonrpc": "2.0",
            "id": request_id,
            "result": {"resources": [r["def"] for r in RESOURCES]},
        }

    if method == "resources/read":
        uri = (params or {}).get("uri")
        if not uri:
            return {
                "jsonrpc": "2.0",
                "id": request_id,
                "error": {"code": -32602, "message": "Missing uri"},
            }
        content = await read_resource(api, uri)
        return {
            "jsonrpc": "2.0",
            "id": request_id,
            "result": {
                "contents": [
                    {"uri": uri, "mimeType": "application/json", "text": content}
                ],
            },
        }

    return {
        "jsonrpc": "2.0",
        "id": request_id,
        "error": {"code": -32601, "message": f"Method not found: {method}"},
    }
