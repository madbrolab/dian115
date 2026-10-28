package hostapi

import (
	"context"
	"errors"
	"strconv"
	"strings"

	"example.com/dian115-plugin-sdk/pluginjson"
)

type StorageMetadata struct {
	Key, Revision, UpdatedAt string
	Bytes                    int64
}
type StoragePage struct {
	Items      []StorageMetadata
	NextCursor string
}
type StorageUsage struct{ Keys, UsedBytes, RemainingBytes, LimitBytes, ValueLimitBytes int64 }

// StorageList returns metadata, not values. Continue with the same prefix and
// opaque cursor; fetch only selected values using StorageGet. No hidden retries
// or unbounded ListAll allocation are performed.
func (c Client) StorageList(ctx context.Context, prefix, cursor string, limit int) (StoragePage, error) {
	if limit < 1 || limit > 100 || len(prefix) > 160 || len(cursor) > 2048 {
		return StoragePage{}, errors.New("invalid storage page bounds")
	}
	query := "prefix=" + storageQueryEscape(prefix) + "&limit=" + strconv.Itoa(limit)
	if cursor != "" {
		query += "&cursor=" + storageQueryEscape(cursor)
	}
	data, err := c.readData(ctx, "/api/plugin-runtime/storage?"+query)
	if err != nil {
		return StoragePage{}, err
	}
	next := pluginjson.Field(data, "next_cursor")
	page := StoragePage{Items: make([]StorageMetadata, 0), NextCursor: pluginjson.Text(next)}
	if string(next) != "null" && (len(next) == 0 || next[0] != '"' || page.NextCursor == "" || len(page.NextCursor) > 2048 || page.NextCursor == cursor) {
		return StoragePage{}, errors.New("invalid storage continuation cursor")
	}
	items := pluginjson.Field(data, "items")
	if len(items) == 0 || items[0] != '[' || len(pluginjson.Index(items, limit)) != 0 {
		return StoragePage{}, errors.New("invalid storage metadata page")
	}
	for i := 0; i < 100; i++ {
		raw := pluginjson.Index(items, i)
		if len(raw) == 0 {
			break
		}
		item := StorageMetadata{Key: pluginjson.Text(pluginjson.Field(raw, "key")), Revision: pluginjson.Text(pluginjson.Field(raw, "revision")), UpdatedAt: pluginjson.Text(pluginjson.Field(raw, "updated_at"))}
		item.Bytes, err = strconv.ParseInt(strings.TrimSpace(string(pluginjson.Field(raw, "bytes"))), 10, 64)
		if err != nil || item.Bytes < 0 || item.Key == "" || item.Revision == "" || item.UpdatedAt == "" {
			return StoragePage{}, errors.New("invalid storage metadata item")
		}
		page.Items = append(page.Items, item)
	}
	if len(page.Items) == 0 && page.NextCursor != "" {
		return StoragePage{}, errors.New("empty storage page has a continuation cursor")
	}
	return page, nil
}

// Keep query encoding small for TinyGo; no URL parser or HTTP client is needed.
func storageQueryEscape(value string) string {
	const hex = "0123456789ABCDEF"
	var out strings.Builder
	for i := 0; i < len(value); i++ {
		c := value[i]
		if c >= 'a' && c <= 'z' || c >= 'A' && c <= 'Z' || c >= '0' && c <= '9' || c == '-' || c == '_' || c == '.' || c == '~' {
			out.WriteByte(c)
		} else {
			out.WriteByte('%')
			out.WriteByte(hex[c>>4])
			out.WriteByte(hex[c&15])
		}
	}
	return out.String()
}
func (c Client) StorageUsage(ctx context.Context) (StorageUsage, error) {
	data, err := c.readData(ctx, "/api/plugin-runtime/storage-usage")
	if err != nil {
		return StorageUsage{}, err
	}
	usage := StorageUsage{}
	for key, target := range map[string]*int64{"keys": &usage.Keys, "used_bytes": &usage.UsedBytes, "remaining_bytes": &usage.RemainingBytes, "limit_bytes": &usage.LimitBytes, "value_limit_bytes": &usage.ValueLimitBytes} {
		n, err := strconv.ParseInt(strings.TrimSpace(string(pluginjson.Field(data, key))), 10, 64)
		if err != nil || n < 0 {
			return StorageUsage{}, errors.New("invalid storage usage response")
		}
		*target = n
	}
	return usage, nil
}
func (c Client) readData(ctx context.Context, path string) (pluginjson.Raw, error) {
	if c.Call == nil {
		return nil, errors.New("invalid Host API client")
	}
	raw, err := c.Call(ctx, "host.call", map[string]any{"method": "GET", "path": path, "headers": map[string]string{"accept": "application/json"}})
	if err != nil {
		return nil, err
	}
	data, err := responseData(raw)
	if err != nil {
		return nil, err
	}
	if pluginjson.Int(pluginjson.Field(raw, "status")) != 200 {
		return nil, errors.New("unexpected Host API read status")
	}
	return data, nil
}

func responseData(raw pluginjson.Raw) (pluginjson.Raw, error) {
	if err := CheckResponse(raw); err != nil {
		return nil, err
	}
	body, err := Body(raw)
	if err != nil {
		return nil, err
	}
	data := pluginjson.Field(body, "data")
	if !pluginjson.Valid(data) || len(data) == 0 || data[0] != '{' {
		return nil, errors.New("invalid Host API response data")
	}
	return data, nil
}
