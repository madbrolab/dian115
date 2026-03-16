package store

import (
	"database/sql"
	"os"
	"path/filepath"
	"strings"
	"time"

	_ "github.com/mattn/go-sqlite3"

	"strm-manager/internal/model"
)

// Store 数据存储
type Store struct {
	db *sql.DB
}

// New 创建数据存储
func New(dbPath string) (*Store, error) {
	// 确保目录存在
	dir := filepath.Dir(dbPath)
	if err := os.MkdirAll(dir, 0755); err != nil {
		return nil, err
	}

	db, err := sql.Open("sqlite3", dbPath)
	if err != nil {
		return nil, err
	}

	// SQLite性能优化
	db.Exec("PRAGMA journal_mode=WAL")    // WAL模式，允许并发读写
	db.Exec("PRAGMA busy_timeout=30000")  // 写锁等待30秒
	db.Exec("PRAGMA synchronous=NORMAL")  // 降低fsync频率
	db.Exec("PRAGMA cache_size=-64000")   // 64MB缓存
	db.Exec("PRAGMA temp_store=MEMORY")   // 临时表存内存
	db.Exec("PRAGMA mmap_size=268435456") // 256MB内存映射

	s := &Store{db: db}
	if err := s.init(); err != nil {
		db.Close()
		return nil, err
	}

	return s, nil
}

// init 初始化数据库表
func (s *Store) init() error {
	// 创建规则表
	_, err := s.db.Exec(`
		CREATE TABLE IF NOT EXISTS strm_rules (
			id INTEGER PRIMARY KEY AUTOINCREMENT,
			name TEXT NOT NULL,
			source_path TEXT NOT NULL,
			output_path TEXT NOT NULL,
			recursive INTEGER DEFAULT 1,
			enabled INTEGER DEFAULT 1,
			sync_mode TEXT DEFAULT 'manual',
			cron_expr TEXT DEFAULT '',
			full_sync_cron TEXT DEFAULT '',
			meta_sync TEXT DEFAULT 'none',
			file_count INTEGER DEFAULT 0,
			last_sync_time DATETIME,
			created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
			updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
		)
	`)
	if err != nil {
		return err
	}

	// 迁移：添加新字段（如果不存在）
	s.db.Exec(`ALTER TABLE strm_rules ADD COLUMN sync_mode TEXT DEFAULT 'manual'`)
	s.db.Exec(`ALTER TABLE strm_rules ADD COLUMN cron_expr TEXT DEFAULT ''`)
	s.db.Exec(`ALTER TABLE strm_rules ADD COLUMN full_sync_cron TEXT DEFAULT ''`)
	s.db.Exec(`ALTER TABLE strm_rules ADD COLUMN last_sync_time DATETIME`)
	s.db.Exec(`ALTER TABLE strm_rules ADD COLUMN meta_sync TEXT DEFAULT 'none'`)

	// 创建文件映射表
	_, err = s.db.Exec(`
		CREATE TABLE IF NOT EXISTS file_mappings (
			id INTEGER PRIMARY KEY AUTOINCREMENT,
			cd2_path TEXT UNIQUE NOT NULL,
			pick_code TEXT NOT NULL,
			file_name TEXT NOT NULL,
			file_size INTEGER DEFAULT 0,
			strm_path TEXT,
			rule_id INTEGER,
			created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
			updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
		);
		CREATE INDEX IF NOT EXISTS idx_cd2_path ON file_mappings(cd2_path);
		CREATE INDEX IF NOT EXISTS idx_pick_code ON file_mappings(pick_code);
		CREATE INDEX IF NOT EXISTS idx_rule_id ON file_mappings(rule_id);
	`)
	if err != nil {
		return err
	}

	// 创建直链缓存表
	_, err = s.db.Exec(`
		CREATE TABLE IF NOT EXISTS link_cache (
			pick_code TEXT NOT NULL,
			user_agent TEXT NOT NULL,
			url TEXT NOT NULL,
			expires_at DATETIME NOT NULL,
			PRIMARY KEY (pick_code, user_agent)
		)
	`)
	if err != nil {
		return err
	}

	// 迁移旧表结构（单列pick_code主键）到新结构
	s.db.Exec(`ALTER TABLE link_cache ADD COLUMN user_agent TEXT DEFAULT 'NoUA'`)

	// 创建设置表
	_, err = s.db.Exec(`
		CREATE TABLE IF NOT EXISTS settings (
			key TEXT PRIMARY KEY,
			value TEXT NOT NULL,
			updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
		)
	`)
	if err != nil {
		return err
	}

	// 创建Emby代理表
	_, err = s.db.Exec(`
		CREATE TABLE IF NOT EXISTS emby_proxies (
			id INTEGER PRIMARY KEY AUTOINCREMENT,
			name TEXT NOT NULL,
			emby_host TEXT NOT NULL,
			api_key TEXT,
			proxy_port INTEGER NOT NULL,
			enabled INTEGER DEFAULT 1,
			local_only INTEGER DEFAULT 0,
			fallback_local INTEGER DEFAULT 1,
			cloud_name TEXT DEFAULT '',
			created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
			updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
		)
	`)
	if err != nil {
		return err
	}

	// 添加新字段（如果不存在）
	s.db.Exec(`ALTER TABLE emby_proxies ADD COLUMN local_only INTEGER DEFAULT 0`)
	s.db.Exec(`ALTER TABLE emby_proxies ADD COLUMN fallback_local INTEGER DEFAULT 1`)
	s.db.Exec(`ALTER TABLE emby_proxies ADD COLUMN cloud_name TEXT DEFAULT ''`)
	s.db.Exec(`ALTER TABLE strm_rules ADD COLUMN exclude_keys TEXT DEFAULT ''`)

	// 目录树相关字段迁移
	s.db.Exec(`ALTER TABLE strm_rules ADD COLUMN file_extensions TEXT DEFAULT ''`)
	s.db.Exec(`ALTER TABLE strm_rules ADD COLUMN clean_strm INTEGER DEFAULT 1`)
	s.db.Exec(`ALTER TABLE strm_rules ADD COLUMN clean_meta INTEGER DEFAULT 0`)
	s.db.Exec(`ALTER TABLE strm_rules ADD COLUMN clean_empty_dir INTEGER DEFAULT 0`)
	s.db.Exec(`ALTER TABLE strm_rules ADD COLUMN clean_dir_depth INTEGER DEFAULT 3`)
	s.db.Exec(`ALTER TABLE strm_rules ADD COLUMN smart_clean INTEGER DEFAULT 0`)
	s.db.Exec(`ALTER TABLE strm_rules ADD COLUMN meta_extensions TEXT DEFAULT ''`)
	s.db.Exec(`ALTER TABLE strm_rules ADD COLUMN cloud_name TEXT DEFAULT ''`)
	s.db.Exec(`ALTER TABLE strm_rules ADD COLUMN tree_built INTEGER DEFAULT 0`)
	s.db.Exec(`ALTER TABLE strm_rules ADD COLUMN tree_file_count INTEGER DEFAULT 0`)

	// 115账号表新增字段迁移
	s.db.Exec(`ALTER TABLE accounts_115 ADD COLUMN device_type TEXT DEFAULT 'web'`)
	s.db.Exec(`ALTER TABLE accounts_115 ADD COLUMN cookie_status TEXT DEFAULT 'unknown'`)
	s.db.Exec(`ALTER TABLE accounts_115 ADD COLUMN last_check_at DATETIME`)

	// 创建115账号表
	_, err = s.db.Exec(`
		CREATE TABLE IF NOT EXISTS accounts_115 (
			id INTEGER PRIMARY KEY AUTOINCREMENT,
			name TEXT NOT NULL,
			cookie TEXT NOT NULL,
			user_id TEXT,
			user_name TEXT,
			is_vip INTEGER DEFAULT 0,
			avatar_url TEXT DEFAULT '',
			avatar_local TEXT DEFAULT '',
			space_total INTEGER DEFAULT 0,
			space_used INTEGER DEFAULT 0,
			auto_sign INTEGER DEFAULT 0,
			is_active INTEGER DEFAULT 0,
			sort_order INTEGER DEFAULT 0,
			device_type TEXT DEFAULT 'ios',
			cookie_status TEXT DEFAULT 'unknown',
			last_check_at DATETIME,
			created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
			updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
		)
	`)
	if err != nil {
		return err
	}

	// 迁移：accounts_115新增字段
	s.db.Exec(`ALTER TABLE accounts_115 ADD COLUMN avatar_url TEXT DEFAULT ''`)
	s.db.Exec(`ALTER TABLE accounts_115 ADD COLUMN avatar_local TEXT DEFAULT ''`)
	s.db.Exec(`ALTER TABLE accounts_115 ADD COLUMN space_total INTEGER DEFAULT 0`)
	s.db.Exec(`ALTER TABLE accounts_115 ADD COLUMN space_used INTEGER DEFAULT 0`)
	s.db.Exec(`ALTER TABLE accounts_115 ADD COLUMN auto_sign INTEGER DEFAULT 0`)

	// 创建日志表
	_, err = s.db.Exec(`
		CREATE TABLE IF NOT EXISTS log_entries (
			id INTEGER PRIMARY KEY AUTOINCREMENT,
			type TEXT NOT NULL,
			category TEXT DEFAULT '',
			level TEXT NOT NULL,
			message TEXT NOT NULL,
			details TEXT,
			rule_id INTEGER DEFAULT 0,
			created_at DATETIME DEFAULT CURRENT_TIMESTAMP
		)
	`)
	if err != nil {
		return err
	}

	// 迁移：添加category字段（如果不存在），必须在创建索引之前
	s.db.Exec(`ALTER TABLE log_entries ADD COLUMN category TEXT DEFAULT ''`)

	// 创建索引（在迁移之后）
	s.db.Exec(`CREATE INDEX IF NOT EXISTS idx_log_type ON log_entries(type)`)
	s.db.Exec(`CREATE INDEX IF NOT EXISTS idx_log_category ON log_entries(category)`)
	s.db.Exec(`CREATE INDEX IF NOT EXISTS idx_log_level ON log_entries(level)`)
	s.db.Exec(`CREATE INDEX IF NOT EXISTS idx_log_created ON log_entries(created_at)`)

	// 创建历史记录表
	_, err = s.db.Exec(`
		CREATE TABLE IF NOT EXISTS history_records (
			id INTEGER PRIMARY KEY AUTOINCREMENT,
			type TEXT NOT NULL,
			rule_id INTEGER,
			rule_name TEXT,
			success INTEGER DEFAULT 0,
			failed INTEGER DEFAULT 0,
			deleted INTEGER DEFAULT 0,
			duration INTEGER DEFAULT 0,
			details TEXT,
			created_at DATETIME DEFAULT CURRENT_TIMESTAMP
		);
		CREATE INDEX IF NOT EXISTS idx_history_type ON history_records(type);
		CREATE INDEX IF NOT EXISTS idx_history_created ON history_records(created_at);
	`)
	if err != nil {
		return err
	}

	// 创建媒体分类表
	_, err = s.db.Exec(`
		CREATE TABLE IF NOT EXISTS media_categories (
			id INTEGER PRIMARY KEY AUTOINCREMENT,
			media_type TEXT NOT NULL,
			name TEXT NOT NULL,
			conditions TEXT,
			sort_order INTEGER DEFAULT 0,
			is_default INTEGER DEFAULT 0,
			created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
			updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
		)
	`)
	if err != nil {
		return err
	}

	// 创建整理规则表
	_, err = s.db.Exec(`
		CREATE TABLE IF NOT EXISTS organize_rules (
			id INTEGER PRIMARY KEY AUTOINCREMENT,
			name TEXT NOT NULL,
			source_path TEXT NOT NULL,
			target_path TEXT NOT NULL,
			media_type TEXT NOT NULL,
			use_category INTEGER DEFAULT 1,
			enabled INTEGER DEFAULT 1,
			created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
			updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
		)
	`)
	if err != nil {
		return err
	}

	// 创建播放记录表
	_, err = s.db.Exec(`
		CREATE TABLE IF NOT EXISTS play_records (
			id INTEGER PRIMARY KEY AUTOINCREMENT,
			file_name TEXT NOT NULL,
			file_path TEXT NOT NULL,
			user_agent TEXT,
			client_ip TEXT,
			proxy_id INTEGER,
			start_time DATETIME,
			end_time DATETIME,
			is_playing INTEGER DEFAULT 0,
			created_at DATETIME DEFAULT CURRENT_TIMESTAMP
		);
		CREATE INDEX IF NOT EXISTS idx_play_records_playing ON play_records(is_playing);
		CREATE INDEX IF NOT EXISTS idx_play_records_created ON play_records(created_at);
	`)
	if err != nil {
		return err
	}

	// 创建目录树表
	_, err = s.db.Exec(`
		CREATE TABLE IF NOT EXISTS file_tree (
			id INTEGER PRIMARY KEY AUTOINCREMENT,
			rule_id INTEGER NOT NULL,
			name TEXT NOT NULL,
			path_115 TEXT NOT NULL,
			cd2_path TEXT NOT NULL,
			mount_path TEXT NOT NULL,
			parent_path TEXT NOT NULL,
			is_dir INTEGER DEFAULT 0,
			file_size INTEGER DEFAULT 0,
			pick_code TEXT DEFAULT '',
			sha1 TEXT DEFAULT '',
			cid TEXT DEFAULT '',
			ext TEXT DEFAULT '',
			strm_path TEXT DEFAULT '',
			created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
			updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
		)
	`)
	if err != nil {
		return err
	}
	s.db.Exec(`CREATE INDEX IF NOT EXISTS idx_ft_rule_id ON file_tree(rule_id)`)
	s.db.Exec(`CREATE INDEX IF NOT EXISTS idx_ft_path_115 ON file_tree(path_115)`)
	s.db.Exec(`CREATE INDEX IF NOT EXISTS idx_ft_cd2_path ON file_tree(cd2_path)`)
	s.db.Exec(`CREATE INDEX IF NOT EXISTS idx_ft_parent_path ON file_tree(parent_path)`)
	s.db.Exec(`CREATE INDEX IF NOT EXISTS idx_ft_ext ON file_tree(ext)`)
	s.db.Exec(`CREATE INDEX IF NOT EXISTS idx_ft_cid ON file_tree(cid)`)
	s.db.Exec(`CREATE INDEX IF NOT EXISTS idx_ft_rule_cid ON file_tree(rule_id, cid)`)
	s.db.Exec(`CREATE UNIQUE INDEX IF NOT EXISTS idx_ft_rule_path ON file_tree(rule_id, path_115)`)

	// 创建监控配置表
	_, err = s.db.Exec(`
		CREATE TABLE IF NOT EXISTS monitor_config (
			id INTEGER PRIMARY KEY CHECK (id = 1),
			mode TEXT NOT NULL DEFAULT 'cd2',
			updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
		)
	`)
	if err != nil {
		return err
	}

	// 创建生活事件表
	_, err = s.db.Exec(`
		CREATE TABLE IF NOT EXISTS life_events (
			id INTEGER PRIMARY KEY,
			type INTEGER NOT NULL,
			file_id TEXT NOT NULL,
			parent_id TEXT NOT NULL,
			file_name TEXT,
			file_category INTEGER,
			file_type INTEGER,
			file_size INTEGER,
			sha1 TEXT,
			pick_code TEXT,
			update_time INTEGER,
			create_time INTEGER,
			processed INTEGER DEFAULT 0,
			created_at DATETIME DEFAULT CURRENT_TIMESTAMP
		);
		CREATE INDEX IF NOT EXISTS idx_life_events_type ON life_events(type);
		CREATE INDEX IF NOT EXISTS idx_life_events_file_id ON life_events(file_id);
		CREATE INDEX IF NOT EXISTS idx_life_events_processed ON life_events(processed);
	`)
	if err != nil {
		return err
	}

	// 创建生活事件状态表
	_, err = s.db.Exec(`
		CREATE TABLE IF NOT EXISTS life_event_state (
			id INTEGER PRIMARY KEY CHECK (id = 1),
			from_time INTEGER NOT NULL DEFAULT 0,
			from_id INTEGER NOT NULL DEFAULT 0,
			last_pull_at DATETIME,
			updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
		)
	`)
	if err != nil {
		return err
	}

	// 初始化默认监控配置
	s.db.Exec(`INSERT OR IGNORE INTO monitor_config (id, mode) VALUES (1, 'cd2')`)
	// 初始化默认生活事件状态
	s.db.Exec(`INSERT OR IGNORE INTO life_event_state (id, from_time, from_id) VALUES (1, 0, 0)`)

	// 初始化默认分类
	s.initDefaultCategories()

	return nil
}

