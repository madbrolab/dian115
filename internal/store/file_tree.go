package store

import (
	"database/sql"
	"fmt"
	"log"
	"strings"

	"strm-manager/internal/model"
)

// ==================== 目录树操作 ====================

// InsertTreeNodes 批量插入目录树节点（使用事务）
func (s *Store) InsertTreeNodes(nodes []*model.FileTreeNode) error {
	if len(nodes) == 0 {
		return nil
	}

	tx, err := s.db.Begin()
	if err != nil {
		return err
	}
	defer tx.Rollback()

	stmt, err := tx.Prepare(`
		INSERT INTO file_tree (rule_id, name, path_115, cd2_path, mount_path, parent_path, is_dir, file_size, pick_code, sha1, cid, ext, strm_path)
		VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
		ON CONFLICT(rule_id, path_115) DO UPDATE SET
			name = excluded.name,
			cd2_path = excluded.cd2_path,
			mount_path = excluded.mount_path,
			parent_path = excluded.parent_path,
			is_dir = excluded.is_dir,
			file_size = excluded.file_size,
			pick_code = excluded.pick_code,
			sha1 = excluded.sha1,
			cid = excluded.cid,
			ext = excluded.ext,
			updated_at = CURRENT_TIMESTAMP
	`)
	if err != nil {
		return err
	}
	defer stmt.Close()

	for _, node := range nodes {
		if node.IsDir {
			log.Printf("[Store] 插入文件夹节点: Name=%s, Path115=%s, CID=%s", node.Name, node.Path115, node.CID)
		}
		_, err := stmt.Exec(
			node.RuleID, node.Name, node.Path115, node.CD2Path, node.MountPath,
			node.ParentPath, node.IsDir, node.FileSize, node.PickCode, node.SHA1,
			node.CID, node.Ext, node.STRMPath,
		)
		if err != nil {
			return fmt.Errorf("插入节点 %s 失败: %v", node.Path115, err)
		}
	}

	return tx.Commit()
}

// UpsertTreeNode 插入或更新单个目录树节点
func (s *Store) UpsertTreeNode(node *model.FileTreeNode) error {
	_, err := s.db.Exec(`
		INSERT INTO file_tree (rule_id, name, path_115, cd2_path, mount_path, parent_path, is_dir, file_size, pick_code, sha1, cid, ext, strm_path)
		VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
		ON CONFLICT(rule_id, path_115) DO UPDATE SET
			name = excluded.name,
			cd2_path = excluded.cd2_path,
			mount_path = excluded.mount_path,
			parent_path = excluded.parent_path,
			is_dir = excluded.is_dir,
			file_size = excluded.file_size,
			pick_code = excluded.pick_code,
			sha1 = excluded.sha1,
			cid = excluded.cid,
			ext = excluded.ext,
			updated_at = CURRENT_TIMESTAMP
	`, node.RuleID, node.Name, node.Path115, node.CD2Path, node.MountPath,
		node.ParentPath, node.IsDir, node.FileSize, node.PickCode, node.SHA1,
		node.CID, node.Ext, node.STRMPath)
	return err
}

// DeleteTreeByRuleID 删除规则的所有目录树节点
func (s *Store) DeleteTreeByRuleID(ruleID int64) error {
	_, err := s.db.Exec(`DELETE FROM file_tree WHERE rule_id = ?`, ruleID)
	if err != nil {
		return err
	}
	// 回收空间，防止数据库文件持续膨胀
	s.db.Exec(`VACUUM`)
	return nil
}

// DeleteTreeNode 删除单个目录树节点
func (s *Store) DeleteTreeNode(ruleID int64, path115 string) error {
	_, err := s.db.Exec(`DELETE FROM file_tree WHERE rule_id = ? AND path_115 = ?`, ruleID, path115)
	return err
}

// DeleteTreeNodeByCD2Path 根据CD2路径删除节点
func (s *Store) DeleteTreeNodeByCD2Path(cd2Path string) error {
	_, err := s.db.Exec(`DELETE FROM file_tree WHERE cd2_path = ?`, cd2Path)
	return err
}

