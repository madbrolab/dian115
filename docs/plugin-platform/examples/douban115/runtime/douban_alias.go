package main

import (
	"encoding/json"
	"regexp"
	"strings"
)

// ---- 豆瓣条目的原名 / 又名（TMDB 匹配的兜底） ----
//
// 有一类条目，TMDB 里**根本没有中文标题**，只拿豆瓣的中文译名去搜是永远搜不到的：
// 《流人 第六季》在豆瓣条目的原名是「Slow Horses Season 6」，而 TMDB 的中文搜索
// 结果里完全不含这部剧——搜「流人」返回的是《潮流合伙人》《千古风流人物》这类
// 只共享单个汉字的无关条目（这类条目即使勉强接受也是错配，所以识别逻辑会拒收，
// 结果就是「TMDB 未匹配」）。
//
// 豆瓣移动端接口会给出条目的原名与又名列表：
//
//	https://m.douban.com/rexxar/api/v2/{tv|movie}/{subject_id}
//	  → original_title: "Slow Horses Season 6"
//	  → aka: ["翻盘特工队(港)", "外放特务组(台)", "驸马", "慢马", ...]
//
// 用这些名字（尤其原名）重新搜一次 TMDB 即可命中。这条兜底只在「按标题一次都没
// 匹配上」时才走，每次同步只让真正失败的条目多付一次请求，命中结果照常进
// tmdb_cache，因此同一部剧下一轮不会再重复这套流程。

const (
	storageDoubanAlias = "douban_alias"
	// doubanAliasVersion 缓存结构版本：结构变更后旧缓存作废。
	doubanAliasVersion = 1
	// doubanAliasMax 缓存条数上限（超限整体重建，避免无限增长）。
	doubanAliasMax = 600
	// doubanAliasTryMax 单个条目最多拿几个名字去重搜 TMDB，避免一次失败拖长同步。
	doubanAliasTryMax = 6
	// doubanAliasCtx 豆瓣接口需要 Referer，否则可能被拒。
	doubanAliasReferer = "https://m.douban.com/"
)

var (
	// 豆瓣 rexxar 接口地址，两种类型各一条（类型不符时豆瓣会 301 到另一条）。
	doubanAliasTypeRe = regexp.MustCompile(`^https://m\.douban\.com/rexxar/api/v2/(tv|movie)/(\d+)$`)
	// 301 响应体里会写明真实地址，用它纠正类型。
	doubanAliasRedirectRe = regexp.MustCompile(`rexxar/api/v2/(tv|movie)/(\d+)`)
	// 又名里的括号注释（"(港)" "(台)" 之类）对 TMDB 搜索没有帮助，去掉。
	doubanAliasParenRe = regexp.MustCompile(`[(（][^)）]{1,12}[)）]`)
)

// doubanSubjectAlias 一个豆瓣条目的原名与又名。
type doubanSubjectAlias struct {
	Original string   `json:"original,omitempty"`
	AKA      []string `json:"aka,omitempty"`
	// OK 是否成功取过。false 表示取过但没有可用数据（如接口受限），
	// 记下来避免每轮同步对同一条目反复请求。
	OK bool `json:"ok,omitempty"`
}

type doubanAliasFile struct {
	Version int                           `json:"version"`
	Items   map[string]doubanSubjectAlias `json:"items"`
}

func (r *runtime) loadDoubanAliases() map[string]doubanSubjectAlias {
	var f doubanAliasFile
	if ok, err := r.storageGet(storageDoubanAlias, &f); err != nil || !ok || f.Version != doubanAliasVersion || f.Items == nil {
		return map[string]doubanSubjectAlias{}
	}
	return f.Items
}

func (r *runtime) saveDoubanAliases(items map[string]doubanSubjectAlias) {
	if items == nil {
		items = map[string]doubanSubjectAlias{}
	}
	_ = r.storagePut(storageDoubanAlias, doubanAliasFile{Version: doubanAliasVersion, Items: items})
}

