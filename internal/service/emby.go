package service

import (
	"encoding/json"
	"fmt"
	"io"
	"net/http"
	"net/http/httputil"
	"net/url"
	"os"
	"path/filepath"
	"regexp"
	"strings"
	"sync"
	"time"

	"strm-manager/internal/client"
	"strm-manager/internal/config"
	"strm-manager/internal/model"
	"strm-manager/internal/store"
)

// EmbyProxyService Emby代理服务
type EmbyProxyService struct {
	cfg            *config.Config
	store          *store.Store
	driver115      *client.Driver115Client
	cd2            *client.CloudDriveClient
	embyURL        *url.URL
	embyAPIKey     string
	reverseProxy   *httputil.ReverseProxy
	directURLCache sync.Map // cd2挂载路径 -> *cachedLink（15分钟过期）
	localOnly      bool
	fallbackLocal  bool
	cloudName      string
	debugMode      bool
	logger         *LoggerService
}

type cachedLink struct {
	url       string
	userAgent string // 获取此直链时使用的UA
	expiresAt time.Time
}

// 匹配视频流请求的正则
var videoStreamPattern = regexp.MustCompile(`(?i)^/(?:emby/)?videos/(\d+)/(?:stream|original\.|[^/]+\.(mp4|mkv|avi|mov|wmv|flv|webm|m4v|ts))`)

// NewEmbyProxyService 创建Emby代理服务
func NewEmbyProxyService(cfg *config.Config, store *store.Store, driver115 *client.Driver115Client, cd2 *client.CloudDriveClient) (*EmbyProxyService, error) {
	var embyURL *url.URL
	var err error

	if cfg != nil && cfg.Emby.Host != "" {
		embyURL, err = url.Parse(cfg.Emby.Host)
		if err != nil {
			return nil, fmt.Errorf("解析Emby地址失败: %v", err)
		}
	}

	svc := &EmbyProxyService{
		cfg:       cfg,
		store:     store,
		driver115: driver115,
		cd2:       cd2,
		embyURL:   embyURL,
	}

	if embyURL != nil {
		svc.reverseProxy = &httputil.ReverseProxy{
			Director:      svc.director,
			ErrorHandler:  svc.errorHandler,
			FlushInterval: -1,
		}
	}

	return svc, nil
}

// NewEmbyProxyServiceWithTarget 创建针对特定目标的Emby代理服务
func NewEmbyProxyServiceWithTarget(embyHost, apiKey string, cfg *config.Config, store *store.Store, driver115 *client.Driver115Client, cd2 *client.CloudDriveClient) (*EmbyProxyService, error) {
	return NewEmbyProxyServiceWithOptions(embyHost, apiKey, false, true, "", cfg, store, driver115, cd2)
}

// NewEmbyProxyServiceWithOptions 创建带选项的Emby代理服务
func NewEmbyProxyServiceWithOptions(embyHost, apiKey string, localOnly, fallbackLocal bool, cloudName string, cfg *config.Config, store *store.Store, driver115 *client.Driver115Client, cd2 *client.CloudDriveClient) (*EmbyProxyService, error) {
	embyURL, err := url.Parse(embyHost)
	if err != nil {
		return nil, fmt.Errorf("解析Emby地址失败: %v", err)
	}

	svc := &EmbyProxyService{
		cfg:           cfg,
		store:         store,
		driver115:     driver115,
		cd2:           cd2,
		embyURL:       embyURL,
		embyAPIKey:    apiKey,
		localOnly:     localOnly,
		fallbackLocal: fallbackLocal,
		cloudName:     cloudName,
	}

	svc.reverseProxy = &httputil.ReverseProxy{
		Director:      svc.director,
		ErrorHandler:  svc.errorHandler,
		FlushInterval: -1,
	}

	return svc, nil
}

// director 修改请求
func (s *EmbyProxyService) director(req *http.Request) {
	req.URL.Scheme = s.embyURL.Scheme
	req.URL.Host = s.embyURL.Host
	req.Host = s.embyURL.Host
}

// SetCD2 热更新CD2客户端
func (s *EmbyProxyService) SetCD2(cd2 *client.CloudDriveClient) {
	s.cd2 = cd2
}

// SetLogger 设置日志服务
func (s *EmbyProxyService) SetLogger(logger *LoggerService) {
	s.logger = logger
}

// errorHandler 错误处理
func (s *EmbyProxyService) errorHandler(w http.ResponseWriter, r *http.Request, err error) {
	if s.logger != nil {
		s.logger.LogEmby(model.LogCategoryError, model.LogLevelError, fmt.Sprintf("代理错误: %s %s - %v", r.Method, r.URL.Path, err), map[string]string{
			"method":    r.Method,
			"path":      r.URL.Path,
			"error":     err.Error(),
			"client_ip": r.RemoteAddr,
		})
	}
	fmt.Printf("[EmbyProxy] 代理错误: %s %s - %v\n", r.Method, r.URL.Path, err)
	http.Error(w, "代理错误: "+err.Error(), http.StatusBadGateway)
}

