# 市场与安装来源 v3

仓库是 HTTP/HTTPS 索引，格式见 [索引 Schema](market-index.schema.json)。每个版本包含 id、name、version、source_url、sha256、delivery，可附加作者说明和 declared_usage。源码 .dian115p 包与加密 .dian115p 包由作者托管，不提交生成包到本项目公共仓库。

插件中心打开时只读取本地安装与来源元数据，不自动等待远程索引。用户点击刷新后汇总来源；单个来源失败独立显示，不隐藏其他来源。移除来源不卸载已安装插件；删除全部来源后重启也不会重新添加。

市场版本先下载校验 SHA256，校验真实 plugin.json 的 ID/版本，再静态分析实际代码；加密包先验证签名并解密再分析。安装确认用此实际版本的检查 token。风险等级和作者声明不会作为访问白名单。

也支持直接从交付地址检查；此时可不提供摘要，但仍由宿主解析代码并等待用户选择安装。JSON 上传使用 files（文件名到源码字符串的映射）或 directory（服务器源码目录）；multipart 使用 file 字段上传 .dian115p 包。
