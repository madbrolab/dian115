# DIAN115 插件市场索引

官方市场入口是仓库根目录的 `plugin-market/index.json`。插件中心添加
`https://github.com/madbrolab/dian115` 时，会自动转换为该索引的 Raw URL。

当前市场对应 Plugin API v2，可收录由 DIAN115 加载的进程内 WASM 插件，以及由 DIAN115 在当前 Docker 容器内启动和监管的 Linux 常驻进程插件。
当前收录的“多账号转存助手”1.0.4 直接调用获批的 115、插件存储与插件通知接口。

自定义市场可以使用相同目录结构，也可以直接提供一个 HTTPS `index.json`
地址。索引中的相对 `package_url` 和 `icon_url` 会以索引最终 URL 为基准解析。

每个插件版本必须提供：

- 稳定的反向域名 `id` 和 SemVer `version`。
- HTTPS 或相对路径的 `.d115p` ZIP 包地址。
- `runtime` 必须披露 `kind`、`protocol`、`autostart` 和 `trust_level`，并与包内签名 manifest 完全一致。插件使用 `wasm` 或 `process`，都不需要额外 Docker、外部 HTTP 服务、端口或运行时 URL。
- `process` 条目必须声明 `trust_level=isolated-process`；这是市场协议中的运行时披露值。当前仅支持 `linux/amd64` 与 `linux/arm64`。安装页会提示它是 DIAN115 托管的沙箱 Linux 原生进程，可常驻并启动包内子进程；包树只读可执行、私有 data 可读写不可执行，其他宿主路径与直接 socket/网络不可用，子进程继承相同限制。115、文件/CD2、TMDB、订阅、通知和外部 HTTPS 只能走声明并获批的 Host Call。
- 整个压缩包的小写 SHA-256。
- 安装页需要展示的 `permissions.apis` 和 `permissions.network`；每项必须包含
  方法/路径或来源/方法、用途 `reason`，网络项必须显式填写 `proxy_mode`。
- 115 接口的账号选择在宿主接口中完成；市场条目不再声明旧的 capability 分组。

安装器会再次读取包内根目录 `manifest.json`，要求插件 ID、版本、运行时类型/协议、接口/网络权限和
每项原因与索引一致。插件中心根据当前仓库快照生成
`consent_digest`，安装请求必须连同 `permissions_accepted: true` 原样回传；索引
变化后旧摘要失效，用户需要重新查看并整体同意。市场索引不能替代包校验，也不会
通过 Host Call 让插件获得 Cookie、管理员令牌或数据库凭据。process 虽由 Landlock ABI 3+ 与 seccomp fail-closed 隔离，仍是容器内原生代码；安装者应评估发布者、签名包、后台行为、声明接口和外部来源。

推荐从 [`docs/plugin-platform/quickstart.md`](../docs/plugin-platform/quickstart.md) 开始；完整平台说明见 [`docs/plugin-platform/README.md`](../docs/plugin-platform/README.md)，签名与 ZIP 规则见 [`docs/plugin-platform/packaging-signing.md`](../docs/plugin-platform/packaging-signing.md)。每次包内容变化都必须提高版本、使用新包文件名并更新 SHA-256，不能覆盖同版本 URL。
