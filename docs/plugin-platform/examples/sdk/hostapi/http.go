package hostapi

import (
	"context"
	"encoding/base64"
	"errors"
	"sort"
	"strings"

	"example.com/dian115-plugin-sdk/pluginjson"
)

// HTTPRequest uses the host's HTTP client, never a guest socket. Session defaults
// to "default"; "none" disables managed cookies for this request only.
type HTTPRequest struct {
	Method, URL, Session string
	Headers              map[string]string
	Body                 []byte
	TimeoutMS            int
}
type HTTPResponse struct {
	Status  int
	Headers pluginjson.Raw
	Body    []byte
}

func validHTTPSession(v string) bool {
	if v == "" {
		return true
	}
	if len(v) > 64 {
		return false
	}
	for i, c := range v {
		if c >= 'a' && c <= 'z' || c >= 'A' && c <= 'Z' || c >= '0' && c <= '9' {
			continue
		}
		if i == 0 || c != '.' && c != '_' && c != '-' {
			return false
		}
	}
	return true
}

func (c Client) HTTP(ctx context.Context, r HTTPRequest) (HTTPResponse, error) {
	var result HTTPResponse
	if c.Call == nil || !(strings.HasPrefix(r.URL, "https://") || strings.HasPrefix(r.URL, "http://")) || !validHTTPSession(r.Session) || r.TimeoutMS < 0 || r.TimeoutMS > 30000 || len(r.Body) > 8<<20 {
		return result, errors.New("invalid HTTP request")
	}
	method := strings.ToUpper(r.Method)
	if method == "" {
		method = "GET"
	}
	switch method {
	case "GET", "HEAD", "POST", "PUT", "PATCH", "DELETE":
	default:
		return result, errors.New("invalid HTTP method")
	}
	request := map[string]any{"method": method, "path": r.URL}
	if r.Headers != nil {
		request["headers"] = r.Headers
	}
	if r.Session != "" {
		request["cookie_session"] = r.Session
	}
	if r.TimeoutMS > 0 {
		request["timeout_ms"] = r.TimeoutMS
	}
	if len(r.Body) > 0 {
		request["body_base64"] = base64.RawStdEncoding.EncodeToString(r.Body)
	}
	raw, err := c.Call(ctx, "host.call", request)
	if err != nil {
		return result, err
	}
	result.Status = pluginjson.Int(pluginjson.Field(raw, "status"))
	result.Headers = pluginjson.Field(raw, "headers")
	if result.Status < 100 || result.Status > 599 {
		return result, errors.New("invalid HTTP response")
	}
	result.Body, err = Body(raw)
	if err != nil {
		return result, err
	}
	// HTTP error statuses retain their body. Transport success does not imply
	// login or business success; the plugin inspects its site's response.
	return result, nil
}

// PostForm accepts site-specific names, CSRF tokens and captcha answers.
// The host remembers response cookies in r.Session; no CookieCloud is needed.
func (c Client) PostForm(ctx context.Context, r HTTPRequest, fields map[string]string) (HTTPResponse, error) {
	keys := make([]string, 0, len(fields))
	for key := range fields {
		keys = append(keys, key)
	}
	sort.Strings(keys)
	var body strings.Builder
	for i, key := range keys {
		if i > 0 {
			body.WriteByte('&')
		}
		body.WriteString(escapeHTTPQuery(key))
		body.WriteByte('=')
		body.WriteString(escapeHTTPQuery(fields[key]))
	}
	headers := make(map[string]string, len(r.Headers)+1)
	for key, value := range r.Headers {
		if !strings.EqualFold(key, "content-type") {
			headers[key] = value
		}
	}
	headers["content-type"] = "application/x-www-form-urlencoded"
	r.Method, r.Body, r.Headers = "POST", []byte(body.String()), headers
	return c.HTTP(ctx, r)
}

type HTTPSite struct {
	ID    string `json:"id"`
	URL   string `json:"url"`
	Label string `json:"label,omitempty"`
}

func (c Client) Sites(ctx context.Context) (pluginjson.Raw, error) {
	return c.sessionRequest(ctx, "GET", "sites", nil, "")
}
func (c Client) SaveSite(ctx context.Context, site HTTPSite, key string) (pluginjson.Raw, error) {
	return c.sessionRequest(ctx, "PUT", "sites", map[string]any{"id": site.ID, "url": site.URL, "label": site.Label}, key)
}
func (c Client) DeleteSite(ctx context.Context, id, key string) (pluginjson.Raw, error) {
	if id == "" {
		return c.sessionRequest(ctx, "DELETE", "sites", nil, key)
	}
	return c.sessionRequest(ctx, "DELETE", "sites?id="+escapeHTTPQuery(id), nil, key)
}

