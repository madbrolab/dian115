package main

import (
	"encoding/json"
	"strings"
)

// RankDef 描述一个内置豆瓣/RSS 榜单。
type RankDef struct {
	Key       string `json:"key"`
	Name      string `json:"name"`
	Route     string `json:"route"`      // RSSHub 相对路由
	MediaType string `json:"media_type"` // movie / tv
	Coming    bool   `json:"coming"`     // 即将上映
}

var builtinRanks = []RankDef{
	{Key: "coming", Name: "即将上映", Route: "/douban/tv/coming", MediaType: "tv", Coming: true},
	{Key: "tv_real_time", Name: "实时热门", Route: "/douban/list/tv_real_time_hotest", MediaType: "tv"},
	{Key: "tv_chinese", Name: "华语口碑", Route: "/douban/list/tv_chinese_best_weekly", MediaType: "tv"},
	{Key: "tv_global", Name: "全球口碑", Route: "/douban/list/tv_global_best_weekly", MediaType: "tv"},
	{Key: "movie_weekly", Name: "电影口碑", Route: "/douban/list/movie_weekly_best", MediaType: "movie"},
	{Key: "bangumi", Name: "BangumiTV", Route: "/bangumi.tv/anime/followrank", MediaType: "tv"},
}

var regionNames = []string{
	"中国大陆", "中国香港", "中国台湾", "美国", "日本", "韩国", "英国", "法国",
	"德国", "泰国", "印度", "俄罗斯", "西班牙", "加拿大", "澳大利亚", "意大利",
	"巴西", "瑞典", "丹麦", "爱尔兰",
}

const (
	defaultRSSHubDomain = "https://rsshub.ddsrem.com"
	defaultRankCron     = "0 8 * * *"
	defaultWishCron     = "0 */6 * * *"
	defaultEmbyCron     = "*/30 * * * *"
	unlimitedRankFetch  = 50
	rankHistoryLimit    = 500
	previewLimit        = 6
	minRankFetch        = 20 // 快照展示需要的最少拉取条数（与每轮订阅条数解耦）
	// rankDisplayLimit 仪表盘榜单快照固定展示的条数（与前端 DashboardPanel 的 TOP_LIMIT 保持一致）。
	// 展示范围内的条目即使超出订阅数量、或命中黑名单，也要做 TMDB 识别，否则界面上没有封面。
	rankDisplayLimit = 5
)

// rankFetchLimit 返回榜单 RSS 拉取条数。
// count 只限制订阅范围（榜单前 N 名），榜单快照要拉取完整榜单（仪表盘展示前 5 项），
// 因此拉取条数取 max(count, minRankFetch)；count<=0 视为不限制（拉 unlimitedRankFetch 条）。
func rankFetchLimit(count int) int {
	if count <= 0 || count > unlimitedRankFetch {
		return unlimitedRankFetch
	}
	if count < minRankFetch {
		return minRankFetch
	}
	return count
}

// RankConfig 单个榜单的自动订阅配置。
type RankConfig struct {
	Enabled bool     `json:"enabled"`
	Count   int      `json:"count"`    // 订阅榜单前 N 名（按榜单位置），0 表示不限制
	MinVote float64  `json:"min_vote"` // 最低 TMDB 评分
	MinYear int      `json:"min_year"` // 最低年份
	Regions []string `json:"regions"`  // 地区筛选，空表示不限
}

// Config 插件持久化配置。
//
// 注意：宿主会递归拒绝业务 result 中包含 "cookie" / "password" 等字样的 key，
// 因此对 UI 输出的字段一律使用不触雷的命名，敏感字段加 omitempty（masked 置空后整个键消失）。
type Config struct {
	DoubanCookie string `json:"douban_cookie,omitempty"`  // 豆瓣登录 Cookie（含 dbcl2），仅存 Host Storage，不下发 UI
	DoubanUserID string `json:"douban_user_id,omitempty"` // 豆瓣用户 ID；支持多个（逗号/换行/分号分隔或主页 URL），想看订阅会逐个读取并合并去重
	RSSHubDomain string `json:"rsshub_domain,omitempty"`

	CloudURL      string `json:"cloud_url,omitempty"`      // CookieCloud 服务器地址
	CloudUUID     string `json:"cloud_uuid,omitempty"`     // CookieCloud UUID
	CloudPasscode string `json:"cloud_passcode,omitempty"` // CookieCloud 密码，仅存不下发

	RankConfigs map[string]RankConfig `json:"rank_configs"`
	Blacklist   string                `json:"blacklist,omitempty"`    // 黑名单关键词，每行一个
	ObserveDays int                   `json:"observe_days,omitempty"` // 观察期天数，0 关闭

	RankCron string `json:"rank_cron,omitempty"` // 榜单同步 Cron（分 时 日 月 周）
	WishCron string `json:"wish_cron,omitempty"` // 想看同步 Cron
	EmbyCron string `json:"emby_cron,omitempty"` // Emby 同步 Cron

	WishEnabled  bool `json:"wish_enabled"`
	WishDays     int  `json:"wish_days"`      // 只看最近 N 天内的想看
	WishMaxPages int  `json:"wish_max_pages"` // 想看列表翻页数

	EmbyEnabled     bool   `json:"emby_enabled"`
	EmbyURL         string `json:"emby_url,omitempty"`
	EmbyAPIKey      string `json:"emby_api_key,omitempty"` // 仅存 Host Storage，不下发 UI
	EmbyUserID      string `json:"emby_user_id,omitempty"` // 空表示自动选择
	EmbyMarkDo      bool   `json:"emby_mark_do"`           // 系列标记「在看」
	EmbyMarkCollect bool   `json:"emby_mark_collect"`      // 电影标记「看过」

	Notify bool `json:"notify"`
}

