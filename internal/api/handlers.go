package api

import (
	"context"
	"encoding/json"
	"fmt"
	"log"
	"net/http"
	"os"
	"path/filepath"
	"strconv"
	"time"

	"github.com/gin-gonic/gin"

	"strm-manager/internal/client"
	"strm-manager/internal/model"
	"strm-manager/internal/service"
	"strm-manager/internal/util"
)

// 保留config包的引用以便后续使用
var _ = struct{}{}

// ==================== 文件浏览 ====================

// browseCD2Path 浏览CD2目录
func (s *Server) browseCD2Path(c *gin.Context) {
	path := c.Query("path")
	if path == "" {
		path = "/"
	}

	ctx, cancel := context.WithTimeout(context.Background(), 30*time.Second)
	defer cancel()

	files, err := s.cd2.GetSubFiles(ctx, path, false)
	if err != nil {
		log.Printf("[browseCD2Path] 获取目录失败: %v", err)
		s.logger.LogSystem(model.LogLevelError, fmt.Sprintf("浏览CD2目录失败: %s - %s", path, err.Error()), nil)
		c.JSON(http.StatusInternalServerError, gin.H{"error": err.Error()})
		return
	}

	// 转换为前端需要的格式
	var result []map[string]interface{}
	for _, f := range files {
		result = append(result, map[string]interface{}{
			"name":   f.Name,
			"path":   f.FullPathName,
			"is_dir": f.IsDirectory,
			"size":   f.Size,
		})
	}

	c.JSON(http.StatusOK, gin.H{
		"path":  path,
		"files": result,
	})
}

// ==================== 系统状态 ====================

func (s *Server) getStatus(c *gin.Context) {
	// 检查CD2连接
	cd2Connected := s.cd2.TestConnection() == nil

	// 检查115登录状态（从数据库读取，不调用115 API）
	login115 := false
	user115 := ""
	if activeAccount, err := s.store.GetActiveAccount115(); err == nil && activeAccount != nil {
		if activeAccount.CookieStatus == model.CookieStatusValid {
			login115 = true
			user115 = activeAccount.UserName
		}
	}

	// 检查Emby连接（从302反代配置检查）
	embyConnected := false
	if proxies, err := s.store.GetAllEmbyProxies(); err == nil {
		for _, proxy := range proxies {
			if proxy.Enabled && proxy.EmbyHost != "" {
				if s.testEmbyConnection(proxy.EmbyHost, proxy.APIKey) == nil {
					embyConnected = true
					break
				}
			}
		}
	}

	// 获取统计
	ruleCount := 0
	fileCount := 0
	if rules, err := s.store.GetAllRules(); err == nil {
		ruleCount = len(rules)
	}
	if count, err := s.store.GetFileMappingCount(); err == nil {
		fileCount = count
	}

	c.JSON(http.StatusOK, model.SystemStatus{
		CD2Connected:  cd2Connected,
		Login115:      login115,
		User115:       user115,
		EmbyConnected: embyConnected,
		RuleCount:     ruleCount,
		FileCount:     fileCount,
	})
}

// ==================== STRM规则 ====================

func (s *Server) getRules(c *gin.Context) {
	rules, err := s.store.GetAllRules()
	if err != nil {
		c.JSON(http.StatusInternalServerError, gin.H{"error": err.Error()})
		return
	}

	// 丰富规则数据：添加目录树统计和实际文件映射数
	type RuleWithStats struct {
		*model.STRMRule
		TreeDirCount   int `json:"tree_dir_count"`
		TreeVideoCount int `json:"tree_video_count"`
	}

	var result []RuleWithStats
	for _, rule := range rules {
		rws := RuleWithStats{STRMRule: rule}

		// 用实际 file_mappings 数量覆盖 file_count（确保准确）
		if count, err := s.store.GetFileMappingCountByRuleID(rule.ID); err == nil {
			rws.FileCount = count
		}

		// 获取目录树统计
		if rule.TreeBuilt {
			if files, dirs, _, err := s.store.GetTreeStats(rule.ID); err == nil {
				rws.TreeDirCount = dirs
				rws.TreeVideoCount = files
			}
		}

		result = append(result, rws)
	}

	c.JSON(http.StatusOK, result)
}

func (s *Server) createRule(c *gin.Context) {
	var rule model.STRMRule
	if err := c.ShouldBindJSON(&rule); err != nil {
		c.JSON(http.StatusBadRequest, gin.H{"error": err.Error()})
		return
	}

	if err := s.store.CreateRule(&rule); err != nil {
		s.logger.LogSync(model.LogLevelError, fmt.Sprintf("创建规则失败: %s", err.Error()), map[string]string{"rule_name": rule.Name}, 0)
		c.JSON(http.StatusInternalServerError, gin.H{"error": err.Error()})
		return
	}

	s.logger.LogSync(model.LogLevelSuccess, fmt.Sprintf("创建规则成功: %s", rule.Name), map[string]string{
		"source_path": rule.SourcePath,
		"output_path": rule.OutputPath,
		"sync_mode":   string(rule.SyncMode),
	}, rule.ID)

	// 刷新监控
	s.monitorSvc.RefreshWatchers()

	c.JSON(http.StatusOK, rule)
}

func (s *Server) updateRule(c *gin.Context) {
	id, err := strconv.ParseInt(c.Param("id"), 10, 64)
	if err != nil {
		c.JSON(http.StatusBadRequest, gin.H{"error": "无效的ID"})
		return
	}

	var rule model.STRMRule
	if err := c.ShouldBindJSON(&rule); err != nil {
		c.JSON(http.StatusBadRequest, gin.H{"error": err.Error()})
		return
	}
	rule.ID = id

	if err := s.store.UpdateRule(&rule); err != nil {
		s.logger.LogSync(model.LogLevelError, fmt.Sprintf("更新规则失败: %s", err.Error()), nil, id)
		c.JSON(http.StatusInternalServerError, gin.H{"error": err.Error()})
		return
	}

	s.logger.LogSync(model.LogLevelSuccess, fmt.Sprintf("更新规则成功: %s", rule.Name), nil, id)

	// 刷新监控
	s.monitorSvc.RefreshWatchers()

	c.JSON(http.StatusOK, rule)
}

func (s *Server) deleteRule(c *gin.Context) {
	id, err := strconv.ParseInt(c.Param("id"), 10, 64)
	if err != nil {
		c.JSON(http.StatusBadRequest, gin.H{"error": "无效的ID"})
		return
	}

	if err := s.store.DeleteRule(id); err != nil {
		s.logger.LogSync(model.LogLevelError, fmt.Sprintf("删除规则失败: %s", err.Error()), nil, id)
		c.JSON(http.StatusInternalServerError, gin.H{"error": err.Error()})
		return
	}

	s.logger.LogSync(model.LogLevelInfo, fmt.Sprintf("删除规则: ID=%d", id), nil, id)

	// 刷新监控
	s.monitorSvc.RefreshWatchers()

	c.JSON(http.StatusOK, gin.H{"success": true})
}

func (s *Server) syncRule(c *gin.Context) {
	id, err := strconv.ParseInt(c.Param("id"), 10, 64)
	if err != nil {
		c.JSON(http.StatusBadRequest, gin.H{"error": "无效的ID"})
		return
	}

	rule, err := s.store.GetRule(id)
	if err != nil {
		c.JSON(http.StatusInternalServerError, gin.H{"error": err.Error()})
		return
	}
	if rule == nil {
		c.JSON(http.StatusNotFound, gin.H{"error": "规则不存在"})
		return
	}

	// 创建后台任务
	task := s.taskMgr.CreateTask(service.TaskTypeSync, "同步规则: "+rule.Name, rule.ID, rule.Name, service.SyncTypeFull)

	// 异步执行同步
	go s.executeSyncTask(task, rule)

	// 立即返回任务信息
	c.JSON(http.StatusOK, gin.H{
		"task_id": task.ID,
		"message": "同步任务已创建，正在后台执行",
	})
}

// executeSyncTask 执行同步任务
func (s *Server) executeSyncTask(task *service.Task, rule *model.STRMRule) {
	startTime := time.Now()
	task.UpdateTask(service.TaskStatusRunning, "正在同步...")
	s.logger.LogSync(model.LogLevelInfo, fmt.Sprintf("开始同步规则: %s", rule.Name), map[string]string{
		"source_path": rule.SourcePath,
		"output_path": rule.OutputPath,
	}, rule.ID)

	// 先执行增量扫描更新目录树
	if s.treeSvc != nil {
		task.AddLog("🔄 增量扫描目录树...")
		scanResult, err := s.treeSvc.IncrementalScan(rule, task)
		if err != nil {
			s.logger.LogSync(model.LogLevelWarning, fmt.Sprintf("增量扫描失败: %s - %s", rule.Name, err.Error()), nil, rule.ID)
			task.AddLog(fmt.Sprintf("⚠️ 增量扫描失败: %s，继续同步", err.Error()))
		} else {
			task.AddLog(fmt.Sprintf("✅ 增量扫描完成: 新增 %d, 删除 %d", len(scanResult.AddedNodes), len(scanResult.DeletedNodes)))
		}
	}

	result, err := s.strmSvc.SyncRuleWithTask(rule, task)
	duration := time.Since(startTime).Milliseconds()

	if err != nil {
		task.SetError(err.Error())
		task.UpdateTask(service.TaskStatusFailed, "同步失败: "+err.Error())
		s.logger.LogSync(model.LogLevelError, fmt.Sprintf("同步规则失败: %s - %s", rule.Name, err.Error()), map[string]string{
			"duration": util.FormatMilliseconds(duration),
		}, rule.ID)
		// 记录失败的历史
		s.saveHistoryRecord("sync", rule.ID, rule.Name, 0, 1, 0, duration, err.Error())
		return
	}

	task.SetDeleted(result.Deleted)
	task.UpdateTask(service.TaskStatusCompleted, "同步完成")

	// 更新规则的文件计数和最后同步时间
	if count, err := s.store.GetFileMappingCountByRuleID(rule.ID); err == nil {
		s.store.UpdateRuleFileCount(rule.ID, count)
	}
	s.store.UpdateRuleLastSyncTime(rule.ID, time.Now())

	s.logger.LogSync(model.LogLevelSuccess, fmt.Sprintf("同步规则完成: %s (成功:%d 失败:%d 删除:%d 耗时:%s)", rule.Name, result.Success, result.Failed, result.Deleted, util.FormatMilliseconds(duration)), map[string]string{
		"success":  fmt.Sprintf("%d", result.Success),
		"failed":   fmt.Sprintf("%d", result.Failed),
		"deleted":  fmt.Sprintf("%d", result.Deleted),
		"duration": util.FormatMilliseconds(duration),
	}, rule.ID)

	// 保存历史记录
	s.saveHistoryRecord("sync", rule.ID, rule.Name, result.Success, result.Failed, result.Deleted, duration, "")

	// 同步完成后通知Emby刷新媒体库
	s.notifyEmbyRefresh(rule.OutputPath)
}

