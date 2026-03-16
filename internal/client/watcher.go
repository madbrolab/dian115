package client

import (
	"context"
	"fmt"
	"io"
	"log"
	"sync"
	"time"

	pb "strm-manager/internal/pb"
)

// FileWatcher 文件监控器（使用CD2推送消息）
type FileWatcher struct {
	cd2       *CloudDriveClient
	callbacks map[string]func(changeType, path string, isDir bool) // key: callback ID
	running   bool
	stopCh    chan struct{}
	mu        sync.RWMutex
}

// NewFileWatcher 创建文件监控器
func NewFileWatcher(cd2 *CloudDriveClient) *FileWatcher {
	return &FileWatcher{
		cd2:       cd2,
		callbacks: make(map[string]func(changeType, path string, isDir bool)),
		stopCh:    make(chan struct{}),
	}
}

// AddCallback 添加回调函数
func (w *FileWatcher) AddCallback(id string, callback func(changeType, path string, isDir bool)) {
	w.mu.Lock()
	defer w.mu.Unlock()
	w.callbacks[id] = callback
}

// RemoveCallback 移除回调函数
func (w *FileWatcher) RemoveCallback(id string) {
	w.mu.Lock()
	defer w.mu.Unlock()
	delete(w.callbacks, id)
}

// GetCallbackCount 获取回调数量
func (w *FileWatcher) GetCallbackCount() int {
	w.mu.RLock()
	defer w.mu.RUnlock()
	return len(w.callbacks)
}

// SetInterval 保留接口兼容性
func (w *FileWatcher) SetInterval(interval time.Duration) {}

// SetWorkerCount 保留接口兼容性
func (w *FileWatcher) SetWorkerCount(count int) {}

// Start 启动监控
func (w *FileWatcher) Start() {
	w.mu.Lock()
	if w.running {
		w.mu.Unlock()
		return
	}
	w.running = true
	w.stopCh = make(chan struct{})
	w.mu.Unlock()
	go w.listenPushMessages()
}

// Stop 停止监控
func (w *FileWatcher) Stop() {
	w.mu.Lock()
	defer w.mu.Unlock()
	if !w.running {
		return
	}
	w.running = false
	close(w.stopCh)
}

// IsRunning 是否运行中
func (w *FileWatcher) IsRunning() bool {
	w.mu.RLock()
	defer w.mu.RUnlock()
	return w.running
}

// listenPushMessages 监听CD2推送消息
func (w *FileWatcher) listenPushMessages() {
	log.Printf("[FileWatcher] 开始监听文件变化推送")
	maxRetries := 3
	retryCount := 0

	for {
		select {
		case <-w.stopCh:
			log.Printf("[FileWatcher] 停止监听")
			return
		default:
		}

		err := w.connectAndListen()
		if err != nil {
			retryCount++
			if retryCount >= maxRetries {
				log.Printf("[FileWatcher] 连接失败次数过多，停止重试。请检查CD2服务状态")
				return
			}
			log.Printf("[FileWatcher] 推送连接断开: %v，5秒后重连 (%d/%d)...", err, retryCount, maxRetries)
		} else {
			// 连接成功后重置重试计数
			retryCount = 0
		}

		select {
		case <-w.stopCh:
			return
		case <-time.After(5 * time.Second):
		}
	}
}

// connectAndListen 连接并监听推送消息
func (w *FileWatcher) connectAndListen() error {
	// 使用无超时context建立长连接
	ctx, cancel := context.WithCancel(context.Background())
	defer cancel()

	go func() {
		<-w.stopCh
		cancel()
	}()

	// 使用channel来实现带超时的连接尝试
	type result struct {
		stream pb.CloudDriveFileSrv_PushMessageClient
		err    error
	}
	resultCh := make(chan result, 1)

	go func() {
		stream, err := w.cd2.PushMessage(ctx)
		resultCh <- result{stream, err}
	}()

	// 等待连接结果或超时
	var stream pb.CloudDriveFileSrv_PushMessageClient
	select {
	case res := <-resultCh:
		if res.err != nil {
			return res.err
		}
		stream = res.stream
	case <-time.After(3 * time.Second):
		cancel() // 超时则取消
		return fmt.Errorf("连接超时")
	case <-w.stopCh:
		return fmt.Errorf("监控已停止")
	}

	log.Printf("[FileWatcher] 已连接到CD2推送服务")

	// 连接成功后继续使用无超时的context接收消息
	for {
		msg, err := stream.Recv()
		if err == io.EOF {
			return nil
		}
		if err != nil {
			return err
		}
		if msg.MessageType == pb.CloudDrivePushMessage_FILE_SYSTEM_CHANGE {
			change := msg.GetFileSystemChange()
			if change != nil {
				w.handleFileSystemChange(change)
			}
		}
	}
}

// handleFileSystemChange 处理文件系统变化
func (w *FileWatcher) handleFileSystemChange(change *pb.FileSystemChange) {
	path := change.Path

	log.Printf("[FileWatcher] 收到推送: type=%v, path=%s, isDir=%v", change.ChangeType, path, change.IsDirectory)

	var changeType string
	switch change.ChangeType {
	case pb.FileSystemChange_CREATE:
		changeType = "add"
	case pb.FileSystemChange_DELETE:
		changeType = "delete"
	case pb.FileSystemChange_RENAME:
		changeType = "rename"
		// rename 处理：先删除旧路径，再添加新路径
		w.notifyCallbacks("delete", path, change.IsDirectory)
		if change.NewPath != nil {
			w.notifyCallbacks("add", *change.NewPath, change.IsDirectory)
		}
		return
	default:
		return
	}

	w.notifyCallbacks(changeType, path, change.IsDirectory)
}

// notifyCallbacks 通知所有回调函数
func (w *FileWatcher) notifyCallbacks(changeType, path string, isDir bool) {
	w.mu.RLock()
	callbacks := make([]func(changeType, path string, isDir bool), 0, len(w.callbacks))
	for _, cb := range w.callbacks {
		callbacks = append(callbacks, cb)
	}
	w.mu.RUnlock()

	for _, cb := range callbacks {
		cb(changeType, path, isDir)
	}
}
