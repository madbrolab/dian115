package service

import (
	"context"
	"fmt"
	"log"
	"os"
	"path/filepath"
	"strings"
	"sync"
	"time"

	"strm-manager/internal/client"
	"strm-manager/internal/model"
	"strm-manager/internal/store"
	"strm-manager/internal/util"
)

// MonitorService 文件监控服务（实时监控模式）
type MonitorService struct {
	store         *store.Store
	cd2           *client.CloudDriveClient
	strm          *STRMService
	treeSvc       *TreeService
	cleanerSvc    *CleanerService
	embySvc       *EmbyProxyService
	logger        *LoggerService
	workQueue     *WorkQueue
	globalWatcher *client.FileWatcher       // 全局唯一的watcher
	rules         map[int64]*model.STRMRule // 当前监控的规则
	running       bool
	mu            sync.RWMutex

	// 防抖：同一目录1秒内的多次变动合并为一次处理
	debounceMu     sync.Mutex
	debounceTimers map[string]*time.Timer // key: "ruleID:dirPath115"
}

// NewMonitorService 创建监控服务
func NewMonitorService(store *store.Store, cd2 *client.CloudDriveClient, strm *STRMService) *MonitorService {
	return &MonitorService{
		store:          store,
		cd2:            cd2,
		strm:           strm,
		rules:          make(map[int64]*model.STRMRule),
		debounceTimers: make(map[string]*time.Timer),
	}
}

// SetLogger 设置日志服务
func (m *MonitorService) SetLogger(logger *LoggerService) {
	m.logger = logger
}

// SetTreeService 设置目录树服务
func (m *MonitorService) SetTreeService(treeSvc *TreeService) {
	m.treeSvc = treeSvc
}

// SetCleanerService 设置清理服务
func (m *MonitorService) SetCleanerService(cleanerSvc *CleanerService) {
	m.cleanerSvc = cleanerSvc
}

// SetEmbyService 设置Emby服务
func (m *MonitorService) SetEmbyService(embySvc *EmbyProxyService) {
	m.embySvc = embySvc
}

// SetWorkQueue 设置工作队列
func (m *MonitorService) SetWorkQueue(wq *WorkQueue) {
	m.workQueue = wq
}

// Start 启动监控
func (m *MonitorService) Start() error {
	m.mu.Lock()
	defer m.mu.Unlock()
	if m.running {
		return nil
	}

	rules, err := m.store.GetRulesBySyncMode(model.SyncModeRealtime)
	if err != nil {
		return err
	}
	if len(rules) == 0 {
		return nil
	}

	// 加载规则到内存
	for _, rule := range rules {
		m.rules[rule.ID] = rule
	}

	// 创建全局watcher并注册统一回调
	m.globalWatcher = client.NewFileWatcher(m.cd2)
	m.globalWatcher.AddCallback("global", m.handleFileChange)

	// 启动全局watcher
	m.globalWatcher.Start()

	m.running = true
	log.Printf("[Monitor] 实时监控服务已启动，共 %d 个规则", len(m.rules))
	if m.logger != nil {
		m.logger.LogMonitor(model.LogLevelSuccess, fmt.Sprintf("实时监控服务已启动，共 %d 个规则", len(m.rules)), nil, 0)
	}
	return nil
}

// Stop 停止监控
func (m *MonitorService) Stop() {
	m.mu.Lock()
	defer m.mu.Unlock()

	if m.globalWatcher != nil {
		m.globalWatcher.Stop()
		m.globalWatcher = nil
	}
	m.rules = make(map[int64]*model.STRMRule)
	m.running = false

	// 清理所有防抖定时器
	m.debounceMu.Lock()
	for _, t := range m.debounceTimers {
		t.Stop()
	}
	m.debounceTimers = make(map[string]*time.Timer)
	m.debounceMu.Unlock()
}

// IsRunning 是否运行中
func (m *MonitorService) IsRunning() bool {
	m.mu.RLock()
	defer m.mu.RUnlock()
	return m.running
}

