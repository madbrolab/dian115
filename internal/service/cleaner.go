package service

import (
	"log"
	"os"
	"path/filepath"
	"strings"

	"strm-manager/internal/model"
)

// 元数据文件扩展名
var metaExtensions = map[string]bool{
	".nfo": true, ".jpg": true, ".jpeg": true, ".png": true,
	".bmp": true, ".gif": true, ".webp": true, ".thumb": true,
	".srt": true, ".ass": true, ".ssa": true, ".sub": true,
	".idx": true, ".sup": true, ".vtt": true,
}

// CleanerService 清理服务
type CleanerService struct {
	logger *LoggerService
}

// NewCleanerService 创建清理服务
func NewCleanerService() *CleanerService {
	return &CleanerService{}
}

// SetLogger 设置日志服务
func (c *CleanerService) SetLogger(logger *LoggerService) {
	c.logger = logger
}

// CleanSTRM 删除STRM文件
func (c *CleanerService) CleanSTRM(strmPath string) error {
	if strmPath == "" {
		return nil
	}
	if _, err := os.Stat(strmPath); os.IsNotExist(err) {
		return nil // 文件不存在，无需删除
	}
	if err := os.Remove(strmPath); err != nil {
		return err
	}
	log.Printf("[Cleaner] 已删除STRM文件: %s", strmPath)
	return nil
}

// GetMetaExtensions 获取规则的元数据后缀列表
func (c *CleanerService) GetMetaExtensions(rule *model.STRMRule) map[string]bool {
	if rule.MetaExtensions != "" {
		exts := make(map[string]bool)
		for _, ext := range strings.Split(rule.MetaExtensions, ",") {
			ext = strings.TrimSpace(strings.ToLower(ext))
			if ext != "" {
				if !strings.HasPrefix(ext, ".") {
					ext = "." + ext
				}
				exts[ext] = true
			}
		}
		if len(exts) > 0 {
			return exts
		}
	}
	return metaExtensions // 默认
}

// CleanMetadata 删除同名元数据文件
// 查找同目录下同文件名（不含扩展名）的元数据文件
func (c *CleanerService) CleanMetadata(strmPath string) ([]string, error) {
	return c.CleanMetadataWithExts(strmPath, metaExtensions)
}

// CleanMetadataWithRule 使用规则配置的元数据后缀删除同名元数据文件
func (c *CleanerService) CleanMetadataWithRule(strmPath string, rule *model.STRMRule) ([]string, error) {
	return c.CleanMetadataWithExts(strmPath, c.GetMetaExtensions(rule))
}

// CleanMetadataWithExts 删除同名元数据文件（指定后缀）
func (c *CleanerService) CleanMetadataWithExts(strmPath string, exts map[string]bool) ([]string, error) {
	if strmPath == "" {
		return nil, nil
	}

	dir := filepath.Dir(strmPath)
	baseName := strings.TrimSuffix(filepath.Base(strmPath), ".strm")

	var deleted []string

	entries, err := os.ReadDir(dir)
	if err != nil {
		if os.IsNotExist(err) {
			return nil, nil
		}
		return nil, err
	}

	for _, entry := range entries {
		if entry.IsDir() {
			continue
		}
		name := entry.Name()
		ext := strings.ToLower(filepath.Ext(name))
		nameWithoutExt := strings.TrimSuffix(name, filepath.Ext(name))

		// 匹配同名文件且是元数据扩展名
		if nameWithoutExt == baseName && exts[ext] {
			fullPath := filepath.Join(dir, name)
			if err := os.Remove(fullPath); err != nil {
				log.Printf("[Cleaner] 删除元数据文件失败: %s - %v", fullPath, err)
				continue
			}
			deleted = append(deleted, fullPath)
			log.Printf("[Cleaner] 已删除元数据文件: %s", fullPath)
		}
	}

	return deleted, nil
}

// CleanEmptyDirs 递归清理空父目录
// maxDepth: 最大向上递归深度
// safePath: 安全路径（不会删除此路径及其上级）
func (c *CleanerService) CleanEmptyDirs(dirPath string, maxDepth int, safePath string) ([]string, error) {
	if dirPath == "" || maxDepth <= 0 {
		return nil, nil
	}

	var deleted []string
	currentDir := dirPath

	for i := 0; i < maxDepth; i++ {
		// 安全检查：不删除安全路径本身
		if currentDir == safePath || currentDir == "/" || currentDir == "." {
			break
		}

		// 检查目录是否为空
		entries, err := os.ReadDir(currentDir)
		if err != nil {
			if os.IsNotExist(err) {
				currentDir = filepath.Dir(currentDir)
				continue
			}
			break
		}

		if len(entries) > 0 {
			break // 目录非空，停止
		}

		// 删除空目录
		if err := os.Remove(currentDir); err != nil {
			log.Printf("[Cleaner] 删除空目录失败: %s - %v", currentDir, err)
			break
		}

		deleted = append(deleted, currentDir)
		log.Printf("[Cleaner] 已删除空目录: %s", currentDir)

		// 向上一级
		currentDir = filepath.Dir(currentDir)
	}

	return deleted, nil
}

// CleanAll 根据规则配置执行完整清理
// 智能清理开启时：删除STRM + 元数据 + 智能清理目录
// 智能清理关闭时：不做任何清理
func (c *CleanerService) CleanAll(rule *model.STRMRule, strmPath string) (string, error) {
	if strmPath == "" {
		return "", nil
	}

	if !rule.SmartClean {
		// 智能清理未开启，不做任何清理
		return filepath.Dir(strmPath), nil
	}

	return c.SmartCleanFile(rule, strmPath)
}

