# DIAN115 插件运行时契约 v1

本文定义 `dian115:plugin@1`（WASM）与 `dian115:process@1`（宿主管理进程）共同使用的 state/action/job/event 调用信封、响应、幂等和错误语义，并给出 WASM 的 health 操作与完整二进制 ABI。业务接口的 `method`、`path`、query、JSON body 和响应字段以本目录的 OpenAPI 为准；运行时不得自行猜测未登记接口。

文中的“必须”“不得”是协议要求，“应”是兼容性建议。所有长度均按字节计算，所有 JSON 和文本均使用 UTF-8。

## 1. 共同约束

### 1.1 JSON 与标识符

- 每次调用信封和每次运行时响应都必须是一个 JSON object，不得返回顶层数组、字符串、数字或多个连续 JSON 值。
- 单个调用信封、运行时响应或 process JSON-RPC 帧不得超过 256 KiB。
- `invocation_id`、view、action、job、handler 和 `state_version` 长度为 1～80，格式为 `^[A-Za-z0-9]+(?:[._-][A-Za-z0-9]+)*$`。
- event topic 长度为 3～80，使用同一格式。
- 时间使用带时区的 RFC 3339；宿主当前会发送 UTC RFC 3339 Nano，例如 `2026-08-21T08:30:00.123456789Z`。
- 运行时响应会经过安全检查。不得把 Cookie、Token、密码、授权头、宿主绝对路径等敏感值放进 UI state 或 callback 结果；需要关联宿主资源时使用宿主返回且允许展示的不透明 `*_ref`。

运行时响应中以下字段名会被拒绝：`cid`、`file_id`、`database_id`、`absolute_path`、`raw_path`、`password`、`client_secret`、`webhook_secret`、`access_token`、`refresh_token`、`authorization`，以及包含 `cookie`、以 `_token` 或 `_secret` 结尾的字段名。以 `_ref` 结尾的不透明引用字段可以使用。任何看起来像 Linux、UNC 或 Windows 绝对路径的字符串也不得出现在响应中。同一安全检查也适用于 action `input` 和 event `data`。Host API 的原始响应位于 `body_base64` 内，不受 UI state 字段命名规则影响；插件在把其中数据投影到 UI state 前必须脱敏。

### 1.2 调用信封

宿主向两种运行时发送相同形状的逻辑信封：

```json
{
  "op": "action",
  "invocation_id": "inv_01J5Y8RZ3J6Y",
  "payload": {}
}
```

| 字段 | 要求 |
| --- | --- |
| `op` | WASM 为 `health`、`state`、`action`、`job` 或 `event`；process v1 当前稳定集合为 `state`、`action`、`job` 和 `event`。 |
| `invocation_id` | 宿主生成的不透明标识。插件必须原样用于日志、去重和派生 Host API 幂等键，不得自行解析其业务含义。 |
| `payload` | WASM `health` 可以省略；其他操作按下文章节提供 object。 |

WASM 直接把此 JSON 交给 `dian115_invoke`。process 运行时对其稳定操作把信封放进 `runtime.invoke.params.envelope`，并额外提供 `background`：

```json
{
  "jsonrpc": "2.0",
  "id": "h:2",
  "method": "runtime.invoke",
  "params": {
    "envelope": {
      "op": "event",
      "invocation_id": "evt_01J5Y9A2CF5Q",
      "payload": {}
    },
    "background": true
  }
}
```

`background=false` 使用 `runtime.timeout_ms`；`background=true` 使用 `runtime.background_timeout_ms`。当前分类如下：

| `op` | `background` | 用途 |
| --- | --- | --- |
| `health` | `false` | WASM 显式健康检查；process 不接收此操作。 |
| `state` | `false` | 为一个 UI view 读取快照。 |
| `action` | `false` | 处理用户动作。 |
| `job` | `true` | 处理定时或手动触发的 manifest job。 |
| `event` | `true` | 处理宿主事件，包括目录监控事件。 |

超时会取消本次宿主调用。WASM 实例可能被卸载；无响应的 process 会被判定为不健康并终止进程组，再按重启策略处理。插件不得假设超时后代码仍会继续运行，也不得在响应后继续修改该次调用的结果。

### 1.3 并发

- 宿主最多同时投递 manifest `runtime.max_concurrency` 个 invocation。WASM 的取值范围为 1～2，process 为 1～16。
- `max_concurrency > 1` 时，同一安装实例会并发收到不同信封；插件必须保护共享内存、文件、KV 缓存和子进程状态。
- 并发响应可以乱序返回，唯一关联依据是 WASM 调用本身或 process JSON-RPC `id`。
- 同一个 `invocation_id` 的重投递不是一项新的业务工作，必须按第 7 节处理。

