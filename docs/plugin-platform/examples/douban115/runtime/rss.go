package main

import (
	"encoding/xml"
	"regexp"
	"strings"
	"unicode"
)

// ---- RSS 结构 ----

type rssFeed struct {
	Channel struct {
		Items []rssItem `xml:"item"`
	} `xml:"channel"`
}

type rssItem struct {
	Title       string `xml:"title"`
	Link        string `xml:"link"`
	Description string `xml:"description"`
	Category    string `xml:"category"`
	PubDate     string `xml:"pubDate"`
}

// rankItem 榜单/想看条目。
type rankItem struct {
	Title     string   `json:"title"`
	Link      string   `json:"link"`
	DoubanID  string   `json:"douban_id"`
	Year      string   `json:"year"`
	MediaType string   `json:"media_type"`
	Category  string   `json:"category"`
	Regions   []string `json:"regions"`
	WishCount int      `json:"wish_count"`
}

// wishItem 豆瓣想看条目。Users 记录这条想看来自哪些豆瓣用户（多用户合并时可能多个）。
type wishItem struct {
	SubjectID string   `json:"subject_id"`
	Title     string   `json:"title"`
	Year      string   `json:"year"`
	Poster    string   `json:"poster"`
	WishTime  string   `json:"wish_time"`
	Users     []string `json:"users,omitempty"`
}

var (
	subjectIDRe = regexp.MustCompile(`subject/(\d+)/?`)
	yearRe      = regexp.MustCompile(`\b(19|20)\d{2}\b`)
	seasonRe    = regexp.MustCompile(`第\s*([0-9]+|[一二三四五六七八九十]+)\s*季|[Ss]eason\s*0*(\d+)|[Ss]0*(\d+)`)
	tagRe       = regexp.MustCompile(`<[^>]+>`)
	wsRe        = regexp.MustCompile(`\s+`)
	wishCountRe = regexp.MustCompile(`([0-9]+)\s*人(?:想看|评价)`)
)

// extractSubjectID 从链接中提取豆瓣 subject ID。
func extractSubjectID(s string) string {
	m := subjectIDRe.FindStringSubmatch(s)
	if len(m) > 1 {
		return m[1]
	}
	return ""
}

// extractYear 提取文本中的 4 位年份。
func extractYear(s string) string {
	m := yearRe.FindStringSubmatch(s)
	if len(m) > 0 {
		return m[0]
	}
	return ""
}

// stripSeasonSuffix 去掉标题末尾的季号（如「信号 第二季」「Dark Season 2」→「信号」「Dark」），
// 供 TMDB 识别使用：TMDB 按基础剧名收录，带季号搜索会识别失败。
// 仅当季号位于标题末尾（其后只剩空白）时才剥离，避免误伤标题中间含类似字样的作品。
func stripSeasonSuffix(title string) string {
	locs := seasonRe.FindAllStringIndex(title, -1)
	if len(locs) == 0 {
		return title
	}
	loc := locs[len(locs)-1]
	if strings.TrimSpace(title[loc[1]:]) != "" {
		return title
	}
	base := strings.TrimSpace(title[:loc[0]])
	if base == "" {
		return title
	}
	return base
}

// extractSeason 从标题提取季号，未识别返回 1。
// 支持阿拉伯数字（第2季 / Season 2 / S2）与中文数字（第二季、第十二季）。
func extractSeason(title string) int {
	m := seasonRe.FindStringSubmatch(title)
	if len(m) > 0 {
		for i := 1; i < len(m); i++ {
			if m[i] != "" {
				if n := parseSeasonNum(m[i]); n > 0 {
					return n
				}
			}
		}
	}
	return 1
}

// parseSeasonNum 解析季号数字：支持阿拉伯数字与中文数字（一至九十九）。
func parseSeasonNum(s string) int {
	s = strings.TrimSpace(s)
	if s == "" {
		return 0
	}
	if n := atoiSafe(s); n > 0 {
		return n
	}
	cn := map[rune]int{'一': 1, '二': 2, '三': 3, '四': 4, '五': 5, '六': 6, '七': 7, '八': 8, '九': 9}
	total, hasTen := 0, false
	for _, ch := range s {
		if ch == '十' {
			if total == 0 {
				total = 1
			}
			hasTen = true
			continue
		}
		v, ok := cn[ch]
		if !ok {
			return 0
		}
		if hasTen {
			total = total*10 + v
			hasTen = false
		} else {
			total = total*10 + v
		}
	}
	if hasTen {
		total *= 10 // 形如「二十」
	}
	return total
}

