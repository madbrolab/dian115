package main

import (
	"fmt"
	"strings"
	"time"
)

// ---- 同步任务分片执行框架 ----
//
// 背景：常驻实例把一次完整同步当成一次连续计算在跑（RSS 拉取 + 逐条 TMDB
// 识别 + 逐条建订阅，实测 60–150 秒）。宿主对单次调用的等待是有预算的，
// 长时间不让出会让宿主侧的活性探测、排队调用持续超时；文档里写明「连续 8 次
// 调用失败」即判定模块状态损坏并按 restart_policy 重启 —— 表现出来就是
// 「任务跑久了插件整体崩溃重启」，且进度全丢。
//
// 因此所有同步任务都拆成小片：
//   - 每片只做 sliceBudget 之内的工作，片与片之间主动 time.Sleep 让出，
//     宿主随时可以完成探测与页面调用；
//   - 每片结束把进度落盘（Host Storage），被重启打断后下一轮从断点继续；
//   - 前台 action 只入队，真正的推进由常驻实例/后台 job 完成。

const (
	storageJobState = "job_state"

	// sliceBudget 单片墙钟预算。必须远小于宿主单次调用超时（清单 30 秒、
	// 前台实测更短），留出余量给单片里最后一项工作本身耗时。
	sliceBudget = 5 * time.Second
	// sliceYield 片间让出时长：让宿主有机会完成健康探测与其他调用。
	sliceYield = 600 * time.Millisecond
	// jobLoopBudget 一次 job/resident 调用内推进任务的总预算。远小于
	// background_timeout_ms（1 小时），避免调用本身撞上限。
	jobLoopBudget = 20 * time.Minute
	// jobStaleAfter 断点超过这个时长没有推进就丢弃，避免卡死的半成品
	// 任务一直占用调度（例如配置已改、榜单已停用）。
	jobStaleAfter = 6 * time.Hour
)

const (
	jobPhaseFetch   = "fetch"
	jobPhaseProcess = "process"
)

// jobState 分片任务的持久化状态。同一时刻只会有一种任务在进行。
type jobState struct {
	Kind      string   `json:"kind"`
	Manual    bool     `json:"manual"` // 是否来自界面「立即运行」（完成后要发通知）
	Phase     string   `json:"phase"`
	StartedAt string   `json:"started_at"`
	UpdatedAt string   `json:"updated_at"`
	Slices    int      `json:"slices"` // 已执行的片数（诊断用）
	Lines     []string `json:"lines"`

	// 榜单任务
	Rank *rankJobPayload `json:"rank,omitempty"`
	// 想看任务
	Wish *wishJobPayload `json:"wish,omitempty"`
	// Emby 任务
	Emby *embyJobPayload `json:"emby,omitempty"`
}

// rankJobPayload 榜单同步的分片状态。
type rankJobPayload struct {
	Ranks   []rankJobRank `json:"ranks"`
	Idx     int           `json:"idx"`      // 当前榜单下标
	Pos     int           `json:"pos"`      // 当前榜单已处理条目数
	NewSubs int           `json:"new_subs"` // 本次新增订阅数
	Total   int           `json:"total"`    // 待处理条目总数（进度展示）
	Done    int           `json:"done"`     // 已处理条目数（进度展示）
	// 订阅池快照：任务开始时读一次并随分片持久化，避免每片重复拉取。
	ExistingMovie []string `json:"existing_movie,omitempty"`
	ExistingTV    []string `json:"existing_tv,omitempty"`
	PoolRead      bool     `json:"pool_read"`
}

type rankJobRank struct {
	Key       string     `json:"key"`
	Name      string     `json:"name"`
	Route     string     `json:"route"`
	MediaType string     `json:"media_type"`
	Count     int        `json:"count"`
	MinVote   float64    `json:"min_vote"`
	MinYear   int        `json:"min_year"`
	Regions   []string   `json:"regions,omitempty"`
	FetchSize int        `json:"fetch_size"`
	Items     []rankItem `json:"items,omitempty"`
	// Snap 本轮该榜单累积的快照条目。放在 job state 里随分片持久化，
	// 避免中断恢复后快照被截断（快照是每轮重建的，不能只靠 storage 里的旧值）。
	Snap      []SnapshotItem `json:"snap,omitempty"`
	Fetched   bool           `json:"fetched"`
	FetchErr  string         `json:"fetch_err,omitempty"`
	Done      bool           `json:"done"`
}

