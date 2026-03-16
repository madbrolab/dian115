package client

import (
	"bytes"
	"crypto/sha1"
	"encoding/json"
	"fmt"
	"io"
	"net/http"
	"net/url"
	"os"
	"path/filepath"
	"strconv"
	"strings"
	"sync"
	"time"

	"strm-manager/internal/model"
)

// Driver115Client 115客户端
type Driver115Client struct {
	cookie          string
	userAgent       string
	client          *http.Client
	mu              sync.RWMutex
	stableOnce      sync.Once
	stablePoint     string
	stableErr       error
	dirPathCache    sync.Map       // 目录路径 → cid 缓存
	debug           bool           // 是否输出详细日志
	onCookieExpired func()         // Cookie失效回调
	rateLimiter     chan time.Time // 令牌桶限流器
	rateQPS         int            // 当前QPS限制
	rateMu          sync.Mutex     // 限流器锁
}

// ErrCookieExpired Cookie已过期错误
var ErrCookieExpired = fmt.Errorf("cookie已过期或无效")

// SetOnCookieExpired 设置Cookie失效回调
func (c *Driver115Client) SetOnCookieExpired(fn func()) {
	c.onCookieExpired = fn
}

// notifyCookieExpired 触发Cookie失效回调
func (c *Driver115Client) notifyCookieExpired() {
	if c.onCookieExpired != nil {
		go c.onCookieExpired()
	}
}

// isCookieExpiredError 判断API响应是否表示Cookie已过期
func isCookieExpiredError(body []byte, statusCode int) bool {
	if statusCode == 401 || statusCode == 403 {
		return true
	}
	// 115 API 返回 state=false 且 errcode 为登录相关
	var resp struct {
		State   bool   `json:"state"`
		Errcode int    `json:"errcode"`
		Error   string `json:"error"`
		Errno   int    `json:"errno"`
	}
	if json.Unmarshal(body, &resp) == nil {
		// errcode 99999 = 未登录; errno 990001/990002 = 登录过期
		if resp.Errcode == 99999 || resp.Errno == 990001 || resp.Errno == 990002 {
			return true
		}
		if !resp.State && (strings.Contains(resp.Error, "登录") || strings.Contains(resp.Error, "login")) {
			return true
		}
	}
	return false
}

// ssoentToApp 将 ssoent 映射为 app 名称（参考 p115client APP_TO_SSOENT）
var ssoentToApp = map[string]string{
	"A1": "web",
	"D1": "ios",
	"D2": "bios",
	"D3": "115ios",
	"F1": "android",
	"F2": "bandroid",
	"F3": "115android",
	"H1": "ipad",
	"H2": "bipad",
	"H3": "115ipad",
	"I1": "tv",
	"I2": "apple_tv",
	"M1": "qandroid",
	"N1": "qios",
	"O1": "qipad",
	"P1": "os_windows",
	"P2": "os_mac",
	"P3": "os_linux",
	"R1": "wechatmini",
	"R2": "alipaymini",
	"S1": "harmony",
}

// getAppType 从 Cookie 的 UID 字段解析 app 类型（参考 p115client）
// UID 格式: {user_id}_{ssoent}_{timestamp}，例如 343973593_F1_1710000000
// ssoent 通过 SSOENT_TO_APP 映射为 app 名称
func (c *Driver115Client) getAppType() string {
	// 从 cookie 中提取 UID
	for _, part := range strings.Split(c.cookie, ";") {
		part = strings.TrimSpace(part)
		if strings.HasPrefix(part, "UID=") {
			uid := strings.TrimPrefix(part, "UID=")
			// UID 格式: user_id_ssoent_timestamp
			parts := strings.SplitN(uid, "_", 3)
			if len(parts) >= 2 {
				ssoent := parts[1]
				if app, ok := ssoentToApp[ssoent]; ok {
					return app
				}
			}
			break
		}
	}
	// 默认 android
	return "android"
}

// getProAPIPrefix 获取 proapi URL 前缀（根据app类型）
// 参考 p115client 的 complete_url + download_folders_app 逻辑：
// chrome 类型: /app/chrome/downfolders
// os_windows/os_mac/os_linux/windows/mac/linux: /{app}/ufile/downfolders
// 其他所有 app: 强制用 os_windows → /os_windows/ufile/downfolders
func (c *Driver115Client) getProAPIPrefix() (folderURL, fileURL string) {
	app := c.getAppType()
	switch app {
	case "web", "desktop":
		folderURL = "https://proapi.115.com/app/chrome/downfolders"
		fileURL = "https://proapi.115.com/app/chrome/downfiles"
	case "windows":
		app = "os_windows"
		folderURL = fmt.Sprintf("https://proapi.115.com/%s/ufile/downfolders", app)
		fileURL = fmt.Sprintf("https://proapi.115.com/%s/ufile/downfiles", app)
	case "mac":
		app = "os_mac"
		folderURL = fmt.Sprintf("https://proapi.115.com/%s/ufile/downfolders", app)
		fileURL = fmt.Sprintf("https://proapi.115.com/%s/ufile/downfiles", app)
	case "linux":
		app = "os_linux"
		folderURL = fmt.Sprintf("https://proapi.115.com/%s/ufile/downfolders", app)
		fileURL = fmt.Sprintf("https://proapi.115.com/%s/ufile/downfiles", app)
	case "os_windows", "os_mac", "os_linux":
		folderURL = fmt.Sprintf("https://proapi.115.com/%s/ufile/downfolders", app)
		fileURL = fmt.Sprintf("https://proapi.115.com/%s/ufile/downfiles", app)
	default:
		// 其他所有 app（android/ios/alipaymini等）强制用 os_windows
		folderURL = "https://proapi.115.com/os_windows/ufile/downfolders"
		fileURL = "https://proapi.115.com/os_windows/ufile/downfiles"
	}
	return
}

// SetDebug 设置是否输出详细日志
func (c *Driver115Client) SetDebug(debug bool) {
	c.debug = debug
}

// debugLog 仅在debug模式下输出日志
func (c *Driver115Client) debugLog(format string, args ...interface{}) {
	if c.debug {
		fmt.Printf(format, args...)
	}
}

// NewDriver115Client 创建115客户端
func NewDriver115Client(cookie, userAgent string) *Driver115Client {
	if userAgent == "" {
		userAgent = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
	}
	c := &Driver115Client{
		cookie:    cookie,
		userAgent: userAgent,
		client: &http.Client{
			Timeout: 30 * time.Second,
			CheckRedirect: func(req *http.Request, via []*http.Request) error {
				return http.ErrUseLastResponse
			},
		},
		rateQPS: 5, // 默认5 QPS
	}
	c.initRateLimiter(5)
	return c
}

// initRateLimiter 初始化令牌桶限流器
func (c *Driver115Client) initRateLimiter(qps int) {
	if qps <= 0 {
		qps = 5
	}
	if qps > 50 {
		qps = 50
	}
	c.rateLimiter = make(chan time.Time, qps)
	// 预填满令牌
	for i := 0; i < qps; i++ {
		c.rateLimiter <- time.Now()
	}
	// 后台定时补充令牌
	go func() {
		interval := time.Second / time.Duration(qps)
		ticker := time.NewTicker(interval)
		defer ticker.Stop()
		for t := range ticker.C {
			select {
			case c.rateLimiter <- t:
			default: // 桶满了，丢弃
			}
		}
	}()
}

// SetRateLimit 设置QPS限制（动态调整）
func (c *Driver115Client) SetRateLimit(qps int) {
	c.rateMu.Lock()
	defer c.rateMu.Unlock()
	if qps == c.rateQPS {
		return
	}
	c.rateQPS = qps
	c.initRateLimiter(qps)
	if c.debug {
		fmt.Printf("[115API] QPS限制已调整为: %d\n", qps)
	}
}

// GetRateLimit 获取当前QPS限制
func (c *Driver115Client) GetRateLimit() int {
	c.rateMu.Lock()
	defer c.rateMu.Unlock()
	return c.rateQPS
}

// waitRateLimit 等待令牌（在发起API请求前调用）
func (c *Driver115Client) waitRateLimit() {
	<-c.rateLimiter
}

// doRequest 发起HTTP请求（带限流和405自动退避重试）
func (c *Driver115Client) doRequest(req *http.Request) (*http.Response, error) {
	c.waitRateLimit()

	// 保存请求体用于重试
	var bodyBytes []byte
	if req.Body != nil {
		bodyBytes, _ = io.ReadAll(req.Body)
		req.Body = io.NopCloser(bytes.NewReader(bodyBytes))
	}

	maxRetries := 3
	for attempt := 0; attempt <= maxRetries; attempt++ {
		if attempt > 0 && bodyBytes != nil {
			req.Body = io.NopCloser(bytes.NewReader(bodyBytes))
		}

		resp, err := c.client.Do(req)
		if err != nil {
			return nil, err
		}

		if resp.StatusCode == 405 || resp.StatusCode == 429 || resp.StatusCode == 503 {
			resp.Body.Close()
			if attempt < maxRetries {
				waitSec := (attempt + 1) * 30 // 30s, 60s, 90s
				c.debugLog("[115API] 收到%d限流，等待%d秒后重试 (第%d次)\n", resp.StatusCode, waitSec, attempt+1)
				time.Sleep(time.Duration(waitSec) * time.Second)
				c.waitRateLimit()
				continue
			}
			return nil, fmt.Errorf("API限流(HTTP %d)，已重试%d次仍失败", resp.StatusCode, maxRetries)
		}

		return resp, nil
	}
	return nil, fmt.Errorf("请求失败：超过最大重试次数")
}

// SetCookie 设置Cookie
func (c *Driver115Client) SetCookie(cookie string) {
	c.mu.Lock()
	defer c.mu.Unlock()
	c.cookie = cookie
}

// SetUserAgent 设置User-Agent
func (c *Driver115Client) SetUserAgent(ua string) {
	c.mu.Lock()
	defer c.mu.Unlock()
	if ua != "" {
		c.userAgent = ua
	}
}

