# DIAN115 plugin developer guide

This guide takes a plugin from source to an installable package. Normative details are linked at each step.

## 1. Architecture

A plugin has one supervised Linux process and one mandatory Vue page:

```text
Vue Federation page (opaque-origin iframe)
  -> getState / invokeAction
  -> DIAN115 runtime bridge
  -> runtime.invoke over framed JSON-RPC
  -> plugin process
  -> host.call
  -> approved DIAN115 handler or public HTTPS Broker
```

The page never receives the administrator Axios client, cookies, local storage, router, DOM, Bot Token, 115 credentials, TMDB key, proxy credentials, CD2 credentials, or direct filesystem access. Business work belongs in the process runtime. The page calls the runtime through the narrow bridge described in [Vue Federation UI v1](ui-federation-v1.md).

The process is started in the current DIAN115 container. It must not listen on a port, create another container, daemonize, or require a remote callback. Direct socket syscalls are blocked. The host exposes the package read-only, one private writable data directory, stdio JSON-RPC, and approved Host APIs.

## 2. Start from the complete sample

Copy [`examples/complete-plugin`](examples/complete-plugin/README.md), then change:

- the plugin ID, name, version, publisher and compatibility range in `manifest.template.json`;
- the Go runtime behavior in `runtime/main.go`;
- the Vue page in `src/AppPage.vue`;
- the exact local APIs in `permissions.apis`;
- optional per-origin proxy preferences in `permissions.network`;
- declared event topics and scheduled jobs.

Build the UI with the same framework packages as the host:

```text
vue
naive-ui
@lucide/vue
```

They must be Federation singletons with `generate: false`. Do not bundle a private copy. The package must expose the module named by `ui.federation.module`, normally `./AppPage`.

Build the runtime as a static ELF for the target host architecture:

```bash
CGO_ENABLED=0 GOOS=linux GOARCH=amd64 go build -trimpath -ldflags="-s -w" -o build/runtime/plugin ./runtime
```