// GetTreeFilesByRule 获取规则的文件列表（可按扩展名过滤）
func (s *Store) GetTreeFilesByRule(ruleID int64, extensions []string) ([]*model.FileTreeNode, error) {
	query := `SELECT id, rule_id, name, path_115, cd2_path, mount_path, parent_path, is_dir, file_size, pick_code, sha1, cid, ext, strm_path, created_at, updated_at
		FROM file_tree WHERE rule_id = ? AND is_dir = 0`
	args := []interface{}{ruleID}

	if len(extensions) > 0 {
		placeholders := make([]string, len(extensions))
		for i, ext := range extensions {
			placeholders[i] = "?"
			args = append(args, strings.ToLower(ext))
		}
		query += " AND ext IN (" + strings.Join(placeholders, ",") + ")"
	}

	query += " ORDER BY path_115"

	rows, err := s.db.Query(query, args...)
	if err != nil {
		return nil, err
	}
	defer rows.Close()

	var nodes []*model.FileTreeNode
	for rows.Next() {
		node, err := s.scanTreeNodeRows(rows)
		if err != nil {
			return nil, err
		}
		nodes = append(nodes, node)
	}
	return nodes, rows.Err()
}

// GetTreeFilesByRulePaged 获取规则的文件列表（分页）
func (s *Store) GetTreeFilesByRulePaged(ruleID int64, extensions []string, limit, offset int) ([]*model.FileTreeNode, int, error) {
	whereClause := "rule_id = ? AND is_dir = 0"
	args := []interface{}{ruleID}

	if len(extensions) > 0 {
		placeholders := make([]string, len(extensions))
		for i, ext := range extensions {
			placeholders[i] = "?"
			args = append(args, strings.ToLower(ext))
		}
		whereClause += " AND ext IN (" + strings.Join(placeholders, ",") + ")"
	}

	// 获取总数
	var total int
	countQuery := "SELECT COUNT(*) FROM file_tree WHERE " + whereClause
	s.db.QueryRow(countQuery, args...).Scan(&total)

	// 获取数据
	query := "SELECT id, rule_id, name, path_115, cd2_path, mount_path, parent_path, is_dir, file_size, pick_code, sha1, cid, ext, strm_path, created_at, updated_at FROM file_tree WHERE " + whereClause + " ORDER BY path_115 LIMIT ? OFFSET ?"
	args = append(args, limit, offset)

	rows, err := s.db.Query(query, args...)
	if err != nil {
		return nil, 0, err
	}
	defer rows.Close()

	var nodes []*model.FileTreeNode
	for rows.Next() {
		node, err := s.scanTreeNodeRows(rows)
		if err != nil {
			return nil, 0, err
		}
		nodes = append(nodes, node)
	}
	return nodes, total, rows.Err()
}

// GetTreeNodeByPath 根据115路径获取节点
func (s *Store) GetTreeNodeByPath(ruleID int64, path115 string) (*model.FileTreeNode, error) {
	row := s.db.QueryRow(`
		SELECT id, rule_id, name, path_115, cd2_path, mount_path, parent_path, is_dir, file_size, pick_code, sha1, cid, ext, strm_path, created_at, updated_at
		FROM file_tree WHERE rule_id = ? AND path_115 = ?
	`, ruleID, path115)
	return s.scanTreeNode(row)
}

// GetDirNodeByPath115 根据115路径获取目录节点（用于查找父目录CID）
func (s *Store) GetDirNodeByPath115(ruleID int64, path115 string) (*model.FileTreeNode, error) {
	row := s.db.QueryRow(`
		SELECT id, rule_id, name, path_115, cd2_path, mount_path, parent_path, is_dir, file_size, pick_code, sha1, cid, ext, strm_path, created_at, updated_at
		FROM file_tree WHERE rule_id = ? AND path_115 = ? AND is_dir = 1 LIMIT 1
	`, ruleID, path115)
	return s.scanTreeNode(row)
}

// GetTreeNodesByParentPrefix 获取指定规则下，path_115或parent_path以prefix开头的所有节点
func (s *Store) GetTreeNodesByParentPrefix(ruleID int64, prefix string) ([]*model.FileTreeNode, error) {
	rows, err := s.db.Query(`
		SELECT id, rule_id, name, path_115, cd2_path, mount_path, parent_path, is_dir, file_size, pick_code, sha1, cid, ext, strm_path, created_at, updated_at
		FROM file_tree WHERE rule_id = ? AND (path_115 LIKE ? OR parent_path LIKE ?)
		ORDER BY path_115
	`, ruleID, prefix+"/%", prefix+"/%")
	if err != nil {
		return nil, err
	}
	defer rows.Close()

	var nodes []*model.FileTreeNode
	for rows.Next() {
		node, err := s.scanTreeNodeRows(rows)
		if err != nil {
			return nil, err
		}
		nodes = append(nodes, node)
	}
	return nodes, rows.Err()
}

