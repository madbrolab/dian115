package main

import (
	"fmt"
	"net/url"
	"regexp"
	"strings"
)

const (
	doubanUA       = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
	doubanHome     = "https://www.douban.com/"
	doubanMovie    = "https://movie.douban.com"
	doubanSearch   = "https://www.douban.com/search?cat=1002&q="
	doubanWish     = "https://movie.douban.com/people/"
	doubanInterest = "https://movie.douban.com/j/subject/"
)

var (
	ckRe     = regexp.MustCompile(`name="ck"\s+value="([^"]+)"`)
	ckJSONRe = regexp.MustCompile(`"ck"\s*:\s*"([^"]+)"`)
	anchorRe = regexp.MustCompile(`(?s)<a[^>]*href="[^"]*subject/(\d+)/[^"]*"[^>]*>(.*?)</a>`)
	imgRe    = regexp.MustCompile(`<img[^>]+src="([^"]+)"`)
	emRe     = regexp.MustCompile(`<em>([^<]{1,120})</em>`)
	dateRe   = regexp.MustCompile(`<span[^>]*class="[^"]*date[^"]*"[^>]*>([^<]+)</span>`)
	dbcl2Re  = regexp.MustCompile(`dbcl2="?([0-9]+):`)

	// 个人主页信息块（movie.douban.com 各「我的影视」页共用）
	usrProfileID = `id="db-usr-profile"`
	imgAltRe     = regexp.MustCompile(`<img[^>]*\salt="([^"]*)"`)
	h1Re         = regexp.MustCompile(`(?s)<h1>\s*(.*?)\s*</h1>`)
	// 形如「影迷甲想看的影视(11)」「某某的想看」，从右侧剥掉，剩下昵称
	wishTitleTailRe = regexp.MustCompile(`(?s)\s*的?\s*想看(?:的)?(?:影视|电影|电视剧|剧集|综艺|条目|作品|影音|书影音|音乐|书籍|图书|游戏|舞台剧|广播剧|动画)?\s*(?:[（(]\s*\d+\s*[）)])?\s*$`)
)

// DoubanUser 豆瓣用户展示信息：昵称 / 头像（Count 为该用户来源的想看订阅条数，仅仪表盘用）。
// 仅用于在「想看订阅」历史里标出条目的来源用户，除此之外不参与业务逻辑。
type DoubanUser struct {
	ID     string `json:"id"`
	Name   string `json:"name,omitempty"`
	Avatar string `json:"avatar,omitempty"`
	Count  int    `json:"count,omitempty"`
}

// htmlUnescape 还原昵称里常见的 HTML 实体（不引入 html 包，避免 WASM 体积膨胀）。
var htmlEntities = strings.NewReplacer(
	"&amp;", "&", "&lt;", "<", "&gt;", ">", "&quot;", `"`,
	"&#39;", "'", "&apos;", "'", "&nbsp;", " ",
)

func htmlUnescape(s string) string {
	if !strings.Contains(s, "&") {
		return s
	}
	return htmlEntities.Replace(s)
}

// stripWishTitleSuffix 从「影迷甲想看的影视(11)」这类标题里剥出昵称。
// 匹配不到后缀时返回空串，交由调用方尝试其它来源。
func stripWishTitleSuffix(s string) string {
	s = strings.TrimSpace(s)
	loc := wishTitleTailRe.FindStringIndex(s)
	if loc == nil || loc[0] <= 0 {
		return ""
	}
	return strings.TrimSpace(s[:loc[0]])
}

