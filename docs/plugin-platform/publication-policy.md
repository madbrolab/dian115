# 插件平台公开发布边界

本项目的 GitHub 公共仓库只公开第三方插件开发所需的协议、Schema、OpenAPI、完整示例、市场索引格式和黑盒联调工具。**主项目源码、构建上下文、部署密钥和生产运行资产永远不得上传到 GitHub。**

这是一条长期规则，不因插件开发、问题排查、版本发布、CI 调试或任何其他请求而放宽。插件开发者不需要主项目源码；宿主实现通过下面的公开契约和运行时黑盒行为提供兼容性边界。

## 允许公开的内容

- `docs/plugin-platform/` 下的插件协议、JSON Schema、OpenAPI、主题契约、完整插件示例和 `conformance/` 黑盒工具；
- `plugin-market/` 下的市场索引 Schema、索引、市场说明和插件图标；
- 根目录使用说明、贡献规则、版本说明、在线规则和截图等非源码材料；
- 第三方插件示例自身的源码。示例源码只能位于 `docs/plugin-platform/examples/`，不能混入主项目目录。

## 永久禁止公开的内容

以下路径和同类文件不得出现在公共 GitHub 分支、插件市场仓库、文档压缩包、示例包或发布附件中：

```text
cmd/
internal/
frontend/src/
frontend/package.json
frontend/package-lock.json
frontend/vite.config.ts
go.mod
go.sum
Dockerfile
docker-compose.yml
scripts/
vendor/
dist/
config/
logs/
*.pem
*.key
*.d115p
```

`docs/plugin-platform/examples/` 中的 Vue、Go 和 TypeScript 仅是第三方插件示例，不属于主项目源码；示例构建产物、发布包和私钥仍然禁止提交。

## 发布前检查

在创建提交或推送公共分支前执行：

```bash
node docs/plugin-platform/conformance/verify-public-surface.mjs
```

脚本会检查 Git 跟踪文件的禁止路径、敏感发布材料、插件包构建产物，以及插件示例是否被放到了允许目录之外。CI 也会执行同一检查；检查失败时不得通过复制、改名、压缩或生成文件绕过。

需要发布插件时，只发布插件作者自己的 `.d115p` 到插件作者控制的地址，再把不含源码的市场条目提交到 `plugin-market/index.json`。不得把主项目源码作为插件 SDK、联调包或 Docker 构建上下文提供给第三方。

## 兼容性来源

第三方开发者只应依赖：

1. [开发者指南](developer-guide.md)；
2. [插件包格式](package-format-v1.md) 和三个 JSON Schema；
3. [进程运行时协议](process-runtime-v1.md)；
4. [Host Call](host-call-v2.md) 和 [OpenAPI](openapi-v1.yaml)；
5. [Vue Federation UI](ui-federation-v1.md)；
6. [黑盒联调工具](conformance/README.md)。

宿主的内部实现不是第三方插件的依赖，也不会作为插件开发资料公开。接口行为发生变化时，必须先更新公开契约和黑盒测试向量，再发布对应的宿主版本。
