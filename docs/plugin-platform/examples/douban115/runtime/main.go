package main

import (
	"encoding/json"
	"fmt"
	"strings"
	"sync"
	"time"
	"unsafe"
)

var inputBuffer, outputBuffer []byte
var guest = newRuntime(&peer{})

//go:wasmexport dian115_alloc
func allocate(size uint32) uint32 {
	if size == 0 || size > frameSize {
		panic("invalid input size")
	}
	inputBuffer = make([]byte, size)
	return uint32(uintptr(unsafe.Pointer(&inputBuffer[0])))
}

//go:wasmexport dian115_handle
func handle(ptr, length uint32) (ret uint64) {
	// 任何 panic 都转成 JSON-RPC 错误返回，绝不让模块整体崩溃
	//（崩溃会让宿主反复重启，状态全丢且无法定位问题）。
	defer func() {
		if rec := recover(); rec != nil {
			response := map[string]any{"error": &rpcError{Code: -32603, Message: fmt.Sprintf("插件内部错误：%v", rec)}}
			outputBuffer, _ = json.Marshal(response)
			ret = uint64(uintptr(unsafe.Pointer(&outputBuffer[0])))<<32 | uint64(len(outputBuffer))
		}
	}()
	var message rpcMessage
	if length == 0 || length > frameSize {
		panic("invalid invocation size")
	}
	raw := unsafe.Slice((*byte)(unsafe.Pointer(uintptr(ptr))), int(length))
	var result any
	var rpcErr *rpcError
	if json.Unmarshal(raw, &message) != nil {
		rpcErr = &rpcError{Code: -32602, Message: "invalid invocation"}
	} else {
		result, rpcErr, _ = guest.handle(message)
	}
	response := map[string]any{}
	if rpcErr != nil {
		response["error"] = rpcErr
	} else {
		response["result"] = result
	}
	var err error
	outputBuffer, err = json.Marshal(response)
	if err != nil {
		panic(err)
	}
	// 宿主会拒绝包含 cookie/password 等字样 key 的业务 result，返回前整体清洗。
	outputBuffer = sanitizeJSON(outputBuffer)
	return uint64(uintptr(unsafe.Pointer(&outputBuffer[0])))<<32 | uint64(len(outputBuffer))
}

func main() {}

// ---- runtime ----

type runtimeState struct {
	Revision    int    `json:"revision"`
	LastStatus  string `json:"lastStatus"`
	LastMessage string `json:"lastMessage"`
}

type runtime struct {
	peer   *peer
	mu     sync.Mutex
	state  runtimeState
	config *Config
	etags  map[string]string // Host Storage key -> 最近一次 GET/PUT 看到的 ETag
	seq    int64
}

func newRuntime(channel *peer) *runtime {
	return &runtime{
		peer:  channel,
		etags: map[string]string{},
		state: runtimeState{Revision: 1, LastStatus: "ready", LastMessage: "运行时已启动"},
	}
}

func (r *runtime) currentConfig() *Config {
	r.mu.Lock()
	defer r.mu.Unlock()
	if r.config == nil {
		r.config = defaultConfig()
	}
	return r.config
}

func (r *runtime) updateState(status, message string) {
	r.mu.Lock()
	r.state.Revision++
	r.state.LastStatus = status
	r.state.LastMessage = message
	r.mu.Unlock()
	// 同步一份到 Host Storage，让常驻实例的进度对 UI 实例可见。
	r.publishState(status, message)
}

type invokeParams struct {
	Envelope struct {
		Op           string          `json:"op"`
		InvocationID string          `json:"invocation_id"`
		Payload      json.RawMessage `json:"payload"`
	} `json:"envelope"`
	Background bool `json:"background"`
}

