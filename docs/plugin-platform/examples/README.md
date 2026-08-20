# 可安装示例

本目录只提供已签名的插件包内容、二进制运行时和开发市场索引，不提供插件源码、构建缓存或发布私钥。它用于先验证“添加仓库 → 刷新 → 查看权限 → 安装 → 打开原生页面”的完整链路。

## 直接安装

在“插件中心 → 仓库与开发”添加以下自定义 HTTPS 市场地址：

```text
https://raw.githubusercontent.com/madbrolab/dian115/main/docs/plugin-platform/examples/dev-market/index.json
```

刷新该仓库后安装“进程内 WASM 状态示例”。示例不申请 Host API 或外部网络权限，只返回一个只读运行状态页面。

开发市场包含：

- [`dev-market/index.json`](dev-market/index.json)：可被插件中心读取的市场索引。
- [`dev-market/packages/in-process-wasm-status-1.0.0.d115p`](dev-market/packages/in-process-wasm-status-1.0.0.d115p)：已经过完整性校验和 Ed25519 签名的可安装包。
- [`in-process-wasm-status/`](in-process-wasm-status/)：同一包的五个已签名成员及一份不入包的说明文档，便于检查 manifest、UI、integrity 与 signature；`runtime/plugin.wasm` 是已编译二进制，不含源码。

## 不要直接重新压缩

Loose files 只是审阅视图。不要对目录执行 `zip -r`，也不要从 Windows 工作区随手重新压缩：Git checkout 可能把 JSON 的 LF 换行改成 CRLF，ZIP 工具还可能加入显式目录成员或不同 Unix mode。任一字节变化都会改变 integrity 或整个包的 SHA-256。

需要复现时，应从 Git blob 读取原始字节，严格按 UTF-8 路径字节排序，只加入这五个普通文件，并把 mode 固定为 `0644`。重新生成任何成员都视为新包：必须使用自己的发布私钥签名、提高版本、使用新文件名并更新市场 SHA-256。完整流程见[打包、完整性与签名](../packaging-signing.md)。

示例发布者私钥不在仓库中，也不会提供。第三方开发者必须生成并保管自己的密钥。
