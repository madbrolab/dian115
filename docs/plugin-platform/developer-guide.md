# DIAN115 插件开发者指南

> 状态：Plugin API v1 当前 Docker 部署可用。主项目已提供市场/仓库、安装确认、remote runtime 管理、网络/代理、文件、115 转存/离线、订阅、KV、托管凭据和独立插件通知能力；官方 SDK、CLI、WASM supervisor 仍未作为稳定公共发行物提供。以下示例均以 HTTP remote runtime 和 `/plugin-api/v1` 为准。

本指南面向开发第三方插件的用户。平台安全设计和实现阶段见 [`README.md`](README.md)，接口的可机读定义见 [`openapi-v1.yaml`](openapi-v1.yaml)。

## 1. 选择运行方式

| 方式 | 适合场景 | 部署方式 | 限制 |
|---|---|---|---|
| WASM（规划） | 规则处理、自动化、轻量数据转换 | 代码随 `.d115p` 安装 | 当前安装器可校验包和 manifest，但 supervisor/import ABI 尚未发布，当前不能执行 |
| 外部 HTTP 服务（当前可用） | Python/Node/Java、原生依赖、已有服务 | 用户独立部署，插件中心绑定地址 | 需要维护服务可用性和验证 webhook |

当前开发和联调请选择外部 HTTP 服务。未来 WASM supervisor 发布后，两种方式将继续使用相同清单、安装时能力确认和业务 API；插件不应根据运行方式绕过能力层。

## 2. 插件项目结构

### 2.1 WASM

```text
my-plugin/
  manifest.json
  src/
  plugin.wasm
  ui/
    schema.json
  assets/
    icon.png
  README.md
```

### 2.2 外部服务

```text
my-plugin/
  manifest.json
  ui/
    schema.json
  assets/
    icon.png
  service/
    ...
  README.md
```

外部服务的实际 base URL 不写入清单。用户在插件中心“运行时”面板绑定，例如 `https://plugin.example.com`；非 HTTPS 只允许 localhost/loopback 开发地址，不能把局域网或公网明文地址当作生产配置。

## 3. `manifest.json`

使用 [`manifest.schema.json`](manifest.schema.json) 校验。关键规则：

- `id` 使用反向域名风格，只允许小写字母、数字、点和连字符，例如 `dev.example.auto-transfer`。
- `version` 使用 SemVer，不带 `v` 前缀。
- `default_locale` 是 manifest 和声明式 UI 自带文案的语言；v1 每个包只提供一种插件文案语言。
- `compatibility.dian115` 和 `compatibility.plugin_api` 必须明确范围。
- 当前宿主要求这两个字段非空并保存原值，但尚未对任意 SemVer 范围执行宿主版本求值；不要把清单中的范围当成宿主已完成兼容性承诺。
- 每个 capability 必须说明 `reason`；安装页会原样展示，避免使用模糊的“正常运行所需”。
- 所有 capability 在安装/更新时一次性整体同意，不存在 required/optional、host/root/quota 或逐操作审批。
- 使用 `accounts.115.use` 时必须提供非空 `permissions.account_access`。
- 声明任一 `files.cloud.*` 或 `transfer.115.*` 时必须同时声明 `accounts.115.use` 和非空 `account_access`。
- 插件 ID、发布者密钥和 runtime kind 不能在普通升级中更改。
- JSON Schema 负责结构校验，宿主和 CLI 还会校验重复 capability、账号依赖、events/jobs 与能力类别的一致性；未知能力会失败。

WASM 清单结构仍由 schema 和安装包检查器保留，用于未来兼容；当前主项目没有 WASM supervisor，插件中心会明确拒绝安装 `runtime.kind=wasm` 的包。当前可实际安装和运行的第三方插件必须使用下文的 remote runtime。

预留的 WASM 清单结构：

```json
{
  "$schema": "https://dian115.example/schemas/plugin-manifest-v1.json",
  "schema_version": 1,
  "id": "dev.example.hello",
  "name": "Hello Plugin",
  "version": "1.0.0",
  "description": "最小 WASM 插件示例。",
  "default_locale": "zh-CN",
  "publisher": {
    "name": "Example Developer",
    "key_id": "ed25519:replace-with-your-key-id"
  },
  "compatibility": {
    "dian115": ">=3.9.0 <4.0.0",
    "plugin_api": "^1.0"
  },
  "runtime": {
    "kind": "wasm",
    "entry": "plugin.wasm",
    "abi": "dian115:plugin@1",
    "memory_mb": 16,
    "timeout_ms": 10000
  },
  "permissions": {
    "capabilities": []
  }
}
```

外部服务 runtime：

```json
{
  "kind": "remote",
  "protocol": "dian115-http-plugin@1",
  "health_path": "/healthz",
  "event_path": "/v1/events",
  "action_path": "/v1/actions",
  "state_path": "/v1/state",
  "job_path": "/v1/jobs"
}
```

路径必须以 `/` 开头，只能是相对 base URL 的固定路径，不能包含 scheme、host、query 或 fragment。

## 4. 能力声明与安装确认

能力项格式：

```json
{
  "capability": "network.http",
  "reason": "连接外部媒体服务并查询评分"
}
```

`permissions` 完整示例：

```json
{
  "capabilities": [
    {"capability":"network.http","reason":"读取规则服务"},
    {"capability":"network.proxy","reason":"允许按系统配置通过代理访问规则服务"},
    {"capability":"transfer.115.create","reason":"创建分享转存任务"},
    {"capability":"accounts.115.use","reason":"选择执行 115 操作的账号"},
    {"capability":"notifications.plugin.send","reason":"反馈插件任务结果到宿主通知通道"}
  ],
  "account_access": ["main", "backup_pool", "backup_select"]
}
```

`account_access` 含义：

| 值 | 安装提示 | 运行时 selector |
|---|---|---|
| `main` | 可使用当前主账号 | `{"mode":"main"}` |
| `backup_pool` | 可让宿主从备用号池轮询选择 | `{"mode":"backup_pool"}` |
| `backup_select` | 可查看安全摘要并指定一个备用账号 | `{"mode":"backup_ref","account_ref":"a115_..."}` |

安装确认是全有或全无：用户不能只批准某个 host、目录、账号或单次操作。当前运行时只检查 endpoint 的 `x-dian115-capability` 是否在已确认的 manifest 中，以及 selector 是否属于 `account_access`。Host API 仍执行对所有插件一致的输入校验、SSRF 阻断、opaque ref 归属、账号绑定、幂等、并发和响应大小上限。

