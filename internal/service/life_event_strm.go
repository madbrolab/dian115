package service

import (
	"log"
	"os"
	"path/filepath"
	"strings"

	"strm-manager/internal/model"
)

// generateSTRMForNodes 为新增节点生成STRM文件
func (s *LifeEventService) generateSTRMForNodes(rule *model.STRMRule, nodes []*model.FileTreeNode) {
	sourcePath115 := cd2PathTo115Path(rule.SourcePath, rule.CloudName)

	for _, node := range nodes {
		if node.IsDir || node.PickCode == "" {
			continue
		}

		relPath, err := filepath.Rel(sourcePath115, node.Path115)
		if err != nil {
			continue
		}

		ext := strings.ToLower(filepath.Ext(relPath))
		strmRelPath := strings.TrimSuffix(relPath, ext) + ".strm"
		strmPath := filepath.Join(rule.OutputPath, strmRelPath)

		if err := os.MkdirAll(filepath.Dir(strmPath), 0755); err != nil {
			continue
		}

		content := node.MountPath
		if content == "" {
			content = node.CD2Path
		}

		if err := os.WriteFile(strmPath, []byte(content), 0644); err != nil {
			continue
		}

		s.store.UpdateTreeNodeSTRMPath(node.ID, strmPath)
		log.Printf("[LifeEvent] 生成STRM: %s", strmPath)

		// 使用防抖器延迟刷新
		if s.debouncer != nil {
			s.debouncer.Add(rule.ID, strmPath)
		}
	}
}

// handleSmartClean 处理智能清理
func (s *LifeEventService) handleSmartClean(rule *model.STRMRule, deletedNodes []*model.FileTreeNode, isDir bool) {
	if !rule.SmartClean || s.cleanerSvc == nil || len(deletedNodes) == 0 {
		return
	}

	if isDir {
		// 目录删除：计算STRM目录路径并清理
		for _, node := range deletedNodes {
			if !node.IsDir {
				continue
			}

			var strmDirPath string
			if node.STRMPath != "" {
				strmDirPath = filepath.Dir(node.STRMPath)
			} else {
				sourcePath115 := cd2PathTo115Path(rule.SourcePath, rule.CloudName)
				relPath, err := filepath.Rel(sourcePath115, node.Path115)
				if err == nil {
					strmDirPath = filepath.Join(rule.OutputPath, relPath)
				}
			}

			if strmDirPath != "" {
				refreshPath, _ := s.cleanerSvc.SmartCleanDirectory(rule, strmDirPath)
				if s.embySvc != nil && refreshPath != "" {
					s.embySvc.RefreshLibraryPath(refreshPath)
				}
			}
			return
		}
	} else {
		// 文件删除：批量收集刷新路径
		refreshDirs := make(map[string]bool)
		for _, node := range deletedNodes {
			if node.IsDir || node.STRMPath == "" {
				continue
			}
			refreshPath, _ := s.cleanerSvc.CleanAll(rule, node.STRMPath)
			if refreshPath != "" {
				refreshDirs[refreshPath] = true
			}
		}

		// 只保留最上层目录,移除其子目录
		finalDirs := make(map[string]bool)
		for dir := range refreshDirs {
			isChild := false
			for parent := range refreshDirs {
				if dir != parent && strings.HasPrefix(dir+string(filepath.Separator), parent+string(filepath.Separator)) {
					isChild = true
					break
				}
			}
			if !isChild {
				finalDirs[dir] = true
			}
		}

		if s.embySvc != nil && len(finalDirs) > 0 {
			log.Printf("[LifeEvent] 批量刷新 %d 个目录", len(finalDirs))
			for dir := range finalDirs {
				s.embySvc.RefreshLibraryPath(dir)
			}
		}
	}
}