// ---- TMDB 搜索的标题候选 ----
//
// BangumiTV 等榜单的标题常是「主标题 + 篇章名 + 季号」拼在一起的长串，
// 例如「Re:ゼロから始める異世界生活 4th season 奪還編」
// 「スティール・ボール・ラン ジョジョの奇妙な冒険 2nd & 3rd STAGE」。
// TMDB 按字面搜这类整串返回 0 结果，需要逐级回退到更短的标题。

var (
	// 末尾篇章名后缀：奪還編 / 夺还篇 / 第2章 / 2nd STAGE / Arc
	tailArcRe = regexp.MustCompile(`(?i)\s+\S{1,14}(?:編|篇|章|part|stage|arc)$`)
	// 主 / 副标题分隔符（「A ～B～」→ 取 A）
	subTitleSepRe = regexp.MustCompile(`[～~]|[（(【「『]`)
)

// stripTailArc 去掉标题末尾的「篇章名」后缀，未匹配时原样返回。
func stripTailArc(title string) string {
	if loc := tailArcRe.FindStringIndex(title); loc != nil {
		if base := strings.TrimSpace(title[:loc[0]]); base != "" {
			return base
		}
	}
	return title
}

// headBeforeSeparator 取主副标题分隔符之前的主标题，未匹配时原样返回。
func headBeforeSeparator(title string) string {
	if loc := subTitleSepRe.FindStringIndex(title); loc != nil && loc[0] > 0 {
		head := strings.TrimRight(strings.TrimSpace(title[:loc[0]]), "·-–—:：,，、")
		if head = strings.TrimSpace(head); head != "" {
			return head
		}
	}
	return title
}

// titleCandidates 生成 TMDB 搜索的替代标题，按「保守 → 激进」排序（不含原串本身）。
// 调用方应先搜原串，无结果再依次尝试这些候选。
func titleCandidates(title string) []string {
	t := strings.TrimSpace(title)
	if t == "" {
		return nil
	}
	out := make([]string, 0, 10)
	seen := map[string]bool{t: true}
	add := func(s string) {
		if s = strings.TrimSpace(s); s == "" || seen[s] {
			return
		}
		seen[s] = true
		out = append(out, s)
	}

	noArc := stripTailArc(t)
	noSeason := stripSeasonSuffix(t)
	head := headBeforeSeparator(t)

	add(noArc)
	add(noSeason)
	add(stripSeasonSuffix(noArc))
	add(head)
	add(stripSeasonSuffix(head))
	add(stripSeasonSuffix(stripTailArc(head)))

	// 逐词递减：保留开头连续 N 个词（N 由多到少，至少 2 个词），
	// 用于「主标题 + 副标题 + 季号」这类纯截断才能命中的情况。
	words := strings.Fields(noSeason)
	for n := len(words) - 1; n >= 2; n-- {
		add(strings.Join(words[:n], " "))
	}
	return out
}

// normalizeTitle 生成用于比较的标题键：只保留字母与数字并转小写。
// 这里必须用 unicode.IsLetter 而不是「码点 ≥ 0x3400」——后者会丢掉全部日文假名
// （U+3040–U+30FF）和韩文谚文，「ヤニねこ」这类纯假名标题会被归一化成空串，
// 名称相关性无从比较，只能退回按热度选片，于是出现封面张冠李戴。
func normalizeTitle(s string) string {
	var b strings.Builder
	for _, ch := range s {
		if unicode.IsLetter(ch) || unicode.IsDigit(ch) {
			b.WriteRune(unicode.ToLower(ch))
		}
	}
	return b.String()
}

// stripTags 去除 HTML 标签并折叠空白。
func stripTags(s string) string {
	return strings.TrimSpace(wsRe.ReplaceAllString(tagRe.ReplaceAllString(s, " "), " "))
}

