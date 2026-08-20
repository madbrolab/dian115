# 插件打包、完整性与签名

DIAN115 插件包使用 `.d115p` 后缀，文件内容是受严格约束的 ZIP。宿主先验证包摘要、ZIP 路径、`integrity.json`、Ed25519 签名、manifest 与市场声明，再安装运行时。以下规则是协议的一部分，不是建议。

## 1. 发布密钥

每个发布者长期保管一个 Ed25519 密钥。私钥输入是 32 字节 seed，公钥是 32 字节；两者在 JSON 中均使用不带 `=` 的 base64url。发布者 ID 的计算方式固定为：

```text
key_id = "ed25519:" + base64url_no_pad(sha256(raw_32_byte_public_key))
```

第一次发布前把计算出的 `key_id` 同时写入 `manifest.json` 的 `publisher.key_id`。同一个发布者后续版本保持密钥稳定；不要为每次构建生成新密钥。

在 Linux 中生成 seed，输出目录必须位于版本库之外：

```bash
install -d -m 700 "$HOME/.config/dian115-plugin-keys"
docker run --rm --user "$(id -u):$(id -g)" \
  -v "$HOME/.config/dian115-plugin-keys:/keys" \
  python:3.13-slim \
  python -c 'import secrets,pathlib; p=pathlib.Path("/keys/publisher.seed"); f=p.open("xb"); f.write(secrets.token_bytes(32)); f.close(); p.chmod(0o600)'
chmod 600 "$HOME/.config/dian115-plugin-keys/publisher.seed"
```

私钥或 seed 绝不能进入插件包、市场仓库、源码仓库、镜像、日志或 CI 构建产物。CI 应通过只读 secret 文件挂载。备份 seed 时使用离线加密存储。

密钥轮换会改变发布者身份。需要轮换时，用旧密钥发布最后一个版本并在项目主页公告新 `key_id`；新密钥签出的包必须由用户重新确认。旧私钥泄露时停止发布，撤下受影响条目并公告，不要静默替换市场中的同版本包。

## 2. 待打包目录

只把运行必需文件放进独立的 staging 目录：

```text
package/
  manifest.json
  ui.schema.json              # manifest 声明 UI 时必需
  assets/icon.svg             # 可选
  runtime/plugin.wasm         # wasm
  runtime/plugin              # process 二选一
  integrity.json              # 构建脚本生成
  signature.json              # 构建脚本生成
dist/
```

不要把源码、构建缓存、测试数据、私钥、Dockerfile 或开发依赖复制到 `package/`。包的硬限制为：压缩包 32 MiB、单文件 32 MiB、解压总量 128 MiB、ZIP 成员最多 1024 个；`integrity.json` 最多登记 1022 个文件。

## 3. integrity 规则

`integrity.json` 覆盖 ZIP 中除 `integrity.json` 和 `signature.json` 以外的每个文件，不能漏项、加项或自引用。每项记录原始文件字节的长度和小写 SHA-256：

```json
{
  "$schema": "https://raw.githubusercontent.com/madbrolab/dian115/main/docs/plugin-platform/integrity.schema.json",
  "schema_version": 1,
  "algorithm": "sha256",
  "files": [
    {
      "path": "manifest.json",
      "size": 1234,
      "sha256": "64位小写十六进制"
    }
  ]
}
```

`files` 必须按路径的 UTF-8 原始字节严格升序排列。摘要针对实际打包字节；换行从 LF 变成 CRLF、JSON 重新格式化或 SVG 被优化都会改变长度和摘要，因此生成 integrity 后不得再改包内文件。

## 4. 签名消息

`manifest.json` 和 `integrity.json` 分别按 RFC 8785 JSON Canonicalization Scheme（JCS）规范化。签名消息是以下字节的直接拼接，其中 `0x00` 是一个 NUL 字节：

```text
UTF8("DIAN115-PLUGIN-PACKAGE-V1")
|| 0x00
|| JCS(manifest.json)
|| 0x00
|| JCS(integrity.json)
```

使用 Ed25519 对整段消息签名。`signature.json` 格式如下：

```json
{
  "$schema": "https://raw.githubusercontent.com/madbrolab/dian115/main/docs/plugin-platform/signature.schema.json",
  "schema_version": 1,
  "algorithm": "Ed25519",
  "canonicalization": "RFC8785-JCS",
  "domain": "DIAN115-PLUGIN-PACKAGE-V1",
  "key_id": "ed25519:发布者KeyID",
  "public_key": "32字节公钥的无填充base64url",
  "signature": "64字节签名的无填充base64url"
}
```

