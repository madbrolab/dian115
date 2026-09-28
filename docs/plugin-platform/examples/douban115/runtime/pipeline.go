package main

import (
	"encoding/json"
	"fmt"
	"net/url"
	"regexp"
	"sort"
	"strings"
	"time"
)

const (
	storageConfig            = "config"
	storageRankHistory       = "rank_history"
	storageWishHistory       = "wish_history"
	storageWishUsers         = "wish_users" // 豆瓣用户 ID -> 昵称/头像（想看订阅来源标记用）
	storageEmbyState         = "emby_state"
	storageRunState          = "run_state"
	storageRankSnapshotMeta  = "rank_snapshot_meta"
	tmdbImageBase            = "https://image.tmdb.org/t/p/w500"
)

// HistoryItem 榜单/想看订阅历史（持久化）。
type HistoryItem struct {
	Unique       string   `json:"unique"`
	Title        string   `json:"title"`
	Year         string   `json:"year"`
	TMDBID       int      `json:"tmdb_id"`
	MediaType    string   `json:"media_type"`
	Season       int      `json:"season"`
	Poster       string   `json:"poster"`
	Link         string   `json:"link"`
	Subscribed   bool     `json:"subscribed"`
	Existing     bool     `json:"existing"`
	Removed      bool     `json:"removed"`         // 曾订阅但已被用户在 dian115 删除：不重复订阅，直到清空历史
	Users        []string `json:"users,omitempty"` // 想看订阅的来源豆瓣用户（多用户合并）
	// ResolveVer 记录 TMDBID/Poster 是由哪一版识别策略得到的。识别策略升级后该值
	// 落后于 tmdbCacheVersion，条目会被重新识别一次，避免旧策略的错配长期沿用。
	ResolveVer   int      `json:"resolve_ver,omitempty"`
	FirstSeen    string   `json:"first_seen"`
	LastSeen     string   `json:"last_seen"`
	SubscribedAt string   `json:"subscribed_at"`
}

// RunState 运行统计。
type RunState struct {
	LastRankRun     string `json:"last_rank_run"`
	LastWishRun     string `json:"last_wish_run"`
	LastEmbyRun     string `json:"last_emby_run"`
	SubscribedTotal int    `json:"subscribed_total"`
	// 常驻调度防重入：记录每个任务最近一次触发的分钟（本地时区）。
	LastRankCronMin string `json:"last_rank_cron_min,omitempty"`
	LastWishCronMin string `json:"last_wish_cron_min,omitempty"`
	LastEmbyCronMin string `json:"last_emby_cron_min,omitempty"`
}

// EmbyState Emby → 豆瓣 同步状态。
type EmbyState struct {
	LastSyncAt string            `json:"last_sync_at"`
	Synced     map[string]string `json:"synced"` // emby 条目 id -> 豆瓣 subject id
}

func tmdbPoster(path string) string {
	if path == "" {
		return ""
	}
	if strings.HasPrefix(path, "http") {
		return path
	}
	return tmdbImageBase + path
}

func stripYearSuffix(s string) string {
	re := regexp.MustCompile(`\s*[（(]?\s*(?:19|20)\d{2}\s*[）)]?\s*$`)
	return strings.TrimSpace(re.ReplaceAllString(s, ""))
}

func nowStr() string {
	return time.Now().Format("2006-01-02 15:04:05")
}

// ---- 识别：标题 → TMDB ----

// TMDB 的中文搜索是模糊匹配而非精确匹配：搜「流人」会把与《流人》毫无关系的
// 《潮流合伙人》《千古风流人物》排在第一页。旧实现只要媒体类型对得上就把得分最高的
// 结果当作答案，于是出现了封面张冠李戴（《流人 第六季》配成《潮流合伙人》）。
// 这里给名称相关性设定分档与最低接受阈值：宁可判为未识别（不显示封面），也不错配。
const (
	tmdbNameExact    = 100  // 归一化后与候选名完全相同
	tmdbNamePrefix   = 65   // 短串（≥2 字）是候选名的前缀
	tmdbNameContains = 60   // 短串（≥3 字）是候选名的连续子串
	tmdbNameFuzzy    = 50   // 字符二元组 Dice 相似度 ≥ tmdbFuzzyMin
	tmdbYearBonus    = 15   // 年份吻合的加分
	tmdbHotCap       = 25   // 热度分上限：热门度只用于同等相关时排序，绝不能盖过名称相关性
	tmdbMinAccept    = 50   // 低于该分数视为不相关，直接判为未识别
	tmdbFuzzyMin     = 0.6  // 模糊匹配的 Dice 阈值
)

