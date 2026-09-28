package main

import (
	"context"
	"encoding/base64"
	"encoding/json"
	"errors"
	"fmt"
	"net/url"
	"strings"
	"time"
)

// hostCall 通过宿主执行一次 Host API / 外部 HTTP 调用。
func (r *runtime) hostCall(req hostCallRequest) (hostCallResponse, error) {
	ctx, cancel := context.WithTimeout(context.Background(), 30*time.Second)
	defer cancel()
	var resp hostCallResponse
	err := r.peer.call(ctx, "host.call", req, &resp)
	return resp, err
}

// b64decode 解码宿主返回的 body_base64（unpadded / padded 均兼容）。
func b64decode(s string) ([]byte, error) {
	if s == "" {
		return nil, nil
	}
	for _, enc := range []*base64.Encoding{base64.RawStdEncoding, base64.StdEncoding} {
		if b, err := enc.DecodeString(s); err == nil {
			return b, nil
		}
	}
	return nil, errors.New("invalid base64 body")
}

// b64encode 编码请求体。
func b64encode(b []byte) string {
	return base64.RawStdEncoding.EncodeToString(b)
}

// httpGet 通过宿主 Broker 发起外部 GET，返回状态码与解码后的正文。
func (r *runtime) httpGet(rawURL string, headers map[string]string) (int, []byte, error) {
	resp, err := r.hostCall(hostCallRequest{Method: "GET", Path: rawURL, Headers: headers})
	if err != nil {
		return 0, nil, err
	}
	body, derr := b64decode(resp.BodyBase64)
	if derr != nil {
		return resp.Status, nil, derr
	}
	return resp.Status, body, nil
}

// httpPostForm 通过宿主 Broker 发起外部表单 POST。
func (r *runtime) httpPostForm(rawURL string, headers map[string]string, form url.Values) (int, []byte, error) {
	if headers == nil {
		headers = map[string]string{}
	}
	headers["content-type"] = "application/x-www-form-urlencoded"
	resp, err := r.hostCall(hostCallRequest{
		Method:     "POST",
		Path:       rawURL,
		Headers:    headers,
		BodyBase64: b64encode([]byte(form.Encode())),
	})
	if err != nil {
		return 0, nil, err
	}
	body, derr := b64decode(resp.BodyBase64)
	if derr != nil {
		return resp.Status, nil, derr
	}
	return resp.Status, body, nil
}

// newIdempotencyKey 生成稳定且唯一的幂等键。
func (r *runtime) newIdempotencyKey(prefix string) string {
	r.mu.Lock()
	r.seq++
	seq := r.seq
	r.mu.Unlock()
	return fmt.Sprintf("%s-%d-%d", prefix, time.Now().UnixNano(), seq)
}

// ---- Host Storage ----

// firstHeader 大小写不敏感地取第一个响应头值。
func firstHeader(headers map[string][]string, name string) string {
	for key, values := range headers {
		if strings.EqualFold(key, name) && len(values) > 0 {
			return strings.TrimSpace(values[0])
		}
	}
	return ""
}

func (r *runtime) setETag(key, etag string) {
	if etag == "" {
		return
	}
	r.mu.Lock()
	if r.etags == nil {
		r.etags = map[string]string{}
	}
	r.etags[key] = etag
	r.mu.Unlock()
}

func (r *runtime) clearETag(key string) {
	r.mu.Lock()
	delete(r.etags, key)
	r.mu.Unlock()
}

func (r *runtime) cachedETag(key string) string {
	r.mu.Lock()
	defer r.mu.Unlock()
	if r.etags == nil {
		return ""
	}
	return r.etags[key]
}

// storageGet 读取插件自己的持久化数据；不存在时返回 false。
func (r *runtime) storageGet(key string, target any) (bool, error) {
	resp, err := r.hostCall(hostCallRequest{Method: "GET", Path: "/api/plugin-runtime/storage/" + key, Headers: map[string]string{"accept": "application/json"}})
	if err != nil {
		return false, err
	}
	if resp.Status == 404 {
		return false, nil
	}
	if resp.Status != 200 {
		return false, fmt.Errorf("storage get HTTP %d", resp.Status)
	}
	if etag := firstHeader(resp.Headers, "ETag"); etag != "" {
		r.setETag(key, etag)
	}
	body, derr := b64decode(resp.BodyBase64)
	if derr != nil {
		return false, derr
	}
	var envelope struct {
		Data struct {
			Value json.RawMessage `json:"value"`
		} `json:"data"`
	}
	if err := json.Unmarshal(body, &envelope); err != nil {
		return false, err
	}
	if len(envelope.Data.Value) == 0 || string(envelope.Data.Value) == "null" {
		return false, nil
	}
	if target == nil {
		return true, nil
	}
	return true, json.Unmarshal(envelope.Data.Value, target)
}