安装器和 runtime 管理会做跨文件和跨能力校验：UI 的 `requires_capabilities` 必须已出现在同一 manifest；有 `events` 时必须声明 `events.subscribe`；有 `jobs` 时必须声明 `scheduler.register`；任一 `files.cloud.*` 或 `transfer.115.*` 必须同时声明 `accounts.115.use` 和非空 `account_access`；`jobs[].id` 必须全局唯一；remote runtime 的 health/event/action/state/job path 必须两两不同；runtime/UI 文件必须存在并通过包校验。更新 capability、reason、account_access、runtime 或 UI 声明时，旧 `consent_digest` 不可复用。

插件可调用 `GET /capabilities` 获取当前已确认的能力快照和 `capability_revision`。更新、禁用或卸载会让旧 token 失效；停用时新的 runtime 投递和 Host API 调用会被拒绝。

## 5. 通用调用规则

Base URL：

```text
https://<dian115-host>/plugin-api/v1
```

### 5.1 认证

WASM SDK 由宿主自动绑定身份，不需要处理 token。

外部插件先换取短期 token：

```http
POST /plugin-api/v1/auth/token
Content-Type: application/json

{
  "client_id": "pli_01K2ABCDE...",
  "client_secret": "d115ps_0123456789abcdef0123456789"
}
```

响应：

```json
{
  "data": {
    "access_token": "eyJ...",
    "token_type": "Bearer",
    "expires_in": 900,
    "capability_revision": 7
  },
  "meta": {
    "request_id": "req_01K...",
    "idempotent_replay": false
  }
}
```

后续请求：

```http
Authorization: Bearer <access_token>
```

不要记录 `client_secret`、`access_token` 或 webhook secret。收到 `401 token_expired` 时只重试一次换票；收到 `401 token_stale` 时停止工作并重新换票，若安装实例已禁用或正在等待更新确认则不要继续调用。

生产部署必须通过 HTTPS 调用 Plugin API。明文 HTTP 只允许 loopback 开发模式；不要把 client secret 发送到局域网或公网明文端点。

### 5.2 幂等

所有创建、修改、取消和文件写入请求必须带：

```http
Idempotency-Key: <每个逻辑操作唯一的 16-128 字符键>
```

建议使用 UUIDv4/UUIDv7。同一端点、同一插件实例、同一 key 和相同请求体会返回原结果；相同 key 配不同请求体返回 `409 idempotency_conflict`。

客户端超时后应使用同一 key 重试，不能生成新 key。job 进入 `attention_required` 且错误码为 `submission_uncertain` 时，不得自动重新创建或再次提交。

普通幂等结果默认保留 24 小时。`submission_uncertain` 对应的记录会固定保留到人工对账完成，期间相同 key 只能返回原状态，不能再次触发上游调用。

### 5.3 请求跟踪与限流

- 每个响应包含 `X-Request-ID`。
- 可传 `X-Correlation-ID` 串联插件自己的任务。
- `429` 会包含 `Retry-After` 或 `retry_after_ms`。
- 分页统一使用 `cursor`，不要依赖数据库 ID 连续递增。
- 时间统一使用 RFC 3339 UTC。

JSON 成功响应统一使用：

```json
{
  "data": {},
  "meta": {
    "request_id": "req_01K...",
    "idempotent_replay": false
  }
}
```

为突出业务字段，后续部分示例只展示 `data` 内部内容；实际 JSON 响应仍包含外层 `data/meta`。文件内容读取是例外，直接返回受限的 `application/octet-stream` 字节流和 ETag/Range 头。

### 5.4 错误格式

错误使用 `application/problem+json`：

```json
{
  "type": "https://dian115.example/problems/capability-denied",
  "title": "Capability denied",
  "status": 403,
  "code": "capability_denied",
  "detail": "plugin manifest does not declare network.http",
  "request_id": "req_01K...",
  "retryable": false
}
```

插件逻辑应主要判断稳定的 `code`，不要解析 `detail` 文本。

### 5.5 安装实例 KV

声明 `storage.kv` 后，每个安装实例拥有独立命名空间。推荐使用可列表、支持 slash key 的 canonical 接口：

```http
GET    /plugin-api/v1/kv?prefix=settings/&limit=100
GET    /plugin-api/v1/kv/settings/main
PUT    /plugin-api/v1/kv/settings/main
DELETE /plugin-api/v1/kv/settings/main
```

`/plugin-api/v1/storage/{key}` 是兼容别名，key 只允许字母、数字、点、下划线和连字符，不提供列表；新插件优先使用 `/kv`。读取响应包含 `ETag: "pkv_<version>"`。更新可带 `If-Match` 做 CAS，删除必须带当前 `If-Match`；写入和删除都必须使用稳定 `Idempotency-Key`。

```json
{
  "value": {
    "enabled": true,
    "cursor": "opaque-plugin-value"
  }
}
```

KV 只能保存插件自己的普通状态。不要写入 client secret、webhook secret、115 Cookie、绝对路径或其他安装实例的数据。

## 6. 网络和系统代理

请求：

```http
POST /plugin-api/v1/network/requests
Authorization: Bearer <token>
Idempotency-Key: 0ec0e7c8-b04d-4fc4-9cb1-d70ba4823012
Content-Type: application/json

{
  "method": "GET",
  "url": "https://api.example.com/v1/items?limit=20",
  "headers": {
    "accept": "application/json"
  },
  "proxy_mode": "system",
  "timeout_ms": 10000,
  "max_response_bytes": 262144,
  "redirects": 3
}
```

响应：

```json
{
  "status": 200,
  "final_url": "https://api.example.com/v1/items?limit=20",
  "headers": {
    "content-type": ["application/json"]
  },
  "body": {
    "encoding": "utf8",
    "data": "{\"items\":[]}"
  },
  "truncated": false,
  "proxy_used": true,
  "duration_ms": 184
}
```

请求 body 支持：

```json
{
  "body": {
    "encoding": "json",
    "data": {"query": "example"}
  }
}
```

或：

```json
{
  "body": {
    "encoding": "base64",
    "data": "AAECAwQ="
  }
}
```

注意：

