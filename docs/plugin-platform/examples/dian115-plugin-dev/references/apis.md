# 接口、网络和权限

用 scripts/api.mjs 检索公开目录：它支持方法、分类、标题和描述检索；无匹配会非零退出。随后在 public-kit/openapi-v1.yaml 找到相应 path operation，阅读参数、请求、成功/失败响应、ETag、幂等要求和任务结果。目录生成时校验条目数量，不能根据想当然的 URL 调用。

当前目录是标准访问目录；扩展访问是公开协议另行定义的显式选择，有更强的安装披露，不能为了绕过缺失接口自动开启。optional 也不是静默取得权限的办法。宿主能力和批准情况与 API 合同分别核对，功能缺失时提供明确说明。

Manifest 只添加所需 `permissions.apis` 方法+路径模板，并以具体业务理由披露。相同声明复制到市场条目；以 `npm run check:contract` 及时发现不同步。参数 ID 是公开引用，不能猜内部数据库 ID。远端 name/fn/file_name 是不透明名称；使用节点/父节点引用构造层级，映射本地 Linux 路径时才转换非法分隔字符。

用 public-kit/examples/sdk/hostapi 处理 Host Call。传输 error、目标 HTTP 4xx/5xx、业务结果分别检查。`Problem` 可带 Code/Detail/Retryable/DiagnosticID；日志保留操作编号和安全错误信息。只在公开协议明确允许、业务能安全重复时采用有界重试；上游超时不是未执行证明。

外部网络同样走 Host Call，HTTP/HTTPS、本地服务、代理与凭据语义以 host-call-v2.md 为准。network 声明中的 origin/methods/proxy_mode 是公开网络路由与披露契约，不把它误当整个宿主的网络防火墙。凭据通过协议允许的宿主绑定/引用使用，不读取宿主登录 cookie 或配置文件。

不要向所有插件授予测试台的全部接口。请求正文、分页、HTTP 响应和日志均保持有界；响应预览截断不等于业务完整结果。调试时结合原始状态码、diagnostic_id、任务引用和时间排查。