// safeProxy 安全地调用反向代理
func (s *EmbyProxyService) safeProxy(w http.ResponseWriter, r *http.Request) {
	defer func() {
		if rec := recover(); rec != nil {
			if s.logger != nil {
				s.logger.LogEmby(model.LogCategoryError, model.LogLevelWarning, fmt.Sprintf("代理连接中断: %s %s", r.Method, r.URL.Path), map[string]string{
					"method": r.Method,
					"path":   r.URL.Path,
					"panic":  fmt.Sprintf("%v", rec),
				})
			}
			s.debugLog("[EmbyProxy] 代理连接中断（已恢复）: %s %s - %v\n", r.Method, r.URL.Path, rec)
		}
	}()
	s.reverseProxy.ServeHTTP(w, r)
}

// debugLog 仅在调试模式下输出日志
func (s *EmbyProxyService) debugLog(format string, args ...interface{}) {
	if s.debugMode {
		fmt.Printf(format, args...)
	}
}

// ServeHTTP 处理HTTP请求
func (s *EmbyProxyService) ServeHTTP(w http.ResponseWriter, r *http.Request) {
	path := r.URL.Path

	// 本地代理模式，直接代理所有请求
	if s.localOnly {
		if s.logger != nil {
			s.logger.LogEmby(model.LogCategoryNormal, model.LogLevelDebug, fmt.Sprintf("本地代理模式转发: %s %s", r.Method, path), map[string]string{
				"client_ip": r.RemoteAddr,
			})
		}
		s.safeProxy(w, r)
		return
	}

	// 检查是否是视频流请求
	if matches := videoStreamPattern.FindStringSubmatch(path); matches != nil {
		itemID := matches[1]
		if itemID == "" {
			itemID = matches[2]
		}
		if itemID != "" {
			if s.logger != nil {
				s.logger.LogEmby(model.LogCategoryNormal, model.LogLevelInfo, fmt.Sprintf("检测到视频流请求: itemID=%s", itemID), map[string]string{
					"item_id":    itemID,
					"path":       path,
					"client_ip":  r.RemoteAddr,
					"user_agent": r.Header.Get("User-Agent"),
				})
			}

			handled, errMsg := s.handleVideoStream(w, r, itemID)
			if handled {
				return
			}
			// 本地视频，直接代理
			if errMsg == "_LOCAL_" {
				if s.logger != nil {
					s.logger.LogEmby(model.LogCategoryNormal, model.LogLevelInfo, fmt.Sprintf("本地视频直接代理: itemID=%s", itemID), map[string]string{
						"item_id":   itemID,
						"client_ip": r.RemoteAddr,
					})
				}
				s.safeProxy(w, r)
				return
			}
			if s.fallbackLocal {
				if s.logger != nil {
					s.logger.LogEmby(model.LogCategoryFail, model.LogLevelWarning, fmt.Sprintf("302失败回退本地代理: itemID=%s, 原因: %s", itemID, errMsg), map[string]string{
						"item_id": itemID,
						"error":   errMsg,
					})
				}
				s.safeProxy(w, r)
				return
			}
			if s.logger != nil {
				s.logger.LogEmby(model.LogCategoryError, model.LogLevelError, fmt.Sprintf("302跳转失败: itemID=%s, 原因: %s", itemID, errMsg), map[string]string{
					"item_id": itemID,
					"error":   errMsg,
				})
			}
			http.Error(w, fmt.Sprintf("获取直链失败: %s", errMsg), http.StatusBadGateway)
			return
		}
		// itemID为空，无法处理，直接代理
		if s.logger != nil {
			s.logger.LogEmby(model.LogCategoryNormal, model.LogLevelDebug, fmt.Sprintf("视频流请求但itemID为空，直接代理: %s", path), nil)
		}
		s.safeProxy(w, r)
		return
	}

	// 非视频流请求，直接代理
	s.safeProxy(w, r)
}

