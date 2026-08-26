# Dian115 Telegram 通知模板参考库

这里提供 **20 套全新、可直接导入**的 Telegram 通知模板：

- 10 套 `classic_html` 普通富文本模板，适合需要兼容旧 Telegram 客户端的用户。
- 10 套 `rich_blocks` 模板，面向 Telegram Bot API 10.3 Rich Message。
- 每套都覆盖当前 **40 个独立通知事件**，整包可导入，也可只选择部分事件。
- 所有包均使用 `dian115-notify-template-package` v2，不携带私有图片地址。

## 选择协议

通知设置中的“发送协议”由用户明确选择，系统不会猜测接收者的 Telegram 客户端版本。

| 你的需求 | 发送协议 | 建议模板 |
| --- | --- | --- |
| 兼容旧客户端 | `classic_html` | `classic-*` |
| 使用 Bot API 10.3 结构化富消息 | `rich_message` | `rich-*` |
| Rich API 明确拒绝时仍需保证通知可读 | `rich_message` | Rich 模板使用自带的经典文本投影回退 |

`rich-*` 模板在通道选择 `classic_html` 时也可导入和预览，但发送时会按经典格式投影，不会调用 `sendRichMessage`。

## 普通富文本：10 套

这一组使用 Telegram HTML 能力：粗体、斜体、下划线、行内代码、剧透、引用、可折叠引用等。每套的栏目名、句式、收尾、符号和 emoji 都按风格重写。

| 下载 | 风格 | 排版特征 | 适合场景 |
| --- | --- | --- | --- |
| [影视库首映](./notify-templates-classic-cinema-library.json) | 影院场记 | 斜体场刊、片库分段、放映收尾 | 影视库、Emby 家庭影院 |
| [机器人调度](./notify-templates-classic-robot-dispatch.json) | 机器人回执 | 代码标题、系统分隔、ACK 收尾 | 自动化、任务队列 |
| [搞笑小喇叭](./notify-templates-classic-comedy-radio.json) | 轻松搞笑 | 剧透标题、口语栏目、不丢正事 | 朋友群、轻松频道 |
| [运维执行摘要](./notify-templates-classic-ops-briefing.json) | 正式运维 | 下划线标识、执行结论、审计语气 | 管理员、运维审计 |
| [极简留白手记](./notify-templates-classic-minimal-note.json) | 极简编辑 | 短标题、低噪音、克制分隔 | 高频通知、小屏阅读 |
| [家庭客厅](./notify-templates-classic-cozy-home.json) | 温和管家 | 家庭语气、舒缓提醒、客厅收尾 | 家庭服务器、共享 Emby |
| [侦探案卷](./notify-templates-classic-detective-file.json) | 黑色案卷 | 线索、案情、结案层次 | 安全通知、错误追踪 |
| [复古街机](./notify-templates-classic-retro-arcade.json) | 8-bit 任务卡 | 代码块、关卡语气、SAVE 收尾 | 游戏化任务频道 |
| [古典纪事](./notify-templates-classic-classical-chronicle.json) | 中式简牍 | 卷目、细目、入档句式 | 收藏库、中文文化主题 |
| [新闻编辑部](./notify-templates-classic-newsroom-wire.json) | 即时快讯 | 核心先行、追加报道、时间线 | 多事件播报频道 |

## Rich Message：10 套

这一组的每个事件都使用 `rich_blocks`，不是只更换 emoji。10 套模板采用 10 种不同块顺序和信息密度，并按主题组合：

- Rich 短标题、字段表、业务列表、分隔线和可折叠详情；
- 每个事件自身的核心数据，例如影视标题、播放用户、设备、账号、任务状态、计数或路径；
- `failure_items`、`result_items`、`strm_tree_items` 结构化数组的逐项展示；
- `tg_time_now` 生成的 Telegram 本地化时间；
- 自动媒体图片所生成的 Rich `<figure>` 布局；
- 按事件跳转到 Emby、存储、任务、账号、更新、监控或订阅等功能的 `tg-button-row`，以及稳定编号复制按钮；
- 完整的经典文本投影，用于经典协议预览或 Rich API 明确错误后的发送回退。