- `system` 表示遵循 DIAN115 系统代理策略，需要 manifest 声明 `network.proxy`。
- `required` 同样需要 `network.proxy`；没有可安全使用的系统代理就失败。
- `direct` 只需要 `network.http`，但仍可能被管理员的全局网络策略拒绝。
- URL 只接受小写 `https` scheme，不允许 userinfo 或 fragment。
- 插件提交的 header 名必须是小写 ASCII token；不能设置 `host`、`cookie`、`authorization`、`proxy-authorization`、连接级 header 或报文分帧 header。需要第三方凭据时申请 `secrets.use`，由宿主注入。
- 需要凭据时可传安装实例专属的 `credential_ref`。该引用不含秘密；宿主只会按 credential binding 的固定位置和模板注入，插件不能在单次请求里改写注入规则。
- 网络响应不保证保留所有 header，敏感和 hop-by-hop header 会被过滤。
- v1 不把 host/method/port 写入 manifest。宿主会对所有插件逐跳校验 scheme、端口、解析出的 IP 和系统网络策略，并把实际拨号固定到已验证 IP；无法保证私网阻断的远端 DNS 代理不会用于插件流量。
- 非幂等上游方法只进行一次 transport attempt；响应不确定时返回 `submission_uncertain`，相同幂等键也不会再次发出请求。

## 7. 文件管理

### 7.1 获取 Host API 根

```http
GET /plugin-api/v1/files/roots
```

```json
{
  "items": [
    {
      "root_id": "root_incoming",
      "root_entry_ref": "fe_01KROOT...",
      "name": "待处理目录",
      "backend": "local",
      "capabilities": ["files.local.read", "files.local.write"]
    }
  ]
}
```

`root_id` 和 `root_entry_ref` 都是安装实例作用域内的 opaque ID。列表只包含 Host API 配置允许暴露的根，不做每插件 root 绑定；不要按 name 或列表顺序猜测，也不要缓存或推断宿主绝对路径、CD2 path 或 CID。云端根还会绑定一个 `account_selection_ref`，不能与其他账号的 entry ref 混用。

### 7.2 列目录

```http
GET /plugin-api/v1/files/entries?root_id=root_incoming&parent_ref=fe_01KROOT...&limit=100
```

```json
{
  "root_id": "root_incoming",
  "parent_ref": "fe_01KROOT...",
  "items": [
    {
      "entry_ref": "fe_01KTASK...",
      "root_id": "root_incoming",
      "display_path": "inbox/task.json",
      "name": "task.json",
      "kind": "file",
      "size": 812,
      "modified_at": "2026-08-17T02:10:00Z",
      "revision": "rev_01K..."
    }
  ],
  "next_cursor": null
}
```

`display_path` 只供界面展示，不能作为后续操作参数。CD2 等 backend 没有可信时间戳时 `modified_at` 为 `null`，不会返回空字符串；`revision` 是独立的 opaque CAS token，不能由客户端从时间戳推断。每次实际执行时，宿主都会重新解析 `entry_ref`、最近存在祖先、符号链接或 Windows reparse point，并再次验证对象仍在 Host API 暴露根内。

### 7.3 读取内容

读取 Host API 根内文件：

```http
GET /plugin-api/v1/files/entries/fe_01KTASK.../content
Range: bytes=0-65535
```

读取受系统统一的单次字节上限和 Range 限制；无效或不可满足的 Range 返回 `416`。Plugin API v1 暂不开放内容写入：当前本地上传不是统一的原子/CAS 写入，CD2 也没有相同语义。只有宿主实现临时文件、`fsync`、原子 rename、revision/ETag 和容量保护后才会增加写内容端点。

该端点直接返回原始字节，不使用 JSON `data/meta` 包装。客户端必须处理 `200/206`、单段 Range、`Content-Range` 和 ETag，不能一次读入不受限内容。

### 7.4 创建目录与重命名

创建目录：

```http
POST /plugin-api/v1/files/directories
Idempotency-Key: f699527c-b310-4434-95a6-6dbd39b526a0
Content-Type: application/json

{
  "parent_ref": "fe_01KROOT...",
  "name": "processed"
}
```

重命名要求 revision：

```http
PATCH /plugin-api/v1/files/entries/fe_01KTASK...
Idempotency-Key: 4cc4d34e-ff0f-4497-9921-cad56abff8a4
If-Match: "rev_01K..."
Content-Type: application/json

{
  "name": "task-processed.json"
}
```

### 7.5 批量复制与移动

```http
POST /plugin-api/v1/files/operations
Idempotency-Key: 54d9695a-a221-4db7-bfe9-c7ed05f91af7
Content-Type: application/json

{
  "operation": "move",
  "source_refs": ["fe_01KTASK..."],
  "destination_parent_ref": "fe_01KPROCESSED...",
  "conflict_policy": "fail"
}
```

返回 `202`：

```json
{
  "job_ref": "job_01K...",
  "status": "queued"
}
```

- v1 只支持同 backend copy/move，默认冲突策略为 `fail`，可选 `rename`，不提供默认覆盖。
- CD2 move 必须使用显式 conflict policy；本地 move 必须在执行时复核并安全预留同名目标，不能直接依赖平台相关的 rename 覆盖行为。
- 本地根检查 `files.local.read/write`，CD2 根检查 `files.cloud.read/write`；只按类别判断，不再检查 manifest root alias。
- v1 暂不开放删除。宿主完成可恢复 trash 后才会增加 `files.local.trash`/`files.cloud.trash`；永久 purge 不属于 Plugin API v1。

## 8. 115 转存与离线

### 8.1 选择 115 账号

先查询当前安装实例可用的 selector 模式：

```http
GET /plugin-api/v1/accounts/115
```

```json
{
  "available_modes": ["main", "backup_pool", "backup_ref"],
  "backup_accounts": [
    {
      "account_ref": "a115_01KBACKUP...",
      "name": "备用账号 2",
      "available": true
    }
  ]
}
```

只有 manifest 的 `account_access` 包含 `backup_select` 时才返回 `backup_accounts`；`account_ref` 是安装实例作用域的 opaque 引用，不是备用账号表 ID。随后创建短时账号选择：

```http
POST /plugin-api/v1/accounts/115/selections
Idempotency-Key: 35b719d1-8b82-4287-b364-8fb0bd21e176
Content-Type: application/json

{
  "selector": {
    "mode": "backup_pool"
  }
}
```

指定备用账号时改为：

```json
{
  "selector": {
    "mode": "backup_ref",
    "account_ref": "a115_01KBACKUP..."
  }
}
```

响应：

```json
{
  "account_selection_ref": "asel_01K...",
  "requested_mode": "backup_pool",
  "display_name": "备用账号 2",
  "expires_at": "2026-08-17T03:15:00Z"
}
```