// GetUserAgent 获取User-Agent
func (c *Driver115Client) GetUserAgent() string {
	c.mu.RLock()
	defer c.mu.RUnlock()
	return c.userAgent
}

// GetCookie 获取Cookie
func (c *Driver115Client) GetCookie() string {
	c.mu.RLock()
	defer c.mu.RUnlock()
	return c.cookie
}

// getPickcodeStablePoint 获取并缓存稳定点
func (c *Driver115Client) getPickcodeStablePoint() (string, error) {
	c.stableOnce.Do(func() {
		sp, err := c.fetchPickcodeStablePoint()
		if err != nil {
			c.stableErr = err
			return
		}
		c.stablePoint = sp
	})
	if c.stableErr != nil {
		return "", c.stableErr
	}
	if c.stablePoint == "" {
		return "", fmt.Errorf("稳定点为空")
	}
	return c.stablePoint, nil
}

func (c *Driver115Client) fetchPickcodeStablePoint() (string, error) {
	info, err := c.getAnyPickcodeFromRoot()
	if err != nil {
		return "", err
	}
	sp := p115GetStablePoint(info)
	if sp == "" {
		return "", fmt.Errorf("无法解析稳定点")
	}
	return sp, nil
}

func (c *Driver115Client) getAnyPickcodeFromRoot() (string, error) {
	files, err := c.listDir("0")
	if err != nil {
		return "", err
	}
	for _, f := range files {
		if f.PickCode != "" {
			return f.PickCode, nil
		}
	}
	return "", fmt.Errorf("未找到可用的pickcode")
}

// ==================== 扫码登录 ====================

// GetQRCode 获取登录二维码（token始终使用web端点）
func (c *Driver115Client) GetQRCode(app string) (*model.QRCodeInfo, error) {
	if app == "" {
		app = "ios"
	}
	// 注意：token和qrcode端点始终使用web，与p115client一致
	apiURL := "https://qrcodeapi.115.com/api/1.0/web/1.0/token"

	req, err := http.NewRequest("GET", apiURL, nil)
	if err != nil {
		return nil, err
	}
	req.Header.Set("User-Agent", c.userAgent)

	resp, err := c.doRequest(req)
	if err != nil {
		return nil, err
	}
	defer resp.Body.Close()

	body, err := io.ReadAll(resp.Body)
	if err != nil {
		return nil, err
	}

	var result struct {
		State int `json:"state"`
		Data  struct {
			UID  string `json:"uid"`
			Sign string `json:"sign"`
			Time int64  `json:"time"`
		} `json:"data"`
	}

	if err := json.Unmarshal(body, &result); err != nil {
		return nil, err
	}

	if result.State != 1 {
		return nil, fmt.Errorf("获取二维码失败")
	}

	// 二维码URL也始终使用web
	qrcodeURL := fmt.Sprintf("https://qrcodeapi.115.com/api/1.0/web/1.0/qrcode?uid=%s", result.Data.UID)

	return &model.QRCodeInfo{
		UID:    result.Data.UID,
		Sign:   result.Data.Sign,
		Time:   result.Data.Time,
		QRCode: qrcodeURL,
		Status: 0,
	}, nil
}

// CheckQRCodeStatus 检查扫码状态（状态端点始终使用web）
// 返回: 0=等待扫码, 1=已扫码待确认, 2=已确认登录成功
func (c *Driver115Client) CheckQRCodeStatus(uid string, app string) (int, error) {
	// 状态检查始终使用web端点，与p115client一致
	apiURL := fmt.Sprintf("https://qrcodeapi.115.com/api/1.0/web/1.0/status?uid=%s&_=%d", uid, time.Now().UnixMilli())

	req, err := http.NewRequest("GET", apiURL, nil)
	if err != nil {
		return -1, err
	}
	req.Header.Set("User-Agent", c.userAgent)

	resp, err := c.doRequest(req)
	if err != nil {
		return -1, err
	}
	defer resp.Body.Close()

	body, err := io.ReadAll(resp.Body)
	if err != nil {
		return -1, err
	}

	var result struct {
		State   bool   `json:"state"`
		Code    int    `json:"code"`
		Message string `json:"message"`
		Key     string `json:"key"`
	}

	if err := json.Unmarshal(body, &result); err != nil {
		return -1, fmt.Errorf("解析响应失败: %v, body: %s", err, string(body))
	}

	// 115 API状态码说明:
	// code=90038 = 等待扫码 (message="请扫描二维码")
	// code=90039 = 已扫码，等待确认 (message="请确认登录")
	// code=0 + state=true = 登录成功，key为登录凭证
	// code=90032 = 二维码过期

	switch result.Code {
	case 90038:
		return 0, nil // 等待扫码
	case 90039:
		return 1, nil // 已扫码待确认
	case 0:
		if result.State && result.Key != "" {
			return 2, nil // 登录成功
		}
		return 0, nil
	case 90032:
		return -1, nil // 二维码过期
	default:
		return 0, nil
	}
}

// LoginWithQRCode 扫码登录成功后获取Cookie（支持不同设备类型）
func (c *Driver115Client) LoginWithQRCode(uid string, app string) (string, *model.User115Info, error) {
	if app == "" {
		app = "alipaymini"
	}

	// 根据设备类型确定API路径和User-Agent（参考p115client）
	loginApp := app
	loginUA := c.userAgent
	switch app {
	case "desktop":
		loginApp = "web"
	case "windows":
		loginApp = "os_windows"
	case "mac":
		loginApp = "os_mac"
	case "linux":
		loginApp = "os_linux"
	case "ios":
		loginUA = "UPhone/1.0.0"
		loginApp = "ios"
	case "115ios":
		loginUA = "UPhone/1.0.0"
		loginApp = "ios"
	case "qios":
		loginUA = "OfficePhone/1.0.0"
		loginApp = "ios"
	case "ipad":
		loginUA = "UPad/1.0.0"
		loginApp = "ios"
	case "115ipad":
		loginUA = "UPad/1.0.0"
		loginApp = "ios"
	case "qipad":
		loginUA = "OfficePad/1.0.0"
		loginApp = "ios"
	}

	apiURL := fmt.Sprintf("https://qrcodeapi.115.com/app/1.0/%s/1.0/login/qrcode/", loginApp)

	form := url.Values{}
	form.Set("account", uid)

	req, err := http.NewRequest("POST", apiURL, strings.NewReader(form.Encode()))
	if err != nil {
		return "", nil, err
	}
	req.Header.Set("Content-Type", "application/x-www-form-urlencoded")
	req.Header.Set("User-Agent", loginUA)

	resp, err := c.doRequest(req)
	if err != nil {
		return "", nil, err
	}
	defer resp.Body.Close()

	// 解析响应获取用户信息和Cookie
	body, _ := io.ReadAll(resp.Body)

	var result struct {
		State int `json:"state"`
		Data  struct {
			UserID   int64  `json:"user_id"`
			UserName string `json:"user_name"`
			Cookie   struct {
				UID  string `json:"UID"`
				CID  string `json:"CID"`
				SEID string `json:"SEID"`
			} `json:"cookie"`
		} `json:"data"`
	}
	if err := json.Unmarshal(body, &result); err != nil {
		return "", nil, fmt.Errorf("解析响应失败: %v, body: %s", err, string(body))
	}

	// 从响应头获取Cookie
	var cookies []string
	for _, cookie := range resp.Cookies() {
		cookies = append(cookies, fmt.Sprintf("%s=%s", cookie.Name, cookie.Value))
	}

	// 如果响应头没有Cookie，尝试从响应体获取
	if len(cookies) == 0 && result.Data.Cookie.UID != "" {
		cookies = append(cookies, fmt.Sprintf("UID=%s", result.Data.Cookie.UID))
		if result.Data.Cookie.CID != "" {
			cookies = append(cookies, fmt.Sprintf("CID=%s", result.Data.Cookie.CID))
		}
		if result.Data.Cookie.SEID != "" {
			cookies = append(cookies, fmt.Sprintf("SEID=%s", result.Data.Cookie.SEID))
		}
	}

	cookieStr := strings.Join(cookies, "; ")

	userInfo := &model.User115Info{
		UserID:   fmt.Sprintf("%d", result.Data.UserID),
		UserName: result.Data.UserName,
	}

	// 保存Cookie
	if cookieStr != "" {
		c.SetCookie(cookieStr)
	}

	return cookieStr, userInfo, nil
}

// ==================== 用户信息 ====================

// GetUserInfo 获取用户信息（使用当前活跃cookie）
func (c *Driver115Client) GetUserInfo() (*model.User115Info, error) {
	c.mu.RLock()
	cookie := c.cookie
	c.mu.RUnlock()

	info, err := c.CheckCookieValid(cookie)
	if err != nil {
		// 只有明确的"Cookie无效"才触发失效回调，网络错误等不触发
		if err.Error() == "Cookie无效" {
			c.notifyCookieExpired()
		}
		return nil, err
	}
	return info, nil
}