// storagePut 保存插件自己的持久化数据。
//
// 宿主对更新已有值强制乐观并发（CAS）：缺少 If-Match 或 ETag 过期会返回 412。
// 这里优先带上缓存的 ETag，遇到 412 时重新 GET 最新 ETag 再重试（最多 4 轮）。
func (r *runtime) storagePut(key string, value any) error {
	v, err := json.Marshal(value)
	if err != nil {
		return err
	}
	body, _ := json.Marshal(map[string]json.RawMessage{"value": v})
	var lastErr error
	for attempt := 0; attempt < 4; attempt++ {
		headers := map[string]string{
			"content-type":    "application/json",
			"idempotency-key": r.newIdempotencyKey("storage-" + key),
		}
		if etag := r.cachedETag(key); etag != "" {
			headers["if-match"] = etag
		}
		resp, err := r.hostCall(hostCallRequest{
			Method:     "PUT",
			Path:       "/api/plugin-runtime/storage/" + key,
			Headers:    headers,
			BodyBase64: b64encode(body),
		})
		if err != nil {
			return err
		}
		if resp.Status == 200 {
			if etag := firstHeader(resp.Headers, "ETag"); etag != "" {
				r.setETag(key, etag)
			}
			return nil
		}
		if resp.Status != 412 && resp.Status != 409 {
			return fmt.Errorf("storage put HTTP %d", resp.Status)
		}
		lastErr = fmt.Errorf("storage put HTTP %d", resp.Status)
		// 冲突：重新读取最新 ETag 后重试。值不存在（404）时清空缓存再裸写。
		if ok, gerr := r.storageGet(key, nil); gerr != nil {
			return gerr
		} else if !ok {
			r.clearETag(key)
		}
	}
	return lastErr
}

// ---- TMDB ----

type tmdbItem struct {
	ID         int    `json:"id"`
	Title      string `json:"title"`
	Name       string `json:"name"`
	MediaType  string `json:"media_type"`
	// 原名（日文/韩文/英文等）：BangumiTV 这类榜单给的是原名，
	// 而 TMDB 的本地化标题往往是中文意译，只比本地化标题会漏识别。
	OriginalTitle string  `json:"original_title"`
	OriginalName  string  `json:"original_name"`
	ReleaseDate   string  `json:"release_date"`
	FirstAirDate  string  `json:"first_air_date"`
	PosterPath    string  `json:"poster_path"`
	VoteAverage   float64 `json:"vote_average"`
	VoteCount     int     `json:"vote_count"`
	Popularity    float64 `json:"popularity"`
}

type tmdbSearchResult struct {
	Page         int        `json:"page"`
	TotalResults int        `json:"total_results"`
	TotalPages   int        `json:"total_pages"`
	Results      []tmdbItem `json:"results"`
}

type tmdbMovieDetail struct {
	ID          int     `json:"id"`
	Title       string  `json:"title"`
	ReleaseDate string  `json:"release_date"`
	PosterPath  string  `json:"poster_path"`
	VoteAverage float64 `json:"vote_average"`
}

type tmdbTVDetail struct {
	ID           int     `json:"id"`
	Name         string  `json:"name"`
	FirstAirDate string  `json:"first_air_date"`
	PosterPath   string  `json:"poster_path"`
	VoteAverage  float64 `json:"vote_average"`
}

func (r *runtime) tmdbSearch(title string, page int) (*tmdbSearchResult, error) {
	q := url.QueryEscape(strings.TrimSpace(title))
	resp, err := r.hostCall(hostCallRequest{
		Method:  "GET",
		Path:    fmt.Sprintf("/api/tmdb/search?q=%s&page=%d", q, page),
		Headers: map[string]string{"accept": "application/json"},
	})
	if err != nil {
		return nil, err
	}
	if resp.Status != 200 {
		return nil, fmt.Errorf("tmdb search HTTP %d", resp.Status)
	}
	body, derr := b64decode(resp.BodyBase64)
	if derr != nil {
		return nil, derr
	}
	var result tmdbSearchResult
	if err := json.Unmarshal(body, &result); err != nil {
		return nil, err
	}
	return &result, nil
}

func (r *runtime) tmdbMovie(id int) (*tmdbMovieDetail, error) {
	resp, err := r.hostCall(hostCallRequest{Method: "GET", Path: fmt.Sprintf("/api/tmdb/movie/%d", id), Headers: map[string]string{"accept": "application/json"}})
	if err != nil {
		return nil, err
	}
	if resp.Status != 200 {
		return nil, fmt.Errorf("tmdb movie HTTP %d", resp.Status)
	}
	body, _ := b64decode(resp.BodyBase64)
	var detail tmdbMovieDetail
	if err := json.Unmarshal(body, &detail); err != nil {
		return nil, err
	}
	return &detail, nil
}

