package main

import (
	"fmt"
	"strings"
	"time"
)

// ---- 三个同步任务的分片实现 ----
//
// 每个 step 函数只做「一小片」工作：处理到 deadline 就保存进度并返回 false，
// 由 runJobLoop 在片间让出后再次进入，从断点继续。这样单次连续占用始终
// 控制在几秒内，宿主随时可以完成探测与页面调用；即使实例被回收，已完成的
// 部分已经落盘，下一轮从断点继续而不是从头重来。

// ---- 榜单订阅 ----

func (r *runtime) stepRankJob(st *jobState, deadline time.Time) bool {
	j := st.Rank
	if j == nil {
		return true
	}
	cfg := r.currentConfig()

	// 阶段一：读订阅池快照 + 逐个拉取榜单 RSS
	if st.Phase == jobPhaseFetch {
		if !j.PoolRead {
			movie, errM := r.listIntents("movie")
			tv, errT := r.listIntents("tv")
			if errM != nil || errT != nil {
				msg := "读取 dian115 订阅池失败，已中止本次榜单订阅（避免重复订阅）：" + firstErr(errM, errT).Error()
				r.finishJob(st, []string{msg}, true)
				return true
			}
			j.ExistingMovie = setKeys(movie)
			j.ExistingTV = setKeys(tv)
			j.PoolRead = true
			r.saveJobState(st)
			r.log("info", "榜单同步：订阅池已读取", map[string]any{"movie": len(movie), "tv": len(tv)})
			if time.Now().After(deadline) {
				return false
			}
		}
		for j.Idx < len(j.Ranks) {
			rk := &j.Ranks[j.Idx]
			tRank := time.Now()
			items, err := r.fetchRank(rk.Route, rk.FetchSize, rk.MediaType)
			rk.Fetched = true
			if err != nil {
				rk.FetchErr = err.Error()
				st.Lines = append(st.Lines, fmt.Sprintf("[%s] 拉取失败：%v", rk.Name, err))
			} else {
				rk.Items = items
				rk.Snap = []SnapshotItem{}
				j.Total += len(items)
				r.log("info", "榜单拉取完成", map[string]any{"rank": rk.Key, "items": len(items), "ms": time.Since(tRank).Milliseconds()})
			}
			j.Idx++
			r.updateState("running", jobProgress(st))
			r.saveJobState(st)
			if time.Now().After(deadline) {
				return false
			}
		}
		st.Phase = jobPhaseProcess
		j.Idx, j.Pos = 0, 0
		r.saveJobState(st)
		if time.Now().After(deadline) {
			return false
		}
	}

	// 阶段二：逐条处理
	existingMovie := toSet(j.ExistingMovie)
	existingTV := toSet(j.ExistingTV)
	history := r.loadRankHistory()
	snapshot := r.loadRankSnapshot()
	snapMeta := r.loadSnapshotMeta()
	var lines []string

	for j.Idx < len(j.Ranks) {
		rk := &j.Ranks[j.Idx]
		if rk.FetchErr != "" || len(rk.Items) == 0 {
			rk.Done = true
			j.Idx++
			j.Pos = 0
			continue
		}
		if j.Pos >= len(rk.Items) {
			// 本榜单处理完：裁剪历史、写快照与更新时间
			bucket := history[rk.Key]
			if len(bucket) > rankHistoryLimit {
				bucket = bucket[len(bucket)-rankHistoryLimit:]
			}
			history[rk.Key] = bucket
			snapshot[rk.Key] = rk.Snap
			snapMeta[rk.Key] = nowStr()
			rk.Done = true
			j.Idx++
			j.Pos = 0
			r.saveRankHistory(history)
			r.saveRankSnapshot(snapshot)
			_ = r.storagePut(storageRankSnapshotMeta, snapMeta)
			r.log("info", "榜单处理完成", memFieldsWith("rank-done", map[string]any{"rank": rk.Key, "snap": len(rk.Snap), "subs": j.NewSubs}))
			if time.Now().After(deadline) {
				return false
			}
			continue
		}
		it := rk.Items[j.Pos]
		unique := it.DoubanID
		if unique == "" {
			unique = "t:" + normalizeTitle(it.Title) + ":" + it.Year
		}
		// 同一榜单内的重复条目只处理一次（分片恢复时前缀已处理过）
		if unique == "" || seenBefore(rk.Items, j.Pos, unique) {
			j.Pos++
			j.Done++
			continue
		}
		bucket, snap, out, subs := r.processRankItem(rk, it, j.Pos, cfg, history[rk.Key], rk.Snap, existingMovie, existingTV)
		history[rk.Key] = bucket
		rk.Snap = snap
		lines = append(lines, out...)
		j.NewSubs += subs
		j.Pos++
		j.Done++
		r.updateState("running", jobProgress(st))
		if time.Now().After(deadline) {
			// 断点落盘：历史与快照立即保存，重启后从下一条继续
			r.saveRankHistory(history)
			r.saveRankSnapshot(snapshot)
			_ = r.storagePut(storageRankSnapshotMeta, snapMeta)
			return false
		}
	}

	r.saveRankHistory(history)
	r.saveRankSnapshot(snapshot)
	_ = r.storagePut(storageRankSnapshotMeta, snapMeta)
	st.Lines = append(st.Lines, lines...)
	r.finishJob(st, nil, false)
	return true
}