// CheckCookieValid 检查指定cookie是否有效，有效则返回用户信息
func (c *Driver115Client) CheckCookieValid(cookie string) (*model.User115Info, error) {
	if cookie == "" {
		return nil, fmt.Errorf("未登录")
	}

	apiURL := "https://my.115.com/?ct=ajax&ac=nav"

	req, err := http.NewRequest("GET", apiURL, nil)
	if err != nil {
		return nil, err
	}
	req.Header.Set("Cookie", cookie)
	req.Header.Set("User-Agent", c.userAgent)

	resp, err := c.doRequest(req)
	if err != nil {
		return nil, err
	}
	defer resp.Body.Close()

	body, err := io.ReadAll(resp.Body)
	if err != nil {
		return nil, err
	}

	c.debugLog("[115API] CheckCookieValid 响应: %s\n", string(body)[:min(500, len(body))])

	// 先只解析state字段，避免data为空数组时报错
	var stateResult struct {
		State bool            `json:"state"`
		Data  json.RawMessage `json:"data"`
	}
	if err := json.Unmarshal(body, &stateResult); err != nil {
		c.debugLog("[115API] CheckCookieValid JSON解析失败: %v\n", err)
		return nil, err
	}

	if !stateResult.State {
		c.debugLog("[115API] CheckCookieValid state=false, Cookie无效\n")
		return nil, fmt.Errorf("Cookie无效")
	}

	// state=true时，data一定是对象，安全解析
	var userData struct {
		UserID   int64  `json:"user_id"`
		UserName string `json:"user_name"`
		IsVIP    int    `json:"vip"`
	}
	if err := json.Unmarshal(stateResult.Data, &userData); err != nil {
		c.debugLog("[115API] CheckCookieValid 解析用户数据失败: %v\n", err)
		return nil, err
	}

	c.debugLog("[115API] CheckCookieValid state=true, user_id=%d, user_name=%s, vip=%d\n", userData.UserID, userData.UserName, userData.IsVIP)

	// 尝试解析扩展信息（头像、空间），失败不影响主流程
	var extInfo struct {
		Data struct {
			Face      json.RawMessage `json:"face"`
			SpaceInfo json.RawMessage `json:"space_info"`
		} `json:"data"`
	}
	var avatarURL string
	var spaceTotal, spaceUsed int64
	if json.Unmarshal(body, &extInfo) == nil {
		// 尝试解析face为对象
		var faceObj struct {
			FaceL string `json:"face_l"`
			FaceM string `json:"face_m"`
		}
		if json.Unmarshal(extInfo.Data.Face, &faceObj) == nil {
			avatarURL = faceObj.FaceL
			if avatarURL == "" {
				avatarURL = faceObj.FaceM
			}
		} else {
			// face可能是字符串
			var faceStr string
			if json.Unmarshal(extInfo.Data.Face, &faceStr) == nil {
				avatarURL = faceStr
			}
		}
		// 尝试解析space_info
		var spaceObj struct {
			AllTotal struct {
				Size int64 `json:"size"`
			} `json:"all_total"`
			AllUsed struct {
				Size int64 `json:"size"`
			} `json:"all_use"`
		}
		if json.Unmarshal(extInfo.Data.SpaceInfo, &spaceObj) == nil {
			spaceTotal = spaceObj.AllTotal.Size
			spaceUsed = spaceObj.AllUsed.Size
		}
	}

	return &model.User115Info{
		UserID:     fmt.Sprintf("%d", userData.UserID),
		UserName:   userData.UserName,
		IsVIP:      userData.IsVIP > 0,
		AvatarURL:  avatarURL,
		SpaceTotal: spaceTotal,
		SpaceUsed:  spaceUsed,
	}, nil
}

// GetSpaceInfo 获取空间信息（更准确）
func (c *Driver115Client) GetSpaceInfo(cookie string) (total, used int64, err error) {
	if cookie == "" {
		c.mu.RLock()
		cookie = c.cookie
		c.mu.RUnlock()
	}
	if cookie == "" {
		return 0, 0, fmt.Errorf("未登录")
	}

	apiURL := "https://proapi.115.com/android/user/space_info"
	req, err := http.NewRequest("GET", apiURL, nil)
	if err != nil {
		return 0, 0, err
	}
	req.Header.Set("Cookie", cookie)
	req.Header.Set("User-Agent", c.userAgent)

	resp, err := c.doRequest(req)
	if err != nil {
		return 0, 0, err
	}
	defer resp.Body.Close()

	body, err := io.ReadAll(resp.Body)
	if err != nil {
		return 0, 0, err
	}

	var result struct {
		State bool `json:"state"`
		Data  struct {
			AllUsed  json.RawMessage `json:"all_use"`
			AllTotal json.RawMessage `json:"all_total"`
		} `json:"data"`
	}
	if err := json.Unmarshal(body, &result); err != nil {
		c.debugLog("[115API] GetSpaceInfo JSON解析失败: %v, body: %s", err, string(body)[:min(300, len(body))])
		return 0, 0, err
	}
	if !result.State {
		c.debugLog("[115API] GetSpaceInfo state=false, body: %s", string(body)[:min(300, len(body))])
		return 0, 0, fmt.Errorf("获取空间信息失败")
	}

	// 解析 all_use 和 all_total（可能是 {"size": 123} 或直接数字）
	type sizeObj struct {
		Size int64 `json:"size"`
	}
	var usedObj, totalObj sizeObj
	json.Unmarshal(result.Data.AllUsed, &usedObj)
	json.Unmarshal(result.Data.AllTotal, &totalObj)

	c.debugLog("[115API] GetSpaceInfo total=%d, used=%d", totalObj.Size, usedObj.Size)
	return totalObj.Size, usedObj.Size, nil
}

// UserSign 每日签到（需要user_id来计算token）
func (c *Driver115Client) UserSign(cookie string, userID string) (string, error) {
	if cookie == "" {
		c.mu.RLock()
		cookie = c.cookie
		c.mu.RUnlock()
	}
	if cookie == "" {
		return "", fmt.Errorf("未登录")
	}

	// 如果没有提供userID，先通过CheckCookieValid获取
	if userID == "" {
		info, err := c.CheckCookieValid(cookie)
		if err != nil {
			return "", fmt.Errorf("获取用户信息失败: %v", err)
		}
		userID = info.UserID
	}

	// 按照p115client的方式计算token: sha1("{user_id}-Points_Sign@#115-{timestamp}")
	t := time.Now().Unix()
	tokenStr := fmt.Sprintf("%s-Points_Sign@#115-%d", userID, t)
	h := sha1.New()
	h.Write([]byte(tokenStr))
	token := fmt.Sprintf("%x", h.Sum(nil))

	apiURL := "https://proapi.115.com/android/2.0/user/points_sign"
	formData := url.Values{}
	formData.Set("token", token)
	formData.Set("token_time", fmt.Sprintf("%d", t))

	req, err := http.NewRequest("POST", apiURL, strings.NewReader(formData.Encode()))
	if err != nil {
		return "", err
	}
	req.Header.Set("Cookie", cookie)
	req.Header.Set("User-Agent", c.userAgent)
	req.Header.Set("Content-Type", "application/x-www-form-urlencoded")

	resp, err := c.doRequest(req)
	if err != nil {
		return "", err
	}
	defer resp.Body.Close()

	body, err := io.ReadAll(resp.Body)
	if err != nil {
		return "", err
	}

	c.debugLog("[115API] UserSign 响应: %s", string(body)[:min(300, len(body))])

	var result struct {
		State bool   `json:"state"`
		Msg   string `json:"msg"`
		Errno int    `json:"errno"`
	}
	if err := json.Unmarshal(body, &result); err != nil {
		return "", err
	}
	if !result.State {
		if result.Errno == 990002 || result.Errno == 990001 {
			return "", fmt.Errorf("Cookie已过期")
		}
		return result.Msg, nil // 可能是"已签到"
	}
	return "签到成功", nil
}

// DownloadAvatar 下载头像到本地缓存
func (c *Driver115Client) DownloadAvatar(avatarURL, savePath string) error {
	if avatarURL == "" {
		return fmt.Errorf("头像URL为空")
	}

	req, err := http.NewRequest("GET", avatarURL, nil)
	if err != nil {
		return err
	}
	req.Header.Set("User-Agent", c.userAgent)

	resp, err := c.doRequest(req)
	if err != nil {
		return err
	}
	defer resp.Body.Close()

	if resp.StatusCode != 200 {
		return fmt.Errorf("下载头像失败: HTTP %d", resp.StatusCode)
	}

	// 确保目录存在
	dir := filepath.Dir(savePath)
	if err := os.MkdirAll(dir, 0755); err != nil {
		return err
	}

	f, err := os.Create(savePath)
	if err != nil {
		return err
	}
	defer f.Close()

	_, err = io.Copy(f, resp.Body)
	return err
}

// ==================== 直链获取 ====================

// DownloadInfo 下载信息
type DownloadInfo struct {
	URL       string
	FileName  string
	FileSize  int64
	PickCode  string
	ExpiresAt time.Time
	UserAgent string
	FromCache bool
}

// GetDownloadURL 获取下载直链（cookie模式，兼容testAAA逻辑）
func (c *Driver115Client) GetDownloadURL(pickCode, userAgent string, samePlayback bool, copyPID string) (*DownloadInfo, error) {
	c.mu.RLock()
	cookie := c.cookie
	if userAgent == "" {
		userAgent = c.userAgent
	}
	c.mu.RUnlock()

	if cookie == "" {
		return nil, fmt.Errorf("未登录")
	}

	if pickCode == "" {
		return nil, fmt.Errorf("pickcode为空")
	}

	c.debugLog("[115API] 获取直链(cookie模式)，pickcode: %s\n", pickCode)

	postPickCode := pickCode
	if samePlayback && copyPID != "" {
		pc, err := c.getPickCodeForCopy(pickCode, copyPID, userAgent)
		if err == nil && pc != "" {
			postPickCode = pc
			c.debugLog("[115API] 多端播放开启 %s -> %s\n", pickCode, postPickCode)
		}
	}

	info, err := c.getDownloadURLApp(postPickCode, userAgent)
	if err != nil {
		return nil, err
	}

	if postPickCode != pickCode {
		go func() {
			_ = c.delayedRemove(postPickCode, userAgent)
		}()
	}

	return info, nil
}

