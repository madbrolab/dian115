# DIAN115 plugin developer guide

This guide takes a plugin from source to an installable package. It is self-contained and does not require the main project's source code. Normative details are linked at each step; use the [black-box conformance tools](conformance/README.md) for local runtime validation.

## 1. Architecture

A plugin has one supervised WASM runtime and one mandatory HTML page:

```text
HTML page (opaque-origin sandbox)
  -> getState / invokeAction
  -> DIAN115 runtime bridge
  -> runtime.invoke envelope over the reactor ABI
  -> plugin WASM reactor
  -> host.call
  -> approved DIAN115 handler or host HTTP/HTTPS Broker
```

The signed page runs in an opaque-origin sandbox. It cannot access native browser storage, parent DOM or host credentials; use api.storage for persistent preferences and action → WASM → Host Call for business/network work. See [UI isolation and managed storage](ui-isolation-v1.md).

The WASM runtime is loaded directly by the main service in the current Docker container. It cannot listen on a port, create another plugin container, daemonize, require a remote callback, or start helper processes. The module receives no host filesystem mount beyond its own read-only package, no sockets, no credentials and no environment secrets. Host files, watches, network, Telegram and notifications remain mediated by approved Host APIs.

## 2. Start from the complete sample

Copy [`examples/complete-plugin`](examples/complete-plugin/README.md), then change:

- the plugin ID, name, version, publisher and compatibility range in `manifest.template.json`;
- the Go runtime behavior in `runtime/main.go`;
- the Vue page in `src/AppPage.vue`;
- the exact local APIs in `permissions.apis`;
- optional per-origin proxy preferences in `permissions.network`;
- declared event topics and scheduled jobs.

Build a self-contained HTML page. The example uses Vue, Naive UI and Lucide as ordinary bundled dependencies; other browser renderers can use the framework-independent SDK in `examples/sdk/page.ts`. Set Vite `base: './'`, call `connectPluginPage()` in the production entry, then mount your own application and providers. The host never mounts a component, shares a Vue instance or observes the document height. Read [the page contract](ui-page-v1.md).

The runtime must be a reactor module built with a size-optimising toolchain. The
Go standard compiler is not accepted: it links the complete Go runtime into the
module, which puts every module far above the host budget and makes each plugin
pay for a runtime it does not need. Use TinyGo for Go sources, or Rust, Zig or C:

```bash
tinygo build -target=wasi -buildmode=c-shared -opt=z -o build/runtime/plugin.wasm ./runtime
```

TinyGo needs `wasm-opt` from Binaryen on `PATH` (or the `WASMOPT` environment
variable pointing at it). Rust, Zig and C are equally accepted as long as the
module keeps the ABI in `wasm-runtime-v1.md`; a `no_std` / `no_alloc` build with
`-Oz` typically lands in the same size range.

The host refuses any module that carries the Go standard runtime, and names
that cause in the packaging error. A **2 MiB** ceiling backs it up for modules
that are not recognisably Go but are still far larger than a plugin should be.
Measure the built module with your selected toolchain; example sizes are not a stable API guarantee. WASM is architecture
independent; no target-architecture build is required.

The protocol also refuses modules that link `encoding/json`, again by name. The
host keeps a loaded plugin's compiled code, so one heavy package is paid for by
every plugin; the reference runtime includes
[`pluginjson`](examples/sdk/pluginjson/pluginjson.go), which
reads the fields a plugin needs without decoding whole documents. Use it (or its
equivalent in your language) instead of a general JSON library:

```go
method := pluginjson.Text(pluginjson.Field(request, "method"))
params := pluginjson.Field(request, "params")
```

Both rules are checked by `conformance/project-check.mjs`, so packaging fails
before installation does. They are developer-experience rules rather than a
security boundary: they keep the catalogue's footprint predictable, and an
author who genuinely needs the standard library should say so rather than work
around the check.

## 3. Define the signed Manifest

The UI and runtime are both required:

```json
{
  "schema_version": 1,
  "id": "example.media-helper",
  "name": "Media helper",
  "version": "1.0.0",
  "description": "Queries media and creates host tasks.",
  "default_locale": "en-US",
  "publisher": {
    "name": "Example publisher",
    "key_id": "ed25519:REPLACED_BY_PACKAGER"
  },
  "compatibility": {
    "dian115": ">=5.0.53 <6.0.0",
    "plugin_api": "^2.0"
  },
  "runtime": {
    "kind": "wasm",
    "entry": "runtime/plugin.wasm",
    "protocol": "dian115:wasm@1"
  },
  "permissions": {
    "apis": [
      {
        "method": "GET",
        "path": "/api/tmdb/search",
        "reason": "Search for media selected in the plugin page"
      }
    ],
    "network": [
      {
        "origin": "http://127.0.0.1:8080",
        "methods": ["GET", "POST"],
        "proxy_mode": "system",
        "reason": "Call a local companion service"
      }
    ]
  },
  "ui": {
    "mode": "page",
    "entry": "frontend/dist/index.html",
    "assets_root": "frontend/dist",
    "icon": "frontend/icon.svg"
  },
  "events": ["files.changed"],
  "jobs": [
    {
      "id": "refresh",
      "handler": "refresh",
      "default_schedule": "*/15 * * * *",
      "allow_overlap": false
    }
  ]
}
```

Only declare local APIs the runtime actually calls. Every `(method, path template)` must appear in [OpenAPI](openapi-v1.yaml). Paths are exact; declaring one parameter route does not authorize a static sibling. Write methods require an `Idempotency-Key` between 16 and 128 printable ASCII characters unless the endpoint's OpenAPI operation says it owns an equivalent idempotency mechanism.

Three optional declaration refinements:

- `"optional": true` on an API entry keeps installation working on hosts that do not offer it; the entry is recorded as `unavailable_apis` and calls fail with a clear error.
- `"host_access": "extended"` asks the administrator for broader access: any non-protected `/api` route (credentials, authentication, host security settings, plugin management and bot tokens stay host-only). Extended calls keep the same idempotency, audit, path-policy and size-limit rules, and JSON responses pass through generic credential redaction.
- `host.capabilities` (a `host.*` runtime method) returns the host version, the live API catalog, and this installation's granted and unavailable APIs, so plugins branch on capability instead of version sniffing.

`permissions.network` is not a website allowlist. A plugin can use the Broker for any HTTP/HTTPS origin, including localhost, loopback, container, host and LAN services. These declarations record a routing preference for a specific origin and method:

- `system`: use the host proxy-domain decision;
- `direct`: use a direct route only when no host proxy-domain rule matches;
- `required`: require a configured proxy even when no host rule matches.

The host rule always wins. An undeclared origin/method uses `system`.

See [Package format v1](package-format-v1.md) for every field and cross-file rule.

## 4. Implement the runtime protocol

WASM plugins use the reactor ABI and broker imports described in [WASM runtime v1](wasm-runtime-v1.md). The module exports `dian115_alloc` and `dian115_handle`, and may import `dian115.host_call` / `dian115.host_read` (or the `wasi_snapshot_preview1` functions the standalone Go runtime needs).

The host calls:

- `runtime.initialize` once after every module load;
- `runtime.invoke` with `op=state`, `action`, `job`, or `event`;
- `runtime.ping` is answered by the host as an availability acknowledgement; it does not enter the guest. Periodic maintenance uses module exit signals and invocation deadlines instead of ping RPCs;
- `runtime.shutdown` before an intentional unload.

The runtime can call:

- `host.call` for approved local APIs or external HTTP/HTTPS services;
- `host.log` for structured installation-scoped logs;
- `host.ui.invalidate` to request a state refresh;
- `host.telegram.list` to read the routes the manifest declared. Telegram routes
  are **not** registered at runtime any more: `host.telegram.register` and
  `host.telegram.unregister` are rejected, and a plugin that needs Telegram
  declares its routes in the manifest instead (see below).

Do not return an arbitrary JSON object for `state`, `action`, or `job`; the host validates each result. The exact frames, payloads, response status enums, ETag requirements, quotas, cancellation semantics and lifecycle are in [WASM runtime v1](wasm-runtime-v1.md).

### Plugin-owned files

The module's own package is mounted read-only at `/package` (`DIAN115_PLUGIN_PACKAGE=/package`), so bundled assets can be read with ordinary language I/O. There is no writable mount, no `/data` and no `/tmp`: `DIAN115_PLUGIN_FILESYSTEM` is `broker-storage`, and every persistent value must go through Host Storage.

```go
template, err := os.ReadFile("/package/assets/template.json")
if err != nil { /* report initialization failure */ }
// Persist state through Host Storage, not a local file.
```

`/package` is host-managed and read-only, and its contents change with every installed version. Host paths such as `/config`, `/etc`, `/proc` and media mounts never resolve for the module. To access an administrator-approved host path, call the corresponding file Host API; do not try to translate it into a local path.

