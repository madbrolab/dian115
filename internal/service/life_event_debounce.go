package service

import (
	"log"
	"sync"
	"time"
)

// EventDebouncer 事件防抖器
type EventDebouncer struct {
	mu           sync.Mutex
	pendingPaths map[int64]map[string]bool // ruleID -> paths
	timer        *time.Timer
	delay        time.Duration
	callback     func(map[int64][]string)
}

// NewEventDebouncer 创建防抖器
func NewEventDebouncer(delay time.Duration, callback func(map[int64][]string)) *EventDebouncer {
	return &EventDebouncer{
		pendingPaths: make(map[int64]map[string]bool),
		delay:        delay,
		callback:     callback,
	}
}

// Add 添加待刷新路径
func (d *EventDebouncer) Add(ruleID int64, path string) {
	d.mu.Lock()
	defer d.mu.Unlock()

	if d.pendingPaths[ruleID] == nil {
		d.pendingPaths[ruleID] = make(map[string]bool)
	}
	d.pendingPaths[ruleID][path] = true

	if d.timer != nil {
		d.timer.Stop()
	}
	d.timer = time.AfterFunc(d.delay, d.flush)
}

// flush 执行批量刷新
func (d *EventDebouncer) flush() {
	d.mu.Lock()
	paths := make(map[int64][]string)
	for ruleID, pathMap := range d.pendingPaths {
		for path := range pathMap {
			paths[ruleID] = append(paths[ruleID], path)
		}
	}
	d.pendingPaths = make(map[int64]map[string]bool)
	d.mu.Unlock()

	if len(paths) > 0 {
		log.Printf("[Debouncer] 批量刷新 %d 个规则的路径", len(paths))
		d.callback(paths)
	}
}