func (c Client) sessionRequest(ctx context.Context, method, path string, input any, key string) (pluginjson.Raw, error) {
	if c.Call == nil {
		return nil, errors.New("HTTP session client is unavailable")
	}
	headers := map[string]string{"accept": "application/json"}
	request := map[string]any{"method": method, "path": "/api/plugin-runtime/http/" + path, "headers": headers}
	if method != "GET" {
		if !validIdempotencyKey(key) {
			return nil, errors.New("invalid HTTP session idempotency key")
		}
		headers["idempotency-key"] = key
	}
	if input != nil {
		body, err := pluginjson.Encode(input)
		if err != nil {
			return nil, err
		}
		headers["content-type"] = "application/json"
		request["body_base64"] = base64.RawStdEncoding.EncodeToString(body)
	}
	raw, err := c.Call(ctx, "host.call", request)
	if err != nil {
		return nil, err
	}
	data, err := responseData(raw)
	if err != nil {
		return nil, err
	}
	if pluginjson.Int(pluginjson.Field(raw, "status")) != 200 {
		return nil, errors.New("unexpected HTTP session response status")
	}
	return data, nil
}

func escapeHTTPQuery(value string) string {
	const hex = "0123456789ABCDEF"
	var b strings.Builder
	for i := 0; i < len(value); i++ {
		v := value[i]
		if v >= 'a' && v <= 'z' || v >= 'A' && v <= 'Z' || v >= '0' && v <= '9' || v == '-' || v == '_' || v == '.' || v == '~' {
			b.WriteByte(v)
		} else {
			b.WriteByte('%')
			b.WriteByte(hex[v>>4])
			b.WriteByte(hex[v&15])
		}
	}
	return b.String()
}

func validManagedHTTPSession(value string) bool { return value != "none" && validHTTPSession(value) }

// Cookies returns only cookies matching targetURL, including HttpOnly values
// belonging to this installation. Display only when explicitly requested by
// the user; avoid broad state snapshots, ordinary preferences and logs.
func (c Client) Cookies(ctx context.Context, targetURL, session string) (pluginjson.Raw, error) {
	if !validManagedHTTPSession(session) {
		return nil, errors.New("invalid cookie session")
	}
	return c.sessionRequest(ctx, "GET", "cookies?url="+escapeHTTPQuery(targetURL)+"&session="+escapeHTTPQuery(session), nil, "")
}
func (c Client) SetCookies(ctx context.Context, targetURL, session string, headers []string, key string) (pluginjson.Raw, error) {
	if !validManagedHTTPSession(session) || len(headers) == 0 || len(headers) > 64 {
		return nil, errors.New("invalid cookie update")
	}
	return c.sessionRequest(ctx, "PUT", "cookies", map[string]any{"url": targetURL, "session": session, "set_cookie": headers}, key)
}

// SetCookieHeader persists a manually entered Cookie header in this account.
func (c Client) SetCookieHeader(ctx context.Context, targetURL, session, cookie, key string) (pluginjson.Raw, error) {
	if !validManagedHTTPSession(session) || strings.TrimSpace(cookie) == "" || len(cookie) > 8192 {
		return nil, errors.New("invalid Cookie header")
	}
	return c.sessionRequest(ctx, "PUT", "cookies", map[string]any{"url": targetURL, "session": session, "cookie": cookie}, key)
}
func (c Client) ClearCookies(ctx context.Context, session, key string) (pluginjson.Raw, error) {
	if !validManagedHTTPSession(session) {
		return nil, errors.New("invalid cookie session")
	}
	return c.sessionRequest(ctx, "DELETE", "cookies?session="+escapeHTTPQuery(session), nil, key)
}
func (c Client) CookieCloud(ctx context.Context) (pluginjson.Raw, error) {
	return c.sessionRequest(ctx, "GET", "cookiecloud", nil, "")
}
func (c Client) ImportCookieCloud(ctx context.Context, session string, domains []string, key string) (pluginjson.Raw, error) {
	if !validManagedHTTPSession(session) || len(domains) == 0 || len(domains) > 16 {
		return nil, errors.New("invalid CookieCloud import")
	}
	return c.sessionRequest(ctx, "POST", "cookiecloud/import", map[string]any{"session": session, "domains": domains}, key)
}
func (c Client) ExportCookieCloud(ctx context.Context, session string, domains []string, revision, key string) (pluginjson.Raw, error) {
	if !validManagedHTTPSession(session) || len(domains) == 0 || len(domains) > 16 || len(revision) != 64 {
		return nil, errors.New("invalid CookieCloud export")
	}
	return c.sessionRequest(ctx, "POST", "cookiecloud/export", map[string]any{"session": session, "domains": domains, "revision": revision}, key)
}

// RenderPage is explicitly requested, GET-only and bounded to a temporary
// FlareSolverr session. It does not retry, submit login forms or start Chromium.
func (c Client) RenderPage(ctx context.Context, targetURL, session string, waitSeconds int, key string) (pluginjson.Raw, error) {
	if !validManagedHTTPSession(session) || waitSeconds < 0 || waitSeconds > 10 {
		return nil, errors.New("invalid render request")
	}
	return c.sessionRequest(ctx, "POST", "render", map[string]any{"url": targetURL, "session": session, "wait_seconds": waitSeconds}, key)
}