## 2. WASM `health`

当前 `health` invocation 属于 `dian115:plugin@1`；`dian115:process@1` 以 `runtime.initialize` 握手、进程存活和退出状态作为健康判断，不要求实现本节操作。

健康检查没有业务副作用，也不进入持久化 delivery ledger。

请求：

```json
{
  "op": "health",
  "invocation_id": "health_42"
}
```

成功响应：

```json
{
  "status": "ok",
  "protocol": "dian115:plugin@1",
  "version": "1.2.3"
}
```

要求：

- `status` 必须是 `ok`。
- WASM 可以返回 `abi: "dian115:plugin@1"`，也可以用同值的 `protocol`。
- `version` 可省略；提供时必须与已安装插件版本完全一致。
- 不健康不得伪装成 `status: "failed"` 的正常响应；WASM 初始化失败、trap 或超时会让宿主把运行时标记为不健康。

## 3. `state`、强 ETag 与条件读取

宿主按 UI view 读取状态：

```json
{
  "op": "state",
  "invocation_id": "state_dashboard",
  "payload": {
    "view": "dashboard",
    "if_none_match": "\"rev_42\""
  }
}
```

首次读取或状态已变化时返回：

```json
{
  "state_version": "rev_43",
  "etag": "\"rev_43\"",
  "state": {
    "summary": {"running": 2, "failed": 0},
    "tasks": []
  }
}
```

状态未变化时可以返回：

```json
{
  "not_modified": true,
  "etag": "\"rev_42\""
}
```

规则：

1. 完整响应必须包含合法的 `state_version` 和 JSON object `state`。
2. `etag` 是强 ETag，值必须严格等于给 `state_version` 加一层双引号，例如 `state_version=rev_43` 对应 `etag="rev_43"`。完整响应省略 `etag` 时宿主会按此规则生成。
3. `if_none_match` 为空表示无缓存；非空时只会包含一个强 ETag，不会发送 `W/` 弱 ETag 或逗号列表。
4. 返回 `not_modified=true` 时必须回显与 `if_none_match` 完全相同的 `etag`，不得同时返回新的 `state`。
5. 即使插件返回完整 state，宿主发现响应 ETag 与请求一致时仍可对前端转换为 HTTP 304。
6. `state` 是当前快照，不得在读取 state 时创建任务、发送通知或执行文件移动等写操作。

## 4. `action`

action ID 必须已经由已安装的 UI schema 声明。表单提交、工具栏动作和表格行操作最终都使用同一信封：

```json
{
  "op": "action",
  "invocation_id": "inv_01J5Y8RZ3J6Y",
  "payload": {
    "id": "start_transfer",
    "input": {
      "account_ref": "account_backup_12",
      "directory_ref": "dir_01J5Y8T2",
      "url": "magnet:?xt=urn:btih:..."
    },
    "context": {
      "locale": "zh-CN",
      "timezone": "Asia/Shanghai"
    }
  }
}
```

响应必须包含以下状态之一：

```json
{
  "status": "succeeded",
  "code": "transfer_created",
  "message": "任务已创建",
  "result": {"task_ref": "task_01J5Y8V1"}
}
```

| `status` | 含义 |
| --- | --- |
| `succeeded` | 动作已经同步完成，是最终结果。 |
| `failed` | 插件已正常处理请求，但业务操作失败；这是可缓存的最终响应，不代表运行时协议故障。 |
| `accepted` | 已创建插件自己的后台任务。应在 `result` 返回不透明 `task_ref`，并通过后续 state、插件日志或插件通知反馈结果。 |
| `skipped` | 请求有效，但当前状态下无需执行。 |

`code` 应是稳定、可供 UI 判断的插件自定义代码；`message` 是已经脱敏的用户可读文本；`retryable` 只是给 UI 的提示，不会自动绕过 invocation 幂等规则。`result` 可省略。

## 5. `job`

job 必须在 manifest `jobs` 中声明。宿主传入 job ID、实际 handler、原计划时间和触发来源：

```json
{
  "op": "job",
  "invocation_id": "inv_01J5YB2K8D4M",
  "payload": {
    "id": "scan_inbox",
    "handler": "scan_inbox",
    "scheduled_for": "2026-08-21T09:00:00Z",
    "trigger": "schedule",
    "attempt": 1
  }
}
```