// tmdbHot 把投票数折算成受上限约束的热度分。
// 旧实现直接把 vote_count/500 累加，一部高票老片能凭热度压过标题完全吻合的新片
// （《罗斯》因此被配成了票数极高的《普罗米修斯》）。
func tmdbHot(voteCount int) int {
	if voteCount < 0 {
		return 0
	}
	if n := voteCount / 500; n < tmdbHotCap {
		return n
	}
	return tmdbHotCap
}

// titleBigrams 取归一化字符串的连续二元字符集合（不足 2 字返回 nil）。
// 中文/日文没有词边界，二元组是比字符集合更可靠的相似度基础。
func titleBigrams(s string) map[string]bool {
	r := []rune(s)
	if len(r) < 2 {
		return nil
	}
	out := make(map[string]bool, len(r)-1)
	for i := 0; i+1 < len(r); i++ {
		out[string(r[i:i+2])] = true
	}
	return out
}

// diceCoefficient 计算两个字符串的二元组 Dice 相似度（0~1）。
// 用于「标题略有差异」的场景，例如 BangumiTV 的「無職転生Ⅲ ～異世界行ったら本気だす～」
// 与 TMDB 原名的差别只有一个罗马数字季号。
func diceCoefficient(a, b string) float64 {
	ga, gb := titleBigrams(a), titleBigrams(b)
	if len(ga) == 0 || len(gb) == 0 {
		return 0
	}
	inter := 0
	for g := range ga {
		if gb[g] {
			inter++
		}
	}
	return 2 * float64(inter) / float64(len(ga)+len(gb))
}

// titleNameScore 计算已归一化的目标标题与候选名的相关性分。
func titleNameScore(target, cand string) int {
	if target == "" || cand == "" {
		return 0
	}
	if target == cand {
		return tmdbNameExact
	}
	short, long := target, cand
	if len([]rune(short)) > len([]rune(long)) {
		short, long = long, short
	}
	n := len([]rune(short))
	// 中文里两个字恰好相邻出现在无关标题中的概率很高（「流人」vs「千古风
	// 流人 物」），所以短串必须至少 3 个字才允许按「包含」判定。
	if n >= 2 && strings.HasPrefix(long, short) {
		return tmdbNamePrefix
	}
	if n >= 3 && strings.Contains(long, short) {
		return tmdbNameContains
	}
	if diceCoefficient(target, cand) >= tmdbFuzzyMin {
		return tmdbNameFuzzy
	}
	return 0
}

// tmdbNameScore 取候选条目的本地化名与原名中相关性最高的一个。
func tmdbNameScore(target string, it *tmdbItem) int {
	if target == "" {
		return 0
	}
	best := 0
	for _, nm := range [4]string{it.Title, it.Name, it.OriginalTitle, it.OriginalName} {
		if nm == "" {
			continue
		}
		if s := titleNameScore(target, normalizeTitle(nm)); s > best {
			best = s
		}
	}
	return best
}

func pickBestTMDB(items []tmdbItem, title, year, mediaType string) *tmdbItem {
	targetKey := normalizeTitle(stripYearSuffix(title))
	var best *tmdbItem
	bestScore := -1
	for i := range items {
		it := &items[i]
		if it.MediaType == "person" {
			continue
		}
		if mediaType != "" && it.MediaType != mediaType {
			continue
		}
		score := tmdbNameScore(targetKey, it)
		date := it.ReleaseDate
		if date == "" {
			date = it.FirstAirDate
		}
		if year != "" && strings.HasPrefix(date, year) {
			score += tmdbYearBonus
		}
		score += tmdbHot(it.VoteCount)
		if score > bestScore {
			best = it
			bestScore = score
		}
	}
	if best == nil || bestScore < tmdbMinAccept {
		return nil
	}
	return best
}

