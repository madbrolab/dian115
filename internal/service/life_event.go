package service

import (
	"log"
	"path/filepath"
	"strings"
	"sync"
	"sync/atomic"
	"time"

	"strm-manager/internal/client"
	"strm-manager/internal/model"
	"strm-manager/internal/store"
)

// LifeEventService 115生活事件监控服务
type LifeEventService struct {
	store      *store.Store
	driver115  *client.Driver115Client
	treeSvc    *TreeService
	strmSvc    *STRMService
	cleanerSvc *CleanerService
	embySvc    *EmbyProxyService
	debouncer  *EventDebouncer
	running    bool
	stopCh     chan struct{}
	mu         sync.RWMutex
	processing atomic.Bool
}

type deleteInfo struct {
	nodes []*model.FileTreeNode
	isDir bool
}

// NewLifeEventService 创建生活事件服务
func NewLifeEventService(store *store.Store, driver115 *client.Driver115Client, treeSvc *TreeService) *LifeEventService {
	svc := &LifeEventService{
		store:     store,
		driver115: driver115,
		treeSvc:   treeSvc,
		stopCh:    make(chan struct{}),
	}
	svc.debouncer = NewEventDebouncer(3*time.Second, svc.batchRefresh)
	return svc
}

// SetDependencies 设置依赖服务
func (s *LifeEventService) SetDependencies(strmSvc *STRMService, cleanerSvc *CleanerService, embySvc *EmbyProxyService) {
	s.strmSvc = strmSvc
	s.cleanerSvc = cleanerSvc
	s.embySvc = embySvc
}

// batchRefresh 批量刷新媒体库
func (s *LifeEventService) batchRefresh(paths map[int64][]string) {
	if s.embySvc == nil {
		return
	}
	for ruleID, pathList := range paths {
		// 提取所有父目录并去重
		parentDirs := make(map[string]bool)
		for _, path := range pathList {
			parentDirs[filepath.Dir(path)] = true
		}
		log.Printf("[LifeEvent] 规则%d: %d个文件 -> %d个父目录需刷新", ruleID, len(pathList), len(parentDirs))
		for dir := range parentDirs {
			s.embySvc.RefreshLibraryPath(dir)
		}
	}
}

// Start 启动轮询
func (s *LifeEventService) Start() error {
	s.mu.Lock()
	defer s.mu.Unlock()

	if s.running {
		return nil
	}

	s.running = true
	go s.pollLoop()
	log.Printf("[LifeEvent] 115生活事件监控已启动，轮询间隔30秒")
	return nil
}

// Stop 停止轮询
func (s *LifeEventService) Stop() {
	s.mu.Lock()
	defer s.mu.Unlock()

	if !s.running {
		return
	}

	close(s.stopCh)
	s.running = false
	log.Printf("[LifeEvent] 115生活事件监控已停止")
}

// IsRunning 是否运行中
func (s *LifeEventService) IsRunning() bool {
	s.mu.RLock()
	defer s.mu.RUnlock()
	return s.running
}

// pollLoop 轮询循环
func (s *LifeEventService) pollLoop() {
	ticker := time.NewTicker(30 * time.Second)
	defer ticker.Stop()

	// 启动时立即执行一次
	s.pollOnce()

	for {
		select {
		case <-s.stopCh:
			return
		case <-ticker.C:
			s.pollOnce()
		}
	}
}

// pollOnce 单次拉取
func (s *LifeEventService) pollOnce() {
	// 检查是否正在处理
	if !s.processing.CompareAndSwap(false, true) {
		log.Printf("[LifeEvent] 上次处理未完成,跳过本次拉取")
		return
	}
	defer s.processing.Store(false)

	log.Printf("[LifeEvent] 开始拉取事件...")
	state, err := s.store.GetLifeEventState()
	if err != nil {
		log.Printf("[LifeEvent] 获取状态失败: %v", err)
		return
	}
	log.Printf("[LifeEvent] 当前状态: from_time=%d, from_id=%d", state.FromTime, state.FromID)

	events, err := s.driver115.GetLifeEvents(state.FromTime, state.FromID)
	if err != nil {
		log.Printf("[LifeEvent] 拉取事件失败: %v", err)
		return
	}

	if len(events) == 0 {
		log.Printf("[LifeEvent] 无新事件")
		return
	}

	log.Printf("[LifeEvent] 拉取到 %d 个事件", len(events))
	s.processBatchEvents(events)

	firstEvent := events[0]
	s.store.UpdateLifeEventState(firstEvent.UpdateTime, firstEvent.ID)
	log.Printf("[LifeEvent] 状态已更新: from_time=%d, from_id=%d", firstEvent.UpdateTime, firstEvent.ID)
}

