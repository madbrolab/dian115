# DIAN115 用户插件平台总体方案

> 状态：Plugin API v1 目标契约。当前实现阶段先落地插件市场仓库、目录/安装管理、安装时能力确认和 115 账号解析基础；WASM/远程插件运行时以及网络、文件、转存、订阅 Host Broker 仍是后续阶段，不能据本文假定它们已在产品中全部启用。

## 1. 背景与现状

当前插件中心展示的是静态清单，插件页面和后端路由都在编译时注册：

- 前端清单位于 [`PluginCenter.vue`](../../frontend/src/views/PluginCenter.vue)，页面路由位于 [`router/index.ts`](../../frontend/src/router/index.ts)。
- 后端插件接口直接挂载在 [`internal/api/router.go`](../../internal/api/router.go) 的 `/api/plugins/*` 下，共享管理员认证和主进程服务对象。
- SPA 会嵌入 Go 二进制，第三方 Vue 模块不能在运行时安全地注册。
- 当前已实现第三方市场索引、仓库刷新、包下载、SHA-256/manifest 一致性校验、安全解压、安装记录、一次性能力确认和 115 账号解析基础；尚未实现包内签名信任、独立插件身份、第三方运行时、Host Broker、原子升级或回滚。

因此，用户插件不能沿用内置插件的做法直接注册 Gin 路由、访问 Store、链接 Go 代码或在同源页面中执行任意 JavaScript。Plugin API v1 必须把第三方代码与管理员会话、数据库、115 Cookie、CD2 Token、Emby Key 和系统文件隔离开。

## 2. 目标与非目标

### 2.1 目标

1. 用户可从本地 `.d115p` 文件、仓库 URL 或插件市场安装、更新、禁用和卸载插件。
2. 开发者可用受控 WASM 或独立 HTTP 服务开发插件。
3. 安装或更新时一次性展示插件声明的全部能力和 115 账号访问模式，用户只能整体同意或取消。
4. 首批开放网络、系统代理、115 转存/离线、文件管理和订阅管理能力。
5. 每次调用可审计、可限流、可撤销；运行时只允许调用 manifest 已声明的能力类别，不做逐操作审批。
6. 插件升级失败可回滚；新增能力类别或账号访问模式必须在更新前重新整体确认。
7. Plugin API v1 在实现层变化时仍保持稳定的开发者契约。

### 2.2 非目标

- 不支持 Go `plugin.so`、DLL、ELF、任意安装脚本或直接在主容器运行 Node/Python。
- 不允许插件访问内部 `/api/*` 管理员接口、SQLite、Docker Socket、宿主环境变量或任意本地路径。
- 不把系统全局 OpenAPI Key、管理员 JWT、账号 Cookie 或代理凭据交给插件。
- v1 不允许插件把任意 Vue/React/HTML 代码注入 DIAN115 同源页面。
- 插件 API 不承诺复刻内部 Store、Service 或数据表结构。

## 3. 核心设计原则

1. **能力披露**：manifest 声明插件会使用的能力类别及原因，安装页逐项说明风险，用户对整份声明一次性同意。
2. **类别校验**：运行时只判断调用所属能力类别是否已在当前已确认的 manifest 中声明；v1 不提供 host、root、quota、每日次数或逐操作授权。
3. **凭据托管**：插件只持有引用或短期令牌，真实凭据由宿主在代理请求时注入。
4. **业务接口优先**：开放“创建转存任务”“创建订阅”等高层能力，不开放底层 115 客户端或数据库。
5. **异步写入**：可能耗时或非幂等的操作进入宿主任务中心，返回 opaque `job_ref`，并支持状态查询和事件通知。
6. **可撤销**：禁用插件必须立即停止调度、撤销令牌、终止运行实例并停止事件投递。
7. **可解释**：安装页必须展示能力原因、网络/文件/订阅风险、后台执行、秘密使用，以及主账号、备用号池、指定备用账号的访问差异。

## 4. 总体架构

```mermaid
flowchart LR
    U["管理员 / 插件中心"] --> PC["Plugin Center API"]
    PC --> I["Installer + Signature Verifier"]
    PC --> R["Plugin Registry"]
    R --> DB["dian115_plugins.db"]
    I --> PKG["/config/plugins/<plugin-id>/<version>"]

    subgraph Runtime["隔离运行时"]
      W["WASM / WASI Runtime"]
      H["External HTTP Plugin"]
    end

    W --> B["Capability Broker"]
    H --> G["Plugin API Gateway"]
    G --> B

    B --> N["Network Broker"]
    B --> F["File Broker"]
    B --> T["Transfer Broker"]
    B --> S["Subscription Facade"]
    B --> E["Events / Scheduler / KV"]

    N --> SYS["现有代理与 HTTP 客户端"]
    F --> FS["本地文件 / CD2"]
    T --> D115["115 高层转存与离线流程"]
    S --> SUB["PT / 聚合订阅引擎"]
```

建议新增后端模块：

```text
internal/plugin/
  manifest/       清单、兼容性与 JSON Schema 校验
  package/        解包、完整性、签名、原子安装与回滚
  registry/       安装实例、版本、状态、发布者与更新源
  permission/     能力目录、安装确认快照与运行时类别校验
  identity/       插件实例身份、短期令牌与撤销
  runtime/        WASM 监督器和外部服务连接器
  broker/         网络、文件、转存、订阅等能力代理
  task/           异步任务、幂等记录和结果保留
  event/          事件订阅、游标、重试和死信
  audit/          脱敏审计日志
```

管理端路由与运行时路由必须分开：

```text
/api/plugin-center/v1/*  管理员使用：市场仓库、安装、升级、日志和异步 operation
/plugin-api/v1/*         外部插件使用：仅限已声明且已整体确认的能力类别
```

`/plugin-api/v1` 必须使用独立 Gin group 和中间件，只接受插件短期令牌或 WASM 宿主身份。管理员 JWT、HttpOnly Cookie、全局 OpenAPI Key、AI 工具调用器和全局 CORS 都不能成为该路由的认证或回退路径。

## 5. 双运行时模型

### 5.1 WASM 插件

WASM 是本地安装插件的首选运行时。建议使用纯 Go 的 `wazero`，不依赖系统动态库。

运行边界：

- 每个插件实例拥有独立 runtime、线性内存、调用队列和取消上下文。
- 默认不挂载目录，不开放 Socket、环境变量、系统时钟精度、随机宿主文件、进程启动或数据库。
- 插件只导入版本化 `dian115:host@1` ABI，SDK 将其封装为类型化能力调用。
- 交互调用默认 10 秒；后台任务默认 5 分钟；超时后关闭当前模块实例。
- 默认最大内存 32 MiB，硬上限 64 MiB；默认并发 1，硬上限 2。
- 连续崩溃、越限或健康检查失败后自动隔离，管理员手动恢复。