## 5. Use Host Call

需要一页看全所有可调用接口时，查 [宿主接口速查表](host-api-quick-reference.md)；逐字段请求/响应格式以 [OpenAPI](openapi-v1.yaml) 为准。

Local request:

```json
{
  "method": "GET",
  "path": "/api/tmdb/search?q=Dune&page=1",
  "headers": {"accept": "application/json"},
  "body_base64": ""
}
```

External request:

```json
{
  "method": "POST",
  "path": "http://127.0.0.1:8080/v1/items",
  "headers": {"content-type": "application/json"},
  "body_base64": "eyJuYW1lIjoiZXhhbXBsZSJ9"
}
```

Result:

```json
{
  "status": 200,
  "headers": {"content-type": ["application/json"]},
  "body_base64": "eyJvayI6dHJ1ZX0"
}
```

`body_base64` accepts padded or unpadded standard Base64 on requests. Responses use unpadded standard Base64. A plugin invocation frame may be up to 16 MiB, and the decoded Host Call request or response body may be up to 8 MiB. Use endpoint pagination even though normal payloads are no longer constrained to 256 KiB.

External access supports only `GET`, `HEAD`, `POST`, `PUT`, `PATCH`, and `DELETE`. `OPTIONS`, `CONNECT`, and `TRACE` are not part of the contract. HTTP/HTTPS transport, DNS, redirects, target resolution and proxy selection are performed by the host. Details and HTTP security warnings are in [Host Call v2](host-call-v2.md).

### Read host-configured Emby data

The plugin runtime can read Emby without receiving the server URL or API Key. Declare only the operations it uses:

```json
{
  "apis": [
    {"method":"GET","path":"/api/plugin-host/emby/instances","reason":"Let the user select an Emby instance"},
    {"method":"GET","path":"/api/plugin-host/emby/libraries","reason":"List available media libraries"},
    {"method":"GET","path":"/api/plugin-host/emby/items","reason":"Search safe media metadata"},
    {"method":"GET","path":"/api/plugin-host/emby/items/:id","reason":"Read one selected media item"}
  ]
}
```

At runtime, call `GET /api/plugin-host/emby/instances`, let the user choose an `id`, and pass it as `proxy_id` to the other calls. When only one instance exists or the host has a valid default, `proxy_id` may be omitted. An instance with `id: 0` represents legacy single-instance configuration and must be used by omitting `proxy_id`, not by sending zero.

```json
{"method":"GET","path":"/api/plugin-host/emby/items?proxy_id=2&type=Movie&q=Dune&limit=20&offset=0"}
```

The item result includes IDs, titles, overview, year, rating, genres, provider IDs, series/episode numbers, dates and image-presence hints. It intentionally excludes the Emby URL, API Key, filesystem paths, media sources, user data, sessions, devices and logs. There are no Emby mutations in the plugin catalog. See the six `PluginEmby*` operations and exact schemas in [OpenAPI](openapi-v1.yaml), and use `offset`/`limit` pagination up to 50 items per call.

For episode subscriptions, also declare `GET /api/plugin-host/emby/episodes`. Confirm the TMDB TV identity and season (including season 0), then pass `proxy_id`, `tmdb_id`, `season` and `total_episodes` to preview coverage. A failed library read is an error, never proof that every episode is missing. Store the user's preferred instance in plugin storage; this does not change the host default. Create the intent with the same instance and season. For a fixed user target, send `episode_scope_mode: "fixed"` and `initial_needed_episodes: "1-3,5"`; the host subtracts live owned episodes before starting work. Do not send `library_snapshot_provided` to bypass the library scan. See the complete flow in [Host Call v2](host-call-v2.md#8-指定实例和集数的订阅流程).

## 6. Telegram

Send an active notification through the approved local API `POST /api/notifications/plugin`. The host uses its Bot configuration and recipient policy; the plugin cannot select an arbitrary chat ID or obtain the Bot Token.

Declare incoming routes in the manifest. The host registers them at install and
enable time, matches a message against them **without loading the plugin**, and
only then loads the plugin to handle it. That is what lets a Telegram plugin
stay unloaded while idle:

```json
{
  "telegram": {
    "commands": [
      {"command": "media_helper", "description": "Open media helper"}
    ],
    "keywords": [
      {"keyword": "media helper", "match": "prefix"}
    ]
  }
}
```