// initDefaultCategories 初始化默认分类
func (s *Store) initDefaultCategories() {
	// 检查是否已有分类
	var count int
	s.db.QueryRow(`SELECT COUNT(*) FROM media_categories`).Scan(&count)
	if count > 0 {
		return
	}

	// 电影分类
	movieCategories := []struct {
		name       string
		conditions string
	}{
		{"动画电影", `{"genre_ids":"16"}`},
		{"华语电影", `{"original_language":"zh,cn,bo,za"}`},
		{"外语电影", `{}`},
	}

	for i, cat := range movieCategories {
		s.db.Exec(`INSERT INTO media_categories (media_type, name, conditions, sort_order, is_default) VALUES (?, ?, ?, ?, 1)`,
			"movie", cat.name, cat.conditions, i+1)
	}

	// 电视剧分类
	tvCategories := []struct {
		name       string
		conditions string
	}{
		{"纪录片", `{"genre_ids":"99"}`},
		{"动漫", `{"genre_ids":"10762,16"}`},
		{"综艺", `{"genre_ids":"10764,10767"}`},
		{"国产剧", `{"origin_country":"CN,TW,HK"}`},
		{"外语剧", `{}`},
	}

	for i, cat := range tvCategories {
		s.db.Exec(`INSERT INTO media_categories (media_type, name, conditions, sort_order, is_default) VALUES (?, ?, ?, ?, 1)`,
			"tv", cat.name, cat.conditions, i+1)
	}
}

// ==================== 监控模式相关 ====================

// GetMonitorConfig 获取监控配置
func (s *Store) GetMonitorConfig() (*model.MonitorConfig, error) {
	var config model.MonitorConfig
	err := s.db.QueryRow(`SELECT id, mode, updated_at FROM monitor_config WHERE id = 1`).
		Scan(&config.ID, &config.Mode, &config.UpdatedAt)
	if err == sql.ErrNoRows {
		return &model.MonitorConfig{ID: 1, Mode: model.MonitorModeCD2, UpdatedAt: time.Now()}, nil
	}
	return &config, err
}

// SetMonitorMode 设置监控模式
func (s *Store) SetMonitorMode(mode model.MonitorMode) error {
	_, err := s.db.Exec(`INSERT OR REPLACE INTO monitor_config (id, mode, updated_at) VALUES (1, ?, ?)`,
		mode, time.Now())
	return err
}

// GetLifeEventState 获取生活事件状态
func (s *Store) GetLifeEventState() (*model.LifeEventState, error) {
	var state model.LifeEventState
	var lastPullAt, updatedAt sql.NullTime
	err := s.db.QueryRow(`SELECT id, from_time, from_id, last_pull_at, updated_at FROM life_event_state WHERE id = 1`).
		Scan(&state.ID, &state.FromTime, &state.FromID, &lastPullAt, &updatedAt)
	if err == sql.ErrNoRows {
		return &model.LifeEventState{ID: 1, FromTime: 0, FromID: 0}, nil
	}
	if err != nil {
		return nil, err
	}
	if lastPullAt.Valid {
		state.LastPullAt = lastPullAt.Time
	}
	if updatedAt.Valid {
		state.UpdatedAt = updatedAt.Time
	}
	return &state, nil
}

