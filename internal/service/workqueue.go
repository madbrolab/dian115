package service

import (
	"context"
	"fmt"
	"log"
	"sync"
	"time"

	"strm-manager/internal/model"
	"strm-manager/internal/util"
)

// JobType 任务类型
type JobType string

const (
	JobTypeFastScan    JobType = "fast_scan"    // 快速扫描（增量）
	JobTypeFullSync    JobType = "full_sync"    // 全量同步
	JobTypeBuildTree   JobType = "build_tree"   // 构建目录树
	JobTypeDelete      JobType = "delete"       // 删除处理
	JobTypeLocalDelete JobType = "local_delete" // 本地反向删除
)

// JobPriority 任务优先级
type JobPriority int

const (
	PriorityNormal JobPriority = 0 // 普通优先级（监控/定时触发）
	PriorityHigh   JobPriority = 1 // 高优先级（手动触发）
)

// Job 工作任务
type Job struct {
	ID       string                      // 任务ID
	Type     JobType                     // 任务类型
	RuleID   int64                       // 规则ID
	Priority JobPriority                 // 优先级
	Params   map[string]interface{}      // 任务参数
	Handler  func(context.Context) error // 任务处理函数
	SubmitAt time.Time                   // 提交时间
}

// WorkQueue 全局工作队列
type WorkQueue struct {
	jobCh       chan Job
	workers     int
	maxWorkers  int // 最大并发worker数
	ruleLocks   map[int64]*sync.RWMutex
	locksMu     sync.Mutex
	pendingJobs map[string]*Job // 待处理任务（用于去重）
	pendingMu   sync.Mutex
	runningJobs map[string]context.CancelFunc // 运行中任务
	runningMu   sync.Mutex
	logger      *LoggerService
	ctx         context.Context
	cancel      context.CancelFunc
	wg          sync.WaitGroup
	// 统计
	stats struct {
		sync.Mutex
		submitted    int64
		completed    int64
		failed       int64
		deduplicated int64
	}
}

// NewWorkQueue 创建工作队列
func NewWorkQueue(queueSize, maxWorkers int, logger *LoggerService) *WorkQueue {
	ctx, cancel := context.WithCancel(context.Background())
	return &WorkQueue{
		jobCh:       make(chan Job, queueSize),
		maxWorkers:  maxWorkers,
		ruleLocks:   make(map[int64]*sync.RWMutex),
		pendingJobs: make(map[string]*Job),
		runningJobs: make(map[string]context.CancelFunc),
		logger:      logger,
		ctx:         ctx,
		cancel:      cancel,
	}
}

// Start 启动工作队列
func (q *WorkQueue) Start() {
	for i := 0; i < q.maxWorkers; i++ {
		q.wg.Add(1)
		go q.worker(i)
	}

	// 启动内存回收goroutine
	q.wg.Add(1)
	go q.memoryCleanup()

	log.Printf("[WorkQueue] 工作队列已启动，worker数: %d, 队列容量: %d", q.maxWorkers, cap(q.jobCh))
	if q.logger != nil {
		q.logger.LogSystem(model.LogLevelInfo, fmt.Sprintf("工作队列已启动，worker数: %d", q.maxWorkers), nil)
	}
}

// Stop 停止工作队列
func (q *WorkQueue) Stop() {
	log.Printf("[WorkQueue] 正在停止工作队列...")
	q.cancel()
	close(q.jobCh)
	q.wg.Wait()
	log.Printf("[WorkQueue] 工作队列已停止")
}

// Submit 提交任务
func (q *WorkQueue) Submit(job Job) error {
	jobKey := fmt.Sprintf("%s:%d", job.Type, job.RuleID)

	q.pendingMu.Lock()
	q.pendingJobs[jobKey] = &job
	q.pendingMu.Unlock()

	// 提交到队列（阻塞等待）
	select {
	case q.jobCh <- job:
		q.stats.Lock()
		q.stats.submitted++
		q.stats.Unlock()
		return nil
	case <-q.ctx.Done():
		return fmt.Errorf("工作队列已关闭")
	}
}

// worker 工作协程
func (q *WorkQueue) worker(id int) {
	defer q.wg.Done()

	for {
		select {
		case job, ok := <-q.jobCh:
			if !ok {
				return
			}
			q.processJob(id, job)
		case <-q.ctx.Done():
			return
		}
	}
}

