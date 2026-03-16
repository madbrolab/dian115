package service

import (
	"fmt"
	"log"
	"path/filepath"
	"strings"
	"time"

	"strm-manager/internal/client"
	"strm-manager/internal/model"
	"strm-manager/internal/store"
	"strm-manager/internal/util"
)

// TreeService 目录树服务
type TreeService struct {
	store       *store.Store
	driver115   *client.Driver115Client
	logger      *LoggerService
	mountPrefix string
}

// NewTreeService 创建目录树服务
func NewTreeService(store *store.Store, driver115 *client.Driver115Client, mountPrefix string) *TreeService {
	return &TreeService{
		store:       store,
		driver115:   driver115,
		mountPrefix: mountPrefix,
	}
}

// SetLogger 设置日志服务
func (t *TreeService) SetLogger(logger *LoggerService) {
	t.logger = logger
}

// SetMountPrefix 热更新挂载前缀
func (t *TreeService) SetMountPrefix(mountPrefix string) {
	t.mountPrefix = mountPrefix
}

// SetDriver115 热更新115客户端
func (t *TreeService) SetDriver115(driver115 *client.Driver115Client) {
	t.driver115 = driver115
}

// IsNodeDeletedByCD2Path 检查CD2路径对应的节点是否已从目录树中删除
func (t *TreeService) IsNodeDeletedByCD2Path(cd2Path string) bool {
	node, _ := t.store.GetTreeNodeByCD2Path(cd2Path)
	return node == nil
}

// IsNodeExistsByCD2Path 检查CD2路径对应的节点是否已存在于目录树中
func (t *TreeService) IsNodeExistsByCD2Path(cd2Path string) bool {
	node, _ := t.store.GetTreeNodeByCD2Path(cd2Path)
	return node != nil
}

