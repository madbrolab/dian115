// Package hostapi wraps the public Host Call contract. The guest supplies its
// ABI transport; no host code, credentials or database driver is required.
package hostapi

import (
	"context"
	"encoding/base64"
	"errors"
	"strconv"
	"strings"

	"example.com/dian115-plugin-sdk/pluginjson"
)

type Transport func(context.Context, string, any) (pluginjson.Raw, error)
type Client struct{ Call Transport }
type Problem struct {
	Status       int
	Code, Detail string
	DiagnosticID string
	Retryable    bool
}

func (p *Problem) Error() string {
	return p.Code + ": " + p.Detail + " (HTTP " + strconv.Itoa(p.Status) + ")"
}

// CheckResponse keeps transport errors distinct from target HTTP failures.
// Low-level host.call returns 4xx/5xx as normal results; helpers must inspect it.
func CheckResponse(raw pluginjson.Raw) error {
	status := pluginjson.Int(pluginjson.Field(raw, "status"))
	if status < 100 || status > 599 {
		return errors.New("invalid Host Call response status")
	}
	if status < 400 {
		return nil
	}
	body, _ := Body(raw)
	code, detail := pluginjson.Text(pluginjson.Field(body, "code")), pluginjson.Text(pluginjson.Field(body, "detail"))
	if code == "" {
		code = "http_error"
	}
	if detail == "" {
		detail = pluginjson.Text(pluginjson.Field(body, "error"))
	}
	if detail == "" {
		detail = "Host API rejected the request"
	}
	return &Problem{Status: status, Code: code, Detail: detail, DiagnosticID: pluginjson.Text(pluginjson.Field(body, "diagnostic_id")), Retryable: string(pluginjson.Field(body, "retryable")) == "true"}
}
func Body(raw pluginjson.Raw) (pluginjson.Raw, error) {
	field := pluginjson.Field(raw, "body_base64")
	if len(field) == 0 || field[0] != '"' {
		return nil, errors.New("invalid Host Call body encoding")
	}
	text := pluginjson.Text(field)
	if len(text) > (8<<20)*4/3+4 {
		return nil, errors.New("Host Call body exceeds limit")
	}
	encoding := base64.RawStdEncoding
	if strings.HasSuffix(text, "=") {
		encoding = base64.StdEncoding
	}
	body, err := encoding.DecodeString(text)
	if len(body) > 8<<20 {
		return nil, errors.New("Host Call body exceeds limit")
	}
	return body, err
}

func validStorageETag(tag string) bool {
	if len(tag) < 7 || !strings.HasPrefix(tag, `"pkv_`) || tag[len(tag)-1] != '"' {
		return false
	}
	digits := tag[5 : len(tag)-1]
	if digits[0] == '0' {
		return false
	}
	for _, c := range digits {
		if c < '0' || c > '9' {
			return false
		}
	}
	_, err := strconv.ParseInt(digits, 10, 64)
	return err == nil
}
func Header(raw pluginjson.Raw, name string) string {
	for key, values := range pluginjson.Fields(pluginjson.Field(raw, "headers")) {
		if strings.EqualFold(key, name) {
			return pluginjson.Text(pluginjson.Index(values, 0))
		}
	}
	return ""
}
func validIdempotencyKey(key string) bool {
	if len(key) < 16 || len(key) > 128 {
		return false
	}
	for _, r := range key {
		if r < 0x21 || r > 0x7e {
			return false
		}
	}
	return true
}
func Key(prefix, businessID string) (string, error) {
	key := prefix + "-" + businessID
	if !validIdempotencyKey(key) {
		return "", errors.New("idempotency key must contain 16-128 printable ASCII characters")
	}
	return key, nil
}
func ValidStorageKey(key string) bool {
	if len(key) < 1 || len(key) > 160 {
		return false
	}
	separator := true
	for _, r := range key {
		if r >= 'a' && r <= 'z' || r >= 'A' && r <= 'Z' || r >= '0' && r <= '9' {
			separator = false
			continue
		}
		if separator || r != '.' && r != '_' && r != '-' {
			return false
		}
		separator = true
	}
	return !separator
}
func (c Client) StorageGet(ctx context.Context, key string) (pluginjson.Raw, string, error) {
	return c.storage(ctx, "GET", key, nil, "", "")
}
func (c Client) StoragePut(ctx context.Context, key string, value pluginjson.Raw, etag, idempotencyKey string) (pluginjson.Raw, string, error) {
	return c.storage(ctx, "PUT", key, value, etag, idempotencyKey)
}
func (c Client) StorageDelete(ctx context.Context, key, idempotencyKey string) error {
	_, _, err := c.storage(ctx, "DELETE", key, nil, "", idempotencyKey)
	return err
}
func (c Client) storage(ctx context.Context, method, key string, value pluginjson.Raw, etag, idempotencyKey string) (pluginjson.Raw, string, error) {
	if c.Call == nil || !ValidStorageKey(key) {
		return nil, "", errors.New("invalid storage client or key")
	}
	headers := map[string]string{"accept": "application/json"}
	request := map[string]any{"method": method, "path": "/api/plugin-runtime/storage/" + key, "headers": headers}
	if method != "GET" {
		if !validIdempotencyKey(idempotencyKey) {
			return nil, "", errors.New("invalid storage idempotency key")
		}
		headers["idempotency-key"] = idempotencyKey
	}
	if method == "PUT" {
		if etag != "" && !validStorageETag(etag) {
			return nil, "", errors.New("invalid storage ETag")
		}
		if len(value) > 1<<20 || !pluginjson.Valid(value) {
			return nil, "", errors.New("storage value must be JSON no larger than 1 MiB")
		}
		body, err := pluginjson.Encode(map[string]any{"value": value})
		if err != nil {
			return nil, "", err
		}
		headers["content-type"] = "application/json"
		request["body_base64"] = base64.RawStdEncoding.EncodeToString(body)
		if etag != "" {
			headers["if-match"] = etag
		}
	}
	raw, err := c.Call(ctx, "host.call", request)
	if err != nil {
		return nil, "", err
	}
	data, err := responseData(raw)
	if err != nil {
		return nil, "", err
	}
	if pluginjson.Int(pluginjson.Field(raw, "status")) != 200 {
		return nil, "", errors.New("unexpected storage response status")
	}
	if method == "DELETE" {
		return nil, "", nil
	}
	value = pluginjson.Field(data, "value")
	responseETag := Header(raw, "ETag")
	if !pluginjson.Valid(value) || pluginjson.Text(pluginjson.Field(data, "key")) != key || !validStorageETag(responseETag) || pluginjson.Text(pluginjson.Field(data, "revision")) != responseETag[1:len(responseETag)-1] || pluginjson.Text(pluginjson.Field(data, "updated_at")) == "" {
		return nil, "", errors.New("invalid storage value response")
	}
	return value, responseETag, nil
}