// handleFileChange 统一处理文件变化（全局回调）
func (m *MonitorService) handleFileChange(changeType, path string, isDir bool) {
	if path == "" {
		return
	}

	m.mu.RLock()
	defer m.mu.RUnlock()

	// 遍历所有规则，找到匹配的规则处理
	for _, rule := range m.rules {
		if !strings.HasPrefix(path, rule.SourcePath) {
			continue
		}

		if m.logger != nil {
			m.logger.LogMonitor(model.LogLevelInfo, fmt.Sprintf("文件变动: %s %s", changeType, filepath.Base(path)), map[string]string{
				"rule_name": rule.Name,
				"path":      path,
				"is_dir":    fmt.Sprintf("%v", isDir),
			}, rule.ID)
		}

		if m.treeSvc == nil {
			if m.logger != nil {
				m.logger.LogMonitor(model.LogLevelWarning, "目录树服务未设置，跳过处理", nil, rule.ID)
			}
			continue
		}

		switch changeType {
		case "add":
			m.handleAdd(rule, path, isDir)
		case "delete":
			m.submitDeleteJob(rule, path, isDir)
		case "rename":
			m.submitDeleteJob(rule, path, isDir)
		}
	}
}

// handleAdd 处理新增事件（全部走快速模式 + 防抖）
func (m *MonitorService) handleAdd(rule *model.STRMRule, cd2Path string, isDir bool) {
	// 非目录文件：检查是否为视频文件，非视频文件（如.nfo/.jpg等）跳过，避免无效扫描
	if !isDir {
		ext := strings.ToLower(filepath.Ext(cd2Path))
		if !m.strm.getVideoExtensions(rule)[ext] {
			return
		}
	}

	// 确定要扫描的目录路径
	var scanDirCD2Path string
	if isDir {
		scanDirCD2Path = cd2Path
	} else {
		scanDirCD2Path = filepath.Dir(cd2Path)
	}

	// 转换为115路径
	scanDir115 := cd2PathTo115Path(scanDirCD2Path, rule.CloudName)
	if scanDir115 == "" {
		log.Printf("[Monitor]   ✗ 无法转换路径: %s", scanDirCD2Path)
		return
	}

	// 防抖：同一目录1秒内合并
	debounceKey := fmt.Sprintf("%d:%s", rule.ID, scanDir115)

	m.debounceMu.Lock()
	if existing, ok := m.debounceTimers[debounceKey]; ok {
		existing.Stop()
	}

	ruleCopy := *rule
	m.debounceTimers[debounceKey] = time.AfterFunc(1*time.Second, func() {
		m.debounceMu.Lock()
		delete(m.debounceTimers, debounceKey)
		m.debounceMu.Unlock()

		// 防抖结束后提交到工作队列
		m.submitFastScanJob(&ruleCopy, scanDirCD2Path, scanDir115)
	})
	m.debounceMu.Unlock()
}

// submitFastScanJob 提交快速扫描任务到工作队列
func (m *MonitorService) submitFastScanJob(rule *model.STRMRule, scanDirCD2Path, scanDir115 string) {
	if m.workQueue == nil {
		m.doFastScan(rule, scanDirCD2Path, scanDir115)
		return
	}

	ruleCopy := *rule
	job := Job{
		ID:       fmt.Sprintf("fastscan-%d-%d", rule.ID, time.Now().UnixNano()),
		Type:     JobTypeFastScan,
		RuleID:   rule.ID,
		Priority: PriorityNormal,
		SubmitAt: time.Now(),
		Handler: func(ctx context.Context) error {
			select {
			case <-ctx.Done():
				return ctx.Err()
			default:
			}
			m.doFastScan(&ruleCopy, scanDirCD2Path, scanDir115)
			return nil
		},
	}

	if err := m.workQueue.Submit(job); err != nil {
		log.Printf("[Monitor] 提交快速扫描任务失败: %v", err)
		m.doFastScan(rule, scanDirCD2Path, scanDir115)
	}
}