// UpdateLifeEventState 更新生活事件状态
func (s *Store) UpdateLifeEventState(fromTime, fromID int64) error {
	_, err := s.db.Exec(`INSERT OR REPLACE INTO life_event_state (id, from_time, from_id, last_pull_at, updated_at) VALUES (1, ?, ?, ?, ?)`,
		fromTime, fromID, time.Now(), time.Now())
	return err
}

// SaveLifeEvents 批量保存生活事件
func (s *Store) SaveLifeEvents(events []model.LifeEvent) error {
	tx, err := s.db.Begin()
	if err != nil {
		return err
	}
	defer tx.Rollback()

	stmt, err := tx.Prepare(`INSERT OR REPLACE INTO life_events 
		(id, type, file_id, parent_id, file_name, file_category, file_type, file_size, sha1, pick_code, update_time, create_time, processed) 
		VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)`)
	if err != nil {
		return err
	}
	defer stmt.Close()

	for _, event := range events {
		_, err = stmt.Exec(event.ID, event.Type, event.FileID, event.ParentID, event.FileName,
			event.FileCategory, event.FileType, event.FileSize, event.SHA1, event.PickCode,
			event.UpdateTime, event.CreateTime, event.Processed)
		if err != nil {
			return err
		}
	}
	return tx.Commit()
}

// GetUnprocessedLifeEvents 获取未处理的生活事件
func (s *Store) GetUnprocessedLifeEvents(limit int) ([]model.LifeEvent, error) {
	rows, err := s.db.Query(`SELECT id, type, file_id, parent_id, file_name, file_category, file_type, 
		file_size, sha1, pick_code, update_time, create_time, processed, created_at 
		FROM life_events WHERE processed = 0 ORDER BY id LIMIT ?`, limit)
	if err != nil {
		return nil, err
	}
	defer rows.Close()

	var events []model.LifeEvent
	for rows.Next() {
		var event model.LifeEvent
		err := rows.Scan(&event.ID, &event.Type, &event.FileID, &event.ParentID, &event.FileName,
			&event.FileCategory, &event.FileType, &event.FileSize, &event.SHA1, &event.PickCode,
			&event.UpdateTime, &event.CreateTime, &event.Processed, &event.CreatedAt)
		if err != nil {
			return nil, err
		}
		events = append(events, event)
	}
	return events, rows.Err()
}

// MarkLifeEventProcessed 标记事件已处理
func (s *Store) MarkLifeEventProcessed(eventID int64) error {
	_, err := s.db.Exec(`UPDATE life_events SET processed = 1 WHERE id = ?`, eventID)
	return err
}

// Close 关闭数据库
func (s *Store) Close() error {
	return s.db.Close()
}

// CleanOldLogs 清理旧日志，保留最近 maxCount 条
func (s *Store) CleanOldLogs(maxCount int) error {
	_, err := s.db.Exec(`
		DELETE FROM log_entries
		WHERE id NOT IN (
			SELECT id FROM log_entries
			ORDER BY created_at DESC
			LIMIT ?
		)
	`, maxCount)
	return err
}

// Vacuum 压缩数据库
func (s *Store) Vacuum() error {
	_, err := s.db.Exec("VACUUM")
	return err
}

// ==================== 规则操作 ====================

// CreateRule 创建规则
func (s *Store) CreateRule(rule *model.STRMRule) error {
	if rule.SyncMode == "" {
		rule.SyncMode = model.SyncModeManual
	}
	if rule.CleanDirDepth == 0 {
		rule.CleanDirDepth = 3
	}
	result, err := s.db.Exec(`
		INSERT INTO strm_rules (name, source_path, output_path, recursive, enabled, sync_mode, cron_expr, full_sync_cron, meta_extensions, exclude_keys,
			file_extensions, smart_clean, clean_strm, clean_meta, clean_empty_dir, clean_dir_depth, cloud_name, tree_built, tree_file_count)
		VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
	`, rule.Name, rule.SourcePath, rule.OutputPath, rule.Recursive, rule.Enabled, rule.SyncMode, rule.CronExpr, rule.FullSyncCron, rule.MetaExtensions, rule.ExcludeKeys,
		rule.FileExtensions, rule.SmartClean, rule.CleanStrm, rule.CleanMeta, rule.CleanEmptyDir, rule.CleanDirDepth, rule.CloudName, rule.TreeBuilt, rule.TreeFileCount)
	if err != nil {
		return err
	}
	rule.ID, _ = result.LastInsertId()
	return nil
}

// UpdateRule 更新规则
func (s *Store) UpdateRule(rule *model.STRMRule) error {
	_, err := s.db.Exec(`
		UPDATE strm_rules SET
			name = ?, source_path = ?, output_path = ?,
			recursive = ?, enabled = ?, sync_mode = ?, cron_expr = ?, full_sync_cron = ?, meta_extensions = ?, exclude_keys = ?,
			file_extensions = ?, smart_clean = ?, clean_strm = ?, clean_meta = ?, clean_empty_dir = ?, clean_dir_depth = ?, cloud_name = ?,
			updated_at = CURRENT_TIMESTAMP
		WHERE id = ?
	`, rule.Name, rule.SourcePath, rule.OutputPath, rule.Recursive, rule.Enabled, rule.SyncMode, rule.CronExpr, rule.FullSyncCron, rule.MetaExtensions, rule.ExcludeKeys,
		rule.FileExtensions, rule.SmartClean, rule.CleanStrm, rule.CleanMeta, rule.CleanEmptyDir, rule.CleanDirDepth, rule.CloudName, rule.ID)
	return err
}

// DeleteRule 删除规则（同时删除关联的目录树）
func (s *Store) DeleteRule(id int64) error {
	// 先删除目录树
	_, err := s.db.Exec(`DELETE FROM file_tree WHERE rule_id = ?`, id)
	if err != nil {
		return err
	}
	// 再删除规则
	_, err = s.db.Exec(`DELETE FROM strm_rules WHERE id = ?`, id)
	return err
}

// GetRule 获取单个规则
func (s *Store) GetRule(id int64) (*model.STRMRule, error) {
	row := s.db.QueryRow(`
		SELECT id, name, source_path, output_path, recursive, enabled, sync_mode, cron_expr, full_sync_cron, meta_extensions, exclude_keys,
			file_extensions, smart_clean, clean_strm, clean_meta, clean_empty_dir, clean_dir_depth, cloud_name, tree_built, tree_file_count,
			file_count, last_sync_time, created_at, updated_at
		FROM strm_rules WHERE id = ?
	`, id)
	return s.scanRule(row)
}

// GetAllRules 获取所有规则
func (s *Store) GetAllRules() ([]*model.STRMRule, error) {
	rows, err := s.db.Query(`
		SELECT id, name, source_path, output_path, recursive, enabled, sync_mode, cron_expr, full_sync_cron, meta_extensions, exclude_keys,
			file_extensions, smart_clean, clean_strm, clean_meta, clean_empty_dir, clean_dir_depth, cloud_name, tree_built, tree_file_count,
			file_count, last_sync_time, created_at, updated_at
		FROM strm_rules ORDER BY id
	`)
	if err != nil {
		return nil, err
	}
	defer rows.Close()

	var rules []*model.STRMRule
	for rows.Next() {
		rule, err := s.scanRuleRows(rows)
		if err != nil {
			return nil, err
		}
		rules = append(rules, rule)
	}
	return rules, rows.Err()
}

// GetEnabledRules 获取启用的规则
func (s *Store) GetEnabledRules() ([]*model.STRMRule, error) {
	rows, err := s.db.Query(`
		SELECT id, name, source_path, output_path, recursive, enabled, sync_mode, cron_expr, full_sync_cron, meta_extensions, exclude_keys,
			file_extensions, smart_clean, clean_strm, clean_meta, clean_empty_dir, clean_dir_depth, cloud_name, tree_built, tree_file_count,
			file_count, last_sync_time, created_at, updated_at
		FROM strm_rules WHERE enabled = 1 ORDER BY id
	`)
	if err != nil {
		return nil, err
	}
	defer rows.Close()

	var rules []*model.STRMRule
	for rows.Next() {
		rule, err := s.scanRuleRows(rows)
		if err != nil {
			return nil, err
		}
		rules = append(rules, rule)
	}
	return rules, rows.Err()
}

// GetRulesBySyncMode 根据同步模式获取规则（支持逗号分隔的多模式匹配）
func (s *Store) GetRulesBySyncMode(syncMode model.SyncMode) ([]*model.STRMRule, error) {
	// 使用 LIKE 匹配，因为 sync_mode 可能是逗号分隔的多值如 "cron,realtime"
	pattern := "%" + string(syncMode) + "%"
	rows, err := s.db.Query(`
		SELECT id, name, source_path, output_path, recursive, enabled, sync_mode, cron_expr, full_sync_cron, meta_extensions, exclude_keys,
			file_extensions, smart_clean, clean_strm, clean_meta, clean_empty_dir, clean_dir_depth, cloud_name, tree_built, tree_file_count,
			file_count, last_sync_time, created_at, updated_at
		FROM strm_rules WHERE enabled = 1 AND sync_mode LIKE ? ORDER BY id
	`, pattern)
	if err != nil {
		return nil, err
	}
	defer rows.Close()

	var rules []*model.STRMRule
	for rows.Next() {
		rule, err := s.scanRuleRows(rows)
		if err != nil {
			return nil, err
		}
		rules = append(rules, rule)
	}
	return rules, rows.Err()
}

// UpdateRuleFileCount 更新规则文件数
func (s *Store) UpdateRuleFileCount(ruleID int64, count int) error {
	_, err := s.db.Exec(`
		UPDATE strm_rules SET file_count = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?
	`, count, ruleID)
	return err
}

