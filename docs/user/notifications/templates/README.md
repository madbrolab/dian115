# Dian115 Telegram 通知模板参考库

这里提供 **20 套全新、可直接导入**的 Telegram 通知模板：

- 10 套 `classic_html` 普通富文本模板，适合需要兼容旧 Telegram 客户端的用户。
- 10 套 `rich_blocks` 模板，面向 Telegram Bot API 10.3 Rich Message。
- 每套都覆盖当前 **41 个独立通知事件**，整包可导入，也可只选择部分事件。
- 所有包均使用 `dian115-notify-template-package` v2，不携带私有图片地址。

## 选择协议

通知设置中的“发送协议”由用户明确选择，系统不会猜测接收者的 Telegram 客户端版本。

| 你的需求 | 发送协议 | 建议模板 |
| --- | --- | --- |
| 兼容旧客户端 | `classic_html` | `classic-*` |
| 使用 Bot API 10.3 结构化富消息 | `rich_message` | `rich-*` |
| Rich API 明确拒绝时仍需保证通知可读 | `rich_message` | Rich 模板使用自带的经典文本投影回退 |

`rich-*` 模板在通道选择 `classic_html` 时也可导入和预览，但发送时会按经典格式投影，不会调用 Rich 发送接口。协议由前端选择；发送端不会根据接收者客户端版本猜测或自动改协议。若用户选择 Rich，只有 Rich API 明确报错时才使用该模板携带的经典文本投影重发。

## 普通富文本：10 套

这一组使用 Telegram HTML 能力：粗体、斜体、下划线、行内代码、引用、可折叠引用等。每套的栏目名、字段标签、句式、符号、emoji 与画质点评都按风格整体重写。

| 下载 | 风格 | 排版特征 | 适合场景 |
| --- | --- | --- | --- |
| [航站播报](notify-templates-classic-airport-broadcast.json) | 航站楼广播 | 航班信息屏、登机口栏目、final call 收尾 | 家庭影院主频道、动态群组 |
| [电报局](notify-templates-classic-telegraph-office.json) | 老式电传 | 急电抬头、逐条电码、“电文毕”落款 | 运维频道、仪式感管理员 |
| [厨房出餐单](notify-templates-classic-kitchen-ticket.json) | 餐厅后厨 | 点菜明细、后厨备注、“出餐！”盖章 | 生活化家庭服务器 |
| [天文观测日志](notify-templates-classic-observatory-log.json) | 天文台夜班 | 观测编号、坐标式字段、归档落款 | 夜间运行的服务器 |
| [法庭卷宗](notify-templates-classic-court-record.json) | 庭审文书 | 审理查明、附卷证物、“宣判如下” | 安全事件、错误追踪 |
| [深夜电台](notify-templates-classic-midnight-radio.json) | 凌晨广播 | 来信式条目、温柔口播、晚安收尾 | 低频通知、私人频道 |
| [实验室记录](notify-templates-classic-lab-notebook.json) | 科研笔记 | 等宽栏目、观测值、“结论”小节 | 扫描质检、测试报告 |
| [茶馆说书](notify-templates-classic-storyteller-teahouse.json) | 评话段子 | “话说”开场、唱词条目、惊堂木收尾 | 朋友群、娱乐频道 |
| [地铁线路图](notify-templates-classic-metro-line.json) | 轨道导乘 | 站点式条目、换乘通道、终点站收尾 | 高频任务频道 |
| [山岳气象](notify-templates-classic-mountain-weather.json) | 气象公报 | 要素逐条、探空附录、出行判断 | 日报周报、平缓节奏 |

## Rich Message：10 套

这一组的每个事件都使用 `rich_blocks`，不是只更换 emoji。10 套模板采用 10 种不同块顺序、列数和折叠策略，并按主题组合：

- Rich 标题、导语、1～3 列字段表、有序/无序列表、分隔线和可折叠详情；
- 每个事件自身的核心数据，例如影视标题、播放用户、设备、账号、任务状态、计数或路径；
- `failure_items`、`result_items`、`strm_tree_items`、`latest_media`、`recent_media` 结构化数组的逐项展示与截断提示；
- `tg_time_now` 生成的 Telegram 本地化时间；
- 自动媒体图片所生成的 Rich `<figure>` 布局；
- 按事件跳转到 Emby、任务、账号、更新、监控或订阅等功能的按钮行，以及目标路径复制按钮；
- 完整的经典文本投影，用于经典协议预览或 Rich API 明确错误后的发送回退。