// handleVideoStream 处理视频流请求
// 返回 (handled, errMsg)：handled=true表示302跳转成功，errMsg为失败原因
func (s *EmbyProxyService) handleVideoStream(w http.ResponseWriter, r *http.Request, itemID string) (bool, string) {
	// 获取客户端UA（115直链与UA绑定，必须用播放器的UA获取直链）
	clientUA := r.Header.Get("User-Agent")
	if clientUA == "" {
		clientUA = s.driver115.GetUserAgent()
		if s.logger != nil {
			s.logger.LogEmby(model.LogCategoryNormal, model.LogLevelDebug, fmt.Sprintf("客户端未提供UA，使用默认UA: itemID=%s", itemID), nil)
		}
	}

	// 1. 获取媒体路径
	if s.logger != nil {
		s.logger.LogEmby(model.LogCategoryNormal, model.LogLevelDebug, fmt.Sprintf("开始获取媒体路径: itemID=%s", itemID), nil)
	}
	mediaPath, err := s.getMediaPath(itemID, r)
	if err != nil {
		if s.logger != nil {
			s.logger.LogEmby(model.LogCategoryError, model.LogLevelError, fmt.Sprintf("获取媒体路径失败: itemID=%s", itemID), map[string]string{
				"error": err.Error(),
			})
		}
		return false, err.Error()
	}
	if s.logger != nil {
		s.logger.LogEmby(model.LogCategoryNormal, model.LogLevelDebug, fmt.Sprintf("获取到媒体路径: itemID=%s, path=%s", itemID, filepath.Base(mediaPath)), map[string]string{
			"media_path": mediaPath,
		})
	}

	// 2. 处理STRM文件
	var cd2Path string
	if strings.HasSuffix(strings.ToLower(mediaPath), ".strm") {
		if s.logger != nil {
			s.logger.LogEmby(model.LogCategoryNormal, model.LogLevelDebug, fmt.Sprintf("检测到STRM文件，读取内容: %s", filepath.Base(mediaPath)), nil)
		}
		strmContent, err := s.readSTRMFile(mediaPath)
		if err != nil {
			if s.logger != nil {
				s.logger.LogEmby(model.LogCategoryError, model.LogLevelError, fmt.Sprintf("读取STRM文件失败: %s", filepath.Base(mediaPath)), map[string]string{
					"error":     err.Error(),
					"strm_path": mediaPath,
				})
			}
			return false, err.Error()
		}
		cd2Path = strings.TrimSpace(strmContent)
		if s.logger != nil {
			s.logger.LogEmby(model.LogCategoryNormal, model.LogLevelDebug, fmt.Sprintf("STRM文件内容: %s -> %s", filepath.Base(mediaPath), filepath.Base(cd2Path)), map[string]string{
				"cd2_path": cd2Path,
			})
		}
	} else {
		cd2Path = mediaPath
	}

	// 3. 检查是否是CD2路径
	if !s.isCD2Path(cd2Path) {
		if s.logger != nil {
			s.logger.LogEmby(model.LogCategoryNormal, model.LogLevelDebug, fmt.Sprintf("非CD2路径，走本地代理: %s", filepath.Base(cd2Path)), map[string]string{
				"path": cd2Path,
			})
		}
		return false, "_LOCAL_"
	}

	// 4. 查内存缓存
	cacheKey := cd2Path + "|" + clientUA
	if cached, ok := s.directURLCache.Load(cacheKey); ok {
		c := cached.(*cachedLink)
		if time.Now().Before(c.expiresAt) {
			if s.logger != nil {
				s.logger.LogEmby(model.LogCategorySuccess, model.LogLevelSuccess, fmt.Sprintf("302跳转成功(缓存命中): %s", filepath.Base(cd2Path)), map[string]string{
					"item_id":    itemID,
					"file_name":  filepath.Base(cd2Path),
					"client_ip":  r.RemoteAddr,
					"cache":      "hit",
					"expires_in": fmt.Sprintf("%.0f秒", time.Until(c.expiresAt).Seconds()),
				})
			}
			http.Redirect(w, r, c.url, http.StatusFound)
			return true, ""
		}
		if s.logger != nil {
			s.logger.LogEmby(model.LogCategoryNormal, model.LogLevelDebug, fmt.Sprintf("缓存已过期，重新获取直链: %s", filepath.Base(cd2Path)), nil)
		}
		s.directURLCache.Delete(cacheKey)
	}

	// 5. 查目录树获取pickcode
	if s.logger != nil {
		s.logger.LogEmby(model.LogCategoryNormal, model.LogLevelDebug, fmt.Sprintf("查询目录树获取pickcode: %s", filepath.Base(cd2Path)), map[string]string{
			"cd2_path": cd2Path,
		})
	}
	treeNode, _ := s.store.GetTreeNodeByMountPath(cd2Path)
	if treeNode == nil {
		stripped := s.stripMountPrefix(cd2Path)
		if s.logger != nil {
			s.logger.LogEmby(model.LogCategoryNormal, model.LogLevelDebug, fmt.Sprintf("挂载路径未匹配，尝试CD2路径查询: %s", stripped), nil)
		}
		treeNode, _ = s.store.GetTreeNodeByCD2Path(stripped)
	}

	if treeNode == nil || treeNode.PickCode == "" {
		errMsg := fmt.Sprintf("目录树未找到: %s", filepath.Base(cd2Path))
		if s.logger != nil {
			s.logger.LogEmby(model.LogCategoryFail, model.LogLevelWarning, errMsg, map[string]string{
				"cd2_path": cd2Path,
				"item_id":  itemID,
			})
		}
		return false, errMsg
	}

	if s.logger != nil {
		s.logger.LogEmby(model.LogCategoryNormal, model.LogLevelDebug, fmt.Sprintf("找到pickcode: %s -> %s", filepath.Base(cd2Path), treeNode.PickCode), map[string]string{
			"pickcode": treeNode.PickCode,
		})
	}

	// 6. 获取直链
	if s.logger != nil {
		s.logger.LogEmby(model.LogCategoryNormal, model.LogLevelDebug, fmt.Sprintf("开始获取115直链: pickcode=%s", treeNode.PickCode), map[string]string{
			"pickcode":   treeNode.PickCode,
			"user_agent": clientUA,
		})
	}
	info, err := s.driver115.GetDownloadURL(treeNode.PickCode, clientUA, false, "")
	if err != nil {
		if s.logger != nil {
			s.logger.LogEmby(model.LogCategoryFail, model.LogLevelWarning, fmt.Sprintf("获取115直链失败: %s", filepath.Base(cd2Path)), map[string]string{
				"error":    err.Error(),
				"pickcode": treeNode.PickCode,
				"item_id":  itemID,
			})
		}
		return false, fmt.Sprintf("获取直链失败: %v", err)
	}

	if info.URL == "" {
		if s.logger != nil {
			s.logger.LogEmby(model.LogCategoryFail, model.LogLevelWarning, fmt.Sprintf("获取到的直链为空: %s", filepath.Base(cd2Path)), map[string]string{
				"pickcode": treeNode.PickCode,
				"item_id":  itemID,
			})
		}
		return false, "获取到的直链为空"
	}

	// 7. 缓存直链
	expireAt := time.Now().Add(15 * time.Minute)
	s.directURLCache.Store(cacheKey, &cachedLink{
		url:       info.URL,
		userAgent: clientUA,
		expiresAt: expireAt,
	})

	if s.logger != nil {
		s.logger.LogEmby(model.LogCategorySuccess, model.LogLevelSuccess, fmt.Sprintf("302跳转成功: %s", filepath.Base(cd2Path)), map[string]string{
			"item_id":   itemID,
			"file_name": filepath.Base(cd2Path),
			"pickcode":  treeNode.PickCode,
			"client_ip": r.RemoteAddr,
			"cache":     "miss",
		})
	}

	// 8. 302重定向
	http.Redirect(w, r, info.URL, http.StatusFound)
	return true, ""
}

