#!/bin/sh
# User-facing Docker wrapper. Data conversion is provided by the selected image.
set -eu

usage() {
  cat <<'HELP'
DIAN115 SQLite → PostgreSQL 迁移

用法：
  export DIAN115_PG_DSN='postgres://用户:密码@地址:5432/库名?sslmode=disable'
  sh migrate-sqlite-to-pgsql.sh --config /绝对路径/config [选项]

选项：
  --config 目录    原容器 /config 对应的完整宿主机目录，必填
  --image 镜像     包含 dian115-db 的 DIAN115 镜像
                   默认 DIAN115_IMAGE；未设置时为 madbrolab/dian115:latest
  --network 网络   迁移容器的 Docker 网络，默认 host（Linux）
  --db 文件名      配置目录内的主库文件名，默认 dian115.db
  --timeout 时长   本次迁移总时限，默认 2h，例如 6h
  --help, -h       显示说明

先停止旧 DIAN115 并备份整个配置目录；目标使用空的 PostgreSQL 数据库。
新装 PostgreSQL 不需要迁移。此脚本依赖镜像内 /usr/local/bin/dian115-db。
完成后使用原配置目录、DIAN115_DB_DRIVER=pgsql 和同一 PG 连接启动应用。
完整教程：https://github.com/madbrolab/dian115/tree/main/tools/database-migration
HELP
}
fail() { printf '%s\n' "$1" >&2; exit 2; }
config=''
image=${DIAN115_IMAGE:-madbrolab/dian115:latest}
network=host
database=dian115.db
timeout=2h
while [ "$#" -gt 0 ]; do
  case "$1" in
    --config|--image|--network|--db|--timeout)
      [ "$#" -ge 2 ] || fail '选项后缺少值；运行 --help 查看用法。'
      case "$1" in
        --config) config=$2 ;; --image) image=$2 ;;
        --network) network=$2 ;; --db) database=$2 ;; --timeout) timeout=$2 ;;
      esac
      shift 2 ;;
    --help|-h) usage; exit 0 ;;
    *) fail '无法识别选项；运行 --help 查看用法。' ;;
  esac
done
command -v docker >/dev/null 2>&1 || fail '找不到 docker，请在运行 DIAN115 的 Docker 宿主机执行。'
[ -d "$config" ] || fail '请通过 --config 指定原容器 /config 对应的宿主机目录。'
config=$(CDPATH='' cd -- "$config" && pwd -P)
case "$database" in ''|*/*|*\\*) fail '--db 只能填写配置目录内的主库文件名。' ;; esac
[ -f "$config/$database" ] || fail '找不到旧 SQLite 主库；请核对 --config 和 --db。'
[ -n "${DIAN115_PG_DSN:-}" ] || fail '请设置 DIAN115_PG_DSN，指向空的 PostgreSQL 目标库。'
case "$image" in ''|-*) fail '--image 必须是包含迁移工具的镜像名或摘要。' ;; esac
[ -n "$network" ] || fail '--network 不能为空。'
[ -n "$timeout" ] || fail '--timeout 不能为空。'
export DIAN115_PG_DSN
# Docker parses --mount as CSV. Quote the entire src field, including commas.
mount_source=$(printf '%s' "$config" | sed 's/"/""/g')
if docker run --rm --network "$network" --entrypoint /usr/local/bin/dian115-db \
  --mount "type=bind,\"src=$mount_source\",dst=/config" \
  -e DIAN115_DB_DRIVER=pgsql -e DIAN115_PG_DSN \
  "$image" migrate --db "/config/$database" --timeout "$timeout"; then
  printf '%s\n' '迁移完成。保留原配置目录，设置 DIAN115_DB_DRIVER=pgsql 与同一 PG 连接，再启动 DIAN115。'
else
  result=$?
  printf '%s\n' "迁移失败，退出码 ${result}。处理上方错误后，使用空目标库重试；保留旧配置目录和备份。" >&2
  exit "$result"
fi
