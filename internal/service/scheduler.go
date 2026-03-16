package service

import (
	"context"
	"fmt"
	"log"
	"path/filepath"
	"strings"
	"sync"
	"time"

	"github.com/robfig/cron/v3"

	"strm-manager/internal/model"
	"strm-manager/internal/store"
)

// SchedulerService 定时同步调度服务
type SchedulerService struct {
	store        *store.Store
	strmSvc      *STRMService
	treeSvc      *TreeService
	logger       *LoggerService
	workQueue    *WorkQueue
	cron         *cron.Cron
	jobs         map[int64]cron.EntryID // 规则ID -> cron增量同步任务ID
	fullSyncJobs map[int64]cron.EntryID // 规则ID -> cron全量同步任务ID
	mu           sync.RWMutex
	running      bool
}

// NewSchedulerService 创建调度服务
func NewSchedulerService(store *store.Store, strmSvc *STRMService) *SchedulerService {
	return &SchedulerService{
		store:        store,
		strmSvc:      strmSvc,
		cron:         cron.New(cron.WithSeconds()),
		jobs:         make(map[int64]cron.EntryID),
		fullSyncJobs: make(map[int64]cron.EntryID),
	}
}

// SetLogger 设置日志服务
func (s *SchedulerService) SetLogger(logger *LoggerService) {
	s.logger = logger
}

// SetTreeService 设置目录树服务
func (s *SchedulerService) SetTreeService(treeSvc *TreeService) {
	s.treeSvc = treeSvc
}

// SetWorkQueue 设置工作队列
func (s *SchedulerService) SetWorkQueue(wq *WorkQueue) {
	s.workQueue = wq
}

// Start 启动调度服务
func (s *SchedulerService) Start() error {
	s.mu.Lock()
	defer s.mu.Unlock()

	if s.running {
		return nil
	}

	// 加载所有定时同步规则
	rules, err := s.store.GetRulesBySyncMode(model.SyncModeCron)
	if err != nil {
		return err
	}

	for _, rule := range rules {
		if err := s.addJob(rule); err != nil {
			log.Printf("[Scheduler] 添加定时任务失败 (规则: %s): %v", rule.Name, err)
			if s.logger != nil {
				s.logger.LogScheduler(model.LogLevelError, fmt.Sprintf("添加定时任务失败: %s", rule.Name), map[string]string{
					"error": err.Error(),
				}, rule.ID)
			}
		}
		// 如果配置了全量同步cron，也添加
		if rule.FullSyncCron != "" {
			if err := s.addFullSyncJob(rule); err != nil {
				log.Printf("[Scheduler] 添加定时全量任务失败 (规则: %s): %v", rule.Name, err)
			}
		}
	}

	// 加载所有启用的规则，检查是否有全量同步cron（可能不在cron模式下但配置了全量同步）
	allRules, err := s.store.GetEnabledRules()
	if err == nil {
		for _, rule := range allRules {
			if rule.Enabled && rule.FullSyncCron != "" {
				if _, exists := s.fullSyncJobs[rule.ID]; !exists {
					if err := s.addFullSyncJob(rule); err != nil {
						log.Printf("[Scheduler] 添加定时全量任务失败 (规则: %s): %v", rule.Name, err)
					}
				}
			}
		}
	}

	// 添加数据库维护任务（每天凌晨3点执行）
	_, err = s.cron.AddFunc("0 0 3 * * *", func() {
		log.Printf("[Scheduler] 开始数据库维护...")

		// 清理旧日志
		if err := s.store.CleanOldLogs(10000); err != nil {
			log.Printf("[Scheduler] 清理日志失败: %v", err)
		} else {
			log.Printf("[Scheduler] 日志清理完成")
		}

		// VACUUM 压缩
		if err := s.store.Vacuum(); err != nil {
			log.Printf("[Scheduler] VACUUM 失败: %v", err)
		} else {
			log.Printf("[Scheduler] VACUUM 完成")
		}

		log.Printf("[Scheduler] 数据库维护完成")
	})
	if err != nil {
		log.Printf("[Scheduler] 添加数据库维护任务失败: %v", err)
	}

	s.cron.Start()
	s.running = true
	log.Printf("[Scheduler] 定时同步服务已启动，共 %d 个任务", len(s.jobs))
	if s.logger != nil {
		s.logger.LogScheduler(model.LogLevelSuccess, fmt.Sprintf("定时同步服务已启动，共 %d 个任务", len(s.jobs)), nil, 0)
	}

	return nil
}