// processRankItem 处理榜单内的一条条目，返回更新后的历史桶、快照、输出行与新增订阅数。
func (r *runtime) processRankItem(rk *rankJobRank, it rankItem, pos int, cfg *Config,
	bucket []HistoryItem, snap []SnapshotItem, existingMovie, existingTV map[string]bool) ([]HistoryItem, []SnapshotItem, []string, int) {
	var lines []string
	var newSubs int
	unique := it.DoubanID
	if unique == "" {
		unique = "t:" + normalizeTitle(it.Title) + ":" + it.Year
	}
	entry := SnapshotItem{Rank: pos + 1, Title: it.Title, Year: it.Year, DoubanID: it.DoubanID, MediaType: it.MediaType, Link: it.Link}
	// 订阅范围 = 只订阅榜单前 count 名；展示范围内的条目也做识别，仪表盘要显示封面。
	inRange := rk.Count <= 0 || pos+1 <= rk.Count
	inDisplay := pos+1 <= rankDisplayLimit
	tItem := time.Now()
	r.log("info", "条目开始", map[string]any{"rank": rk.Key, "pos": pos + 1, "title": it.Title, "mt": it.MediaType})

	idx := findHistory(bucket, unique)
	if idx >= 0 {
		h := &bucket[idx]
		h.LastSeen = nowStr()
		// 与宿主真实订阅状态对账：用户在 dian115 手动删掉的订阅不能继续显示
		// 「已订阅」，也不能被下一轮自动重新订阅（标记 removed）。
		if h.TMDBID > 0 {
			present := intentPresent(existingMovie, existingTV, h.MediaType, h.TMDBID, h.Season)
			switch {
			case (h.Subscribed || h.Existing) && !present:
				h.Subscribed = false
				h.Existing = false
				h.Removed = true
			case h.Removed && present:
				h.Removed = false
				h.Existing = true
			}
		}
		if h.Subscribed || h.Existing || h.Removed {
			// 识别策略升级后，历史里的 TMDB 关联可能来自旧策略，存在张冠李戴；
			// 版本落后的条目按新策略重新识别并回写。
			if h.ResolveVer < tmdbCacheVersion && (inRange || inDisplay) {
				if mi, err := r.resolveTMDBWithAlias(it.Title, it.Year, it.MediaType, it.DoubanID); err == nil {
					h.TMDBID = tmdbIDOf(mi)
					h.Poster = ""
					if mi != nil {
						h.Poster = tmdbPoster(mi.PosterPath)
					}
					h.ResolveVer = tmdbCacheVersion
					r.log("info", "历史条目按新策略重新识别", map[string]any{"title": it.Title, "tmdb": h.TMDBID})
				}
			}
			entry.TMDBID = h.TMDBID
			entry.Poster = h.Poster
			switch {
			case h.Removed:
				entry.Status = "removed"
			case h.Subscribed:
				entry.Status = "subscribed"
			default:
				entry.Status = "existing"
			}
			return bucket, appendSnap(snap, entry), lines, 0
		}
	}

	// 展示范围内先做 TMDB 识别（仪表盘要封面）
	var mi *tmdbItem
	var resolveErr error
	if inRange || inDisplay {
		mi, resolveErr = r.resolveTMDBWithAlias(it.Title, it.Year, it.MediaType, it.DoubanID)
		r.log("info", "条目识别完成", memFieldsWith("item", map[string]any{"rank": rk.Key, "pos": pos + 1, "tmdb": tmdbIDOf(mi), "ms": time.Since(tItem).Milliseconds()}))
	}
	if mi != nil {
		entry.TMDBID = mi.ID
		entry.Poster = tmdbPoster(mi.PosterPath)
	}
	if !inRange {
		entry.Status = "beyond"
		entry.Reason = fmt.Sprintf("订阅数量为 %d，仅订阅榜单前 %d 名", rk.Count, rk.Count)
		return bucket, appendSnap(snap, entry), lines, 0
	}
	if blacklistHit(cfg.Blacklist, it.Title+"\n"+it.Category) {
		entry.Status = "blacklisted"
		return bucket, appendSnap(snap, entry), lines, 0
	}
	if resolveErr != nil || mi == nil {
		if idx < 0 {
			bucket = append(bucket, HistoryItem{Unique: unique, Title: it.Title, Year: it.Year, MediaType: it.MediaType, Link: it.Link, FirstSeen: nowStr(), LastSeen: nowStr()})
		}
		entry.Status = "unresolved"
		entry.TMDBID = 0
		entry.Poster = ""
		return bucket, appendSnap(snap, entry), lines, 0
	}
	if rk.MinVote > 0 && mi.VoteAverage > 0 && mi.VoteAverage < rk.MinVote {
		entry.Status = "filtered"
		entry.Reason = fmt.Sprintf("评分 %.1f < %.1f", mi.VoteAverage, rk.MinVote)
		return bucket, appendSnap(snap, entry), lines, 0
	}
	if rk.MinYear > 0 && it.Year != "" && atoiSafe(it.Year) < rk.MinYear {
		entry.Status = "filtered"
		entry.Reason = "年份过早"
		return bucket, appendSnap(snap, entry), lines, 0
	}
	if len(rk.Regions) > 0 && !regionMatch(rk.Regions, it.Regions) {
		entry.Status = "filtered"
		entry.Reason = "地区不匹配"
		return bucket, appendSnap(snap, entry), lines, 0
	}
	season := 1
	if it.MediaType == "tv" {
		season = extractSeason(it.Title)
	}
	// 已存在订阅（同一部剧可能同时出现在多个榜单，用订阅键集合跨榜单去重）
	if intentPresent(existingMovie, existingTV, it.MediaType, mi.ID, season) {
		if idx >= 0 {
			bucket[idx].Existing = true
			bucket[idx].Removed = false
		} else {
			bucket = append(bucket, newHistoryItem(unique, it, mi, season, true, false))
		}
		entry.Status = "existing"
		return bucket, appendSnap(snap, entry), lines, 0
	}
	// 观察期
	if cfg.ObserveDays > 0 {
		if idx >= 0 {
			if daysSince(bucket[idx].FirstSeen) < cfg.ObserveDays {
				entry.Status = "observing"
				return bucket, appendSnap(snap, entry), lines, 0
			}
		} else {
			bucket = append(bucket, newHistoryItem(unique, it, mi, season, false, false))
			entry.Status = "observing"
			return bucket, appendSnap(snap, entry), lines, 0
		}
	}
	title := it.Title
	if mi.Title != "" && it.MediaType == "movie" {
		title = mi.Title
	}
	sid, err := r.createIntent(mi.ID, season, it.MediaType, title, it.Year, true)
	if err != nil {
		lines = append(lines, fmt.Sprintf("[%s] 订阅失败《%s》：%v", rk.Name, it.Title, err))
		entry.Status = "unresolved"
		entry.Reason = "订阅失败"
		return bucket, appendSnap(snap, entry), lines, 0
	}
	item := newHistoryItem(unique, it, mi, season, false, true)
	item.SubscribedAt = nowStr()
	if idx >= 0 {
		bucket[idx] = item
	} else {
		bucket = append(bucket, item)
	}
	// 立即回填订阅池快照：同一部剧出现在后面的榜单时按「已存在」处理
	rememberIntent(existingMovie, existingTV, it.MediaType, mi.ID, season)
	r.recordSubscribed()
	newSubs = 1
	entry.Status = "subscribed"
	lines = append(lines, fmt.Sprintf("[%s] 已订阅《%s》(TMDB %d, id=%d)", rk.Name, it.Title, mi.ID, sid))
	return bucket, appendSnap(snap, entry), lines, newSubs
}

