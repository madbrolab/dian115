package model

import "time"

// SyncMode 同步模式
type SyncMode string

const (
	SyncModeManual   SyncMode = "manual"   // 手动同步
	SyncModeCron     SyncMode = "cron"     // 定时同步
	SyncModeRealtime SyncMode = "realtime" // 实时监控
)

// HasSyncMode 检查 sync_mode 字段是否包含指定模式（支持逗号分隔的多模式）
func HasSyncMode(syncModeStr string, mode SyncMode) bool {
	if syncModeStr == string(mode) {
		return true
	}
	for i := 0; i < len(syncModeStr); {
		j := i
		for j < len(syncModeStr) && syncModeStr[j] != ',' {
			j++
		}
		if syncModeStr[i:j] == string(mode) {
			return true
		}
		i = j + 1
	}
	return false
}

// STRMRule STRM生成规则
type STRMRule struct {
	ID             int64     `json:"id"`
	Name           string    `json:"name"`
	SourcePath     string    `json:"source_path"` // CD2源路径（CD2内部路径）
	OutputPath     string    `json:"output_path"` // STRM输出路径
	Recursive      bool      `json:"recursive"`
	Enabled        bool      `json:"enabled"`
	SyncMode       SyncMode  `json:"sync_mode"`       // 同步模式: manual, cron, realtime（逗号分隔可多选）
	CronExpr       string    `json:"cron_expr"`       // Cron表达式（定时同步时使用）
	FullSyncCron   string    `json:"full_sync_cron"`  // 定时全量同步Cron表达式（重建目录树+同步）
	MetaExtensions string    `json:"meta_extensions"` // 元数据文件后缀（逗号分隔，如 .nfo,.jpg），为空使用默认
	ExcludeKeys    string    `json:"exclude_keys"`    // 排除关键字（逗号分隔）
	FileExtensions string    `json:"file_extensions"` // 自定义文件后缀（逗号分隔，如 .mkv,.mp4），为空使用全局默认
	SmartClean     bool      `json:"smart_clean"`     // 智能清理：CD2删除时同步清理STRM+元数据+空目录
	CleanStrm      bool      `json:"clean_strm"`      // 源文件删除后是否删除STRM文件
	CleanMeta      bool      `json:"clean_meta"`      // 源文件删除后是否删除同名元数据文件
	CleanEmptyDir  bool      `json:"clean_empty_dir"` // 是否清理空父目录
	CleanDirDepth  int       `json:"clean_dir_depth"` // 清理空目录的最大向上递归深度
	CloudName      string    `json:"cloud_name"`      // CD2中的云盘名称（如 115, 115open）
	TreeBuilt      bool      `json:"tree_built"`      // 目录树是否已构建
	TreeFileCount  int       `json:"tree_file_count"` // 目录树中的文件数量
	FileCount      int       `json:"file_count"`      // 已同步文件数
	LastSyncTime   time.Time `json:"last_sync_time"`  // 最后同步时间
	CreatedAt      time.Time `json:"created_at"`
	UpdatedAt      time.Time `json:"updated_at"`
}

// FileMapping 文件映射
type FileMapping struct {
	ID        int64     `json:"id"`
	CD2Path   string    `json:"cd2_path"`  // CD2完整路径
	PickCode  string    `json:"pick_code"` // 115 pickcode
	FileName  string    `json:"file_name"` // 文件名
	FileSize  int64     `json:"file_size"` // 文件大小
	STRMPath  string    `json:"strm_path"` // STRM文件路径
	RuleID    int64     `json:"rule_id"`   // 关联的规则ID
	CreatedAt time.Time `json:"created_at"`
	UpdatedAt time.Time `json:"updated_at"`
}

// FileTreeNode 目录树节点
type FileTreeNode struct {
	ID         int64     `json:"id"`
	RuleID     int64     `json:"rule_id"`     // 关联的 STRM 规则 ID
	Name       string    `json:"name"`        // 文件/目录名
	Path115    string    `json:"path_115"`    // 115 网盘路径（如 /电影/xxx.mkv）
	CD2Path    string    `json:"cd2_path"`    // CD2 内部路径（如 /115/电影/xxx.mkv）
	MountPath  string    `json:"mount_path"`  // CD2 挂载路径（如 /CloudNAS/CloudDrive/115/电影/xxx.mkv）
	ParentPath string    `json:"parent_path"` // 父目录的 115 路径
	IsDir      bool      `json:"is_dir"`      // 是否为目录
	FileSize   int64     `json:"file_size"`   // 文件大小
	PickCode   string    `json:"pick_code"`   // 115 pickcode
	SHA1       string    `json:"sha1"`        // 文件 SHA1
	CID        string    `json:"cid"`         // 115 目录/文件 ID
	Ext        string    `json:"ext"`         // 文件扩展名（小写，如 .mkv）
	STRMPath   string    `json:"strm_path"`   // 已生成的 STRM 文件路径
	CreatedAt  time.Time `json:"created_at"`
	UpdatedAt  time.Time `json:"updated_at"`
}