// getDownloadURLApp 使用proapi app(安卓)接口获取直链
func (c *Driver115Client) getDownloadURLApp(pickCode, userAgent string) (*DownloadInfo, error) {
	apiURL := "http://proapi.115.com/android/2.0/ufile/download"

	payload := fmt.Sprintf("{\"pick_code\":\"%s\"}", pickCode)
	cipher, err := p115Encrypt([]byte(payload))
	if err != nil {
		return nil, err
	}

	req, err := http.NewRequest("POST", apiURL, strings.NewReader("data="+url.QueryEscape(string(cipher))))
	if err != nil {
		return nil, err
	}

	req.Header.Set("Content-Type", "application/x-www-form-urlencoded")
	req.Header.Set("Cookie", c.cookie)
	if userAgent != "" {
		req.Header.Set("User-Agent", userAgent)
	}

	resp, err := c.doRequest(req)
	if err != nil {
		return nil, err
	}
	defer resp.Body.Close()

	if resp.StatusCode >= 400 {
		if resp.StatusCode == 401 || resp.StatusCode == 403 {
			c.notifyCookieExpired()
			return nil, ErrCookieExpired
		}
		return nil, fmt.Errorf("HTTP Error %d", resp.StatusCode)
	}

	body, err := io.ReadAll(resp.Body)
	if err != nil {
		return nil, err
	}

	var result struct {
		State bool            `json:"state"`
		Data  json.RawMessage `json:"data"`
		Errno int             `json:"errno"`
		Msg   string          `json:"msg"`
	}

	c.debugLog("[115API] 响应内容: %s\n", string(body)[:min(500, len(body))])

	if err := json.Unmarshal(body, &result); err != nil {
		return nil, err
	}

	if !result.State {
		if isCookieExpiredError(body, resp.StatusCode) {
			c.notifyCookieExpired()
			return nil, ErrCookieExpired
		}
		return nil, fmt.Errorf("%s (errno=%d)", result.Msg, result.Errno)
	}

	plain := result.Data
	if len(result.Data) > 0 && result.Data[0] == '"' {
		var encrypted string
		if err := json.Unmarshal(result.Data, &encrypted); err != nil {
			return nil, err
		}
		decrypted, err := p115Decrypt([]byte(encrypted))
		if err != nil {
			return nil, err
		}
		plain = decrypted
	}

	urlStr, fileName, fileSize, pickCodeResp, err := parseDownloadURLData(plain)
	if err != nil {
		return nil, err
	}
	if urlStr == "" {
		return nil, fmt.Errorf("下载链接为空")
	}

	if fileName == "" {
		if parsed, err := url.Parse(urlStr); err == nil {
			fileName = pathBaseFromURL(parsed)
		}
	}

	expiresAt := parseURLExpiresAt(urlStr)

	return &DownloadInfo{
		URL:       urlStr,
		FileName:  fileName,
		FileSize:  fileSize,
		PickCode:  pickCodeResp,
		ExpiresAt: expiresAt,
		UserAgent: userAgent,
	}, nil
}

func parseDownloadURLData(plain []byte) (string, string, int64, string, error) {
	var raw any
	if err := json.Unmarshal(plain, &raw); err != nil {
		return "", "", 0, "", err
	}
	return extractDownloadURLFromAny(raw)
}

func extractDownloadURLFromAny(raw any) (string, string, int64, string, error) {
	switch v := raw.(type) {
	case map[string]any:
		if urlStr, fileName, fileSize, pickCode, ok := extractDownloadURLFromMap(v); ok {
			return urlStr, fileName, fileSize, pickCode, nil
		}
		for _, val := range v {
			if infoMap, ok := val.(map[string]any); ok {
				if urlStr, fileName, fileSize, pickCode, ok := extractDownloadURLFromMap(infoMap); ok {
					return urlStr, fileName, fileSize, pickCode, nil
				}
			}
		}
	case []any:
		if len(v) > 0 {
			if infoMap, ok := v[0].(map[string]any); ok {
				if urlStr, fileName, fileSize, pickCode, ok := extractDownloadURLFromMap(infoMap); ok {
					return urlStr, fileName, fileSize, pickCode, nil
				}
			}
		}
	}
	return "", "", 0, "", fmt.Errorf("无法解析下载数据")
}

func extractDownloadURLFromMap(m map[string]any) (string, string, int64, string, bool) {
	urlStr := ""
	if rawURL, ok := m["url"]; ok {
		switch u := rawURL.(type) {
		case string:
			urlStr = u
		case map[string]any:
			if inner, ok := u["url"].(string); ok {
				urlStr = inner
			}
		}
	}
	fileName, _ := m["file_name"].(string)
	pickCode, _ := m["pick_code"].(string)
	fileSize := int64(0)
	if fs, ok := m["file_size"]; ok {
		switch v := fs.(type) {
		case float64:
			fileSize = int64(v)
		case int64:
			fileSize = v
		case int:
			fileSize = int64(v)
		case string:
			if parsed, err := strconv.ParseInt(v, 10, 64); err == nil {
				fileSize = parsed
			}
		}
	}
	if urlStr == "" && fileName == "" && pickCode == "" {
		return "", "", 0, "", false
	}
	return urlStr, fileName, fileSize, pickCode, true
}

func pathBaseFromURL(u *url.URL) string {
	if u == nil {
		return ""
	}
	seg := u.Path
	if seg == "" {
		return ""
	}
	if idx := strings.LastIndex(seg, "/"); idx >= 0 && idx+1 < len(seg) {
		return seg[idx+1:]
	}
	return seg
}

func parseURLExpiresAt(rawURL string) time.Time {
	parsed, err := url.Parse(rawURL)
	if err != nil {
		return time.Now().Add(30 * time.Minute)
	}
	q := parsed.Query()
	tStr := q.Get("t")
	if tStr == "" {
		return time.Now().Add(30 * time.Minute)
	}
	t, err := strconv.ParseInt(tStr, 10, 64)
	if err != nil {
		return time.Now().Add(30 * time.Minute)
	}
	return time.Unix(t-60*5, 0)
}

func (c *Driver115Client) getPickCodeForCopy(pickCode, pid, userAgent string) (string, error) {
	id := pickcodeToID(pickCode)
	if id <= 0 {
		return "", fmt.Errorf("无效pickcode")
	}

	apiURL := "https://proapi.115.com/android/files/copy"
	form := url.Values{}
	form.Set("pid", pid)
	form.Set("file_id", strconv.FormatInt(id, 10))

	req, err := http.NewRequest("POST", apiURL, strings.NewReader(form.Encode()))
	if err != nil {
		return "", err
	}
	req.Header.Set("Content-Type", "application/x-www-form-urlencoded")
	req.Header.Set("Cookie", c.cookie)
	if userAgent != "" {
		req.Header.Set("User-Agent", userAgent)
	}

	resp, err := c.doRequest(req)
	if err != nil {
		return "", err
	}
	defer resp.Body.Close()

	if resp.StatusCode >= 400 {
		return "", fmt.Errorf("HTTP Error %d", resp.StatusCode)
	}

	body, err := io.ReadAll(resp.Body)
	if err != nil {
		return "", err
	}

	var copyResult struct {
		State bool   `json:"state"`
		Errno int    `json:"errno"`
		Msg   string `json:"msg"`
	}
	if err := json.Unmarshal(body, &copyResult); err != nil {
		return "", err
	}
	if !copyResult.State {
		return "", fmt.Errorf("%s (errno=%d)", copyResult.Msg, copyResult.Errno)
	}

	files, err := c.listDir(pid)
	if err != nil {
		return "", err
	}
	if len(files) == 0 {
		return "", fmt.Errorf("复制后目录为空")
	}
	return files[0].PickCode, nil
}

func (c *Driver115Client) delayedRemove(pickCode, userAgent string) error {
	time.Sleep(5 * time.Second)
	id := pickcodeToID(pickCode)
	if id <= 0 {
		return nil
	}
	apiURL := "https://proapi.115.com/android/rb/delete"
	form := url.Values{}
	form.Set("file_id", strconv.FormatInt(id, 10))

	req, err := http.NewRequest("POST", apiURL, strings.NewReader(form.Encode()))
	if err != nil {
		return err
	}
	req.Header.Set("Content-Type", "application/x-www-form-urlencoded")
	req.Header.Set("Cookie", c.cookie)
	if userAgent != "" {
		req.Header.Set("User-Agent", userAgent)
	}

	resp, err := c.doRequest(req)
	if err != nil {
		return err
	}
	defer resp.Body.Close()

	if resp.StatusCode >= 400 {
		return fmt.Errorf("HTTP Error %d", resp.StatusCode)
	}

	return nil
}

// getDirIDByPath 通过115 API根据目录路径一次性获取目录ID
// 调用 GET https://webapi.115.com/files/getid?path=xxx
// 注意：此API只能获取目录ID，不能获取文件ID
// GetDirIDByPath 公开方法：通过路径获取目录CID
func (c *Driver115Client) GetDirIDByPath(dirPath string) (string, error) {
	return c.getDirIDByPath(dirPath)
}

// ListDir 公开方法：列出目录下的文件
func (c *Driver115Client) ListDir(cid string) ([]*FileInfo115, error) {
	return c.listDir(cid)
}

func (c *Driver115Client) getDirIDByPath(dirPath string) (string, error) {
	// 先查内存缓存
	if cached, ok := c.dirPathCache.Load(dirPath); ok {
		cid := cached.(string)
		c.debugLog("[115API] 目录缓存命中: %s -> cid=%s\n", dirPath, cid)
		return cid, nil
	}

	c.mu.RLock()
	cookie := c.cookie
	c.mu.RUnlock()

	apiURL := fmt.Sprintf("https://webapi.115.com/files/getid?path=%s", url.QueryEscape(dirPath))

	req, err := http.NewRequest("GET", apiURL, nil)
	if err != nil {
		return "", err
	}
	req.Header.Set("Cookie", cookie)
	req.Header.Set("User-Agent", c.userAgent)

	resp, err := c.doRequest(req)
	if err != nil {
		return "", err
	}
	defer resp.Body.Close()

	body, err := io.ReadAll(resp.Body)
	if err != nil {
		return "", err
	}

	c.debugLog("[115API] getid响应: %s\n", string(body)[:min(500, len(body))])

	var result struct {
		State bool   `json:"state"`
		ID    any    `json:"id"`
		Errno int    `json:"errno"`
		Error string `json:"error"`
	}

	if err := json.Unmarshal(body, &result); err != nil {
		return "", fmt.Errorf("解析getid响应失败: %v", err)
	}

	if !result.State {
		return "", fmt.Errorf("获取目录ID失败: %s (errno=%d)", result.Error, result.Errno)
	}

	// id 可能是 int 或 string
	var cid string
	switch v := result.ID.(type) {
	case float64:
		cid = strconv.FormatInt(int64(v), 10)
	case string:
		cid = v
	default:
		return "", fmt.Errorf("无法解析目录ID: %v", result.ID)
	}

	if cid == "" || cid == "0" {
		return "", fmt.Errorf("目录不存在: %s", dirPath)
	}

	// 写入缓存
	c.dirPathCache.Store(dirPath, cid)
	c.debugLog("[115API] 目录ID获取成功: %s -> cid=%s\n", dirPath, cid)

	return cid, nil
}

