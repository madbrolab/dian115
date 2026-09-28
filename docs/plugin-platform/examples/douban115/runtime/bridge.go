package main

import (
	"context"
	"encoding/json"
	"errors"
	goruntime "runtime"
	"sync"
	"unsafe"
)

const protocol = "dian115:wasm@1"
const frameSize = 16 << 20

// hostChanMu 串行化 hostCall→hostRead 序列：宿主响应缓冲是单一共享区，
// 并发调用会把彼此的响应覆盖掉。所有对宿主的调用（含后台 goroutine）都必须持锁。
var hostChanMu sync.Mutex

type rpcError struct {
	Code    int    `json:"code"`
	Message string `json:"message"`
}

type rpcMessage struct {
	Method string          `json:"method"`
	Params json.RawMessage `json:"params"`
}

// peer 承载与宿主的 JSON-RPC 双向通道。WASM 模块没有 Socket，唯一对外通道是
// dian115.host_call / dian115.host_read 这两个宿主导入。
type peer struct{}

//go:wasmimport dian115 host_call
func hostCall(ptr, length uint32) uint32

//go:wasmimport dian115 host_read
func hostRead(ptr, capacity uint32) uint32

// call 提交一个 host.* JSON-RPC 请求并等待宿主应答。
// hostCall 写入的响应缓冲会被下一次 hostCall 覆盖，因此 hostCall→hostRead
// 必须作为临界区整体持锁执行。
func (p *peer) call(ctx context.Context, method string, params any, target any) error {
	if err := ctx.Err(); err != nil {
		return err
	}
	request, err := json.Marshal(map[string]any{"method": method, "params": params})
	if err != nil {
		return err
	}
	hostChanMu.Lock()
	size := hostCall(uint32(uintptr(unsafe.Pointer(&request[0]))), uint32(len(request)))
	var response []byte
	if size != 0 && size <= frameSize {
		response = make([]byte, size)
		if hostRead(uint32(uintptr(unsafe.Pointer(&response[0]))), size) != size {
			response = nil
		}
	}
	hostChanMu.Unlock()
	goruntime.KeepAlive(request)
	if response == nil {
		return errors.New("invalid host response size")
	}
	var envelope struct {
		Result json.RawMessage `json:"result"`
		Error  string          `json:"error"`
	}
	if err := json.Unmarshal(response, &envelope); err != nil {
		return err
	}
	if envelope.Error != "" {
		return errors.New(envelope.Error)
	}
	if target == nil {
		return nil
	}
	return json.Unmarshal(envelope.Result, target)
}

// hostCallRequest 是 host.call 的请求参数。
type hostCallRequest struct {
	Method        string            `json:"method"`
	Path          string            `json:"path"`
	Headers       map[string]string `json:"headers,omitempty"`
	BodyBase64    string            `json:"body_base64,omitempty"`
	CredentialRef string            `json:"credential_ref,omitempty"`
}

// hostCallResponse 是 host.call 的应答。
type hostCallResponse struct {
	Status     int                 `json:"status"`
	Headers    map[string][]string `json:"headers"`
	BodyBase64 string              `json:"body_base64"`
}
