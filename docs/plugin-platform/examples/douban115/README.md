# 豆瓣订阅中心（local.douban115）

DIAN115 的第三方插件：把豆瓣榜单与豆瓣「想看」列表自动解析为 TMDB 身份并创建聚合订阅，支持多用户合并去重，并可把 Emby 观影记录回写到豆瓣。

> **版本状态：1.0.0 为对外首个正式版本**，之后按 SemVer 正常迭代（修复 `x.y.z` 的 `z`、兼容性新增 `y`、破坏性变更 `x`）。1.0.0 之前为内部迭代版本（1.4.x），版本号已在 1.0.0 重置。

## 发布记录

| 版本 | 日期 | 产物 | SHA-256 |
| --- | --- | --- | --- |
| 1.0.8 | 2026-09-28 | `releases/local.douban115-1.0.8.d115p` | `9ce6f6c0da0ac91f00198cf00ec02fa595e957b42c1e2032c9aca944992ba0b4` |
| 1.0.7 | 2026-09-28 | `releases/local.douban115-1.0.7.d115p` | `7bc1226d5d79cc321286c5e4a5bc07ede7ab1e2a923b8d4b4532db20de2fbc0f` |
| 1.0.6 | 2026-09-28 | `releases/local.douban115-1.0.6.d115p` | `f601db35aebeb583ed51331b0dfe4b918c39e2d92c4922a6446322fdec5ad7e0` |
| 1.0.5 | 2026-09-28 | `releases/local.douban115-1.0.5.d115p` | `7247c891087c7cb12ab66f9efd9a9bc3ebbb07cec44063bfa7f782ee8b0cc5e1` |
| 1.1.0（已撤回） | 2026-09-28 | `releases/local.douban115-1.1.0.d115p` | `107aff079c4b27936d26307cb7dda6652d1040859d750b27e7d8a7fed02c8450` |
| 1.0.4 | 2026-09-28 | `releases/local.douban115-1.0.4.d115p` | `ff212a42314a09c65f4a67d82fd2625ffc9909af0032f3b0bd03a78c2b987b77` |
| 1.0.3 | 2026-09-28 | `releases/local.douban115-1.0.3.d115p` | `0918fc611da41ec257738668d761be4860ae5f792d57cc233fe40db587201439` |
| 1.0.1 | 2026-09-28 | `releases/local.douban115-1.0.1.d115p` | `e9b1c49e84ccd12b3e0c82dd23dd3d02f4b3e634dd975818d31600749b148060` |
| 1.0.0 | 2026-09-28 | `releases/local.douban115-1.0.0.d115p` | `0ba84dc4b72d304601514318ca015b11bc463bda96f566178f74f70a8207292b` |

- 插件 ID：`local.douban115`
- 运行时：WASM（`dian115:wasm@1`），常驻实例
- 兼容性：dian115 `>=3.8.51 <5.0.0`，Plugin API `^2.0`
- UI：Vue 3 联邦模块（federation）

## 功能

