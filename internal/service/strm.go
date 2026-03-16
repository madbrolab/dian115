package service

import (
	"fmt"
	"log"
	"os"
	"path/filepath"
	"strings"
	"sync"
	"sync/atomic"
	"time"

	"strm-manager/internal/client"
	"strm-manager/internal/model"
	"strm-manager/internal/store"
	"strm-manager/internal/util"
)

// 视频文件扩展名
var videoExtensions = map[string]bool{
	".mp4": true, ".mkv": true, ".avi": true, ".mov": true,
	".wmv": true, ".flv": true, ".ts": true, ".m2ts": true,
	".rmvb": true, ".iso": true, ".m4v": true, ".webm": true,
	".rm": true, ".mpg": true, ".mpeg": true, ".vob": true,
	".3gp": true, ".asf": true, ".divx": true, ".f4v": true,
	".mts": true, ".tp": true, ".trp": true, ".ogv": true,
}

// strmWorkerCount 并发生成STRM的worker数量
const strmWorkerCount = 20

// STRMService STRM生成服务
type STRMService struct {
	store       *store.Store
	cd2         *client.CloudDriveClient
	treeSvc     *TreeService
	cleanerSvc  *CleanerService
	embySvc     *EmbyProxyService
	mountPrefix string         // CD2挂载前缀
	logger      *LoggerService // 日志服务
}

// NewSTRMService 创建STRM服务
func NewSTRMService(store *store.Store, cd2 *client.CloudDriveClient, mountPrefix string) *STRMService {
	return &STRMService{
		store:       store,
		cd2:         cd2,
		mountPrefix: mountPrefix,
		cleanerSvc:  NewCleanerService(),
	}
}

// SetLogger 设置日志服务
func (s *STRMService) SetLogger(logger *LoggerService) {
	s.logger = logger
}

// SetCD2 热更新CD2客户端
func (s *STRMService) SetCD2(cd2 *client.CloudDriveClient) {
	s.cd2 = cd2
}

// SetMountPrefix 热更新挂载前缀
func (s *STRMService) SetMountPrefix(mountPrefix string) {
	s.mountPrefix = mountPrefix
}

// SetTreeService 设置目录树服务
func (s *STRMService) SetTreeService(treeSvc *TreeService) {
	s.treeSvc = treeSvc
}

// SetCleanerService 设置清理服务
func (s *STRMService) SetCleanerService(cleanerSvc *CleanerService) {
	s.cleanerSvc = cleanerSvc
}

// SetEmbyService 设置Emby服务
func (s *STRMService) SetEmbyService(embySvc *EmbyProxyService) {
	s.embySvc = embySvc
}