主程序当前默认只有 256 MiB Go 软内存上限，见 [`cmd/main.go`](../../cmd/main.go)，因此必须限制插件内存、并发和缓存。

适用语言：Rust、TinyGo、AssemblyScript，以及任何能输出兼容 WASI/WASM Component 的语言。

### 5.2 外部 HTTP 插件

Node.js、Python、Java 或需要原生依赖的插件由用户独立部署，DIAN115 只安装其签名清单并绑定服务地址。

- 服务地址由管理员在安装时填写，不能由安装包静默指定。
- 每个安装实例使用独立 client secret 换取 15 分钟短期访问令牌。
- 宿主向插件投递事件和 UI action 时使用独立 webhook secret 签名。
- manifest 为 health、event、action、state 和 scheduled job 声明互不相同的固定 callback path；UI 初始状态和调度 handler 因此不依赖未声明路由。
- 插件服务不可获得管理员 Cookie、全局 OpenAPI Key 或其他插件的令牌。
- 服务地址变更、证书指纹变更或从公网切换到局域网必须重新确认。
- 生产环境默认只允许 HTTPS；明文 HTTP 仅限 loopback 开发模式，并持续显示风险状态。
- 宿主连接远程插件时不跟随重定向，限制响应体和超时，并按系统网络安全策略校验解析后的目标 IP 和固定拨号。

外部服务插件与 WASM 插件使用同一份能力、错误码、幂等和审计语义。

## 6. 插件包格式

扩展名为 `.d115p`，底层是 ZIP：

```text
manifest.json              必需，插件元数据与权限声明
integrity.json             必需，载荷文件 SHA-256 清单
signature.json             正式安装必需，Ed25519 签名
plugin.wasm                runtime.kind=wasm 时必需
ui/schema.json             可选，声明式 UI
assets/*                   可选，图标和静态资源
README.md                  建议，面向管理员的说明
```

三个元文件分别由 [`manifest.schema.json`](manifest.schema.json)、[`integrity.schema.json`](integrity.schema.json) 和 [`signature.schema.json`](signature.schema.json) 定义；UI 由 [`ui-schema-v1.schema.json`](ui-schema-v1.schema.json) 定义。

安装限制建议：

| 项目 | 默认值 | 硬上限 |
|---|---:|---:|
| 压缩包大小 | 16 MiB | 32 MiB |
| 解压后总量 | 64 MiB | 128 MiB |
| 文件数量 | 256 | 1024 |
| 单个非 WASM 文件 | 8 MiB | 32 MiB |
| `plugin.wasm` | 8 MiB | 16 MiB |
| 清单大小 | 64 KiB | 256 KiB |

安装器必须拒绝：

- 绝对路径、驱动器前缀、反斜杠、`..`、NUL、重复路径和 Unicode NFC/case-fold 碰撞。
- Windows DOS 设备名（`CON/PRN/AUX/NUL/COM1..9/LPT1..9`）、ADS `:`、尾随点或空格，以及规范化后发生变化的成员名。
- 符号链接、硬链接、设备文件和未列入 `integrity.json` 的额外文件。
- 压缩炸弹、超量文件、声明大小溢出或解压后摘要不一致。
- 未声明的 WASM imports、超出内存上限的模块和不兼容 ABI。

仓库现有 ZIP 路径和符号链接校验可参考 [`internal/service/portable_strm.go`](../../internal/service/portable_strm.go)。

### 6.1 签名

正式包使用 Ed25519。签名输入必须严格定义为以下字节序列；其中 `\0` 表示单个 NUL 字节，不是反斜杠和数字零两个字符：

```text
DIAN115-PLUGIN-PACKAGE-V1\0
JCS(manifest.json)\0
JCS(integrity.json)
```

其中 JCS 使用 RFC 8785 JSON Canonicalization Scheme。`integrity.json` 规则为：

- path 先转为 UTF-8 NFC，分隔符固定 `/`，再按 UTF-8 字节序升序排列；重复、case-fold 冲突和排序错误均拒绝。
- `sha256` 是原始文件字节的小写 64 位十六进制摘要，`size` 是解压后字节数。
- 列出 `manifest.json`、运行时、UI、assets 和 README 等全部载荷，但不包含 `integrity.json` 自身或 `signature.json`。
- ZIP 中除这两个元文件外的成员必须与 files 数组完全一致，既不能缺失，也不能多出未签名文件。

`signature.json.public_key` 是原始 32 字节 Ed25519 公钥的无 padding base64url，`signature` 是 64 字节签名的无 padding base64url。`key_id` 必须等于 `ed25519:` + `base64url(SHA-256(raw_public_key))`，并与 `manifest.publisher.key_id` 完全一致。

信任策略：

- 官方市场：由内置市场根密钥或其签发的发布者证书验证。
- 社区插件：首次安装展示发布者指纹，用户确认后采用 TOFU；密钥变化视为新发布者。
- 本地开发：CLI 生成开发者密钥并签名。
- 无签名包：只允许显式开启开发模式后临时安装，禁止自动更新，并持续显示风险状态。

签名与域分隔实现可参考 [`internal/runtimepayload/payload.go`](../../internal/runtimepayload/payload.go)，但插件必须使用独立密钥域和信任库。

## 7. 清单与兼容性

清单完整 Schema 位于 [`manifest.schema.json`](manifest.schema.json)。核心示例：

```json
{
  "schema_version": 1,
  "id": "dev.example.auto-transfer",
  "name": "自动转存助手",
  "version": "1.0.0",
  "description": "根据外部规则创建受控转存任务。",
  "default_locale": "zh-CN",
  "publisher": {
    "name": "Example Studio",
    "key_id": "ed25519:QmFzZTY0VXJsS2V5RmluZ2VycHJpbnQ"
  },
  "compatibility": {
    "dian115": ">=3.9.0 <4.0.0",
    "plugin_api": "^1.0"
  },
  "runtime": {
    "kind": "wasm",
    "entry": "plugin.wasm",
    "abi": "dian115:plugin@1",
    "memory_mb": 32,
    "timeout_ms": 10000
  },
  "ui": {
    "schema": "ui/schema.json"
  },
  "permissions": {
    "capabilities": [
      {
        "capability": "network.http",
        "reason": "读取规则服务"
      },
      {
        "capability": "transfer.115.create",
        "reason": "创建 115 转存任务"
      },
      {
        "capability": "accounts.115.use",
        "reason": "让用户选择执行 115 操作的账号"
      }
    ],
    "account_access": ["main", "backup_pool", "backup_select"]
  }
}
```