| 下载 | 风格 | Rich 布局重点 | 适合场景 |
| --- | --- | --- | --- |
| [指挥中心](./notify-templates-rich-command-center.json) | 运行指挥台 | 三列密集字段先行、默认展开日志 | 综合管理频道 |
| [星际任务](./notify-templates-rich-space-mission.json) | 航程遥测 | 状态导语、编号遥测列表、轨道字段 | 科幻、沉浸式主题 |
| [臻选首映礼](./notify-templates-rich-luxury-premiere.json) | 高级影院 | 首映导语、三列宾客卡、折叠场记 | 高质量影视库 |
| [AI 运营官](./notify-templates-rich-ai-operator.json) | AI 解析面板 | 输入字段、嵌套推理标题、结论高亮 | 自动化与 AI 服务 |
| [数据实验室](./notify-templates-rich-data-laboratory.json) | 实验观测 | 三列参数、编号指标、折叠样本 | 测试、质量与扫描 |
| [综艺庆典](./notify-templates-rich-variety-festival.json) | 开麦现场 | 高亮开场、业务节目单、后台详情 | 搞笑、鲜明群聊 |
| [霓虹网格](./notify-templates-rich-neon-grid.json) | 赛博信号板 | 字段先行、霓虹标题、信号列表 | 技术监控频道 |
| [博物档案馆](./notify-templates-rich-museum-archive.json) | 长期典藏 | 单列目录卡、展开档案、编号沿革 | 历史留档、低频重要事件 |
| [冒险任务簿](./notify-templates-rich-adventure-quest.json) | 任务结算 | 编号进度、结果字段、任务日志 | 游戏化运营频道 |
| [静谧仪表盘](./notify-templates-rich-calm-dashboard.json) | 克制工作台 | 单句结论、四项字段、默认收起详情 | 高频、低干扰频道 |

## 导入方法

1. 下载一个 JSON 模板包。
2. 打开 Dian115 的“通知设置 → Telegram 推送”。
3. 先选择需要的发送协议：“经典 HTML”或“Rich Message”。
4. 进入模板设计器，选择“导入模板”并上传 JSON。
5. 在导入预览中勾选需要覆盖的事件，确认后保存。
6. 发送测试消息，确认当前 Telegram 频道的字体、图片和按钮效果。

## 自定义边界

模板导入后，除变量表达式和控制语句外，所有用户可见的文字与 emoji 都可以自定义。包括：

- 标题文案、栏目名、提示语、收尾语；
- 所有 emoji、分隔符、字段标签；
- 粗体、斜体、高亮、引用等格式；
- Rich Blocks 的标题、表格、列表、折叠区和按钮文案；
- Dolby Vision、HDR、4K、1080P 四档画质点评。

需要保留的是 `{{ ... }}` / `{% ... %}` 中的变量、条件和循环；按钮的 `action` / `value` 也应使用系统允许的动作。除此之外，模板文案没有锁死内容。每个事件拥有独立的变量合同，导入器会拒绝未知变量、错误配对的富文本控制符和非法 Rich Blocks。

### 标题长度

这 20 套模板的通知标题均为静态短标题，最长 **16 个可见字符**；Rich 标题块也只使用简短的静态栏目名。影视名、用户名、路径、错误文本等可变长字段全部放在正文、字段表或折叠详情中，避免 Telegram 会话列表和通知横幅的标题失控。

自定义标题时建议继续保持在 18 个字符以内，不要在标题中插入 `title`、`show_name`、`target_path`、`error`等无固定长度的变量。

## 图片策略

- 所有模板均使用 `image_mode: "auto"`。
- 模板包不包含 `image_url`，不会暴露私有默认图链接。
- 有 TMDB 图片时优先使用媒体图；否则由当前通知事件的图片策略决定。
- Rich 协议下，自动图片会进入 Rich Message 媒体布局；经典协议下使用兼容的图文发送。

## 覆盖的 40 个事件

- 播放：`playback_start`、`playback_stop`
- 媒体库：`media_library_add`、`media_library_update`、`media_library_delete`
- Emby 账户安全：`emby_user_authenticated`、`emby_user_authentication_failed`、`emby_user_locked_out`、`emby_user_created`、`emby_user_deleted`、`emby_user_password_changed`、`emby_user_policy_updated`
- 整理与扫描：`library_organize_success`、`library_organize_skip`、`library_organize_fail`、`library_quality_scan`、`library_missing_scan`、`strm_generate`
- 文件操作：`share_receive`、`offline_download`、`tg_auto_transfer`、`tg_auto_offline`、`tg_video_download`、`account_migration`、`ed2k_task`、`media_auto_share`
- 账号：`account_cookie_invalid`、`account_switched`、`account_checkin`、`dianying_checkin`
- 容器与项目更新：`container_update_check`、`container_update_result`、`container_update_test`、`dian115_self_update`
- 代理健康：`proxy_health_daily_report`、`proxy_health_test_report`
- 订阅：`subscribe_added`、`subscribe_landed`、`subscribe_partial`
- 插件：`plugin_notification_message`

## 校验结果

发布前已使用当前 Dian115 后端完成：

- 20 个 JSON 包语法校验；
- 800 个模板的导入归一化和事件变量合同校验；
- 800 个样例上下文渲染；
- 经典 Telegram HTML 预览校验；
- 400 个 Rich 模板的各类标题、字段表、折叠、业务列表、按钮和本地化时间合同校验；
- 三类结构化数组循环、8 类画质点评引用和 10 种 Rich 布局指纹校验；
- 标题静态化和 18 字符上限校验；
- 每包 40 事件、无重复 key、无 `image_url` 的可移植性校验。
