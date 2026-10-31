# 长连接与常驻任务（API 3.8）

后台脚本可以保持长连接，也可以声明开机自动运行的常驻任务。常驻任务、WebSocket 和流式读取声明 `requires.api: "3.7"`，原生 TCP 和对外推送声明 `"3.8"`。

## 常驻任务

在清单的任务上加 `daemon: true`：

```json
{ "jobs": [{ "id": "listen", "entry": "jobs/listen.js", "daemon": true }] }
```

```js
export async function run(ctx) {
  const socket = await ctx.ws.connect({ url: 'wss://example.com/events' })
  for (;;) {
    const message = await socket.receive()
    if (message.type === 'close') throw new Error('连接已关闭：' + message.code)
    if (message.type === 'text') await handle(ctx, message.text)
  }
}
```

- 插件启用时启动，宿主开机时自动启动，停用、更新、卸载或宿主关闭时停止。
- 处理函数结束或抛错后自动重启，等待时间从 1 秒翻倍到最多 5 分钟；连续运行满 1 分钟后恢复为 1 秒。所以连接断开时直接抛错即可，不用自己写重连。
- 不进入任务队列，不能设置 `default_schedule`、`interval_seconds`、`timeout_seconds`。
- 没有 `ctx.task.checkpoint` 恢复语义；需要保存的进度写入 `ctx.storage`。
- 状态和最近 200 条日志可用 `GET /api/extensions/v3/{id}/daemons` 读取，`console.log` 会写入这里。
- 超出内存预算时脚本被中止，随后按上述规则重启。

## WebSocket

```js
const socket = await ctx.ws.connect({
  url: 'wss://example.com/socket',
  headers: { Authorization: 'Bearer ...' },
  protocols: ['json'],
  session: 'default',
  max_message_bytes: 4 * 1024 * 1024,
})
await socket.send(JSON.stringify({ op: 'subscribe' }))
const message = await socket.receive()
await socket.close(1000, 'done')
```

| `receive()` 结果 | 说明 |
| --- | --- |
| `{type:'text', text}` | 文本消息 |
| `{type:'binary', data}` | 二进制消息，`data` 为 Uint8Array |
| `{type:'close', code, reason}` | 对方关闭连接 |

网络异常时 `receive()` 抛错。`send` 接受字符串或二进制。`max_message_bytes` 默认 1 MiB，最大 16 MiB。Cookie 会话和 `proxy` 与 `ctx.http.request` 相同。

也可以用标准写法 `new WebSocket(url, protocols)`，支持 `onopen`、`onmessage`、`onerror`、`onclose`、`addEventListener`、`send`、`close`。额外提供 `socket.closed`，是连接结束时完成的 Promise；处理函数要 `await` 它，否则函数返回后连接随脚本结束。

## 流式读取

`ctx.http.stream` 在收到响应头时就返回，不等响应结束。参数与 `ctx.http.request` 相同，不支持缓存和 `save_to`。

```js
const response = await ctx.http.stream({ url: 'https://example.com/events' })
const events = response.events()
for (;;) {
  const { done, value } = await events.next()
  if (done) break
  await handle(ctx, value.event, value.data)
}
```

| 读取方式 | 结果 |
| --- | --- |
| `response.read()` | 下一段 Uint8Array，结束时为 `null` |
| `response.chunks().next()` | 同上，迭代器形式 |
| `response.lines().next()` | 下一行文本 |
| `response.events().next()` | 下一条 SSE 事件 `{event, data, id}` |
| `response.close()` | 提前关闭 |

三种迭代器只选一种使用。脚本引擎不支持 `for await`，请按上面的写法循环调用 `next()`。

## 对外推送 SSE

HTTP 处理器可以边运行边输出，适合实时进度和事件推送。`ctx.response` 只在 HTTP 处理器里可用。

```js
export async function handle(ctx, request) {
  const stream = await ctx.response.sse()
  await stream.send({ event: 'ready', id: 1, data: { ok: true } })
  for (;;) {
    await stream.comment()
    await ctx.sleep(15000)
  }
}
```