兼容策略：

- `schema_version` 管安装包格式，只允许宿主明确支持的整数版本。
- `plugin_api` 管能力 HTTP/ABI 契约，遵循 SemVer。
- v1 次版本只添加可选字段、端点或枚举；不改变既有字段语义。
- 废弃能力至少保留 180 天或两个 DIAN115 次版本，取更长者。
- 插件不能依赖内部数据库、内部 `/api` 路由或未文档化响应字段。

## 8. 权限模型

v1 使用“安装时披露、一次性整体同意、运行时按类别校验”的模型：

```text
manifest capabilities + reason + optional account_access
```

- `capability`：插件会调用的系统能力类别。
- `reason`：安装页直接展示给用户的用途说明。
- `account_access`：声明 `accounts.115.use` 时必填，列出 `main`、`backup_pool`、`backup_select` 中会使用的模式。
- `capability_revision`：安装或更新后递增，用于让旧 token 和旧 WASM invocation 立即失效；它不是细粒度授权版本。

用户不能只勾选一部分能力。拒绝任一项就不安装/不更新；同意后插件可在其声明类别内调用相应 Host API，不再弹出 host、目录、额度或逐操作确认。平台仍执行所有插件一致的接口级安全规则，例如 SSRF 阻断、opaque ref、幂等、包大小、响应上限、并发上限和敏感信息脱敏；这些是系统边界，不是用户逐项授权。

### 8.1 v1 能力目录

| 能力 | 安装提示重点 |
|---|---|
| `network.http` | 可连接外部 HTTPS 服务并发送插件提供的数据 |
| `network.proxy` | 可要求请求走系统代理，但看不到代理地址和凭据 |
| `files.local.read` / `files.local.write` | 可读取或修改 Host API 暴露的本地文件根 |
| `files.cloud.read` / `files.cloud.write` | 可读取或修改 Host API 暴露的云端文件根 |
| `transfer.115.read` / `create` / `cancel` | 可读取、创建或取消 115 转存/离线任务 |
| `accounts.115.use` | 可按 `account_access` 使用主账号、备用号池或指定备用账号 |
| `subscriptions.read` / `create` / `update` / `cancel` | 可读取或改变订阅记录 |
| `events.subscribe` | 可接收宿主事件 |
| `scheduler.register` | 可在后台定时运行 manifest 声明的 job |
| `storage.kv` | 可保存安装实例私有数据 |
| `secrets.use` | 可使用用户保存的 opaque credential ref，但不能读取秘密明文 |

Manifest v1 只允许上表能力。未知能力、重复能力、缺少 `reason`，或声明 `accounts.115.use` 却没有 `account_access` 时直接拒绝安装。`events` 仍要求声明 `events.subscribe`，`jobs` 仍要求声明 `scheduler.register`；这里只做类别一致性校验，不再把 topic/job ID 变成授权范围。

### 8.2 安装与更新确认

1. 当前 catalog 快照展示完整能力列表及每项 `reason`；下载后的独立 staging、包 SHA-256、manifest 一致性和 ZIP 静态安全检查由当前安装器执行。
2. `account_access` 分别显示为“主账号”“从备用号池自动选择”“查看并指定一个备用账号”。
3. catalog 为当前仓库快照生成 `consent_digest`；用户勾选一次“我理解并同意该插件使用以上全部能力”后，管理 API 必须同时提交 `permissions_accepted: true` 和该摘要。
4. 当前摘要覆盖仓库 ID、插件 ID/名称/版本/作者、包 URL/SHA-256、capabilities、reasons 和 account_access；仓库刷新后任一内容变化都会让旧摘要失效并返回 `409`。
5. 后续签名链会把发布者 key、runtime 和更完整的静态检查结果也纳入确认快照；任一披露变化都必须重新整体确认。

运行时与 Host Broker 接入后，对未声明类别返回 `403 capability_denied`。设计中不存在 `approval_required`、`awaiting_approval` 或供插件触发的审批接口；业务 API 通过类别校验和通用输入校验后，同步执行或创建 `queued` operation/job。

## 9. 插件身份与凭据

### 9.1 WASM

WASM 调用由宿主直接绑定 `installation_id`，插件看不到访问令牌。每次 host call 自动附带：

- `plugin_id`
- `installation_id`
- `package_version`
- `capability_revision`
- `invocation_id`

### 9.2 外部服务

安装后生成：

- `client_id`：可公开的安装实例标识。
- `client_secret`：只展示一次，服务端只保存哈希。
- `webhook_secret`：只用于验证宿主投递事件，不与 client secret 复用。

外部插件通过 `/plugin-api/v1/auth/token` 换取短期 JWT：

```json
{
  "client_id": "pli_01K...",
  "client_secret": "d115ps_0123456789abcdef0123456789"
}
```

令牌必须包含独立 audience、安装实例、能力确认修订号和短过期时间。禁用、卸载、安装新版本或手动撤销后立即失效。

第三方凭据由可信配置界面保存为安装实例专属的 opaque `credential_ref`。插件声明 `secrets.use` 后可在网络请求中引用它；网络 Broker 只按该 credential binding 的固定注入规则加入 header、query 或 body，插件不能动态指定注入规则。宿主生成的响应元数据、日志和审计不记录明文，并对响应中的精确秘密字节做阻断，但通用 HTTP 上游仍可能对秘密变换后回显。因此安装页必须把 `secrets.use` 标为高风险：若要求插件在任何情况下都不能观察凭据，应实现固定请求/固定响应的专用 Connector，而不是使用通用 Network Broker。

## 10. 开放接口设计

正式契约位于 [`openapi-v1.yaml`](openapi-v1.yaml)。所有业务写接口必须带 `Idempotency-Key`。普通结果默认保留 24 小时；进入 `submission_uncertain` 的记录必须固定保留到人工对账完成，之后才恢复常规保留策略。

### 10.1 网络连接与代理调用

入口：`POST /plugin-api/v1/network/requests`

规则：