// readSTRMFile 读取STRM文件内容
func (s *EmbyProxyService) readSTRMFile(strmPath string) (string, error) {
	content, err := os.ReadFile(strmPath)
	if err != nil {
		return "", fmt.Errorf("读取STRM文件失败: %v", err)
	}
	return strings.TrimSpace(string(content)), nil
}

// isCD2Path 检查路径是否包含CD2挂载前缀
func (s *EmbyProxyService) isCD2Path(path string) bool {
	mountPrefixes := []string{
		"/CloudNAS/CloudDrive",
		"/CloudNAS",
		"/mnt/CloudDrive",
		"/mnt/clouddrive",
	}
	for _, prefix := range mountPrefixes {
		if strings.HasPrefix(path, prefix) {
			return true
		}
	}
	return false
}

// stripMountPrefix 去掉CD2挂载前缀+云盘名称，得到115内部路径
func (s *EmbyProxyService) stripMountPrefix(cd2Path string) string {
	mountPrefixes := []string{
		"/CloudNAS/CloudDrive",
		"/CloudNAS",
		"/mnt/CloudDrive",
		"/mnt/clouddrive",
	}

	stripped := cd2Path
	for _, prefix := range mountPrefixes {
		if strings.HasPrefix(stripped, prefix) {
			stripped = strings.TrimPrefix(stripped, prefix)
			break
		}
	}

	if s.cloudName != "" {
		cloudPrefix := "/" + s.cloudName
		if strings.HasPrefix(stripped, cloudPrefix) {
			stripped = strings.TrimPrefix(stripped, cloudPrefix)
		}
	}

	if stripped != cd2Path {
		if s.logger != nil {
			s.logger.LogEmby(model.LogCategoryNormal, model.LogLevelDebug, fmt.Sprintf("路径转换: %s -> %s", cd2Path, stripped), nil)
		}
		s.debugLog("[EmbyProxy] 路径转换: %s -> %s\n", cd2Path, stripped)
	}
	return stripped
}

// getMediaPath 获取媒体文件路径
func (s *EmbyProxyService) getMediaPath(itemID string, r *http.Request) (string, error) {
	embyHost := s.embyURL.String()

	apiKey := s.embyAPIKey
	if apiKey == "" {
		apiKey = r.URL.Query().Get("api_key")
	}
	if apiKey == "" {
		apiKey = r.URL.Query().Get("X-Emby-Token")
	}
	if apiKey == "" {
		if auth := r.Header.Get("X-Emby-Authorization"); auth != "" {
			if idx := strings.Index(auth, "Token=\""); idx != -1 {
				start := idx + 7
				end := strings.Index(auth[start:], "\"")
				if end != -1 {
					apiKey = auth[start : start+end]
				}
			}
		}
	}

	if apiKey == "" {
		if s.logger != nil {
			s.logger.LogEmby(model.LogCategoryFail, model.LogLevelWarning, fmt.Sprintf("未找到API Key: itemID=%s", itemID), map[string]string{
				"item_id": itemID,
			})
		}
	}

	apiURL := fmt.Sprintf("%s/emby/Items?Ids=%s&Fields=Path,MediaSources&api_key=%s", embyHost, itemID, apiKey)
	s.debugLog("[EmbyProxy] 获取媒体信息: %s\n", apiURL)

	if s.logger != nil {
		s.logger.LogEmby(model.LogCategoryNormal, model.LogLevelDebug, fmt.Sprintf("调用Emby API获取媒体信息: itemID=%s", itemID), nil)
	}

	path, err := s.tryGetMediaPath(apiURL, r)
	if err == nil && path != "" {
		return path, nil
	}

	return "", fmt.Errorf("获取媒体路径失败: %v", err)
}