// submitDeleteJob 提交删除任务到工作队列
func (m *MonitorService) submitDeleteJob(rule *model.STRMRule, cd2Path string, isDir bool) {
	if m.workQueue == nil {
		m.doDelete(rule, cd2Path, isDir)
		return
	}

	ruleCopy := *rule
	job := Job{
		ID:       fmt.Sprintf("delete-%d-%d", rule.ID, time.Now().UnixNano()),
		Type:     JobTypeDelete,
		RuleID:   rule.ID,
		Priority: PriorityNormal,
		SubmitAt: time.Now(),
		Handler: func(ctx context.Context) error {
			select {
			case <-ctx.Done():
				return ctx.Err()
			default:
			}
			m.doDelete(&ruleCopy, cd2Path, isDir)
			return nil
		},
	}

	if err := m.workQueue.Submit(job); err != nil {
		log.Printf("[Monitor] 提交删除任务失败: %v", err)
		m.doDelete(rule, cd2Path, isDir)
	}
}

// doFastScan 执行快速模式扫描（实际执行逻辑）
func (m *MonitorService) doFastScan(rule *model.STRMRule, scanDirCD2Path, scanDir115 string) {
	startTime := time.Now()

	added, err := m.treeSvc.FastScanDirectory(rule, scanDirCD2Path, scanDir115)
	if err != nil {
		log.Printf("[Monitor]   ✗ 快速扫描失败: %v", err)
		if m.logger != nil {
			m.logger.LogMonitor(model.LogLevelError, fmt.Sprintf("快速扫描失败: %s - %v", scanDir115, err), nil, rule.ID)
		}
		return
	}

	if len(added) == 0 {
		return
	}

	// 为新增的文件节点生成 STRM
	var strmPaths []string
	for _, node := range added {
		if !node.IsDir && node.PickCode != "" {
			// 计算STRM路径
			path115 := node.Path115
			sourcePath115 := cd2PathTo115Path(rule.SourcePath, rule.CloudName)
			relPath, err := filepath.Rel(sourcePath115, path115)
			if err != nil {
				log.Printf("[Monitor] 计算相对路径失败: %s - %v", node.Name, err)
				continue
			}

			ext := strings.ToLower(filepath.Ext(relPath))
			strmRelPath := strings.TrimSuffix(relPath, ext) + ".strm"
			strmPath := filepath.Join(rule.OutputPath, strmRelPath)

			// 创建STRM文件
			if err := os.MkdirAll(filepath.Dir(strmPath), 0755); err != nil {
				log.Printf("[Monitor] 创建目录失败: %s - %v", node.Name, err)
				continue
			}

			// STRM内容：挂载路径
			content := node.CD2Path
			if m.strm.mountPrefix != "" {
				mountPrefix := strings.TrimSuffix(m.strm.mountPrefix, "/")
				if !strings.HasPrefix(content, "/") {
					content = mountPrefix + "/" + content
				} else {
					content = mountPrefix + content
				}
			}

			if err := os.WriteFile(strmPath, []byte(content), 0644); err != nil {
				log.Printf("[Monitor] 生成STRM失败: %s - %v", node.Name, err)
				continue
			}

			// 更新目录树中的STRM路径
			m.store.UpdateTreeNodeSTRMPath(node.ID, strmPath)
			strmPaths = append(strmPaths, strmPath)
		}
	}

	// 刷新媒体库：提取父目录去重
	if m.embySvc != nil && len(strmPaths) > 0 {
		parentDirs := make(map[string]bool)
		for _, strmPath := range strmPaths {
			parentDirs[filepath.Dir(strmPath)] = true
		}
		log.Printf("[Monitor] %d个文件 -> %d个父目录需刷新", len(strmPaths), len(parentDirs))
		for dir := range parentDirs {
			if err := m.embySvc.RefreshLibraryPath(dir); err != nil {
				log.Printf("[Monitor] 通知Emby刷新失败: %s - %v", dir, err)
			}
		}
	}

	// 更新统计
	m.store.UpdateRuleLastSyncTime(rule.ID, time.Now())
	if count, err := m.store.GetFileMappingCountByRuleID(rule.ID); err == nil {
		m.store.UpdateRuleFileCount(rule.ID, count)
	}

	elapsed := time.Since(startTime)
	if m.logger != nil {
		m.logger.LogMonitor(model.LogLevelSuccess, fmt.Sprintf("快速扫描完成: %s, 新增%d个文件, 生成%d个STRM (%s)", scanDir115, len(added), len(strmPaths), util.FormatDuration(elapsed)), map[string]string{
			"rule_name": rule.Name,
			"count":     fmt.Sprintf("%d", len(added)),
			"strm":      fmt.Sprintf("%d", len(strmPaths)),
		}, rule.ID)
	}

	log.Printf("[Monitor] ===== 快速模式扫描结束 =====")
}