// saveHistoryRecord 保存历史记录
func (s *Server) saveHistoryRecord(recordType string, ruleID int64, ruleName string, success, failed, deleted int, duration int64, errMsg string) {
	details := ""
	if errMsg != "" {
		details = errMsg
	}

	record := &model.HistoryRecord{
		Type:     recordType,
		RuleID:   ruleID,
		RuleName: ruleName,
		Success:  success,
		Failed:   failed,
		Deleted:  deleted,
		Duration: duration,
		Details:  details,
	}

	if err := s.store.CreateHistoryRecord(record); err != nil {
		log.Printf("[History] 保存历史记录失败: %v", err)
		s.logger.LogSystem(model.LogLevelError, "保存历史记录失败: "+err.Error(), nil)
	}
}

// notifyEmbyRefresh 通知Emby刷新媒体库
func (s *Server) notifyEmbyRefresh(path string) {
	// 获取所有启用的Emby代理配置
	proxies, err := s.store.GetAllEmbyProxies()
	if err != nil {
		log.Printf("[Sync] 获取Emby代理配置失败: %v", err)
		s.logger.LogEmby(model.LogCategoryError, model.LogLevelError, "获取Emby代理配置失败: "+err.Error(), nil)
		return
	}

	for _, proxy := range proxies {
		if !proxy.Enabled || proxy.EmbyHost == "" {
			continue
		}

		// 创建临时Emby服务来刷新
		embySvc, err := service.NewEmbyProxyServiceWithTarget(proxy.EmbyHost, proxy.APIKey, s.cfg, s.store, s.driver115, s.cd2)
		if err != nil {
			log.Printf("[Sync] 创建Emby服务失败: %v", err)
			s.logger.LogEmby(model.LogCategoryError, model.LogLevelError, fmt.Sprintf("创建Emby服务失败: %s", err.Error()), nil)
			continue
		}

		// 刷新整个媒体库
		if err := embySvc.RefreshLibrary(); err != nil {
			log.Printf("[Sync] 通知Emby刷新失败 (%s): %v", proxy.Name, err)
			s.logger.LogEmby(model.LogCategoryFail, model.LogLevelWarning, fmt.Sprintf("通知Emby刷新失败: %s", proxy.Name), map[string]string{"error": err.Error()})
		} else {
			log.Printf("[Sync] 已通知Emby刷新媒体库: %s", proxy.Name)
			s.logger.LogEmby(model.LogCategorySuccess, model.LogLevelSuccess, fmt.Sprintf("已通知Emby刷新媒体库: %s", proxy.Name), nil)
		}
	}
}

func (s *Server) syncAllRules(c *gin.Context) {
	rules, err := s.store.GetEnabledRules()
	if err != nil {
		c.JSON(http.StatusInternalServerError, gin.H{"error": err.Error()})
		return
	}

	// 创建后台任务
	task := s.taskMgr.CreateTask(service.TaskTypeSyncAll, "同步所有规则", 0, "", service.SyncTypeFull)

	// 异步执行同步
	go s.executeSyncAllTask(task, rules)

	// 立即返回任务信息
	c.JSON(http.StatusOK, gin.H{
		"task_id": task.ID,
		"message": "同步任务已创建，正在后台执行",
	})
}

// executeSyncAllTask 执行全部同步任务
func (s *Server) executeSyncAllTask(task *service.Task, rules []*model.STRMRule) {
	startTime := time.Now()
	task.UpdateTask(service.TaskStatusRunning, "正在同步所有规则...")
	s.logger.LogSync(model.LogLevelInfo, fmt.Sprintf("开始同步所有规则，共 %d 个", len(rules)), nil, 0)

	totalSuccess := 0
	totalFailed := 0
	totalDeleted := 0

	for i, rule := range rules {
		if task.IsCancelled() {
			task.UpdateTask(service.TaskStatusCancelled, "任务已取消")
			return
		}

		task.Message = "正在同步: " + rule.Name + " (" + strconv.Itoa(i+1) + "/" + strconv.Itoa(len(rules)) + ")"

		result, err := s.strmSvc.SyncRuleWithTask(rule, task)
		if err != nil {
			totalFailed++
			continue
		}

		// 更新每个规则的文件计数和最后同步时间
		if count, err := s.store.GetFileMappingCountByRuleID(rule.ID); err == nil {
			s.store.UpdateRuleFileCount(rule.ID, count)
		}
		s.store.UpdateRuleLastSyncTime(rule.ID, time.Now())

		totalSuccess += result.Success
		totalFailed += result.Failed
		totalDeleted += result.Deleted
	}

	duration := time.Since(startTime).Milliseconds()

	task.SyncedFiles = totalSuccess
	task.FailedFiles = totalFailed
	task.DeletedFiles = totalDeleted
	task.UpdateTask(service.TaskStatusCompleted, "同步完成")
	s.logger.LogSync(model.LogLevelSuccess, fmt.Sprintf("全部规则同步完成 (成功:%d 失败:%d 删除:%d 耗时:%s)", totalSuccess, totalFailed, totalDeleted, util.FormatMilliseconds(duration)), map[string]string{
		"success":  fmt.Sprintf("%d", totalSuccess),
		"failed":   fmt.Sprintf("%d", totalFailed),
		"deleted":  fmt.Sprintf("%d", totalDeleted),
		"duration": util.FormatMilliseconds(duration),
	}, 0)

	// 保存历史记录
	s.saveHistoryRecord("sync", 0, "全部规则", totalSuccess, totalFailed, totalDeleted, duration, "")

	// 同步完成后通知Emby刷新媒体库
	s.notifyEmbyRefresh("")
}

// ==================== 115登录 ====================

var currentQRCode *model.QRCodeInfo
var currentQRCodeApp string // 当前二维码的设备类型

func (s *Server) getQRCode(c *gin.Context) {
	app := c.DefaultQuery("app", "web")
	qrcode, err := s.driver115.GetQRCode(app)
	if err != nil {
		c.JSON(http.StatusInternalServerError, gin.H{"error": err.Error()})
		return
	}
	currentQRCode = qrcode
	currentQRCodeApp = app
	c.JSON(http.StatusOK, qrcode)
}

func (s *Server) getQRCodeStatus(c *gin.Context) {
	if currentQRCode == nil {
		c.JSON(http.StatusBadRequest, gin.H{"error": "请先获取二维码"})
		return
	}

	status, err := s.driver115.CheckQRCodeStatus(currentQRCode.UID, currentQRCodeApp)
	if err != nil {
		c.JSON(http.StatusInternalServerError, gin.H{"error": err.Error()})
		return
	}

	currentQRCode.Status = status
	c.JSON(http.StatusOK, gin.H{"status": status})
}

func (s *Server) loginWithQRCode(c *gin.Context) {
	if currentQRCode == nil {
		c.JSON(http.StatusBadRequest, gin.H{"error": "请先获取二维码"})
		return
	}

	log.Printf("[loginWithQRCode] 开始登录，UID: %s, 设备: %s", currentQRCode.UID, currentQRCodeApp)

	cookie, userInfo, err := s.driver115.LoginWithQRCode(currentQRCode.UID, currentQRCodeApp)
	if err != nil {
		log.Printf("[loginWithQRCode] 登录失败: %v", err)
		s.logger.Log115(model.LogCategoryFail, model.LogLevelError, "扫码登录失败: "+err.Error(), nil)
		c.JSON(http.StatusInternalServerError, gin.H{"error": err.Error()})
		return
	}

	log.Printf("[loginWithQRCode] 登录成功，Cookie长度: %d, 用户: %+v, 设备: %s", len(cookie), userInfo, currentQRCodeApp)

	// 保存Cookie到数据库
	if cookie != "" {
		if err := s.store.SetSetting("115_cookie", cookie); err != nil {
			log.Printf("[loginWithQRCode] 保存Cookie到数据库失败: %v", err)
		} else {
			log.Printf("[loginWithQRCode] Cookie已保存到数据库")
		}
	}

	s.logger.Log115(model.LogCategorySuccess, model.LogLevelSuccess, "扫码登录成功", map[string]interface{}{
		"user_info":   userInfo,
		"device_type": currentQRCodeApp,
	})

	c.JSON(http.StatusOK, gin.H{
		"success":     true,
		"cookie":      cookie,
		"user_info":   userInfo,
		"device_type": currentQRCodeApp,
	})
}

func (s *Server) setCookie(c *gin.Context) {
	var req struct {
		Cookie string `json:"cookie"`
	}
	if err := c.ShouldBindJSON(&req); err != nil {
		c.JSON(http.StatusBadRequest, gin.H{"error": err.Error()})
		return
	}

	s.driver115.SetCookie(req.Cookie)

	// 验证Cookie
	userInfo, err := s.driver115.GetUserInfo()
	if err != nil {
		s.logger.Log115(model.LogCategoryError, model.LogLevelError, "Cookie验证失败: "+err.Error(), nil)
		c.JSON(http.StatusBadRequest, gin.H{"error": "Cookie无效: " + err.Error()})
		return
	}

	// 保存Cookie到数据库
	if err := s.store.SetSetting("115_cookie", req.Cookie); err != nil {
		log.Printf("[setCookie] 保存Cookie到数据库失败: %v", err)
		s.logger.Log115(model.LogCategoryError, model.LogLevelError, "保存Cookie到数据库失败: "+err.Error(), nil)
	}

	s.logger.Log115(model.LogCategorySuccess, model.LogLevelSuccess, "115登录成功", map[string]interface{}{
		"user_info": userInfo,
	})

	c.JSON(http.StatusOK, gin.H{
		"success":   true,
		"user_info": userInfo,
	})
}

