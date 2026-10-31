# 开发者 Skill v3

完整目录位于 `examples/dian115-plugin-dev/`。将该目录安装到自己的 Codex/兼容技能目录，或让 Skill Installer 从公开仓库对应路径安装。必须复制 SKILL.md、scripts、agents 与 assets/public-kit；不需要主项目源码。

开发：`使用 $dian115-plugin-dev 开发一个可以安装后自定义站点、搜索资源并交给宿主转存的插件。`

审查：`使用 $dian115-plugin-dev 审查这个插件有没有恶意代码：/绝对路径/插件.dian115p`

脚本都在 `scripts/` 下，只依赖 Node.js 18 以上：

| 脚本 | 作用 |
| --- | --- |
| `init.mjs <绝对目录> <插件ID> [--template starter|bot|daemon|webhook|lab] [--name 名称] [--author 作者]` | 从模板创建插件 |
| `check.mjs <目录> [--pack <输出.dian115p>]` | 结构检查、恶意代码扫描，可选打包 |
| `audit.mjs <目录或.dian115p> [--json]` | 只读扫描，不运行插件 |

skill 携带固定版本公开协议、SDK、完整 API 测试台和黑盒工具。同步脚本 `node docs/plugin-platform/conformance/sync-dev-skill.mjs` 更新内容，`--check` 核对摘要。使用本仓库当前版本的完整目录，勿混用旧版协议和 SDK。