// Stop 停止调度服务
func (s *SchedulerService) Stop() {
	s.mu.Lock()
	defer s.mu.Unlock()

	if !s.running {
		return
	}

	s.cron.Stop()
	s.running = false
	log.Printf("[Scheduler] 定时同步服务已停止")
	if s.logger != nil {
		s.logger.LogScheduler(model.LogLevelInfo, "定时同步服务已停止", nil, 0)
	}
}

// IsRunning 检查是否运行中
func (s *SchedulerService) IsRunning() bool {
	s.mu.RLock()
	defer s.mu.RUnlock()
	return s.running
}

// RefreshJobs 刷新所有定时任务
func (s *SchedulerService) RefreshJobs() error {
	s.mu.Lock()
	defer s.mu.Unlock()

	// 移除所有现有任务
	for ruleID, entryID := range s.jobs {
		s.cron.Remove(entryID)
		delete(s.jobs, ruleID)
	}
	for ruleID, entryID := range s.fullSyncJobs {
		s.cron.Remove(entryID)
		delete(s.fullSyncJobs, ruleID)
	}

	// 重新加载定时同步规则
	rules, err := s.store.GetRulesBySyncMode(model.SyncModeCron)
	if err != nil {
		return err
	}

	for _, rule := range rules {
		if err := s.addJob(rule); err != nil {
			log.Printf("[Scheduler] 添加定时任务失败 (规则: %s): %v", rule.Name, err)
			if s.logger != nil {
				s.logger.LogScheduler(model.LogLevelError, fmt.Sprintf("刷新时添加定时任务失败: %s", rule.Name), map[string]string{
					"error": err.Error(),
				}, rule.ID)
			}
		}
	}

	// 重新加载全量同步任务
	allRules, err := s.store.GetEnabledRules()
	if err == nil {
		for _, rule := range allRules {
			if rule.FullSyncCron != "" {
				if err := s.addFullSyncJob(rule); err != nil {
					log.Printf("[Scheduler] 添加定时全量任务失败 (规则: %s): %v", rule.Name, err)
				}
			}
		}
	}

	log.Printf("[Scheduler] 定时任务已刷新，共 %d 个增量任务, %d 个全量任务", len(s.jobs), len(s.fullSyncJobs))
	if s.logger != nil {
		s.logger.LogScheduler(model.LogLevelInfo, fmt.Sprintf("定时任务已刷新，共 %d 个任务", len(s.jobs)), nil, 0)
	}
	return nil
}

// AddOrUpdateJob 添加或更新规则的定时任务
func (s *SchedulerService) AddOrUpdateJob(rule *model.STRMRule) error {
	s.mu.Lock()
	defer s.mu.Unlock()

	// 如果已存在增量同步任务，先移除
	if entryID, exists := s.jobs[rule.ID]; exists {
		s.cron.Remove(entryID)
		delete(s.jobs, rule.ID)
	}
	// 如果已存在全量同步任务，先移除
	if entryID, exists := s.fullSyncJobs[rule.ID]; exists {
		s.cron.Remove(entryID)
		delete(s.fullSyncJobs, rule.ID)
	}

	// 如果是定时同步模式且已启用，添加增量同步任务
	if model.HasSyncMode(string(rule.SyncMode), model.SyncModeCron) && rule.Enabled && rule.CronExpr != "" {
		if err := s.addJob(rule); err != nil {
			return err
		}
	}

	// 如果配置了全量同步cron，添加全量同步任务
	if rule.Enabled && rule.FullSyncCron != "" {
		if err := s.addFullSyncJob(rule); err != nil {
			return err
		}
	}

	return nil
}

