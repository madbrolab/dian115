<p align="center">
  <img src="frontend/public/logo.jpg" alt="DIAN-115 Logo" width="86" />
</p>

<h1 align="center">DIAN-115</h1>

<p align="center">
  <strong>115 网盘媒体自动化与 Emby / Navidrome 管理平台</strong><br />
  连接资源发现、订阅、转存、整理、入库与播放，让个人收藏和多人影音服务拥有完整的工作流。
</p>

<p align="center">
  <a href="https://madbrolab.github.io/dian115/">用户 WIKI</a> ·
  <a href="https://madbrolab.github.io/dian115/demo/">在线 Demo</a> ·
  <a href="https://t.me/dian115group">Telegram 交流群</a> ·
  <a href="docs/plugin-platform/README.md">插件开发文档</a> ·
  <a href="tools/database-migration/README.md">SQLite → PostgreSQL 迁移</a>
</p>

<p align="center">
  <img src="https://img.shields.io/badge/Platform-Linux-333333?logo=linux&logoColor=white" alt="Linux 平台" />
  <img src="https://img.shields.io/badge/Deployment-Docker-2496ED?logo=docker&logoColor=white" alt="Docker 部署" />
  <img src="https://img.shields.io/badge/License-Private-64748B" alt="私有授权" />
</p>

## 项目介绍

DIAN-115 是面向个人、家庭与自托管用户的媒体自动化管理平台。它连接 115 网盘、CloudDrive2 / AURA、Emby、Navidrome、PT 站点、Telegram 和通知服务，将资源获取、媒体整理、STRM 生成、媒体入库、播放代理与日常维护组织成可追踪的工作流。

