package main

import (
	"encoding/json"
	"fmt"
	"sort"
	"strings"
	"time"
)

// ---- 榜单快照（每次榜单同步后持久化，供仪表盘展示） ----

const (
	storageRankSnapshot = "rank_snapshot"
	snapshotItemLimit   = 50 // 每个榜单最多保留的快照条目
	dashHistoryLimit    = 60 // 仪表盘订阅历史每类最多返回条数
)

// SnapshotItem 榜单快照条目。键名必须避开宿主安全字段规则
// （不得含 cookie/password，不得以 _token/_secret 结尾，字符串值不得以 / 开头）。
type SnapshotItem struct {
	Rank      int    `json:"rank"` // 榜单内名次（1 起）
	Title     string `json:"title"`
	Year      string `json:"year,omitempty"`
	DoubanID  string `json:"douban_id,omitempty"`
	TMDBID    int    `json:"tmdb_id,omitempty"`
	MediaType string `json:"media_type"`
	Poster    string `json:"poster,omitempty"` // https://image.tmdb.org/... 完整 URL
	Link      string `json:"link,omitempty"`   // https://movie.douban.com/subject/... 完整 URL
	Status    string `json:"status"`           // subscribed/existing/observing/blacklisted/filtered/unresolved
	Reason    string `json:"reason,omitempty"`
}

func (r *runtime) loadRankSnapshot() map[string][]SnapshotItem {
	var m map[string][]SnapshotItem
	if _, err := r.storageGet(storageRankSnapshot, &m); err != nil || m == nil {
		return map[string][]SnapshotItem{}
	}
	return m
}

func (r *runtime) saveRankSnapshot(m map[string][]SnapshotItem) {
	_ = r.storagePut(storageRankSnapshot, m)
}

// loadSnapshotMeta 读取每个榜单快照的更新时间（仪表盘展示「更新于」）。
func (r *runtime) loadSnapshotMeta() map[string]string {
	var m map[string]string
	if _, err := r.storageGet(storageRankSnapshotMeta, &m); err != nil || m == nil {
		return map[string]string{}
	}
	return m
}

// ---- 仪表盘数据 ----

// HistoryEntry 订阅历史条目（榜单订阅与想看订阅通用）。
type HistoryEntry struct {
	Title        string   `json:"title"`
	Year         string   `json:"year,omitempty"`
	MediaType    string   `json:"media_type"`
	Season       int      `json:"season,omitempty"`
	TMDBID       int      `json:"tmdb_id,omitempty"`
	Poster       string   `json:"poster,omitempty"`
	Link         string   `json:"link,omitempty"`
	Source       string   `json:"source"`              // 榜单名 或 豆瓣想看
	SourceKey    string   `json:"source_key"`          // 榜单 key 或 wish
	Users        []string `json:"users,omitempty"`     // 想看订阅的来源豆瓣用户（多用户）
	SubscribedAt string   `json:"subscribed_at"`       // 订阅时间
	Existing     bool     `json:"existing"`            // true=订阅池已存在（非本插件新增）
	Removed      bool     `json:"removed,omitempty"`   // true=曾被订阅但已在 dian115 删除，不再重复订阅
}

// RankDash 单个榜单的仪表盘视图。
type RankDash struct {
	Key       string         `json:"key"`
	Name      string         `json:"name"`
	MediaType string         `json:"media_type"`
	Enabled   bool           `json:"enabled"`
	FetchedAt string         `json:"fetched_at,omitempty"`
	Items     []SnapshotItem `json:"items"`
}

// DashStats 订阅统计。
type DashStats struct {
	TotalSubscribed int            `json:"total_subscribed"` // 插件累计订阅（不含已存在/已删除）
	MonthNew        int            `json:"month_new"`        // 本月新增
	WishTotal       int            `json:"wish_total"`
	RankTotal       int            `json:"rank_total"`
	PerRank         map[string]int `json:"per_rank"`
	BlacklistHits   int            `json:"blacklist_hits"`
	Observing       int            `json:"observing"`
	RemovedCount    int            `json:"removed_count"` // 已被用户在 dian115 删除、不再重复订阅的条目
}

