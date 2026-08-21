# DIAN115 Plugin API v2

This directory is the complete public contract for third-party plugins.
## Supported plugin shape

Every plugin is one signed `.d115p` ZIP containing both parts below:

- a statically linked Linux `process` runtime supervised by DIAN115;
- a signed Vue 3 Module Federation page using the host-provided Vue 3, Naive UI, and `@lucide/vue` packages.

The UI is mandatory. Packages without `ui.mode=federation`, a signed Federation entry, and a valid process runtime are rejected. There is no WASM runtime, remote runtime, extra plugin container, declarative UI, or UI fallback protocol.

The process cannot open network sockets or freely browse the container filesystem. It receives a read-only package directory and one writable private data directory. All HTTP/HTTPS requests and all DIAN115 business operations go through `host.call`. HTTP targets may be internet, LAN, host, container, loopback, or other locally reachable services. Linux system directories and `/config` are denied, except that the plugin can access only its own private data directory supplied in `DIAN115_PLUGIN_DATA`.

## Authoritative files

Read these files in order:

1. [Developer guide](developer-guide.md): end-to-end workflow and capability overview.
2. [Package format v1](package-format-v1.md): Manifest, ZIP, integrity, signature, market index, installation and update rules.
3. [Process runtime v1](process-runtime-v1.md): framed JSON-RPC, lifecycle, invocation envelopes, results, Telegram and logging.
4. [Host Call v2](host-call-v2.md): local Host APIs, external HTTP/HTTPS, local services, proxy precedence, credentials, limits and errors.
5. [Vue Federation UI v1](ui-federation-v1.md): build contract, component props, bridge API, sandbox and every stable theme variable.
6. [OpenAPI](openapi-v1.yaml): exact request and response schemas for every approved local Host API.

Machine-readable schemas:

- [manifest.schema.json](manifest.schema.json)
- [integrity.schema.json](integrity.schema.json)
- [signature.schema.json](signature.schema.json)
- [market index schema](../../plugin-market/index.schema.json)

The complete sample is in [`examples/complete-plugin`](examples/complete-plugin/README.md). It contains a Go process runtime, a Vue page, a Manifest template, packaging/signing code, and a market entry template.

## Compatibility and source of truth

`compatibility.dian115` is a SemVer range selected by the plugin publisher. `compatibility.plugin_api` must target Plugin API v2. The host still checks the signed package, market disclosure, platform, ELF architecture, UI and permissions at installation time.

For local Host APIs, the runtime catalog returned by `GET /api/plugin-center/v1/host-apis` and the `x-dian115-host-apis.entries` section in `openapi-v1.yaml` contain the same entries. A repository test compares the code catalog with this published list so a catalog change cannot silently leave the documentation behind.

## Security summary

- Install only packages signed by a publisher you trust. A native process remains publisher code even inside the host sandbox.
- The package limit is 32 MiB compressed, 128 MiB expanded, 1024 ZIP members, and 32 MiB per member.
- The Linux sandbox is fail closed. If Landlock/seccomp cannot be applied, the plugin does not start.
- Brokered network access supports `GET`, `HEAD`, `POST`, `PUT`, `PATCH`, and `DELETE` over HTTP and HTTPS. The host does not reject a target because it resolves to loopback, private, link-local, container, host or other non-public addresses.
- Host proxy-domain rules have higher priority than plugin routing preferences.
- Telegram registrations are runtime operations, not install-time declarations. Each plugin can register at most 3 commands and 3 keywords. Conflicts are rejected at registration and do not fail installation.
- Host message parsing always runs before plugin Telegram matching.
- File APIs validate the submitted path, normalized path, resolved symbolic-link target, and saved watch source. Linux system directories and `/config` remain protected.