// getVideoExtensions 获取规则的视频扩展名
func (s *STRMService) getVideoExtensions(rule *model.STRMRule) map[string]bool {
	if rule.FileExtensions != "" {
		exts := make(map[string]bool)
		for _, ext := range strings.Split(rule.FileExtensions, ",") {
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
	return videoExtensions
}

// getExtensionList 获取规则的扩展名列表（用于数据库查询）
func (s *STRMService) getExtensionList(rule *model.STRMRule) []string {
	exts := s.getVideoExtensions(rule)
	list := make([]string, 0, len(exts))
	for ext := range exts {
		list = append(list, ext)
	}
	return list
}

// strmJob 单个STRM生成任务
type strmJob struct {
	node     *model.FileTreeNode
	strmPath string
	content  string
}

// concurrentGenerateSTRM 并发生成STRM文件，返回新增数和跳过数
func (s *STRMService) concurrentGenerateSTRM(
	rule *model.STRMRule,
	treeFiles []*model.FileTreeNode,
	existingSTRMs map[string]bool,
	excludeKeywords []string,
	result *SyncResult,
	task *Task,
) (newCount int, skipCount int) {
	sourcePath115 := cd2PathTo115Path(rule.SourcePath, rule.CloudName)
	mountPrefix := strings.TrimSuffix(s.mountPrefix, "/")

	// 预先计算所有需要新建的任务，跳过已存在的
	jobs := make([]strmJob, 0)
	for _, node := range treeFiles {
		if task != nil && task.IsCancelled() {
			return
		}

		// 排除关键字检查
		skip := false
		for _, keyword := range excludeKeywords {
			if strings.Contains(node.Path115, keyword) {
				skip = true
				break
			}
		}
		if skip {
			continue
		}

		relPath, err := filepath.Rel(sourcePath115, node.Path115)
		if err != nil {
			continue
		}

		ext := strings.ToLower(filepath.Ext(relPath))
		strmRelPath := strings.TrimSuffix(relPath, ext) + ".strm"
		strmPath := filepath.Join(rule.OutputPath, strmRelPath)

		// 已存在则标记跳过
		if _, exists := existingSTRMs[strmPath]; exists {
			existingSTRMs[strmPath] = true
			skipCount++
			result.Success++
			if task != nil {
				task.IncrementSynced()
			}
			if node.STRMPath == "" {
				s.store.UpdateTreeNodeSTRMPath(node.ID, strmPath)
			}
			continue
		}

		// 计算内容
		content := node.CD2Path
		if mountPrefix != "" {
			if !strings.HasPrefix(content, "/") {
				content = mountPrefix + "/" + content
			} else {
				content = mountPrefix + content
			}
		}

		jobs = append(jobs, strmJob{node: node, strmPath: strmPath, content: content})
	}

	if len(jobs) == 0 {
		return
	}

	// 并发处理新建任务
	jobCh := make(chan strmJob, len(jobs))
	for _, job := range jobs {
		jobCh <- job
	}
	close(jobCh)

	var (
		mu         sync.Mutex
		newCounter int64
		wg         sync.WaitGroup
	)

	// 进度日志：每500个新建文件记录一次
	var progressCounter int64

	workerCount := strmWorkerCount
	if len(jobs) < workerCount {
		workerCount = len(jobs)
	}

	wg.Add(workerCount)
	for i := 0; i < workerCount; i++ {
		go func() {
			defer wg.Done()
			for job := range jobCh {
				if task != nil && task.IsCancelled() {
					return
				}

				startTime := time.Now()

				if err := os.MkdirAll(filepath.Dir(job.strmPath), 0755); err != nil {
					mu.Lock()
					result.Failed++
					result.Errors = append(result.Errors, fmt.Sprintf("%s: %v", job.node.Path115, err))
					mu.Unlock()
					if task != nil {
						task.IncrementFailed()
					}
					continue
				}

				if err := os.WriteFile(job.strmPath, []byte(job.content), 0644); err != nil {
					mu.Lock()
					result.Failed++
					result.Errors = append(result.Errors, fmt.Sprintf("%s: %v", job.node.Path115, err))
					mu.Unlock()
					if task != nil {
						task.IncrementFailed()
						task.AddLog(fmt.Sprintf("❌ 创建失败: %s - %v", job.node.Name, err))
					}
					continue
				}

				elapsed := time.Since(startTime).Milliseconds()
				atomic.AddInt64(&newCounter, 1)

				mu.Lock()
				result.Success++
				mu.Unlock()

				// 更新目录树中的STRM路径
				s.store.UpdateTreeNodeSTRMPath(job.node.ID, job.strmPath)

				if task != nil {
					task.IncrementSynced()
					task.AddLog(fmt.Sprintf("✅ STRM已创建: %s 耗时:%s", job.node.Name, util.FormatMilliseconds(elapsed)))
				}
				if s.logger != nil {
					s.logger.LogSync(model.LogLevelSuccess, fmt.Sprintf("STRM已创建: %s", job.node.Name), map[string]string{
						"source": job.node.Path115,
						"target": job.strmPath,
					}, rule.ID)
				}

				// 每500个输出一次进度
				cur := atomic.AddInt64(&progressCounter, 1)
				if cur%500 == 0 && s.logger != nil {
					total := int64(len(jobs))
					s.logger.LogSync(model.LogLevelInfo, fmt.Sprintf("新建进度: %d/%d (%.1f%%)", cur, total, float64(cur)*100/float64(total)), nil, rule.ID)
				}
			}
		}()
	}

	wg.Wait()
	newCount = int(atomic.LoadInt64(&newCounter))
	return
}

// SyncRuleFromTree 从目录树生成STRM（并发版本）
func (s *STRMService) SyncRuleFromTree(rule *model.STRMRule, task *Task) (*SyncResult, error) {
	result := &SyncResult{
		RuleID:   rule.ID,
		RuleName: rule.Name,
	}

	// 确保输出目录存在
	if err := os.MkdirAll(rule.OutputPath, 0755); err != nil {
		return nil, fmt.Errorf("创建输出目录失败: %v", err)
	}

	// 1. 检查目录树是否已构建
	if !rule.TreeBuilt && s.treeSvc != nil {
		if task != nil {
			task.AddLog("🌳 目录树未构建，开始构建...")
		}
		if err := s.treeSvc.BuildTree(rule, task); err != nil {
			return nil, fmt.Errorf("构建目录树失败: %v", err)
		}
	}

	// 2. 从目录树获取文件列表（按扩展名过滤）
	extensions := s.getExtensionList(rule)
	treeFiles, err := s.store.GetTreeFilesByRule(rule.ID, extensions)
	if err != nil {
		return nil, fmt.Errorf("获取目录树文件失败: %v", err)
	}

	if task != nil {
		task.AddLog(fmt.Sprintf("📂 目录树中共 %d 个匹配文件", len(treeFiles)))
	}

	// 3. 获取已存在的STRM文件映射
	existingSTRMs := make(map[string]bool)
	filepath.Walk(rule.OutputPath, func(path string, info os.FileInfo, err error) error {
		if err != nil || info.IsDir() {
			return nil
		}
		if filepath.Ext(path) == ".strm" {
			existingSTRMs[path] = false
		}
		return nil
	})

	// 4. 解析排除关键字
	var excludeKeywords []string
	if rule.ExcludeKeys != "" {
		for _, key := range strings.Split(rule.ExcludeKeys, ",") {
			key = strings.TrimSpace(key)
			if key != "" {
				excludeKeywords = append(excludeKeywords, key)
			}
		}
	}

	// 5. 并发生成STRM
	if s.logger != nil {
		s.logger.LogSync(model.LogLevelInfo, fmt.Sprintf("开始同步: %s，共 %d 个文件（并发数: %d）", rule.Name, len(treeFiles), strmWorkerCount), nil, rule.ID)
	}

	newCount, skipCount := s.concurrentGenerateSTRM(rule, treeFiles, existingSTRMs, excludeKeywords, result, task)

	if task != nil && task.IsCancelled() {
		return result, fmt.Errorf("任务已取消")
	}

	// 6. 删除孤立的STRM文件
	orphanCount := 0
	for strmPath, processed := range existingSTRMs {
		if !processed {
			if rule.CleanStrm {
				if s.cleanerSvc != nil {
					s.cleanerSvc.CleanAll(rule, strmPath)
				} else {
					os.Remove(strmPath)
				}
			} else {
				os.Remove(strmPath)
			}
			orphanCount++
			if task != nil {
				task.AddLog(fmt.Sprintf("🗑️ 已删除失效STRM: %s", strmPath))
			}
			if s.logger != nil {
				s.logger.LogSync(model.LogLevelWarning, fmt.Sprintf("🗑️ 已删除失效STRM: %s", filepath.Base(strmPath)), map[string]string{
					"path": strmPath,
				}, rule.ID)
			}
		}
	}
	result.Deleted = orphanCount

	if task != nil {
		task.Message = fmt.Sprintf("新增: %d, 跳过: %d, 删除: %d", newCount, skipCount, orphanCount)
		task.AddLog(fmt.Sprintf("📊 同步完成: 新增 %d 个, 跳过 %d 个, 删除 %d 个", newCount, skipCount, orphanCount))
	}

	if s.logger != nil {
		s.logger.LogSync(model.LogLevelSuccess, fmt.Sprintf("同步完成: %s - 新增%d 跳过%d 删除%d", rule.Name, newCount, skipCount, orphanCount), map[string]string{
			"rule_name": rule.Name,
			"new":       fmt.Sprintf("%d", newCount),
			"skipped":   fmt.Sprintf("%d", skipCount),
			"deleted":   fmt.Sprintf("%d", orphanCount),
		}, rule.ID)
	}

	// 通知Emby刷新整个输出目录（同步完成后一次性刷新）
	if s.embySvc != nil && (newCount > 0 || orphanCount > 0) {
		if err := s.embySvc.RefreshLibraryPath(rule.OutputPath); err != nil {
			log.Printf("[STRM] 通知Emby刷新失败: %s - %v", rule.OutputPath, err)
		} else {
			if task != nil {
				task.AddLog("📢 已通知Emby刷新媒体库")
			}
		}
	}

	return result, nil
}

// SyncRule 同步单个规则
func (s *STRMService) SyncRule(rule *model.STRMRule) (*SyncResult, error) {
	return s.SyncRuleWithTask(rule, nil)
}

// SyncRuleWithTask 同步单个规则（带任务进度跟踪）
func (s *STRMService) SyncRuleWithTask(rule *model.STRMRule, task *Task) (*SyncResult, error) {
	return s.SyncRuleFromTree(rule, task)
}

// SyncAllRules 同步所有启用的规则
func (s *STRMService) SyncAllRules() ([]*SyncResult, error) {
	rules, err := s.store.GetEnabledRules()
	if err != nil {
		return nil, err
	}

	var results []*SyncResult
	for _, rule := range rules {
		result, err := s.SyncRule(rule)
		if err != nil {
			result.Errors = append(result.Errors, err.Error())
		}
		results = append(results, result)
	}

	return results, nil
}

// createSTRM 创建STRM文件（不再保存数据库映射）
func (s *STRMService) createSTRM(f *model.CD2FileInfo, strmPath string, rule *model.STRMRule) error {
	if err := os.MkdirAll(filepath.Dir(strmPath), 0755); err != nil {
		return err
	}

	content := f.Path
	if s.mountPrefix != "" {
		mountPrefix := strings.TrimSuffix(s.mountPrefix, "/")
		if !strings.HasPrefix(f.Path, "/") {
			content = mountPrefix + "/" + f.Path
		} else {
			content = mountPrefix + f.Path
		}
	}

	return os.WriteFile(strmPath, []byte(content), 0644)
}

// deleteOrphanFiles 删除孤立的STRM文件
func (s *STRMService) deleteOrphanFiles(dir string, validFiles map[string]bool) int {
	var count int
	filepath.Walk(dir, func(path string, info os.FileInfo, err error) error {
		if err != nil || info.IsDir() {
			return nil
		}
		if filepath.Ext(path) != ".strm" {
			return nil
		}
		if !validFiles[path] {
			os.Remove(path)
			count++
		}
		return nil
	})
	return count
}

// SyncResult 同步结果
type SyncResult struct {
	RuleID   int64    `json:"rule_id"`
	RuleName string   `json:"rule_name"`
	Success  int      `json:"success"`
	Failed   int      `json:"failed"`
	Deleted  int      `json:"deleted"`
	Errors   []string `json:"errors,omitempty"`
}

// HandleFileChange 处理文件变化
func (s *STRMService) HandleFileChange(added, removed []*model.CD2FileInfo) {
	rules, err := s.store.GetEnabledRules()
	if err != nil {
		return
	}

	for _, f := range added {
		for _, rule := range rules {
			if strings.HasPrefix(f.Path, rule.SourcePath) {
				ext := strings.ToLower(filepath.Ext(f.Name))
				exts := s.getVideoExtensions(rule)
				if !exts[ext] {
					continue
				}

				relPath, _ := filepath.Rel(rule.SourcePath, f.Path)
				strmRelPath := strings.TrimSuffix(relPath, ext) + ".strm"
				strmPath := filepath.Join(rule.OutputPath, strmRelPath)

				s.createSTRM(f, strmPath, rule)
				break
			}
		}
	}

	// removed 的处理已移至 monitor.handleDelete，由智能清理统一处理
}
