package hostapi

import (
	"context"
	"encoding/base64"
	"example.com/dian115-plugin-sdk/pluginjson"
	"net/url"
	"testing"
)

func TestStorageCatalogHelpersKeepScopeAndBounds(t *testing.T) {
	calls := 0
	client := Client{Call: func(_ context.Context, _ string, input any) (pluginjson.Raw, error) {
		calls++
		request := input.(map[string]any)
		path := request["path"].(string)
		body := `{"data":{"items":[{"key":"a_b","revision":"pkv_2","bytes":5,"updated_at":"2026-10-28T00:00:00Z"}],"next_cursor":"opaque.scope.cursor"}}`
		if path == "/api/plugin-runtime/storage-usage" {
			body = `{"data":{"keys":1,"used_bytes":5,"remaining_bytes":16777211,"limit_bytes":16777216,"value_limit_bytes":262144}}`
		} else {
			parsed, _ := url.Parse(path)
			if parsed.Path != "/api/plugin-runtime/storage" || parsed.Query().Get("prefix") != "a_" || parsed.Query().Get("cursor") != "opaque+cursor&" {
				t.Fatal("query scope changed", path)
			}
		}
		return pluginjson.Encode(map[string]any{"status": 200, "body_base64": base64.RawStdEncoding.EncodeToString([]byte(body))})
	}}
	page, err := client.StorageList(context.Background(), "a_", "opaque+cursor&", 50)
	if err != nil || len(page.Items) != 1 || page.Items[0].Key != "a_b" || page.Items[0].Bytes != 5 || page.NextCursor != "opaque.scope.cursor" {
		t.Fatal(page, err)
	}
	usage, err := client.StorageUsage(context.Background())
	if err != nil || usage.Keys != 1 || usage.UsedBytes != 5 || usage.LimitBytes != 16777216 {
		t.Fatal(usage, err)
	}
	if _, err := client.StorageList(context.Background(), "", "", 1000); err == nil || calls != 2 {
		t.Fatal("unbounded page accepted", calls, err)
	}
}

func TestStorageCatalogRejectsMalformedSuccess(t *testing.T) {
	for _, body := range []string{`{}`, `{"data":null}`, `{"data":{"items":{},"next_cursor":null}}`, `{"data":{"items":[{"key":"x"}],"next_cursor":null}}`} {
		client := Client{Call: func(context.Context, string, any) (pluginjson.Raw, error) {
			return pluginjson.Encode(map[string]any{"status": 200, "body_base64": base64.RawStdEncoding.EncodeToString([]byte(body))})
		}}
		if _, err := client.StorageList(context.Background(), "", "", 50); err == nil {
			t.Fatal("malformed page accepted", body)
		}
		if _, err := client.StorageUsage(context.Background()); err == nil {
			t.Fatal("malformed usage appeared as zero", body)
		}
	}
}

func TestStorageCatalogRequiresUsableContinuation(t *testing.T) {
	for _, body := range []string{`{"data":{"items":[]}}`, `{"data":{"items":[],"next_cursor":42}}`, `{"data":{"items":[],"next_cursor":"next"}}`, `{"data":{"items":[],"next_cursor":"same"}}`} {
		client := Client{Call: func(context.Context, string, any) (pluginjson.Raw, error) { return jobHostResponse(200, body), nil }}
		if _, err := client.StorageList(context.Background(), "", "same", 50); err == nil {
			t.Fatal("unusable continuation accepted", body)
		}
	}
	client := Client{Call: func(context.Context, string, any) (pluginjson.Raw, error) {
		return jobHostResponse(200, `{"data":{"items":[],"next_cursor":null}}`), nil
	}}
	if page, err := client.StorageList(context.Background(), "", "", 50); err != nil || len(page.Items) != 0 || page.NextCursor != "" {
		t.Fatal("empty final page rejected", page, err)
	}
}