// seenBefore 判断同一榜单内该条目在 pos 之前是否已出现过（分片恢复后的去重）。
func seenBefore(items []rankItem, pos int, unique string) bool {
	for i := 0; i < pos && i < len(items); i++ {
		u := items[i].DoubanID
		if u == "" {
			u = "t:" + normalizeTitle(items[i].Title) + ":" + items[i].Year
		}
		if u == unique {
			return true
		}
	}
	return false
}

// ---- 想看订阅 ----

func (r *runtime) stepWishJob(st *jobState, deadline time.Time) bool {
	j := st.Wish
	if j == nil {
		return true
	}

	// 阶段一：逐用户逐页抓取想看列表
	if st.Phase == jobPhaseFetch {
		for j.Idx < len(j.Users) {
			userID := j.Users[j.Idx]
			items, info, err := r.getWishPage(userID, j.Page)
			if err != nil {
				j.FetchErrs = append(j.FetchErrs, fmt.Sprintf("用户 %s 第 %d 页读取失败：%v", userID, j.Page+1, err))
			} else {
				// 昵称只在首页解析得到，这里只记录一次，避免同一用户被重复列出
				if j.Page == 0 && info.ID != "" {
					j.UserInfo = append(j.UserInfo, info)
					r.saveWishUsers(mergeWishUsers(r.loadWishUsers(), []DoubanUser{info}))
				}
				// 标注来源用户：多用户合并后靠它记录「这条想看来自谁」
				for i := range items {
					items[i].Users = unionStrings(items[i].Users, []string{userID})
				}
				j.Items = mergeWishItems(j.Items, items)
				if len(items) == 0 {
					// 该用户没有更多想看：直接切到下一个用户
					j.Page = j.MaxPages
				}
			}
			j.Page++
			if j.Page >= j.MaxPages {
				j.Idx++
				j.Page = 0
			}
			r.updateState("running", jobProgress(st))
			r.saveJobState(st)
			if time.Now().After(deadline) {
				return false
			}
		}
		if len(j.UserInfo) > 0 {
			r.saveWishUsers(mergeWishUsers(r.loadWishUsers(), j.UserInfo))
		}
		st.Lines = append(st.Lines, fmt.Sprintf("想看同步：%d 个用户（%s）", len(j.Users), wishUserNames(j.UserInfo, j.Users)))
		st.Lines = append(st.Lines, j.FetchErrs...)
		if len(j.Items) == 0 {
			if len(j.FetchErrs) > 0 {
				st.Lines = append(st.Lines, "全部用户读取失败，本次未订阅")
			} else {
				st.Lines = append(st.Lines, "想看列表为空或无法解析")
			}
			r.finishJob(st, nil, false)
			return true
		}
		st.Phase = jobPhaseProcess
		j.Pos = 0
		r.saveJobState(st)
		if time.Now().After(deadline) {
			return false
		}
	}

	// 阶段二：逐条处理
	cfg := r.currentConfig()
	if !j.PoolRead {
		movie, errM := r.listIntents("movie")
		tv, errT := r.listIntents("tv")
		if errM != nil || errT != nil {
			msg := "读取 dian115 订阅池失败，已中止本次想看订阅（避免重复订阅）：" + firstErr(errM, errT).Error()
			r.finishJob(st, []string{msg}, true)
			return true
		}
		j.ExistingMovie = setKeys(movie)
		j.ExistingTV = setKeys(tv)
		j.PoolRead = true
		r.saveJobState(st)
		if time.Now().After(deadline) {
			return false
		}
	}
	existingMovie := toSet(j.ExistingMovie)
	existingTV := toSet(j.ExistingTV)
	history := r.loadWishHistory()
	userCache := r.loadWishUsers()
	now := time.Now()
	var lines []string

	for j.Pos < len(j.Items) {
		it := j.Items[j.Pos]
		r.updateState("running", jobProgress(st))
		if j.Days > 0 && it.WishTime != "" {
			if t, err := parseCNTime(it.WishTime); err == nil {
				if now.Sub(t).Hours() > float64(j.Days*24) {
					j.Pos++
					continue
				}
			}
		}
		out, subs := r.processWishItem(it, cfg, history, existingMovie, existingTV, userCache)
		lines = append(lines, out...)
		j.Subs += subs
		j.Pos++
		r.saveWishHistory(history)
		r.saveJobState(st)
		if time.Now().After(deadline) {
			return false
		}
	}
	r.saveWishHistory(history)
	lines = append(lines, fmt.Sprintf("共处理 %d 条想看，新订阅 %d 条", len(j.Items), j.Subs))
	st.Lines = append(st.Lines, lines...)
	r.finishJob(st, nil, false)
	return true
}