// doDelete 执行删除处理（实际执行逻辑）
func (m *MonitorService) doDelete(rule *model.STRMRule, cd2Path string, isDir bool) {
	var deleted []*model.FileTreeNode
	var err error

	if isDir {
		deleted, err = m.treeSvc.DeleteTreeByPrefix(rule, cd2Path)
		if err != nil {
			if m.logger != nil {
				m.logger.LogMonitor(model.LogLevelError, fmt.Sprintf("删除目录节点失败: %v", err), map[string]string{"path": cd2Path}, rule.ID)
			}
			return
		}
	} else {
		deleted, err = m.treeSvc.HandleDeleteFile(rule, cd2Path)
		if err != nil {
			if m.logger != nil {
				m.logger.LogMonitor(model.LogLevelError, fmt.Sprintf("删除文件节点失败: %v", err), map[string]string{"path": cd2Path}, rule.ID)
			}
			return
		}
	}

	if len(deleted) == 0 {
		return
	}

	if m.logger != nil {
		m.logger.LogMonitor(model.LogLevelInfo, fmt.Sprintf("已删除 %d 个节点: %s", len(deleted), filepath.Base(cd2Path)), nil, rule.ID)
	}

	if rule.SmartClean && m.cleanerSvc != nil {
		if isDir {
			sourcePath115 := cd2PathTo115Path(cd2Path, rule.CloudName)
			ruleSource115 := cd2PathTo115Path(rule.SourcePath, rule.CloudName)
			relPath, relErr := filepath.Rel(ruleSource115, sourcePath115)
			if relErr == nil && relPath != "." {
				strmDirPath := filepath.Join(rule.OutputPath, relPath)
				refreshPath, err := m.cleanerSvc.SmartCleanDirectory(rule, strmDirPath)
				if err != nil {
					if m.logger != nil {
						m.logger.LogMonitor(model.LogLevelError, fmt.Sprintf("智能清理目录失败: %s", filepath.Base(strmDirPath)), map[string]string{"error": err.Error()}, rule.ID)
					}
				} else {
					if m.logger != nil {
						m.logger.LogMonitor(model.LogLevelSuccess, fmt.Sprintf("智能清理目录: %s", filepath.Base(strmDirPath)), nil, rule.ID)
					}
					if m.embySvc != nil {
						if err := m.embySvc.RefreshLibraryPath(refreshPath); err != nil {
							log.Printf("[Monitor] 通知Emby刷新失败: %s - %v", refreshPath, err)
						}
					}
				}
			}
		} else {
			refreshDirs := make(map[string]bool)
			for _, node := range deleted {
				if node.IsDir || node.STRMPath == "" {
					continue
				}
				strmPath := node.STRMPath
				refreshPath, err := m.cleanerSvc.CleanAll(rule, strmPath)
				if err != nil {
					if m.logger != nil {
						m.logger.LogMonitor(model.LogLevelError, fmt.Sprintf("智能清理失败: %s", filepath.Base(strmPath)), map[string]string{"error": err.Error()}, rule.ID)
					}
				} else {
					if m.logger != nil {
						m.logger.LogMonitor(model.LogLevelSuccess, fmt.Sprintf("智能清理: %s", filepath.Base(strmPath)), nil, rule.ID)
					}
					if refreshPath != "" {
						refreshDirs[refreshPath] = true
					}
				}
			}

			// 只保留最上层目录,移除其子目录
			finalDirs := make(map[string]bool)
			for dir := range refreshDirs {
				isChild := false
				for parent := range refreshDirs {
					if dir != parent && strings.HasPrefix(dir+string(filepath.Separator), parent+string(filepath.Separator)) {
						isChild = true
						break
					}
				}
				if !isChild {
					finalDirs[dir] = true
				}
			}

			if m.embySvc != nil && len(finalDirs) > 0 {
				log.Printf("[Monitor] 批量刷新 %d 个目录", len(finalDirs))
				for dir := range finalDirs {
					if err := m.embySvc.RefreshLibraryPath(dir); err != nil {
						log.Printf("[Monitor] 通知Emby刷新失败: %s - %v", dir, err)
					}
				}
			}
		}
	}
}