// GetTreeNodeByCD2Path 根据CD2路径获取节点（跨规则查询）
func (s *Store) GetTreeNodeByCD2Path(cd2Path string) (*model.FileTreeNode, error) {
	row := s.db.QueryRow(`
		SELECT id, rule_id, name, path_115, cd2_path, mount_path, parent_path, is_dir, file_size, pick_code, sha1, cid, ext, strm_path, created_at, updated_at
		FROM file_tree WHERE cd2_path = ? LIMIT 1
	`, cd2Path)
	return s.scanTreeNode(row)
}

// GetTreeNodeByMountPath 根据挂载路径获取节点（用于Emby 302查询）
func (s *Store) GetTreeNodeByMountPath(mountPath string) (*model.FileTreeNode, error) {
	row := s.db.QueryRow(`
		SELECT id, rule_id, name, path_115, cd2_path, mount_path, parent_path, is_dir, file_size, pick_code, sha1, cid, ext, strm_path, created_at, updated_at
		FROM file_tree WHERE mount_path = ? LIMIT 1
	`, mountPath)
	return s.scanTreeNode(row)
}

// GetTreeNodeBySTRMPath 根据STRM路径获取节点（用于反向删除）
func (s *Store) GetTreeNodeBySTRMPath(strmPath string) (*model.FileTreeNode, error) {
	row := s.db.QueryRow(`
		SELECT id, rule_id, name, path_115, cd2_path, mount_path, parent_path, is_dir, file_size, pick_code, sha1, cid, ext, strm_path, created_at, updated_at
		FROM file_tree WHERE strm_path = ? LIMIT 1
	`, strmPath)
	return s.scanTreeNode(row)
}

// UpdateTreeNodeSTRMPath 更新节点的STRM路径
func (s *Store) UpdateTreeNodeSTRMPath(id int64, strmPath string) error {
	_, err := s.db.Exec(`UPDATE file_tree SET strm_path = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?`, strmPath, id)
	return err
}

// GetTreeStats 获取目录树统计
func (s *Store) GetTreeStats(ruleID int64) (files int, dirs int, totalSize int64, err error) {
	err = s.db.QueryRow(`SELECT COUNT(*) FROM file_tree WHERE rule_id = ? AND is_dir = 0`, ruleID).Scan(&files)
	if err != nil {
		return
	}
	err = s.db.QueryRow(`SELECT COUNT(*) FROM file_tree WHERE rule_id = ? AND is_dir = 1`, ruleID).Scan(&dirs)
	if err != nil {
		return
	}
	err = s.db.QueryRow(`SELECT COALESCE(SUM(file_size), 0) FROM file_tree WHERE rule_id = ? AND is_dir = 0`, ruleID).Scan(&totalSize)
	return
}

// GetTreeRootParentPath 获取目录树中最短的 parent_path（即根节点的 parent_path）
func (s *Store) GetTreeRootParentPath(ruleID int64) (string, error) {
	var rootPath string
	err := s.db.QueryRow(`
		SELECT parent_path FROM file_tree WHERE rule_id = ?
		ORDER BY LENGTH(parent_path) ASC LIMIT 1
	`, ruleID).Scan(&rootPath)
	if err != nil {
		return "", err
	}
	return rootPath, nil
}

// GetTreeNodesByParentPath 获取指定父路径下的子节点（文件浏览器用）
func (s *Store) GetTreeNodesByParentPath(ruleID int64, parentPath string) ([]*model.FileTreeNode, error) {
	rows, err := s.db.Query(`
		SELECT id, rule_id, name, path_115, cd2_path, mount_path, parent_path, is_dir, file_size, pick_code, sha1, cid, ext, strm_path, created_at, updated_at
		FROM file_tree WHERE rule_id = ? AND parent_path = ?
		ORDER BY is_dir DESC, name ASC
	`, ruleID, parentPath)
	if err != nil {
		return nil, err
	}
	defer rows.Close()

	var nodes []*model.FileTreeNode
	for rows.Next() {
		node, err := s.scanTreeNodeRows(rows)
		if err != nil {
			return nil, err
		}
		nodes = append(nodes, node)
	}
	return nodes, rows.Err()
}