// processWishItem 处理一条想看条目；返回输出行与新增订阅数。
func (r *runtime) processWishItem(it wishItem, cfg *Config, history map[string]HistoryItem,
	existingMovie, existingTV map[string]bool, userCache map[string]DoubanUser) ([]string, int) {
	var lines []string
	prev, hadPrev := history[it.SubjectID]
	if hadPrev {
		if prev.TMDBID > 0 {
			present := intentPresent(existingMovie, existingTV, prev.MediaType, prev.TMDBID, prev.Season)
			switch {
			case (prev.Subscribed || prev.Existing) && !present:
				prev.Subscribed = false
				prev.Existing = false
				prev.Removed = true
			case prev.Removed && present:
				prev.Removed = false
				prev.Existing = true
			}
		}
		prev.Users = unionStrings(prev.Users, it.Users)
		history[it.SubjectID] = prev
		if prev.Subscribed || prev.Existing || prev.Removed {
			if prev.ResolveVer < tmdbCacheVersion {
				mt := prev.MediaType
				if mt == "" {
					mt = "movie"
				}
				if mi, err := r.resolveTMDBWithAlias(it.Title, it.Year, mt, it.SubjectID); err == nil {
					prev.TMDBID = tmdbIDOf(mi)
					prev.Poster = ""
					if mi != nil {
						prev.Poster = tmdbPoster(mi.PosterPath)
					}
					prev.ResolveVer = tmdbCacheVersion
					history[it.SubjectID] = prev
				}
			}
			return lines, 0
		}
	}
	// 想看列表以电影为主，但同样可能包含剧集；用标题识别媒体类型
	mt := "movie"
	mi, err := r.resolveTMDBWithAlias(it.Title, it.Year, "movie", it.SubjectID)
	if err != nil || mi == nil {
		mi, err = r.resolveTMDBWithAlias(it.Title, it.Year, "tv", it.SubjectID)
		if err != nil || mi == nil {
			return lines, 0
		}
		mt = "tv"
	}
	season := 1
	if mt == "tv" {
		season = extractSeason(it.Title)
	}
	firstSeen := nowStr()
	usersOf := it.Users
	if hadPrev {
		if prev.FirstSeen != "" {
			firstSeen = prev.FirstSeen
		}
		usersOf = unionStrings(prev.Users, it.Users)
	}
	if intentPresent(existingMovie, existingTV, mt, mi.ID, season) {
		history[it.SubjectID] = HistoryItem{Unique: it.SubjectID, Title: it.Title, Year: it.Year, TMDBID: mi.ID, MediaType: mt, Season: season, Poster: tmdbPoster(mi.PosterPath), Users: usersOf, Existing: true, ResolveVer: tmdbCacheVersion, FirstSeen: firstSeen, LastSeen: nowStr()}
		return lines, 0
	}
	sid, err := r.createIntent(mi.ID, season, mt, it.Title, it.Year, true)
	if err != nil {
		lines = append(lines, fmt.Sprintf("订阅失败《%s》（来源：%s）：%v", it.Title, wishUsersLabel(userCache, usersOf), err))
		return lines, 0
	}
	history[it.SubjectID] = HistoryItem{Unique: it.SubjectID, Title: it.Title, Year: it.Year, TMDBID: mi.ID, MediaType: mt, Season: season, Poster: tmdbPoster(mi.PosterPath), Users: usersOf, Subscribed: true, ResolveVer: tmdbCacheVersion, FirstSeen: firstSeen, LastSeen: nowStr(), SubscribedAt: nowStr()}
	rememberIntent(existingMovie, existingTV, mt, mi.ID, season)
	r.recordSubscribed()
	lines = append(lines, fmt.Sprintf("已订阅想看《%s》(TMDB %d, id=%d) · 来源：%s", it.Title, mi.ID, sid, wishUsersLabel(userCache, usersOf)))
	return lines, 1
}