func (r *runtime) handle(message rpcMessage) (any, *rpcError, bool) {
	switch message.Method {
	case "runtime.initialize":
		var input struct {
			Protocol string `json:"protocol"`
		}
		if json.Unmarshal(message.Params, &input) != nil || input.Protocol != protocol {
			return nil, &rpcError{Code: -32602, Message: "unsupported process protocol"}, false
		}
		r.loadConfig()
		return map[string]any{"ready": true, "protocol": protocol}, nil, false
	case "runtime.invoke":
		var input invokeParams
		if json.Unmarshal(message.Params, &input) != nil || input.Envelope.Op == "" || input.Envelope.InvocationID == "" {
			return nil, &rpcError{Code: -32602, Message: "invalid runtime.invoke params"}, false
		}
		result, err := r.invoke(input)
		if err != nil {
			return nil, &rpcError{Code: -32602, Message: err.Error()}, false
		}
		return result, nil, false
	case "runtime.shutdown":
		return map[string]any{"stopping": true}, nil, true
	default:
		return nil, &rpcError{Code: -32601, Message: "method not found"}, false
	}
}

func (r *runtime) invoke(input invokeParams) (any, error) {
	switch input.Envelope.Op {
	case "state":
		return r.stateResult(input.Envelope.Payload)
	case "action":
		return r.action(input.Envelope.InvocationID, input.Envelope.Payload)
	case "job":
		return r.job(input.Envelope.Payload)
	case "event":
		return r.event(input.Envelope.Payload)
	case "resident":
		// 常驻模式：宿主用第二个模块实例发起这一次不限时调用，
		// 插件在这里运行自己的 Cron 调度主循环。
		return r.residentLoop()
	default:
		return nil, fmt.Errorf("unsupported invocation op %q", input.Envelope.Op)
	}
}

// ---- state ----

type stateView struct {
	Revision       int                      `json:"revision"`
	LastStatus     string                   `json:"lastStatus"`
	LastMessage    string                   `json:"lastMessage"`
	Config         *Config                  `json:"config"`
	DoubanLoggedIn bool                     `json:"doubanLoggedIn"` // 键名不能包含 cookie（宿主安全字段规则）
	EmbyAPIKeySet  bool                     `json:"embyApiKeySet"`
	CloudSyncSet   bool                     `json:"cloudSyncSet"`
	RunState       RunState                 `json:"runState"`
	RankPreview    map[string][]HistoryItem `json:"rankPreview"`
	WishPreview    []HistoryItem            `json:"wishPreview"`
	WishUsers      []DoubanUser             `json:"wishUsers"` // 想看订阅的豆瓣用户（含昵称）
	EmbyPreview    map[string]any           `json:"embyPreview"`
	Ranks          []RankDef                `json:"ranks"`
}

