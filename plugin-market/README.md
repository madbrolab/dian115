# DIAN115 插件市场索引

官方市场入口是仓库根目录的 `plugin-market/index.json`。插件中心添加
`https://github.com/madbrolab/dian115` 时，会自动转换为该索引的 Raw URL。

当前市场对应 Plugin API v2，只收录由 DIAN115 在当前 Docker 容器内启动和监管的 Linux 常驻进程插件。
旧运行时插件不会继续出现在市场索引中；发布者必须先迁移为 process 包并重新签名。

自定义市场可以使用相同目录结构，也可以直接提供一个 HTTPS `index.json`
地址。索引中的相对 `package_url` 和 `icon_url` 会以索引最终 URL 为基准解析。

每个插件版本必须提供：

- 稳定的反向域名 `id` 和 SemVer `version`。
- HTTPS 或相对路径的 `.d115p` ZIP 包地址。
- `runtime` 必须披露 `kind=process`、`protocol=dian115:process@1`、`autostart=true` 和 `trust_level=isolated-process`，并与包内签名 Manifest 一致。`autostart=true` 表示启用插件后由宿主自动监管进程，不表示插件可以脱离宿主自行常驻。插件不需要额外 Docker、外部 HTTP 服务、端口或运行时 URL。
- process 插件是 DIAN115 托管的 Linux 原生进程，可常驻并启动包内子进程；宿主沙箱限制文件系统、网络 socket 和危险系统调用，HTTP/HTTPS（含本机、容器与局域网目标）以及 115、文件/CD2、订阅、TMDB、目录监控和通知均通过 Host API。
- 整个压缩包的小写 SHA-256。
- 安装页需要展示的 `permissions.apis`；每项必须包含方法、路径和用途 `reason`。`permissions.network` 不是网站白名单，只声明特定 HTTP/HTTPS 来源/方法的 `proxy_mode` 路由偏好；未声明地址默认跟随宿主规则，宿主强制代理域名优先。
- 115 接口的账号选择在宿主接口中完成；市场条目不再声明旧的 capability 分组。

安装器会再次读取包内根目录 `manifest.json`，要求插件 ID、版本、运行时类型/协议和接口/网络路由与
每项原因与索引一致。插件中心根据当前仓库快照生成
`consent_digest`，安装请求必须连同 `permissions_accepted: true` 原样回传；索引
变化后旧摘要失效，用户需要重新查看并整体同意。市场索引不能替代包校验，也不会
通过 Host Call 让插件获得 Cookie、管理员令牌、Telegram Bot Token 或数据库凭据。Telegram 命令和关键词由已启动插件通过进程协议动态注册，不写入市场索引，也不参与安装冲突检查；冲突由宿主在注册调用时拒绝。原生进程若沙箱不可用会拒绝启动；安装者仍应评估发布者、签名包、声明接口和网络路由偏好。

管理员也可以在插件中心直接导入完整的 `.d115p` 文件。此路径不需要市场索引，但仍执行完全相同的签名、完整性、Manifest、权限、运行时和 UI 校验，并要求管理员确认权限；导入包不会自动发布到本市场。

完整开发说明见 `docs/plugin-platform/developer-guide.md`。

市场仓库只接收插件索引、Schema、图标和插件作者发布地址，不接收 DIAN115 主项目源码、Docker 构建上下文、构建产物或私钥。公共发布边界和自动检查见 `docs/plugin-platform/publication-policy.md`。