func defaultConfig() *Config {
	ranks := map[string]RankConfig{}
	for _, r := range builtinRanks {
		ranks[r.Key] = RankConfig{Enabled: false, Count: 3, MinVote: 0, MinYear: 0, Regions: []string{}}
	}
	return &Config{
		RSSHubDomain:    defaultRSSHubDomain,
		RankConfigs:     ranks,
		RankCron:        defaultRankCron,
		WishCron:        defaultWishCron,
		EmbyCron:        defaultEmbyCron,
		ObserveDays:     0,
		WishDays:        7,
		WishMaxPages:    3,
		EmbyMarkDo:      true,
		EmbyMarkCollect: true,
	}
}

// masked 返回用于界面展示的配置副本。敏感字段清空后，配合 omitempty 整个键
// 不会出现在 state JSON 中（宿主会拒绝包含 cookie/password 字样 key 的 result）。
func (c *Config) masked() *Config {
	cp := *c
	cp.DoubanCookie = ""
	cp.EmbyAPIKey = ""
	cp.CloudPasscode = ""
	return &cp
}

// hasCookie 判断是否已配置豆瓣 Cookie。
func (c *Config) hasCookie() bool {
	return strings.TrimSpace(c.DoubanCookie) != ""
}

// rankDef 按 key 查找榜单定义。
func rankDef(key string) *RankDef {
	for i := range builtinRanks {
		if builtinRanks[i].Key == key {
			return &builtinRanks[i]
		}
	}
	return nil
}

// uiRankDefs 返回给 UI 展示的榜单定义副本；route 去掉前导斜杠，
// 避免被宿主按「绝对路径」安全规则拒绝整个 state result。
func uiRankDefs() []RankDef {
	out := make([]RankDef, len(builtinRanks))
	for i, rd := range builtinRanks {
		rd.Route = strings.TrimPrefix(rd.Route, "/")
		out[i] = rd
	}
	return out
}

// normalizeConfig 合并用户配置与默认值。
func normalizeConfig(raw []byte, def *Config) *Config {
	cfg := def
	if cfg == nil {
		cfg = defaultConfig()
	}
	if len(raw) > 0 {
		var user Config
		if err := json.Unmarshal(raw, &user); err == nil {
			merge := map[string]RankConfig{}
			for k, v := range cfg.RankConfigs {
				merge[k] = v
			}
			for k, v := range user.RankConfigs {
				merge[k] = v
			}
			user.RankConfigs = merge
			*cfg = user
		}
	}
	if strings.TrimSpace(cfg.RSSHubDomain) == "" {
		cfg.RSSHubDomain = defaultRSSHubDomain
	}
	if strings.TrimSpace(cfg.RankCron) == "" {
		cfg.RankCron = defaultRankCron
	}
	if strings.TrimSpace(cfg.WishCron) == "" {
		cfg.WishCron = defaultWishCron
	}
	if strings.TrimSpace(cfg.EmbyCron) == "" {
		cfg.EmbyCron = defaultEmbyCron
	}
	if cfg.WishDays <= 0 {
		cfg.WishDays = 7
	}
	if cfg.WishMaxPages <= 0 {
		cfg.WishMaxPages = 3
	}
	if cfg.RankConfigs == nil {
		cfg.RankConfigs = map[string]RankConfig{}
	}
	cfg.CloudURL = normalizeCloudURL(cfg.CloudURL)
	return cfg
}

// normalizeCloudURL 规范化 CookieCloud 地址：去掉尾部斜杠，未写路径时补上
// dian115 内置 CookieCloud 的默认路径（用户常直接填 http://127.0.0.1:3000）。
func normalizeCloudURL(v string) string {
	v = strings.TrimRight(strings.TrimSpace(v), "/")
	if v == "" {
		return v
	}
	if i := strings.Index(v, "://"); i >= 0 && !strings.Contains(v[i+3:], "/") {
		return v + defaultCloudPath
	}
	return v
}
