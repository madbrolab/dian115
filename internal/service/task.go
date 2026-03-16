package service

import (
	"sync"
	"time"
)

// TaskStatus 任务状态
type TaskStatus string

const (
	TaskStatusPending   TaskStatus = "pending"   // 等待中
	TaskStatusRunning   TaskStatus = "running"   // 运行中
	TaskStatusCompleted TaskStatus = "completed" // 已完成
	TaskStatusFailed    TaskStatus = "failed"    // 失败
	TaskStatusCancelled TaskStatus = "cancelled" // 已取消
)

// TaskType 任务类型
type TaskType string

const (
	TaskTypeSync      TaskType = "sync"       // 同步任务
	TaskTypeSyncAll   TaskType = "sync_all"   // 全量同步
	TaskTypeArchive   TaskType = "archive"    // 归档任务
	TaskTypeBuildTree TaskType = "build_tree" // 构建目录树
)

// SyncType 同步类型
type SyncType string

const (
	SyncTypeFull        SyncType = "full"        // 全量同步
	SyncTypeIncremental SyncType = "incremental" // 增量同步
)

// Task 后台任务
type Task struct {
	ID           string     `json:"id"`
	Type         TaskType   `json:"type"`
	Name         string     `json:"name"`
	Status       TaskStatus `json:"status"`
	SyncType     SyncType   `json:"sync_type"`     // 同步类型
	RuleID       int64      `json:"rule_id"`       // 关联规则ID
	RuleName     string     `json:"rule_name"`     // 规则名称
	TotalFiles   int        `json:"total_files"`   // 总文件数
	SyncedFiles  int        `json:"synced_files"`  // 已同步文件数
	FailedFiles  int        `json:"failed_files"`  // 失败文件数
	DeletedFiles int        `json:"deleted_files"` // 删除文件数
	Progress     float64    `json:"progress"`      // 进度百分比
	Message      string     `json:"message"`       // 当前状态消息
	Error        string     `json:"error"`         // 错误信息
	Logs         []string   `json:"logs"`          // 实时日志
	StartTime    time.Time  `json:"start_time"`
	EndTime      time.Time  `json:"end_time,omitempty"`
	CreatedAt    time.Time  `json:"created_at"`

	// 内部使用
	cancelCh chan struct{} `json:"-"`
	mu       sync.RWMutex  `json:"-"`
}

// AddLog 添加日志
func (t *Task) AddLog(log string) {
	t.mu.Lock()
	defer t.mu.Unlock()
	// 最多保留100条日志
	if len(t.Logs) >= 100 {
		t.Logs = t.Logs[1:]
	}
	t.Logs = append(t.Logs, log)
}

// TaskManager 任务管理器
type TaskManager struct {
	tasks    map[string]*Task
	mu       sync.RWMutex
	maxTasks int // 最大保留任务数
}

// NewTaskManager 创建任务管理器
func NewTaskManager() *TaskManager {
	return &TaskManager{
		tasks:    make(map[string]*Task),
		maxTasks: 100, // 最多保留100个任务记录
	}
}

// CreateTask 创建任务
func (m *TaskManager) CreateTask(taskType TaskType, name string, ruleID int64, ruleName string, syncType SyncType) *Task {
	m.mu.Lock()
	defer m.mu.Unlock()

	task := &Task{
		ID:        generateTaskID(),
		Type:      taskType,
		Name:      name,
		Status:    TaskStatusPending,
		SyncType:  syncType,
		RuleID:    ruleID,
		RuleName:  ruleName,
		CreatedAt: time.Now(),
		cancelCh:  make(chan struct{}),
	}

	m.tasks[task.ID] = task
	m.cleanup()

	return task
}

// GetTask 获取任务
func (m *TaskManager) GetTask(id string) *Task {
	m.mu.RLock()
	defer m.mu.RUnlock()
	return m.tasks[id]
}

// GetAllTasks 获取所有任务
func (m *TaskManager) GetAllTasks() []*Task {
	m.mu.RLock()
	defer m.mu.RUnlock()

	tasks := make([]*Task, 0, len(m.tasks))
	for _, task := range m.tasks {
		tasks = append(tasks, task)
	}

	// 按创建时间倒序排序
	for i := 0; i < len(tasks)-1; i++ {
		for j := i + 1; j < len(tasks); j++ {
			if tasks[i].CreatedAt.Before(tasks[j].CreatedAt) {
				tasks[i], tasks[j] = tasks[j], tasks[i]
			}
		}
	}

	return tasks
}