const (
	storageTMDBCache = "tmdb_cache"
	tmdbCacheMax     = 800
	// tmdbCacheVersion 识别策略版本号，递增后旧缓存（含此前失败的「未识别」记录）作废，
	// 条目会按新策略重新识别一次。
	// v2 = 引入标题变体回退 titleCandidates（修复 BangumiTV 长标题识别失败）。
	// v3 = 打分加入名称相关性阈值与原名比对（修复《流人 第六季》→《潮流合伙人》
	//      《罗斯》→《普罗米修斯》这类张冠李戴的错配）。
	// v4 = 标题完全搜不到时回落到豆瓣条目的原名/又名再搜一轮（TMDB 没有中文标题的
	//      条目只能靠原名命中，如《流人 第六季》→ Slow Horses Season 6）。
	tmdbCacheVersion = 4
)

// tmdbCacheFile TMDB 缓存的落盘结构。带版本号：识别策略升级后旧结果不再复用，
// 否则「改进了识别逻辑但旧条目仍记录为未识别」会让修复对存量用户不生效。
// 旧版本写入的是裸 map，反序列化到本结构时 Version 为 0，同样会被视为过期。
type tmdbCacheFile struct {
	Version int                  `json:"version"`
	Items   map[string]*tmdbItem `json:"items"`
}

func (r *runtime) loadTMDBCache() map[string]*tmdbItem {
	var f tmdbCacheFile
	if ok, err := r.storageGet(storageTMDBCache, &f); err != nil || !ok || f.Version != tmdbCacheVersion || f.Items == nil {
		return map[string]*tmdbItem{}
	}
	return f.Items
}

func (r *runtime) saveTMDBCache(cache map[string]*tmdbItem) {
	if cache == nil {
		cache = map[string]*tmdbItem{}
	}
	_ = r.storagePut(storageTMDBCache, tmdbCacheFile{Version: tmdbCacheVersion, Items: cache})
}

// resolveTMDB 带本地缓存：榜单条目跨轮重复出现，且拉取条数大于订阅数，
// 缓存可避免每轮对相同条目重复发起识别（未识别结果同样缓存，防止反复空搜）。
// 缓存未命中时的识别顺序：本地 TMDB 搜索（含标题变体）→ 豆瓣原名/又名兜底。
// 含季号的剧名（如「信号 第二季」）用剥离季号后的基础剧名做搜索词，
// 同一部剧的各季共享一份搜索结果；季号由 extractSeason 单独提取用于订阅。
func (r *runtime) resolveTMDB(title, year, mediaType string) (*tmdbItem, error) {
	searchTitle := tmdbSearchTitle(title, mediaType)
	key := tmdbCacheKey(searchTitle, year, mediaType)
	cache := r.loadTMDBCache()
	if hit, exists := cache[key]; exists {
		if hit == nil {
			// 便于排查「明明改进了识别逻辑却仍无封面」：说明命中的是历史遗留的未识别结果。
			r.log("info", "TMDB 缓存命中（未识别）", map[string]any{"title": title})
		}
		return hit, nil
	}
	best, err := r.resolveTMDBRaw(searchTitle, year, mediaType)
	if err != nil {
		return nil, err
	}
	if len(cache) >= tmdbCacheMax {
		cache = map[string]*tmdbItem{} // 简单限容：超限整体重建，下次重新识别
	}
	cache[key] = best
	r.saveTMDBCache(cache)
	return best, nil
}

// tmdbSearchTitle 实际拿去搜索的词：剧集剥掉季号（「信号 第二季」用「信号」搜），
// 同一部剧的各季共享一份搜索结果。
func tmdbSearchTitle(title, mediaType string) string {
	t := strings.TrimSpace(title)
	if mediaType == "tv" {
		if base := stripSeasonSuffix(stripYearSuffix(t)); base != "" {
			return base
		}
	}
	return t
}