- URL 必须使用小写 `https` scheme，不允许 userinfo 或 fragment。v1 不在 manifest 中限制 host/method/port，但所有插件统一受 SSRF、安全网段、响应大小、超时和系统级限流策略约束。
- `proxy_mode` 只允许 `system`、`direct`、`required`。插件不能传入代理 URL 或读取代理密码；使用 `system/required` 必须声明 `network.proxy`，`direct` 仍可被管理员的全局网络策略拒绝。
- 需要第三方凭据时，请求只能携带本安装实例的 opaque `credential_ref`，并声明 `secrets.use`；credential binding 的注入位置由可信宿主配置管理，不属于 manifest 权限。
- 响应中的 `final_url` 只能返回脱敏 URL；`Location`、`Set-Cookie` 等敏感 header 会被移除，检测到精确凭据字节被上游回显时整次调用失败而不是把内容交给插件。
- 管理员可强制插件使用系统代理并拒绝 `direct`。
- 插件提交的 header 名必须使用小写 ASCII token；禁止 `host`、`cookie`、`authorization`、`proxy-authorization`、连接级 header，以及 `transfer-encoding`、`content-length` 等报文分帧 header。托管凭据只能由宿主注入。
- DNS 解析后拒绝 loopback、私网、CGNAT、链路本地、多播、未指定地址、云元数据和其他 special-use 网段。
- 每次重定向重新校验 scheme、目标 IP 和系统网络策略，并用自定义 `DialContext` 固定到已验证 IP，TLS `ServerName` 仍使用原主机名，防止 DNS rebinding。
- 若系统代理在远端重新解析 DNS，且无法提供等价的私网阻断保证，则该代理不能承载插件流量。
- 响应体默认 256 KiB，硬上限 2 MiB；默认超时 10 秒，硬上限 30 秒。

可参考现有代理选择思想 [`internal/util/http_client.go`](../../internal/util/http_client.go) 和外部 URL 校验逻辑 [`internal/api/chat_ai_web_memory_tools.go`](../../internal/api/chat_ai_web_memory_tools.go)，但不能直接复用当前 transport：校验 DNS 与实际拨号仍可能二次解析，且 `GetProxyURL()` 可能含代理凭据。

### 10.2 115 账号选择

声明任一 `files.cloud.*` 或 `transfer.115.*` 时必须同时声明 `accounts.115.use`，且 `permissions.account_access` 非空。Host API 使用统一 selector：

```json
{"mode":"main"}
{"mode":"backup_pool"}
{"mode":"backup_ref","account_ref":"a115_01K..."}
```

- `main` 需要 `account_access` 包含 `main`，使用当前激活的主账号。
- `backup_pool` 需要包含 `backup_pool`，由宿主通过原子轮询从启用且有效的备用号池选择账号。
- `backup_ref` 需要包含 `backup_select`，`account_ref` 必须来自本安装实例的账号列表，是不含数据库 ID 的 opaque 引用。
- 插件先调用 `POST /plugin-api/v1/accounts/115/selections`，获得短时 `account_selection_ref`；后续 115 目录、目标、分享预览、离线列表和提交操作都使用该引用。
- `account_selection_ref`、`target_ref`、`preview_ref`、`item_ref`、115 目录 `root_id/entry_ref` 和 job 都绑定同一个实际账号。混用返回 `409 account_context_mismatch`，宿主绝不通过猜测或自动换号修复。
- 插件永远拿不到 Cookie、设备凭据、真实备用账号表 ID 或原始 CID。账号失效时返回稳定错误；非幂等请求结果不确定后禁止切换账号重试。

### 10.3 转存与离线接口

入口：

```text
GET  /plugin-api/v1/transfers/115/targets
GET  /plugin-api/v1/accounts/115
POST /plugin-api/v1/accounts/115/selections
POST /plugin-api/v1/transfers/115/share-previews
GET  /plugin-api/v1/transfers/115/share-previews/{preview_ref}/items
POST /plugin-api/v1/transfers/115/share-receives
POST /plugin-api/v1/transfers/115/offline-downloads
GET  /plugin-api/v1/transfers/115/offline-tasks
GET  /plugin-api/v1/transfers/115/offline-quota
GET  /plugin-api/v1/jobs/{job_ref}
POST /plugin-api/v1/jobs/{job_ref}/cancel
```

设计要求：

- 插件使用宿主提供的 opaque `target_ref`，不直接读取 115 CID、账号 ID 或 Cookie，且根 CID `0` 不能成为插件目标。
- 所有目标、预览、离线任务和提交结果都携带或隐式绑定 `account_selection_ref`；创建任务时相关引用必须属于同一账号。
- 分享链接先创建短时 `preview_ref`，再从预览结果选择 opaque `item_ref`。创建转存时不再接受 raw `share_code`，也不允许空选择或 `file_id=0` 隐式扩大为整分享。
- 预览必须把分享 URL 限定为 115 官方 host；当前通用解析器允许任意 URL host，不能直接作为插件安全边界。
- 账号 Cookie、设备信息和 CD2 Token由宿主管理。
- 每个副作用发生前，必须在同一事务持久化 `plugin_job + idempotency + outbox`，再进行一次 transport attempt。
- 分享使用显式正整数文件 ID 的 `ShareReceiveOnce`，离线使用 `OfflineAddURLsOnce`；不能直接复用会整分享或自动重试 POST 的现有桥接调用。
- 公共 job 状态包含 `queued/running/succeeded/partial/failed/cancelled/attention_required`，不会进入逐操作审批状态。
- 网络中断后无法判断非幂等 115 请求是否已提交时进入终态 `attention_required`，错误码为 `submission_uncertain`，该幂等键在人工对账前不能过期或再次提交。
- 离线单次最多 50 个 URL；未来若批量拆分，每个 child batch 单独记录成功、失败或不确定，绝不重投不确定批次。
- cancel 只能停止排队或仍在宿主管理中的工作，不能撤销 115 已接受的请求。
- 分享码、接收码和离线链接在日志、通知、错误与审计中按敏感字段脱敏。
- 每个任务绑定创建它的插件实例；默认不能查询或取消其他实例的任务。

现有默认目录解析、通知和账号选择逻辑可抽入 `TransferService`，但不能直接调用 [`internal/api/bridge.go`](../../internal/api/bridge.go) 的整分享/重试流程。认证前可证明未提交的失败才允许故障切换；任何不确定提交都禁止换账号重试。

### 10.4 文件管理接口

入口：

```text
GET   /plugin-api/v1/files/roots
GET   /plugin-api/v1/files/entries
GET   /plugin-api/v1/files/entries/{entry_ref}
GET   /plugin-api/v1/files/entries/{entry_ref}/content
POST  /plugin-api/v1/files/directories
PATCH /plugin-api/v1/files/entries/{entry_ref}
POST  /plugin-api/v1/files/operations
```

关键约束：

