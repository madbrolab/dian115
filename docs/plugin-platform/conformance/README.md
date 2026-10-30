# v3 检查工具

- `node project-check.mjs <插件目录>`：检查源码清单、入口、路径、任务和触发器；调用权限由宿主在安装和运行时检查，本地通过不代表一定可安装。
- `node pack.mjs <插件源码目录> <目录外的插件.dian115p>`：无需安装依赖，生成可读源码插件包。
- `node --test docs/plugin-platform/conformance/*.test.mjs`：SDK 路径隔离与示例恢复语义测试。
- `node annotate-openapi.mjs` / `--check`：把[字段词汇表](api-glossary.json)与[常用接口示例](api-cookbook.json)写入 OpenAPI；示例先按契约校验，不符合即失败。
- `node generate-reference.mjs` / `--check`：由 OpenAPI 生成接口速查与逐接口参考（参数、字段、调用写法、示例）。
- `node generate-sdk-types.mjs` / `--check`：生成 SDK 的 `host-api.d.ts`，`ctx.api` 按路径推断请求体与响应类型。
- `npx -p typescript tsc --noEmit --strict --module esnext --moduleResolution bundler --target es2022 sdk-types.check.ts`：类型推断回归检查（需要 TypeScript）。
- `node openapi-check.mjs`：公开 OpenAPI 引用完整性。
- `node runtime-check.mjs <URL> <插件ID> <仓库外Cookie文件>`：已登录宿主只读黑盒检查，不启动任务或外部动作。
- `node sync-dev-skill.mjs` / `--check`：更新或检查 skill 携带的公开开发材料。
- `node verify-public-surface.mjs`：独立公开仓库中的发布边界检查；私有主项目本身包含源码，不能作为公开提交目标。

契约由宿主处理器自动核对：私有主项目中的 `go run ./cmd/pluginopenapi`（`-write` 补齐）与 `go test ./cmd/pluginopenapi` 在路由、请求字段、查询参数或响应结构漂移时失败；它不随公开材料发布。更新顺序：`pluginopenapi -write` → `annotate-openapi.mjs` → `generate-reference.mjs` → `generate-sdk-types.mjs` → `sync-dev-skill.mjs`。

工具只能验证相应检查点。实际登录、验证码、外部通知与 CD2 业务需要用户提供测试环境后显式验证。
