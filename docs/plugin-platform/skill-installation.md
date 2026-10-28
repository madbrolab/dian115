# 第三方插件开发 Skill

`dian115-plugin-dev` 帮助 AI 创建、修改、测试和签名打包 DIAN115 第三方 `.d115p` 插件。安装包自带固定版本的公开协议、SDK、最小模板、完整能力示例和黑盒检查工具；不需要 DIAN115 主项目源码或 MCP 服务。

## 安装

在 Codex 中使用内置 Skill Installer，发送：

```text
$skill-installer 从 https://github.com/madbrolab/dian115/tree/main/docs/plugin-platform/examples/dian115-plugin-dev 安装 dian115-plugin-dev
```

团队也可将该完整目录复制到插件项目的 `.agents/skills/dian115-plugin-dev/`；个人手动安装可放在 `~/.agents/skills/dian115-plugin-dev/`。避免同时安装同名的个人和项目副本。以上路径及 Skill Installer 用法见 [OpenAI 官方技能说明](https://learn.chatgpt.com/docs/build-skills)。新 skill 未显示时重新打开会话或重启客户端。

首次安装可使用 main 获取已发布目录；需要可重复安装时，将链接中的 main 替换为发布提交号。安装会同时取得目录内所有 references/scripts/assets，不能只复制 SKILL.md。其他支持 SKILL.md 的客户端可使用同一目录，安装入口按各客户端文档操作；本 skill 不依赖特定 MCP。

## 使用

```text
使用 $dian115-plugin-dev 开发一个 DIAN115 第三方插件：
用户手动选择目录，分页检查文件并发送汇总通知。
提供配置、任务进度、取消和异常退出后的核对恢复。
插件 ID 为 dev.example.file-check，作者为 Example。
```

开发者说明需求、目标宿主版本和必要测试引用即可；AI 会先选择公开能力、数据结构和执行方式，再开发与验证。只要求分析时保持分析范围；已有插件按现有结构修改。

也可单独使用工具，以下 `<skill>` 表示安装后的绝对目录：

```bash
node <skill>/scripts/verify.mjs
node <skill>/scripts/doctor.mjs
node <skill>/scripts/api.mjs --query storage --method GET
node <skill>/scripts/init.mjs --dir ./my-plugin --id dev.example.my-plugin --name 我的插件 --publisher Example
```

默认最小模板无业务权限/网络权限、无后台轮询和任务，演示受管偏好及只读 WASM 状态。显式 `--template complete` 提供通知、任务恢复、watch 和 Telegram 等能力示例，作者需删减演示权限及替换占位地址。

## 版本、验证和发布

`contract-lock.json` 固定资源 SHA-256、来源基准提交、接口数量和实测工具链；初始化后复制到项目 `.dian115/`。正常开发离线读取该快照，环境检查不自动安装依赖或切换协议。

新项目自带 npm test、Go runtime 单测、UI/WASM 构建、合同检查和项目外签名保护。目标环境需 Node 20+、Go 1.25+、TinyGo 与 Binaryen；已验证版本见 skill 锁。doctor 缺少工具时非零退出，不会声称构建就绪。

静态检查、模拟预览、实际宿主验收分别记录。实际宿主验收包含首次打开、持久化、休眠唤醒、异常恢复、重复调用和卸载清空；有外部副作用时在已授权的测试数据上运行。离线 mock 不代表业务 API 全部通过。

作者密钥保存在项目外，由 DIAN115_PLUGIN_SIGNING_KEY 指定；首次生成需明确 --generate-key。包位于项目 releases/，通过插件中心的“仓库与开发 → 导入本地插件”安装。卸载清空插件数据，取消/卸载不撤销已完成的外部业务。

## 维护者

唯一协议/SDK/完整示例维护源仍在本目录原有位置。更新它们后执行：

```bash
node docs/plugin-platform/conformance/sync-dev-skill.mjs
node docs/plugin-platform/conformance/sync-dev-skill.mjs --check
node --test docs/plugin-platform/examples/dian115-plugin-dev/scripts/scaffold.test.mjs
```

sync 的输入为明确白名单，不读取主项目实现；生成 public-kit 和摘要锁。检查工具自己的诊断字符串按同一公开检查器副本识别，不放宽源码、密钥或构建产物的发布边界。CI 验证快照一致性、初始化行为，以及生成项目的 UI 和单测。

Skill 源码与第三方模板放在 `docs/plugin-platform/examples/dian115-plugin-dev/`，公开提交前继续运行 `node docs/plugin-platform/conformance/verify-public-surface.mjs`。skill 目录中不提交 node_modules、构建产物、安装包或签名私钥。