// UpdateRuleLastSyncTime 更新规则最后同步时间
func (s *Store) UpdateRuleLastSyncTime(ruleID int64, syncTime time.Time) error {
	_, err := s.db.Exec(`
		UPDATE strm_rules SET last_sync_time = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?
	`, syncTime, ruleID)
	return err
}

func (s *Store) scanRule(row *sql.Row) (*model.STRMRule, error) {
	var r model.STRMRule
	var syncMode sql.NullString
	var cronExpr sql.NullString
	var fullSyncCron sql.NullString
	var metaExtensions sql.NullString
	var excludeKeys sql.NullString
	var fileExtensions sql.NullString
	var cloudName sql.NullString
	var cleanDirDepth sql.NullInt64
	var lastSyncTime sql.NullTime
	err := row.Scan(&r.ID, &r.Name, &r.SourcePath, &r.OutputPath, &r.Recursive, &r.Enabled, &syncMode, &cronExpr, &fullSyncCron, &metaExtensions, &excludeKeys,
		&fileExtensions, &r.SmartClean, &r.CleanStrm, &r.CleanMeta, &r.CleanEmptyDir, &cleanDirDepth, &cloudName, &r.TreeBuilt, &r.TreeFileCount,
		&r.FileCount, &lastSyncTime, &r.CreatedAt, &r.UpdatedAt)
	if err == sql.ErrNoRows {
		return nil, nil
	}
	if syncMode.Valid {
		r.SyncMode = model.SyncMode(syncMode.String)
	} else {
		r.SyncMode = model.SyncModeManual
	}
	if cronExpr.Valid {
		r.CronExpr = cronExpr.String
	}
	if fullSyncCron.Valid {
		r.FullSyncCron = fullSyncCron.String
	}
	if metaExtensions.Valid {
		r.MetaExtensions = metaExtensions.String
	}
	if excludeKeys.Valid {
		r.ExcludeKeys = excludeKeys.String
	}
	if fileExtensions.Valid {
		r.FileExtensions = fileExtensions.String
	}
	if cloudName.Valid {
		r.CloudName = cloudName.String
	}
	if cleanDirDepth.Valid {
		r.CleanDirDepth = int(cleanDirDepth.Int64)
	} else {
		r.CleanDirDepth = 3
	}
	if lastSyncTime.Valid {
		r.LastSyncTime = lastSyncTime.Time
	}
	return &r, err
}

func (s *Store) scanRuleRows(rows *sql.Rows) (*model.STRMRule, error) {
	var r model.STRMRule
	var syncMode sql.NullString
	var cronExpr sql.NullString
	var fullSyncCron sql.NullString
	var metaExtensions sql.NullString
	var excludeKeys sql.NullString
	var fileExtensions sql.NullString
	var cloudName sql.NullString
	var cleanDirDepth sql.NullInt64
	var lastSyncTime sql.NullTime
	err := rows.Scan(&r.ID, &r.Name, &r.SourcePath, &r.OutputPath, &r.Recursive, &r.Enabled, &syncMode, &cronExpr, &fullSyncCron, &metaExtensions, &excludeKeys,
		&fileExtensions, &r.SmartClean, &r.CleanStrm, &r.CleanMeta, &r.CleanEmptyDir, &cleanDirDepth, &cloudName, &r.TreeBuilt, &r.TreeFileCount,
		&r.FileCount, &lastSyncTime, &r.CreatedAt, &r.UpdatedAt)
	if syncMode.Valid {
		r.SyncMode = model.SyncMode(syncMode.String)
	} else {
		r.SyncMode = model.SyncModeManual
	}
	if cronExpr.Valid {
		r.CronExpr = cronExpr.String
	}
	if fullSyncCron.Valid {
		r.FullSyncCron = fullSyncCron.String
	}
	if metaExtensions.Valid {
		r.MetaExtensions = metaExtensions.String
	}
	if excludeKeys.Valid {
		r.ExcludeKeys = excludeKeys.String
	}
	if fileExtensions.Valid {
		r.FileExtensions = fileExtensions.String
	}
	if cloudName.Valid {
		r.CloudName = cloudName.String
	}
	if cleanDirDepth.Valid {
		r.CleanDirDepth = int(cleanDirDepth.Int64)
	} else {
		r.CleanDirDepth = 3
	}
	if lastSyncTime.Valid {
		r.LastSyncTime = lastSyncTime.Time
	}
	return &r, err
}

// ==================== 文件映射操作 ====================

// SaveFileMapping 保存文件映射
func (s *Store) SaveFileMapping(f *model.FileMapping) error {
	_, err := s.db.Exec(`
		INSERT INTO file_mappings (cd2_path, pick_code, file_name, file_size, strm_path, rule_id, updated_at)
		VALUES (?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
		ON CONFLICT(cd2_path) DO UPDATE SET
			pick_code = excluded.pick_code,
			file_name = excluded.file_name,
			file_size = excluded.file_size,
			strm_path = excluded.strm_path,
			rule_id = excluded.rule_id,
			updated_at = CURRENT_TIMESTAMP
	`, f.CD2Path, f.PickCode, f.FileName, f.FileSize, f.STRMPath, f.RuleID)
	return err
}

// GetFileMappingByCD2Path 根据CD2路径获取映射
// 支持精确匹配和后缀匹配（处理挂载前缀差异）
func (s *Store) GetFileMappingByCD2Path(cd2Path string) (*model.FileMapping, error) {
	// 1. 先尝试精确匹配
	row := s.db.QueryRow(`
		SELECT id, cd2_path, pick_code, file_name, file_size, strm_path, rule_id, created_at, updated_at
		FROM file_mappings WHERE cd2_path = ?
	`, cd2Path)
	mapping, err := s.scanFileMapping(row)
	if err == nil && mapping != nil {
		return mapping, nil
	}

	// 2. 尝试后缀匹配（处理挂载前缀差异）
	// 例如：查询 /115/电影/xxx.mkv 能匹配到 /CloudNAS/CloudDrive/115/电影/xxx.mkv
	row = s.db.QueryRow(`
		SELECT id, cd2_path, pick_code, file_name, file_size, strm_path, rule_id, created_at, updated_at
		FROM file_mappings WHERE cd2_path LIKE ?
	`, "%"+cd2Path)
	return s.scanFileMapping(row)
}

// GetFileMappingByPickCode 根据pickcode获取映射
func (s *Store) GetFileMappingByPickCode(pickCode string) (*model.FileMapping, error) {
	row := s.db.QueryRow(`
		SELECT id, cd2_path, pick_code, file_name, file_size, strm_path, rule_id, created_at, updated_at
		FROM file_mappings WHERE pick_code = ?
	`, pickCode)
	return s.scanFileMapping(row)
}

// GetFileMappingsByRuleID 根据规则ID获取映射列表
func (s *Store) GetFileMappingsByRuleID(ruleID int64) ([]*model.FileMapping, error) {
	rows, err := s.db.Query(`
		SELECT id, cd2_path, pick_code, file_name, file_size, strm_path, rule_id, created_at, updated_at
		FROM file_mappings WHERE rule_id = ?
	`, ruleID)
	if err != nil {
		return nil, err
	}
	defer rows.Close()

	var files []*model.FileMapping
	for rows.Next() {
		f, err := s.scanFileMappingRows(rows)
		if err != nil {
			return nil, err
		}
		files = append(files, f)
	}
	return files, rows.Err()
}

// GetFileMappingsByFileName 根据文件名获取映射列表
func (s *Store) GetFileMappingsByFileName(fileName string) ([]*model.FileMapping, error) {
	rows, err := s.db.Query(`
		SELECT id, cd2_path, pick_code, file_name, file_size, strm_path, rule_id, created_at, updated_at
		FROM file_mappings WHERE file_name = ?
	`, fileName)
	if err != nil {
		return nil, err
	}
	defer rows.Close()

	var files []*model.FileMapping
	for rows.Next() {
		f, err := s.scanFileMappingRows(rows)
		if err != nil {
			return nil, err
		}
		files = append(files, f)
	}
	return files, rows.Err()
}

// DeleteFileMappingsByRuleID 删除规则关联的所有映射
func (s *Store) DeleteFileMappingsByRuleID(ruleID int64) error {
	_, err := s.db.Exec(`DELETE FROM file_mappings WHERE rule_id = ?`, ruleID)
	return err
}

// DeleteFileMappingBySTRMPath 根据STRM路径删除映射
func (s *Store) DeleteFileMappingBySTRMPath(strmPath string) error {
	_, err := s.db.Exec(`DELETE FROM file_mappings WHERE strm_path = ?`, strmPath)
	return err
}

// GetFileMappingCount 获取文件映射总数
func (s *Store) GetFileMappingCount() (int, error) {
	var count int
	err := s.db.QueryRow(`SELECT COUNT(*) FROM file_mappings`).Scan(&count)
	return count, err
}

// GetFileMappingCountByRuleID 获取规则的文件映射数
func (s *Store) GetFileMappingCountByRuleID(ruleID int64) (int, error) {
	var count int
	err := s.db.QueryRow(`SELECT COUNT(*) FROM file_mappings WHERE rule_id = ?`, ruleID).Scan(&count)
	return count, err
}

func (s *Store) scanFileMapping(row *sql.Row) (*model.FileMapping, error) {
	var f model.FileMapping
	var strmPath sql.NullString
	err := row.Scan(&f.ID, &f.CD2Path, &f.PickCode, &f.FileName, &f.FileSize, &strmPath, &f.RuleID, &f.CreatedAt, &f.UpdatedAt)
	if err == sql.ErrNoRows {
		return nil, nil
	}
	if strmPath.Valid {
		f.STRMPath = strmPath.String
	}
	return &f, err
}