// parseDoubanUserProfile 从「想看」页 HTML 解析用户昵称与头像。
// 首选个人资料块里的头像 alt（就是昵称原文，无需裁剪），
// 回退到 h1「XX想看的影视(N)」再剥掉后缀；都取不到时返回空串。
func parseDoubanUserProfile(html string) (name, avatar string) {
	if i := strings.Index(html, usrProfileID); i >= 0 {
		end := i + 1200
		if end > len(html) {
			end = len(html)
		}
		window := html[i:end]
		if m := imgAltRe.FindStringSubmatch(window); len(m) > 1 {
			name = strings.TrimSpace(htmlUnescape(m[1]))
		}
		if m := imgRe.FindStringSubmatch(window); len(m) > 1 {
			avatar = strings.TrimSpace(m[1])
			if strings.HasPrefix(avatar, "//") {
				avatar = "https:" + avatar
			}
		}
	}
	if name == "" {
		if m := h1Re.FindStringSubmatch(html); len(m) > 1 {
			name = stripWishTitleSuffix(htmlUnescape(stripTags(m[1])))
		}
	}
	// 登录自己主页时豆瓣会显示「我的想看」，此时昵称不适用，宁可不显示
	if name == "我" {
		name = ""
	}
	return name, avatar
}

// ---- 用户昵称缓存 ----
//
// 昵称只在抓取想看列表时随页面一起拿到，因此缓存到 Host Storage，
// 供仪表盘在展示历史条目时把用户 ID 映射成昵称（历史条目只存 ID）。

func (r *runtime) loadWishUsers() map[string]DoubanUser {
	var m map[string]DoubanUser
	if _, err := r.storageGet(storageWishUsers, &m); err != nil || m == nil {
		return map[string]DoubanUser{}
	}
	return m
}

func (r *runtime) saveWishUsers(m map[string]DoubanUser) {
	_ = r.storagePut(storageWishUsers, m)
}

// mergeWishUsers 合并新抓取到的用户信息与缓存（新值优先，空昵称回退缓存）。
func mergeWishUsers(cached map[string]DoubanUser, fresh []DoubanUser) map[string]DoubanUser {
	out := map[string]DoubanUser{}
	for k, v := range cached {
		out[k] = v
	}
	for _, u := range fresh {
		if u.ID == "" {
			continue
		}
		prev := out[u.ID]
		if u.Name == "" {
			u.Name = prev.Name
		}
		if u.Avatar == "" {
			u.Avatar = prev.Avatar
		}
		out[u.ID] = u
	}
	return out
}

// wishUserInfos 按给定顺序返回用户展示信息（昵称缺失时只保留 ID）。
func (r *runtime) wishUserInfos(ids []string) []DoubanUser {
	cache := r.loadWishUsers()
	out := make([]DoubanUser, 0, len(ids))
	for _, id := range ids {
		if id == "" {
			continue
		}
		u, ok := cache[id]
		if !ok {
			u = DoubanUser{ID: id}
		}
		if u.ID == "" {
			u.ID = id
		}
		out = append(out, u)
	}
	return out
}

// userDisplay 返回「昵称（ID）」形式的展示文案，昵称未知时退化为 ID。
func userDisplay(u DoubanUser) string {
	if u.Name == "" {
		return u.ID
	}
	return u.Name + "（" + u.ID + "）"
}

// wishUserNames 把本次同步的用户渲染成一行文案（优先昵称，缺失时用 ID）。
// infos 为空（全部用户抓取失败）时退回配置里的用户 ID 列表。
func wishUserNames(infos []DoubanUser, configured []string) string {
	if len(infos) == 0 {
		return strings.Join(configured, "、")
	}
	parts := make([]string, 0, len(infos))
	for _, u := range infos {
		if u.Name != "" {
			parts = append(parts, u.Name)
			continue
		}
		parts = append(parts, u.ID)
	}
	return strings.Join(parts, "、")
}

// wishUsersLabel 把一组用户 ID 渲染成「昵称（ID）」文案，用于订阅日志。
func wishUsersLabel(cache map[string]DoubanUser, ids []string) string {
	parts := make([]string, 0, len(ids))
	for _, id := range ids {
		if u, ok := cache[id]; ok {
			parts = append(parts, userDisplay(u))
			continue
		}
		parts = append(parts, id)
	}
	return strings.Join(parts, "、")
}

