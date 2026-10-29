package main

import (
	"context"
	"encoding/base64"
	"errors"
	goruntime "runtime"
	"strings"
	"sync"
	"time"
	"unsafe"

	"example.com/dian115-plugin-sdk/hostapi"
	"example.com/dian115-plugin-sdk/pluginjson"
)

const protocol = "dian115:wasm@1"
const frameSize = 16 << 20

type rpcError struct {
	Code    int
	Message string
}
type peer struct{}

//go:wasmimport dian115 host_call
func hostCall(ptr, length uint32) uint32

//go:wasmimport dian115 host_read
func hostRead(ptr, capacity uint32) uint32

// call sends one JSON-RPC request to the host and returns the raw result. The
// caller reads only the fields it needs, so the runtime never has to decode a
// whole document or pull in a general JSON decoder.
func (p *peer) call(ctx context.Context, method string, params any) (pluginjson.Raw, error) {
	if err := ctx.Err(); err != nil {
		return nil, err
	}
	request, err := pluginjson.Encode(map[string]any{"method": method, "params": params})
	if err != nil {
		return nil, err
	}
	size := hostCall(uint32(uintptr(unsafe.Pointer(&request[0]))), uint32(len(request)))
	goruntime.KeepAlive(request)
	if size == 0 || size > frameSize {
		return nil, errors.New("invalid host response size")
	}
	response := make([]byte, size)
	if hostRead(uint32(uintptr(unsafe.Pointer(&response[0]))), size) != size {
		return nil, errors.New("host response read failed")
	}
	if text := pluginjson.Text(pluginjson.Field(response, "error")); text != "" {
		return nil, errors.New(text)
	}
	return pluginjson.Field(response, "result"), nil
}

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
func handle(ptr, length uint32) uint64 {
	if length == 0 || length > frameSize {
		panic("invalid invocation size")
	}
	raw := unsafe.Slice((*byte)(unsafe.Pointer(uintptr(ptr))), int(length))
	var result any
	var rpcErr *rpcError
	method := pluginjson.Text(pluginjson.Field(raw, "method"))
	if method == "" {
		rpcErr = &rpcError{-32602, "invalid invocation"}
	} else {
		result, rpcErr, _ = guest.handle(method, pluginjson.Field(raw, "params"))
	}
	response := map[string]any{}
	if rpcErr != nil {
		response["error"] = map[string]any{"code": rpcErr.Code, "message": rpcErr.Message}
	} else {
		response["result"] = result
	}
	var err error
	outputBuffer, err = pluginjson.Encode(response)
	if err != nil {
		panic(err)
	}
	return uint64(uintptr(unsafe.Pointer(&outputBuffer[0])))<<32 | uint64(len(outputBuffer))
}

type runtimeState struct {
	Revision    int
	ActionCount int
	EventCount  int
	WatchActive bool
	LastStatus  string
	LastMessage string
}

// encode renders the state snapshot in the JSON shape the host validates.
func (s runtimeState) encode() map[string]any {
	return map[string]any{
		"revision": s.Revision, "actionCount": s.ActionCount, "eventCount": s.EventCount,
		"watchActive": s.WatchActive, "lastStatus": s.LastStatus, "lastMessage": s.LastMessage,
	}
}

type runtime struct {
	peer  *peer
	mu    sync.Mutex
	state runtimeState
}

func newRuntime(channel *peer) *runtime {
	return &runtime{peer: channel, state: runtimeState{Revision: 1, LastStatus: "ready", LastMessage: "运行时已启动"}}
}