func (s *Server) get115Status(c *gin.Context) {
	// 从数据库读取活跃账号信息，不调用115 API
	activeAccount, err := s.store.GetActiveAccount115()
	if err != nil || activeAccount == nil || activeAccount.CookieStatus != model.CookieStatusValid {
		c.JSON(http.StatusOK, gin.H{
			"logged_in": false,
			"error":     "未登录或Cookie已失效",
		})
		return
	}

	c.JSON(http.StatusOK, gin.H{
		"logged_in": true,
		"user_info": map[string]interface{}{
			"user_id":   activeAccount.UserID,
			"user_name": activeAccount.UserName,
			"is_vip":    activeAccount.IsVIP,
		},
	})
}

// ==================== 设置 ====================

func (s *Server) getSettings(c *gin.Context) {
	// 从数据库读取设置
	settings := make(map[string]interface{})

	// CD2设置
	cd2Host, _ := s.store.GetSetting("cd2_host")
	cd2Username, _ := s.store.GetSetting("cd2_username")
	cd2MountPrefix, _ := s.store.GetSetting("cd2_mount_prefix")
	cd2APIToken, _ := s.store.GetSetting("cd2_api_token")
	cd2UseAPIToken, _ := s.store.GetSetting("cd2_use_api_token")
	settings["clouddrive2"] = map[string]interface{}{
		"host":          cd2Host,
		"username":      cd2Username,
		"mount_prefix":  cd2MountPrefix,
		"api_token":     cd2APIToken,
		"use_api_token": cd2UseAPIToken == "true",
	}

	// Emby设置
	embyHost, _ := s.store.GetSetting("emby_host")
	embyAPIKey, _ := s.store.GetSetting("emby_api_key")
	settings["emby"] = map[string]string{
		"host":    embyHost,
		"api_key": embyAPIKey,
	}

	c.JSON(http.StatusOK, settings)
}

// getSettingsFlat 获取扁平化的设置（前端使用）
func (s *Server) getSettingsFlat(c *gin.Context) {
	settings := make(map[string]interface{})

	// CD2设置
	cd2Host, _ := s.store.GetSetting("cd2_host")
	cd2Username, _ := s.store.GetSetting("cd2_username")
	cd2MountPrefix, _ := s.store.GetSetting("cd2_mount_prefix")
	cd2APIToken, _ := s.store.GetSetting("cd2_api_token")
	cd2UseAPIToken, _ := s.store.GetSetting("cd2_use_api_token")

	settings["cd2_host"] = cd2Host
	settings["cd2_username"] = cd2Username
	settings["cd2_mount_prefix"] = cd2MountPrefix
	settings["cd2_api_token"] = cd2APIToken
	settings["cd2_use_api_token"] = cd2UseAPIToken == "true"

	// HTTP代理设置
	proxyHost, _ := s.store.GetSetting("proxy_host")
	proxyPort, _ := s.store.GetSetting("proxy_port")
	proxyUsername, _ := s.store.GetSetting("proxy_username")
	settings["proxy_host"] = proxyHost
	settings["proxy_port"] = proxyPort
	settings["proxy_username"] = proxyUsername

	// 企业微信设置
	wechatCorpid, _ := s.store.GetSetting("wechat_corpid")
	wechatAgentid, _ := s.store.GetSetting("wechat_agentid")
	wechatTouser, _ := s.store.GetSetting("wechat_touser")
	settings["wechat_corpid"] = wechatCorpid
	settings["wechat_agentid"] = wechatAgentid
	settings["wechat_touser"] = wechatTouser

	// Telegram设置
	tgChatid, _ := s.store.GetSetting("tg_chatid")
	settings["tg_chatid"] = tgChatid

	// 115自动切换设置
	autoSwitch, _ := s.store.GetSetting("115_auto_switch")
	settings["115_auto_switch"] = autoSwitch == "true"

	// 115 API QPS限制
	qpsStr, _ := s.store.GetSetting("115_api_qps")
	qps := 5 // 默认5
	if qpsStr != "" {
		if v, err := strconv.Atoi(qpsStr); err == nil && v > 0 {
			qps = v
		}
	}
	settings["115_api_qps"] = qps

	c.JSON(http.StatusOK, settings)
}

// saveCD2Settings 保存CD2设置
func (s *Server) saveCD2Settings(c *gin.Context) {
	var input struct {
		CD2Host        string `json:"cd2_host"`
		CD2Username    string `json:"cd2_username"`
		CD2Password    string `json:"cd2_password"`
		CD2APIToken    string `json:"cd2_api_token"`
		CD2UseAPIToken bool   `json:"cd2_use_api_token"`
		CD2MountPrefix string `json:"cd2_mount_prefix"`
	}

	if err := c.ShouldBindJSON(&input); err != nil {
		c.JSON(http.StatusBadRequest, gin.H{"error": err.Error()})
		return
	}

	log.Printf("[saveCD2Settings] 保存CD2设置: host=%s, use_api_token=%v", input.CD2Host, input.CD2UseAPIToken)

	// 保存设置到数据库
	if input.CD2Host != "" {
		s.store.SetSetting("cd2_host", input.CD2Host)
	}
	// 挂载前缀允许保存空值（用户可能清空）
	s.store.SetSetting("cd2_mount_prefix", input.CD2MountPrefix)

	// 保存认证方式
	if input.CD2UseAPIToken {
		s.store.SetSetting("cd2_use_api_token", "true")
		if input.CD2APIToken != "" {
			s.store.SetSetting("cd2_api_token", input.CD2APIToken)
		}
	} else {
		s.store.SetSetting("cd2_use_api_token", "false")
		if input.CD2Username != "" {
			s.store.SetSetting("cd2_username", input.CD2Username)
		}
		if input.CD2Password != "" {
			s.store.SetSetting("cd2_password", input.CD2Password)
		}
	}

	// 重新创建CD2客户端
	s.recreateCD2Client()

	// 热更新各服务引用的CD2客户端
	s.strmSvc.SetCD2(s.cd2)
	s.monitorSvc.SetCD2(s.cd2)
	s.embySvc.SetCD2(s.cd2)

	// 热更新挂载前缀
	s.strmSvc.SetMountPrefix(input.CD2MountPrefix)
	if s.treeSvc != nil {
		s.treeSvc.SetMountPrefix(input.CD2MountPrefix)
	}

	s.logger.LogSystem(model.LogLevelSuccess, "CD2设置已保存", map[string]string{
		"host": input.CD2Host,
	})

	c.JSON(http.StatusOK, gin.H{"success": true})
}

// refreshCD2Token 刷新CD2 Token
func (s *Server) refreshCD2Token(c *gin.Context) {
	if err := s.cd2.Login(); err != nil {
		s.logger.LogSystem(model.LogLevelError, "刷新CD2 Token失败: "+err.Error(), nil)
		c.JSON(http.StatusOK, gin.H{
			"success": false,
			"error":   err.Error(),
		})
		return
	}
	s.logger.LogSystem(model.LogLevelSuccess, "CD2 Token刷新成功", nil)
	c.JSON(http.StatusOK, gin.H{"success": true})
}

// recreateCD2Client 重新创建CD2客户端
func (s *Server) recreateCD2Client() {
	cd2Host, _ := s.store.GetSetting("cd2_host")
	cd2UseAPIToken, _ := s.store.GetSetting("cd2_use_api_token")

	if cd2UseAPIToken == "true" {
		cd2APIToken, _ := s.store.GetSetting("cd2_api_token")
		s.cd2 = client.NewCloudDriveClientWithToken(cd2Host, cd2APIToken)
	} else {
		cd2Username, _ := s.store.GetSetting("cd2_username")
		cd2Password, _ := s.store.GetSetting("cd2_password")
		s.cd2 = client.NewCloudDriveClient(cd2Host, cd2Username, cd2Password)
	}
}

func (s *Server) updateSettings(c *gin.Context) {
	// 只更新部分配置，保存到数据库
	var input struct {
		CloudDrive2 *struct {
			Host        string `json:"host"`
			Username    string `json:"username"`
			Password    string `json:"password"`
			MountPrefix string `json:"mount_prefix"`
		} `json:"clouddrive2"`
		Emby *struct {
			Host   string `json:"host"`
			APIKey string `json:"api_key"`
		} `json:"emby"`
	}

	if err := c.ShouldBindJSON(&input); err != nil {
		c.JSON(http.StatusBadRequest, gin.H{"error": err.Error()})
		return
	}

	log.Printf("[updateSettings] 收到设置更新请求")

	var settingsErrors []string

	// 保存CD2设置到数据库
	if input.CloudDrive2 != nil {
		if input.CloudDrive2.Host != "" {
			if err := s.store.SetSetting("cd2_host", input.CloudDrive2.Host); err != nil {
				log.Printf("[updateSettings] 保存cd2_host失败: %v", err)
				settingsErrors = append(settingsErrors, "cd2_host: "+err.Error())
			}
		}
		if input.CloudDrive2.Username != "" {
			if err := s.store.SetSetting("cd2_username", input.CloudDrive2.Username); err != nil {
				log.Printf("[updateSettings] 保存cd2_username失败: %v", err)
				settingsErrors = append(settingsErrors, "cd2_username: "+err.Error())
			}
		}
		if input.CloudDrive2.Password != "" {
			if err := s.store.SetSetting("cd2_password", input.CloudDrive2.Password); err != nil {
				log.Printf("[updateSettings] 保存cd2_password失败: %v", err)
				settingsErrors = append(settingsErrors, "cd2_password: "+err.Error())
			}
		}
		if err := s.store.SetSetting("cd2_mount_prefix", input.CloudDrive2.MountPrefix); err != nil {
			log.Printf("[updateSettings] 保存cd2_mount_prefix失败: %v", err)
			settingsErrors = append(settingsErrors, "cd2_mount_prefix: "+err.Error())
		}
		// 热更新挂载前缀
		s.strmSvc.SetMountPrefix(input.CloudDrive2.MountPrefix)
		if s.treeSvc != nil {
			s.treeSvc.SetMountPrefix(input.CloudDrive2.MountPrefix)
		}
	}

	// 保存Emby设置到数据库
	if input.Emby != nil {
		if input.Emby.Host != "" {
			if err := s.store.SetSetting("emby_host", input.Emby.Host); err != nil {
				log.Printf("[updateSettings] 保存emby_host失败: %v", err)
				settingsErrors = append(settingsErrors, "emby_host: "+err.Error())
			}
		}
		if input.Emby.APIKey != "" {
			if err := s.store.SetSetting("emby_api_key", input.Emby.APIKey); err != nil {
				log.Printf("[updateSettings] 保存emby_api_key失败: %v", err)
				settingsErrors = append(settingsErrors, "emby_api_key: "+err.Error())
			}
		}
	}

	if len(settingsErrors) > 0 {
		s.logger.LogSystem(model.LogLevelError, fmt.Sprintf("部分设置保存失败: %v", settingsErrors), nil)
	} else {
		s.logger.LogSystem(model.LogLevelSuccess, "系统设置保存成功", nil)
	}

	log.Printf("[updateSettings] 设置保存成功")
	c.JSON(http.StatusOK, gin.H{"success": true})
}

