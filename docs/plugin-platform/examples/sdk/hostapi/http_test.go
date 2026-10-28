package hostapi

import (
	"context"
	"encoding/base64"
	"example.com/dian115-plugin-sdk/pluginjson"
	"testing"
)

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
