package service

import (
	"log"
	"sync"

	"strm-manager/internal/client"
	"strm-manager/internal/model"
	"strm-manager/internal/store"
)

// MonitorManager 监控管理器（统一管理CD2和115生活事件两种模式）
type MonitorManager struct {
	store       *store.Store
	cd2Monitor  *MonitorService
	lifeMonitor *LifeEventService
	currentMode model.MonitorMode
	mu          sync.RWMutex
}

// NewMonitorManager 创建监控管理器
func NewMonitorManager(store *store.Store, cd2 *client.CloudDriveClient, driver115 *client.Driver115Client, strm *STRMService, treeSvc *TreeService) *MonitorManager {
	return &MonitorManager{
		store:       store,
		cd2Monitor:  NewMonitorService(store, cd2, strm),
		lifeMonitor: NewLifeEventService(store, driver115, treeSvc),
	}
}

// SetDependencies 设置依赖服务
func (m *MonitorManager) SetDependencies(logger *LoggerService, treeSvc *TreeService, cleanerSvc *CleanerService, embySvc *EmbyProxyService, wq *WorkQueue, strmSvc *STRMService) {
	m.cd2Monitor.SetLogger(logger)
	m.cd2Monitor.SetTreeService(treeSvc)
	m.cd2Monitor.SetCleanerService(cleanerSvc)
	m.cd2Monitor.SetEmbyService(embySvc)
	m.cd2Monitor.SetWorkQueue(wq)

	// 设置 LifeEventService 的依赖
	m.lifeMonitor.SetDependencies(strmSvc, cleanerSvc, embySvc)
}

// Start 启动监控（根据配置的模式）
func (m *MonitorManager) Start() error {
	config, err := m.store.GetMonitorConfig()
	if err != nil {
		return err
	}

	m.mu.Lock()
	m.currentMode = config.Mode
	m.mu.Unlock()

	// 检查是否有规则启用了实时监控
	rules, err := m.store.GetRulesBySyncMode(model.SyncModeRealtime)
	if err != nil {
		return err
	}

	if len(rules) == 0 {
		log.Printf("[MonitorManager] 无实时监控规则，跳过启动")
		return nil
	}

	if config.Mode == model.MonitorModeCD2 {
		log.Printf("[MonitorManager] 启动CD2监控模式")
		return m.cd2Monitor.Start()
	} else {
		log.Printf("[MonitorManager] 启动115生活事件监控模式")
		return m.lifeMonitor.Start()
	}
}

// Stop 停止监控
func (m *MonitorManager) Stop() {
	m.cd2Monitor.Stop()
	m.lifeMonitor.Stop()
}

// SwitchMode 切换监控模式
func (m *MonitorManager) SwitchMode(mode model.MonitorMode) error {
	m.mu.Lock()
	defer m.mu.Unlock()

	if m.currentMode == mode {
		return nil
	}

	// 停止当前模式
	if m.currentMode == model.MonitorModeCD2 {
		m.cd2Monitor.Stop()
	} else {
		m.lifeMonitor.Stop()
	}

	// 保存新模式
	if err := m.store.SetMonitorMode(mode); err != nil {
		return err
	}

	m.currentMode = mode

	// 启动新模式
	rules, _ := m.store.GetRulesBySyncMode(model.SyncModeRealtime)
	if len(rules) > 0 {
		if mode == model.MonitorModeCD2 {
			m.cd2Monitor.Start()
		} else {
			m.lifeMonitor.Start()
		}
	}

	log.Printf("[MonitorManager] 已切换到 %s 监控模式", mode)
	return nil
}

// GetCurrentMode 获取当前监控模式
func (m *MonitorManager) GetCurrentMode() model.MonitorMode {
	m.mu.RLock()
	defer m.mu.RUnlock()
	return m.currentMode
}

// IsRunning 是否运行中
func (m *MonitorManager) IsRunning() bool {
	m.mu.RLock()
	mode := m.currentMode
	m.mu.RUnlock()

	if mode == model.MonitorModeCD2 {
		return m.cd2Monitor.IsRunning()
	}
	return m.lifeMonitor.IsRunning()
}