// BuildTree 全量构建目录树
func (t *TreeService) BuildTree(rule *model.STRMRule, task *Task) error {
	startTime := time.Now()

	if task != nil {
		task.AddLog("🌳 开始构建目录树...")
	}
	log.Printf("[TreeService] 开始构建目录树: 规则=%s, 源路径=%s", rule.Name, rule.SourcePath)
	if t.logger != nil {
		t.logger.Log(model.LogType115, model.LogCategoryNormal, model.LogLevelInfo, fmt.Sprintf("开始构建目录树: %s", rule.Name), map[string]string{
			"rule_name":   rule.Name,
			"source_path": rule.SourcePath,
		}, rule.ID)
	}

	// 1. 清空该规则的旧目录树
	if err := t.store.DeleteTreeByRuleID(rule.ID); err != nil {
		return fmt.Errorf("清空旧目录树失败: %v", err)
	}

	// 2. 从CD2路径提取115路径
	path115 := cd2PathTo115Path(rule.SourcePath, rule.CloudName)
	if path115 == "" || path115 == "/" {
		return fmt.Errorf("无法从CD2路径 %s 提取115路径（云盘名称: %s）", rule.SourcePath, rule.CloudName)
	}

	if task != nil {
		task.AddLog(fmt.Sprintf("📂 115网盘路径: %s", path115))
	}

	// 3. 调用115 API递归遍历，批量收集节点
	var nodes []*model.FileTreeNode
	batchSize := 2000
	totalFiles := 0
	totalDirs := 0

	// 用于调试：统计扩展名分布
	extStats := make(map[string]int)
	emptyNameCount := 0

	// 获取规则的视频后缀
	videoExts := t.getVideoExtensions(rule)

	err := t.driver115.WalkDir115(path115, 1000, func(item *client.FileInfo115, fullPath string, parentPath string) error {
		// 检查任务是否被取消
		if task != nil && task.IsCancelled() {
			return fmt.Errorf("任务已取消")
		}

		// 处理目录节点
		if item.IsDir {
			totalDirs++
			// 将文件夹也写入数据库
			node := &model.FileTreeNode{
				RuleID:     rule.ID,
				Name:       item.Name,
				Path115:    fullPath,
				CD2Path:    path115ToCD2Path(fullPath, rule.CloudName),
				MountPath:  cd2PathToMountPath(path115ToCD2Path(fullPath, rule.CloudName), t.mountPrefix),
				ParentPath: parentPath,
				IsDir:      true,
				FileSize:   0,
				PickCode:   "",
				SHA1:       "",
				CID:        item.Cid,
				Ext:        "",
			}
			nodes = append(nodes, node)

			// 批量写入
			if len(nodes) >= batchSize {
				if err := t.store.InsertTreeNodes(nodes); err != nil {
					return fmt.Errorf("批量写入目录树失败: %v", err)
				}
				nodes = nodes[:0]
			}
			return nil
		}

		ext := strings.ToLower(filepath.Ext(item.Name))
		extStats[ext]++

		// 只保留匹配视频后缀的文件
		if !videoExts[ext] {
			return nil
		}

		if item.Name == "" || item.Name == item.PickCode {
			emptyNameCount++
			if emptyNameCount <= 5 {
				log.Printf("[TreeService] 调试: 文件名为空或为pickcode, name=%q, pc=%s, fid=%s, path=%s", item.Name, item.PickCode, item.Fid, fullPath)
			}
		}

		node := &model.FileTreeNode{
			RuleID:     rule.ID,
			Name:       item.Name,
			Path115:    fullPath,
			CD2Path:    path115ToCD2Path(fullPath, rule.CloudName),
			MountPath:  cd2PathToMountPath(path115ToCD2Path(fullPath, rule.CloudName), t.mountPrefix),
			ParentPath: parentPath,
			IsDir:      false,
			FileSize:   item.Size,
			PickCode:   item.PickCode,
			SHA1:       item.Sha1,
			CID:        item.Cid,
			Ext:        ext,
		}

		nodes = append(nodes, node)
		totalFiles++

		// 批量写入
		if len(nodes) >= batchSize {
			if err := t.store.InsertTreeNodes(nodes); err != nil {
				return fmt.Errorf("批量写入目录树失败: %v", err)
			}
			if task != nil {
				task.AddLog(fmt.Sprintf("📝 已写入 %d 个文件, %d 个目录...", totalFiles, totalDirs))
			}
			nodes = nodes[:0]
		}

		return nil
	})

	if err != nil {
		return fmt.Errorf("遍历115目录失败: %v", err)
	}

	// 输出扩展名统计（DEBUG级别）
	if t.logger != nil {
		type extCount struct {
			ext   string
			count int
		}
		var sortedExts []extCount
		for ext, count := range extStats {
			sortedExts = append(sortedExts, extCount{ext, count})
		}
		for i := 0; i < len(sortedExts) && i < 10; i++ {
			for j := i + 1; j < len(sortedExts); j++ {
				if sortedExts[j].count > sortedExts[i].count {
					sortedExts[i], sortedExts[j] = sortedExts[j], sortedExts[i]
				}
			}
		}
		var extSummary string
		for i := 0; i < len(sortedExts) && i < 10; i++ {
			extSummary += fmt.Sprintf("%s:%d ", sortedExts[i].ext, sortedExts[i].count)
		}
		t.logger.Debug(model.LogType115, fmt.Sprintf("目录树扩展名统计: %s", extSummary), nil)
	}

	// 写入剩余节点
	if len(nodes) > 0 {
		if err := t.store.InsertTreeNodes(nodes); err != nil {
			return fmt.Errorf("写入剩余节点失败: %v", err)
		}
	}

	// 4. 更新规则的目录树状态
	if err := t.store.UpdateRuleTreeStatus(rule.ID, true, totalFiles); err != nil {
		log.Printf("[TreeService] 更新规则目录树状态失败: %v", err)
	}

	elapsed := time.Since(startTime)
	log.Printf("[TreeService] 目录树构建完成: 规则=%s, 文件=%d, 目录=%d, 耗时=%s", rule.Name, totalFiles, totalDirs, util.FormatDuration(elapsed))

	if task != nil {
		task.AddLog(fmt.Sprintf("✅ 目录树构建完成: %d 个文件, %d 个目录, 耗时 %s", totalFiles, totalDirs, util.FormatDuration(elapsed)))
	}

	if t.logger != nil {
		t.logger.LogSync(model.LogLevelSuccess, fmt.Sprintf("目录树构建完成: %s", rule.Name), map[string]string{
			"files":    fmt.Sprintf("%d", totalFiles),
			"dirs":     fmt.Sprintf("%d", totalDirs),
			"duration": util.FormatDuration(elapsed),
		}, rule.ID)
	}

	return nil
}