`main` 使用当前激活主账号；`backup_pool` 由宿主原子轮询一个启用且有效的备用账号；`backup_ref` 只接受上述列表返回的引用。宿主不会返回 Cookie、设备凭据、真实数据库 ID 或 CID。

选择创建后，所有 115 目录、target、preview、item、离线任务和 job ref 都与该 `account_selection_ref` 及实际账号绑定。跨账号组合返回 `409 account_context_mismatch`。选择过期后已有 job 仍使用其创建时锁定的账号，但不能用过期选择创建新请求；结果不确定时禁止自动换号重试。

### 8.2 获取目标

```http
GET /plugin-api/v1/transfers/115/targets?operation=share_receive&account_selection_ref=asel_01K...
```

```json
{
  "items": [
    {
      "target_ref": "trg_01KSHARE...",
      "alias": "share_default",
      "name": "默认分享转存目录",
      "operation": "share_receive",
      "account_selection_ref": "asel_01K..."
    }
  ]
}
```

插件不能读取 115 CID、账号 ID、Cookie 或设备凭据。`target_ref` 与账号选择绑定，根 CID `0` 不会作为插件目标下发。

`GET /transfers/115/targets` 返回宿主为该账号配置的默认目录；需要让用户选择任意深层目录时，插件还要声明 `files.cloud.read` 或 `files.cloud.write`，并走 File Broker：

1. `GET /plugin-api/v1/files/roots?account_selection_ref=asel_01K...` 取得云端 `root_id/root_entry_ref`。
2. 使用 `GET /plugin-api/v1/files/entries?root_id=...&parent_ref=...&account_selection_ref=asel_01K...` 逐层浏览，直到用户选中一个 `kind=directory` 的 `entry_ref`。
3. 把该目录转换为同账号、同安装实例作用域的 `target_ref`：

```http
POST /plugin-api/v1/transfers/115/targets
Content-Type: application/json

{
  "operation": "offline_download",
  "entry_ref": "fe_01KDEEPDIR..."
}
```

响应中的 `data.target_ref` 可直接用于后续分享转存或离线下载。宿主会重新确认 `entry_ref` 仍是该 `account_selection_ref` 下存在的云目录，只把内部 CID 保存在 opaque target 记录中；文件条目、跨账号引用和根 CID `0` 都会被拒绝。

### 8.3 创建分享预览

```http
POST /plugin-api/v1/transfers/115/share-previews
Idempotency-Key: 27606a6b-35b4-43c2-92d9-456fe226e29f
Content-Type: application/json

{
  "share_url": "https://115.com/s/abc123?password=1a2b",
  "account_selection_ref": "asel_01K..."
}
```

响应：

```json
{
  "preview_ref": "spv_01K...",
  "expires_at": "2026-08-17T02:35:00Z",
  "title": "示例分享",
  "item_count": 12,
  "account_selection_ref": "asel_01K..."
}
```

宿主只接受明确列入白名单的 115 官方 host，并自行解析分享码。`preview_ref` 短时有效，原始分享码和接收码不会在后续响应、日志或事件中回显。

### 8.4 选择预览项

```http
GET /plugin-api/v1/transfers/115/share-previews/spv_01K.../items?limit=100
```

```json
{
  "items": [
    {
      "item_ref": "si_01KITEM...",
      "name": "Season 01",
      "kind": "directory",
      "size": 4294967296
    }
  ],
  "next_cursor": null
}
```

创建转存时必须明确提交一个或多个 `item_ref`。空选择、特殊 ID 或“整个分享”隐式扩展都无效。

### 8.5 创建分享转存 job

```http
POST /plugin-api/v1/transfers/115/share-receives
Idempotency-Key: f45dbd77-c7ea-46bf-92bf-8317af1dbdad
Content-Type: application/json

{
  "preview_ref": "spv_01K...",
  "selection": {
    "item_refs": ["si_01KITEM..."]
  },
  "target_ref": "trg_01KSHARE...",
  "metadata": {
    "label": "example rule #42"
  }
}
```

宿主必须先验证 `preview_ref`、全部 `item_ref` 和 `target_ref` 属于同一账号，再持久化 plugin job、幂等记录和 outbox，然后使用显式文件 ID 的单次传输调用。不能用空选择扩大为整分享，也不能在传输不确定时切换账号再次提交。

### 8.6 创建离线下载 job

```http
POST /plugin-api/v1/transfers/115/offline-downloads
Idempotency-Key: 718a3927-a9ae-4022-a704-c0d043685f6f
Content-Type: application/json

{
  "urls": ["magnet:?xt=urn:btih:..."],
  "target_ref": "trg_01KOFFLINE..."
}
```

单次最多 50 个 URL。宿主只进行一次非幂等 transport attempt；如果无法确认 115 是否已接受，job 进入 `attention_required`，不能自动重投。

创建响应：

```json
{
  "job_ref": "job_01K...",
  "status": "queued"
}
```

### 8.7 查询和取消 job

```http
GET /plugin-api/v1/jobs/job_01K...
```

```json
{
  "job_ref": "job_01K...",
  "kind": "transfer.115.share_receive",
  "status": "succeeded",
  "progress": 1,
  "cancellable": false,
  "created_at": "2026-08-17T02:20:00Z",
  "started_at": "2026-08-17T02:20:01Z",
  "finished_at": "2026-08-17T02:20:04Z"
}
```

取消：

```http
POST /plugin-api/v1/jobs/job_01K.../cancel
Idempotency-Key: 9b293578-ddc2-49c2-9b9d-0b358d72038e
```

cancel 只允许操作本安装实例拥有且当前 `cancellable=true` 的 job。宿主按 job 类型校验原始能力；转存 job 还需要 `transfer.115.cancel`。它只能停止排队或仍由宿主管理的工作，不能撤销 115 已经接受的转存或离线任务。离线任务列表与额度通过 `/transfers/115/offline-tasks?account_selection_ref=...` 和 `/transfers/115/offline-quota?account_selection_ref=...` 读取。

离线任务状态由宿主归一为 `queued/downloading/succeeded/failed/indeterminate`，插件不能依赖 CD2 或 115 的内部常量字符串。

不要在日志中打印分享 URL、分享码、接收码或离线 URL。`attention_required + submission_uncertain` 是终态，必须提示用户人工核对；对应幂等键在明确结果前不会再次执行。

## 9. 订阅管理

### 9.1 获取宿主配置档

```http
GET /plugin-api/v1/subscription-profiles
```