// tryGetMediaPath 尝试从指定URL获取媒体路径
func (s *EmbyProxyService) tryGetMediaPath(apiURL string, r *http.Request) (string, error) {
	req, err := http.NewRequest("GET", apiURL, nil)
	if err != nil {
		return "", err
	}

	if s.embyAPIKey != "" {
		req.Header.Set("X-Emby-Token", s.embyAPIKey)
	}
	if auth := r.Header.Get("X-Emby-Authorization"); auth != "" {
		req.Header.Set("X-Emby-Authorization", auth)
	}

	client := &http.Client{Timeout: 10 * time.Second}
	resp, err := client.Do(req)
	if err != nil {
		if s.logger != nil {
			s.logger.LogEmby(model.LogCategoryError, model.LogLevelError, fmt.Sprintf("请求Emby API失败: %v", err), map[string]string{
				"error": err.Error(),
			})
		}
		return "", err
	}
	defer resp.Body.Close()

	if resp.StatusCode != http.StatusOK {
		if s.logger != nil {
			s.logger.LogEmby(model.LogCategoryError, model.LogLevelError, fmt.Sprintf("Emby API返回异常状态码: %d", resp.StatusCode), map[string]string{
				"status_code": fmt.Sprintf("%d", resp.StatusCode),
			})
		}
		return "", fmt.Errorf("Emby API返回: %d", resp.StatusCode)
	}

	body, err := io.ReadAll(resp.Body)
	if err != nil {
		return "", err
	}

	// 尝试解析为Items列表响应
	var listResult struct {
		Items []struct {
			Path         string `json:"Path"`
			MediaSources []struct {
				Path string `json:"Path"`
			} `json:"MediaSources"`
		} `json:"Items"`
	}

	if err := json.Unmarshal(body, &listResult); err == nil && len(listResult.Items) > 0 {
		item := listResult.Items[0]
		if len(item.MediaSources) > 0 && item.MediaSources[0].Path != "" {
			s.debugLog("[EmbyProxy] 从Items列表获取路径: %s\n", item.MediaSources[0].Path)
			return item.MediaSources[0].Path, nil
		}
		if item.Path != "" {
			s.debugLog("[EmbyProxy] 从Items列表获取路径: %s\n", item.Path)
			return item.Path, nil
		}
	}

	// 尝试解析为单个Item响应
	var singleResult struct {
		Path         string `json:"Path"`
		MediaSources []struct {
			Path string `json:"Path"`
		} `json:"MediaSources"`
	}

	if err := json.Unmarshal(body, &singleResult); err != nil {
		if s.logger != nil {
			s.logger.LogEmby(model.LogCategoryError, model.LogLevelError, fmt.Sprintf("解析Emby API响应失败: %v", err), map[string]string{
				"error": err.Error(),
			})
		}
		fmt.Printf("[EmbyProxy] 解析响应失败: %v, body: %s\n", err, string(body))
		return "", err
	}

	if len(singleResult.MediaSources) > 0 && singleResult.MediaSources[0].Path != "" {
		return singleResult.MediaSources[0].Path, nil
	}

	return singleResult.Path, nil
}

// ==================== Emby 辅助功能 ====================

// SearchMediaByName 根据文件名搜索Emby媒体并返回封面图
func (s *EmbyProxyService) SearchMediaByName(fileName string) (string, error) {
	if s.embyURL == nil {
		return "", fmt.Errorf("Emby未配置")
	}

	embyHost := s.embyURL.String()
	apiKey := s.embyAPIKey

	name := strings.TrimSuffix(fileName, filepath.Ext(fileName))

	if s.logger != nil {
		s.logger.LogEmby(model.LogCategoryNormal, model.LogLevelDebug, fmt.Sprintf("搜索Emby媒体: %s", name), nil)
	}

	searchURL := fmt.Sprintf("%s/emby/Items?SearchTerm=%s&Recursive=true&IncludeItemTypes=Movie,Series,Episode&Fields=PrimaryImageAspectRatio&Limit=1&api_key=%s",
		embyHost, url.QueryEscape(name), apiKey)

	req, err := http.NewRequest("GET", searchURL, nil)
	if err != nil {
		return "", err
	}
	if apiKey != "" {
		req.Header.Set("X-Emby-Token", apiKey)
	}

	client := &http.Client{Timeout: 10 * time.Second}
	resp, err := client.Do(req)
	if err != nil {
		if s.logger != nil {
			s.logger.LogEmby(model.LogCategoryError, model.LogLevelError, fmt.Sprintf("搜索Emby媒体请求失败: %s", name), map[string]string{
				"error": err.Error(),
			})
		}
		return "", err
	}
	defer resp.Body.Close()

	if resp.StatusCode != http.StatusOK {
		return "", fmt.Errorf("搜索失败: %d", resp.StatusCode)
	}

	body, err := io.ReadAll(resp.Body)
	if err != nil {
		return "", err
	}

	var result struct {
		Items []struct {
			ID        string            `json:"Id"`
			Name      string            `json:"Name"`
			ImageTags map[string]string `json:"ImageTags"`
		} `json:"Items"`
	}

	if err := json.Unmarshal(body, &result); err != nil {
		return "", err
	}

	if len(result.Items) == 0 {
		if s.logger != nil {
			s.logger.LogEmby(model.LogCategoryNormal, model.LogLevelDebug, fmt.Sprintf("搜索Emby媒体无结果: %s", name), nil)
		}
		return "", nil
	}

	item := result.Items[0]
	if _, ok := item.ImageTags["Primary"]; ok {
		posterURL := fmt.Sprintf("%s/emby/Items/%s/Images/Primary?api_key=%s", embyHost, item.ID, apiKey)
		if s.logger != nil {
			s.logger.LogEmby(model.LogCategorySuccess, model.LogLevelDebug, fmt.Sprintf("搜索Emby媒体命中: %s -> %s", name, item.Name), nil)
		}
		return posterURL, nil
	}

	return "", nil
}

