# 安装、升级与迁移

## 授权激活

首次启动时，按页面提示填写 License Key 完成激活；已激活实例可从账号菜单更换密钥，页面提示需要重启时按提示操作。详细步骤见 [授权与激活指南](https://madbrolab.github.io/dian115/#guide/license)。

实际承载量取决于主机、账号与外部服务，授权有效期与附加功能以收到的密钥为准。授权或激活遇到问题时，可联系 [@succt](https://t.me/succt)。

## 部署指南

**新装推荐 PostgreSQL（PGSQL）。** 下面两套 Docker Compose 都包含 DIAN115 和 PostgreSQL，选一套即可。已有 SQLite 数据的实例先按[迁移流程](#postgresql-与旧-sqlite-数据迁移)处理。

| 部署方式 | 适用场景 | 数据库连接 |
| --- | --- | --- |
| [Host 网络](#host-网络) | 推荐用于 Linux / NAS，尤其适合多个 Emby 代理实例和独立音乐服务 | 应用通过宿主机回环地址连接 PostgreSQL |
| [桥接网络](#桥接网络) | 按需映射应用端口，使用独立的 Docker 网络 | 应用在 Compose 网络内通过服务名 `postgres` 连接 |

### 环境准备

- 使用 Linux / NAS 主机，安装 Docker Engine 与 Docker Compose v2。
- 新建部署目录，创建 `config` 和 `dian115AI` 子目录，选一种网络方式，将相应示例保存为 `compose.yml`。按实际情况替换媒体和云盘挂载的宿主机路径。
- 在同一目录新建 `.env`，运行 `openssl rand -hex 24` 生成密码，填到 `POSTGRES_PASSWORD=` 后。两套示例都直接用这个值初始化 PostgreSQL 并构造连接串，十六进制密码可以直接写入连接串。
- 使用 CD2 时，先完成 FUSE、共享挂载、API Token 和云盘挂载设置，参见 [CD2 部署与接入](https://madbrolab.github.io/dian115/#guide/cd2)。
- 为 DIAN-115 与 Emby 配置一致的媒体目录和云盘目录，参见 [路径搭配指南](https://madbrolab.github.io/dian115/#guide/paths)。

```dotenv
POSTGRES_PASSWORD=
```

### Host 网络

DIAN115 直接使用宿主机端口。PostgreSQL 只把端口映射到宿主机的 `127.0.0.1:15432`。

```yaml
services:
  postgres:
    image: postgres:18
    restart: unless-stopped
    environment:
      POSTGRES_DB: dian115
      POSTGRES_USER: dian115
      POSTGRES_PASSWORD: "${POSTGRES_PASSWORD:?请在 .env 设置数据库密码}"
    ports:
      - "127.0.0.1:15432:5432"
    volumes:
      - ./postgres-data:/var/lib/postgresql
    healthcheck:
      test: ["CMD", "pg_isready", "-h", "127.0.0.1", "-U", "dian115", "-d", "dian115"]
      interval: 5s
      timeout: 3s
      retries: 20

  dian115:
    image: madbrolab/dian115:latest
    container_name: dian115
    restart: unless-stopped
    network_mode: host
    depends_on:
      postgres:
        condition: service_healthy
    environment:
      PORT: "8095"
      TZ: Asia/Shanghai
      DIAN115_DB_DRIVER: pgsql
      DIAN115_PG_DSN: "postgres://dian115:${POSTGRES_PASSWORD}@127.0.0.1:15432/dian115?sslmode=disable"
    volumes:
      - ./config:/config
      - ./dian115AI:/dian115AI
      - /mnt/user/media:/媒体库
      - /mnt/cache/CloudNAS:/CloudNAS:rslave
      # 需要 DianCupLite 容器管理时，按部署方案配置 Docker 访问。
      # - /var/run/docker.sock:/var/run/docker.sock
```

Emby 代理和独立音乐服务直接使用各自在页面中配置的宿主机端口。多个实例应设置不同端口。

### 桥接网络

两个服务使用同一个 Compose 网络。PostgreSQL 通过 `postgres:5432` 访问，宿主机仅映射需要对外提供的应用端口。

```yaml
services:
  postgres:
    image: postgres:18
    restart: unless-stopped
    environment:
      POSTGRES_DB: dian115
      POSTGRES_USER: dian115
      POSTGRES_PASSWORD: "${POSTGRES_PASSWORD:?请在 .env 设置数据库密码}"
    volumes:
      - ./postgres-data:/var/lib/postgresql
    healthcheck:
      test: ["CMD", "pg_isready", "-h", "127.0.0.1", "-U", "dian115", "-d", "dian115"]
      interval: 5s
      timeout: 3s
      retries: 20

  dian115:
    image: madbrolab/dian115:latest
    container_name: dian115
    restart: unless-stopped
    depends_on:
      postgres:
        condition: service_healthy
    ports:
      - "8095:8095"
      # - "8098:8098" # 启用 Emby 代理时按实例配置添加
      # - "4534:4534" # 启用独立音乐服务时按实际配置添加
    environment:
      PORT: "8095"
      TZ: Asia/Shanghai
      DIAN115_DB_DRIVER: pgsql
      DIAN115_PG_DSN: "postgres://dian115:${POSTGRES_PASSWORD}@postgres:5432/dian115?sslmode=disable"
    volumes:
      - ./config:/config
      - ./dian115AI:/dian115AI
      - /mnt/user/media:/媒体库
      - /mnt/cache/CloudNAS:/CloudNAS:rslave
      # 需要 DianCupLite 容器管理时，按部署方案配置 Docker 访问。
      # - /var/run/docker.sock:/var/run/docker.sock
```

多个 Emby 代理实例或其他独立服务端口需要分别映射。使用反向代理时，将目标指向实际的服务地址与端口。

### 启动与检查

在部署目录执行以下命令。应用会在 PostgreSQL 就绪后启动，并为新库初始化表结构。

```bash
docker compose config --quiet
docker compose up -d
docker compose ps
docker compose logs --tail=200 dian115
```

访问 `http://服务器IP:8095`，设置管理员密码并完成[授权激活](#授权激活)。

### 端口与目录

| 项目 | 默认值或示例 | 说明 |
| --- | --- | --- |
| Web 管理端 | `8095` | 管理后台、API 与插件入口；可通过 `PORT` 调整。 |
| Emby 代理 | `8098` | 第一个实例的默认端口，其他实例按页面配置。 |
| 独立音乐服务器 | `4534` | 按音乐服务配置启用。 |
| 应用数据 | `/config` | 保留应用配置与本地文件，必须持久化并备份。 |
| PostgreSQL 数据 | `./postgres-data` | 宿主机上的数据库目录，采用 PGSQL 时应另做数据库备份。 |
| AI 工作区 | `/dian115AI` | 使用 AI 文件与仓库工具时持久化。 |
| 媒体目录 | `/媒体库` | 本示例的媒体和 STRM 输出目录，需与 Emby 保持一致。 |
| 云盘挂载根 | `/CloudNAS` | CD2 向 DIAN-115 与 Emby 提供的共享目录。 |

CD2 使用 `/mnt/cache/CloudNAS:/CloudNAS:shared` 发布挂载，DIAN-115 与 Emby 使用 `/mnt/cache/CloudNAS:/CloudNAS:rslave` 接收挂载。宿主机也需支持相应的挂载传播。保存 CD2 API 设置后点击“自动读取”，确认挂载路径，例如 `/CloudNAS/CloudDrive`。

### PostgreSQL 与旧 SQLite 数据迁移

- **已有 PostgreSQL**。可移除示例中的 `postgres` 服务和应用的 `depends_on`，将 `DIAN115_PG_DSN` 改为应用可达的数据库连接串。数据库账号须有建表权限，远程连接按服务方要求配置 TLS。密码含特殊字符时，对连接串中的密码做 URL 百分号编码。详见 [PostgreSQL 部署教程](https://madbrolab.github.io/dian115/docs/database-postgresql/)。
- **新装选用 SQLite**。在任一示例中移除 `postgres` 服务及应用的 `depends_on` 和 `DIAN115_PG_DSN`，将 `DIAN115_DB_DRIVER` 改为 `sqlite`，保留 `/config` 挂载。
- **已有 SQLite 要切换到 PostgreSQL**。先停止 DIAN115 并备份完整配置目录，用兼容镜像和下方脚本将业务数据导入空 PostgreSQL 库，最后保留原配置目录并以 PG 连接启动。

- [迁移脚本与详细使用教程](../../tools/database-migration/README.md)：配置目录、兼容镜像、空目标库、Host / Docker 网络、特殊密码、自定义参数、错误处理和回退。
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

- 优先备份完整 `/config`。使用 PostgreSQL 时同时备份数据库，并保存 STRM 输出、路径规则、关键插件配置和使用中的 AI 工作区。
- 更新前结束重要任务并完成备份，再执行以下命令，更新后核对账号、连接与最近日志。

```bash
docker compose pull dian115
docker compose up -d dian115
docker compose logs --tail=200 dian115
```

- 网络或连接异常时，先检查系统设置中的连接测试，再结合任务详情与运行日志定位问题。
- 整理规则或挂载路径变化后，先在小目录验证读取、识别、输出与播放。
- Cookie、Bot Token、OpenAPI Key、完整授权码等敏感信息应妥善保管；反馈问题时对相关日志脱敏。
