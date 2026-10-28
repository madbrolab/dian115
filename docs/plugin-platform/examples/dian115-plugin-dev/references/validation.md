# 验证、排错和发布

## 三类证据

1. **声明/静态**：`npm run check:contract`、TypeScript、相关公开合同检查。声明正确不证明 runtime 能构建或 API 实际可调用。
2. **构建/单测**：npm ci、npm test、go test ./runtime、npm run build、npm run check。SDK 修改时再在 .dian115/examples/sdk 运行 Go 测试。测试选择覆盖可观察行为，不仅匹配源码文字。
3. **真实宿主**：安装签名包，验证首次打开/配置保存/闲置唤醒/错误恢复/重复调用/卸载重装；涉及副作用和长任务时覆盖响应丢失、核对、取消及重启恢复。按任务授权在测试数据上运行；报告 mock 与真实宿主的分别结果。

没有 TinyGo/Binaryen 则不能声称 WASM 构建通过；没有宿主则明确该类未测。默认基线是构建与相关单测/合同检查，不要求为每个插件准备真实数据库集群、压力环境或容器构建。

## 排错顺序

记下宿主/插件版本、invocation_id/job_ref、时间和 diagnostic_id，在插件中心诊断页/有界日志关联同一次调用。空闲按需释放不是崩溃；runtime_backoff 时先读最后错误，不反复重启。永久包错误需修包；资源门限不足与业务 HTTP 错误分别处理。HTTP 404/412/413、限流、权限拒绝、回执冲突等按公开 Problem 语义处理。完整错误矩阵见 public-kit/troubleshooting.md。

## 签名

使用 Node 20+、Go 1.25+，快照记录的已实测 TinyGo/Binaryen 版本见 contract-lock.json。doctor 检查 PATH 或 TINYGO/WASMOPT，缺少工具不会自行下载安装。WASM 构建使用 TinyGo reactor，不链接 encoding/json；限制以 wasm-runtime-v1.md 为准。

生成项目的 package 命令要求显式 DIAN115_PLUGIN_SIGNING_KEY，解析符号链接后必须在项目外。首次本地生成需明确 `-- --generate-key`；持续发布沿用同一作者密钥，CI 通过外部 secret 文件注入。不得打印密钥或打包进源码/安装包。

包和市场条目的 ID、版本、权限与签名身份一致。发布前核对包 SHA-256、兼容范围、下载地址和权限理由。example.invalid 仅用于本地导入占位，不是可发布地址。包 URL、源码托管、市场提交及真实宿主安装遵守用户已授权范围，skill 本身不授予额外权限。

DIAN115 官方公共仓库只允许协议、Schema、公开 SDK、第三方示例与黑盒工具；示例代码放 docs/plugin-platform/examples/，发布前运行官方 verify-public-surface。其他作者的独立插件仓库按自己的规则组织源码；不能把官方仓库根源码禁区误套到作者自己的 go.mod。生成物、密钥和主项目实现始终不进入官方公共资料。

## 验收提示词

试用 skill 时用可执行需求验证产物，记录执行命令与实际结果：

- “创建只有配置偏好和状态读取的插件”：零业务 API/网络权限，非驻留，初始化不写业务。
- “增加用户手动发送通知”：仅新增对应权限，意图先保存，丢失响应复用原 ID。
- “增加可恢复分页批处理”：保存 start ID/job_ref，检查点有界，恢复只读核对，取消后不续跑。
- “修复配置读取失败”：显示失败，不能默认空值覆盖；相关写入暂停直到重读成功。
- “修改已有插件并移除 watch”：保留业务和身份，删除无用动作/事件/权限，合同仍通过。
- “只分析内置插件功能”：识别为其他接入范围，不生成 .d115p。

这些是行为验收向量，不意味着未运行的 AI 试用已通过。自动测试覆盖脚本/生成物，人工或独立会话试用另行如实记录。