// actionDashboard 组装仪表盘数据。整体结果需控制在 256 KiB 内。
func (r *runtime) actionDashboard() (any, error) {
	cfg := r.currentConfig()
	snapshot := r.loadRankSnapshot()
	fetchedAt := map[string]string{}
	{
		var meta map[string]string
		if _, err := r.storageGet("rank_snapshot_meta", &meta); err == nil && meta != nil {
			fetchedAt = meta
		}
	}

	ranks := make([]RankDash, 0, len(builtinRanks))
	observeQueue := make([]SnapshotItem, 0)
	blacklistHits := make([]SnapshotItem, 0)
	for _, rd := range builtinRanks {
		_, enabled := cfg.RankConfigs[rd.Key]
		entry := RankDash{
			Key:       rd.Key,
			Name:      rd.Name,
			MediaType: rd.MediaType,
			Enabled:   enabled && cfg.RankConfigs[rd.Key].Enabled,
			FetchedAt: fetchedAt[rd.Key],
			Items:     snapshot[rd.Key],
		}
		if entry.Items == nil {
			entry.Items = []SnapshotItem{}
		}
		ranks = append(ranks, entry)
		for _, it := range entry.Items {
			switch it.Status {
			case "observing":
				observeQueue = append(observeQueue, it)
			case "blacklisted":
				blacklistHits = append(blacklistHits, it)
			}
		}
	}

	// 订阅历史：榜单（合并各榜单历史，按订阅时间倒序）
	rankHist := make([]HistoryEntry, 0)
	rh := r.loadRankHistory()
	rankNames := map[string]string{}
	for _, rd := range builtinRanks {
		rankNames[rd.Key] = rd.Name
	}
	for key, bucket := range rh {
		for _, it := range bucket {
			if !it.Subscribed && !it.Existing && !it.Removed {
				continue
			}
			rankHist = append(rankHist, HistoryEntry{
				Title: it.Title, Year: it.Year, MediaType: it.MediaType, Season: it.Season,
				TMDBID: it.TMDBID, Poster: it.Poster, Link: it.Link,
				Source: rankNames[key], SourceKey: key,
				SubscribedAt: it.SubscribedAt, Existing: it.Existing, Removed: it.Removed,
			})
		}
	}
	sortHistory(rankHist)
	rankTotal := len(rankHist)
	if len(rankHist) > dashHistoryLimit {
		rankHist = rankHist[:dashHistoryLimit]
	}

	// 订阅历史：想看
	wishHist := make([]HistoryEntry, 0)
	wishUsers := make([]DoubanUser, 0)
	wh := r.loadWishHistory()
	// 想看历史条目只存用户 ID，这里带上 ID→昵称映射，界面即可标出用户名
	seenUser := map[string]bool{}
	userCount := map[string]int{} // 每位用户来源的想看订阅条数（完整历史，不受展示截断影响）
	for _, it := range wh {
		if !it.Subscribed && !it.Existing && !it.Removed {
			continue
		}
		wishHist = append(wishHist, HistoryEntry{
			Title: it.Title, Year: it.Year, MediaType: it.MediaType, Season: it.Season,
			TMDBID: it.TMDBID, Poster: it.Poster, Link: it.Link,
			Source: "豆瓣想看", SourceKey: "wish", Users: it.Users,
			SubscribedAt: it.SubscribedAt, Existing: it.Existing, Removed: it.Removed,
		})
		for _, u := range it.Users {
			if u != "" {
				seenUser[u] = true
				userCount[u]++
			}
		}
	}
	// 已配置但历史里还没出现的用户也一并带上，界面可显示「0 条」
	for _, u := range cfg.wishUsers() {
		seenUser[u] = true
	}
	// 按配置顺序优先排列（界面上的用户顺序与设置一致），历史里多出来的用户排在后面
	ids := make([]string, 0, len(seenUser))
	for _, u := range cfg.wishUsers() {
		if seenUser[u] {
			ids = append(ids, u)
			delete(seenUser, u)
		}
	}
	rest := make([]string, 0, len(seenUser))
	for u := range seenUser {
		rest = append(rest, u)
	}
	sort.Strings(rest)
	ids = append(ids, rest...)
	wishUsers = r.wishUserInfos(ids)
	for i := range wishUsers {
		wishUsers[i].Count = userCount[wishUsers[i].ID]
	}
	sortHistory(wishHist)
	wishTotal := len(wishHist)
	if len(wishHist) > dashHistoryLimit {
		wishHist = wishHist[:dashHistoryLimit]
	}

	// 统计
	stats := DashStats{PerRank: map[string]int{}}
	monthPrefix := time.Now().Format("2006-01")
	countMonth := func(list []HistoryEntry) {
		for _, e := range list {
			if e.Existing || e.Removed {
				continue
			}
			stats.TotalSubscribed++
			if strings.HasPrefix(e.SubscribedAt, monthPrefix) {
				stats.MonthNew++
			}
		}
	}
	// 注意：rankHist/wishHist 可能被截断，统计用截断前的总数口径，
	// TotalSubscribed/MonthNew 以完整历史计算，这里重新扫一遍完整集合。
	stats.RankTotal = rankTotal
	stats.WishTotal = wishTotal
	{
		full := make([]HistoryEntry, 0, rankTotal+wishTotal)
		for key, bucket := range rh {
			for _, it := range bucket {
				if !it.Subscribed && !it.Existing && !it.Removed {
					continue
				}
				full = append(full, HistoryEntry{SubscribedAt: it.SubscribedAt, Existing: it.Existing, Removed: it.Removed, SourceKey: key})
			}
		}
		for _, it := range wh {
			if !it.Subscribed && !it.Existing && !it.Removed {
				continue
			}
			full = append(full, HistoryEntry{SubscribedAt: it.SubscribedAt, Existing: it.Existing, Removed: it.Removed, SourceKey: "wish"})
		}
		countMonth(full)
		for _, e := range full {
			if e.Removed {
				stats.RemovedCount++
				continue
			}
			if e.Existing || e.SourceKey == "wish" {
				continue
			}
			stats.PerRank[e.SourceKey]++
		}
	}
	stats.BlacklistHits = len(blacklistHits)
	stats.Observing = len(observeQueue)

	rs := r.loadRunState()
	return map[string]any{
		"status":         "succeeded",
		"generated_at":   nowStr(),
		"ranks":          ranks,
		"rank_history":   rankHist,
		"wish_history":   wishHist,
		"wish_users":     wishUsers,
		"observe_queue":  observeQueue,
		"blacklist_hits": blacklistHits,
		"stats":          stats,
		"run_state":      rs,
		"message":        "ok",
	}, nil
}