// LinkCache 直链缓存
type LinkCache struct {
	PickCode  string    `json:"pick_code"`
	UserAgent string    `json:"user_agent"`
	URL       string    `json:"url"`
	ExpiresAt time.Time `json:"expires_at"`
}

// CD2FileInfo CD2文件信息
type CD2FileInfo struct {
	Name       string `json:"name"`
	Path       string `json:"path"`
	Size       int64  `json:"size"`
	IsDir      bool   `json:"isDir"`
	PickCode   string `json:"pickCode"`
	ModifyTime int64  `json:"modifyTime"`
}

// FileInfo 文件信息（通用）
type FileInfo struct {
	Name     string    `json:"name"`
	Path     string    `json:"path"`
	Size     int64     `json:"size"`
	IsDir    bool      `json:"is_dir"`
	ModTime  time.Time `json:"mod_time"`
	PickCode string    `json:"pick_code"`
	FileHash string    `json:"file_hash"`
}

// QRCodeInfo 二维码信息
type QRCodeInfo struct {
	UID    string `json:"uid"`
	Sign   string `json:"sign"`
	Time   int64  `json:"time"`
	QRCode string `json:"qrcode"` // 二维码图片URL或Base64
	Status int    `json:"status"` // 0=等待扫码, 1=已扫码待确认, 2=已确认
}

// User115Info 115用户信息
type User115Info struct {
	UserID     string `json:"user_id"`
	UserName   string `json:"user_name"`
	IsVIP      bool   `json:"is_vip"`
	AvatarURL  string `json:"avatar_url"`  // 头像URL
	SpaceTotal int64  `json:"space_total"` // 总空间(字节)
	SpaceUsed  int64  `json:"space_used"`  // 已用空间(字节)
}

// SystemStatus 系统状态
type SystemStatus struct {
	CD2Connected  bool   `json:"cd2_connected"`
	Login115      bool   `json:"login_115"`
	User115       string `json:"user_115"`
	EmbyConnected bool   `json:"emby_connected"`
	RuleCount     int    `json:"rule_count"`
	FileCount     int    `json:"file_count"`
}

// EmbyProxy Emby代理配置
type EmbyProxy struct {
	ID            int64     `json:"id"`
	Name          string    `json:"name"`
	EmbyHost      string    `json:"emby_host"`
	APIKey        string    `json:"api_key"`
	ProxyPort     int       `json:"proxy_port"`
	Enabled       bool      `json:"enabled"`
	LocalOnly     bool      `json:"local_only"`     // 使用本地代理（不使用302跳转）
	FallbackLocal bool      `json:"fallback_local"` // 302跳转失败时使用本地代理
	CloudName     string    `json:"cloud_name"`     // 115云盘名称（CD2挂载时的云盘名，如115open）
	CreatedAt     time.Time `json:"created_at"`
	UpdatedAt     time.Time `json:"updated_at"`
}

// Account115 115账号配置
type Account115 struct {
	ID           int64     `json:"id"`
	Name         string    `json:"name"`          // 配置名称
	Cookie       string    `json:"cookie"`        // Cookie内容
	UserID       string    `json:"user_id"`       // 用户ID（从cookie解析或API获取）
	UserName     string    `json:"user_name"`     // 用户名
	IsVIP        bool      `json:"is_vip"`        // 是否VIP
	AvatarURL    string    `json:"avatar_url"`    // 头像URL（原始）
	AvatarLocal  string    `json:"avatar_local"`  // 本地缓存头像路径
	SpaceTotal   int64     `json:"space_total"`   // 总空间(字节)
	SpaceUsed    int64     `json:"space_used"`    // 已用空间(字节)
	AutoSign     bool      `json:"auto_sign"`     // 是否自动签到
	IsActive     bool      `json:"is_active"`     // 是否为当前激活账号
	SortOrder    int       `json:"sort_order"`    // 排序顺序
	DeviceType   string    `json:"device_type"`   // 登录设备类型
	CookieStatus string    `json:"cookie_status"` // cookie状态: valid/invalid/unknown
	LastCheckAt  time.Time `json:"last_check_at"` // 最后检查时间
	CreatedAt    time.Time `json:"created_at"`
	UpdatedAt    time.Time `json:"updated_at"`
}