func (s *Store) scanFileMappingRows(rows *sql.Rows) (*model.FileMapping, error) {
	var f model.FileMapping
	var strmPath sql.NullString
	err := rows.Scan(&f.ID, &f.CD2Path, &f.PickCode, &f.FileName, &f.FileSize, &strmPath, &f.RuleID, &f.CreatedAt, &f.UpdatedAt)
	if strmPath.Valid {
		f.STRMPath = strmPath.String
	}
	return &f, err
}

// ==================== 直链缓存操作 ====================

// SaveLinkCache 保存直链缓存
func (s *Store) SaveLinkCache(pickCode, userAgent, url string, expiresAt time.Time) error {
	_, err := s.db.Exec(`
		INSERT INTO link_cache (pick_code, user_agent, url, expires_at)
		VALUES (?, ?, ?, ?)
		ON CONFLICT(pick_code, user_agent) DO UPDATE SET
			url = excluded.url,
			expires_at = excluded.expires_at
	`, pickCode, normalizeUserAgent(userAgent), url, expiresAt)
	return err
}

// GetLinkCache 获取直链缓存
func (s *Store) GetLinkCache(pickCode, userAgent string) (*model.LinkCache, error) {
	row := s.db.QueryRow(`
		SELECT pick_code, user_agent, url, expires_at
		FROM link_cache
		WHERE pick_code = ? AND user_agent = ? AND expires_at > CURRENT_TIMESTAMP
	`, pickCode, normalizeUserAgent(userAgent))

	var c model.LinkCache
	err := row.Scan(&c.PickCode, &c.UserAgent, &c.URL, &c.ExpiresAt)
	if err == sql.ErrNoRows {
		return nil, nil
	}
	return &c, err
}

// DeleteExpiredCache 删除过期缓存
func (s *Store) DeleteExpiredCache() error {
	_, err := s.db.Exec(`DELETE FROM link_cache WHERE expires_at <= CURRENT_TIMESTAMP`)
	return err
}

func normalizeUserAgent(userAgent string) string {
	if strings.TrimSpace(userAgent) == "" {
		return "NoUA"
	}
	return userAgent
}

// ==================== 设置操作 ====================

// GetSetting 获取设置
func (s *Store) GetSetting(key string) (string, error) {
	var value string
	err := s.db.QueryRow(`SELECT value FROM settings WHERE key = ?`, key).Scan(&value)
	if err == sql.ErrNoRows {
		return "", nil
	}
	return value, err
}

// SetSetting 保存设置
func (s *Store) SetSetting(key, value string) error {
	_, err := s.db.Exec(`
		INSERT INTO settings (key, value, updated_at)
		VALUES (?, ?, CURRENT_TIMESTAMP)
		ON CONFLICT(key) DO UPDATE SET
			value = excluded.value,
			updated_at = CURRENT_TIMESTAMP
	`, key, value)
	return err
}

// GetAllSettings 获取所有设置
func (s *Store) GetAllSettings() (map[string]string, error) {
	rows, err := s.db.Query(`SELECT key, value FROM settings`)
	if err != nil {
		return nil, err
	}
	defer rows.Close()

	settings := make(map[string]string)
	for rows.Next() {
		var key, value string
		if err := rows.Scan(&key, &value); err != nil {
			return nil, err
		}
		settings[key] = value
	}
	return settings, rows.Err()
}

// DeleteSetting 删除设置
func (s *Store) DeleteSetting(key string) error {
	_, err := s.db.Exec(`DELETE FROM settings WHERE key = ?`, key)
	return err
}

// ==================== Emby代理操作 ====================

// CreateEmbyProxy 创建Emby代理
func (s *Store) CreateEmbyProxy(proxy *model.EmbyProxy) error {
	result, err := s.db.Exec(`
		INSERT INTO emby_proxies (name, emby_host, api_key, proxy_port, enabled, local_only, fallback_local, cloud_name)
		VALUES (?, ?, ?, ?, ?, ?, ?, ?)
	`, proxy.Name, proxy.EmbyHost, proxy.APIKey, proxy.ProxyPort, proxy.Enabled, proxy.LocalOnly, proxy.FallbackLocal, proxy.CloudName)
	if err != nil {
		return err
	}
	proxy.ID, _ = result.LastInsertId()
	return nil
}

// UpdateEmbyProxy 更新Emby代理
func (s *Store) UpdateEmbyProxy(proxy *model.EmbyProxy) error {
	_, err := s.db.Exec(`
		UPDATE emby_proxies SET
			name = ?, emby_host = ?, api_key = ?, proxy_port = ?, enabled = ?,
			local_only = ?, fallback_local = ?, cloud_name = ?, updated_at = CURRENT_TIMESTAMP
		WHERE id = ?
	`, proxy.Name, proxy.EmbyHost, proxy.APIKey, proxy.ProxyPort, proxy.Enabled,
		proxy.LocalOnly, proxy.FallbackLocal, proxy.CloudName, proxy.ID)
	return err
}

// DeleteEmbyProxy 删除Emby代理
func (s *Store) DeleteEmbyProxy(id int64) error {
	_, err := s.db.Exec(`DELETE FROM emby_proxies WHERE id = ?`, id)
	return err
}

// GetEmbyProxy 获取单个Emby代理
func (s *Store) GetEmbyProxy(id int64) (*model.EmbyProxy, error) {
	row := s.db.QueryRow(`
		SELECT id, name, emby_host, api_key, proxy_port, enabled, local_only, fallback_local, cloud_name, created_at, updated_at
		FROM emby_proxies WHERE id = ?
	`, id)
	return s.scanEmbyProxy(row)
}

// GetAllEmbyProxies 获取所有Emby代理
func (s *Store) GetAllEmbyProxies() ([]*model.EmbyProxy, error) {
	rows, err := s.db.Query(`
		SELECT id, name, emby_host, api_key, proxy_port, enabled, local_only, fallback_local, cloud_name, created_at, updated_at
		FROM emby_proxies ORDER BY id
	`)
	if err != nil {
		return nil, err
	}
	defer rows.Close()

	var proxies []*model.EmbyProxy
	for rows.Next() {
		p, err := s.scanEmbyProxyRows(rows)
		if err != nil {
			return nil, err
		}
		proxies = append(proxies, p)
	}
	return proxies, rows.Err()
}

// GetEnabledEmbyProxies 获取启用的Emby代理
func (s *Store) GetEnabledEmbyProxies() ([]*model.EmbyProxy, error) {
	rows, err := s.db.Query(`
		SELECT id, name, emby_host, api_key, proxy_port, enabled, local_only, fallback_local, cloud_name, created_at, updated_at
		FROM emby_proxies WHERE enabled = 1 ORDER BY id
	`)
	if err != nil {
		return nil, err
	}
	defer rows.Close()

	var proxies []*model.EmbyProxy
	for rows.Next() {
		p, err := s.scanEmbyProxyRows(rows)
		if err != nil {
			return nil, err
		}
		proxies = append(proxies, p)
	}
	return proxies, rows.Err()
}

func (s *Store) scanEmbyProxy(row *sql.Row) (*model.EmbyProxy, error) {
	var p model.EmbyProxy
	var apiKey, cloudName sql.NullString
	var localOnly, fallbackLocal sql.NullBool
	err := row.Scan(&p.ID, &p.Name, &p.EmbyHost, &apiKey, &p.ProxyPort, &p.Enabled, &localOnly, &fallbackLocal, &cloudName, &p.CreatedAt, &p.UpdatedAt)
	if err == sql.ErrNoRows {
		return nil, nil
	}
	if apiKey.Valid {
		p.APIKey = apiKey.String
	}
	if localOnly.Valid {
		p.LocalOnly = localOnly.Bool
	}
	if fallbackLocal.Valid {
		p.FallbackLocal = fallbackLocal.Bool
	} else {
		p.FallbackLocal = true // 默认值
	}
	if cloudName.Valid {
		p.CloudName = cloudName.String
	}
	return &p, err
}

func (s *Store) scanEmbyProxyRows(rows *sql.Rows) (*model.EmbyProxy, error) {
	var p model.EmbyProxy
	var apiKey, cloudName sql.NullString
	var localOnly, fallbackLocal sql.NullBool
	err := rows.Scan(&p.ID, &p.Name, &p.EmbyHost, &apiKey, &p.ProxyPort, &p.Enabled, &localOnly, &fallbackLocal, &cloudName, &p.CreatedAt, &p.UpdatedAt)
	if apiKey.Valid {
		p.APIKey = apiKey.String
	}
	if localOnly.Valid {
		p.LocalOnly = localOnly.Bool
	}
	if fallbackLocal.Valid {
		p.FallbackLocal = fallbackLocal.Bool
	} else {
		p.FallbackLocal = true // 默认值
	}
	if cloudName.Valid {
		p.CloudName = cloudName.String
	}
	return &p, err
}

// ==================== 115账号操作 ====================

// CreateAccount115 创建115账号
func (s *Store) CreateAccount115(account *model.Account115) error {
	// 获取最大排序值
	var maxOrder int
	s.db.QueryRow(`SELECT COALESCE(MAX(sort_order), 0) FROM accounts_115`).Scan(&maxOrder)
	account.SortOrder = maxOrder + 1

	if account.CookieStatus == "" {
		account.CookieStatus = model.CookieStatusUnknown
	}
	if account.DeviceType == "" {
		account.DeviceType = "ios"
	}

	result, err := s.db.Exec(`
		INSERT INTO accounts_115 (name, cookie, user_id, user_name, is_vip, avatar_url, avatar_local, space_total, space_used, auto_sign, is_active, sort_order, device_type, cookie_status)
		VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
	`, account.Name, account.Cookie, account.UserID, account.UserName, account.IsVIP, account.AvatarURL, account.AvatarLocal, account.SpaceTotal, account.SpaceUsed, account.AutoSign, account.IsActive, account.SortOrder, account.DeviceType, account.CookieStatus)
	if err != nil {
		return err
	}
	account.ID, _ = result.LastInsertId()
	return nil
}

