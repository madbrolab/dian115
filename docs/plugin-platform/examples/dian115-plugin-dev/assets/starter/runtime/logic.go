package main

import "example.com/dian115-plugin-sdk/pluginjson"

func dispatch(raw pluginjson.Raw) map[string]any {
	fail := func(code int, message string) map[string]any {
		return map[string]any{"error": map[string]any{"code": code, "message": message}}
	}
	if !pluginjson.Valid(raw) {
		return fail(-32602, "invalid JSON invocation")
	}
	params := pluginjson.Field(raw, "params")
	switch pluginjson.Text(pluginjson.Field(raw, "method")) {
	case "runtime.initialize":
		if pluginjson.Text(pluginjson.Field(params, "protocol")) != "dian115:wasm@1" {
			return fail(-32602, "unsupported runtime protocol")
		}
		return map[string]any{"result": map[string]any{"ready": true, "protocol": "dian115:wasm@1"}}
	case "runtime.shutdown":
		return map[string]any{"result": map[string]any{"stopping": true}}
	case "runtime.invoke":
		env := pluginjson.Field(params, "envelope")
		if pluginjson.Text(pluginjson.Field(env, "invocation_id")) == "" || pluginjson.Text(pluginjson.Field(env, "op")) != "state" {
			return fail(-32602, "only read-only state is implemented")
		}
		payload := pluginjson.Field(env, "payload")
		if pluginjson.Field(payload, "view") == nil {
			return fail(-32602, "state view is required")
		}
		const etag = `"state-v1"`
		if pluginjson.Text(pluginjson.Field(payload, "if_none_match")) == etag {
			return map[string]any{"result": map[string]any{"not_modified": true, "etag": etag}}
		}
		return map[string]any{"result": map[string]any{"state_version": "state-v1", "etag": etag, "state": map[string]any{"status": "ready", "message": "轻量运行时已就绪"}}}
	default:
		return fail(-32601, "method not found")
	}
}
