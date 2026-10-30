# 第三方可信扩展市场 v3

index.json 是来源元数据，plugins 初始为空。每个版本提供 id、name、version、source_url（源码或加密 .dian115p 包）、sha256 和 delivery（source/encrypted），可附加 description、author、declared_usage。清单格式见 index.schema.json。

插件中心支持官方和自定义 HTTP/HTTPS 索引。用户主动刷新后展示元数据；选择版本后下载 ZIP，核对 SHA256、实际 plugin.json 的 ID/版本，再解析实际代码形成安装报告。索引声明不作为权限授予或安全保证，安装仍由用户选择。

源码和加密 .dian115p 包 由作者在自有交付地址托管，不把生成包、密钥或主项目源码提交到本目录。此目录只接收索引、Schema、说明和明确的市场静态资源；公开第三方示例源码只放 docs/plugin-platform/examples/。