// doubanCookieHeader 把配置中的 Cookie 串转换为请求 header。
func (c *Config) doubanCookieHeader() string {
	return strings.TrimSpace(c.DoubanCookie)
}

// cookieUserID 从 dbcl2 Cookie 解析豆瓣用户 ID。
func (c *Config) cookieUserID() string {
	m := dbcl2Re.FindStringSubmatch(c.DoubanCookie)
	if len(m) > 1 {
		return m[1]
	}
	return strings.TrimSpace(c.DoubanUserID)
}

// doubanPeopleRe 匹配个人主页 URL 中的 ID（https://www.douban.com/people/<id>/）。
var doubanPeopleRe = regexp.MustCompile(`people/([A-Za-z0-9_-]+)`)

// doubanIDRe 判定一个 token 是否像豆瓣用户 ID（字母/数字/下划线/连字符）。
var doubanIDRe = regexp.MustCompile(`^[A-Za-z0-9_-]+$`)

// doubanIDNoise 是拆分 URL 时可能产生的非 ID 片段。
var doubanIDNoise = map[string]bool{
	"http": true, "https": true, "www": true, "com": true, "cn": true,
	"movie": true, "people": true, "douban": true, "subject": true, "wish": true,
}

// ParseDoubanUserIDs 解析配置中的豆瓣用户 ID 列表，支持多个用户：
// 逗号（中英文）、顿号、分号、竖线、空白与换行分隔；也支持直接粘贴个人主页 URL
// （自动取出 /people/<id>/ 部分）。去重并保持出现顺序。
func ParseDoubanUserIDs(raw string) []string {
	raw = strings.TrimSpace(raw)
	if raw == "" {
		return nil
	}
	// 先把 URL 形式的 ID 提取出来，再对剩余文本按分隔符切分。
	tokens := make([]string, 0, 4)
	for _, m := range doubanPeopleRe.FindAllStringSubmatch(raw, -1) {
		tokens = append(tokens, m[1])
	}
	rest := doubanPeopleRe.ReplaceAllString(raw, " ")
	fields := strings.FieldsFunc(rest, func(r rune) bool {
		switch r {
		case ',', '，', '、', ';', '；', '|', '/', '?', '&', '=', ':', ' ', '\t', '\n', '\r', '\u3000':
			return true
		}
		return false
	})
	tokens = append(tokens, fields...)

	out := make([]string, 0, len(tokens))
	seen := map[string]bool{}
	for _, t := range tokens {
		t = strings.TrimSpace(t)
		if t == "" || seen[t] || doubanIDNoise[strings.ToLower(t)] || !doubanIDRe.MatchString(t) {
			continue
		}
		seen[t] = true
		out = append(out, t)
	}
	return out
}

// wishUsers 返回本次想看同步要处理的用户列表：
// 优先用配置里的（支持多个），未配置时回退到 Cookie 中的 dbcl2。
func (c *Config) wishUsers() []string {
	if ids := ParseDoubanUserIDs(c.DoubanUserID); len(ids) > 0 {
		return ids
	}
	if uid := c.cookieUserID(); uid != "" {
		return []string{uid}
	}
	return nil
}

// appendUniqueString 追加不重复的字符串。
func appendUniqueString(list []string, v string) []string {
	if v == "" {
		return list
	}
	for _, x := range list {
		if x == v {
			return list
		}
	}
	return append(list, v)
}

// unionStrings 合并两个字符串集合（保序去重）。
func unionStrings(a, b []string) []string {
	out := make([]string, 0, len(a)+len(b))
	for _, s := range a {
		out = appendUniqueString(out, s)
	}
	for _, s := range b {
		out = appendUniqueString(out, s)
	}
	return out
}

