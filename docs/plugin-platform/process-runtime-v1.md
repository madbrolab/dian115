# DIAN115 Process Runtime v1

`process` 运行时用于需要常驻循环、第三方原生库或主动后台任务的插件。可执行文件由 DIAN115 在当前 Docker 容器内通过强制沙箱启动和监管；它不是远程运行时，不监听 DIAN115 回调端口，也不是额外的 Docker 服务。`dian115:process@1` 当前稳定支持 `state`、`action`、`job` 和 `event`，共享信封、幂等、超时、错误层次和 Host Call JSON 见[运行时契约 v1](runtime-contract-v1.md)。

## 1. Manifest

```json
{
  "runtime": {
    "kind": "process",
    "entry": "runtime/plugin",
    "protocol": "dian115:process@1",
    "startup_timeout_ms": 10000,
    "shutdown_timeout_ms": 5000,
    "timeout_ms": 30000,
    "background_timeout_ms": 300000,
    "max_concurrency": 4,
    "restart_policy": "on-failure"
  }
}
```

`entry` 必须是包内相对路径，必须被 `integrity.json` 覆盖，并在 ZIP 中带可执行位。当前只支持 `linux/amd64` 与 `linux/arm64`，安装器会检查 ELF 架构与当前容器一致。入口及包内子程序应静态链接并把运行所需文件全部放进签名包；沙箱不允许读取或执行宿主共享库。入口可以创建线程、常驻循环和包内子进程，但不得自行 daemonize、脱离宿主创建的进程组或遗留后台服务。

## 2. 生命周期

| 时机 | 宿主行为 |
| --- | --- |
| DIAN115 启动或插件启用 | 建立沙箱并启动入口，完成初始化握手后再接受 state/action/job/event |
| 插件页面关闭 | 进程继续运行，调度和监控不停止 |
| 进程异常退出 | 指数退避重启；连续失败进入熔断状态 |
| 插件禁用 | 停止新投递，发送关闭请求，随后终止整个进程组 |
| 插件更新 | 先停止旧进程；新包握手成功后才启用新版本 |
| 插件卸载或 DIAN115 退出 | 停止进程并回收子进程，不留下后台服务 |

运行状态会显示 `starting`、`running`、`backoff`、`failed` 或 `stopped`，以及 PID、启动时间、重启次数、最近退出码和最近错误。插件自己的 stderr 与结构化日志写入当前安装实例的独立日志；单条 message 与 fields 各限 8 KiB，总量按 4 MiB、5000 条和 14 天限制裁剪。

## 3. stdio 帧

stdin/stdout 是全双工 JSON-RPC 2.0 通道。stdout 只能写协议帧；普通日志必须写 stderr 或调用 `host.log`。每帧使用 UTF-8 JSON 和 `Content-Length`，格式如下：

```text
Content-Length: <JSON 字节数>\r\n
Content-Type: application/json\r\n
\r\n
<JSON>
```

每个 JSON-RPC frame 最大 256 KiB，header 总计最大 8 KiB。需要响应的 request 及其 response 的 `id` 必须是非空且不超过 128 字节的字符串；notification 省略 `id`。实现必须支持请求与响应交错：插件处理一次 `runtime.invoke` 时可以同步发起 `host.call`，常驻循环也可以在没有待处理 invocation 时主动发起 `host.call`；宿主还可能并发发送最多 `runtime.max_concurrency` 个 invocation。JSON-RPC `id` 在未完成请求中必须唯一，插件发起的请求建议使用 `p:` 前缀。未知 method 应返回标准 `-32601`，坏参数返回 `-32602`；不得让单个错误终止读循环。stdout 的帧写入必须串行化，不能由多个线程交错输出。

## 4. 宿主调用插件

启动后的第一个请求是 `runtime.initialize`：

```json
{
  "jsonrpc": "2.0",
  "id": "host_1",
  "method": "runtime.initialize",
  "params": {
    "protocol": "dian115:process@1",
    "plugin_id": "example.helper",
    "plugin_version": "1.0.0",
    "installation_id": 42,
    "locale": "zh-CN",
    "timezone": "Asia/Shanghai"
  }
}
```

插件成功响应后视为 ready：

```json
{"jsonrpc":"2.0","id":"host_1","result":{"ready":true}}
```

所有状态读取、UI 动作、定时任务和事件投递都属于当前稳定协议，并统一使用 `runtime.invoke`；`envelope` 与 WASM 的 `dian115_invoke` 对应操作完全相同，不存在另一个 HTTP callback。process 的健康状态由 `runtime.initialize` 握手、进程存活和退出状态判断，v1 不要求插件处理单独的 `health` invocation：

```json
{
  "jsonrpc": "2.0",
  "id": "host_2",
  "method": "runtime.invoke",
  "params": {
    "envelope": {
      "op": "event",
      "invocation_id": "evt_01",
      "payload": {
        "id": "evt_01",
        "topic": "files.changed",
        "occurred_at": "2026-08-20T08:00:00Z",
        "data": {"watch_ref": "fw_01", "added": ["movie.mkv"]}
      }
    },
    "background": true
  }
}
```

`result` 是对应 state/action/job/event 契约要求的 JSON 对象，完整字段和响应 status 见[运行时契约 v1](runtime-contract-v1.md)。宿主对 action/job/event 使用持久化 delivery ledger；不确定投递会带相同 `invocation_id` 重试，插件必须按 ID 幂等处理。state 可重复调用但不进入 ledger。