// doubanSubjectAliasFor 取条目原名/又名，带缓存（含「取过但没有」的负结果）。
func (r *runtime) doubanSubjectAliasFor(subjectID, mediaType string) doubanSubjectAlias {
	subjectID = strings.TrimSpace(subjectID)
	if subjectID == "" {
		return doubanSubjectAlias{}
	}
	cache := r.loadDoubanAliases()
	if hit, ok := cache[subjectID]; ok {
		return hit
	}
	a := r.fetchDoubanSubjectAlias(subjectID, mediaType)
	if len(cache) >= doubanAliasMax {
		cache = map[string]doubanSubjectAlias{} // 简单限容：超限整体重建
	}
	cache[subjectID] = a
	r.saveDoubanAliases(cache)
	return a
}

// fetchDoubanSubjectAlias 调豆瓣移动端接口取 original_title 与 aka。
// 类型（tv/movie）不符时豆瓣返回 301，这里按响应体里的真实地址纠正后重试一次。
func (r *runtime) fetchDoubanSubjectAlias(subjectID, mediaType string) doubanSubjectAlias {
	kind := "movie"
	if mediaType == "tv" {
		kind = "tv"
	}
	for attempt := 0; attempt < 2; attempt++ {
		url := doubanAliasURL(kind, subjectID)
		status, body, err := r.doubanGet(url, doubanAliasReferer)
		if err != nil {
			r.log("warn", "豆瓣原名/又名取回失败", map[string]any{"subject": subjectID, "err": errString(err)})
			return doubanSubjectAlias{}
		}
		// 类型猜错时豆瓣 301 到正确地址（宿主 Broker 不跟随跨类型跳转）。
		if status == 301 || status == 302 {
			if m := doubanAliasRedirectRe.FindStringSubmatch(string(body)); len(m) > 2 && m[1] != kind {
				kind = m[1]
				continue
			}
		}
		if status != 200 {
			return doubanSubjectAlias{}
		}
		var raw struct {
			OriginalTitle string   `json:"original_title"`
			AKA           []string `json:"aka"`
		}
		if err := json.Unmarshal(body, &raw); err != nil {
			return doubanSubjectAlias{}
		}
		a := doubanSubjectAlias{Original: strings.TrimSpace(raw.OriginalTitle), OK: true}
		for _, s := range raw.AKA {
			if s = cleanAlias(s); s != "" {
				a.AKA = append(a.AKA, s)
			}
		}
		r.log("info", "豆瓣原名/又名已取回", map[string]any{
			"subject": subjectID, "original": a.Original, "aka": len(a.AKA),
		})
		return a
	}
	return doubanSubjectAlias{}
}

func doubanAliasURL(kind, subjectID string) string {
	return "https://m.douban.com/rexxar/api/v2/" + kind + "/" + subjectID
}

// cleanAlias 去掉又名里的括号注释与多余空白（"(港)" 这类对 TMDB 搜索无帮助）。
func cleanAlias(s string) string {
	s = doubanAliasParenRe.ReplaceAllString(s, " ")
	return strings.TrimSpace(wsRe.ReplaceAllString(s, " "))
}

// aliasQueries 由豆瓣原名/又名生成 TMDB 搜索词，按「原名 → 又名」顺序、去重后限量。
// 与榜单标题同源的名字会跳过（那个词已经搜过并且失败了）。
func aliasQueries(title, mediaType string, a doubanSubjectAlias) []string {
	seen := map[string]bool{searchKey(title, mediaType): true}
	out := make([]string, 0, doubanAliasTryMax)
	add := func(s string) {
		if len(out) >= doubanAliasTryMax {
			return
		}
		s = cleanAlias(s)
		if s == "" {
			return
		}
		k := searchKey(s, mediaType)
		if k == "" || seen[k] {
			return
		}
		seen[k] = true
		out = append(out, s)
	}
	add(a.Original)
	for _, s := range a.AKA {
		add(s)
	}
	return out
}

// searchKey 把标题归一化为「实际会被拿去搜索」的形式（与 resolveTMDB 一致），
// 仅用于判重：与榜单标题同源的名字不必重搜（那个词已经搜过并且失败了）。
func searchKey(title, mediaType string) string {
	return normalizeTitle(tmdbSearchTitle(title, mediaType))
}