| 下载 | 风格 | Rich 布局重点 | 适合场景 |
| --- | --- | --- | --- |
| [飞行记录器](notify-templates-rich-flight-recorder.json) | 航空黑匣子 | 时间戳导语先行、双列遥测、原始记录默认展开 | 综合管理频道 |
| [围棋棋谱](notify-templates-rich-go-kifu.json) | 对局棋谱 | 单列局面字段、编号着手列表、折叠棋评 | 游戏化运营频道 |
| [急诊病历](notify-templates-rich-er-chart.json) | 急诊病历卡 | 高亮主诉、三列生命体征、危险按钮 | 告警与错误频道 |
| [拍卖图录](notify-templates-rich-auction-catalog.json) | 拍卖行图录 | 开拍导语、双列拍品卡、编号 lot 列表 | 影视收藏与入库频道 |
| [深空测控](notify-templates-rich-deep-space-tracking.json) | 测控电文 | 三列信号字段先行、折叠轨道参数 | 技术监控频道 |
| [号外](notify-templates-rich-newspaper-extra.json) | 报纸号外 | 大标题导语、单列事实栏、折叠背景 | 多事件播报频道 |
| [品鉴菜单](notify-templates-rich-tasting-menu.json) | 餐厅品鉴 | 上菜顺序列表先行、双列配餐字段 | 生活化家庭频道 |
| [索书卡](notify-templates-rich-card-catalog.json) | 图书馆卡片 | 单列索书字段卡、折叠典藏沿革 | 长期留档、低频事件 |
| [演唱会场刊](notify-templates-rich-concert-program.json) | 演出节目单 | 节目单列表、三列票务字段、花絮默认展开 | 热闹群聊频道 |
| [潜水日志](notify-templates-rich-dive-log.json) | 水肺记录 | 深度时间字段、折叠装备清单、无序要点 | 低频巡检与日报 |

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
- 粗体、斜体、下划线、行内代码、引用、折叠引用等格式；
- Rich Blocks 的标题、字段表、列表、折叠区和按钮文案；
- Dolby Vision、HDR、4K、1080P 四档画质点评。

需要保留的是 `{{ ... }}` / `{% ... %}` 中的变量、条件和循环；按钮的 `action` / `value` 也应使用系统允许的动作。除此之外，模板文案没有锁死内容。每个事件拥有独立的变量合同，导入器会拒绝未知变量、错误配对的富文本控制符和非法 Rich Blocks。

### 标题长度

这 20 套模板的通知标题均为静态短标题，最长 **16 个可见字符**；Rich 标题块也只使用简短的静态栏目名。影视名、用户名、路径、错误文本等可变长字段全部放在正文、字段表或折叠详情中，避免 Telegram 会话列表和通知横幅的标题失控。

自定义标题时建议继续保持在 18 个字符以内，不要在标题中插入 `title`、`show_name`、`target_path`、`error` 等无固定长度的变量。

## 图片策略

- 所有模板均使用 `image_mode: "auto"`。
- 模板包不包含 `image_url`，不会暴露私有默认图链接。
- 有 TMDB 图片时优先使用媒体图；否则由当前通知事件的图片策略决定。
- Rich 协议下，自动图片会进入 Rich Message 媒体布局；经典协议下使用兼容的图文发送。

## 覆盖的 41 个事件

- 播放：`playback_start`、`playback_stop`
- 媒体库：`media_library_add`、`media_library_update`
- Emby 账户安全：`emby_user_authenticated`、`emby_user_authentication_failed`、`emby_user_locked_out`、`emby_user_created`、`emby_user_deleted`、`emby_user_password_changed`、`emby_user_policy_updated`
- 整理与扫描：`library_organize_success`、`library_organize_skip`、`library_organize_fail`、`library_quality_scan`、`library_missing_scan`、`strm_generate`
- 文件操作：`share_receive`、`offline_download`、`tg_auto_transfer`、`tg_auto_offline`、`tg_video_download`、`account_migration`、`ed2k_task`、`media_auto_share`
- 账号：`account_cookie_invalid`、`account_switched`、`account_checkin`、`dianying_checkin`
- 容器与项目更新：`container_update_check`、`container_update_result`、`container_update_test`、`dian115_self_update`
- 代理健康：`proxy_health_daily_report`、`proxy_health_test_report`
- 运行统计：`daily_statistics_report`、`emby_library_statistics_report`
- 订阅：`subscribe_added`、`subscribe_landed`、`subscribe_partial`
- 插件：`plugin_notification_message`

## 校验结果

发布前已使用当前 Dian115 后端完成：

- 20 个 JSON 包语法与严格字段校验；
- 820 个模板的导入归一化和事件变量合同校验；
- 820 个样例上下文渲染，正文均非空；
- 经典 Telegram HTML 格式配对校验；
- 410 个 Rich 模板的标题、字段表、折叠、数组循环、按钮和本地化时间合同校验，Rich HTML 与纯文本投影均渲染成功；
- 标题静态化和 18 字符上限校验；
- 每包 41 事件、无重复 key、无 `image_url` 的可移植性校验。
