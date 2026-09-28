package main

import (
	"time"
)

// ---- 跨实例状态与任务队列 ----
//
// 宿主对前台 action 有很短的硬超时（实测约 10 秒即被判 runtime_unavailable），
// 而一次完整同步（RSS 拉取 + 逐条 TMDB 识别 + 逐条建订阅），甚至单次
// CookieCloud 拉取（响应体可达数百 KB）都可能超出该预算。因此：
//   - UI 触发的「立即运行」只把请求写入 Host Storage 队列并立即返回；
//   - 常驻实例（resident，后台预算以小时计）每 30 秒检查队列并真正执行；
//   - 执行进度通过 state_public（Host Storage）跨实例回传给 UI 实例。

const (
	storageStatePublic = "state_public"
	storageRunRequests = "run_requests"
)

// StatePublic 跨实例可见的运行状态。Revision 用 unix 秒，
// 并入 state ETag，让 UI 轮询能感知到常驻实例的进度更新。
type StatePublic struct {
	Status    string `json:"status"`
	Message   string `json:"message"`
	UpdatedAt string `json:"updated_at"`
	Revision  int64  `json:"revision"`
}

// RunRequests 「立即运行」请求队列（unix 秒时间戳，0 表示无请求）。
type RunRequests struct {
	Rank  int64 `json:"rank"`
	Wish  int64 `json:"wish"`
	Emby  int64 `json:"emby"`
	Cloud int64 `json:"cloud"`
}

func (r *runtime) loadStatePublic() *StatePublic {
	var s StatePublic
	if ok, err := r.storageGet(storageStatePublic, &s); err == nil && ok && s.UpdatedAt != "" {
		return &s
	}
	return nil
}

func (r *runtime) publishState(status, message string) {
	_ = r.storagePut(storageStatePublic, StatePublic{Status: status, Message: message, UpdatedAt: nowStr(), Revision: time.Now().Unix()})
}

func (r *runtime) loadRunRequests() RunRequests {
	var q RunRequests
	_, _ = r.storageGet(storageRunRequests, &q)
	return q
}

func (r *runtime) saveRunRequests(q RunRequests) {
	_ = r.storagePut(storageRunRequests, q)
}

// requestRun 把一个「立即运行」请求入队并立刻返回。
func (r *runtime) requestRun(kind string) (any, error) {
	q := r.loadRunRequests()
	now := time.Now().Unix()
	switch kind {
	case "rank":
		q.Rank = now
	case "wish":
		q.Wish = now
	case "emby":
		q.Emby = now
	case "cloud":
		q.Cloud = now
	}
	r.saveRunRequests(q)
	r.updateState("running", requestLabel(kind)+"已排队，调度器将在约 30 秒内开始执行")
	return map[string]any{
		"status":  "accepted",
		"message": requestLabel(kind) + "已排队，正在后台执行，完成后此处会显示结果",
	}, nil
}

// runRequested 判断队列里是否已有该类型的请求。
func runRequested(q RunRequests, kind string) bool {
	switch kind {
	case "rank":
		return q.Rank != 0
	case "wish":
		return q.Wish != 0
	case "emby":
		return q.Emby != 0
	case "cloud":
		return q.Cloud != 0
	}
	return false
}

func requestLabel(kind string) string {
	switch kind {
	case "rank":
		return "榜单订阅"
	case "wish":
		return "想看订阅"
	case "emby":
		return "Emby 观影同步"
	case "cloud":
		return "CookieCloud 同步"
	}
	return "任务"
}

// clearRunRequest 清掉一个排队请求（任务即将/已经由其他路径执行）。
func (r *runtime) clearRunRequest(kind string) {
	q := r.loadRunRequests()
	switch kind {
	case "rank":
		if q.Rank == 0 {
			return
		}
		q.Rank = 0
	case "wish":
		if q.Wish == 0 {
			return
		}
		q.Wish = 0
	case "emby":
		if q.Emby == 0 {
			return
		}
		q.Emby = 0
	case "cloud":
		if q.Cloud == 0 {
			return
		}
		q.Cloud = 0
	default:
		return
	}
	r.saveRunRequests(q)
}

// drainRunRequests 由常驻实例调用：执行所有排队的「立即运行」请求。
// 返回是否有任务执行（用于日志）。
func (r *runtime) drainRunRequests() bool {
	q := r.loadRunRequests()
	if q.Rank == 0 && q.Wish == 0 && q.Emby == 0 && q.Cloud == 0 {
		return false
	}
	// 已有任务在跑：保留请求，等它结束后再处理，避免两个同步互相打断。
	if kind := r.activeJobKind(); kind != "" {
		r.log("info", "已有同步任务进行中，请求继续排队", map[string]any{"running": kind})
		return false
	}
	// 先清队列再执行，避免执行中再次入队的请求被覆盖丢失。
	remaining := q
	if q.Rank != 0 {
		remaining.Rank = 0
	}
	if q.Wish != 0 {
		remaining.Wish = 0
	}
	if q.Emby != 0 {
		remaining.Emby = 0
	}
	if q.Cloud != 0 {
		remaining.Cloud = 0
	}
	r.saveRunRequests(remaining)
	if q.Rank != 0 {
		r.runTask("rank")
	}
	if q.Wish != 0 {
		r.runTask("wish")
	}
	if q.Emby != 0 {
		r.runTask("emby")
	}
	if q.Cloud != 0 {
		r.runTask("cloud")
	}
	return true
}

// runTask 启动一个分片任务。任务本身由 runJobLoop 按片推进并回写跨实例状态；
// 若此时已有别的任务占用，请求会重新回到队列等下一轮。
func (r *runtime) runTask(kind string) {
	r.updateState("running", requestLabel(kind)+"执行中…")
	if r.runJobLoop(kind, true) {
		return
	}
	// 没跑起来（通常是别的任务仍在进行）：放回队列，下一轮再试。
	// 队列里已经有同类请求时不再重复入队，避免请求被反复叠加。
	if q := r.loadRunRequests(); !runRequested(q, kind) {
		r.requestRun(kind)
	}
}

func recToString(rec any) string {
	switch v := rec.(type) {
	case string:
		return v
	case error:
		return v.Error()
	default:
		return "unknown panic"
	}
}