// GetPathByFileID 通过文件ID获取文件路径
// 调用 GET https://webapi.115.com/files/get_info?file_id=xxx
func (c *Driver115Client) GetPathByFileID(fileID string) (string, error) {
	c.mu.RLock()
	cookie := c.cookie
	c.mu.RUnlock()

	apiURL := fmt.Sprintf("https://webapi.115.com/files/get_info?file_id=%s", fileID)

	req, err := http.NewRequest("GET", apiURL, nil)
	if err != nil {
		return "", err
	}
	req.Header.Set("Cookie", cookie)
	req.Header.Set("User-Agent", c.userAgent)

	resp, err := c.doRequest(req)
	if err != nil {
		return "", err
	}
	defer resp.Body.Close()

	body, err := io.ReadAll(resp.Body)
	if err != nil {
		return "", err
	}

	c.debugLog("[115API] get_info响应: %s\n", string(body)[:min(500, len(body))])

	var result struct {
		State bool `json:"state"`
		Data  []struct {
			Path string `json:"path"`
		} `json:"data"`
		Errno int    `json:"errno"`
		Error string `json:"error"`
	}

	if err := json.Unmarshal(body, &result); err != nil {
		return "", fmt.Errorf("解析get_info响应失败: %v", err)
	}

	if !result.State {
		return "", fmt.Errorf("获取文件信息失败: %s (errno=%d)", result.Error, result.Errno)
	}

	if len(result.Data) == 0 {
		return "", fmt.Errorf("文件不存在: file_id=%s", fileID)
	}

	path := result.Data[0].Path
	c.debugLog("[115API] 文件路径获取成功: file_id=%s -> path=%s\n", fileID, path)

	return path, nil
}

// GetDownloadURLByPath 通过文件路径获取直链
// path 是115内部的文件路径，如 /媒体库/电影/xxx.mp4
// userAgent: 指定UA，确保直链与播放器UA匹配；为空则使用默认UA
// 流程：先用 /files/getid 一次性获取父目录ID，再 listDir 最后一级找文件的 pickcode
func (c *Driver115Client) GetDownloadURLByPath(filePath string, userAgent string) (*DownloadInfo, error) {
	c.mu.RLock()
	cookie := c.cookie
	if userAgent == "" {
		userAgent = c.userAgent
	}
	c.mu.RUnlock()

	if cookie == "" {
		return nil, fmt.Errorf("未登录")
	}

	c.debugLog("[115API] 通过路径获取直链: %s\n", filePath)

	cleanPath := strings.TrimSpace(filePath)
	parts := strings.Split(strings.Trim(cleanPath, "/"), "/")
	if len(parts) == 0 {
		return nil, fmt.Errorf("无效的路径")
	}

	fileName := parts[len(parts)-1]

	// 获取父目录ID：如果路径只有一级（文件在根目录），cid=0；否则用 getid API
	var parentCid string
	if len(parts) == 1 {
		parentCid = "0"
	} else {
		dirParts := parts[:len(parts)-1]
		dirPath := "/" + strings.Join(dirParts, "/")
		cid, err := c.getDirIDByPath(dirPath)
		if err != nil {
			fmt.Printf("[115API] getid获取父目录失败: %v, 回退到逐级遍历\n", err)
			// 回退：逐级遍历目录
			cid, err = c.walkDirPath(parts[:len(parts)-1])
			if err != nil {
				return nil, fmt.Errorf("获取父目录失败: %v", err)
			}
		}
		parentCid = cid
	}

	c.debugLog("[115API] 父目录cid=%s，查找文件: %s\n", parentCid, fileName)

	// listDir 最后一级，找到文件的 pickcode
	files, err := c.listDir(parentCid)
	if err != nil {
		return nil, fmt.Errorf("列出目录失败: %v", err)
	}

	for _, f := range files {
		if f.Name == fileName {
			if f.IsDir {
				return nil, fmt.Errorf("路径指向目录而非文件: %s", fileName)
			}
			if f.PickCode != "" {
				c.debugLog("[115API] 找到文件, pickcode=%s\n", f.PickCode)
				return c.GetDownloadURL(f.PickCode, userAgent, false, "")
			}
			// 回退：通过文件ID转换pickcode
			fid, err := strconv.ParseInt(f.Fid, 10, 64)
			if err != nil || fid <= 0 {
				return nil, fmt.Errorf("无效的文件ID: %s", f.Fid)
			}
			stablePoint, err := c.getPickcodeStablePoint()
			if err != nil {
				return nil, fmt.Errorf("获取稳定点失败: %v", err)
			}
			pickcode, err := p115IDToPickcode(fid, stablePoint, "a")
			if err != nil {
				return nil, fmt.Errorf("转换pickcode失败: %v", err)
			}
			c.debugLog("[115API] 找到文件, ID=%d, pickcode=%s (ID转换)\n", fid, pickcode)
			return c.GetDownloadURL(pickcode, userAgent, false, "")
		}
	}

	return nil, fmt.Errorf("未找到文件: %s (在目录 cid=%s 中)", fileName, parentCid)
}

// walkDirPath 逐级遍历目录路径获取最终目录的cid（作为getid的回退方案）
func (c *Driver115Client) walkDirPath(dirParts []string) (string, error) {
	currentCid := "0"
	for i, part := range dirParts {
		c.debugLog("[115API] 回退遍历第%d级: %s (cid=%s)\n", i+1, part, currentCid)
		files, err := c.listDir(currentCid)
		if err != nil {
			return "", fmt.Errorf("列出目录失败: %v", err)
		}
		found := false
		for _, f := range files {
			if f.Name == part && f.IsDir {
				currentCid = f.Cid
				found = true
				break
			}
		}
		if !found {
			return "", fmt.Errorf("未找到目录: %s (在 cid=%s 中)", part, currentCid)
		}
	}
	// 缓存遍历结果
	dirPath := "/" + strings.Join(dirParts, "/")
	c.dirPathCache.Store(dirPath, currentCid)
	return currentCid, nil
}

// FileInfo115 115文件信息
type FileInfo115 struct {
	Cid      string `json:"cid"` // 目录ID或文件ID
	Name     string `json:"n"`   // 文件名
	Size     int64  `json:"s"`   // 文件大小
	PickCode string `json:"pc"`  // pickcode
	IsDir    bool   `json:"-"`   // 是否是目录
	Fid      string `json:"fid"` // 文件ID
	Sha1     string `json:"sha"` // 文件SHA1
}

// findDirPickcode 通过列出父目录来获取目标目录的真实 pickcode
func (c *Driver115Client) findDirPickcode(cleanPath string, targetCid string) string {
	parts := strings.Split(cleanPath, "/")
	if len(parts) == 0 {
		return ""
	}
	targetName := parts[len(parts)-1]

	// 获取父目录的 cid
	var parentCid string
	if len(parts) == 1 {
		parentCid = "0" // 父目录是根目录
	} else {
		parentPath := "/" + strings.Join(parts[:len(parts)-1], "/")
		pid, err := c.getDirIDByPath(parentPath)
		if err != nil {
			return ""
		}
		parentCid = pid
	}

	// 列出父目录，找到目标目录的 pickcode
	files, err := c.listDir(parentCid)
	if err != nil {
		return ""
	}
	for _, f := range files {
		if f.IsDir && (f.Cid == targetCid || f.Name == targetName) {
			if f.PickCode != "" {
				c.debugLog("[115API] 从父目录找到真实pickcode: %s -> %s\n", targetCid, f.PickCode)
				return f.PickCode
			}
		}
	}
	return ""
}

// getDirPickcode 通过 fs_file_skim 获取目录的真实 pickcode
func (c *Driver115Client) getDirPickcode(cid string) (string, error) {
	c.mu.RLock()
	cookie := c.cookie
	c.mu.RUnlock()

	params := fmt.Sprintf("file_id[0]=%s", cid)
	apiURL := "https://webapi.115.com/files/file_skim"
	req, err := http.NewRequest("POST", apiURL, strings.NewReader(params))
	if err != nil {
		return "", err
	}
	req.Header.Set("Cookie", cookie)
	req.Header.Set("User-Agent", c.userAgent)
	req.Header.Set("Content-Type", "application/x-www-form-urlencoded")

	resp, err := c.doRequest(req)
	if err != nil {
		return "", err
	}
	body, _ := io.ReadAll(resp.Body)
	resp.Body.Close()

	c.debugLog("[115API] file_skim响应: %s\n", string(body)[:min(500, len(body))])

	var skimResp struct {
		State bool `json:"state"`
		Data  []struct {
			FileID   string `json:"file_id"`
			PickCode string `json:"pick_code"`
		} `json:"data"`
	}
	if err := json.Unmarshal(body, &skimResp); err != nil {
		return "", fmt.Errorf("解析file_skim响应失败: %v", err)
	}
	if !skimResp.State || len(skimResp.Data) == 0 {
		return "", fmt.Errorf("获取目录pickcode失败: cid=%s", cid)
	}
	pc := skimResp.Data[0].PickCode
	c.debugLog("[115API] 目录真实pickcode: cid=%s -> pc=%s\n", cid, pc)
	return pc, nil
}