// sameStringSet 判断两个字符串集合是否等价（忽略顺序）。
func sameStringSet(a, b []string) bool {
	if len(a) != len(b) {
		return false
	}
	for _, x := range a {
		found := false
		for _, y := range b {
			if x == y {
				found = true
				break
			}
		}
		if !found {
			return false
		}
	}
	return true
}

// getWishItemsMultiRet 依次抓取多个用户的想看列表并合并。
// 同一 subject 出现在多个用户列表时合并为一条（Users 记录全部来源用户）；
// 单个用户失败不影响其他用户，失败信息随返回值一并带回；
// 同时带回每个用户的昵称/头像（用于在订阅历史里标出用户名）。
func (r *runtime) getWishItemsMultiRet(users []string, maxPages int) ([]wishItem, []DoubanUser, []string) {
	merged := map[string]*wishItem{}
	order := make([]string, 0, 32)
	infos := make([]DoubanUser, 0, len(users))
	var errs []string
	for _, u := range users {
		items, info, err := r.getWishItemsWithUser(u, maxPages)
		if err != nil {
			errs = append(errs, fmt.Sprintf("用户 %s 读取失败：%v", u, err))
			continue
		}
		uid := info.ID
		if uid == "" {
			uid = u
		}
		info.ID = uid
		infos = append(infos, info)
		for _, it := range items {
			if it.SubjectID == "" {
				continue
			}
			if ex, ok := merged[it.SubjectID]; ok {
				ex.Users = appendUniqueString(ex.Users, uid)
				continue
			}
			cp := it
			cp.Users = appendUniqueString(cp.Users, uid)
			merged[it.SubjectID] = &cp
			order = append(order, it.SubjectID)
		}
	}
	out := make([]wishItem, 0, len(order))
	for _, id := range order {
		out = append(out, *merged[id])
	}
	return out, infos, errs
}

// getWishItemsMulti 兼容入口：只关心条目与错误信息。
func (r *runtime) getWishItemsMulti(users []string, maxPages int) ([]wishItem, []string) {
	items, _, errs := r.getWishItemsMultiRet(users, maxPages)
	return items, errs
}

// subjectCK 从豆瓣页面 HTML 提取 ck（CSRF token）。
func subjectCK(html string) string {
	if m := ckRe.FindStringSubmatch(html); len(m) > 1 {
		return m[1]
	}
	if m := ckJSONRe.FindStringSubmatch(html); len(m) > 1 {
		return m[1]
	}
	return ""
}

// parseWishHTML 解析豆瓣想看列表页。
func parseWishHTML(html string) []wishItem {
	seen := map[string]bool{}
	var items []wishItem
	linkRe := regexp.MustCompile(`href="https://movie\.douban\.com/subject/(\d+)/"`)
	for _, m := range linkRe.FindAllStringSubmatchIndex(html, -1) {
		id := html[m[2]:m[3]]
		if seen[id] {
			continue
		}
		seen[id] = true
		end := m[1] + 1600
		if end > len(html) {
			end = len(html)
		}
		window := html[m[1]:end]
		item := wishItem{SubjectID: id}
		item.Title = extractTitleFromWindow(window)
		item.Year = extractYear(window)
		item.Poster = extractPoster(window)
		item.WishTime = extractWishTime(window)
		if item.Title == "" {
			item.Title = id
		}
		items = append(items, item)
	}
	return items
}

func extractTitleFromWindow(window string) string {
	if m := emRe.FindStringSubmatch(window); len(m) > 1 {
		if t := strings.TrimSpace(m[1]); t != "" {
			return t
		}
	}
	// 回退到第一个 subject 链接的文本
	if m := anchorRe.FindStringSubmatch(window); len(m) > 2 {
		if t := stripTags(m[2]); t != "" && len(t) < 120 {
			return t
		}
	}
	return ""
}

func extractPoster(window string) string {
	if m := imgRe.FindStringSubmatch(window); len(m) > 1 {
		return m[1]
	}
	return ""
}