不要用“按键名字母排序后 `json.dumps`”代替 JCS；尤其是 Unicode 键顺序、数字和转义规则可能不同。使用明确实现 RFC 8785 的库。

## 5. ZIP 规则

ZIP 只能包含普通文件，并满足以下条件：

- 使用 UTF-8、NFC 规范化的相对 POSIX 路径；分隔符只能是 `/`。
- 禁止空路径、绝对路径、反斜杠、冒号、NUL、`.`、`..`、重复斜杠、尾随 `/`、尾随空格或点。
- 禁止显式目录成员、符号链接及其他特殊文件。
- 路径不能发生大小写折叠或 NFC 冲突，也不能使用 `CON`、`NUL`、`COM1` 等保留设备名。
- `integrity.json` 必须精确覆盖所有其他成员。
- process 入口和确实需要执行的包内子程序使用 Unix `0755`；它们必须是目标 `linux/amd64` 或 `linux/arm64` 的自包含静态链接文件。其余普通文件使用 `0644`，插件私有 data 树不可执行。

不要直接运行 `zip -r`：它常加入目录成员，可能保留主机特有权限或把不应发布的文件一起打包。

## 6. 可复制的 Linux 构建脚本

下面的脚本只读取 `package/`，把私钥作为单独参数读取，并显式创建每个 ZIP 成员。保存为开发仓库中的 `tools/package_plugin.py`；它不是插件包内容。需要执行权限的附加子程序通过 `D115_EXECUTABLES` 以英文逗号分隔声明。

```python
from __future__ import annotations

import base64, hashlib, json, os, pathlib, sys, unicodedata, zipfile
import rfc8785
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

root = pathlib.Path(sys.argv[1]).resolve()
seed_path = pathlib.Path(sys.argv[2]).resolve()
output_dir = pathlib.Path(sys.argv[3]).resolve()

def b64url(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")

def valid_path(path: str) -> None:
    if (not path or path != unicodedata.normalize("NFC", path)
            or "\\" in path or ":" in path or "\0" in path
            or path.startswith("/") or path.endswith("/")):
        raise ValueError(f"unsafe package path: {path!r}")
    parts = path.split("/")
    reserved = {"CON", "PRN", "AUX", "NUL"} | {
        f"{p}{n}" for p in ("COM", "LPT") for n in range(1, 10)
    }
    for part in parts:
        if not part or part in (".", "..") or part.endswith((".", " ")):
            raise ValueError(f"unsafe package path: {path!r}")
        if part.split(".", 1)[0].upper() in reserved:
            raise ValueError(f"reserved package path: {path!r}")

seed = seed_path.read_bytes()
if len(seed) != 32:
    raise ValueError("publisher seed must contain exactly 32 bytes")
private_key = Ed25519PrivateKey.from_private_bytes(seed)
public_key = private_key.public_key().public_bytes(
    serialization.Encoding.Raw, serialization.PublicFormat.Raw
)
key_id = "ed25519:" + b64url(hashlib.sha256(public_key).digest())

for generated in (root / "integrity.json", root / "signature.json"):
    generated.unlink(missing_ok=True)

files: dict[str, bytes] = {}
folded: dict[str, str] = {}
for item in root.rglob("*"):
    if item.is_symlink() or (item.exists() and not item.is_file()):
        if item.is_symlink():
            raise ValueError(f"symlink is forbidden: {item}")
        continue
    path = item.relative_to(root).as_posix()
    valid_path(path)
    collision_key = unicodedata.normalize("NFC", path).casefold()
    if collision_key in folded:
        raise ValueError(f"path collision: {folded[collision_key]!r}, {path!r}")
    folded[collision_key] = path
    payload = item.read_bytes()
    if len(payload) > 32 * 1024 * 1024:
        raise ValueError(f"file too large: {path}")
    files[path] = payload

if "manifest.json" not in files:
    raise ValueError("manifest.json is required")
manifest = json.loads(files["manifest.json"])
if manifest.get("publisher", {}).get("key_id") != key_id:
    raise ValueError(f"manifest publisher.key_id must be {key_id}")

ordered = sorted(files, key=lambda p: p.encode("utf-8"))
integrity = {
    "$schema": "https://raw.githubusercontent.com/madbrolab/dian115/main/docs/plugin-platform/integrity.schema.json",
    "schema_version": 1,
    "algorithm": "sha256",
    "files": [{
        "path": path,
        "size": len(files[path]),
        "sha256": hashlib.sha256(files[path]).hexdigest(),
    } for path in ordered],
}
integrity_bytes = (json.dumps(
    integrity, ensure_ascii=False, indent=2, separators=(",", ": ")
) + "\n").encode("utf-8")
(root / "integrity.json").write_bytes(integrity_bytes)

message = (b"DIAN115-PLUGIN-PACKAGE-V1\0"
           + rfc8785.dumps(manifest) + b"\0" + rfc8785.dumps(integrity))
signature = {
    "$schema": "https://raw.githubusercontent.com/madbrolab/dian115/main/docs/plugin-platform/signature.schema.json",
    "schema_version": 1,
    "algorithm": "Ed25519",
    "canonicalization": "RFC8785-JCS",
    "domain": "DIAN115-PLUGIN-PACKAGE-V1",
    "key_id": key_id,
    "public_key": b64url(public_key),
    "signature": b64url(private_key.sign(message)),
}
signature_bytes = (json.dumps(
    signature, ensure_ascii=False, indent=2, separators=(",", ": ")
) + "\n").encode("utf-8")
(root / "signature.json").write_bytes(signature_bytes)

all_files = dict(files)
all_files["integrity.json"] = integrity_bytes
all_files["signature.json"] = signature_bytes
if len(all_files) > 1024 or sum(map(len, all_files.values())) > 128 * 1024 * 1024:
    raise ValueError("package file count or expanded size exceeds the limit")

runtime = manifest.get("runtime", {})
executables = {p for p in os.getenv("D115_EXECUTABLES", "").split(",") if p}
if runtime.get("kind") == "process":
    executables.add(runtime["entry"])
for path in executables:
    valid_path(path)
    if path not in all_files:
        raise ValueError(f"executable is missing: {path}")

output_dir.mkdir(parents=True, exist_ok=True)
output = output_dir / f'{manifest["id"]}-{manifest["version"]}.d115p'
with zipfile.ZipFile(output, "w", zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
    for path in sorted(all_files, key=lambda p: p.encode("utf-8")):
        info = zipfile.ZipInfo(path, (1980, 1, 1, 0, 0, 0))
        info.create_system = 3
        info.compress_type = zipfile.ZIP_DEFLATED
        info.external_attr = ((0o100755 if path in executables else 0o100644) << 16)
        archive.writestr(info, all_files[path], compresslevel=9)

if output.stat().st_size > 32 * 1024 * 1024:
    output.unlink()
    raise ValueError("compressed package exceeds 32 MiB")
print(json.dumps({"package": str(output), "key_id": key_id,
                  "sha256": hashlib.sha256(output.read_bytes()).hexdigest()},
                 ensure_ascii=False))
```