// DeleteFile 删除115网盘文件/目录（移到回收站）
// fileID 是文件或目录的 CID/FID
func (c *Driver115Client) DeleteFile(fileID string) error {
	c.mu.RLock()
	cookie := c.cookie
	c.mu.RUnlock()

	apiURL := "https://webapi.115.com/rb/delete"

	formData := fmt.Sprintf("fid[0]=%s", url.QueryEscape(fileID))
	req, err := http.NewRequest("POST", apiURL, strings.NewReader(formData))
	if err != nil {
		return err
	}

	req.Header.Set("Cookie", cookie)
	req.Header.Set("User-Agent", c.userAgent)
	req.Header.Set("Content-Type", "application/x-www-form-urlencoded")

	resp, err := c.doRequest(req)
	if err != nil {
		return err
	}
	defer resp.Body.Close()

	body, err := io.ReadAll(resp.Body)
	if err != nil {
		return err
	}

	c.debugLog("[115API] DeleteFile响应: %s\n", string(body))

	var result struct {
		State   bool   `json:"state"`
		Message string `json:"error"`
	}
	if err := json.Unmarshal(body, &result); err != nil {
		return fmt.Errorf("解析响应失败: %v", err)
	}
	if !result.State {
		return fmt.Errorf("删除文件失败: %s", result.Message)
	}

	return nil
}

// RenameFile 重命名115网盘文件/目录
func (c *Driver115Client) RenameFile(fileID, newName string) error {
	c.mu.RLock()
	cookie := c.cookie
	c.mu.RUnlock()

	apiURL := "https://webapi.115.com/files/batch_rename"

	formData := fmt.Sprintf("files_new_name[%s]=%s", url.QueryEscape(fileID), url.QueryEscape(newName))
	req, err := http.NewRequest("POST", apiURL, strings.NewReader(formData))
	if err != nil {
		return err
	}

	req.Header.Set("Cookie", cookie)
	req.Header.Set("User-Agent", c.userAgent)
	req.Header.Set("Content-Type", "application/x-www-form-urlencoded")

	resp, err := c.doRequest(req)
	if err != nil {
		return err
	}
	defer resp.Body.Close()

	body, err := io.ReadAll(resp.Body)
	if err != nil {
		return err
	}

	c.debugLog("[115API] RenameFile响应: %s\n", string(body))

	var result struct {
		State   bool   `json:"state"`
		Message string `json:"error"`
	}
	if err := json.Unmarshal(body, &result); err != nil {
		return fmt.Errorf("解析响应失败: %v", err)
	}
	if !result.State {
		return fmt.Errorf("重命名文件失败: %s", result.Message)
	}

	return nil
}

// listDir 列出目录下的文件
func (c *Driver115Client) listDir(cid string) ([]*FileInfo115, error) {
	c.mu.RLock()
	cookie := c.cookie
	c.mu.RUnlock()

	apiURL := fmt.Sprintf("https://webapi.115.com/files?aid=1&cid=%s&o=user_ptime&asc=0&offset=0&show_dir=1&limit=1000&snap=0&natsort=1&format=json", cid)

	req, err := http.NewRequest("GET", apiURL, nil)
	if err != nil {
		return nil, err
	}

	req.Header.Set("Cookie", cookie)
	req.Header.Set("User-Agent", c.userAgent)

	resp, err := c.doRequest(req)
	if err != nil {
		return nil, err
	}
	defer resp.Body.Close()

	body, err := io.ReadAll(resp.Body)
	if err != nil {
		return nil, err
	}

	c.debugLog("[115API] listDir响应: %s\n", string(body)[:min(500, len(body))])

	var result struct {
		State bool `json:"state"`
		Data  []struct {
			Cid      string `json:"cid"` // 目录ID
			Fid      string `json:"fid"` // 文件ID
			Name     string `json:"n"`   // 文件名
			Size     int64  `json:"s"`   // 文件大小
			PickCode string `json:"pc"`  // pickcode
			Pid      string `json:"pid"` // 父目录ID
		} `json:"data"`
		Msg string `json:"error"`
	}

	if err := json.Unmarshal(body, &result); err != nil {
		return nil, fmt.Errorf("解析响应失败: %v", err)
	}

	if !result.State {
		return nil, fmt.Errorf("列出目录失败: %s", result.Msg)
	}

	var files []*FileInfo115
	for _, item := range result.Data {
		f := &FileInfo115{
			Name:     item.Name,
			Size:     item.Size,
			PickCode: item.PickCode,
			Fid:      item.Fid,
		}
		// 如果有cid但没有fid，说明是目录
		if item.Cid != "" && item.Fid == "" {
			f.IsDir = true
			f.Cid = item.Cid
		} else {
			f.IsDir = false
			f.Cid = item.Fid
		}
		files = append(files, f)
	}

	return files, nil
}

// WalkDir115 递归遍历115网盘目录，构建文件列表
// path115: 115网盘路径（如 /电影）
// callback: 每个文件/目录的回调，参数为(文件信息, 完整115路径, 父目录路径)
// cooldown: 每次API请求间隔（毫秒），防止频率限制
func (c *Driver115Client) WalkDir115(path115 string, cooldown int, callback func(item *FileInfo115, fullPath string, parentPath string) error) error {
	cleanPath := strings.Trim(path115, "/")
	if cleanPath == "" {
		return fmt.Errorf("路径不能为空")
	}

	cid, err := c.getDirIDByPath("/" + cleanPath)
	if err != nil {
		parts := strings.Split(cleanPath, "/")
		cid, err = c.walkDirPath(parts)
		if err != nil {
			return fmt.Errorf("获取目录ID失败: %v", err)
		}
	}

	// 尝试快速模式：使用 proapi downfiles/downfolders
	// 需要目录的真实 pickcode，通过列出父目录来获取
	realPickcode := c.findDirPickcode(cleanPath, cid)
	if realPickcode != "" {
		c.debugLog("[115API] 使用快速模式构建目录树, pickcode=%s (真实), cid=%s\n", realPickcode, cid)
		err := c.walkDir115Fast(realPickcode, cid, "/"+cleanPath, callback)
		if err == nil {
			return nil
		}
		c.debugLog("[115API] 快速模式失败，回退到递归模式: %v\n", err)
	}

	// 回退到递归模式
	return c.walkDir115Recursive(cid, "/"+cleanPath, cooldown, callback)
}

// dirPageItem downfolders 单条目录记录
type dirPageItem struct {
	Fid string `json:"fid"`
	Fn  string `json:"fn"`
	Pid string `json:"pid"`
}

// filePageItem downfiles 单条文件记录
type filePageItem struct {
	Pc  string `json:"pc"`
	Pid string `json:"pid"`
	Fs  int64  `json:"fs"`
}

// fetchAllDirPages 拉取 downfolders 所有分页（动态并发：边拉边判断是否有下一页）
func (c *Driver115Client) fetchAllDirPages(pickcode, cookie, baseURL string) ([]dirPageItem, error) {
	type pageResp struct {
		State bool `json:"state"`
		Data  struct {
			List        []dirPageItem `json:"list"`
			HasNextPage bool          `json:"has_next_page"`
			Count       int           `json:"count"`
		} `json:"data"`
		Msg string `json:"error"`
	}

	fetchPage := func(page int) (pageResp, error) {
		apiURL := fmt.Sprintf("%s?pickcode=%s&page=%d&per_page=5000", baseURL, url.QueryEscape(pickcode), page)
		req, err := http.NewRequest("GET", apiURL, nil)
		if err != nil {
			return pageResp{}, err
		}
		req.Header.Set("Cookie", cookie)
		req.Header.Set("User-Agent", c.userAgent)
		resp, err := c.doRequest(req)
		if err != nil {
			return pageResp{}, err
		}
		body, err := io.ReadAll(resp.Body)
		resp.Body.Close()
		if err != nil {
			return pageResp{}, err
		}
		var r pageResp
		if err := json.Unmarshal(body, &r); err != nil {
			return pageResp{}, fmt.Errorf("解析downfolders响应失败: %v", err)
		}
		if !r.State {
			return pageResp{}, fmt.Errorf("downfolders失败: %s", r.Msg)
		}
		return r, nil
	}

	start := time.Now()
	first, err := fetchPage(1)
	if err != nil {
		return nil, err
	}
	c.debugLog("[115API] downfolders 第1页: %d条, hasNext=%v\n", len(first.Data.List), first.Data.HasNextPage)

	allItems := make([]dirPageItem, 0, 5000)
	allItems = append(allItems, first.Data.List...)

	if !first.Data.HasNextPage {
		c.debugLog("[115API] downfolders 完成: 共%d条, 耗时%v\n", len(allItems), time.Since(start).Round(time.Millisecond))
		return allItems, nil
	}

	// 动态并发：先拉2-6页，根据结果决定是否继续
	type pageResult struct {
		page    int
		items   []dirPageItem
		hasNext bool
		err     error
	}

	var mu sync.Mutex
	resultMap := make(map[int]pageResult)

	fetchBatch := func(startPage, endPage int) {
		var wg sync.WaitGroup
		sem := make(chan struct{}, 5)
		for p := startPage; p <= endPage; p++ {
			wg.Add(1)
			sem <- struct{}{}
			go func(page int) {
				defer func() { <-sem; wg.Done() }()
				r, err := fetchPage(page)
				mu.Lock()
				resultMap[page] = pageResult{page: page, items: r.Data.List, hasNext: r.Data.HasNextPage, err: err}
				mu.Unlock()
			}(p)
		}
		wg.Wait()
	}

	currentPage := 2
	for {
		batchEnd := currentPage + 4
		fetchBatch(currentPage, batchEnd)

		// 按顺序合并结果
		hasMore := false
		for p := currentPage; p <= batchEnd; p++ {
			r, ok := resultMap[p]
			if !ok || r.err != nil {
				c.debugLog("[115API] downfolders 第%d页失败\n", p)
				break
			}
			allItems = append(allItems, r.items...)
			if p%5 == 0 {
				c.debugLog("[115API] downfolders 第%d页: %d条, 累计%d条\n", p, len(r.items), len(allItems))
			}
			if r.hasNext {
				hasMore = true
			} else {
				hasMore = false
				break
			}
		}

		if !hasMore {
			break
		}
		currentPage = batchEnd + 1
	}

	c.debugLog("[115API] downfolders 完成: 共%d条, 耗时%v\n", len(allItems), time.Since(start).Round(time.Millisecond))
	return allItems, nil
}