// DeviceTypes 支持的设备类型
var DeviceTypes = map[string]string{
	"ios":        "115生活_苹果端",
	"115ios":     "115_苹果端",
	"android":    "115生活_安卓端",
	"115android": "115_安卓端",
	"ipad":       "115生活_苹果平板端",
	"115ipad":    "115_苹果平板端",
	"tv":         "115生活_安卓电视端",
	"apple_tv":   "115生活_苹果电视端",
	"qandroid":   "115管理_安卓端",
	"qios":       "115管理_苹果端",
	"qipad":      "115管理_苹果平板端",
	"wechatmini": "115生活_微信小程序端",
	"alipaymini": "115生活_支付宝小程序端",
	"harmony":    "115_鸿蒙端",
}

// CookieStatus 常量
const (
	CookieStatusValid   = "valid"
	CookieStatusInvalid = "invalid"
	CookieStatusUnknown = "unknown"
)

// ==================== 日志系统 ====================

// LogType 日志类型（按功能模块分类）
type LogType string

const (
	LogTypeSystem    LogType = "system"    // 系统日志
	LogTypeSync      LogType = "sync"      // STRM同步日志
	LogTypeArchive   LogType = "archive"   // 归档日志
	LogTypeEmby      LogType = "emby"      // Emby代理日志
	LogType115       LogType = "115"       // 115网盘日志
	LogTypeMonitor   LogType = "monitor"   // 文件监控日志
	LogTypeScheduler LogType = "scheduler" // 定时任务日志
	LogTypeAPI       LogType = "api"       // API请求日志
)

// LogLevel 日志级别
type LogLevel string

const (
	LogLevelDebug   LogLevel = "debug"   // 调试信息
	LogLevelInfo    LogLevel = "info"    // 普通信息
	LogLevelSuccess LogLevel = "success" // 成功
	LogLevelWarning LogLevel = "warning" // 警告
	LogLevelError   LogLevel = "error"   // 错误
)

// LogCategory 日志类别（简化为4类）
type LogCategory string

const (
	LogCategoryNormal  LogCategory = "normal"  // 普通
	LogCategorySuccess LogCategory = "success" // 成功
	LogCategoryFail    LogCategory = "fail"    // 失败
	LogCategoryError   LogCategory = "error"   // 错误
)

// LogEntry 日志条目
type LogEntry struct {
	ID        int64       `json:"id"`
	Type      LogType     `json:"type"`     // 日志类型（模块）
	Category  LogCategory `json:"category"` // 日志类别（操作）
	Level     LogLevel    `json:"level"`    // 日志级别
	Message   string      `json:"message"`  // 日志消息
	Details   string      `json:"details"`  // 详细信息（JSON格式）
	RuleID    int64       `json:"rule_id"`  // 关联的规则ID（可选）
	CreatedAt time.Time   `json:"created_at"`
}

// HistoryRecord 历史记录
type HistoryRecord struct {
	ID        int64     `json:"id"`
	Type      string    `json:"type"`      // sync/archive
	RuleID    int64     `json:"rule_id"`   // 关联的规则ID
	RuleName  string    `json:"rule_name"` // 规则名称
	Success   int       `json:"success"`   // 成功数量
	Failed    int       `json:"failed"`    // 失败数量
	Deleted   int       `json:"deleted"`   // 删除数量
	Duration  int64     `json:"duration"`  // 耗时（毫秒）
	Details   string    `json:"details"`   // 详细信息（JSON格式）
	CreatedAt time.Time `json:"created_at"`
}

// ==================== 二级分类系统 ====================

// MediaCategory 媒体分类
type MediaCategory struct {
	ID         int64     `json:"id"`
	MediaType  string    `json:"media_type"` // movie/tv
	Name       string    `json:"name"`       // 分类名称
	Conditions string    `json:"conditions"` // 匹配条件（JSON格式）
	SortOrder  int       `json:"sort_order"` // 排序顺序
	IsDefault  bool      `json:"is_default"` // 是否为默认分类（无法删除）
	CreatedAt  time.Time `json:"created_at"`
	UpdatedAt  time.Time `json:"updated_at"`
}

// CategoryCondition 分类条件
type CategoryCondition struct {
	GenreIDs         string `json:"genre_ids,omitempty"`         // 类型ID，逗号分隔
	OriginalLanguage string `json:"original_language,omitempty"` // 原始语言
	OriginCountry    string `json:"origin_country,omitempty"`    // 原产国
}

// OrganizeRule 整理规则
type OrganizeRule struct {
	ID          int64     `json:"id"`
	Name        string    `json:"name"`         // 规则名称
	SourcePath  string    `json:"source_path"`  // 源路径
	TargetPath  string    `json:"target_path"`  // 目标路径
	MediaType   string    `json:"media_type"`   // movie/tv
	UseCategory bool      `json:"use_category"` // 是否使用二级分类
	Enabled     bool      `json:"enabled"`
	CreatedAt   time.Time `json:"created_at"`
	UpdatedAt   time.Time `json:"updated_at"`
}

// ==================== 仪表板数据 ====================

