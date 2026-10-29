package hostapi

import (
	"context"
	"encoding/base64"
	"example.com/dian115-plugin-sdk/pluginjson"
	"net/url"
	"testing"
)

func TestHTTPBatchCacheControlsAndPerItemErrors(t *testing.T) {
	var method string
	var input map[string]any
	c := Client{Call: func(_ context.Context, m string, in any) (pluginjson.Raw, error) {
		method, input = m, in.(map[string]any)
		return pluginjson.Encode(map[string]any{"results": []any{
			map[string]any{"response": map[string]any{"status": 200, "headers": map[string]any{"x-dian115-body-truncated": []any{"true"}}, "body_base64": base64.RawStdEncoding.EncodeToString([]byte("page")), "network": map[string]any{"cache": "hit", "duration_ms": 2, "queue_ms": 0, "reused_connection": true}}},
			map[string]any{"error": "fixture failure"},
		}})
	}}
	result, err := c.HTTPBatch(context.Background(), []HTTPRequest{{URL: "https://one.test", TimeoutMS: 300000, CacheTTLMS: 60000}, {URL: "http://two.test", CacheMode: "no-store"}}, 4)
	if err != nil || len(result) != 2 || method != "host.http.batch" || input["concurrency"] != 4 {
		t.Fatal(method, input, result, err)
	}
	if result[0].Error != nil || !result[0].Response.Truncated || result[0].Response.Network.Cache != "hit" || !result[0].Response.Network.ReusedConnection || result[1].Error == nil {
		t.Fatal(result)
	}
	requests := input["requests"].([]any)
	if requests[0].(map[string]any)["timeout_ms"] != 300000 || requests[1].(map[string]any)["cache_mode"] != "no-store" {
		t.Fatal(input)
	}
	if _, err = c.HTTPBatch(context.Background(), []HTTPRequest{{URL: "https://one.test", Method: "POST"}}, 1); err == nil {
		t.Fatal("batch accepted side effect")
	}
	if _, err = c.HTTP(context.Background(), HTTPRequest{URL: "https://one.test", TimeoutMS: 300001}); err == nil {
		t.Fatal("unbounded timeout accepted")
	}
	if _, err = c.HTTP(context.Background(), HTTPRequest{URL: "https://one.test", CacheTTLMS: 86400001}); err == nil {
		t.Fatal("unbounded cache lifetime accepted")
	}
	if _, err = c.HTTP(context.Background(), HTTPRequest{URL: "https://one.test", CacheMode: "made-up"}); err == nil {
		t.Fatal("invalid cache mode accepted")
	}
}

func TestPostFormAndDynamicSites(t *testing.T) {
	var request map[string]any
	c := Client{Call: func(_ context.Context, _ string, input any) (pluginjson.Raw, error) {
		request = input.(map[string]any)
		body, _ := pluginjson.Encode(map[string]any{"data": map[string]any{"sites": []any{}}})
		return pluginjson.Encode(map[string]any{"status": 200, "body_base64": base64.RawStdEncoding.EncodeToString(body)})
	}}
	fields := map[string]string{"password": "p&=+ 密码", "csrf": "a/b?c", "captcha": "1234", "username": "user@example.test"}
	headers := map[string]string{"Content-Type": "old", "x-custom": "kept"}
	if _, err := c.PostForm(context.Background(), HTTPRequest{URL: "https://custom.test/login", Session: "account", Headers: headers}, fields); err != nil {
		t.Fatal(err)
	}
	body, err := base64.RawStdEncoding.DecodeString(request["body_base64"].(string))
	if err != nil {
		t.Fatal(err)
	}
	form, err := url.ParseQuery(string(body))
	if err != nil {
		t.Fatal(err)
	}
	for key, value := range fields {
		if form.Get(key) != value {
			t.Fatal("form changed", key, form)
		}
	}
	if headers["Content-Type"] != "old" || request["cookie_session"] != "account" || request["method"] != "POST" {
		t.Fatal("request mutated", request, headers)
	}
	if _, err := c.SaveSite(context.Background(), HTTPSite{ID: "mine", URL: "http://192.0.2.1:8080/api", Label: "我的站点"}, "site-save-sdk-123456"); err != nil {
		t.Fatal(err)
	}
	body, _ = base64.RawStdEncoding.DecodeString(request["body_base64"].(string))
	if pluginjson.Text(pluginjson.Field(body, "url")) != "http://192.0.2.1:8080/api" {
		t.Fatal(request, string(body))
	}
	if _, err := c.SetCookieHeader(context.Background(), "https://custom.test", "account", "auth=manual", "manual-sdk-123456"); err != nil {
		t.Fatal(err)
	}
	body, _ = base64.RawStdEncoding.DecodeString(request["body_base64"].(string))
	if pluginjson.Text(pluginjson.Field(body, "cookie")) != "auth=manual" {
		t.Fatal(request)
	}
	if _, err := c.DeleteSite(context.Background(), "site-a", "site-remove-123456"); err != nil || request["path"] != "/api/plugin-runtime/http/sites?id=site-a" {
		t.Fatal(request, err)
	}
	if _, err := c.DeleteSite(context.Background(), "", "site-reset-123456"); err != nil || request["path"] != "/api/plugin-runtime/http/sites" {
		t.Fatal(request, err)
	}
}

