# 插件通知

插件通过宿主已配置的推送渠道给用户发消息。宿主目前有两个渠道：**Telegram**（`telegram`）和**企业微信**（`wecom`，企业微信应用消息，也可经“微信插件”在个人微信中接收）。插件不接触 Bot Token、企业微信密钥或会话 ID。

```js
// 后台任务
const r = await ctx.notify({ title: '转存完成', body: '3 个文件已转存', level: 'success' })
// 页面
const r = await ctx.notifications.send({ title: '测试', body: '来自插件页面' })
// 发送前查看渠道
const channels = await ctx.notifications.channels()
```

## 参数

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `title` | string，必填 | 标题，≤160 字 |
| `body` | string，必填 | 正文。`text` ≤2000 字；`markdown`/`html` ≤3500 字 |
| `level` | `info` / `success` / `warning` / `error` | 级别，决定图标 ℹ️ ✅ ⚠️ ❌，默认 info |
| `format` | `text` / `markdown` / `html` | 内容格式，见下表，默认 text |
| `channels` | `('telegram'|'wecom'|'all')[]` | 只发到这些渠道；省略或 `all` 为全部 |
| `overrides` | `{telegram?, wecom?}` | 按渠道覆盖 `title` / `body` / `format` / `image_url` |
| `image_url` | HTTPS 地址 | 图片；无凭据、无 # 片段 |
| `buttons` | `[[{text, url \| callback_data}]]` | 最多 8 行、每行 1–4 个；`url` 必须 HTTPS |
| `silent` | boolean | Telegram 静音送达 |
| `dedupe_key` | string ≤200 | 去重键，见“去重与重试” |
| `job_ref` | string | 宿主下发的 `job_` 引用（可选） |

## 格式在各渠道的效果

| format | Telegram | 企业微信 |
| --- | --- | --- |
| `text`（默认） | 套用用户编辑的“插件任务结果”模板，正文按纯文本转义 | 套用企业微信渠道自己的模板，纯文本 |
| `markdown` | 转为 Telegram HTML：`# 标题`、`**粗体**`、`*斜体*`、`~~删除~~`、`` `代码` ``、```` ``` ```` 代码块、`[文字](https://…)`、`- 列表`、`> 引用` | 以企业微信 markdown 消息原样发送（只在企业微信客户端渲染，微信插件中显示为不支持）；带图片时改为图文卡片，正文转纯文本 |
| `html` | Telegram HTML 子集：`b/strong`、`i/em`、`u`、`s/del`、`code`、`pre`、`a href`（http/https/tg）、`blockquote`、`tg-spoiler`；`<br>`/`<p>` 变换行，其他标签与属性移除 | 不支持 HTML，转为纯文本，链接保留为“文字（地址）”；`deliveries[].dropped` 含 `formatting` |

`markdown` 与 `html` 不经过用户模板：宿主在标题前加级别图标，在末尾加一行“🧩 来自插件「插件名」”，插件不能冒充系统通知。要让两个渠道显示不同内容，用 `overrides`：

```js
await ctx.notify({
  title: '订阅更新', level: 'info', format: 'html',
  body: '<b>权力的游戏</b> S01E04 已入库<br><a href="https://example.com/x">详情</a>',
  overrides: { wecom: { format: 'markdown', body: '**权力的游戏** S01E04 已入库\n[详情](https://example.com/x)' } },
  buttons: [[{ text: '打开媒体库', url: 'https://emby.example.com' }]],
})
```

## 图片与按钮

| 功能 | Telegram | 企业微信 |
| --- | --- | --- |
| 图片 | 图片消息；正文 ≤1000 字作说明，超长时图片后另发文字 | 图文卡片（标题、摘要、图片、跳转第一个链接按钮） |
| 链接按钮 | 内联按钮 | 只保留第一个，作为卡片跳转或文末链接 |
| 回调按钮 `callback_data` | 支持：用户点击后触发清单中 `{event:'callback', job}` 任务 | 不支持（报告为 dropped） |

## 用户控制与渠道选择

用户在通知设置中对每个渠道单独决定：是否接收插件通知、静默时段。各渠道互不影响——Telegram 静默不会阻止企业微信，反之亦然。`channels` 只能缩小发送范围，不能绕过用户关闭的渠道或静默时段。

发送前可调用 `ctx.notifications.channels()`（`GET /api/extensions/v3/_notify/channels`）：

```json
[{"channel":"telegram","name":"Telegram","configured":true,"enabled":true,"quiet_now":false,"deliverable":true,
  "formats":["text","markdown","html"],"capabilities":["link_buttons","callback_buttons","images"],"max_body_runes":3500}]
```

`deliverable=false` 的渠道此刻发送会被跳过。

## 返回结果

```json
{"event":"plugin_notification_message","accepted":true,
 "deliveries":[{"channel":"telegram","status":"sent","format":"markdown","preserved":["link_buttons"]},
               {"channel":"wecom","status":"skipped","reason":"quiet_hours"}]}
```

- `accepted`：至少一个渠道已发送。
- `deliveries[]`：每个请求渠道一项。`status` 为 `sent`、`skipped`（`reason`：`not_configured` 未配置、`disabled` 用户关闭插件通知、`quiet_hours` 静默时段）或 `failed`（`error` 为脱敏原因，如“Telegram 拒绝消息（400）：…”）。
- `suppressed` + `suppression_reason`：完全没有发送。`no_channel_enabled` 所有渠道都关闭了插件通知；`telegram_not_configured` 没有可用渠道；`no_eligible_channel` 请求的渠道都被跳过。
- 所有渠道都发送失败时调用抛错，错误信息逐渠道列出脱敏原因。

## 去重、限额与重试

- 每个插件每分钟最多 12 条，超出时抛出限流错误（含建议等待秒数），不会影响其他插件和系统通知。
- `dedupe_key`：10 分钟内同一插件相同键只发送一次（返回 `deduplicated:true`）。后台 `ctx.notify` 还会把每个键的结果永久记在插件数据中：相同键、相同内容直接返回上次结果；相同键、不同内容返回冲突；投递结果未确认的键需要换新键，避免重复打扰用户。
- 没有到达任何渠道的通知（参数错误、限流或所有渠道被跳过）不占用去重键，可以用相同键重试；所有渠道都发送失败时，后台把该键记为待核对，再次发送需换新键，避免可能已到达的消息重复。
- 发送是同步的：返回时各渠道已经有结果。企业微信受官方频控，按每 2 秒一条排队发送。