// UpdateTreeNode 增量更新单个节点（文件新增/修改）
func (t *TreeService) UpdateTreeNode(rule *model.STRMRule, cd2Path string) error {
	// 从CD2路径转换为115路径
	path115 := cd2PathTo115Path(cd2Path, rule.CloudName)
	if path115 == "" {
		return fmt.Errorf("无法转换路径: %s", cd2Path)
	}

	// 调用115 API获取文件信息
	fileInfo, err := t.driver115.GetFileInfo115(path115)
	if err != nil {
		return fmt.Errorf("获取115文件信息失败: %v", err)
	}

	node := &model.FileTreeNode{
		RuleID:     rule.ID,
		Name:       fileInfo.Name,
		Path115:    path115,
		CD2Path:    cd2Path,
		MountPath:  cd2PathToMountPath(cd2Path, t.mountPrefix),
		ParentPath: filepath.Dir(path115),
		IsDir:      fileInfo.IsDir,
		FileSize:   fileInfo.Size,
		PickCode:   fileInfo.PickCode,
		SHA1:       fileInfo.Sha1,
		CID:        fileInfo.Cid,
		Ext:        strings.ToLower(filepath.Ext(fileInfo.Name)),
	}

	if err := t.store.UpsertTreeNode(node); err != nil {
		return fmt.Errorf("更新目录树节点失败: %v", err)
	}

	// 更新规则的文件计数
	files, _, _, _ := t.store.GetTreeStats(rule.ID)
	t.store.UpdateRuleTreeStatus(rule.ID, true, files)

	if t.logger != nil {
		t.logger.Debug(model.LogType115, fmt.Sprintf("目录树节点已更新: %s", path115), nil)
	}
	return nil
}

// HandleCD2FileChange 处理CD2文件变动，增量更新目录树
// cd2Path: CD2内部路径（如 /115open/媒体库/电影/xxx.mkv）
// changeType: "add", "delete", "rename"
// newCD2Path: 仅rename时有值
// 返回: (新增的节点列表, 删除的节点列表, error)
func (t *TreeService) HandleCD2FileChange(rule *model.STRMRule, changeType, cd2Path string, newCD2Path string) ([]*model.FileTreeNode, []*model.FileTreeNode, error) {
	if t.logger != nil {
		t.logger.Debug(model.LogTypeMonitor, fmt.Sprintf("CD2文件变动: %s %s", changeType, cd2Path), map[string]string{
			"rule_name": rule.Name,
		})
	}

	switch changeType {
	case "add":
		added, err := t.handleAddFile(rule, cd2Path)
		return added, nil, err
	case "delete":
		deleted, err := t.handleDeleteFile(rule, cd2Path)
		return nil, deleted, err
	case "rename":
		deleted, err := t.handleDeleteFile(rule, cd2Path)
		if err != nil {
			log.Printf("[TreeService]   删除旧路径失败: %v", err)
		}
		added, err2 := t.handleAddFile(rule, newCD2Path)
		if err2 != nil {
			return nil, deleted, err2
		}
		return added, deleted, nil
	default:
		log.Printf("[TreeService]   未知变动类型: %s", changeType)
		return nil, nil, fmt.Errorf("未知变动类型: %s", changeType)
	}
}

// handleAddFile 处理文件新增：查父目录CID → listDir → 写入目录树
func (t *TreeService) handleAddFile(rule *model.STRMRule, cd2Path string) ([]*model.FileTreeNode, error) {
	path115 := cd2PathTo115Path(cd2Path, rule.CloudName)
	if path115 == "" {
		return nil, fmt.Errorf("无法转换路径: %s", cd2Path)
	}

	parentPath115 := filepath.Dir(path115)
	fileName := filepath.Base(path115)

	log.Printf("[TreeService]   path_115: %s", path115)
	log.Printf("[TreeService]   父目录path_115: %s", parentPath115)
	log.Printf("[TreeService]   文件名: %s", fileName)

	// 1. 获取父目录CID
	parentCID := t.getParentCID(rule, parentPath115)
	if parentCID == "" {
		return nil, fmt.Errorf("获取父目录CID失败")
	}

	// 2. 用CID列出父目录下的文件
	log.Printf("[TreeService]   调用listDir(cid=%s)...", parentCID)
	files, err := t.driver115.ListDir(parentCID)
	if err != nil {
		log.Printf("[TreeService]   ✗ listDir失败: %v", err)
		return nil, fmt.Errorf("列出目录失败: %v", err)
	}
	log.Printf("[TreeService]   ✓ listDir返回 %d 个文件/目录", len(files))

	// 3. 找到目标，写入目录树
	for _, f := range files {
		if f.Name == fileName {
			log.Printf("[TreeService]   ✓ 找到: name=%s, pickcode=%s, size=%d, isDir=%v",
				f.Name, f.PickCode, f.Size, f.IsDir)

			if f.IsDir {
				// 目标是目录：写入目录节点，然后递归列出子文件
				return t.handleAddDirectory(rule, cd2Path, path115, parentPath115, f)
			}

			// 目标是文件：直接写入
			node := t.buildTreeNode(rule, f, path115, cd2Path, parentPath115)
			if err := t.store.UpsertTreeNode(node); err != nil {
				return nil, fmt.Errorf("写入目录树失败: %v", err)
			}
			log.Printf("[TreeService]   ✓ 已写入目录树")

			fc, _, _, _ := t.store.GetTreeStats(rule.ID)
			t.store.UpdateRuleTreeStatus(rule.ID, true, fc)
			return []*model.FileTreeNode{node}, nil
		}
	}

	log.Printf("[TreeService]   ✗ 在listDir结果中未找到: %s", fileName)
	return nil, fmt.Errorf("在目录(cid=%s)中未找到: %s", parentCID, fileName)
}