func TestHTTPSessionRequestsAndHTTPStatus(t *testing.T) {
	var request map[string]any
	c := Client{Call: func(ctx context.Context, method string, input any) (pluginjson.Raw, error) {
		request = input.(map[string]any)
		return pluginjson.Encode(map[string]any{"status": 401, "headers": map[string]any{}, "body_base64": base64.RawStdEncoding.EncodeToString([]byte(`{"login":false}`))})
	}}
	r, e := c.HTTP(context.Background(), HTTPRequest{URL: "https://example.test/login", Method: "POST", Session: "account-a", Body: []byte("x=y"), TimeoutMS: 30000})
	if e != nil || r.Status != 401 || string(r.Body) != `{"login":false}` || request["cookie_session"] != "account-a" {
		t.Fatal(r, e, request)
	}
	if _, e = c.HTTP(context.Background(), HTTPRequest{URL: "https://example.test", Session: "../bad"}); e == nil {
		t.Fatal("bad session accepted")
	}
	c.Call = func(ctx context.Context, method string, input any) (pluginjson.Raw, error) {
		request = input.(map[string]any)
		body, _ := pluginjson.Encode(map[string]any{"data": map[string]any{"total_cookies": 0}})
		return pluginjson.Encode(map[string]any{"status": 200, "body_base64": base64.RawStdEncoding.EncodeToString(body)})
	}
	if _, e = c.Cookies(context.Background(), "https://example.test/a?x=1&y=2", "account-a"); e != nil || request["path"] != "/api/plugin-runtime/http/cookies?url=https%3A%2F%2Fexample.test%2Fa%3Fx%3D1%26y%3D2&session=account-a" {
		t.Fatal(request, e)
	}
	if _, e = c.SetCookies(context.Background(), "https://example.test", "account-a", []string{"auth=x; Secure; HttpOnly"}, "cookie-write-attempt-123"); e != nil {
		t.Fatal(e)
	}
	body, _ := base64.RawStdEncoding.DecodeString(request["body_base64"].(string))
	if pluginjson.Text(pluginjson.Field(body, "session")) != "account-a" || pluginjson.Text(pluginjson.Index(pluginjson.Field(body, "set_cookie"), 0)) != "auth=x; Secure; HttpOnly" {
		t.Fatal(string(body))
	}
	if _, e = c.ClearCookies(context.Background(), "account-a", "clear-attempt-123456"); e != nil {
		t.Fatal(e)
	}
	if _, e = c.ImportCookieCloud(context.Background(), "account-a", []string{"example.test"}, "import-attempt-123456"); e != nil {
		t.Fatal(e)
	}
	if _, e = c.RenderPage(context.Background(), "https://example.test", "account-a", 3, "render-attempt-123456"); e != nil {
		t.Fatal(e)
	}
}
