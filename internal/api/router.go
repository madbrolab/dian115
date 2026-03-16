package api

import (
	"net/http"
	"sync"

	"github.com/gin-gonic/gin"

	"strm-manager/internal/client"
	"strm-manager/internal/config"
	"strm-manager/internal/service"
	"strm-manager/internal/store"
)

// Server API服务器
type Server struct {
	cfg        *config.Config
	store      *store.Store
	cd2        *client.CloudDriveClient
	driver115  *client.Driver115Client
	strmSvc    *service.STRMService
	monitorSvc *service.MonitorService
	monitorMgr *service.MonitorManager
	embySvc    *service.EmbyProxyService
	treeSvc    *service.TreeService
	logger     *service.LoggerService
	taskMgr    *service.TaskManager
	engine     *gin.Engine
	proxyCache sync.Map // embyHost -> *service.EmbyProxyService（复用代理实例，保留缓存）
}

// NewServer 创建API服务器
func NewServer(
	cfg *config.Config,
	store *store.Store,
	cd2 *client.CloudDriveClient,
	driver115 *client.Driver115Client,
	strmSvc *service.STRMService,
	monitorSvc *service.MonitorService,
	embySvc *service.EmbyProxyService,
	logger *service.LoggerService,
) *Server {
	s := &Server{
		cfg:        cfg,
		store:      store,
		cd2:        cd2,
		driver115:  driver115,
		strmSvc:    strmSvc,
		monitorSvc: monitorSvc,
		embySvc:    embySvc,
		logger:     logger,
		taskMgr:    service.NewTaskManager(),
	}

	// 设置Cookie失效回调
	if driver115 != nil {
		driver115.SetOnCookieExpired(func() {
			s.MarkActiveCookieInvalid()
		})
	}

	return s
}

// SetMonitorManager 设置监控管理器
func (s *Server) SetMonitorManager(mgr *service.MonitorManager) {
	s.monitorMgr = mgr
}

