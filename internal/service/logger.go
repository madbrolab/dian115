package service

import (
	"encoding/json"
	"log"
	"sync"
	"time"

	"strm-manager/internal/model"
	"strm-manager/internal/store"
)

// LoggerService 日志服务
type LoggerService struct {
	store       *store.Store
	subscribers map[string]chan *model.LogEntry
	mu          sync.RWMutex
}

// NewLoggerService 创建日志服务
func NewLoggerService(store *store.Store) *LoggerService {
	return &LoggerService{
		store:       store,
		subscribers: make(map[string]chan *model.LogEntry),
	}
}

// Log 记录日志（完整参数）
func (l *LoggerService) Log(logType model.LogType, category model.LogCategory, level model.LogLevel, message string, details interface{}, ruleID int64) {
	var detailsStr string
	if details != nil {
		if b, err := json.Marshal(details); err == nil {
			detailsStr = string(b)
		}
	}

	entry := &model.LogEntry{
		Type:      logType,
		Category:  category,
		Level:     level,
		Message:   message,
		Details:   detailsStr,
		RuleID:    ruleID,
		CreatedAt: time.Now(),
	}

	// 保存到数据库
	if err := l.store.CreateLogEntry(entry); err != nil {
		log.Printf("[Logger] 保存日志失败: %v", err)
	}

	// 广播给所有订阅者
	l.broadcast(entry)
}

// ==================== 按模块的便捷方法 ====================

// LogSync 记录STRM同步日志
func (l *LoggerService) LogSync(level model.LogLevel, message string, details interface{}, ruleID int64) {
	l.Log(model.LogTypeSync, levelToCategory(level), level, message, details, ruleID)
}

// LogArchive 记录归档日志
func (l *LoggerService) LogArchive(level model.LogLevel, message string, details interface{}, ruleID int64) {
	l.Log(model.LogTypeArchive, levelToCategory(level), level, message, details, ruleID)
}

// LogSystem 记录系统日志
func (l *LoggerService) LogSystem(level model.LogLevel, message string, details interface{}) {
	l.Log(model.LogTypeSystem, levelToCategory(level), level, message, details, 0)
}

// LogEmby 记录Emby代理日志
func (l *LoggerService) LogEmby(category model.LogCategory, level model.LogLevel, message string, details interface{}) {
	l.Log(model.LogTypeEmby, category, level, message, details, 0)
}

// Log115 记录115网盘日志
func (l *LoggerService) Log115(category model.LogCategory, level model.LogLevel, message string, details interface{}) {
	l.Log(model.LogType115, category, level, message, details, 0)
}

// LogMonitor 记录文件监控日志
func (l *LoggerService) LogMonitor(level model.LogLevel, message string, details interface{}, ruleID int64) {
	l.Log(model.LogTypeMonitor, levelToCategory(level), level, message, details, ruleID)
}

// LogScheduler 记录定时任务日志
func (l *LoggerService) LogScheduler(level model.LogLevel, message string, details interface{}, ruleID int64) {
	l.Log(model.LogTypeScheduler, levelToCategory(level), level, message, details, ruleID)
}

// LogAPI 记录API请求日志
func (l *LoggerService) LogAPI(level model.LogLevel, message string, details interface{}) {
	l.Log(model.LogTypeAPI, levelToCategory(level), level, message, details, 0)
}

// ==================== 按级别的便捷方法 ====================

// Debug 记录调试日志
func (l *LoggerService) Debug(logType model.LogType, message string, details interface{}) {
	l.Log(logType, model.LogCategoryNormal, model.LogLevelDebug, message, details, 0)
}

// Info 记录信息日志
func (l *LoggerService) Info(logType model.LogType, message string, details interface{}) {
	l.Log(logType, model.LogCategoryNormal, model.LogLevelInfo, message, details, 0)
}

// Success 记录成功日志
func (l *LoggerService) Success(logType model.LogType, message string, details interface{}) {
	l.Log(logType, model.LogCategorySuccess, model.LogLevelSuccess, message, details, 0)
}

// Warning 记录警告日志
func (l *LoggerService) Warning(logType model.LogType, message string, details interface{}) {
	l.Log(logType, model.LogCategoryFail, model.LogLevelWarning, message, details, 0)
}

// Error 记录错误日志
func (l *LoggerService) Error(logType model.LogType, message string, details interface{}) {
	l.Log(logType, model.LogCategoryError, model.LogLevelError, message, details, 0)
}

// levelToCategory 根据日志级别自动映射类别
func levelToCategory(level model.LogLevel) model.LogCategory {
	switch level {
	case model.LogLevelSuccess:
		return model.LogCategorySuccess
	case model.LogLevelError:
		return model.LogCategoryError
	case model.LogLevelWarning:
		return model.LogCategoryFail
	default:
		return model.LogCategoryNormal
	}
}

// ==================== 订阅系统 ====================

// Subscribe 订阅日志
func (l *LoggerService) Subscribe(id string) chan *model.LogEntry {
	l.mu.Lock()
	defer l.mu.Unlock()

	ch := make(chan *model.LogEntry, 100)
	l.subscribers[id] = ch
	return ch
}

// Unsubscribe 取消订阅
func (l *LoggerService) Unsubscribe(id string) {
	l.mu.Lock()
	defer l.mu.Unlock()

	if ch, ok := l.subscribers[id]; ok {
		close(ch)
		delete(l.subscribers, id)
	}
}

// broadcast 广播日志给所有订阅者
func (l *LoggerService) broadcast(entry *model.LogEntry) {
	l.mu.RLock()
	defer l.mu.RUnlock()

	for _, ch := range l.subscribers {
		select {
		case ch <- entry:
		default:
			// 通道满了，跳过
		}
	}
}

// ==================== 查询方法 ====================

// GetLogs 获取日志列表
func (l *LoggerService) GetLogs(logType string, category string, level string, limit, offset int) ([]*model.LogEntry, int, error) {
	return l.store.GetLogEntries(logType, category, level, limit, offset)
}

// ClearLogs 清空日志
func (l *LoggerService) ClearLogs(logType string) error {
	return l.store.ClearLogEntries(logType)
}

// GetRecentStats 获取最近统计
func (l *LoggerService) GetRecentStats() (map[string]interface{}, error) {
	return l.store.GetLogStats()
}
