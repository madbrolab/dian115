package api

import (
	"fmt"
	"net/http"
	"strconv"
	"time"

	"github.com/gin-gonic/gin"

	"strm-manager/internal/model"
	"strm-manager/internal/service"
	"strm-manager/internal/util"
)

// SetTreeService 设置目录树服务
func (s *Server) SetTreeService(treeSvc *service.TreeService) {
	s.treeSvc = treeSvc
}

// buildTree 构建目录树
func (s *Server) buildTree(c *gin.Context) {
	idStr := c.Param("id")
	id, err := strconv.ParseInt(idStr, 10, 64)
	if err != nil {
		c.JSON(http.StatusBadRequest, gin.H{"error": "无效的规则ID"})
		return
	}

	rule, err := s.store.GetRule(id)
	if err != nil || rule == nil {
		c.JSON(http.StatusNotFound, gin.H{"error": "规则不存在"})
		return
	}

	if s.treeSvc == nil {
		c.JSON(http.StatusInternalServerError, gin.H{"error": "目录树服务未初始化"})
		return
	}

	if rule.CloudName == "" {
		c.JSON(http.StatusBadRequest, gin.H{"error": "请先配置云盘名称（cloud_name）"})
		return
	}

	// 创建后台任务
	task := s.taskMgr.CreateTask(service.TaskTypeBuildTree, fmt.Sprintf("构建目录树: %s", rule.Name), rule.ID, rule.Name, service.SyncTypeFull)

	go func() {
		task.UpdateTask(service.TaskStatusRunning, "正在构建目录树...")
		err := s.treeSvc.BuildTree(rule, task)
		if err != nil {
			task.SetError(err.Error())
			task.UpdateTask(service.TaskStatusFailed, "构建失败: "+err.Error())
		} else {
			task.UpdateTask(service.TaskStatusCompleted, "目录树构建完成")
		}
	}()

	c.JSON(http.StatusOK, gin.H{
		"message": "目录树构建任务已启动",
		"task_id": task.ID,
	})
}

// getTreeStats 获取目录树统计
func (s *Server) getTreeStats(c *gin.Context) {
	idStr := c.Param("id")
	id, err := strconv.ParseInt(idStr, 10, 64)
	if err != nil {
		c.JSON(http.StatusBadRequest, gin.H{"error": "无效的规则ID"})
		return
	}

	files, dirs, totalSize, err := s.store.GetTreeStats(id)
	if err != nil {
		c.JSON(http.StatusInternalServerError, gin.H{"error": err.Error()})
		return
	}

	c.JSON(http.StatusOK, gin.H{
		"rule_id":    id,
		"files":      files,
		"dirs":       dirs,
		"total_size": totalSize,
	})
}

// deleteTree 删除目录树
func (s *Server) deleteTree(c *gin.Context) {
	idStr := c.Param("id")
	id, err := strconv.ParseInt(idStr, 10, 64)
	if err != nil {
		c.JSON(http.StatusBadRequest, gin.H{"error": "无效的规则ID"})
		return
	}

	if err := s.store.DeleteTreeByRuleID(id); err != nil {
		c.JSON(http.StatusInternalServerError, gin.H{"error": err.Error()})
		return
	}

	// 更新规则状态
	s.store.UpdateRuleTreeStatus(id, false, 0)

	c.JSON(http.StatusOK, gin.H{"message": "目录树已删除"})
}

// splitAndTrim 分割并去除空白
func splitAndTrim(s string, sep string) []string {
	parts := make([]string, 0)
	for _, p := range splitString(s, sep) {
		p = trimSpace(p)
		if p != "" {
			parts = append(parts, p)
		}
	}
	return parts
}

func splitString(s, sep string) []string {
	result := make([]string, 0)
	for len(s) > 0 {
		idx := indexOf(s, sep)
		if idx < 0 {
			result = append(result, s)
			break
		}
		result = append(result, s[:idx])
		s = s[idx+len(sep):]
	}
	return result
}

func indexOf(s, sub string) int {
	for i := 0; i <= len(s)-len(sub); i++ {
		if s[i:i+len(sub)] == sub {
			return i
		}
	}
	return -1
}