func extractWishTime(window string) string {
	if m := dateRe.FindStringSubmatch(window); len(m) > 1 {
		return strings.TrimSpace(m[1])
	}
	return ""
}

// parseSearchHTML 解析豆瓣搜索页，返回候选 subject 列表。
func parseSearchHTML(html string) []wishItem {
	seen := map[string]bool{}
	var items []wishItem
	for _, m := range anchorRe.FindAllStringSubmatch(html, -1) {
		id := m[1]
		title := stripTags(m[2])
		if title == "" || seen[id] {
			continue
		}
		seen[id] = true
		items = append(items, wishItem{SubjectID: id, Title: title})
	}
	return items
}

// ---- 豆瓣客户端 ----

// getWishItems 读取豆瓣「想看」列表。
func (r *runtime) getWishItems(userID string, maxPages int) ([]wishItem, error) {
	items, _, err := r.getWishItemsWithUser(userID, maxPages)
	return items, err
}

// getWishItemsWithUser 读取豆瓣「想看」列表，并顺带解析该用户的昵称/头像。
// 昵称只在首页解析一次（个人资料块只出现在页面顶部）；解析不到时回退到缓存中的
// 历史昵称，避免偶发改版或页面差异导致界面上的用户名突然消失。
func (r *runtime) getWishItemsWithUser(userID string, maxPages int) ([]wishItem, DoubanUser, error) {
	if userID == "" {
		userID = r.currentConfig().cookieUserID()
	}
	if userID == "" {
		return nil, DoubanUser{}, &doubanError{Msg: "未配置豆瓣用户 ID，且 Cookie 缺少 dbcl2"}
	}
	info := DoubanUser{ID: userID}
	var all []wishItem
	for page := 0; page < maxPages; page++ {
		items, pageInfo, err := r.getWishPage(userID, page)
		if page == 0 && pageInfo.Name != "" {
			info = pageInfo
		}
		if err != nil {
			return nil, info, err
		}
		if len(items) == 0 {
			break
		}
		all = append(all, items...)
	}
	if info.Name == "" {
		if cached, ok := r.loadWishUsers()[userID]; ok {
			info.Name = cached.Name
			if info.Avatar == "" {
				info.Avatar = cached.Avatar
			}
		}
	}
	return all, info, nil
}

// getWishPage 抓取想看列表的单页（每页 15 条）。
//
// 想看同步按页分片：一次只抓一页，让长列表也能在调用预算内推进，
// 而不是一次抓完所有用户的所有页（豆瓣每页都要 1~2 秒，用户多时必然超时）。
func (r *runtime) getWishPage(userID string, page int) ([]wishItem, DoubanUser, error) {
	if userID == "" {
		userID = r.currentConfig().cookieUserID()
	}
	if userID == "" {
		return nil, DoubanUser{}, &doubanError{Msg: "未配置豆瓣用户 ID，且 Cookie 缺少 dbcl2"}
	}
	info := DoubanUser{ID: userID}
	start := page * 15
	rawURL := doubanWish + userID + "/wish?start=" + itoaSafe(start) + "&sort=time&rating=all&filter=all&mode=grid"
	status, body, err := r.doubanGet(rawURL, doubanMovie+"/people/"+userID+"/wish")
	if err != nil {
		return nil, info, err
	}
	if status == 401 || status == 403 {
		return nil, info, &doubanError{Msg: "豆瓣 Cookie 失效或触发风控"}
	}
	if status != 200 {
		return nil, info, &httpError{Status: status, Body: string(body)}
	}
	if looksBlocked(string(body)) {
		return nil, info, &doubanError{Msg: "豆瓣 Cookie 失效或触发登录验证"}
	}
	htmlText := string(body)
	if page == 0 {
		if name, avatar := parseDoubanUserProfile(htmlText); name != "" || avatar != "" {
			info.Name = name
			info.Avatar = avatar
		}
		if info.Name == "" {
			if cached, ok := r.loadWishUsers()[userID]; ok {
				info.Name = cached.Name
				if info.Avatar == "" {
					info.Avatar = cached.Avatar
				}
			}
		}
	}
	return parseWishHTML(htmlText), info, nil
}

