<p align="center">
  <img src="docs/assets/logo.jpg" alt="DIAN-115 Logo" width="86" />
</p>

<h1 align="center">DIAN-115</h1>

<p align="center">
  <strong>115 网盘媒体自动化与 Emby / Navidrome 管理平台</strong><br />
  连接资源发现、订阅、转存、整理、入库与播放，让个人收藏和多人影音服务拥有完整的工作流。
</p>

## 快速导航

| 入口 | 内容 |
| --- | --- |
| **安装与升级** | Docker Compose 新装推荐 PostgreSQL · [Host 网络](docs/user/installation.md#host-网络) · [桥接网络](docs/user/installation.md#桥接网络) · [授权激活](docs/user/installation.md#授权激活) · [升级维护](docs/user/installation.md#更新与维护) · [SQLite 数据迁移](tools/database-migration/README.md) |
| **使用与体验** | [用户 Wiki](https://madbrolab.github.io/dian115/) · [管理端 Demo](https://madbrolab.github.io/dian115/demo/#/overview) · [用户门户](https://madbrolab.github.io/dian115/demo/portal/) · [音乐播放器](https://madbrolab.github.io/dian115/demo/music/) · [项目截图](docs/assets/screenshots/) |
| **插件商店** | 在 DIAN115 的插件中心安装与更新 · [官方插件安装包和版本说明](https://github.com/madbrolab/dian115-plugin-releases/releases) |
| **插件开发与集成** | [开发文档](docs/plugin-platform/README.md) · [快速开始](docs/plugin-platform/guides/quickstart.md) · [MoviePilot PT 连接](docs/plugin-platform/examples/moviepilot-bridge/README.md) |
| **规则与配套** | [在线规则](online-rules/README.md) · [识别词表](rules/recognition/) · [通知模板](docs/user/notifications/README.md) · [浏览器扩展](browser-extension/video-downloader/README.md) · [Madby](https://github.com/madbrolab/madby) |
| **问题反馈** | [GitHub Issues](https://github.com/madbrolab/dian115/issues) · [Telegram 交流群](https://t.me/dian115group) · [授权私聊 @succtxx_bot](https://t.me/succtxx_bot) |

DIAN115 面向个人、家庭与自托管用户，将资源发现、订阅、转存、整理、STRM 生成、入库与播放串在一起。主程序通过 [Docker 镜像](https://hub.docker.com/r/madbrolab/dian115)部署，使用 License Key 激活。

## 核心功能

| 功能模块 | 主要能力 |
| --- | --- |
| 资源发现与订阅 | 探索电影、剧集与演员；接入 PT 搜索、RSS、Telegram 频道、UIndex、TGx、TheRARBG、海盗湾与MADOW，按来源和质量策略订阅。 |
| 115 账号与文件 | 多账号配置、Cookie 健康检查、离线下载、分享与回收站维护；支持目录书签、批量改名与文件管理。 |
| 媒体整理 | TMDB 刮削、AI 辅助识别、命名模板、分类规则、洗版和多版本管理；支持本地整理与 CD2 云端整理。 |
| STRM 与虚拟影库 | 目录树构建，全量、增量和实时同步，STRM 生成、孤立文件清理与播放链接模式配置。 |
| Emby 接入与迁移 | 多实例播放代理、媒体浏览、缺集检查、媒体分享、Webhook / Madby 事件接入，以及 Emby 媒体画像与 FFP 复用。 |
| 音乐中心 | 独立音乐服务器，无需部署NAVIDROME，可使用支持subsonic协议的第三方播放器链接。提供专辑、歌单、歌词和独立播放器。 |
| 内置工具 | 文件秒传、多号云迁移、秘享空间、视频下载器、Emby 封面、AI 字幕、统计海报、PT 刷流与站点统计等。 |
| 通知与 AI | Telegram、企业微信、微信 ClawBot 独立配置通知；点点 AI 助手支持流式对话，按使用位置选择模型和管理工具。 |
| 用户门户 | 独立用户入口，支持共享或独享账号、求片、工单、消息、签到积分、社区、徽章与观影记录。 |
| 系统与运维 | 任务队列、运行日志、全局与 FFP 缓存、DianCupLite 容器管理，以及网络、API、词表和安全设置。 |

功能依赖相应的账号、外部服务与授权配置。详细说明见 [功能介绍](https://madbrolab.github.io/dian115/#features) 和 [门户指南](https://madbrolab.github.io/dian115/#guide/portal)。

## 参与贡献

在线规则贡献请阅读[贡献指南](CONTRIBUTING.md)。反馈问题时，请提供版本、部署方式、复现步骤和脱敏日志。

## 致谢

感谢以下项目与服务为媒体管理工作流提供支持：

[CloudDrive2](https://www.clouddrive2.com/) · [Emby](https://emby.media/) · [Navidrome](https://www.navidrome.org/) · [TMDB](https://www.themoviedb.org/)