// handleAddDirectory 处理新增目录：写入目录节点 + 递归列出子文件全部写入
func (t *TreeService) handleAddDirectory(rule *model.STRMRule, cd2Path, path115, parentPath115 string, dirInfo *client.FileInfo115) ([]*model.FileTreeNode, error) {
	// 写入目录节点本身
	dirNode := t.buildTreeNode(rule, dirInfo, path115, cd2Path, parentPath115)
	if err := t.store.UpsertTreeNode(dirNode); err != nil {
		return nil, fmt.Errorf("写入目录节点失败: %v", err)
	}

	dirCID := dirInfo.Cid
	log.Printf("[TreeService]   目录CID: %s，开始递归列出子文件...", dirCID)

	// 递归遍历目录下所有文件
	var addedNodes []*model.FileTreeNode
	err := t.driver115.WalkDir115(path115, 500, func(item *client.FileInfo115, fullPath string, itemParentPath string) error {
		itemCD2Path := path115ToCD2Path(fullPath, rule.CloudName)
		node := &model.FileTreeNode{
			RuleID:     rule.ID,
			Name:       item.Name,
			Path115:    fullPath,
			CD2Path:    itemCD2Path,
			MountPath:  cd2PathToMountPath(itemCD2Path, t.mountPrefix),
			ParentPath: itemParentPath,
			IsDir:      item.IsDir,
			FileSize:   item.Size,
			PickCode:   item.PickCode,
			SHA1:       item.Sha1,
			CID:        item.Cid,
			Ext:        strings.ToLower(filepath.Ext(item.Name)),
		}
		if err := t.store.UpsertTreeNode(node); err != nil {
			return fmt.Errorf("写入节点失败: %v", err)
		}
		if !item.IsDir {
			addedNodes = append(addedNodes, node)
		}
		return nil
	})
	if err != nil {
		log.Printf("[TreeService]   ✗ 递归遍历失败: %v", err)
		return addedNodes, err
	}

	log.Printf("[TreeService]   ✓ 目录递归完成，共写入 %d 个文件", len(addedNodes))

	fc, _, _, _ := t.store.GetTreeStats(rule.ID)
	t.store.UpdateRuleTreeStatus(rule.ID, true, fc)
	return addedNodes, nil
}

// getParentCID 获取父目录CID（优先目录树缓存，回退115 API）
func (t *TreeService) getParentCID(rule *model.STRMRule, parentPath115 string) string {
	dirNode, _ := t.store.GetDirNodeByPath115(rule.ID, parentPath115)
	if dirNode != nil && dirNode.CID != "" {
		log.Printf("[TreeService]   ✓ 从目录树获取父目录CID: %s", dirNode.CID)
		return dirNode.CID
	}

	log.Printf("[TreeService]   目录树中未找到父目录，调用115 API...")
	cid, err := t.driver115.GetDirIDByPath(parentPath115)
	if err != nil {
		log.Printf("[TreeService]   ✗ 获取父目录CID失败: %v", err)
		return ""
	}
	log.Printf("[TreeService]   ✓ 从115 API获取父目录CID: %s", cid)
	return cid
}

// buildTreeNode 构建目录树节点
func (t *TreeService) buildTreeNode(rule *model.STRMRule, f *client.FileInfo115, path115, cd2Path, parentPath115 string) *model.FileTreeNode {
	return &model.FileTreeNode{
		RuleID:     rule.ID,
		Name:       f.Name,
		Path115:    path115,
		CD2Path:    cd2Path,
		MountPath:  cd2PathToMountPath(path115ToCD2Path(path115, rule.CloudName), t.mountPrefix),
		ParentPath: parentPath115,
		IsDir:      f.IsDir,
		FileSize:   f.Size,
		PickCode:   f.PickCode,
		SHA1:       f.Sha1,
		CID:        f.Cid,
		Ext:        strings.ToLower(filepath.Ext(f.Name)),
	}
}

