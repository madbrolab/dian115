---
name: dian115-plugin-dev
description: 开发、修改和排错 DIAN115 v3 第三方可信扩展，使用普通宿主 API、直接挂载页面和后台 JavaScript 编排；提供源码检查、任务恢复、独立存储及可选服务端加密交付流程。随主程序编译的内置功能不属于此流程。
---

# DIAN115 可信扩展开发

当前契约为宿主插件 API 3.5。涉及图片、真实媒体信息、AI 或演员资料时先读 assets/public-kit/media-and-ai.md：复用宿主图片裁剪/缩放/人脸检测与 badge 图片、FFP 共享探测、无工具 AI 文本调用、Emby 演员查询与头像上传；不要重复实现宿主已具备的服务或读取宿主密钥。`ctx.files.call` 支持本地 hardlink/symlink 与非递归空目录 rmdir。使用新增 SQLite/NFO 接口时声明 requires.api=3.4；只使用 3.3 媒体功能时可声明 requires.api=3.3，并将实际调用写入 declared_usage。UI/后台都使用现有 ctx.api，不虚构新的运行时对象。3.4 的 data/sqlite 仅查询插件自有、已关闭 checkpoint 的静态资料库，采用 table/columns/equals 分页，不接受 SQL 或宿主数据库路径；media/nfo 只读受保护规则约束的媒体 .nfo 并返回结构化字段。资料库按需下载缓存，不能把第三方整库或凭据随包分发。

图片 `inspect:true` 只检查头部尺寸（含 JPEG EXIF 朝向），不证明像素完整；候选回退须处理实际解码/生成失败。应传入受限的 width/height，避免整图尺寸处理与不必要放大；宿主复用成品画布叠加 badge，并按源图总像素预算排队。不要把降低 JPEG quality 当成降低解码内存，也不要声称首次解码已省略。文件与图片操作始终保留取消和失败处理。

订阅功能先读 assets/public-kit/subscriptions.md，使用 3.5 的 GET /api/cache/magnet/changes 与 POST /api/pt/search incremental 模式；不要全量扫缓存或把搜索缓存的空结果当成新的查询结果。按“订阅 × 来源/站点”保存独立时间基线、固定窗口分页进度和候选；完整空结果推进基线，错误/未读完保留；先原子保存候选再推进基线，最后提交。磁力与 ED2K 均可交给 115，MD4 不得转为 BTIH。外部 HTTP 数据源需要真实支持时间范围与游标，旧接口不能冒充增量。使用这些接口声明 requires.api=3.5。

使用本 skill 自带的 assets/public-kit 公开契约，不要求取得 DIAN115 主项目源码。先阅读其中 README.md、api-reference.md 和 developer-guide.md，再按实际功能读取 network.md、ui-theme.md、storage-and-lifecycle.md 或 encrypted-delivery.md。宿主 API 的真实输入输出查 openapi-v3.json，不凭印象创造参数或把目录当白名单。插件不能读取宿主文件内容：相对路径是插件自有目录，宿主路径只能交给宿主 move/copy/remove/rename/mkdir 执行（CD2 两端走 gRPC，混合走挂载路径系统命令，带进度）。

插件是宿主的可信组成部分：页面直接使用宿主 API；后台 JS 决定业务逻辑、顺序和定时任务，实际业务交给现有接口与统一队列。无需 WASM、Host Call、独立 Node 服务、内置 Chromium 或旧安装兼容。保留用户选择的框架与业务方式，不强制增设运行隔离。

先确定插件 ID、页面/后台入口、调用的业务 API、用户填写的站点和路径、外部写操作及业务结果如何核对。可以明文填写账号密码、CK 和安装后自定义地址；配置保存在插件 SDK 存储中，不写入源码、公开仓库、日志或报告。Cookie 持久化、属性导入、本地 CookieCloud 和按需 FlareSolverr 的用法按 network.md。

涉及站点登录、验证或响应慢时，先读 assets/public-kit/network.md 的“登录与自动验证”和“避免每次查询都等待浏览器”。Loading 页可能已有完整 JSON，不要默认逐页等待浏览器；解析已知数据并核验结构，未知结构才回退。登录以独立账号页为准，同一 session 完成验证与提交；仅在站点明确拒绝原操作且允许重试时有限重试，超时不重放。默认 FlareSolverr 用插件自己的 network-capabilities 探测，不能读取全局设置；旧宿主 404 才沿用已有 endpoint。分别实测首次与复用会话的时间和结果，不能将缓存命中当作首次提速。

