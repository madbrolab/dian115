package hostapi

import (
	"context"
	"encoding/base64"
	"errors"
	"strings"
	"testing"

	"example.com/dian115-plugin-sdk/pluginjson"
)

func TestStorageHelperAndHTTPFailures(t *testing.T) {
	var request map[string]any
	client := Client{Call: func(_ context.Context, method string, params any) (pluginjson.Raw, error) {
		request = params.(map[string]any)
		raw, _ := pluginjson.Encode(map[string]any{"status": 200, "headers": map[string]any{"Etag": []string{`"pkv_2"`}}, "body_base64": base64.RawStdEncoding.EncodeToString([]byte(`{"data":{"key":"settings","value":{"saved":true},"revision":"pkv_2","updated_at":"2026-10-28T00:00:00Z"}}`))})
		return raw, nil
	}}
	value, etag, err := client.StoragePut(context.Background(), "settings", pluginjson.Raw(`{"saved":true}`), `"pkv_1"`, "save-settings-inv_12345")
	if err != nil || string(value) != `{"saved":true}` || etag != `"pkv_2"` || request["path"] != "/api/plugin-runtime/storage/settings" {
		t.Fatal(string(value), etag, err)
	}
	if request["headers"].(map[string]string)["if-match"] != `"pkv_1"` {
		t.Fatal("CAS header lost")
	}
	for _, key := range []string{"", "settings/rules", "a..b", "-start", "end-"} {
		if ValidStorageKey(key) {
			t.Fatal(key)
		}
	}
	raw, _ := pluginjson.Encode(map[string]any{"status": 412, "body_base64": base64.RawStdEncoding.EncodeToString([]byte(`{"code":"version_conflict","detail":"reload state","retryable":false}`))})
	var problem *Problem
	if err := CheckResponse(raw); !errors.As(err, &problem) || problem.Status != 412 || problem.Code != "version_conflict" || problem.Retryable {
		t.Fatal(err)
	}
}

func TestStorageRejectsMalformedSuccessAndKeepsNull(t *testing.T) {
	valid := `{"data":{"key":"settings","value":null,"revision":"pkv_2","updated_at":"2026-10-28T00:00:00Z"}}`
	body, tag := valid, `"pkv_2"`
	calls := 0
	client := Client{Call: func(context.Context, string, any) (pluginjson.Raw, error) {
		calls++
		return pluginjson.Encode(map[string]any{"status": 200, "headers": map[string]any{"ETag": []string{tag}}, "body_base64": base64.RawStdEncoding.EncodeToString([]byte(body))})
	}}
	value, etag, err := client.StorageGet(context.Background(), "settings")
	if err != nil || string(value) != "null" || etag != tag {
		t.Fatal("JSON null is a valid stored value", string(value), etag, err)
	}
	for _, bad := range []string{`{}`, `{"data":{}}`, strings.Replace(valid, "settings", "other", 1), strings.Replace(valid, `"value":null,`, "", 1), strings.Replace(valid, "pkv_2", "pkv_3", 1), strings.Replace(valid, `"updated_at":"2026-10-28T00:00:00Z"`, `"updated_at":null`, 1)} {
		body = bad
		if _, _, err := client.StorageGet(context.Background(), "settings"); err == nil {
			t.Fatal("invalid success accepted", bad)
		}
	}
	body = valid
	for _, bad := range []string{"", `"2"`, `pkv_2`, `W/"pkv_2"`, `"pkv_0"`, `"pkv_02"`} {
		tag = bad
		if _, _, err := client.StorageGet(context.Background(), "settings"); err == nil {
			t.Fatal("invalid response ETag accepted", bad)
		}
		before := calls
		if bad != "" {
			if _, _, err := client.StoragePut(context.Background(), "settings", pluginjson.Raw(`true`), bad, "storage-invalid-tag-12345"); err == nil || calls != before {
				t.Fatal("invalid input ETag reached host", bad, err)
			}
		}
	}
	body = `{"data":{}}`
	if err := client.StorageDelete(context.Background(), "settings", "storage-delete-123456"); err != nil {
		t.Fatal("empty delete acknowledgement rejected", err)
	}
}

func TestHostBodyEncodingAndDecodedLimit(t *testing.T) {
	for _, raw := range []pluginjson.Raw{pluginjson.Raw(`{}`), pluginjson.Raw(`{"body_base64":null}`), pluginjson.Raw(`{"body_base64":4}`)} {
		if _, err := Body(raw); err == nil {
			t.Fatal("missing or non-string body accepted", string(raw))
		}
	}
	for _, encoding := range []*base64.Encoding{base64.RawStdEncoding, base64.StdEncoding} {
		raw, _ := pluginjson.Encode(map[string]any{"body_base64": encoding.EncodeToString([]byte("x"))})
		if body, err := Body(raw); err != nil || string(body) != "x" {
			t.Fatal(string(body), err)
		}
	}
	raw, _ := pluginjson.Encode(map[string]any{"body_base64": base64.RawStdEncoding.EncodeToString(make([]byte, (8<<20)+1))})
	if _, err := Body(raw); err == nil {
		t.Fatal("decoded response exceeded 8 MiB")
	}
	var problem *Problem
	if err := CheckResponse(jobHostResponse(404, `{"error":"当前业务资源不存在"}`)); !errors.As(err, &problem) || problem.Detail != "当前业务资源不存在" {
		t.Fatal("plain Host API error lost its detail", err)
	}
}