| 方法 | 说明 |
| --- | --- |
| `stream.send({event, id, retry, data})` | 发送一条事件。`data` 不是字符串时转成 JSON，多行会拆成多个 `data:` |
| `stream.comment(text)` | 发送注释，用作心跳，默认 `ping`。很多代理会断开长时间无数据的连接 |

其他格式用 `ctx.response.stream({status, headers})`，返回 `{write(data)}`，每次写入立即发出：

```js
const body = await ctx.response.stream({ headers: { 'Content-Type': 'application/x-ndjson' } })
await body.write(JSON.stringify({ n: 1 }) + '\n')
```

- 处理函数返回时响应结束，此后返回值被忽略。
- 开始输出后不再受 `http.timeout_seconds` 限制，客户端断开时脚本被中止。
- 登录页面可用 `new EventSource(ctx.server.hookURL('events'))`；外部访问用 `http.public` 或监听端口，并自行鉴权。
- 处理器之间不共享内存。要把常驻任务收到的事件推给页面，先写入 `ctx.storage`，处理器轮询读取。
- 经过反向代理时需要关闭响应缓冲。宿主已发送 `X-Accel-Buffering: no`，其他代理按各自方式配置。

## 原生 TCP

需要 `network.tcp` 权限，在清单声明，用户在插件卡片上开启后才能用。未授权时调用抛错。只在后台可用。

```js
const socket = await ctx.tcp.connect({ host: 'redis.lan', port: 6379 })
await socket.write('PING\r\n')
const reply = await socket.read({ timeout_ms: 5000 })
await socket.close()
```

| `connect` 参数 | 说明 |
| --- | --- |
| `host`、`port` | 必填 |
| `tls` | 使用 TLS，默认否 |
| `server_name` | TLS 证书域名，默认用 `host` |
| `insecure` | 跳过证书校验，只用于用户自己的内网设备 |
| `timeout_seconds` | 连接超时，默认 30 秒 |

| 连接方法 | 说明 |
| --- | --- |
| `read({timeout_ms})` | 下一段 Uint8Array，对方关闭时为 `null`，超时抛错且连接保持可用 |
| `lines().next()` | 按行读取文本 |
| `write(data)` | 写入字符串或二进制，单次最多 16 MiB，30 秒超时 |
| `end()` | 关闭写方向，仍可继续读 |
| `close()` | 关闭连接 |

`local_address`、`remote_address` 是两端地址。TCP 不走宿主代理。

### 开放端口

```json
{ "permissions": ["network.tcp"], "jobs": [{ "id": "server", "entry": "jobs/server.js", "daemon": true }] }
```

```js
export async function run(ctx) {
  const server = await ctx.tcp.listen({ port: 9000 })
  for (;;) {
    const client = await server.accept()
    await serve(ctx, client)
  }
}

async function serve(ctx, client) {
  const data = await client.read({ timeout_ms: 30000 })
  await client.write(data)
  await client.close()
}
```

- `host` 默认 `127.0.0.1`，只有本机能连。外部访问要写 `0.0.0.0` 并自己鉴权；安全扫描会标记。
- `port` 为 0 时由系统分配，实际端口在 `server.port`。
- 端口随脚本结束关闭，所以放在常驻任务里；停用插件时自动释放。
- `accept` 按顺序处理连接。要同时服务多个连接，不要 `await serve()`，并给每个连接加错误处理。
- DIAN115 运行在 Docker 里时，要在容器上映射端口，外部才能访问。

## 限制

- 每个插件最多同时保持 16 条连接，WebSocket、流式读取、TCP 连接、TCP 监听和对外推送合计。
- `timeout_seconds` 只限制建立连接，默认 30 秒；连接建立后不再超时，由任务生命周期决定。
- 普通任务的超时仍然有效，长连接建议放在常驻任务里。
- 脚本结束时，宿主关闭它打开的全部连接。
- 不支持 UDP，也不能作为 WebSocket 服务端。
- 后台脚本是单线程的，连接再多也不会并行执行 JS。

检测到这些能力时，安装确认会显示“开机后常驻后台运行”“建立 WebSocket 长连接”“保持流式网络连接”“对外推送事件流”；“建立原生 TCP 连接”“开放 TCP 端口”属于危险等级。
