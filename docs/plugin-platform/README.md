# DIAN115 插件平台（Plugin API v2 设计）

插件运行在 DIAN115 主进程的 WASM 沙箱中。开发者只需要提供 `manifest.json`、声明式 `ui/schema.json` 和 `runtime/plugin.wasm`；不能注入 Vue/HTML/JavaScript，也不需要 Docker、HTTP 服务或独立凭据。

## 核心模型

插件通过唯一的通用 Host ABI 调用宿主：

```text
WASM dian115.host_call(method, path, headers, body)
  -> 宿主登记的接口目录 -> 真实 DIAN115 Handler -> 原样 JSON 响应
```

插件不再实现账号转换、预览转换或文件/订阅专用 DTO 等中间层。主项目接口使用 `method + path`；调用外部网站接口时使用同一个 `host_call` 的 `method + https://origin/path`。宿主只检查安装时批准的接口/来源、请求边界、幂等、审计和敏感接口黑名单。未登记接口即使属于同一类别也会被拒绝。

## 安装授权

manifest 的 `permissions.apis` 声明完整方法和路径，`permissions.network` 声明外部域名/IP。安装页逐项展示方法、路径、用途、读写风险、外部来源和地址快照；用户整体同意后才安装。新增接口、扩大路径或新增域名时必须重新确认。宿主永远不向插件暴露 Cookie、密码、JWT、115 凭据、TMDB Key 或代理秘密。

## 已登记接口类别

- 115：账号选项、离线/转存、任务查询；支持主账号、备用号池和指定备用账号。
- 文件/CD2：目录、文件管理、移动/整理和监控；CD2 路径由宿主通过 CD2 gRPC 执行，插件不接触 socket、Token 或挂载绝对路径。
- 订阅：读取、创建、更新和取消普通订阅、聚合订阅及 PT 订阅；执行记录中的可复用下载地址会由宿主移除。
- 订阅边界：PT 搜索结果、站点/RSS、全局订阅设置和下载器管理接口不在插件目录中，插件不会取得 PT Cookie、API Key、Token、passkey、私密 RSS 地址或下载器凭据。
- TMDB：搜索、趋势、电影/剧集详情等查询由宿主执行，使用系统配置的凭据、代理和 TMDB 缓存；插件不能直连 TMDB。
- 通知：独立的插件通知类型，可反馈任务结果到已配置的 Telegram 通知通道。
- 调度/事件/KV/日志：安装实例隔离，支持定时任务、目录轮询、事件投递、独立日志和大小/保留期限制。

接口是否可用以当前版本的接口目录和 [OpenAPI](openapi-v1.yaml) 为准；文档没有列出的路径不能猜测或调用。

## 文档

- [开发指南](developer-guide.md)：ABI、manifest、UI、调用示例和发布流程。
- [manifest schema](manifest.schema.json)、[UI schema](ui-schema-v1.schema.json)：机器校验定义。
- [OpenAPI](openapi-v1.yaml)：Host API 的逻辑投影；WASM 通过 `host_call` 调用，不发起网络请求。

官方市场索引位于 `madbrolab/dian115` 的 `plugin-market/index.json`；用户也可以添加自己的 HTTPS 索引仓库。插件市场只发布插件包和元数据，不接受源码上传到 DIAN115 项目。