// RefreshLibrary 通知Emby刷新媒体库
func (s *EmbyProxyService) RefreshLibrary() error {
	if s.embyURL == nil {
		return fmt.Errorf("Emby未配置")
	}

	embyHost := s.embyURL.String()
	apiKey := s.embyAPIKey

	if s.logger != nil {
		s.logger.LogEmby(model.LogCategoryNormal, model.LogLevelInfo, "开始通知Emby刷新媒体库", nil)
	}

	refreshURL := fmt.Sprintf("%s/emby/Library/Refresh?api_key=%s", embyHost, apiKey)

	req, err := http.NewRequest("POST", refreshURL, nil)
	if err != nil {
		return err
	}
	if apiKey != "" {
		req.Header.Set("X-Emby-Token", apiKey)
	}

	httpClient := &http.Client{Timeout: 30 * time.Second}
	resp, err := httpClient.Do(req)
	if err != nil {
		if s.logger != nil {
			s.logger.LogEmby(model.LogCategoryError, model.LogLevelError, fmt.Sprintf("刷新媒体库请求失败: %v", err), map[string]string{
				"error": err.Error(),
			})
		}
		return fmt.Errorf("刷新媒体库失败: %v", err)
	}
	defer resp.Body.Close()

	if resp.StatusCode != http.StatusOK && resp.StatusCode != http.StatusNoContent {
		if s.logger != nil {
			s.logger.LogEmby(model.LogCategoryError, model.LogLevelError, fmt.Sprintf("刷新媒体库返回异常: %d", resp.StatusCode), map[string]string{
				"status_code": fmt.Sprintf("%d", resp.StatusCode),
			})
		}
		return fmt.Errorf("刷新媒体库返回: %d", resp.StatusCode)
	}

	fmt.Printf("[EmbyProxy] 已通知Emby刷新媒体库\n")
	if s.logger != nil {
		s.logger.LogEmby(model.LogCategorySuccess, model.LogLevelSuccess, "已通知Emby刷新媒体库", nil)
	}
	return nil
}

// RefreshLibraryPath 通知Emby刷新指定路径
func (s *EmbyProxyService) RefreshLibraryPath(path string) error {
	if s == nil || s.embyURL == nil {
		return nil
	}

	embyHost := s.embyURL.String()
	apiKey := s.embyAPIKey

	if s.logger != nil {
		s.logger.LogEmby(model.LogCategoryNormal, model.LogLevelInfo, fmt.Sprintf("开始通知Emby刷新路径: %s", path), nil)
	}

	refreshURL := fmt.Sprintf("%s/emby/Library/Media/Updated?api_key=%s&Path=%s",
		embyHost, apiKey, url.QueryEscape(path))

	req, err := http.NewRequest("POST", refreshURL, nil)
	if err != nil {
		return err
	}
	if apiKey != "" {
		req.Header.Set("X-Emby-Token", apiKey)
	}

	httpClient := &http.Client{Timeout: 30 * time.Second}
	resp, err := httpClient.Do(req)
	if err != nil {
		if s.logger != nil {
			s.logger.LogEmby(model.LogCategoryError, model.LogLevelError, fmt.Sprintf("刷新路径请求失败: %s", path), map[string]string{
				"error": err.Error(),
				"path":  path,
			})
		}
		return fmt.Errorf("刷新路径失败: %v", err)
	}
	defer resp.Body.Close()

	if resp.StatusCode != http.StatusOK && resp.StatusCode != http.StatusNoContent {
		if s.logger != nil {
			s.logger.LogEmby(model.LogCategoryError, model.LogLevelError, fmt.Sprintf("刷新路径返回异常: %d, path=%s", resp.StatusCode, path), map[string]string{
				"status_code": fmt.Sprintf("%d", resp.StatusCode),
				"path":        path,
			})
		}
	}

	fmt.Printf("[EmbyProxy] 已通知Emby刷新路径: %s\n", path)
	if s.logger != nil {
		s.logger.LogEmby(model.LogCategorySuccess, model.LogLevelSuccess, fmt.Sprintf("已通知Emby刷新路径: %s", path), nil)
	}
	return nil
}

// ==================== Emby 统计 ====================

// EmbyStats Emby统计信息
type EmbyStats struct {
	MovieCount   int    `json:"movie_count"`
	SeriesCount  int    `json:"series_count"`
	EpisodeCount int    `json:"episode_count"`
	PlayingCount int    `json:"playing_count"`
	RecentCount  int    `json:"recent_count"`
	ServerID     string `json:"server_id"`
}