// SmartCleanFile 智能清理单个文件：删除STRM + 元数据，如果目录无其他strm则清空目录，向上清理空目录
// 返回最后存在的父目录路径（用于Emby刷新）
func (c *CleanerService) SmartCleanFile(rule *model.STRMRule, strmPath string) (string, error) {
	// 1. 删除STRM文件
	c.CleanSTRM(strmPath)

	// 2. 删除同名元数据文件（使用规则配置的后缀）
	c.CleanMetadataWithRule(strmPath, rule)

	// 3. 检查同目录是否还有其他 .strm 文件
	dir := filepath.Dir(strmPath)
	hasOtherStrm := c.dirHasSTRM(dir)

	if !hasOtherStrm {
		// 没有其他strm文件 → 清空整个目录（RemoveAll）
		if err := os.RemoveAll(dir); err != nil {
			log.Printf("[Cleaner] 清空目录失败: %s - %v", dir, err)
			return dir, nil
		}
		log.Printf("[Cleaner] 已清空无STRM目录: %s", dir)
		// 向上清理空父目录（到 OutputPath 停），返回最后存在的目录
		return c.cleanEmptyParents(filepath.Dir(dir), rule.OutputPath), nil
	}

	return dir, nil
}

// SmartCleanDirectory 智能清理目录：直接删除对应的STRM输出目录，向上清理空目录
// 返回最后存在的父目录路径（用于Emby刷新）
func (c *CleanerService) SmartCleanDirectory(rule *model.STRMRule, strmDirPath string) (string, error) {
	if strmDirPath == "" || strmDirPath == rule.OutputPath {
		return "", nil
	}

	// 直接删除整个目录
	if err := os.RemoveAll(strmDirPath); err != nil {
		log.Printf("[Cleaner] 删除STRM目录失败: %s - %v", strmDirPath, err)
		return "", err
	}
	log.Printf("[Cleaner] 已删除STRM目录: %s", strmDirPath)

	// 清理父目录中的季元数据
	c.cleanSeasonMetadata(filepath.Dir(strmDirPath), filepath.Base(strmDirPath))

	// 向上清理空父目录，返回最后存在的目录
	return c.cleanEmptyParents(filepath.Dir(strmDirPath), rule.OutputPath), nil
}

// cleanSeasonMetadata 清理父目录中的季元数据文件
func (c *CleanerService) cleanSeasonMetadata(parentDir, dirName string) {
	entries, err := os.ReadDir(parentDir)
	if err != nil {
		return
	}

	dirNameLower := strings.ToLower(dirName)
	altName := c.normalizeSeasonName(dirNameLower)

	for _, entry := range entries {
		if entry.IsDir() {
			continue
		}
		nameWithoutExt := strings.TrimSuffix(strings.ToLower(entry.Name()), filepath.Ext(entry.Name()))
		if nameWithoutExt == dirNameLower || strings.HasPrefix(nameWithoutExt, dirNameLower+"-") ||
			(altName != "" && (nameWithoutExt == altName || strings.HasPrefix(nameWithoutExt, altName+"-"))) {
			filePath := filepath.Join(parentDir, entry.Name())
			os.Remove(filePath)
			log.Printf("[Cleaner] 已删除目录元数据: %s", filePath)
		}
	}
}

// normalizeSeasonName 标准化季名称（Season 1 -> season01, S01 -> season01）
func (c *CleanerService) normalizeSeasonName(name string) string {
	name = strings.ToLower(strings.TrimSpace(name))
	if strings.HasPrefix(name, "season ") {
		num := strings.TrimPrefix(name, "season ")
		if len(num) == 1 && num >= "0" && num <= "9" {
			return "season0" + num
		}
	} else if strings.HasPrefix(name, "s") && len(name) <= 3 {
		num := strings.TrimPrefix(name, "s")
		if len(num) == 1 && num >= "0" && num <= "9" {
			return "season0" + num
		} else if len(num) == 2 {
			return "season" + num
		}
	}
	return ""
}

// dirHasSTRM 检查目录中是否还有 .strm 文件
func (c *CleanerService) dirHasSTRM(dir string) bool {
	entries, err := os.ReadDir(dir)
	if err != nil {
		return false
	}
	for _, entry := range entries {
		if !entry.IsDir() && strings.ToLower(filepath.Ext(entry.Name())) == ".strm" {
			return true
		}
	}
	return false
}

// cleanEmptyParents 向上清理空父目录，到 safePath 停止
// 返回最后存在的目录路径（第一个非空目录或 safePath）
func (c *CleanerService) cleanEmptyParents(dir string, safePath string) string {
	for {
		if dir == safePath || dir == "/" || dir == "." || dir == "" {
			return dir
		}
		// 规范化路径比较
		absDir, _ := filepath.Abs(dir)
		absSafe, _ := filepath.Abs(safePath)
		if absDir == absSafe {
			return dir
		}

		entries, err := os.ReadDir(dir)
		if err != nil {
			return dir
		}

		// 检查是否有.strm文件、视频文件或子目录
		hasImportantFile := false
		videoExts := map[string]bool{".mp4": true, ".mkv": true, ".avi": true, ".mov": true, ".wmv": true, ".flv": true, ".webm": true, ".m4v": true, ".ts": true}
		for _, entry := range entries {
			if entry.IsDir() {
				hasImportantFile = true
				break
			}
			ext := strings.ToLower(filepath.Ext(entry.Name()))
			if ext == ".strm" || videoExts[ext] {
				hasImportantFile = true
				break
			}
		}
		if hasImportantFile {
			return dir
		}

		if err := os.Remove(dir); err != nil {
			log.Printf("[Cleaner] 删除空目录失败: %s - %v", dir, err)
			return dir
		}
		log.Printf("[Cleaner] 已删除空目录: %s", dir)
		dir = filepath.Dir(dir)
	}
}