// UpdateAccount115 更新115账号
func (s *Store) UpdateAccount115(account *model.Account115) error {
	_, err := s.db.Exec(`
		UPDATE accounts_115 SET
			name = ?, cookie = ?, user_id = ?, user_name = ?, is_vip = ?, avatar_url = ?, avatar_local = ?, space_total = ?, space_used = ?, auto_sign = ?, is_active = ?, sort_order = ?, device_type = ?, cookie_status = ?, updated_at = CURRENT_TIMESTAMP
		WHERE id = ?
	`, account.Name, account.Cookie, account.UserID, account.UserName, account.IsVIP, account.AvatarURL, account.AvatarLocal, account.SpaceTotal, account.SpaceUsed, account.AutoSign, account.IsActive, account.SortOrder, account.DeviceType, account.CookieStatus, account.ID)
	return err
}

// UpdateAccount115CookieStatus 更新cookie状态
func (s *Store) UpdateAccount115CookieStatus(id int64, status string) error {
	_, err := s.db.Exec(`UPDATE accounts_115 SET cookie_status = ?, last_check_at = CURRENT_TIMESTAMP, updated_at = CURRENT_TIMESTAMP WHERE id = ?`, status, id)
	return err
}

// DeleteAccount115 删除115账号
func (s *Store) DeleteAccount115(id int64) error {
	_, err := s.db.Exec(`DELETE FROM accounts_115 WHERE id = ?`, id)
	return err
}

// GetAccount115 获取单个115账号
func (s *Store) GetAccount115(id int64) (*model.Account115, error) {
	row := s.db.QueryRow(`
		SELECT id, name, cookie, user_id, user_name, is_vip, avatar_url, avatar_local, space_total, space_used, auto_sign, is_active, sort_order, device_type, cookie_status, last_check_at, created_at, updated_at
		FROM accounts_115 WHERE id = ?
	`, id)
	return s.scanAccount115(row)
}

// GetAllAccounts115 获取所有115账号（按排序顺序）
func (s *Store) GetAllAccounts115() ([]*model.Account115, error) {
	rows, err := s.db.Query(`
		SELECT id, name, cookie, user_id, user_name, is_vip, avatar_url, avatar_local, space_total, space_used, auto_sign, is_active, sort_order, device_type, cookie_status, last_check_at, created_at, updated_at
		FROM accounts_115 ORDER BY sort_order ASC
	`)
	if err != nil {
		return nil, err
	}
	defer rows.Close()

	var accounts []*model.Account115
	for rows.Next() {
		a, err := s.scanAccount115Rows(rows)
		if err != nil {
			return nil, err
		}
		accounts = append(accounts, a)
	}
	return accounts, rows.Err()
}

// GetActiveAccount115 获取当前激活的115账号
func (s *Store) GetActiveAccount115() (*model.Account115, error) {
	row := s.db.QueryRow(`
		SELECT id, name, cookie, user_id, user_name, is_vip, avatar_url, avatar_local, space_total, space_used, auto_sign, is_active, sort_order, device_type, cookie_status, last_check_at, created_at, updated_at
		FROM accounts_115 WHERE is_active = 1 LIMIT 1
	`)
	return s.scanAccount115(row)
}

// GetNextValidAccount115 获取下一个cookie有效的账号（用于自动切换）
func (s *Store) GetNextValidAccount115(excludeID int64) (*model.Account115, error) {
	row := s.db.QueryRow(`
		SELECT id, name, cookie, user_id, user_name, is_vip, avatar_url, avatar_local, space_total, space_used, auto_sign, is_active, sort_order, device_type, cookie_status, last_check_at, created_at, updated_at
		FROM accounts_115 WHERE cookie_status = 'valid' AND id != ? ORDER BY sort_order ASC LIMIT 1
	`, excludeID)
	return s.scanAccount115(row)
}

// SetActiveAccount115 设置激活的115账号
func (s *Store) SetActiveAccount115(id int64) error {
	// 先取消所有账号的激活状态
	_, err := s.db.Exec(`UPDATE accounts_115 SET is_active = 0`)
	if err != nil {
		return err
	}
	// 设置指定账号为激活
	_, err = s.db.Exec(`UPDATE accounts_115 SET is_active = 1, updated_at = CURRENT_TIMESTAMP WHERE id = ?`, id)
	return err
}

// UpdateAccount115SortOrder 更新115账号排序
func (s *Store) UpdateAccount115SortOrder(id int64, sortOrder int) error {
	_, err := s.db.Exec(`UPDATE accounts_115 SET sort_order = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?`, sortOrder, id)
	return err
}

// ReorderAccounts115 重新排序115账号
func (s *Store) ReorderAccounts115(ids []int64) error {
	tx, err := s.db.Begin()
	if err != nil {
		return err
	}
	defer tx.Rollback()

	for i, id := range ids {
		_, err := tx.Exec(`UPDATE accounts_115 SET sort_order = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?`, i+1, id)
		if err != nil {
			return err
		}
	}

	return tx.Commit()
}

func (s *Store) scanAccount115(row *sql.Row) (*model.Account115, error) {
	var a model.Account115
	var userID, userName, deviceType, cookieStatus, avatarURL, avatarLocal sql.NullString
	var lastCheckAt sql.NullTime
	var spaceTotal, spaceUsed sql.NullInt64
	err := row.Scan(&a.ID, &a.Name, &a.Cookie, &userID, &userName, &a.IsVIP, &avatarURL, &avatarLocal, &spaceTotal, &spaceUsed, &a.AutoSign, &a.IsActive, &a.SortOrder, &deviceType, &cookieStatus, &lastCheckAt, &a.CreatedAt, &a.UpdatedAt)
	if err == sql.ErrNoRows {
		return nil, nil
	}
	if userID.Valid {
		a.UserID = userID.String
	}
	if userName.Valid {
		a.UserName = userName.String
	}
	if avatarURL.Valid {
		a.AvatarURL = avatarURL.String
	}
	if avatarLocal.Valid {
		a.AvatarLocal = avatarLocal.String
	}
	if spaceTotal.Valid {
		a.SpaceTotal = spaceTotal.Int64
	}
	if spaceUsed.Valid {
		a.SpaceUsed = spaceUsed.Int64
	}
	if deviceType.Valid {
		a.DeviceType = deviceType.String
	} else {
		a.DeviceType = "ios"
	}
	if cookieStatus.Valid {
		a.CookieStatus = cookieStatus.String
	} else {
		a.CookieStatus = model.CookieStatusUnknown
	}
	if lastCheckAt.Valid {
		a.LastCheckAt = lastCheckAt.Time
	}
	return &a, err
}

func (s *Store) scanAccount115Rows(rows *sql.Rows) (*model.Account115, error) {
	var a model.Account115
	var userID, userName, deviceType, cookieStatus, avatarURL, avatarLocal sql.NullString
	var lastCheckAt sql.NullTime
	var spaceTotal, spaceUsed sql.NullInt64
	err := rows.Scan(&a.ID, &a.Name, &a.Cookie, &userID, &userName, &a.IsVIP, &avatarURL, &avatarLocal, &spaceTotal, &spaceUsed, &a.AutoSign, &a.IsActive, &a.SortOrder, &deviceType, &cookieStatus, &lastCheckAt, &a.CreatedAt, &a.UpdatedAt)
	if userID.Valid {
		a.UserID = userID.String
	}
	if userName.Valid {
		a.UserName = userName.String
	}
	if avatarURL.Valid {
		a.AvatarURL = avatarURL.String
	}
	if avatarLocal.Valid {
		a.AvatarLocal = avatarLocal.String
	}
	if spaceTotal.Valid {
		a.SpaceTotal = spaceTotal.Int64
	}
	if spaceUsed.Valid {
		a.SpaceUsed = spaceUsed.Int64
	}
	if deviceType.Valid {
		a.DeviceType = deviceType.String
	} else {
		a.DeviceType = "ios"
	}
	if cookieStatus.Valid {
		a.CookieStatus = cookieStatus.String
	} else {
		a.CookieStatus = model.CookieStatusUnknown
	}
	if lastCheckAt.Valid {
		a.LastCheckAt = lastCheckAt.Time
	}
	return &a, err
}

// ==================== 日志操作 ====================

// CreateLogEntry 创建日志条目
func (s *Store) CreateLogEntry(entry *model.LogEntry) error {
	result, err := s.db.Exec(`
		INSERT INTO log_entries (type, category, level, message, details, rule_id)
		VALUES (?, ?, ?, ?, ?, ?)
	`, entry.Type, entry.Category, entry.Level, entry.Message, entry.Details, entry.RuleID)
	if err != nil {
		return err
	}
	entry.ID, _ = result.LastInsertId()
	return nil
}

// GetLogEntries 获取日志列表
func (s *Store) GetLogEntries(logType, category, level string, limit, offset int) ([]*model.LogEntry, int, error) {
	// 构建查询条件
	where := "1=1"
	args := []interface{}{}

	if logType != "" && logType != "all" {
		where += " AND type = ?"
		args = append(args, logType)
	}
	if category != "" && category != "all" {
		where += " AND category = ?"
		args = append(args, category)
	}
	if level != "" && level != "all" {
		where += " AND level = ?"
		args = append(args, level)
	}

	// 获取总数
	var total int
	countQuery := "SELECT COUNT(*) FROM log_entries WHERE " + where
	s.db.QueryRow(countQuery, args...).Scan(&total)

	// 获取数据
	query := "SELECT id, type, category, level, message, details, rule_id, created_at FROM log_entries WHERE " + where + " ORDER BY created_at DESC LIMIT ? OFFSET ?"
	args = append(args, limit, offset)

	rows, err := s.db.Query(query, args...)
	if err != nil {
		return nil, 0, err
	}
	defer rows.Close()

	var entries []*model.LogEntry
	for rows.Next() {
		var e model.LogEntry
		var details sql.NullString
		var category sql.NullString
		err := rows.Scan(&e.ID, &e.Type, &category, &e.Level, &e.Message, &details, &e.RuleID, &e.CreatedAt)
		if err != nil {
			return nil, 0, err
		}
		if details.Valid {
			e.Details = details.String
		}
		if category.Valid {
			e.Category = model.LogCategory(category.String)
		}
		entries = append(entries, &e)
	}
	return entries, total, rows.Err()
}