- 插件操作已存在对象时只提交 opaque `entry_ref`，列举响应可返回 `display_path` 供界面展示，但它不能作为后续授权依据。
- `files.local.*` 可发现系统配置允许暴露的本地虚拟根，`files.cloud.*` 可发现所选账号下 Host API 暴露的云端根；不再为每个插件安装实例逐根授权。
- 云端 `root_id/entry_ref` 与 `account_selection_ref` 绑定，不能跨主账号或备用账号混用。所有路径仍保持 opaque，插件不能提交宿主绝对路径或原始 CID。
- 每次真正执行时都重新解析 root、对象、最近存在祖先、符号链接和 Windows reparse point，再验证仍位于 Host API 暴露根内，防止预检后的 TOCTOU 换链。
- v1 开放 list/stat/read、mkdir、rename、同 backend copy/move；批量操作走持久化 job，支持进度和部分失败明细。
- v1 暂不开放内容写入：当前本地上传非原子且可覆盖，CD2 没有统一上传语义。完成临时文件、`fsync`、原子 rename、ETag/CAS 和配额后再扩展。
- v1 暂不开放删除：当前本地删除最终使用 `os.RemoveAll`，不是可恢复回收站。先实现宿主级 trash，再分别开放 `files.local.trash` 和 `files.cloud.trash`；永久 purge 不进入 v1。
- copy/move 默认冲突策略为 `fail`，可选 `rename`，不默认覆盖。CD2 move 必须使用显式 policy，本地 move 必须在执行时原子复核同名目标，不能直接依赖当前平台差异较大的 rename 行为。
- 本地文件和 CD2 可通过统一 root backend 暴露，但插件不接触 CD2 gRPC 凭据。

当前文件管理器的 `cleanLocalPath` 只屏蔽少量系统目录，见 [`internal/api/handlers.go`](../../internal/api/handlers.go)，不能直接复用为插件边界。路径根校验可参考 [`internal/api/chat_ai_file_tools.go`](../../internal/api/chat_ai_file_tools.go) 中“解析已存在祖先后验证根内”的实现。

### 10.5 订阅管理接口

入口：

```text
GET    /plugin-api/v1/subscription-profiles
GET    /plugin-api/v1/subscriptions
POST   /plugin-api/v1/subscriptions
GET    /plugin-api/v1/subscriptions/{subscription_ref}
PATCH  /plugin-api/v1/subscriptions/{subscription_ref}/episodes
DELETE /plugin-api/v1/subscriptions/{subscription_ref}
POST   /plugin-api/v1/subscriptions/{subscription_ref}/search
```

统一 Facade 使用稳定字段，不暴露内部表：

- `engine`: `pt` 或 `aggregate`。插件不能通过一个模糊的 `auto` 绕过不同引擎的权限和配置约束。
- 媒体身份以 `tmdb_id + media_type + season` 为主键，标题只是展示信息。
- TV 未传 `season` 时统一按 1，电影统一按 0；`total_episodes` 和展开后的集数集合硬上限为 10000。
- 创建输入不接受 title/year/poster/state/covered/baseline/terminal 字段，也不接受 raw proxy ID、下载器名、保存路径或站点 JSON；这些值由宿主 TMDB、媒体库和系统配置的 profile 解析。
- aggregate 必须调用 `PoolOrchestrator.CreateIntent`；PT 必须把现有 handler 的默认值、路径校验、冲突检查、持久化和首次搜索完整抽入 `SubscriptionFacade`。
- v1 更新只开放 aggregate TV 的集数范围，并要求 `If-Match` revision；通用 PT 更新和 `upgrade` PATCH 暂缓。
- 插件声明 `subscriptions.cancel` 后可删除 Host API 返回的订阅；当前 PT/aggregate 删除是物理删除，且不会撤销下载器或 115 已接受的工作，安装提示必须明确这一风险，接口不再逐次弹出审批。
- 对外活动状态是 `pending/searching/transferring/waiting/verifying/partial/needs_attention/failed/expired` 的并集。内部兼容 `landed/cancelled` 行必须被 Facade 过滤或迁移，完成和删除通过 job/event 表达，随后查询返回 `404`。
- 订阅完成、部分完成、失败和取消通过事件通知插件。

PT 创建逻辑当前位于 [`internal/api/pt_subscription_handlers.go`](../../internal/api/pt_subscription_handlers.go)，聚合订阅状态位于 [`internal/store/pool_intent_store.go`](../../internal/store/pool_intent_store.go)。Facade 必须调用现有业务流程，不能直接写表，也不能把兼容展示表 `subscribe_records` 当作权威状态。

## 11. 事件、调度与插件存储

### 11.1 事件

- 事件至少投递一次，插件必须按 `event_id` 去重；副作用通过 transactional outbox 发送。
- 每个订阅保存游标；失败采用指数退避，达到上限进入死信队列。
- 事件载荷按已声明能力类别裁剪，不属于该类别的字段不出现，而不是仅返回空值。
- 默认主题包括插件生命周期、转存任务、订阅状态、文件任务和系统健康。

外部插件 webhook 请求头：

```http
X-Dian115-Event-ID: evt_01K...
X-Dian115-Timestamp: 1786900000
X-Dian115-Signature: v1=<hex-hmac-sha256>
```

签名原文为 UTF-8 字节 `v1\n<timestamp>\n<METHOD>\n<path-and-query>\n<SHA256(raw_body)>`，再计算 HMAC-SHA256。这样签名同时绑定方法、目标和原始请求体。接收方应拒绝超过 5 分钟的请求、使用常量时间比较，并保存已处理事件 ID 或 invocation ID。

### 11.2 调度

- 插件只能注册清单允许的任务 ID。
- 默认最短周期 5 分钟，系统可提高下限。
- 同一任务默认禁止重入，错过执行采用 `skip`，不能无限补跑。
- `default_schedule` 使用 DIAN115 cron v1：五段数字 cron（分、时、日、月、周），支持 `*`、列表、升序范围和步长，不接受秒、年份或英文月份/星期名；星期取 `0..6`，`0` 为星期日。日和星期不能同时限定，以避免不同 cron 方言的 OR/AND 歧义。时区使用安装实例时区；DST 跳过的本地时间不补跑，重复的本地时间只执行一次。系统可应用对所有插件一致的最短周期和并发上限。
- 禁用插件立即取消未开始任务，并向运行中任务发出取消信号。

### 11.3 KV 存储

- 每个安装实例独立命名空间。
- 默认 16 MiB，单值 256 KiB。
- 支持 CAS/version，避免并发覆盖。
- 插件卸载默认保留 30 天，可由用户立即彻底删除。
- 版本升级前创建轻量快照，健康检查失败时随代码一起回滚。

## 12. 声明式 UI

v1 使用 [`ui-schema-v1.schema.json`](ui-schema-v1.schema.json) 描述页面、表单、表格、状态、任务进度和动作按钮，由 DIAN115 的受信 Vue 组件渲染。