// mergeWishItems 合并想看条目（按 subject 去重并合并来源用户）。
func mergeWishItems(dst, src []wishItem) []wishItem {
	for _, it := range src {
		found := false
		for i := range dst {
			if dst[i].SubjectID == it.SubjectID && it.SubjectID != "" {
				dst[i].Users = unionStrings(dst[i].Users, it.Users)
				found = true
				break
			}
		}
		if !found {
			dst = append(dst, it)
		}
	}
	return dst
}

// ---- Emby 观影同步 ----

// embySyncedLimit 已同步记录的保留上限。旧实现在超过 600 条时按 map 随机
// 删除，被删掉的条目下一轮会被重新同步一遍 —— 于是每 30 分钟一轮的 Emby
// 同步永远做不完，任务时长无限累加。这里把上限提高到远超实际规模，并在
// 超限时才裁剪（正常规模下不会触发）。
const embySyncedLimit = 4000
const embySyncedTrimTo = 3000

// embyMaxPerRun 每轮最多实际标记的条目数。
//
// 首轮同步时「已观看」列表可能有几百条，每条都要走 TMDB 详情 + 豆瓣搜索 +
// 豆瓣标记（2~3 次外网请求）。即便按片推进，一轮做完几百条也要几十分钟，
// 期间宿主随时可能回收实例。这里给每轮设上限：本轮只处理最前面的一批，
// 剩下的下一轮继续（已标记的都已落盘，不会重复请求）。
const embyMaxPerRun = 40