// RemoveJob 移除规则的定时任务
func (s *SchedulerService) RemoveJob(ruleID int64) {
	s.mu.Lock()
	defer s.mu.Unlock()

	if entryID, exists := s.jobs[ruleID]; exists {
		s.cron.Remove(entryID)
		delete(s.jobs, ruleID)
	}
	if entryID, exists := s.fullSyncJobs[ruleID]; exists {
		s.cron.Remove(entryID)
		delete(s.fullSyncJobs, ruleID)
	}
	log.Printf("[Scheduler] 已移除定时任务 (规则ID: %d)", ruleID)
	if s.logger != nil {
		s.logger.LogScheduler(model.LogLevelInfo, fmt.Sprintf("已移除定时任务: 规则ID=%d", ruleID), nil, ruleID)
	}
}

// addJob 添加定时任务（内部方法，需要持有锁）
func (s *SchedulerService) addJob(rule *model.STRMRule) error {
	if rule.CronExpr == "" {
		return nil
	}

	// 创建任务函数
	ruleID := rule.ID
	ruleName := rule.Name
	job := func() {
		log.Printf("[Scheduler] 开始执行定时同步 (规则: %s)", ruleName)
		if s.logger != nil {
			s.logger.LogScheduler(model.LogLevelInfo, fmt.Sprintf("开始执行定时同步: %s", ruleName), nil, ruleID)
		}

		// 获取最新的规则信息
		currentRule, err := s.store.GetRule(ruleID)
		if err != nil || currentRule == nil {
			log.Printf("[Scheduler] 获取规则失败 (ID: %d): %v", ruleID, err)
			if s.logger != nil {
				s.logger.LogScheduler(model.LogLevelError, fmt.Sprintf("获取规则失败: ID=%d", ruleID), map[string]string{
					"error": fmt.Sprintf("%v", err),
				}, ruleID)
			}
			return
		}

		if !currentRule.Enabled {
			log.Printf("[Scheduler] 规则已禁用，跳过同步 (规则: %s)", ruleName)
			if s.logger != nil {
				s.logger.LogScheduler(model.LogLevelWarning, fmt.Sprintf("规则已禁用，跳过同步: %s", ruleName), nil, ruleID)
			}
			return
		}

		// 通过工作队列执行同步
		s.submitSyncJob(ruleID, ruleName, currentRule, false)
	}

	// 添加到cron
	entryID, err := s.cron.AddFunc(rule.CronExpr, job)
	if err != nil {
		return err
	}

	s.jobs[rule.ID] = entryID
	log.Printf("[Scheduler] 已添加定时任务 (规则: %s, Cron: %s)", rule.Name, rule.CronExpr)
	if s.logger != nil {
		s.logger.LogScheduler(model.LogLevelSuccess, fmt.Sprintf("已添加定时任务: %s (Cron: %s)", rule.Name, rule.CronExpr), map[string]string{
			"cron_expr": rule.CronExpr,
		}, rule.ID)
	}

	return nil
}

