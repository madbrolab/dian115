"""
MCP 服务端：SSE 传输 + JSON-RPC 分发
"""

from asyncio import CancelledError, Queue, TimeoutError, wait_for
from typing import Any, Dict
from uuid import uuid4

from fastapi import Request
from orjson import (
    JSONDecodeError as OrjsonJSONDecodeError,
    dumps as orjson_dumps,
    loads as orjson_loads,
)
from starlette.responses import Response, StreamingResponse

from .handlers import dispatch_rpc


def _sse_message(event: str, data: str) -> str:
    """
    构造一条 SSE 消息。

    :param event: 事件名。
    :param data: 数据内容。
    :return: 格式化为 "event: x\\ndata: y\\n\\n" 的字符串。
    """
    return f"event: {event}\ndata: {data}\n\n"


class MCPManager:
    """
    MCP SSE + JSON-RPC 管理：会话存储、GET SSE 流、POST 消息处理。
    """

    def __init__(self, api: Any, servicer: Any = None):
        """
        :param api: 插件 Api 实例，供 RPC 调用。
        :param servicer: 插件 ServiceHelper 实例。
        """
        self._api = api
        self._servicer = servicer
        self._endpoint = "/mcp/messages"
        # session_id -> Queue of JSON-RPC response bodies (str)
        self._sessions: Dict[str, Queue] = {}

    async def handle_sse(self, request: Request):
        """
        GET /mcp/sse：建立 SSE 连接，先发送 endpoint 事件，再持续发送 message 事件。

        :param request: FastAPI 请求对象。
        :return: StreamingResponse，媒体类型 text/event-stream。
        """
        scope = request.scope
        # 返回客户端用于 POST 的完整路径（含插件前缀），否则客户端会误解析为相对路径导致失败
        path = (
            request.url.path if getattr(request, "url", None) else scope.get("path", "")
        ) or ""
        if path.rstrip("/").endswith("mcp/sse"):
            base = path.rsplit("mcp/sse", 1)[0].rstrip("/")
        else:
            base = scope.get("root_path", "").rstrip("/")
        message_path = (base or "") + self._endpoint
        session_id = uuid4().hex
        self._sessions[session_id] = Queue()
        endpoint_url = f"{message_path}?session_id={session_id}"
        apikey = request.query_params.get("apikey")
        if apikey:
            endpoint_url += f"&apikey={apikey}"

        async def event_stream():
            try:
                yield _sse_message("endpoint", endpoint_url)
                while True:
                    try:
                        body = await wait_for(
                            self._sessions[session_id].get(), timeout=300.0
                        )
                        yield _sse_message("message", body)
                    except TimeoutError:
                        yield _sse_message(
                            "message", orjson_dumps({"ping": True}).decode()
                        )
            except CancelledError:
                pass
            finally:
                self._sessions.pop(session_id, None)

        return StreamingResponse(
            event_stream(),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
                "X-Accel-Buffering": "no",
            },
        )

    async def handle_messages(self, request: Request):
        """
        POST /mcp/messages?session_id=xxx：接收 JSON-RPC 请求，分发后把响应写入该会话的 SSE 流。

        :param request: FastAPI 请求对象，query 含 session_id，body 为 JSON-RPC。
        :return: 202 Accepted 或 4xx 错误响应。
        """
        session_id = request.query_params.get("session_id")
        if not session_id:
            return Response("session_id is required", status_code=400)
        queue = self._sessions.get(session_id)
        if not queue:
            return Response("Could not find session", status_code=404)
        try:
            body = await request.body()
            msg = orjson_loads(body) if body else {}
        except OrjsonJSONDecodeError:
            return Response("Could not parse message", status_code=400)
        method = msg.get("method")
        req_id = msg.get("id")
        params = msg.get("params") or {}
        try:
            result = await dispatch_rpc(
                self._api, self._servicer, method, params, req_id
            )
            if result is not None:
                await queue.put(orjson_dumps(result).decode())
        except Exception as e:
            err = {
                "jsonrpc": "2.0",
                "id": req_id,
                "error": {"code": -32603, "message": str(e)},
            }
            await queue.put(orjson_dumps(err).decode())
        return Response("Accepted", status_code=202)