// tmdbCacheKey 缓存键带识别策略版本前缀：即使宿主持久化的旧缓存被完整读出，
// 旧键（无版本前缀）也永远不会命中，条目必然按新策略重新识别一次。
func tmdbCacheKey(searchTitle, year, mediaType string) string {
	return fmt.Sprintf("v%d:%s:%s:%s", tmdbCacheVersion, mediaType, normalizeTitle(searchTitle), year)
}

// rememberTMDBResult 把兜底识别到的结果也记到「榜单标题」对应的缓存键上。
// 否则标题键会一直留着「未识别」的旧结论，每轮同步都要再走一遍兜底
// （多读一次豆瓣原名缓存）。写入后下一轮直接命中。
func (r *runtime) rememberTMDBResult(title, year, mediaType string, mi *tmdbItem) {
	if mi == nil {
		return
	}
	key := tmdbCacheKey(tmdbSearchTitle(title, mediaType), year, mediaType)
	cache := r.loadTMDBCache()
	if hit, exists := cache[key]; exists && hit != nil {
		return
	}
	if len(cache) >= tmdbCacheMax {
		cache = map[string]*tmdbItem{}
	}
	cache[key] = mi
	r.saveTMDBCache(cache)
}

// resolveTMDBWithAlias 先按标题识别；识别不出来、且知道豆瓣条目 ID 时，
// 再取豆瓣条目的原名/又名重试一轮。
//
// 为什么必须有这条兜底：有些条目 TMDB 压根没有中文标题（《流人 第六季》在 TMDB
// 只有英文名 Slow Horses），拿豆瓣译名去搜 TMDB 永远搜不到——搜「流人」返回的
// 全是只共享单个汉字的无关条目，识别逻辑为保证不张冠李戴会把它们全部拒收，
// 结果是「TMDB 未匹配」。豆瓣条目自己存着原名（Slow Horses Season 6）与又名列表，
// 用它重搜即可命中。
//
// 代价是受控的：只在标题彻底失败时才多一次豆瓣请求；重搜 TMDB 的结果会连同
// 「榜单标题键」一起写进 tmdb_cache（rememberTMDBResult），因此同一部剧
// 下一轮同步直接命中缓存，不会再读豆瓣原名缓存。
func (r *runtime) resolveTMDBWithAlias(title, year, mediaType, subjectID string) (*tmdbItem, error) {
	mi, err := r.resolveTMDB(title, year, mediaType)
	if mi != nil || strings.TrimSpace(subjectID) == "" {
		return mi, err
	}
	for _, q := range aliasQueries(title, mediaType, r.doubanSubjectAliasFor(subjectID, mediaType)) {
		hit, herr := r.resolveTMDB(q, year, mediaType)
		if herr == nil && hit != nil {
			r.log("info", "TMDB 靠豆瓣原名/又名命中", map[string]any{
				"title": title, "query": q, "tmdb": hit.ID, "subject": subjectID,
			})
			r.rememberTMDBResult(title, year, mediaType, hit)
			return hit, nil
		}
	}
	return nil, err
}

// resolveTMDBRaw 依次尝试「原标题 → 标题变体」搜索 TMDB，返回第一个能匹配到的结果。
// 变体回退用于长标题（「主标题 + 副标题 + 季号/篇章名」拼接）在 TMDB 搜不到的情况，
// 榜单里这类标题不少（尤其 BangumiTV 的日文原名）。
func (r *runtime) resolveTMDBRaw(title, year, mediaType string) (*tmdbItem, error) {
	title = strings.TrimSpace(title)
	if title == "" {
		return nil, nil
	}
	base := stripYearSuffix(title)
	if base == "" {
		base = title
	}
	queries := make([]string, 0, 12)
	queries = append(queries, base)
	if base != title {
		queries = append(queries, title)
	}
	queries = append(queries, titleCandidates(base)...)

	var firstErr error
	for i, q := range queries {
		result, err := r.tmdbSearch(q, 1)
		if err != nil {
			if i == 0 {
				firstErr = err
			}
			continue
		}
		if result == nil || len(result.Results) == 0 {
			continue
		}
		if best := pickBestTMDB(result.Results, q, year, mediaType); best != nil {
			if i > 0 {
				r.log("info", "TMDB 变体命中", map[string]any{"title": title, "query": q, "tmdb": best.ID, "tries": i + 1})
			}
			return best, nil
		}
	}
	if len(queries) > 1 {
		r.log("info", "TMDB 未识别", map[string]any{"title": title, "tries": len(queries)})
	}
	return nil, firstErr
}