// processEvent 处理事件
func (s *LifeEventService) processEvent(event *model.LifeEvent) {
	// 只处理上传(1,2)、移动(5,6)、接收(14)、删除(22)事件
	if event.Type != 1 && event.Type != 2 && event.Type != 5 && event.Type != 6 && event.Type != 14 && event.Type != 22 {
		log.Printf("[LifeEvent] 跳过事件类型 %d (不在处理范围内)", event.Type)
		return
	}

	log.Printf("[LifeEvent] 处理事件详情: Type=%d, FileID=%s, ParentID=%s, FileName=%s, FileCategory=%d, FileSize=%d",
		event.Type, event.FileID, event.ParentID, event.FileName, event.FileCategory, event.FileSize)

	rules, err := s.store.GetAllRules()
	if err != nil {
		log.Printf("[LifeEvent] 获取规则失败: %v", err)
		return
	}
	log.Printf("[LifeEvent] 共有 %d 个规则", len(rules))

	matchedCount := 0
	for _, rule := range rules {
		if !rule.Enabled || !model.HasSyncMode(string(rule.SyncMode), model.SyncModeRealtime) {
			continue
		}
		matchedCount++
		log.Printf("[LifeEvent] 规则 %s (ID=%d) 启用了实时监控", rule.Name, rule.ID)

		if event.Type == 22 {
			log.Printf("[LifeEvent] 处理删除事件")
			s.handleDelete(event, rule)
		} else {
			log.Printf("[LifeEvent] 处理添加/移动事件")
			s.handleAddOrMove(event, rule)
		}
	}

	if matchedCount == 0 {
		log.Printf("[LifeEvent] 没有规则启用实时监控，跳过处理")
	}
}

// shouldProcessFile 检查文件是否应该被处理（根据规则的文件后缀配置）
func (s *LifeEventService) shouldProcessFile(ext string, rule *model.STRMRule) bool {
	// 如果规则配置了自定义文件后缀
	if rule.FileExtensions != "" {
		for _, ruleExt := range strings.Split(rule.FileExtensions, ",") {
			ruleExt = strings.TrimSpace(strings.ToLower(ruleExt))
			if ruleExt != "" {
				if !strings.HasPrefix(ruleExt, ".") {
					ruleExt = "." + ruleExt
				}
				if ext == ruleExt {
					return true
				}
			}
		}
		return false
	}
	// 使用默认视频后缀
	return videoExtensions[ext]
}

// handleAddOrMove 处理上传/移动/接收事件
func (s *LifeEventService) handleAddOrMove(event *model.LifeEvent, rule *model.STRMRule) {
	// 只对文件进行后缀检查，文件夹(FileCategory=0)直接处理
	if event.FileCategory != 0 {
		ext := strings.ToLower(filepath.Ext(event.FileName))
		if !s.shouldProcessFile(ext, rule) {
			log.Printf("[LifeEvent] 跳过非目标文件: FileName=%s, Ext=%s, 规则=%s", event.FileName, ext, rule.Name)
			s.store.MarkLifeEventProcessed(event.ID)
			return
		}
	} else {
		log.Printf("[LifeEvent] 处理文件夹添加/移动: FileName=%s", event.FileName)
	}

	log.Printf("[LifeEvent] handleAddOrMove: 查找父目录节点 ParentID=%s", event.ParentID)
	// 使用事件中的ParentID查找目录树节点
	nodes, err := s.store.GetTreeNodesByCID(rule.ID, event.ParentID)
	if err != nil || len(nodes) == 0 {
		log.Printf("[LifeEvent] 未找到父目录节点: ParentID=%s, err=%v", event.ParentID, err)
		s.store.MarkLifeEventProcessed(event.ID)
		return
	}

	parentNode := nodes[0]
	cd2Path := filepath.Join(parentNode.CD2Path, event.FileName)
	path115 := filepath.Join(parentNode.Path115, event.FileName)
	log.Printf("[LifeEvent] 父目录节点: CD2Path=%s, Path115=%s", parentNode.CD2Path, parentNode.Path115)
	log.Printf("[LifeEvent] 文件路径: CD2Path=%s, Path115=%s", cd2Path, path115)

	if !strings.HasPrefix(cd2Path, rule.SourcePath) {
		log.Printf("[LifeEvent] 文件不在规则源路径下: cd2Path=%s, sourcePath=%s", cd2Path, rule.SourcePath)
		s.store.MarkLifeEventProcessed(event.ID)
		return
	}

	// 触发快速扫描
	parentCD2 := filepath.Dir(cd2Path)
	parent115 := filepath.Dir(path115)
	log.Printf("[LifeEvent] 触发快速扫描: parentCD2=%s, parent115=%s", parentCD2, parent115)
	addedNodes, err := s.treeSvc.FastScanDirectory(rule, parentCD2, parent115)
	if err != nil {
		log.Printf("[LifeEvent] 快速扫描失败: %v", err)
	} else if len(addedNodes) > 0 {
		log.Printf("[LifeEvent] 快速扫描新增 %d 个节点，开始生成STRM", len(addedNodes))
		s.generateSTRMForNodes(rule, addedNodes)
	}
	s.store.MarkLifeEventProcessed(event.ID)
	log.Printf("[LifeEvent] 事件已标记为已处理: ID=%d", event.ID)
}