// FastScanDirectory 快速模式增量扫描目录
// 用 WalkDir115（内部优先快速模式 downfolders/downfiles）扫描目录，
// 与目录树中已有节点做 diff，只写入新增的节点
func (t *TreeService) FastScanDirectory(rule *model.STRMRule, scanDirCD2Path, scanDir115 string) ([]*model.FileTreeNode, error) {
	log.Printf("[TreeService] 快速扫描: %s", scanDir115)

	// 获取目录树中该目录下已有的节点（用于 diff）
	existingNodes, _ := t.store.GetTreeNodesByParentPrefix(rule.ID, scanDir115)
	existingSet := make(map[string]bool) // key: path_115
	for _, n := range existingNodes {
		existingSet[n.Path115] = true
	}
	log.Printf("[TreeService]   目录树中已有 %d 个节点", len(existingSet))

	// 用 WalkDir115 扫描（内部自动选择快速/递归模式）
	var addedNodes []*model.FileTreeNode
	var totalScanned int
	videoExts := t.getVideoExtensions(rule)

	err := t.driver115.WalkDir115(scanDir115, 0, func(item *client.FileInfo115, fullPath string, parentPath string) error {
		totalScanned++

		// 处理文件夹
		if item.IsDir {
			// 已存在的跳过
			if existingSet[fullPath] {
				return nil
			}
			itemCD2Path := path115ToCD2Path(fullPath, rule.CloudName)
			node := &model.FileTreeNode{
				RuleID:     rule.ID,
				Name:       item.Name,
				Path115:    fullPath,
				CD2Path:    itemCD2Path,
				MountPath:  cd2PathToMountPath(itemCD2Path, t.mountPrefix),
				ParentPath: parentPath,
				IsDir:      true,
				FileSize:   0,
				PickCode:   "",
				SHA1:       "",
				CID:        item.Cid,
				Ext:        "",
			}
			if err := t.store.UpsertTreeNode(node); err != nil {
				return fmt.Errorf("写入文件夹节点失败: %v", err)
			}
			addedNodes = append(addedNodes, node)
			return nil
		}

		// 只保留匹配视频后缀的文件
		ext := strings.ToLower(filepath.Ext(item.Name))
		if !videoExts[ext] {
			return nil
		}

		// 已存在的跳过
		if existingSet[fullPath] {
			return nil
		}

		itemCD2Path := path115ToCD2Path(fullPath, rule.CloudName)
		node := &model.FileTreeNode{
			RuleID:     rule.ID,
			Name:       item.Name,
			Path115:    fullPath,
			CD2Path:    itemCD2Path,
			MountPath:  cd2PathToMountPath(itemCD2Path, t.mountPrefix),
			ParentPath: parentPath,
			IsDir:      false,
			FileSize:   item.Size,
			PickCode:   item.PickCode,
			SHA1:       item.Sha1,
			CID:        item.Cid,
			Ext:        ext,
		}
		if err := t.store.UpsertTreeNode(node); err != nil {
			return fmt.Errorf("写入节点失败: %v", err)
		}
		addedNodes = append(addedNodes, node)
		return nil
	})

	if err != nil {
		log.Printf("[TreeService]   ✗ WalkDir115失败: %v", err)
		return addedNodes, err
	}

	log.Printf("[TreeService]   扫描完成: 共%d个节点, 新增%d个", totalScanned, len(addedNodes))

	// 更新规则文件计数
	fc, _, _, _ := t.store.GetTreeStats(rule.ID)
	t.store.UpdateRuleTreeStatus(rule.ID, true, fc)

	return addedNodes, nil
}