// ---- 识别：TMDB / 标题 → 豆瓣 ----

func (r *runtime) resolveDouban(title, year string) (string, string) {
	base := strings.TrimSpace(stripYearSuffix(title))
	if base == "" {
		return "", ""
	}
	var queries []string
	if year != "" {
		queries = append(queries, base+" "+year)
	}
	queries = append(queries, base)
	for _, q := range queries {
		name, sid, err := r.searchSubject(q)
		if err == nil && sid != "" {
			return name, sid
		}
	}
	return "", ""
}

// ---- 榜单订阅 ----

func tmdbIDOf(mi *tmdbItem) int {
	if mi == nil {
		return 0
	}
	return mi.ID
}

// appendSnap 追加快照条目并限制长度。
func appendSnap(snap []SnapshotItem, entry SnapshotItem) []SnapshotItem {
	if len(snap) >= snapshotItemLimit {
		return snap
	}
	return append(snap, entry)
}

func newHistoryItem(unique string, it rankItem, mi *tmdbItem, season int, existing, subscribed bool) HistoryItem {
	return HistoryItem{
		Unique:     unique,
		Title:      it.Title,
		Year:       it.Year,
		TMDBID:     mi.ID,
		MediaType:  it.MediaType,
		Season:     season,
		Poster:     tmdbPoster(mi.PosterPath),
		Link:       it.Link,
		Existing:   existing,
		Subscribed: subscribed,
		ResolveVer: tmdbCacheVersion,
		FirstSeen:  nowStr(),
		LastSeen:   nowStr(),
	}
}

// ---- 想看订阅 ----

// runWishSync 支持多用户：配置里可填多个豆瓣用户 ID（逗号/换行/分号等分隔，
// 也支持粘贴个人主页 URL），逐个抓取想看列表后合并去重，同一部片只订阅一次，
// 历史里用 Users 记录来源用户；单个用户失败不影响其余用户。
// 抓取时顺带解析每个用户的昵称/头像并缓存，供界面把用户 ID 展示成用户名。
type embyUser struct {
	ID   string `json:"Id"`
	Name string `json:"Name"`
}

type embyItem struct {
	ID                string            `json:"Id"`
	Name              string            `json:"Name"`
	Type              string            `json:"Type"`
	ProductionYear    int               `json:"ProductionYear"`
	ProviderIDs       map[string]string `json:"ProviderIds"`
	SeriesName        string            `json:"SeriesName"`
	SeriesID          string            `json:"SeriesId"`
	ParentIndexNumber int               `json:"ParentIndexNumber"`
	IndexNumber       int               `json:"IndexNumber"`
	DatePlayed        string            `json:"DatePlayed"`
	UserData          struct {
		Played bool `json:"Played"`
	} `json:"UserData"`
}

type embyListResult struct {
	Items            []embyItem `json:"Items"`
	TotalRecordCount int        `json:"TotalRecordCount"`
}

func (r *runtime) embyRequest(path string, query url.Values, target any) error {
	cfg := r.currentConfig()
	base := strings.TrimRight(strings.TrimSpace(cfg.EmbyURL), "/")
	if base == "" {
		return &doubanError{Msg: "未配置 Emby 地址"}
	}
	query.Set("api_key", cfg.EmbyAPIKey)
	rawURL := base + "/emby" + path + "?" + query.Encode()
	status, body, err := r.httpGet(rawURL, map[string]string{"accept": "application/json", "user-agent": doubanUA})
	if err != nil {
		return err
	}
	if status != 200 {
		return &httpError{Status: status, Body: string(body)}
	}
	return json.Unmarshal(body, target)
}

func (r *runtime) embyUsers() ([]embyUser, error) {
	var out []embyUser
	if err := r.embyRequest("/Users", url.Values{}, &out); err != nil {
		return nil, err
	}
	return out, nil
}