func (s *Server) testCD2(c *gin.Context) {
	// 接收用户输入的参数进行测试
	var input struct {
		Host        string `json:"host"`
		Username    string `json:"username"`
		Password    string `json:"password"`
		APIToken    string `json:"api_token"`
		UseAPIToken bool   `json:"use_api_token"`
	}

	if err := c.ShouldBindJSON(&input); err != nil {
		log.Printf("[testCD2] 解析参数失败: %v, 使用当前配置测试", err)
		// 如果没有传参数，使用当前配置测试
		if err := s.cd2.TestConnection(); err != nil {
			log.Printf("[testCD2] 使用当前配置测试失败: %v", err)
			s.logger.LogSystem(model.LogLevelError, "CD2当前配置连接测试失败: "+err.Error(), nil)
			c.JSON(http.StatusOK, gin.H{
				"success": false,
				"error":   err.Error(),
			})
			return
		}
		s.logger.LogSystem(model.LogLevelSuccess, "CD2当前配置连接测试成功", nil)
		c.JSON(http.StatusOK, gin.H{"success": true})
		return
	}

	var testClient *client.CloudDriveClient

	if input.UseAPIToken {
		log.Printf("[testCD2] 测试连接(API Token): host=%s, token_len=%d", input.Host, len(input.APIToken))
		testClient = client.NewCloudDriveClientWithToken(input.Host, input.APIToken)
	} else {
		log.Printf("[testCD2] 测试连接(用户名密码): host=%s, username=%s, password_len=%d", input.Host, input.Username, len(input.Password))
		testClient = client.NewCloudDriveClient(input.Host, input.Username, input.Password)
	}

	if err := testClient.TestConnection(); err != nil {
		log.Printf("[testCD2] 连接失败: %v", err)
		s.logger.LogSystem(model.LogLevelError, fmt.Sprintf("CD2连接测试失败: %s", err.Error()), map[string]string{"host": input.Host})
		c.JSON(http.StatusOK, gin.H{
			"success": false,
			"error":   err.Error(),
		})
		return
	}

	log.Printf("[testCD2] 连接成功")
	s.logger.LogSystem(model.LogLevelSuccess, "CD2连接测试成功", map[string]string{"host": input.Host})
	c.JSON(http.StatusOK, gin.H{"success": true})
}

func (s *Server) testEmby(c *gin.Context) {
	// 接收用户输入的参数进行测试
	var input struct {
		Host   string `json:"host"`
		APIKey string `json:"api_key"`
	}

	if err := c.ShouldBindJSON(&input); err != nil {
		// 如果没有传参数，使用当前配置测试
		if err := s.testEmbyConnection("", ""); err != nil {
			s.logger.LogEmby(model.LogCategoryFail, model.LogLevelError, "Emby当前配置连接测试失败: "+err.Error(), nil)
			c.JSON(http.StatusOK, gin.H{
				"success": false,
				"error":   err.Error(),
			})
			return
		}
		s.logger.LogEmby(model.LogCategorySuccess, model.LogLevelSuccess, "Emby当前配置连接测试成功", nil)
		c.JSON(http.StatusOK, gin.H{"success": true})
		return
	}

	// 使用用户输入的参数测试
	if err := s.testEmbyConnection(input.Host, input.APIKey); err != nil {
		s.logger.LogEmby(model.LogCategoryFail, model.LogLevelError, fmt.Sprintf("Emby连接测试失败: %s", err.Error()), map[string]string{"host": input.Host})
		c.JSON(http.StatusOK, gin.H{
			"success": false,
			"error":   err.Error(),
		})
		return
	}
	s.logger.LogEmby(model.LogCategorySuccess, model.LogLevelSuccess, "Emby连接测试成功", map[string]string{"host": input.Host})
	c.JSON(http.StatusOK, gin.H{"success": true})
}

func (s *Server) testEmbyConnection(host, apiKey string) error {
	if host == "" {
		// 从数据库读取配置
		host, _ = s.store.GetSetting("emby_host")
		apiKey, _ = s.store.GetSetting("emby_api_key")
	}

	url := host + "/emby/System/Info"
	if apiKey != "" {
		url += "?api_key=" + apiKey
	}

	resp, err := http.Get(url)
	if err != nil {
		return err
	}
	defer resp.Body.Close()

	if resp.StatusCode != http.StatusOK {
		return http.ErrNotSupported
	}
	return nil
}

// ==================== Emby代理管理 ====================

func (s *Server) getEmbyProxies(c *gin.Context) {
	proxies, err := s.store.GetAllEmbyProxies()
	if err != nil {
		c.JSON(http.StatusInternalServerError, gin.H{"error": err.Error()})
		return
	}
	if proxies == nil {
		proxies = []*model.EmbyProxy{}
	}
	c.JSON(http.StatusOK, proxies)
}

func (s *Server) createEmbyProxy(c *gin.Context) {
	// 检查是否已存在Emby代理配置（只允许1个）
	existing, _ := s.store.GetAllEmbyProxies()
	if len(existing) > 0 {
		c.JSON(http.StatusBadRequest, gin.H{"error": "只允许配置1个Emby代理，请编辑现有配置"})
		return
	}

	var proxy model.EmbyProxy
	if err := c.ShouldBindJSON(&proxy); err != nil {
		c.JSON(http.StatusBadRequest, gin.H{"error": err.Error()})
		return
	}

	proxy.Enabled = true
	if err := s.store.CreateEmbyProxy(&proxy); err != nil {
		s.logger.LogEmby(model.LogCategoryError, model.LogLevelError, "创建Emby代理失败: "+err.Error(), nil)
		c.JSON(http.StatusInternalServerError, gin.H{"error": err.Error()})
		return
	}

	s.logger.LogEmby(model.LogCategorySuccess, model.LogLevelSuccess, fmt.Sprintf("创建Emby代理: %s", proxy.Name), map[string]string{
		"host": proxy.EmbyHost,
		"port": fmt.Sprintf("%d", proxy.ProxyPort),
	})
	c.JSON(http.StatusOK, proxy)
}

func (s *Server) updateEmbyProxy(c *gin.Context) {
	id, err := strconv.ParseInt(c.Param("id"), 10, 64)
	if err != nil {
		c.JSON(http.StatusBadRequest, gin.H{"error": "无效的ID"})
		return
	}

	var proxy model.EmbyProxy
	if err := c.ShouldBindJSON(&proxy); err != nil {
		c.JSON(http.StatusBadRequest, gin.H{"error": err.Error()})
		return
	}

	proxy.ID = id
	if err := s.store.UpdateEmbyProxy(&proxy); err != nil {
		s.logger.LogEmby(model.LogCategoryError, model.LogLevelError, fmt.Sprintf("更新Emby代理失败: %s", err.Error()), nil)
		c.JSON(http.StatusInternalServerError, gin.H{"error": err.Error()})
		return
	}

	s.logger.LogEmby(model.LogCategorySuccess, model.LogLevelSuccess, fmt.Sprintf("更新Emby代理: %s", proxy.Name), nil)
	c.JSON(http.StatusOK, proxy)
}

func (s *Server) deleteEmbyProxy(c *gin.Context) {
	id, err := strconv.ParseInt(c.Param("id"), 10, 64)
	if err != nil {
		c.JSON(http.StatusBadRequest, gin.H{"error": "无效的ID"})
		return
	}

	if err := s.store.DeleteEmbyProxy(id); err != nil {
		s.logger.LogEmby(model.LogCategoryError, model.LogLevelError, fmt.Sprintf("删除Emby代理失败: %s", err.Error()), nil)
		c.JSON(http.StatusInternalServerError, gin.H{"error": err.Error()})
		return
	}

	s.logger.LogEmby(model.LogCategoryNormal, model.LogLevelInfo, fmt.Sprintf("删除Emby代理: ID=%d", id), nil)
	c.JSON(http.StatusOK, gin.H{"success": true})
}

// ==================== Emby统计API ====================

// getEmbyStats 获取Emby统计信息
func (s *Server) getEmbyStats(c *gin.Context) {
	// 获取第一个启用的Emby代理配置
	proxies, err := s.store.GetAllEmbyProxies()
	if err != nil || len(proxies) == 0 {
		c.JSON(http.StatusOK, gin.H{
			"configured": false,
		})
		return
	}

	proxy := proxies[0]
	if !proxy.Enabled || proxy.EmbyHost == "" {
		c.JSON(http.StatusOK, gin.H{
			"configured": false,
		})
		return
	}

	// 创建Emby服务
	embySvc, err := service.NewEmbyProxyServiceWithTarget(proxy.EmbyHost, proxy.APIKey, s.cfg, s.store, s.driver115, s.cd2)
	if err != nil {
		c.JSON(http.StatusOK, gin.H{
			"configured": true,
			"online":     false,
			"error":      err.Error(),
		})
		return
	}

	// 获取统计信息
	stats, err := embySvc.GetStats()
	if err != nil {
		c.JSON(http.StatusOK, gin.H{
			"configured": true,
			"online":     false,
			"error":      err.Error(),
		})
		return
	}

	c.JSON(http.StatusOK, gin.H{
		"configured":    true,
		"online":        true,
		"name":          proxy.Name,
		"host":          proxy.EmbyHost,
		"port":          proxy.ProxyPort,
		"local_only":    proxy.LocalOnly,
		"movie_count":   stats.MovieCount,
		"series_count":  stats.SeriesCount,
		"episode_count": stats.EpisodeCount,
		"playing_count": stats.PlayingCount,
		"server_id":     stats.ServerID,
	})
}

// getEmbyRecentItems 获取Emby最近入库
func (s *Server) getEmbyRecentItems(c *gin.Context) {
	limit, _ := strconv.Atoi(c.DefaultQuery("limit", "12"))

	proxies, _ := s.store.GetAllEmbyProxies()
	if len(proxies) == 0 {
		c.JSON(http.StatusOK, []interface{}{})
		return
	}

	proxy := proxies[0]
	embySvc, err := service.NewEmbyProxyServiceWithTarget(proxy.EmbyHost, proxy.APIKey, s.cfg, s.store, s.driver115, s.cd2)
	if err != nil {
		c.JSON(http.StatusOK, []interface{}{})
		return
	}

	items, err := embySvc.GetRecentItems(limit)
	if err != nil {
		c.JSON(http.StatusOK, []interface{}{})
		return
	}

	c.JSON(http.StatusOK, items)
}