// GetRunningTasks 获取运行中的任务
func (m *TaskManager) GetRunningTasks() []*Task {
	m.mu.RLock()
	defer m.mu.RUnlock()

	var tasks []*Task
	for _, task := range m.tasks {
		if task.Status == TaskStatusRunning || task.Status == TaskStatusPending {
			tasks = append(tasks, task)
		}
	}
	return tasks
}

// CancelTask 取消任务
func (m *TaskManager) CancelTask(id string) bool {
	m.mu.RLock()
	task, exists := m.tasks[id]
	m.mu.RUnlock()

	if !exists {
		return false
	}

	task.mu.Lock()
	defer task.mu.Unlock()

	if task.Status != TaskStatusRunning && task.Status != TaskStatusPending {
		return false
	}

	close(task.cancelCh)
	task.Status = TaskStatusCancelled
	task.EndTime = time.Now()
	task.Message = "任务已取消"

	return true
}

// DeleteTask 删除任务
func (m *TaskManager) DeleteTask(id string) bool {
	m.mu.Lock()
	defer m.mu.Unlock()

	task, exists := m.tasks[id]
	if !exists {
		return false
	}

	// 只能删除已完成/失败/取消的任务
	if task.Status == TaskStatusRunning || task.Status == TaskStatusPending {
		return false
	}

	delete(m.tasks, id)
	return true
}

// cleanup 清理旧任务
func (m *TaskManager) cleanup() {
	if len(m.tasks) <= m.maxTasks {
		return
	}

	// 找出已完成的旧任务并删除
	var oldestCompleted *Task
	for _, task := range m.tasks {
		if task.Status == TaskStatusCompleted || task.Status == TaskStatusFailed || task.Status == TaskStatusCancelled {
			if oldestCompleted == nil || task.CreatedAt.Before(oldestCompleted.CreatedAt) {
				oldestCompleted = task
			}
		}
	}

	if oldestCompleted != nil {
		delete(m.tasks, oldestCompleted.ID)
	}
}

// UpdateTask 更新任务状态
func (t *Task) UpdateTask(status TaskStatus, message string) {
	t.mu.Lock()
	defer t.mu.Unlock()

	t.Status = status
	t.Message = message

	if status == TaskStatusRunning && t.StartTime.IsZero() {
		t.StartTime = time.Now()
	}

	if status == TaskStatusCompleted || status == TaskStatusFailed || status == TaskStatusCancelled {
		t.EndTime = time.Now()
	}
}

// UpdateProgress 更新进度
func (t *Task) UpdateProgress(synced, failed, total int, message string) {
	t.mu.Lock()
	defer t.mu.Unlock()

	t.SyncedFiles = synced
	t.FailedFiles = failed
	t.TotalFiles = total
	t.Message = message

	if total > 0 {
		t.Progress = float64(synced+failed) / float64(total) * 100
	}
}

// SetTotalFiles 设置总文件数
func (t *Task) SetTotalFiles(total int) {
	t.mu.Lock()
	defer t.mu.Unlock()
	t.TotalFiles = total
}

// IncrementSynced 增加已同步数
func (t *Task) IncrementSynced() {
	t.mu.Lock()
	defer t.mu.Unlock()
	t.SyncedFiles++
	if t.TotalFiles > 0 {
		t.Progress = float64(t.SyncedFiles+t.FailedFiles) / float64(t.TotalFiles) * 100
	}
}

// IncrementFailed 增加失败数
func (t *Task) IncrementFailed() {
	t.mu.Lock()
	defer t.mu.Unlock()
	t.FailedFiles++
	if t.TotalFiles > 0 {
		t.Progress = float64(t.SyncedFiles+t.FailedFiles) / float64(t.TotalFiles) * 100
	}
}

// SetDeleted 设置删除数
func (t *Task) SetDeleted(count int) {
	t.mu.Lock()
	defer t.mu.Unlock()
	t.DeletedFiles = count
}

// SetError 设置错误
func (t *Task) SetError(err string) {
	t.mu.Lock()
	defer t.mu.Unlock()
	t.Error = err
}

// IsCancelled 检查是否已取消
func (t *Task) IsCancelled() bool {
	select {
	case <-t.cancelCh:
		return true
	default:
		return false
	}
}

// generateTaskID 生成任务ID
func generateTaskID() string {
	return time.Now().Format("20060102150405") + "-" + randomString(6)
}

// randomString 生成随机字符串
func randomString(n int) string {
	const letters = "abcdefghijklmnopqrstuvwxyz0123456789"
	b := make([]byte, n)
	for i := range b {
		b[i] = letters[time.Now().UnixNano()%int64(len(letters))]
		time.Sleep(time.Nanosecond)
	}
	return string(b)
}
