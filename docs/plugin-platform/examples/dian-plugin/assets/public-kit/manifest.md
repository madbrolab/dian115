# 清单参考 plugin.json

清单放在插件根目录。这里的规则就是宿主安装时的校验规则，不满足会拒绝安装。机器可读版本见 [Schema](manifest.schema.json)。

## 顶层字段

| 字段 | 必填 | 规则 |
| --- | --- | --- |
| `schema_version` | 是 | 固定为 `3` |
| `id` | 是 | 小写字母、数字，用 `.` 或 `-` 分隔，最长 128。安装后不能改 |
| `name` | 是 | 显示名称 |
| `version` | 是 | 版本字符串，上架时同一 `id` 下不可重复 |
| `author` | 上架必填 | 作者署名，显示在插件卡片和安装确认；本地安装缺失时显示“未署名” |
| `description` | 上架必填 | 说明插件做什么 |
| `homepage` | 否 | 项目主页 |
| `icon` | 否 | 包内的 svg、png 或 webp |
| `requires.api` | 建议 | 最低宿主插件 API，如 `"3.7"`；宿主更低时拒绝安装 |
| `ui` | 三选一 | `{entry}`，存在的 `.js` 或 `.html` 文件 |
| `jobs` | 三选一 | 后台任务数组 |
| `http` | 三选一 | HTTP 处理器 |
| `menu` | 否 | `{title, order}`，需要 `ui`；是否显示在侧栏由用户决定 |
| `settings` | 否 | 宿主渲染的设置表单；有页面的插件建议把设置做在页面里 |
| `events` | 否 | 触发任务的事件 |
| `listeners` | 否 | 启用时绑定的端口，需要 `http` |
| `permissions` | 否 | 申请的消息渠道，见下 |
| `declared_usage` | 建议 | 作者说明，见下 |

`ui`、`jobs`、`http` 至少提供一项。所有路径都相对插件根目录，不能以 `/` 开头，不能含 `..` 或反斜杠。

## jobs[]

| 字段 | 规则 |
| --- | --- |
| `id` | 必填，同 `id` 规则，不可重复 |
| `entry` | 必填，存在的文件 |
| `handler` | 导出的函数名，默认 `run` |
| `recover` | 恢复函数名，见[开发指南](developer-guide.md) |
| `title` | 任务队列里的名称，最多 40 字 |
| `queue` | `false` 时不显示在任务队列页，适合短任务 |
| `default_schedule` | 五段 cron |
| `interval_seconds` | 固定间隔，优先于 `default_schedule`，最大 365 天 |
| `timeout_seconds` | 默认 30 分钟，最大 365 天 |
| `allow_overlap` | 是否允许同时运行多个实例 |
| `daemon` | 常驻任务，不能同时设置定时或超时，见[长连接](long-connections.md) |

## events[]

| `event` | 必填字段 | 可选字段 | 任务输入 |
| --- | --- | --- | --- |
| `message` | `job`，且 `commands`、`prefixes`、`keywords`、`patterns` 至少一项 | `channels` | 消息，见[消息渠道](messaging.md) |
| `account_message` | `job`，且 `prefixes`、`keywords`、`patterns`、`all` 至少一项 | `peer_types`、`include_outgoing` | 账号消息 |
| `callback` | `job` | | 按钮回调 |
| `host` | `job`、`types` | | 宿主事件 `{id,type,title,content,data,at}` |

- 每个事件的文本规则合计最多 32 条，单条不超过 256 字节。
- `keywords`、`patterns` 需要声明 `telegram.bot` 或 `wecom`；`patterns` 是 RE2 正则，不支持反向引用。
- `account_message` 需要声明 `telegram.account`，不支持 `commands`。
- `types` 支持末尾 `*` 通配，可用类型由 `ctx.events.catalog()` 列出。

## permissions[]

可选值：`telegram.bot`、`wecom`、`telegram.account`、`network.tcp`。声明只是申请，用户在插件卡片上逐项开启后才生效。

## settings[]

| 字段 | 规则 |
| --- | --- |
| `key` | 必填，不可重复 |
| `label` | 必填 |
| `type` | `text`、`password`、`textarea`、`number`、`boolean`、`select`、`path`、`url` |
| `options` | `select` 必填，`[{label,value}]` |
| `default`、`required`、`help`、`placeholder` | 可选 |

值保存在插件 KV 的 `settings` 键，用 `ctx.settings.get()` 读取。

## http

| 字段 | 规则 |
| --- | --- |
| `entry` | 必填，存在的文件 |
| `handler` | 导出的函数名，默认 `handle` |
| `timeout_seconds` | 默认 60，最大 3600 |
| `public` | `true` 时开放 `/plugin-hooks/<id>/`，无需登录，处理器必须自行鉴权 |

用 `ctx.response` 流式输出后不再受 `timeout_seconds` 限制，见[长连接](long-connections.md)。

## listeners[]

`{id, port, host}`。`port` 为 1 到 65535，`id` 不可重复。不填 `host` 会监听全部网卡，建议写 `127.0.0.1`。

## declared_usage

自由结构，只是告知，不是权限白名单。写清楚能减少用户疑虑，安全审查也会比对这里的站点：

```json
{
  "declared_usage": {
    "purpose": "把新资源推送到 TG",
    "sites": ["api.example.com"],
    "apis": ["/api/115/status"],
    "paths": "用户在设置里选择的目录",
    "notifications": "任务完成时发送"
  }
}
```