profile 使用 opaque ref 表示宿主已经配置的 PT 下载器、站点范围、质量规则或媒体库。持有 `subscriptions.create` 即可发现 Host API 可用的 profile，不必额外声明 `subscriptions.read`。插件不能提交 raw `proxy_id`、下载器名称、保存路径、站点 JSON 或本地路径。

### 9.2 创建

```http
POST /plugin-api/v1/subscriptions
Idempotency-Key: b30ee4e8-3f8f-4325-a7c9-c9d591ac34fe
Content-Type: application/json

{
  "engine": "aggregate",
  "media": {
    "tmdb_id": 1399,
    "media_type": "tv",
    "season": 1
  },
  "options": {
    "enabled_sources": ["dianying", "pt", "tg"],
    "total_episodes": 10,
    "needed_episodes": "1-10",
    "profile_ref": "sprof_01KDEFAULT..."
  },
  "metadata": {
    "label": "用户关注列表同步"
  }
}
```

响应为持久化创建 job：

```json
{
  "job_ref": "job_01KSUB...",
  "status": "queued"
}
```

job 成功后返回类型化结果，例如 `{"type":"subscription_created","subscription_ref":"sub_01K...","initial_search_submitted":true}`；再通过订阅查询接口取得 revision、宿主补全的标题和当前状态。创建接口不会在副作用完成前伪装成同步成功。

创建 PT 订阅时使用 `engine=pt` 和宿主下发的 `profile_ref`。宿主会执行 TMDB 补全、媒体库检查、内部 PT/aggregate 冲突检查、下载器与路径校验、默认规则、持久化和首次搜索。插件不能提交 title/year/poster/state/covered/baseline/terminal 字段，也不能使用 `library_snapshot_provided` 绕过宿主检查。

TV 省略 `season` 时宿主统一按 1，电影只允许 0。`total_episodes` 最大 10000；`needed_episodes` 使用 `all` 或 `1-6,8,10-12` 紧凑格式，展开后也不能超过 10000。

### 9.3 查询和分页

```http
GET /plugin-api/v1/subscriptions?engine=aggregate&state=pending&limit=50
```

声明 `subscriptions.read` 后可读取 Host API 暴露的订阅集合；每条记录包含安全的 `created_by` 摘要，便于插件区分自身和其他来源。插件始终使用 opaque `subscription_ref`，权威记录来自 PT subscriptions 或 pool intents，不使用兼容展示表的 ID。

活动状态统一为 `pending/searching/transferring/waiting/verifying/partial/needs_attention/failed/expired`。`landed/cancelled` 仅是现有内部兼容状态，不作为 Plugin API 的活动订阅返回；完成或删除由 job/event 表达，之后对象查询为 `404`。

### 9.4 更新 aggregate TV 集数

```http
PATCH /plugin-api/v1/subscriptions/sub_01K.../episodes
Idempotency-Key: b86e7340-2435-44cb-b360-5824086a8106
If-Match: "rev_01K..."
Content-Type: application/json

{
  "total_episodes": 12,
  "needed_episodes": "1-12"
}
```

v1 只允许 aggregate TV 调用该接口，并由 `PoolOrchestrator.UpdateIntentEpisodes` 推进状态。PT 通用更新、洗版切换和任意字段 PATCH 暂不开放。revision 不匹配返回 `412 precondition_failed`。

### 9.5 删除与手动搜索

```http
DELETE /plugin-api/v1/subscriptions/sub_01K...
Idempotency-Key: 7e40478a-f21c-4b14-9701-3d4ec590a3f8
```

当前 PT 和 aggregate 的删除语义都是物理删除订阅记录，不会撤销下载器或 115 已经接受的工作。声明 `subscriptions.cancel` 后删除请求直接创建 `queued` job，不再逐操作审批；插件仍不能绕过冲突清理流程，安装页必须把该物理删除风险明确展示给用户。

触发一次宿主搜索：

```http
POST /plugin-api/v1/subscriptions/sub_01K.../search
Idempotency-Key: 0531215b-ed4b-48fe-af1c-6231821bd9b5
```

搜索进入持久化 job，并要求 `subscriptions.update`；创建、删除和搜索都不能把内部 WorkQueue task ID 暴露给插件。

### 9.6 插件通知

声明 `notifications.plugin.send` 后，插件可以把自身任务结果交给宿主已经配置的通知通道。宿主从安装记录注入插件显示名，插件不能在请求中伪造名称，也不能取得 Telegram Bot Token、白名单或其他凭据。

```http
POST /plugin-api/v1/notifications
Authorization: Bearer <plugin access token>
Idempotency-Key: 9b293578-ddc2-49c2-9b9d-0b358d72038e
Content-Type: application/json
```

```json
{
  "level": "success",
  "title": "离线任务完成",
  "body": "已保存 12 个文件",
  "job_ref": "job_01K...",
  "dedupe_key": "offline-20260818-001"
}
```

`level` 只能是 `info`、`success`、`warning`、`error`。`title` 最多 160 个字符，`body` 最多 2000 个字符，`job_ref` 最多 128 个字符；控制字符和未知 JSON 字段会被拒绝。宿主在最终 Telegram 渲染前再次进行 HTML 转义和内部地址脱敏。

成功排队返回 `202`；重复 `dedupe_key`（同一安装实例十分钟内）或通知通道未启用/命中静默时段返回 `200`，响应中的 `deduplicated` 或 `suppressed/suppression_reason` 会说明结果。单个插件每分钟最多 12 条，超限返回 `429 rate_limited` 和 `Retry-After`；不要通过更换幂等键绕过限制。所有写请求都必须使用稳定的 `Idempotency-Key`，同一逻辑操作重试时保持不变。

通知开关和模板位于宿主的“通知插件”页面；Telegram 渠道中的独立通知类型名称为“插件通知”，事件标识固定为 `plugin_notification_message`。用户可以独立关闭“插件通知”，这不会影响系统文件、订阅或账号通知；插件应把 `suppressed` 视为明确结果而不是无限重试。

## 10. 事件处理

### 10.1 事件信封

```json
{
  "event_id": "evt_01K...",
  "topic": "transfer.completed",
  "occurred_at": "2026-08-17T02:20:04Z",
  "installation_id": "pli_01K...",
  "data": {
    "job_ref": "job_01K...",
    "status": "succeeded"
  }
}
```

事件至少投递一次。处理流程应先用 `event_id` 去重，再执行副作用。

### 10.2 外部服务验证

收到 webhook 后：