// GetStats 获取Emby统计信息
func (s *EmbyProxyService) GetStats() (*EmbyStats, error) {
	if s.embyURL == nil {
		return nil, fmt.Errorf("Emby未配置")
	}

	if s.logger != nil {
		s.logger.LogEmby(model.LogCategoryNormal, model.LogLevelDebug, "开始获取Emby统计信息", nil)
	}

	stats := &EmbyStats{}
	embyHost := s.embyURL.String()
	apiKey := s.embyAPIKey

	serverInfoURL := fmt.Sprintf("%s/emby/System/Info/Public", embyHost)
	if serverInfo, err := s.fetchServerInfo(serverInfoURL); err == nil {
		stats.ServerID = serverInfo.ID
	} else if s.logger != nil {
		s.logger.LogEmby(model.LogCategoryFail, model.LogLevelWarning, fmt.Sprintf("获取Emby服务器信息失败: %v", err), nil)
	}

	movieURL := fmt.Sprintf("%s/emby/Items/Counts?api_key=%s", embyHost, apiKey)
	if counts, err := s.fetchItemCounts(movieURL); err == nil {
		stats.MovieCount = counts.MovieCount
		stats.SeriesCount = counts.SeriesCount
		stats.EpisodeCount = counts.EpisodeCount
	} else if s.logger != nil {
		s.logger.LogEmby(model.LogCategoryFail, model.LogLevelWarning, fmt.Sprintf("获取Emby媒体数量失败: %v", err), nil)
	}

	sessionsURL := fmt.Sprintf("%s/emby/Sessions?api_key=%s", embyHost, apiKey)
	if sessions, err := s.fetchSessions(sessionsURL); err == nil {
		for _, session := range sessions {
			if session.NowPlayingItem != nil {
				stats.PlayingCount++
			}
		}
	} else if s.logger != nil {
		s.logger.LogEmby(model.LogCategoryFail, model.LogLevelWarning, fmt.Sprintf("获取Emby会话信息失败: %v", err), nil)
	}

	stats.RecentCount = 0

	if s.logger != nil {
		s.logger.LogEmby(model.LogCategoryNormal, model.LogLevelDebug, fmt.Sprintf("Emby统计: 电影=%d, 剧集=%d, 集数=%d, 播放中=%d", stats.MovieCount, stats.SeriesCount, stats.EpisodeCount, stats.PlayingCount), nil)
	}

	return stats, nil
}

type serverInfo struct {
	ID string `json:"Id"`
}

func (s *EmbyProxyService) fetchServerInfo(apiURL string) (*serverInfo, error) {
	req, _ := http.NewRequest("GET", apiURL, nil)

	httpClient := &http.Client{Timeout: 10 * time.Second}
	resp, err := httpClient.Do(req)
	if err != nil {
		return nil, err
	}
	defer resp.Body.Close()

	var info serverInfo
	if err := json.NewDecoder(resp.Body).Decode(&info); err != nil {
		return nil, err
	}
	return &info, nil
}

type itemCounts struct {
	MovieCount   int `json:"MovieCount"`
	SeriesCount  int `json:"SeriesCount"`
	EpisodeCount int `json:"EpisodeCount"`
}

func (s *EmbyProxyService) fetchItemCounts(apiURL string) (*itemCounts, error) {
	req, _ := http.NewRequest("GET", apiURL, nil)
	if s.embyAPIKey != "" {
		req.Header.Set("X-Emby-Token", s.embyAPIKey)
	}

	httpClient := &http.Client{Timeout: 10 * time.Second}
	resp, err := httpClient.Do(req)
	if err != nil {
		return nil, err
	}
	defer resp.Body.Close()

	var counts itemCounts
	if err := json.NewDecoder(resp.Body).Decode(&counts); err != nil {
		return nil, err
	}
	return &counts, nil
}

type embySession struct {
	NowPlayingItem *struct {
		Name string `json:"Name"`
		Type string `json:"Type"`
	} `json:"NowPlayingItem"`
	UserName string `json:"UserName"`
}

func (s *EmbyProxyService) fetchSessions(apiURL string) ([]embySession, error) {
	req, _ := http.NewRequest("GET", apiURL, nil)
	if s.embyAPIKey != "" {
		req.Header.Set("X-Emby-Token", s.embyAPIKey)
	}

	httpClient := &http.Client{Timeout: 10 * time.Second}
	resp, err := httpClient.Do(req)
	if err != nil {
		return nil, err
	}
	defer resp.Body.Close()

	var sessions []embySession
	if err := json.NewDecoder(resp.Body).Decode(&sessions); err != nil {
		return nil, err
	}
	return sessions, nil
}

// ==================== Emby 媒体查询 ====================

// MediaItem 媒体项
type MediaItem struct {
	ID       string `json:"id"`
	Name     string `json:"name"`
	Type     string `json:"type"`
	Year     int    `json:"year"`
	Poster   string `json:"poster"`
	Overview string `json:"overview"`
}

// GetRecentItems 获取最近入库的媒体
func (s *EmbyProxyService) GetRecentItems(limit int) ([]MediaItem, error) {
	if s.embyURL == nil {
		return nil, fmt.Errorf("Emby未配置")
	}

	embyHost := s.embyURL.String()
	apiKey := s.embyAPIKey

	apiURL := fmt.Sprintf("%s/emby/Items/Latest?Limit=%d&IncludeItemTypes=Movie,Series&api_key=%s",
		embyHost, limit, apiKey)

	return s.fetchMediaItems(apiURL)
}