// parseRegions 从 category 文本识别已知地区。
func parseRegions(s string) []string {
	var regions []string
	for _, name := range regionNames {
		if strings.Contains(s, name) {
			regions = append(regions, name)
		}
	}
	return regions
}

// parseWishCount 从描述文本解析想看人数。
func parseWishCount(s string) int {
	m := wishCountRe.FindStringSubmatch(s)
	if len(m) > 1 {
		return atoiSafe(m[1])
	}
	return 0
}

// matchBlacklist 判断黑名单规则是否命中文本；支持 regex: / case: 前缀。
func matchBlacklist(rule, haystack string) bool {
	rule = strings.TrimSpace(rule)
	if rule == "" {
		return false
	}
	caseSensitive := false
	if strings.HasPrefix(strings.ToLower(rule), "case:") {
		caseSensitive = true
		rule = strings.TrimSpace(rule[5:])
	}
	flags := ""
	if !caseSensitive {
		flags = "(?i)"
	}
	if strings.HasPrefix(strings.ToLower(rule), "regex:") {
		pattern := strings.TrimSpace(rule[6:])
		if pattern == "" {
			return false
		}
		re, err := regexp.Compile(flags + pattern)
		if err != nil {
			return false
		}
		return re.MatchString(haystack)
	}
	src := haystack
	target := rule
	if !caseSensitive {
		src = strings.ToLower(haystack)
		target = strings.ToLower(rule)
	}
	for _, token := range strings.Fields(target) {
		if !strings.Contains(src, token) {
			return false
		}
	}
	return true
}

// blacklistHit 判断标题/描述是否命中任意黑名单规则。
func blacklistHit(blacklist, haystack string) bool {
	for _, line := range strings.Split(blacklist, "\n") {
		if matchBlacklist(line, haystack) {
			return true
		}
	}
	return false
}

// fetchRank 拉取并解析 RSS 榜单。
func (r *runtime) fetchRank(route string, limit int, mediaType string) ([]rankItem, error) {
	cfg := r.currentConfig()
	domain := defaultRSSHubDomain
	if cfg != nil && strings.TrimSpace(cfg.RSSHubDomain) != "" {
		domain = strings.TrimRight(strings.TrimSpace(cfg.RSSHubDomain), "/")
	}
	rawURL := domain + route + "?limit=" + itoaSafe(limit)
	status, body, err := r.httpGet(rawURL, map[string]string{
		"user-agent": "Mozilla/5.0 (iPhone; CPU iPhone OS 16_0 like Mac OS X) AppleWebKit/605.1.15 Mobile/15E148",
		"accept":     "application/rss+xml, application/xml, text/xml, */*",
	})
	if err != nil {
		return nil, err
	}
	if status != 200 {
		return nil, &httpError{Status: status, Body: string(body)}
	}
	var feed rssFeed
	if err := xml.Unmarshal(body, &feed); err != nil {
		return nil, err
	}
	var items []rankItem
	for _, it := range feed.Channel.Items {
		if strings.TrimSpace(it.Title) == "" {
			continue
		}
		mt := mediaType
		if mt == "" || mt == "unknown" {
			if strings.Contains(strings.ToLower(it.Title), "季") || seasonRe.MatchString(it.Title) {
				mt = "tv"
			} else if strings.Contains(strings.ToLower(route), "movie") {
				mt = "movie"
			} else {
				mt = "tv"
			}
		}
		items = append(items, rankItem{
			Title:     strings.TrimSpace(it.Title),
			Link:      strings.TrimSpace(it.Link),
			DoubanID:  extractSubjectID(it.Link),
			Year:      extractYear(it.Description + " " + it.Category),
			MediaType: mt,
			Category:  strings.TrimSpace(it.Category),
			Regions:   parseRegions(it.Category + " " + it.Description),
			WishCount: parseWishCount(it.Description),
		})
	}
	return items, nil
}

type httpError struct {
	Status int
	Body   string
}

func (e *httpError) Error() string {
	return "HTTP " + itoaSafe(e.Status)
}