// RefreshWatchers 刷新监控器
func (m *MonitorService) RefreshWatchers() error {
	m.mu.Lock()
	defer m.mu.Unlock()

	rules, err := m.store.GetRulesBySyncMode(model.SyncModeRealtime)
	if err != nil {
		return err
	}

	if len(rules) == 0 {
		if m.running {
			if m.globalWatcher != nil {
				m.globalWatcher.Stop()
				m.globalWatcher = nil
			}
			m.rules = make(map[int64]*model.STRMRule)
			m.running = false
			log.Printf("[Monitor] 无实时监控规则，监控服务已自动停止")
		}
		return nil
	}

	if !m.running {
		m.globalWatcher = client.NewFileWatcher(m.cd2)
		m.globalWatcher.AddCallback("global", m.handleFileChange)
		m.running = true
	}

	// 重新加载规则
	m.rules = make(map[int64]*model.STRMRule)
	for _, rule := range rules {
		m.rules[rule.ID] = rule
	}

	if !m.globalWatcher.IsRunning() {
		m.globalWatcher.Start()
	}

	if m.logger != nil {
		m.logger.LogMonitor(model.LogLevelInfo, fmt.Sprintf("监控器已刷新，共 %d 个规则", len(m.rules)), nil, 0)
	}
	return nil
}

// AddOrUpdateWatcher 添加或更新规则的监控器
func (m *MonitorService) AddOrUpdateWatcher(rule *model.STRMRule) {
	m.mu.Lock()
	defer m.mu.Unlock()

	if model.HasSyncMode(string(rule.SyncMode), model.SyncModeRealtime) && rule.Enabled && m.running {
		m.rules[rule.ID] = rule
	} else {
		delete(m.rules, rule.ID)
	}
}

// RemoveWatcher 移除规则的监控器
func (m *MonitorService) RemoveWatcher(ruleID int64) {
	m.mu.Lock()
	defer m.mu.Unlock()
	delete(m.rules, ruleID)
}

// GetWatcherCount 获取监控器数量
func (m *MonitorService) GetWatcherCount() int {
	m.mu.RLock()
	defer m.mu.RUnlock()
	return len(m.rules)
}

// SetCD2 热更新CD2客户端
func (m *MonitorService) SetCD2(cd2 *client.CloudDriveClient) {
	m.mu.Lock()
	m.cd2 = cd2
	m.mu.Unlock()
	_ = m.RefreshWatchers()
}

// GetWorkQueueStats 获取工作队列统计信息
func (m *MonitorService) GetWorkQueueStats() map[string]interface{} {
	if m.workQueue == nil {
		return nil
	}
	return m.workQueue.GetStats()
}