// addFullSyncJob 添加定时全量同步任务（内部方法，需要持有锁）
func (s *SchedulerService) addFullSyncJob(rule *model.STRMRule) error {
	if rule.FullSyncCron == "" {
		return nil
	}

	ruleID := rule.ID
	ruleName := rule.Name
	job := func() {
		log.Printf("[Scheduler] 开始执行定时全量同步 (规则: %s)", ruleName)
		if s.logger != nil {
			s.logger.LogScheduler(model.LogLevelInfo, fmt.Sprintf("开始执行定时全量同步: %s", ruleName), nil, ruleID)
		}

		currentRule, err := s.store.GetRule(ruleID)
		if err != nil || currentRule == nil {
			log.Printf("[Scheduler] 获取规则失败 (ID: %d): %v", ruleID, err)
			return
		}

		if !currentRule.Enabled {
			log.Printf("[Scheduler] 规则已禁用，跳过全量同步 (规则: %s)", ruleName)
			return
		}

		// 如果配置了云盘名称且有目录树服务，先重建目录树
		if currentRule.CloudName != "" && s.treeSvc != nil {
			log.Printf("[Scheduler] 重建目录树 (规则: %s)", ruleName)
			if s.logger != nil {
				s.logger.LogScheduler(model.LogLevelInfo, fmt.Sprintf("定时全量同步-重建目录树: %s", ruleName), nil, ruleID)
			}
			if err := s.treeSvc.BuildTree(currentRule, nil); err != nil {
				log.Printf("[Scheduler] 重建目录树失败 (规则: %s): %v", ruleName, err)
				if s.logger != nil {
					s.logger.LogScheduler(model.LogLevelError, fmt.Sprintf("定时全量同步-重建目录树失败: %s", ruleName), map[string]string{
						"error": err.Error(),
					}, ruleID)
				}
				return
			}
			// 重新加载规则
			currentRule, _ = s.store.GetRule(ruleID)
		}

		// 通过工作队列执行全量同步
		s.submitSyncJob(ruleID, ruleName, currentRule, true)
	}

	entryID, err := s.cron.AddFunc(rule.FullSyncCron, job)
	if err != nil {
		return err
	}

	s.fullSyncJobs[rule.ID] = entryID
	log.Printf("[Scheduler] 已添加定时全量同步任务 (规则: %s, Cron: %s)", rule.Name, rule.FullSyncCron)
	if s.logger != nil {
		s.logger.LogScheduler(model.LogLevelSuccess, fmt.Sprintf("已添加定时全量同步任务: %s (Cron: %s)", rule.Name, rule.FullSyncCron), map[string]string{
			"full_sync_cron": rule.FullSyncCron,
		}, rule.ID)
	}

	return nil
}

// submitSyncJob 提交同步任务到工作队列
func (s *SchedulerService) submitSyncJob(ruleID int64, ruleName string, rule *model.STRMRule, isFullSync bool) {
	doSync := func() {
		var changedDirs []string

		// 增量同步：先调用 IncrementalScan 更新目录树
		if !isFullSync && s.treeSvc != nil {
			log.Printf("[Scheduler] 增量扫描目录树 (规则: %s)", ruleName)
			if s.logger != nil {
				s.logger.LogScheduler(model.LogLevelInfo, fmt.Sprintf("增量扫描目录树: %s", ruleName), nil, ruleID)
			}

			scanResult, err := s.treeSvc.IncrementalScan(rule, nil)
			if err != nil {
				log.Printf("[Scheduler] 增量扫描失败 (规则: %s): %v", ruleName, err)
				if s.logger != nil {
					s.logger.LogScheduler(model.LogLevelError, fmt.Sprintf("增量扫描失败: %s", ruleName), map[string]string{
						"error": err.Error(),
					}, ruleID)
				}
			} else {
				log.Printf("[Scheduler] 增量扫描完成 (规则: %s): 新增=%d, 删除=%d", ruleName, len(scanResult.AddedNodes), len(scanResult.DeletedNodes))
				if s.logger != nil {
					s.logger.LogScheduler(model.LogLevelSuccess, fmt.Sprintf("增量扫描完成: %s", ruleName), map[string]string{
						"added":   fmt.Sprintf("%d", len(scanResult.AddedNodes)),
						"deleted": fmt.Sprintf("%d", len(scanResult.DeletedNodes)),
					}, ruleID)
				}

				// 收集变化的父目录
				changedDirs = s.collectChangedDirs(rule, scanResult)
			}
		}

		result, err := s.strmSvc.SyncRule(rule)
		if err != nil {
			syncType := "定时同步"
			if isFullSync {
				syncType = "定时全量同步"
			}
			log.Printf("[Scheduler] %s失败 (规则: %s): %v", syncType, ruleName, err)
			if s.logger != nil {
				s.logger.LogScheduler(model.LogLevelError, fmt.Sprintf("%s失败: %s", syncType, ruleName), map[string]string{
					"error": err.Error(),
				}, ruleID)
			}
			return
		}

		s.store.UpdateRuleLastSyncTime(ruleID, time.Now())
		if count, err := s.store.GetFileMappingCountByRuleID(ruleID); err == nil {
			s.store.UpdateRuleFileCount(ruleID, count)
		}

		// 增量同步且有变化目录时，只刷新变化的父目录
		if !isFullSync && len(changedDirs) > 0 && s.strmSvc.embySvc != nil {
			log.Printf("[Scheduler] 增量刷新 %d 个父目录", len(changedDirs))
			for _, dir := range changedDirs {
				s.strmSvc.embySvc.RefreshLibraryPath(dir)
			}
		}

		syncType := "定时同步"
		if isFullSync {
			syncType = "定时全量同步"
		}
		log.Printf("[Scheduler] %s完成 (规则: %s): 成功=%d, 失败=%d, 删除=%d",
			syncType, ruleName, result.Success, result.Failed, result.Deleted)
		if s.logger != nil {
			s.logger.LogScheduler(model.LogLevelSuccess, fmt.Sprintf("%s完成: %s", syncType, ruleName), map[string]string{
				"success": fmt.Sprintf("%d", result.Success),
				"failed":  fmt.Sprintf("%d", result.Failed),
				"deleted": fmt.Sprintf("%d", result.Deleted),
			}, ruleID)
		}
	}

	if s.workQueue == nil {
		doSync()
		return
	}

	jobType := JobTypeFastScan
	if isFullSync {
		jobType = JobTypeFullSync
	}

	job := Job{
		ID:       fmt.Sprintf("scheduler-%s-%d-%d", jobType, ruleID, time.Now().UnixNano()),
		Type:     jobType,
		RuleID:   ruleID,
		Priority: PriorityNormal,
		SubmitAt: time.Now(),
		Handler: func(ctx context.Context) error {
			select {
			case <-ctx.Done():
				return ctx.Err()
			default:
			}
			doSync()
			return nil
		},
	}

	if err := s.workQueue.Submit(job); err != nil {
		log.Printf("[Scheduler] 提交同步任务到队列失败: %v，直接执行", err)
		doSync()
	}
}

