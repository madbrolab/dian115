---
name: dian115-plugin-dev
description: 创建、修改、测试、排错和签名打包 DIAN115 第三方 .d115p 插件，使用公开 SDK、独立 HTML 页面和 WASM。适用于插件作者的独立项目；DIAN115 随主程序编译的内置功能不属于此流程。
---

# DIAN115 第三方插件开发

以用户要求的功能为目标，交付轻量、可构建、可安装、可排错的插件。全部资料和工具随 skill 安装，不依赖 DIAN115 主项目源码、数据库、MCP 或付费服务。用户只要求分析时先给方案；要求开发时持续完成实现及可执行的验证。

以下路径均相对本 SKILL.md 所在目录；在命令中将 `<skill>` 替换为实际绝对路径。不要假定 skill 位于项目内，也不要修改已安装 skill 的模板来实现用户插件。

## 开始工作

1. 新建项目：确认功能、目标宿主版本、插件 ID、名称和作者；能从上下文推断的直接采用。用几句话说明所需 API、持久数据、副作用和执行方式。只询问影响实现的缺失信息。
2. 修改已有插件：先读现有 Manifest、契约锁、业务和测试，保留作者代码与已授权选择；不要重新初始化或自动替换其 SDK。修旧代码应按当前协议处理，无需加入旧平台兼容层。
3. 新项目运行 `node <skill>/scripts/verify.mjs` 与 `node <skill>/scripts/doctor.mjs`。doctor 只检查，不安装工具、不连接宿主。缺少工具时继续不依赖它的工作，并明确阻塞哪项验证。
4. 默认使用最小模板：

```bash
node <skill>/scripts/init.mjs --dir <new-directory> --id <publisher.plugin> --name <插件名称> --publisher <作者名称>
```

目标必须不存在。生成根目录即插件项目；`.dian115/` 内是固定版本的公开协议、SDK 和检查工具。默认无业务 API/网络权限、无事件/任务/调度、非驻留。仅在用户明确需要能力演示项目时使用 `--template complete`；其中包含真实副作用示例和较多权限，需要按业务删减。

## 按任务读取资料

先读 [实现路线](references/development.md)，然后只加载相关专项：

- 选择接口、HTTP 错误、网络和授权： [接口和权限](references/apis.md)。`node <skill>/scripts/api.mjs --query <词语> [--method GET] [--json]` 检索固定目录；精确请求/响应读 [OpenAPI](assets/public-kit/openapi-v1.yaml)，不要只看接口标题。
- 站点登录、自动 Set-Cookie、多账号会话、CookieCloud 与按需 FlareSolverr： [HTTP 会话](references/http.md)。优先 HTTP，不为 Cookie 保活引入浏览器或常驻任务。
- 配置、并发写入、分页、凭据、卸载： [数据生命周期](references/storage.md)。
- 副作用、长任务、取消、异常退出恢复： [调用与恢复](references/recovery.md)。
- 页面、受管偏好、主题、错误界面： [页面接入](references/ui.md)。
- 首开/唤醒/失败排查、测试、签名和交付： [验证与发布](references/validation.md)。
- 特殊 Telegram、watch、cron、resident 功能：从 [开发者指南](assets/public-kit/developer-guide.md) 定位相应公开协议，再查看 [完整示例](assets/public-kit/examples/complete-plugin/README.md) 的相关实现，按需摘取。

## 实现中始终保持的约束

- 每个包同时包含签名 HTML 页面与 `dian115:wasm@1` WASM。页面用 SDK connectPluginPage 连接宿主，自行挂载应用和 Provider，不共享宿主框架实例；业务网络经 action → WASM → Host Call。
- 公开契约和能力声明是接口依据。缺失能力要说明，不能猜私有端点、读取宿主数据库、取消 sandbox 或要求主项目源码。
- 支持直接填写账号密码、Cookie 和安装后自定义地址，使用 PostForm / SetCookieHeader / sites。CookieCloud 是可选来源；不因自有凭据字段名拒绝业务，不强制每个新地址改包重装。秘密不写普通页面偏好或日志。
- 初始化和 state 查询不发送通知、不提交业务写入。页内变量/guest 全局变量会随页面或模块释放；恢复记录读取完毕后才允许相关写入。
- 发送副作用前持久保存稳定 invocation ID；普通输入可一并保存，密码/Cookie 使用 transientInput，仅重新提供原字段，由宿主哈希核对；结果不确定时核对事实，重试复用原编号和幂等键。取消和卸载不能撤销已完成的外部业务。
- 长任务使用公开宿主任务能力；需要恢复时实现只读核对回调。按需加载、有界批次/分页/预览优先，常驻只用于确有持续执行需要的功能。
- 卸载清空插件数据，重装为空。重启、休眠和停用保留持久配置。业务格式版本与 ETag 并发版本分别处理。
- Manifest 与市场条目的权限、身份、版本保持一致；只声明实际使用的方法、路径和网络需求。目标主机文件路径按 Linux 语义处理，远端文件名保持不变。

## 验证和交付

正常流程为：相关单测 → UI/WASM 构建 → `npm run check` → 签名打包；根据修改范围选测试，避免为了形式重跑无关环境检查。`npm run check:contract` 可在没有构建时检查声明；它不代表构建或宿主验收通过。

生成项目支持：

```bash
npm ci
npm test
# 最小模板的本机协议单测
go test ./runtime
npm run build
npm run check
# 通过外部文件传入固定作者密钥；首次本地创建再显式添加 -- --generate-key
DIAN115_PLUGIN_SIGNING_KEY=/absolute/path/outside/project/publisher.pem npm run package
```

按 [验证与发布](references/validation.md) 区分静态检查、mock、真实宿主验收。真实宿主不可用时列出未执行项；不要把模拟响应或合同检查说成实际 API 全部成功。宿主操作、外部业务写入、上传和市场发布均限于用户已授权的范围；本地代码、测试和打包按任务授权连续完成。

最终给出安装包/源码位置、安装步骤、权限用途、数据及卸载说明、已执行测试与剩余验证。发布私钥留在项目外；不提交 build、releases、密钥或宿主实现。此 skill 的版本和内容摘要见 [contract-lock.json](contract-lock.json)。开发中使用本地固定快照；更新由维护者显式发布，不能静默切换 main。
