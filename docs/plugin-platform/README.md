# DIAN115 Plugin API v2

This directory is the complete public contract for third-party plugins. It is intentionally source-free: the main application's implementation is private and is never required for plugin development. The permanent publication boundary is defined in [publication-policy.md](publication-policy.md).
## Supported plugin shape

Every plugin is one signed `.d115p` ZIP containing both parts below:

- a statically linked Linux `process` runtime supervised by DIAN115;
- a signed Vue 3 Module Federation page using the host-provided Vue 3, Naive UI, and `@lucide/vue` packages.

The UI is mandatory. Packages without `ui.mode=federation`, a signed Federation entry, and a valid process runtime are rejected. The only runtime is the supervised native process; there is no remote runtime, extra plugin container, alternate UI format, or UI fallback protocol.

The process is started directly by the main service inside the current Docker container. It cannot open network sockets or inspect paths outside its private root. Each installation owns `/config/package/<plugin-id>/`: its `package/` release directory, `data/` persistent directory and `tmp/` temporary directory are visible as `/package`, `/data` and `/tmp` after the helper enters the private root. Other plugins, `/config` itself, Linux system directories and media mounts are not present in that root. Host files, watches, HTTP requests and DIAN115 business operations continue through `host.call`. HTTP targets may be internet, LAN, host, container, loopback, or other locally reachable services.

## Authoritative files

Read these files in order:

1. [Developer guide](developer-guide.md): end-to-end workflow and capability overview.
2. [Package format v1](package-format-v1.md): Manifest, ZIP, integrity, signature, market index, installation and update rules.
3. [Process runtime v1](process-runtime-v1.md): framed JSON-RPC, lifecycle, invocation envelopes, results, Telegram and logging.
4. [Host Call v2](host-call-v2.md): local Host APIs, external HTTP/HTTPS, local services, proxy precedence, credentials, limits and errors.
5. [Vue Federation UI v1](ui-federation-v1.md): build contract, component props, bridge API, trusted same-origin behavior and every stable theme variable.
6. [OpenAPI](openapi-v1.yaml): exact request and response schemas for every approved local Host API.
7. [Black-box conformance](conformance/README.md): runtime smoke testing and public-surface checks without main-project source.

Machine-readable schemas:

- [manifest.schema.json](manifest.schema.json)
- [integrity.schema.json](integrity.schema.json)
- [signature.schema.json](signature.schema.json)
- [market index schema](market-index.schema.json)

The complete sample is in [`examples/complete-plugin`](examples/complete-plugin/README.md). It contains a Go process runtime, a Vue page, a Manifest template, packaging/signing code, and a market entry template.

## Compatibility and source of truth

`compatibility.dian115` is a SemVer range selected by the plugin publisher. `compatibility.plugin_api` must target Plugin API v2. The host still checks the signed package, market disclosure, platform, ELF architecture, UI and permissions at installation time.

For local Host APIs, the runtime catalog returned by `GET /api/plugin-center/v1/host-apis` and the `x-dian115-host-apis.entries` section in `openapi-v1.yaml` are the public compatibility contract. A host release must keep those two public lists identical; plugin authors do not need access to the private implementation. The black-box conformance materials describe how to validate a plugin against this contract.

## Security summary

- Install only packages signed by a publisher you trust. A native process remains publisher code even inside the host sandbox.
- The mandatory Vue page is trusted same-origin publisher code. It is not placed in an iframe sandbox or an extra CSP sandbox and may use browser storage, images, popups and ordinary browser requests. Administrators must treat installing a plugin as trusting both its signed UI and runtime; backend authorization remains authoritative for Host APIs.
- The package limit is 32 MiB compressed, 128 MiB expanded, 1024 ZIP members, and 32 MiB per member.
- The Linux sandbox uses the capabilities already present in a standard Docker container for the pre-exec `chroot`, then clears all capabilities without changing UID or the container configuration. No Compose addition, mount, network, ptrace, BPF or host service is required. The normal mode is `private-root`; if a deployment deliberately removes the default `SYS_CHROOT` capability, the helper uses `host-api-only` instead and denies all plugin pathname file syscalls. If the mandatory seccomp or process setup cannot be applied, the plugin does not start.
- The host validates the signed static ELF before installing the filter. A plugin may start a package-local helper process when needed; every descendant inherits the same private root, seccomp/no-new-privileges policy and process-group lifecycle, so it can use only that plugin's files and cannot open a direct socket or affect unrelated processes.
- `DIAN115_PLUGIN_DATA=/data`, `DIAN115_PLUGIN_PACKAGE=/package/...` and `TMPDIR=/tmp` are paths inside the plugin's private root. Use them for plugin-owned resources and persistent files. Use the approved file/watch APIs for host data; a host path is never exposed as a plugin-owned path.
- Brokered network access supports `GET`, `HEAD`, `POST`, `PUT`, `PATCH`, and `DELETE` over HTTP and HTTPS. The host does not reject a target because it resolves to loopback, private, link-local, container, host or other non-public addresses.
- Host proxy-domain rules have higher priority than plugin routing preferences.
- Telegram registrations are runtime operations, not install-time declarations. Each plugin can register at most 3 commands and 3 keywords. Conflicts are rejected at registration and do not fail installation.
- Host message parsing always runs before plugin Telegram matching.
- File APIs validate the submitted path, normalized path, resolved symbolic-link target, and saved watch source. Linux system directories and `/config` remain protected.

## Local import

Administrators can import a plugin package directly from the Plugin Center's
"Repositories & development" tab. The flow is deliberately the same trust
boundary as a market install:

1. Select a `.d115p` file. The host stores it in a private, short-lived staging directory and returns a review token; the browser never receives a server filesystem path.
2. The host validates ZIP limits, `manifest.json`, `integrity.json`, Ed25519 signature, process runtime, static ELF, Federation UI, and declared permissions before showing the review dialog.
3. After the administrator accepts the displayed permissions and process risk, the token is submitted to install. The host re-checks the token, expiry, SHA-256, consent digest, and package before starting the normal asynchronous install operation.

The token expires after 15 minutes, is single-use, and is removed after install, cancellation, failure, or expiry. Local import does not create a market repository entry and does not bypass signature, integrity, UI, runtime, filesystem, network, Telegram, or permission checks. Installed records show `本地导入` as their source.

## Public-source boundary

The GitHub repository publishes plugin contracts and third-party examples only. Never publish the main project's `cmd/`, `internal/`, `frontend/src/`, build files, deployment files, generated release packages, or private signing keys. Run the public-surface check before every public commit; CI rejects violations. See [publication-policy.md](publication-policy.md).
