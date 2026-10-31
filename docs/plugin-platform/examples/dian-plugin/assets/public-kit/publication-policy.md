# 插件平台公开材料边界

公共仓库仅包含协议、Schema、OpenAPI、UI/主题契约、公开 SDK、第三方完整示例、市场元数据和黑盒工具。第三方示例源码只能放在 docs/plugin-platform/examples/。

主项目源码、cmd/、internal/、frontend/src/、主项目构建/部署文件、根 go.mod/go.sum、生产脚本、vendor、密钥、Docker 构建上下文和生成发布产物永远不得公开。不得通过改名、加密、压缩或复制进示例目录规避。独立源码托管与加密服务的宿主实现同属私有主项目，不进入公开 skill。

示例只发布源码；node_modules、build、releases、插件生成包、签名私钥和真实用户配置均不提交。发布新插件版本时由插件作者自行托管交付 .dian115p 包；本项目只接收允许的源码示例和明确的市场元数据。公开材料不是代码执行授权或安全保证。

创建任何公共提交前，在隔离的公开仓库运行：

```sh
node docs/plugin-platform/conformance/verify-public-surface.mjs
```

同时核对本轮待发布文件和提交 author/committer；身份按用户长期约定使用中性 bot。不要从私有主项目直接推送整棵工作树。公开 SDK 与工具只能依赖公开材料，不复制主项目实现。