// ClearLogEntries 清空日志
func (s *Store) ClearLogEntries(logType string) error {
	if logType == "" || logType == "all" {
		_, err := s.db.Exec(`DELETE FROM log_entries`)
		return err
	}
	_, err := s.db.Exec(`DELETE FROM log_entries WHERE type = ?`, logType)
	return err
}

// GetLogStats 获取日志统计
func (s *Store) GetLogStats() (map[string]interface{}, error) {
	stats := make(map[string]interface{})

	// 按类型统计
	typeStats := make(map[string]int)
	rows, err := s.db.Query(`SELECT type, COUNT(*) FROM log_entries GROUP BY type`)
	if err != nil {
		return stats, err
	}
	defer rows.Close()

	for rows.Next() {
		var logType string
		var count int
		if err := rows.Scan(&logType, &count); err != nil {
			return stats, err
		}
		typeStats[logType] = count
	}
	stats["by_type"] = typeStats

	// 按级别统计
	levelStats := make(map[string]int)
	rows2, err := s.db.Query(`SELECT level, COUNT(*) FROM log_entries GROUP BY level`)
	if err != nil {
		return stats, err
	}
	defer rows2.Close()

	for rows2.Next() {
		var level string
		var count int
		if err := rows2.Scan(&level, &count); err != nil {
			return stats, err
		}
		levelStats[level] = count
	}
	stats["by_level"] = levelStats

	// 按类别统计
	categoryStats := make(map[string]int)
	rows3, err := s.db.Query(`SELECT COALESCE(category, ''), COUNT(*) FROM log_entries GROUP BY category`)
	if err != nil {
		return stats, err
	}
	defer rows3.Close()

	for rows3.Next() {
		var category string
		var count int
		if err := rows3.Scan(&category, &count); err != nil {
			return stats, err
		}
		if category == "" {
			category = "default"
		}
		categoryStats[category] = count
	}
	stats["by_category"] = categoryStats

	// 总数
	var total int
	s.db.QueryRow(`SELECT COUNT(*) FROM log_entries`).Scan(&total)
	stats["total"] = total

	// 今日数量
	var today int
	s.db.QueryRow(`SELECT COUNT(*) FROM log_entries WHERE created_at >= date('now')`).Scan(&today)
	stats["today"] = today

	// 今日错误数
	var todayErrors int
	s.db.QueryRow(`SELECT COUNT(*) FROM log_entries WHERE created_at >= date('now') AND level = 'error'`).Scan(&todayErrors)
	stats["today_errors"] = todayErrors

	return stats, nil
}

// ==================== 历史记录操作 ====================

// CreateHistoryRecord 创建历史记录
func (s *Store) CreateHistoryRecord(record *model.HistoryRecord) error {
	result, err := s.db.Exec(`
		INSERT INTO history_records (type, rule_id, rule_name, success, failed, deleted, duration, details)
		VALUES (?, ?, ?, ?, ?, ?, ?, ?)
	`, record.Type, record.RuleID, record.RuleName, record.Success, record.Failed, record.Deleted, record.Duration, record.Details)
	if err != nil {
		return err
	}
	record.ID, _ = result.LastInsertId()
	return nil
}

// GetHistoryRecords 获取历史记录
func (s *Store) GetHistoryRecords(recordType string, limit, offset int) ([]*model.HistoryRecord, int, error) {
	where := "1=1"
	args := []interface{}{}

	if recordType != "" && recordType != "all" {
		where += " AND type = ?"
		args = append(args, recordType)
	}

	// 获取总数
	var total int
	countQuery := "SELECT COUNT(*) FROM history_records WHERE " + where
	s.db.QueryRow(countQuery, args...).Scan(&total)

	// 获取数据
	query := "SELECT id, type, rule_id, rule_name, success, failed, deleted, duration, details, created_at FROM history_records WHERE " + where + " ORDER BY created_at DESC LIMIT ? OFFSET ?"
	args = append(args, limit, offset)

	rows, err := s.db.Query(query, args...)
	if err != nil {
		return nil, 0, err
	}
	defer rows.Close()

	var records []*model.HistoryRecord
	for rows.Next() {
		var r model.HistoryRecord
		var details, ruleName sql.NullString
		err := rows.Scan(&r.ID, &r.Type, &r.RuleID, &ruleName, &r.Success, &r.Failed, &r.Deleted, &r.Duration, &details, &r.CreatedAt)
		if err != nil {
			return nil, 0, err
		}
		if details.Valid {
			r.Details = details.String
		}
		if ruleName.Valid {
			r.RuleName = ruleName.String
		}
		records = append(records, &r)
	}
	return records, total, rows.Err()
}

// GetHistoryStats 获取历史统计
func (s *Store) GetHistoryStats() (map[string]int, error) {
	stats := make(map[string]int)

	// 最近24小时的统计
	rows, err := s.db.Query(`
		SELECT type, COUNT(*) FROM history_records
		WHERE created_at > datetime('now', '-24 hours')
		GROUP BY type
	`)
	if err != nil {
		return stats, err
	}
	defer rows.Close()

	for rows.Next() {
		var recordType string
		var count int
		if err := rows.Scan(&recordType, &count); err != nil {
			return stats, err
		}
		stats[recordType] = count
	}
	return stats, rows.Err()
}

// ==================== 媒体分类操作 ====================

// CreateMediaCategory 创建媒体分类
func (s *Store) CreateMediaCategory(cat *model.MediaCategory) error {
	// 获取最大排序值
	var maxOrder int
	s.db.QueryRow(`SELECT COALESCE(MAX(sort_order), 0) FROM media_categories WHERE media_type = ?`, cat.MediaType).Scan(&maxOrder)
	cat.SortOrder = maxOrder + 1

	result, err := s.db.Exec(`
		INSERT INTO media_categories (media_type, name, conditions, sort_order, is_default)
		VALUES (?, ?, ?, ?, ?)
	`, cat.MediaType, cat.Name, cat.Conditions, cat.SortOrder, cat.IsDefault)
	if err != nil {
		return err
	}
	cat.ID, _ = result.LastInsertId()
	return nil
}

// UpdateMediaCategory 更新媒体分类
func (s *Store) UpdateMediaCategory(cat *model.MediaCategory) error {
	_, err := s.db.Exec(`
		UPDATE media_categories SET
			name = ?, conditions = ?, sort_order = ?, updated_at = CURRENT_TIMESTAMP
		WHERE id = ?
	`, cat.Name, cat.Conditions, cat.SortOrder, cat.ID)
	return err
}

// DeleteMediaCategory 删除媒体分类
func (s *Store) DeleteMediaCategory(id int64) error {
	// 检查是否为默认分类
	var isDefault bool
	s.db.QueryRow(`SELECT is_default FROM media_categories WHERE id = ?`, id).Scan(&isDefault)
	if isDefault {
		return nil // 默认分类不能删除
	}
	_, err := s.db.Exec(`DELETE FROM media_categories WHERE id = ?`, id)
	return err
}

// GetMediaCategories 获取媒体分类列表
func (s *Store) GetMediaCategories(mediaType string) ([]*model.MediaCategory, error) {
	query := `SELECT id, media_type, name, conditions, sort_order, is_default, created_at, updated_at FROM media_categories`
	args := []interface{}{}

	if mediaType != "" {
		query += ` WHERE media_type = ?`
		args = append(args, mediaType)
	}
	query += ` ORDER BY sort_order ASC`

	rows, err := s.db.Query(query, args...)
	if err != nil {
		return nil, err
	}
	defer rows.Close()

	var categories []*model.MediaCategory
	for rows.Next() {
		var c model.MediaCategory
		var conditions sql.NullString
		err := rows.Scan(&c.ID, &c.MediaType, &c.Name, &conditions, &c.SortOrder, &c.IsDefault, &c.CreatedAt, &c.UpdatedAt)
		if err != nil {
			return nil, err
		}
		if conditions.Valid {
			c.Conditions = conditions.String
		}
		categories = append(categories, &c)
	}
	return categories, rows.Err()
}

// ReorderMediaCategories 重新排序媒体分类
func (s *Store) ReorderMediaCategories(ids []int64) error {
	tx, err := s.db.Begin()
	if err != nil {
		return err
	}
	defer tx.Rollback()

	for i, id := range ids {
		_, err := tx.Exec(`UPDATE media_categories SET sort_order = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?`, i+1, id)
		if err != nil {
			return err
		}
	}

	return tx.Commit()
}

// ==================== 整理规则操作 ====================

// CreateOrganizeRule 创建整理规则
func (s *Store) CreateOrganizeRule(rule *model.OrganizeRule) error {
	result, err := s.db.Exec(`
		INSERT INTO organize_rules (name, source_path, target_path, media_type, use_category, enabled)
		VALUES (?, ?, ?, ?, ?, ?)
	`, rule.Name, rule.SourcePath, rule.TargetPath, rule.MediaType, rule.UseCategory, rule.Enabled)
	if err != nil {
		return err
	}
	rule.ID, _ = result.LastInsertId()
	return nil
}

// UpdateOrganizeRule 更新整理规则
func (s *Store) UpdateOrganizeRule(rule *model.OrganizeRule) error {
	_, err := s.db.Exec(`
		UPDATE organize_rules SET
			name = ?, source_path = ?, target_path = ?, media_type = ?, use_category = ?, enabled = ?, updated_at = CURRENT_TIMESTAMP
		WHERE id = ?
	`, rule.Name, rule.SourcePath, rule.TargetPath, rule.MediaType, rule.UseCategory, rule.Enabled, rule.ID)
	return err
}

