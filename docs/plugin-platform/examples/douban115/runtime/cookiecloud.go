package main

import (
	"crypto/aes"
	"crypto/cipher"
	"crypto/md5"
	"encoding/base64"
	"encoding/hex"
	"encoding/json"
	"errors"
	"fmt"
	"net/url"
	"strings"
	"time"
)

// CookieCloud 端到端加密数据解密与豆瓣 Cookie 提取。
//
// CookieCloud 官方算法（CryptoJS OpenSSL 格式）：
//   - key = md5(uuid + "-" + password) 十六进制前 16 位作为 passphrase 字符串；
//   - 密文 = base64("Salted__" + salt[8] + AES-256-CBC(ciphertext))，
//     key/iv 由 EVP_BytesToKey(MD5, passphrase, salt, keyLen=32, ivLen=16) 派生。
// 兼容路径：若数据不是 Salted__ 前缀，则尝试 AES-128-GCM（nonce 12B 前置 + tag 16B 后置）。

type cookieCloudItem struct {
	Name   string `json:"name"`
	Value  string `json:"value"`
	Domain string `json:"domain"`
	Path   string `json:"path"`
}

type cookieCloudPayload struct {
	CookieData map[string][]cookieCloudItem `json:"cookie_data"`
}

func md5Hex(parts ...string) string {
	h := md5.Sum([]byte(strings.Join(parts, "")))
	return hex.EncodeToString(h[:])
}

// evpKDF 实现 OpenSSL EVP_BytesToKey（MD5，1 次迭代）。
func evpKDF(pass, salt []byte, keyLen, ivLen int) (key, iv []byte) {
	total := keyLen + ivLen
	var d []byte
	prev := []byte{}
	for len(d) < total {
		h := md5.New()
		h.Write(prev)
		h.Write(pass)
		h.Write(salt)
		prev = h.Sum(nil)
		d = append(d, prev...)
	}
	return d[:keyLen], d[keyLen : keyLen+ivLen]
}

func pkcs7Unpad(data []byte) []byte {
	if len(data) == 0 {
		return data
	}
	pad := int(data[len(data)-1])
	if pad <= 0 || pad > aes.BlockSize || pad > len(data) {
		return data
	}
	for _, b := range data[len(data)-pad:] {
		if int(b) != pad {
			return data
		}
	}
	return data[:len(data)-pad]
}

// cookieCloudDecrypt 解密 CookieCloud 的 encrypted 字段，返回明文 JSON。
func cookieCloudDecrypt(uuid, password, encryptedB64 string) ([]byte, error) {
	if strings.TrimSpace(uuid) == "" || strings.TrimSpace(password) == "" {
		return nil, errors.New("CookieCloud UUID 或密码为空")
	}
	passphrase := md5Hex(uuid, "-", password)[:16]
	data, err := base64.StdEncoding.DecodeString(strings.TrimSpace(encryptedB64))
	if err != nil {
		return nil, fmt.Errorf("encrypted 字段 base64 解码失败：%w", err)
	}
	if len(data) > 8 && string(data[:8]) == "Salted__" {
		// CryptoJS OpenSSL 格式
		if len(data) < 8+16+aes.BlockSize {
			return nil, errors.New("加密数据长度异常")
		}
		salt := data[8:16]
		body := data[16:]
		if len(body)%aes.BlockSize != 0 {
			return nil, errors.New("加密数据不是 AES 块对齐")
		}
		key, iv := evpKDF([]byte(passphrase), salt, 32, aes.BlockSize)
		block, err := aes.NewCipher(key)
		if err != nil {
			return nil, err
		}
		out := make([]byte, len(body))
		cipher.NewCBCDecrypter(block, iv).CryptBlocks(out, body)
		return pkcs7Unpad(out), nil
	}
	// 备用格式：AES-128-GCM，key=passphrase 的 16 字节，nonce=前 12 字节，tag=后 16 字节
	if len(data) < 12+16 {
		return nil, errors.New("无法识别的 CookieCloud 加密格式")
	}
	block, err := aes.NewCipher([]byte(passphrase))
	if err != nil {
		return nil, err
	}
	gcm, err := cipher.NewGCM(block)
	if err != nil {
		return nil, err
	}
	nonce, body, tag := data[:12], data[12:len(data)-16], data[len(data)-16:]
	out, err := gcm.Open(nil, nonce, append(body, tag...), nil)
	if err != nil {
		return nil, fmt.Errorf("CookieCloud 解密失败（密码错误或格式不支持）：%w", err)
	}
	return out, nil
}

// buildDoubanCookie 从解密后的 payload 中提取豆瓣域 Cookie 字符串。
func buildDoubanCookie(plain []byte) (string, int, error) {
	var payload cookieCloudPayload
	if err := json.Unmarshal(plain, &payload); err != nil {
		return "", 0, fmt.Errorf("解密数据不是有效 JSON：%w", err)
	}
	pairs := make([]string, 0, 16)
	for domain, items := range payload.CookieData {
		dl := strings.ToLower(domain)
		if !strings.Contains(dl, "douban.com") {
			continue
		}
		for _, it := range items {
			if it.Name == "" {
				continue
			}
			pairs = append(pairs, it.Name+"="+it.Value)
		}
	}
	if len(pairs) == 0 {
		return "", 0, nil
	}
	return strings.Join(pairs, "; "), len(pairs), nil
}

