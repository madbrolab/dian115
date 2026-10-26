# DIAN115：把 SQLite 旧数据迁移到 PostgreSQL

此目录提供供用户在 Linux / NAS Docker 宿主机运行的迁移脚本。只需 Docker 和常见 Shell 命令.

- [下载迁移脚本](https://raw.githubusercontent.com/madbrolab/dian115/main/tools/database-migration/migrate-sqlite-to-pgsql.sh)
- [在线使用文档](https://madbrolab.github.io/dian115/docs/database-migration/)
- [新装 PostgreSQL](https://madbrolab.github.io/dian115/docs/database-postgresql/)

**脚本调用所选 DIAN115 镜像内的 `/usr/local/bin/dian115-db`。镜像必须包含 PostgreSQL 支持及这个程序。教程对应 v5.0.42 起的迁移接口；请使用实际已取得、包含该工具的对应版本或本地镜像，不要仅凭 `latest` 名称判断版本。**


新装没有旧 SQLite 数据时，直接配置 PostgreSQL 连接并启动 DIAN115，不运行本迁移脚本。

## 1. 确定配置目录、镜像与服务名

以下例子假设：

| 项目 | 例子 | 你需要填写什么 |
| --- | --- | --- |
| 原容器名 / Compose 服务名 | `dian115` | 自己正在使用的名称 |
| `/config` 的宿主机目录 | `/mnt/appdata/dian115/config` | 原容器实际绑定的整个目录 |
| 主 SQLite 文件名 | `dian115.db` | 自定义文件名使用 `--db` |
| 迁移与后续运行镜像 | `dian115-pgsql:local` | 已取得的兼容版本、本地镜像或镜像摘要 |
| 目标库 / 用户 | `dian115_pg` / `dian115` | 自己新建的空库与有建表权限的账号 |

查看原容器的配置挂载和镜像：

```sh
docker inspect --format '{{range .Mounts}}{{if eq .Destination "/config"}}{{println .Source}}{{end}}{{end}}' dian115
docker inspect --format '{{.Config.Image}}' dian115
```

记录实际目录和准备使用的兼容镜像，例如：

```sh
export DIAN115_CONFIG='/mnt/appdata/dian115/config'
export DIAN115_IMAGE='dian115-pgsql:local'
```

上面的镜像名是填写示例。Docker Hub 有对应版本时可提前 `docker pull "$DIAN115_IMAGE"`；使用本地构建镜像时填写本地名称即可。迁移完成后让应用使用同一个兼容版本。

## 2. 停止旧实例并备份整个配置目录

在原 Compose 文件所在目录执行：

```sh
docker compose stop dian115
cp -a "$DIAN115_CONFIG" "${DIAN115_CONFIG}.sqlite-backup.$(date +%Y%m%d-%H%M%S)"
```

没有使用 Compose 时，把停止命令换为 `docker stop dian115`，其他步骤相同。停止所有共用该目录的 DIAN115 实例；备份完成前不要迁移。

备份整个目录，包含各业务 SQLite 分库、业务密钥、本地图片、歌词及其他资源。**不要只复制 `dian115.db`，也不要删除 `-wal`、`-shm` 或密钥文件。** 后续 DIAN115 继续绑定这个原配置目录。

备份目录放在原目录旁边，例如 `config.sqlite-backup.20261027-120000`，不要放进原 `config` 内。

## 3. 准备空的 PostgreSQL 目标库

已有 PostgreSQL 时，为此次迁移新建一个空数据库，账号应有该库的连接、建 schema、建表和建索引权限。推荐让迁移账号成为目标库的所有者。

管理员可以进入自己的 PostgreSQL 容器执行 SQL；下面的 `PG容器名` 和 `管理员账号` 必须替换为实际值：

```sh
docker exec -it PG容器名 psql -U 管理员账号 -d postgres
```

在 `psql` 内执行以下示例；已有账号时跳过第一条：

```sql
CREATE ROLE dian115 LOGIN PASSWORD 'YourStrongPassword';
CREATE DATABASE dian115_pg OWNER dian115;
```

退出 `psql` 使用 `\q`。已有正常业务数据的 PG 库不能作为此次导入目标；不要提前用 DIAN115 向这个库写入数据。迁移程序负责创建所需业务表。

需要安装 PostgreSQL 时，先按[新装教程](https://madbrolab.github.io/dian115/docs/database-postgresql/)启动数据库服务，暂时保持 DIAN115 停止。

## 4. 选择连接方式

`DIAN115_PG_DSN` 是完整的 PostgreSQL 连接串。以下密码均为示例，替换成自己的值。

### 方式 A：PG 在同一宿主机，通过映射端口连接

例如 PG 发布了宿主机 `15432` 到容器 `5432`，使用脚本默认的 Linux `host` 网络：

```sh
export DIAN115_PG_DSN='postgres://dian115:YourStrongPassword@127.0.0.1:15432/dian115_pg?sslmode=disable'
```

这里填**宿主机端口 `15432`**，不是 PG 容器内的 `5432`。后续 DIAN115 也使用 Host 网络时，可以直接复用这个连接串。

### 方式 B：迁移容器与 PG 在同一个 Docker 网络

例如 PG 的服务名为 `postgres`，两者连接到 `dian115-storage` 网络：

```sh
export DIAN115_PG_DSN='postgres://dian115:YourStrongPassword@postgres:5432/dian115_pg?sslmode=disable'
```

执行脚本时加 `--network dian115-storage`。此时填写 **PG 服务名和容器端口 `5432`**；不要用 `127.0.0.1`，它在桥接容器内指向迁移容器自己。

后续 DIAN115 也加入同一网络，才能继续使用 `postgres:5432`。也可以连接同一个 PG 库的另一个可达地址；要保持用户、数据库和实际目标相同。

### 方式 C：PG 在另一台机器

填写那台机器可达的 IP / 域名和服务端口。PG 应允许来自当前宿主机的连接；按服务端要求配置 TLS，例如 `sslmode=require` 或提供证书后使用 `verify-full`。

本教程的 `sslmode=disable` 例子用于受信任的本机或私有网络，远程服务按其实际 TLS 配置填写。

### 密码包含特殊字符

连接串中用户名和密码里的保留字符需要进行 URL 百分号编码，例如：

| 字符 | 编码 |
| --- | --- |
| `@` | `%40` |
| `:` | `%3A` |
| `/` | `%2F` |
| `?` | `%3F` |
| `#` | `%23` |
| `%` | `%25` |
| `$` | `%24` |
| `&` | `%26` |
| 单引号 | `%27` |

例如数据库密码 `Demo@2026#1`，连接串中的密码部分应写成 `Demo%402026%231`；在 PostgreSQL 中设置密码时仍使用原始密码。Shell 里用单引号包住完整连接串，不要对已经编码的密码重复编码。

## 5. 下载脚本

在 Docker 宿主机执行，文件会保存到当前目录：

```sh
curl --fail --location \
  'https://raw.githubusercontent.com/madbrolab/dian115/main/tools/database-migration/migrate-sqlite-to-pgsql.sh' \
  --output migrate-sqlite-to-pgsql.sh
sh migrate-sqlite-to-pgsql.sh --help
```

如果没有 `curl`，可以在上方“下载迁移脚本”链接保存文件，再传到宿主机。脚本使用 `sh` 执行，不要求额外 `chmod`，不要把 HTML 网页另存为脚本。

## 6. 执行一次迁移

宿主机网络：

```sh
sh migrate-sqlite-to-pgsql.sh \
  --config "$DIAN115_CONFIG" \
  --image "$DIAN115_IMAGE"
```

同一 Docker 网络：

```sh
sh migrate-sqlite-to-pgsql.sh \
  --config "$DIAN115_CONFIG" \
  --image "$DIAN115_IMAGE" \
  --network dian115-storage
```

脚本创建临时容器，绑定原配置目录，调用所选镜像的迁移程序，结束后移除临时容器。它不会自动启动 DIAN115，也不会修改原 Compose 文件。

正常完成时，迁移程序输出类似以下内容，随后脚本提示“迁移完成”：

```json
{"backend":"pgsql","ready":true}
```

不要只看到某几张表的导入行数就启动应用；等待整个脚本正常结束。**不需要额外的迁移报告、激活文件或复验命令。**

## 7. 用 PostgreSQL 启动 DIAN115

在原 `dian115` 服务中，把 `image` 设为步骤 1 选定的兼容镜像，并增加这两个环境变量；保留原端口、媒体挂载以及原 `/config`：

```yaml
environment:
  DIAN115_DB_DRIVER: pgsql
  DIAN115_PG_DSN: 'postgres://dian115:YourStrongPassword@127.0.0.1:15432/dian115_pg?sslmode=disable'
```

把示例替换成步骤 4 选定的实际连接。如果使用 Docker 网络，确认应用加入同一网络。Compose 使用 `$` 插值；连接串含保留字符时按前述规则编码密码，避免把原始 `$` 直接写进 Compose。

然后执行：

```sh
docker compose up -d dian115
```

通过 NAS / Docker 管理界面部署的用户，在原容器设置里增加相同环境变量并启动原容器，继续使用原来的 `/config` 挂载。

登录后打开“系统设置 → 基础设置 → 数据库维护”，确认显示 PostgreSQL 与此次目标库名；查看原来的账号、整理规则、虚拟影库、音乐等内容。这是迁移后的使用确认，不是额外的启动门槛。

## 参数一览

| 参数 / 变量 | 默认值 | 说明 |
| --- | --- | --- |
| `--config` | 无，必填 | 原容器 `/config` 对应的完整宿主机目录 |
| `--image` | `DIAN115_IMAGE`，未设置则 `madbrolab/dian115:latest` | 必须包含 `dian115-db`；推荐明确指定版本 |
| `--network` | `host` | Linux 宿主机网络；桥接时填 PG 所在网络 |
| `--db` | `dian115.db` | 只填主库文件名，不填路径 |
| `--timeout` | `2h` | 本次迁移的总时限，例如 `6h` |
| `DIAN115_PG_DSN` | 无，必填 | 目标 PostgreSQL 连接串 |

自定义主库名、较长迁移时限的例子：

```sh
sh migrate-sqlite-to-pgsql.sh \
  --config "$DIAN115_CONFIG" --image "$DIAN115_IMAGE" \
  --db my-dian115.db --timeout 6h
```

`--db` 指的是原实例实际使用的主库文件名；不要为了迁移随意重命名主库和分库。

## 迁移保留与忽略的内容

- 导入当前版本仍使用的业务表和字段，保留记录 ID、自增序号和加密凭据；音乐按当前结构转换。
- 历史废表、废列、旧索引和无关文件忽略；未使用的可选分库、表或新增字段按当前默认值初始化。
- 原 SQLite 文件和业务密钥保留；本地图片、歌词等文件继续通过原 `/config` 提供。
- 导入后的新数据只写入 PostgreSQL，不会同步回旧 SQLite。

## 失败时怎么处理

| 现象 | 处理方法 |
| --- | --- |
| 找不到 `dian115-db` / `stat ... no such file` | 所选镜像没有迁移工具。取得兼容镜像，再通过 `--image` 指定；脚本本身不包含数据转换程序。 |
| 找不到旧 SQLite 主库 | 用步骤 1 的 `docker inspect` 查原 `/config` 路径，自定义主库名补 `--db`。 |
| `connection refused` / 连接超时 | 检查步骤 4 的地址、映射端口和网络；PG 服务须已启动。 |
| 无法解析 `postgres` | `postgres` 是 Docker 网络服务名。迁移容器加入同一网络，或改用宿主机地址与映射端口。 |
| 密码认证失败 | 核对用户、原始密码及连接串里的百分号编码，确认连到的是预期 PG 服务。 |
| `permission denied` / 无法建 schema 或表 | 让迁移账号成为目标库所有者，或由数据库管理员补足权限。 |
| SQLite 忙、无法取得源库锁 | 停止所有使用原配置目录的写入进程，再迁移。不要删除锁、WAL 或 SHM 来绕过占用。 |
| 重复主键或目标已有数据 | 使用新的空目标库，不要向已使用的业务库重复导入。 |
| 字段转换或业务表导入报错 | 保存错误所在表及错误描述，隐藏连接凭据；修正具体问题后使用空目标库重试。 |
| 音乐迁移中断或总时限到达 | 不启动新库实例。排除错误，必要时加长 `--timeout`，再用新的空目标库重试。 |
| 迁移后账号、图片或歌词不可用 | 确认仍绑定原 `/config` 及密钥，并连接到正确目标库。 |

迁移失败可能已经在目标 PG 中留下部分已提交的数据，尤其是分阶段导入的音乐数据。不要把重复执行当作断点续传；保留旧源库，换空目标库重试即可。脚本会保留迁移程序的非零退出码，不会在失败后自动启动应用。

## 需要回退 SQLite 时

先停止 PostgreSQL 模式下的 DIAN115；移除 `DIAN115_DB_DRIVER=pgsql` 和 `DIAN115_PG_DSN`，保持原 `/config` 和旧镜像兼容性，再启动原实例。默认后端为 SQLite，优先使用迁移前备份恢复需要恢复的文件。

回退只能恢复到原 SQLite 或备份的状态；迁移后新增在 PG 中的数据不会自动合并回 SQLite。确认新库使用正常前保留旧目录和备份，不要在两个后端同时运行写入实例。

## 验证这个用户脚本

维护者可以在装有 Node.js 的机器运行：

```sh
node --test tools/database-migration/verify-migration-script.test.mjs
```

这些测试使用假的 Docker 命令核对参数、凭据传递与错误退出，不创建容器。迁移 SQL、字段映射和音乐转换由对应发布镜像提供，不包含在此公共目录。