// getEmbyRandomItems 获取Emby随机媒体
func (s *Server) getEmbyRandomItems(c *gin.Context) {
	limit, _ := strconv.Atoi(c.DefaultQuery("limit", "12"))

	proxies, _ := s.store.GetAllEmbyProxies()
	if len(proxies) == 0 {
		c.JSON(http.StatusOK, []interface{}{})
		return
	}

	proxy := proxies[0]
	embySvc, err := service.NewEmbyProxyServiceWithTarget(proxy.EmbyHost, proxy.APIKey, s.cfg, s.store, s.driver115, s.cd2)
	if err != nil {
		c.JSON(http.StatusOK, []interface{}{})
		return
	}

	items, err := embySvc.GetRandomItems(limit)
	if err != nil {
		c.JSON(http.StatusOK, []interface{}{})
		return
	}

	c.JSON(http.StatusOK, items)
}

// getEmbyPopularItems 获取Emby热门媒体
func (s *Server) getEmbyPopularItems(c *gin.Context) {
	limit, _ := strconv.Atoi(c.DefaultQuery("limit", "12"))

	proxies, _ := s.store.GetAllEmbyProxies()
	if len(proxies) == 0 {
		c.JSON(http.StatusOK, []interface{}{})
		return
	}

	proxy := proxies[0]
	embySvc, err := service.NewEmbyProxyServiceWithTarget(proxy.EmbyHost, proxy.APIKey, s.cfg, s.store, s.driver115, s.cd2)
	if err != nil {
		c.JSON(http.StatusOK, []interface{}{})
		return
	}

	items, err := embySvc.GetPopularItems(limit)
	if err != nil {
		c.JSON(http.StatusOK, []interface{}{})
		return
	}

	c.JSON(http.StatusOK, items)
}

// getEmbyPlayingSessions 获取Emby正在播放
func (s *Server) getEmbyPlayingSessions(c *gin.Context) {
	proxies, _ := s.store.GetAllEmbyProxies()
	if len(proxies) == 0 {
		c.JSON(http.StatusOK, []interface{}{})
		return
	}

	proxy := proxies[0]
	embySvc, err := service.NewEmbyProxyServiceWithTarget(proxy.EmbyHost, proxy.APIKey, s.cfg, s.store, s.driver115, s.cd2)
	if err != nil {
		c.JSON(http.StatusOK, []interface{}{})
		return
	}

	sessions, err := embySvc.GetPlayingSessions()
	if err != nil {
		c.JSON(http.StatusOK, []interface{}{})
		return
	}

	c.JSON(http.StatusOK, sessions)
}

// ==================== 115账号管理 ====================

// getAccounts115 获取所有115账号
func (s *Server) getAccounts115(c *gin.Context) {
	accounts, err := s.store.GetAllAccounts115()
	if err != nil {
		c.JSON(http.StatusInternalServerError, gin.H{"error": err.Error()})
		return
	}
	if accounts == nil {
		accounts = []*model.Account115{}
	}

	// 隐藏cookie的敏感部分
	for _, a := range accounts {
		if len(a.Cookie) > 20 {
			a.Cookie = a.Cookie[:10] + "..." + a.Cookie[len(a.Cookie)-10:]
		}
	}

	c.JSON(http.StatusOK, accounts)
}

// createAccount115 创建115账号
func (s *Server) createAccount115(c *gin.Context) {
	var input struct {
		Name       string `json:"name"`
		Cookie     string `json:"cookie"`
		DeviceType string `json:"device_type"`
		AutoSign   bool   `json:"auto_sign"`
	}

	if err := c.ShouldBindJSON(&input); err != nil {
		c.JSON(http.StatusBadRequest, gin.H{"error": err.Error()})
		return
	}

	if input.Cookie == "" {
		c.JSON(http.StatusBadRequest, gin.H{"error": "Cookie不能为空"})
		return
	}

	// 如果没有提供名称，使用当前时间
	if input.Name == "" {
		input.Name = time.Now().Format("2006-01-02 15:04:05")
	}
	if input.DeviceType == "" {
		input.DeviceType = "ios"
	}

	account := &model.Account115{
		Name:         input.Name,
		Cookie:       input.Cookie,
		DeviceType:   input.DeviceType,
		AutoSign:     input.AutoSign,
		CookieStatus: model.CookieStatusUnknown,
	}

	// 尝试获取用户信息并验证cookie
	tempClient := client.NewDriver115Client(input.Cookie, "Mozilla/5.0")
	if userInfo, err := tempClient.GetUserInfo(); err == nil {
		account.UserID = userInfo.UserID
		account.UserName = userInfo.UserName
		account.IsVIP = userInfo.IsVIP
		account.AvatarURL = userInfo.AvatarURL
		account.CookieStatus = model.CookieStatusValid

		// 单独获取空间信息
		if total, used, err := tempClient.GetSpaceInfo(input.Cookie); err == nil {
			account.SpaceTotal = total
			account.SpaceUsed = used
		}

		// 缓存头像到本地
		if userInfo.AvatarURL != "" {
			avatarPath := fmt.Sprintf("./data/avatars/%s.jpg", userInfo.UserID)
			if err := tempClient.DownloadAvatar(userInfo.AvatarURL, avatarPath); err == nil {
				account.AvatarLocal = avatarPath
			}
		}
	} else {
		account.CookieStatus = model.CookieStatusInvalid
	}

	// 如果是第一个账号，设为激活
	existingAccounts, _ := s.store.GetAllAccounts115()
	if len(existingAccounts) == 0 {
		account.IsActive = true
	}

	if err := s.store.CreateAccount115(account); err != nil {
		s.logger.Log115(model.LogCategoryError, model.LogLevelError, "创建115账号失败: "+err.Error(), nil)
		c.JSON(http.StatusInternalServerError, gin.H{"error": err.Error()})
		return
	}

	// 如果是激活账号，更新115客户端
	if account.IsActive {
		s.driver115.SetCookie(account.Cookie)
	}

	s.logger.Log115(model.LogCategorySuccess, model.LogLevelSuccess, fmt.Sprintf("创建115账号: %s", account.Name), map[string]string{
		"user_name": account.UserName,
	})
	c.JSON(http.StatusOK, account)
}

// updateAccount115 更新115账号
func (s *Server) updateAccount115(c *gin.Context) {
	id, err := strconv.ParseInt(c.Param("id"), 10, 64)
	if err != nil {
		c.JSON(http.StatusBadRequest, gin.H{"error": "无效的ID"})
		return
	}

	var input struct {
		Name     string `json:"name"`
		Cookie   string `json:"cookie"`
		AutoSign *bool  `json:"auto_sign"`
	}

	if err := c.ShouldBindJSON(&input); err != nil {
		c.JSON(http.StatusBadRequest, gin.H{"error": err.Error()})
		return
	}

	// 获取现有账号
	account, err := s.store.GetAccount115(id)
	if err != nil || account == nil {
		c.JSON(http.StatusNotFound, gin.H{"error": "账号不存在"})
		return
	}

	if input.Name != "" {
		account.Name = input.Name
	}
	if input.AutoSign != nil {
		account.AutoSign = *input.AutoSign
	}

	// 如果更新了cookie，重新获取用户信息
	if input.Cookie != "" && input.Cookie != account.Cookie {
		account.Cookie = input.Cookie
		tempClient := client.NewDriver115Client(input.Cookie, "Mozilla/5.0")
		if userInfo, err := tempClient.GetUserInfo(); err == nil {
			account.UserID = userInfo.UserID
			account.UserName = userInfo.UserName
			account.IsVIP = userInfo.IsVIP
			account.AvatarURL = userInfo.AvatarURL
			account.CookieStatus = model.CookieStatusValid

			// 单独获取空间信息
			if total, used, err := tempClient.GetSpaceInfo(input.Cookie); err == nil {
				account.SpaceTotal = total
				account.SpaceUsed = used
			}

			// 缓存头像
			if userInfo.AvatarURL != "" {
				avatarPath := fmt.Sprintf("./data/avatars/%s.jpg", userInfo.UserID)
				if err := tempClient.DownloadAvatar(userInfo.AvatarURL, avatarPath); err == nil {
					account.AvatarLocal = avatarPath
				}
			}
		}
	}

	if err := s.store.UpdateAccount115(account); err != nil {
		s.logger.Log115(model.LogCategoryError, model.LogLevelError, "更新115账号失败: "+err.Error(), nil)
		c.JSON(http.StatusInternalServerError, gin.H{"error": err.Error()})
		return
	}

	// 如果是激活账号，更新115客户端
	if account.IsActive {
		s.driver115.SetCookie(account.Cookie)
	}

	s.logger.Log115(model.LogCategorySuccess, model.LogLevelSuccess, fmt.Sprintf("更新115账号: %s", account.Name), nil)
	c.JSON(http.StatusOK, account)
}

// deleteAccount115 删除115账号
func (s *Server) deleteAccount115(c *gin.Context) {
	id, err := strconv.ParseInt(c.Param("id"), 10, 64)
	if err != nil {
		c.JSON(http.StatusBadRequest, gin.H{"error": "无效的ID"})
		return
	}

	// 检查是否是激活账号
	account, _ := s.store.GetAccount115(id)
	if account != nil && account.IsActive {
		c.JSON(http.StatusBadRequest, gin.H{"error": "不能删除当前激活的账号"})
		return
	}

	// 删除缓存的头像文件
	if account != nil && account.AvatarLocal != "" {
		os.Remove(account.AvatarLocal)
	}

	if err := s.store.DeleteAccount115(id); err != nil {
		s.logger.Log115(model.LogCategoryError, model.LogLevelError, fmt.Sprintf("删除115账号失败: %s", err.Error()), nil)
		c.JSON(http.StatusInternalServerError, gin.H{"error": err.Error()})
		return
	}

	s.logger.Log115(model.LogCategoryNormal, model.LogLevelInfo, fmt.Sprintf("删除115账号: ID=%d", id), nil)
	c.JSON(http.StatusOK, gin.H{"success": true})
}