// DeleteOrganizeRule 删除整理规则
func (s *Store) DeleteOrganizeRule(id int64) error {
	_, err := s.db.Exec(`DELETE FROM organize_rules WHERE id = ?`, id)
	return err
}

// GetOrganizeRules 获取整理规则列表
func (s *Store) GetOrganizeRules() ([]*model.OrganizeRule, error) {
	rows, err := s.db.Query(`
		SELECT id, name, source_path, target_path, media_type, use_category, enabled, created_at, updated_at
		FROM organize_rules ORDER BY id
	`)
	if err != nil {
		return nil, err
	}
	defer rows.Close()

	var rules []*model.OrganizeRule
	for rows.Next() {
		var r model.OrganizeRule
		err := rows.Scan(&r.ID, &r.Name, &r.SourcePath, &r.TargetPath, &r.MediaType, &r.UseCategory, &r.Enabled, &r.CreatedAt, &r.UpdatedAt)
		if err != nil {
			return nil, err
		}
		rules = append(rules, &r)
	}
	return rules, rows.Err()
}

// GetOrganizeRule 获取单个整理规则
func (s *Store) GetOrganizeRule(id int64) (*model.OrganizeRule, error) {
	row := s.db.QueryRow(`
		SELECT id, name, source_path, target_path, media_type, use_category, enabled, created_at, updated_at
		FROM organize_rules WHERE id = ?
	`, id)

	var r model.OrganizeRule
	err := row.Scan(&r.ID, &r.Name, &r.SourcePath, &r.TargetPath, &r.MediaType, &r.UseCategory, &r.Enabled, &r.CreatedAt, &r.UpdatedAt)
	if err == sql.ErrNoRows {
		return nil, nil
	}
	return &r, err
}

// ==================== 仪表板数据操作 ====================

// GetLibraryStats 获取入库统计
func (s *Store) GetLibraryStats() (*model.LibraryStats, error) {
	return s.GetLibraryStatsWithLimit(20) // 默认20条
}

// GetLibraryStatsWithLimit 获取入库统计（指定条数）
func (s *Store) GetLibraryStatsWithLimit(limit int) (*model.LibraryStats, error) {
	stats := &model.LibraryStats{
		LatestMovies: []model.LatestMovie{},
	}

	if limit <= 0 {
		limit = 20
	}
	if limit > 100 {
		limit = 100
	}

	// 获取总入库数
	s.db.QueryRow(`SELECT COUNT(*) FROM file_mappings`).Scan(&stats.Total)

	// 获取最新入库记录
	rows, err := s.db.Query(`
		SELECT id, file_name, cd2_path, created_at
		FROM file_mappings
		ORDER BY created_at DESC
		LIMIT ?
	`, limit)
	if err != nil {
		return stats, err
	}
	defer rows.Close()

	for rows.Next() {
		var m model.LatestMovie
		err := rows.Scan(&m.ID, &m.Name, &m.SourcePath, &m.AddedAt)
		if err != nil {
			continue
		}
		stats.LatestMovies = append(stats.LatestMovies, m)
	}

	return stats, nil
}

// GetSyncChartData 获取同步图表数据（最近30天）
func (s *Store) GetSyncChartData() (*model.SyncChartData, error) {
	data := &model.SyncChartData{
		Labels: []string{},
		Values: []int{},
	}

	// 获取最近30天的同步数据
	rows, err := s.db.Query(`
		SELECT date(created_at) as sync_date, COUNT(*) as count
		FROM file_mappings
		WHERE created_at >= date('now', '-30 days')
		GROUP BY date(created_at)
		ORDER BY sync_date ASC
	`)
	if err != nil {
		return data, err
	}
	defer rows.Close()

	for rows.Next() {
		var date string
		var count int
		if err := rows.Scan(&date, &count); err != nil {
			continue
		}
		data.Labels = append(data.Labels, date)
		data.Values = append(data.Values, count)
	}

	return data, nil
}

// ==================== 播放记录操作 ====================

// CreatePlayRecord 创建播放记录
func (s *Store) CreatePlayRecord(record *model.PlayRecord) error {
	result, err := s.db.Exec(`
		INSERT INTO play_records (file_name, file_path, user_agent, client_ip, proxy_id, start_time, is_playing)
		VALUES (?, ?, ?, ?, ?, ?, 1)
	`, record.FileName, record.FilePath, record.UserAgent, record.ClientIP, record.ProxyID, record.StartTime)
	if err != nil {
		return err
	}
	record.ID, _ = result.LastInsertId()
	return nil
}

// UpdatePlayRecordEnd 更新播放记录结束
func (s *Store) UpdatePlayRecordEnd(id int64) error {
	_, err := s.db.Exec(`
		UPDATE play_records SET is_playing = 0, end_time = CURRENT_TIMESTAMP WHERE id = ?
	`, id)
	return err
}

// GetRedirectStats 获取302跳转统计
func (s *Store) GetRedirectStats() (*model.RedirectStats, error) {
	stats := &model.RedirectStats{
		PlayingNow: []model.PlayingItem{},
	}

	// 正在播放数
	s.db.QueryRow(`SELECT COUNT(*) FROM play_records WHERE is_playing = 1`).Scan(&stats.Playing)

	// 今日播放数
	s.db.QueryRow(`SELECT COUNT(*) FROM play_records WHERE date(created_at) = date('now')`).Scan(&stats.Today)

	// 总播放数
	s.db.QueryRow(`SELECT COUNT(*) FROM play_records`).Scan(&stats.Total)

	// 正在播放的内容
	rows, err := s.db.Query(`
		SELECT file_name, client_ip, start_time
		FROM play_records
		WHERE is_playing = 1
		ORDER BY start_time DESC
		LIMIT 5
	`)
	if err != nil {
		return stats, err
	}
	defer rows.Close()

	for rows.Next() {
		var item model.PlayingItem
		var startTime sql.NullTime
		err := rows.Scan(&item.Title, &item.User, &startTime)
		if err != nil {
			continue
		}
		if startTime.Valid {
			item.StartTime = startTime.Time
		}
		stats.PlayingNow = append(stats.PlayingNow, item)
	}

	return stats, nil
}

// GetPlayRecords 获取播放记录列表
func (s *Store) GetPlayRecords(limit, offset int) ([]*model.PlayRecord, int, error) {
	var total int
	s.db.QueryRow(`SELECT COUNT(*) FROM play_records`).Scan(&total)

	rows, err := s.db.Query(`
		SELECT id, file_name, file_path, user_agent, client_ip, proxy_id, start_time, end_time, is_playing, created_at
		FROM play_records
		ORDER BY created_at DESC
		LIMIT ? OFFSET ?
	`, limit, offset)
	if err != nil {
		return nil, 0, err
	}
	defer rows.Close()

	var records []*model.PlayRecord
	for rows.Next() {
		var r model.PlayRecord
		var startTime, endTime sql.NullTime
		err := rows.Scan(&r.ID, &r.FileName, &r.FilePath, &r.UserAgent, &r.ClientIP, &r.ProxyID, &startTime, &endTime, &r.IsPlaying, &r.CreatedAt)
		if err != nil {
			continue
		}
		if startTime.Valid {
			r.StartTime = startTime.Time
		}
		if endTime.Valid {
			r.EndTime = endTime.Time
		}
		records = append(records, &r)
	}

	return records, total, nil
}

// ==================== 仪表板额外统计 ====================

// GetDashboardMetrics 获取仪表板关键指标
func (s *Store) GetDashboardMetrics() (*model.DashboardMetrics, error) {
	metrics := &model.DashboardMetrics{}

	// STRM文件总数
	s.db.QueryRow(`SELECT COUNT(*) FROM file_mappings`).Scan(&metrics.StrmTotal)

	// 今日新增
	s.db.QueryRow(`SELECT COUNT(*) FROM file_mappings WHERE date(created_at) = date('now')`).Scan(&metrics.StrmToday)

	// 24小时同步
	s.db.QueryRow(`SELECT COUNT(*) FROM file_mappings WHERE created_at >= datetime('now', '-24 hours')`).Scan(&metrics.Sync24h)

	// 错误数量
	s.db.QueryRow(`SELECT COUNT(*) FROM log_entries WHERE level = 'ERROR' AND created_at >= datetime('now', '-24 hours')`).Scan(&metrics.ErrorCount)

	return metrics, nil
}

// GetDriver115Stats 获取115网盘统计
func (s *Store) GetDriver115Stats() (*model.Driver115Stats, error) {
	stats := &model.Driver115Stats{}

	// 账号总数
	s.db.QueryRow(`SELECT COUNT(*) FROM accounts_115`).Scan(&stats.AccountCount)

	// 今日API调用（从日志中统计）
	s.db.QueryRow(`SELECT COUNT(*) FROM log_entries WHERE message LIKE '%115 API%' AND date(created_at) = date('now')`).Scan(&stats.ApiCallsToday)

	stats.SpaceUsed = "-" // 需要从115 API获取

	return stats, nil
}

// GetRecentActivity 获取最近活动
func (s *Store) GetRecentActivity(limit int) ([]model.ActivityLog, error) {
	if limit <= 0 {
		limit = 20
	}

	rows, err := s.db.Query(`
		SELECT id, level, message, created_at
		FROM log_entries
		WHERE level IN ('INFO', 'ERROR', 'WARN')
		ORDER BY created_at DESC
		LIMIT ?
	`, limit)
	if err != nil {
		return nil, err
	}
	defer rows.Close()

	var logs []model.ActivityLog
	for rows.Next() {
		var log model.ActivityLog
		err := rows.Scan(&log.ID, &log.Type, &log.Message, &log.CreatedAt)
		if err != nil {
			continue
		}
		logs = append(logs, log)
	}

	return logs, nil
}