1. 读取原始 body，不要先重新序列化 JSON。
2. 检查 `X-Dian115-Timestamp` 与当前时间相差不超过 5 分钟。
3. 计算 body 的十六进制 SHA-256，并构造 `v1\n<timestamp>\n<METHOD>\n<path-and-query>\n<body-sha256>`。
4. 计算 `HMAC-SHA256(webhook_secret, signing_string)`，再使用常量时间比较验证 `X-Dian115-Signature: v1=<hex>`。
5. 已处理过 `event_id` 或 `invocation_id` 时直接返回原有 `2xx` 结果。

接收方应在 10 秒内返回。耗时工作放入自己的队列；`5xx` 或超时会触发宿主重试，`2xx` 表示已接收而非业务已完成。

### 10.3 WASM 事件入口

SDK 暴露高层 handler，底层 ABI 不应由业务代码直接操作：

```rust
async fn on_event(event: dian115::Event) -> Result<(), dian115::Error> {
    match event.topic.as_str() {
        "transfer.completed" => { /* update plugin state */ }
        _ => {}
    }
    Ok(())
}
```

上例是目标 SDK 形态，SDK 尚未发布。

同一 SDK 还应提供 `on_job(job_id, invocation)` 和 `load_ui_state(view_id)` 高层入口，使 WASM 与远程插件的 scheduled job、声明式 UI 状态语义一致。

## 11. 声明式 UI

UI 文件使用 [`ui-schema-v1.schema.json`](ui-schema-v1.schema.json)。示例：

```json
{
  "schema_version": 1,
  "navigation": {
    "title": "自动转存助手",
    "icon": "cloud-download"
  },
  "views": [
    {
      "id": "main",
      "title": "运行状态",
      "sections": [
        {
          "type": "status",
          "source": "state.runtime",
          "fields": [
            {"key": "healthy", "label": "服务状态", "format": "boolean"},
            {"key": "processed_today", "label": "今日处理", "format": "number"}
          ]
        },
        {
          "type": "form",
          "id": "settings",
          "submit_action": "save_settings",
          "fields": [
            {"key": "enabled", "label": "启用自动处理", "control": "switch"},
            {"key": "interval_minutes", "label": "检查周期", "control": "number", "min": 5, "max": 1440}
          ]
        },
        {
          "type": "actions",
          "actions": [
            {"id": "test_connection", "label": "测试连接", "icon": "plug", "style": "secondary"}
          ]
        }
      ]
    }
  ]
}
```

UI action 只调用插件自己的 action handler。handler 若要访问网络、文件、转存或订阅，仍需调用对应能力 API。

Action 的 `confirm` 只控制宿主界面的普通命令提示框，不改变安装时已确认的 capability。异步能力调用通过校验后返回 `202 queued`，不会进入逐操作审批状态。

不要在 UI state 中返回 secret、token、绝对路径、115 CID 或其他插件数据。

插件 UI 的字面字符串使用 manifest 的 `default_locale`。v1 不定义运行时翻译资源或语言切换，宿主只负责自身导航、错误和安装确认等文案的国际化。表单也不接受插件提供的正则表达式；`select/multiselect` 必须提供非空且 value 不重复的 `options`，数值与长度边界必须满足 `min <= max`，不适用于当前 control 的字段会被安装器拒绝。

UI 语义校验还要求 `views[].id` 在整个 UI 文件内唯一；同一 view 内 section/form ID 和 action ID 不重复；同一 form 的 `fields[].key`、同一 table 的 column key 和同一 option 列表的 value 不重复。渲染器不能采用“后一个覆盖前一个”的方式容忍冲突。

## 12. 外部插件回调协议

DIAN115 会调用安装时配置的固定路径。

### 12.1 健康检查

```http
GET <base_url><health_path>
X-Dian115-Timestamp: ...
X-Dian115-Signature: v1=...
```

```json
{
  "status": "ok",
  "protocol": "dian115-http-plugin@1",
  "version": "1.0.0"
}
```

绑定完成后的健康检查也使用 webhook secret，并按空 body 的 SHA-256 参与同一签名算法。远程插件端点不得通过重定向把宿主带到另一个地址。

### 12.2 UI state

宿主通过签名 GET 拉取声明式 UI 的初始和刷新状态：

```http
GET <base_url><state_path>?view=main
X-Dian115-Timestamp: ...
X-Dian115-Signature: v1=...
If-None-Match: "state_01K..."
```

```json
{
  "state_version": "state_01K...",
  "state": {
    "runtime": {"healthy": true, "processed_today": 3},
    "settings": {"enabled": true, "interval_minutes": 15},
    "active_task": {"running": false},
    "recent_transfers": [],
    "logs": []
  }
}
```

响应同时返回 quoted `ETag`；状态未变化可返回 `304`。原始 JSON 最大 256 KiB，路径必须与 UI Schema 的 `source` 对应，并且不得包含 token、secret、宿主绝对路径或其他插件的数据。

### 12.3 UI action

```http
POST <base_url><action_path>/test_connection
X-Dian115-Timestamp: ...
X-Dian115-Signature: v1=...
Content-Type: application/json

{
  "invocation_id": "inv_01K...",
  "input": {},
  "context": {
    "locale": "zh-CN",
    "timezone": "Asia/Shanghai"
  }
}
```

响应：

```json
{
  "status": "succeeded",
  "message": "连接正常",
  "state_patch": {
    "runtime.healthy": true
  }
}
```

插件服务不能要求宿主把管理员 token、Cookie 或能力 token放入回调 body。服务应使用自己的 client credential 调用 Plugin API Gateway。

### 12.4 Scheduled job

宿主按 manifest 的 job 声明调用固定 job endpoint：

```http
POST <base_url><job_path>/poll_rules
X-Dian115-Timestamp: ...
X-Dian115-Signature: v1=...
Content-Type: application/json

{
  "invocation_id": "inv_01KJOB...",
  "job_id": "poll-rules",
  "scheduled_for": "2026-08-17T03:00:00Z",
  "trigger": "schedule",
  "attempt": 1
}
```

插件必须按 `invocation_id` 去重，在 10 秒内把工作放入自己的队列，并返回 `{"status":"accepted"}` 或 `{"status":"skipped"}`。投递语义为至少一次；宿主重试时保持相同 invocation ID。未在 manifest `jobs[]` 中声明的 job 一律拒绝。