// setActiveAccount115 设置激活的115账号
func (s *Server) setActiveAccount115(c *gin.Context) {
	id, err := strconv.ParseInt(c.Param("id"), 10, 64)
	if err != nil {
		c.JSON(http.StatusBadRequest, gin.H{"error": "无效的ID"})
		return
	}

	// 获取账号
	account, err := s.store.GetAccount115(id)
	if err != nil || account == nil {
		c.JSON(http.StatusNotFound, gin.H{"error": "账号不存在"})
		return
	}

	// 设置为激活
	if err := s.store.SetActiveAccount115(id); err != nil {
		s.logger.Log115(model.LogCategoryError, model.LogLevelError, "切换115账号失败: "+err.Error(), nil)
		c.JSON(http.StatusInternalServerError, gin.H{"error": err.Error()})
		return
	}

	// 更新115客户端
	s.driver115.SetCookie(account.Cookie)

	s.logger.Log115(model.LogCategorySuccess, model.LogLevelSuccess, fmt.Sprintf("切换115账号: %s", account.Name), nil)
	c.JSON(http.StatusOK, gin.H{"success": true})
}

// reorderAccounts115 重新排序115账号
func (s *Server) reorderAccounts115(c *gin.Context) {
	var input struct {
		IDs []int64 `json:"ids"`
	}

	if err := c.ShouldBindJSON(&input); err != nil {
		c.JSON(http.StatusBadRequest, gin.H{"error": err.Error()})
		return
	}

	if err := s.store.ReorderAccounts115(input.IDs); err != nil {
		c.JSON(http.StatusInternalServerError, gin.H{"error": err.Error()})
		return
	}

	c.JSON(http.StatusOK, gin.H{"success": true})
}

// getAccount115Cookie 获取115账号的完整Cookie（用于编辑）
func (s *Server) getAccount115Cookie(c *gin.Context) {
	id, err := strconv.ParseInt(c.Param("id"), 10, 64)
	if err != nil {
		c.JSON(http.StatusBadRequest, gin.H{"error": "无效的ID"})
		return
	}

	account, err := s.store.GetAccount115(id)
	if err != nil || account == nil {
		c.JSON(http.StatusNotFound, gin.H{"error": "账号不存在"})
		return
	}

	c.JSON(http.StatusOK, gin.H{"cookie": account.Cookie})
}

// getDeviceTypes 获取支持的设备类型列表
func (s *Server) getDeviceTypes(c *gin.Context) {
	c.JSON(http.StatusOK, model.DeviceTypes)
}

// setAutoSwitch 设置自动切换开关
func (s *Server) setAutoSwitch(c *gin.Context) {
	var input struct {
		Enabled bool `json:"enabled"`
	}
	if err := c.ShouldBindJSON(&input); err != nil {
		c.JSON(http.StatusBadRequest, gin.H{"error": err.Error()})
		return
	}
	value := "false"
	if input.Enabled {
		value = "true"
	}
	if err := s.store.SetSetting("115_auto_switch", value); err != nil {
		c.JSON(http.StatusInternalServerError, gin.H{"error": err.Error()})
		return
	}
	c.JSON(http.StatusOK, gin.H{"success": true})
}

// setAPIRateLimit 设置115 API QPS限制
func (s *Server) setAPIRateLimit(c *gin.Context) {
	var input struct {
		QPS int `json:"qps"`
	}
	if err := c.ShouldBindJSON(&input); err != nil {
		c.JSON(http.StatusBadRequest, gin.H{"error": err.Error()})
		return
	}
	if input.QPS < 1 || input.QPS > 50 {
		c.JSON(http.StatusBadRequest, gin.H{"error": "QPS必须在1-50之间"})
		return
	}
	if err := s.store.SetSetting("115_api_qps", strconv.Itoa(input.QPS)); err != nil {
		c.JSON(http.StatusInternalServerError, gin.H{"error": err.Error()})
		return
	}
	s.driver115.SetRateLimit(input.QPS)
	log.Printf("[Settings] 115 API QPS限制已设置为: %d", input.QPS)
	c.JSON(http.StatusOK, gin.H{"success": true, "qps": input.QPS})
}

// checkAllCookies 检查所有账号的cookie有效性
func (s *Server) checkAllCookies(c *gin.Context) {
	accounts, err := s.store.GetAllAccounts115()
	if err != nil {
		c.JSON(http.StatusInternalServerError, gin.H{"error": err.Error()})
		return
	}

	results := make([]gin.H, 0, len(accounts))
	for _, account := range accounts {
		status := model.CookieStatusInvalid
		if _, err := s.driver115.CheckCookieValid(account.Cookie); err == nil {
			status = model.CookieStatusValid
		}
		s.store.UpdateAccount115CookieStatus(account.ID, status)
		results = append(results, gin.H{
			"id":     account.ID,
			"name":   account.Name,
			"status": status,
		})
	}

	// 检查当前激活账号是否失效，如果失效且开启了自动切换则切换
	autoSwitch, _ := s.store.GetSetting("115_auto_switch")
	if autoSwitch == "true" {
		s.tryAutoSwitchCookie()
	}

	c.JSON(http.StatusOK, gin.H{"results": results})
}

// tryAutoSwitchCookie 尝试自动切换到可用的cookie
func (s *Server) tryAutoSwitchCookie() {
	activeAccount, err := s.store.GetActiveAccount115()
	if err != nil || activeAccount == nil {
		return
	}

	// 如果当前激活账号cookie有效，不需要切换
	if activeAccount.CookieStatus == model.CookieStatusValid {
		return
	}

	// 查找下一个有效的账号
	nextAccount, err := s.store.GetNextValidAccount115(activeAccount.ID)
	if err != nil || nextAccount == nil {
		log.Printf("[CookieCheck] 所有cookie均已失效，无法自动切换")
		if s.logger != nil {
			s.logger.Log115(model.LogCategoryError, model.LogLevelError, "所有115 Cookie均已失效", nil)
		}
		return
	}

	// 切换到新账号
	if err := s.store.SetActiveAccount115(nextAccount.ID); err != nil {
		log.Printf("[CookieCheck] 自动切换账号失败: %v", err)
		return
	}
	s.driver115.SetCookie(nextAccount.Cookie)
	log.Printf("[CookieCheck] 已自动切换到账号: %s (ID: %d)", nextAccount.Name, nextAccount.ID)
	if s.logger != nil {
		s.logger.Log115(model.LogCategorySuccess, model.LogLevelInfo, fmt.Sprintf("Cookie失效，已自动切换到: %s", nextAccount.Name), nil)
	}
}

// signAccount115 手动签到单个账号
func (s *Server) signAccount115(c *gin.Context) {
	id, err := strconv.ParseInt(c.Param("id"), 10, 64)
	if err != nil {
		c.JSON(http.StatusBadRequest, gin.H{"error": "无效的ID"})
		return
	}

	account, err := s.store.GetAccount115(id)
	if err != nil || account == nil {
		c.JSON(http.StatusNotFound, gin.H{"error": "账号不存在"})
		return
	}

	msg, err := s.driver115.UserSign(account.Cookie, account.UserID)
	if err != nil {
		c.JSON(http.StatusInternalServerError, gin.H{"error": err.Error()})
		return
	}

	c.JSON(http.StatusOK, gin.H{"message": msg})
}

// refreshAccount115Info 刷新单个账号的用户信息（头像、VIP、容量）
func (s *Server) refreshAccount115Info(c *gin.Context) {
	id, err := strconv.ParseInt(c.Param("id"), 10, 64)
	if err != nil {
		c.JSON(http.StatusBadRequest, gin.H{"error": "无效的ID"})
		return
	}

	account, err := s.store.GetAccount115(id)
	if err != nil || account == nil {
		c.JSON(http.StatusNotFound, gin.H{"error": "账号不存在"})
		return
	}

	tempClient := client.NewDriver115Client(account.Cookie, "Mozilla/5.0")
	userInfo, err := tempClient.GetUserInfo()
	if err != nil {
		c.JSON(http.StatusInternalServerError, gin.H{"error": "获取用户信息失败: " + err.Error()})
		return
	}

	account.UserID = userInfo.UserID
	account.UserName = userInfo.UserName
	account.IsVIP = userInfo.IsVIP
	account.AvatarURL = userInfo.AvatarURL
	account.CookieStatus = model.CookieStatusValid

	// 单独获取空间信息（nav API不返回space_info）
	if total, used, err := tempClient.GetSpaceInfo(account.Cookie); err == nil {
		account.SpaceTotal = total
		account.SpaceUsed = used
	} else {
		log.Printf("[115API] 获取空间信息失败: %v", err)
		account.SpaceTotal = userInfo.SpaceTotal
		account.SpaceUsed = userInfo.SpaceUsed
	}

	// 缓存头像
	if userInfo.AvatarURL != "" {
		avatarPath := fmt.Sprintf("./data/avatars/%s.jpg", userInfo.UserID)
		if err := tempClient.DownloadAvatar(userInfo.AvatarURL, avatarPath); err == nil {
			account.AvatarLocal = avatarPath
		}
	}

	if err := s.store.UpdateAccount115(account); err != nil {
		c.JSON(http.StatusInternalServerError, gin.H{"error": err.Error()})
		return
	}

	c.JSON(http.StatusOK, account)
}

// autoSignAll 自动签到所有开启签到的账号
func (s *Server) autoSignAll() {
	accounts, err := s.store.GetAllAccounts115()
	if err != nil {
		return
	}
	for _, account := range accounts {
		if !account.AutoSign || account.CookieStatus == model.CookieStatusInvalid {
			continue
		}
		msg, err := s.driver115.UserSign(account.Cookie, account.UserID)
		if err != nil {
			log.Printf("[AutoSign] 账号 %s 签到失败: %v", account.Name, err)
		} else {
			log.Printf("[AutoSign] 账号 %s: %s", account.Name, msg)
		}
	}
}

// checkSingleCookie 检查单个账号的cookie有效性
func (s *Server) checkSingleCookie(c *gin.Context) {
	idStr := c.Param("id")
	id, err := strconv.ParseInt(idStr, 10, 64)
	if err != nil {
		c.JSON(http.StatusBadRequest, gin.H{"error": "无效的ID"})
		return
	}

	accounts, err := s.store.GetAllAccounts115()
	if err != nil {
		c.JSON(http.StatusInternalServerError, gin.H{"error": err.Error()})
		return
	}

	var target *model.Account115
	for _, a := range accounts {
		if a.ID == id {
			target = a
			break
		}
	}
	if target == nil {
		c.JSON(http.StatusNotFound, gin.H{"error": "账号不存在"})
		return
	}

	status := model.CookieStatusInvalid
	if _, err := s.driver115.CheckCookieValid(target.Cookie); err == nil {
		status = model.CookieStatusValid
	}
	s.store.UpdateAccount115CookieStatus(target.ID, status)

	c.JSON(http.StatusOK, gin.H{"id": target.ID, "status": status})
}

