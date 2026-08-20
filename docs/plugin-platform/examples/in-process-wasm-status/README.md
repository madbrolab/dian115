# 进程内 WASM 状态示例

这是 `dev.example.in-process-wasm-status` 1.0.0 的已签名包内容审阅目录。它只演示 `dian115:plugin@1` 的 health/state、声明式状态页面、integrity 和 Ed25519 签名，不申请 Host API 或外部网络权限。

可安装包与开发市场地址见[示例总览](../README.md)。本目录不提供插件源码、构建脚本或发布私钥；`runtime/plugin.wasm` 是已编译二进制。

实际 `.d115p` 只包含以下五个成员：

```text
manifest.json
ui.schema.json
runtime/plugin.wasm
integrity.json
signature.json
```

当前 `README.md` 是仓库说明，不属于插件包，也不应加入现有 1.0.0 的 ZIP。修改或重新压缩任何包成员都会改变 integrity/包 SHA-256；需要派生示例时必须使用自己的密钥、提高版本并按[打包签名规范](../../packaging-signing.md)重新构建。

1.0.0 成员中的 `$schema` 是签名时使用的协议标识，保留原字节以便验签；实际离线校验请显式使用 [manifest schema](../../manifest.schema.json)、[UI schema](../../ui-schema-v1.schema.json)、[integrity schema](../../integrity.schema.json) 和 [signature schema](../../signature.schema.json)，新插件直接填写文档给出的 GitHub Raw URL。