// wishJobPayload 想看同步的分片状态。
type wishJobPayload struct {
	Users    []string `json:"users"`     // 待抓取的豆瓣用户
	Idx      int      `json:"idx"`       // 当前用户下标
	Page     int      `json:"page"`      // 当前用户已抓取页数
	MaxPages int      `json:"max_pages"` // 每个用户翻页数
	Days     int      `json:"days"`
	// 抓取到的想看条目（跨用户合并后），process 阶段逐条处理。
	Items     []wishItem   `json:"items,omitempty"`
	Pos       int          `json:"pos"` // 已处理条目数
	UserInfo  []DoubanUser `json:"user_info,omitempty"`
	FetchErrs []string     `json:"fetch_errs,omitempty"`
	Subs      int          `json:"subs"`
	// 订阅池快照（与榜单同步同理，避免每片重复拉取）。
	ExistingMovie []string `json:"existing_movie,omitempty"`
	ExistingTV    []string `json:"existing_tv,omitempty"`
	PoolRead      bool     `json:"pool_read"`
}

// embyJobPayload Emby 同步的分片状态。
//
// Emby 同步是最容易失控的任务：一次「已观看」查询就是 100 部电影 + 200 集剧集，
// 每条未同步条目还要走 TMDB 详情 + 豆瓣搜索 + 豆瓣标记（2~3 次外网请求）。
// 首次同步可达数百条请求、几十分钟，远超宿主单次调用的承受范围 —— 这正是
// 「任务跑久了插件就崩溃重启」的主要来源。因此它同样按片推进，且每轮限量。
type embyJobPayload struct {
	Users   []embyUser `json:"users"`
	Idx     int        `json:"idx"`  // 当前用户下标
	Fetched bool       `json:"fetched"` // 当前用户的播放记录是否已拉取
	// 当前用户的待处理条目（只保留当前用户，控制 state 体积）
	Movies   []embyItem `json:"movies,omitempty"`
	Episodes []embyItem `json:"episodes,omitempty"`
	MoviePos int        `json:"movie_pos"`
	EpiPos   int        `json:"epi_pos"`
	MarkDo   bool       `json:"mark_do"`
	MarkColl bool       `json:"mark_collect"`
	UserID   string     `json:"user_id,omitempty"` // 单用户模式（配置指定）
	Synced   int        `json:"synced"`            // 本次实际标记条数
	Skipped  int        `json:"skipped"`           // 本次跳过（已同步/未匹配）条数
	// FailStreak 连续未能成功标记的条目数。Emby 地址不可达、豆瓣 Cookie 失效时
	// 每一条都要等一次网络超时，几百条就是几十分钟的空转；连续失败到阈值就
	// 收工，把原因报给用户，而不是让任务一直挂着直到被宿主回收。
	FailStreak int      `json:"fail_streak"`
	Errs       []string `json:"errs,omitempty"`
}

// ---- 存取 ----

func (r *runtime) loadJobState() *jobState {
	var st jobState
	if ok, err := r.storageGet(storageJobState, &st); err != nil || !ok || st.Kind == "" {
		return nil
	}
	if t, err := time.ParseInLocation("2006-01-02 15:04:05", st.UpdatedAt, time.Local); err == nil {
		if time.Since(t) > jobStaleAfter {
			r.log("info", "丢弃过期的未完成任务", map[string]any{"kind": st.Kind, "updated": st.UpdatedAt})
			r.clearJobState()
			return nil
		}
	}
	return &st
}

func (r *runtime) saveJobState(st *jobState) {
	if st == nil {
		return
	}
	st.UpdatedAt = nowStr()
	_ = r.storagePut(storageJobState, st)
}

func (r *runtime) clearJobState() {
	r.clearETag(storageJobState)
	_ = r.storagePut(storageJobState, nil)
}