// SetupRouter 设置路由
func (s *Server) SetupRouter() *gin.Engine {
	gin.SetMode(gin.ReleaseMode)
	engine := gin.New()
	engine.Use(gin.Recovery())
	engine.Use(corsMiddleware())

	// 静态文件
	engine.Static("/static", "./static")
	engine.Static("/data/avatars", "./data/avatars")
	engine.StaticFile("/", "./static/strm.html")
	engine.StaticFile("/strm", "./static/strm.html")

	// API路由
	api := engine.Group("/api")
	{
		// 系统状态
		api.GET("/status", s.getStatus)

		// 文件浏览
		api.GET("/browse", s.browseCD2Path)

		// STRM规则
		api.GET("/rules", s.getRules)
		api.POST("/rules", s.createRule)
		api.PUT("/rules/:id", s.updateRule)
		api.DELETE("/rules/:id", s.deleteRule)
		api.POST("/rules/:id/sync", s.syncRule)
		api.POST("/rules/:id/full-sync", s.fullSyncRule)
		api.POST("/rules/:id/toggle", s.toggleRule)
		api.POST("/rules/sync-all", s.syncAllRules)

		// 115登录
		api.GET("/115/qrcode", s.getQRCode)
		api.GET("/115/qrcode/status", s.getQRCodeStatus)
		api.POST("/115/login", s.loginWithQRCode)
		api.POST("/115/cookie", s.setCookie)
		api.GET("/115/status", s.get115Status)

		// 设置
		api.GET("/settings", s.getSettingsFlat)
		api.PUT("/settings", s.updateSettings)
		api.PUT("/settings/cd2", s.saveCD2Settings)
		api.POST("/settings/cd2/refresh-token", s.refreshCD2Token)
		api.POST("/settings/test/cd2", s.testCD2)
		api.POST("/settings/test/emby", s.testEmby)

		// Emby代理管理
		api.GET("/emby-proxies", s.getEmbyProxies)
		api.POST("/emby-proxies", s.createEmbyProxy)
		api.PUT("/emby-proxies/:id", s.updateEmbyProxy)
		api.DELETE("/emby-proxies/:id", s.deleteEmbyProxy)

		// Emby统计API
		api.GET("/emby/stats", s.getEmbyStats)
		api.GET("/emby/recent", s.getEmbyRecentItems)
		api.GET("/emby/random", s.getEmbyRandomItems)
		api.GET("/emby/popular", s.getEmbyPopularItems)
		api.GET("/emby/playing", s.getEmbyPlayingSessions)

		// 115账号管理
		api.GET("/accounts/115", s.getAccounts115)
		api.POST("/accounts/115", s.createAccount115)
		api.PUT("/accounts/115/:id", s.updateAccount115)
		api.DELETE("/accounts/115/:id", s.deleteAccount115)
		api.POST("/accounts/115/:id/activate", s.setActiveAccount115)
		api.GET("/accounts/115/:id/cookie", s.getAccount115Cookie)
		api.POST("/accounts/115/reorder", s.reorderAccounts115)
		api.GET("/115/device-types", s.getDeviceTypes)
		api.POST("/115/check-cookies", s.checkAllCookies)
		api.POST("/accounts/115/:id/check", s.checkSingleCookie)
		api.POST("/accounts/115/:id/sign", s.signAccount115)
		api.POST("/accounts/115/:id/refresh", s.refreshAccount115Info)
		api.PUT("/115/auto-switch", s.setAutoSwitch)
		api.PUT("/115/rate-limit", s.setAPIRateLimit)

		// 日志管理
		api.GET("/logs", s.getLogs)
		api.GET("/logs/stream", s.streamLogs)
		api.DELETE("/logs", s.clearLogs)
		api.GET("/logs/stats", s.getLogStats)

		// 历史记录
		api.GET("/history", s.getHistoryRecords)
		api.GET("/history/stats", s.getHistoryStats)

		// 媒体分类
		api.GET("/categories", s.getMediaCategories)
		api.POST("/categories", s.createMediaCategory)
		api.PUT("/categories/:id", s.updateMediaCategory)
		api.DELETE("/categories/:id", s.deleteMediaCategory)
		api.POST("/categories/reorder", s.reorderMediaCategories)

		// 设置分类（别名，兼容前端）
		api.GET("/settings/categories", s.getSettingsCategories)
		api.POST("/settings/categories", s.saveSettingsCategories)

		// 整理规则
		api.GET("/organize-rules", s.getOrganizeRules)
		api.POST("/organize-rules", s.createOrganizeRule)
		api.PUT("/organize-rules/:id", s.updateOrganizeRule)
		api.DELETE("/organize-rules/:id", s.deleteOrganizeRule)

		// 本地路径浏览
		api.GET("/local-dirs", s.listLocalDir)

		// 仪表板数据
		api.GET("/dashboard/stats", s.getDashboardStats)
		api.GET("/dashboard/library", s.getLibraryStats)
		api.GET("/dashboard/redirect", s.getRedirectStats)
		api.GET("/dashboard/sync-chart", s.getSyncChartData)

		// 后台任务管理
		api.GET("/tasks", s.getTasks)
		api.GET("/tasks/:id", s.getTask)
		api.POST("/tasks/:id/cancel", s.cancelTask)
		api.DELETE("/tasks/:id", s.deleteTask)

		// 工作队列统计
		api.GET("/workqueue/stats", s.getWorkQueueStats)

		// 监控模式
		api.GET("/monitor/config", s.getMonitorConfig)
		api.PUT("/monitor/mode", s.setMonitorMode)

		// 目录树管理
		api.POST("/rules/:id/tree/build", s.buildTree)
		api.GET("/rules/:id/tree/stats", s.getTreeStats)
		api.DELETE("/rules/:id/tree", s.deleteTree)
	}

	s.engine = engine
	return engine
}

