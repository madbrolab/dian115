# 消息渠道（API 3.6）

插件可以直接使用 Telegram 机器人、企业微信和 TG 监控账号收发消息：注册命令、监听前缀和关键字、读取会话、给指定会话发消息。

宿主代为调用这些渠道，插件拿不到 Bot Token、企业微信密钥和渠道配置，也拿不到账号的手机号和登录信息。

## 申请与授权

在清单中声明要用的渠道：

```json
{
  "requires": { "api": "3.6" },
  "permissions": ["telegram.bot", "wecom", "telegram.account"],
  "events": [
    { "event": "message", "job": "on-command", "commands": ["task"], "prefixes": ["!run "] },
    { "event": "message", "job": "on-keyword", "keywords": ["失败"], "patterns": ["^工单\\s*\\d+$"], "channels": ["telegram"] },
    { "event": "account_message", "job": "on-account", "keywords": ["新资源"], "peer_types": ["channel", "group"] }
  ]
}
```

| 权限 | 能力 |
| --- | --- |
| `telegram.bot` | 机器人发送、编辑、删除消息，读取已知会话，关键字监听 |
| `wecom` | 企业微信应用发送消息，读取已知用户，关键字监听 |
| `telegram.account` | 账号读取会话列表和消息，发送消息，实时接收消息 |

安装后权限默认关闭，用户在插件卡片上逐项开启。未授权时调用抛错。更新插件时，已授权且仍被声明的权限保留，新申请的权限保持关闭。

## 接收消息

| 触发字段 | 匹配方式 | 是否需要授权 |
| --- | --- | --- |
| `commands` | `/命令`，同步到 Telegram 命令菜单 | 否 |
| `prefixes` | 文本以其开头 | 否 |
| `keywords` | 不区分大小写的包含匹配 | 是 |
| `patterns` | RE2 正则 | 是 |

- 每个事件最多 32 条规则，单条不超过 256 字节。
- `channels` 把 `message` 事件限制到 `telegram` 或 `wecom`，省略为全部。
- 只处理机器人白名单用户和企业微信用户发来的消息。
- 同一条消息会分发给所有命中的插件；每个插件只运行第一个命中的事件。
- `/` 开头的文本和宿主能识别的分享链接由宿主优先处理。其他命中前缀或关键字的文本排在 AI 对话和自然语言指令之前，由插件接手，宿主不再回复。

任务输入：

```json
{
  "channel": "telegram",
  "chat_id": 123456789,
  "chat_type": "private",
  "chat_title": "",
  "user_id": 123456789,
  "username": "alice",
  "message_id": 42,
  "message_thread_id": 0,
  "text": "!run backup",
  "date": 1790000000,
  "trigger": { "type": "prefix", "value": "!run " }
}
```

企业微信的 `channel` 为 `wecom`，`chat_id` 只是稳定哈希，真实用户 ID 在 `channel_user_id`。

### 账号消息

`account_message` 事件需要 `telegram.account` 权限。至少设置一项 `prefixes`、`keywords`、`patterns`，或用 `all: true` 接收全部消息。

| 字段 | 说明 |
| --- | --- |
| `peer_types` | `private`、`group`、`channel`，省略为全部 |
| `include_outgoing` | 是否包含账号自己发出的消息，默认否；开启时注意避免自己触发自己 |

```json
{
  "channel": "telegram_account",
  "peer_type": "group",
  "peer_id": "1234567",
  "message_id": 88,
  "sender_id": "7654321",
  "sender_name": "",
  "text": "新资源已上传",
  "is_outgoing": false,
  "date": "2026-11-01T08:00:00+08:00",
  "has_media": false,
  "trigger": { "type": "keyword", "value": "新资源" }
}
```

账号未登录或客户端未运行时收不到事件。事件队列已满时会丢弃新消息，需要完整记录时用 `messages` 补读。

## 回复

`ctx.messaging.reply` 按消息来源的渠道自动回复：

```js
export async function run(ctx, input) {
  if (input.text.includes('失败')) {
    await ctx.messaging.reply(input, { text: '已记录，正在处理' })
  }
}
```

回复需要来源渠道对应的权限。只用命令和前缀接收消息时，无需授权也能触发，但回复前仍要授权；也可以用 `ctx.notify` 发普通通知。

## Telegram 机器人

```js
const chats = await ctx.telegram.bot.chats()
const { message_id } = await ctx.telegram.bot.send({
  chat_id: chats[0].id,
  text: '<b>备份完成</b>',
  format: 'html',
  buttons: [[{ text: '查看', callback_data: 'view:1' }]],
})
await ctx.telegram.bot.edit({ chat_id: chats[0].id, message_id, text: '已归档' })
await ctx.telegram.bot.delete({ chat_id: chats[0].id, message_id })
```

| 字段 | 说明 |
| --- | --- |
| `chat_id` | 数字 ID 或 `@频道名`；机器人须已在该会话中 |
| `text` | ≤4096 字；与 `image_url` 至少一项 |
| `format` | `text`（默认）或 `html`，HTML 需符合 Telegram 规则 |
| `image_url` | 图片地址，此时 `text` 作为说明 |
| `buttons` | 链接或回调按钮；回调触发清单中的 `callback` 事件 |
| `reply_to`、`message_thread_id`、`silent` | 回复目标、话题和静音 |

Telegram 不提供列出机器人全部会话的接口。`chats()` 返回白名单用户，以及宿主见过的会话。这里发的消息不经过通知模板、渠道开关和静默时段。

## 企业微信

```js
const users = await ctx.wecom.users()
await ctx.wecom.send({ to: users[0].id, title: '提醒', text: '任务完成' })
```

省略 `to` 时发给通知设置里配置的接收人。可选 `image_url`、`link`。企业微信没有会话概念，`users()` 只返回发过消息的用户，不支持回调按钮、编辑和删除。

## TG 监控账号

```js
const me = await ctx.telegram.account.status()
if (me.logged_in) {
  const dialogs = await ctx.telegram.account.dialogs()
  const peer = { peer_type: dialogs[0].type, peer_id: dialogs[0].id, access_hash: dialogs[0].access_hash }
  const history = await ctx.telegram.account.messages({ ...peer, limit: 20 })
  await ctx.telegram.account.send({ ...peer, text: '收到' })
}
```

- `messages` 的 `limit` 最大 100，用 `offset_id` 向前翻页。
- `access_hash` 可省略，宿主从会话列表查找；传入可减少一次查询。
- 账号发出的消息就是用户本人发的，会计入 Telegram 对该账号的风控，请谨慎设计触发条件。

@BotFather 和 Telegram 官方登录通知账号（777000）对插件不可见：不出现在会话列表，不能读取或发送，也不触发事件。旧的账号客户端接口对插件全部禁用，请使用本页接口。

## 限额

| 操作 | 每插件每分钟 |
| --- | --- |
| 机器人发送、编辑、删除 | 30 |
| 企业微信发送 | 20 |
| 账号发送 | 20 |
| 账号读取会话和消息 | 60 |

超限时抛错并给出等待秒数，Telegram 自身的频率限制也按此返回。

页面和后台都使用相同的 `ctx.telegram`、`ctx.wecom`、`ctx.messaging`；HTTP 调用为 `POST /api/extensions/v3/{id}/messaging/{operation}`。