| 模块 | 说明 |
| --- | --- |
| 榜单自动订阅 | 内置 6 个榜单（即将上映、实时热门、华语口碑、全球口碑、电影口碑、BangumiTV），按 Cron 拉取 → 解析 TMDB → 按榜单位置订阅前 N 名 |
| 想看自动订阅 | 支持配置**多个**豆瓣用户 ID（逗号/中文逗号/顿号/分号/竖线/空格/换行分隔，也可直接粘贴 `douban.com/people/<ID>/` 主页链接），逐个抓取后**合并去重**，同一部片只订阅一次；空则回退 Cookie 里的 `dbcl2` |
| 用户昵称标记 | 抓取想看页时解析「头像 + 昵称」，缓存到 `wish_users`；仪表盘条目显示「想看 · 昵称 等 N 人」，设置页显示「已识别用户」chips |
| 识别兜底 | 榜单/想看条目标题在 TMDB 搜不到时，取豆瓣条目的**原名 / 又名**重搜一次（解决《流人 第六季》这类 TMDB 无中文标题的条目「TMDB 未匹配」） |
| 季号识别 | 《信号 第二季》《庆余年 第三季》等带季号标题会被剥离季号，用基础剧名搜索 TMDB（支持阿拉伯数字与中文数字季号），再回填正确 season |
| Emby 同步豆瓣 | 读取 Emby 观看记录，把「已看/在看」状态回写到豆瓣 |
| CookieCloud | 支持从本机 CookieCloud 拉取并解密豆瓣 Cookie（AES-256-CBC + Salted__，key = md5(uuid+"-"+password)[:16]） |
| 去重与对账 | 与现有订阅池对账，只做增量订阅；黑名单关键词过滤；观察期内的条目先观察再订阅 |
| 仪表盘 | 榜单快照、订阅历史、想看历史、按用户统计、运行状态、手动触发与清空历史 |
| 榜单封面 | 榜单卡片直接使用 TMDB 海报（豆瓣图床有 referer 白名单、浏览器无法直连，1.1.0 的豆瓣封面方案已回退） |
| 通知 | 订阅与同步结果通过 `POST /api/notifications/plugin` 推送 |

## 目录结构

```text
douban115/
├── manifest.template.json      # 插件 Manifest 模板（打包时替换 publisher key_id）
├── market-entry.template.json  # 市场条目模板（须与 manifest 权限完全一致）
├── frontend/icon.svg           # 插件图标
├── runtime/                    # Go 运行时（编译为 WASM）
│   ├── main.go                 # action 分发、state view、test-douban
│   ├── config.go               # 配置结构、内置榜单、默认值
│   ├── pipeline.go             # 榜单/想看流水线、TMDB 解析、订阅、历史
│   ├── douban.go               # 豆瓣抓取、Cookie、用户 ID 解析、昵称解析
│   ├── douban_alias.go         # 豆瓣条目原名/又名（TMDB 识别兜底）
│   ├── rss.go                  # RSSHub 榜单解析、季号识别
│   ├── cookiecloud.go          # CookieCloud 拉取与解密
│   ├── dashboard.go            # 仪表盘数据聚合
│   ├── hostapi.go / bridge.go  # Host Call 封装
│   ├── cron.go / scheduler.go  # 定时调度
│   ├── jobslice.go             # 同步任务分片框架（断点续跑）
│   ├── jobsteps.go             # 榜单/想看/Emby 三个同步的分片实现
│   ├── mem.go                  # WASM 内存采样（崩溃诊断日志）
│   └── taskqueue.go            # 后台任务队列
├── src/                        # Vue 3 联邦 UI
│   ├── AppPage.vue             # 设置页
│   ├── DashboardPanel.vue      # 仪表盘
│   └── main.ts                 # 本地预览入口（含示例数据）
└── scripts/
    ├── build-runtime.mjs       # Go → WASM 构建
    ├── package.mjs             # 签名打包（Ed25519）
    └── wasm-harness.mjs        # 本地测试台（149 项断言）
```

## 构建与发布

前置：Node 22+、Go 1.22+，以及一份 `dian115` 公共仓库（提供 `docs/plugin-platform/conformance/` 校验脚本）。

```bash
npm install

# 前端类型检查 + 构建，然后编译 WASM 运行时
npm run build

# 契约/权限/构建产物校验（需在 dian115 仓库旁并列存放）
npm run check

# 完整流程：build + check + 签名打包，产出 releases/local.douban115-<version>.d115p
npm run release
```

签名私钥默认读取项目根目录的 `developer-ed25519-private.pem`（可由 `npm run package -- --generate-key` 生成），也可通过环境变量 `DIAN115_PLUGIN_SIGNING_KEY` 指定。**私钥、`build/`、`releases/`、`market-entry.generated.json` 均不得提交。**

### 本地测试台