// MarkActiveCookieInvalid 当115 API调用失败时标记当前cookie失效并尝试自动切换
func (s *Server) MarkActiveCookieInvalid() {
	activeAccount, err := s.store.GetActiveAccount115()
	if err != nil || activeAccount == nil {
		return
	}
	s.store.UpdateAccount115CookieStatus(activeAccount.ID, model.CookieStatusInvalid)
	log.Printf("[CookieCheck] 当前Cookie已失效: %s (ID: %d)", activeAccount.Name, activeAccount.ID)

	autoSwitch, _ := s.store.GetSetting("115_auto_switch")
	if autoSwitch == "true" {
		s.tryAutoSwitchCookie()
	}
}

// ==================== 日志管理 ====================

// getLogs 获取日志列表
func (s *Server) getLogs(c *gin.Context) {
	logType := c.DefaultQuery("type", "all")
	category := c.DefaultQuery("category", "all")
	level := c.DefaultQuery("level", "all")
	limit, _ := strconv.Atoi(c.DefaultQuery("limit", "100"))
	offset, _ := strconv.Atoi(c.DefaultQuery("offset", "0"))

	if limit <= 0 || limit > 500 {
		limit = 100
	}

	logs, total, err := s.store.GetLogEntries(logType, category, level, limit, offset)
	if err != nil {
		c.JSON(http.StatusInternalServerError, gin.H{"error": err.Error()})
		return
	}

	if logs == nil {
		logs = []*model.LogEntry{}
	}

	c.JSON(http.StatusOK, gin.H{
		"logs":   logs,
		"total":  total,
		"limit":  limit,
		"offset": offset,
	})
}

// streamLogs 实时日志流（SSE）
func (s *Server) streamLogs(c *gin.Context) {
	// 设置SSE头
	c.Header("Content-Type", "text/event-stream")
	c.Header("Cache-Control", "no-cache")
	c.Header("Connection", "keep-alive")
	c.Header("Access-Control-Allow-Origin", "*")
	c.Header("X-Accel-Buffering", "no") // 禁用nginx缓冲

	// 强制设置流式响应，禁用内部缓冲
	c.Writer.Header().Set("Transfer-Encoding", "chunked")

	// 订阅日志
	subscriberID := c.Query("id")
	if subscriberID == "" {
		subscriberID = time.Now().Format("20060102150405.000")
	}

	logChan := s.logger.Subscribe(subscriberID)
	defer s.logger.Unsubscribe(subscriberID)

	// 发送连接确认事件，确保SSE通道畅通
	c.SSEvent("connected", `{"status":"ok"}`)
	c.Writer.Flush()

	// 发送心跳（缩短间隔，保持连接活跃）
	ticker := time.NewTicker(15 * time.Second)
	defer ticker.Stop()

	ctx := c.Request.Context()

	for {
		select {
		case <-ctx.Done():
			return
		case entry, ok := <-logChan:
			if !ok {
				return
			}
			if entry != nil {
				data, _ := json.Marshal(entry)
				c.SSEvent("log", string(data))
				c.Writer.Flush()
			}
		case <-ticker.C:
			c.SSEvent("ping", "")
			c.Writer.Flush()
		}
	}
}

// clearLogs 清空日志
func (s *Server) clearLogs(c *gin.Context) {
	logType := c.DefaultQuery("type", "all")

	if err := s.store.ClearLogEntries(logType); err != nil {
		c.JSON(http.StatusInternalServerError, gin.H{"error": err.Error()})
		return
	}

	s.logger.LogSystem(model.LogLevelInfo, fmt.Sprintf("日志已清空 (类型: %s)", logType), nil)
	c.JSON(http.StatusOK, gin.H{"success": true})
}

// getLogStats 获取日志统计
func (s *Server) getLogStats(c *gin.Context) {
	stats, err := s.logger.GetRecentStats()
	if err != nil {
		c.JSON(http.StatusInternalServerError, gin.H{"error": err.Error()})
		return
	}

	c.JSON(http.StatusOK, stats)
}

// ==================== 历史记录管理 ====================

// getHistoryRecords 获取历史记录
func (s *Server) getHistoryRecords(c *gin.Context) {
	recordType := c.DefaultQuery("type", "all")
	limit, _ := strconv.Atoi(c.DefaultQuery("limit", "20"))
	offset, _ := strconv.Atoi(c.DefaultQuery("offset", "0"))

	if limit <= 0 || limit > 100 {
		limit = 20
	}

	records, total, err := s.store.GetHistoryRecords(recordType, limit, offset)
	if err != nil {
		c.JSON(http.StatusInternalServerError, gin.H{"error": err.Error()})
		return
	}

	if records == nil {
		records = []*model.HistoryRecord{}
	}

	c.JSON(http.StatusOK, gin.H{
		"records": records,
		"total":   total,
		"limit":   limit,
		"offset":  offset,
	})
}

// getHistoryStats 获取历史统计
func (s *Server) getHistoryStats(c *gin.Context) {
	stats, err := s.store.GetHistoryStats()
	if err != nil {
		c.JSON(http.StatusInternalServerError, gin.H{"error": err.Error()})
		return
	}

	c.JSON(http.StatusOK, stats)
}

// ==================== 媒体分类管理 ====================

// getMediaCategories 获取媒体分类
func (s *Server) getMediaCategories(c *gin.Context) {
	mediaType := c.Query("media_type")

	categories, err := s.store.GetMediaCategories(mediaType)
	if err != nil {
		c.JSON(http.StatusInternalServerError, gin.H{"error": err.Error()})
		return
	}

	if categories == nil {
		categories = []*model.MediaCategory{}
	}

	c.JSON(http.StatusOK, categories)
}

// createMediaCategory 创建媒体分类
func (s *Server) createMediaCategory(c *gin.Context) {
	var cat model.MediaCategory
	if err := c.ShouldBindJSON(&cat); err != nil {
		c.JSON(http.StatusBadRequest, gin.H{"error": err.Error()})
		return
	}

	if cat.MediaType == "" || cat.Name == "" {
		c.JSON(http.StatusBadRequest, gin.H{"error": "媒体类型和名称不能为空"})
		return
	}

	if err := s.store.CreateMediaCategory(&cat); err != nil {
		c.JSON(http.StatusInternalServerError, gin.H{"error": err.Error()})
		return
	}

	c.JSON(http.StatusOK, cat)
}

// updateMediaCategory 更新媒体分类
func (s *Server) updateMediaCategory(c *gin.Context) {
	id, err := strconv.ParseInt(c.Param("id"), 10, 64)
	if err != nil {
		c.JSON(http.StatusBadRequest, gin.H{"error": "无效的ID"})
		return
	}

	var cat model.MediaCategory
	if err := c.ShouldBindJSON(&cat); err != nil {
		c.JSON(http.StatusBadRequest, gin.H{"error": err.Error()})
		return
	}

	cat.ID = id
	if err := s.store.UpdateMediaCategory(&cat); err != nil {
		c.JSON(http.StatusInternalServerError, gin.H{"error": err.Error()})
		return
	}

	c.JSON(http.StatusOK, cat)
}

// deleteMediaCategory 删除媒体分类
func (s *Server) deleteMediaCategory(c *gin.Context) {
	id, err := strconv.ParseInt(c.Param("id"), 10, 64)
	if err != nil {
		c.JSON(http.StatusBadRequest, gin.H{"error": "无效的ID"})
		return
	}

	if err := s.store.DeleteMediaCategory(id); err != nil {
		c.JSON(http.StatusInternalServerError, gin.H{"error": err.Error()})
		return
	}

	c.JSON(http.StatusOK, gin.H{"success": true})
}

// reorderMediaCategories 重新排序媒体分类
func (s *Server) reorderMediaCategories(c *gin.Context) {
	var input struct {
		IDs []int64 `json:"ids"`
	}

	if err := c.ShouldBindJSON(&input); err != nil {
		c.JSON(http.StatusBadRequest, gin.H{"error": err.Error()})
		return
	}

	if err := s.store.ReorderMediaCategories(input.IDs); err != nil {
		c.JSON(http.StatusInternalServerError, gin.H{"error": err.Error()})
		return
	}

	c.JSON(http.StatusOK, gin.H{"success": true})
}

// ==================== 整理规则管理 ====================

// getOrganizeRules 获取整理规则
func (s *Server) getOrganizeRules(c *gin.Context) {
	rules, err := s.store.GetOrganizeRules()
	if err != nil {
		c.JSON(http.StatusInternalServerError, gin.H{"error": err.Error()})
		return
	}

	if rules == nil {
		rules = []*model.OrganizeRule{}
	}

	c.JSON(http.StatusOK, rules)
}

// createOrganizeRule 创建整理规则
func (s *Server) createOrganizeRule(c *gin.Context) {
	var rule model.OrganizeRule
	if err := c.ShouldBindJSON(&rule); err != nil {
		c.JSON(http.StatusBadRequest, gin.H{"error": err.Error()})
		return
	}

	rule.Enabled = true
	if err := s.store.CreateOrganizeRule(&rule); err != nil {
		c.JSON(http.StatusInternalServerError, gin.H{"error": err.Error()})
		return
	}

	c.JSON(http.StatusOK, rule)
}

// updateOrganizeRule 更新整理规则
func (s *Server) updateOrganizeRule(c *gin.Context) {
	id, err := strconv.ParseInt(c.Param("id"), 10, 64)
	if err != nil {
		c.JSON(http.StatusBadRequest, gin.H{"error": "无效的ID"})
		return
	}

	var rule model.OrganizeRule
	if err := c.ShouldBindJSON(&rule); err != nil {
		c.JSON(http.StatusBadRequest, gin.H{"error": err.Error()})
		return
	}

	rule.ID = id
	if err := s.store.UpdateOrganizeRule(&rule); err != nil {
		c.JSON(http.StatusInternalServerError, gin.H{"error": err.Error()})
		return
	}

	c.JSON(http.StatusOK, rule)
}