// handleDelete 处理删除事件
func (s *LifeEventService) handleDelete(event *model.LifeEvent, rule *model.STRMRule) {
	// 只对文件进行后缀检查，文件夹(FileCategory=0)直接处理
	if event.FileCategory != 0 {
		ext := strings.ToLower(filepath.Ext(event.FileName))
		if !s.shouldProcessFile(ext, rule) {
			log.Printf("[LifeEvent] 跳过非目标文件: FileName=%s, Ext=%s, 规则=%s", event.FileName, ext, rule.Name)
			s.store.MarkLifeEventProcessed(event.ID)
			return
		}
	} else {
		log.Printf("[LifeEvent] 处理文件夹删除: FileName=%s", event.FileName)
	}

	log.Printf("[LifeEvent] handleDelete: 查找节点 FileID=%s, FileName=%s, FileCategory=%d",
		event.FileID, event.FileName, event.FileCategory)
	// 通过FileID查找并删除节点
	nodes, err := s.store.GetTreeNodesByCID(rule.ID, event.FileID)
	if err != nil {
		log.Printf("[LifeEvent] 查询数据库出错: FileID=%s, err=%v", event.FileID, err)
	}
	if err != nil || len(nodes) == 0 {
		log.Printf("[LifeEvent] 数据库未找到节点: FileID=%s (规则=%s), 尝试通过ParentID构建路径",
			event.FileID, rule.Name)

		// 通过ParentID查找父目录节点
		parentNodes, err := s.store.GetTreeNodesByCID(rule.ID, event.ParentID)
		if err != nil || len(parentNodes) == 0 {
			log.Printf("[LifeEvent] 未找到父目录节点 ParentID=%s (规则=%s), 文件不在监控路径下或未入库，防止误删跳过处理",
				event.ParentID, rule.Name)
			s.store.MarkLifeEventProcessed(event.ID)
			return
		}

		parentNode := parentNodes[0]
		cd2Path := filepath.Join(parentNode.CD2Path, event.FileName)
		log.Printf("[LifeEvent] 父目录节点: CD2Path=%s, Path115=%s", parentNode.CD2Path, parentNode.Path115)
		log.Printf("[LifeEvent] 通过父目录构建路径: CD2Path=%s", cd2Path)

		// 检查路径是否在规则源路径下
		if !strings.HasPrefix(cd2Path, rule.SourcePath) {
			log.Printf("[LifeEvent] 文件不在规则源路径下: cd2Path=%s, sourcePath=%s", cd2Path, rule.SourcePath)
			s.store.MarkLifeEventProcessed(event.ID)
			return
		}

		// 删除该路径并执行智能清理
		log.Printf("[LifeEvent] 删除目录树节点: CD2Path=%s", cd2Path)
		deletedNodes, _ := s.treeSvc.DeleteTreeByPrefix(rule, cd2Path)
		s.handleSmartClean(rule, deletedNodes, event.FileCategory == 0)
		s.store.MarkLifeEventProcessed(event.ID)
		log.Printf("[LifeEvent] 事件已标记为已处理: ID=%d", event.ID)
		return
	}

	node := nodes[0]
	log.Printf("[LifeEvent] 找到节点: CD2Path=%s", node.CD2Path)

	if !strings.HasPrefix(node.CD2Path, rule.SourcePath) {
		log.Printf("[LifeEvent] 节点不在规则源路径下: cd2Path=%s, sourcePath=%s", node.CD2Path, rule.SourcePath)
		s.store.MarkLifeEventProcessed(event.ID)
		return
	}

	log.Printf("[LifeEvent] 删除目录树节点: CD2Path=%s", node.CD2Path)
	deletedNodes, _ := s.treeSvc.DeleteTreeByPrefix(rule, node.CD2Path)
	s.handleSmartClean(rule, deletedNodes, node.IsDir)
	s.store.MarkLifeEventProcessed(event.ID)
	log.Printf("[LifeEvent] 事件已标记为已处理: ID=%d", event.ID)
}

