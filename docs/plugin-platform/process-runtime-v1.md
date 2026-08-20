# DIAN115 Process Runtime v1

`process` 运行时用于需要常驻循环、第三方原生库或主动后台任务的插件。可执行文件由 DIAN115 在当前 Docker 容器内直接启动和监管；它不是远程运行时，不监听端口，也不是额外的 Docker 服务。

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

`entry` 必须是包内相对路径，必须被 `integrity.json` 覆盖，并在 ZIP 中带可执行位。DIAN115 只在官方 Docker/Linux 平台执行该文件，并在安装时检查 ELF 架构与当前容器一致。建议使用静态链接 ELF，或把必需运行文件放入包内；沙箱只放开包目录和插件私有数据目录，不放开系统库目录。入口不得自行 daemonize 或脱离进程组。

## 2. 生命周期

| 时机 | 宿主行为 |
| --- | --- |
| DIAN115 启动或插件启用 | 启动入口，完成初始化握手后再接受 action/job/event |
| 插件页面关闭 | 进程继续运行，调度和监控不停止 |
| 进程异常退出 | 指数退避重启；连续失败进入熔断状态 |
| 插件禁用 | 停止新投递，发送关闭请求，随后终止整个进程组 |
| 插件更新 | 先停止旧进程；新包握手成功后才启用新版本 |
| 插件卸载或 DIAN115 退出 | 停止进程并回收子进程，不留下后台服务 |

运行状态会显示 `starting`、`running`、`backoff`、`failed` 或 `stopped`，以及 PID、启动时间、重启次数、最近退出码和最近错误。插件自己的 stderr 与结构化日志写入当前安装实例的独立日志，按 4 MiB、5000 条和 14 天限制裁剪。

## 3. stdio 帧

stdin/stdout 是全双工 JSON-RPC 2.0 通道。stdout 只能写协议帧；普通日志必须写 stderr 或调用 `host.log`。每帧使用 UTF-8 JSON 和 `Content-Length`，格式如下：

```text
Content-Length: <JSON 字节数>\r\n
Content-Type: application/json\r\n
\r\n
<JSON>
```

实现必须支持请求与响应交错：插件处理一次 `runtime.invoke` 时可以同步发起 `host.call`，宿主也可能并发发送多个 invocation。JSON-RPC `id` 在未完成请求中必须唯一。未知 method 应返回标准 `-32601`，坏参数返回 `-32602`；不得让单个错误终止读循环。

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

所有状态、动作、定时任务和目录事件统一使用 `runtime.invoke`，其中 `envelope` 与 WASM 的 `dian115_invoke` 完全相同：

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

`result` 是对应 state/action/job/event 契约要求的 JSON 对象。宿主使用现有持久化 delivery ledger；不确定投递会带相同 `invocation_id` 重试，插件必须按 ID 幂等处理。

停止时宿主发送 `runtime.shutdown`。插件应停止自己的新任务、关闭文件句柄并尽快响应；超过 `shutdown_timeout_ms` 后，宿主先终止进程组，再在宽限期后强制结束。

## 5. 插件调用宿主

插件通过 `host.call` 调用安装时批准的 Host API 或 HTTPS 来源：

```json
{
  "jsonrpc": "2.0",
  "id": "plugin_1",
  "method": "host.call",
  "params": {
    "method": "POST",
    "path": "/api/notifications/plugin",
    "headers": {"content-type": "application/json", "idempotency-key": "task-42-done"},
    "body_base64": "eyJsZXZlbCI6InN1Y2Nlc3MiLCJ0aXRsZSI6IuS7u+WKoeWujOaIkCIsImJvZHkiOiLlt7LlpITnkIYifQ"
  }
}
```

成功结果与 WASM Host Call 相同：

```json
{"jsonrpc":"2.0","id":"plugin_1","result":{"status":200,"headers":{"content-type":["application/json"]},"body_base64":"e30"}}
```

外部请求把完整 `https://...` URL 放在 `path` 字段。宿主执行权限匹配、代理选择、请求限制、审计和响应脱敏；不要在命令行参数、环境变量、stdout 或日志中保存账号 Cookie、Token 或其他凭据。

结构化日志使用 `host.log`：

```json
{
  "jsonrpc": "2.0",
  "method": "host.log",
  "params": {"level": "info", "message": "任务完成", "fields": {"job_ref": "job_01"}}
}
```

## 6. 运行环境与信任边界

工作目录和可写数据目录由宿主放在 `/config` 下的安装实例私有目录。宿主只传递运行所需的最小环境，不把 DIAN115 的数据库凭据、Cookie、JWT 或代理秘密作为环境变量传给插件。

process 插件在 DIAN115 宿主管理下运行，并受强制沙箱约束。宿主启动内部沙箱 helper 后先启用 `no_new_privs`，再应用 Landlock 文件系统规则和 seccomp 系统调用过滤，最后 exec 插件入口。包目录只读/可执行，插件私有数据目录可读写；直连网络、越权文件访问、挂载命名空间、ptrace、BPF、内核模块、fanotify 等危险能力会被拒绝。插件可以创建包内子进程，子进程继承同一沙箱；禁用或卸载时，DIAN115 会终止整个进程组。

沙箱不可用时按 fail closed 处理：DIAN115 拒绝启动 process 插件并记录健康状态错误。插件不得假设能读取宿主挂载目录、打开 socket、访问 CD2 gRPC、读取环境凭据或直连外部网站；115、文件/CD2、订阅、TMDB、目录监控、外部网络和通知都必须走安装时声明并获批的 `host.call`。

需要跨本地、CD2 和 115 的可靠目录监控时，应使用宿主 `/api/plugin-runtime/watches`，而不是自己轮询：宿主能识别 CD2 挂载前缀、调用 gRPC、固定 115 账号、跨重启保存快照，并用稳定事件 ID 重试投递。
