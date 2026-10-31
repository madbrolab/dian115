# 配方

可以直接改用的写法。接口细节查[接口参考](host-api-reference.md)。

## 可恢复的写操作

外部动作前先存检查点，重启后先核对再决定是否继续：

```js
export async function run(ctx, input) {
  await ctx.task.checkpoint({ step: 'transfer', share: input.share })
  const result = await ctx.api.post('/api/115/share/receive', input)
  await ctx.task.checkpoint({ step: 'done', result })
  return result
}

export async function recover(ctx, checkpoint) {
  if (checkpoint?.step === 'done') return { action: 'complete', result: checkpoint.result }
  return { action: 'attention' }
}
```

清单写 `"recover": "recover"`。不确定动作是否已发生时返回 `attention`，不要重复执行。

## 批量处理并显示进度

```js
export async function run(ctx, input) {
  const items = input.items
  let done = 0, failed = 0
  await ctx.task.update({ total: items.length, done, failed })
  for (const item of items) {
    try { await handle(ctx, item); done++ } catch (error) { failed++; await ctx.task.log(item + '：' + error.message) }
    await ctx.task.update({ done, failed, message: item })
  }
  return { done, failed }
}
```

## 定时任务

```json
{ "jobs": [{ "id": "daily", "entry": "jobs/daily.js", "title": "每日检查", "default_schedule": "0 8 * * *" }] }
```

## 注册 TG 命令并回复

```json
{
  "permissions": ["telegram.bot", "wecom"],
  "events": [{ "event": "message", "job": "on-command", "commands": ["status"] }],
  "jobs": [{ "id": "on-command", "entry": "jobs/command.js", "queue": false }]
}
```

```js
export async function run(ctx, input) {
  const status = await ctx.api.get('/api/115/status')
  await ctx.messaging.reply(input, { text: JSON.stringify(status) })
}
```

## 关键字触发并做出动作

```json
{
  "permissions": ["telegram.bot"],
  "events": [{ "event": "message", "job": "on-word", "keywords": ["转存"], "patterns": ["115\\.com/s/\\w+"] }]
}
```

```js
export async function run(ctx, input) {
  await ctx.task.log(`触发：${input.trigger.type} ${input.trigger.value}`)
  await ctx.messaging.reply(input, { text: '收到，开始处理' })
}
```

## 带按钮的消息

```js
await ctx.telegram.bot.send({ chat_id, text: '要继续吗？', buttons: [[{ text: '继续', callback_data: 'go:42' }]] })
```

```json
{ "events": [{ "event": "callback", "job": "on-button" }] }
```

任务输入的 `data` 是 `go:42`，`chat_id`、`message_id` 指向按钮所在消息。

## 监控账号消息

```json
{
  "permissions": ["telegram.account"],
  "events": [{ "event": "account_message", "job": "on-account", "keywords": ["新资源"], "peer_types": ["channel"] }]
}
```

账号权限等于用用户本人的身份说话，只申请确实需要的，并尽量用关键字过滤。

## 监听目录

```js
await ctx.watch.add({ id: 'inbox', path: '/mnt/cd2/115/Inbox', job: 'on-change', interval_seconds: 300, patterns: ['*.mkv'] })
```

路径在 CD2 挂载目录内会自动走 CD2 接口。CD2 监听默认只看一层，需要子目录时加 `recursive: true`。

```js
export async function run(ctx, input) {
  for (const change of input.changes) await ctx.task.log(`${change.kind} ${change.path}`)
}
```

## 移动文件到 CD2

```js
await ctx.http.request({ url, save_to: 'downloads/a.torrent' })
await ctx.files.call({ operation: 'move', path: 'downloads/a.torrent', destination_dir: '/mnt/cd2/115/种子' })
```

## 订阅宿主事件

```json
{ "events": [{ "event": "host", "job": "on-event", "types": ["library_organize_*"] }],
  "jobs": [{ "id": "on-event", "entry": "jobs/event.js", "allow_overlap": true }] }
```

事件可能密集到达，建议 `allow_overlap: true`，否则上一条未结束时新事件会提交失败。

## Webhook

```json
{ "http": { "entry": "jobs/hook.js", "public": true } }
```

```js
export async function handle(ctx, request) {
  const { secret } = await ctx.settings.get()
  if (request.headers['X-Secret']?.[0] !== secret) return { status: 401, body: 'denied' }
  return { json: { ok: true } }
}
```

地址是 `/plugin-hooks/<插件ID>/<路径>`。公开回调任何人都能访问，必须自己鉴权。

## 保持 WebSocket 连接

```json
{ "jobs": [{ "id": "listen", "entry": "jobs/listen.js", "daemon": true }] }
```

```js
export async function run(ctx) {
  const { url } = await ctx.settings.get()
  const socket = await ctx.ws.connect({ url })
  for (;;) {
    const message = await socket.receive()
    if (message.type === 'close') throw new Error('连接关闭')
    if (message.type === 'text') await ctx.notify({ title: '新事件', body: message.text })
  }
}
```

断线时抛错，宿主会按退避时间重启。

## 读取 SSE

```js
const response = await ctx.http.stream({ url })
const events = response.events()
for (;;) {
  const { done, value } = await events.next()
  if (done) break
  await ctx.task.log(value.data)
}
```

## 对外推送进度

```js
export async function handle(ctx, request) {
  const stream = await ctx.response.sse()
  for (let i = 1; i <= 10; i++) {
    await stream.send({ event: 'progress', data: { percent: i * 10 } })
    await ctx.sleep(1000)
  }
}
```

页面：

```js
const source = new EventSource(ctx.server.hookURL('progress'))
source.addEventListener('progress', event => render(JSON.parse(event.data)))
```

## 连接 TCP 服务

```json
{ "permissions": ["network.tcp"] }
```

```js
const { host, port } = await ctx.settings.get()
const socket = await ctx.tcp.connect({ host, port })
await socket.write('PING\r\n')
const reply = await socket.read({ timeout_ms: 5000 })
await socket.close()
```

地址放在设置里让用户填，不要写死内网地址。

## 保存配置

```js
const revision = await ctx.storage.set('state', { last: Date.now() })
const state = await ctx.storage.get('state')
```

页面可用 `ctx.storage.set(key, value, expected_revision)` 防止覆盖。不要用 `localStorage`。

## 登录外部站点

账号密码写在设置里，用固定的 `session` 复用 Cookie，见[网络与登录](network.md)。

```js
await ctx.http.request({ url: 'https://site.example/login', method: 'POST', form: { user, password }, session: 'site' })
const page = await ctx.http.request({ url: 'https://site.example/me', session: 'site' })
```

## 解析网页

```js
const page = await ctx.http.request({ url })
const links = ctx.html.load(page.body, { baseURL: url }).find('a.title').map(item => item.url('href'))
```

## 调用 AI

```js
const reply = await ctx.api.post(`/api/extensions/v3/${ctx.plugin.id}/ai/complete`, { prompt: '翻译：hello' })
```

参数见[媒体与 AI](media-and-ai.md)。
