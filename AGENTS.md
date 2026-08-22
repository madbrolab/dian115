# Repository Publication Rules

This repository has a permanent public-source boundary:

- Never upload the DIAN115 main-project source code to GitHub, regardless of the task, debugging need, release process, or user request.
- Never publish `cmd/`, `internal/`, `frontend/src/`, main-project build/deployment files, `go.mod`, `go.sum`, production scripts, generated release artifacts, private keys, or Docker build context as plugin documentation or SDK material.
- Third-party plugin source is allowed only under `docs/plugin-platform/examples/`. Its generated `build/`, `releases/`, `.d115p`, and signing keys are never allowed.
- Public plugin materials must be limited to the protocol documents, schemas, OpenAPI contract, UI/theme contract, complete plugin examples, market metadata, and black-box conformance tools.

Before any public commit, run:

```bash
node docs/plugin-platform/conformance/verify-public-surface.mjs
```

This rule is repository policy, not a suggestion. When a task conflicts with it, keep the main source private and provide a source-free contract or black-box fixture instead.