// DeleteTreeByPrefix 删除目录及其下所有节点
func (t *TreeService) DeleteTreeByPrefix(rule *model.STRMRule, cd2Path string) ([]*model.FileTreeNode, error) {
	path115 := cd2PathTo115Path(cd2Path, rule.CloudName)
	if path115 == "" {
		return nil, fmt.Errorf("无法转换路径: %s", cd2Path)
	}

	// 获取该路径下所有节点
	nodes, err := t.store.GetTreeNodesByParentPrefix(rule.ID, path115)
	if err != nil {
		return nil, err
	}

	// 也获取该路径本身的节点
	selfNode, _ := t.store.GetTreeNodeByCD2Path(cd2Path)
	if selfNode != nil {
		nodes = append(nodes, selfNode)
	}

	if len(nodes) == 0 {
		log.Printf("[TreeService]   目录树中未找到节点: %s", path115)
		return nil, nil
	}

	// 批量删除
	for _, node := range nodes {
		_ = t.store.DeleteTreeNodeByCD2Path(node.CD2Path)
	}

	log.Printf("[TreeService]   已删除 %d 个节点 (前缀: %s)", len(nodes), path115)
	if t.logger != nil {
		t.logger.LogSync(model.LogLevelWarning, fmt.Sprintf("目录树批量删除: %d个节点", len(nodes)), map[string]string{
			"path": path115,
		}, rule.ID)
	}

	fc, _, _, _ := t.store.GetTreeStats(rule.ID)
	t.store.UpdateRuleTreeStatus(rule.ID, true, fc)

	return nodes, nil
}

// HandleDeleteFile 处理文件删除：从目录树中删除节点（公开方法）
func (t *TreeService) HandleDeleteFile(rule *model.STRMRule, cd2Path string) ([]*model.FileTreeNode, error) {
	return t.handleDeleteFile(rule, cd2Path)
}

// handleDeleteFile 处理文件删除：从目录树中删除节点
func (t *TreeService) handleDeleteFile(rule *model.STRMRule, cd2Path string) ([]*model.FileTreeNode, error) {
	node, err := t.store.GetTreeNodeByCD2Path(cd2Path)
	if err != nil {
		log.Printf("[TreeService]   查询节点失败: %v", err)
		return nil, err
	}
	if node == nil {
		log.Printf("[TreeService]   目录树中未找到节点，跳过删除: %s", cd2Path)
		return nil, nil
	}

	log.Printf("[TreeService]   找到节点: name=%s, pickcode=%s, isDir=%v", node.Name, node.PickCode, node.IsDir)

	if err := t.store.DeleteTreeNodeByCD2Path(cd2Path); err != nil {
		log.Printf("[TreeService]   ✗ 删除节点失败: %v", err)
		return nil, err
	}

	log.Printf("[TreeService]   ✓ 已从目录树删除")

	// 更新规则文件计数
	fileCount, _, _, _ := t.store.GetTreeStats(rule.ID)
	t.store.UpdateRuleTreeStatus(rule.ID, true, fileCount)

	return []*model.FileTreeNode{node}, nil
}

// RemoveTreeNode 删除单个节点（文件删除）
func (t *TreeService) RemoveTreeNode(rule *model.STRMRule, cd2Path string) (*model.FileTreeNode, error) {
	// 先查询节点信息（用于返回给调用方做清理）
	node, err := t.store.GetTreeNodeByCD2Path(cd2Path)
	if err != nil {
		return nil, fmt.Errorf("查询目录树节点失败: %v", err)
	}
	if node == nil {
		return nil, nil // 节点不存在，无需删除
	}

	// 删除节点
	if err := t.store.DeleteTreeNodeByCD2Path(cd2Path); err != nil {
		return nil, fmt.Errorf("删除目录树节点失败: %v", err)
	}

	// 更新规则的文件计数
	files, _, _, _ := t.store.GetTreeStats(rule.ID)
	t.store.UpdateRuleTreeStatus(rule.ID, true, files)

	if t.logger != nil {
		t.logger.Debug(model.LogTypeSync, fmt.Sprintf("目录树节点已删除: %s", filepath.Base(cd2Path)), nil)
	}
	return node, nil
}

// GetTreeFiles 获取目录树中的文件列表（按后缀过滤）
func (t *TreeService) GetTreeFiles(ruleID int64, extensions []string) ([]*model.FileTreeNode, error) {
	return t.store.GetTreeFilesByRule(ruleID, extensions)
}

// GetTreeStats 获取目录树统计信息
func (t *TreeService) GetTreeStats(ruleID int64) (totalFiles int, totalDirs int, totalSize int64, err error) {
	return t.store.GetTreeStats(ruleID)
}

// ==================== 路径转换工具函数 ====================

// cd2PathTo115Path CD2路径转115路径
// 例: /115/电影/xxx.mkv + cloudName=115 → /电影/xxx.mkv
func cd2PathTo115Path(cd2Path string, cloudName string) string {
	if cloudName == "" {
		return cd2Path
	}
	prefix := "/" + cloudName
	if strings.HasPrefix(cd2Path, prefix) {
		result := strings.TrimPrefix(cd2Path, prefix)
		if result == "" {
			return "/"
		}
		return result
	}
	return cd2Path
}

