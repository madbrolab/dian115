# 排错 v3

- 首次页面加载失败：查看页面显示的资源 URL、HTTP 状态和模块报错。确认 ui.entry 存在，JS 导出 mount，资源用相对路径，服务未停用该安装。
- UI 关闭后仍有副作用：检查 mount 清理函数、AbortSignal、订阅和定时器。后台任务与页面分离，按任务记录判断是否需要取消。
- 宿主重启后任务为 attention_required：原业务可能已成功，先查询结果。recover 返回 complete、resume 或 attention；不靠新业务标识绕过未确认结果。
- 请求慢：单次 http.request 显式配置 timeout_seconds、必要的 cache_seconds；任务进度写入 task.update。检查网站、代理、DNS 和外部渲染服务的实际响应。
- Cookie 未生效：检查 session、URL、Domain/Path/Secure、UA、Cookie 到期时间。importCookies 用于保留完整属性。
- 目录监听报错：查看 watches 记录的 error。失败快照会保留原状态，不生成删除；CD2 返回完整列表后才比较差异。
- 卸载处于 deleting：后台操作尚未退出或目录无法删除。修复挂载/权限后重试卸载；宿主重启也会继续清理。不要手动复用该 ID 的目录。
- 加密安装失败：检查包是否完整、是否包含离线内容密钥封装，以及主程序版本是否支持该包。用户无需配置平台地址、公钥或令牌；报告、密文或 nonce 被修改都会拒绝安装。

- 任务失败“内存超出预算”：脚本运行时宿主堆增长超过插件预算。避免把大响应读进内存（用 save_to）、分批处理数组；运营者可调 DIAN115_EXTENSION_MEMORY_MB。
- “插件只能读写自己的 data/files 目录”：宿主路径只能由宿主移动/复制/删除，不能读取内容；需要内容时先交给宿主的业务接口处理。
- 文件移动看不到进度：后台任务中默认写入任务进度；页面调用会生成“插件 X：文件移动”队列任务。CD2 两端都在挂载内时由 CD2 服务端执行，只有开始和完成两个点。
- CD2 移动报“只能在同一个网盘路径下”：两端都在 CD2 时走 gRPC，只支持同一云盘；跨云盘需先移到本地路径再移入目标挂载路径。

- 通知没有收到：看返回的 `deliveries`。`skipped/disabled` 表示用户在该渠道关闭了插件通知，`quiet_hours` 为该渠道静默时段，`not_configured` 为渠道未配置；`failed` 的 `error` 给出脱敏原因（如 Telegram 拒绝 HTML 时的解析错误）。
- 企业微信里 markdown 显示“不支持”：个人微信（微信插件）不渲染企业微信 markdown，可用 `overrides.wecom.format:'text'`。

报告问题时提供宿主版本、插件 ID/版本/revision、失败操作、任务标识与脱敏错误。不要上传 Cookie、密码、运行密钥或整份数据库。