`scripts/wasm-harness.mjs` 在 Node 里直接驱动编译出的 WASM，mock 掉 RSSHub / 豆瓣 / TMDB / 宿主 Host Call，覆盖榜单同步、季号识别（中文数字 + 剥离季号）、按榜单位置订阅、TMDB 候选打分与原名回退、豆瓣原名/又名兜底识别、多用户想看合并去重、昵称解析与缓存、CookieCloud 解密、Emby 同步、去重对账、后台任务队列等场景：

```bash
node scripts/wasm-harness.mjs     # 140 项断言
```

### 安装

插件中心 → 导入插件包（选择 `releases/*.d115p`）→ 查看权限声明并同意 → 启用。

## 配置项

| 配置 | 说明 |
| --- | --- |
| 豆瓣 Cookie | 含 `dbcl2`，仅存 Host Storage，不下发 UI |
| 豆瓣用户 ID | 支持多个（分隔符见上），留空时从 Cookie 自动解析，也可直接粘贴个人主页链接 |
| RSSHub 域名 | 默认 `https://rsshub.ddsrem.com` |
| CookieCloud | 地址 / UUID / 密码；本机 dian115 内置服务挂在 Web 端口 `/cookiecloud`，默认 `http://127.0.0.1:8095/cookiecloud` |
| 榜单订阅 | 每个榜单独立开关、订阅前 N 名、最低评分、最低年份、地区筛选 |
| 黑名单关键词 | 每行一个，支持 `regex:` 前缀 |
| 观察期 | 0 关闭；开启后新条目先观察 N 天再订阅 |
| 三种 Cron | 榜单同步（默认 `0 8 * * *`）、想看同步（默认 `0 */6 * * *`）、Emby 同步（默认 `*/30 * * * *`） |
| 想看范围 | 只看最近 N 天、翻页数 |
| Emby | 地址 / API Key / 用户 ID / 同步策略 |

## 权限声明

- `permissions.apis`：TMDB 搜索与详情（3 项）、订阅池读写（2 项）、插件 storage 读写（2 项）、插件通知（1 项）。
- `permissions.network`：RSSHub 与豆瓣域名走 `system` 路由（跟随宿主代理），其中 `m.douban.com` 除移动页条目信息外还用于取条目的原名/又名（TMDB 识别兜底）；本机 CookieCloud 候选地址（`127.0.0.1` / `localhost` 的 3000、8088、8080 端口）显式声明 `proxy_mode: "direct"`，避免宿主全局代理拦截内网自环请求。
- `market-entry.template.json` 与 `manifest.template.json` 的权限列表必须完全一致，否则契约校验失败。

## 已知限制

- 宿主前台 action 存在约 10 秒硬超时（文档写 30 秒），因此拉取豆瓣、CookieCloud 同步、榜单同步等耗时操作一律走后台任务队列（`run_requests` + 常驻实例消费）。
- 后台预算也不是无限的：一次同步若被当成一次连续计算来跑（榜单同步实测 60–150 秒、Emby 同步可达数百次外网请求），宿主侧的活性探测与排队调用长时间得不到响应，累积失败后会按 `restart_policy` 回收整个模块（表现为「插件崩溃重启」）。因此同步任务一律**分片执行**：每片只做 5 秒之内的工作，片间主动让出，进度落在 `job_state`，被回收后下一轮从断点继续；同类任务互斥，不会重入。Emby 同步每轮另设 40 条的上限，避免首轮几百条请求把任务拖到几十分钟。
- WASM 运行时是单线程，`host_call` 同步阻塞，Go 侧 context 超时无法中断进行中的 Host Call。
- 宿主 broker 外部 HTTP 默认总超时 10 秒、响应上限 8 MiB；大响应（约 650 KB）传输可能耗时 9–11 秒。
- 宿主 storage 读取约 30 ms/KB，榜单快照与历史都只存必要的字段；豆瓣条目原名/又名只有识别失败的条目才会请求，且会缓存（含「取过但没有」的负结果）。
- 兜底识别依赖豆瓣条目的 `original_title`/`aka`：若豆瓣对该条目也没录原名，或 TMDB 侧确实不存在对应条目，则仍会保持「TMDB 未匹配」（宁可不显示封面，也不错配）。

## 许可

MIT