// processBatchEvents 批量处理事件
func (s *LifeEventService) processBatchEvents(events []model.LifeEvent) {
	rules, err := s.store.GetAllRules()
	if err != nil {
		log.Printf("[LifeEvent] 获取规则失败: %v", err)
		return
	}

	enabledRules := make([]*model.STRMRule, 0)
	for _, rule := range rules {
		if rule.Enabled && model.HasSyncMode(string(rule.SyncMode), model.SyncModeRealtime) {
			enabledRules = append(enabledRules, rule)
		}
	}

	if len(enabledRules) == 0 {
		return
	}

	// 按规则分组收集删除节点
	ruleDeletes := make(map[int64]*deleteInfo)

	for i, event := range events {
		log.Printf("[LifeEvent] 处理事件 %d/%d: ID=%d, Type=%d, FileName=%s", i+1, len(events), event.ID, event.Type, event.FileName)

		if event.Type == 22 {
			s.processBatchDelete(&event, enabledRules, ruleDeletes)
		} else if event.Type == 1 || event.Type == 2 || event.Type == 5 || event.Type == 6 || event.Type == 14 {
			s.processEvent(&event)
		}
	}

	// 批量执行智能清理和刷新
	for ruleID, delInfo := range ruleDeletes {
		for _, rule := range enabledRules {
			if rule.ID == ruleID && len(delInfo.nodes) > 0 {
				log.Printf("[LifeEvent] 规则%d批量清理%d个节点", ruleID, len(delInfo.nodes))
				s.handleSmartClean(rule, delInfo.nodes, delInfo.isDir)
				break
			}
		}
	}
}

// processBatchDelete 批量处理删除事件
func (s *LifeEventService) processBatchDelete(event *model.LifeEvent, rules []*model.STRMRule, ruleDeletes map[int64]*deleteInfo) {
	for _, rule := range rules {
		deletedNodes := s.handleDeleteForRule(event, rule)
		if len(deletedNodes) > 0 {
			if ruleDeletes[rule.ID] == nil {
				ruleDeletes[rule.ID] = &deleteInfo{nodes: make([]*model.FileTreeNode, 0), isDir: event.FileCategory == 0}
			}
			ruleDeletes[rule.ID].nodes = append(ruleDeletes[rule.ID].nodes, deletedNodes...)
		}
	}
	s.store.MarkLifeEventProcessed(event.ID)
}

// handleDeleteForRule 处理单个规则的删除
func (s *LifeEventService) handleDeleteForRule(event *model.LifeEvent, rule *model.STRMRule) []*model.FileTreeNode {
	if event.FileCategory != 0 {
		ext := strings.ToLower(filepath.Ext(event.FileName))
		if !s.shouldProcessFile(ext, rule) {
			return nil
		}
	}

	nodes, _ := s.store.GetTreeNodesByCID(rule.ID, event.FileID)
	if len(nodes) > 0 {
		node := nodes[0]
		if strings.HasPrefix(node.CD2Path, rule.SourcePath) {
			deletedNodes, _ := s.treeSvc.DeleteTreeByPrefix(rule, node.CD2Path)
			return deletedNodes
		}
	} else {
		parentNodes, _ := s.store.GetTreeNodesByCID(rule.ID, event.ParentID)
		if len(parentNodes) > 0 {
			cd2Path := filepath.Join(parentNodes[0].CD2Path, event.FileName)
			if strings.HasPrefix(cd2Path, rule.SourcePath) {
				deletedNodes, _ := s.treeSvc.DeleteTreeByPrefix(rule, cd2Path)
				return deletedNodes
			}
		}
	}
	return nil
}