- `trigger` 是 `schedule` 或 `manual`。
- `scheduled_for` 是本次逻辑运行原定时间；重投递时保持不变。
- `attempt` 是逻辑调用字段。v1 首次值为 `1`；传输层重投递不会修改已经参与幂等哈希的信封，插件不得用它替代 `invocation_id` 去重。
- `allow_overlap=false` 时，宿主不会为同一安装实例并发启动同一 job 的两个逻辑运行。

v1 job 必须返回 `accepted` 或 `skipped`：

```json
{
  "status": "accepted",
  "message": "扫描任务已接收",
  "result": {"task_ref": "task_01J5YB3A"}
}
```

`accepted` 是本次 job delivery 的成功确认。耗时工作可以由常驻 process 继续执行，但必须持久化自己的任务状态，并在禁用或 shutdown 时可控停止；WASM 不会在 invocation 返回后继续执行。无需运行时返回 `skipped`。

## 6. `event`

只有 manifest `events` 中声明的 topic 会投递：

```json
{
  "op": "event",
  "invocation_id": "evt_01J5YC0D9G7P",
  "payload": {
    "id": "evt_01J5YC0D9G7P",
    "topic": "files.changed",
    "occurred_at": "2026-08-21T09:10:00Z",
    "data": {
      "watch_ref": "watch_01J5YBZQ",
      "backend": "cd2",
      "added": [{"entry_ref": "entry_01J5YC02", "name": "movie.mkv"}],
      "removed": [],
      "modified": [],
      "resync_required": false
    }
  }
}
```

`payload.id` 与顶层 `invocation_id` 相同。宿主在投递结果不确定时会用相同 ID、topic、时间和 data 重投递。

推荐响应：

```json
{"status":"accepted"}
```

无需处理可以返回 `{"status":"skipped"}`。为兼容最小消费者，v1 也接受任意安全 JSON object（包括 `{}`），但插件不应依赖空响应表达失败。业务处理失败应写独立日志并由自身任务状态或插件通知反馈；传输失败才会触发宿主 delivery 重试。

## 7. 幂等、重放与超时

### 7.1 invocation ledger

`action`、`job` 和 `event` 使用安装实例隔离的持久化 delivery ledger，语义是“至少一次投递 + 相同结果重放”，不是“恰好一次执行”。

- 相同 `invocation_id` 和相同逻辑请求：宿主可能不再调用插件，直接重放已保存响应，并在管理接口标记 `replayed=true`。
- 相同 `invocation_id` 但 action/job/topic/input/data 不同：拒绝为 `invocation_conflict`。
- 相同调用仍在执行：拒绝为可重试的 `invocation_in_progress`。
- 宿主在进程退出、超时或响应是否送达不确定时，可以使用同一信封重投递。

插件必须先按 `invocation_id` 查自己的完成记录，再执行不可逆副作用；完成记录与插件状态应尽可能原子保存。对宿主写接口的每一个副作用还必须发送稳定且唯一的 `Idempotency-Key`，推荐格式为 `<invocation_id>:<operation>`。例如事件中移动文件与发送通知应使用两个不同键：`evt_...:move` 与 `evt_...:notify`。

WASM `health` 和两种运行时的 `state` 不进入 ledger，必须天然可重复。

### 7.2 超时和取消

- `timeout_ms` 约束 WASM health 以及两种运行时 state/action 的完整执行，包括其内部 Host Call。
- `background_timeout_ms` 约束 job/event 的完整执行。
- 等待并发槽位也计入超时。
- 超时后宿主不再接受迟到响应。WASM 调用上下文会取消并可卸载实例；process invocation 超时会导致不健康终止和按策略重启。
- process 自主循环发起的 `host.call` 不继承某个 `runtime.invoke` 的前台超时，但仍受 Host API/网络接口自身限制，并会在 shutdown 或进程终止时中断。

### 7.3 错误层次

开发者必须区分以下四层：