func (r *runtime) handle(method string, params pluginjson.Raw) (any, *rpcError, bool) {
	switch method {
	case "runtime.initialize":
		if pluginjson.Text(pluginjson.Field(params, "protocol")) != protocol {
			return nil, &rpcError{Code: -32602, Message: "unsupported runtime protocol"}, false
		}
		// Telegram 路由写在 manifest 的 telegram 段里，由宿主在安装时登记，
		// 所以这里不需要（也不允许）再向宿主注册。宿主可以在插件未加载时
		// 完成命令匹配，再把插件加载起来处理消息。
		return map[string]any{"ready": true, "protocol": protocol}, nil, false
	case "runtime.invoke":
		envelope := pluginjson.Field(params, "envelope")
		op := pluginjson.Text(pluginjson.Field(envelope, "op"))
		invocationID := pluginjson.Text(pluginjson.Field(envelope, "invocation_id"))
		if op == "" || invocationID == "" {
			return nil, &rpcError{Code: -32602, Message: "invalid runtime.invoke params"}, false
		}
		result, err := r.invoke(op, invocationID, pluginjson.Field(envelope, "payload"))
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

func (r *runtime) invoke(op, invocationID string, payload pluginjson.Raw) (any, error) {
	switch op {
	case "state":
		return r.stateResult(payload)
	case "action":
		return r.action(invocationID, payload)
	case "job":
		return r.job(invocationID, payload)
	case "recover":
		return r.recoverJob(invocationID, payload)
	case "event":
		return r.event(payload)
	case "resident":
		// 常驻模式：宿主用第二个模块实例发起这一次不限时调用，插件在此运行
		// 自己的主循环。返回错误会被视为崩溃并触发重启。
		return r.residentLoop()
	default:
		return nil, errors.New("unsupported invocation op: " + op)
	}
}

// residentLoop 是常驻模块的主循环。注意常驻模块是独立的第二个实例，与应答
// 普通调用的服务模块不共享内存；需要展示给界面或跨模块交换的状态请通过
// Host Storage 持久化。
func (r *runtime) residentLoop() (any, error) {
	r.log("info", "resident loop started", nil)
	r.sendCallbackNotification()
	ticker := time.NewTicker(time.Minute)
	defer ticker.Stop()
	beats := 0
	for range ticker.C {
		beats++
		at := time.Now().UTC().Format(time.RFC3339Nano)
		value, _ := pluginjson.Encode(map[string]any{"beats": beats, "at": at})
		body, _ := pluginjson.Encode(map[string]any{"value": pluginjson.Raw(value)})
		_, err := r.hostCall(map[string]any{
			"method": "PUT", "path": "/api/plugin-runtime/storage/resident-heartbeat",
			"headers":     map[string]string{"content-type": "application/json", "idempotency-key": "resident-heartbeat-" + at},
			"body_base64": base64.RawStdEncoding.EncodeToString(body),
		})
		if err != nil {
			r.log("warning", "resident heartbeat was not saved", map[string]any{"reason": err.Error()})
		}
	}
	return map[string]any{"status": "stopped"}, nil
}

// sendCallbackNotification 演示带回调按钮的出站通知：用户点击“查询状态”后，
// 宿主会把 telegram.callback 事件投递回本插件。
func (r *runtime) sendCallbackNotification() {
	body, _ := pluginjson.Encode(map[string]any{
		"level": "info", "title": "示例插件常驻模块已启动",
		"body":       "常驻循环正在后台运行，点击按钮可随时查询运行状态。",
		"dedupe_key": "resident-loop-started",
		"buttons":    []any{[]any{map[string]any{"text": "查询状态", "callback_data": "status"}}},
	})
	_, err := r.hostCall(map[string]any{
		"method": "POST", "path": "/api/notifications/plugin",
		"headers":     map[string]string{"content-type": "application/json", "idempotency-key": "resident-loop-started"},
		"body_base64": base64.RawStdEncoding.EncodeToString(body),
	})
	if err != nil {
		r.log("warning", "resident startup notification was not sent", map[string]any{"reason": err.Error()})
	}
}

func (r *runtime) stateResult(payload pluginjson.Raw) (any, error) {
	if pluginjson.Field(payload, "view") == nil {
		return nil, errors.New("invalid state payload")
	}
	r.mu.Lock()
	snapshot := r.state
	r.mu.Unlock()
	version := "state-v" + pluginjson.Number(snapshot.Revision)
	etag := `"` + version + `"`
	if pluginjson.Text(pluginjson.Field(payload, "if_none_match")) == etag {
		return map[string]any{"not_modified": true, "etag": etag}, nil
	}
	return map[string]any{"state_version": version, "etag": etag, "state": snapshot.encode()}, nil
}

func (r *runtime) action(invocationID string, payload pluginjson.Raw) (any, error) {
	actionID := pluginjson.Text(pluginjson.Field(payload, "id"))
	input := pluginjson.Field(payload, "input")
	if actionID == "" {
		return nil, errors.New("invalid action payload")
	}
	switch actionID {
	case "refresh":
		r.updateState("succeeded", "运行时状态已刷新", false)
		return map[string]any{"status": "succeeded", "message": "运行时状态已刷新"}, nil
	case "send-test":
		body, _ := pluginjson.Encode(map[string]any{
			"level": "success", "title": "插件测试通知", "body": "完整插件示例已成功调用宿主通知接口。",
			"dedupe_key": invocationID,
		})
		response, err := r.hostCall(map[string]any{
			"method": "POST", "path": "/api/notifications/plugin",
			"headers":     map[string]string{"content-type": "application/json", "idempotency-key": "example-notify-" + invocationID},
			"body_base64": base64.RawStdEncoding.EncodeToString(body),
		})
		status := hostStatus(response)
		if err != nil || status >= 400 {
			message := "宿主通知调用失败"
			if err != nil {
				message = err.Error()
			}
			r.updateState("failed", message, false)
			return map[string]any{"status": "failed", "message": message, "hostStatus": status}, nil
		}
		r.updateState("succeeded", "测试通知已发送", false)
		return map[string]any{"status": "succeeded", "message": "测试通知已发送", "hostStatus": status}, nil
	case "storage-demo":
		return r.storageDemo(invocationID)
	case "external-link":
		return map[string]any{"status": "succeeded", "message": "外部页面地址已生成", "url": "https://example.com/oauth/start"}, nil
	case "fetch-local":
		target := strings.TrimSpace(pluginjson.Text(pluginjson.Field(input, "url")))
		if target == "" {
			return map[string]any{"status": "failed", "message": "URL 不能为空"}, nil
		}
		client := hostapi.Client{Call: r.peer.call}
		ctx, cancel := context.WithTimeout(context.Background(), 180*time.Second)
		defer cancel()
		session := pluginjson.Text(pluginjson.Field(input, "session"))
		response, err := client.HTTP(ctx, hostapi.HTTPRequest{Method: "GET", URL: target, Session: session, TimeoutMS: 120000, Headers: map[string]string{"accept": "application/json, text/plain;q=0.9"}})
		status := response.Status
		if err != nil || status >= 400 {
			message := "宿主网络 Broker 调用失败"
			if err != nil {
				message = err.Error()
			}
			r.updateState("failed", message, false)
			return map[string]any{"status": "failed", "message": message, "hostStatus": status}, nil
		}
		r.updateState("succeeded", "宿主 Broker 返回 HTTP "+pluginjson.Number(status), false)
		return map[string]any{"status": "succeeded", "message": "宿主 Broker 请求完成", "hostStatus": status, "cache": response.Network.Cache, "durationMS": response.Network.DurationMS, "reusedConnection": response.Network.ReusedConnection}, nil
	case "site-list", "site-save", "site-delete", "site-login", "cookie-save", "cookiecloud-info", "cookiecloud-import", "cookiecloud-export", "cookies-clear", "http-render", "http-batch", "http-cache-info", "http-cache-clear":
		return r.httpSessionAction(actionID, invocationID, input)
	case "create-watch":
		watchPath := strings.TrimSpace(pluginjson.Text(pluginjson.Field(input, "path")))
		if watchPath == "" {
			return map[string]any{"status": "failed", "message": "目录路径不能为空"}, nil
		}
		body, _ := pluginjson.Encode(map[string]any{
			"source":      map[string]any{"kind": "host_path", "path": watchPath},
			"event_topic": "files.changed", "recursive": true, "interval_seconds": 30,
		})
		response, err := r.hostCall(map[string]any{
			"method": "POST", "path": "/api/plugin-runtime/watches",
			"headers":     map[string]string{"content-type": "application/json", "idempotency-key": "example-watch-" + invocationID},
			"body_base64": base64.RawStdEncoding.EncodeToString(body),
		})
		status := hostStatus(response)
		if err != nil || status >= 400 {
			message := "目录监控创建失败"
			if err != nil {
				message = err.Error()
			}
			r.updateState("failed", message, false)
			return map[string]any{"status": "failed", "message": message, "hostStatus": status}, nil
		}
		r.updateState("succeeded", "目录监控已创建", true)
		return map[string]any{"status": "succeeded", "message": "目录监控已创建", "hostStatus": status}, nil
	default:
		return map[string]any{"status": "failed", "code": "unknown_action", "message": "未知动作"}, nil
	}
}

func (r *runtime) storageDemo(invocationID string) (any, error) {
	client := hostapi.Client{Call: r.peer.call}
	// The synchronous reactor call is bounded by the host invocation budget.
	ctx := context.Background()
	current, etag, err := client.StorageGet(ctx, "example")
	var problem *hostapi.Problem
	if err != nil && !(errors.As(err, &problem) && problem.Status == 404) {
		return map[string]any{"status": "failed", "message": err.Error()}, nil
	}
	if err == nil && pluginjson.Text(pluginjson.Field(current, "operation_ref")) == invocationID {
		r.updateState("succeeded", "Host Storage 已保存该业务数据", false)
		return map[string]any{"status": "succeeded", "message": "Host Storage 已保存该业务数据"}, nil
	}
	value, err := pluginjson.Encode(map[string]any{"schema_version": 1, "saved_by": "complete-plugin", "operation_ref": invocationID})
	if err != nil {
		return nil, err
	}
	key, err := hostapi.Key("complete-storage", invocationID)
	if err != nil {
		return nil, err
	}
	if _, _, err := client.StoragePut(ctx, "example", value, etag, key); err != nil {
		return map[string]any{"status": "failed", "message": err.Error()}, nil
	}
	r.updateState("succeeded", "Host Storage 已使用 ETag/CAS 保存示例数据", false)
	return map[string]any{"status": "succeeded", "message": "Host Storage 已保存示例数据"}, nil
}

// hostStatus reads the HTTP status of a host.call response envelope.
func hostStatus(response pluginjson.Raw) int {
	return pluginjson.Int(pluginjson.Field(response, "status"))
}

func (r *runtime) job(invocationID string, payload pluginjson.Raw) (any, error) {
	if pluginjson.Text(pluginjson.Field(payload, "id")) != "refresh" {
		return map[string]any{"status": "skipped", "message": "未声明的任务"}, nil
	}
	client := hostapi.Client{Call: r.peer.call}
	ctx := context.Background()
	if pluginjson.Text(pluginjson.Field(payload, "job_ref")) != "" {
		checkpoint, _ := pluginjson.Encode(map[string]any{"schema_version": 1, "cursor": 1})
		if err := client.SaveCheckpoint(ctx, checkpoint, 50); err != nil {
			return nil, err
		}
		current, etag, err := client.StorageGet(ctx, "jobs.refresh")
		var problem *hostapi.Problem
		if err != nil && !(errors.As(err, &problem) && problem.Status == 404) {
			return nil, err
		}
		if pluginjson.Text(pluginjson.Field(current, "operation_ref")) != invocationID {
			value, _ := pluginjson.Encode(map[string]any{"schema_version": 1, "operation_ref": invocationID})
			key, err := hostapi.Key("refresh-job", invocationID)
			if err != nil {
				return nil, err
			}
			if _, _, err := client.StoragePut(ctx, "jobs.refresh", value, etag, key); err != nil {
				return nil, err
			}
		}
		checkpoint, _ = pluginjson.Encode(map[string]any{"schema_version": 1, "cursor": 2})
		if err := client.SaveCheckpoint(ctx, checkpoint, 100); err != nil {
			return nil, err
		}
	}
	r.updateState("succeeded", "定时刷新已接受", false)
	return map[string]any{"status": "accepted", "message": "定时刷新已接受"}, nil
}

// The verification phase performs only a GET. Its stable operation marker
// stands in for an upstream fact; real plugins query their actual upstream.
func (r *runtime) recoverJob(invocationID string, payload pluginjson.Raw) (any, error) {
	if pluginjson.Text(pluginjson.Field(payload, "handler")) != "refresh-recover" {
		return map[string]any{"decision": "attention_required"}, nil
	}
	client := hostapi.Client{Call: r.peer.call}
	value, _, err := client.StorageGet(context.Background(), "jobs.refresh")
	if err == nil && pluginjson.Text(pluginjson.Field(value, "operation_ref")) == invocationID {
		return map[string]any{"decision": "complete", "result": map[string]any{"status": "accepted", "message": "已核对持久结果，无需重复写入"}}, nil
	}
	var problem *hostapi.Problem
	if err != nil && !(errors.As(err, &problem) && problem.Status == 404) {
		return nil, err
	}
	checkpoint := pluginjson.Field(payload, "checkpoint")
	if len(checkpoint) == 0 {
		checkpoint = pluginjson.Raw(`null`)
	}
	return map[string]any{"decision": "resume", "checkpoint": checkpoint}, nil
}

func (r *runtime) event(payload pluginjson.Raw) (any, error) {
	topic := pluginjson.Text(pluginjson.Field(payload, "topic"))
	data := pluginjson.Field(payload, "data")
	if topic == "" {
		return nil, errors.New("invalid event payload")
	}
	if topic == "telegram.message" {
		match := pluginjson.Field(data, "match")
		matchType := pluginjson.Text(pluginjson.Field(match, "type"))
		matchValue := pluginjson.Text(pluginjson.Field(match, "value"))
		r.updateState("succeeded", "已处理 Telegram "+matchType, false)
		return map[string]any{
			"handled": true,
			"reply": map[string]any{
				"format": "plain", "text": "完整插件示例已收到：" + matchValue,
				// 第一行演示回调按钮（点击后宿主投递 telegram.callback 事件），
				// 第二行演示普通链接按钮。
				"buttons": []any{
					[]any{map[string]any{"text": "查询状态", "callback_data": "status"}},
					[]any{map[string]any{"text": "查看文档", "url": "https://example.com/plugins/complete-plugin"}},
				},
			},
		}, nil
	}
	if topic == "telegram.callback" {
		// 回调按钮点击：data.callback.data 是插件创建按钮时附带的原样负载。
		if pluginjson.Text(pluginjson.Field(pluginjson.Field(data, "callback"), "data")) != "status" {
			return map[string]any{"handled": true, "answer": "未知操作", "alert": true}, nil
		}
		r.mu.Lock()
		snapshot := r.state
		r.mu.Unlock()
		return map[string]any{
			"handled": true,
			"answer":  "示例插件运行正常",
			"reply": map[string]any{
				"format": "plain",
				"text": "运行状态：" + snapshot.LastStatus + "\n最近消息：" + snapshot.LastMessage +
					"\n动作次数：" + pluginjson.Number(snapshot.ActionCount) + "，事件次数：" + pluginjson.Number(snapshot.EventCount),
				"buttons": []any{[]any{map[string]any{"text": "再次查询", "callback_data": "status"}}},
			},
		}, nil
	}
	r.mu.Lock()
	r.state.EventCount++
	r.state.Revision++
	r.state.LastStatus = "succeeded"
	r.state.LastMessage = "已接收事件：" + topic
	r.mu.Unlock()
	return map[string]any{"accepted": true}, nil
}

func (r *runtime) updateState(status, message string, watchActive bool) {
	r.mu.Lock()
	r.state.Revision++
	r.state.ActionCount++
	r.state.LastStatus = status
	r.state.LastMessage = message
	if watchActive {
		r.state.WatchActive = true
	}
	r.mu.Unlock()
}

func (r *runtime) hostCall(request map[string]any) (pluginjson.Raw, error) {
	ctx, cancel := context.WithTimeout(context.Background(), 20*time.Second)
	defer cancel()
	raw, err := r.peer.call(ctx, "host.call", request)
	if err == nil {
		err = hostapi.CheckResponse(raw)
	}
	return raw, err
}

func (r *runtime) log(level, message string, fields map[string]any) {
	ctx, cancel := context.WithTimeout(context.Background(), 3*time.Second)
	defer cancel()
	_, _ = r.peer.call(ctx, "host.log", map[string]any{"level": level, "message": message, "fields": fields})
}

func main() {}