func (r *runtime) stateResult(raw json.RawMessage) (any, error) {
	var payload struct {
		View        string `json:"view"`
		IfNoneMatch string `json:"if_none_match"`
	}
	if len(raw) > 0 {
		_ = json.Unmarshal(raw, &payload)
	}
	// 配置可能被常驻实例改写（例如后台完成的 CookieCloud 同步会把豆瓣 Cookie
	// 写进配置），这里每次状态查询都重新读取，保证界面展示与后台一致。
	r.loadConfig()
	r.mu.Lock()
	snapshot := r.state
	r.mu.Unlock()
	// 跨实例状态：常驻实例执行的同步进度写在 Host Storage 里，
	// UI 实例每次 state 调用都读取最新值，并把它的版本并入 ETag。
	pub := r.loadStatePublic()
	status, message := snapshot.LastStatus, snapshot.LastMessage
	pubRev := int64(0)
	if pub != nil && pub.Revision > 0 {
		status, message = pub.Status, pub.Message
		pubRev = pub.Revision
	}
	version := fmt.Sprintf("state-v%d-%d", snapshot.Revision, pubRev)
	etag := `"` + version + `"`
	if payload.IfNoneMatch == etag {
		return map[string]any{"not_modified": true, "etag": etag}, nil
	}

	cfg := r.currentConfig()
	view := stateView{
		Revision:       snapshot.Revision,
		LastStatus:     status,
		LastMessage:    message,
		Config:         cfg.masked(),
		DoubanLoggedIn: strings.TrimSpace(cfg.DoubanCookie) != "",
		EmbyAPIKeySet:  strings.TrimSpace(cfg.EmbyAPIKey) != "",
		CloudSyncSet:   strings.TrimSpace(cfg.CloudPasscode) != "",
		RunState:       r.loadRunState(),
		RankPreview:    map[string][]HistoryItem{},
	}
	rh := r.loadRankHistory()
	for _, rd := range builtinRanks {
		bucket := rh[rd.Key]
		if len(bucket) > previewLimit {
			bucket = bucket[len(bucket)-previewLimit:]
		}
		view.RankPreview[rd.Key] = bucket
	}
	// route 以 "/" 开头会被宿主按绝对路径规则拒绝，UI 展示用去掉前导斜杠的副本。
	view.Ranks = uiRankDefs()
	wh := r.loadWishHistory()
	view.WishPreview = make([]HistoryItem, 0, len(wh))
	for _, it := range wh {
		view.WishPreview = append(view.WishPreview, it)
	}
	if len(view.WishPreview) > previewLimit {
		view.WishPreview = view.WishPreview[len(view.WishPreview)-previewLimit:]
	}
	es := r.loadEmbyState()
	view.EmbyPreview = map[string]any{"lastSyncAt": es.LastSyncAt, "syncedCount": len(es.Synced)}
	// 想看订阅用户（配置里的顺序，昵称来自上次抓取缓存）
	view.WishUsers = r.wishUserInfos(cfg.wishUsers())
	if view.WishUsers == nil {
		view.WishUsers = []DoubanUser{}
	}

	return map[string]any{"state_version": version, "etag": etag, "state": view}, nil
}

// ---- action ----

func (r *runtime) action(invocationID string, raw json.RawMessage) (any, error) {
	var payload struct {
		ID    string          `json:"id"`
		Input json.RawMessage `json:"input"`
	}
	if json.Unmarshal(raw, &payload) != nil || payload.ID == "" {
		return nil, fmt.Errorf("invalid action payload")
	}
	switch payload.ID {
	case "save-config":
		return r.actionSaveConfig(payload.Input)
	case "run-ranks":
		return r.requestRun("rank")
	case "preview-ranks":
		return r.actionPreviewRanks()
	case "run-wish":
		return r.requestRun("wish")
	case "run-emby":
		return r.requestRun("emby")
	case "test-douban":
		return r.actionTestDouban()
	case "test-emby":
		return r.actionTestEmby()
	case "sync-cookiecloud":
		return r.actionSyncCookieCloud(payload.Input)
	case "dashboard":
		return r.actionDashboard()
	case "clear-history":
		return r.actionClearHistory(payload.Input)
	case "cron-next":
		return r.actionCronNext()
	default:
		return map[string]any{"status": "failed", "code": "unknown_action", "message": "未知动作"}, nil
	}
}

func (r *runtime) actionSaveConfig(raw json.RawMessage) (any, error) {
	var input struct {
		Config json.RawMessage `json:"config"`
	}
	if len(raw) > 0 {
		_ = json.Unmarshal(raw, &input)
	}
	if len(input.Config) == 0 {
		return map[string]any{"status": "failed", "message": "配置为空"}, nil
	}
	// 敏感字段留空时保留已保存的值（界面不回传已保存的 Cookie/Key/密码）。
	cur := r.currentConfig()
	oldCookie := cur.DoubanCookie
	oldAPIKey := cur.EmbyAPIKey
	oldPasscode := cur.CloudPasscode
	cfg := normalizeConfig(input.Config, cur)
	// Cron 表达式校验：不合法直接拒绝保存，避免常驻调度静默失效。
	for _, item := range []struct {
		name  string
		value string
	}{
		{"榜单同步 Cron", cfg.RankCron},
		{"想看同步 Cron", cfg.WishCron},
		{"Emby 同步 Cron", cfg.EmbyCron},
	} {
		if err := validateCron(item.value); err != nil {
			return map[string]any{"status": "failed", "message": fmt.Sprintf("%s 无效：%v", item.name, err)}, nil
		}
	}
	if strings.TrimSpace(cfg.DoubanCookie) == "" {
		cfg.DoubanCookie = oldCookie
	}
	if strings.TrimSpace(cfg.EmbyAPIKey) == "" {
		cfg.EmbyAPIKey = oldAPIKey
	}
	if strings.TrimSpace(cfg.CloudPasscode) == "" {
		cfg.CloudPasscode = oldPasscode
	}
	r.mu.Lock()
	r.config = cfg
	r.mu.Unlock()
	if err := r.storagePut(storageConfig, cfg); err != nil {
		return map[string]any{"status": "failed", "message": "保存失败：" + err.Error()}, nil
	}
	r.updateState("succeeded", "配置已保存")
	return map[string]any{"status": "succeeded", "message": "配置已保存"}, nil
}