优点：

- 不执行第三方前端 JavaScript，不共享管理员 Cookie。
- 自动继承主题、移动端布局、宿主界面国际化、能力不可用状态和命令确认提示。
- action 只调用插件运行时入口，插件仍需通过 Capability Broker 执行业务操作。

UI Schema 中的 `confirm` 只是一层普通交互提示，不会改变安装时已确认的能力集合。状态路径解析必须拒绝 `__proto__`、`prototype`、`constructor` 等保留段，并使用自有属性访问，不能把第三方 patch 直接深合并进 Vue 状态对象。

v1 section 只支持 `status`、`form`、`table`、`log`、`progress`、`actions`。`form` 内可使用 `text`、`textarea`、`number`、`switch`、`select`、`multiselect`、`secret-ref`、`file-picker`、`directory-picker` 控件，`actions` 渲染受控按钮；tabs 留到后续 Schema 版本。

v1 的插件自带标题、说明和标签都是 `default_locale` 指定语言的字面字符串；宿主导航、错误和安装确认文案仍随 DIAN115 语言切换。多语言插件资源包和稳定翻译 key 留到 UI Schema v2。v1 也不接受插件自带正则表达式；文本、数值、选项和路径控件只使用宿主提供的有界校验器。

安装器必须按作用域检查标识符唯一性：manifest job ID 全局唯一，UI view ID 全局唯一，同一 view 的 section/form/action ID 不重复，同一表单 field key、表格 column key 和选项 value 不重复。发现冲突直接拒绝安装，不能依赖 JSON 对象覆盖或渲染顺序消歧。

若未来开放自定义 HTML，必须使用独立来源和 sandbox iframe，禁止 `allow-same-origin`、顶层导航、弹窗和任意表单提交，并通过 nonce 绑定的 `postMessage` 协议通信。不能把第三方 HTML 直接挂在当前同源页面，因为管理员认证使用 HttpOnly Cookie。

## 13. 插件市场与仓库

### 13.1 官方仓库

系统首次初始化时创建不可重复的官方源：

```json
{
  "name": "DIAN115 官方市场",
  "repository_url": "https://github.com/madbrolab/dian115",
  "index_url": "https://raw.githubusercontent.com/madbrolab/dian115/main/plugin-market/index.json",
  "official": true,
  "enabled": true
}
```

`official` 由系统内置记录决定，不能由客户端提交或把自定义源升级为官方源。当前管理 API 不提供仓库启用/禁用切换，官方源保持启用且不能删除；自定义源可删除。

### 13.2 自定义仓库

用户可添加两类 HTTPS 来源：

- GitHub 仓库首页，例如 `https://github.com/example/dian115-plugins`。服务端固定规范化为 `https://raw.githubusercontent.com/example/dian115-plugins/main/plugin-market/index.json`；非 `main` 分支应直接添加对应的 HTTPS Raw `index.json` URL。
- 直接索引 URL，例如 `https://plugins.example.com/dian115/index.json`。必须是公开 HTTPS JSON；不接受 URL userinfo、fragment、重定向到非 HTTPS、宿主 Cookie 或管理员提供的任意请求 header。

仓库刷新使用专用下载器并执行 DNS/IP 固定、私网和云元数据阻断、重定向逐跳复核、大小/耗时上限、ETag/Last-Modified 条件请求。自定义仓库不因“能添加”而获得宿主网络凭据；私有仓库认证留到后续版本的专用 credential binding。

### 13.3 `plugin-market/index.json`