// defaultCloudPath 是 dian115 内置 CookieCloud 服务的默认路径前缀。
const defaultCloudPath = "/cookiecloud"

// cloudCandidates 生成 CookieCloud 候选地址：用户配置优先，其次补齐本机常见
// 主机名/端口变体（这些地址已在 manifest 的 network 权限中声明为直连）。
func cloudCandidates(rawURL string) []string {
	seen := map[string]bool{}
	out := make([]string, 0, 6)
	add := func(u string) {
		u = strings.TrimRight(strings.TrimSpace(u), "/")
		if u == "" || seen[u] {
			return
		}
		seen[u] = true
		out = append(out, u)
	}
	add(rawURL)
	u, err := url.Parse(strings.TrimSpace(rawURL))
	if err != nil {
		return out
	}
	host := u.Hostname()
	if host != "127.0.0.1" && host != "localhost" && host != "::1" {
		return out // 非本机地址不做猜测，避免请求计划外的目标
	}
	path := strings.TrimRight(u.Path, "/")
	if path == "" {
		path = defaultCloudPath
	}
	port := u.Port()
	hosts := []string{"127.0.0.1", "localhost"}
	ports := []string{port, "3000", "8088", "8080"}
	for _, h := range hosts {
		for _, p := range ports {
			if p == "" {
				add(fmt.Sprintf("http://%s%s", h, path))
			} else {
				add(fmt.Sprintf("http://%s:%s%s", h, p, path))
			}
		}
	}
	return out
}

// syncCookieCloud 从 CookieCloud 拉取并解密数据，返回豆瓣 Cookie 字符串。
// 依次尝试候选地址（配置地址优先），任一成功即返回；全程写插件日志便于排查。
func (r *runtime) syncCookieCloud() (string, int, error) {
	cfg := r.currentConfig()
	if strings.TrimSpace(cfg.CloudURL) == "" || !strings.HasPrefix(strings.TrimSpace(cfg.CloudURL), "http") {
		return "", 0, errors.New("未配置 CookieCloud 服务器地址")
	}
	if strings.TrimSpace(cfg.CloudUUID) == "" || strings.TrimSpace(cfg.CloudPasscode) == "" {
		return "", 0, errors.New("未配置 CookieCloud UUID 或密码")
	}
	var lastErr error
	for _, base := range cloudCandidates(cfg.CloudURL) {
		target := base + "/get/" + cfg.CloudUUID
		r.log("info", "CookieCloud 拉取开始", map[string]any{"url": target})
		start := time.Now()
		status, body, err := r.httpGet(target, map[string]string{"accept": "application/json"})
		ms := time.Since(start).Milliseconds()
		if err != nil {
			r.log("warning", "CookieCloud 请求失败", map[string]any{"url": target, "ms": ms, "error": err.Error()})
			lastErr = fmt.Errorf("请求 %s 失败（%dms）：%v", target, ms, err)
			continue
		}
		if status != 200 {
			r.log("warning", "CookieCloud 返回异常", map[string]any{"url": target, "status": status, "ms": ms})
			lastErr = fmt.Errorf("CookieCloud 返回 HTTP %d（%s）", status, target)
			continue
		}
		r.log("info", "CookieCloud 拉取成功", map[string]any{"url": target, "ms": ms, "bytes": len(body)})
		var resp struct {
			Encrypted string `json:"encrypted"`
		}
		if err := json.Unmarshal(body, &resp); err != nil || resp.Encrypted == "" {
			lastErr = fmt.Errorf("%s 响应缺少 encrypted 字段", target)
			continue
		}
		plain, err := cookieCloudDecrypt(cfg.CloudUUID, cfg.CloudPasscode, resp.Encrypted)
		if err != nil {
			// 解密失败与地址无关，换地址也不会好，直接返回。
			return "", 0, err
		}
		cookie, count, err := buildDoubanCookie(plain)
		if err != nil {
			return "", 0, err
		}
		if cookie == "" {
			return "", 0, errors.New("CookieCloud 数据中没有豆瓣域的 Cookie（请确认浏览器扩展已同步豆瓣）")
		}
		return cookie, count, nil
	}
	if lastErr == nil {
		lastErr = errors.New("没有可用的 CookieCloud 地址")
	}
	return "", 0, lastErr
}

// runCloudSync 由常驻实例执行：拉取豆瓣 Cookie 并写回配置。
// 返回给界面的结果行。
func (r *runtime) runCloudSync() []string {
	cfg := r.currentConfig()
	cookie, count, err := r.syncCookieCloud()
	if err != nil {
		r.log("warning", "CookieCloud 同步失败", map[string]any{"error": err.Error()})
		return []string{"CookieCloud 同步失败：" + err.Error()}
	}
	cfg.DoubanCookie = cookie
	r.mu.Lock()
	r.config = cfg
	r.mu.Unlock()
	if err := r.storagePut(storageConfig, cfg); err != nil {
		return []string{"已获取 Cookie 但保存失败：" + err.Error()}
	}
	r.log("info", "CookieCloud 同步完成", map[string]any{"cookies": count})
	return []string{fmt.Sprintf("已从 CookieCloud 获取 %d 条豆瓣 Cookie 并保存", count)}
}