将实现放在独立插件目录，plugin.json 使用 schema_version=3。`scripts/init.mjs <绝对目标目录> <插件ID>` 可生成不触发外部动作的测试台；也可直接基于用户现有项目修改。清单 declared_usage 如实说明接口、站点/IP、路径、CD2、通知和触发器；动态站点要说明由用户配置，不伪称静态分析已经发现所有访问范围。风险报告供安装选择，不做权限拦截。

页面导出 mount(element,ctx)，返回清理函数并使用 ctx.signal；也可提供完整 HTML。只要求跟随主项目明暗主题，保持表单标签、状态和错误清楚。不要屏蔽浏览器能力或把通用 Script error 直接当成业务失败。

后台导出 run(ctx,input)，所有异步操作必须 await。任务用稳定 business_key；变更动作前后保存检查点。实现 recover 时先核对远端或宿主的实际结果，再返回 complete/resume/attention；超时、重启、调用失败均不能证明外部动作未发生。通知用稳定 dedupe_key，不更换标识来绕过未知结果。每次后台运行都进入宿主统一任务队列：job 写 `title` 让队列显示“插件名：标题”；批量处理用 `ctx.task.update({total,done,failed,message})` 上报任务级计数，队列显示“已处理 done/total”，单个文件移动的进度不会覆盖整体进度；页面发起的测试、预览等短任务设 `"queue": false` 不进队列页面。不允许重叠的 job 被重启打断后处于“需要核对”，会拒绝新的运行，页面要提供 `ctx.tasks.retry(id)` 入口。详见 developer-guide.md 的“任务队列与进度”。公开契约仅收录插件可调用的接口，具体权限由宿主安装和运行检查；本地 project-check 只检查结构。宿主文件操作仅接受允许的业务路径，也不能把宿主文件放进插件目录；CookieCloud 读不到 115 域名；安装后的代码不能再改，改了插件会停用，需要重新打包安装。SDK 的页面类型和后台类型分别在 examples/sdk/index.d.ts 与 background.d.ts。

默认文件放插件 data/files；只有业务需要且用户明确配置时才访问绝对 Linux 路径。CD2 复用宿主 gRPC，不复制主项目私有 protobuf/客户端实现。目录读取或流失败保留基线，不推断删除；目录轮询和任务应在停用、卸载后停止。卸载清空插件全部默认数据，不撤销共享 CookieCloud 或已提交业务结果。

验证以实际行为为准：源码检查、SDK 与业务单元测试，必要时在用户已授权的宿主做黑盒检查。先验证只读路径，再测试有业务副作用的操作；未经授权不自动登录第三方站点、发送通知、转存、删除文件或更新服务器。没有环境时明确区分本地测试通过与真实站点未验证。默认不要求 Docker、真实 PostgreSQL 或 Linux 压力测试。

交付可读源码目录或 .dian115p 包，结构见 public-kit/package-format.md；可用 public-kit/conformance/pack.mjs 生成包，输出放源码目录外。不将 node_modules、构建缓存、私钥或真实凭据放入源码包。需要保密时在平台加密网页选择源码目录或可读 .dian115p，无需登录或口令，直接加密并下载 .dian115p；平台不保存源码或安装包。用户直接安装加密 .dian115p，主程序内置解密；不得要求公钥、运行令牌、平台地址或在线取钥。管理员在解密窗口使用独立审查令牌并上传加密 .dian115p，查看或下载还原源码；不依赖发布记录，不执行插件代码。解密和完整性通过不代表无恶意代码，需要人工审查。不要自行混淆后冒充审查完成，也不把解密主密钥放入插件。加密不能阻止拥有宿主运行权限的人观察明文。

修改结束运行 public-kit/conformance/project-check.mjs，补充对重复调用、任务恢复与卸载相关行为的测试。发布 GitHub 之前检查公开材料边界，始终不包含主项目源码或其加密/改名副本；提交身份遵循用户已有约定。最终报告实际改动、验证结果、安装方法与尚未验证的外部业务。