// actionSyncCookieCloud 保存表单里刚填写的 CookieCloud 配置，并把一次同步请求
// 排入后台队列。
//
// CookieCloud 的响应体可达数百 KB（拉取本身要数秒），加上解密与解析后可能超过
// 前台 action 的硬超时，因此这里只入队并立即返回；真正的拉取由常驻实例执行，
// 结果通过跨实例状态回传给界面。
func (r *runtime) actionSyncCookieCloud(raw json.RawMessage) (any, error) {
	var input struct {
		URL      string `json:"cloud_url"`
		UUID     string `json:"cloud_uuid"`
		Passcode string `json:"cloud_passcode"`
	}
	if len(raw) > 0 {
		_ = json.Unmarshal(raw, &input)
	}
	cfg := r.currentConfig()
	changed := false
	if v := strings.TrimSpace(input.URL); v != "" && v != cfg.CloudURL {
		cfg.CloudURL = v
		changed = true
	}
	if v := strings.TrimSpace(input.UUID); v != "" && v != cfg.CloudUUID {
		cfg.CloudUUID = v
		changed = true
	}
	if v := strings.TrimSpace(input.Passcode); v != "" && v != cfg.CloudPasscode {
		cfg.CloudPasscode = v
		changed = true
	}
	if changed {
		r.mu.Lock()
		r.config = cfg
		r.mu.Unlock()
		// 落盘后常驻实例下一轮 loadConfig 才能拿到最新配置。
		if err := r.storagePut(storageConfig, cfg); err != nil {
			return map[string]any{"status": "failed", "message": "保存 CookieCloud 配置失败：" + err.Error()}, nil
		}
	}
	if strings.TrimSpace(cfg.CloudURL) == "" {
		return map[string]any{"status": "failed", "message": "请先填写 CookieCloud 服务器地址"}, nil
	}
	if strings.TrimSpace(cfg.CloudUUID) == "" || strings.TrimSpace(cfg.CloudPasscode) == "" {
		return map[string]any{"status": "failed", "message": "请先填写 CookieCloud UUID 与密码"}, nil
	}
	return r.requestRun("cloud")
}

// actionPreviewRanks 预览榜单原始条目。
//
// 前台 action 的预算只有几十秒，而拉一个榜单 RSS 就要几秒，因此这里限制
// 单次预览的榜单数量：超出的榜单提示用户分批查看，避免整次调用被超时掐断。
func (r *runtime) actionPreviewRanks() (any, error) {
	cfg := r.currentConfig()
	out := map[string]any{}
	previewed, skipped := 0, 0
	for _, rd := range builtinRanks {
		rc, ok := cfg.RankConfigs[rd.Key]
		if !ok || !rc.Enabled {
			continue
		}
		if previewed >= previewRankLimit {
			skipped++
			continue
		}
		previewed++
		items, err := r.fetchRank(rd.Route, rankFetchLimit(rc.Count), rd.MediaType)
		if err != nil {
			out[rd.Key] = map[string]any{"error": err.Error()}
			continue
		}
		preview := make([]map[string]any, 0, len(items))
		for _, it := range items {
			preview = append(preview, map[string]any{
				"title":      it.Title,
				"year":       it.Year,
				"douban_id":  it.DoubanID,
				"media_type": it.MediaType,
				"link":       it.Link,
			})
		}
		out[rd.Key] = map[string]any{"name": rd.Name, "items": preview}
	}
	msg := fmt.Sprintf("榜单预览完成（%d 个榜单）", previewed)
	if skipped > 0 {
		msg += fmt.Sprintf("；还有 %d 个榜单未预览（单次上限 %d 个，避免超时）", skipped, previewRankLimit)
	}
	return map[string]any{"status": "succeeded", "message": msg, "ranks": out}, nil
}

