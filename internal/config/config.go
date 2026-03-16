package config

import (
	"os"
	"strconv"
)

// Config 主配置结构（只包含服务端口，其他配置从数据库读取）
type Config struct {
	Server   ServerConfig   `json:"server"`
	Database DatabaseConfig `json:"database"`
	// 以下配置从数据库动态读取，这里只是结构定义
	CloudDrive2 CloudDrive2Config `json:"clouddrive2"`
	Driver115   Driver115Config   `json:"driver_115"`
	Emby        EmbyConfig        `json:"emby"`
}

// ServerConfig 服务器配置
type ServerConfig struct {
	Host     string `json:"host"`
	Port     int    `json:"port"`
	EmbyPort int    `json:"emby_port"` // Emby代理端口
}

// CloudDrive2Config CD2配置
type CloudDrive2Config struct {
	Host        string `json:"host"`
	Username    string `json:"username"`
	Password    string `json:"password"`
	APIToken    string `json:"api_token"`     // API Token (与用户名密码二选一)
	UseAPIToken bool   `json:"use_api_token"` // 是否使用 API Token 认证
	MountPrefix string `json:"mount_prefix"`  // 115在CD2中的挂载路径前缀
}

// Driver115Config 115配置
type Driver115Config struct {
	Cookie    string `json:"cookie"`
	UserAgent string `json:"user_agent"`
}

// EmbyConfig Emby配置
type EmbyConfig struct {
	Host   string `json:"host"`
	APIKey string `json:"api_key"`
}

// DatabaseConfig 数据库配置
type DatabaseConfig struct {
	Path string `json:"path"`
}

// LoadFromEnv 从环境变量加载配置
func LoadFromEnv() *Config {
	cfg := &Config{
		Server: ServerConfig{
			Host:     getEnv("SERVER_HOST", "0.0.0.0"),
			Port:     getEnvInt("SERVER_PORT", 8095),
			EmbyPort: getEnvInt("EMBY_PROXY_PORT", 8098),
		},
		Database: DatabaseConfig{
			Path: getEnv("DATABASE_PATH", "/app/data/strm.db"),
		},
	}
	return cfg
}

// getEnv 获取环境变量，如果不存在则返回默认值
func getEnv(key, defaultValue string) string {
	if value := os.Getenv(key); value != "" {
		return value
	}
	return defaultValue
}

// getEnvInt 获取整数环境变量
func getEnvInt(key string, defaultValue int) int {
	if value := os.Getenv(key); value != "" {
		if intVal, err := strconv.Atoi(value); err == nil {
			return intVal
		}
	}
	return defaultValue
}