func sortHistory(list []HistoryEntry) {
	sort.SliceStable(list, func(i, j int) bool {
		return list[i].SubscribedAt > list[j].SubscribedAt
	})
}

// ---- 订阅历史清理 ----

// actionClearHistory 清空插件的订阅历史（scope = rank / wish / all）。
//
// 历史是插件的「已处理」记录：条目标记为已订阅/已存在后不会被重复处理，
// 用户删掉的订阅会以 removed 记录保留（避免下一轮又被自动订回来）。
// 清空历史等于让插件忘掉这些记录，下一轮会重新评估对应来源的条目。
func (r *runtime) actionClearHistory(raw json.RawMessage) (any, error) {
	var input struct {
		Scope string `json:"scope"`
	}
	if len(raw) > 0 {
		_ = json.Unmarshal(raw, &input)
	}
	scope := strings.ToLower(strings.TrimSpace(input.Scope))
	if scope == "" {
		scope = "all"
	}
	if scope != "rank" && scope != "wish" && scope != "all" {
		return map[string]any{"status": "failed", "message": "scope 只能是 rank / wish / all"}, nil
	}
	cleared := 0
	if scope == "rank" || scope == "all" {
		for _, bucket := range r.loadRankHistory() {
			cleared += len(bucket)
		}
		r.saveRankHistory(map[string][]HistoryItem{})
	}
	if scope == "wish" || scope == "all" {
		cleared += len(r.loadWishHistory())
		r.saveWishHistory(map[string]HistoryItem{})
	}
	msg := fmt.Sprintf("已清空%s订阅历史，共 %d 条记录", clearScopeLabel(scope), cleared)
	r.updateState("succeeded", msg)
	return map[string]any{"status": "succeeded", "message": msg, "cleared": cleared, "scope": scope}, nil
}

func clearScopeLabel(scope string) string {
	switch scope {
	case "rank":
		return "榜单"
	case "wish":
		return "想看"
	default:
		return "全部"
	}
}

// snapshotStatus 文案（供运行日志使用）。
func snapshotStatusText(s string) string {
	switch s {
	case "subscribed":
		return "已订阅"
	case "existing":
		return "已存在"
	case "observing":
		return "观察中"
	case "blacklisted":
		return "黑名单"
	case "filtered":
		return "已过滤"
	case "unresolved":
		return "未识别"
	case "removed":
		return "已删除"
	default:
		return s
	}
}

var _ = fmt.Sprintf // 保留 fmt 引用（后续扩展）