`default_schedule` 使用 DIAN115 cron v1：恰好五段，依次为分、时、日、月、周，只允许数字、`*`、列表、升序范围和步长，不支持秒、年份或英文名称；星期范围是 `0..6`，`0` 表示星期日。日和星期至少一项必须为 `*`，安装器会拒绝降序范围、越界值、零步长和两项同时限定。时区使用安装实例时区；DST 中不存在的本地时刻跳过，重复时刻只执行一次，系统停机错过的执行也采用 `skip`。宿主可应用对所有插件一致的最短周期和并发上限。

### 12.5 管理端绑定与联调

安装完成后，管理员在插件中心的“运行时”面板完成以下流程：

1. 从安装 operation 的一次性结果中保存 `client_id`、`client_secret` 和 `webhook_secret`，将它们配置到独立插件服务；宿主只保存 client secret 哈希和加密 webhook secret。
2. 调用 `PUT /api/plugin-center/v1/installations/{installation_id}/runtime`（或兼容的 `POST .../runtime/bind`）提交 `{"base_url":"https://plugin.example.com"}`。留空可解除绑定。
3. 调用 `POST .../runtime/health-check`。只有返回 `health.status=ok` 且协议/版本符合 manifest，才应把服务标记为可用。
4. 用 `GET .../runtime/ui` 读取已校验的 UI Schema、事件主题和 job 声明；用 `GET .../runtime/state?view=main` 加载状态，并保存响应的强 ETag。下一次请求带 `If-None-Match`，收到 `304` 时保留本地状态。
5. UI action、手动 job 和事件联调分别使用 `/runtime/actions/{action}`、`/runtime/jobs/{job}/trigger` 和 `/runtime/events`。宿主为缺省 invocation/event ID 生成安装作用域的 opaque ID；重试时必须复用同一 ID。
6. 需要第三方 API 凭据时，在“托管凭据”页创建 `secret binding`。插件只在自己的网络请求中提交 `credential_ref`，不能提交秘密明文或动态注入规则。

运行时管理端点使用管理员认证，插件服务不能调用这些 `/api/plugin-center/v1` 路由。插件服务收到宿主回调后，仍使用自己的短期 Plugin API token 调用 `/plugin-api/v1`；不要把管理员 Cookie、client secret 或 webhook secret 放入回调 body。

## 13. 插件配置与秘密

普通配置可由插件 KV 保存。第三方 API Key、用户名密码等应由可信的 `secret-ref` 表单控件保存为宿主凭据；插件只收到 opaque 引用：

```json
{
  "credential_ref": "cred_01KRULES..."
}
```

调用网络 Broker 时可把该值放在 `credential_ref` 字段。header/query/body 位置和模板由可信 credential binding 固定配置，`secrets.use` 只声明插件会使用托管秘密；插件不能动态提供注入规则，也不能引用其他安装实例的凭据。网络响应、错误和调试日志不会包含注入后的值。

管理员创建 binding 的管理请求示例（秘密只通过 HTTPS 发送一次）：

```http
POST /api/plugin-center/v1/installations/42/secret-bindings
Authorization: Bearer <admin-token>
Content-Type: application/json

{
  "label": "规则服务 API Key",
  "host": "rules.example.com",
  "method": "GET",
  "path_prefix": "/v1/",
  "location": "header",
  "name": "x-api-key",
  "secret": "replace-with-user-secret"
}
```

响应只返回 `credential_ref`、host、method、path prefix、注入位置和字段名，不返回 `secret`。删除使用 `DELETE /api/plugin-center/v1/installations/{installation_id}/secret-bindings/{credential_ref}`；不能跨安装实例复用引用。

## 14. 打包与签名

目标 CLI 命令如下，当前尚未实现：

```bash
dian115-plugin init
dian115-plugin lint
dian115-plugin dev
dian115-plugin pack
dian115-plugin sign --key developer.key
dian115-plugin verify plugin.d115p
```

预期流程：

1. `lint` 校验 manifest、UI Schema、能力/账号依赖和 runtime 入口。
2. `pack` 按 UTF-8 NFC path 的字节序生成 `integrity.json`，列出除 `integrity.json`/`signature.json` 外全部 ZIP 成员的原始字节数和小写 SHA-256，并拒绝未声明文件和不安全路径。
3. `sign` 使用开发者 Ed25519 私钥签署 manifest 与 integrity。
4. `verify` 在本地执行与宿主相同的解包、摘要、签名和兼容性校验。

私钥不能放入插件包、代码仓库或 CI artifact。市场发布应使用 CI secret 或独立签名机。

`signature.json` 使用无 padding base64url。`key_id` 为 `ed25519:` + `base64url(SHA-256(raw_public_key))`，必须同时匹配 signature 与 manifest。示例目录中的签名使用 RFC 8032 的公开测试 seed `9d61...7f60`，仅供测试验证，绝不能作为真实发布密钥；当前签名原文 SHA-256 为 `2f2175de1d5dfd7a99466d980bec66da918cbb8355e4c9f0a83ca21d1862ee11`。

## 15. 发布到插件市场