// SetupEmbyProxy 设置Emby代理路由器（单独端口）
func (s *Server) SetupEmbyProxy() *gin.Engine {
	gin.SetMode(gin.ReleaseMode)
	engine := gin.New()
	engine.Use(gin.Recovery())
	engine.Use(corsMiddleware())

	// Emby代理 - 所有请求都转发
	engine.Any("/*path", s.handleEmbyProxy)

	return engine
}

// Run 运行服务器
func (s *Server) Run(addr string) error {
	return s.engine.Run(addr)
}

// RunEmbyProxy 运行Emby代理服务器（使用默认配置）
func (s *Server) RunEmbyProxy(addr string) error {
	embyEngine := s.SetupEmbyProxy()
	return embyEngine.Run(addr)
}

// RunEmbyProxyWithTarget 运行指定目标的Emby代理服务器
func (s *Server) RunEmbyProxyWithTarget(addr, embyHost, apiKey string) error {
	return s.RunEmbyProxyWithOptions(addr, embyHost, apiKey, false, true, "")
}

// RunEmbyProxyWithOptions 运行带选项的Emby代理服务器
func (s *Server) RunEmbyProxyWithOptions(addr, embyHost, apiKey string, localOnly, fallbackLocal bool, cloudName string) error {
	gin.SetMode(gin.ReleaseMode)
	engine := gin.New()
	engine.Use(gin.Recovery())
	engine.Use(corsMiddleware())

	// 创建针对特定Emby服务器的代理处理器
	engine.Any("/*path", func(c *gin.Context) {
		s.handleEmbyProxyWithOptions(c, embyHost, apiKey, localOnly, fallbackLocal, cloudName)
	})

	return engine.Run(addr)
}

// corsMiddleware CORS中间件
func corsMiddleware() gin.HandlerFunc {
	return func(c *gin.Context) {
		c.Header("Access-Control-Allow-Origin", "*")
		c.Header("Access-Control-Allow-Methods", "GET, POST, PUT, DELETE, OPTIONS")
		c.Header("Access-Control-Allow-Headers", "Content-Type, Authorization, X-Emby-Authorization")

		if c.Request.Method == "OPTIONS" {
			c.AbortWithStatus(http.StatusNoContent)
			return
		}

		c.Next()
	}
}

// handleEmbyProxy 处理Emby代理请求
func (s *Server) handleEmbyProxy(c *gin.Context) {
	s.embySvc.ServeHTTP(c.Writer, c.Request)
}

// handleEmbyProxyWithTarget 处理指定目标的Emby代理请求
func (s *Server) handleEmbyProxyWithTarget(c *gin.Context, embyHost, apiKey string) {
	s.handleEmbyProxyWithOptions(c, embyHost, apiKey, false, true, "")
}

// handleEmbyProxyWithOptions 处理带选项的Emby代理请求（复用代理实例）
func (s *Server) handleEmbyProxyWithOptions(c *gin.Context, embyHost, apiKey string, localOnly, fallbackLocal bool, cloudName string) {
	// 用 embyHost 作为 key 复用代理实例，避免每次请求都新建导致缓存丢失
	cacheKey := embyHost
	if cached, ok := s.proxyCache.Load(cacheKey); ok {
		cached.(*service.EmbyProxyService).ServeHTTP(c.Writer, c.Request)
		return
	}

	proxySvc, err := service.NewEmbyProxyServiceWithOptions(embyHost, apiKey, localOnly, fallbackLocal, cloudName, s.cfg, s.store, s.driver115, s.cd2)
	if err != nil {
		c.JSON(http.StatusInternalServerError, gin.H{"error": err.Error()})
		return
	}
	proxySvc.SetLogger(s.logger)
	s.proxyCache.Store(cacheKey, proxySvc)
	proxySvc.ServeHTTP(c.Writer, c.Request)
}