At most 3 commands and 3 keywords per plugin, and command names must not collide
with each other or with the host's reserved commands. Unloading the plugin no
longer drops the routes, so a plugin does not need to stay resident to keep
receiving messages.

Manifest route conflicts are reported by the host and never replace another installation's routes. Runtime registration and unregistration are rejected. Use `host.telegram.list` for the actual installed routes.

Host parsing always runs first. Only a message the host did not handle and that matches a registered route is delivered as `event` topic `telegram.message`. Unmatched messages never reach plugins.

Notification and reply buttons may carry `callback_data` instead of `url`. A tap is delivered back to the owning installation as `event` topic `telegram.callback` (declare it in `events`), and the plugin answers with a toast (`answer`/`alert`) plus an optional follow-up `reply`. See [host.call v2](host-call-v2.md) sections 11-12 for the callback contract and the file/transfer/job broker APIs.

WASM plugins that need an always-on main loop (timers, pollers, long-lived state) can declare `"resident": true` in `runtime`; the host keeps a second module instance running an endless `resident` invocation. See [WASM runtime v1](wasm-runtime-v1.md).

## 7. Directory watches

Declare the event topic in `events`, then approve the exact watch APIs your runtime uses. Creating a host path watch:

```json
{
  "source": {"kind": "host_path", "path": "/media/incoming"},
  "event_topic": "files.changed",
  "recursive": true,
  "interval_seconds": 30
}
```

Creating a 115 watch:

```json
{
  "source": {
    "kind": "115",
    "account": {"mode": "backup", "id": 12},
    "cid": "0"
  },
  "event_topic": "files.changed",
  "recursive": false,
  "interval_seconds": 60
}
```

The interval is 5 to 86400 seconds and each plugin can have at most 32 watches. A `backup_pool` selector is resolved once and persisted as one concrete account. The first scan creates a baseline and emits no mass-added event. Later deliveries preserve a stable event ID for retries. Full request/response schemas are in [OpenAPI](openapi-v1.yaml).

## 8. Build the UI

The remote Vue component receives:

- `api`: the frozen bridge defined by the public UI SDK;
- `installationId`, `pluginId`;
- `runtime`, `runtimeState`;
- `navKey="main"`;
- `themeContract="dian115-theme-v1"`.

The bridge provides only `getState(view)`, `invokeAction(action, input)`, and `refresh()`. The component may emit `action`, `refresh`, or `close`. Use Naive UI for controls and `@lucide/vue` for icons. Style with the stable `--dian-*` variables so light/dark and configured host themes update without remounting.

The page uses an opaque-origin sandbox and CSP. Signed page resources load through anonymous CORS; the plugin owns its providers; native browser storage and direct fetch/XHR/WebSocket are blocked. Use the managed storage and job bridge, handle errors, and keep messages JSON serializable. See [UI isolation](ui-isolation-v1.md).

The production HTML entry loads all required CSS and owns its root/body layout. Use fluid widths and local scrolling for tables; the host provides a stable iframe viewport rather than a content-height feedback loop. Ordinary browser errors do not cause the host to destroy the page. Report selected real failures explicitly with api.reportError.

## 9. Package, sign and publish

The package root must contain:

```text
manifest.json
frontend/icon.svg                 # optional icon, UI itself is mandatory
frontend/dist/index.html          # mandatory signed HTML entry
frontend/dist/assets/...          # signed page scripts/styles/fonts
runtime/plugin.wasm                # mandatory WASM reactor
integrity.json
signature.json
```

`integrity.json` lists every ZIP member except itself and `signature.json`, sorted by UTF-8 path bytes. Sign this exact byte sequence with Ed25519:

```text
UTF8("DIAN115-PLUGIN-PACKAGE-V1")
0x00
RFC8785-JCS(manifest.json)
0x00
RFC8785-JCS(integrity.json)
```

Publish the `.d115p` on HTTPS and add one entry to a market `index.json`. The market runtime and permissions disclosure must exactly match the signed Manifest; the market SHA-256 must match the package bytes. The complete sample packager generates the key ID, integrity file, signature file, ZIP permissions, package SHA-256, and market entry values.

## 10. Local import behavior

An administrator may also select the finished `.d115p` from the Plugin Center. This is an installation path, not a second package format: the host performs the same archive, manifest, integrity, signature, WASM runtime, HTML UI, and permission checks before presenting the consent dialog. The package must therefore be complete and signed even when it is not published in a market index.

