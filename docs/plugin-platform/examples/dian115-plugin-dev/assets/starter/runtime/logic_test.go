package main

import (
	"example.com/dian115-plugin-sdk/pluginjson"
	"testing"
)

func result(t *testing.T, raw string) pluginjson.Raw {
	t.Helper()
	data, err := pluginjson.Encode(dispatch(pluginjson.Raw(raw)))
	if err != nil {
		t.Fatal(err)
	}
	return data
}
func TestInitializationHasNoBusinessState(t *testing.T) {
	raw := result(t, `{"method":"runtime.initialize","params":{"protocol":"dian115:wasm@1"}}`)
	if string(pluginjson.Field(pluginjson.Field(raw, "result"), "ready")) != "true" {
		t.Fatal(string(raw))
	}
	bad := result(t, `{"method":"runtime.initialize","params":{"protocol":"wrong"}}`)
	if pluginjson.Field(bad, "error") == nil {
		t.Fatal("accepted unsupported protocol")
	}
}
func TestStateETagAndFreshInstance(t *testing.T) {
	raw := result(t, `{"method":"runtime.invoke","params":{"envelope":{"op":"state","invocation_id":"inv_state","payload":{"view":"main"}}}}`)
	value := pluginjson.Field(raw, "result")
	if pluginjson.Text(pluginjson.Field(value, "etag")) != `"state-v1"` || pluginjson.Text(pluginjson.Field(pluginjson.Field(value, "state"), "status")) != "ready" {
		t.Fatal(string(raw))
	}
	cached := result(t, `{"method":"runtime.invoke","params":{"envelope":{"op":"state","invocation_id":"inv_cached","payload":{"view":"main","if_none_match":"\"state-v1\""}}}}`)
	if string(pluginjson.Field(pluginjson.Field(cached, "result"), "not_modified")) != "true" {
		t.Fatal(string(cached))
	}
}
func TestRejectsUnimplementedWrites(t *testing.T) {
	for _, raw := range []string{`{invalid}`, `{"method":"unknown"}`, `{"method":"runtime.invoke","params":{"envelope":{"op":"action","invocation_id":"inv_write","payload":{"id":"send"}}}}`} {
		if pluginjson.Field(result(t, raw), "error") == nil {
			t.Fatal("accepted invalid or unimplemented operation", raw)
		}
	}
}