// path115ToCD2Path 115路径转CD2路径
// 例: /电影/xxx.mkv + cloudName=115 → /115/电影/xxx.mkv
func path115ToCD2Path(path115 string, cloudName string) string {
	if cloudName == "" {
		return path115
	}
	return "/" + cloudName + path115
}

// cd2PathToMountPath CD2路径转挂载路径
// 例: /115/电影/xxx.mkv + mountPrefix=/CloudNAS/CloudDrive → /CloudNAS/CloudDrive/115/电影/xxx.mkv
func cd2PathToMountPath(cd2Path string, mountPrefix string) string {
	if mountPrefix == "" {
		return cd2Path
	}
	mountPrefix = strings.TrimSuffix(mountPrefix, "/")
	if !strings.HasPrefix(cd2Path, "/") {
		return mountPrefix + "/" + cd2Path
	}
	return mountPrefix + cd2Path
}

// getVideoExtensions 获取规则的视频扩展名
func (t *TreeService) getVideoExtensions(rule *model.STRMRule) map[string]bool {
	// 默认视频扩展名
	defaultExts := map[string]bool{
		".mp4": true, ".mkv": true, ".avi": true, ".mov": true,
		".wmv": true, ".flv": true, ".ts": true, ".m2ts": true,
		".rmvb": true, ".iso": true, ".m4v": true, ".webm": true,
		".rm": true, ".mpg": true, ".mpeg": true, ".vob": true,
		".3gp": true, ".asf": true, ".divx": true, ".f4v": true,
		".mts": true, ".tp": true, ".trp": true, ".ogv": true,
	}

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
	return defaultExts
}

// IncrementalScanResult 增量扫描结果
type IncrementalScanResult struct {
	AddedNodes   []*model.FileTreeNode // 新增的文件节点
	DeletedNodes []*model.FileTreeNode // 已删除的文件节点
	TotalScanned int                   // 扫描到的总文件数
}