主程序采用私有授权，通过发布镜像部署。本仓库提供用户文档、规则与第三方插件开发资料；完整使用教程见 [用户 WIKI](https://madbrolab.github.io/dian115/)。

**典型工作流：** 发现资源 → 订阅或获取 → 识别与整理 → 生成 STRM → Emby 入库与播放 → 通知、分享与维护。

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

## 在线体验

| 演示入口 | 体验内容 |
| --- | --- |
| [管理控制台](https://madbrolab.github.io/dian115/demo/) | 探索、订阅、整理、文件、插件和系统管理。 |
| [用户门户](https://madbrolab.github.io/dian115/demo/portal/) | 用户账户、媒体、求片、积分、社区和工单。 |
| [音乐播放器](https://madbrolab.github.io/dian115/demo/music/) | 专辑、歌曲、歌单、收藏、歌词和播放界面。 |

Demo 使用静态样例数据展示页面与交互。真实账号连接、后台任务与媒体服务在自己的部署实例中配置。

## 授权激活

首次启动时，按页面提示填写 License Key 完成激活；已激活实例可从账号菜单更换密钥，页面提示需要重启时按提示操作。详细步骤见 [授权与激活指南](https://madbrolab.github.io/dian115/#guide/license)。

实际承载量取决于主机、账号与外部服务，授权有效期与附加功能以收到的密钥为准。授权或激活遇到问题时，可联系 [@succt](https://t.me/succt)。

## 部署指南

**优先推荐 Host 网络部署（Linux / NAS）。** DIAN-115 直接使用宿主机网络，Web 管理端、Emby 代理和音乐服务无需逐项配置 Docker 端口映射，适合多实例代理场景。下方完整 Compose 示例默认采用 Host 网络；需要 Docker 网络隔离时，可选择桥接模式。

### 环境准备

- 使用 Linux / NAS 主机，安装 Docker Engine 与 Docker Compose v2。
- 准备持久化配置目录、媒体目录和云盘挂载目录。
- 使用 CD2 时，先完成 FUSE、共享挂载、API Token 和云盘挂载设置，参见 [CD2 部署与接入](https://madbrolab.github.io/dian115/#guide/cd2)。
- 为 DIAN-115 与 Emby 配置一致的媒体目录和云盘目录，参见 [路径搭配指南](https://madbrolab.github.io/dian115/#guide/paths)。

### 推荐部署：Docker Compose · Host 网络

新建部署目录，创建 `config` 和 `dian115AI` 子目录，将下面示例保存为 `compose.yml`。`/mnt/user/media` 与 `/mnt/cache/CloudNAS` 是宿主机示例路径，部署前替换为实际目录。

```yaml
services:
  dian115:
    image: madbrolab/dian115:latest
    container_name: dian115
    restart: unless-stopped
    network_mode: host
    environment:
      - PORT=8095
      - TZ=Asia/Shanghai
    volumes:
      - ./config:/config
      - ./dian115AI:/dian115AI
      - /mnt/user/media:/媒体库
      - /mnt/cache/CloudNAS:/CloudNAS:rslave
      # 需要 DianCupLite 容器管理时，按部署方案配置 Docker 访问。
      # - /var/run/docker.sock:/var/run/docker.sock
```

启动并查看状态：

```bash
docker compose pull
docker compose up -d
docker compose ps
docker compose logs --tail=200 dian115
```

访问 `http://服务器IP:8095`，设置管理员密码并完成授权激活。`network_mode: host` 下无需添加 `ports`；Emby 代理和音乐服务也直接使用各自在页面中配置的宿主机端口，多个服务或实例应设置不同端口。

### 可选部署：桥接网络

需要 Docker 网络隔离时，可改用桥接网络。从上方示例中移除 `network_mode: host`，在 `dian115` 服务下添加：

```yaml
ports:
  - "8095:8095"
  - "8098:8098" # 第一个 Emby 代理实例，按实际配置调整
  # - "4534:4534" # 使用独立音乐服务器时按实际配置启用
```

多个 Emby 代理实例或其他独立服务端口需要分别映射。使用反向代理时，将目标指向实际的服务地址与端口。

### 端口与目录

| 项目 | 默认值或示例 | 说明 |
| --- | --- | --- |
| Web 管理端 | `8095` | 管理后台、API 与插件入口；可通过 `PORT` 调整。 |
| Emby 代理 | `8098` | 第一个实例的默认端口，其他实例按页面配置。 |
| 独立音乐服务器 | `4534` | 按音乐服务配置启用。 |
| 应用数据 | `/config` | 数据库、账号与设置，必须持久化并备份。 |
| AI 工作区 | `/dian115AI` | 使用 AI 文件与仓库工具时持久化。 |
| 媒体目录 | `/媒体库` | 本示例的媒体和 STRM 输出目录，需与 Emby 保持一致。 |
| 云盘挂载根 | `/CloudNAS` | CD2 向 DIAN-115 与 Emby 提供的共享目录。 |

CD2 使用 `/mnt/cache/CloudNAS:/CloudNAS:shared` 发布挂载，DIAN-115 与 Emby 使用 `/mnt/cache/CloudNAS:/CloudNAS:rslave` 接收挂载。宿主机也需支持相应的挂载传播。保存 CD2 API 设置后点击“自动读取”，确认挂载路径，例如 `/CloudNAS/CloudDrive`。

### PostgreSQL 与旧 SQLite 数据迁移

新装 PostgreSQL 直接配置数据库类型和连接串，参见[新装教程](https://madbrolab.github.io/dian115/docs/database-postgresql/)。已有 SQLite 数据的实例，先停止并备份完整配置目录，再使用公开脚本将业务数据导入空 PG 库，最后保留原目录并以 PG 连接启动。

- [迁移脚本与详细使用教程](tools/database-migration/README.md)：配置目录、兼容镜像、空目标库、Host / Docker 网络、特殊密码、自定义参数、错误处理和回退。
- [直接下载 Shell 脚本](https://raw.githubusercontent.com/madbrolab/dian115/main/tools/database-migration/migrate-sqlite-to-pgsql.sh)。

脚本调用所选镜像内的迁移工具；先取得包含该工具的兼容镜像，具体发布状态和填写示例见教程。

### FlareSolverr：按需接入

使用 UIndex 等需要 Cloudflare 验证的来源时，可在同一份 Compose 中增加以下服务：

```yaml
services:
  # 保留原有 dian115 服务，在 services 下追加此服务。
  flaresolverr:
    image: ghcr.io/flaresolverr/flaresolverr:latest
    container_name: flaresolverr
    restart: unless-stopped
    ports:
      - "127.0.0.1:8191:8191" # 供同机 Host 网络访问
    environment:
      - LOG_LEVEL=info
      - TZ=Asia/Shanghai
```

```bash
docker compose up -d flaresolverr
```

在 **系统设置 → FlareSolverr 过盾设置** 中保存地址并测试连接：

| 部署关系 | 服务地址 |
| --- | --- |
| DIAN-115 使用 Host 网络，FlareSolverr 在同一宿主机（推荐搭配） | `http://127.0.0.1:8191`，使用上方端口映射。 |
| DIAN-115 与 FlareSolverr 在同一 Compose 桥接网络 | `http://flaresolverr:8191`，服务间访问可不映射端口。 |
| 不同机器或不同 Docker 网络 | 映射到实际内网地址后使用 `http://FlareSolverr主机IP:8191`。 |

桥接网络容器中的 `127.0.0.1` 指向容器自身。首次请求可能因浏览器环境启动而较慢；完整步骤见 [FlareSolverr 指南](https://madbrolab.github.io/dian115/#guide/flaresolverr)。

## 推荐配置顺序

1. **初始化与激活**：设置管理员密码和 License Key，确认重启后数据与授权状态保留。
2. **云盘与路径**：添加 115 主账号，配置 CD2 / AURA 地址、Token、挂载点及实际云盘名称，验证目录可读。
3. **迁移评估**：已有 Emby 媒体库时，先按下方流程保留媒体画像与路径映射。
4. **媒体服务**：接入 Emby / Navidrome，配置代理端口、路径转换、Webhook / Madby 和 OpenAPI Key。
5. **资源来源**：验证下载器、PT 站点、RSS、Telegram 频道监控与MADOW的连接。
6. **整理与 STRM**：用小目录测试识别、命名、分类和洗版，先全量建树，再生成 STRM，验证播放后开启实时或定时同步。
7. **通知与扩展**：配置各通知渠道、AI、音乐与用户门户，验证消息、播放和访问权限。
8. **日常运维**：设置备份与维护计划，通过任务队列、日志、缓存和账号状态持续检查。

接收、整理、STRM 输出与播放分别验证。完整教程见 [配置指南](https://madbrolab.github.io/dian115/#setup)。

## 已有 Emby 媒体库迁移

已有媒体库由其他工具生成时，先处理媒体画像与旧路径，确认后再生成新 STRM。推荐流程：

1. 备份旧 Emby 数据库、STRM 目录与 DIAN-115 配置，完成账号、CD2 与授权连接。
2. 在 STRM 规则中只构建目录树，暂不生成 STRM。
3. 通过 **插件中心 → Emby 媒体画像** 读取旧库条目、路径、媒体流与章节信息。
4. 配置路径替换，将旧 Emby 路径匹配到新的 115 / CD2 目录树，检查未匹配条目。
5. 配置 Madby 的 DIAN-115 地址与 OpenAPI Key，核对原生 Webhook 与 Madby 的事件配置，避免重复通知。
6. 将可用画像上报到MADOW SHA1 FFP，保留可复用的识别结果。
7. 确认路径、画像、Madby 与通知正常后，再生成 STRM 并进行 Emby 扫描。

路径尚未匹配时，同时生成 STRM 与执行大规模扫描会增加重复条目和排查成本。迁移应先完成小范围验证，再逐步切换媒体库。

## 更新与维护

- 优先备份完整 `/config`，同时保存 STRM 输出、路径规则和关键插件配置；使用 AI 工作区时一并备份。
- 更新前结束重要任务并完成备份，再执行以下命令，更新后核对账号、连接与最近日志。

```bash
docker compose pull dian115
docker compose up -d dian115
docker compose logs --tail=200 dian115
```

- 网络或连接异常时，先检查系统设置中的连接测试，再结合任务详情与运行日志定位问题。
- 整理规则或挂载路径变化后，先在小目录验证读取、识别、输出与播放。
- Cookie、Bot Token、OpenAPI Key、完整授权码等敏感信息应妥善保管；反馈问题时对相关日志脱敏。

## 插件开发与规则贡献

第三方插件开发以 [插件平台公开文档](docs/plugin-platform/README.md) 为准，包含协议、Schema、OpenAPI、Vue Federation UI 契约、完整示例和黑盒联调工具。插件开发使用公开契约，主程序源码保持私有。

内置工具随主程序运行，第三方插件通过插件平台安装与管理。规则贡献请阅读 [贡献指南](CONTRIBUTING.md)；在线规则入口见 [online-rules](online-rules/README.md)。

## 文档与支持

- [用户 WIKI](https://madbrolab.github.io/dian115/)：功能、部署、配置、授权与门户教程。
- [Telegram 交流群](https://t.me/dian115group)：使用交流与问题反馈。
- [官方支持 @succt](https://t.me/succt)：授权与激活问题。

反馈问题时，请提供版本、部署方式、复现步骤和脱敏后的相关日志。

## 致谢

感谢以下项目与服务为媒体管理工作流提供支持：

[CloudDrive2](https://www.clouddrive2.com/) · [Emby](https://emby.media/) · [Navidrome](https://www.navidrome.org/) · [TMDB](https://www.themoviedb.org/)