// processJob 处理任务
func (q *WorkQueue) processJob(workerID int, job Job) {
	jobKey := fmt.Sprintf("%s:%d", job.Type, job.RuleID)

	// 从待处理队列移除
	q.pendingMu.Lock()
	delete(q.pendingJobs, jobKey)
	q.pendingMu.Unlock()

	// 获取规则锁
	lock := q.getRuleLock(job.RuleID)

	// 根据任务类型选择锁策略
	isFullOperation := job.Type == JobTypeBuildTree || job.Type == JobTypeFullSync
	if isFullOperation {
		lock.Lock()
		defer lock.Unlock()
	} else {
		lock.RLock()
		defer lock.RUnlock()
	}

	// 创建任务上下文（带超时）
	ctx, cancel := context.WithTimeout(q.ctx, 30*time.Minute)
	defer cancel()

	// 记录运行中任务
	q.runningMu.Lock()
	q.runningJobs[job.ID] = cancel
	q.runningMu.Unlock()

	defer func() {
		q.runningMu.Lock()
		delete(q.runningJobs, job.ID)
		q.runningMu.Unlock()
	}()

	startTime := time.Now()
	log.Printf("[WorkQueue] Worker-%d 开始执行: %s, ruleID=%d, 优先级=%d", workerID, job.Type, job.RuleID, job.Priority)

	// 执行任务
	err := job.Handler(ctx)
	elapsed := time.Since(startTime)

	if err != nil {
		q.stats.Lock()
		q.stats.failed++
		q.stats.Unlock()
		log.Printf("[WorkQueue] Worker-%d 执行失败: %s, ruleID=%d, 耗时=%s, 错误=%v", workerID, job.Type, job.RuleID, util.FormatDuration(elapsed), err)
		if q.logger != nil {
			q.logger.LogSystem(model.LogLevelError, fmt.Sprintf("任务执行失败: %s", job.Type), map[string]interface{}{
				"rule_id": job.RuleID,
				"error":   err.Error(),
				"elapsed": elapsed.String(),
			})
		}
	} else {
		q.stats.Lock()
		q.stats.completed++
		q.stats.Unlock()
		log.Printf("[WorkQueue] Worker-%d 执行完成: %s, ruleID=%d, 耗时=%s", workerID, job.Type, job.RuleID, util.FormatDuration(elapsed))
	}
}

// getRuleLock 获取规则锁
func (q *WorkQueue) getRuleLock(ruleID int64) *sync.RWMutex {
	q.locksMu.Lock()
	defer q.locksMu.Unlock()

	if lock, exists := q.ruleLocks[ruleID]; exists {
		return lock
	}

	lock := &sync.RWMutex{}
	q.ruleLocks[ruleID] = lock
	return lock
}

// memoryCleanup 内存清理
func (q *WorkQueue) memoryCleanup() {
	defer q.wg.Done()

	ticker := time.NewTicker(10 * time.Minute)
	defer ticker.Stop()

	for {
		select {
		case <-ticker.C:
			q.cleanupRuleLocks()
		case <-q.ctx.Done():
			return
		}
	}
}

// cleanupRuleLocks 清理未使用的规则锁
func (q *WorkQueue) cleanupRuleLocks() {
	q.locksMu.Lock()
	defer q.locksMu.Unlock()

	// 只保留有运行中任务的规则锁
	q.runningMu.Lock()
	activeRules := make(map[int64]bool)
	for _, job := range q.runningJobs {
		_ = job // 这里简化处理，实际应该从job中提取ruleID
	}
	q.runningMu.Unlock()

	// 清理未使用的锁（简化版：保留所有，避免并发问题）
	// 实际生产环境可以根据最后使用时间清理
	beforeCount := len(q.ruleLocks)
	if beforeCount > 100 {
		log.Printf("[WorkQueue] 规则锁数量: %d (考虑清理)", beforeCount)
	}
	_ = activeRules
}

// GetStats 获取统计信息
func (q *WorkQueue) GetStats() map[string]interface{} {
	q.stats.Lock()
	defer q.stats.Unlock()

	q.pendingMu.Lock()
	pendingCount := len(q.pendingJobs)
	q.pendingMu.Unlock()

	q.runningMu.Lock()
	runningCount := len(q.runningJobs)
	q.runningMu.Unlock()

	return map[string]interface{}{
		"queue_size":   len(q.jobCh),
		"queue_cap":    cap(q.jobCh),
		"pending":      pendingCount,
		"running":      runningCount,
		"workers":      q.maxWorkers,
		"submitted":    q.stats.submitted,
		"completed":    q.stats.completed,
		"failed":       q.stats.failed,
		"deduplicated": q.stats.deduplicated,
	}
}