func trimSpace(s string) string {
	start := 0
	end := len(s)
	for start < end && (s[start] == ' ' || s[start] == '\t' || s[start] == '\n' || s[start] == '\r') {
		start++
	}
	for end > start && (s[end-1] == ' ' || s[end-1] == '\t' || s[end-1] == '\n' || s[end-1] == '\r') {
		end--
	}
	return s[start:end]
}

// toggleRule 启用/停用规则
func (s *Server) toggleRule(c *gin.Context) {
	idStr := c.Param("id")
	id, err := strconv.ParseInt(idStr, 10, 64)
	if err != nil {
		c.JSON(http.StatusBadRequest, gin.H{"error": "无效的规则ID"})
		return
	}

	rule, err := s.store.GetRule(id)
	if err != nil || rule == nil {
		c.JSON(http.StatusNotFound, gin.H{"error": "规则不存在"})
		return
	}

	// 切换启用状态
	rule.Enabled = !rule.Enabled
	if err := s.store.UpdateRule(rule); err != nil {
		c.JSON(http.StatusInternalServerError, gin.H{"error": err.Error()})
		return
	}

	status := "已启用"
	if !rule.Enabled {
		status = "已停用"
	}

	if s.logger != nil {
		s.logger.LogSync(model.LogLevelInfo, fmt.Sprintf("规则 %s %s", rule.Name, status), nil, rule.ID)
	}

	// 刷新监控
	s.monitorSvc.RefreshWatchers()

	c.JSON(http.StatusOK, gin.H{
		"message": fmt.Sprintf("规则 %s %s", rule.Name, status),
		"enabled": rule.Enabled,
	})
}

// fullSyncRule 全量同步（重建目录树 + 同步STRM）
func (s *Server) fullSyncRule(c *gin.Context) {
	id, err := strconv.ParseInt(c.Param("id"), 10, 64)
	if err != nil {
		c.JSON(http.StatusBadRequest, gin.H{"error": "无效的规则ID"})
		return
	}

	rule, err := s.store.GetRule(id)
	if err != nil || rule == nil {
		c.JSON(http.StatusNotFound, gin.H{"error": "规则不存在"})
		return
	}

	// 创建后台任务
	task := s.taskMgr.CreateTask(service.TaskTypeSync, "全量同步: "+rule.Name, rule.ID, rule.Name, service.SyncTypeFull)

	go func() {
		startTime := time.Now()
		task.UpdateTask(service.TaskStatusRunning, "正在全量同步...")

		// 重建目录树
		if s.treeSvc != nil {
			task.AddLog("🌳 步骤1: 重建目录树...")
			if err := s.treeSvc.BuildTree(rule, task); err != nil {
				task.SetError(err.Error())
				task.UpdateTask(service.TaskStatusFailed, "目录树构建失败: "+err.Error())
				return
			}
			// 重新加载规则（目录树状态已更新）
			rule, _ = s.store.GetRule(id)
		}

		// 同步STRM
		task.AddLog("📝 步骤2: 同步STRM文件...")
		result, err := s.strmSvc.SyncRuleWithTask(rule, task)
		if err != nil {
			task.SetError(err.Error())
			task.UpdateTask(service.TaskStatusFailed, "同步失败: "+err.Error())
			return
		}

		duration := time.Since(startTime).Milliseconds()
		task.SetDeleted(result.Deleted)
		task.UpdateTask(service.TaskStatusCompleted, fmt.Sprintf("全量同步完成 (成功:%d 失败:%d 删除:%d 耗时:%s)", result.Success, result.Failed, result.Deleted, util.FormatMilliseconds(duration)))

		if s.logger != nil {
			s.logger.LogSync(model.LogLevelSuccess, fmt.Sprintf("全量同步完成: %s", rule.Name), map[string]string{
				"success":  fmt.Sprintf("%d", result.Success),
				"failed":   fmt.Sprintf("%d", result.Failed),
				"deleted":  fmt.Sprintf("%d", result.Deleted),
				"duration": util.FormatMilliseconds(duration),
			}, rule.ID)
		}
	}()

	c.JSON(http.StatusOK, gin.H{
		"message": "全量同步任务已启动",
		"task_id": task.ID,
	})
}