官方市场读取 [`madbrolab/dian115`](https://github.com/madbrolab/dian115) 仓库的 `plugin-market/index.json`。自定义 GitHub 仓库采用相同目录：

```text
plugin-market/
  index.json
  index.json.sig          官方源建议，detached signature
releases/
  my-plugin-1.0.0.d115p   也可以使用 GitHub Release 的 HTTPS asset
```

最小索引：

```json
{
  "schema_version": 1,
  "repository": {
    "id": "com.example.plugins",
    "name": "Example DIAN115 Plugins",
    "homepage": "https://github.com/example/dian115-plugins"
  },
  "generated_at": "2026-08-17T00:00:00Z",
  "plugins": [
    {
      "id": "dev.example.remote-auto-transfer",
      "name": "Remote Auto Transfer",
      "version": "1.0.0",
      "description": "从规则服务创建 115 转存任务。",
      "author": "Example Studio",
      "package_url": "https://github.com/example/dian115-plugins/releases/download/v1.0.0/remote-auto-transfer.d115p",
      "sha256": "<64 lowercase hex>",
      "capabilities": [
        {"capability": "network.http", "reason": "读取自动转存规则"},
        {"capability": "transfer.115.create", "reason": "创建 115 转存任务"},
        {"capability": "accounts.115.use", "reason": "选择执行 115 操作的账号"}
      ],
      "account_access": ["main", "backup_pool", "backup_select"],
      "min_dian115": "3.9.0",
      "published_at": "2026-08-17T00:00:00Z"
    }
  ]
}
```

发布检查：

1. `package_url` 使用公开 HTTPS，构建产物不可在发布后原地替换；新内容发布新版本。
2. `sha256` 是完整 `.d115p` 下载字节的摘要，不是 `manifest.json` 或 `integrity.json` 的摘要。
3. 索引中的每项 capability 必须是包含 `capability` 和 1-240 字符 `reason` 的对象；不接受字符串简写或 required/optional 分组。
4. 索引中的 `id/version/capabilities/reasons/account_access` 必须与包内 manifest 完全一致。
5. 任一 `files.cloud.*` 或 `transfer.115.*` 必须同时列出 `accounts.115.use` 和非空 `account_access`；市场校验和安装器都会拒绝不一致条目。
6. 当前安装器强制验证 HTTPS 下载、完整包 SHA-256、ZIP 安全性、manifest/integrity 完整覆盖、RFC 8785 JCS、Ed25519 signature、publisher key 一致性，以及 runtime/UI/event/job/cron 与 capability 声明；发布者信任根、TOFU/吊销和兼容范围求值仍未作为稳定能力提供。包签名通过只证明内容由包内公钥签署，不等同于该发布者已被宿主信任。
7. GitHub 仓库主页固定解析 `main/plugin-market/index.json`；非 `main` 分支应让用户直接添加对应的 HTTPS Raw `index.json` 地址。正式发布建议用 CI 原子更新索引。

本地测试自定义源时，可在插件中心添加 GitHub 仓库首页或直接 HTTPS index URL，调用 `POST /api/plugin-center/v1/repositories/{id}/refresh`，然后从 catalog 安装。catalog 每项返回当前 `consent_digest`；`POST /api/plugin-center/v1/installations` 必须同时发送该摘要和 `permissions_accepted: true`，仓库刷新导致摘要变化时服务端返回 `409`。刷新和安装响应包含 `{ "operation": { "id": "..." } }`；客户端轮询 `/api/plugin-center/v1/operations/{id}` 的 `queued/running/succeeded/failed` 状态。当前不支持 operation 取消或重启续跑；服务重启会把未完成的仓库刷新/安装 operation 标记为 `failed`。发布者信任根/TOFU/吊销、安装 operation 中断续跑和 management idempotency 是后续增强。

```json
{
  "repository_id": 2,
  "plugin_id": "dev.example.remote-auto-transfer",
  "version": "1.0.0",
  "permissions_accepted": true,
  "consent_digest": "<catalog 返回的 64 位小写十六进制摘要>",
  "enable": true
}
```

`consent_digest` 是服务端生成的不透明快照值，管理客户端必须原样回传，不要自行拼字段重算。收到 `409` 时丢弃旧摘要，重新读取 catalog 并让用户查看新的完整披露。

## 16. 版本升级与数据迁移

- 插件版本使用 SemVer。
- 配置与 KV migration 必须可重复执行，并记录最后成功版本。
- 升级前不要执行不可逆外部副作用。
- migration 失败应返回错误，让宿主回滚代码与 KV 快照。
- 新增 capability、扩大 `account_access` 或改变 reason 会触发新的整体确认；建议提高插件主版本并在发行说明中说明。
- 不要依赖 UI Schema 未声明字段、错误文本或内部 provider ID。

## 17. 必须处理的错误码

| code | 含义 | 建议处理 |
|---|---|---|
| `invalid_request` | 请求格式错误 | 修复插件，不重试 |
| `unauthorized` | token 无效 | 检查配置 |
| `token_expired` | 短期 token 过期 | 换票后重试一次 |
| `token_stale` | capability revision 已变化或安装实例已撤销 | 重新换票；禁用/更新待确认时停止调用 |
| `capability_denied` | manifest 未声明该能力类别或账号模式 | 修正 manifest/selector，不重试 |
| `idempotency_key_required` | 写调用缺少幂等键 | 使用同一逻辑操作的稳定 key 后重试 |
| `idempotency_conflict` | key 被不同请求占用 | 生成新的逻辑操作或修复状态机 |
| `rate_limited` | 超出系统级速率上限 | 按 `Retry-After` 延迟 |
| `quota_exceeded` | 超出系统级存储或流量上限 | 等待容量恢复或提示用户 |
| `credential_reflected` | 上游响应包含宿主可识别的凭据明文 | 不重试，检查绑定的 method/path 与上游行为 |
| `resource_not_found` | 目标、文件或任务不存在 | 刷新宿主资源引用 |
| `conflict` | 订阅冲突、文件 ETag 冲突等 | 读取最新状态后决策 |
| `precondition_failed` | `If-Match` revision 已过期 | 重新读取 ETag 并让业务决定是否重试 |
| `preview_expired` | 分享 preview 已过期 | 用原分享 URL 重新预览并重新选择 item ref |
| `range_not_satisfiable` | 文件 Range 无效或越界 | 修正 Range，不要原样重试 |
| `upstream_unavailable` | 115、代理或外部服务不可用 | 有界退避重试 |
| `submission_uncertain` | 非幂等请求结果无法确认 | job 进入 `attention_required`，禁止自动重建，要求人工核对 |
| `account_context_mismatch` | 组合了不同 115 账号绑定的 selection/target/preview/item/ref | 重新从同一 `account_selection_ref` 获取全部引用 |
| `account_selection_expired` | 短时账号选择已过期 | 重新创建选择；不要改变已提交 job 的账号 |
| `account_unavailable` | 主账号或备用号池当前没有可用账号 | 提示用户检查账号状态，之后再创建新选择 |
| `internal_error` | 宿主内部错误 | 使用同一幂等键有限重试并保留 request ID |

## 18. 开发与测试检查表

- 只声明实际会调用的能力，并为每项提供用户能理解的具体 reason。
- 所有写调用使用稳定幂等键。
- 事件按 `event_id` 去重，handler 可重复执行。
- `429/5xx` 使用有上限的指数退避和 jitter。
- 不把 token、secret、分享码、接收码、离线链接或用户文件内容写入日志。
- 不在本地缓存宿主绝对路径、CID、Cookie、display path 或内部数据库 ID；业务操作只使用 opaque ref。
- 正确处理 token 撤销、插件禁用、宿主重启和 job `attention_required`。
- 外部服务验证 webhook 时间戳、HMAC 和重放。
- 文件重命名使用 revision 条件；v1 不假设内容写入或删除能力存在。
- 升级 migration 可重复、可失败回滚。
- UI 文本适合移动端，不依赖自定义 JavaScript。

完整测试包样例位于 [`examples/remote-auto-transfer`](examples/remote-auto-transfer)：包含 manifest、UI、integrity 和 Ed25519 signature；签名只使用公开测试密钥。
