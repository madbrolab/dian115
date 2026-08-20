# 第一个 DIAN115 插件：从空目录到安装成功

本教程用于验证完整开发链路：准备包结构、在 Docker/Linux 中构建运行时、生成完整性清单和签名、建立临时 HTTPS 市场、在插件中心安装并查看运行状态。DIAN115 不提供本地文件导入，开发版本也通过自定义 HTTPS 市场安装。

## 1. 准备环境

- 一台可以运行 Docker 的开发机。
- Git 和一个可通过 HTTPS 访问的仓库或对象存储；GitHub Raw 可以用于开发市场。
- 运行时所需的语言工具链放进 Docker 构建，不依赖 Windows 本机环境。
- 一个长期保管的 Ed25519 发布者私钥。私钥绝不能放进插件包、市场仓库或日志。

建议把开发源码与最终 staging 分开；`package/` 中只放会进入 `.d115p` 的文件：

```text
my-plugin/
  src/                        # 仅在开发者自己的仓库
  tools/
  package/
    manifest.json
    ui.schema.json
    README.md
    assets/icon.svg
    runtime/plugin.wasm       # wasm；process 时为 runtime/plugin
    integrity.json            # 构建时生成
    signature.json            # 构建时生成
  dist/my-plugin-1.0.0.d115p
```

`integrity.json` 和 `signature.json` 是构建产物，不要手工维护。包内只放运行所需文件；开发源码留在开发者自己的仓库，不提交到 DIAN115 官方市场。

## 2. 选择运行时

| 需求 | 运行时 |
| --- | --- |
| 页面 action、定时任务、事件处理，依赖少 | `wasm` |
| 常驻循环、包内原生库、需要启动包内子进程 | `process` |

WASM 使用 `dian115:plugin@1`，原生进程使用 `dian115:process@1`。两者都通过 Host Call 使用 115、文件/CD2、订阅、TMDB、通知及宿主管理的外部网络，不连接 DIAN115 HTTP 端口，也不读取账号凭据。process 只支持 `linux/amd64` 与 `linux/arm64`，由 Landlock ABI 3+ 与 seccomp fail-closed 隔离：只能读取/执行签名包、读写不可执行的私有 data，不能访问其他宿主路径或直接使用 socket；包内子进程继承相同限制。详见 [Process Runtime v1](process-runtime-v1.md)。

完整 ABI 和回调格式见 [运行时与回调契约](runtime-contract-v1.md)，process 的 stdio 与生命周期补充见 [Process Runtime v1](process-runtime-v1.md)。

## 3. 编写 manifest

最小 WASM manifest：

```json
{
  "$schema": "https://raw.githubusercontent.com/madbrolab/dian115/main/docs/plugin-platform/manifest.schema.json",
  "schema_version": 1,
  "id": "com.example.media-helper",
  "name": "媒体助手",
  "version": "1.0.0",
  "description": "演示 DIAN115 插件完整开发链路。",
  "default_locale": "zh-CN",
  "publisher": {
    "name": "Example",
    "key_id": "ed25519:替换为发布者KeyID"
  },
  "compatibility": {
    "dian115": ">=3.8.47 <4.0.0",
    "plugin_api": "^2.0"
  },
  "runtime": {
    "kind": "wasm",
    "entry": "runtime/plugin.wasm",
    "abi": "dian115:plugin@1",
    "memory_mb": 8,
    "timeout_ms": 30000,
    "background_timeout_ms": 300000,
    "max_concurrency": 1
  },
  "permissions": {
    "apis": [
      {
        "method": "GET",
        "path": "/api/tmdb/search",
        "reason": "按用户输入搜索媒体"
      }
    ],
    "network": []
  },
  "ui": {
    "schema": "ui.schema.json",
    "icon": "assets/icon.svg"
  },
  "events": [],
  "jobs": []
}
```

规则：

- `id` 发布后永久不变；每次改变包内容必须提高 SemVer，开发阶段也不要覆盖同一版本。
- `publisher.key_id` 必须由签名公钥计算，不能随版本变化。
- `permissions.apis` 使用登记目录中的准确 `METHOD + path` 模板；动态段在 manifest 中写 `:id`，实际调用时替换成真实值。
- `permissions.network` 每项显式填写 `origin`、`methods`、`proxy_mode` 和 `reason`。
- 目录监控的 `event_topic` 必须同时出现在 manifest 的 `events` 中。
- 定时任务必须写入 `jobs`。

外部来源声明示例；安装页会展示 origin、方法、代理模式、用途和当时解析到的 IP，重定向后的来源也必须提前获批：

```json
{
  "network": [
    {
      "origin": "https://api.example.com",
      "methods": ["GET", "POST"],
      "proxy_mode": "system",
      "reason": "读取用户指定网站的公开链接并提交处理结果"
    }
  ]
}
```

定时任务写入 `jobs`，例如：

```json
{
  "events": ["files.changed"],
  "jobs": [
    {
      "id": "refresh-catalog",
      "handler": "refresh_catalog",
      "default_schedule": "0 */6 * * *",
      "allow_overlap": false
    }
  ]
}
```

完整字段以 [manifest schema](manifest.schema.json) 为准。

## 4. 编写声明式 UI

UI 不包含 Vue、HTML 或 CSS。插件返回 state，`ui.schema.json` 只描述如何用宿主原生组件显示 state 和触发 action。

最小 UI：

