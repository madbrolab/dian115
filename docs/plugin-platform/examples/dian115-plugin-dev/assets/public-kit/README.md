# DIAN115 Plugin API v2

This directory is the complete public contract for third-party plugins. It is intentionally source-free: the main application's implementation is private and is never required for plugin development. The permanent publication boundary is defined in [publication-policy.md](publication-policy.md).
开发者可安装 [第三方插件开发 Skill](skill-installation.md)，使用固定公开契约、最小模板和检查工具创建插件。

## Supported plugin shape

Every plugin is one signed `.d115p` ZIP containing both parts below:

- a signed, self-contained HTML page with its own renderer and a framework-independent SDK connection;
- a WASM reactor runtime (`dian115:wasm@1`) executed by the embedded container runtime.

The UI is mandatory. Packages without `ui.mode=page`, a signed HTML entry, and a valid WASM runtime are rejected. There is no native process runtime, remote runtime, extra plugin container, alternate UI format, or UI fallback protocol.

The plugin owns its HTML, CSS, framework providers, rendering and scrolling. The host displays the signed page in an isolated iframe and sends theme/state updates through the SDK; it does not resize to content or replace the page on browser error events. Package all required styles in the production entry and use relative asset URLs.

WASM is executed by the main service inside the current Docker container without inherited host descriptors, sockets, secrets, or preopened host paths. Host files, watches, HTTP requests and DIAN115 business operations continue through `host.call`. HTTP targets may be internet, LAN, host, container, loopback, or other locally reachable services.

## Authoritative files

Read these files in order:

1. [Developer guide](developer-guide.md): end-to-end workflow and capability overview.
2. [Package format v1](package-format-v1.md): Manifest, ZIP, integrity, signature, market index, installation and update rules.
3. [WASM runtime v1](wasm-runtime-v1.md): reactor ABI, broker imports, quotas, Telegram events and lifecycle.
4. [Host Call v2](host-call-v2.md): local Host APIs, external HTTP/HTTPS, local services, proxy precedence, credentials, limits and errors.
5. [数据存储与生命周期](storage-and-lifecycle.md)：存储位置、JSON 结构、CAS、升级与卸载清空。
6. [Independent HTML page v1](ui-page-v1.md): build contract, SDK connection, bridge API, opaque-origin isolation and managed storage and every stable theme variable.
7. [可恢复后台任务](job-recovery-v1.md)：检查点、只读上游核对与安全续跑。
8. [OpenAPI](openapi-v1.yaml): exact request and response schemas for every approved local Host API. [宿主接口速查表](host-api-quick-reference.md) 按分类列出一页可看的全部 178 条接口。
9. [Black-box conformance](conformance/README.md): manifest, market, WASM and public-surface checks without main-project source.
10. [UI 隔离、存储与后台调用](ui-isolation-v1.md)：浏览器边界、页面持久化、后台调用和接入要求。
11. [插件排错](troubleshooting.md)：首次打开、恢复、Host Call、资源与卸载错误的处理路径。

Machine-readable schemas:

- [manifest.schema.json](manifest.schema.json)
- [integrity.schema.json](integrity.schema.json)
- [signature.schema.json](signature.schema.json)
- [market index schema](market-index.schema.json)

The complete sample is in [`examples/complete-plugin`](examples/complete-plugin/README.md). It contains a Go WASM reactor runtime, a Vue page, a Manifest template, packaging/signing code, and a market entry template.

## Compatibility and source of truth

`compatibility.dian115` is a SemVer range selected by the plugin publisher. `compatibility.plugin_api` must target Plugin API v2. The host still checks the signed package, market disclosure, WASM module, UI and permissions at installation time.

For local Host APIs, the runtime catalog returned by `GET /api/plugin-center/v1/host-apis` and the `x-dian115-host-apis.entries` section in `openapi-v1.yaml` are the public compatibility contract. A host release must keep those two public lists identical; plugin authors do not need access to the private implementation. The black-box conformance materials describe how to validate a plugin against this contract.

## Security summary

- Install only packages signed by a publisher you trust. An installed plugin remains publisher code even inside the WASM sandbox.
- The mandatory Vue page runs in an opaque-origin sandbox. Native browser persistence and parent DOM access are blocked; use the managed `api.storage` bridge. Direct network calls use runtime actions and Host Call. See [UI isolation](ui-isolation-v1.md) for storage and uninstall semantics.
- The package limit is 32 MiB compressed, 128 MiB expanded, 1024 ZIP members, and 32 MiB per member.
- WASM plugins have no inherited file descriptors, sockets, credentials, environment secrets or preopened host directories. The embedded runtime enforces module memory and context time limits; network, storage, notifications, watches and DIAN115 operations are brokered Host API calls. Installing a plugin does not start any plugin executable or helper process.
- The plugin's package is mounted read-only at `/package` (`DIAN115_PLUGIN_PACKAGE=/package`). There is no writable mount: `DIAN115_PLUGIN_FILESYSTEM` is `broker-storage`, and every persistent value goes through Host Storage. Host paths are never exposed as plugin-owned paths.
- Brokered network access supports `GET`, `HEAD`, `POST`, `PUT`, `PATCH`, and `DELETE` over HTTP and HTTPS. The host does not reject a target because it resolves to loopback, private, link-local, container, host or other non-public addresses.
- Host proxy-domain rules have higher priority than plugin routing preferences.
- Backend plugins can read host-configured Emby instances, aggregate statistics, libraries and safe media metadata through six explicit read-only Host APIs. Emby addresses, API Keys, paths, media sources, users, sessions, devices, logs and mutations remain private.
- Telegram routes are install-time declarations in the manifest `telegram` block, not runtime registrations. Each plugin may declare at most 3 commands and 3 keywords. A conflict is reported at registration time and does not fail installation. Declaring the routes is what lets the host match a message and wake an unloaded plugin instead of requiring it to stay resident.
- Host message parsing always runs before plugin Telegram matching.
- File APIs validate the submitted path, normalized path, resolved symbolic-link target, and saved watch source. Linux system directories and `/config` remain protected.

## Local import

Administrators can import a plugin package directly from the Plugin Center's
"Repositories & development" tab. The flow is deliberately the same trust
boundary as a market install:

1. Select a `.d115p` file. The host stores it in a private, short-lived staging directory and returns a review token; the browser never receives a server filesystem path.
2. The host validates ZIP limits, `manifest.json`, `integrity.json`, Ed25519 signature, the declared WASM runtime, HTML UI, and permissions before showing the review dialog.
3. After the administrator accepts the displayed permissions, the token is submitted to install. The host re-checks the token, expiry, SHA-256, consent digest, and package before starting the normal asynchronous install operation.

The token expires after 15 minutes, is single-use, and is removed after install, cancellation, failure, or expiry. Local import does not create a market repository entry and does not bypass signature, integrity, UI, runtime, filesystem, network, Telegram, or permission checks. Installed records show `本地导入` as their source.

## Public-source boundary

The GitHub repository publishes plugin contracts and third-party examples only. Never publish the main project's `cmd/`, `internal/`, `frontend/src/`, build files, deployment files, generated release packages, or private signing keys. Run the public-surface check before every public commit; CI rejects violations. See [publication-policy.md](publication-policy.md).

- [轻量 HTTP 会话、CookieCloud 与 FlareSolverr](http-sessions-v1.md)：自动 Set-Cookie、按安装和账号隔离、加密持久化、共享 CookieCloud 按域名读写及按需渲染。