// embyAbortStreak 连续多少条未能同步就提前收工。Emby 不可达或豆瓣 Cookie 失效时，
// 每一条都要等一次网络超时，几百条就是几十分钟空转——不如早点把原因报给用户。
const embyAbortStreak = 8

func (r *runtime) stepEmbyJob(st *jobState, deadline time.Time) bool {
	j := st.Emby
	if j == nil {
		return true
	}
	cfg := r.currentConfig()
	state := r.loadEmbyState()
	if state.Synced == nil {
		state.Synced = map[string]string{}
	}
	r.updateState("running", jobProgress(st))

	// 阶段一：确定要处理的 Emby 用户
	if len(j.Users) == 0 {
		if want := strings.TrimSpace(cfg.EmbyUserID); want != "" {
			// 配置里常被填成 Emby 的登录名而不是用户 ID，直接用它拼接口会 500。
			// 先查一次用户列表按 ID 或名称匹配，查不到再按原样使用。
			j.Users = []embyUser{{ID: want}}
			if us, err := r.embyUsers(); err == nil {
				for _, u := range us {
					if u.ID == want || strings.EqualFold(u.Name, want) {
						j.Users = []embyUser{{ID: u.ID, Name: u.Name}}
						break
					}
				}
			}
		} else {
			us, err := r.embyUsers()
			if err != nil {
				r.finishJob(st, []string{"读取 Emby 用户失败：" + err.Error()}, true)
				return true
			}
			j.Users = us
		}
		if len(j.Users) == 0 {
			r.finishJob(st, []string{"Emby 没有可用用户"}, false)
			return true
		}
		r.saveJobState(st)
		if time.Now().After(deadline) {
			return false
		}
	}

	for j.Idx < len(j.Users) {
		// 达到每轮上限：结束本轮，剩余的下一轮继续（已标记的都已落盘）
		if j.Synced >= embyMaxPerRun {
			break
		}
		if j.FailStreak >= embyAbortStreak {
			break
		}
		u := j.Users[j.Idx]
		if !j.Fetched {
			movies, episodes, err := r.embyPlayed(u.ID)
			if err != nil {
				j.Errs = append(j.Errs, fmt.Sprintf("用户 %s 读取播放记录失败：%v", u.Name, err))
				j.Idx++
				j.Fetched = false
				r.saveJobState(st)
				continue
			}
			j.Movies, j.Episodes = movies, episodes
			j.Fetched = true
			r.log("info", "Emby 播放记录已读取", map[string]any{"user": u.ID, "movies": len(movies), "episodes": len(episodes)})
			r.saveJobState(st)
			if time.Now().After(deadline) {
				return false
			}
		}
		// 电影 → 看过
		for j.MoviePos < len(j.Movies) && j.Synced < embyMaxPerRun && j.FailStreak < embyAbortStreak {
			mv := j.Movies[j.MoviePos]
			key := "m:" + mv.ID
			if _, done := state.Synced[key]; !done {
				if j.MarkColl {
					if r.syncEmbyMovie(u, mv, state) {
						j.Synced++
						j.FailStreak = 0
						st.Lines = append(st.Lines, fmt.Sprintf("已标记看过《%s》", mv.Name))
					} else {
						j.FailStreak++
					}
				}
				state.Synced[key] = mv.Name
				// 逐条落盘：实例被回收时不重复处理已标记过的条目
				r.saveEmbyState(state)
			} else {
				j.Skipped++
			}
			j.MoviePos++
			if time.Now().After(deadline) {
				r.saveJobState(st)
				return false
			}
		}
		// 剧集 → 在看 / 看过
		for j.EpiPos < len(j.Episodes) && j.Synced < embyMaxPerRun && j.FailStreak < embyAbortStreak {
			ep := j.Episodes[j.EpiPos]
			key := "s:" + ep.SeriesID
			if _, done := state.Synced[key]; !done {
				series, err := r.embySeries(u.ID, ep.SeriesID)
				if err != nil {
					j.Skipped++
				} else {
					finished := series.UserData.Played
					status := "do"
					if finished && j.MarkColl {
						status = "collect"
					} else if !j.MarkDo && !finished {
						state.Synced[key] = series.Name
						r.saveEmbyState(state)
						j.EpiPos++
						continue
					}
					if r.syncEmbySeries(u, series, status, state) {
						label := "在看"
						if status == "collect" {
							label = "看过"
						}
						j.Synced++
						j.FailStreak = 0
						st.Lines = append(st.Lines, fmt.Sprintf("已标记%s《%s》", label, series.Name))
					} else {
						j.FailStreak++
					}
					state.Synced[key] = series.Name
					r.saveEmbyState(state)
				}
			} else {
				j.Skipped++
			}
			j.EpiPos++
			if time.Now().After(deadline) {
				r.saveJobState(st)
				return false
			}
		}
		// 本用户完成
		r.log("info", "Emby 用户同步完成", map[string]any{"user": u.ID, "synced": j.Synced, "skipped": j.Skipped})
		j.Idx++
		j.Fetched = false
		j.MoviePos, j.EpiPos = 0, 0
		j.Movies, j.Episodes = nil, nil
		r.saveJobState(st)
		if time.Now().After(deadline) {
			return false
		}
	}

	if len(state.Synced) > embySyncedLimit {
		for k := range state.Synced {
			if len(state.Synced) <= embySyncedTrimTo {
				break
			}
			delete(state.Synced, k)
		}
	}
	state.LastSyncAt = nowStr()
	r.saveEmbyState(state)
	st.Lines = append(st.Lines, j.Errs...)
	if j.FailStreak >= embyAbortStreak {
		st.Lines = append(st.Lines, fmt.Sprintf("连续 %d 条未能同步，本轮提前结束：请检查 Emby 地址/API Key 是否可达、豆瓣 Cookie 是否失效", j.FailStreak))
	} else if j.Synced >= embyMaxPerRun {
		st.Lines = append(st.Lines, fmt.Sprintf("本轮已同步 %d 条（每轮上限 %d），剩余条目下一轮继续", j.Synced, embyMaxPerRun))
	} else if j.Synced == 0 {
		st.Lines = append(st.Lines, "Emby 同步完成，无新记录")
	}
	r.finishJob(st, nil, false)
	return true
}
