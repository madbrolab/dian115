# DIAN115 插件平台（Plugin API v2）

插件安装并运行在 DIAN115 当前 Docker 容器内，不需要额外 Docker、HTTP 服务、端口或独立凭据。开发者可以选择轻量的 `wasm` 运行时，也可以选择由 DIAN115 启动和监管的常驻 `process` 运行时；两者使用同一套声明式 UI、Host API、定时任务、事件、目录监控、通知、KV 和独立日志。

`process` 是受宿主管理的 Linux 原生进程：启用时自动启动，禁用、更新、卸载或 DIAN115 退出时停止，异常退出时按宿主策略退避重启。宿主会通过 Linux Landlock 与 seccomp 施加 fail-closed 沙箱：插件包目录只读/可执行，插件私有数据目录可读写，直连网络、越权文件访问和危险系统调用被拒绝；插件可以启动包内子进程，但子进程继承同一限制。115、TMDB、订阅、文件/CD2、目录监控、外部网络和通知都必须走安装时声明并获批的 Host API。

## 核心模型

插件通过唯一的通用 Host Call 调用宿主：

```text
WASM import 或 process stdio host.call
  -> 宿主登记的 METHOD + path -> 真实 DIAN115 Handler -> JSON 响应
```

插件不再实现账号转换、预览转换或文件/订阅专用 DTO 等中间层。主项目接口使用 `method + path`；调用外部网站接口时把完整 HTTPS URL 放在同一个 `path` 字段。宿主只检查安装时批准的接口/来源、请求边界、幂等、审计和敏感接口黑名单。未登记接口即使属于同一类别也会被拒绝。

## 安装授权

manifest 的 `permissions.apis` 声明完整方法和路径，`permissions.network` 声明外部域名/IP。安装页逐项展示方法、路径、用途、读写风险、外部来源和地址快照；用户整体同意后才安装。新增接口、扩大路径、新增域名或切换到原生进程时必须重新确认。通过 Host Call 调用时，宿主永远不向插件暴露 Cookie、密码、JWT、115 凭据、TMDB Key 或代理秘密；原生进程也只能通过获批 Host API 使用这些能力。若当前 Linux/Docker 环境无法启用沙箱，DIAN115 会拒绝启动 process 插件。

## 已登记接口类别

- 115：账号选项、离线/转存、任务查询；支持主账号、备用号池和指定备用账号。
- 文件/CD2：目录、文件管理、移动/整理和持久化监控；CD2 挂载前缀由宿主通过 CD2 gRPC 扫描和操作，非 CD2 路径走本地挂载，插件不接触 CD2 socket 或 Token。
- 订阅：读取、创建、更新和取消普通订阅、聚合订阅及 PT 订阅；执行记录中的可复用下载地址会由宿主移除。
- 订阅边界：PT 搜索结果、站点/RSS、全局订阅设置和下载器管理接口不在插件目录中，插件不会取得 PT Cookie、API Key、Token、passkey、私密 RSS 地址或下载器凭据。
- TMDB：搜索、趋势、电影/剧集详情等查询由宿主执行，使用系统配置的凭据、代理和 TMDB 缓存；插件不能直连 TMDB。
- 通知：独立的插件通知类型，可反馈任务结果到已配置的 Telegram 通知通道。
- 调度/事件/KV/日志：安装实例隔离；插件页面关闭后，常驻进程、定时任务、目录监控和事件投递继续运行；日志有大小、条数和保留期限制。

接口是否可用以当前版本的接口目录和 [OpenAPI](openapi-v1.yaml) 为准；文档没有列出的路径不能猜测或调用。

## 文档

- [开发指南](developer-guide.md)：manifest、UI、调用示例、监控和发布流程。
- [进程运行时协议](process-runtime-v1.md)：同容器常驻进程、stdio 协议和生命周期。
- [manifest schema](manifest.schema.json)、[UI schema](ui-schema-v1.schema.json)：机器校验定义。
- [OpenAPI](openapi-v1.yaml)：Host API 的逻辑投影；插件通过 Host Call 调用，不需要连接 DIAN115 HTTP 端口。

官方市场索引位于 `madbrolab/dian115` 的 `plugin-market/index.json`；用户也可以添加自己的 HTTPS 索引仓库。插件市场只发布插件包和元数据，不接受源码上传到 DIAN115 项目。