只在 Docker/Linux 环境运行：

```bash
docker run --rm --user "$(id -u):$(id -g)" \
  -e HOME=/tmp/dian115-plugin-home \
  -e D115_EXECUTABLES="runtime/plugin,runtime/helper" \
  -v "$PWD:/work" -w /work \
  -v "$HOME/.config/dian115-plugin-keys/publisher.seed:/run/secrets/publisher.seed:ro" \
  python:3.13-slim \
  sh -c 'mkdir -p "$HOME" && python -m pip install --user --no-cache-dir cryptography rfc8785 && python tools/package_plugin.py package /run/secrets/publisher.seed dist'
```

WASM 插件不需要 `D115_EXECUTABLES`，可删除这一行。命令最后输出的整个 `.d115p` SHA-256 必须原样写进市场条目的 `sha256`。

## 7. 发布前验证

必须在一个不含私钥的全新容器中做第二次验证：

1. ZIP 成员数量、路径、类型和 Unix mode 合法，成员集合与 integrity 完全一致。
2. 对每个成员重新计算字节长度和 SHA-256。
3. 用 `signature.json.public_key` 重新计算 `key_id`，确认同时等于 signature 与 manifest 中的值。
4. 重新 JCS 规范化 manifest 和 integrity，验证 Ed25519 签名。
5. 使用仓库中的 [manifest schema](manifest.schema.json)、[UI schema](ui-schema-v1.schema.json)、[integrity schema](integrity.schema.json)、[signature schema](signature.schema.json) 和 [市场 schema](../../plugin-market/index.schema.json) 校验 JSON。
6. 重新计算包 SHA-256，确认等于市场 index；确认市场中的 ID、版本、运行时和权限与 manifest 完全一致。

可把下面的独立验证器保存为 `tools/verify_plugin.py`。它不读取私钥，只使用包内公钥验证现有签名：