// deleteOrganizeRule 删除整理规则
func (s *Server) deleteOrganizeRule(c *gin.Context) {
	id, err := strconv.ParseInt(c.Param("id"), 10, 64)
	if err != nil {
		c.JSON(http.StatusBadRequest, gin.H{"error": "无效的ID"})
		return
	}

	if err := s.store.DeleteOrganizeRule(id); err != nil {
		c.JSON(http.StatusInternalServerError, gin.H{"error": err.Error()})
		return
	}

	c.JSON(http.StatusOK, gin.H{"success": true})
}

// ==================== 本地路径浏览 ====================

// listLocalDir 列出本地目录
func (s *Server) listLocalDir(c *gin.Context) {
	path := c.Query("path")
	if path == "" {
		path = "/"
	}

	// 安全检查：防止路径遍历攻击
	cleanPath := filepath.Clean(path)
	if !filepath.IsAbs(cleanPath) {
		cleanPath = "/" + cleanPath
	}

	entries, err := os.ReadDir(cleanPath)
	if err != nil {
		c.JSON(http.StatusInternalServerError, gin.H{"error": err.Error()})
		return
	}

	type DirEntry struct {
		Name  string `json:"name"`
		Path  string `json:"path"`
		IsDir bool   `json:"is_dir"`
	}

	var dirs []DirEntry
	for _, entry := range entries {
		// 只返回目录
		if entry.IsDir() {
			dirs = append(dirs, DirEntry{
				Name:  entry.Name(),
				Path:  filepath.Join(cleanPath, entry.Name()),
				IsDir: true,
			})
		}
	}

	// 添加父目录
	parent := filepath.Dir(cleanPath)
	if parent != cleanPath {
		dirs = append([]DirEntry{{
			Name:  "..",
			Path:  parent,
			IsDir: true,
		}}, dirs...)
	}

	c.JSON(http.StatusOK, gin.H{
		"current": cleanPath,
		"entries": dirs,
	})
}

// ==================== 仪表板数据 ====================

// getDashboardStats 获取仪表板统计数据
func (s *Server) getDashboardStats(c *gin.Context) {
	// 获取入库统计
	limit, _ := strconv.Atoi(c.DefaultQuery("limit", "20"))
	libraryStats, err := s.store.GetLibraryStatsWithLimit(limit)
	if err != nil {
		libraryStats = &model.LibraryStats{
			Total:        0,
			LatestMovies: []model.LatestMovie{},
		}
	}

	// 为每个入库记录获取Emby封面图
	s.enrichLibraryStatsWithPosters(libraryStats)

	// 获取302跳转统计
	redirectStats, err := s.store.GetRedirectStats()
	if err != nil {
		redirectStats = &model.RedirectStats{
			Playing:    0,
			Today:      0,
			Total:      0,
			PlayingNow: []model.PlayingItem{},
		}
	}

	// 获取同步图表数据
	syncChart, err := s.store.GetSyncChartData()
	if err != nil {
		syncChart = &model.SyncChartData{
			Labels: []string{},
			Values: []int{},
		}
	}

	// 获取关键指标
	metrics, err := s.store.GetDashboardMetrics()
	if err != nil {
		metrics = &model.DashboardMetrics{}
	}

	// 获取115统计
	driver115Stats, err := s.store.GetDriver115Stats()
	if err != nil {
		driver115Stats = &model.Driver115Stats{}
	}

	// 获取最近活动
	recentActivity, err := s.store.GetRecentActivity(10)
	if err != nil {
		recentActivity = []model.ActivityLog{}
	}

	c.JSON(http.StatusOK, gin.H{
		"library":        libraryStats,
		"redirect":       redirectStats,
		"syncChart":      syncChart,
		"metrics":        metrics,
		"driver115":      driver115Stats,
		"recentActivity": recentActivity,
	})
}

// getLibraryStats 获取入库统计
func (s *Server) getLibraryStats(c *gin.Context) {
	limit, _ := strconv.Atoi(c.DefaultQuery("limit", "20"))
	stats, err := s.store.GetLibraryStatsWithLimit(limit)
	if err != nil {
		c.JSON(http.StatusInternalServerError, gin.H{"error": err.Error()})
		return
	}
	c.JSON(http.StatusOK, stats)
}

// getRedirectStats 获取302跳转统计
func (s *Server) getRedirectStats(c *gin.Context) {
	stats, err := s.store.GetRedirectStats()
	if err != nil {
		c.JSON(http.StatusInternalServerError, gin.H{"error": err.Error()})
		return
	}
	c.JSON(http.StatusOK, stats)
}

// getSyncChartData 获取同步图表数据
func (s *Server) getSyncChartData(c *gin.Context) {
	data, err := s.store.GetSyncChartData()
	if err != nil {
		c.JSON(http.StatusInternalServerError, gin.H{"error": err.Error()})
		return
	}
	c.JSON(http.StatusOK, data)
}

// ==================== 设置分类 ====================

// getSettingsCategories 获取设置分类（用于设置页面的分类配置）
func (s *Server) getSettingsCategories(c *gin.Context) {
	// 从数据库获取分类设置
	categoriesJSON, _ := s.store.GetSetting("categories")
	if categoriesJSON == "" {
		c.JSON(http.StatusOK, []interface{}{})
		return
	}

	var categories []interface{}
	if err := json.Unmarshal([]byte(categoriesJSON), &categories); err != nil {
		c.JSON(http.StatusOK, []interface{}{})
		return
	}
	c.JSON(http.StatusOK, categories)
}

// saveSettingsCategories 保存设置分类
func (s *Server) saveSettingsCategories(c *gin.Context) {
	var categories []interface{}
	if err := c.ShouldBindJSON(&categories); err != nil {
		c.JSON(http.StatusBadRequest, gin.H{"error": err.Error()})
		return
	}

	categoriesJSON, err := json.Marshal(categories)
	if err != nil {
		c.JSON(http.StatusInternalServerError, gin.H{"error": err.Error()})
		return
	}

	if err := s.store.SetSetting("categories", string(categoriesJSON)); err != nil {
		c.JSON(http.StatusInternalServerError, gin.H{"error": err.Error()})
		return
	}

	c.JSON(http.StatusOK, gin.H{"success": true})
}

// ==================== 后台任务管理 ====================

// getTasks 获取所有任务
func (s *Server) getTasks(c *gin.Context) {
	tasks := s.taskMgr.GetAllTasks()
	c.JSON(http.StatusOK, tasks)
}

// getTask 获取单个任务
func (s *Server) getTask(c *gin.Context) {
	id := c.Param("id")
	task := s.taskMgr.GetTask(id)
	if task == nil {
		c.JSON(http.StatusNotFound, gin.H{"error": "任务不存在"})
		return
	}
	c.JSON(http.StatusOK, task)
}

// cancelTask 取消任务
func (s *Server) cancelTask(c *gin.Context) {
	id := c.Param("id")
	if s.taskMgr.CancelTask(id) {
		c.JSON(http.StatusOK, gin.H{"success": true})
	} else {
		c.JSON(http.StatusBadRequest, gin.H{"error": "无法取消任务"})
	}
}

// deleteTask 删除任务
func (s *Server) deleteTask(c *gin.Context) {
	id := c.Param("id")
	if s.taskMgr.DeleteTask(id) {
		c.JSON(http.StatusOK, gin.H{"success": true})
	} else {
		c.JSON(http.StatusBadRequest, gin.H{"error": "无法删除任务"})
	}
}

// ==================== 工作队列统计 ====================

// getWorkQueueStats 获取工作队列统计信息
func (s *Server) getWorkQueueStats(c *gin.Context) {
	stats := s.monitorSvc.GetWorkQueueStats()
	if stats == nil {
		c.JSON(http.StatusOK, gin.H{
			"enabled": false,
		})
		return
	}
	c.JSON(http.StatusOK, stats)
}

// enrichLibraryStatsWithPosters 为入库统计添加Emby封面图
func (s *Server) enrichLibraryStatsWithPosters(stats *model.LibraryStats) {
	if stats == nil || len(stats.LatestMovies) == 0 {
		return
	}

	// 获取第一个启用的Emby代理配置
	proxies, err := s.store.GetAllEmbyProxies()
	if err != nil || len(proxies) == 0 {
		return
	}

	var embySvc *service.EmbyProxyService
	for _, proxy := range proxies {
		if proxy.Enabled && proxy.EmbyHost != "" {
			embySvc, err = service.NewEmbyProxyServiceWithTarget(proxy.EmbyHost, proxy.APIKey, s.cfg, s.store, s.driver115, s.cd2)
			if err == nil {
				break
			}
		}
	}

	if embySvc == nil {
		return
	}

	// 为每个入库记录搜索封面图
	for i := range stats.LatestMovies {
		movie := &stats.LatestMovies[i]
		if movie.Poster != "" {
			continue // 已有封面图
		}

		posterURL, err := embySvc.SearchMediaByName(movie.Name)
		if err == nil && posterURL != "" {
			movie.Poster = posterURL
		}
	}
}

// ==================== 监控模式 ====================

// getMonitorConfig 获取监控配置
func (s *Server) getMonitorConfig(c *gin.Context) {
	config, err := s.store.GetMonitorConfig()
	if err != nil {
		c.JSON(http.StatusInternalServerError, gin.H{"error": err.Error()})
		return
	}
	c.JSON(http.StatusOK, config)
}

// setMonitorMode 设置监控模式
func (s *Server) setMonitorMode(c *gin.Context) {
	var input struct {
		Mode string `json:"mode"`
	}
	if err := c.ShouldBindJSON(&input); err != nil {
		c.JSON(http.StatusBadRequest, gin.H{"error": err.Error()})
		return
	}

	mode := model.MonitorMode(input.Mode)
	if mode != model.MonitorModeCD2 && mode != model.MonitorModeLifeEvent {
		c.JSON(http.StatusBadRequest, gin.H{"error": "无效的监控模式"})
		return
	}

	// 热更新：立即切换监控模式
	if s.monitorMgr != nil {
		if err := s.monitorMgr.SwitchMode(mode); err != nil {
			c.JSON(http.StatusInternalServerError, gin.H{"error": err.Error()})
			return
		}
	} else {
		// 如果monitorMgr未设置，只更新数据库
		if err := s.store.SetMonitorMode(mode); err != nil {
			c.JSON(http.StatusInternalServerError, gin.H{"error": err.Error()})
			return
		}
	}

	s.logger.LogSystem(model.LogLevelInfo, fmt.Sprintf("切换监控模式: %s", mode), nil)
	c.JSON(http.StatusOK, gin.H{"message": "监控模式已切换"})
}
