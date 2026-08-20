# DIAN115 插件市场索引

官方市场入口是仓库根目录的 `plugin-market/index.json`。插件中心添加
`https://github.com/madbrolab/dian115` 时，会自动转换为该索引的 Raw URL。

当前市场对应 Plugin API v2，可收录由 DIAN115 加载的进程内 WASM 插件，以及由 DIAN115 在当前 Docker 容器内启动和监管的 Linux 常驻进程插件。
当前收录的“多账号转存助手”1.0.3 直接调用获批的 115、插件存储与插件通知接口。

自定义市场可以使用相同目录结构，也可以直接提供一个 HTTPS `index.json`
地址。索引中的相对 `package_url` 和 `icon_url` 会以索引最终 URL 为基准解析。

每个插件版本必须提供：

- 稳定的反向域名 `id` 和 SemVer `version`。
- HTTPS 或相对路径的 `.d115p` ZIP 包地址。
- `runtime` 必须披露 `kind`、`protocol`、`autostart` 和 `trust_level`，并与包内签名 manifest 完全一致。插件使用 `wasm` 或 `process`，都不需要额外 Docker、外部 HTTP 服务、端口或运行时 URL。
- `process` 条目必须声明 `trust_level=isolated-process`；安装页会提示它是 DIAN115 托管的 Linux 原生进程，可常驻和启动包内子进程，但由宿主沙箱限制文件系统、直连网络和危险系统调用，所有业务能力仍需走获批 Host API。
- 整个压缩包的小写 SHA-256。
- 安装页需要展示的 `permissions.apis` 和 `permissions.network`；每项必须包含
  方法/路径或来源/方法、用途 `reason`，网络项可声明 `proxy_mode`。
- 115 接口的账号选择在宿主接口中完成；市场条目不再声明旧的 capability 分组。

安装器会再次读取包内根目录 `manifest.json`，要求插件 ID、版本、运行时类型/协议、接口/网络权限和
每项原因与索引一致。插件中心根据当前仓库快照生成
`consent_digest`，安装请求必须连同 `permissions_accepted: true` 原样回传；索引
变化后旧摘要失效，用户需要重新查看并整体同意。市场索引不能替代包校验，也不会
通过 Host Call 让插件获得 Cookie、管理员令牌或数据库凭据。原生进程若沙箱不可用会拒绝启动；安装者仍应评估发布者、签名包、声明接口和外部来源。

完整开发说明见 `docs/plugin-platform/developer-guide.md`。