| 层次 | 表现 | 处理方式 |
| --- | --- | --- |
| ABI / 通道错误 | WASM trap、`host_call` ABI status `2`、process 退出或 JSON-RPC error | 当前调用没有可信业务响应；宿主返回 `runtime_unavailable` 或 `runtime_rejected`，可能重启运行时。 |
| 运行时契约错误 | 非 object JSON、超过 256 KiB、state 缺字段、非法 status/ETag、敏感字段泄漏 | 宿主返回非重试的 `runtime_protocol_error`；修复插件。 |
| Host Call 拒绝或接口错误 | process `host.call` JSON-RPC error，或成功 HostCallResponse 中 `status >= 400` | 前者表示请求未形成正常 Host API 响应；后者必须解码 `body_base64` 中的 problem JSON，并按接口语义处理。 |
| 插件业务结果 | action 的 `failed`、job/event 的 `skipped` | 这是正常协议响应，会被 ledger 保存；不得期待宿主把它当传输失败自动重投。 |

管理接口可能返回的稳定运行时代码包括：`invalid_request`、`resource_not_found`、`plugin_disabled`、`runtime_invalid`、`runtime_unavailable`、`runtime_rejected`、`runtime_protocol_error`、`invocation_conflict`、`invocation_in_progress` 和 `capability_denied`。插件自身的 `code` 不得冒充这些宿主代码。

## 8. 通用 Host Call JSON

两种运行时使用完全相同的请求：

```json
{
  "method": "POST",
  "path": "/api/notifications/plugin",
  "headers": {
    "content-type": "application/json",
    "idempotency-key": "inv_01J5Y8RZ3J6Y:notify"
  },
  "body_base64": "eyJsZXZlbCI6InN1Y2Nlc3MifQ"
}
```

成功完成 Host Call 传输后得到：

```json
{
  "status": 202,
  "headers": {"content-type": ["application/json"]},
  "body_base64": "e30"
}
```

- `method` 使用大写 `GET`、`HEAD`、`POST`、`PUT`、`PATCH` 或 `DELETE`。
- 本地接口 `path` 是完整 `/api/...` 路径和 query；外部请求是已批准的完整 `https://...` URL；总长度不得超过 4096 字节。
- request 只允许 `method`、`path`、`headers` 和 `body_base64`，未知字段会被拒绝。
- 只允许 `accept`、`content-type`、`if-match`、`if-none-match`、`idempotency-key` 和 `x-correlation-id` 请求头。不得提交身份、Cookie、Host 或代理头。
- 单个 header 名最多 100 字节，值最多 4096 字节，名称和值均不得包含 CR/LF。
- `body_base64` 接受标准 Base64 的有填充或无填充形式；宿主响应使用无填充标准 Base64。
- `status` 是真实 HTTP/逻辑 Handler 状态。非 2xx 仍是一次成功的 Host Call 传输，不等于 WASM ABI status `2` 或 JSON-RPC error。
- Host Call 外层 JSON 上限为 256 KiB；由于 body 使用 Base64，业务响应正文可用空间小于 256 KiB。

## 9. WASM ABI：`dian115:plugin@1`

### 9.1 唯一允许的导入和导出

等价 WAT 签名如下；这是接口声明，不是插件实现源码：

```wat
(import "dian115" "host_call"
  (func $host_call (param i32 i32 i32 i32) (result i64)))
(import "dian115" "log"
  (func $log (param i32 i32)))

(memory (export "memory") <min-pages> <max-pages>)
(func (export "dian115_alloc") (param i32) (result i32))
(func (export "dian115_invoke") (param i32 i32) (result i64))

;; 可选
(func (export "dian115_free") (param i32 i32))
(func (export "dian115_init"))
(func (export "dian115_shutdown"))
```

不得导入 WASI、memory 或任何其他函数；不得导出除上述名称以外的函数。`memory` 必须由插件定义并导出，必须声明最大页数，初始值和最大值均不得超过 manifest `memory_mb`。一页为 64 KiB。

宿主在实例化成功后调用一次可选 `dian115_init()`；任何 trap 都会使加载失败。卸载时宿主尽力调用一次可选 `dian115_shutdown()`，随后关闭实例；它不是长期清理任务的入口。

### 9.2 `dian115_invoke` 的指针、长度和 i64

调用顺序：

1. 宿主调用 `req_ptr = dian115_alloc(req_len)`。
2. 宿主把恰好 `req_len` 字节的 UTF-8 信封写入 `[req_ptr, req_ptr + req_len)`；不附加 NUL。
3. 宿主调用 `packed = dian115_invoke(req_ptr, req_len)`。
4. 插件返回 response 指针和长度打包后的 i64。
5. 宿主立即复制 response，再按第 9.3 节释放。

i64 按无符号位模式解释：

```text
bits 63..32 = response_ptr (u32)
bits 31..0  = response_len (u32)

packed = (u64(response_ptr) << 32) | u64(response_len)
response_ptr = u32(u64(packed) >> 32)
response_len = u32(u64(packed))
```