```json
{
  "$schema": "https://raw.githubusercontent.com/madbrolab/dian115/main/docs/plugin-platform/ui-schema-v1.schema.json",
  "schema_version": 1,
  "navigation": {"title": "媒体助手", "icon": "search"},
  "appearance": {"theme": "system", "density": "comfortable", "surface": "soft"},
  "views": [
    {
      "id": "workspace",
      "title": "工作台",
      "layout": {"type": "stack", "columns": 1, "max_width": "narrow"},
      "sections": [
        {
          "type": "form",
          "id": "search_form",
          "title": "搜索媒体",
          "source": "state.form",
          "submit_action": "search",
          "submit_label": "开始搜索",
          "presentation": {"variant": "card", "tone": "primary", "icon": "search"},
          "fields": [
            {"key": "query", "label": "关键词", "control": "text", "required": true, "max_length": 100}
          ]
        }
      ]
    }
  ]
}
```

运行时的 state 至少包含：

```json
{"form":{"query":""}}
```

点击按钮后 action input 为：

```json
{"query":"用户输入的关键词"}
```

动态账号、目录 picker、条件显示、表格、进度、主题和移动端规则见 [声明式 UI 开发手册](ui-development-guide.md)。

## 5. 在 Docker/Linux 中构建

不要使用 Windows 本机产物冒充插件运行时。

Rust WASM 的典型命令：

```bash
docker run --rm \
  -v "$PWD:/work" -w /work \
  rust:1.85-bookworm \
  sh -lc 'rustup target add wasm32-unknown-unknown && cargo test && cargo build --release --target wasm32-unknown-unknown'
```

把生成的模块复制为 `runtime/plugin.wasm`。模块必须符合 `dian115:plugin@1` ABI，不得带 WASI、socket 或未批准导入。

process 插件必须在目标 Linux 架构中构建为自包含的静态链接 ELF；沙箱不会开放宿主动态链接器或共享库：

```bash
docker buildx build --platform linux/amd64 --output type=local,dest=dist .
file dist/runtime/plugin
```

分别为 `linux/amd64` 与 `linux/arm64` 发布独立包和版本，不要把错误架构交给安装器。

## 6. 生成完整性清单、签名和包

严格按照 [打包、完整性与签名](packaging-signing.md) 操作。完成后必须验证：

- Manifest、UI、integrity、signature 都通过 JSON Schema。
- integrity 覆盖 ZIP 中除自身和 signature 外的全部文件。
- Ed25519 签名、发布者 key ID 和市场 SHA-256 一致。
- ZIP 没有显式目录、符号链接、绝对路径、`..`、大小写冲突或未登记文件。
- process 入口和包内需要执行的子程序保留 `0755`，普通文件使用 `0644`。

最终得到：

```text
dist/media-helper-1.0.0.d115p
```

## 7. 建立开发市场

创建 `index.json`：

```json
{
  "$schema": "https://raw.githubusercontent.com/madbrolab/dian115/main/plugin-market/index.schema.json",
  "schema_version": 1,
  "repository": {
    "id": "example.dev-market",
    "name": "Example 开发市场",
    "homepage": "https://github.com/example/dian115-plugins"
  },
  "plugins": [
    {
      "id": "com.example.media-helper",
      "name": "媒体助手",
      "version": "1.0.0",
      "description": "开发版本",
      "author": "Example",
      "package_url": "packages/media-helper-1.0.0.d115p",
      "sha256": "替换为整个d115p文件的小写SHA-256",
      "runtime": {
        "kind": "wasm",
        "protocol": "dian115:plugin@1",
        "autostart": true,
        "trust_level": "sandboxed"
      },
      "permissions": {
        "apis": [
          {"method": "GET", "path": "/api/tmdb/search", "reason": "按用户输入搜索媒体"}
        ],
        "network": []
      },
      "tags": ["development"]
    }
  ]
}
```

市场条目的 ID、版本、运行时和权限必须与包内 manifest 完全一致。process 的 `protocol` 为 `dian115:process@1`，`trust_level` 为 `isolated-process`。

将 index、图标和 `.d115p` 发布到 HTTPS。开发时可以使用 GitHub Raw 的直接地址：

```text
https://raw.githubusercontent.com/<owner>/<repo>/<branch>/index.json
```

## 8. 安装和调试

1. 打开“插件中心 → 仓库与开发”。
2. 添加开发市场的 HTTPS `index.json` 地址。
3. 刷新该仓库，确认页面显示刚发布的版本和 SHA-256。
4. 查看安装页列出的运行时、Host API、外部来源和风险，再整体同意安装。
5. 在“外置插件”中打开插件工作区，执行 action。
6. 在插件独立日志中检查运行时、Host Call 和错误码。

如果更新后仍显示旧内容：提高插件版本、使用新包文件名、更新 index 的 SHA-256，然后刷新具体仓库。不要用同一版本覆盖旧包；GitHub Raw、CDN 和浏览器都可能缓存旧 URL。

完整排错见 [错误码与调试](errors-debugging.md)。仓库内还提供一个只含已签名二进制、没有源码的[可安装开发市场示例](examples/README.md)，用于先验证安装链路。

## 完成标准

第三方开发者应在不查看 DIAN115 主项目源码的情况下完成以下动作：

- Docker/Linux 构建运行时。
- Schema 校验、签名和打包。
- 通过自定义 HTTPS 市场安装。
- 在宿主原生 UI 中看到 state 并执行 action。
- 直接调用获批 Host API，正确处理错误和幂等重放。
- 从独立日志定位问题并发布新版本。