```json
{
  "schema_version": 1,
  "repository": {
    "id": "madbrolab.dian115",
    "name": "DIAN115 官方市场",
    "homepage": "https://github.com/madbrolab/dian115"
  },
  "generated_at": "2026-08-17T00:00:00Z",
  "plugins": [
    {
      "id": "dev.example.remote-auto-transfer",
      "name": "Remote Auto Transfer",
      "version": "1.0.0",
      "description": "从规则服务创建 115 转存任务。",
      "author": "Example Studio",
      "homepage": "https://example.com/plugins/remote-auto-transfer",
      "package_url": "https://example.com/releases/remote-auto-transfer-1.0.0.d115p",
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

索引规则：

- `repository.id` 和插件 `id` 使用小写反向域名风格；同一索引内 `id + version` 组合唯一，同一插件可列出多个 SemVer 版本。
- `package_url` 必须是绝对 HTTPS URL或相对索引最终 URL 的安全相对路径；`sha256` 先校验下载字节，再进入 ZIP/manifest 校验。包内 integrity/signature 属于后续信任阶段，市场元数据永远不能替代包内签名。
- `capabilities` 每项必须包含 `capability` 和非空 `reason`，不接受字符串简写或 required/optional 分组；它与 `account_access` 都必须和包内 manifest 完全一致，否则不能安装。
- 任一 `files.cloud.*` 或 `transfer.115.*` 都要求同时列出 `accounts.115.use` 且 `account_access` 非空；列出 `accounts.115.use` 时同样必须提供非空 `account_access`。
- 未识别字段按 `schema_version` 策略处理；未知必需能力、降级版本、重复条目、无效 SemVer 或摘要格式错误会使单个条目无效，不应让整个源缓存替换为部分解析结果。
- 刷新成功后原子替换该仓库的 catalog 快照；刷新失败保留最后一次成功快照，并显示 `stale/error` 状态和脱敏错误。

官方索引应再提供 detached signature 和内置根密钥验证；自定义仓库至少依赖每个 `.d115p` 的发布者签名并在首次安装使用 TOFU。列表页必须始终显示来源、官方/自定义状态、发布者 key、更新时间和签名状态。

### 13.4 仓库管理与异步 operation

当前 MVP 的仓库刷新和安装写操作返回 operation 对象：

```json
{
  "operation": {
    "id": "1c51a4ba-6da8-4a55-81bd-273af478514d",
    "kind": "repository_refresh",
    "status": "queued",
    "progress": 0,
    "created_at": "2026-08-17 11:00:00"
  }
}
```

客户端通过 `GET /api/plugin-center/v1/operations/{id}` 查询，也可用 `GET /api/plugin-center/v1/operations` 查看最近任务。当前状态只有 `queued/running/succeeded/failed`；成功详情可带顶层 `result`，失败 operation 的 `error` 当前是展示文本。当前 MVP 不提供 operation 取消、重启续跑或管理写请求 `Idempotency-Key`；服务重启会把未完成 operation 标记为 failed。

## 14. 安装、升级与卸载生命周期

### 14.1 插件中心用户流程

当前插件中心第一屏是“插件市场”，另有“已安装”和“仓库与开发”视图，不做营销页。市场展示名称、来源、版本、作者、能力原因和账号访问模式；已安装视图保留现有内置插件，并为用户插件提供启用/禁用、重新安装/更新和卸载操作。发布者信任、runtime 健康、插件日志和配置面板随签名与运行时阶段补齐。

当前 MVP 的“安装插件”使用连续步骤：

1. 从聚合 catalog 选择 `repository_id + plugin_id + version`。
2. 展示市场条目中的全部 capabilities/reasons、account_access、包摘要和官方/自定义来源，并保存该条目的 `consent_digest`。
3. 用户一次性整体同意，不出现 host/root/quota/每日额度或逐操作审批控件。
4. 调用 `POST /api/plugin-center/v1/installations`，提交 `permissions_accepted: true`、当前 `consent_digest` 和是否立即 `enable`；摘要不匹配时重新打开确认页。
5. 使用返回的 `operation.id` 展示下载、SHA-256/manifest 校验、安全解压和写库进度；刷新页面后可从 operations 列表恢复查看。

包内签名链、跨进程崩溃恢复和本地 `.d115p` 上传属于后续增强。实现这些能力时，更新页必须显示旧/新版本的发布者、runtime、capabilities、reasons、account_access 和 UI 差异，任何披露变化都重新整体确认。

### 14.2 插件中心管理 API

管理 API 只服务受信的同源管理界面，继续使用管理员认证与现有同源保护；它不能被插件令牌调用，也不能转发到 `/plugin-api/v1`。当前已实现端点：

| 端点 | 用途 |
|---|---|
| `GET /api/plugin-center/v1/repositories` | 列出官方和自定义仓库、刷新状态及最后成功快照 |
| `POST /api/plugin-center/v1/repositories` | 添加 GitHub 仓库或直接 HTTPS index URL |
| `DELETE /api/plugin-center/v1/repositories/{repository_id}` | 删除自定义源；自动创建的官方源不能删除 |
| `POST /api/plugin-center/v1/repositories/{repository_id}/refresh` | 创建仓库刷新 operation |
| `GET /api/plugin-center/v1/catalog` | 返回已启用仓库的完整聚合列表和每项 `consent_digest`；当前搜索/分页在前端完成 |
| `POST /api/plugin-center/v1/installations` | 提交 `repository_id/plugin_id/version/permissions_accepted/consent_digest/enable` 并创建安装 operation |
| `GET /api/plugin-center/v1/installations` | 列出安装记录、版本、能力、账号访问模式和启用状态 |
| `POST /api/plugin-center/v1/installations/{installation_id}/enable` | 将安装记录标记为启用；当前不启动第三方 runtime |
| `POST /api/plugin-center/v1/installations/{installation_id}/disable` | 将安装记录标记为禁用；完整令牌撤销/停止调度待 runtime 阶段实现 |
| `GET /api/plugin-center/v1/installations/{installation_id}/account-options` | 获取该安装记录可使用的主账号/备用账号安全摘要 |
| `DELETE /api/plugin-center/v1/installations/{installation_id}` | 卸载安装记录 |
| `GET /api/plugin-center/v1/operations` | 列出最近的管理 operation |
| `GET /api/plugin-center/v1/operations/{id}` | 查询单个 operation 进度和结果 |

管理 API 只接受现有管理员认证，插件 token 不能调用。安装请求必须显式携带 `permissions_accepted: true` 和 catalog 当前 `consent_digest`；缺失时返回 `400`，摘要与刷新后的仓库快照不一致时返回 `409`。服务端保存 consent digest、capabilities/reasons/account_access 作为展示与审计依据，并从 HTTPS `package_url` 下载不超过 32 MiB 的包、核对包 SHA-256、检查 manifest 的 ID/version/capabilities/reasons/account_access 与确认页一致，在独立 staging 安全解压后写入新的唯一版本目录并保存安装记录。包内 integrity/Ed25519 签名验证、发布者信任、跨进程孤立目录回收和管理写请求幂等属于下一阶段；即使安装记录为 enabled，也不能把它描述成已具备完整 Host Broker/runtime 执行能力。

### 14.3 后续完整安装目标

1. 下载或上传到 staging，先限制压缩包总大小。
2. 完整遍历 ZIP 并验证路径、类型、文件数和解压后大小。
3. 读取清单，验证 Schema、插件 ID、SemVer、宿主版本和 Plugin API 范围。
4. 验证完整性清单、发布者签名、信任链和 WASM imports。
5. 展示发布者、来源、全部能力、账号访问模式和风险差异。
6. 用户整体确认后写入版本目录、确认快照和插件数据库。
7. 原子切换 `current` 版本，启动运行时并执行健康检查。
8. 健康检查失败时恢复旧版本、旧能力确认快照和 KV 快照。

上述八步是完整目标。当前 MVP 已实现 HTTPS 下载、市场 SHA-256、manifest 一致性检查、安全解压和安装记录，但尚未实现包内 integrity/Ed25519 信任、原子 current 切换、KV 快照、健康检查和第三方 runtime 执行。

### 14.4 后续更新目标

- 更新源必须使用 HTTPS，市场响应自身也要签名。
- 版本必须单调递增；降级只允许管理员显式操作。
- 发布者密钥、插件 ID 或 runtime kind 变化视为新安装。
- 能力、reason、account_access、发布者和 runtime 均未变化时，可按用户策略自动更新。
- 任一披露内容变化时必须暂停并重新整体确认，不能复用旧 `consent_digest`。

### 14.5 禁用与卸载

当前 MVP 的 enable/disable/delete 作用于安装管理记录和账号解析资格。等 runtime 上线后，才追加以下副作用：

禁用：

- 立即撤销访问令牌。
- 停止 WASM 实例或外部事件投递。
- 取消调度与未开始任务。
- 保留代码、配置、KV 和审计。

卸载：

- 默认删除代码和令牌，保留数据 30 天。
- 用户可选择同时清理 KV、日志、任务和历史确认快照。
- 审计摘要和发布者信任记录按系统保留策略保存。

## 15. 数据与审计

当前 MVP 可在主配置库创建 `plugin_repositories`、`plugin_installations` 和 `plugin_operations`，优先支撑仓库、目录、安装确认和进度恢复。完整 runtime 上线后建议迁移或扩展为独立 `dian115_plugins.db`，避免插件任务和事件高频写入竞争主库。目标表包括：

| 表 | 用途 |
|---|---|
| `plugin_publishers` | 发布者公钥、信任来源和吊销状态 |
| `plugin_packages` | 包版本、摘要、来源、兼容范围 |
| `plugin_installations` | 安装实例、当前版本、运行状态 |
| `plugin_consents` | 安装/更新时确认的 capability、reason、account_access、digest 和修订号 |
| `plugin_credentials` | client secret 哈希、webhook secret 密文、撤销时间 |
| `plugin_secret_bindings` | opaque credential ref、加密秘密、允许的 host 与注入策略 |
| `plugin_kv` | 带版本号的插件 KV |
| `plugin_jobs` | 对外稳定 job、所有权、幂等键和结果 |
| `plugin_outbox` | 副作用与事件的事务发件箱 |
| `plugin_event_subscriptions` | 主题、游标和投递配置 |
| `plugin_event_deliveries` | 重试、死信和最后错误 |
| `plugin_audit_logs` | 脱敏调用摘要、耗时、结果和资源范围 |

`client_secret` 只保存抗离线破解的哈希；webhook secret 和第三方凭据必须使用操作系统保护的密钥或独立随机主密钥加密，并支持轮换。不能复用仓库中从固定字符串派生的配置加密密钥，也不能把解密密钥与 SQLite 文件放在同一备份中。

审计记录包含：

- 插件、安装实例、版本、调用 ID、consent digest 和 capability revision。
- 能力名、账号选择模式、opaque 资源引用类型、方法、结果码和耗时。
- 目标 URL 只保留 scheme/host/port；默认不记录 query、header 和 body。
- 文件路径按虚拟根记录，敏感段可哈希。
- 分享码、接收码、离线链接、令牌和秘密绝不进入日志。

## 16. 完整目标状态机

以下完整状态机随签名、runtime 和崩溃恢复阶段实现；当前 MVP 仅持久化安装记录的 `installed + enabled/disabled` 状态，并将重启时未完成的管理 operation 标记为 failed。

安装实例状态：

```text
staged -> awaiting_consent -> installing -> enabled
                                    |          |
                                    v          v
                                  failed    disabled
                                               |
                                               v
                                           uninstalling -> removed

