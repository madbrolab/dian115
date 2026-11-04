# 第三方可信扩展市场 v3

index.json 是 v3 来源元数据索引，plugins 初始为空。每个版本提供 id、name、version、author、description、homepage、changelog、source_url、sha256 和 delivery；保护与准入就绪的宿主要求新正式安装采用 protected-v4，历史 source/encrypted 保留兼容。可选 icon、repository_url、keywords 用于卡片与搜索，permissions 须覆盖插件清单申请项。格式见 [index.schema.json](index.schema.json)，完整规则见[市场规范](../docs/plugin-platform/market.md)。

用户从“用户插件”页右下角打开商店后才加载来源；各来源独立请求、完成即展示，失败不阻塞其他来源。右侧支持一行一个地址批量添加。搜索、来源与安装状态筛选、更新排序直接使用元数据，同源每个插件默认显示最新可比较版本，卡片分页渲染，图标按需加载。

选择版本后才下载插件包，核对 SHA256、来源签名以及实际 plugin.json 的 ID、版本、作者和权限，再形成安装报告。安装确认先展示能力风险摘要，接口和 DNS 明细按需展开；固定解析只用于安装检查快照。索引声明不作为权限授予或安全保证，安装仍由用户选择。

源码和加密 .dian115p 包 由作者在自有交付地址托管，不把生成包、密钥或主项目源码提交到本目录。此目录只接收索引、Schema、说明和明确的市场静态资源；公开第三方示例源码只放 docs/plugin-platform/examples/。