// fetchAllFilePages 拉取 downfiles 所有分页（动态并发）
func (c *Driver115Client) fetchAllFilePages(pickcode, cookie, baseURL string) ([]filePageItem, error) {
	type pageResp struct {
		State bool `json:"state"`
		Data  struct {
			List        []filePageItem `json:"list"`
			HasNextPage bool           `json:"has_next_page"`
			Count       int            `json:"count"`
		} `json:"data"`
		Msg string `json:"error"`
	}

	fetchPage := func(page int) (pageResp, error) {
		apiURL := fmt.Sprintf("%s?pickcode=%s&page=%d&per_page=5000", baseURL, url.QueryEscape(pickcode), page)
		req, err := http.NewRequest("GET", apiURL, nil)
		if err != nil {
			return pageResp{}, err
		}
		req.Header.Set("Cookie", cookie)
		req.Header.Set("User-Agent", c.userAgent)
		resp, err := c.doRequest(req)
		if err != nil {
			return pageResp{}, err
		}
		body, err := io.ReadAll(resp.Body)
		resp.Body.Close()
		if err != nil {
			return pageResp{}, err
		}
		var r pageResp
		if err := json.Unmarshal(body, &r); err != nil {
			return pageResp{}, fmt.Errorf("解析downfiles响应失败: %v", err)
		}
		if !r.State {
			return pageResp{}, fmt.Errorf("downfiles失败: %s", r.Msg)
		}
		return r, nil
	}

	start := time.Now()
	first, err := fetchPage(1)
	if err != nil {
		return nil, err
	}
	c.debugLog("[115API] downfiles 第1页: %d条, hasNext=%v\n", len(first.Data.List), first.Data.HasNextPage)

	allItems := make([]filePageItem, 0, 5000)
	allItems = append(allItems, first.Data.List...)

	if !first.Data.HasNextPage {
		c.debugLog("[115API] downfiles 完成: 共%d条, 耗时%v\n", len(allItems), time.Since(start).Round(time.Millisecond))
		return allItems, nil
	}

	// 动态并发
	type pageResult struct {
		page    int
		items   []filePageItem
		hasNext bool
		err     error
	}

	var mu sync.Mutex
	resultMap := make(map[int]pageResult)

	fetchBatch := func(startPage, endPage int) {
		var wg sync.WaitGroup
		sem := make(chan struct{}, 5)
		for p := startPage; p <= endPage; p++ {
			wg.Add(1)
			sem <- struct{}{}
			go func(page int) {
				defer func() { <-sem; wg.Done() }()
				r, err := fetchPage(page)
				mu.Lock()
				resultMap[page] = pageResult{page: page, items: r.Data.List, hasNext: r.Data.HasNextPage, err: err}
				mu.Unlock()
			}(p)
		}
		wg.Wait()
	}

	currentPage := 2
	for {
		batchEnd := currentPage + 4
		fetchBatch(currentPage, batchEnd)

		hasMore := false
		for p := currentPage; p <= batchEnd; p++ {
			r, ok := resultMap[p]
			if !ok || r.err != nil {
				c.debugLog("[115API] downfiles 第%d页失败\n", p)
				break
			}
			allItems = append(allItems, r.items...)
			if p%5 == 0 {
				c.debugLog("[115API] downfiles 第%d页: %d条, 累计%d条\n", p, len(r.items), len(allItems))
			}
			if r.hasNext {
				hasMore = true
			} else {
				hasMore = false
				break
			}
		}

		if !hasMore {
			break
		}
		currentPage = batchEnd + 1
	}

	c.debugLog("[115API] downfiles 完成: 共%d条, 耗时%v\n", len(allItems), time.Since(start).Round(time.Millisecond))
	return allItems, nil
}

// walkDir115Fast 使用 proapi downfiles/downfolders 快速遍历（downfolders+downfiles 并发）
func (c *Driver115Client) walkDir115Fast(pickcode, rootCid, rootPath string, callback func(item *FileInfo115, fullPath string, parentPath string) error) error {
	c.mu.RLock()
	cookie := c.cookie
	c.mu.RUnlock()

	folderBaseURL, fileBaseURL := c.getProAPIPrefix()
	c.debugLog("[115API] 快速模式API: folders=%s, files=%s\n", folderBaseURL, fileBaseURL)

	// 1. 并发拉取 downfolders + downfiles
	var (
		rawDirs  []dirPageItem
		rawFiles []filePageItem
		dirsErr  error
		filesErr error
		wg       sync.WaitGroup
	)

	c.debugLog("[115API] 并发拉取 downfolders + downfiles...\n")
	fetchStart := time.Now()

	wg.Add(2)
	go func() {
		defer wg.Done()
		items, err := c.fetchAllDirPages(pickcode, cookie, folderBaseURL)
		if err != nil {
			dirsErr = err
			return
		}
		rawDirs = items
	}()
	go func() {
		defer wg.Done()
		items, err := c.fetchAllFilePages(pickcode, cookie, fileBaseURL)
		if err != nil {
			filesErr = err
			return
		}
		rawFiles = items
	}()
	wg.Wait()

	if dirsErr != nil {
		return dirsErr
	}
	if filesErr != nil {
		return filesErr
	}

	c.debugLog("[115API] 并发拉取完成: 目录%d个, 文件%d个, 耗时%v\n", len(rawDirs), len(rawFiles), time.Since(fetchStart).Round(time.Millisecond))

	// 2. 构建目录 map
	type dirInfo struct {
		ID       string
		Name     string
		ParentID string
	}
	dirs := make(map[string]*dirInfo, len(rawDirs)+1)
	dirs[rootCid] = &dirInfo{ID: rootCid, Name: "", ParentID: ""}
	for i := range rawDirs {
		d := &rawDirs[i]
		dirs[d.Fid] = &dirInfo{ID: d.Fid, Name: d.Fn, ParentID: d.Pid}
	}

	// 3. 构建目录路径缓存
	dirPaths := make(map[string]string, len(dirs))
	dirPaths[rootCid] = rootPath

	var getDirPath func(id string) string
	getDirPath = func(id string) string {
		if p, ok := dirPaths[id]; ok {
			return p
		}
		d, ok := dirs[id]
		if !ok {
			return rootPath
		}
		parentPath := getDirPath(d.ParentID)
		fullPath := parentPath + "/" + d.Name
		dirPaths[id] = fullPath
		return fullPath
	}
	for id := range dirs {
		getDirPath(id)
	}

	// 4. 回调所有目录（除根目录）
	for id, d := range dirs {
		if id == rootCid {
			continue
		}
		parentPath := getDirPath(d.ParentID)
		fullPath := dirPaths[id]
		if err := callback(&FileInfo115{
			Cid:   id,
			Name:  d.Name,
			IsDir: true,
		}, fullPath, parentPath); err != nil {
			return err
		}
	}

	// 5. 批量获取文件名（/files/file，已有并发）
	type fileEntry struct {
		Pc  string
		Pid string
		Fs  int64
		Fid string
	}
	allFiles := make([]fileEntry, len(rawFiles))
	fids := make([]string, len(rawFiles))
	for i := range rawFiles {
		f := &rawFiles[i]
		fid := pickcodeToID(f.Pc)
		fidStr := strconv.FormatInt(fid, 10)
		allFiles[i] = fileEntry{Pc: f.Pc, Pid: f.Pid, Fs: f.Fs, Fid: fidStr}
		fids[i] = fidStr
	}
	batchStart := time.Now()
	nameMap := c.batchGetFileNames(fids, cookie)
	c.debugLog("[115API] batchGetFileNames完成: %d个文件名, 耗时%v\n", len(nameMap), time.Since(batchStart).Round(time.Millisecond))

	// 6. 回调所有文件
	for _, f := range allFiles {
		name := f.Pc
		sha1 := ""
		if info, ok := nameMap[f.Fid]; ok {
			name = info.Name
			sha1 = info.Sha1
		}
		parentPath := getDirPath(f.Pid)
		fullPath := parentPath + "/" + name
		if err := callback(&FileInfo115{
			Cid:      f.Fid,
			Name:     name,
			Size:     f.Fs,
			PickCode: f.Pc,
			IsDir:    false,
			Fid:      f.Fid,
			Sha1:     sha1,
		}, fullPath, parentPath); err != nil {
			return err
		}
	}

	return nil
}

