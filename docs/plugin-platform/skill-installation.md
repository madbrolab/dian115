# 开发者 Skill v3

完整目录位于 `examples/dian115-plugin-dev/`。将该目录安装到自己的 Codex/兼容技能目录，或让 Skill Installer 从公开仓库对应路径安装。必须复制 SKILL.md、scripts、agents 与 assets/public-kit；不需要主项目源码。

使用：`使用 $dian115-plugin-dev 开发一个可以安装后自定义站点、搜索资源并交给宿主转存的插件。`

skill 携带固定版本公开协议、SDK、完整 API 测试台和黑盒工具。同步脚本 `node docs/plugin-platform/conformance/sync-dev-skill.mjs` 更新内容，`--check` 核对摘要。使用本仓库当前版本的完整目录，勿混用旧版协议和 SDK。