某些语言把 WebAssembly i64 映射为有符号整数；移位前必须按 u64 重新解释，不能进行有符号右移。response 是单个 UTF-8 JSON object，不带 NUL。`response_len=0` 会被宿主解释为 `{}`。

response 可以复用 request buffer，也可以位于新 buffer。复用时必须保证原分配容量足以容纳整个 response；通常更安全的做法是单独分配 response。

### 9.3 内存所有权

- `dian115_alloc` 返回的内存和 `dian115_invoke` 返回的 response 内存始终由插件分配。
- 宿主只在调用期间读写这些范围，不长期持有 guest 指针。
- 若导出 `dian115_free(ptr, len)`：
  - response 与 request 不同：宿主先后调用 `free(req_ptr, req_len)` 和 `free(response_ptr, response_len)`；零长度 response 不调用第二次。
  - response 与 request 相同：宿主只调用一次 `free(req_ptr, max(req_len, response_len))`。
- 因此 `dian115_free` 必须容忍上述逻辑长度，不能要求第二个参数必须等于分配器内部记录的原始容量。
- 若不导出 `dian115_free`，宿主不会释放 guest buffer；插件必须使用可复用 arena、bump allocator reset 或其他有界策略，避免每次 invocation 永久增长。
- 插件不得在 `dian115_invoke` 返回后异步读写已返回的 response buffer。

### 9.4 `dian115.host_call`

签名：

```text
host_call(req_ptr: i32, req_len: i32, resp_ptr: i32, resp_cap: i32) -> i64
```

request 是第 8 节的 Host Call JSON。宿主先完整复制 request，再执行接口，然后尝试把 HostCallResponse JSON 写入 response buffer。返回值编码不同于 `dian115_invoke`：

```text
bits 63..32 = abi_status (u32)
bits 31..0  = response_length_or_required_length (u32)
```

| ABI status | 名称 | 低 32 位 | 含义 |
| --- | --- | --- | --- |
| `0` | `OK` | 实际响应长度 | response buffer 已写入完整 HostCallResponse JSON。 |
| `1` | `SHORT_BUFFER` | 所需长度 | buffer 未写入可依赖的完整响应；换更大 buffer 后重试。 |
| `2` | `ABI_ERROR` | 当前为 `0` | 指针/长度、请求 JSON、权限、URL、header、超限、取消或宿主内部错误；没有 HostCallResponse。 |

`resp_cap` 不得超过 256 KiB。强烈建议直接准备接近上限的可复用 response buffer，因为宿主在判断 `SHORT_BUFFER` 前已经执行了请求。若必须在 status `1` 后重试写接口，必须复用完全相同的请求和 `Idempotency-Key`，否则可能产生两次副作用。status `0` 后还必须检查 HostCallResponse 内部的 HTTP `status`。

request 和 response buffer 可以重叠，因为宿主先复制 request；为简化分配器和调试，仍建议使用不同范围。所有 guest 指针都必须位于已导出的 linear memory 内，`ptr + len` 不得溢出。

### 9.5 `dian115.log`

```text
log(ptr: i32, len: i32) -> void
```

buffer 是不带 NUL 的 UTF-8 纯文本。ABI 最多读取 16 KiB，持久化前会去除控制字符、敏感信息并裁剪为单条 8 KiB；WASM `log` 固定为 `info` 级别。需要结构化级别和 fields 的原生插件使用 process `host.log`。

### 9.6 WASM 限制汇总

| 项目 | v1 限制 |
| --- | --- |
| `.wasm` 文件 | 16 MiB |
| linear memory | manifest 8～64 MiB，必须有不超过该值的 max |
| invocation request | 256 KiB |
| invocation response | 256 KiB |
| Host Call request JSON / response JSON | 各 256 KiB |
| Host Call decoded request body | 256 KiB；外层 Base64 JSON仍受 256 KiB 限制 |
| ABI log 输入 | 16 KiB；持久化单条 8 KiB |
| 并发 | 1～2 |

## 10. process 主动调用、并发与关闭

process 的 framing、初始化、沙箱和进程组生命周期见 [Process Runtime v1](process-runtime-v1.md)。`dian115:process@1` 当前稳定承诺通过 `runtime.invoke` 处理 `state`、`action`、`job` 和 `event`，其 envelope 与本文件第 3～6 节完全一致；process 健康状态由初始化握手与进程生命周期判断。本节规定 process 主动调用与关闭的补充行为。