// RenameTreeNode 重命名目录树节点（更新名称和所有相关路径）
func (s *Store) RenameTreeNode(nodeID int64, newName string) error {
	// 先获取当前节点
	row := s.db.QueryRow(`
		SELECT id, rule_id, name, path_115, cd2_path, mount_path, parent_path, is_dir, file_size, pick_code, sha1, cid, ext, strm_path, created_at, updated_at
		FROM file_tree WHERE id = ?
	`, nodeID)
	node, err := s.scanTreeNode(row)
	if err != nil || node == nil {
		return fmt.Errorf("节点不存在: %d", nodeID)
	}

	oldPath115 := node.Path115
	newPath115 := node.ParentPath + "/" + newName

	// 更新当前节点
	_, err = s.db.Exec(`
		UPDATE file_tree SET name = ?, path_115 = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?
	`, newName, newPath115, nodeID)
	if err != nil {
		return err
	}

	// 如果是目录，还需要更新所有子节点的路径
	if node.IsDir {
		oldPrefix := oldPath115 + "/"
		newPrefix := newPath115 + "/"
		// 更新子节点的 path_115
		_, err = s.db.Exec(`
			UPDATE file_tree SET
				path_115 = ? || SUBSTR(path_115, ?),
				updated_at = CURRENT_TIMESTAMP
			WHERE rule_id = ? AND path_115 LIKE ?
		`, newPrefix, len(oldPrefix)+1, node.RuleID, oldPrefix+"%")
		if err != nil {
			return err
		}
		// 更新子节点的 parent_path
		_, err = s.db.Exec(`
			UPDATE file_tree SET
				parent_path = ? || SUBSTR(parent_path, ?),
				updated_at = CURRENT_TIMESTAMP
			WHERE rule_id = ? AND parent_path LIKE ?
		`, newPrefix, len(oldPrefix)+1, node.RuleID, oldPrefix+"%")
		if err != nil {
			return err
		}
		// 更新直接子节点的 parent_path
		_, err = s.db.Exec(`
			UPDATE file_tree SET parent_path = ?, updated_at = CURRENT_TIMESTAMP
			WHERE rule_id = ? AND parent_path = ?
		`, newPath115, node.RuleID, oldPath115)
		if err != nil {
			return err
		}
	}

	return nil
}

// DeleteTreeNodeAndChildren 删除节点及其所有子节点（目录时递归删除）
func (s *Store) DeleteTreeNodeAndChildren(nodeID int64) (int64, error) {
	// 先获取当前节点
	row := s.db.QueryRow(`
		SELECT id, rule_id, name, path_115, cd2_path, mount_path, parent_path, is_dir, file_size, pick_code, sha1, cid, ext, strm_path, created_at, updated_at
		FROM file_tree WHERE id = ?
	`, nodeID)
	node, err := s.scanTreeNode(row)
	if err != nil || node == nil {
		return 0, fmt.Errorf("节点不存在: %d", nodeID)
	}

	var totalDeleted int64

	if node.IsDir {
		// 删除所有子节点
		result, err := s.db.Exec(`DELETE FROM file_tree WHERE rule_id = ? AND path_115 LIKE ?`, node.RuleID, node.Path115+"/%")
		if err != nil {
			return 0, err
		}
		childDeleted, _ := result.RowsAffected()
		totalDeleted += childDeleted
	}

	// 删除当前节点
	_, err = s.db.Exec(`DELETE FROM file_tree WHERE id = ?`, nodeID)
	if err != nil {
		return 0, err
	}
	totalDeleted++

	return totalDeleted, nil
}

// GetTreeNodeByID 根据ID获取节点
func (s *Store) GetTreeNodeByID(nodeID int64) (*model.FileTreeNode, error) {
	row := s.db.QueryRow(`
		SELECT id, rule_id, name, path_115, cd2_path, mount_path, parent_path, is_dir, file_size, pick_code, sha1, cid, ext, strm_path, created_at, updated_at
		FROM file_tree WHERE id = ?
	`, nodeID)
	return s.scanTreeNode(row)
}