// doubanGet 带 Cookie 与 UA 访问豆瓣。
// 注意：宿主 Broker 禁止插件设置 host/connection/content-length 等请求头
// （host 头由宿主根据 URL 自动生成），否则返回 -32001。
func (r *runtime) doubanGet(rawURL, referer string) (int, []byte, error) {
	cfg := r.currentConfig()
	headers := map[string]string{
		"user-agent": doubanUA,
		"accept":     "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
	}
	if referer != "" {
		headers["referer"] = referer
	}
	if cookie := cfg.doubanCookieHeader(); cookie != "" {
		headers["cookie"] = cookie
	}
	return r.httpGet(rawURL, headers)
}

// searchSubject 按标题搜索豆瓣条目，返回最佳匹配 subject ID。
func (r *runtime) searchSubject(title string) (string, string, error) {
	rawURL := doubanSearch + url.QueryEscape(title)
	status, body, err := r.doubanGet(rawURL, doubanHome)
	if err != nil {
		return "", "", err
	}
	if status != 200 {
		return "", "", &httpError{Status: status, Body: string(body)}
	}
	items := parseSearchHTML(string(body))
	if len(items) == 0 {
		return "", "", nil
	}
	// 优先标题精确匹配
	targetKey := normalizeTitle(title)
	for _, it := range items {
		if normalizeTitle(it.Title) == targetKey {
			return it.Title, it.SubjectID, nil
		}
	}
	return items[0].Title, items[0].SubjectID, nil
}

// markWatched 标记豆瓣条目观看状态：collect=看过，do=在看。
func (r *runtime) markWatched(subjectID, status string) error {
	cfg := r.currentConfig()
	ck := ""
	// 尝试从条目页获取 ck
	pageURL := doubanMovie + "/subject/" + subjectID + "/"
	if s, body, err := r.doubanGet(pageURL, doubanMovie); err == nil && s == 200 {
		ck = subjectCK(string(body))
	}
	if ck == "" {
		return &doubanError{Msg: "无法获取豆瓣 ck，请确认 Cookie 有效"}
	}
	form := url.Values{}
	form.Set("ck", ck)
	form.Set("interest", status)
	form.Set("rating", "")
	form.Set("foldcollect", "U")
	form.Set("tags", "")
	form.Set("comment", "")
	form.Set("private", "on")
	headers := map[string]string{
		"user-agent":       doubanUA,
		"accept":           "application/json, text/javascript, */*; q=0.01",
		"referer":          pageURL,
		"origin":           doubanMovie,
		"x-requested-with": "XMLHttpRequest",
	}
	if cookie := cfg.doubanCookieHeader(); cookie != "" {
		headers["cookie"] = cookie
	}
	statusCode, body, err := r.httpPostForm(doubanInterest+subjectID+"/interest", headers, form)
	if err != nil {
		return err
	}
	if statusCode != 200 {
		return &httpError{Status: statusCode, Body: string(body)}
	}
	// 豆瓣返回 JSON，r=false 表示失败
	if strings.Contains(string(body), `"r":false`) {
		return &doubanError{Msg: "豆瓣拒绝标记（可能未开播或风控）"}
	}
	return nil
}

func looksBlocked(text string) bool {
	lower := strings.ToLower(text)
	markers := []string{"accounts.douban.com/passport/login", "sec.douban.com", "captcha", "验证码", "登录豆瓣", "异常请求"}
	for _, m := range markers {
		if strings.Contains(lower, m) || strings.Contains(text, m) {
			return true
		}
	}
	return false
}

type doubanError struct {
	Msg string
}

func (e *doubanError) Error() string {
	return e.Msg
}