Use `GOARCH=arm64` for an ARM64 DIAN115 image. A ZIP with an ELF `PT_INTERP` segment is rejected; copying shared libraries beside the entry does not make a dynamically linked entry valid.

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
    "dian115": ">=3.8.51 <4.0.0",
    "plugin_api": "^2.0"
  },
  "runtime": {
    "kind": "process",
    "entry": "runtime/plugin",
    "protocol": "dian115:process@1"
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
        "origin": "https://api.example.com",
        "methods": ["GET", "POST"],
        "proxy_mode": "system",
        "reason": "Call the publisher service"
      }
    ]
  },
  "ui": {
    "mode": "federation",
    "icon": "frontend/icon.svg",
    "federation": {
      "entry": "frontend/dist/assets/remoteEntry.js",
      "assets_root": "frontend/dist/assets",
      "module": "./AppPage"
    }
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

Only declare local APIs the process actually calls. Every `(method, path template)` must appear in [OpenAPI](openapi-v1.yaml). Paths are exact; declaring one parameter route does not authorize a static sibling. Write methods require an `Idempotency-Key` between 16 and 128 printable ASCII characters unless the endpoint's OpenAPI operation says it owns an equivalent idempotency mechanism.

`permissions.network` is not a website allowlist. A plugin can use the Broker for any public HTTPS origin. These declarations record a routing preference for a specific origin and method:

- `system`: use the host proxy-domain decision;
- `direct`: use a direct route only when no host proxy-domain rule matches;
- `required`: require a configured proxy even when no host rule matches.

The host rule always wins. An undeclared origin/method uses `system`.

See [Package format v1](package-format-v1.md) for every field and cross-file rule.

## 4. Implement the process protocol

The process reads and writes `Content-Length` framed JSON-RPC 2.0 on stdin/stdout. The channel is full duplex: while handling `runtime.invoke`, the process may send `host.call`, `host.log`, or a Telegram registration and wait for the response. Keep reading stdout responses concurrently or both sides can deadlock.

The host calls:

- `runtime.initialize` once after every process start;
- `runtime.invoke` with `op=state`, `action`, `job`, or `event`;
- `runtime.shutdown` before an intentional stop.

The process can call:

- `host.call` for approved local APIs or external public HTTPS;
- `host.log` for structured installation-scoped logs;
- `host.ui.invalidate` to request a state refresh;
- `host.telegram.register`, `host.telegram.list`, and `host.telegram.unregister`.

The precise frames, payloads, response status enums, ETag requirements, retries and error codes are in [Process runtime v1](process-runtime-v1.md). Do not return an arbitrary JSON object for `state`, `action`, or `job`; the host validates each result.

## 5. Use Host Call

Local request:

```json
{
  "method": "GET",
  "path": "/api/tmdb/search?query=Dune",
  "headers": {"accept": "application/json"},
  "body_base64": ""
}
```

External request:

```json
{
  "method": "POST",
  "path": "https://api.example.com/v1/items",
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

`body_base64` accepts padded or unpadded standard Base64 on requests. Responses use unpadded standard Base64. The process Host Call request and response are each limited to 256 KiB.

External access supports only `GET`, `HEAD`, `POST`, `PUT`, `PATCH`, and `DELETE`. `OPTIONS`, `CONNECT`, and `TRACE` are not part of the contract. TLS, DNS, redirects, SSRF checks and proxy selection are performed by the host. Details are in [Host Call v2](host-call-v2.md).

## 6. Telegram

Send an active notification through the approved local API `POST /api/notifications/plugin`. The host uses its Bot configuration and recipient policy; the plugin cannot select an arbitrary chat ID or obtain the Bot Token.

Register incoming routes at runtime, normally while handling `runtime.initialize`:

```json
{
  "jsonrpc": "2.0",
  "id": "p:telegram:1",
  "method": "host.telegram.register",
  "params": {
    "commands": [
      {"command": "media_helper", "description": "Open media helper"}
    ],
    "keywords": [
      {"keyword": "media helper", "match": "prefix"}
    ]
  }
}
```

Each installation may register at most 3 commands and 3 keywords. Registration atomically replaces the installation's previous set. Reserved host commands, conflicts with another plugin, or the global 64-plugin-command limit return JSON-RPC `-32003`; the previous registration remains active and installation is not affected.

Host parsing always runs first. Only a message the host did not handle and that matches a registered route is delivered as `event` topic `telegram.message`. Unmatched messages never reach plugins.

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

- `api` and `hostApi`: the same frozen bridge;
- `installationId`, `pluginId`;
- `runtime`, `runtimeState`;
- `navKey="main"`;
- `themeContract="dian115-theme-v1"`.

The bridge provides only `getState(view)`, `invokeAction(action, input)`, and `refresh()`. The component may emit `action`, `refresh`, or `close`. Use Naive UI for controls and `@lucide/vue` for icons. Style with the stable `--dian-*` variables so light/dark and configured host themes update without remounting.

The page runs in `sandbox="allow-scripts"` without `allow-same-origin`. It cannot call DIAN115 HTTP APIs directly. See [Vue Federation UI v1](ui-federation-v1.md) for the exact TypeScript contract and theme table.

## 9. Package, sign and publish

The package root must contain:

```text
manifest.json
frontend/icon.svg                 # optional icon, UI itself is mandatory
frontend/dist/assets/...          # mandatory signed Federation assets
runtime/plugin                    # mandatory executable static Linux ELF
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

## 10. Release checklist

- UI is present, exposes the declared module, uses host singletons, and contains no unsigned remote scripts.
- Every UI asset and runtime file is covered by `integrity.json`.
- Runtime entry is a static ELF for the target architecture and has executable ZIP mode bits.
- Runtime handles full-duplex JSON-RPC and every required response contract.
- Every local Host API is declared exactly and appears in OpenAPI.
- Write calls use stable idempotency keys.
- Network calls use public HTTPS and tolerate proxy use and redirect revalidation.
- Filesystem requests never depend on Linux system paths or `/config`.
- Telegram registration stays within 3 commands and 3 keywords and handles conflicts.
- The publisher key is stable across upgrades and the private key is not shipped.
- Market metadata exactly matches the signed package.