停止时宿主发送 `runtime.shutdown`，参数为 `{"reason":"host_stop"}`。插件必须先进入 stopping 状态，停止自主循环、定时器、新的 `host.call` 和子进程，再处理或取消未完成 invocation、刷新私有状态并响应，随后退出入口进程。超过 `shutdown_timeout_ms` 后，宿主先终止整个进程组，再在宽限期后强制结束；迟到响应不会被接受。

## 5. 插件调用宿主

插件通过 `host.call` 调用安装时批准的 Host API 或 HTTPS 来源。它既可以在处理 `runtime.invoke` 时调用，也可以由插件自己的常驻循环、定时器或包内子进程任务主动触发；主动调用不需要先收到一个 invocation，也不需要 DIAN115 Token。进程及其子进程没有直接 socket 能力，因此外部 HTTPS 也必须走这条通道：

```json
{
  "jsonrpc": "2.0",
  "id": "plugin_1",
  "method": "host.call",
  "params": {
    "method": "POST",
    "path": "/api/notifications/plugin",
    "headers": {"content-type": "application/json", "idempotency-key": "task-42-done-0001"},
    "body_base64": "eyJsZXZlbCI6InN1Y2Nlc3MiLCJ0aXRsZSI6IuS7u+WKoeWujOaIkCIsImJvZHkiOiLlt7LlpITnkIYifQ"
  }
}
```

成功结果与 WASM Host Call 相同：

```json
{"jsonrpc":"2.0","id":"plugin_1","result":{"status":200,"headers":{"content-type":["application/json"]},"body_base64":"e30"}}
```

`host.call` 必须带非空 JSON-RPC `id`；ABI、声明或权限层拒绝时宿主返回 `-32001`，正常 Host Call 则在 `result.status` 返回真实 HTTP 状态，包括 4xx/5xx。多个 `host.call` 可以并发且响应可以乱序，必须按 ID 关联。写操作始终携带由 invocation 或插件任务引用派生的稳定 `Idempotency-Key`。

外部请求把完整 `https://...` URL 放在 `path` 字段。宿主只允许 manifest `permissions.network` 已声明且用户安装时批准的 origin、方法和 `proxy_mode`，并执行代理选择、请求限制、审计和响应脱敏；不要在命令行参数、环境变量、stdout 或日志中保存账号 Cookie、Token 或其他凭据。完整的允许 header、Base64、大小限制和错误分层见[运行时契约 v1](runtime-contract-v1.md)。

结构化日志使用 `host.log`，可以作为不等待响应的 notification，也可以带 ID 等待 `{"accepted":true}`：

```json
{
  "jsonrpc": "2.0",
  "method": "host.log",
  "params": {"level": "info", "message": "任务完成", "fields": {"job_ref": "job_01"}}
}
```

## 6. 运行环境与沙箱边界

当前稳定实现只在 `linux/amd64` 与 `linux/arm64` 启动 process。宿主在执行插件入口之前设置 `no_new_privs`、Landlock 文件系统规则和 seccomp 系统调用过滤；Landlock 不可用、ABI 低于 3 或任一规则安装失败时均 fail closed，插件不会在降级模式下运行。

文件系统边界如下：

- `DIAN115_PLUGIN_PACKAGE` 指向已签名包树。插件可以读取并执行其中的文件，但不能创建、修改、删除或截断包内容。
- 工作目录、`HOME` 和 `DIAN115_PLUGIN_DATA` 指向当前安装实例的私有 data 树。插件可以读写、创建、移动和删除数据，但不能从该树执行程序；临时文件也位于这棵树中。
- 除标准流实现所需的 `/dev/null` 普通读写外，宿主的配置、数据库、媒体挂载、CD2 挂载、系统目录和其他插件目录都不可访问。
- 包树与 data 树必须互不包含；路径解析或隔离规则无法建立时启动失败。

seccomp 阻止 `socket`、`socketpair`、`connect`、`bind`、`listen`、收发消息等直接网络入口，同时阻止 mount/namespace、ptrace、BPF 等逃逸面。插件不能直连公网、局域网、DIAN115 HTTP 端口、CD2 gRPC socket 或本机代理。它可以执行签名包树中的子程序，但所有子进程都会继承同一 Landlock、seccomp、无新权限和进程组边界，不能借子进程扩大文件或网络权限，也不能执行从 data 目录下载的文件。

宿主只传递运行协议所需的环境，不把数据库凭据、115 Cookie、管理员 JWT、TMDB Key、CD2 gRPC 凭据或代理秘密交给插件。115、文件/CD2、TMDB、订阅、Telegram 插件通知以及 manifest 声明的外部 HTTPS 均必须调用用户已批准的 `host.call`；宿主统一执行账号选择、代理、缓存、幂等、审计和响应脱敏。

process 可以运行自己的循环和维护私有 data，但不能直接打开宿主目录做原生 watcher。监控本地挂载、CD2 或 115 目录时，必须通过已批准的 `/api/plugin-runtime/watches` Host API 登记；宿主负责访问目录、识别 CD2 挂载前缀、调用 gRPC、固定 115 账号、跨重启保存快照，并以稳定事件 ID 向 process 的 `event` 操作投递变化。

安装页仍会展示“原生常驻进程”、发布者、包签名、后台行为、申请的接口和外部来源。沙箱限制不替代对发布者和签名包的判断，安装者应只批准确实需要的 Host Call。