### 10.1 主动 `host.call`

完成 `runtime.initialize` 后，process 可以在以下任意时机主动发送 `host.call`：

- 正在处理 `runtime.invoke` 时；
- 自己的常驻循环、定时器或包内子进程产生任务时；
- 插件页面已经关闭，但安装实例仍启用时。

它不需要等待宿主先发起一个 invocation，也不需要持有 DIAN115 HTTP Token。示例：

```json
{
  "jsonrpc": "2.0",
  "id": "p:17",
  "method": "host.call",
  "params": {
    "method": "GET",
    "path": "/api/plugin-runtime/watches",
    "headers": {"accept": "application/json"},
    "body_base64": ""
  }
}
```

成功时 `result` 就是第 8 节的 HostCallResponse；请求在 ABI/权限层被拒绝时返回 JSON-RPC error `-32001`。`host.call` 的 JSON-RPC ID 必须是非空字符串且不超过 128 字节，插件应使用自己的 `p:` 前缀并保证所有未完成请求中唯一。

主动调用仍受安装时批准的 METHOD + path、网络来源、幂等、审计、响应脱敏和接口限流约束。process 的 seccomp 阻止直接 socket，Landlock 阻止读取其他宿主路径；包内子进程继承两层限制，不能绕过 Host Call。需要由子进程请求宿主能力时，应由入口进程代理到同一 stdio 通道。

### 10.2 全双工与并发

- 插件必须持续读取 stdin；不得在等待某个 `host.call` 响应时停止处理新的 `runtime.invoke` 或 `runtime.shutdown`。
- 宿主可能并发发送最多 `max_concurrency` 个 `runtime.invoke`，也可能在 `host.call` 未完成时发送新的 invocation。
- 宿主和插件的响应都可以乱序。以 JSON-RPC `id` 匹配，不能按发送顺序匹配。
- stdout 的所有写入必须串行化成完整帧，两个线程不得交错写 header 或 JSON body。
- 每帧最大 256 KiB，header 总计最大 8 KiB。需要响应的 request 及其 response 使用非空、最多 128 字节的字符串 ID；notification 省略 ID。未知 method 返回 `-32601`，参数不合法返回 `-32602`；单个请求错误不得停止读循环。

结构化日志可以作为 request 或 notification 发送：

```json
{
  "jsonrpc": "2.0",
  "method": "host.log",
  "params": {
    "level": "info",
    "message": "目录扫描完成",
    "fields": {"watch_ref": "watch_01J5YBZQ", "count": 3}
  }
}
```

level 支持 `debug`、`info`、`warn`/`warning` 和 `error`。message 与 fields 各最多 8 KiB，并会自动脱敏。

### 10.3 `runtime.shutdown`

禁用、更新、卸载或宿主退出时，宿主停止新投递并发送：

```json
{
  "jsonrpc": "2.0",
  "id": "h:99",
  "method": "runtime.shutdown",
  "params": {"reason": "host_stop"}
}
```

插件收到后必须：

1. 原子地进入 stopping 状态，不再创建自主任务或发起新的 `host.call`。
2. 取消定时器和目录轮询，停止或等待仍在运行的 invocation。
3. 终止自己创建的包内子进程，刷新插件私有状态和必要日志。
4. 返回 JSON-RPC result，例如 `{"stopped":true}`，随后让入口进程退出。

清理和响应必须在 `shutdown_timeout_ms` 内完成。超时后宿主向整个进程组发送终止信号，宽限期结束仍未退出则强制结束；入口进程退出时遗留的子进程也会被回收。不得自行 daemonize、创建脱离进程组的长期后台服务，或在 shutdown 后继续调用宿主。

## 11. 最小实现检查表

- WASM 导入/导出签名、memory max、i64 高低 32 位与 `free` 规则完全一致。
- 所有运行时响应都是单个、脱敏且不超过 256 KiB 的 JSON object。
- state 使用与 `state_version` 严格匹配的强 ETag，并正确处理 `if_none_match`。
- action/job/event 以 `invocation_id` 去重；每个宿主写操作另带稳定 `Idempotency-Key`。
- 同时区分 ABI/JSON-RPC 错误、运行时契约错误、HostCallResponse HTTP 状态和插件业务 status。
- process 的 stdin 读循环与 stdout 写锁不会被业务处理阻塞；主动 `host.call` 使用唯一 `p:` ID。
- process 在 shutdown 时停止自主循环、Host Call 和所有子进程，并在超时前退出。