// activeJobKind 返回当前进行中的任务类型（空串表示无）。
func (r *runtime) activeJobKind() string {
	if st := r.loadJobState(); st != nil {
		return st.Kind
	}
	return ""
}

// ---- 推进 ----

// startJob 建立一个分片任务（若已有同类任务在进行则沿用，避免重复排队）。
func (r *runtime) startJob(kind string, manual bool) *jobState {
	if cur := r.loadJobState(); cur != nil {
		if cur.Kind == kind {
			if manual {
				cur.Manual = true
				r.saveJobState(cur)
			}
			return cur
		}
		// 另一种任务正在进行：先让位，等它跑完再排本次请求。
		return nil
	}
	st := &jobState{Kind: kind, Manual: manual, Phase: jobPhaseFetch, StartedAt: nowStr(), UpdatedAt: nowStr()}
	if err := r.prepareJob(st); err != nil {
		r.log("warning", "任务启动失败", map[string]any{"kind": kind, "reason": err.Error()})
		r.updateState("failed", requestLabel(kind)+"启动失败："+err.Error())
		return nil
	}
	r.saveJobState(st)
	return st
}

// prepareJob 建立任务骨架（不发起网络请求，网络拉取在分片里做）。
func (r *runtime) prepareJob(st *jobState) error {
	cfg := r.currentConfig()
	switch st.Kind {
	case "rank":
		ranks := make([]rankJobRank, 0, len(builtinRanks))
		for _, rd := range builtinRanks {

			rc, ok := cfg.RankConfigs[rd.Key]
			if !ok || !rc.Enabled {
				continue
			}
			ranks = append(ranks, rankJobRank{
				Key: rd.Key, Name: rd.Name, Route: rd.Route, MediaType: rd.MediaType,
				Count: rc.Count, MinVote: rc.MinVote, MinYear: rc.MinYear, Regions: rc.Regions,
				FetchSize: rankFetchLimit(rc.Count),
			})
		}
		if len(ranks) == 0 {
			return fmt.Errorf("没有启用任何榜单")
		}
		st.Rank = &rankJobPayload{Ranks: ranks}
	case "wish":
		if !cfg.WishEnabled {
			return fmt.Errorf("想看订阅未启用")
		}
		users := cfg.wishUsers()
		if len(users) == 0 {
			return fmt.Errorf("未配置豆瓣用户 ID，且 Cookie 缺少 dbcl2，无法读取想看列表")
		}
		st.Wish = &wishJobPayload{Users: users, MaxPages: cfg.WishMaxPages, Days: cfg.WishDays}
	case "emby":
		if !cfg.EmbyEnabled {
			return fmt.Errorf("Emby 同步未启用")
		}
		if strings.TrimSpace(cfg.EmbyURL) == "" || strings.TrimSpace(cfg.EmbyAPIKey) == "" {
			return fmt.Errorf("未配置 Emby 地址或 API Key")
		}
		st.Emby = &embyJobPayload{MarkDo: cfg.EmbyMarkDo, MarkColl: cfg.EmbyMarkCollect}
	case "cloud":
		// CookieCloud 同步是一次性拉取，本身只有几秒，不需要分片。
	default:
		return fmt.Errorf("不支持的任务类型 %q", kindLabel(st.Kind))
	}
	return nil
}

// runJobLoop 在一次调用内循环推进任务直到完成或预算耗尽。
// 返回是否已跑完（未跑完时下次调用/下一轮调度会从断点继续）。
func (r *runtime) runJobLoop(kind string, manual bool) bool {
	st := r.startJob(kind, manual)
	if st == nil {
		// 有别的任务在跑：把请求留在队列里，下一轮再来。
		return false
	}
	deadline := time.Now().Add(jobLoopBudget)
	for {
		done := r.runJobSlice(st)
		if done {
			return true
		}
		if time.Now().After(deadline) {
			r.log("warning", "任务单次预算耗尽，下一轮继续", map[string]any{"kind": kind, "slices": st.Slices})
			return false
		}
		// 片间让出：让宿主完成探测与其他调用，避免长时间独占。
		time.Sleep(sliceYield)
		if cur := r.loadJobState(); cur == nil || cur.Kind != kind {
			// 进度不在了（被清理或过期）：本轮到此为止，下一轮会重新排队。
			return false
		}
	}
}