func (r *runtime) tmdbTV(id int) (*tmdbTVDetail, error) {
	resp, err := r.hostCall(hostCallRequest{Method: "GET", Path: fmt.Sprintf("/api/tmdb/tv/%d", id), Headers: map[string]string{"accept": "application/json"}})
	if err != nil {
		return nil, err
	}
	if resp.Status != 200 {
		return nil, fmt.Errorf("tmdb tv HTTP %d", resp.Status)
	}
	body, _ := b64decode(resp.BodyBase64)
	var detail tmdbTVDetail
	if err := json.Unmarshal(body, &detail); err != nil {
		return nil, err
	}
	return &detail, nil
}

// ---- 订阅 ----

type poolIntent struct {
	ID              int    `json:"id"`
	TMDBID          int    `json:"tmdb_id"`
	Season          int    `json:"season"`
	MediaType       string `json:"media_type"`
	Title           string `json:"title"`
	Year            string `json:"year"`
	State           string `json:"state"`
	PosterPath      string `json:"poster_path"`
	NeededEpisodes  string `json:"needed_episodes"`
	CoveredEpisodes string `json:"covered_episodes"`
}

type poolIntentResult struct {
	Code string     `json:"code"`
	Data poolIntent `json:"data"`
}

type poolIntentListResult struct {
	Code   string         `json:"code"`
	Data   []poolIntent   `json:"data"`
	Counts map[string]int `json:"counts"`
}

// listIntents 读取宿主现有订阅，返回去重键集合。
func (r *runtime) listIntents(mediaType string) (map[string]bool, error) {
	resp, err := r.hostCall(hostCallRequest{
		Method:  "GET",
		Path:    fmt.Sprintf("/api/subscribe/pool/intents?media_type=%s&limit=500&offset=0", mediaType),
		Headers: map[string]string{"accept": "application/json"},
	})
	if err != nil {
		return nil, err
	}
	if resp.Status != 200 {
		return nil, fmt.Errorf("list intents HTTP %d", resp.Status)
	}
	body, _ := b64decode(resp.BodyBase64)
	var result poolIntentListResult
	if err := json.Unmarshal(body, &result); err != nil {
		return nil, err
	}
	keys := map[string]bool{}
	for _, it := range result.Data {
		if mediaType == "tv" {
			keys[fmt.Sprintf("%d-S%d", it.TMDBID, it.Season)] = true
		} else {
			keys[fmt.Sprintf("%d", it.TMDBID)] = true
		}
	}
	return keys, nil
}

// createIntent 创建一条聚合订阅意图，返回新订阅 ID。
func (r *runtime) createIntent(tmdbID, season int, mediaType, title, year string, follow bool) (int, error) {
	req := map[string]any{
		"tmdb_id":    tmdbID,
		"media_type": mediaType,
		"title":      title,
	}
	if year != "" {
		req["year"] = year
	}
	if mediaType == "tv" {
		req["season"] = season
		if follow {
			req["episode_scope_mode"] = "follow"
		}
	}
	body, _ := json.Marshal(req)
	resp, err := r.hostCall(hostCallRequest{
		Method:     "POST",
		Path:       "/api/subscribe/pool/intents",
		Headers:    map[string]string{"content-type": "application/json", "idempotency-key": r.newIdempotencyKey("subscribe")},
		BodyBase64: b64encode(body),
	})
	if err != nil {
		return 0, err
	}
	if resp.Status != 200 {
		return 0, fmt.Errorf("create intent HTTP %d", resp.Status)
	}
	rb, _ := b64decode(resp.BodyBase64)
	var result poolIntentResult
	if err := json.Unmarshal(rb, &result); err != nil {
		return 0, err
	}
	if result.Code != "ok" || result.Data.ID <= 0 {
		return 0, fmt.Errorf("create intent rejected: %s", string(rb))
	}
	return result.Data.ID, nil
}

// ---- 通知 ----

func (r *runtime) notify(level, title, body string) {
	cfg := r.currentConfig()
	if cfg == nil || !cfg.Notify {
		return
	}
	b, _ := json.Marshal(map[string]string{"level": level, "title": title, "body": body})
	_, err := r.hostCall(hostCallRequest{
		Method:     "POST",
		Path:       "/api/notifications/plugin",
		Headers:    map[string]string{"content-type": "application/json", "idempotency-key": r.newIdempotencyKey("notify")},
		BodyBase64: b64encode(b),
	})
	if err != nil {
		r.log("warning", "通知发送失败", map[string]any{"reason": err.Error()})
	}
}

// log 记录安装作用域日志。
func (r *runtime) log(level, message string, fields map[string]any) {
	ctx, cancel := context.WithTimeout(context.Background(), 3*time.Second)
	defer cancel()
	var ignored map[string]any
	_ = r.peer.call(ctx, "host.log", map[string]any{"level": level, "message": message, "fields": fields}, &ignored)
}
