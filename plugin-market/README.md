# DIAN115 插件市场索引

官方市场入口是仓库根目录的 `plugin-market/index.json`。插件中心添加
`https://github.com/madbrolab/dian115` 时，会自动转换为该索引的 Raw URL。

当前市场对应 Plugin API v1，只收录由 DIAN115 主进程加载的进程内 WASM 插件。

自定义市场可以使用相同目录结构，也可以直接提供一个 HTTPS `index.json`
地址。索引中的相对 `package_url` 和 `icon_url` 会以索引最终 URL 为基准解析。

每个插件版本必须提供：

- 稳定的反向域名 `id` 和 SemVer `version`。
- HTTPS 或相对路径的 `.d115p` ZIP 包地址。
- 包内必须包含 `runtime.kind=wasm` 的 WASM 入口；插件由 DIAN115 主进程加载，不需要 Docker、外部 HTTP 服务或运行时 URL。
- 整个压缩包的小写 SHA-256。
- 安装页需要展示的 `capabilities`；每项必须是包含 `capability` 和非空
  `reason` 的对象，不能使用字符串简写，也没有 required/optional 分组。
- 声明 `accounts.115.use` 时必须提供非空 `account_access`；可选值为
  `main`、`backup_pool` 和 `backup_select`。

安装器会再次读取包内根目录 `manifest.json`，要求插件 ID、版本、`runtime.kind=wasm`、能力类别和
每项原因、115 账号访问模式与索引一致。插件中心根据当前仓库快照生成
`consent_digest`，安装请求必须连同 `permissions_accepted: true` 原样回传；索引
变化后旧摘要失效，用户需要重新查看并整体同意。市场索引不能替代包校验，也不会
让插件获得 Cookie、管理员令牌或数据库访问能力。

完整开发说明见 `docs/plugin-platform/developer-guide.md`。