func (r *runtime) embyPlayed(uid string) (movies []embyItem, episodes []embyItem, err error) {
	var mRes embyListResult
	q := url.Values{}
	q.Set("Recursive", "true")
	q.Set("IncludeItemTypes", "Movie")
	q.Set("IsPlayed", "true")
	q.Set("SortBy", "DatePlayed")
	q.Set("SortOrder", "Descending")
	q.Set("Limit", "100")
	q.Set("Fields", "ProviderIds,DatePlayed,ProductionYear")
	if err := r.embyRequest("/Users/"+uid+"/Items", q, &mRes); err != nil {
		return nil, nil, err
	}
	movies = mRes.Items

	var eRes embyListResult
	q2 := url.Values{}
	q2.Set("Recursive", "true")
	q2.Set("IncludeItemTypes", "Episode")
	q2.Set("IsPlayed", "true")
	q2.Set("SortBy", "DatePlayed")
	q2.Set("SortOrder", "Descending")
	q2.Set("Limit", "200")
	q2.Set("Fields", "ProviderIds,DatePlayed,SeriesName,SeriesId,ParentIndexNumber,IndexNumber")
	if err := r.embyRequest("/Users/"+uid+"/Items", q2, &eRes); err != nil {
		return nil, nil, err
	}
	episodes = eRes.Items
	return movies, episodes, nil
}

func (r *runtime) embySeries(uid, seriesID string) (*embyItem, error) {
	q := url.Values{}
	q.Set("Fields", "ProviderIds,Name,ProductionYear,UserData")
	var item embyItem
	if err := r.embyRequest("/Users/"+uid+"/Items/"+seriesID, q, &item); err != nil {
		return nil, err
	}
	return &item, nil
}

func (r *runtime) syncEmbyMovie(u embyUser, mv embyItem, state EmbyState) bool {
	title := mv.Name
	year := itoaSafe(mv.ProductionYear)
	if tmdbID := atoiSafe(mv.ProviderIDs["Tmdb"]); tmdbID > 0 {
		if d, err := r.tmdbMovie(tmdbID); err == nil && d != nil {
			if d.Title != "" {
				title = d.Title
			}
			if d.ReleaseDate != "" {
				year = extractYear(d.ReleaseDate)
			}
		}
	}
	name, sid := r.resolveDouban(title, year)
	if sid == "" {
		return false
	}
	if err := r.markWatched(sid, "collect"); err != nil {
		r.log("warning", "豆瓣标记看过失败", map[string]any{"title": name, "reason": err.Error()})
		return false
	}
	return true
}

func (r *runtime) syncEmbySeries(u embyUser, series *embyItem, status string, state EmbyState) bool {
	title := series.Name
	year := itoaSafe(series.ProductionYear)
	if tmdbID := atoiSafe(series.ProviderIDs["Tmdb"]); tmdbID > 0 {
		if d, err := r.tmdbTV(tmdbID); err == nil && d != nil {
			if d.Name != "" {
				title = d.Name
			}
			if d.FirstAirDate != "" {
				year = extractYear(d.FirstAirDate)
			}
		}
	}
	name, sid := r.resolveDouban(title, year)
	if sid == "" {
		return false
	}
	if err := r.markWatched(sid, status); err != nil {
		r.log("warning", "豆瓣标记观看状态失败", map[string]any{"title": name, "reason": err.Error()})
		return false
	}
	return true
}

// ---- 工具 ----

func findHistory(bucket []HistoryItem, unique string) int {
	for i := range bucket {
		if bucket[i].Unique == unique {
			return i
		}
	}
	return -1
}

// intentKey 生成订阅去重键（与 listIntents 的键格式保持一致）。
func intentKey(tmdbID, season int, mediaType string) string {
	if mediaType == "tv" {
		return fmt.Sprintf("%d-S%d", tmdbID, season)
	}
	return fmt.Sprintf("%d", tmdbID)
}