// previewRankLimit 单次预览的榜单数量上限（前台调用预算有限）。
const previewRankLimit = 2

func (r *runtime) actionTestDouban() (any, error) {
	cfg := r.currentConfig()
	users := cfg.wishUsers()
	res := map[string]any{
		"loggedIn":  cfg.hasCookie(),
		"userCount": len(users),
		"userIds":   users,
	}
	if len(users) == 0 {
		res["status"] = "failed"
		res["message"] = "未配置豆瓣 Cookie / 用户 ID（可从浏览器复制，或通过 CookieCloud 同步）"
		return res, nil
	}
	details := make([]map[string]any, 0, len(users))
	infos := make([]DoubanUser, 0, len(users))
	total := 0
	var firstErr error
	for _, u := range users {
		d := map[string]any{"userId": u}
		items, info, err := r.getWishItemsWithUser(u, 1)
		if err != nil {
			d["error"] = err.Error()
			if firstErr == nil {
				firstErr = err
			}
		} else {
			d["count"] = len(items)
			total += len(items)
			if info.ID == "" {
				info.ID = u
			}
			d["name"] = info.Name
			d["display"] = userDisplay(info)
			infos = append(infos, info)
		}
		details = append(details, d)
	}
	// 测试连接时顺带刷新昵称缓存，界面即可把用户 ID 显示成用户名
	r.saveWishUsers(mergeWishUsers(r.loadWishUsers(), infos))
	res["users"] = details
	if firstErr != nil && total == 0 {
		res["status"] = "failed"
		res["message"] = "全部用户连接失败：" + firstErr.Error()
		return res, nil
	}
	res["status"] = "succeeded"
	label := wishUserNames(infos, users)
	var msg string
	if len(users) == 1 {
		msg = fmt.Sprintf("连接成功（%s），读取到 %d 条想看", label, total)
	} else {
		msg = fmt.Sprintf("连接成功，%d 个用户（%s）共读取到 %d 条想看（首页）", len(users), label, total)
	}
	if failed := len(users) - len(infos); failed > 0 {
		msg += fmt.Sprintf("；其中 %d 个用户读取失败", failed)
	}
	res["message"] = msg
	res["sampleCount"] = total
	return res, nil
}

func (r *runtime) actionTestEmby() (any, error) {
	cfg := r.currentConfig()
	if strings.TrimSpace(cfg.EmbyURL) == "" || strings.TrimSpace(cfg.EmbyAPIKey) == "" {
		return map[string]any{"status": "failed", "message": "未配置 Emby 地址或 API Key"}, nil
	}
	users, err := r.embyUsers()
	if err != nil {
		return map[string]any{"status": "failed", "message": "连接失败：" + err.Error()}, nil
	}
	names := make([]string, 0, len(users))
	for _, u := range users {
		names = append(names, u.Name)
	}
	return map[string]any{"status": "succeeded", "message": fmt.Sprintf("连接成功，%d 个用户", len(users)), "users": names}, nil
}