// LibraryStats 入库统计
type LibraryStats struct {
	Total        int           `json:"total"`         // 总入库数
	LatestMovies []LatestMovie `json:"latest_movies"` // 最新入库的电影
}

// LatestMovie 最新入库的电影
type LatestMovie struct {
	ID         int64     `json:"id"`
	Name       string    `json:"name"`        // 电影名称
	Poster     string    `json:"poster"`      // 海报URL
	AddedAt    time.Time `json:"added_at"`    // 入库时间
	SourcePath string    `json:"source_path"` // 源路径
}

// RedirectStats 302跳转统计
type RedirectStats struct {
	Playing    int           `json:"playing"`     // 正在播放数
	Today      int           `json:"today"`       // 今日播放数
	Total      int           `json:"total"`       // 总播放数
	PlayingNow []PlayingItem `json:"playing_now"` // 正在播放的内容
}

// PlayingItem 正在播放的项目
type PlayingItem struct {
	Title     string    `json:"title"`      // 标题
	User      string    `json:"user"`       // 用户
	StartTime time.Time `json:"start_time"` // 开始时间
	Progress  float64   `json:"progress"`   // 播放进度
}

// SyncChartData 同步图表数据
type SyncChartData struct {
	Labels []string `json:"labels"` // 日期标签
	Values []int    `json:"values"` // 同步数量
}

// DashboardMetrics 仪表板关键指标
type DashboardMetrics struct {
	StrmTotal  int `json:"strm_total"`  // STRM文件总数
	StrmToday  int `json:"strm_today"`  // 今日新增
	Sync24h    int `json:"sync_24h"`    // 24小时同步
	ErrorCount int `json:"error_count"` // 错误数量
}

// Driver115Stats 115网盘统计
type Driver115Stats struct {
	SpaceUsed     string `json:"space_used"`      // 空间使用
	AccountCount  int    `json:"account_count"`   // 账号总数
	ApiCallsToday int    `json:"api_calls_today"` // 今日API调用
}

// ActivityLog 活动日志
type ActivityLog struct {
	ID        int64     `json:"id"`
	Type      string    `json:"type"`    // 类型：sync, error, info
	Message   string    `json:"message"` // 消息
	CreatedAt time.Time `json:"created_at"`
}

// PlayRecord 播放记录
type PlayRecord struct {
	ID        int64     `json:"id"`
	FileName  string    `json:"file_name"`  // 文件名
	FilePath  string    `json:"file_path"`  // 文件路径
	UserAgent string    `json:"user_agent"` // 用户代理
	ClientIP  string    `json:"client_ip"`  // 客户端IP
	ProxyID   int64     `json:"proxy_id"`   // 代理ID
	StartTime time.Time `json:"start_time"` // 开始时间
	EndTime   time.Time `json:"end_time"`   // 结束时间
	IsPlaying bool      `json:"is_playing"` // 是否正在播放
	CreatedAt time.Time `json:"created_at"`
}

// ==================== 监控模式 ====================

// MonitorMode 监控模式
type MonitorMode string

const (
	MonitorModeCD2       MonitorMode = "cd2"        // CD2文件系统监控
	MonitorModeLifeEvent MonitorMode = "life_event" // 115生活事件监控
)

// MonitorConfig 全局监控配置
type MonitorConfig struct {
	ID        int64       `json:"id"`
	Mode      MonitorMode `json:"mode"` // 监控模式
	UpdatedAt time.Time   `json:"updated_at"`
}

// LifeEvent 115生活事件
type LifeEvent struct {
	ID           int64     `json:"id"`
	Type         int       `json:"type"`          // 事件类型
	FileID       string    `json:"file_id"`       // 文件ID
	ParentID     string    `json:"parent_id"`     // 父目录ID
	FileName     string    `json:"file_name"`     // 文件名
	FileCategory int       `json:"file_category"` // 文件分类
	FileType     int       `json:"file_type"`     // 文件类型
	FileSize     int64     `json:"file_size"`     // 文件大小
	SHA1         string    `json:"sha1"`          // SHA1
	PickCode     string    `json:"pick_code"`     // PickCode
	UpdateTime   int64     `json:"update_time"`   // 更新时间戳
	CreateTime   int64     `json:"create_time"`   // 创建时间戳
	Processed    bool      `json:"processed"`     // 是否已处理
	CreatedAt    time.Time `json:"created_at"`
}

// LifeEventState 生活事件轮询状态
type LifeEventState struct {
	ID         int64     `json:"id"`
	FromTime   int64     `json:"from_time"`    // 上次拉取的时间戳
	FromID     int64     `json:"from_id"`      // 上次拉取的事件ID
	LastPullAt time.Time `json:"last_pull_at"` // 最后拉取时间
	UpdatedAt  time.Time `json:"updated_at"`
}