// intentPresent 查询订阅池快照中是否已有该条目。
// 走两套 map 是为了兼容历史上把剧集 season 记成 0、而订阅池按 S1 去重的情况。
func intentPresent(movie, tv map[string]bool, mediaType string, tmdbID, season int) bool {
	if tmdbID <= 0 {
		return false
	}
	if mediaType == "tv" {
		if tv[intentKey(tmdbID, season, "tv")] {
			return true
		}
		// 历史记录里 season 缺失（0）时，回退到主 season 判定。
		return season <= 0 && tv[intentKey(tmdbID, 1, "tv")]
	}
	return movie[intentKey(tmdbID, 0, "movie")]
}

// rememberIntent 把刚创建的订阅写入订阅池快照，供同一轮后续榜单去重。
func rememberIntent(movie, tv map[string]bool, mediaType string, tmdbID, season int) {
	if tmdbID <= 0 {
		return
	}
	if mediaType == "tv" {
		if tv != nil {
			tv[intentKey(tmdbID, season, "tv")] = true
		}
		return
	}
	if movie != nil {
		movie[intentKey(tmdbID, 0, "movie")] = true
	}
}

// firstErr 返回第一个非 nil 的错误。
func firstErr(errs ...error) error {
	for _, err := range errs {
		if err != nil {
			return err
		}
	}
	return nil
}

func regionMatch(selected, actual []string) bool {
	if len(selected) == 0 {
		return true
	}
	set := map[string]bool{}
	for _, a := range actual {
		set[strings.ToLower(a)] = true
	}
	for _, s := range selected {
		if set[strings.ToLower(s)] {
			return true
		}
	}
	return false
}

func daysSince(t string) int {
	if t == "" {
		return 0
	}
	parsed, err := time.Parse("2006-01-02 15:04:05", t)
	if err != nil {
		return 0
	}
	return int(time.Since(parsed).Hours() / 24)
}

func parseCNTime(t string) (time.Time, error) {
	formats := []string{"2006-01-02", "2006-01-02 15:04:05", "2006年1月2日", "2006-01-02 15:04"}
	for _, f := range formats {
		if v, err := time.Parse(f, t); err == nil {
			return v, nil
		}
	}
	return time.Time{}, fmt.Errorf("无法解析时间 %s", t)
}

// ---- 历史读写 ----

func (r *runtime) loadRankHistory() map[string][]HistoryItem {
	var m map[string][]HistoryItem
	if _, err := r.storageGet(storageRankHistory, &m); err != nil || m == nil {
		return map[string][]HistoryItem{}
	}
	return m
}

func (r *runtime) saveRankHistory(m map[string][]HistoryItem) {
	_ = r.storagePut(storageRankHistory, m)
}

func (r *runtime) loadWishHistory() map[string]HistoryItem {
	var m map[string]HistoryItem
	if _, err := r.storageGet(storageWishHistory, &m); err != nil || m == nil {
		return map[string]HistoryItem{}
	}
	return m
}

func (r *runtime) saveWishHistory(m map[string]HistoryItem) {
	_ = r.storagePut(storageWishHistory, m)
}

func (r *runtime) loadEmbyState() EmbyState {
	var s EmbyState
	if _, err := r.storageGet(storageEmbyState, &s); err != nil {
		return EmbyState{}
	}
	return s
}

func (r *runtime) saveEmbyState(s EmbyState) {
	_ = r.storagePut(storageEmbyState, s)
}

func (r *runtime) loadRunState() RunState {
	var s RunState
	if _, err := r.storageGet(storageRunState, &s); err != nil {
		return RunState{}
	}
	return s
}

func (r *runtime) markRun(kind string) {
	s := r.loadRunState()
	now := nowStr()
	switch kind {
	case "rank":
		s.LastRankRun = now
	case "wish":
		s.LastWishRun = now
	case "emby":
		s.LastEmbyRun = now
	}
	_ = r.storagePut(storageRunState, s)
}

func (r *runtime) recordSubscribed() {
	s := r.loadRunState()
	s.SubscribedTotal++
	_ = r.storagePut(storageRunState, s)
}

// sortedRankKeys 返回按内置顺序的榜单 key。
func sortedRankKeys() []string {
	keys := make([]string, 0, len(builtinRanks))
	for _, rd := range builtinRanks {
		keys = append(keys, rd.Key)
	}
	sort.Strings(keys)
	return keys
}
