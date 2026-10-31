# 排错 v3

- 首次页面加载失败：查看页面显示的资源 URL、HTTP 状态和模块报错。确认 ui.entry 存在，JS 导出 mount，资源用相对路径，服务未停用该安装。
- UI 关闭后仍有副作用：检查 mount 清理函数、AbortSignal、订阅和定时器。后台任务与页面分离，按任务记录判断是否需要取消。
- 宿主重启后任务为 attention_required：原业务可能已成功，先查询结果。recover 返回 complete、resume 或 attention；不靠新业务标识绕过未确认结果。
- 请求慢：分别测量 HTTP、验证计算、渲染和前台轮询时间。`render.wait_seconds` 是固定等待；Loading 外壳可能已经带有可直接解析的业务 JSON。先看 [网络文档](network.md#避免每次查询都等待浏览器)，不要仅增加超时或用旧缓存隐藏慢请求。
- Cookie 未生效：检查 session、URL、Domain/Path/Secure、UA、Cookie 到期时间。importCookies 用于保留完整属性。
- 有 Cookie 仍退避：Cookie 存在不等于登录有效。更新后增加会话修订号，清除普通旧失败窗口并独立核验账号页，保留 429 等待；防止旧运行覆盖新会话状态。
- 浏览器通过但 HTTP 一直验证：两个传输通道可能不能共享机器验证结果。优先使用已返回的浏览器文档，或按该站点已确认的公开机器验证协议在同一 HTTP 会话内完成验证；不要无限重试登录。
- 系统已有 FlareSolverr 却要求再填：通过插件自身 `network-capabilities` 探测默认服务支持；支持时省略 endpoint，旧宿主 404 时可沿用已有地址。不得读取禁止的全局设置接口。文档更新不等于部署的宿主已经支持新能力。
- 目录监听报错：查看 watches 记录的 error。失败快照会保留原状态，不生成删除；CD2 返回完整列表后才比较差异。
- 卸载处于 deleting：后台操作尚未退出或目录无法删除。修复挂载/权限后重试卸载；宿主重启也会继续清理。不要手动复用该 ID 的目录。
- 加密安装失败：检查包是否完整、是否包含离线内容密钥封装，以及主程序版本是否支持该包。用户无需配置平台地址、公钥或令牌；报告、密文或 nonce 被修改都会拒绝安装。

- 任务失败“内存超出预算”：脚本运行时宿主堆增长超过插件预算。避免把大响应读进内存（用 save_to）、分批处理数组；运营者可调 DIAN115_EXTENSION_MEMORY_MB。
- “插件只能读写自己的 data/files 目录”：宿主路径只能由宿主移动/复制/删除，不能读取内容；需要内容时先交给宿主的业务接口处理。
- 文件移动看不到进度：后台任务中默认写入任务进度；页面调用会生成“插件 X：文件移动”队列任务。CD2 两端都在挂载内时由 CD2 服务端执行，只有开始和完成两个点。
- CD2 移动报“只能在同一个网盘路径下”：两端都在 CD2 时走 gRPC，只支持同一云盘；跨云盘需先移到本地路径再移入目标挂载路径。

- 通知没有收到：看返回的 `deliveries`。`skipped/disabled` 表示用户在该渠道关闭了插件通知，`quiet_hours` 为该渠道静默时段，`not_configured` 为渠道未配置；`failed` 的 `error` 给出脱敏原因（如 Telegram 拒绝 HTML 时的解析错误）。
- 企业微信里 markdown 显示“不支持”：个人微信（微信插件）不渲染企业微信 markdown，可用 `overrides.wecom.format:'text'`。

- `Cannot read property 'xxx' of undefined or null`：代码读取了不存在的对象的属性，比如写错 ctx 成员。错误末尾的括号是文件和行号。后台 ctx 没有 `tasks`、`events`、`usage`，可用成员见 [API 参考](api-reference.md)。
- `SyntaxError ... for await`：脚本引擎不支持 `for await` 和异步生成器，循环调用 `next()`，见[长连接](long-connections.md)。
- `permission ... is not granted`：清单声明了权限但用户没开，到插件卡片打开；或者代码用了清单没声明的渠道。
- 关键字不触发：确认授权已开。`/` 开头的文本和宿主能识别的链接由宿主优先处理；只有白名单用户的消息会进入插件。
- 账号事件收不到：账号要登录且客户端在运行；默认不包含账号自己发的消息。
- `操作过于频繁`：超过消息渠道限额，按提示等待。账号发送要控制频率，避免 Telegram 风控。
- 常驻任务不运行：调用 `GET /api/extensions/v3/{id}/daemons` 看 `last_error` 和日志。反复重启时等待时间会增加到 5 分钟。
- `每个插件最多同时保持 16 条长连接`：用完调用 `close()`，脚本结束时宿主也会全部关闭。SSE 连接也计入。
- `permission network.tcp is not granted`：清单声明 `network.tcp`，并在插件卡片打开“原生 TCP”。
- TCP 端口外部连不上：`host` 默认只绑定本机；Docker 部署还要映射端口。
- `address already in use`：端口被占用，换端口。常驻任务重启时会自动重试。
- SSE 收不到实时数据：反向代理开了缓冲，或处理器没有用 `ctx.response`。长时间无数据时用 `stream.comment()` 发心跳。
- CD2 目录监听很慢或扫描超时：路径写挂载路径，让宿主走 CD2 接口；减少 `recursive` 范围，调大 `interval_seconds`。
- 市场仓库报 `is missing author, ...`：条目缺少必填字段，见[市场规范](market.md)，发布前运行 `market-check.mjs`。
- 安装报“引用了禁止调用的宿主接口”：代码写了受保护的接口，改用公开能力，比如消息用 `ctx.telegram`，不要调用账号客户端接口。

报告问题时提供宿主版本、插件 ID/版本/revision、失败操作、任务标识与脱敏错误。不要上传 Cookie、密码、运行密钥或整份数据库。