enabled -> updating -> enabled
                 |-> rollback -> enabled/failed
enabled -> quarantined -> disabled/enabled
```

任何状态转换必须带原因和审计记录。进程重启后，`installing/updating/uninstalling` 必须通过事务日志恢复或回滚，不能猜测为成功。

通用 [`internal/service/workqueue.go`](../../internal/service/workqueue.go) 只能作为执行器，不能作为插件事实源：它的终态会淘汰、容量有限且没有安装实例所有权。公共 `job_ref` 必须来自插件数据库，内部 work queue task ID 永不对外。

## 17. 代码集成建议

| 平台能力 | 现有可复用点 | 必须新增的边界 |
|---|---|---|
| HTTP/代理 | `internal/util/http_client.go` | SSRF-safe fixed-IP dialer、能力类别校验、header 过滤和系统级上限 |
| 文件 | `internal/api/local_file_backend.go` | 虚拟根和 entry ref、执行时复核、显式冲突策略、插件所有权 |
| 115 转存/离线 | `internal/client/share115.go`、`internal/client/driver115.go` | preview/item ref、Once 传输、持久化 job、submission uncertain |
| PT 订阅 | `internal/api/pt_subscription_handlers.go` | `SubscriptionFacade` 和稳定 DTO |
| 聚合订阅 | `internal/service/pool_orchestrator.go` | 同上，保留冲突和状态机规则 |
| 签名 | `internal/runtimepayload/payload.go` | 插件专用信任域、发布者库、JCS |
| ZIP 校验 | `internal/service/portable_strm.go` | 通用安全解包器与安装配额 |
| 工作队列 | `internal/service/workqueue.go` | 插件任务所有权、幂等、持久化 operation/job 和结果保留 |

不建议复用现有管理员通用调用器。部分 AI 工具会以管理员身份调用内部 API，这种方式不适合作为第三方插件边界。

## 18. 分阶段交付

### 阶段 A：平台内核

- 清单与 Schema 校验。
- 安全解包、签名、发布者信任和原子版本目录。
- 插件数据库、状态机、能力确认快照、审计和管理 API。
- 插件中心改为“内置插件 + 已安装插件”动态列表。

验收：可安装一个无业务能力的签名包，完成启用、禁用、升级回滚和卸载。

### 阶段 B：外部服务插件 MVP

- 外部服务绑定、短期令牌和 webhook 签名。
- Network Broker、KV、事件与任务中心。
- 声明式 UI 基础组件。

验收：Python/Node 示例插件可安装、显示配置页、调用已声明的网络能力并接收事件。

### 阶段 C：核心业务能力

- File Broker v1：只读、mkdir、rename、同 backend copy/move。
- Transfer Broker。
- Subscription Facade；v1 仅开放 aggregate TV 集数更新。
- 115 账号 selector、备用号池解析、异步 job 和能力级审计。

验收：插件无法绕过 Host API 暴露根、opaque ref、账号绑定、对象所有权和系统级上限；不确定提交不会被重试；禁用后所有能力立即失效。

### 阶段 C.1：可恢复文件写入与删除

- 本地与 CD2 统一的原子内容写入、ETag/CAS 和配额。
- 宿主级可恢复 trash、恢复操作和保留策略。
- `files.local.trash`、`files.cloud.trash` 上线；永久 purge 继续保留为管理员操作。

### 阶段 D：WASM 与市场

- `wazero` runtime supervisor、ABI 和 Rust/TinyGo SDK。
- 市场索引签名、更新检查、发布者撤销和风险提示。
- SDK CLI：`init/lint/dev/pack/sign/publish`。

验收：相同示例同时提供 WASM 与 HTTP 实现，能力与账号选择行为一致。

## 19. 上线前安全验收

- ZIP traversal、大小写碰撞、压缩炸弹和符号链接测试。
- Manifest/完整性/签名篡改与发布者换钥测试。
- SSRF：IPv4/IPv6、DNS rebinding、重定向、userinfo、非标准端口和代理绕过。
- 文件：`..`、符号链接、junction/reparse point、TOCTOU、跨根 move、覆盖和系统级容量上限。
- 幂等：相同键重放、不同 body 冲突、进程重启恢复和非幂等 `submission_uncertain` 人工对账。
- 能力确认：更新 digest、token stale、未声明类别调用、跨插件任务读取和伪造 account_ref。
- 资源：WASM 内存、CPU、并发、日志洪泛、事件积压和远程插件超时。
- 隐私：日志、通知、错误、审计和前端均不得泄露 Cookie、Key、CID、分享密码或代理凭据。

开发者使用方式、请求示例和错误处理见 [`developer-guide.md`](developer-guide.md)。