```python
import base64, hashlib, json, pathlib, sys, unicodedata, zipfile
import rfc8785
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

package = pathlib.Path(sys.argv[1])
raw_package = package.read_bytes()
if not raw_package or len(raw_package) > 32 * 1024 * 1024:
    raise ValueError("invalid compressed package size")

with zipfile.ZipFile(package) as archive:
    infos = archive.infolist()
    if len(infos) > 1024:
        raise ValueError("too many ZIP members")
    names, folded, files = [], {}, {}
    for info in infos:
        name = info.filename
        parts = name.split("/")
        if (not name or info.is_dir() or name.startswith("/") or name.endswith("/")
                or "\\" in name or ":" in name or "\0" in name
                or name != unicodedata.normalize("NFC", name)
                or any(not p or p in (".", "..") or p.endswith((".", " ")) for p in parts)):
            raise ValueError(f"unsafe ZIP member: {name!r}")
        collision = unicodedata.normalize("NFC", name).casefold()
        if name in names or collision in folded:
            raise ValueError(f"duplicate/colliding ZIP member: {name!r}")
        names.append(name); folded[collision] = name
        mode = info.external_attr >> 16
        if mode and (mode & 0o170000) != 0o100000:
            raise ValueError(f"non-regular ZIP member: {name!r}")
        if info.file_size > 32 * 1024 * 1024:
            raise ValueError(f"oversized ZIP member: {name!r}")
        files[name] = archive.read(info)

if sum(map(len, files.values())) > 128 * 1024 * 1024:
    raise ValueError("expanded package exceeds 128 MiB")
for required in ("manifest.json", "integrity.json", "signature.json"):
    if required not in files:
        raise ValueError(f"missing {required}")

manifest = json.loads(files["manifest.json"])
integrity = json.loads(files["integrity.json"])
signature = json.loads(files["signature.json"])
items = integrity["files"]
paths = [item["path"] for item in items]
if paths != sorted(paths, key=lambda p: p.encode("utf-8")) or len(paths) != len(set(paths)):
    raise ValueError("integrity paths are not unique UTF-8-byte sorted values")
if set(paths) != set(files) - {"integrity.json", "signature.json"}:
    raise ValueError("integrity and ZIP member sets differ")
for item in items:
    payload = files[item["path"]]
    if item["size"] != len(payload) or item["sha256"] != hashlib.sha256(payload).hexdigest():
        raise ValueError(f'integrity mismatch: {item["path"]}')

decode = lambda value: base64.urlsafe_b64decode(value + "=" * (-len(value) % 4))
public_key = decode(signature["public_key"])
key_id = "ed25519:" + base64.urlsafe_b64encode(
    hashlib.sha256(public_key).digest()).rstrip(b"=").decode("ascii")
if key_id != signature["key_id"] or key_id != manifest["publisher"]["key_id"]:
    raise ValueError("publisher key_id mismatch")
message = (b"DIAN115-PLUGIN-PACKAGE-V1\0" + rfc8785.dumps(manifest)
           + b"\0" + rfc8785.dumps(integrity))
Ed25519PublicKey.from_public_bytes(public_key).verify(
    decode(signature["signature"]), message)

runtime = manifest["runtime"]
entry_mode = next(i.external_attr >> 16 for i in infos if i.filename == runtime["entry"])
if runtime["kind"] == "process" and entry_mode & 0o111 != 0o111:
    raise ValueError("process entry is not executable")
print(json.dumps({"valid": True, "id": manifest["id"], "version": manifest["version"],
                  "sha256": hashlib.sha256(raw_package).hexdigest()}, ensure_ascii=False))
```

在全新 Linux 容器执行：

```bash
docker run --rm -v "$PWD:/work:ro" -w /work python:3.13-slim \
  sh -lc 'python -m pip install --no-cache-dir cryptography rfc8785 && python tools/verify_plugin.py dist/example-1.0.0.d115p'
```

staging JSON 和市场 index 另行用仓库 Schema 检查；示例使用 `check-jsonschema`，不要只依赖编辑器提示：

```bash
docker run --rm -v "$PWD:/work:ro" -w /work python:3.13-slim sh -lc '
  python -m pip install --no-cache-dir check-jsonschema &&
  check-jsonschema --schemafile docs/plugin-platform/manifest.schema.json package/manifest.json &&
  check-jsonschema --schemafile docs/plugin-platform/ui-schema-v1.schema.json package/ui.schema.json &&
  check-jsonschema --schemafile docs/plugin-platform/integrity.schema.json package/integrity.json &&
  check-jsonschema --schemafile docs/plugin-platform/signature.schema.json package/signature.json &&
  check-jsonschema --schemafile plugin-market/index.schema.json market/index.json
'
```

发布后不要覆盖同一版本的包或复用同一个 URL。任何字节变化都提高 SemVer、使用新文件名、更新市场 SHA-256，再刷新对应仓库。