// batchGetFileNames 批量获取文件名（通过 fs_file_skim API，并发请求）
func (c *Driver115Client) batchGetFileNames(fids []string, cookie string) map[string]struct{ Name, Sha1 string } {
	result := make(map[string]struct{ Name, Sha1 string })
	if len(fids) == 0 {
		return result
	}

	// 每批最多200个
	batchSize := 10000
	var batches [][]string
	for i := 0; i < len(fids); i += batchSize {
		end := i + batchSize
		if end > len(fids) {
			end = len(fids)
		}
		batches = append(batches, fids[i:end])
	}

	c.debugLog("[115API] batchGetFileNames: %d个文件, 分%d批, 并发请求\n", len(fids), len(batches))

	// 并发请求（最多10个goroutine，提高并发度）
	type batchResult struct {
		data map[string]struct{ Name, Sha1 string }
		err  error
	}
	resultCh := make(chan batchResult, len(batches))
	var wg sync.WaitGroup
	sem := make(chan struct{}, 5) // 并发限制，通过QPS调节实际速率

	for batchIdx, batch := range batches {
		wg.Add(1)
		sem <- struct{}{}
		go func(batch []string, idx int) {
			defer func() {
				<-sem
				wg.Done()
			}()
			br := batchResult{data: make(map[string]struct{ Name, Sha1 string })}

			params := "file_id=" + strings.Join(batch, ",")

			apiURL := "https://webapi.115.com/files/file"
			req, err := http.NewRequest("POST", apiURL, strings.NewReader(params))
			if err != nil {
				br.err = err
				resultCh <- br
				return
			}
			req.Header.Set("Cookie", cookie)
			req.Header.Set("User-Agent", c.userAgent)
			req.Header.Set("Content-Type", "application/x-www-form-urlencoded")

			resp, err := c.doRequest(req)
			if err != nil {
				br.err = err
				resultCh <- br
				return
			}
			body, _ := io.ReadAll(resp.Body)
			resp.Body.Close()

			var skimResp struct {
				State bool `json:"state"`
				Data  []struct {
					FileID   string `json:"file_id"`
					FileName string `json:"file_name"`
					Sha1     string `json:"sha1"`
				} `json:"data"`
			}
			if err := json.Unmarshal(body, &skimResp); err != nil || !skimResp.State {
				debugBody := string(body)
				if len(debugBody) > 500 {
					debugBody = debugBody[:500]
				}
				c.debugLog("[115API] batchGetFileNames批次%d失败: err=%v, state=%v, 响应=%s\n", idx, err, skimResp.State, debugBody)
				br.err = fmt.Errorf("批次%d失败", idx)
				resultCh <- br
				return
			}

			// 每10批输出一次进度
			if idx%10 == 0 {
				c.debugLog("[115API] batchGetFileNames进度: %d/%d批\n", idx+1, len(batches))
			}

			// 调试：第一批输出前3个结果
			if idx == 0 && len(skimResp.Data) > 0 {
				for i := 0; i < 3 && i < len(skimResp.Data); i++ {
					c.debugLog("[115API] batchGetFileNames样本[%d]: file_id=%s, file_name=%s\n", i, skimResp.Data[i].FileID, skimResp.Data[i].FileName)
				}
			}

			for _, item := range skimResp.Data {
				br.data[item.FileID] = struct{ Name, Sha1 string }{Name: item.FileName, Sha1: item.Sha1}
			}
			resultCh <- br
		}(batch, batchIdx)
	}

	// 等待所有goroutine完成
	go func() {
		wg.Wait()
		close(resultCh)
	}()

	// 收集结果
	successCount := 0
	failCount := 0
	for br := range resultCh {
		if br.err != nil {
			failCount++
		} else {
			successCount++
		}
		for k, v := range br.data {
			result[k] = v
		}
	}

	c.debugLog("[115API] batchGetFileNames完成: 成功%d批, 失败%d批, 获取%d个文件名\n", successCount, failCount, len(result))

	return result
}

// walkDir115Recursive 递归遍历目录
func (c *Driver115Client) walkDir115Recursive(cid string, currentPath string, cooldown int, callback func(item *FileInfo115, fullPath string, parentPath string) error) error {
	if cooldown > 0 {
		time.Sleep(time.Duration(cooldown) * time.Millisecond)
	}

	// 分页列出目录内容
	offset := 0
	pageSize := 1000
	for {
		files, err := c.listDirPaged(cid, offset, pageSize)
		if err != nil {
			return fmt.Errorf("列出目录 %s 失败: %v", currentPath, err)
		}

		for _, f := range files {
			fullPath := currentPath + "/" + f.Name

			if err := callback(f, fullPath, currentPath); err != nil {
				return err
			}

			// 如果是目录，递归遍历
			if f.IsDir {
				if err := c.walkDir115Recursive(f.Cid, fullPath, cooldown, callback); err != nil {
					return err
				}
			}
		}

		// 如果返回的文件数小于pageSize，说明已经遍历完
		if len(files) < pageSize {
			break
		}
		offset += pageSize
	}

	return nil
}

// listDirPaged 分页列出目录下的文件
func (c *Driver115Client) listDirPaged(cid string, offset, limit int) ([]*FileInfo115, error) {
	c.mu.RLock()
	cookie := c.cookie
	c.mu.RUnlock()

	apiURL := fmt.Sprintf("https://webapi.115.com/files?aid=1&cid=%s&o=user_ptime&asc=0&offset=%d&show_dir=1&limit=%d&snap=0&natsort=1&format=json", cid, offset, limit)

	req, err := http.NewRequest("GET", apiURL, nil)
	if err != nil {
		return nil, err
	}

	req.Header.Set("Cookie", cookie)
	req.Header.Set("User-Agent", c.userAgent)

	resp, err := c.doRequest(req)
	if err != nil {
		return nil, err
	}
	defer resp.Body.Close()

	body, err := io.ReadAll(resp.Body)
	if err != nil {
		return nil, err
	}

	c.debugLog("[115API] listDirPaged响应: %s\n", string(body)[:min(500, len(body))])

	var result struct {
		State bool `json:"state"`
		Data  []struct {
			Cid      string `json:"cid"` // 目录ID
			Fid      string `json:"fid"` // 文件ID
			Name     string `json:"n"`   // 文件名
			Size     int64  `json:"s"`   // 文件大小
			PickCode string `json:"pc"`  // pickcode
			Sha1     string `json:"sha"` // SHA1
			Pid      string `json:"pid"` // 父目录ID
		} `json:"data"`
		Msg string `json:"error"`
	}

	if err := json.Unmarshal(body, &result); err != nil {
		return nil, fmt.Errorf("解析响应失败: %v", err)
	}

	if !result.State {
		return nil, fmt.Errorf("列出目录失败: %s", result.Msg)
	}

	var files []*FileInfo115
	for _, item := range result.Data {
		f := &FileInfo115{
			Name:     item.Name,
			Size:     item.Size,
			PickCode: item.PickCode,
			Fid:      item.Fid,
			Sha1:     item.Sha1,
		}
		if item.Cid != "" && item.Fid == "" {
			f.IsDir = true
			f.Cid = item.Cid
		} else {
			f.IsDir = false
			f.Cid = item.Fid
		}
		files = append(files, f)
	}

	return files, nil
}

// GetFileInfo115 通过路径获取单个文件的115信息
func (c *Driver115Client) GetFileInfo115(path115 string) (*FileInfo115, error) {
	cleanPath := strings.Trim(path115, "/")
	parts := strings.Split(cleanPath, "/")
	if len(parts) == 0 {
		return nil, fmt.Errorf("无效路径")
	}

	fileName := parts[len(parts)-1]

	var parentCid string
	if len(parts) == 1 {
		parentCid = "0"
	} else {
		dirPath := "/" + strings.Join(parts[:len(parts)-1], "/")
		cid, err := c.getDirIDByPath(dirPath)
		if err != nil {
			cid, err = c.walkDirPath(parts[:len(parts)-1])
			if err != nil {
				return nil, fmt.Errorf("获取父目录失败: %v", err)
			}
		}
		parentCid = cid
	}

	files, err := c.listDir(parentCid)
	if err != nil {
		return nil, err
	}

	for _, f := range files {
		if f.Name == fileName {
			return f, nil
		}
	}

	return nil, fmt.Errorf("未找到文件: %s", fileName)
}

func min(a, b int) int {
	if a < b {
		return a
	}
	return b
}

func pickcodeToID(pickcode string) int64 {
	return p115PickcodeToID(pickcode)
}

// GetLifeEvents 获取115生活事件
func (c *Driver115Client) GetLifeEvents(fromTime, fromID int64) ([]model.LifeEvent, error) {
	c.mu.RLock()
	cookie := c.cookie
	c.mu.RUnlock()

	apiURL := "https://proapi.115.com/android/behavior/detail?limit=1000&offset=0"

	req, err := http.NewRequest("GET", apiURL, nil)
	if err != nil {
		return nil, err
	}
	req.Header.Set("Cookie", cookie)
	req.Header.Set("User-Agent", c.userAgent)

	resp, err := c.doRequest(req)
	if err != nil {
		return nil, err
	}
	defer resp.Body.Close()

	body, err := io.ReadAll(resp.Body)
	if err != nil {
		return nil, err
	}

	var result struct {
		State bool `json:"state"`
		Data  struct {
			Count    string `json:"count"`
			NextPage bool   `json:"next_page"`
			List     []struct {
				ID           string `json:"id"`
				Type         int    `json:"type"`
				FileID       string `json:"file_id"`
				ParentID     string `json:"parent_id"`
				FileName     string `json:"file_name"`
				FileCategory int    `json:"file_category"`
				FileType     int    `json:"file_type"`
				FileSize     int64  `json:"file_size"`
				SHA1         string `json:"sha1"`
				PickCode     string `json:"pick_code"`
				UpdateTime   int64  `json:"update_time"`
				CreateTime   int64  `json:"create_time"`
			} `json:"list"`
		} `json:"data"`
	}

	if err := json.Unmarshal(body, &result); err != nil {
		return nil, err
	}

	if !result.State {
		return nil, fmt.Errorf("获取生活事件失败")
	}

	events := make([]model.LifeEvent, 0)
	seen := make(map[string]bool)
	offset := 0

	for {
		for _, item := range result.Data.List {
			var id int64
			fmt.Sscanf(item.ID, "%d", &id)

			if fromID > 0 && id <= fromID {
				return events, nil
			}
			if fromTime > 0 && item.UpdateTime < fromTime {
				return events, nil
			}

			if !seen[item.FileID] {
				events = append(events, model.LifeEvent{
					ID:           id,
					Type:         item.Type,
					FileID:       item.FileID,
					ParentID:     item.ParentID,
					FileName:     item.FileName,
					FileCategory: item.FileCategory,
					FileType:     item.FileType,
					FileSize:     item.FileSize,
					SHA1:         item.SHA1,
					PickCode:     item.PickCode,
					UpdateTime:   item.UpdateTime,
					CreateTime:   item.CreateTime,
				})
				seen[item.FileID] = true
			}
		}

		if !result.Data.NextPage {
			break
		}

		offset += len(result.Data.List)
		apiURL = fmt.Sprintf("https://proapi.115.com/android/behavior/detail?limit=1000&offset=%d", offset)
		req, _ = http.NewRequest("GET", apiURL, nil)
		req.Header.Set("Cookie", cookie)
		req.Header.Set("User-Agent", c.userAgent)

		resp, err = c.doRequest(req)
		if err != nil {
			break
		}
		body, _ = io.ReadAll(resp.Body)
		resp.Body.Close()

		if err := json.Unmarshal(body, &result); err != nil || !result.State {
			break
		}
	}

	return events, nil
}