The inspect endpoint is `POST /api/plugin-center/v1/imports/inspect` with a multipart field named `package`. A successful response contains `import_token`, `expires_at`, `file_name`, and the same plugin permission snapshot shown by a market install. The administrator then submits `POST /api/plugin-center/v1/imports/{token}/install` with `permissions_accepted: true` and the returned `consent_digest`. The host revalidates every value and queues the normal `plugin_install` operation.

Import tokens are private, single-use, and expire after 15 minutes. The host deletes the staged file after the operation is accepted or rejected. No local package is uploaded to a repository, and the installed source is recorded as `本地导入`.

## 11. Release checklist

- The HTML entry is present, connects using the public SDK, owns its providers, and loads packaged assets using relative URLs.
- UI bridge props, action inputs and results are JSON-serializable; no functions, DOM nodes, cyclic objects, `BigInt` or Vue proxy objects cross the bridge.
- Every UI asset and runtime file is covered by `integrity.json`.
- WASM runtime entry has the WASM magic, exports `dian115_alloc`/`dian115_handle` and exports memory.
- Runtime returns the required response envelope for every op and handles cancellation.
- Every local Host API is declared exactly and appears in OpenAPI.
- Write calls use stable idempotency keys.
- Network calls use host-brokered HTTP/HTTPS, support local services, and tolerate proxy use and redirect revalidation.
- Filesystem requests never depend on Linux system paths or `/config`.
- Telegram registration stays within 3 commands and 3 keywords and handles conflicts.
- The publisher key is stable across upgrades and the private key is not shipped.
- Market metadata exactly matches the signed package.
- `node docs/plugin-platform/conformance/verify-public-surface.mjs` passes before public publication; no main-project source is included.

## 12. Data and lifecycle

Start with `resident: false`. Opening the page or invoking work loads the service module; ordinary status metadata reads do not. The host can release idle modules, so guest globals are temporary. Use the shared [SDK](examples/sdk/README.md) for storage, ETag/CAS and HTTP errors. Read [storage and lifecycle](storage-and-lifecycle.md) for exact locations, limits and JSON structure.

Use bounded metadata pages and the usage endpoint instead of loading every stored value to build a list. Probe `features.storage_catalog_v1` first and declare the two GET permissions. Long Host Jobs and UI background runs appear in the main Task Queue with shared progress and cancellation; continue using the original `job_ref` for plugin-side queries. The Plugin Center's diagnostic panel links stable error codes to redacted administrator details. See [background jobs](ui-isolation-v1.md#可查询可取消的后台调用) and [troubleshooting](troubleshooting.md).

Uninstall clears private configuration, credentials, task records, logs, deliveries and files. Reinstallation starts empty. Disable, restart and upgrade preserve persistent configuration. A failed file cleanup leaves an inactive uninstall marker and a retryable error; it is not a successful uninstall.

Do not mistake the 8 MiB Host Call body limit for the 256 KiB business payload limit. Check target HTTP status even when the host import returned a normal result. A 412 conflict requires a fresh read and business merge, not an unconditional retry. Use stable invocation and idempotency IDs across uncertain results.


排查首次打开、恢复、存储或卸载问题时，按 [插件排错](troubleshooting.md) 根据错误码处理。

## 需要登录的第三方站点

先采用 [HTTP 会话](http-sessions-v1.md)：宿主自动接收 Set-Cookie、持久保存登录状态；多账号分配独立 cookie_session。CookieCloud 导入和写回通过公开接口完成，不复制全局 Key/密码到插件，不调用 PT 导入端点。只有站点确实需要渲染时才调用 render 复用外部 FlareSolverr；DIAN115 不内置 Chromium。初始化、state 与唤醒不自动登录、不写回共享 CookieCloud。


## 用户自定义地址和站点登录

第三方插件可以在页面提供账号、密码、明文 Cookie、自定义站点与验证码输入，不根据字段名拒绝业务数据。普通 HTTP 地址可以来自安装后配置。站点配置使用 `/api/plugin-runtime/http/sites`，CookieCloud 可访问 Manifest 声明或此接口保存的域名；不必为新增域名重新打包。表单登录使用 SDK PostForm，手填 Cookie 使用 SetCookieHeader，CookieCloud 是第三种可选来源。交互验证码由站点适配器按实际流程取得图片/令牌、收集答案和验证；平台不固定站点的字段或登录接口。完整约定与示例见 [HTTP 会话](http-sessions-v1.md) 和完整示例的 runtime/http_sessions.go、src/AppPage.vue。
