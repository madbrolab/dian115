# DIAN115 插件平台（Plugin API v2）

插件安装并运行在 DIAN115 当前 Docker 容器内，不需要额外 Docker、HTTP 服务、端口或独立凭据。开发者可以选择轻量的 `wasm` 运行时，也可以选择由 DIAN115 启动和监管的常驻 `process` 运行时；两者使用同一套声明式 UI、Host API、定时任务、事件、目录监控、通知、KV 和独立日志，也都稳定支持 `state`、`action`、`job` 和 `event` 回调。

`process` 是受宿主管理和沙箱隔离的 Linux 原生进程，目前只支持 `linux/amd64` 与 `linux/arm64`。启用时自动启动，禁用、更新、卸载或 DIAN115 退出时停止，异常退出时按宿主策略退避重启。宿主要求 Landlock ABI 3 或更高版本并以 fail-closed 方式启动：包目录只读且可执行，插件私有 data 目录可读写但不可执行，其他宿主路径不可访问；seccomp 阻止直接创建或使用 socket。包内子进程继承相同限制。115、文件/CD2、TMDB、订阅、通知和外部 HTTPS 请求都只能通过安装时声明并获批的 Host Call，宿主凭据不会交给插件。

## 核心模型

插件通过唯一的通用 Host Call 调用宿主：

```text
WASM import 或 process stdio host.call
  -> 宿主登记的 METHOD + path -> 真实 DIAN115 Handler -> JSON 响应
```

插件不再实现账号转换、预览转换或文件/订阅专用 DTO 等中间层。主项目接口使用 `method + path`；调用外部网站接口时把完整 HTTPS URL 放在同一个 `path` 字段。宿主只检查安装时批准的接口/来源、请求边界、幂等、审计和敏感接口黑名单。未登记接口即使属于同一类别也会被拒绝。

## 安装授权

manifest 的 `permissions.apis` 声明完整方法和路径，`permissions.network` 声明外部域名/IP。安装页逐项展示方法、路径、用途、读写风险、外部来源和地址快照；用户整体同意后才安装。新增接口、扩大路径、新增域名或切换到原生进程时必须重新确认。通过 Host Call 调用时，宿主永远不向插件暴露 Cookie、密码、JWT、115 凭据、TMDB Key 或代理秘密。`process` 只有受支持的 Linux/Docker 架构可运行；它虽受强制沙箱限制，仍是签名包中的原生代码，用户应同时核对发布者、包签名和申请的 Host Call 权限。

## 已登记接口类别

- 115：账号选项、离线/转存、任务查询；支持主账号、备用号池和指定备用账号。
- 文件/CD2：目录、文件管理、移动/整理和持久化监控；CD2 挂载前缀由宿主通过 CD2 gRPC 扫描和操作，非 CD2 路径走本地挂载，插件不接触 CD2 socket 或 Token。
- 订阅：读取、创建、更新和取消普通订阅、聚合订阅及 PT 订阅；执行记录中的可复用下载地址会由宿主移除。
- 订阅边界：PT 搜索结果、站点/RSS、全局订阅设置和下载器管理接口不在插件目录中，插件不会取得 PT Cookie、API Key、Token、passkey、私密 RSS 地址或下载器凭据。
- TMDB：搜索、趋势、电影/剧集详情等查询由宿主执行，使用系统配置的凭据、代理和 TMDB 缓存；插件不能直连 TMDB。
- 通知：独立的插件通知类型，可反馈任务结果到已配置的 Telegram 通知通道。
- 调度/事件/KV/日志：安装实例隔离；插件页面关闭后，常驻进程、定时任务、目录监控和事件投递继续运行；日志有大小、条数和保留期限制。

接口是否可用以当前版本的接口目录和 [OpenAPI](openapi-v1.yaml) 为准；文档没有列出的路径不能猜测或调用。

## 推荐阅读顺序

1. [从空目录到安装成功](quickstart.md)：选运行时、写 manifest/UI、Docker/Linux 构建、建立开发市场并安装。
2. [开发指南](developer-guide.md)：平台能力、权限、多账号、文件/CD2、订阅、监控和发布原则。
3. [运行时与回调契约](runtime-contract-v1.md)：WASM ABI、state/action/job/event/health envelope、Host Call、幂等与超时。
4. [Process Runtime v1](process-runtime-v1.md)：同容器沙箱进程、JSON-RPC stdio、文件/网络边界和生命周期。
5. [声明式 UI 开发手册](ui-development-guide.md)：state/source、表单与 row action、动态 picker、主题、布局和完整工作台示例。
6. [Host API 参考](host-api-reference.md)与 [OpenAPI](openapi-v1.yaml)：115、文件/CD2、订阅、TMDB、通知、KV/storage 和 watch 的请求响应。
7. [打包、完整性与签名](packaging-signing.md)：Ed25519、RFC 8785 JCS、ZIP 约束及可复制的 Linux 工具。
8. [错误码与调试](errors-debugging.md)：四层错误、重试、日志限制和常见故障。
9. [可安装示例](examples/README.md)：无源码的签名 WASM 包和可直接添加的开发市场。

机器校验文件包括 [manifest schema](manifest.schema.json)、[UI schema](ui-schema-v1.schema.json)、[integrity schema](integrity.schema.json)、[signature schema](signature.schema.json) 和[市场 schema](../../plugin-market/index.schema.json)。插件通过 Host Call 使用 OpenAPI 中的逻辑接口，不需要也不能连接 DIAN115 HTTP 端口。

官方市场索引位于 `madbrolab/dian115` 的 `plugin-market/index.json`；用户也可以添加自己的 HTTPS 索引仓库。插件市场只发布插件包和元数据，不接受源码上传到 DIAN115 项目。