// GetRandomItems 获取随机媒体
func (s *EmbyProxyService) GetRandomItems(limit int) ([]MediaItem, error) {
	if s.embyURL == nil {
		return nil, fmt.Errorf("Emby未配置")
	}

	embyHost := s.embyURL.String()
	apiKey := s.embyAPIKey

	apiURL := fmt.Sprintf("%s/emby/Items?SortBy=Random&Limit=%d&Recursive=true&IncludeItemTypes=Movie,Series&api_key=%s",
		embyHost, limit, apiKey)

	return s.fetchMediaItemsFromSearch(apiURL)
}

// GetPopularItems 获取热门媒体
func (s *EmbyProxyService) GetPopularItems(limit int) ([]MediaItem, error) {
	if s.embyURL == nil {
		return nil, fmt.Errorf("Emby未配置")
	}

	embyHost := s.embyURL.String()
	apiKey := s.embyAPIKey

	apiURL := fmt.Sprintf("%s/emby/Items?SortBy=PlayCount&SortOrder=Descending&Limit=%d&Recursive=true&IncludeItemTypes=Movie,Series&api_key=%s",
		embyHost, limit, apiKey)

	return s.fetchMediaItemsFromSearch(apiURL)
}

// GetPlayingSessions 获取正在播放的会话
func (s *EmbyProxyService) GetPlayingSessions() ([]map[string]interface{}, error) {
	if s.embyURL == nil {
		return nil, fmt.Errorf("Emby未配置")
	}

	embyHost := s.embyURL.String()
	apiKey := s.embyAPIKey

	apiURL := fmt.Sprintf("%s/emby/Sessions?api_key=%s", embyHost, apiKey)

	req, _ := http.NewRequest("GET", apiURL, nil)
	if apiKey != "" {
		req.Header.Set("X-Emby-Token", apiKey)
	}

	httpClient := &http.Client{Timeout: 10 * time.Second}
	resp, err := httpClient.Do(req)
	if err != nil {
		return nil, err
	}
	defer resp.Body.Close()

	var sessions []map[string]interface{}
	if err := json.NewDecoder(resp.Body).Decode(&sessions); err != nil {
		return nil, err
	}

	var playing []map[string]interface{}
	for _, session := range sessions {
		if session["NowPlayingItem"] != nil {
			item := session["NowPlayingItem"].(map[string]interface{})
			playing = append(playing, map[string]interface{}{
				"user":     session["UserName"],
				"device":   session["DeviceName"],
				"client":   session["Client"],
				"title":    item["Name"],
				"type":     item["Type"],
				"progress": session["PlayState"],
			})
		}
	}

	return playing, nil
}

func (s *EmbyProxyService) fetchMediaItems(apiURL string) ([]MediaItem, error) {
	req, _ := http.NewRequest("GET", apiURL, nil)
	if s.embyAPIKey != "" {
		req.Header.Set("X-Emby-Token", s.embyAPIKey)
	}

	httpClient := &http.Client{Timeout: 10 * time.Second}
	resp, err := httpClient.Do(req)
	if err != nil {
		return nil, err
	}
	defer resp.Body.Close()

	var items []struct {
		ID             string `json:"Id"`
		Name           string `json:"Name"`
		Type           string `json:"Type"`
		ProductionYear int    `json:"ProductionYear"`
	}

	if err := json.NewDecoder(resp.Body).Decode(&items); err != nil {
		return nil, err
	}

	embyHost := s.embyURL.String()
	apiKey := s.embyAPIKey

	var result []MediaItem
	for _, item := range items {
		result = append(result, MediaItem{
			ID:     item.ID,
			Name:   item.Name,
			Type:   item.Type,
			Year:   item.ProductionYear,
			Poster: fmt.Sprintf("%s/emby/Items/%s/Images/Primary?api_key=%s", embyHost, item.ID, apiKey),
		})
	}

	return result, nil
}

func (s *EmbyProxyService) fetchMediaItemsFromSearch(apiURL string) ([]MediaItem, error) {
	req, _ := http.NewRequest("GET", apiURL, nil)
	if s.embyAPIKey != "" {
		req.Header.Set("X-Emby-Token", s.embyAPIKey)
	}

	httpClient := &http.Client{Timeout: 10 * time.Second}
	resp, err := httpClient.Do(req)
	if err != nil {
		return nil, err
	}
	defer resp.Body.Close()

	var result struct {
		Items []struct {
			ID             string `json:"Id"`
			Name           string `json:"Name"`
			Type           string `json:"Type"`
			ProductionYear int    `json:"ProductionYear"`
		} `json:"Items"`
	}

	if err := json.NewDecoder(resp.Body).Decode(&result); err != nil {
		return nil, err
	}

	embyHost := s.embyURL.String()
	apiKey := s.embyAPIKey

	var items []MediaItem
	for _, item := range result.Items {
		items = append(items, MediaItem{
			ID:     item.ID,
			Name:   item.Name,
			Type:   item.Type,
			Year:   item.ProductionYear,
			Poster: fmt.Sprintf("%s/emby/Items/%s/Images/Primary?api_key=%s", embyHost, item.ID, apiKey),
		})
	}

	return items, nil
}
