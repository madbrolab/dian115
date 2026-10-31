# 宿主接口参考

本页由 `openapi-v3.json` 生成：每个接口的参数、请求字段、调用写法、示例和响应字段。字段说明来自宿主代码注释、[字段词汇表](conformance/api-glossary.json)与[常用接口示例](conformance/api-cookbook.json)；手写示例已按契约校验。

## 调用与解析约定

- 后台用 `ctx.api.get/post/put/patch/delete(path, body)`，页面用同名的 `ctx.api`；路径必须以 `/api/` 开头，GET 参数写在查询串里。
- 返回值就是接口原始 JSON（不再包一层）。不同接口的外层结构不同：有的直接是对象，有的为 `{code:"ok",data}`，以本页“响应”为准。
- HTTP 非 2xx 时抛错：后台错误对象含 `status`、`method`、`path`、`data`（通常为 `{error:"原因"}`）；页面沿用 Axios 错误（`e.response.status`、`e.response.data.error`）。
- 写操作超时或中断时先查询业务结果再决定是否重试，不要盲目重发转存、离线等外部动作。
- 115 目录只按节点 ID（cid）和父 ID 组织；名称是不透明元数据。

## 目录

- [115 账号、离线与分享](#115-账号-离线与分享)（27）
- [CD2](#cd2)（2）
- [cache](#cache)（1）
- [看板与历史](#看板与历史)（8）
- [Emby](#emby)（10）
- [插件平台](#插件平台)（52）
- [媒体库](#媒体库)（1）
- [宿主文件管理](#宿主文件管理)（18）
- [整理](#整理)（24）
- [pt](#pt)（4）
- [同步规则与 STRM](#同步规则与-strm)（13）
- [任务队列](#任务队列)（6）
- [订阅](#订阅)（16）
- [TMDB](#tmdb)（7）
- [加密服务](#加密服务)（3）

## 115 账号、离线与分享

### GET `/api/115/accounts/options`

<a id="get-api-115-accounts-options"></a>

列出可用账号。 列出可用于 115 操作的账号。写操作的 account.mode/id 从这里取值；只返回 Cookie 状态，不返回 Cookie。

**调用**

```js
const res = await ctx.api.get('/api/115/accounts/options')
```

**响应 200**

```json
{
  "accounts": [
    {
      "mode": "main",
      "id": 1,
      "name": "主账号",
      "user_name": "user01",
      "is_vip": true,
      "cookie_status": "valid",
      "cloud_name": "115"
    },
    {
      "mode": "backup",
      "id": 2,
      "name": "备用 2",
      "is_vip": false,
      "cookie_status": "valid"
    }
  ]
}
```

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `accounts` | AccountOption[] |  |
| `accounts[].cloud_name` | string | CD2 中的云盘名称（挂载根下第一层目录） |
| `accounts[].cookie_status` | string | 只返回状态，不返回 Cookie。 |
| `accounts[].id` | integer(int64) | 账号 ID；写操作的 account.id 取此值 |
| `accounts[].is_vip` | boolean | 是否 115 VIP |
| `accounts[].mode` | "main" / "backup" / "backup_pool" | 账号类型；写操作的 account.mode 取此值 |
| `accounts[].name` | string | 名称 |
| `accounts[].user_name` | string |  |

### GET `/api/115/browse-dirs`

<a id="get-api-115-browse-dirs"></a>

浏览 115 目录树。 读取目标账号的目录树。

**参数**

| 名称 | 位置 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- | --- |
| `captcha_token` | query | string |  | 115 风控验证会话令牌。接口返回需要验证码时，用户完成验证后带上它重试 |
| `cid` | query | string |  | 115 目录节点 ID（字符串）。根目录为 "0"；目录层级只按节点 ID 与父 ID 建立，不按名称拆分 |
| `token` | query | string |  | captcha_token 的兼容名称 |

**调用**

```js
const res = await ctx.api.get('/api/115/browse-dirs')
```

**响应 200**（按契约结构生成的示例值）

```json
{
  "account_id": 2,
  "cid": "2876543210987654321",
  "dirs": [
    null
  ]
}
```

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `account_id` | integer |  |
| `cid` | any | 115 目录节点 ID（字符串）。根目录为 "0"；目录层级只按节点 ID 与父 ID 建立，不按名称拆分 |
| `dirs` | any[] |  |

### GET `/api/115/directories`

<a id="get-api-115-directories"></a>

浏览 115 目录。 列出 115 目录下的子目录（只含目录）。cid 省略为根目录 "0"。遇到 115 风控时返回验证码要求，完成验证后带 captcha_token 重试。

**参数**

| 名称 | 位置 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- | --- |
| `account_mode` | query | "main" / "backup" / "backup_pool" |  | main 使用主账号；backup 使用指定备用账号；backup_pool 每次读取选择一个可用备用账号。默认 main。 |
| `account_id` | query | integer(int64) |  | account_mode=backup 时必填；main 时可指定主账号，省略则使用当前活动主账号。 |
| `cid` | query | string |  | 115 目录节点 ID（字符串）。根目录为 "0"；目录层级只按节点 ID 与父 ID 建立，不按名称拆分 |
| `account_uuid` | query | string |  | 115 账号 UUID，可代替 account_id 指定账号 |
| `captcha_token` | query | string |  | 115 风控验证会话令牌。接口返回需要验证码时，用户完成验证后带上它重试 |
| `token` | query | string |  | captcha_token 的兼容名称 |

**调用**

```js
const res = await ctx.api.get('/api/115/directories?cid=0')
```

**响应 200**

```json
{
  "cid": "0",
  "dirs": [
    {
      "cid": "2876543210987654321",
      "name": "电影"
    },
    {
      "cid": "2876543210987654322",
      "name": "剧集"
    }
  ],
  "account": {
    "mode": "main",
    "id": 1,
    "name": "主账号"
  }
}
```

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `account` | AccountSummary |  |
| `account.cloud_name` | string | CD2 中的云盘名称（挂载根下第一层目录） |
| `account.id` | integer(int64) | 实际使用的账号 ID |
| `account.mode` | "main" / "backup" | 实际使用的账号类型：main 或 backup |
| `account.name` | string | 名称 |
| `cid` | string | 115 目录节点 ID（字符串）。根目录为 "0"；目录层级只按节点 ID 与父 ID 建立，不按名称拆分 |
| `dirs` | AccountDirectory[] |  |
| `dirs[].cid` | string | 115 目录节点 ID（字符串）。根目录为 "0"；目录层级只按节点 ID 与父 ID 建立，不按名称拆分 |
| `dirs[].name` | string | 名称 |

### POST `/api/115/offline/add`

<a id="post-api-115-offline-add"></a>

创建离线任务。 提交 115 离线下载。urls 支持磁力、ed2k、HTTP(S)，每次最多 100 个。accepted 为 115 接受的数量；下载进度用离线任务列表查询。

**请求体（JSON）**

| 字段 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- |
| `account` | AccountSelector |  | 写操作的账号选择器。`backup` 必须给出 `id`；`backup_pool` 只允许创建离线或转存时由宿主选定账号，不允许修改已有离线任务。 |
| `account.id` | integer(int64) |  | 备用账号 ID，来自 GET /api/115/accounts/options |
| `account.mode` | "main" / "backup" / "backup_pool" |  | main 主账号（默认）；backup 指定备用账号（需 id）；backup_pool 由宿主挑选备用账号（仅创建离线或转存） |
| `save_cid` | string |  | 离线下载保存目录的 115 节点 ID；主账号省略时使用账号默认离线目录，备用账号必须提供 |
| `urls` | string[] | 是 | 离线下载地址：磁力链接、ed2k、HTTP(S) 链接，每次 1–100 个 |

**调用**

```js
const res = await ctx.api.post('/api/115/offline/add', {
  "urls": [
    "magnet:?xt=urn:btih:c9e15763f722f23e98a29decdfae341b98d53056"
  ],
  "save_cid": "2876543210987654321"
})
```

**响应 200**

```json
{
  "success": true,
  "accepted": 1,
  "save_cid": "2876543210987654321",
  "account": {
    "mode": "main",
    "id": 1,
    "name": "主账号"
  }
}
```

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `accepted` | integer |  |
| `account` | AccountSummary |  |
| `account.cloud_name` | string | CD2 中的云盘名称（挂载根下第一层目录） |
| `account.id` | integer(int64) | 实际使用的账号 ID |
| `account.mode` | "main" / "backup" | 实际使用的账号类型：main 或 backup |
| `account.name` | string | 名称 |
| `save_cid` | string | 离线下载保存目录的 115 节点 ID；主账号省略时使用账号默认离线目录，备用账号必须提供 |
| `success` | true | 是否成功；成功响应中恒为 true，失败时返回 4xx/5xx 与 error |

### POST `/api/115/offline/clear`

<a id="post-api-115-offline-clear"></a>

清理离线任务。 批量清理目标账号中的离线任务。

**请求体（JSON）**

| 字段 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- |
| `account` | AccountSelector |  | 写操作的账号选择器。`backup` 必须给出 `id`；`backup_pool` 只允许创建离线或转存时由宿主选定账号，不允许修改已有离线任务。 |
| `account.id` | integer(int64) |  | 备用账号 ID，来自 GET /api/115/accounts/options |
| `account.mode` | "main" / "backup" / "backup_pool" |  | main 主账号（默认）；backup 指定备用账号（需 id）；backup_pool 由宿主挑选备用账号（仅创建离线或转存） |
| `flag` | integer | 是 | 0 已完成；1 全部；2 失败；3 进行中；4 已完成及源文件；5 全部及源文件。 |

**调用**

```js
const res = await ctx.api.post('/api/115/offline/clear', {
  "account": {
    "id": 1,
    "mode": "main"
  },
  "flag": 0
})
```

**响应 202**（按契约结构生成的示例值）

```json
{
  "account": {
    "cloud_name": "<cloud_name>",
    "id": 0,
    "mode": "main",
    "name": "<name>"
  },
  "message": "<message>",
  "status": "queued",
  "task_id": "20261029213000-a1b2c3"
}
```

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `account` | AccountSummary |  |
| `account.cloud_name` | string | CD2 中的云盘名称（挂载根下第一层目录） |
| `account.id` | integer(int64) | 实际使用的账号 ID |
| `account.mode` | "main" / "backup" | 实际使用的账号类型：main 或 backup |
| `account.name` | string | 名称 |
| `message` | string | 给用户看的结果说明 |
| `status` | "queued" |  |
| `task_id` | string | 统一任务队列的任务 ID，可用 GET /api/tasks/{id} 查询进度 |

### POST `/api/115/offline/delete`

<a id="post-api-115-offline-delete"></a>

删除离线任务。 删除离线任务。info_hash 或 info_hashes 二选一；delete_source=true 同时删除已下载文件。

**请求体（JSON）**

| 字段 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- |
| `account` | AccountSelector |  | 写操作的账号选择器。`backup` 必须给出 `id`；`backup_pool` 只允许创建离线或转存时由宿主选定账号，不允许修改已有离线任务。 |
| `account.id` | integer(int64) |  | 备用账号 ID，来自 GET /api/115/accounts/options |
| `account.mode` | "main" / "backup" / "backup_pool" |  | main 主账号（默认）；backup 指定备用账号（需 id）；backup_pool 由宿主挑选备用账号（仅创建离线或转存） |
| `delete_source` | boolean |  | 是否同时删除源文件 |
| `info_hash` | string |  | 115 离线任务 info hash（来自离线任务列表） |
| `info_hashes` | string[] |  | 多个离线任务 info hash |

**调用**

```js
const res = await ctx.api.post('/api/115/offline/delete', {
  "info_hashes": [
    "c9e15763f722f23e98a29decdfae341b98d53056"
  ],
  "delete_source": false
})
```

**响应 200**（按契约结构生成的示例值）

```json
{
  "account": {
    "cloud_name": "<cloud_name>",
    "id": 0,
    "mode": "main",
    "name": "<name>"
  }
}
```

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `account` | AccountSummary |  |
| `account.cloud_name` | string | CD2 中的云盘名称（挂载根下第一层目录） |
| `account.id` | integer(int64) | 实际使用的账号 ID |
| `account.mode` | "main" / "backup" | 实际使用的账号类型：main 或 backup |
| `account.name` | string | 名称 |

### GET `/api/115/offline/download-path`

<a id="get-api-115-offline-download-path"></a>

查询默认离线目录。 查询目标账号的默认离线目录。

**参数**

| 名称 | 位置 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- | --- |
| `account_mode` | query | "main" / "backup" / "backup_pool" |  | main 使用主账号；backup 使用指定备用账号；backup_pool 每次读取选择一个可用备用账号。默认 main。 |
| `account_id` | query | integer(int64) |  | account_mode=backup 时必填；main 时可指定主账号，省略则使用当前活动主账号。 |
| `account_uuid` | query | string |  | 115 账号 UUID，可代替 account_id 指定账号 |

**调用**

```js
const res = await ctx.api.get('/api/115/offline/download-path')
```

**响应 200**（按契约结构生成的示例值）

```json
{
  "account": {
    "cloud_name": "<cloud_name>",
    "id": 0,
    "mode": "main",
    "name": "<name>"
  }
}
```

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `account` | AccountSummary |  |
| `account.cloud_name` | string | CD2 中的云盘名称（挂载根下第一层目录） |
| `account.id` | integer(int64) | 实际使用的账号 ID |
| `account.mode` | "main" / "backup" | 实际使用的账号类型：main 或 backup |
| `account.name` | string | 名称 |

### POST `/api/115/offline/pause`

<a id="post-api-115-offline-pause"></a>

暂停离线任务。 暂停一个离线任务。响应为 115 原始结果透传，字段随 115 变化；HTTP 200 即表示成功。

**请求体（JSON）**

| 字段 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- |
| `account` | object |  | 115 账号。请求中为选择器 {mode,id}：mode=main 主账号（默认）、backup 备用账号（需 id）、backup_pool 由宿主挑选备用账号；响应中为实际使用的账号摘要 |
| `account.id` | integer |  |  |
| `account.mode` | string |  |  |
| `account.uuid` | string |  |  |
| `info_hash` | string |  | 115 离线任务 info hash（来自离线任务列表） |

**调用**

```js
const res = await ctx.api.post('/api/115/offline/pause', {
  "info_hash": "c9e15763f722f23e98a29decdfae341b98d53056",
  "account": {
    "mode": "main"
  }
})
```

**响应 200**（按契约结构生成的示例值）

```json
{}
```

响应为宿主或上游服务原样透传的 JSON，字段可能随上游变化；以 HTTP 2xx 判断成功。

### GET `/api/115/offline/quota`

<a id="get-api-115-offline-quota"></a>

查询离线额度。 查询目标账号的离线配额。

**参数**

| 名称 | 位置 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- | --- |
| `account_mode` | query | "main" / "backup" / "backup_pool" |  | main 使用主账号；backup 使用指定备用账号；backup_pool 每次读取选择一个可用备用账号。默认 main。 |
| `account_id` | query | integer(int64) |  | account_mode=backup 时必填；main 时可指定主账号，省略则使用当前活动主账号。 |
| `account_uuid` | query | string |  | 115 账号 UUID，可代替 account_id 指定账号 |

**调用**

```js
const res = await ctx.api.get('/api/115/offline/quota')
```

**响应 200**（按契约结构生成的示例值）

```json
{
  "account": {
    "cloud_name": "<cloud_name>",
    "id": 0,
    "mode": "main",
    "name": "<name>"
  }
}
```

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `account` | AccountSummary |  |
| `account.cloud_name` | string | CD2 中的云盘名称（挂载根下第一层目录） |
| `account.id` | integer(int64) | 实际使用的账号 ID |
| `account.mode` | "main" / "backup" | 实际使用的账号类型：main 或 backup |
| `account.name` | string | 名称 |

### POST `/api/115/offline/restart`

<a id="post-api-115-offline-restart"></a>

重试离线任务。 重新提交一个离线任务。

**请求体（JSON）**

| 字段 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- |
| `account` | AccountSelector |  | 写操作的账号选择器。`backup` 必须给出 `id`；`backup_pool` 只允许创建离线或转存时由宿主选定账号，不允许修改已有离线任务。 |
| `account.id` | integer(int64) |  | 备用账号 ID，来自 GET /api/115/accounts/options |
| `account.mode` | "main" / "backup" / "backup_pool" |  | main 主账号（默认）；backup 指定备用账号（需 id）；backup_pool 由宿主挑选备用账号（仅创建离线或转存） |
| `info_hash` | string | 是 | 115 离线任务 info hash（来自离线任务列表） |

**调用**

```js
const res = await ctx.api.post('/api/115/offline/restart', {
  "account": {
    "id": 1,
    "mode": "main"
  },
  "info_hash": "c9e15763f722f23e98a29decdfae341b98d53056"
})
```

**响应 200**（按契约结构生成的示例值）

```json
{
  "account": {
    "cloud_name": "<cloud_name>",
    "id": 0,
    "mode": "main",
    "name": "<name>"
  }
}
```

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `account` | AccountSummary |  |
| `account.cloud_name` | string | CD2 中的云盘名称（挂载根下第一层目录） |
| `account.id` | integer(int64) | 实际使用的账号 ID |
| `account.mode` | "main" / "backup" | 实际使用的账号类型：main 或 backup |
| `account.name` | string | 名称 |

### POST `/api/115/offline/resume`

<a id="post-api-115-offline-resume"></a>

恢复离线任务。 恢复一个已暂停的离线任务。响应为 115 原始结果透传；HTTP 200 即表示成功。

**请求体（JSON）**

| 字段 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- |
| `account` | object |  | 115 账号。请求中为选择器 {mode,id}：mode=main 主账号（默认）、backup 备用账号（需 id）、backup_pool 由宿主挑选备用账号；响应中为实际使用的账号摘要 |
| `account.id` | integer |  |  |
| `account.mode` | string |  |  |
| `account.uuid` | string |  |  |
| `info_hash` | string |  | 115 离线任务 info hash（来自离线任务列表） |

**调用**

```js
const res = await ctx.api.post('/api/115/offline/resume', {
  "info_hash": "c9e15763f722f23e98a29decdfae341b98d53056",
  "account": {
    "mode": "main"
  }
})
```

**响应 200**（按契约结构生成的示例值）

```json
{}
```

响应为宿主或上游服务原样透传的 JSON，字段可能随上游变化；以 HTTP 2xx 判断成功。

### GET `/api/115/offline/tasks`

<a id="get-api-115-offline-tasks"></a>

查询离线任务。 分页查询离线任务。status 可为 all、failed、completed、downloading；progress 为 0–1 的小数；status 为归一化状态，status_code 为 115 原始状态码。

**参数**

| 名称 | 位置 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- | --- |
| `account_mode` | query | "main" / "backup" / "backup_pool" |  | main 使用主账号；backup 使用指定备用账号；backup_pool 每次读取选择一个可用备用账号。默认 main。 |
| `account_id` | query | integer(int64) |  | account_mode=backup 时必填；main 时可指定主账号，省略则使用当前活动主账号。 |
| `page` | query | integer |  | 页码，从 1 开始 |
| `page_size` | query | integer |  | 每页条数 |
| `status` | query | "all" / "failed" / "completed" / "downloading" |  | 推荐的状态过滤器；提供后忽略 `stat`。 |
| `stat` | query | string |  | 兼容 115 原始状态码的过滤器。 |
| `account_uuid` | query | string |  | 115 账号 UUID，可代替 account_id 指定账号 |

**调用**

```js
const res = await ctx.api.get('/api/115/offline/tasks?page=1&page_size=30&status=downloading')
```

**响应 200**

```json
{
  "items": [
    {
      "info_hash": "c9e15763f722f23e98a29decdfae341b98d53056",
      "name": "Example.S01.1080p",
      "size": 4294967296,
      "progress": 0.42,
      "status": "downloading",
      "download_rate": 5242880,
      "remaining_seconds": 600,
      "added_at": 1761744000,
      "updated_at": 1761744600,
      "status_code": 1,
      "target_cid": "2876543210987654321",
      "can_pause": true,
      "can_resume": false,
      "can_restart": false,
      "file_id": "",
      "error": "",
      "move_status": 0
    }
  ],
  "page": 1,
  "page_size": 30,
  "page_count": 1,
  "total": 1,
  "account": {
    "mode": "main",
    "id": 1,
    "name": "主账号"
  }
}
```

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `account` | AccountSummary |  |
| `account.cloud_name` | string | CD2 中的云盘名称（挂载根下第一层目录） |
| `account.id` | integer(int64) | 实际使用的账号 ID |
| `account.mode` | "main" / "backup" | 实际使用的账号类型：main 或 backup |
| `account.name` | string | 名称 |
| `items` | OfflineTask[] |  |
| `items[].added_at` | integer(int64) | 添加时间（Unix 秒） |
| `items[].can_pause` | boolean | 当前是否可暂停 |
| `items[].can_restart` | boolean | 当前是否可重试 |
| `items[].can_resume` | boolean | 当前是否可恢复 |
| `items[].download_rate` | integer(int64) | 下载速度，字节/秒 |
| `items[].error` | string | 失败原因（原始业务错误） |
| `items[].file_id` | string | 完成后在 115 中的文件或目录 ID |
| `items[].info_hash` | string | 115 离线任务 info hash（来自离线任务列表） |
| `items[].move_status` | integer |  |
| `items[].name` | string | 名称 |
| `items[].progress` | number | 下载进度，0–1 的小数 |
| `items[].remaining_seconds` | integer(int64) | 预计剩余秒数 |
| `items[].size` | integer(int64) | 字节数 |
| `items[].status` | "unknown" / "failed" / "stopped" / "downloading" / "moving" / "completed" / "move_failed" | 归一化状态：downloading 下载中、completed 完成、failed 失败、stopped 已暂停、moving 正在移动到目标目录、move_failed 移动失败、unknown |
| `items[].status_code` | integer | 115 原始状态码 |
| `items[].target_cid` | string | 转存目标目录的 115 节点 ID；主账号省略时使用账号默认转存目录，备用账号必须提供 |
| `items[].updated_at` | integer(int64) | 最后更新时间（Unix 秒） |
| `page` | integer | 页码，从 1 开始 |
| `page_count` | integer | 总页数 |
| `page_size` | integer | 每页条数 |
| `total` | integer(int64) | 符合条件的总条数 |

### GET `/api/115/recyclebin`

<a id="get-api-115-recyclebin"></a>

读取回收站。 读取目标账号的回收站列表。

**参数**

| 名称 | 位置 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- | --- |
| `limit` | query | integer |  | 本次最多返回的条数 |
| `offset` | query | integer |  | 跳过的条数，从 0 开始 |

**调用**

```js
const res = await ctx.api.get('/api/115/recyclebin')
```

**响应 200**（按契约结构生成的示例值）

```json
{}
```

响应为宿主或上游服务原样透传的 JSON，字段可能随上游变化；以 HTTP 2xx 判断成功。

### POST `/api/115/recyclebin/clear`

<a id="post-api-115-recyclebin-clear"></a>

清空回收站。 清空目标账号的回收站。

**请求体（JSON）**

| 字段 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- |
| `password` | string |  |  |

**调用**

```js
const res = await ctx.api.post('/api/115/recyclebin/clear', {
  "password": "<password>"
})
```

**响应 200**（按契约结构生成的示例值）

```json
{}
```

响应为宿主或上游服务原样透传的 JSON，字段可能随上游变化；以 HTTP 2xx 判断成功。

### POST `/api/115/recyclebin/delete`

<a id="post-api-115-recyclebin-delete"></a>

彻底删除回收站文件。 彻底删除 115 回收站中的文件。id 或 ids 二选一；开启回收站密码时提供 password。响应为 115 原始结果透传。

**请求体（JSON）**

| 字段 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- |
| `id` | string |  |  |
| `ids` | string[] |  |  |
| `password` | string |  |  |

**调用**

```js
const res = await ctx.api.post('/api/115/recyclebin/delete', {
  "ids": [
    "2876543210987654399"
  ],
  "password": ""
})
```

**响应 200**（按契约结构生成的示例值）

```json
{}
```

响应为宿主或上游服务原样透传的 JSON，字段可能随上游变化；以 HTTP 2xx 判断成功。

### POST `/api/115/recyclebin/revert`

<a id="post-api-115-recyclebin-revert"></a>

还原回收站文件。 还原回收站中的文件。

**请求体（JSON）**

| 字段 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- |
| `id` | string |  |  |
| `ids` | string[] |  |  |

**调用**

```js
const res = await ctx.api.post('/api/115/recyclebin/revert', {
  "id": "<id>",
  "ids": [
    ""
  ]
})
```

**响应 200**（按契约结构生成的示例值）

```json
{}
```

响应为宿主或上游服务原样透传的 JSON，字段可能随上游变化；以 HTTP 2xx 判断成功。

### GET `/api/115/share-notlogin-quota`

<a id="get-api-115-share-notlogin-quota"></a>

查询免登录转存额度。 查询目标账号的免登录转存配额。

**调用**

```js
const res = await ctx.api.get('/api/115/share-notlogin-quota')
```

**响应 200**（按契约结构生成的示例值）

```json
{}
```

响应为宿主或上游服务原样透传的 JSON，字段可能随上游变化；以 HTTP 2xx 判断成功。

### POST `/api/115/share/receive`

<a id="post-api-115-share-receive"></a>

转存 115 分享。 把 115 分享转存到账号目录。share_url 与 share_code 二选一；提取码可放在链接 password= 或 receive_code。主账号省略 target_cid 时转存到默认转存目录，备用账号必须给出。只表示 115 已接受转存，不代表整理完成。

**请求体（JSON）**

| 字段 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- |
| `account` | AccountSelector |  | 写操作的账号选择器。`backup` 必须给出 `id`；`backup_pool` 只允许创建离线或转存时由宿主选定账号，不允许修改已有离线任务。 |
| `account.id` | integer(int64) |  | 备用账号 ID，来自 GET /api/115/accounts/options |
| `account.mode` | "main" / "backup" / "backup_pool" |  | main 主账号（默认）；backup 指定备用账号（需 id）；backup_pool 由宿主挑选备用账号（仅创建离线或转存） |
| `file_ids` | string[] |  | 只处理这些 115 文件/目录 ID；省略时处理全部 |
| `receive_code` | string |  | 分享提取码（链接 password= 的值） |
| `share_code` | string |  | 115 分享码（分享链接 /s/ 之后、? 之前的部分） |
| `share_url` | string(uri) |  | 完整 115 分享链接，可带 ?password=提取码 |
| `target_cid` | string |  | 转存目标目录的 115 节点 ID；主账号省略时使用账号默认转存目录，备用账号必须提供 |

**调用**

```js
const res = await ctx.api.post('/api/115/share/receive', {
  "share_url": "https://115cdn.com/s/sw3abcd1234?password=x1y2",
  "target_cid": "2876543210987654321",
  "account": {
    "mode": "main"
  }
})
```

**响应 200**

```json
{
  "success": true,
  "share_code": "sw3abcd1234",
  "target_cid": "2876543210987654321",
  "account": {
    "mode": "main",
    "id": 1,
    "name": "主账号"
  }
}
```

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `account` | AccountSummary |  |
| `account.cloud_name` | string | CD2 中的云盘名称（挂载根下第一层目录） |
| `account.id` | integer(int64) | 实际使用的账号 ID |
| `account.mode` | "main" / "backup" | 实际使用的账号类型：main 或 backup |
| `account.name` | string | 名称 |
| `share_code` | string | 115 分享码（分享链接 /s/ 之后、? 之前的部分） |
| `success` | true | 是否成功；成功响应中恒为 true，失败时返回 4xx/5xx 与 error |
| `target_cid` | string | 转存目标目录的 115 节点 ID；主账号省略时使用账号默认转存目录，备用账号必须提供 |

### GET `/api/115/shares`

<a id="get-api-115-shares"></a>

列出分享链接。 读取目标账号创建的分享列表。

**参数**

| 名称 | 位置 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- | --- |
| `limit` | query | integer |  | 本次最多返回的条数 |
| `offset` | query | integer |  | 跳过的条数，从 0 开始 |
| `show_cancel_share` | query | boolean |  |  |

**调用**

```js
const res = await ctx.api.get('/api/115/shares')
```

**响应 200**（按契约结构生成的示例值）

```json
{
  "count": 0,
  "limit": 20,
  "list": [
    {}
  ],
  "offset": 0
}
```

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `count` | integer |  |
| `limit` | integer | 本次最多返回的条数 |
| `list` | object[] |  |
| `offset` | integer | 跳过的条数，从 0 开始 |

### GET `/api/115/shares/{share_code}`

<a id="get-api-115-shares-share-code"></a>

读取分享详情。 读取一条分享的详情。

**参数**

| 名称 | 位置 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- | --- |
| `share_code` | path | string | 是 | 115 分享码（分享链接 /s/ 之后、? 之前的部分） |

**调用**

```js
const res = await ctx.api.get('/api/115/shares/sw3abcd1234')
```

**响应 200**（按契约结构生成的示例值）

```json
{}
```

响应为宿主或上游服务原样透传的 JSON，字段可能随上游变化；以 HTTP 2xx 判断成功。

### DELETE `/api/115/shares/{share_code}`

<a id="delete-api-115-shares-share-code"></a>

删除分享。 删除一条分享链接。

**参数**

| 名称 | 位置 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- | --- |
| `share_code` | path | string | 是 | 115 分享码（分享链接 /s/ 之后、? 之前的部分） |
| `action` | query | string |  |  |

**调用**

```js
const res = await ctx.api.delete('/api/115/shares/sw3abcd1234')
```

**响应 200**（按契约结构生成的示例值）

```json
{
  "action": null,
  "success": true
}
```

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `action` | any |  |
| `success` | boolean | 是否成功；成功响应中恒为 true，失败时返回 4xx/5xx 与 error |

### GET `/api/115/shares/{share_code}/access-users`

<a id="get-api-115-shares-share-code-access-users"></a>

读取分享领取记录。 读取一条分享的领取用户记录。

**参数**

| 名称 | 位置 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- | --- |
| `share_code` | path | string | 是 | 115 分享码（分享链接 /s/ 之后、? 之前的部分） |

**调用**

```js
const res = await ctx.api.get('/api/115/shares/sw3abcd1234/access-users')
```

**响应 200**（按契约结构生成的示例值）

```json
{}
```

响应为宿主或上游服务原样透传的 JSON，字段可能随上游变化；以 HTTP 2xx 判断成功。

### POST `/api/115/shares/{share_code}/activate`

<a id="post-api-115-shares-share-code-activate"></a>

激活分享。 激活一条分享。

**参数**

| 名称 | 位置 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- | --- |
| `share_code` | path | string | 是 | 115 分享码（分享链接 /s/ 之后、? 之前的部分） |

**调用**

```js
const res = await ctx.api.post('/api/115/shares/sw3abcd1234/activate', {})
```

**响应 200**（按契约结构生成的示例值）

```json
{}
```

响应为宿主或上游服务原样透传的 JSON，字段可能随上游变化；以 HTTP 2xx 判断成功。

### GET `/api/115/shares/{share_code}/download-details`

<a id="get-api-115-shares-share-code-download-details"></a>

读取分享下载明细。 读取一条分享的下载明细。

**参数**

| 名称 | 位置 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- | --- |
| `share_code` | path | string | 是 | 115 分享码（分享链接 /s/ 之后、? 之前的部分） |
| `end_time` | query | string |  | 结束时间 |
| `limit` | query | integer |  | 本次最多返回的条数 |
| `offset` | query | integer |  | 跳过的条数，从 0 开始 |
| `start_time` | query | string |  | 开始时间 |

**调用**

```js
const res = await ctx.api.get('/api/115/shares/sw3abcd1234/download-details')
```

**响应 200**（按契约结构生成的示例值）

```json
{}
```

响应为宿主或上游服务原样透传的 JSON，字段可能随上游变化；以 HTTP 2xx 判断成功。

### POST `/api/115/shares/{share_code}/renew`

<a id="post-api-115-shares-share-code-renew"></a>

续期分享。 续期一条分享。

**参数**

| 名称 | 位置 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- | --- |
| `share_code` | path | string | 是 | 115 分享码（分享链接 /s/ 之后、? 之前的部分） |

**请求体（JSON）**

| 字段 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- |
| `activate_first` | boolean |  |  |
| `auto_renewal` | boolean |  |  |
| `share_duration` | integer |  |  |

**调用**

```js
const res = await ctx.api.post('/api/115/shares/sw3abcd1234/renew', {
  "activate_first": true,
  "auto_renewal": true,
  "share_duration": 0
})
```

**响应 200**（按契约结构生成的示例值）

```json
{
  "activate": {},
  "activate_first": true,
  "after": {},
  "after_error": null,
  "share_code": "sw3abcd1234",
  "share_duration": 0,
  "success": true,
  "update": {}
}
```

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `activate` | object |  |
| `activate_first` | boolean |  |
| `after` | object |  |
| `after_error` | any |  |
| `share_code` | any | 115 分享码（分享链接 /s/ 之后、? 之前的部分） |
| `share_duration` | integer |  |
| `success` | boolean | 是否成功；成功响应中恒为 true，失败时返回 4xx/5xx 与 error |
| `update` | object |  |

### POST `/api/115/shares/{share_code}/update`

<a id="post-api-115-shares-share-code-update"></a>

更新分享设置。 更新一条分享的有效期等设置。

**参数**

| 名称 | 位置 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- | --- |
| `share_code` | path | string | 是 | 115 分享码（分享链接 /s/ 之后、? 之前的部分） |

**调用**

```js
const res = await ctx.api.post('/api/115/shares/sw3abcd1234/update', {})
```

**响应 200**（按契约结构生成的示例值）

```json
{}
```

响应为宿主或上游服务原样透传的 JSON，字段可能随上游变化；以 HTTP 2xx 判断成功。

### GET `/api/115/status`

<a id="get-api-115-status"></a>

查询 115 账号状态。 读取目标账号的在线状态。

**调用**

```js
const res = await ctx.api.get('/api/115/status')
```

**响应 200**（按契约结构生成的示例值）

```json
{
  "api_blocked": true,
  "error": "<error>",
  "logged_in": true,
  "user_info": {
    "avatar_local": "<avatar_local>",
    "avatar_url": "<avatar_url>",
    "is_vip": true,
    "space_total": 0,
    "space_used": 0,
    "user_id": "<user_id>",
    "user_name": "<user_name>"
  }
}
```

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `api_blocked` | boolean |  |
| `error` | string | 失败原因（原始业务错误） |
| `logged_in` | boolean |  |
| `user_info` | object |  |
| `user_info.avatar_local` | string |  |
| `user_info.avatar_url` | string |  |
| `user_info.is_vip` | boolean |  |
| `user_info.space_total` | integer |  |
| `user_info.space_used` | integer |  |
| `user_info.user_id` | string |  |
| `user_info.user_name` | string |  |

## CD2

### GET `/api/browse`

<a id="get-api-browse"></a>

浏览 CD2。 按 CD2 路径（不含挂载前缀）浏览 CloudDrive2。

**参数**

| 名称 | 位置 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- | --- |
| `path` | query | string |  | 宿主绝对 Linux 路径；位于 CD2 挂载路径下时由 CD2 处理 |

**调用**

```js
const res = await ctx.api.get('/api/browse?path=/115/电影')
```

**响应 200**

```json
{
  "path": "/115/电影",
  "files": [
    {
      "name": "Example (2024)",
      "path": "/115/电影/Example (2024)",
      "is_dir": true,
      "size": 0
    }
  ]
}
```

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `files` | CD2Entry[] |  |
| `files[].is_dir` | boolean | 是否为目录 |
| `files[].name` | string | 名称 |
| `files[].path` | string | CD2 路径（不含挂载前缀） |
| `files[].size` | integer(int64) | 字节数 |
| `path` | string | 宿主绝对 Linux 路径；位于 CD2 挂载路径下时由 CD2 处理 |

### GET `/api/cd2/clouds`

<a id="get-api-cd2-clouds"></a>

列出 CD2 云盘。 列出 CD2 中已挂载的云盘。path 为 CD2 路径，加上系统设置中的 CD2 挂载前缀即为宿主路径。

**调用**

```js
const res = await ctx.api.get('/api/cd2/clouds')
```

**响应 200**

```json
{
  "clouds": [
    {
      "name": "115",
      "path": "/115"
    }
  ]
}
```

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `clouds` | CD2Cloud[] |  |
| `clouds[].name` | string | 名称 |
| `clouds[].path` | string | 宿主绝对 Linux 路径；位于 CD2 挂载路径下时由 CD2 处理 |

## cache

### GET `/api/cache/magnet/changes`

<a id="get-api-cache-magnet-changes"></a>

按时间窗口增量查询磁力和 ED2K 缓存。 API 3.5；按 updated_at/id 升序续读，后端按时间范围过滤且不全量计数。窗口下界包含、上界排除。完整空结果可以推进基线；错误、未读完或游标不前进时必须保留原基线。

**参数**

| 名称 | 位置 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- | --- |
| `keyword` | query | string | 是 | 必填番号/关键词；标题或文件名的宽匹配，调用方仍需精确匹配。 |
| `since` | query | string |  | 包含下界，整秒 RFC3339；省略从 1970-01-01 开始。 |
| `until` | query | string |  | 排他上界，整秒 RFC3339；省略由宿主固定为当前整秒。续页必须沿用。 |
| `cursor_time` | query | string |  | 上一页的更新时间，与 cursor_id 一起传入。 |
| `cursor_id` | query | integer |  | 上一页最后一条记录 ID；不传为首次读取。 |
| `limit` | query | integer |  | 每页条数 1–500，默认 100；没有 total 或 OFFSET。 |

**调用**

```js
const res = await ctx.api.get('/api/cache/magnet/changes?keyword=SSIS-001&since=2026-01-01T00%3A00%3A00Z&until=2026-01-02T00%3A00%3A00Z&limit=100')
```

**响应 200**

```json
{
  "items": [],
  "until": "2026-01-02T00:00:00Z",
  "complete": true
}
```

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `complete` | boolean | 窗口已读完；空结果也可能为 true。 |
| `cursor_id` | integer |  |
| `cursor_time` | string(date-time) |  |
| `items` | MagnetCacheChangeItem[] |  |
| `items[].created_at` | string | 创建时间（RFC 3339） |
| `items[].file_name` | string | 解析出的文件名 |
| `items[].id` | integer |  |
| `items[].info_hash` | string | 磁力为 BTIH；ED2K 为 MD4，不能把 MD4 拼成磁力。 |
| `items[].link_type` | "magnet" / "ed2k" |  |
| `items[].magnet_link` | string | 原始磁力或 ED2K 链接；ED2K 原样提交 115。 |
| `items[].source` | string |  |
| `items[].source_detail` | string | 来源详情 |
| `items[].title` | string | 标题 |
| `items[].updated_at` | string | 更新时间（RFC 3339） |
| `until` | string(date-time) | 本次固定窗口的排他上界；只有 complete=true 才能作为下一次基线。 |

## 看板与历史

### GET `/api/dashboard/emby-latest`

<a id="get-api-dashboard-emby-latest"></a>

读取看板最新媒体。 读取看板最新入库媒体。

**参数**

| 名称 | 位置 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- | --- |
| `limit` | query | integer |  | 本次最多返回的条数 |
| `proxy_id` | query | integer |  | Emby 实例 ID，来自 GET /api/plugin-host/emby/instances；省略使用默认实例 |

**调用**

```js
const res = await ctx.api.get('/api/dashboard/emby-latest')
```

**响应 200**（按契约结构生成的示例值）

```json
[
  null
]
```

响应为宿主或上游服务原样透传的 JSON，字段可能随上游变化；以 HTTP 2xx 判断成功。

### GET `/api/dashboard/library`

<a id="get-api-dashboard-library"></a>

读取看板媒体库。 读取看板媒体库视图。

**参数**

| 名称 | 位置 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- | --- |
| `limit` | query | integer |  | 本次最多返回的条数 |

**调用**

```js
const res = await ctx.api.get('/api/dashboard/library')
```

**响应 200**（按契约结构生成的示例值）

```json
{
  "latest_movies": [
    {
      "added_at": "2026-10-29T21:30:00+08:00",
      "id": 0,
      "name": "<name>",
      "poster": "<poster>",
      "source_path": "<source_path>"
    }
  ],
  "total": 0
}
```

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `latest_movies` | object[] | 最新入库的电影 |
| `latest_movies[].added_at` | string(date-time) | 入库时间 |
| `latest_movies[].id` | integer |  |
| `latest_movies[].name` | string | 电影名称 |
| `latest_movies[].poster` | string | 海报URL |
| `latest_movies[].source_path` | string | 源路径 |
| `total` | integer | 总入库数 |

### GET `/api/dashboard/quick-stats`

<a id="get-api-dashboard-quick-stats"></a>

读取看板快报。 读取看板快速统计。

**参数**

| 名称 | 位置 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- | --- |
| `proxy_id` | query | integer |  | Emby 实例 ID，来自 GET /api/plugin-host/emby/instances；省略使用默认实例 |

**调用**

```js
const res = await ctx.api.get('/api/dashboard/quick-stats')
```

**响应 200**（按契约结构生成的示例值）

```json
{
  "driver115": {
    "account_count": 0,
    "api_calls_today": 0,
    "space_used": "<space_used>"
  },
  "metrics": {
    "error_count": 0,
    "file_growth": [
      {
        "date": "<date>",
        "label": "<label>",
        "strm": 0
      }
    ],
    "strm_today": 0,
    "strm_total": 0,
    "sync_24h": 0
  },
  "redirect": {
    "playing": 0,
    "playing_now": [
      {
        "avatar_url": "<avatar_url>",
        "item_id": "<item_id>",
        "overview": "<overview>",
        "poster": "<poster>",
        "progress": 0,
        "rating": 0,
        "source": "<source>",
        "start_time": "2026-10-29T21:30:00+08:00",
        "title": "<title>",
        "type": "<type>",
        "user": "<user>",
        "user_id": "<user_id>",
        "year": 0
      }
    ],
    "today": 0,
    "total": 0
  }
}
```

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `driver115` | object |  |
| `driver115.account_count` | integer | 账号总数 |
| `driver115.api_calls_today` | integer | 今日API调用 |
| `driver115.space_used` | string | 空间使用 |
| `metrics` | object |  |
| `metrics.error_count` | integer | 错误数量 |
| `metrics.file_growth` | object[] | 最近七天新增趋势（从旧到新） |
| `metrics.file_growth[].date` | string |  |
| `metrics.file_growth[].label` | string |  |
| `metrics.file_growth[].strm` | integer |  |
| `metrics.strm_today` | integer | STRM 今日新增 |
| `metrics.strm_total` | integer | STRM 文件总数 |
| `metrics.sync_24h` | integer | 24小时同步 |
| `redirect` | object |  |
| `redirect.playing` | integer | 正在播放数 |
| `redirect.playing_now` | object[] | 正在播放的内容 |
| `redirect.playing_now[].avatar_url` | string | 用户头像 |
| `redirect.playing_now[].item_id` | string | Emby 媒体项 ID，用于同一播放去重 |
| `redirect.playing_now[].overview` | string | 简介 |
| `redirect.playing_now[].poster` | string | 封面图URL |
| `redirect.playing_now[].progress` | number | 播放进度 (0-100) |
| `redirect.playing_now[].rating` | number | 评分 |
| `redirect.playing_now[].source` | string | 来源：EMBY |
| `redirect.playing_now[].start_time` | string(date-time) | 开始时间 |
| `redirect.playing_now[].title` | string | 标题 |
| `redirect.playing_now[].type` | string | 类型：Movie/Series/Episode |
| `redirect.playing_now[].user` | string | 用户 |
| `redirect.playing_now[].user_id` | string | 用户ID |
| `redirect.playing_now[].year` | integer | 年份 |
| `redirect.today` | integer | 今日播放数 |
| `redirect.total` | integer | 总播放数 |

### GET `/api/dashboard/resource-center-stats`

<a id="get-api-dashboard-resource-center-stats"></a>

读取资源中心统计。 读取资源中心统计。

**调用**

```js
const res = await ctx.api.get('/api/dashboard/resource-center-stats')
```

**响应 200**（按契约结构生成的示例值）

```json
{
  "subscribed_movie_count": 0,
  "subscribed_tv_count": 0,
  "tg_resource_count": 0
}
```

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `subscribed_movie_count` | integer |  |
| `subscribed_tv_count` | integer |  |
| `tg_resource_count` | integer |  |

### GET `/api/dashboard/stats`

<a id="get-api-dashboard-stats"></a>

读取看板统计。 读取看板汇总统计。

**参数**

| 名称 | 位置 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- | --- |
| `details_only` | query | boolean |  |  |
| `limit` | query | integer |  | 本次最多返回的条数 |
| `proxy_id` | query | integer |  | Emby 实例 ID，来自 GET /api/plugin-host/emby/instances；省略使用默认实例 |

**调用**

```js
const res = await ctx.api.get('/api/dashboard/stats')
```

**响应 200**（按契约结构生成的示例值）

```json
{
  "driver115": {
    "account_count": 0,
    "api_calls_today": 0,
    "space_used": "<space_used>"
  },
  "library": {
    "latest_movies": [
      {
        "added_at": "2026-10-29T21:30:00+08:00",
        "id": 0,
        "name": "<name>",
        "poster": "<poster>",
        "source_path": "<source_path>"
      }
    ],
    "total": 0
  },
  "metrics": {
    "error_count": 0,
    "file_growth": [
      {
        "date": "<date>",
        "label": "<label>",
        "strm": 0
      }
    ],
    "strm_today": 0,
    "strm_total": 0,
    "sync_24h": 0
  },
  "recentActivity": [
    {
      "created_at": "2026-10-29T21:30:00+08:00",
      "id": 0,
      "message": "<message>",
      "type": "<type>"
    }
  ],
  "recentSyncLogs": [
    {
      "created_at": "2026-10-29T21:30:00+08:00",
      "id": 0,
      "level": "<level>",
      "message": "<message>",
      "source": "<source>"
    }
  ],
  "redirect": {
    "playing": 0,
    "playing_now": [
      {
        "avatar_url": "<avatar_url>",
        "item_id": "<item_id>",
        "overview": "<overview>",
        "poster": "<poster>",
        "progress": 0,
        "rating": 0,
        "source": "<source>",
        "start_time": "2026-10-29T21:30:00+08:00",
        "title": "<title>",
        "type": "<type>",
        "user": "<user>",
        "user_id": "<user_id>",
        "year": 0
      }
    ],
    "today": 0,
    "total": 0
  },
  "syncChart": {
    "labels": [
      ""
    ],
    "values": [
      0
    ]
  }
}
```

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `driver115` | object |  |
| `driver115.account_count` | integer | 账号总数 |
| `driver115.api_calls_today` | integer | 今日API调用 |
| `driver115.space_used` | string | 空间使用 |
| `library` | object |  |
| `library.latest_movies` | object[] | 最新入库的电影 |
| `library.latest_movies[].added_at` | string(date-time) | 入库时间 |
| `library.latest_movies[].id` | integer |  |
| `library.latest_movies[].name` | string | 电影名称 |
| `library.latest_movies[].poster` | string | 海报URL |
| `library.latest_movies[].source_path` | string | 源路径 |
| `library.total` | integer | 总入库数 |
| `metrics` | object |  |
| `metrics.error_count` | integer | 错误数量 |
| `metrics.file_growth` | object[] | 最近七天新增趋势（从旧到新） |
| `metrics.file_growth[].date` | string |  |
| `metrics.file_growth[].label` | string |  |
| `metrics.file_growth[].strm` | integer |  |
| `metrics.strm_today` | integer | STRM 今日新增 |
| `metrics.strm_total` | integer | STRM 文件总数 |
| `metrics.sync_24h` | integer | 24小时同步 |
| `recentActivity` | object[] |  |
| `recentActivity[].created_at` | string(date-time) | 创建时间（RFC 3339） |
| `recentActivity[].id` | integer |  |
| `recentActivity[].message` | string | 消息 |
| `recentActivity[].type` | string | 类型：sync, error, info |
| `recentSyncLogs` | object[] |  |
| `recentSyncLogs[].created_at` | string(date-time) | 创建时间（RFC 3339） |
| `recentSyncLogs[].id` | integer |  |
| `recentSyncLogs[].level` | string | 日志级别 |
| `recentSyncLogs[].message` | string | 消息 |
| `recentSyncLogs[].source` | string | 来源：EMBY / STRM |
| `redirect` | object |  |
| `redirect.playing` | integer | 正在播放数 |
| `redirect.playing_now` | object[] | 正在播放的内容 |
| `redirect.playing_now[].avatar_url` | string | 用户头像 |
| `redirect.playing_now[].item_id` | string | Emby 媒体项 ID，用于同一播放去重 |
| `redirect.playing_now[].overview` | string | 简介 |
| `redirect.playing_now[].poster` | string | 封面图URL |
| `redirect.playing_now[].progress` | number | 播放进度 (0-100) |
| `redirect.playing_now[].rating` | number | 评分 |
| `redirect.playing_now[].source` | string | 来源：EMBY |
| `redirect.playing_now[].start_time` | string(date-time) | 开始时间 |
| `redirect.playing_now[].title` | string | 标题 |
| `redirect.playing_now[].type` | string | 类型：Movie/Series/Episode |
| `redirect.playing_now[].user` | string | 用户 |
| `redirect.playing_now[].user_id` | string | 用户ID |
| `redirect.playing_now[].year` | integer | 年份 |
| `redirect.today` | integer | 今日播放数 |
| `redirect.total` | integer | 总播放数 |
| `syncChart` | object |  |
| `syncChart.labels` | string[] | 日期标签 |
| `syncChart.values` | integer[] | 同步数量 |

### GET `/api/dashboard/sync-chart`

<a id="get-api-dashboard-sync-chart"></a>

读取同步图表。 读取同步趋势图表数据。

**调用**

```js
const res = await ctx.api.get('/api/dashboard/sync-chart')
```

**响应 200**（按契约结构生成的示例值）

```json
{
  "labels": [
    ""
  ],
  "values": [
    0
  ]
}
```

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `labels` | string[] | 日期标签 |
| `values` | integer[] | 同步数量 |

### GET `/api/history`

<a id="get-api-history"></a>

读取操作历史。 读取宿主操作历史记录。

**参数**

| 名称 | 位置 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- | --- |
| `limit` | query | integer |  | 本次最多返回的条数 |
| `offset` | query | integer |  | 跳过的条数，从 0 开始 |
| `type` | query | string |  |  |

**调用**

```js
const res = await ctx.api.get('/api/history')
```

**响应 200**（按契约结构生成的示例值）

```json
{
  "limit": 20,
  "offset": 0,
  "records": [
    {
      "created_at": "2026-10-29T21:30:00+08:00",
      "deleted": 0,
      "details": "<details>",
      "duration": 0,
      "failed": 0,
      "id": 0,
      "rule_id": 1,
      "rule_name": "<rule_name>",
      "success": 0,
      "type": "<type>"
    }
  ],
  "total": 0
}
```

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `limit` | any | 本次最多返回的条数 |
| `offset` | any | 跳过的条数，从 0 开始 |
| `records` | object[] |  |
| `records[].created_at` | string(date-time) | 创建时间（RFC 3339） |
| `records[].deleted` | integer | 删除数量 |
| `records[].details` | string | 详细信息（JSON格式） |
| `records[].duration` | integer | 耗时（毫秒） |
| `records[].failed` | integer | 失败数量 |
| `records[].id` | integer |  |
| `records[].rule_id` | integer | 关联的规则ID |
| `records[].rule_name` | string | 规则名称 |
| `records[].success` | integer | 成功数量 |
| `records[].type` | string |  |
| `total` | integer | 符合条件的总条数 |

### GET `/api/history/stats`

<a id="get-api-history-stats"></a>

读取历史统计。 读取操作历史统计。

**调用**

```js
const res = await ctx.api.get('/api/history/stats')
```

**响应 200**（按契约结构生成的示例值）

```json
{}
```

响应为宿主或上游服务原样透传的 JSON，字段可能随上游变化；以 HTTP 2xx 判断成功。

## Emby

### POST `/api/emby-control/items/{id}/refresh`

<a id="post-api-emby-control-items-id-refresh"></a>

刷新 Emby 媒体。 刷新一个 Emby 媒体的元数据。

**参数**

| 名称 | 位置 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- | --- |
| `id` | path | string | 是 |  |
| `proxy_id` | query | integer |  | Emby 实例 ID，来自 GET /api/plugin-host/emby/instances；省略使用默认实例 |

**请求体（JSON）**

| 字段 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- |
| `image_refresh_mode` | string |  |  |
| `metadata_refresh_mode` | string |  |  |
| `recursive` | boolean |  |  |
| `replace_all_images` | boolean |  |  |
| `replace_all_metadata` | boolean |  |  |

**调用**

```js
const res = await ctx.api.post('/api/emby-control/items/id/refresh', {
  "image_refresh_mode": "<image_refresh_mode>",
  "metadata_refresh_mode": "<metadata_refresh_mode>",
  "recursive": true,
  "replace_all_images": true,
  "replace_all_metadata": true
})
```

**响应 200**（按契约结构生成的示例值）

```json
{}
```

响应为宿主或上游服务原样透传的 JSON，字段可能随上游变化；以 HTTP 2xx 判断成功。

### GET `/api/emby-control/libraries`

<a id="get-api-emby-control-libraries"></a>

读取 Emby 控制媒体库。 读取 Emby 媒体库及同步配置。

**参数**

| 名称 | 位置 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- | --- |
| `proxy_id` | query | integer |  | Emby 实例 ID，来自 GET /api/plugin-host/emby/instances；省略使用默认实例 |

**调用**

```js
const res = await ctx.api.get('/api/emby-control/libraries')
```

**响应 200**（按契约结构生成的示例值）

```json
{}
```

响应为宿主或上游服务原样透传的 JSON，字段可能随上游变化；以 HTTP 2xx 判断成功。

### POST `/api/emby-control/library/refresh`

<a id="post-api-emby-control-library-refresh"></a>

刷新 Emby 媒体库。 刷新 Emby 媒体库。

**参数**

| 名称 | 位置 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- | --- |
| `proxy_id` | query | integer |  | Emby 实例 ID，来自 GET /api/plugin-host/emby/instances；省略使用默认实例 |

**调用**

```js
const res = await ctx.api.post('/api/emby-control/library/refresh', {})
```

**响应 200**（按契约结构生成的示例值）

```json
{}
```

响应为宿主或上游服务原样透传的 JSON，字段可能随上游变化；以 HTTP 2xx 判断成功。

### GET `/api/emby-control/status`

<a id="get-api-emby-control-status"></a>

读取 Emby 控制状态。 读取 Emby 控制模块状态。

**参数**

| 名称 | 位置 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- | --- |
| `proxy_id` | query | integer |  | Emby 实例 ID，来自 GET /api/plugin-host/emby/instances；省略使用默认实例 |

**调用**

```js
const res = await ctx.api.get('/api/emby-control/status')
```

**响应 200**（按契约结构生成的示例值）

```json
{
  "api_key_configured": true,
  "configured": true,
  "error": null,
  "host": null,
  "online": true,
  "ready": true,
  "server_info": {}
}
```

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `api_key_configured` | boolean |  |
| `configured` | boolean |  |
| `error` | any | 失败原因（原始业务错误） |
| `host` | any |  |
| `online` | boolean |  |
| `ready` | boolean |  |
| `server_info` | object |  |

### GET `/api/plugin-host/emby/episodes`

<a id="get-api-plugin-host-emby-episodes"></a>

读取 Emby 缺集。 按 TMDB ID 查询 Emby 中某季已有与缺失的集数，适合订阅补集。

**参数**

| 名称 | 位置 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- | --- |
| `proxy_id` | query | integer |  | Emby 实例 ID，来自 GET /api/plugin-host/emby/instances；省略使用默认实例 |
| `season` | query | integer |  | 季号，0 为特别篇 |
| `tmdb_id` | query | string |  | TMDB 媒体 ID；电影与剧集分别编号，需配合 media_type 使用 |
| `total_episodes` | query | integer |  | 该季总集数，0 表示未知 |

**调用**

```js
const res = await ctx.api.get('/api/plugin-host/emby/episodes?tmdb_id=1399&season=1&total_episodes=10')
```

**响应 200**

```json
{
  "tmdb_id": 1399,
  "season": 1,
  "total_episodes": 10,
  "covered_episodes": "1-3",
  "needed_episodes": "4-10",
  "complete": false,
  "proxy_id": 1
}
```

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `complete` | boolean |  |
| `covered_episodes` | string | 已拥有的集数集合，格式如 "1-3,5" |
| `needed_episodes` | string | 仍需获取的集数集合，格式如 "4-10" |
| `proxy_id` | integer | Emby 实例 ID，来自 GET /api/plugin-host/emby/instances；省略使用默认实例 |
| `season` | integer | 季号，0 为特别篇 |
| `tmdb_id` | integer | TMDB 媒体 ID；电影与剧集分别编号，需配合 media_type 使用 |
| `total_episodes` | integer | 该季总集数，0 表示未知 |

### GET `/api/plugin-host/emby/instances`

<a id="get-api-plugin-host-emby-instances"></a>

列出 Emby 实例。 列出 Emby 实例。多实例时其他 Emby 接口用 proxy_id 指定；id 为 0 的旧版单实例调用时省略 proxy_id。

**调用**

```js
const res = await ctx.api.get('/api/plugin-host/emby/instances')
```

**响应 200**

```json
{
  "items": [
    {
      "id": 1,
      "name": "家里的 Emby",
      "is_default": true,
      "api_key_configured": true
    }
  ]
}
```

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `items` | PluginEmbyInstance[] |  |
| `items[].api_key_configured` | boolean |  |
| `items[].id` | integer(int64) | 持久化实例 ID；旧版单实例配置使用 0，调用其他接口时应省略 `proxy_id`。 |
| `items[].is_default` | boolean | 是否为默认项 |
| `items[].name` | string | 名称 |

### GET `/api/plugin-host/emby/items`

<a id="get-api-plugin-host-emby-items"></a>

查询 Emby 媒体。 使用宿主保存的 Emby 凭据分页搜索安全媒体元数据。宿主明确禁用用户播放数据并丢弃媒体路径、MediaSources 及未列入响应模型的字段；一页最多返回 50 条。

**参数**

| 名称 | 位置 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- | --- |
| `proxy_id` | query | integer(int64) |  | Emby 实例 ID。存在多个实例且宿主未设置有效默认实例时必填；旧版单实例配置省略该参数。 |
| `q` | query | string |  | Emby 搜索词；宿主按 UTF-8 字节安全截取到 200 字节。 |
| `library_id` | query | string |  | 仅列出指定媒体库下的条目；值来自媒体库列表的 `id`。 |
| `type` | query | "Movie" / "Series" / "Episode" / "Video" / "Audio" / "MusicAlbum" / "MusicArtist" / "BoxSet" / "Person" |  | 媒体类型，含 Person；Person 请求由宿主转发至 Emby /Persons |
| `limit` | query | integer |  | 本次最多返回的条数 |
| `offset` | query | integer |  | 跳过的条数，从 0 开始 |
| `sort_by` | query | "date_created" / "name" / "community_rating" |  |  |
| `sort_order` | query | "asc" / "desc" |  |  |

**调用**

```js
const res = await ctx.api.get('/api/plugin-host/emby/items')
```

**响应 200**（按契约结构生成的示例值）

```json
{
  "items": [
    {
      "backdrop_count": 0,
      "community_rating": 0,
      "date_created": "<date_created>",
      "genres": [
        ""
      ],
      "has_primary_image": true,
      "id": "<id>",
      "index_number": 0,
      "name": "<name>",
      "original_title": "<original_title>",
      "overview": "<overview>",
      "parent_id": "<parent_id>",
      "parent_index_number": 0,
      "premiere_date": "<premiere_date>",
      "production_year": 0,
      "provider_ids": {},
      "proxy_id": 1,
      "proxy_name": "<proxy_name>",
      "series_id": "<series_id>",
      "series_name": "<series_name>",
      "sort_name": "<sort_name>",
      "type": "<type>"
    }
  ],
  "limit": 20,
  "offset": 0,
  "total": 0
}
```

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `items` | PluginEmbyItem[] |  |
| `items[].backdrop_count` | integer |  |
| `items[].community_rating` | number |  |
| `items[].date_created` | string |  |
| `items[].genres` | string[] |  |
| `items[].has_primary_image` | boolean |  |
| `items[].id` | string | Emby 媒体 ID |
| `items[].index_number` | integer |  |
| `items[].name` | string | 名称 |
| `items[].original_title` | string | 原始语言标题 |
| `items[].overview` | string | 简介 |
| `items[].parent_id` | string |  |
| `items[].parent_index_number` | integer |  |
| `items[].premiere_date` | string |  |
| `items[].production_year` | integer |  |
| `items[].provider_ids` | object | 外部 ID，如 {"Tmdb":"1399"} |
| `items[].proxy_id` | integer(int64) | Emby 实例 ID，来自 GET /api/plugin-host/emby/instances；省略使用默认实例 |
| `items[].proxy_name` | string |  |
| `items[].series_id` | string |  |
| `items[].series_name` | string |  |
| `items[].sort_name` | string |  |
| `items[].type` | string |  |
| `limit` | integer | 本次最多返回的条数 |
| `offset` | integer | 跳过的条数，从 0 开始 |
| `total` | integer | 符合条件的总条数 |

### GET `/api/plugin-host/emby/items/{id}`

<a id="get-api-plugin-host-emby-items-id"></a>

读取 Emby 媒体详情。 使用宿主保存的 Emby 凭据读取一条安全媒体元数据。返回字段与列表条目相同，不包含路径、MediaSources、用户播放数据或宿主凭据。

**参数**

| 名称 | 位置 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- | --- |
| `id` | path | string | 是 | Emby 媒体条目 ID。 |
| `proxy_id` | query | integer(int64) |  | Emby 实例 ID。存在多个实例且宿主未设置有效默认实例时必填；旧版单实例配置省略该参数。 |

**调用**

```js
const res = await ctx.api.get('/api/plugin-host/emby/items/id')
```

**响应 200**（按契约结构生成的示例值）

```json
{
  "item": {
    "backdrop_count": 0,
    "community_rating": 0,
    "date_created": "<date_created>",
    "genres": [
      ""
    ],
    "has_primary_image": true,
    "id": "<id>",
    "index_number": 0,
    "name": "<name>",
    "original_title": "<original_title>",
    "overview": "<overview>",
    "parent_id": "<parent_id>",
    "parent_index_number": 0,
    "premiere_date": "<premiere_date>",
    "production_year": 0,
    "provider_ids": {},
    "proxy_id": 1,
    "proxy_name": "<proxy_name>",
    "series_id": "<series_id>",
    "series_name": "<series_name>",
    "sort_name": "<sort_name>",
    "type": "<type>"
  }
}
```

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `item` | PluginEmbyItem |  |
| `item.backdrop_count` | integer |  |
| `item.community_rating` | number |  |
| `item.date_created` | string |  |
| `item.genres` | string[] |  |
| `item.has_primary_image` | boolean |  |
| `item.id` | string | Emby 媒体 ID |
| `item.index_number` | integer |  |
| `item.name` | string | 名称 |
| `item.original_title` | string | 原始语言标题 |
| `item.overview` | string | 简介 |
| `item.parent_id` | string |  |
| `item.parent_index_number` | integer |  |
| `item.premiere_date` | string |  |
| `item.production_year` | integer |  |
| `item.provider_ids` | object | 外部 ID，如 {"Tmdb":"1399"} |
| `item.proxy_id` | integer(int64) | Emby 实例 ID，来自 GET /api/plugin-host/emby/instances；省略使用默认实例 |
| `item.proxy_name` | string |  |
| `item.series_id` | string |  |
| `item.series_name` | string |  |
| `item.sort_name` | string |  |
| `item.type` | string |  |

### GET `/api/plugin-host/emby/libraries`

<a id="get-api-plugin-host-emby-libraries"></a>

读取 Emby 媒体库。 使用宿主保存的 Emby 凭据读取媒体库标识、名称和类型。媒体库文件路径及原始 Emby 配置不会返回。

**参数**

| 名称 | 位置 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- | --- |
| `proxy_id` | query | integer(int64) |  | Emby 实例 ID。存在多个实例且宿主未设置有效默认实例时必填；旧版单实例配置省略该参数。 |

**调用**

```js
const res = await ctx.api.get('/api/plugin-host/emby/libraries')
```

**响应 200**（按契约结构生成的示例值）

```json
{
  "items": [
    {
      "id": "<id>",
      "name": "<name>",
      "proxy_id": 1,
      "proxy_name": "<proxy_name>",
      "type": "<type>"
    }
  ]
}
```

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `items` | PluginEmbyLibrary[] |  |
| `items[].id` | string |  |
| `items[].name` | string | 名称 |
| `items[].proxy_id` | integer(int64) | Emby 实例 ID，来自 GET /api/plugin-host/emby/instances；省略使用默认实例 |
| `items[].proxy_name` | string |  |
| `items[].type` | string |  |

### GET `/api/plugin-host/emby/stats`

<a id="get-api-plugin-host-emby-stats"></a>

读取 Emby 统计。 使用宿主保存的 Emby 地址和 API Key 读取媒体总数以及聚合后的用户数、播放中数量。不会返回用户、会话或服务器身份详情。

**参数**

| 名称 | 位置 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- | --- |
| `proxy_id` | query | integer(int64) |  | Emby 实例 ID。存在多个实例且宿主未设置有效默认实例时必填；旧版单实例配置省略该参数。 |

**调用**

```js
const res = await ctx.api.get('/api/plugin-host/emby/stats')
```

**响应 200**（按契约结构生成的示例值）

```json
{
  "configured": true,
  "episode_count": 0,
  "movie_count": 0,
  "online": true,
  "playing_count": 0,
  "proxy_id": 1,
  "proxy_name": "<proxy_name>",
  "series_count": 0,
  "user_count": 0
}
```

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `configured` | true |  |
| `episode_count` | integer |  |
| `movie_count` | integer |  |
| `online` | true |  |
| `playing_count` | integer | 当前正在播放的聚合数量；不返回会话或用户详情。 |
| `proxy_id` | integer(int64) | Emby 实例 ID，来自 GET /api/plugin-host/emby/instances；省略使用默认实例 |
| `proxy_name` | string |  |
| `series_count` | integer |  |
| `user_count` | integer | 用户聚合数量；不返回用户身份。 |

## 插件平台

### GET `/api/extensions/v3/_events`

<a id="get-api-extensions-v3-events"></a>

宿主业务事件目录（events[].types 可订阅的类型）。

**调用**

```js
const res = await ctx.api.get('/api/extensions/v3/_events')
```

**响应 200**（按契约结构生成的示例值）

```json
[
  {
    "description": "<description>",
    "group": "<group>",
    "name": "<name>",
    "type": "<type>"
  }
]
```

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `[].description` | string |  |
| `[].group` | string |  |
| `[].name` | string | 名称 |
| `[].type` | string |  |

### GET `/api/extensions/v3/_notify/channels`

<a id="get-api-extensions-v3-notify-channels"></a>

列出通知渠道及插件可用的格式与功能。 列出通知渠道：是否配置、用户是否允许插件通知、当前是否静默，以及可用格式与功能。发送前据此选择 channels 与 format。

**调用**

```js
const res = await ctx.api.get('/api/extensions/v3/_notify/channels')
```

**响应 200**

```json
[
  {
    "channel": "telegram",
    "name": "Telegram",
    "configured": true,
    "enabled": true,
    "quiet_now": false,
    "deliverable": true,
    "formats": [
      "text",
      "markdown",
      "html"
    ],
    "capabilities": [
      "link_buttons",
      "callback_buttons",
      "images"
    ],
    "max_body_runes": 3500
  },
  {
    "channel": "wecom",
    "name": "企业微信",
    "configured": true,
    "enabled": true,
    "quiet_now": true,
    "deliverable": false,
    "formats": [
      "text",
      "markdown"
    ],
    "capabilities": [
      "link_buttons",
      "images"
    ],
    "max_body_runes": 3500
  }
]
```

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `[].capabilities` | string[] | 支持的功能：link_buttons、callback_buttons、images |
| `[].channel` | "telegram" / "wecom" | 渠道键，用于 channels / overrides |
| `[].configured` | boolean | 宿主已配置该渠道 |
| `[].deliverable` | boolean | 现在发送会到达（configured 且 enabled 且不在静默时段） |
| `[].enabled` | boolean | 用户允许插件通知在该渠道发送 |
| `[].formats` | string[] | 该渠道可渲染的格式 |
| `[].max_body_runes` | integer | markdown/html 正文最大字符数 |
| `[].name` | string | 显示名称 |
| `[].notes` | string | 渠道差异说明 |
| `[].quiet_now` | boolean | 该渠道当前处于静默时段 |

### GET `/api/extensions/v3/{id}`

<a id="get-api-extensions-v3-id"></a>

安装元数据、风险报告及资源基础地址。

**参数**

| 名称 | 位置 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- | --- |
| `id` | path | string | 是 |  |

**调用**

```js
const res = await ctx.api.get('/api/extensions/v3/id')
```

**响应 200**（按契约结构生成的示例值）

```json
{
  "asset_base": "<asset_base>",
  "installation": {
    "delivery": "source",
    "enabled": true,
    "error": "<error>",
    "generation": "<generation>",
    "id": "<id>",
    "installed_at": "2026-10-29T21:30:00+08:00",
    "manifest": {
      "author": "<author>",
      "declared_usage": {},
      "description": "<description>",
      "events": [
        {
          "commands": null,
          "event": null,
          "job": null,
          "prefixes": null
        }
      ],
      "id": "<id>",
      "jobs": [
        {
          "allow_overlap": null,
          "default_schedule": null,
          "entry": null,
          "handler": null,
          "id": null,
          "interval_seconds": null,
          "queue": null,
          "recover": null,
          "timeout_seconds": null,
          "title": null
        }
      ],
      "name": "<name>",
      "schema_version": 3,
      "ui": {
        "entry": "<entry>"
      },
      "version": "<version>"
    },
    "numeric_id": 0,
    "report": {
      "code_digest": "<code_digest>",
      "findings": [
        {
          "action": "<action>",
          "dynamic": true,
          "file": "<file>",
          "kind": "<kind>",
          "line": 0,
          "risk": "read",
          "target": "<target>"
        }
      ],
      "gaps": [
        ""
      ],
      "hosts": [
        {
          "at": "2026-10-29T21:30:00+08:00",
          "error": "<error>",
          "host": "<host>",
          "ips": [
            null
          ]
        }
      ],
      "risk": "read",
      "trusted_extension": true,
      "version": "<version>"
    },
    "revision": "<revision>",
    "state": "installed"
  }
}
```

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `asset_base` | string |  |
| `installation` | ExtensionInstallation |  |
| `installation.delivery` | "source" / "encrypted" |  |
| `installation.enabled` | boolean | 是否启用 |
| `installation.error` | string | 失败原因（原始业务错误） |
| `installation.generation` | string |  |
| `installation.id` | string |  |
| `installation.installed_at` | string(date-time) |  |
| `installation.manifest` | ExtensionManifest |  |
| `installation.manifest.author` | string |  |
| `installation.manifest.declared_usage` | object |  |
| `installation.manifest.description` | string |  |
| `installation.manifest.events` | object[] |  |
| `installation.manifest.id` | string |  |
| `installation.manifest.jobs` | object[] |  |
| `installation.manifest.name` | string | 名称 |
| `installation.manifest.schema_version` | 3 |  |
| `installation.manifest.ui` | object |  |
| `installation.manifest.version` | string |  |
| `installation.numeric_id` | integer |  |
| `installation.report` | ExtensionReport |  |
| `installation.report.code_digest` | string |  |
| `installation.report.findings` | ExtensionFinding[] |  |
| `installation.report.gaps` | string[] |  |
| `installation.report.hosts` | ExtensionHostObservation[] |  |
| `installation.report.risk` | "read" / "write" / "high" / "unknown" |  |
| `installation.report.trusted_extension` | true |  |
| `installation.report.version` | string |  |
| `installation.revision` | string |  |
| `installation.state` | "installed" / "deleting" / "broken" |  |

### POST `/api/extensions/v3/{id}/ai/complete`

<a id="post-api-extensions-v3-id-ai-complete"></a>

复用宿主 AI 生成或翻译文本。 宿主插件 API 3.3。支持宿主 Chat Completions 和 Responses 协议；不执行工具、不共享聊天记录、不返回密钥；并发 4、总时限 150 秒。

**参数**

| 名称 | 位置 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- | --- |
| `id` | path | string | 是 |  |

**请求体（JSON）**

| 字段 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- |
| `context` | any |  | 任意 JSON 数据，作为用户提示的数据上下文；总请求体最多 128 KiB |
| `max_tokens` | integer |  | 默认 4096 |
| `model` | string |  | 模型覆盖；省略使用该提供商配置 |
| `prompt` | string | 是 | 必填任务说明 |
| `provider_id` | string |  | 已配置提供商 ID；省略使用整理场景默认 |
| `system` | string |  | 调用方指令；不会自动附加宿主对话历史或工具 |
| `temperature` | number |  |  |

**调用**

```js
const res = await ctx.api.post('/api/extensions/v3/id/ai/complete', {
  "context": null,
  "max_tokens": 0,
  "model": "<model>",
  "prompt": "<prompt>",
  "provider_id": "<provider_id>",
  "system": "<system>",
  "temperature": 0
})
```

**响应 200**（按契约结构生成的示例值）

```json
{
  "finish_reason": "<finish_reason>",
  "model": "<model>",
  "provider_id": "<provider_id>",
  "text": "<text>",
  "usage": {
    "completion_tokens": 0,
    "prompt_tokens": 0,
    "total_tokens": 0
  }
}
```

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `finish_reason` | string | 原样返回终止原因；调用方须检查截断和内容格式 |
| `model` | string |  |
| `provider_id` | string |  |
| `text` | string |  |
| `usage` | object |  |
| `usage.completion_tokens` | integer |  |
| `usage.prompt_tokens` | integer |  |
| `usage.total_tokens` | integer |  |

### GET `/api/extensions/v3/{id}/ai/providers`

<a id="get-api-extensions-v3-id-ai-providers"></a>

读取可用于插件的 AI 提供商与模型。 宿主插件 API 3.3。仅已启用提供商的 ID/名称/模型/协议和默认选择；不返回 URL、API Key。

**参数**

| 名称 | 位置 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- | --- |
| `id` | path | string | 是 |  |

**调用**

```js
const res = await ctx.api.get('/api/extensions/v3/id/ai/providers')
```

**响应 200**（按契约结构生成的示例值）

```json
{
  "configured": true,
  "default_model": "<default_model>",
  "default_provider_id": "<default_provider_id>",
  "providers": [
    {
      "id": "<id>",
      "model": "<model>",
      "models": [
        ""
      ],
      "name": "<name>",
      "protocol": "<protocol>"
    }
  ]
}
```

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `configured` | boolean |  |
| `default_model` | string |  |
| `default_provider_id` | string |  |
| `providers` | object[] |  |
| `providers[].id` | string |  |
| `providers[].model` | string |  |
| `providers[].models` | string[] |  |
| `providers[].name` | string | 名称 |
| `providers[].protocol` | string |  |

### POST `/api/extensions/v3/{id}/cd2/{method}`

<a id="post-api-extensions-v3-id-cd2-method"></a>

复用宿主 CD2 gRPC 客户端。

**参数**

| 名称 | 位置 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- | --- |
| `id` | path | string | 是 |  |
| `method` | path | "list" / "stat" / "mkdir" / "rename" / "move" / "copy" / "remove" / "search" | 是 |  |

**请求体（JSON）**

| 字段 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- |
| `destination` | string |  |  |
| `force_refresh` | boolean |  |  |
| `fuzzy` | boolean |  | 是否模糊匹配 |
| `name` | string |  | 名称 |
| `parent` | string |  |  |
| `path` | string |  | 宿主绝对 Linux 路径；位于 CD2 挂载路径下时由 CD2 处理 |
| `query` | string |  | 搜索关键词 |

**调用**

```js
const res = await ctx.api.post('/api/extensions/v3/id/cd2/list', {
  "destination": "<destination>",
  "force_refresh": true,
  "fuzzy": true,
  "name": "<name>",
  "parent": "<parent>",
  "path": "/mnt/media/电影",
  "query": "<query>"
})
```

**响应 200**（按契约结构生成的示例值）

```json
{
  "id": "<id>",
  "is_dir": true,
  "modified": "<modified>",
  "name": "<name>",
  "path": "/mnt/media/电影",
  "size": 0
}
```

响应为宿主或上游服务原样透传的 JSON，字段可能随上游变化；以 HTTP 2xx 判断成功。

### POST `/api/extensions/v3/{id}/cookiecloud/{operation}`

<a id="post-api-extensions-v3-id-cookiecloud-operation"></a>

读取或写入宿主本地 CookieCloud。

**参数**

| 名称 | 位置 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- | --- |
| `id` | path | string | 是 |  |
| `operation` | path | "read" / "write" | 是 |  |

**请求体（JSON）**

| 字段 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- |
| `cookies` | ExtensionCookie[] |  |  |
| `cookies[].domain` | string | 是 |  |
| `cookies[].expires_at` | integer |  |  |
| `cookies[].host_only` | boolean | 是 |  |
| `cookies[].http_only` | boolean | 是 |  |
| `cookies[].name` | string | 是 | 名称 |
| `cookies[].path` | string | 是 | 宿主绝对 Linux 路径；位于 CD2 挂载路径下时由 CD2 处理 |
| `cookies[].same_site` | "lax" / "strict" / "none" / "" |  |  |
| `cookies[].secure` | boolean | 是 |  |
| `cookies[].value` | string | 是 |  |
| `domains` | string[] | 是 |  |
| `revision` | string |  |  |

**调用**

```js
const res = await ctx.api.post('/api/extensions/v3/id/cookiecloud/read', {
  "cookies": [
    {
      "domain": "<domain>",
      "expires_at": 0,
      "host_only": true,
      "http_only": true,
      "name": "<name>",
      "path": "/mnt/media/电影",
      "same_site": "lax",
      "secure": true,
      "value": "<value>"
    }
  ],
  "domains": [
    ""
  ],
  "revision": "<revision>"
})
```

**响应 200**（按契约结构生成的示例值）

```json
{
  "cookies": [
    {
      "domain": "<domain>",
      "expires_at": 0,
      "host_only": true,
      "http_only": true,
      "name": "<name>",
      "path": "/mnt/media/电影",
      "same_site": "lax",
      "secure": true,
      "value": "<value>"
    }
  ],
  "domains": [
    {
      "cookie_count": 0,
      "domain": "<domain>"
    }
  ],
  "revision": "<revision>"
}
```

响应为宿主或上游服务原样透传的 JSON，字段可能随上游变化；以 HTTP 2xx 判断成功。

### POST `/api/extensions/v3/{id}/cookies`

<a id="post-api-extensions-v3-id-cookies"></a>

读取 Cookie 或写入明文 Cookie 头。

**参数**

| 名称 | 位置 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- | --- |
| `id` | path | string | 是 |  |

**请求体（JSON）**

| 字段 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- |
| `cookie` | string |  |  |
| `session` | string |  |  |
| `url` | string | 是 |  |

**调用**

```js
const res = await ctx.api.post('/api/extensions/v3/id/cookies', {
  "cookie": "<cookie>",
  "session": "<session>",
  "url": "<url>"
})
```

**响应 200**（按契约结构生成的示例值）

```json
[
  {
    "domain": "<domain>",
    "expires_at": 0,
    "host_only": true,
    "http_only": true,
    "name": "<name>",
    "path": "/mnt/media/电影",
    "same_site": "lax",
    "secure": true,
    "value": "<value>"
  }
]
```

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `[].domain` | string |  |
| `[].expires_at` | integer |  |
| `[].host_only` | boolean |  |
| `[].http_only` | boolean |  |
| `[].name` | string | 名称 |
| `[].path` | string | 宿主绝对 Linux 路径；位于 CD2 挂载路径下时由 CD2 处理 |
| `[].same_site` | "lax" / "strict" / "none" / "" |  |
| `[].secure` | boolean |  |
| `[].value` | string |  |

### POST `/api/extensions/v3/{id}/cookies/import`

<a id="post-api-extensions-v3-id-cookies-import"></a>

导入 CookieCloud 格式 Cookie；保留属性。

**参数**

| 名称 | 位置 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- | --- |
| `id` | path | string | 是 |  |

**请求体（JSON）**

| 字段 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- |
| `cookies` | ExtensionCookie[] | 是 |  |
| `cookies[].domain` | string | 是 |  |
| `cookies[].expires_at` | integer |  |  |
| `cookies[].host_only` | boolean | 是 |  |
| `cookies[].http_only` | boolean | 是 |  |
| `cookies[].name` | string | 是 | 名称 |
| `cookies[].path` | string | 是 | 宿主绝对 Linux 路径；位于 CD2 挂载路径下时由 CD2 处理 |
| `cookies[].same_site` | "lax" / "strict" / "none" / "" |  |  |
| `cookies[].secure` | boolean | 是 |  |
| `cookies[].value` | string | 是 |  |
| `replace` | boolean |  |  |
| `session` | string |  |  |

**调用**

```js
const res = await ctx.api.post('/api/extensions/v3/id/cookies/import', {
  "cookies": [
    {
      "domain": "<domain>",
      "expires_at": 0,
      "host_only": true,
      "http_only": true,
      "name": "<name>",
      "path": "/mnt/media/电影",
      "same_site": "lax",
      "secure": true,
      "value": "<value>"
    }
  ],
  "replace": true,
  "session": "<session>"
})
```

**响应 200**（按契约结构生成的示例值）

```json
{
  "ok": true
}
```

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `ok` | boolean |  |

### POST `/api/extensions/v3/{id}/data/sqlite`

<a id="post-api-extensions-v3-id-data-sqlite"></a>

只读查询插件自有静态 SQLite。 API 3.4；512 MiB 文件、5 秒、最多 200 行及 64 列。文本截取前 8192 字符，BLOB 返回 null，总文本最多 2 MiB。mode=ro&immutable=1，仅用于已关闭并完成 checkpoint 的静态资料库；不接受 SQL、连接串、附件、宿主路径或扩展加载。

**参数**

| 名称 | 位置 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- | --- |
| `id` | path | string | 是 |  |

**请求体（JSON）**

| 字段 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- |
| `columns` | string[] |  |  |
| `equals` | object |  | 列名到精确匹配值；ASCII NOCASE，与参数绑定，不接受 SQL |
| `limit` | integer |  | 本次最多返回的条数 |
| `offset` | integer |  | 跳过的条数，从 0 开始 |
| `source` | string | 是 | 插件自有文件相对路径；只读、完整静态 SQLite，不读取宿主数据库或 WAL |
| `table` | string |  | 留空返回表目录 |

**调用**

```js
const res = await ctx.api.post('/api/extensions/v3/id/data/sqlite', {
  "columns": [
    ""
  ],
  "equals": {},
  "limit": 20,
  "offset": 0,
  "source": "<source>",
  "table": "<table>"
})
```

**响应 200**（按契约结构生成的示例值）

```json
{
  "columns": [
    ""
  ],
  "items": [
    {}
  ],
  "limit": 20,
  "offset": 0,
  "tables": [
    ""
  ]
}
```

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `columns` | string[] |  |
| `items` | object[] |  |
| `limit` | integer | 本次最多返回的条数 |
| `offset` | integer | 跳过的条数，从 0 开始 |
| `tables` | string[] |  |

### POST `/api/extensions/v3/{id}/files`

<a id="post-api-extensions-v3-id-files"></a>

文件操作：相对路径为插件自有（可读写内容）；绝对路径或 cd2: 为宿主路径，仅宿主执行管理操作。宿主 move/copy/remove 进入任务队列。 3.3 新增 hardlink/symlink：只允许宿主本地路径、单个普通源文件与完整 destination，拒绝覆盖和 CD2；硬链接必须同文件系统。rmdir 只删除一个空目录（支持插件自有和宿主本地），非递归且不支持 CD2。

**参数**

| 名称 | 位置 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- | --- |
| `id` | path | string | 是 |  |
| `wait` | query | "0" |  | 宿主移动/复制/删除时 0 表示立即返回 task_id |

**请求体（JSON）**

| 字段 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- |
| `algorithm` | "sha256" |  |  |
| `content` | string |  |  |
| `destination` | string |  | 完整目标路径 |
| `destination_dir` | string |  | 目标目录 |
| `encoding` | "utf8" / "base64" |  |  |
| `length` | integer |  |  |
| `limit` | integer |  | 本次最多返回的条数 |
| `name` | string |  | 重命名的新名称 |
| `offset` | integer |  | 跳过的条数，从 0 开始 |
| `operation` | "read" / "write" / "append" / "list" / "walk" / "stat" / "exists" / "hash" / "mkdir" / "rmdir" / "remove" / "rename" / "move" / "copy" / "hardlink" / "symlink" | 是 |  |
| `overwrite` | boolean |  |  |
| `path` | string |  | 插件相对路径，或宿主绝对 Linux / cd2:/ 路径；内容读写仅限插件相对路径 |
| `paths` | string[] |  | 多个宿主绝对路径 |
| `pattern` | string |  |  |

**调用**

```js
const res = await ctx.api.post('/api/extensions/v3/id/files', {
  "algorithm": "sha256",
  "content": "<content>",
  "destination": "<destination>",
  "destination_dir": "<destination_dir>",
  "encoding": "utf8",
  "length": 0,
  "limit": 20,
  "name": "<name>",
  "offset": 0,
  "operation": "read",
  "overwrite": true,
  "path": "/mnt/media/电影",
  "paths": [
    ""
  ],
  "pattern": "<pattern>"
})
```

**响应 200**（按契约结构生成的示例值）

```json
""
```

响应为宿主或上游服务原样透传的 JSON，字段可能随上游变化；以 HTTP 2xx 判断成功。

### GET `/api/extensions/v3/{id}/files/download`

<a id="get-api-extensions-v3-id-files-download"></a>

下载插件自有文件（相对路径，支持 Range）。

**参数**

| 名称 | 位置 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- | --- |
| `id` | path | string | 是 |  |
| `path` | query | string | 是 | 插件 data/files 下的相对路径；不接受宿主绝对路径 |
| `inline` | query | "1" |  |  |

**调用**

```js
const res = await ctx.api.get('/api/extensions/v3/id/files/download?path=%2Fmnt%2Fmedia%2F%E7%94%B5%E5%BD%B1')
```

**响应 200**：成功响应

### POST `/api/extensions/v3/{id}/files/upload`

<a id="post-api-extensions-v3-id-files-upload"></a>

流式上传到插件自有路径。

**参数**

| 名称 | 位置 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- | --- |
| `id` | path | string | 是 |  |
| `path` | query | string |  | 插件 data/files 下的相对路径；不接受宿主绝对路径 |

**请求体**：application/octet-stream / multipart/form-data

**调用**

```js
const res = await ctx.api.post('/api/extensions/v3/id/files/upload', {})
```

**响应 200**（按契约结构生成的示例值）

```json
{
  "path": "/mnt/media/电影",
  "sha256": "<sha256>",
  "size": 0
}
```

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `path` | string | 宿主绝对 Linux 路径；位于 CD2 挂载路径下时由 CD2 处理 |
| `sha256` | string |  |
| `size` | integer | 字节数 |

### GET `/api/extensions/v3/{id}/hook/{path}`

<a id="get-api-extensions-v3-id-hook-path"></a>

登录态 Webhook：交给清单 http 处理器同步响应。

**参数**

| 名称 | 位置 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- | --- |
| `id` | path | string | 是 |  |
| `path` | path | string | 是 | 宿主绝对 Linux 路径；位于 CD2 挂载路径下时由 CD2 处理 |

**调用**

```js
const res = await ctx.api.get('/api/extensions/v3/id/hook/%2Fmnt%2Fmedia%2F%E7%94%B5%E5%BD%B1')
```

**响应 200**：成功响应

### POST `/api/extensions/v3/{id}/hook/{path}`

<a id="post-api-extensions-v3-id-hook-path"></a>

登录态 Webhook：交给清单 http 处理器同步响应。

**参数**

| 名称 | 位置 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- | --- |
| `id` | path | string | 是 |  |
| `path` | path | string | 是 | 宿主绝对 Linux 路径；位于 CD2 挂载路径下时由 CD2 处理 |

**调用**

```js
const res = await ctx.api.post('/api/extensions/v3/id/hook/%2Fmnt%2Fmedia%2F%E7%94%B5%E5%BD%B1', {})
```

**响应 200**：成功响应

### PUT `/api/extensions/v3/{id}/hook/{path}`

<a id="put-api-extensions-v3-id-hook-path"></a>

登录态 Webhook：交给清单 http 处理器同步响应。

**参数**

| 名称 | 位置 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- | --- |
| `id` | path | string | 是 |  |
| `path` | path | string | 是 | 宿主绝对 Linux 路径；位于 CD2 挂载路径下时由 CD2 处理 |

**调用**

```js
const res = await ctx.api.put('/api/extensions/v3/id/hook/%2Fmnt%2Fmedia%2F%E7%94%B5%E5%BD%B1', {})
```

**响应 200**：成功响应

### PATCH `/api/extensions/v3/{id}/hook/{path}`

<a id="patch-api-extensions-v3-id-hook-path"></a>

登录态 Webhook：交给清单 http 处理器同步响应。

**参数**

| 名称 | 位置 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- | --- |
| `id` | path | string | 是 |  |
| `path` | path | string | 是 | 宿主绝对 Linux 路径；位于 CD2 挂载路径下时由 CD2 处理 |

**调用**

```js
const res = await ctx.api.patch('/api/extensions/v3/id/hook/%2Fmnt%2Fmedia%2F%E7%94%B5%E5%BD%B1', {})
```

**响应 200**：成功响应

### DELETE `/api/extensions/v3/{id}/hook/{path}`

<a id="delete-api-extensions-v3-id-hook-path"></a>

登录态 Webhook：交给清单 http 处理器同步响应。

**参数**

| 名称 | 位置 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- | --- |
| `id` | path | string | 是 |  |
| `path` | path | string | 是 | 宿主绝对 Linux 路径；位于 CD2 挂载路径下时由 CD2 处理 |

**调用**

```js
const res = await ctx.api.delete('/api/extensions/v3/id/hook/%2Fmnt%2Fmedia%2F%E7%94%B5%E5%BD%B1')
```

**响应 200**：成功响应

### POST `/api/extensions/v3/{id}/http`

<a id="post-api-extensions-v3-id-http"></a>

普通 HTTP，持久 Cookie，可选缓存及超时。

**参数**

| 名称 | 位置 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- | --- |
| `id` | path | string | 是 |  |

**请求体（JSON）**

| 字段 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- |
| `body` | string |  |  |
| `cache_seconds` | integer |  |  |
| `headers` | object |  |  |
| `max_bytes` | integer |  |  |
| `method` | string |  |  |
| `proxy` | string |  |  |
| `session` | string |  |  |
| `timeout_seconds` | integer |  |  |
| `url` | string | 是 |  |

**调用**

```js
const res = await ctx.api.post('/api/extensions/v3/id/http', {
  "body": "<body>",
  "cache_seconds": 0,
  "headers": {},
  "max_bytes": 67108864,
  "method": "<method>",
  "proxy": "<proxy>",
  "session": "<session>",
  "timeout_seconds": 120,
  "url": "<url>"
})
```

**响应 200**（按契约结构生成的示例值）

```json
{
  "body": "<body>",
  "body_base64": "<body_base64>",
  "cached": true,
  "data": null,
  "headers": {},
  "path": "/mnt/media/电影",
  "sha256": "<sha256>",
  "size": 0,
  "status": 0,
  "url": "<url>"
}
```

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `body` | string |  |
| `body_base64` | string | response_type=base64 时的原始字节 |
| `cached` | boolean |  |
| `data` | any | response_type=json 时解析后的值 |
| `headers` | object |  |
| `path` | string | save_to 写入的路径 |
| `sha256` | string |  |
| `size` | integer | 字节数 |
| `status` | integer |  |
| `url` | string |  |

### GET `/api/extensions/v3/{id}/icon`

<a id="get-api-extensions-v3-id-icon"></a>

插件清单 icon 图片。

**参数**

| 名称 | 位置 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- | --- |
| `id` | path | string | 是 |  |

**调用**

```js
const res = await ctx.api.get('/api/extensions/v3/id/icon')
```

**响应 200**：成功响应

### POST `/api/extensions/v3/{id}/jobs/{job}`

<a id="post-api-extensions-v3-id-jobs-job"></a>

提交持久任务；相同业务标识和输入返回原任务。

**参数**

| 名称 | 位置 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- | --- |
| `id` | path | string | 是 |  |
| `job` | path | string | 是 |  |

**请求体（JSON）**

| 字段 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- |
| `business_key` | string | 是 |  |
| `input` | any |  |  |

**调用**

```js
const res = await ctx.api.post('/api/extensions/v3/id/jobs/job', {
  "business_key": "<business_key>",
  "input": null
})
```

**响应 200**（按契约结构生成的示例值）

```json
{
  "attempted": true,
  "business_key": "<business_key>",
  "checkpoint": null,
  "created_at": "2026-10-29T21:30:00+08:00",
  "done": 0,
  "error": "<error>",
  "failed": 0,
  "id": "<id>",
  "input": null,
  "job_id": "<job_id>",
  "logs": [
    ""
  ],
  "message": "<message>",
  "progress": 0,
  "result": null,
  "revision": "<revision>",
  "stage": "<stage>",
  "status": "queued",
  "total": 0,
  "updated_at": "2026-10-29T21:30:00+08:00"
}
```

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `attempted` | boolean |  |
| `business_key` | string |  |
| `checkpoint` | any | 插件自己的任意 JSON 业务值；结构由该插件定义。 |
| `created_at` | string(date-time) | 创建时间（RFC 3339） |
| `done` | integer | 任务级已完成项数 |
| `error` | string | 失败原因（原始业务错误） |
| `failed` | integer | 任务级失败项数 |
| `id` | string |  |
| `input` | any | 插件自己的任意 JSON 业务值；结构由该插件定义。 |
| `job_id` | string |  |
| `logs` | string[] |  |
| `message` | string | 给用户看的结果说明 |
| `progress` | number |  |
| `result` | any | 插件自己的任意 JSON 业务值；结构由该插件定义。 |
| `revision` | string |  |
| `stage` | string |  |
| `status` | "queued" / "running" / "failed" / "succeeded" / "cancelled" / "attention_required" |  |
| `total` | integer | 任务级总项数（ctx.task.update 上报）；0 或省略表示只上报百分比 |
| `updated_at` | string(date-time) | 更新时间（RFC 3339） |

### GET `/api/extensions/v3/{id}/listeners`

<a id="get-api-extensions-v3-id-listeners"></a>

独立监听端口及运行状态。

**参数**

| 名称 | 位置 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- | --- |
| `id` | path | string | 是 |  |

**调用**

```js
const res = await ctx.api.get('/api/extensions/v3/id/listeners')
```

**响应 200**（按契约结构生成的示例值）

```json
[
  {
    "address": "<address>",
    "error": "<error>",
    "host": "<host>",
    "id": "<id>",
    "port": 0,
    "running": true,
    "source": "manifest"
  }
]
```

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `[].address` | string |  |
| `[].error` | string | 失败原因（原始业务错误） |
| `[].host` | string |  |
| `[].id` | string |  |
| `[].port` | integer |  |
| `[].running` | boolean |  |
| `[].source` | "manifest" / "runtime" |  |

### POST `/api/extensions/v3/{id}/listeners`

<a id="post-api-extensions-v3-id-listeners"></a>

开启并持久化运行时监听端口。

**参数**

| 名称 | 位置 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- | --- |
| `id` | path | string | 是 |  |

**请求体（JSON）**

| 字段 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- |
| `host` | string |  |  |
| `id` | string | 是 |  |
| `port` | integer | 是 |  |

**调用**

```js
const res = await ctx.api.post('/api/extensions/v3/id/listeners', {
  "host": "<host>",
  "id": "<id>",
  "port": 1
})
```

**响应 200**（按契约结构生成的示例值）

```json
{
  "address": "<address>",
  "error": "<error>",
  "host": "<host>",
  "id": "<id>",
  "port": 0,
  "running": true,
  "source": "manifest"
}
```

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `address` | string |  |
| `error` | string | 失败原因（原始业务错误） |
| `host` | string |  |
| `id` | string |  |
| `port` | integer |  |
| `running` | boolean |  |
| `source` | "manifest" / "runtime" |  |

### DELETE `/api/extensions/v3/{id}/listeners/{listener}`

<a id="delete-api-extensions-v3-id-listeners-listener"></a>

关闭运行时监听端口。

**参数**

| 名称 | 位置 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- | --- |
| `id` | path | string | 是 |  |
| `listener` | path | string | 是 |  |

**调用**

```js
const res = await ctx.api.delete('/api/extensions/v3/id/listeners/listener')
```

**响应 200**（按契约结构生成的示例值）

```json
{
  "ok": true
}
```

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `ok` | boolean |  |

### GET `/api/extensions/v3/{id}/media/badges`

<a id="get-api-extensions-v3-id-media-badges"></a>

列出宿主 badge 包与图片。 宿主插件 API 3.3。不返回配置密钥或外部源认证信息。

**参数**

| 名称 | 位置 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- | --- |
| `id` | path | string | 是 |  |

**调用**

```js
const res = await ctx.api.get('/api/extensions/v3/id/media/badges')
```

**响应 200**（按契约结构生成的示例值）

```json
{
  "active_id": "<active_id>",
  "packs": [
    {
      "badges": [
        {
          "asset_url": "<asset_url>",
          "group_id": "<group_id>",
          "id": "<id>",
          "name": "<name>"
        }
      ],
      "id": "<id>",
      "name": "<name>",
      "revision": "<revision>"
    }
  ]
}
```

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `active_id` | string |  |
| `packs` | object[] |  |
| `packs[].badges` | ExtensionBadge[] |  |
| `packs[].badges[].asset_url` | string | 可供 image 的 source 或 badges/read 使用的固定宿主资源地址 |
| `packs[].badges[].group_id` | string |  |
| `packs[].badges[].id` | string |  |
| `packs[].badges[].name` | string | 名称 |
| `packs[].id` | string |  |
| `packs[].name` | string | 名称 |
| `packs[].revision` | string |  |

### POST `/api/extensions/v3/{id}/media/badges/read`

<a id="post-api-extensions-v3-id-media-badges-read"></a>

读取宿主 badge 图片或保存到插件目录。 宿主插件 API 3.3。通过包 ID、版本和资源键校验，版本失效返回错误。

**参数**

| 名称 | 位置 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- | --- |
| `id` | path | string | 是 |  |

**请求体（JSON）**

| 字段 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- |
| `asset_url` | string | 是 | 必须是宿主 badge 目录返回的 URL，不接受任意 HTTP URL |
| `save_to` | string |  | 可选插件相对路径；省略则返回 body_base64 |

**调用**

```js
const res = await ctx.api.post('/api/extensions/v3/id/media/badges/read', {
  "asset_url": "<asset_url>",
  "save_to": "<save_to>"
})
```

**响应 200**（按契约结构生成的示例值）

```json
{
  "body_base64": "<body_base64>",
  "content_type": "<content_type>",
  "path": "/mnt/media/电影",
  "sha256": "<sha256>",
  "size": 0
}
```

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `body_base64` | string |  |
| `content_type` | string |  |
| `path` | string | 宿主绝对 Linux 路径；位于 CD2 挂载路径下时由 CD2 处理 |
| `sha256` | string |  |
| `size` | integer | 字节数 |

### POST `/api/extensions/v3/{id}/media/emby-image`

<a id="post-api-extensions-v3-id-media-emby-image"></a>

上传插件图片到 Emby 条目主图。 宿主插件 API 3.3。使用宿主 Emby 配置，源图片只读插件自有文件；覆盖指定条目的 Primary 图像。

**参数**

| 名称 | 位置 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- | --- |
| `id` | path | string | 是 |  |
| `proxy_id` | query | integer |  | Emby 实例 ID，来自 GET /api/plugin-host/emby/instances；省略使用默认实例 |

**请求体（JSON）**

| 字段 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- |
| `item_id` | string | 是 |  |
| `source` | string | 是 | 插件自有图片相对路径；会转为 JPEG 后上传到 Emby 主图 |

**调用**

```js
const res = await ctx.api.post('/api/extensions/v3/id/media/emby-image', {
  "item_id": "<item_id>",
  "source": "<source>"
})
```

**响应 200**（按契约结构生成的示例值）

```json
{
  "item_id": "<item_id>",
  "success": true
}
```

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `item_id` | string |  |
| `success` | boolean |  |

### POST `/api/extensions/v3/{id}/media/image`

<a id="post-api-extensions-v3-id-media-image"></a>

裁剪、缩放与合成插件图片。 宿主插件 API 3.3。支持 PNG/JPEG/GIF 首帧/WebP 与静态 SVG 子集；自动纠正 EXIF。输入 32 MiB、24 MP、每边 12000 像素；最多并发 2，处理中源图合计 24 MP、超额在解码前排队，总时限 90 秒。inspect 只检查头部；裁剪区域直接缩放后复用画布叠加，不透明 JPEG 不创建白底。不读取任意宿主图片或执行图像命令。

**参数**

| 名称 | 位置 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- | --- |
| `id` | path | string | 是 |  |

**请求体（JSON）**

| 字段 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- |
| `crop` | "none" / "center" / "left" / "right" / "face" |  |  |
| `destination` | string |  | 处理结果保存到插件 data/files 的相对路径；inspect=true 可省略 |
| `fit` | "contain" / "cover" |  |  |
| `format` | "jpeg" / "jpg" / "png" |  |  |
| `height` | integer |  | 输出高度；0 保持/按宽度等比推导 |
| `inspect` | boolean |  | 仅检查图片头或 SVG 尺寸，返回 JPEG EXIF 纠正后的宽高；不解压像素、不写文件，不保证像素完整 |
| `overlays` | ExtensionImageOverlay[] |  |  |
| `overlays[].corner` | "top-left" / "top-right" / "bottom-left" / "bottom-right" |  |  |
| `overlays[].opacity` | number |  | 默认 1 |
| `overlays[].scale` | number |  | 相对输出图片宽度；默认 0.18 |
| `overlays[].source` | string | 是 | 插件自有图片相对路径或目录接口返回的宿主 badge asset_url |
| `overlays[].width` | integer |  |  |
| `overlays[].x` | integer |  | 距离所选角的横向像素偏移 |
| `overlays[].y` | integer |  | 距离所选角的纵向像素偏移 |
| `quality` | integer |  | JPEG 默认 92 |
| `ratio` | number |  | 裁剪宽高比，默认 2/3；人脸未检测到时回退 right |
| `source` | string | 是 | 插件图片相对路径或宿主 badge asset_url；绝对宿主文件路径不可读 |
| `width` | integer |  | 输出宽度；0 保持/按高度等比推导 |

**调用**

```js
const res = await ctx.api.post('/api/extensions/v3/id/media/image', {
  "crop": "none",
  "destination": "<destination>",
  "fit": "contain",
  "format": "jpeg",
  "height": 0,
  "inspect": true,
  "overlays": [
    {
      "corner": "top-left",
      "opacity": 0,
      "scale": 0,
      "source": "<source>",
      "width": 0,
      "x": 0,
      "y": 0
    }
  ],
  "quality": 1,
  "ratio": 0,
  "source": "<source>",
  "width": 0
})
```

**响应 200**（按契约结构生成的示例值）

```json
{
  "image": {
    "crop_applied": "<crop_applied>",
    "faces": 0,
    "format": "<format>",
    "height": 0,
    "width": 0
  },
  "path": "/mnt/media/电影",
  "sha256": "<sha256>",
  "size": 0
}
```

响应为宿主或上游服务原样透传的 JSON，字段可能随上游变化；以 HTTP 2xx 判断成功。

### POST `/api/extensions/v3/{id}/media/nfo`

<a id="post-api-extensions-v3-id-media-nfo"></a>

读取媒体 NFO 的结构化资料。 API 3.4；只读标准 movie NFO，最多 2 MiB、50000 元素、32 层、单字段 64 KiB。只返回声明的资料字段，不返回任意文件文本；不解析外部实体，不返回非 num/jav 类型的 uniqueid 作为番号。

**参数**

| 名称 | 位置 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- | --- |
| `id` | path | string | 是 |  |

**请求体（JSON）**

| 字段 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- |
| `path` | string | 是 | 受宿主文件保护约束的本地绝对 .nfo 路径或 cd2:/...；最大 2 MiB |

**调用**

```js
const res = await ctx.api.post('/api/extensions/v3/id/media/nfo', {
  "path": "/mnt/media/电影"
})
```

**响应 200**（按契约结构生成的示例值）

```json
{
  "actor_photos": {},
  "actors": [
    ""
  ],
  "director": "<director>",
  "genres": [
    ""
  ],
  "label": "<label>",
  "number": "<number>",
  "original_plot": "<original_plot>",
  "original_title": "<original_title>",
  "outline": "<outline>",
  "plot": "<plot>",
  "rating": "<rating>",
  "release_date": "<release_date>",
  "runtime": "<runtime>",
  "series": "<series>",
  "source_url": "<source_url>",
  "studio": "<studio>",
  "tags": [
    ""
  ],
  "title": "<title>",
  "trailer": "<trailer>",
  "votes": "<votes>"
}
```

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `actor_photos` | object |  |
| `actors` | string[] |  |
| `director` | string |  |
| `genres` | string[] |  |
| `label` | string |  |
| `number` | string |  |
| `original_plot` | string |  |
| `original_title` | string | 原始语言标题 |
| `outline` | string |  |
| `plot` | string |  |
| `rating` | string |  |
| `release_date` | string |  |
| `runtime` | string |  |
| `series` | string |  |
| `source_url` | string |  |
| `studio` | string |  |
| `tags` | string[] |  |
| `title` | string | 标题 |
| `trailer` | string |  |
| `votes` | string |  |

### POST `/api/extensions/v3/{id}/media/probe`

<a id="post-api-extensions-v3-id-media-probe"></a>

复用宿主 FFP 获取真实媒体信息。 宿主插件 API 3.3。复用已有 SHA1 缓存和全局整理探测并发；无缓存时调用宿主 FFP。CD2 需要挂载；不返回直链、原始探测 JSON 或凭据。总时限 120 秒。

**参数**

| 名称 | 位置 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- | --- |
| `id` | path | string | 是 |  |

**请求体（JSON）**

| 字段 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- |
| `path` | string | 是 | 受宿主路径规则保护的绝对媒体路径或 cd2:/ 路径；仅真实媒体文件，不接受 URL/STRM/命令行 |
| `sha1` | string |  | 可选 115 SHA1；用于复用共享 FFP 缓存 |

**调用**

```js
const res = await ctx.api.post('/api/extensions/v3/id/media/probe', {
  "path": "/mnt/media/电影",
  "sha1": "<sha1>"
})
```

**响应 200**（按契约结构生成的示例值）

```json
{
  "audio_codec": "<audio_codec>",
  "audio_tracks": [
    {
      "bit_rate": 0,
      "channels": 0,
      "codec": "<codec>",
      "default": true,
      "index": 0,
      "language": "<language>",
      "layout": "<layout>",
      "profile": "<profile>",
      "title": "<title>"
    }
  ],
  "bit_rate": 0,
  "color_depth": 0,
  "container": "<container>",
  "duration": 0,
  "file_size": 0,
  "frame_rate": 0,
  "hdr_type": "<hdr_type>",
  "height": 0,
  "pixel_format": "<pixel_format>",
  "profile": "<profile>",
  "resolution": "<resolution>",
  "structural_color_unknown": true,
  "structural_only": true,
  "subtitle_tracks": [
    {
      "codec": "<codec>",
      "default": true,
      "forced": true,
      "index": 0,
      "language": "<language>",
      "title": "<title>"
    }
  ],
  "video_codec": "<video_codec>",
  "width": 0
}
```

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `audio_codec` | string |  |
| `audio_tracks` | object[] |  |
| `audio_tracks[].bit_rate` | integer |  |
| `audio_tracks[].channels` | integer |  |
| `audio_tracks[].codec` | string |  |
| `audio_tracks[].default` | boolean |  |
| `audio_tracks[].index` | integer |  |
| `audio_tracks[].language` | string |  |
| `audio_tracks[].layout` | string |  |
| `audio_tracks[].profile` | string |  |
| `audio_tracks[].title` | string | 标题 |
| `bit_rate` | integer |  |
| `color_depth` | integer |  |
| `container` | string |  |
| `duration` | number |  |
| `file_size` | integer |  |
| `frame_rate` | number |  |
| `hdr_type` | string |  |
| `height` | integer |  |
| `pixel_format` | string |  |
| `profile` | string |  |
| `resolution` | string |  |
| `structural_color_unknown` | boolean |  |
| `structural_only` | boolean |  |
| `subtitle_tracks` | object[] |  |
| `subtitle_tracks[].codec` | string |  |
| `subtitle_tracks[].default` | boolean |  |
| `subtitle_tracks[].forced` | boolean |  |
| `subtitle_tracks[].index` | integer |  |
| `subtitle_tracks[].language` | string |  |
| `subtitle_tracks[].title` | string | 标题 |
| `video_codec` | string |  |
| `width` | integer |  |

### GET `/api/extensions/v3/{id}/network-capabilities`

<a id="get-api-extensions-v3-id-network-capabilities"></a>

查询宿主默认渲染能力与配置状态（不返回地址和凭据）。

**参数**

| 名称 | 位置 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- | --- |
| `id` | path | string | 是 |  |

**调用**

```js
const res = await ctx.api.get('/api/extensions/v3/id/network-capabilities')
```

**响应 200**（按契约结构生成的示例值）

```json
{
  "default_render_endpoint": true,
  "render_configured": true
}
```

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `default_render_endpoint` | boolean |  |
| `render_configured` | boolean |  |

### POST `/api/extensions/v3/{id}/notify`

<a id="post-api-extensions-v3-id-notify"></a>

发送插件通知（选择渠道、格式与按渠道内容）。 发送插件通知。默认发往用户允许插件通知的所有渠道；channels 只缩小范围，不会越过用户的渠道开关与静默时段。text 套用用户的插件通知模板；markdown/html 按原样排版（Telegram 渲染为 HTML，企业微信 markdown 原样发送、html 转纯文本），宿主附加来源行。deliveries 逐渠道报告结果。后台用 ctx.notify(...)，页面用 ctx.notifications.send(...)。

**参数**

| 名称 | 位置 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- | --- |
| `id` | path | string | 是 |  |

**请求体（JSON）**

| 字段 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- |
| `body` | string | 是 | 正文；text 最多 2000 字，markdown/html 最多 3500 字 |
| `buttons` | ExtensionNotificationButton[][] |  | 按钮行（最多 8 行，每行 1–4 个） |
| `channels` | "telegram" / "wecom" / "all"[] |  | 只发到这些渠道；省略或 all 表示所有允许插件通知的渠道。不能绕过用户在该渠道关闭的插件通知或静默时段 |
| `dedupe_key` | string |  | 去重键：10 分钟内同一插件相同键只发一次；后台 outbox 永久按此键记录投递结果 |
| `format` | "text" / "markdown" / "html" |  | text：套用用户的插件通知模板（纯文本，默认）；markdown / html：按原样排版发送，宿主附加“来自插件”来源行 |
| `image_url` | string(uri) |  | 图片（HTTPS，无凭据）。Telegram 发图片消息；企业微信发图文卡片 |
| `job_ref` | string |  | 宿主下发的 job_ 引用（可选） |
| `level` | "info" / "success" / "warning" / "error" |  | 级别，决定图标：ℹ️ ✅ ⚠️ ❌ |
| `overrides` | object |  | 按渠道覆盖内容，键为 telegram / wecom |
| `overrides.telegram` | ExtensionNotificationChannelContent |  | 某个渠道专用的内容，未填字段沿用通用内容 |
| `overrides.telegram.body` | string |  | 该渠道的正文（text 最多 2000 字，markdown/html 最多 3500 字） |
| `overrides.telegram.format` | "text" / "markdown" / "html" |  | text：套用用户的插件通知模板（纯文本，默认）；markdown / html：按原样排版发送，宿主附加“来自插件”来源行 |
| `overrides.telegram.image_url` | string(uri) |  | 该渠道的图片（HTTPS） |
| `overrides.telegram.title` | string |  | 该渠道的标题 |
| `overrides.wecom` | ExtensionNotificationChannelContent |  | 某个渠道专用的内容，未填字段沿用通用内容 |
| `overrides.wecom.body` | string |  | 该渠道的正文（text 最多 2000 字，markdown/html 最多 3500 字） |
| `overrides.wecom.format` | "text" / "markdown" / "html" |  | text：套用用户的插件通知模板（纯文本，默认）；markdown / html：按原样排版发送，宿主附加“来自插件”来源行 |
| `overrides.wecom.image_url` | string(uri) |  | 该渠道的图片（HTTPS） |
| `overrides.wecom.title` | string |  | 该渠道的标题 |
| `silent` | boolean |  | Telegram 静音送达（不响铃） |
| `title` | string | 是 | 标题 |

**调用**

```js
const res = await ctx.api.post('/api/extensions/v3/id/notify', {
  "title": "转存完成",
  "body": "**3** 个文件已转存到 `/电影`\n- Example.2024.mkv\n[查看任务](https://example.com/tasks/1)",
  "level": "success",
  "format": "markdown",
  "channels": [
    "telegram",
    "wecom"
  ],
  "overrides": {
    "wecom": {
      "body": "3 个文件已转存到 /电影",
      "format": "text"
    }
  },
  "buttons": [
    [
      {
        "text": "打开 115",
        "url": "https://115.com/"
      }
    ]
  ],
  "dedupe_key": "transfer:20261029-1"
})
```

**响应 200**

```json
{
  "event": "plugin_notification_message",
  "accepted": true,
  "channels": [
    {
      "channel": "telegram",
      "preserved": [
        "link_buttons"
      ]
    }
  ],
  "deliveries": [
    {
      "channel": "telegram",
      "status": "sent",
      "format": "markdown",
      "preserved": [
        "link_buttons"
      ]
    },
    {
      "channel": "wecom",
      "status": "skipped",
      "reason": "quiet_hours"
    }
  ]
}
```

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `accepted` | boolean | 至少一个渠道已发送 |
| `channels` | object[] |  |
| `channels[].channel` | string |  |
| `channels[].dropped` | string[] |  |
| `channels[].preserved` | string[] |  |
| `deduplicated` | boolean | 命中 dedupe_key，未重复发送 |
| `deliveries` | ExtensionNotificationDelivery[] | 每个请求渠道的结果 |
| `deliveries[].channel` | "telegram" / "wecom" | 渠道 |
| `deliveries[].dropped` | string[] | 该渠道丢弃的功能，可能包含 formatting |
| `deliveries[].error` | string | 失败原因（不含令牌、会话 ID 等敏感信息） |
| `deliveries[].format` | "text" / "markdown" / "html" | 该渠道实际使用的格式（企业微信不支持 html，会降为 text） |
| `deliveries[].preserved` | string[] | 该渠道保留的功能：link_buttons、callback_buttons、images |
| `deliveries[].reason` | "not_configured" / "disabled" / "quiet_hours" | not_configured 渠道未配置；disabled 用户在该渠道关闭了插件通知；quiet_hours 该渠道处于静默时段 |
| `deliveries[].status` | "sent" / "skipped" / "failed" | sent 已发送；skipped 未发送（见 reason）；failed 发送失败（见 error） |
| `event` | string | 宿主通知事件键（plugin_notification_message） |
| `suppressed` | boolean | 没有发送（见 suppression_reason） |
| `suppression_reason` | string | no_channel_enabled 所有渠道都关闭插件通知；telegram_not_configured 没有可用渠道；no_eligible_channel 请求的渠道都未配置、关闭或静默 |

### POST `/api/extensions/v3/{id}/render`

<a id="post-api-extensions-v3-id-render"></a>

按需复用外部 FlareSolverr。

**参数**

| 名称 | 位置 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- | --- |
| `id` | path | string | 是 |  |

**请求体（JSON）**

| 字段 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- |
| `endpoint` | string |  | 省略时由宿主内部使用已配置的 FlareSolverr 地址；不向插件返回系统设置。 |
| `session` | string |  |  |
| `timeout_seconds` | integer |  |  |
| `url` | string | 是 |  |
| `wait_seconds` | integer |  |  |

**调用**

```js
const res = await ctx.api.post('/api/extensions/v3/id/render', {
  "endpoint": "<endpoint>",
  "session": "<session>",
  "timeout_seconds": 180,
  "url": "<url>",
  "wait_seconds": 0
})
```

**响应 200**（按契约结构生成的示例值）

```json
{
  "html": "<html>",
  "http_status_verified": true,
  "url": "<url>",
  "user_agent": "<user_agent>"
}
```

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `html` | string |  |
| `http_status_verified` | boolean |  |
| `url` | string |  |
| `user_agent` | string |  |

### GET `/api/extensions/v3/{id}/runs`

<a id="get-api-extensions-v3-id-runs"></a>

读取插件/runs。

**参数**

| 名称 | 位置 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- | --- |
| `id` | path | string | 是 |  |
| `limit` | query | integer |  | 本次最多返回的条数 |
| `offset` | query | integer |  | 跳过的条数，从 0 开始 |

**调用**

```js
const res = await ctx.api.get('/api/extensions/v3/id/runs')
```

**响应 200**（按契约结构生成的示例值）

```json
[
  {
    "attempted": true,
    "business_key": "<business_key>",
    "checkpoint": null,
    "created_at": "2026-10-29T21:30:00+08:00",
    "done": 0,
    "error": "<error>",
    "failed": 0,
    "id": "<id>",
    "input": null,
    "job_id": "<job_id>",
    "logs": [
      ""
    ],
    "message": "<message>",
    "progress": 0,
    "result": null,
    "revision": "<revision>",
    "stage": "<stage>",
    "status": "queued",
    "total": 0,
    "updated_at": "2026-10-29T21:30:00+08:00"
  }
]
```

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `[].attempted` | boolean |  |
| `[].business_key` | string |  |
| `[].checkpoint` | any | 插件自己的任意 JSON 业务值；结构由该插件定义。 |
| `[].created_at` | string(date-time) | 创建时间（RFC 3339） |
| `[].done` | integer | 任务级已完成项数 |
| `[].error` | string | 失败原因（原始业务错误） |
| `[].failed` | integer | 任务级失败项数 |
| `[].id` | string |  |
| `[].input` | any | 插件自己的任意 JSON 业务值；结构由该插件定义。 |
| `[].job_id` | string |  |
| `[].logs` | string[] |  |
| `[].message` | string | 给用户看的结果说明 |
| `[].progress` | number |  |
| `[].result` | any | 插件自己的任意 JSON 业务值；结构由该插件定义。 |
| `[].revision` | string |  |
| `[].stage` | string |  |
| `[].status` | "queued" / "running" / "failed" / "succeeded" / "cancelled" / "attention_required" |  |
| `[].total` | integer | 任务级总项数（ctx.task.update 上报）；0 或省略表示只上报百分比 |
| `[].updated_at` | string(date-time) | 更新时间（RFC 3339） |

### GET `/api/extensions/v3/{id}/runs/{run}`

<a id="get-api-extensions-v3-id-runs-run"></a>

读取插件/runs/{run}。

**参数**

| 名称 | 位置 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- | --- |
| `id` | path | string | 是 |  |
| `run` | path | string | 是 |  |

**调用**

```js
const res = await ctx.api.get('/api/extensions/v3/id/runs/run')
```

**响应 200**（按契约结构生成的示例值）

```json
{
  "attempted": true,
  "business_key": "<business_key>",
  "checkpoint": null,
  "created_at": "2026-10-29T21:30:00+08:00",
  "done": 0,
  "error": "<error>",
  "failed": 0,
  "id": "<id>",
  "input": null,
  "job_id": "<job_id>",
  "logs": [
    ""
  ],
  "message": "<message>",
  "progress": 0,
  "result": null,
  "revision": "<revision>",
  "stage": "<stage>",
  "status": "queued",
  "total": 0,
  "updated_at": "2026-10-29T21:30:00+08:00"
}
```

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `attempted` | boolean |  |
| `business_key` | string |  |
| `checkpoint` | any | 插件自己的任意 JSON 业务值；结构由该插件定义。 |
| `created_at` | string(date-time) | 创建时间（RFC 3339） |
| `done` | integer | 任务级已完成项数 |
| `error` | string | 失败原因（原始业务错误） |
| `failed` | integer | 任务级失败项数 |
| `id` | string |  |
| `input` | any | 插件自己的任意 JSON 业务值；结构由该插件定义。 |
| `job_id` | string |  |
| `logs` | string[] |  |
| `message` | string | 给用户看的结果说明 |
| `progress` | number |  |
| `result` | any | 插件自己的任意 JSON 业务值；结构由该插件定义。 |
| `revision` | string |  |
| `stage` | string |  |
| `status` | "queued" / "running" / "failed" / "succeeded" / "cancelled" / "attention_required" |  |
| `total` | integer | 任务级总项数（ctx.task.update 上报）；0 或省略表示只上报百分比 |
| `updated_at` | string(date-time) | 更新时间（RFC 3339） |

### POST `/api/extensions/v3/{id}/runs/{run}/cancel`

<a id="post-api-extensions-v3-id-runs-run-cancel"></a>

取消任务。

**参数**

| 名称 | 位置 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- | --- |
| `id` | path | string | 是 |  |
| `run` | path | string | 是 |  |

**调用**

```js
const res = await ctx.api.post('/api/extensions/v3/id/runs/run/cancel', {})
```

**响应 200**（按契约结构生成的示例值）

```json
{
  "ok": true
}
```

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `ok` | boolean |  |

### POST `/api/extensions/v3/{id}/runs/{run}/retry`

<a id="post-api-extensions-v3-id-runs-run-retry"></a>

调用恢复处理器核对任务结果。

**参数**

| 名称 | 位置 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- | --- |
| `id` | path | string | 是 |  |
| `run` | path | string | 是 |  |

**调用**

```js
const res = await ctx.api.post('/api/extensions/v3/id/runs/run/retry', {})
```

**响应 200**（按契约结构生成的示例值）

```json
{
  "attempted": true,
  "business_key": "<business_key>",
  "checkpoint": null,
  "created_at": "2026-10-29T21:30:00+08:00",
  "done": 0,
  "error": "<error>",
  "failed": 0,
  "id": "<id>",
  "input": null,
  "job_id": "<job_id>",
  "logs": [
    ""
  ],
  "message": "<message>",
  "progress": 0,
  "result": null,
  "revision": "<revision>",
  "stage": "<stage>",
  "status": "queued",
  "total": 0,
  "updated_at": "2026-10-29T21:30:00+08:00"
}
```

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `attempted` | boolean |  |
| `business_key` | string |  |
| `checkpoint` | any | 插件自己的任意 JSON 业务值；结构由该插件定义。 |
| `created_at` | string(date-time) | 创建时间（RFC 3339） |
| `done` | integer | 任务级已完成项数 |
| `error` | string | 失败原因（原始业务错误） |
| `failed` | integer | 任务级失败项数 |
| `id` | string |  |
| `input` | any | 插件自己的任意 JSON 业务值；结构由该插件定义。 |
| `job_id` | string |  |
| `logs` | string[] |  |
| `message` | string | 给用户看的结果说明 |
| `progress` | number |  |
| `result` | any | 插件自己的任意 JSON 业务值；结构由该插件定义。 |
| `revision` | string |  |
| `stage` | string |  |
| `status` | "queued" / "running" / "failed" / "succeeded" / "cancelled" / "attention_required" |  |
| `total` | integer | 任务级总项数（ctx.task.update 上报）；0 或省略表示只上报百分比 |
| `updated_at` | string(date-time) | 更新时间（RFC 3339） |

### GET `/api/extensions/v3/{id}/settings`

<a id="get-api-extensions-v3-id-settings"></a>

清单默认值叠加已保存的 settings。

**参数**

| 名称 | 位置 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- | --- |
| `id` | path | string | 是 |  |

**调用**

```js
const res = await ctx.api.get('/api/extensions/v3/id/settings')
```

**响应 200**（按契约结构生成的示例值）

```json
{}
```

响应为宿主或上游服务原样透传的 JSON，字段可能随上游变化；以 HTTP 2xx 判断成功。

### PUT `/api/extensions/v3/{id}/sidebar`

<a id="put-api-extensions-v3-id-sidebar"></a>

设置插件页面是否显示在侧边栏。

**参数**

| 名称 | 位置 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- | --- |
| `id` | path | string | 是 |  |

**请求体（JSON）**

| 字段 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- |
| `sidebar` | boolean | 是 | 插件页面是否显示在侧边栏 |

**调用**

```js
const res = await ctx.api.put('/api/extensions/v3/id/sidebar', {
  "sidebar": true
})
```

**响应 200**（按契约结构生成的示例值）

```json
{
  "ok": true
}
```

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `ok` | boolean |  |

### GET `/api/extensions/v3/{id}/storage`

<a id="get-api-extensions-v3-id-storage"></a>

读取插件/storage。

**参数**

| 名称 | 位置 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- | --- |
| `id` | path | string | 是 |  |
| `limit` | query | integer |  | 本次最多返回的条数 |
| `offset` | query | integer |  | 跳过的条数，从 0 开始 |

**调用**

```js
const res = await ctx.api.get('/api/extensions/v3/id/storage')
```

**响应 200**（按契约结构生成的示例值）

```json
[
  {
    "encrypted_bytes": 0,
    "key": "<key>",
    "revision": 0
  }
]
```

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `[].encrypted_bytes` | integer |  |
| `[].key` | string |  |
| `[].revision` | integer |  |

### GET `/api/extensions/v3/{id}/storage/{key}`

<a id="get-api-extensions-v3-id-storage-key"></a>

读取插件/storage/{key}。

**参数**

| 名称 | 位置 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- | --- |
| `id` | path | string | 是 |  |
| `key` | path | string | 是 |  |

**调用**

```js
const res = await ctx.api.get('/api/extensions/v3/id/storage/key')
```

**响应 200**（按契约结构生成的示例值）

```json
{
  "revision": 0,
  "value": null
}
```

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `revision` | integer |  |
| `value` | any | 插件自己的任意 JSON 业务值；结构由该插件定义。 |

### PUT `/api/extensions/v3/{id}/storage/{key}`

<a id="put-api-extensions-v3-id-storage-key"></a>

写入 JSON，支持乐观版本检查。

**参数**

| 名称 | 位置 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- | --- |
| `id` | path | string | 是 |  |
| `key` | path | string | 是 |  |

**请求体（JSON）**

| 字段 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- |
| `expected_revision` | integer |  |  |
| `value` | any | 是 |  |

**调用**

```js
const res = await ctx.api.put('/api/extensions/v3/id/storage/key', {
  "expected_revision": 0,
  "value": null
})
```

**响应 200**（按契约结构生成的示例值）

```json
{
  "revision": 0
}
```

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `revision` | integer |  |

### DELETE `/api/extensions/v3/{id}/storage/{key}`

<a id="delete-api-extensions-v3-id-storage-key"></a>

删除插件 KV。

**参数**

| 名称 | 位置 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- | --- |
| `id` | path | string | 是 |  |
| `key` | path | string | 是 |  |

**调用**

```js
const res = await ctx.api.delete('/api/extensions/v3/id/storage/key')
```

**响应 200**（按契约结构生成的示例值）

```json
{
  "ok": true
}
```

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `ok` | boolean |  |

### GET `/api/extensions/v3/{id}/usage`

<a id="get-api-extensions-v3-id-usage"></a>

读取插件/usage。

**参数**

| 名称 | 位置 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- | --- |
| `id` | path | string | 是 |  |

**调用**

```js
const res = await ctx.api.get('/api/extensions/v3/id/usage')
```

**响应 200**（按契约结构生成的示例值）

```json
{}
```

响应为宿主或上游服务原样透传的 JSON，字段可能随上游变化；以 HTTP 2xx 判断成功。

### GET `/api/extensions/v3/{id}/watches`

<a id="get-api-extensions-v3-id-watches"></a>

读取插件/watches。

**参数**

| 名称 | 位置 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- | --- |
| `id` | path | string | 是 |  |

**调用**

```js
const res = await ctx.api.get('/api/extensions/v3/id/watches')
```

**响应 200**（按契约结构生成的示例值）

```json
[
  {
    "debounce_ms": 0,
    "error": "<error>",
    "id": "<id>",
    "initialized": true,
    "interval_seconds": 0,
    "job": "<job>",
    "kind": "local",
    "path": "/mnt/media/电影",
    "patterns": [
      ""
    ],
    "pending": null,
    "pending_snapshot": {},
    "realtime": true,
    "recursive": true,
    "sequence": 0,
    "snapshot": {}
  }
]
```

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `[].debounce_ms` | integer |  |
| `[].error` | string | 失败原因（原始业务错误） |
| `[].id` | string |  |
| `[].initialized` | boolean |  |
| `[].interval_seconds` | integer |  |
| `[].job` | string |  |
| `[].kind` | "local" / "cd2" |  |
| `[].path` | string | 宿主绝对 Linux 路径；位于 CD2 挂载路径下时由 CD2 处理 |
| `[].patterns` | string[] | 文件名 glob 过滤 |
| `[].pending` | any | 插件自己的任意 JSON 业务值；结构由该插件定义。 |
| `[].pending_snapshot` | object |  |
| `[].realtime` | boolean | local 默认 true：inotify 事件提前触发快照比较 |
| `[].recursive` | boolean |  |
| `[].sequence` | integer |  |
| `[].snapshot` | object |  |

### POST `/api/extensions/v3/{id}/watches`

<a id="post-api-extensions-v3-id-watches"></a>

持久化目录轮询；变化进入统一任务队列。

**参数**

| 名称 | 位置 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- | --- |
| `id` | path | string | 是 |  |

**请求体（JSON）**

| 字段 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- |
| `id` | string | 是 |  |
| `interval_seconds` | integer |  |  |
| `job` | string | 是 |  |
| `kind` | "local" / "cd2" | 是 |  |
| `path` | string | 是 | 宿主绝对 Linux 路径；位于 CD2 挂载路径下时由 CD2 处理 |

**调用**

```js
const res = await ctx.api.post('/api/extensions/v3/id/watches', {
  "id": "<id>",
  "interval_seconds": 5,
  "job": "<job>",
  "kind": "local",
  "path": "/mnt/media/电影"
})
```

**响应 200**（按契约结构生成的示例值）

```json
{
  "ok": true
}
```

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `ok` | boolean |  |

### DELETE `/api/extensions/v3/{id}/watches/{watch}`

<a id="delete-api-extensions-v3-id-watches-watch"></a>

删除监听并阻止晚到轮询写回。

**参数**

| 名称 | 位置 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- | --- |
| `id` | path | string | 是 |  |
| `watch` | path | string | 是 |  |

**调用**

```js
const res = await ctx.api.delete('/api/extensions/v3/id/watches/watch')
```

**响应 200**（按契约结构生成的示例值）

```json
{
  "ok": true
}
```

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `ok` | boolean |  |

### GET `/plugin-hooks/{id}/{path}`

<a id="get-plugin-hooks-id-path"></a>

公开回调（清单 http.public=true；无需宿主登录，插件自行鉴权）。

**参数**

| 名称 | 位置 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- | --- |
| `id` | path | string | 是 |  |
| `path` | path | string | 是 | 宿主绝对 Linux 路径；位于 CD2 挂载路径下时由 CD2 处理 |

**响应 200**：成功响应

### POST `/plugin-hooks/{id}/{path}`

<a id="post-plugin-hooks-id-path"></a>

公开回调（清单 http.public=true；无需宿主登录，插件自行鉴权）。

**参数**

| 名称 | 位置 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- | --- |
| `id` | path | string | 是 |  |
| `path` | path | string | 是 | 宿主绝对 Linux 路径；位于 CD2 挂载路径下时由 CD2 处理 |

**响应 200**：成功响应

### PUT `/plugin-hooks/{id}/{path}`

<a id="put-plugin-hooks-id-path"></a>

公开回调（清单 http.public=true；无需宿主登录，插件自行鉴权）。

**参数**

| 名称 | 位置 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- | --- |
| `id` | path | string | 是 |  |
| `path` | path | string | 是 | 宿主绝对 Linux 路径；位于 CD2 挂载路径下时由 CD2 处理 |

**响应 200**：成功响应

### PATCH `/plugin-hooks/{id}/{path}`

<a id="patch-plugin-hooks-id-path"></a>

公开回调（清单 http.public=true；无需宿主登录，插件自行鉴权）。

**参数**

| 名称 | 位置 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- | --- |
| `id` | path | string | 是 |  |
| `path` | path | string | 是 | 宿主绝对 Linux 路径；位于 CD2 挂载路径下时由 CD2 处理 |

**响应 200**：成功响应

### DELETE `/plugin-hooks/{id}/{path}`

<a id="delete-plugin-hooks-id-path"></a>

公开回调（清单 http.public=true；无需宿主登录，插件自行鉴权）。

**参数**

| 名称 | 位置 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- | --- |
| `id` | path | string | 是 |  |
| `path` | path | string | 是 | 宿主绝对 Linux 路径；位于 CD2 挂载路径下时由 CD2 处理 |

**响应 200**：成功响应

## 媒体库

### POST `/api/library/check-owned`

<a id="post-api-library-check-owned"></a>

检查媒体库是否已存在。 按 TMDB 信息检查媒体是否已入库。

**请求体（JSON）**

| 字段 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- |
| `fast` | boolean |  |  |
| `items` | object[] |  |  |
| `items[].include_seasons` | boolean |  |  |
| `items[].media_type` | string |  | 媒体类型：movie 电影、tv 剧集 |
| `items[].proxy_id` | integer |  | Emby 实例 ID，来自 GET /api/plugin-host/emby/instances；省略使用默认实例 |
| `items[].tmdb_id` | integer |  | TMDB 媒体 ID；电影与剧集分别编号，需配合 media_type 使用 |
| `proxy_id` | integer |  | Emby 实例 ID，来自 GET /api/plugin-host/emby/instances；省略使用默认实例 |
| `tmdb_ids` | integer[] |  | 多个 TMDB ID |

**调用**

```js
const res = await ctx.api.post('/api/library/check-owned', {
  "fast": true,
  "items": [
    {
      "include_seasons": true,
      "media_type": "tv",
      "proxy_id": 1,
      "tmdb_id": 1399
    }
  ],
  "proxy_id": 1,
  "tmdb_ids": [
    0
  ]
})
```

**响应 200**（按契约结构生成的示例值）

```json
{
  "code": "<code>",
  "owned": {},
  "states": {}
}
```

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `code` | string |  |
| `owned` | object |  |
| `states` | object |  |

## 宿主文件管理

### GET `/api/local-dirs`

<a id="get-api-local-dirs"></a>

浏览可选目录。 读取文件管理器可用目录。

**参数**

| 名称 | 位置 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- | --- |
| `path` | query | string |  | 要浏览的绝对宿主路径；插件调用时 `path` 或 `root_path` 至少提供一个。 |
| `root_path` | query | string |  | 可选浏览根边界，返回的父目录不会越过它。 |
| `source_path` | query | string |  | 可选源路径；为 CD2 路径时限制浏览在同一 CD2 挂载范围。 |

**调用**

```js
const res = await ctx.api.get('/api/local-dirs')
```

**响应 200**（按契约结构生成的示例值）

```json
{
  "current": "<current>",
  "entries": [
    {
      "is_dir": true,
      "name": "<name>",
      "path": "/mnt/media/电影"
    }
  ]
}
```

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `current` | string |  |
| `entries` | LocalDirectoryEntry[] |  |
| `entries[].is_dir` | true | 是否为目录 |
| `entries[].name` | string | 名称 |
| `entries[].path` | string | 宿主绝对 Linux 路径；位于 CD2 挂载路径下时由 CD2 处理 |

### GET `/api/local-files`

<a id="get-api-local-files"></a>

列出文件。 列出宿主目录。位于 CD2 挂载路径下时通过 CD2 读取（backend=cd2）。插件后台更推荐 ctx.files.call({operation:'list'})。

**参数**

| 名称 | 位置 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- | --- |
| `path` | query | string | 是 | 用户选择的绝对业务目录路径，须通过宿主文件保护检查。 |

**调用**

```js
const res = await ctx.api.get('/api/local-files?path=/mnt/media')
```

**响应 200**

```json
{
  "current": "/mnt/media",
  "parent": "/mnt",
  "backend": "local",
  "entries": [
    {
      "name": "电影",
      "path": "/mnt/media/电影",
      "is_dir": true,
      "size": 0,
      "mod_time": "2026-10-29 21:30:00",
      "ext": ""
    },
    {
      "name": "a.mkv",
      "path": "/mnt/media/a.mkv",
      "is_dir": false,
      "size": 4294967296,
      "mod_time": "2026-10-29 21:30:00",
      "ext": ".mkv"
    }
  ]
}
```

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `backend` | "local" / "cd2" |  |
| `current` | string |  |
| `entries` | LocalFileEntry[] |  |
| `entries[].ext` | string | 扩展名（含点），目录为空 |
| `entries[].is_dir` | boolean | 是否为目录 |
| `entries[].mod_time` | string | 修改时间 |
| `entries[].name` | string | 名称 |
| `entries[].path` | string | 宿主绝对 Linux 路径；位于 CD2 挂载路径下时由 CD2 处理 |
| `entries[].size` | integer(int64) | 字节数 |
| `parent` | string |  |

### DELETE `/api/local-files`

<a id="delete-api-local-files"></a>

删除文件。 删除文件或目录。

**请求体（JSON）**

| 字段 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- |
| `paths` | string[] | 是 | 多个宿主绝对路径 |

**调用**

```js
const res = await ctx.api.delete('/api/local-files', {
  "paths": [
    ""
  ]
})
```

**响应 200**（按契约结构生成的示例值）

```json
{
  "success": true
}
```

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `success` | true | 是否成功；成功响应中恒为 true，失败时返回 4xx/5xx 与 error |

### POST `/api/local-files/batch`

<a id="post-api-local-files-batch"></a>

批量管理文件。 批量删除/移动/复制，作为后台任务执行，立即返回任务 ID；用 batch-status 查询进度。

**请求体（JSON）**

| 字段 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- |
| `dest_dir` | string |  | move 和 copy 时必填。 |
| `operation` | "delete" / "move" / "copy" | 是 | delete 删除、move 移动、copy 复制 |
| `paths` | string[] | 是 | 多个宿主绝对路径 |

**调用**

```js
const res = await ctx.api.post('/api/local-files/batch', {
  "operation": "move",
  "paths": [
    "/mnt/inbox/a.mkv",
    "/mnt/inbox/b.mkv"
  ],
  "dest_dir": "/mnt/media/电影"
})
```

**响应 202**（按契约结构生成的示例值）

```json
{
  "status": "<status>",
  "task_id": "20261029213000-a1b2c3",
  "total": 1
}
```

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `status` | string |  |
| `task_id` | string | 统一任务队列的任务 ID，可用 GET /api/tasks/{id} 查询进度 |
| `total` | integer | 符合条件的总条数 |

### GET `/api/local-files/batch-status`

<a id="get-api-local-files-batch-status"></a>

查询文件任务。 查询批量文件任务状态。

**参数**

| 名称 | 位置 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- | --- |
| `task_id` | query | string | 是 | 统一任务队列的任务 ID，可用 GET /api/tasks/{id} 查询进度 |

**调用**

```js
const res = await ctx.api.get('/api/local-files/batch-status?task_id=20261029213000-a1b2c3')
```

**响应 200**（按契约结构生成的示例值）

```json
{
  "done": 0,
  "errors": [
    ""
  ],
  "id": "<id>",
  "operation": "delete",
  "status": "<status>",
  "total": 0
}
```

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `done` | integer |  |
| `errors` | string[] | 逐项失败原因 |
| `id` | string |  |
| `operation` | "delete" / "move" / "copy" |  |
| `status` | string |  |
| `total` | integer | 符合条件的总条数 |

### POST `/api/local-files/copy`

<a id="post-api-local-files-copy"></a>

复制文件。 按宿主规则在本地挂载或 CD2 之间复制文件。

**请求体（JSON）**

| 字段 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- |
| `dest_dir` | string | 是 | 目标目录的宿主绝对路径 |
| `src_paths` | string[] | 是 | 要处理的宿主绝对路径（本地与 CD2 挂载路径不能混合） |

**调用**

```js
const res = await ctx.api.post('/api/local-files/copy', {
  "dest_dir": "/mnt/media/电影",
  "src_paths": [
    ""
  ]
})
```

**响应 200**（按契约结构生成的示例值）

```json
{
  "success": true
}
```

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `success` | true | 是否成功；成功响应中恒为 true，失败时返回 4xx/5xx 与 error |

### POST `/api/local-files/mkdir`

<a id="post-api-local-files-mkdir"></a>

创建目录。 在文件管理器中创建目录。

**请求体（JSON）**

| 字段 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- |
| `path` | string | 是 | 宿主绝对 Linux 路径；位于 CD2 挂载路径下时由 CD2 处理 |

**调用**

```js
const res = await ctx.api.post('/api/local-files/mkdir', {
  "path": "/mnt/media/电影"
})
```

**响应 200**（按契约结构生成的示例值）

```json
{
  "path": "/mnt/media/电影",
  "success": true
}
```

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `path` | string | 宿主绝对 Linux 路径；位于 CD2 挂载路径下时由 CD2 处理 |
| `success` | true | 是否成功；成功响应中恒为 true，失败时返回 4xx/5xx 与 error |

### POST `/api/local-files/move`

<a id="post-api-local-files-move"></a>

移动文件。 文件管理器移动：把 src_paths 移入 dest_dir，同步执行，完成后返回。本地与 CD2 挂载路径不能混合。插件需要进度或跨本地/CD2 时用 ctx.files.call({operation:'move'})。

**请求体（JSON）**

| 字段 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- |
| `dest_dir` | string | 是 | 目标目录的宿主绝对路径 |
| `src_paths` | string[] | 是 | 要处理的宿主绝对路径（本地与 CD2 挂载路径不能混合） |

**调用**

```js
const res = await ctx.api.post('/api/local-files/move', {
  "src_paths": [
    "/mnt/inbox/a.mkv"
  ],
  "dest_dir": "/mnt/media/电影"
})
```

**响应 200**

```json
{
  "success": true
}
```

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `success` | true | 是否成功；成功响应中恒为 true，失败时返回 4xx/5xx 与 error |

### POST `/api/local-files/organize`

<a id="post-api-local-files-organize"></a>

整理文件。 按整理规则整理一个宿主路径，提交后在后台执行。rule_id 省略时由宿主按路径选择规则；可选规则见 organize-options。

**请求体（JSON）**

| 字段 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- |
| `path` | string | 是 | 宿主绝对 Linux 路径；位于 CD2 挂载路径下时由 CD2 处理 |
| `rule_id` | integer(int64) |  | 规则 ID（整理规则或同步规则，见所在接口） |

**调用**

```js
const res = await ctx.api.post('/api/local-files/organize', {
  "path": "/mnt/inbox/Example.S01E01.mkv",
  "rule_id": 1
})
```

**响应 200**

```json
{
  "message": "整理任务已提交"
}
```

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `message` | string | 给用户看的结果说明 |

### GET `/api/local-files/organize-options`

<a id="get-api-local-files-organize-options"></a>

读取整理选项。 读取可用的整理目标和规则。

**参数**

| 名称 | 位置 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- | --- |
| `path` | query | string | 是 | 宿主绝对 Linux 路径；位于 CD2 挂载路径下时由 CD2 处理 |

**调用**

```js
const res = await ctx.api.get('/api/local-files/organize-options?path=%2Fmnt%2Fmedia%2F%E7%94%B5%E5%BD%B1')
```

**响应 200**（按契约结构生成的示例值）

```json
{
  "mode": "<mode>",
  "path": "/mnt/media/电影",
  "rules": [
    {
      "cloud_name": "<cloud_name>",
      "id": 0,
      "media_type": "tv",
      "mode": "<mode>",
      "name": "<name>",
      "source_path": "<source_path>",
      "target_path": "<target_path>",
      "transfer_mode": "<transfer_mode>"
    }
  ]
}
```

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `mode` | string |  |
| `path` | string | 宿主绝对 Linux 路径；位于 CD2 挂载路径下时由 CD2 处理 |
| `rules` | OrganizeRuleOption[] |  |
| `rules[].cloud_name` | string | CD2 中的云盘名称（挂载根下第一层目录） |
| `rules[].id` | integer(int64) |  |
| `rules[].media_type` | string | 媒体类型：movie 电影、tv 剧集 |
| `rules[].mode` | string |  |
| `rules[].name` | string | 名称 |
| `rules[].source_path` | string | 来源宿主路径 |
| `rules[].target_path` | string | 目标宿主路径 |
| `rules[].transfer_mode` | string |  |

### POST `/api/local-files/recognize`

<a id="post-api-local-files-recognize"></a>

识别媒体文件。 识别一个文件或目录对应的影视条目（不移动文件）。

**请求体（JSON）**

| 字段 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- |
| `path` | string | 是 | 宿主绝对 Linux 路径；位于 CD2 挂载路径下时由 CD2 处理 |

**调用**

```js
const res = await ctx.api.post('/api/local-files/recognize', {
  "path": "/mnt/inbox/Game.of.Thrones.S01E01.1080p.mkv"
})
```

**响应 200**

```json
{
  "path": "/mnt/inbox/Game.of.Thrones.S01E01.1080p.mkv",
  "name": "Game.of.Thrones.S01E01.1080p.mkv",
  "is_dir": false,
  "media_type": "tv",
  "title": "权力的游戏",
  "year": 2011,
  "tmdb_id": 1399,
  "season": 1,
  "episode": 1
}
```

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `episode` | integer | 集号 |
| `is_dir` | boolean | 是否为目录 |
| `media_type` | "movie" / "tv" | 媒体类型：movie 电影、tv 剧集 |
| `name` | string | 名称 |
| `path` | string | 宿主绝对 Linux 路径；位于 CD2 挂载路径下时由 CD2 处理 |
| `season` | integer | 季号，0 为特别篇 |
| `title` | string | 标题 |
| `tmdb_id` | integer | TMDB 媒体 ID；电影与剧集分别编号，需配合 media_type 使用 |
| `year` | integer | 年份 |

### POST `/api/local-files/rename`

<a id="post-api-local-files-rename"></a>

重命名文件。 重命名文件或目录。

**请求体（JSON）**

| 字段 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- |
| `new_name` | string | 是 | 新名称（不含目录） |
| `old_path` | string | 是 | 原宿主绝对路径 |

**调用**

```js
const res = await ctx.api.post('/api/local-files/rename', {
  "new_name": "<new_name>",
  "old_path": "<old_path>"
})
```

**响应 200**（按契约结构生成的示例值）

```json
{
  "new_path": "<new_path>",
  "success": true
}
```

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `new_path` | string | 改名后的宿主绝对路径 |
| `success` | true | 是否成功；成功响应中恒为 true，失败时返回 4xx/5xx 与 error |

### POST `/api/local-files/rename/execute`

<a id="post-api-local-files-rename-execute"></a>

执行批量重命名。 执行批量重命名。

**请求体（JSON）**

| 字段 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- |
| `items` | object[] | 是 |  |
| `items[].new_name` | string | 是 | 新名称（不含目录） |
| `items[].path` | string | 是 | 宿主绝对 Linux 路径；位于 CD2 挂载路径下时由 CD2 处理 |
| `items[].target_dir` | string |  |  |

**调用**

```js
const res = await ctx.api.post('/api/local-files/rename/execute', {
  "items": [
    {
      "new_name": "<new_name>",
      "path": "/mnt/media/电影",
      "target_dir": "<target_dir>"
    }
  ]
})
```

**响应 200**（按契约结构生成的示例值）

```json
{}
```

响应为宿主或上游服务原样透传的 JSON，字段可能随上游变化；以 HTTP 2xx 判断成功。

### POST `/api/local-files/rename/preview`

<a id="post-api-local-files-rename-preview"></a>

预览重命名。 预览批量重命名结果。

**请求体（JSON）**

| 字段 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- |
| `auto_recognize` | boolean |  |  |
| `include_dirs` | boolean |  |  |
| `paths` | string[] | 是 | 多个宿主绝对路径 |
| `recursive` | boolean |  |  |
| `rules` | object[] |  |  |
| `rules[].case_mode` | string |  |  |
| `rules[].case_sensitive` | boolean |  |  |
| `rules[].classes` | string[] |  |  |
| `rules[].collapse_spaces` | boolean |  |  |
| `rules[].dot_space` | string |  |  |
| `rules[].episode_width` | integer |  |  |
| `rules[].ext_mode` | string |  |  |
| `rules[].find` | string |  |  |
| `rules[].from` | integer |  | range 起始（含），按字符计数 |
| `rules[].index` | integer |  |  |
| `rules[].mode` | string |  |  |
| `rules[].padding` | integer |  |  |
| `rules[].pattern` | string |  |  |
| `rules[].position` | string |  |  |
| `rules[].remove_chars` | string |  |  |
| `rules[].replace_with` | string |  |  |
| `rules[].scope` | string |  | all(默认)  /  first |
| `rules[].season_width` | integer |  |  |
| `rules[].seq_scope` | string |  | global(默认)  /  per_folder |
| `rules[].start` | integer |  |  |
| `rules[].step` | integer |  |  |
| `rules[].template_pattern` | string |  |  |
| `rules[].text` | string |  |  |
| `rules[].to` | integer |  | range 结束（不含） |
| `rules[].trim` | boolean |  |  |
| `rules[].tv_template_pattern` | string |  |  |
| `rules[].type` | string |  |  |
| `rules[].use_regex` | boolean |  |  |
| `rules[].value` | string |  |  |
| `tmdb` | object |  |  |
| `tmdb.media_type` | string |  | 媒体类型：movie 电影、tv 剧集 |
| `tmdb.season` | integer |  | tv：集名解析用；0 = 从识别结果推断 |
| `tmdb.title` | string |  | 标题 |
| `tmdb.tmdb_id` | integer |  | TMDB 媒体 ID；电影与剧集分别编号，需配合 media_type 使用 |
| `tmdb.year` | integer |  | 年份 |
| `tmdb_overrides` | object[] |  |  |
| `tmdb_overrides[].group` | string |  |  |
| `tmdb_overrides[].media_type` | string |  | 媒体类型：movie 电影、tv 剧集 |
| `tmdb_overrides[].tmdb_id` | integer |  | TMDB 媒体 ID；电影与剧集分别编号，需配合 media_type 使用 |

**调用**

```js
const res = await ctx.api.post('/api/local-files/rename/preview', {
  "auto_recognize": true,
  "include_dirs": true,
  "paths": [
    ""
  ],
  "recursive": true,
  "rules": [
    {
      "case_mode": "<case_mode>",
      "case_sensitive": true,
      "classes": [
        ""
      ],
      "collapse_spaces": true,
      "dot_space": "<dot_space>",
      "episode_width": 0,
      "ext_mode": "<ext_mode>",
      "find": "<find>",
      "from": 0,
      "index": 0,
      "mode": "<mode>",
      "padding": 0,
      "pattern": "<pattern>",
      "position": "<position>",
      "remove_chars": "<remove_chars>",
      "replace_with": "<replace_with>",
      "scope": "<scope>",
      "season_width": 0,
      "seq_scope": "<seq_scope>",
      "start": 0,
      "step": 0,
      "template_pattern": "<template_pattern>",
      "text": "<text>",
      "to": 0,
      "trim": true,
      "tv_template_pattern": "<tv_template_pattern>",
      "type": "<type>",
      "use_regex": true,
      "value": "<value>"
    }
  ],
  "tmdb": {
    "media_type": "tv",
    "season": 1,
    "title": "<title>",
    "tmdb_id": 1399,
    "year": 0
  },
  "tmdb_overrides": [
    {
      "group": "<group>",
      "media_type": "tv",
      "tmdb_id": 1399
    }
  ]
})
```

**响应 200**（按契约结构生成的示例值）

```json
{
  "items": [
    {
      "action": "<action>",
      "group": "<group>",
      "is_dir": true,
      "new_name": "<new_name>",
      "old_name": "<old_name>",
      "path": "/mnt/media/电影",
      "reason": "<reason>",
      "size": 0,
      "vars": {}
    }
  ],
  "summary": {}
}
```

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `items` | object[] |  |
| `items[].action` | string |  |
| `items[].group` | string |  |
| `items[].is_dir` | boolean | 是否为目录 |
| `items[].new_name` | string | 新名称（不含目录） |
| `items[].old_name` | string |  |
| `items[].path` | string | 宿主绝对 Linux 路径；位于 CD2 挂载路径下时由 CD2 处理 |
| `items[].reason` | string |  |
| `items[].size` | integer | 字节数 |
| `items[].vars` | object |  |
| `summary` | object |  |

### POST `/api/local-files/scrape`

<a id="post-api-local-files-scrape"></a>

刮削文件。 调用宿主刮削能力处理文件。

**请求体（JSON）**

| 字段 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- |
| `config` | object |  |  |
| `config.banner` | boolean |  |  |
| `config.clear_logo` | boolean |  |  |
| `config.episode_thumb` | boolean |  |  |
| `config.fanart` | boolean |  |  |
| `config.local_root` | string |  |  |
| `config.nfo` | object |  |  |
| `config.nfo.episode` | boolean |  | 集号 |
| `config.nfo.movie` | boolean |  |  |
| `config.nfo.season` | boolean |  | 季号，0 为特别篇 |
| `config.nfo.tv` | boolean |  |  |
| `config.output_mode` | string |  |  |
| `config.overwrite` | boolean |  |  |
| `config.poster` | boolean |  |  |
| `config.season_poster` | boolean |  |  |
| `config.skip_existing` | boolean |  |  |
| `config.strm_rule_id` | integer |  |  |
| `paths` | string[] |  | 多个宿主绝对路径 |

**调用**

```js
const res = await ctx.api.post('/api/local-files/scrape', {
  "config": {
    "banner": true,
    "clear_logo": true,
    "episode_thumb": true,
    "fanart": true,
    "local_root": "<local_root>",
    "nfo": {
      "episode": 1,
      "movie": true,
      "season": 1,
      "tv": true
    },
    "output_mode": "<output_mode>",
    "overwrite": true,
    "poster": true,
    "season_poster": true,
    "skip_existing": true,
    "strm_rule_id": 0
  },
  "paths": [
    ""
  ]
})
```

**响应 200**（按契约结构生成的示例值）

```json
{}
```

响应为宿主或上游服务原样透传的 JSON，字段可能随上游变化；以 HTTP 2xx 判断成功。

### GET `/api/local-files/search`

<a id="get-api-local-files-search"></a>

搜索文件。 在文件管理器中按名称搜索文件。

**参数**

| 名称 | 位置 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- | --- |
| `fuzzy` | query | boolean |  | 是否模糊匹配 |
| `limit` | query | integer |  | 本次最多返回的条数 |
| `path` | query | string |  | 宿主绝对 Linux 路径；位于 CD2 挂载路径下时由 CD2 处理 |
| `q` | query | string |  | 搜索关键词 |

**调用**

```js
const res = await ctx.api.get('/api/local-files/search')
```

**响应 200**（按契约结构生成的示例值）

```json
{
  "backend": "<backend>",
  "current": null,
  "entries": [
    {
      "ext": "<ext>",
      "is_dir": true,
      "mod_time": "<mod_time>",
      "name": "<name>",
      "path": "/mnt/media/电影",
      "size": 0
    }
  ],
  "query": null,
  "truncated": true
}
```

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `backend` | string |  |
| `current` | any |  |
| `entries` | object[] |  |
| `entries[].ext` | string | 扩展名（含点），目录为空 |
| `entries[].is_dir` | boolean | 是否为目录 |
| `entries[].mod_time` | string | 修改时间 |
| `entries[].name` | string | 名称 |
| `entries[].path` | string | 宿主绝对 Linux 路径；位于 CD2 挂载路径下时由 CD2 处理 |
| `entries[].size` | integer | 字节数 |
| `query` | any | 搜索关键词 |
| `truncated` | boolean |  |

### GET `/api/local-files/tree`

<a id="get-api-local-files-tree"></a>

读取目录树。 读取本地挂载或 CD2 挂载目录树。

**参数**

| 名称 | 位置 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- | --- |
| `path` | query | string | 是 | 宿主绝对 Linux 路径；位于 CD2 挂载路径下时由 CD2 处理 |

**调用**

```js
const res = await ctx.api.get('/api/local-files/tree?path=%2Fmnt%2Fmedia%2F%E7%94%B5%E5%BD%B1')
```

**响应 200**（按契约结构生成的示例值）

```json
{
  "children": [
    {
      "children": [
        {
          "children": [
            null
          ],
          "name": "<name>",
          "path": "/mnt/media/电影"
        }
      ],
      "name": "<name>",
      "path": "/mnt/media/电影"
    }
  ],
  "name": "<name>",
  "path": "/mnt/media/电影"
}
```

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `children` | LocalDirectoryTree[] |  |
| `children[].children` | LocalDirectoryTree[] |  |
| `children[].children[].children` | LocalDirectoryTree[] |  |
| `children[].children[].name` | string | 名称 |
| `children[].children[].path` | string | 宿主绝对 Linux 路径；位于 CD2 挂载路径下时由 CD2 处理 |
| `children[].name` | string | 名称 |
| `children[].path` | string | 宿主绝对 Linux 路径；位于 CD2 挂载路径下时由 CD2 处理 |
| `name` | string | 名称 |
| `path` | string | 宿主绝对 Linux 路径；位于 CD2 挂载路径下时由 CD2 处理 |

### POST `/api/local-files/upload`

<a id="post-api-local-files-upload"></a>

上传文件。 以 multipart 表单上传文件到文件管理器目录。

**调用**

```js
const res = await ctx.api.post('/api/local-files/upload', {})
```

**响应 200**（按契约结构生成的示例值）

```json
{
  "success": true,
  "uploaded": [
    ""
  ]
}
```

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `success` | boolean | 是否成功；成功响应中恒为 true，失败时返回 4xx/5xx 与 error |
| `uploaded` | string[] |  |

## 整理

### GET `/api/organize/categories`

<a id="get-api-organize-categories"></a>

读取整理分类。 读取整理分类列表。

**参数**

| 名称 | 位置 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- | --- |
| `media_type` | query | string |  | 媒体类型：movie 电影、tv 剧集 |

**调用**

```js
const res = await ctx.api.get('/api/organize/categories')
```

**响应 200**（按契约结构生成的示例值）

```json
[
  {
    "categories": "<categories>",
    "created_at": "2026-10-29T21:30:00+08:00",
    "id": 0,
    "media_type": "tv",
    "name": "<name>",
    "updated_at": "2026-10-29T21:30:00+08:00"
  }
]
```

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `[].categories` | string | JSON数组 |
| `[].created_at` | string(date-time) | 创建时间（RFC 3339） |
| `[].id` | integer |  |
| `[].media_type` | string | 媒体类型：movie 电影、tv 剧集 |
| `[].name` | string | 名称 |
| `[].updated_at` | string(date-time) | 更新时间（RFC 3339） |

### GET `/api/organize/categories/{id}`

<a id="get-api-organize-categories-id"></a>

读取整理分类详情。 读取一个整理分类的详情。

**参数**

| 名称 | 位置 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- | --- |
| `id` | path | string | 是 |  |

**调用**

```js
const res = await ctx.api.get('/api/organize/categories/id')
```

**响应 200**（按契约结构生成的示例值）

```json
{
  "categories": "<categories>",
  "created_at": "2026-10-29T21:30:00+08:00",
  "id": 0,
  "media_type": "tv",
  "name": "<name>",
  "updated_at": "2026-10-29T21:30:00+08:00"
}
```

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `categories` | string | JSON数组 |
| `created_at` | string(date-time) | 创建时间（RFC 3339） |
| `id` | integer |  |
| `media_type` | string | 媒体类型：movie 电影、tv 剧集 |
| `name` | string | 名称 |
| `updated_at` | string(date-time) | 更新时间（RFC 3339） |

### GET `/api/organize/category-templates`

<a id="get-api-organize-category-templates"></a>

读取分类模板。 读取整理分类模板。

**调用**

```js
const res = await ctx.api.get('/api/organize/category-templates')
```

**响应 200**（按契约结构生成的示例值）

```json
[
  {
    "description": "<description>",
    "key": "<key>",
    "movie": [
      {
        "conditions": [
          null
        ],
        "name": "<name>",
        "path": "/mnt/media/电影",
        "priority": 0
      }
    ],
    "name": "<name>",
    "summary": {},
    "tv": [
      {
        "conditions": [
          null
        ],
        "name": "<name>",
        "path": "/mnt/media/电影",
        "priority": 0
      }
    ],
    "warnings": [
      ""
    ]
  }
]
```

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `[].description` | string |  |
| `[].key` | string |  |
| `[].movie` | object[] |  |
| `[].movie[].conditions` | any[] |  |
| `[].movie[].name` | string | 名称 |
| `[].movie[].path` | string | 宿主绝对 Linux 路径；位于 CD2 挂载路径下时由 CD2 处理 |
| `[].movie[].priority` | integer |  |
| `[].name` | string | 名称 |
| `[].summary` | object |  |
| `[].tv` | object[] |  |
| `[].tv[].conditions` | any[] |  |
| `[].tv[].name` | string | 名称 |
| `[].tv[].path` | string | 宿主绝对 Linux 路径；位于 CD2 挂载路径下时由 CD2 处理 |
| `[].tv[].priority` | integer |  |
| `[].warnings` | string[] |  |

### GET `/api/organize/config`

<a id="get-api-organize-config"></a>

读取整理配置。 读取文件整理配置。

**调用**

```js
const res = await ctx.api.get('/api/organize/config')
```

**响应 200**（按契约结构生成的示例值）

```json
{
  "blacklist": "<blacklist>",
  "concurrent_organize": 0,
  "created_at": "2026-10-29T21:30:00+08:00",
  "custom_placeholders": "<custom_placeholders>",
  "custom_release_groups": "<custom_release_groups>",
  "custom_words": "<custom_words>",
  "field_alias_config": "<field_alias_config>",
  "id": 0,
  "movie_template": "<movie_template>",
  "tv_template": "<tv_template>",
  "updated_at": "2026-10-29T21:30:00+08:00",
  "version_folder_config": "<version_folder_config>",
  "wash_version_config": "<wash_version_config>"
}
```

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `blacklist` | string | 全局黑名单，每行一个关键词，文件名包含则跳过整理 |
| `concurrent_organize` | integer | 批量整理并发数（默认1，最大3） |
| `created_at` | string(date-time) | 创建时间（RFC 3339） |
| `custom_placeholders` | string | 自定义占位符正则，每行一个 |
| `custom_release_groups` | string | 自定义制作组/字幕组，每行一个（支持正则） |
| `custom_words` | string | 自定义识别词（同类工具格式：每行一条，# 注释，屏蔽词/替换词 => /集偏移 <> >>） |
| `field_alias_config` | string | 全局字段别名映射 JSON（适用于所有重命名模板） |
| `id` | integer |  |
| `movie_template` | string |  |
| `tv_template` | string |  |
| `updated_at` | string(date-time) | 更新时间（RFC 3339） |
| `version_folder_config` | string | 多版目录全局配置 JSON（启用开关、别名映射等） |
| `wash_version_config` | string | 洗版评分规则 JSON |

### GET `/api/organize/history`

<a id="get-api-organize-history"></a>

读取整理历史。 读取文件整理历史。

**参数**

| 名称 | 位置 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- | --- |
| `mode` | query | string |  |  |
| `page` | query | integer |  | 页码，从 1 开始 |
| `page_size` | query | integer |  | 每页条数 |
| `rule_id` | query | integer |  | 规则 ID（整理规则或同步规则，见所在接口） |
| `search` | query | string |  |  |
| `status` | query | string |  |  |

**调用**

```js
const res = await ctx.api.get('/api/organize/history')
```

**响应 200**（按契约结构生成的示例值）

```json
{
  "list": [
    {
      "action": "<action>",
      "backdrop_path": "<backdrop_path>",
      "can_manual_organize": true,
      "completed_at": "2026-10-29T21:30:00+08:00",
      "confidence": 0,
      "created_at": "2026-10-29T21:30:00+08:00",
      "detail_msg": "<detail_msg>",
      "episode": 1,
      "error_msg": "<error_msg>",
      "id": 0,
      "manual_source_path": "<manual_source_path>",
      "media_type": "tv",
      "method": "<method>",
      "organize_mode": "<organize_mode>",
      "overview": "<overview>",
      "poster_path": "/1XS1oqL89opfnbLl8WnZY1O1uJx.jpg",
      "rule_id": 1,
      "rule_name": "<rule_name>",
      "season": 1,
      "season_specified": true,
      "source_check_error": "<source_check_error>",
      "source_exists": true,
      "source_hash": "<source_hash>",
      "source_identity": "<source_identity>",
      "source_path": "<source_path>",
      "status": "<status>",
      "target_check_error": "<target_check_error>",
      "target_exists": true,
      "target_path": "<target_path>",
      "title": "<title>",
      "tmdb_id": 1399,
      "transfer_mode": "<transfer_mode>",
      "year": 0
    }
  ],
  "page": 1,
  "page_size": 30,
  "status_counts": {},
  "total": 0
}
```

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `list` | object[] |  |
| `list[].action` | string | organize=整理 / wash=洗版PK / manual_organize=手动整理 |
| `list[].backdrop_path` | string | TMDB 横版背景路径 |
| `list[].can_manual_organize` | boolean |  |
| `list[].completed_at` | string(date-time) |  |
| `list[].confidence` | number | 识别置信度 |
| `list[].created_at` | string(date-time) | 创建时间（RFC 3339） |
| `list[].detail_msg` | string | 过程详情（如洗版评分对比） |
| `list[].episode` | integer | 集（电视剧） |
| `list[].error_msg` | string | 失败原因 |
| `list[].id` | integer |  |
| `list[].manual_source_path` | string |  |
| `list[].media_type` | string | 媒体类型：movie 电影、tv 剧集 |
| `list[].method` | string | 识别方式：regex/ai/ai+regex |
| `list[].organize_mode` | string |  |
| `list[].overview` | string | TMDB媒体简介 |
| `list[].poster_path` | string | TMDB海报路径（如 /xxxx.jpg） |
| `list[].rule_id` | integer | 规则 ID（整理规则或同步规则，见所在接口） |
| `list[].rule_name` | string | 规则名称（API层填充，不存数据库） |
| `list[].season` | integer | 季（电视剧） |
| `list[].season_specified` | boolean | 季号是否由识别结果明确给出（用于区分 S00 与未知季） |
| `list[].source_check_error` | string |  |
| `list[].source_exists` | boolean |  |
| `list[].source_hash` | string | 规则ID+源路径的稳定收据键 |
| `list[].source_identity` | string | 实际文件对象身份（本地文件ID/CD2文件ID） |
| `list[].source_path` | string | 源文件路径 |
| `list[].status` | string |  |
| `list[].target_check_error` | string |  |
| `list[].target_exists` | boolean |  |
| `list[].target_path` | string | 目标文件路径 |
| `list[].title` | string | 识别出的标题 |
| `list[].tmdb_id` | integer | TMDB 媒体 ID；电影与剧集分别编号，需配合 media_type 使用 |
| `list[].transfer_mode` | string | 整理方式：move/hardlink |
| `list[].year` | integer | 年份 |
| `page` | any | 页码，从 1 开始 |
| `page_size` | any | 每页条数 |
| `status_counts` | object |  |
| `total` | integer | 符合条件的总条数 |

### DELETE `/api/organize/history/{id}`

<a id="delete-api-organize-history-id"></a>

删除整理历史。 删除一条整理历史记录。

**参数**

| 名称 | 位置 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- | --- |
| `id` | path | string | 是 |  |
| `action` | query | string |  |  |

**调用**

```js
const res = await ctx.api.delete('/api/organize/history/id')
```

**响应 200**（按契约结构生成的示例值）

```json
{
  "deleted": 0,
  "success": true
}
```

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `deleted` | integer |  |
| `success` | boolean | 是否成功；成功响应中恒为 true，失败时返回 4xx/5xx 与 error |

### GET `/api/organize/history/{id}/detail`

<a id="get-api-organize-history-id-detail"></a>

读取整理详情。 读取一条整理历史详情。

**参数**

| 名称 | 位置 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- | --- |
| `id` | path | string | 是 |  |

**调用**

```js
const res = await ctx.api.get('/api/organize/history/id/detail')
```

**响应 200**（按契约结构生成的示例值）

```json
{
  "detail_msg": "<detail_msg>",
  "ffp": {
    "data": null,
    "raw": "<raw>",
    "source": "<source>"
  },
  "id": 0,
  "source_path": "<source_path>",
  "target_path": "<target_path>",
  "wash_comparison": {
    "decision": "<decision>",
    "mode": "<mode>",
    "raw_lines": [
      ""
    ],
    "source": {
      "audio_codec": null,
      "color_depth": null,
      "dimension_scores": null,
      "file_extension": null,
      "file_name": null,
      "file_size": null,
      "frame_rate": null,
      "hdr": null,
      "label": null,
      "resolution": null,
      "score": null,
      "source": null,
      "subtitle": null,
      "video_codec": null
    },
    "summary": "<summary>",
    "targets": [
      {
        "audio_codec": null,
        "color_depth": null,
        "dimension_scores": null,
        "file_extension": null,
        "file_name": null,
        "file_size": null,
        "frame_rate": null,
        "hdr": null,
        "label": null,
        "resolution": null,
        "score": null,
        "source": null,
        "subtitle": null,
        "video_codec": null
      }
    ],
    "winner": "<winner>",
    "winner_index": 0
  }
}
```

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `detail_msg` | string |  |
| `ffp` | object |  |
| `ffp.data` | any |  |
| `ffp.raw` | string |  |
| `ffp.source` | string |  |
| `id` | integer |  |
| `source_path` | string | 来源宿主路径 |
| `target_path` | string | 目标宿主路径 |
| `wash_comparison` | object |  |
| `wash_comparison.decision` | string |  |
| `wash_comparison.mode` | string |  |
| `wash_comparison.raw_lines` | string[] |  |
| `wash_comparison.source` | object |  |
| `wash_comparison.source.audio_codec` | any |  |
| `wash_comparison.source.color_depth` | any |  |
| `wash_comparison.source.dimension_scores` | any |  |
| `wash_comparison.source.file_extension` | any |  |
| `wash_comparison.source.file_name` | any |  |
| `wash_comparison.source.file_size` | any |  |
| `wash_comparison.source.frame_rate` | any |  |
| `wash_comparison.source.hdr` | any |  |
| `wash_comparison.source.label` | any |  |
| `wash_comparison.source.resolution` | any |  |
| `wash_comparison.source.score` | any |  |
| `wash_comparison.source.source` | any |  |
| `wash_comparison.source.subtitle` | any |  |
| `wash_comparison.source.video_codec` | any |  |
| `wash_comparison.summary` | string |  |
| `wash_comparison.targets` | object[] |  |
| `wash_comparison.targets[].audio_codec` | any |  |
| `wash_comparison.targets[].color_depth` | any |  |
| `wash_comparison.targets[].dimension_scores` | any |  |
| `wash_comparison.targets[].file_extension` | any |  |
| `wash_comparison.targets[].file_name` | any |  |
| `wash_comparison.targets[].file_size` | any |  |
| `wash_comparison.targets[].frame_rate` | any |  |
| `wash_comparison.targets[].hdr` | any |  |
| `wash_comparison.targets[].label` | any |  |
| `wash_comparison.targets[].resolution` | any |  |
| `wash_comparison.targets[].score` | any |  |
| `wash_comparison.targets[].source` | any |  |
| `wash_comparison.targets[].subtitle` | any |  |
| `wash_comparison.targets[].video_codec` | any |  |
| `wash_comparison.winner` | string |  |
| `wash_comparison.winner_index` | integer |  |

### POST `/api/organize/history/{id}/manual-organize`

<a id="post-api-organize-history-id-manual-organize"></a>

手动整理。 对一条历史记录执行手动整理。

**参数**

| 名称 | 位置 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- | --- |
| `id` | path | string | 是 |  |

**请求体（JSON）**

| 字段 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- |
| `media_type` | string |  | 媒体类型：movie 电影、tv 剧集 |
| `season` | integer |  | 季号，0 为特别篇 |
| `sync_directory` | boolean |  |  |
| `tmdb_id` | integer |  | TMDB 媒体 ID；电影与剧集分别编号，需配合 media_type 使用 |
| `type` | string |  |  |

**调用**

```js
const res = await ctx.api.post('/api/organize/history/id/manual-organize', {
  "media_type": "tv",
  "season": 1,
  "sync_directory": true,
  "tmdb_id": 1399,
  "type": "<type>"
})
```

**响应 200**（按契约结构生成的示例值）

```json
{
  "file_count": 0,
  "message": null,
  "sibling_video_count": 0,
  "success": true,
  "task_id": "20261029213000-a1b2c3"
}
```

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `file_count` | integer |  |
| `message` | any | 给用户看的结果说明 |
| `sibling_video_count` | integer |  |
| `success` | boolean | 是否成功；成功响应中恒为 true，失败时返回 4xx/5xx 与 error |
| `task_id` | string | 统一任务队列的任务 ID，可用 GET /api/tasks/{id} 查询进度 |

### GET `/api/organize/history/{id}/manual-organize-context`

<a id="get-api-organize-history-id-manual-organize-context"></a>

读取手动整理上下文。 读取一条历史记录的手动整理上下文。

**参数**

| 名称 | 位置 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- | --- |
| `id` | path | string | 是 |  |

**调用**

```js
const res = await ctx.api.get('/api/organize/history/id/manual-organize-context')
```

**响应 200**（按契约结构生成的示例值）

```json
{
  "can_sync_directory": true,
  "directory": "<directory>",
  "history_id": 0,
  "sibling_video_count": 0,
  "source_path": "<source_path>",
  "status": "<status>",
  "total_video_count": 0
}
```

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `can_sync_directory` | boolean |  |
| `directory` | string |  |
| `history_id` | integer |  |
| `sibling_video_count` | integer |  |
| `source_path` | string | 来源宿主路径 |
| `status` | string |  |
| `total_video_count` | integer |  |

### POST `/api/organize/history/{id}/rename-source`

<a id="post-api-organize-history-id-rename-source"></a>

重命名整理来源。 修正一条历史记录的来源名称。

**参数**

| 名称 | 位置 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- | --- |
| `id` | path | string | 是 |  |

**请求体（JSON）**

| 字段 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- |
| `new_name` | string | 是 | 新名称（不含目录） |

**调用**

```js
const res = await ctx.api.post('/api/organize/history/id/rename-source', {
  "new_name": "<new_name>"
})
```

**响应 200**（按契约结构生成的示例值）

```json
{
  "message": "<message>",
  "success": true,
  "warnings": [
    ""
  ]
}
```

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `message` | string | 给用户看的结果说明 |
| `success` | boolean | 是否成功；成功响应中恒为 true，失败时返回 4xx/5xx 与 error |
| `warnings` | string[] |  |

### GET `/api/organize/jobs/{job_id}/progress`

<a id="get-api-organize-jobs-job-id-progress"></a>

读取整理进度。 读取一个整理任务的进度。

**参数**

| 名称 | 位置 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- | --- |
| `job_id` | path | string | 是 |  |

**调用**

```js
const res = await ctx.api.get('/api/organize/jobs/job_id/progress')
```

**响应 200**（按契约结构生成的示例值）

```json
{
  "created_at": "2026-10-29T21:30:00+08:00",
  "deleted_files": 0,
  "end_time": "2026-10-29T21:30:00+08:00",
  "error": "<error>",
  "failed_files": 0,
  "id": "<id>",
  "logs": [
    ""
  ],
  "merged_into_task_id": "<merged_into_task_id>",
  "message": "<message>",
  "name": "<name>",
  "progress": 0,
  "result": null,
  "result_available": true,
  "result_version": 0,
  "rule_id": 1,
  "rule_name": "<rule_name>",
  "start_time": "2026-10-29T21:30:00+08:00",
  "status": "<status>",
  "sync_type": "<sync_type>",
  "synced_files": 0,
  "total_files": 0,
  "type": "<type>"
}
```

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `created_at` | string(date-time) | 创建时间（RFC 3339） |
| `deleted_files` | integer | 删除文件数 |
| `end_time` | string(date-time) | 结束时间 |
| `error` | string | 错误信息 |
| `failed_files` | integer | 失败文件数 |
| `id` | string |  |
| `logs` | string[] | 实时日志 |
| `merged_into_task_id` | string | 去重后实际执行中的任务 ID |
| `message` | string | 当前状态消息 |
| `name` | string | 名称 |
| `progress` | number | 进度百分比 |
| `result` | any | 通用后台任务最终结果（主要供 AI 长任务轮询） |
| `result_available` | boolean |  |
| `result_version` | integer |  |
| `rule_id` | integer | 关联规则ID |
| `rule_name` | string | 规则名称 |
| `start_time` | string(date-time) | 开始时间 |
| `status` | string |  |
| `sync_type` | string | 同步类型 |
| `synced_files` | integer | 已同步文件数 |
| `total_files` | integer | 总文件数 |
| `type` | string |  |

### GET `/api/organize/queue`

<a id="get-api-organize-queue"></a>

读取整理队列。 读取待整理队列。

**调用**

```js
const res = await ctx.api.get('/api/organize/queue')
```

**响应 200**（按契约结构生成的示例值）

```json
{
  "cd2_discovery": {},
  "cd2_polls": {}
}
```

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `cd2_discovery` | object |  |
| `cd2_polls` | object |  |

### POST `/api/organize/retry-failed`

<a id="post-api-organize-retry-failed"></a>

重试失败整理。 重试失败的整理任务。

**请求体（JSON）**

| 字段 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- |
| `ids` | integer[] |  | 可选：指定历史记录ID列表 |
| `rule_id` | integer |  | 可选：指定规则ID |

**调用**

```js
const res = await ctx.api.post('/api/organize/retry-failed', {
  "ids": [
    0
  ],
  "rule_id": 1
})
```

**响应 200**（按契约结构生成的示例值）

```json
{
  "message": "<message>",
  "submitted": 0,
  "success": true,
  "total": 0
}
```

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `message` | string | 给用户看的结果说明 |
| `submitted` | integer |  |
| `success` | boolean | 是否成功；成功响应中恒为 true，失败时返回 4xx/5xx 与 error |
| `total` | integer | 符合条件的总条数 |

### GET `/api/organize/rules`

<a id="get-api-organize-rules"></a>

读取整理规则。 读取文件整理规则列表。

**调用**

```js
const res = await ctx.api.get('/api/organize/rules')
```

**响应 200**（按契约结构生成的示例值）

```json
[
  {
    "ai_threshold": 0,
    "category_id": 0,
    "cloud_name": "<cloud_name>",
    "created_at": "2026-10-29T21:30:00+08:00",
    "delete_empty_dir": true,
    "delete_filtered_source": true,
    "delete_source": true,
    "duplicate_policy": "<duplicate_policy>",
    "enable_monitor": true,
    "enabled": true,
    "exclude_extensions": "<exclude_extensions>",
    "exclude_paths": [
      ""
    ],
    "failure_action": "<failure_action>",
    "failure_path": "<failure_path>",
    "file_extensions": "<file_extensions>",
    "id": 0,
    "input_type": "<input_type>",
    "is_default": true,
    "media_type": "tv",
    "min_file_size": 0,
    "mode": "<mode>",
    "monitor_interval": 0,
    "multi_version_wash_config": "<multi_version_wash_config>",
    "name": "<name>",
    "organize_strategy": "<organize_strategy>",
    "pre_filter_config": "<pre_filter_config>",
    "rename_template": "<rename_template>",
    "scrape_config": {
      "banner": true,
      "clear_logo": true,
      "episode_thumb": true,
      "fanart": true,
      "local_root": "<local_root>",
      "nfo": {
        "episode": 1,
        "movie": null,
        "season": 1,
        "tv": null
      },
      "output_mode": "<output_mode>",
      "overwrite": true,
      "poster": true,
      "season_poster": true,
      "skip_existing": true,
      "strm_rule_id": 0
    },
    "scrape_enabled": true,
    "source_cid": "2876543210987654321",
    "source_path": "<source_path>",
    "sync_subtitle": true,
    "target_path": "<target_path>",
    "transfer_mode": "<transfer_mode>",
    "updated_at": "2026-10-29T21:30:00+08:00",
    "use_ai": true,
    "use_ai_always": true,
    "use_ai_on_no_title": true,
    "use_ai_on_tmdb_miss": true,
    "use_category": true,
    "use_ffprobe": true,
    "use_type_folder": true
  }
]
```

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `[].ai_threshold` | number |  |
| `[].category_id` | integer |  |
| `[].cloud_name` | string | 云盘名称（用于组合 CD2 内部路径） |
| `[].created_at` | string(date-time) | 创建时间（RFC 3339） |
| `[].delete_empty_dir` | boolean | 整理完成后智能清理：删除已无媒体（视频 / 虚拟影库为 STRM）的源目录并逐级向上 |
| `[].delete_filtered_source` | boolean | 被排除/淘汰时是否删除源文件 |
| `[].delete_source` | boolean | 整理完成后删除源文件 |
| `[].duplicate_policy` | string | 重复策略 |
| `[].enable_monitor` | boolean | 启用自动监控 |
| `[].enabled` | boolean | 是否启用 |
| `[].exclude_extensions` | string | 排除扩展名，逗号分隔 |
| `[].exclude_paths` | string[] |  |
| `[].failure_action` | string |  |
| `[].failure_path` | string |  |
| `[].file_extensions` | string | 允许的扩展名，逗号分隔 |
| `[].id` | integer |  |
| `[].input_type` | string | video（默认）/strm（仅 .strm） |
| `[].is_default` | boolean | 默认规则不可删除 |
| `[].media_type` | string | 媒体类型：movie 电影、tv 剧集 |
| `[].min_file_size` | integer | 最小文件大小（MB） |
| `[].mode` | string |  |
| `[].monitor_interval` | integer | 轮询间隔（秒），CD2模式有效 |
| `[].multi_version_wash_config` | string | 多版本洗版配置 JSON（仅 multi_version_wash 策略） |
| `[].name` | string | 名称 |
| `[].organize_strategy` | string | 整理策略: single（单一版本，默认）/ multi_version（多版共存） |
| `[].pre_filter_config` | string | 前置过滤条件 JSON（识别完成后立刻判断） |
| `[].rename_template` | string |  |
| `[].scrape_config` | object |  |
| `[].scrape_config.banner` | boolean |  |
| `[].scrape_config.clear_logo` | boolean |  |
| `[].scrape_config.episode_thumb` | boolean |  |
| `[].scrape_config.fanart` | boolean |  |
| `[].scrape_config.local_root` | string |  |
| `[].scrape_config.nfo` | object |  |
| `[].scrape_config.nfo.episode` | any | 集号 |
| `[].scrape_config.nfo.movie` | any |  |
| `[].scrape_config.nfo.season` | any | 季号，0 为特别篇 |
| `[].scrape_config.nfo.tv` | any |  |
| `[].scrape_config.output_mode` | string |  |
| `[].scrape_config.overwrite` | boolean |  |
| `[].scrape_config.poster` | boolean |  |
| `[].scrape_config.season_poster` | boolean |  |
| `[].scrape_config.skip_existing` | boolean |  |
| `[].scrape_config.strm_rule_id` | integer |  |
| `[].scrape_enabled` | boolean |  |
| `[].source_cid` | string | 源路径CID（CD2目录树匹配用） |
| `[].source_path` | string | 来源宿主路径 |
| `[].sync_subtitle` | boolean | 整理时同步移动/重命名同名字幕文件 |
| `[].target_path` | string | 目标宿主路径 |
| `[].transfer_mode` | string | move/hardlink（默认 move） |
| `[].updated_at` | string(date-time) | 更新时间（RFC 3339） |
| `[].use_ai` | boolean | 启用AI识别（总开关，关闭则下方三个细分开关全部失效） |
| `[].use_ai_always` | boolean | 无论正则成功与否都调用 AI 做二次校正（默认 false，慎用，会消耗大量 token） |
| `[].use_ai_on_no_title` | boolean | 正则无法识别标题时调用 AI（默认 true） |
| `[].use_ai_on_tmdb_miss` | boolean | TMDB 未命中时调用 AI 再次匹配（默认 true） |
| `[].use_category` | boolean | 二级分类目录 |
| `[].use_ffprobe` | boolean | 使用ffprobe获取媒体信息 |
| `[].use_type_folder` | boolean | 一级类型目录（电影/电视剧） |

### POST `/api/organize/rules`

<a id="post-api-organize-rules"></a>

创建整理规则。 创建文件整理规则。

**请求体（JSON）**

| 字段 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- |
| `ai_threshold` | number |  |  |
| `category_id` | integer |  |  |
| `cloud_name` | string |  | 云盘名称（用于组合 CD2 内部路径） |
| `created_at` | string(date-time) |  | 创建时间（RFC 3339） |
| `delete_empty_dir` | boolean |  | 整理完成后智能清理：删除已无媒体（视频 / 虚拟影库为 STRM）的源目录并逐级向上 |
| `delete_filtered_source` | boolean |  | 被排除/淘汰时是否删除源文件 |
| `delete_source` | boolean |  | 整理完成后删除源文件 |
| `duplicate_policy` | string |  | 重复策略 |
| `enable_monitor` | boolean |  | 启用自动监控 |
| `enabled` | boolean |  | 是否启用 |
| `exclude_extensions` | string |  | 排除扩展名，逗号分隔 |
| `exclude_paths` | string[] |  |  |
| `failure_action` | string |  |  |
| `failure_path` | string |  |  |
| `file_extensions` | string |  | 允许的扩展名，逗号分隔 |
| `id` | integer |  |  |
| `input_type` | string |  | video（默认）/strm（仅 .strm） |
| `is_default` | boolean |  | 默认规则不可删除 |
| `media_type` | string |  | 媒体类型：movie 电影、tv 剧集 |
| `min_file_size` | integer |  | 最小文件大小（MB） |
| `mode` | string |  |  |
| `monitor_interval` | integer |  | 轮询间隔（秒），CD2模式有效 |
| `multi_version_wash_config` | string |  | 多版本洗版配置 JSON（仅 multi_version_wash 策略） |
| `name` | string |  | 名称 |
| `organize_strategy` | string |  | 整理策略: single（单一版本，默认）/ multi_version（多版共存） |
| `pre_filter_config` | string |  | 前置过滤条件 JSON（识别完成后立刻判断） |
| `rename_template` | string |  |  |
| `scrape_config` | object |  |  |
| `scrape_config.banner` | boolean |  |  |
| `scrape_config.clear_logo` | boolean |  |  |
| `scrape_config.episode_thumb` | boolean |  |  |
| `scrape_config.fanart` | boolean |  |  |
| `scrape_config.local_root` | string |  |  |
| `scrape_config.nfo` | object |  |  |
| `scrape_config.nfo.episode` | boolean |  | 集号 |
| `scrape_config.nfo.movie` | boolean |  |  |
| `scrape_config.nfo.season` | boolean |  | 季号，0 为特别篇 |
| `scrape_config.nfo.tv` | boolean |  |  |
| `scrape_config.output_mode` | string |  |  |
| `scrape_config.overwrite` | boolean |  |  |
| `scrape_config.poster` | boolean |  |  |
| `scrape_config.season_poster` | boolean |  |  |
| `scrape_config.skip_existing` | boolean |  |  |
| `scrape_config.strm_rule_id` | integer |  |  |
| `scrape_enabled` | boolean |  |  |
| `source_cid` | string |  | 源路径CID（CD2目录树匹配用） |
| `source_path` | string |  | 来源宿主路径 |
| `sync_subtitle` | boolean |  | 整理时同步移动/重命名同名字幕文件 |
| `target_path` | string |  | 目标宿主路径 |
| `transfer_mode` | string |  | move/hardlink（默认 move） |
| `updated_at` | string(date-time) |  | 更新时间（RFC 3339） |
| `use_ai` | boolean |  | 启用AI识别（总开关，关闭则下方三个细分开关全部失效） |
| `use_ai_always` | boolean |  | 无论正则成功与否都调用 AI 做二次校正（默认 false，慎用，会消耗大量 token） |
| `use_ai_on_no_title` | boolean |  | 正则无法识别标题时调用 AI（默认 true） |
| `use_ai_on_tmdb_miss` | boolean |  | TMDB 未命中时调用 AI 再次匹配（默认 true） |
| `use_category` | boolean |  | 二级分类目录 |
| `use_ffprobe` | boolean |  | 使用ffprobe获取媒体信息 |
| `use_type_folder` | boolean |  | 一级类型目录（电影/电视剧） |

**调用**

```js
const res = await ctx.api.post('/api/organize/rules', {
  "ai_threshold": 0,
  "category_id": 0,
  "cloud_name": "<cloud_name>",
  "created_at": "2026-10-29T21:30:00+08:00",
  "delete_empty_dir": true,
  "delete_filtered_source": true,
  "delete_source": true,
  "duplicate_policy": "<duplicate_policy>",
  "enable_monitor": true,
  "enabled": true,
  "exclude_extensions": "<exclude_extensions>",
  "exclude_paths": [
    ""
  ],
  "failure_action": "<failure_action>",
  "failure_path": "<failure_path>",
  "file_extensions": "<file_extensions>",
  "id": 0,
  "input_type": "<input_type>",
  "is_default": true,
  "media_type": "tv",
  "min_file_size": 0,
  "mode": "<mode>",
  "monitor_interval": 0,
  "multi_version_wash_config": "<multi_version_wash_config>",
  "name": "<name>",
  "organize_strategy": "<organize_strategy>",
  "pre_filter_config": "<pre_filter_config>",
  "rename_template": "<rename_template>",
  "scrape_config": {
    "banner": true,
    "clear_logo": true,
    "episode_thumb": true,
    "fanart": true,
    "local_root": "<local_root>",
    "nfo": {
      "episode": 1,
      "movie": true,
      "season": 1,
      "tv": true
    },
    "output_mode": "<output_mode>",
    "overwrite": true,
    "poster": true,
    "season_poster": true,
    "skip_existing": true,
    "strm_rule_id": 0
  },
  "scrape_enabled": true,
  "source_cid": "2876543210987654321",
  "source_path": "<source_path>",
  "sync_subtitle": true,
  "target_path": "<target_path>",
  "transfer_mode": "<transfer_mode>",
  "updated_at": "2026-10-29T21:30:00+08:00",
  "use_ai": true,
  "use_ai_always": true,
  "use_ai_on_no_title": true,
  "use_ai_on_tmdb_miss": true,
  "use_category": true,
  "use_ffprobe": true,
  "use_type_folder": true
})
```

**响应 200**（按契约结构生成的示例值）

```json
{
  "ai_threshold": 0,
  "category_id": 0,
  "cloud_name": "<cloud_name>",
  "created_at": "2026-10-29T21:30:00+08:00",
  "delete_empty_dir": true,
  "delete_filtered_source": true,
  "delete_source": true,
  "duplicate_policy": "<duplicate_policy>",
  "enable_monitor": true,
  "enabled": true,
  "exclude_extensions": "<exclude_extensions>",
  "exclude_paths": [
    ""
  ],
  "failure_action": "<failure_action>",
  "failure_path": "<failure_path>",
  "file_extensions": "<file_extensions>",
  "id": 0,
  "input_type": "<input_type>",
  "is_default": true,
  "media_type": "tv",
  "min_file_size": 0,
  "mode": "<mode>",
  "monitor_interval": 0,
  "multi_version_wash_config": "<multi_version_wash_config>",
  "name": "<name>",
  "organize_strategy": "<organize_strategy>",
  "pre_filter_config": "<pre_filter_config>",
  "rename_template": "<rename_template>",
  "scrape_config": {
    "banner": true,
    "clear_logo": true,
    "episode_thumb": true,
    "fanart": true,
    "local_root": "<local_root>",
    "nfo": {
      "episode": 1,
      "movie": true,
      "season": 1,
      "tv": true
    },
    "output_mode": "<output_mode>",
    "overwrite": true,
    "poster": true,
    "season_poster": true,
    "skip_existing": true,
    "strm_rule_id": 0
  },
  "scrape_enabled": true,
  "source_cid": "2876543210987654321",
  "source_path": "<source_path>",
  "sync_subtitle": true,
  "target_path": "<target_path>",
  "transfer_mode": "<transfer_mode>",
  "updated_at": "2026-10-29T21:30:00+08:00",
  "use_ai": true,
  "use_ai_always": true,
  "use_ai_on_no_title": true,
  "use_ai_on_tmdb_miss": true,
  "use_category": true,
  "use_ffprobe": true,
  "use_type_folder": true
}
```

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `ai_threshold` | number |  |
| `category_id` | integer |  |
| `cloud_name` | string | 云盘名称（用于组合 CD2 内部路径） |
| `created_at` | string(date-time) | 创建时间（RFC 3339） |
| `delete_empty_dir` | boolean | 整理完成后智能清理：删除已无媒体（视频 / 虚拟影库为 STRM）的源目录并逐级向上 |
| `delete_filtered_source` | boolean | 被排除/淘汰时是否删除源文件 |
| `delete_source` | boolean | 整理完成后删除源文件 |
| `duplicate_policy` | string | 重复策略 |
| `enable_monitor` | boolean | 启用自动监控 |
| `enabled` | boolean | 是否启用 |
| `exclude_extensions` | string | 排除扩展名，逗号分隔 |
| `exclude_paths` | string[] |  |
| `failure_action` | string |  |
| `failure_path` | string |  |
| `file_extensions` | string | 允许的扩展名，逗号分隔 |
| `id` | integer |  |
| `input_type` | string | video（默认）/strm（仅 .strm） |
| `is_default` | boolean | 默认规则不可删除 |
| `media_type` | string | 媒体类型：movie 电影、tv 剧集 |
| `min_file_size` | integer | 最小文件大小（MB） |
| `mode` | string |  |
| `monitor_interval` | integer | 轮询间隔（秒），CD2模式有效 |
| `multi_version_wash_config` | string | 多版本洗版配置 JSON（仅 multi_version_wash 策略） |
| `name` | string | 名称 |
| `organize_strategy` | string | 整理策略: single（单一版本，默认）/ multi_version（多版共存） |
| `pre_filter_config` | string | 前置过滤条件 JSON（识别完成后立刻判断） |
| `rename_template` | string |  |
| `scrape_config` | object |  |
| `scrape_config.banner` | boolean |  |
| `scrape_config.clear_logo` | boolean |  |
| `scrape_config.episode_thumb` | boolean |  |
| `scrape_config.fanart` | boolean |  |
| `scrape_config.local_root` | string |  |
| `scrape_config.nfo` | object |  |
| `scrape_config.nfo.episode` | boolean | 集号 |
| `scrape_config.nfo.movie` | boolean |  |
| `scrape_config.nfo.season` | boolean | 季号，0 为特别篇 |
| `scrape_config.nfo.tv` | boolean |  |
| `scrape_config.output_mode` | string |  |
| `scrape_config.overwrite` | boolean |  |
| `scrape_config.poster` | boolean |  |
| `scrape_config.season_poster` | boolean |  |
| `scrape_config.skip_existing` | boolean |  |
| `scrape_config.strm_rule_id` | integer |  |
| `scrape_enabled` | boolean |  |
| `source_cid` | string | 源路径CID（CD2目录树匹配用） |
| `source_path` | string | 来源宿主路径 |
| `sync_subtitle` | boolean | 整理时同步移动/重命名同名字幕文件 |
| `target_path` | string | 目标宿主路径 |
| `transfer_mode` | string | move/hardlink（默认 move） |
| `updated_at` | string(date-time) | 更新时间（RFC 3339） |
| `use_ai` | boolean | 启用AI识别（总开关，关闭则下方三个细分开关全部失效） |
| `use_ai_always` | boolean | 无论正则成功与否都调用 AI 做二次校正（默认 false，慎用，会消耗大量 token） |
| `use_ai_on_no_title` | boolean | 正则无法识别标题时调用 AI（默认 true） |
| `use_ai_on_tmdb_miss` | boolean | TMDB 未命中时调用 AI 再次匹配（默认 true） |
| `use_category` | boolean | 二级分类目录 |
| `use_ffprobe` | boolean | 使用ffprobe获取媒体信息 |
| `use_type_folder` | boolean | 一级类型目录（电影/电视剧） |

### PUT `/api/organize/rules/{id}`

<a id="put-api-organize-rules-id"></a>

更新整理规则。 更新一条整理规则。

**参数**

| 名称 | 位置 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- | --- |
| `id` | path | string | 是 |  |

**请求体（JSON）**

| 字段 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- |
| `ai_threshold` | number |  |  |
| `category_id` | integer |  |  |
| `cloud_name` | string |  | 云盘名称（用于组合 CD2 内部路径） |
| `created_at` | string(date-time) |  | 创建时间（RFC 3339） |
| `delete_empty_dir` | boolean |  | 整理完成后智能清理：删除已无媒体（视频 / 虚拟影库为 STRM）的源目录并逐级向上 |
| `delete_filtered_source` | boolean |  | 被排除/淘汰时是否删除源文件 |
| `delete_source` | boolean |  | 整理完成后删除源文件 |
| `duplicate_policy` | string |  | 重复策略 |
| `enable_monitor` | boolean |  | 启用自动监控 |
| `enabled` | boolean |  | 是否启用 |
| `exclude_extensions` | string |  | 排除扩展名，逗号分隔 |
| `exclude_paths` | string[] |  |  |
| `failure_action` | string |  |  |
| `failure_path` | string |  |  |
| `file_extensions` | string |  | 允许的扩展名，逗号分隔 |
| `id` | integer |  |  |
| `input_type` | string |  | video（默认）/strm（仅 .strm） |
| `is_default` | boolean |  | 默认规则不可删除 |
| `media_type` | string |  | 媒体类型：movie 电影、tv 剧集 |
| `min_file_size` | integer |  | 最小文件大小（MB） |
| `mode` | string |  |  |
| `monitor_interval` | integer |  | 轮询间隔（秒），CD2模式有效 |
| `multi_version_wash_config` | string |  | 多版本洗版配置 JSON（仅 multi_version_wash 策略） |
| `name` | string |  | 名称 |
| `organize_strategy` | string |  | 整理策略: single（单一版本，默认）/ multi_version（多版共存） |
| `pre_filter_config` | string |  | 前置过滤条件 JSON（识别完成后立刻判断） |
| `rename_template` | string |  |  |
| `scrape_config` | object |  |  |
| `scrape_config.banner` | boolean |  |  |
| `scrape_config.clear_logo` | boolean |  |  |
| `scrape_config.episode_thumb` | boolean |  |  |
| `scrape_config.fanart` | boolean |  |  |
| `scrape_config.local_root` | string |  |  |
| `scrape_config.nfo` | object |  |  |
| `scrape_config.nfo.episode` | boolean |  | 集号 |
| `scrape_config.nfo.movie` | boolean |  |  |
| `scrape_config.nfo.season` | boolean |  | 季号，0 为特别篇 |
| `scrape_config.nfo.tv` | boolean |  |  |
| `scrape_config.output_mode` | string |  |  |
| `scrape_config.overwrite` | boolean |  |  |
| `scrape_config.poster` | boolean |  |  |
| `scrape_config.season_poster` | boolean |  |  |
| `scrape_config.skip_existing` | boolean |  |  |
| `scrape_config.strm_rule_id` | integer |  |  |
| `scrape_enabled` | boolean |  |  |
| `source_cid` | string |  | 源路径CID（CD2目录树匹配用） |
| `source_path` | string |  | 来源宿主路径 |
| `sync_subtitle` | boolean |  | 整理时同步移动/重命名同名字幕文件 |
| `target_path` | string |  | 目标宿主路径 |
| `transfer_mode` | string |  | move/hardlink（默认 move） |
| `updated_at` | string(date-time) |  | 更新时间（RFC 3339） |
| `use_ai` | boolean |  | 启用AI识别（总开关，关闭则下方三个细分开关全部失效） |
| `use_ai_always` | boolean |  | 无论正则成功与否都调用 AI 做二次校正（默认 false，慎用，会消耗大量 token） |
| `use_ai_on_no_title` | boolean |  | 正则无法识别标题时调用 AI（默认 true） |
| `use_ai_on_tmdb_miss` | boolean |  | TMDB 未命中时调用 AI 再次匹配（默认 true） |
| `use_category` | boolean |  | 二级分类目录 |
| `use_ffprobe` | boolean |  | 使用ffprobe获取媒体信息 |
| `use_type_folder` | boolean |  | 一级类型目录（电影/电视剧） |

**调用**

```js
const res = await ctx.api.put('/api/organize/rules/id', {
  "ai_threshold": 0,
  "category_id": 0,
  "cloud_name": "<cloud_name>",
  "created_at": "2026-10-29T21:30:00+08:00",
  "delete_empty_dir": true,
  "delete_filtered_source": true,
  "delete_source": true,
  "duplicate_policy": "<duplicate_policy>",
  "enable_monitor": true,
  "enabled": true,
  "exclude_extensions": "<exclude_extensions>",
  "exclude_paths": [
    ""
  ],
  "failure_action": "<failure_action>",
  "failure_path": "<failure_path>",
  "file_extensions": "<file_extensions>",
  "id": 0,
  "input_type": "<input_type>",
  "is_default": true,
  "media_type": "tv",
  "min_file_size": 0,
  "mode": "<mode>",
  "monitor_interval": 0,
  "multi_version_wash_config": "<multi_version_wash_config>",
  "name": "<name>",
  "organize_strategy": "<organize_strategy>",
  "pre_filter_config": "<pre_filter_config>",
  "rename_template": "<rename_template>",
  "scrape_config": {
    "banner": true,
    "clear_logo": true,
    "episode_thumb": true,
    "fanart": true,
    "local_root": "<local_root>",
    "nfo": {
      "episode": 1,
      "movie": true,
      "season": 1,
      "tv": true
    },
    "output_mode": "<output_mode>",
    "overwrite": true,
    "poster": true,
    "season_poster": true,
    "skip_existing": true,
    "strm_rule_id": 0
  },
  "scrape_enabled": true,
  "source_cid": "2876543210987654321",
  "source_path": "<source_path>",
  "sync_subtitle": true,
  "target_path": "<target_path>",
  "transfer_mode": "<transfer_mode>",
  "updated_at": "2026-10-29T21:30:00+08:00",
  "use_ai": true,
  "use_ai_always": true,
  "use_ai_on_no_title": true,
  "use_ai_on_tmdb_miss": true,
  "use_category": true,
  "use_ffprobe": true,
  "use_type_folder": true
})
```

**响应 200**（按契约结构生成的示例值）

```json
{
  "ai_threshold": 0,
  "category_id": 0,
  "cloud_name": "<cloud_name>",
  "created_at": "2026-10-29T21:30:00+08:00",
  "delete_empty_dir": true,
  "delete_filtered_source": true,
  "delete_source": true,
  "duplicate_policy": "<duplicate_policy>",
  "enable_monitor": true,
  "enabled": true,
  "exclude_extensions": "<exclude_extensions>",
  "exclude_paths": [
    ""
  ],
  "failure_action": "<failure_action>",
  "failure_path": "<failure_path>",
  "file_extensions": "<file_extensions>",
  "id": 0,
  "input_type": "<input_type>",
  "is_default": true,
  "media_type": "tv",
  "min_file_size": 0,
  "mode": "<mode>",
  "monitor_interval": 0,
  "multi_version_wash_config": "<multi_version_wash_config>",
  "name": "<name>",
  "organize_strategy": "<organize_strategy>",
  "pre_filter_config": "<pre_filter_config>",
  "rename_template": "<rename_template>",
  "scrape_config": {
    "banner": true,
    "clear_logo": true,
    "episode_thumb": true,
    "fanart": true,
    "local_root": "<local_root>",
    "nfo": {
      "episode": 1,
      "movie": true,
      "season": 1,
      "tv": true
    },
    "output_mode": "<output_mode>",
    "overwrite": true,
    "poster": true,
    "season_poster": true,
    "skip_existing": true,
    "strm_rule_id": 0
  },
  "scrape_enabled": true,
  "source_cid": "2876543210987654321",
  "source_path": "<source_path>",
  "sync_subtitle": true,
  "target_path": "<target_path>",
  "transfer_mode": "<transfer_mode>",
  "updated_at": "2026-10-29T21:30:00+08:00",
  "use_ai": true,
  "use_ai_always": true,
  "use_ai_on_no_title": true,
  "use_ai_on_tmdb_miss": true,
  "use_category": true,
  "use_ffprobe": true,
  "use_type_folder": true
}
```

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `ai_threshold` | number |  |
| `category_id` | integer |  |
| `cloud_name` | string | 云盘名称（用于组合 CD2 内部路径） |
| `created_at` | string(date-time) | 创建时间（RFC 3339） |
| `delete_empty_dir` | boolean | 整理完成后智能清理：删除已无媒体（视频 / 虚拟影库为 STRM）的源目录并逐级向上 |
| `delete_filtered_source` | boolean | 被排除/淘汰时是否删除源文件 |
| `delete_source` | boolean | 整理完成后删除源文件 |
| `duplicate_policy` | string | 重复策略 |
| `enable_monitor` | boolean | 启用自动监控 |
| `enabled` | boolean | 是否启用 |
| `exclude_extensions` | string | 排除扩展名，逗号分隔 |
| `exclude_paths` | string[] |  |
| `failure_action` | string |  |
| `failure_path` | string |  |
| `file_extensions` | string | 允许的扩展名，逗号分隔 |
| `id` | integer |  |
| `input_type` | string | video（默认）/strm（仅 .strm） |
| `is_default` | boolean | 默认规则不可删除 |
| `media_type` | string | 媒体类型：movie 电影、tv 剧集 |
| `min_file_size` | integer | 最小文件大小（MB） |
| `mode` | string |  |
| `monitor_interval` | integer | 轮询间隔（秒），CD2模式有效 |
| `multi_version_wash_config` | string | 多版本洗版配置 JSON（仅 multi_version_wash 策略） |
| `name` | string | 名称 |
| `organize_strategy` | string | 整理策略: single（单一版本，默认）/ multi_version（多版共存） |
| `pre_filter_config` | string | 前置过滤条件 JSON（识别完成后立刻判断） |
| `rename_template` | string |  |
| `scrape_config` | object |  |
| `scrape_config.banner` | boolean |  |
| `scrape_config.clear_logo` | boolean |  |
| `scrape_config.episode_thumb` | boolean |  |
| `scrape_config.fanart` | boolean |  |
| `scrape_config.local_root` | string |  |
| `scrape_config.nfo` | object |  |
| `scrape_config.nfo.episode` | boolean | 集号 |
| `scrape_config.nfo.movie` | boolean |  |
| `scrape_config.nfo.season` | boolean | 季号，0 为特别篇 |
| `scrape_config.nfo.tv` | boolean |  |
| `scrape_config.output_mode` | string |  |
| `scrape_config.overwrite` | boolean |  |
| `scrape_config.poster` | boolean |  |
| `scrape_config.season_poster` | boolean |  |
| `scrape_config.skip_existing` | boolean |  |
| `scrape_config.strm_rule_id` | integer |  |
| `scrape_enabled` | boolean |  |
| `source_cid` | string | 源路径CID（CD2目录树匹配用） |
| `source_path` | string | 来源宿主路径 |
| `sync_subtitle` | boolean | 整理时同步移动/重命名同名字幕文件 |
| `target_path` | string | 目标宿主路径 |
| `transfer_mode` | string | move/hardlink（默认 move） |
| `updated_at` | string(date-time) | 更新时间（RFC 3339） |
| `use_ai` | boolean | 启用AI识别（总开关，关闭则下方三个细分开关全部失效） |
| `use_ai_always` | boolean | 无论正则成功与否都调用 AI 做二次校正（默认 false，慎用，会消耗大量 token） |
| `use_ai_on_no_title` | boolean | 正则无法识别标题时调用 AI（默认 true） |
| `use_ai_on_tmdb_miss` | boolean | TMDB 未命中时调用 AI 再次匹配（默认 true） |
| `use_category` | boolean | 二级分类目录 |
| `use_ffprobe` | boolean | 使用ffprobe获取媒体信息 |
| `use_type_folder` | boolean | 一级类型目录（电影/电视剧） |

### DELETE `/api/organize/rules/{id}`

<a id="delete-api-organize-rules-id"></a>

删除整理规则。 删除一条整理规则。

**参数**

| 名称 | 位置 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- | --- |
| `id` | path | string | 是 |  |

**调用**

```js
const res = await ctx.api.delete('/api/organize/rules/id')
```

**响应 200**（按契约结构生成的示例值）

```json
{
  "success": true
}
```

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `success` | boolean | 是否成功；成功响应中恒为 true，失败时返回 4xx/5xx 与 error |

### POST `/api/organize/rules/{id}/scan`

<a id="post-api-organize-rules-id-scan"></a>

扫描整理规则。 扫描一条整理规则的待处理文件。

**参数**

| 名称 | 位置 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- | --- |
| `id` | path | string | 是 |  |

**调用**

```js
const res = await ctx.api.post('/api/organize/rules/id/scan', {})
```

**响应 200**（按契约结构生成的示例值）

```json
{
  "existing": true,
  "preempted": true,
  "submitted": 0,
  "task_id": "20261029213000-a1b2c3"
}
```

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `existing` | boolean |  |
| `preempted` | boolean |  |
| `submitted` | integer |  |
| `task_id` | string | 统一任务队列的任务 ID，可用 GET /api/tasks/{id} 查询进度 |

### POST `/api/organize/rules/{id}/submit`

<a id="post-api-organize-rules-id-submit"></a>

提交整理任务。 提交一条整理规则的执行任务。

**参数**

| 名称 | 位置 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- | --- |
| `id` | path | string | 是 |  |

**请求体（JSON）**

| 字段 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- |
| `source_path` | string |  | 来源宿主路径 |

**调用**

```js
const res = await ctx.api.post('/api/organize/rules/id/submit', {
  "source_path": "<source_path>"
})
```

**响应 200**（按契约结构生成的示例值）

```json
{
  "message": "<message>",
  "success": true
}
```

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `message` | string | 给用户看的结果说明 |
| `success` | boolean | 是否成功；成功响应中恒为 true，失败时返回 4xx/5xx 与 error |

### POST `/api/organize/rules/{id}/trigger`

<a id="post-api-organize-rules-id-trigger"></a>

触发整理规则。 立即执行一条整理规则。

**参数**

| 名称 | 位置 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- | --- |
| `id` | path | string | 是 |  |

**请求体（JSON）**

| 字段 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- |
| `source_paths` | string[] |  | 要整理的文件列表 |

**调用**

```js
const res = await ctx.api.post('/api/organize/rules/id/trigger', {
  "source_paths": [
    ""
  ]
})
```

**响应 200**（按契约结构生成的示例值）

```json
{
  "errors": [
    ""
  ],
  "submitted": 0
}
```

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `errors` | string[] | 逐项失败原因 |
| `submitted` | integer |  |

### GET `/api/organize/template-variables`

<a id="get-api-organize-template-variables"></a>

读取模板变量。 读取整理路径模板可用变量。

**调用**

```js
const res = await ctx.api.get('/api/organize/template-variables')
```

**响应 200**（按契约结构生成的示例值）

```json
{
  "default_movie_template": null,
  "default_tv_template": null,
  "variables": [
    {
      "alias_of": "<alias_of>",
      "description": "<description>",
      "empty_when": "<empty_when>",
      "example": "<example>",
      "group": "<group>",
      "key": "<key>",
      "label": "<label>",
      "movie": true,
      "multi_version_only": true,
      "tv": true
    }
  ]
}
```

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `default_movie_template` | any |  |
| `default_tv_template` | any |  |
| `variables` | object[] |  |
| `variables[].alias_of` | string |  |
| `variables[].description` | string |  |
| `variables[].empty_when` | string |  |
| `variables[].example` | string |  |
| `variables[].group` | string |  |
| `variables[].key` | string |  |
| `variables[].label` | string |  |
| `variables[].movie` | boolean |  |
| `variables[].multi_version_only` | boolean |  |
| `variables[].tv` | boolean |  |

### GET `/api/organize/tmdb-cache/stats`

<a id="get-api-organize-tmdb-cache-stats"></a>

读取 TMDB 缓存统计。 读取整理模块的 TMDB 缓存统计。

**调用**

```js
const res = await ctx.api.get('/api/organize/tmdb-cache/stats')
```

**响应 200**（按契约结构生成的示例值）

```json
{
  "expired_count": 0,
  "today_count": 0,
  "total_count": 0,
  "total_size": 0,
  "valid_count": 0
}
```

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `expired_count` | integer | TMDB和分享缓存使用 |
| `today_count` | integer | 分享和磁力缓存使用 |
| `total_count` | integer |  |
| `total_size` | integer | TMDB缓存使用（字节） |
| `valid_count` | integer | TMDB和分享缓存使用 |

### GET `/api/organize/tmdb/search`

<a id="get-api-organize-tmdb-search"></a>

整理模块搜索 TMDB。 使用宿主 TMDB 凭据搜索媒体。

**参数**

| 名称 | 位置 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- | --- |
| `media_type` | query | string |  | 媒体类型：movie 电影、tv 剧集 |
| `page` | query | integer |  | 页码，从 1 开始 |
| `q` | query | string |  | 搜索关键词 |

**调用**

```js
const res = await ctx.api.get('/api/organize/tmdb/search')
```

**响应 200**（按契约结构生成的示例值）

```json
{
  "page": 1,
  "results": [
    {
      "backdrop_path": "<backdrop_path>",
      "first_air_date": "<first_air_date>",
      "genre_ids": [
        0
      ],
      "id": 0,
      "media_type": "tv",
      "name": "<name>",
      "original_language": "<original_language>",
      "original_name": "<original_name>",
      "original_title": "<original_title>",
      "overview": "<overview>",
      "popularity": 0,
      "poster_path": "/1XS1oqL89opfnbLl8WnZY1O1uJx.jpg",
      "release_date": "<release_date>",
      "title": "<title>",
      "vote_average": 0,
      "vote_count": 0
    }
  ],
  "total_pages": 0,
  "total_results": 0
}
```

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `page` | integer | 页码，从 1 开始 |
| `results` | object[] |  |
| `results[].backdrop_path` | string | TMDB 背景图相对路径，拼接 https://image.tmdb.org/t/p/w1280 使用 |
| `results[].first_air_date` | string |  |
| `results[].genre_ids` | integer[] |  |
| `results[].id` | integer |  |
| `results[].media_type` | string | 媒体类型：movie 电影、tv 剧集 |
| `results[].name` | string | 名称 |
| `results[].original_language` | string |  |
| `results[].original_name` | string |  |
| `results[].original_title` | string | 原始语言标题 |
| `results[].overview` | string | 简介 |
| `results[].popularity` | number |  |
| `results[].poster_path` | string | TMDB 海报相对路径，拼接 https://image.tmdb.org/t/p/w500 使用 |
| `results[].release_date` | string |  |
| `results[].title` | string | 标题 |
| `results[].vote_average` | number |  |
| `results[].vote_count` | integer |  |
| `total_pages` | integer | 总页数 |
| `total_results` | integer | 总结果数 |

### GET `/api/organize/wash-version/default`

<a id="get-api-organize-wash-version-default"></a>

读取洗版默认配置。 读取默认洗版配置。

**调用**

```js
const res = await ctx.api.get('/api/organize/wash-version/default')
```

**响应 200**（按契约结构生成的示例值）

```json
{
  "dimensions": [
    {
      "enabled": true,
      "name": "<name>",
      "priority": [
        ""
      ],
      "weight": 0
    }
  ],
  "excludes": {
    "codecs": [
      ""
    ],
    "hdr_types": [
      ""
    ],
    "resolutions": [
      ""
    ]
  }
}
```

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `dimensions` | object[] |  |
| `dimensions[].enabled` | boolean | 是否启用 |
| `dimensions[].name` | string | 维度名: resolution, source, video_codec, etc. |
| `dimensions[].priority` | string[] | 优先级列表（靠前得分越高） |
| `dimensions[].weight` | number | 权重 |
| `excludes` | object | 保留兼容，但不再在洗版中使用（前置过滤已替代） |
| `excludes.codecs` | string[] | 排除的编码 |
| `excludes.hdr_types` | string[] | 排除的 HDR 类型 |
| `excludes.resolutions` | string[] | 排除的分辨率 |

## pt

### POST `/api/pt/download`

<a id="post-api-pt-download"></a>

将 PT 种子提交宿主下载器。 使用宿主配置的站点与下载器完成种子获取和提交。site_id、downloader 指定目标；检查 data.success 和 data.state_uncertain。超时或不确定结果不能证明未提交，应先核对下载器。

**请求体（JSON）**

| 字段 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- |
| `allow_unknown_episode_files` | boolean |  |  |
| `download_url` | string |  |  |
| `downloader` | string |  |  |
| `info_hash` | string |  | 115 离线任务 info hash（来自离线任务列表） |
| `media_type` | string |  | 媒体类型：movie 电影、tv 剧集 |
| `needed_episodes` | integer[] |  | 仍需获取的集数集合，格式如 "4-10" |
| `needed_episodes_by_season` | object |  |  |
| `preselected_episodes` | integer[] |  |  |
| `preselected_files` | string[] |  |  |
| `priority_level` | integer |  |  |
| `rapid_upload` | boolean |  |  |
| `save_path` | string |  |  |
| `season` | integer |  | 季号，0 为特别篇 |
| `season_specified` | boolean |  |  |
| `site_id` | integer |  |  |
| `site_name` | string |  |  |
| `tag` | string |  |  |
| `title` | string |  | 标题 |

**调用**

```js
const res = await ctx.api.post('/api/pt/download', {
  "allow_unknown_episode_files": true,
  "download_url": "<download_url>",
  "downloader": "<downloader>",
  "info_hash": "c9e15763f722f23e98a29decdfae341b98d53056",
  "media_type": "tv",
  "needed_episodes": "4-10",
  "needed_episodes_by_season": {},
  "preselected_episodes": [
    0
  ],
  "preselected_files": [
    ""
  ],
  "priority_level": 0,
  "rapid_upload": true,
  "save_path": "<save_path>",
  "season": 1,
  "season_specified": true,
  "site_id": 0,
  "site_name": "<site_name>",
  "tag": "<tag>",
  "title": "<title>"
})
```

**响应 200**（按契约结构生成的示例值）

```json
{
  "code": "<code>",
  "data": {
    "already_existed": true,
    "download_id": "<download_id>",
    "downloader": "<downloader>",
    "error": "<error>",
    "rapid_upload_error": "<rapid_upload_error>",
    "rapid_upload_queued": true,
    "selected_episodes": [
      0
    ],
    "selected_episodes_by_season": {},
    "selected_files": "<selected_files>",
    "state_uncertain": true,
    "success": true
  }
}
```

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `code` | string |  |
| `data` | object |  |
| `data.already_existed` | boolean |  |
| `data.download_id` | string |  |
| `data.downloader` | string |  |
| `data.error` | string | 失败原因（原始业务错误） |
| `data.rapid_upload_error` | string |  |
| `data.rapid_upload_queued` | boolean |  |
| `data.selected_episodes` | integer[] |  |
| `data.selected_episodes_by_season` | object |  |
| `data.selected_files` | string |  |
| `data.state_uncertain` | boolean |  |
| `data.success` | boolean | 是否成功；成功响应中恒为 true，失败时返回 4xx/5xx 与 error |

### GET `/api/pt/downloaders`

<a id="get-api-pt-downloaders"></a>

读取下载器列表（密码与 API Key 脱敏）。

**调用**

```js
const res = await ctx.api.get('/api/pt/downloaders')
```

**响应 200**（按契约结构生成的示例值）

```json
{
  "code": "<code>",
  "data": [
    {
      "api_key": "<api_key>",
      "auth_mode": "<auth_mode>",
      "created_at": "2026-10-29T21:30:00+08:00",
      "host": "<host>",
      "id": 0,
      "is_default": true,
      "name": "<name>",
      "password": "<password>",
      "save_path": "<save_path>",
      "type": "<type>",
      "updated_at": "2026-10-29T21:30:00+08:00",
      "username": "<username>"
    }
  ]
}
```

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `code` | string |  |
| `data` | object[] |  |
| `data[].api_key` | string | 宿主已脱敏的占位值，不含原始凭据 |
| `data[].auth_mode` | string |  |
| `data[].created_at` | string(date-time) | 创建时间（RFC 3339） |
| `data[].host` | string |  |
| `data[].id` | integer |  |
| `data[].is_default` | boolean | 是否为默认项 |
| `data[].name` | string | 名称 |
| `data[].password` | string | 宿主已脱敏的占位值，不含原始凭据 |
| `data[].save_path` | string |  |
| `data[].type` | string |  |
| `data[].updated_at` | string(date-time) | 更新时间（RFC 3339） |
| `data[].username` | string |  |

### POST `/api/pt/search`

<a id="post-api-pt-search"></a>

搜索指定 PT 站点。 普通搜索保持原行为。API 3.5 incremental=true 时必须显式指定一个馒头站点和 keyword：将发布时间窗口传给站点，每次实时取 100 条的一页，忽略 max_pages/page_size/extra_keywords/priority_rule/stop_when_found，返回原始候选供调用方精确匹配。window.complete=false 用 next_page 和同一 published_before 续读；完整空结果也可推进基线；错误/不完整响应不能推进。其他站点暂不支持该模式。

**请求体（JSON）**

| 字段 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- |
| `category` | string |  |  |
| `episodes` | integer[] |  |  |
| `extra_keywords` | string[] |  |  |
| `imdb_id` | string |  |  |
| `incremental` | boolean |  | API 3.5：显式单个馒头站点和 keyword，按发布时间窗口实时取一页，不使用搜索页缓存。 |
| `keyword` | string |  |  |
| `max_pages` | integer |  |  |
| `media_type` | string |  | 媒体类型：movie 电影、tv 剧集 |
| `mteam_mode` | "normal" / "adult" |  | 仅馒头：normal 普通区 / adult 成人区；省略保留默认；adult 不附加影视分类，模式参与缓存键。 |
| `page` | integer |  | 页码，从 1 开始 |
| `page_size` | integer |  | 每页条数 |
| `priority_rule` | string |  |  |
| `published_after` | string(date-time) |  | incremental=true 时包含下界；整秒 RFC3339，省略为 1970-01-01。 |
| `published_before` | string(date-time) |  | incremental=true 时排他上界；整秒 RFC3339，首请求可省略，续页必须沿用返回的 window.until。 |
| `search_name_limit` | integer |  |  |
| `season` | integer |  | 季号，0 为特别篇 |
| `season_specified` | boolean |  |  |
| `site_ids` | integer[] |  |  |
| `sort_order` | string |  |  |
| `stop_when_found` | boolean |  |  |
| `tmdb_id` | integer |  | TMDB 媒体 ID；电影与剧集分别编号，需配合 media_type 使用 |
| `year` | string |  | 年份 |

**调用**

```js
const res = await ctx.api.post('/api/pt/search', {
  "keyword": "SSIS-001",
  "site_ids": [
    7
  ],
  "mteam_mode": "adult",
  "incremental": true,
  "published_after": "2026-01-01T00:00:00Z",
  "published_before": "2026-01-02T00:00:00Z",
  "page": 1
})
```

**响应 200**

```json
{
  "code": "ok",
  "data": {
    "torrents": [],
    "total_found": 0,
    "total_passed": 0,
    "window": {
      "since": "2026-01-01T00:00:00Z",
      "until": "2026-01-02T00:00:00Z",
      "complete": true
    }
  }
}
```

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `code` | string |  |
| `data` | object |  |
| `data.errors` | string[] | 逐项失败原因 |
| `data.torrents` | object[] |  |
| `data.torrents[].anidb_id` | string |  |
| `data.torrents[].author` | string |  |
| `data.torrents[].bangumi_id` | string |  |
| `data.torrents[].category` | string |  |
| `data.torrents[].comments` | integer |  |
| `data.torrents[].completed` | integer |  |
| `data.torrents[].detail_url` | string |  |
| `data.torrents[].discount` | string |  |
| `data.torrents[].douban_id` | string |  |
| `data.torrents[].download_factor` | any |  |
| `data.torrents[].download_url` | string |  |
| `data.torrents[].episodes` | any[] |  |
| `data.torrents[].files` | any[] |  |
| `data.torrents[].free_deadline` | string |  |
| `data.torrents[].free_type` | string |  |
| `data.torrents[].hit_and_run` | boolean |  |
| `data.torrents[].imdb_id` | string |  |
| `data.torrents[].info_hash` | string | 115 离线任务 info hash（来自离线任务列表） |
| `data.torrents[].labels` | any[] |  |
| `data.torrents[].leechers` | integer |  |
| `data.torrents[].mal_id` | string |  |
| `data.torrents[].match_metadata` | any |  |
| `data.torrents[].priority_level` | integer |  |
| `data.torrents[].publish_time` | string |  |
| `data.torrents[].recognition_trace` | string |  |
| `data.torrents[].seeders` | integer |  |
| `data.torrents[].site_id` | integer |  |
| `data.torrents[].site_name` | string |  |
| `data.torrents[].site_priority` | integer |  |
| `data.torrents[].site_upload` | number |  |
| `data.torrents[].size` | integer | 字节数 |
| `data.torrents[].sub_title` | string |  |
| `data.torrents[].tag` | string |  |
| `data.torrents[].title` | string | 标题 |
| `data.torrents[].tmdb_id` | string | TMDB 媒体 ID；电影与剧集分别编号，需配合 media_type 使用 |
| `data.torrents[].torrent_id` | string |  |
| `data.torrents[].torrent_progress` | number |  |
| `data.torrents[].torrent_status` | string |  |
| `data.torrents[].tvdb_id` | string |  |
| `data.torrents[].tvmaze_id` | string |  |
| `data.torrents[].upload_factor` | any |  |
| `data.total_found` | integer |  |
| `data.total_passed` | integer |  |
| `data.window` | PTSearchWindow |  |
| `data.window.complete` | boolean | 只有 true 才表示整个窗口读取完成；空末页同样推进基线。 |
| `data.window.next_page` | integer | complete=false 时下一页；不得改动当前窗口。 |
| `data.window.page_signature` | string | 当前页资源 ID 指纹，用于拒绝重复页，空页省略。 |
| `data.window.since` | string(date-time) |  |
| `data.window.until` | string(date-time) |  |

### GET `/api/pt/sites`

<a id="get-api-pt-sites"></a>

读取 PT 站点列表（凭据脱敏）。

**调用**

```js
const res = await ctx.api.get('/api/pt/sites')
```

**响应 200**（按契约结构生成的示例值）

```json
{
  "code": "<code>",
  "data": [
    {
      "api_key": "<api_key>",
      "cookie": "<cookie>",
      "created_at": "2026-10-29T21:30:00+08:00",
      "domain": "<domain>",
      "downloader": "<downloader>",
      "enabled": true,
      "id": 0,
      "last_error": "<last_error>",
      "last_status": "<last_status>",
      "last_test_at": "2026-10-29T21:30:00+08:00",
      "limit_count": 0,
      "limit_interval": 0,
      "limit_seconds": 0,
      "name": "<name>",
      "parser_type": "<parser_type>",
      "priority": 0,
      "proxy_enabled": true,
      "rss_enabled": true,
      "search_enabled": true,
      "timeout_seconds": 0,
      "token": "<token>",
      "updated_at": "2026-10-29T21:30:00+08:00",
      "url": "<url>",
      "user_agent": "<user_agent>"
    }
  ]
}
```

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `code` | string |  |
| `data` | object[] |  |
| `data[].api_key` | string | 宿主已脱敏的占位值，不含原始凭据 |
| `data[].cookie` | string | 宿主已脱敏的占位值，不含原始凭据 |
| `data[].created_at` | string(date-time) | 创建时间（RFC 3339） |
| `data[].domain` | string |  |
| `data[].downloader` | string |  |
| `data[].enabled` | boolean | 是否启用 |
| `data[].id` | integer |  |
| `data[].last_error` | string |  |
| `data[].last_status` | string |  |
| `data[].last_test_at` | string(date-time) |  |
| `data[].limit_count` | integer |  |
| `data[].limit_interval` | integer |  |
| `data[].limit_seconds` | integer |  |
| `data[].name` | string | 名称 |
| `data[].parser_type` | string |  |
| `data[].priority` | integer |  |
| `data[].proxy_enabled` | boolean |  |
| `data[].rss_enabled` | boolean |  |
| `data[].search_enabled` | boolean |  |
| `data[].timeout_seconds` | integer |  |
| `data[].token` | string | 宿主已脱敏的占位值，不含原始凭据 |
| `data[].updated_at` | string(date-time) | 更新时间（RFC 3339） |
| `data[].url` | string |  |
| `data[].user_agent` | string |  |

## 同步规则与 STRM

### GET `/api/rules`

<a id="get-api-rules"></a>

读取同步规则。 读取云盘同步规则列表。

**调用**

```js
const res = await ctx.api.get('/api/rules')
```

**响应 200**（按契约结构生成的示例值）

```json
[
  null
]
```

响应为宿主或上游服务原样透传的 JSON，字段可能随上游变化；以 HTTP 2xx 判断成功。

### POST `/api/rules`

<a id="post-api-rules"></a>

创建同步规则。 创建云盘同步规则。

**调用**

```js
const res = await ctx.api.post('/api/rules', {})
```

**响应 200**（按契约结构生成的示例值）

```json
{
  "clean_dir_depth": 0,
  "clean_empty_dir": true,
  "clean_meta": true,
  "clean_strm": true,
  "cloud_name": "<cloud_name>",
  "created_at": "2026-10-29T21:30:00+08:00",
  "cron_expr": "<cron_expr>",
  "enabled": true,
  "exclude_keys": "<exclude_keys>",
  "file_count": 0,
  "file_extensions": "<file_extensions>",
  "full_sync_cron": "<full_sync_cron>",
  "generate_strm": true,
  "id": 0,
  "last_sync_time": "2026-10-29T21:30:00+08:00",
  "link_mode": "<link_mode>",
  "meta_extensions": "<meta_extensions>",
  "meta_sync": "<meta_sync>",
  "name": "<name>",
  "output_path": "<output_path>",
  "recursive": true,
  "server_url": "<server_url>",
  "smart_clean": true,
  "source_cid": "2876543210987654321",
  "source_path": "<source_path>",
  "sync_mode": "<sync_mode>",
  "tree_built": true,
  "tree_file_count": 0,
  "updated_at": "2026-10-29T21:30:00+08:00"
}
```

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `clean_dir_depth` | integer | 清理空目录的最大向上递归深度 |
| `clean_empty_dir` | boolean | 是否清理空父目录 |
| `clean_meta` | boolean | 源文件删除后是否删除同名元数据文件 |
| `clean_strm` | boolean | 源文件删除后是否删除STRM文件 |
| `cloud_name` | string | CD2中的云盘名称（来自 CD2 根目录） |
| `created_at` | string(date-time) | 创建时间（RFC 3339） |
| `cron_expr` | string | Cron表达式（定时同步时使用） |
| `enabled` | boolean | 是否启用 |
| `exclude_keys` | string | 排除关键字（逗号分隔） |
| `file_count` | integer | 已同步文件数 |
| `file_extensions` | string | 自定义文件后缀（逗号分隔，如 .mkv,.mp4），为空使用全局默认 |
| `full_sync_cron` | string | 定时全量同步Cron表达式（重建目录树+同步） |
| `generate_strm` | boolean | 是否执行 STRM 文件生成步骤 |
| `id` | integer |  |
| `last_sync_time` | string(date-time) | 最后同步时间 |
| `link_mode` | string | 生成模式: "path"（默认，CD2路径）或 "link"（链接格式） |
| `meta_extensions` | string | 元数据文件后缀（逗号分隔，如 .nfo,.jpg），为空使用默认 |
| `meta_sync` | string |  |
| `name` | string | 名称 |
| `output_path` | string | STRM输出路径 |
| `recursive` | boolean |  |
| `server_url` | string | 链接模式下的服务地址，如 http://192.168.1.100:8080 |
| `smart_clean` | boolean | 智能清理：CD2删除时同步清理STRM+元数据+空目录 |
| `source_cid` | string | 来源目录的 115 节点 ID |
| `source_path` | string | CD2源路径（CD2内部路径） |
| `sync_mode` | string | 同步模式: manual, cron, realtime（逗号分隔可多选） |
| `tree_built` | boolean | 目录树是否已构建 |
| `tree_file_count` | integer | 目录树中的文件数量 |
| `updated_at` | string(date-time) | 更新时间（RFC 3339） |

### POST `/api/rules/sync-all`

<a id="post-api-rules-sync-all"></a>

同步全部规则。 执行全部同步规则。

**调用**

```js
const res = await ctx.api.post('/api/rules/sync-all', {})
```

**响应 200**（按契约结构生成的示例值）

```json
{
  "message": "<message>",
  "task_id": "20261029213000-a1b2c3"
}
```

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `message` | string | 给用户看的结果说明 |
| `task_id` | string | 统一任务队列的任务 ID，可用 GET /api/tasks/{id} 查询进度 |

### PUT `/api/rules/{id}`

<a id="put-api-rules-id"></a>

更新同步规则。 更新一条同步规则。

**参数**

| 名称 | 位置 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- | --- |
| `id` | path | string | 是 |  |

**调用**

```js
const res = await ctx.api.put('/api/rules/id', {})
```

**响应 200**（按契约结构生成的示例值）

```json
{
  "clean_dir_depth": 0,
  "clean_empty_dir": true,
  "clean_meta": true,
  "clean_strm": true,
  "cloud_name": "<cloud_name>",
  "created_at": "2026-10-29T21:30:00+08:00",
  "cron_expr": "<cron_expr>",
  "enabled": true,
  "exclude_keys": "<exclude_keys>",
  "file_count": 0,
  "file_extensions": "<file_extensions>",
  "full_sync_cron": "<full_sync_cron>",
  "generate_strm": true,
  "id": 0,
  "last_sync_time": "2026-10-29T21:30:00+08:00",
  "link_mode": "<link_mode>",
  "meta_extensions": "<meta_extensions>",
  "meta_sync": "<meta_sync>",
  "name": "<name>",
  "output_path": "<output_path>",
  "recursive": true,
  "server_url": "<server_url>",
  "smart_clean": true,
  "source_cid": "2876543210987654321",
  "source_path": "<source_path>",
  "sync_mode": "<sync_mode>",
  "tree_built": true,
  "tree_file_count": 0,
  "updated_at": "2026-10-29T21:30:00+08:00"
}
```

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `clean_dir_depth` | integer | 清理空目录的最大向上递归深度 |
| `clean_empty_dir` | boolean | 是否清理空父目录 |
| `clean_meta` | boolean | 源文件删除后是否删除同名元数据文件 |
| `clean_strm` | boolean | 源文件删除后是否删除STRM文件 |
| `cloud_name` | string | CD2中的云盘名称（来自 CD2 根目录） |
| `created_at` | string(date-time) | 创建时间（RFC 3339） |
| `cron_expr` | string | Cron表达式（定时同步时使用） |
| `enabled` | boolean | 是否启用 |
| `exclude_keys` | string | 排除关键字（逗号分隔） |
| `file_count` | integer | 已同步文件数 |
| `file_extensions` | string | 自定义文件后缀（逗号分隔，如 .mkv,.mp4），为空使用全局默认 |
| `full_sync_cron` | string | 定时全量同步Cron表达式（重建目录树+同步） |
| `generate_strm` | boolean | 是否执行 STRM 文件生成步骤 |
| `id` | integer |  |
| `last_sync_time` | string(date-time) | 最后同步时间 |
| `link_mode` | string | 生成模式: "path"（默认，CD2路径）或 "link"（链接格式） |
| `meta_extensions` | string | 元数据文件后缀（逗号分隔，如 .nfo,.jpg），为空使用默认 |
| `meta_sync` | string |  |
| `name` | string | 名称 |
| `output_path` | string | STRM输出路径 |
| `recursive` | boolean |  |
| `server_url` | string | 链接模式下的服务地址，如 http://192.168.1.100:8080 |
| `smart_clean` | boolean | 智能清理：CD2删除时同步清理STRM+元数据+空目录 |
| `source_cid` | string | 来源目录的 115 节点 ID |
| `source_path` | string | CD2源路径（CD2内部路径） |
| `sync_mode` | string | 同步模式: manual, cron, realtime（逗号分隔可多选） |
| `tree_built` | boolean | 目录树是否已构建 |
| `tree_file_count` | integer | 目录树中的文件数量 |
| `updated_at` | string(date-time) | 更新时间（RFC 3339） |

### DELETE `/api/rules/{id}`

<a id="delete-api-rules-id"></a>

删除同步规则。 删除一条同步规则。

**参数**

| 名称 | 位置 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- | --- |
| `id` | path | string | 是 |  |

**调用**

```js
const res = await ctx.api.delete('/api/rules/id')
```

**响应 200**（按契约结构生成的示例值）

```json
{
  "success": true
}
```

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `success` | boolean | 是否成功；成功响应中恒为 true，失败时返回 4xx/5xx 与 error |

### POST `/api/rules/{id}/clean-orphans`

<a id="post-api-rules-id-clean-orphans"></a>

清理孤立文件。 清理一条规则产生的孤立文件。

**参数**

| 名称 | 位置 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- | --- |
| `id` | path | string | 是 |  |

**调用**

```js
const res = await ctx.api.post('/api/rules/id/clean-orphans', {})
```

**响应 200**（按契约结构生成的示例值）

```json
{
  "message": "<message>",
  "task_id": "20261029213000-a1b2c3"
}
```

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `message` | string | 给用户看的结果说明 |
| `task_id` | string | 统一任务队列的任务 ID，可用 GET /api/tasks/{id} 查询进度 |

### POST `/api/rules/{id}/full-sync`

<a id="post-api-rules-id-full-sync"></a>

全量同步规则。 全量执行一条同步规则。

**参数**

| 名称 | 位置 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- | --- |
| `id` | path | string | 是 |  |

**调用**

```js
const res = await ctx.api.post('/api/rules/id/full-sync', {})
```

**响应 200**（按契约结构生成的示例值）

```json
{
  "message": "<message>",
  "task_id": "20261029213000-a1b2c3"
}
```

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `message` | string | 给用户看的结果说明 |
| `task_id` | string | 统一任务队列的任务 ID，可用 GET /api/tasks/{id} 查询进度 |

### POST `/api/rules/{id}/generate-strm`

<a id="post-api-rules-id-generate-strm"></a>

生成 STRM。 为一条同步规则生成 STRM 文件。

**参数**

| 名称 | 位置 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- | --- |
| `id` | path | string | 是 |  |

**调用**

```js
const res = await ctx.api.post('/api/rules/id/generate-strm', {})
```

**响应 200**（按契约结构生成的示例值）

```json
{
  "message": "<message>",
  "task_id": "20261029213000-a1b2c3"
}
```

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `message` | string | 给用户看的结果说明 |
| `task_id` | string | 统一任务队列的任务 ID，可用 GET /api/tasks/{id} 查询进度 |

### POST `/api/rules/{id}/sync`

<a id="post-api-rules-id-sync"></a>

同步规则。 立即执行一个同步（STRM）规则，作为后台任务运行。

**参数**

| 名称 | 位置 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- | --- |
| `id` | path | string | 是 |  |

**调用**

```js
const res = await ctx.api.post('/api/rules/id/sync', {})
```

**响应 200**

```json
{
  "message": "同步任务已提交",
  "task_id": "20261029213000-a1b2c3"
}
```

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `message` | string | 给用户看的结果说明 |
| `task_id` | string | 统一任务队列的任务 ID，可用 GET /api/tasks/{id} 查询进度 |

### POST `/api/rules/{id}/sync-metadata`

<a id="post-api-rules-id-sync-metadata"></a>

同步元数据。 同步一条规则的元数据。

**参数**

| 名称 | 位置 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- | --- |
| `id` | path | string | 是 |  |

**调用**

```js
const res = await ctx.api.post('/api/rules/id/sync-metadata', {})
```

**响应 200**（按契约结构生成的示例值）

```json
{
  "message": "<message>",
  "task_id": "20261029213000-a1b2c3"
}
```

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `message` | string | 给用户看的结果说明 |
| `task_id` | string | 统一任务队列的任务 ID，可用 GET /api/tasks/{id} 查询进度 |

### POST `/api/rules/{id}/toggle`

<a id="post-api-rules-id-toggle"></a>

启停同步规则。 启用或停用一条同步规则。

**参数**

| 名称 | 位置 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- | --- |
| `id` | path | string | 是 |  |

**调用**

```js
const res = await ctx.api.post('/api/rules/id/toggle', {})
```

**响应 200**（按契约结构生成的示例值）

```json
{
  "enabled": true,
  "message": null
}
```

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `enabled` | boolean | 是否启用 |
| `message` | any | 给用户看的结果说明 |

### DELETE `/api/rules/{id}/tree`

<a id="delete-api-rules-id-tree"></a>

清空规则目录树。 清空一条同步规则已生成的目录树。

**参数**

| 名称 | 位置 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- | --- |
| `id` | path | string | 是 |  |

**调用**

```js
const res = await ctx.api.delete('/api/rules/id/tree')
```

**响应 200**（按契约结构生成的示例值）

```json
{
  "message": "<message>"
}
```

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `message` | string | 给用户看的结果说明 |

### GET `/api/rules/{id}/tree/stats`

<a id="get-api-rules-id-tree-stats"></a>

读取规则目录统计。 读取一条同步规则的目录树统计。

**参数**

| 名称 | 位置 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- | --- |
| `id` | path | string | 是 |  |

**调用**

```js
const res = await ctx.api.get('/api/rules/id/tree/stats')
```

**响应 200**（按契约结构生成的示例值）

```json
{
  "dirs": 0,
  "files": 0,
  "rule_id": 1,
  "total_size": 0
}
```

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `dirs` | integer |  |
| `files` | integer |  |
| `rule_id` | any | 规则 ID（整理规则或同步规则，见所在接口） |
| `total_size` | integer |  |

## 任务队列

### GET `/api/scheduler/jobs`

<a id="get-api-scheduler-jobs"></a>

读取宿主任务。 读取宿主定时任务列表。

**调用**

```js
const res = await ctx.api.get('/api/scheduler/jobs')
```

**响应 200**（按契约结构生成的示例值）

```json
{
  "data": [
    null
  ],
  "success": true
}
```

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `data` | any[] |  |
| `success` | boolean | 是否成功；成功响应中恒为 true，失败时返回 4xx/5xx 与 error |

### POST `/api/scheduler/jobs/trigger`

<a id="post-api-scheduler-jobs-trigger"></a>

触发宿主任务。 立即触发一个宿主定时任务；trigger_key 取自 GET /api/scheduler/jobs。

**请求体（JSON）**

| 字段 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- |
| `trigger_key` | string |  | 宿主定时任务键，来自 GET /api/scheduler/jobs |

**调用**

```js
const res = await ctx.api.post('/api/scheduler/jobs/trigger', {
  "trigger_key": "<GET /api/scheduler/jobs 返回的任务键>"
})
```

**响应 200**（按契约结构生成的示例值）

```json
{
  "message": "<message>",
  "success": true
}
```

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `message` | string | 给用户看的结果说明 |
| `success` | boolean | 是否成功；成功响应中恒为 true，失败时返回 4xx/5xx 与 error |

### GET `/api/tasks`

<a id="get-api-tasks"></a>

列出后台任务。 列出统一任务队列中的近期任务（含插件任务与文件任务），数组元素结构同 GET /api/tasks/{id}。

**调用**

```js
const res = await ctx.api.get('/api/tasks')
```

**响应 200**（按契约结构生成的示例值）

```json
{}
```

响应为宿主或上游服务原样透传的 JSON，字段可能随上游变化；以 HTTP 2xx 判断成功。

### GET `/api/tasks/{id}`

<a id="get-api-tasks-id"></a>

读取任务详情。 查询统一任务队列中的任务。status 常见值 pending、running、completed、failed、cancelled；进度看 total_files/synced_files/failed_files 与 message。

**参数**

| 名称 | 位置 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- | --- |
| `id` | path | string | 是 |  |

**调用**

```js
const res = await ctx.api.get('/api/tasks/id')
```

**响应 200**（按契约结构生成的示例值）

```json
{
  "created_at": "2026-10-29T21:30:00+08:00",
  "deleted_files": 0,
  "end_time": "2026-10-29T21:30:00+08:00",
  "error": "<error>",
  "failed_files": 0,
  "id": "<id>",
  "logs": [
    ""
  ],
  "merged_into_task_id": "<merged_into_task_id>",
  "message": "<message>",
  "name": "<name>",
  "progress": 0,
  "result": null,
  "result_available": true,
  "result_version": 0,
  "rule_id": 1,
  "rule_name": "<rule_name>",
  "start_time": "2026-10-29T21:30:00+08:00",
  "status": "<status>",
  "sync_type": "<sync_type>",
  "synced_files": 0,
  "total_files": 0,
  "type": "<type>"
}
```

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `created_at` | string(date-time) | 创建时间（RFC 3339） |
| `deleted_files` | integer | 删除文件数 |
| `end_time` | string(date-time) | 结束时间 |
| `error` | string | 错误信息 |
| `failed_files` | integer | 失败文件数 |
| `id` | string | 任务 ID |
| `logs` | string[] | 实时日志 |
| `merged_into_task_id` | string | 去重后实际执行中的任务 ID |
| `message` | string | 当前状态消息 |
| `name` | string | 名称 |
| `progress` | number | 进度百分比 |
| `result` | any | 通用后台任务最终结果（主要供 AI 长任务轮询） |
| `result_available` | boolean | 是否有可读取的任务结果 |
| `result_version` | integer |  |
| `rule_id` | integer | 关联规则ID |
| `rule_name` | string | 规则名称 |
| `start_time` | string(date-time) | 开始时间 |
| `status` | string | pending 等待中、running 运行中、completed 已完成、failed 失败、cancelled 已取消 |
| `sync_type` | string | 同步类型 |
| `synced_files` | integer | 已同步文件数 |
| `total_files` | integer | 总文件数 |
| `type` | string | 任务类型（如 file_operation、plugin 等） |

### POST `/api/tasks/{id}/cancel`

<a id="post-api-tasks-id-cancel"></a>

取消任务。 取消运行中或排队中的任务。外部已提交的业务（例如 115 已接受的转存）不会回滚。

**参数**

| 名称 | 位置 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- | --- |
| `id` | path | string | 是 |  |

**调用**

```js
const res = await ctx.api.post('/api/tasks/id/cancel', {})
```

**响应 200**

```json
{
  "success": true
}
```

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `success` | boolean | 是否成功；成功响应中恒为 true，失败时返回 4xx/5xx 与 error |

### GET `/api/workqueue/stats`

<a id="get-api-workqueue-stats"></a>

读取工作队列统计。 读取宿主工作队列统计。

**调用**

```js
const res = await ctx.api.get('/api/workqueue/stats')
```

**响应 200**（按契约结构生成的示例值）

```json
{}
```

响应为宿主或上游服务原样透传的 JSON，字段可能随上游变化；以 HTTP 2xx 判断成功。

## 订阅

### GET `/api/subscribe/air-calendar`

<a id="get-api-subscribe-air-calendar"></a>

读取追剧日历。 读取订阅播出日历。

**参数**

| 名称 | 位置 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- | --- |
| `month` | query | integer |  |  |
| `year` | query | integer |  | 年份 |

**调用**

```js
const res = await ctx.api.get('/api/subscribe/air-calendar')
```

**响应 200**（按契约结构生成的示例值）

```json
{
  "code": "<code>",
  "data": [
    {
      "air_date": "<air_date>",
      "episode": 1,
      "episode_name": "<episode_name>",
      "episode_overview": "<episode_overview>",
      "name": "<name>",
      "poster_path": "/1XS1oqL89opfnbLl8WnZY1O1uJx.jpg",
      "season": 1,
      "tmdb_id": 1399
    }
  ],
  "month": null,
  "year": null
}
```

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `code` | string |  |
| `data` | object[] |  |
| `data[].air_date` | string |  |
| `data[].episode` | integer | 集号 |
| `data[].episode_name` | string |  |
| `data[].episode_overview` | string |  |
| `data[].name` | string | 名称 |
| `data[].poster_path` | string | TMDB 海报相对路径，拼接 https://image.tmdb.org/t/p/w500 使用 |
| `data[].season` | integer | 季号，0 为特别篇 |
| `data[].tmdb_id` | integer | TMDB 媒体 ID；电影与剧集分别编号，需配合 media_type 使用 |
| `month` | any |  |
| `year` | any | 年份 |

### POST `/api/subscribe/batch-delete`

<a id="post-api-subscribe-batch-delete"></a>

批量删除订阅。 批量删除订阅记录。

**请求体（JSON）**

| 字段 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- |
| `actor_subscription_ids` | integer[] |  |  |
| `pool_intent_ids` | integer[] |  |  |

**调用**

```js
const res = await ctx.api.post('/api/subscribe/batch-delete', {
  "actor_subscription_ids": [
    0
  ],
  "pool_intent_ids": [
    0
  ]
})
```

**响应 200**（按契约结构生成的示例值）

```json
{
  "code": "<code>",
  "deleted": {
    "actor": 0,
    "pool": 0,
    "total": 0
  },
  "errors": [
    ""
  ]
}
```

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `code` | string |  |
| `deleted` | object |  |
| `deleted.actor` | integer |  |
| `deleted.pool` | integer |  |
| `deleted.total` | integer | 符合条件的总条数 |
| `errors` | string[] | 逐项失败原因 |

### POST `/api/subscribe/delete-by-media`

<a id="post-api-subscribe-delete-by-media"></a>

按媒体删除订阅。 按媒体删除订阅记录。

**请求体（JSON）**

| 字段 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- |
| `delete_all` | boolean |  |  |
| `media_type` | string |  | 媒体类型：movie 电影、tv 剧集 |
| `seasons` | integer[] |  |  |
| `tmdb_id` | integer |  | TMDB 媒体 ID；电影与剧集分别编号，需配合 media_type 使用 |

**调用**

```js
const res = await ctx.api.post('/api/subscribe/delete-by-media', {
  "delete_all": true,
  "media_type": "tv",
  "seasons": [
    0
  ],
  "tmdb_id": 1399
})
```

**响应 200**（按契约结构生成的示例值）

```json
{
  "code": "<code>",
  "deleted": {
    "actor": 0,
    "pool": 0,
    "total": 0
  },
  "errors": [
    ""
  ]
}
```

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `code` | string |  |
| `deleted` | object |  |
| `deleted.actor` | integer |  |
| `deleted.pool` | integer |  |
| `deleted.total` | integer | 符合条件的总条数 |
| `errors` | string[] | 逐项失败原因 |

### GET `/api/subscribe/entry-settings`

<a id="get-api-subscribe-entry-settings"></a>

读取订阅入口设置。 读取订阅入口设置。

**调用**

```js
const res = await ctx.api.get('/api/subscribe/entry-settings')
```

**响应 200**（按契约结构生成的示例值）

```json
{
  "code": "<code>",
  "data": {
    "mode": null
  }
}
```

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `code` | string |  |
| `data` | object |  |
| `data.mode` | any |  |

### PUT `/api/subscribe/entry-settings`

<a id="put-api-subscribe-entry-settings"></a>

更新订阅入口设置。 更新订阅入口设置。

**请求体（JSON）**

| 字段 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- |
| `mode` | string |  |  |

**调用**

```js
const res = await ctx.api.put('/api/subscribe/entry-settings', {
  "mode": "<mode>"
})
```

**响应 200**（按契约结构生成的示例值）

```json
{
  "code": "<code>",
  "data": {
    "mode": null
  }
}
```

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `code` | string |  |
| `data` | object |  |
| `data.mode` | any |  |

### GET `/api/subscribe/history`

<a id="get-api-subscribe-history"></a>

读取订阅历史。 读取订阅执行历史。

**参数**

| 名称 | 位置 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- | --- |
| `limit` | query | integer |  | 本次最多返回的条数 |
| `offset` | query | integer |  | 跳过的条数，从 0 开始 |

**调用**

```js
const res = await ctx.api.get('/api/subscribe/history')
```

**响应 200**（按契约结构生成的示例值）

```json
{
  "code": "<code>",
  "data": {
    "records": [
      {
        "completed_at": "2026-10-29T21:30:00+08:00",
        "covered_episodes": "1-3",
        "created_at": "2026-10-29T21:30:00+08:00",
        "id": 0,
        "intent_id": 0,
        "landed_tag": "<landed_tag>",
        "landed_via": "<landed_via>",
        "last_error": "<last_error>",
        "media_type": "tv",
        "season": 1,
        "state": "<state>",
        "title": "<title>",
        "tmdb_id": 1399
      }
    ]
  }
}
```

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `code` | string |  |
| `data` | object |  |
| `data.records` | object[] |  |
| `data.records[].completed_at` | string(date-time) |  |
| `data.records[].covered_episodes` | string | 已拥有的集数集合，格式如 "1-3,5" |
| `data.records[].created_at` | string(date-time) | 创建时间（RFC 3339） |
| `data.records[].id` | integer |  |
| `data.records[].intent_id` | integer |  |
| `data.records[].landed_tag` | string |  |
| `data.records[].landed_via` | string |  |
| `data.records[].last_error` | string |  |
| `data.records[].media_type` | string | 媒体类型：movie 电影、tv 剧集 |
| `data.records[].season` | integer | 季号，0 为特别篇 |
| `data.records[].state` | string |  |
| `data.records[].title` | string | 标题 |
| `data.records[].tmdb_id` | integer | TMDB 媒体 ID；电影与剧集分别编号，需配合 media_type 使用 |

### GET `/api/subscribe/library-settings`

<a id="get-api-subscribe-library-settings"></a>

读取媒体库订阅设置。 读取媒体库订阅设置。

**调用**

```js
const res = await ctx.api.get('/api/subscribe/library-settings')
```

**响应 200**（按契约结构生成的示例值）

```json
{
  "code": "<code>",
  "data": {
    "proxy_id": 1
  }
}
```

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `code` | string |  |
| `data` | object |  |
| `data.proxy_id` | any | Emby 实例 ID，来自 GET /api/plugin-host/emby/instances；省略使用默认实例 |

### PUT `/api/subscribe/library-settings`

<a id="put-api-subscribe-library-settings"></a>

更新媒体库订阅设置。 更新媒体库订阅设置。

**请求体（JSON）**

| 字段 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- |
| `proxy_id` | integer |  | Emby 实例 ID，来自 GET /api/plugin-host/emby/instances；省略使用默认实例 |

**调用**

```js
const res = await ctx.api.put('/api/subscribe/library-settings', {
  "proxy_id": 1
})
```

**响应 200**（按契约结构生成的示例值）

```json
{
  "code": "<code>",
  "data": {
    "proxy_id": 1
  }
}
```

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `code` | string |  |
| `data` | object |  |
| `data.proxy_id` | any | Emby 实例 ID，来自 GET /api/plugin-host/emby/instances；省略使用默认实例 |

### GET `/api/subscribe/pool/intents`

<a id="get-api-subscribe-pool-intents"></a>

查询聚合订阅。 读取聚合订阅意图。

**参数**

| 名称 | 位置 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- | --- |
| `state` | query | "pending" / "searching" / "transferring" / "partial" / "caught_up" / "landed" / "failed" / "expired" |  |  |
| `media_type` | query | "movie" / "tv" |  | 媒体类型：movie 电影、tv 剧集 |
| `limit` | query | integer |  | 本次最多返回的条数 |
| `offset` | query | integer |  | 跳过的条数，从 0 开始 |

**调用**

```js
const res = await ctx.api.get('/api/subscribe/pool/intents')
```

**响应 200**（按契约结构生成的示例值）

```json
{
  "code": "ok",
  "counts": {},
  "data": [
    {
      "backdrop_path": "<backdrop_path>",
      "baseline_priority_level": 0,
      "baseline_tag": "<baseline_tag>",
      "covered_episodes": "1-3",
      "created_at": "2026-10-29T21:30:00+08:00",
      "enabled_sources": "<enabled_sources>",
      "episode_scope_mode": "follow",
      "id": 0,
      "is_upgrade": 0,
      "landed_at": "2026-10-29T21:30:00+08:00",
      "landed_share_code": "<landed_share_code>",
      "landed_tag": "<landed_tag>",
      "landed_via": "<landed_via>",
      "last_check_at": "2026-10-29T21:30:00+08:00",
      "last_error": "<last_error>",
      "media_type": "tv",
      "metadata_checked_at": "2026-10-29T21:30:00+08:00",
      "needed_episodes": "4-10",
      "poster_path": "/1XS1oqL89opfnbLl8WnZY1O1uJx.jpg",
      "priority_rule": "<priority_rule>",
      "proxy_id": 1,
      "retry_count": 0,
      "season": 1,
      "state": "pending",
      "subscribe_kind": "<subscribe_kind>",
      "title": "<title>",
      "tmdb_id": 1399,
      "total_episodes_known": 0,
      "updated_at": "2026-10-29T21:30:00+08:00",
      "year": "<year>"
    }
  ]
}
```

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `code` | "ok" |  |
| `counts` | object |  |
| `data` | PoolIntent[] |  |
| `data[].backdrop_path` | string | TMDB 背景图相对路径，拼接 https://image.tmdb.org/t/p/w1280 使用 |
| `data[].baseline_priority_level` | integer |  |
| `data[].baseline_tag` | string |  |
| `data[].covered_episodes` | string | 已拥有的集数集合，格式如 "1-3,5" |
| `data[].created_at` | string(date-time) | 创建时间（RFC 3339） |
| `data[].enabled_sources` | string | JSON 数组字符串。 |
| `data[].episode_scope_mode` | "follow" / "fixed" | follow 自动跟随新集；fixed 只获取指定集数范围 |
| `data[].id` | integer(int64) | 订阅 ID，用于 GET/DELETE /api/subscribe/pool/intents/{id} |
| `data[].is_upgrade` | 0 / 1 | 1 表示洗版订阅（已有资源，寻找更好版本） |
| `data[].landed_at` | string(date-time) |  |
| `data[].landed_share_code` | string | 宿主返回前会移除 URL 和凭据。 |
| `data[].landed_tag` | string |  |
| `data[].landed_via` | string |  |
| `data[].last_check_at` | string(date-time) | 最近一次检查时间 |
| `data[].last_error` | string | 宿主返回前会移除 URL 和凭据。 |
| `data[].media_type` | "movie" / "tv" | 媒体类型：movie 电影、tv 剧集 |
| `data[].metadata_checked_at` | string(date-time) |  |
| `data[].needed_episodes` | string | 需要的集号（如 "1-24"），空=全部 |
| `data[].poster_path` | string | TMDB 海报相对路径，拼接 https://image.tmdb.org/t/p/w500 使用 |
| `data[].priority_rule` | string |  |
| `data[].proxy_id` | integer(int64) | Emby 实例 ID，来自 GET /api/plugin-host/emby/instances；省略使用默认实例 |
| `data[].retry_count` | integer | 已重试次数 |
| `data[].season` | integer | 0=电影或全集 |
| `data[].state` | "pending" / "searching" / "transferring" / "partial" / "caught_up" / "landed" / "failed" / "expired" | 订阅状态：pending 刚创建、searching 搜索资源中、transferring 转存中、waiting 等待下载或转存完成、verifying 核对实际季集、partial 部分完成、caught_up 已覆盖当前已知集 |
| `data[].subscribe_kind` | string | "" 普通/洗版；"missing" 缺集补全 |
| `data[].title` | string | 标题 |
| `data[].tmdb_id` | integer | TMDB 媒体 ID；电影与剧集分别编号，需配合 media_type 使用 |
| `data[].total_episodes_known` | integer | 宿主当前已知的该季总集数，0 表示未知 |
| `data[].updated_at` | string(date-time) | 更新时间（RFC 3339） |
| `data[].year` | string | 年份 |

### POST `/api/subscribe/pool/intents`

<a id="post-api-subscribe-pool-intents"></a>

创建聚合订阅。 创建聚合订阅（电影或剧集某一季）。剧集可用 initial_needed_episodes 只订阅缺失的集；宿主按启用的来源自动搜索并转存。

**请求体（JSON）**

| 字段 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- |
| `backdrop_path` | string |  | TMDB 背景图相对路径，拼接 https://image.tmdb.org/t/p/w1280 使用 |
| `enabled_sources` | string[] |  | 启用的资源来源；省略使用宿主默认来源 |
| `episode_scope_mode` | "follow" / "fixed" |  | follow 自动跟随新集；fixed 只获取 initial_needed_episodes 指定的集 |
| `initial_covered_episodes` | string |  | 创建时已拥有的集数集合，格式如 "1-3" |
| `initial_needed_episodes` | string |  | 创建时需要获取的集数集合，格式如 "4-10" |
| `library_snapshot_provided` | boolean |  |  |
| `media_type` | "movie" / "tv" | 是 | 媒体类型：movie 电影、tv 剧集 |
| `poster_path` | string |  | TMDB 海报相对路径，拼接 https://image.tmdb.org/t/p/w500 使用 |
| `proxy_id` | integer(int64) |  | Emby 实例 ID，来自 GET /api/plugin-host/emby/instances；省略使用默认实例 |
| `season` | integer |  | 季号，0 为特别篇 |
| `title` | string | 是 | 标题 |
| `tmdb_id` | integer | 是 | TMDB 媒体 ID；电影与剧集分别编号，需配合 media_type 使用 |
| `total_episodes` | integer |  | 该季总集数，0 表示未知 |
| `year` | string |  | 年份 |

**调用**

```js
const res = await ctx.api.post('/api/subscribe/pool/intents', {
  "tmdb_id": 1399,
  "media_type": "tv",
  "title": "权力的游戏",
  "year": "2011",
  "season": 1,
  "total_episodes": 10,
  "episode_scope_mode": "fixed",
  "initial_covered_episodes": "1-3",
  "initial_needed_episodes": "4-10"
})
```

**响应 200**（按契约结构生成的示例值）

```json
{
  "code": "ok",
  "data": {
    "backdrop_path": "<backdrop_path>",
    "baseline_priority_level": 0,
    "baseline_tag": "<baseline_tag>",
    "covered_episodes": "1-3",
    "created_at": "2026-10-29T21:30:00+08:00",
    "enabled_sources": "<enabled_sources>",
    "episode_scope_mode": "follow",
    "id": 0,
    "is_upgrade": 0,
    "landed_at": "2026-10-29T21:30:00+08:00",
    "landed_share_code": "<landed_share_code>",
    "landed_tag": "<landed_tag>",
    "landed_via": "<landed_via>",
    "last_check_at": "2026-10-29T21:30:00+08:00",
    "last_error": "<last_error>",
    "media_type": "tv",
    "metadata_checked_at": "2026-10-29T21:30:00+08:00",
    "needed_episodes": "4-10",
    "poster_path": "/1XS1oqL89opfnbLl8WnZY1O1uJx.jpg",
    "priority_rule": "<priority_rule>",
    "proxy_id": 1,
    "retry_count": 0,
    "season": 1,
    "state": "pending",
    "subscribe_kind": "<subscribe_kind>",
    "title": "<title>",
    "tmdb_id": 1399,
    "total_episodes_known": 0,
    "updated_at": "2026-10-29T21:30:00+08:00",
    "year": "<year>"
  }
}
```

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `code` | "ok" |  |
| `data` | PoolIntent |  |
| `data.backdrop_path` | string | TMDB 背景图相对路径，拼接 https://image.tmdb.org/t/p/w1280 使用 |
| `data.baseline_priority_level` | integer |  |
| `data.baseline_tag` | string |  |
| `data.covered_episodes` | string | 已拥有的集数集合，格式如 "1-3,5" |
| `data.created_at` | string(date-time) | 创建时间（RFC 3339） |
| `data.enabled_sources` | string | JSON 数组字符串。 |
| `data.episode_scope_mode` | "follow" / "fixed" | follow 自动跟随新集；fixed 只获取指定集数范围 |
| `data.id` | integer(int64) | 订阅 ID，用于 GET/DELETE /api/subscribe/pool/intents/{id} |
| `data.is_upgrade` | 0 / 1 | 1 表示洗版订阅（已有资源，寻找更好版本） |
| `data.landed_at` | string(date-time) |  |
| `data.landed_share_code` | string | 宿主返回前会移除 URL 和凭据。 |
| `data.landed_tag` | string |  |
| `data.landed_via` | string |  |
| `data.last_check_at` | string(date-time) | 最近一次检查时间 |
| `data.last_error` | string | 宿主返回前会移除 URL 和凭据。 |
| `data.media_type` | "movie" / "tv" | 媒体类型：movie 电影、tv 剧集 |
| `data.metadata_checked_at` | string(date-time) |  |
| `data.needed_episodes` | string | 需要的集号（如 "1-24"），空=全部 |
| `data.poster_path` | string | TMDB 海报相对路径，拼接 https://image.tmdb.org/t/p/w500 使用 |
| `data.priority_rule` | string |  |
| `data.proxy_id` | integer(int64) | Emby 实例 ID，来自 GET /api/plugin-host/emby/instances；省略使用默认实例 |
| `data.retry_count` | integer | 已重试次数 |
| `data.season` | integer | 0=电影或全集 |
| `data.state` | "pending" / "searching" / "transferring" / "partial" / "caught_up" / "landed" / "failed" / "expired" | 订阅状态：pending 刚创建、searching 搜索资源中、transferring 转存中、waiting 等待下载或转存完成、verifying 核对实际季集、partial 部分完成、caught_up 已覆盖当前已知集 |
| `data.subscribe_kind` | string | "" 普通/洗版；"missing" 缺集补全 |
| `data.title` | string | 标题 |
| `data.tmdb_id` | integer | TMDB 媒体 ID；电影与剧集分别编号，需配合 media_type 使用 |
| `data.total_episodes_known` | integer | 宿主当前已知的该季总集数，0 表示未知 |
| `data.updated_at` | string(date-time) | 更新时间（RFC 3339） |
| `data.year` | string | 年份 |

### GET `/api/subscribe/pool/intents/{id}`

<a id="get-api-subscribe-pool-intents-id"></a>

读取聚合订阅。 读取一条聚合订阅意图。

**参数**

| 名称 | 位置 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- | --- |
| `id` | path | integer(int64) | 是 |  |

**调用**

```js
const res = await ctx.api.get('/api/subscribe/pool/intents/1')
```

**响应 200**（按契约结构生成的示例值）

```json
{
  "code": "ok",
  "data": {
    "backdrop_path": "<backdrop_path>",
    "baseline_priority_level": 0,
    "baseline_tag": "<baseline_tag>",
    "covered_episodes": "1-3",
    "created_at": "2026-10-29T21:30:00+08:00",
    "enabled_sources": "<enabled_sources>",
    "episode_scope_mode": "follow",
    "id": 0,
    "is_upgrade": 0,
    "landed_at": "2026-10-29T21:30:00+08:00",
    "landed_share_code": "<landed_share_code>",
    "landed_tag": "<landed_tag>",
    "landed_via": "<landed_via>",
    "last_check_at": "2026-10-29T21:30:00+08:00",
    "last_error": "<last_error>",
    "media_type": "tv",
    "metadata_checked_at": "2026-10-29T21:30:00+08:00",
    "needed_episodes": "4-10",
    "poster_path": "/1XS1oqL89opfnbLl8WnZY1O1uJx.jpg",
    "priority_rule": "<priority_rule>",
    "proxy_id": 1,
    "retry_count": 0,
    "season": 1,
    "state": "pending",
    "subscribe_kind": "<subscribe_kind>",
    "title": "<title>",
    "tmdb_id": 1399,
    "total_episodes_known": 0,
    "updated_at": "2026-10-29T21:30:00+08:00",
    "year": "<year>"
  }
}
```

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `code` | "ok" |  |
| `data` | PoolIntent |  |
| `data.backdrop_path` | string | TMDB 背景图相对路径，拼接 https://image.tmdb.org/t/p/w1280 使用 |
| `data.baseline_priority_level` | integer |  |
| `data.baseline_tag` | string |  |
| `data.covered_episodes` | string | 已拥有的集数集合，格式如 "1-3,5" |
| `data.created_at` | string(date-time) | 创建时间（RFC 3339） |
| `data.enabled_sources` | string | JSON 数组字符串。 |
| `data.episode_scope_mode` | "follow" / "fixed" | follow 自动跟随新集；fixed 只获取指定集数范围 |
| `data.id` | integer(int64) | 订阅 ID，用于 GET/DELETE /api/subscribe/pool/intents/{id} |
| `data.is_upgrade` | 0 / 1 | 1 表示洗版订阅（已有资源，寻找更好版本） |
| `data.landed_at` | string(date-time) |  |
| `data.landed_share_code` | string | 宿主返回前会移除 URL 和凭据。 |
| `data.landed_tag` | string |  |
| `data.landed_via` | string |  |
| `data.last_check_at` | string(date-time) | 最近一次检查时间 |
| `data.last_error` | string | 宿主返回前会移除 URL 和凭据。 |
| `data.media_type` | "movie" / "tv" | 媒体类型：movie 电影、tv 剧集 |
| `data.metadata_checked_at` | string(date-time) |  |
| `data.needed_episodes` | string | 需要的集号（如 "1-24"），空=全部 |
| `data.poster_path` | string | TMDB 海报相对路径，拼接 https://image.tmdb.org/t/p/w500 使用 |
| `data.priority_rule` | string |  |
| `data.proxy_id` | integer(int64) | Emby 实例 ID，来自 GET /api/plugin-host/emby/instances；省略使用默认实例 |
| `data.retry_count` | integer | 已重试次数 |
| `data.season` | integer | 0=电影或全集 |
| `data.state` | "pending" / "searching" / "transferring" / "partial" / "caught_up" / "landed" / "failed" / "expired" | 订阅状态：pending 刚创建、searching 搜索资源中、transferring 转存中、waiting 等待下载或转存完成、verifying 核对实际季集、partial 部分完成、caught_up 已覆盖当前已知集 |
| `data.subscribe_kind` | string | "" 普通/洗版；"missing" 缺集补全 |
| `data.title` | string | 标题 |
| `data.tmdb_id` | integer | TMDB 媒体 ID；电影与剧集分别编号，需配合 media_type 使用 |
| `data.total_episodes_known` | integer | 宿主当前已知的该季总集数，0 表示未知 |
| `data.updated_at` | string(date-time) | 更新时间（RFC 3339） |
| `data.year` | string | 年份 |

### DELETE `/api/subscribe/pool/intents/{id}`

<a id="delete-api-subscribe-pool-intents-id"></a>

取消聚合订阅。 取消一条聚合订阅意图。

**参数**

| 名称 | 位置 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- | --- |
| `id` | path | integer(int64) | 是 |  |

**调用**

```js
const res = await ctx.api.delete('/api/subscribe/pool/intents/1')
```

**响应 200**（按契约结构生成的示例值）

```json
{
  "code": "ok"
}
```

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `code` | "ok" |  |

### PATCH `/api/subscribe/pool/intents/{id}/episodes`

<a id="patch-api-subscribe-pool-intents-id-episodes"></a>

更新订阅集数。 更新聚合订阅需要和已覆盖的集数。

**参数**

| 名称 | 位置 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- | --- |
| `id` | path | integer(int64) | 是 |  |

**请求体（JSON）**

| 字段 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- |
| `covered_episodes` | string |  | 已拥有的集数集合，格式如 "1-3,5" |
| `needed_episodes` | string |  | 仍需获取的集数集合，格式如 "4-10" |
| `total_episodes` | integer |  | 该季总集数，0 表示未知 |

**调用**

```js
const res = await ctx.api.patch('/api/subscribe/pool/intents/1/episodes', {
  "covered_episodes": "1-3",
  "needed_episodes": "4-10",
  "total_episodes": 10
})
```

**响应 200**（按契约结构生成的示例值）

```json
{
  "code": "ok",
  "data": {
    "backdrop_path": "<backdrop_path>",
    "baseline_priority_level": 0,
    "baseline_tag": "<baseline_tag>",
    "covered_episodes": "1-3",
    "created_at": "2026-10-29T21:30:00+08:00",
    "enabled_sources": "<enabled_sources>",
    "episode_scope_mode": "follow",
    "id": 0,
    "is_upgrade": 0,
    "landed_at": "2026-10-29T21:30:00+08:00",
    "landed_share_code": "<landed_share_code>",
    "landed_tag": "<landed_tag>",
    "landed_via": "<landed_via>",
    "last_check_at": "2026-10-29T21:30:00+08:00",
    "last_error": "<last_error>",
    "media_type": "tv",
    "metadata_checked_at": "2026-10-29T21:30:00+08:00",
    "needed_episodes": "4-10",
    "poster_path": "/1XS1oqL89opfnbLl8WnZY1O1uJx.jpg",
    "priority_rule": "<priority_rule>",
    "proxy_id": 1,
    "retry_count": 0,
    "season": 1,
    "state": "pending",
    "subscribe_kind": "<subscribe_kind>",
    "title": "<title>",
    "tmdb_id": 1399,
    "total_episodes_known": 0,
    "updated_at": "2026-10-29T21:30:00+08:00",
    "year": "<year>"
  }
}
```

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `code` | "ok" |  |
| `data` | PoolIntent |  |
| `data.backdrop_path` | string | TMDB 背景图相对路径，拼接 https://image.tmdb.org/t/p/w1280 使用 |
| `data.baseline_priority_level` | integer |  |
| `data.baseline_tag` | string |  |
| `data.covered_episodes` | string | 已拥有的集数集合，格式如 "1-3,5" |
| `data.created_at` | string(date-time) | 创建时间（RFC 3339） |
| `data.enabled_sources` | string | JSON 数组字符串。 |
| `data.episode_scope_mode` | "follow" / "fixed" | follow 自动跟随新集；fixed 只获取指定集数范围 |
| `data.id` | integer(int64) | 订阅 ID，用于 GET/DELETE /api/subscribe/pool/intents/{id} |
| `data.is_upgrade` | 0 / 1 | 1 表示洗版订阅（已有资源，寻找更好版本） |
| `data.landed_at` | string(date-time) |  |
| `data.landed_share_code` | string | 宿主返回前会移除 URL 和凭据。 |
| `data.landed_tag` | string |  |
| `data.landed_via` | string |  |
| `data.last_check_at` | string(date-time) | 最近一次检查时间 |
| `data.last_error` | string | 宿主返回前会移除 URL 和凭据。 |
| `data.media_type` | "movie" / "tv" | 媒体类型：movie 电影、tv 剧集 |
| `data.metadata_checked_at` | string(date-time) |  |
| `data.needed_episodes` | string | 需要的集号（如 "1-24"），空=全部 |
| `data.poster_path` | string | TMDB 海报相对路径，拼接 https://image.tmdb.org/t/p/w500 使用 |
| `data.priority_rule` | string |  |
| `data.proxy_id` | integer(int64) | Emby 实例 ID，来自 GET /api/plugin-host/emby/instances；省略使用默认实例 |
| `data.retry_count` | integer | 已重试次数 |
| `data.season` | integer | 0=电影或全集 |
| `data.state` | "pending" / "searching" / "transferring" / "partial" / "caught_up" / "landed" / "failed" / "expired" | 订阅状态：pending 刚创建、searching 搜索资源中、transferring 转存中、waiting 等待下载或转存完成、verifying 核对实际季集、partial 部分完成、caught_up 已覆盖当前已知集 |
| `data.subscribe_kind` | string | "" 普通/洗版；"missing" 缺集补全 |
| `data.title` | string | 标题 |
| `data.tmdb_id` | integer | TMDB 媒体 ID；电影与剧集分别编号，需配合 media_type 使用 |
| `data.total_episodes_known` | integer | 宿主当前已知的该季总集数，0 表示未知 |
| `data.updated_at` | string(date-time) | 更新时间（RFC 3339） |
| `data.year` | string | 年份 |

### GET `/api/subscribe/pt-search-site-selection`

<a id="get-api-subscribe-pt-search-site-selection"></a>

读取订阅站点选择。 读取订阅搜索使用的站点选择。

**调用**

```js
const res = await ctx.api.get('/api/subscribe/pt-search-site-selection')
```

**响应 200**（按契约结构生成的示例值）

```json
{
  "code": "<code>",
  "data": {
    "remembered": true,
    "site_ids": [
      0
    ]
  }
}
```

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `code` | string |  |
| `data` | object |  |
| `data.remembered` | boolean |  |
| `data.site_ids` | integer[] |  |

### PUT `/api/subscribe/pt-search-site-selection`

<a id="put-api-subscribe-pt-search-site-selection"></a>

更新订阅站点选择。 更新订阅搜索使用的站点选择。

**请求体（JSON）**

| 字段 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- |
| `site_ids` | integer[] |  |  |

**调用**

```js
const res = await ctx.api.put('/api/subscribe/pt-search-site-selection', {
  "site_ids": [
    0
  ]
})
```

**响应 200**（按契约结构生成的示例值）

```json
{
  "code": "<code>",
  "data": {
    "remembered": true,
    "site_ids": [
      0
    ]
  }
}
```

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `code` | string |  |
| `data` | object |  |
| `data.remembered` | boolean |  |
| `data.site_ids` | integer[] |  |

### GET `/api/subscribe/records`

<a id="get-api-subscribe-records"></a>

查询订阅记录。 查询某个媒体的订阅记录，可用于判断是否已订阅。

**参数**

| 名称 | 位置 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- | --- |
| `channel` | query | "aggregate" |  | 当前稳定值为 `aggregate`；省略返回全部。 |
| `media_type` | query | "movie" / "tv" |  | 媒体类型：movie 电影、tv 剧集 |
| `season` | query | integer |  | 季号，0 为特别篇 |
| `tmdb_id` | query | string |  | TMDB 媒体 ID；电影与剧集分别编号，需配合 media_type 使用 |

**调用**

```js
const res = await ctx.api.get('/api/subscribe/records?tmdb_id=1399&media_type=tv&season=1')
```

**响应 200**（按契约结构生成的示例值）

```json
{
  "code": "ok",
  "data": {
    "records": [
      {
        "backdrop_path": "<backdrop_path>",
        "channel": "aggregate",
        "covered_episodes": "1-3",
        "created_at": "2026-10-29T21:30:00+08:00",
        "id": 0,
        "is_upgrade": true,
        "media_type": "tv",
        "needed_episodes": "4-10",
        "poster_path": "/1XS1oqL89opfnbLl8WnZY1O1uJx.jpg",
        "season": 1,
        "status": "active",
        "title": "<title>",
        "tmdb_id": 1399,
        "total_episodes_known": 0,
        "updated_at": "2026-10-29T21:30:00+08:00",
        "year": "<year>"
      }
    ]
  }
}
```

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `code` | "ok" |  |
| `data` | object |  |
| `data.records` | SubscribeRecord[] |  |
| `data.records[].backdrop_path` | string | TMDB 背景图相对路径，拼接 https://image.tmdb.org/t/p/w1280 使用 |
| `data.records[].channel` | "aggregate" |  |
| `data.records[].covered_episodes` | string | 已拥有的集数集合，格式如 "1-3,5" |
| `data.records[].created_at` | string(date-time) | 创建时间（RFC 3339） |
| `data.records[].id` | integer(int64) |  |
| `data.records[].is_upgrade` | boolean |  |
| `data.records[].media_type` | "movie" / "tv" | 媒体类型：movie 电影、tv 剧集 |
| `data.records[].needed_episodes` | string | 仍需获取的集数集合，格式如 "4-10" |
| `data.records[].poster_path` | string | TMDB 海报相对路径，拼接 https://image.tmdb.org/t/p/w500 使用 |
| `data.records[].season` | integer | 0 表示无季信息（电影或整部） |
| `data.records[].status` | "active" / "partial" / "failed" / "expired" |  |
| `data.records[].title` | string | 标题 |
| `data.records[].tmdb_id` | integer | TMDB 媒体 ID；电影与剧集分别编号，需配合 media_type 使用 |
| `data.records[].total_episodes_known` | integer | 宿主当前已知的该季总集数，0 表示未知 |
| `data.records[].updated_at` | string(date-time) | 更新时间（RFC 3339） |
| `data.records[].year` | string | 年份 |

## TMDB

### GET `/api/tmdb/discover/movie`

<a id="get-api-tmdb-discover-movie"></a>

发现 TMDB 电影。 按条件发现电影。

**参数**

| 名称 | 位置 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- | --- |
| `page` | query | integer |  | 页码，从 1 开始 |
| `language` | query | string |  |  |
| `with_genres` | query | string |  | TMDB 电影发现参数；其他 TMDB 发现参数也按原样透传。 |
| `sort_by` | query | string |  |  |

**调用**

```js
const res = await ctx.api.get('/api/tmdb/discover/movie')
```

**响应 200**（按契约结构生成的示例值）

```json
{
  "page": 1,
  "results": [
    {
      "backdrop_path": "<backdrop_path>",
      "first_air_date": "<first_air_date>",
      "genre_ids": [
        0
      ],
      "id": 0,
      "media_type": "tv",
      "name": "<name>",
      "original_language": "<original_language>",
      "original_name": "<original_name>",
      "original_title": "<original_title>",
      "overview": "<overview>",
      "popularity": 0,
      "poster_path": "/1XS1oqL89opfnbLl8WnZY1O1uJx.jpg",
      "release_date": "<release_date>",
      "title": "<title>",
      "vote_average": 0,
      "vote_count": 0
    }
  ],
  "total_pages": 0,
  "total_results": 0
}
```

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `page` | integer | 页码，从 1 开始 |
| `results` | TmdbItem[] |  |
| `results[].backdrop_path` | string | TMDB 背景图相对路径，拼接 https://image.tmdb.org/t/p/w1280 使用 |
| `results[].first_air_date` | string | 剧集首播日期 |
| `results[].genre_ids` | integer[] |  |
| `results[].id` | integer | TMDB ID |
| `results[].media_type` | string | movie 或 tv |
| `results[].name` | string | 剧集名称（电影为空） |
| `results[].original_language` | string |  |
| `results[].original_name` | string |  |
| `results[].original_title` | string | 原始语言标题 |
| `results[].overview` | string | 简介 |
| `results[].popularity` | number |  |
| `results[].poster_path` | string | TMDB 海报相对路径，拼接 https://image.tmdb.org/t/p/w500 使用 |
| `results[].release_date` | string | 电影上映日期 |
| `results[].title` | string | 电影标题（剧集为空） |
| `results[].vote_average` | number |  |
| `results[].vote_count` | integer |  |
| `total_pages` | integer | 总页数 |
| `total_results` | integer | 总结果数 |

### GET `/api/tmdb/discover/tv`

<a id="get-api-tmdb-discover-tv"></a>

发现 TMDB 剧集。 按条件发现剧集。

**参数**

| 名称 | 位置 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- | --- |
| `page` | query | integer |  | 页码，从 1 开始 |
| `language` | query | string |  |  |
| `with_genres` | query | string |  | TMDB 剧集发现参数；其他 TMDB 发现参数也按原样透传。 |
| `sort_by` | query | string |  |  |

**调用**

```js
const res = await ctx.api.get('/api/tmdb/discover/tv')
```

**响应 200**（按契约结构生成的示例值）

```json
{
  "page": 1,
  "results": [
    {
      "backdrop_path": "<backdrop_path>",
      "first_air_date": "<first_air_date>",
      "genre_ids": [
        0
      ],
      "id": 0,
      "media_type": "tv",
      "name": "<name>",
      "original_language": "<original_language>",
      "original_name": "<original_name>",
      "original_title": "<original_title>",
      "overview": "<overview>",
      "popularity": 0,
      "poster_path": "/1XS1oqL89opfnbLl8WnZY1O1uJx.jpg",
      "release_date": "<release_date>",
      "title": "<title>",
      "vote_average": 0,
      "vote_count": 0
    }
  ],
  "total_pages": 0,
  "total_results": 0
}
```

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `page` | integer | 页码，从 1 开始 |
| `results` | TmdbItem[] |  |
| `results[].backdrop_path` | string | TMDB 背景图相对路径，拼接 https://image.tmdb.org/t/p/w1280 使用 |
| `results[].first_air_date` | string | 剧集首播日期 |
| `results[].genre_ids` | integer[] |  |
| `results[].id` | integer | TMDB ID |
| `results[].media_type` | string | movie 或 tv |
| `results[].name` | string | 剧集名称（电影为空） |
| `results[].original_language` | string |  |
| `results[].original_name` | string |  |
| `results[].original_title` | string | 原始语言标题 |
| `results[].overview` | string | 简介 |
| `results[].popularity` | number |  |
| `results[].poster_path` | string | TMDB 海报相对路径，拼接 https://image.tmdb.org/t/p/w500 使用 |
| `results[].release_date` | string | 电影上映日期 |
| `results[].title` | string | 电影标题（剧集为空） |
| `results[].vote_average` | number |  |
| `results[].vote_count` | integer |  |
| `total_pages` | integer | 总页数 |
| `total_results` | integer | 总结果数 |

### GET `/api/tmdb/genres`

<a id="get-api-tmdb-genres"></a>

查询 TMDB 类型。 读取电影和剧集类型。

**参数**

| 名称 | 位置 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- | --- |
| `type` | query | "movie" / "tv" |  | tv 返回剧集类型，其他值或省略返回电影类型。 |

**调用**

```js
const res = await ctx.api.get('/api/tmdb/genres')
```

**响应 200**（按契约结构生成的示例值）

```json
{
  "genres": [
    {
      "id": 0,
      "name": "<name>"
    }
  ]
}
```

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `genres` | TmdbGenre[] |  |
| `genres[].id` | integer |  |
| `genres[].name` | string | 名称 |

### GET `/api/tmdb/movie/{id}`

<a id="get-api-tmdb-movie-id"></a>

查询 TMDB 电影。 读取电影详情。

**参数**

| 名称 | 位置 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- | --- |
| `id` | path | integer | 是 |  |

**调用**

```js
const res = await ctx.api.get('/api/tmdb/movie/1')
```

**响应 200**（按契约结构生成的示例值）

```json
{
  "backdrop_path": "<backdrop_path>",
  "genres": [
    {
      "id": 0,
      "name": "<name>"
    }
  ],
  "id": 0,
  "original_title": "<original_title>",
  "overview": "<overview>",
  "poster_path": "/1XS1oqL89opfnbLl8WnZY1O1uJx.jpg",
  "production_companies": [
    {
      "id": 0,
      "logo_path": "<logo_path>",
      "name": "<name>",
      "origin_country": "<origin_country>"
    }
  ],
  "release_date": "<release_date>",
  "runtime": 0,
  "status": "<status>",
  "title": "<title>",
  "vote_average": 0,
  "vote_count": 0
}
```

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `backdrop_path` | string | TMDB 背景图相对路径，拼接 https://image.tmdb.org/t/p/w1280 使用 |
| `genres` | TmdbGenre[] |  |
| `genres[].id` | integer |  |
| `genres[].name` | string | 名称 |
| `id` | integer |  |
| `original_title` | string | 原始语言标题 |
| `overview` | string | 简介 |
| `poster_path` | string | TMDB 海报相对路径，拼接 https://image.tmdb.org/t/p/w500 使用 |
| `production_companies` | TmdbCompany[] |  |
| `production_companies[].id` | integer |  |
| `production_companies[].logo_path` | string |  |
| `production_companies[].name` | string | 名称 |
| `production_companies[].origin_country` | string |  |
| `release_date` | string |  |
| `runtime` | integer |  |
| `status` | string |  |
| `title` | string | 标题 |
| `vote_average` | number |  |
| `vote_count` | integer |  |

### GET `/api/tmdb/search`

<a id="get-api-tmdb-search"></a>

搜索 TMDB。 搜索 TMDB 电影与剧集（多类型）。电影用 title/release_date，剧集用 name/first_air_date。

**参数**

| 名称 | 位置 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- | --- |
| `q` | query | string | 是 | 搜索关键词 |
| `page` | query | integer |  | 页码，从 1 开始 |

**调用**

```js
const res = await ctx.api.get('/api/tmdb/search?q=权力的游戏&page=1')
```

**响应 200**

```json
{
  "page": 1,
  "total_pages": 1,
  "total_results": 1,
  "results": [
    {
      "id": 1399,
      "media_type": "tv",
      "title": "",
      "name": "权力的游戏",
      "original_title": "",
      "original_name": "Game of Thrones",
      "original_language": "en",
      "overview": "七大王国的权力争夺。",
      "poster_path": "/1XS1oqL89opfnbLl8WnZY1O1uJx.jpg",
      "backdrop_path": "/2OMB0ynKlyIenMJWI2Dy9IWT4c.jpg",
      "release_date": "",
      "first_air_date": "2011-04-17",
      "genre_ids": [
        10765,
        18
      ],
      "popularity": 120.5,
      "vote_average": 8.4,
      "vote_count": 23000
    }
  ]
}
```

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `page` | integer | 页码，从 1 开始 |
| `results` | TmdbItem[] |  |
| `results[].backdrop_path` | string | TMDB 背景图相对路径，拼接 https://image.tmdb.org/t/p/w1280 使用 |
| `results[].first_air_date` | string | 剧集首播日期 |
| `results[].genre_ids` | integer[] |  |
| `results[].id` | integer | TMDB ID |
| `results[].media_type` | string | movie 或 tv |
| `results[].name` | string | 剧集名称（电影为空） |
| `results[].original_language` | string |  |
| `results[].original_name` | string |  |
| `results[].original_title` | string | 原始语言标题 |
| `results[].overview` | string | 简介 |
| `results[].popularity` | number |  |
| `results[].poster_path` | string | TMDB 海报相对路径，拼接 https://image.tmdb.org/t/p/w500 使用 |
| `results[].release_date` | string | 电影上映日期 |
| `results[].title` | string | 电影标题（剧集为空） |
| `results[].vote_average` | number |  |
| `results[].vote_count` | integer |  |
| `total_pages` | integer | 总页数 |
| `total_results` | integer | 总结果数 |

### GET `/api/tmdb/trending`

<a id="get-api-tmdb-trending"></a>

查询 TMDB 趋势。 读取电影或剧集趋势。

**参数**

| 名称 | 位置 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- | --- |
| `media_type` | query | "all" / "movie" / "tv" / "person" |  | 媒体类型：movie 电影、tv 剧集 |
| `time_window` | query | "day" / "week" |  |  |
| `page` | query | integer |  | 页码，从 1 开始 |

**调用**

```js
const res = await ctx.api.get('/api/tmdb/trending')
```

**响应 200**（按契约结构生成的示例值）

```json
{
  "page": 1,
  "results": [
    {
      "backdrop_path": "<backdrop_path>",
      "first_air_date": "<first_air_date>",
      "genre_ids": [
        0
      ],
      "id": 0,
      "media_type": "tv",
      "name": "<name>",
      "original_language": "<original_language>",
      "original_name": "<original_name>",
      "original_title": "<original_title>",
      "overview": "<overview>",
      "popularity": 0,
      "poster_path": "/1XS1oqL89opfnbLl8WnZY1O1uJx.jpg",
      "release_date": "<release_date>",
      "title": "<title>",
      "vote_average": 0,
      "vote_count": 0
    }
  ],
  "total_pages": 0,
  "total_results": 0
}
```

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `page` | integer | 页码，从 1 开始 |
| `results` | TmdbItem[] |  |
| `results[].backdrop_path` | string | TMDB 背景图相对路径，拼接 https://image.tmdb.org/t/p/w1280 使用 |
| `results[].first_air_date` | string | 剧集首播日期 |
| `results[].genre_ids` | integer[] |  |
| `results[].id` | integer | TMDB ID |
| `results[].media_type` | string | movie 或 tv |
| `results[].name` | string | 剧集名称（电影为空） |
| `results[].original_language` | string |  |
| `results[].original_name` | string |  |
| `results[].original_title` | string | 原始语言标题 |
| `results[].overview` | string | 简介 |
| `results[].popularity` | number |  |
| `results[].poster_path` | string | TMDB 海报相对路径，拼接 https://image.tmdb.org/t/p/w500 使用 |
| `results[].release_date` | string | 电影上映日期 |
| `results[].title` | string | 电影标题（剧集为空） |
| `results[].vote_average` | number |  |
| `results[].vote_count` | integer |  |
| `total_pages` | integer | 总页数 |
| `total_results` | integer | 总结果数 |

### GET `/api/tmdb/tv/{id}`

<a id="get-api-tmdb-tv-id"></a>

查询 TMDB 剧集。 读取剧集详情和季度信息。

**参数**

| 名称 | 位置 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- | --- |
| `id` | path | integer | 是 |  |
| `raw_episode_counts` | query | boolean |  | 为 `true` 时不应用宿主保存的集数修正规则。 |

**调用**

```js
const res = await ctx.api.get('/api/tmdb/tv/1')
```

**响应 200**（按契约结构生成的示例值）

```json
{
  "backdrop_path": "<backdrop_path>",
  "first_air_date": "<first_air_date>",
  "genres": [
    {
      "id": 0,
      "name": "<name>"
    }
  ],
  "id": 0,
  "name": "<name>",
  "number_of_episodes": 0,
  "number_of_seasons": 0,
  "original_name": "<original_name>",
  "overview": "<overview>",
  "poster_path": "/1XS1oqL89opfnbLl8WnZY1O1uJx.jpg",
  "seasons": [
    {
      "air_date": "<air_date>",
      "episode_count": 0,
      "id": 0,
      "name": "<name>",
      "poster_path": "/1XS1oqL89opfnbLl8WnZY1O1uJx.jpg",
      "season_number": 0
    }
  ],
  "status": "<status>"
}
```

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `backdrop_path` | string | TMDB 背景图相对路径，拼接 https://image.tmdb.org/t/p/w1280 使用 |
| `first_air_date` | string |  |
| `genres` | TmdbGenre[] |  |
| `genres[].id` | integer |  |
| `genres[].name` | string | 名称 |
| `id` | integer |  |
| `name` | string | 名称 |
| `number_of_episodes` | integer |  |
| `number_of_seasons` | integer |  |
| `original_name` | string |  |
| `overview` | string | 简介 |
| `poster_path` | string | TMDB 海报相对路径，拼接 https://image.tmdb.org/t/p/w500 使用 |
| `seasons` | TmdbSeason[] |  |
| `seasons[].air_date` | string |  |
| `seasons[].episode_count` | integer |  |
| `seasons[].id` | integer |  |
| `seasons[].name` | string | 名称 |
| `seasons[].poster_path` | string | TMDB 海报相对路径，拼接 https://image.tmdb.org/t/p/w500 使用 |
| `seasons[].season_number` | integer |  |
| `status` | string |  |

## 加密服务

### POST `/v3/decrypt`

<a id="post-v3-decrypt"></a>

管理员上传加密 .dian115p 并解密为源码包；不留档、不执行插件。

**请求体**：application/vnd.dian115.plugin

**响应 200**：还原后的源码 .dian115p，文件路径和字节保持一致

### GET `/v3/info`

<a id="get-v3-info"></a>

读取加密 Worker 的插件包格式与上传容量。

**响应 200**（按契约结构生成的示例值）

```json
{
  "admin_decryption": true,
  "host_key_id": "<host_key_id>",
  "max_encrypted_upload_bytes": 0,
  "max_expanded_bytes": 0,
  "max_upload_bytes": 0,
  "offline_install": true,
  "package_extension": ".dian115p",
  "package_media_type": "application/vnd.dian115.plugin",
  "protocol": 3,
  "public_encryption": true,
  "source_retention": false
}
```

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `admin_decryption` | true |  |
| `host_key_id` | string | 内部源码保护版本标识，不是用户配置项 |
| `max_encrypted_upload_bytes` | integer | 管理员上传加密包的容量，独立于源码压缩包容量 |
| `max_expanded_bytes` | integer |  |
| `max_upload_bytes` | integer |  |
| `offline_install` | true |  |
| `package_extension` | ".dian115p" |  |
| `package_media_type` | "application/vnd.dian115.plugin" |  |
| `protocol` | 3 |  |
| `public_encryption` | true | 作者加密入口公开，无需登录或口令 |
| `source_retention` | false | 上传内容和处理结果均不留档 |

### POST `/v3/releases`

<a id="post-v3-releases"></a>

公开上传完整源码 .dian115p 包并取得加密交付包，无需登录或口令。

**请求体**：application/vnd.dian115.plugin

**响应 200**：成功
