package main

import (
	"encoding/json"
	"regexp"
	"strconv"
	"strings"
)

func atoiSafe(s string) int {
	n, err := strconv.Atoi(s)
	if err != nil {
		return 0
	}
	return n
}

func itoaSafe(n int) string {
	return strconv.Itoa(n)
}

// setKeys / toSet 在「订阅池键集合」与其可持久化形式之间转换。
// 分片任务的进度要写进 Host Storage，map 直接序列化没问题，但统一成切片
// 能让 job state 的体积与顺序都可控。
func setKeys(m map[string]bool) []string {
	out := make([]string, 0, len(m))
	for k := range m {
		out = append(out, k)
	}
	return out
}

func toSet(s []string) map[string]bool {
	out := make(map[string]bool, len(s))
	for _, k := range s {
		out[k] = true
	}
	return out
}

// errString 把 error 转成可写进日志的字符串（诊断日志里 err 字段用）。
func errString(err error) string {
	if err == nil {
		return ""
	}
	return err.Error()
}

// ---- UI result 安全字段过滤 ----
// 宿主会递归拒绝业务 result 中包含敏感字样的 key（process-runtime-v1.md 第 4 节）：
// 包含 "cookie" 的 key、名为 password/authorization 等的 key、以 _token/_secret 结尾的 key。
// 这里在返回前统一清洗，作为字段命名规则的第二道防线。

var bannedKeyRe = regexp.MustCompile(`_token$|_secret$`)

func isBannedKey(key string) bool {
	k := strings.ToLower(key)
	if strings.Contains(k, "cookie") {
		return true
	}
	switch k {
	case "password", "client_secret", "webhook_secret", "access_token", "refresh_token",
		"authorization", "cid", "file_id", "database_id", "absolute_path", "raw_path":
		return true
	}
	return bannedKeyRe.MatchString(k)
}

// sanitizeForUI 递归删除 result 中会触发宿主安全字段拒绝的键值对。
func sanitizeForUI(value any) any {
	switch v := value.(type) {
	case map[string]any:
		out := make(map[string]any, len(v))
		for k, val := range v {
			if isBannedKey(k) {
				continue
			}
			out[k] = sanitizeForUI(val)
		}
		return out
	case []any:
		out := make([]any, len(v))
		for i, val := range v {
			out[i] = sanitizeForUI(val)
		}
		return out
	default:
		return value
	}
}

// sanitizeJSON 对最终响应 JSON 做整体安全清洗（键名过滤）。
func sanitizeJSON(raw []byte) []byte {
	var v any
	if err := json.Unmarshal(raw, &v); err != nil {
		return raw
	}
	out, err := json.Marshal(sanitizeForUI(v))
	if err != nil {
		return raw
	}
	return out
}