// runJobSlice 执行一片，返回任务是否已全部完成。
func (r *runtime) runJobSlice(st *jobState) bool {
	st.Slices++
	deadline := time.Now().Add(sliceBudget)
	var done bool
	func() {
		defer func() {
			if rec := recover(); rec != nil {
				r.log("error", "任务分片执行异常", map[string]any{"kind": st.Kind, "reason": fmt.Sprint(rec)})
				done = true
				r.finishJob(st, []string{"内部错误：" + recToString(rec)}, true)
			}
		}()
		switch st.Kind {
		case "rank":
			done = r.stepRankJob(st, deadline)
		case "wish":
			done = r.stepWishJob(st, deadline)
		case "emby":
			done = r.stepEmbyJob(st, deadline)
		case "cloud":
			done = true
			r.finishJob(st, r.runCloudSync(), false)
		default:
			done = true
			r.clearJobState()
		}
	}()
	if done {
		return true
	}
	r.saveJobState(st)
	return false
}

func (r *runtime) finishJob(st *jobState, lines []string, failed bool) {
	if st == nil {
		return
	}
	all := append([]string{}, st.Lines...)
	all = append(all, lines...)
	msg := strings.Join(trimEmpty(all), "\n")
	if msg == "" {
		msg = requestLabel(st.Kind) + "完成（无新增内容）"
	}
	r.clearJobState()
	// 队列标记再清一次：清队列那一步可能撞上 Host Storage 的 CAS 冲突而没写成功，
	// 残留的标记会让同一个任务在下一轮又被跑一遍。
	r.clearRunRequest(st.Kind)
	if failed {
		r.updateState("failed", msg)
		return
	}
	r.markRun(st.Kind)
	r.updateState("succeeded", msg)
	if st.Manual || st.Kind == "rank" || st.Kind == "wish" || st.Kind == "emby" {
		r.notify("info", requestLabel(st.Kind)+"完成", msg)
	}
}

func trimEmpty(in []string) []string {
	out := make([]string, 0, len(in))
	for _, s := range in {
		if strings.TrimSpace(s) != "" {
			out = append(out, s)
		}
	}
	return out
}

func kindLabel(kind string) string {
	if kind == "" {
		return "任务"
	}
	return kind
}

// jobProgress 生成进度文案，供状态栏展示。
func jobProgress(st *jobState) string {
	switch st.Kind {
	case "rank":
		if st.Rank == nil {
			return "榜单订阅执行中…"
		}
		if st.Phase == jobPhaseFetch {
			return fmt.Sprintf("榜单订阅：拉取榜单 %d/%d…", st.Rank.Idx+1, len(st.Rank.Ranks))
		}
		if st.Rank.Idx < len(st.Rank.Ranks) {
			total := len(st.Rank.Ranks[st.Rank.Idx].Items)
			pos := st.Rank.Pos + 1
			if pos > total {
				pos = total
			}
			return fmt.Sprintf("榜单订阅（%d/%d：%s）第 %d/%d 条…",
				st.Rank.Idx+1, len(st.Rank.Ranks), st.Rank.Ranks[st.Rank.Idx].Name, pos, total)
		}
		return "榜单订阅：收尾中…"
	case "wish":
		if st.Wish == nil {
			return "想看订阅执行中…"
		}
		if st.Phase == jobPhaseFetch {
			return fmt.Sprintf("想看订阅：读取第 %d/%d 位用户…", st.Wish.Idx+1, len(st.Wish.Users))
		}
		total := len(st.Wish.Items)
		pos := st.Wish.Pos + 1
		if pos > total {
			pos = total
		}
		return fmt.Sprintf("想看订阅：处理第 %d/%d 条…", pos, total)
	case "emby":
		if st.Emby == nil {
			return "Emby 观影同步执行中…"
		}
		return fmt.Sprintf("Emby 观影同步：第 %d/%d 位用户…", st.Emby.Idx+1, len(st.Emby.Users))
	}
	return requestLabel(st.Kind) + "执行中…"
}