// actionCronNext 返回三个同步任务的 cron 与下次触发时间，供界面展示与校验。
func (r *runtime) actionCronNext() (any, error) {
	cfg := r.currentConfig()
	out := map[string]any{"status": "succeeded"}
	now := time.Now()
	for _, item := range []struct {
		name string
		expr string
		key  string
	}{
		{"榜单", cfg.RankCron, "rank"},
		{"想看", cfg.WishCron, "wish"},
		{"Emby", cfg.EmbyCron, "emby"},
	} {
		spec, err := parseCron(item.expr)
		if err != nil {
			out[item.key] = map[string]any{"cron": item.expr, "error": err.Error()}
			continue
		}
		next := spec.nextFire(now)
		entry := map[string]any{"cron": item.expr}
		if !next.IsZero() {
			entry["next"] = next.Format("2006-01-02 15:04")
		}
		out[item.key] = entry
	}
	out["message"] = "已计算下次触发时间"
	return out, nil
}

// ---- job ----

// jobKindOf 把定时 job 的 id 映射到分片任务类型。
func jobKindOf(id string) string {
	switch id {
	case "rank-sync":
		return "rank"
	case "wish-sync":
		return "wish"
	case "emby-sync":
		return "emby"
	}
	return ""
}

func (r *runtime) job(raw json.RawMessage) (any, error) {
	var payload struct {
		ID string `json:"id"`
	}
	if json.Unmarshal(raw, &payload) != nil {
		return map[string]any{"status": "skipped", "message": "无效任务"}, nil
	}
	// 同步任务统一走分片循环：每次调用只推进几秒的工作，进度落盘，
	// 未跑完的部分由下一轮调度继续（见 jobslice.go）。
	//
	// 宿主若把定时 job 派给了服务实例，而常驻实例正跑着另一个任务，
	// 这里直接跳过：两个实例同时推进两份进度会互相覆盖。
	// 同一种任务不算冲突——那正是断点续跑的路径。
	if running := r.activeJobKind(); running != "" && running != jobKindOf(payload.ID) {
		return map[string]any{"status": "skipped", "message": requestLabel(running) + "仍在进行中，本次跳过"}, nil
	}
	switch payload.ID {
	case "rank-sync":
		r.clearRunRequest("rank")
		r.updateState("running", "定时榜单订阅执行中")
		r.runJobLoop("rank", false)
	case "wish-sync":
		r.clearRunRequest("wish")
		r.updateState("running", "定时想看订阅执行中")
		r.runJobLoop("wish", false)
	case "emby-sync":
		r.clearRunRequest("emby")
		r.updateState("running", "定时 Emby 观影同步执行中")
		r.runJobLoop("emby", false)
	case "cloud-sync":
		r.clearRunRequest("cloud")
		r.updateState("running", "CookieCloud 同步执行中")
		lines := r.runCloudSync()
		r.updateState("succeeded", strings.Join(lines, "\n"))
	default:
		return map[string]any{"status": "skipped", "message": "未声明的任务"}, nil
	}
	return map[string]any{"status": "accepted"}, nil
}

// ---- event ----

func (r *runtime) event(raw json.RawMessage) (any, error) {
	// 本插件不注册事件与 Telegram 路由，仅确认收到。
	return map[string]any{"accepted": true}, nil
}

// ---- config 加载 ----

func (r *runtime) loadConfig() {
	cfg := defaultConfig()
	if ok, err := r.storageGet(storageConfig, cfg); err == nil && ok {
		cfg = normalizeConfig(nil, cfg)
	} else if err != nil {
		cfg = defaultConfig()
	}
	r.mu.Lock()
	r.config = cfg
	r.mu.Unlock()
	// 进程重启后，如果跨实例状态还停留在「运行中」且已超过 5 分钟没有心跳
	//（任务执行期间每条都会刷新），说明上次任务被超时/崩溃中断，标记为失败。
	if pub := r.loadStatePublic(); pub != nil && pub.Status == "running" {
		if t, err := time.ParseInLocation("2006-01-02 15:04:05", pub.UpdatedAt, time.Local); err == nil {
			if time.Since(t) > 5*time.Minute {
				r.publishState("failed", "上次任务执行被中断（进程重启），可重新运行")
			}
		}
	}
}