// IncrementalScan 增量扫描：扫描115网盘构建新树，与旧树对比，返回新增和删除的节点
// 用于定时同步场景，既能发现新增文件，也能检测已删除文件
func (t *TreeService) IncrementalScan(rule *model.STRMRule, task *Task) (*IncrementalScanResult, error) {
	startTime := time.Now()

	if task != nil {
		task.AddLog("🔄 开始增量扫描...")
	}
	log.Printf("[TreeService] 增量扫描: 规则=%s, 源路径=%s", rule.Name, rule.SourcePath)

	// 1. 从CD2路径提取115路径
	path115 := cd2PathTo115Path(rule.SourcePath, rule.CloudName)
	if path115 == "" || path115 == "/" {
		return nil, fmt.Errorf("无法从CD2路径 %s 提取115路径（云盘名称: %s）", rule.SourcePath, rule.CloudName)
	}

	// 2. 获取目录树中已有的所有节点（旧树）
	existingNodes, err := t.store.GetTreeFilesByRule(rule.ID, nil)
	if err != nil {
		return nil, fmt.Errorf("获取目录树节点失败: %v", err)
	}

	oldTreeMap := make(map[string]*model.FileTreeNode) // key: path_115
	for _, node := range existingNodes {
		oldTreeMap[node.Path115] = node
	}

	if task != nil {
		task.AddLog(fmt.Sprintf("📂 旧树中有 %d 个节点", len(oldTreeMap)))
	}
	log.Printf("[TreeService]   旧树节点数: %d", len(oldTreeMap))

	// 3. 扫描115网盘构建新树
	newTreeMap := make(map[string]*model.FileTreeNode) // key: path_115
	videoExts := t.getVideoExtensions(rule)
	totalScanned := 0

	err = t.driver115.WalkDir115(path115, 1000, func(item *client.FileInfo115, fullPath string, parentPath string) error {
		// 检查任务是否被取消
		if task != nil && task.IsCancelled() {
			return fmt.Errorf("任务已取消")
		}

		// 跳过目录，只处理文件
		if item.IsDir {
			return nil
		}

		totalScanned++

		// 只保留匹配视频后缀的文件
		ext := strings.ToLower(filepath.Ext(item.Name))
		if !videoExts[ext] {
			return nil
		}

		itemCD2Path := path115ToCD2Path(fullPath, rule.CloudName)
		node := &model.FileTreeNode{
			RuleID:     rule.ID,
			Name:       item.Name,
			Path115:    fullPath,
			CD2Path:    itemCD2Path,
			MountPath:  cd2PathToMountPath(itemCD2Path, t.mountPrefix),
			ParentPath: parentPath,
			IsDir:      false,
			FileSize:   item.Size,
			PickCode:   item.PickCode,
			SHA1:       item.Sha1,
			CID:        item.Cid,
			Ext:        ext,
		}

		newTreeMap[fullPath] = node
		return nil
	})

	if err != nil {
		return nil, fmt.Errorf("扫描115目录失败: %v", err)
	}

	if task != nil {
		task.AddLog(fmt.Sprintf("📂 新树中有 %d 个节点", len(newTreeMap)))
	}
	log.Printf("[TreeService]   新树节点数: %d (扫描总数: %d)", len(newTreeMap), totalScanned)

	// 4. 对比新旧树，找出新增和删除的节点
	var addedNodes []*model.FileTreeNode
	var deletedNodes []*model.FileTreeNode

	// 4.1 找出新增的节点（新树有，旧树没有）
	for path115, newNode := range newTreeMap {
		if _, exists := oldTreeMap[path115]; !exists {
			addedNodes = append(addedNodes, newNode)
		}
	}

	// 4.2 找出删除的节点（旧树有，新树没有）
	for path115, oldNode := range oldTreeMap {
		if _, exists := newTreeMap[path115]; !exists {
			deletedNodes = append(deletedNodes, oldNode)
		}
	}

	if task != nil {
		task.AddLog(fmt.Sprintf("📊 对比结果: 新增 %d 个, 删除 %d 个", len(addedNodes), len(deletedNodes)))
	}
	log.Printf("[TreeService]   对比结果: 新增=%d, 删除=%d", len(addedNodes), len(deletedNodes))

	// 5. 批量写入新增节点
	if len(addedNodes) > 0 {
		batchSize := 2000
		for i := 0; i < len(addedNodes); i += batchSize {
			end := i + batchSize
			if end > len(addedNodes) {
				end = len(addedNodes)
			}
			batch := addedNodes[i:end]
			if err := t.store.InsertTreeNodes(batch); err != nil {
				return nil, fmt.Errorf("批量写入新增节点失败: %v", err)
			}
			if task != nil {
				task.AddLog(fmt.Sprintf("✅ 已写入 %d/%d 个新增节点", end, len(addedNodes)))
			}
		}
		log.Printf("[TreeService]   已写入 %d 个新增节点", len(addedNodes))
	}

	// 6. 批量删除已删除节点
	if len(deletedNodes) > 0 {
		for _, node := range deletedNodes {
			if err := t.store.DeleteTreeNode(rule.ID, node.Path115); err != nil {
				log.Printf("[TreeService]   删除节点失败: %s - %v", node.Path115, err)
			}
		}
		if task != nil {
			task.AddLog(fmt.Sprintf("🗑️ 已删除 %d 个失效节点", len(deletedNodes)))
		}
		log.Printf("[TreeService]   已删除 %d 个失效节点", len(deletedNodes))
	}

	// 7. 更新规则的目录树状态
	totalFiles := len(newTreeMap)
	if err := t.store.UpdateRuleTreeStatus(rule.ID, true, totalFiles); err != nil {
		log.Printf("[TreeService] 更新规则目录树状态失败: %v", err)
	}

	elapsed := time.Since(startTime)
	log.Printf("[TreeService] 增量扫描完成: 规则=%s, 新增=%d, 删除=%d, 总计=%d, 耗时=%v",
		rule.Name, len(addedNodes), len(deletedNodes), totalFiles, elapsed)

	if task != nil {
		task.AddLog(fmt.Sprintf("✅ 增量扫描完成: 新增 %d, 删除 %d, 总计 %d, 耗时 %v",
			len(addedNodes), len(deletedNodes), totalFiles, elapsed))
	}

	if t.logger != nil {
		t.logger.LogSync(model.LogLevelSuccess, fmt.Sprintf("增量扫描完成: %s", rule.Name), map[string]string{
			"added":    fmt.Sprintf("%d", len(addedNodes)),
			"deleted":  fmt.Sprintf("%d", len(deletedNodes)),
			"total":    fmt.Sprintf("%d", totalFiles),
			"duration": util.FormatDuration(elapsed),
		}, rule.ID)
	}

	return &IncrementalScanResult{
		AddedNodes:   addedNodes,
		DeletedNodes: deletedNodes,
		TotalScanned: totalScanned,
	}, nil
}