// GetTreeNodesByCID 根据CID获取节点
func (s *Store) GetTreeNodesByCID(ruleID int64, cid string) ([]*model.FileTreeNode, error) {
	log.Printf("[Store] GetTreeNodesByCID: ruleID=%d, cid=%s", ruleID, cid)

	// 调试：查询数据库中文件夹节点的 CID 情况
	var dirCount, emptyCidCount int
	s.db.QueryRow("SELECT COUNT(*) FROM file_tree WHERE rule_id = ? AND is_dir = 1", ruleID).Scan(&dirCount)
	s.db.QueryRow("SELECT COUNT(*) FROM file_tree WHERE rule_id = ? AND is_dir = 1 AND (cid IS NULL OR cid = '')", ruleID).Scan(&emptyCidCount)
	log.Printf("[Store] 规则 %d: 共 %d 个文件夹, 其中 %d 个 CID 为空", ruleID, dirCount, emptyCidCount)

	rows, err := s.db.Query(`
		SELECT id, rule_id, name, path_115, cd2_path, mount_path, parent_path, is_dir, file_size, pick_code, sha1, cid, ext, strm_path, created_at, updated_at
		FROM file_tree WHERE rule_id = ? AND cid = ?
	`, ruleID, cid)
	if err != nil {
		log.Printf("[Store] GetTreeNodesByCID 查询出错: %v", err)
		return nil, err
	}
	defer rows.Close()

	var nodes []*model.FileTreeNode
	for rows.Next() {
		var n model.FileTreeNode
		var pickCode, sha1, cidVal, ext, strmPath sql.NullString
		err := rows.Scan(&n.ID, &n.RuleID, &n.Name, &n.Path115, &n.CD2Path, &n.MountPath,
			&n.ParentPath, &n.IsDir, &n.FileSize, &pickCode, &sha1, &cidVal, &ext, &strmPath,
			&n.CreatedAt, &n.UpdatedAt)
		if err != nil {
			return nil, err
		}
		if pickCode.Valid {
			n.PickCode = pickCode.String
		}
		if sha1.Valid {
			n.SHA1 = sha1.String
		}
		if cidVal.Valid {
			n.CID = cidVal.String
		}
		if ext.Valid {
			n.Ext = ext.String
		}
		if strmPath.Valid {
			n.STRMPath = strmPath.String
		}
		log.Printf("[Store] 找到节点: Name=%s, Path115=%s, IsDir=%v, CID=%s", n.Name, n.Path115, n.IsDir, n.CID)
		nodes = append(nodes, &n)
	}
	log.Printf("[Store] GetTreeNodesByCID 返回 %d 个节点", len(nodes))
	return nodes, rows.Err()
}

// UpdateRuleTreeStatus 更新规则的目录树状态
func (s *Store) UpdateRuleTreeStatus(ruleID int64, treeBuilt bool, treeFileCount int) error {
	_, err := s.db.Exec(`
		UPDATE strm_rules SET tree_built = ?, tree_file_count = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?
	`, treeBuilt, treeFileCount, ruleID)
	return err
}

// scanTreeNode 扫描单行目录树节点
func (s *Store) scanTreeNode(row *sql.Row) (*model.FileTreeNode, error) {
	var n model.FileTreeNode
	var pickCode, sha1, cid, ext, strmPath sql.NullString
	err := row.Scan(&n.ID, &n.RuleID, &n.Name, &n.Path115, &n.CD2Path, &n.MountPath,
		&n.ParentPath, &n.IsDir, &n.FileSize, &pickCode, &sha1, &cid, &ext, &strmPath,
		&n.CreatedAt, &n.UpdatedAt)
	if err == sql.ErrNoRows {
		return nil, nil
	}
	if err != nil {
		return nil, err
	}
	if pickCode.Valid {
		n.PickCode = pickCode.String
	}
	if sha1.Valid {
		n.SHA1 = sha1.String
	}
	if cid.Valid {
		n.CID = cid.String
	}
	if ext.Valid {
		n.Ext = ext.String
	}
	if strmPath.Valid {
		n.STRMPath = strmPath.String
	}
	return &n, nil
}

// scanTreeNodeRows 扫描多行目录树节点
func (s *Store) scanTreeNodeRows(rows *sql.Rows) (*model.FileTreeNode, error) {
	var n model.FileTreeNode
	var pickCode, sha1, cid, ext, strmPath sql.NullString
	err := rows.Scan(&n.ID, &n.RuleID, &n.Name, &n.Path115, &n.CD2Path, &n.MountPath,
		&n.ParentPath, &n.IsDir, &n.FileSize, &pickCode, &sha1, &cid, &ext, &strmPath,
		&n.CreatedAt, &n.UpdatedAt)
	if err != nil {
		return nil, err
	}
	if pickCode.Valid {
		n.PickCode = pickCode.String
	}
	if sha1.Valid {
		n.SHA1 = sha1.String
	}
	if cid.Valid {
		n.CID = cid.String
	}
	if ext.Valid {
		n.Ext = ext.String
	}
	if strmPath.Valid {
		n.STRMPath = strmPath.String
	}
	return &n, nil
}
