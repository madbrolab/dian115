# 实现路线

## 新建和修改

新建先用最小模板建立能够通过合同检查的 UI/WASM 闭环，再加入用户需要的能力。最小模板仅演示受管页面偏好与只读 runtime state；不自动连接业务 API。将业务数据放入 Host Storage 后再增添 GET/PUT 权限。需要复杂功能时阅读完整示例，不把全部示例动作和权限带入成品。

生成器参数包括 `--dir`、`--id`、`--name`、`--publisher`、`--version`、`--compatibility`；默认版本 1.0.0，宿主范围沿用快照的已验证范围。确认实际功能最低宿主要求后再收窄范围。`--template complete` 是显式的能力展示选择，不代表生产模板默认值。

现有项目先检查自己的锁和 SDK。对照目标宿主公开能力选择是否升级，先解决当前功能；不能为了套模板重写项目或改变签名身份。一次业务请求的恢复记录有未确认状态时，升级策略需明确其核对方式。

## 生成项目结构

- `index.html` 与 `src/main.ts`：正式页面入口，SDK 连接后自行挂载 `src/AppPage.vue`。只有开发模式独立窗口启用本地 mock，正式构建不带 mock。
- `runtime/logic.go`：可本机单测的协议分发；`runtime/main.go`：WASM ABI 适配。
- `manifest.template.json`、`market-entry.template.json`：相同身份、版本、权限。
- `.dian115/`：随项目提交的固定公开契约、SDK、检查工具和来源锁。根 go.mod 使用本地 replace，无需导入宿主模块。
- `scripts/build-runtime.mjs`、`scripts/package.mjs`：公开构建/签名实现；`scripts/sign.mjs` 限定密钥位于项目外。

页面与 guest 的业务格式要共同变更。一次状态读取产生一致的 state_version/强 ETag；未改变时可用 not_modified。状态读取失败仍保留页面错误和重试入口。

## 来源与更新

Skill 中 public-kit 由仓库的 `conformance/sync-dev-skill.mjs` 从明确白名单生成；canonical SDK、完整示例和协议仍只有一份维护源。模板自身的代码位于 assets/starter。contract-lock 记录 skill 版本、来源基准提交及每个资源 SHA-256；内容摘要标识确切快照，基准提交不是未来发布提交的自引用。

作者的项目 `.dian115/contract-lock.json` 记录初始化所用快照；运行 doctor/verify 不会改动它。升级时明确选择新 skill/契约版本、查看接口变化并测试原恢复状态，不自动拉取 main 或降级到私有接口。skill 安装为只读开发依赖，业务代码写到用户项目。

外部 HTTP、通知、文件监听、Telegram、定时和常驻的完整封套见 public-kit/developer-guide.md；需要哪个主题再读相应协议。不要引入额外数据库、服务或容器来代替已有 Host 能力，除非用户功能本身要求。