// GetJobStatus 获取任务状态
func (s *SchedulerService) GetJobStatus() []map[string]interface{} {
	s.mu.RLock()
	defer s.mu.RUnlock()

	var status []map[string]interface{}
	for ruleID, entryID := range s.jobs {
		entry := s.cron.Entry(entryID)
		rule, _ := s.store.GetRule(ruleID)

		jobStatus := map[string]interface{}{
			"rule_id":   ruleID,
			"rule_name": "",
			"cron_expr": "",
			"next_run":  entry.Next,
			"prev_run":  entry.Prev,
		}

		if rule != nil {
			jobStatus["rule_name"] = rule.Name
			jobStatus["cron_expr"] = rule.CronExpr
		}

		status = append(status, jobStatus)
	}

	return status
}

// collectChangedDirs 收集变化的父目录
func (s *SchedulerService) collectChangedDirs(rule *model.STRMRule, scanResult *IncrementalScanResult) []string {
	dirMap := make(map[string]bool)
	sourcePath115 := cd2PathTo115Path(rule.SourcePath, rule.CloudName)

	for _, node := range scanResult.AddedNodes {
		if node.STRMPath != "" {
			dirMap[filepath.Dir(node.STRMPath)] = true
		}
	}

	for _, node := range scanResult.DeletedNodes {
		if node.STRMPath != "" {
			dirMap[filepath.Dir(node.STRMPath)] = true
		} else if node.Path115 != "" {
			relPath, _ := filepath.Rel(sourcePath115, node.Path115)
			ext := strings.ToLower(filepath.Ext(relPath))
			strmRelPath := strings.TrimSuffix(relPath, ext) + ".strm"
			strmPath := filepath.Join(rule.OutputPath, strmRelPath)
			dirMap[filepath.Dir(strmPath)] = true
		}
	}

	dirs := make([]string, 0, len(dirMap))
	for dir := range dirMap {
		dirs = append(dirs, dir)
	}
	return dirs
}
