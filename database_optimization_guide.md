# 数据库优化指南 - 解决重启问题

## 问题分析
程序莫名重启的主要原因是数据库操作导致的崩溃，具体包括：
1. 缺少连接池配置
2. busy_timeout 太短（5秒）
3. 大量 ALTER TABLE 操作每次启动都执行
4. 没有错误恢复机制

## 立即修复方案

### 1. 修改 internal/store/sqlite.go 的 New 函数（第28-43行）

**原代码：**
```go
db, err := sql.Open("sqlite3", dbPath)
if err != nil {
    return nil, err
}

// SQLite性能优化
db.Exec("PRAGMA journal_mode=WAL")    // WAL模式，允许并发读写
db.Exec("PRAGMA busy_timeout=5000")   // 写锁等待5秒
db.Exec("PRAGMA synchronous=NORMAL")  // 降低fsync频率
db.Exec("PRAGMA cache_size=-64000")   // 64MB缓存
db.Exec("PRAGMA temp_store=MEMORY")   // 临时表存内存
db.Exec("PRAGMA mmap_size=268435456") // 256MB内存映射
```

**修改为：**
```go
db, err := sql.Open("sqlite3", dbPath)
if err != nil {
    return nil, err
}

// 连接池配置（关键修复）
db.SetMaxOpenConns(10)                    // 限制最大连接数
db.SetMaxIdleConns(5)                     // 保持空闲连接
db.SetConnMaxLifetime(time.Hour)          // 连接最大生命周期

// SQLite性能优化
db.Exec("PRAGMA journal_mode=WAL")        // WAL模式，允许并发读写
db.Exec("PRAGMA busy_timeout=30000")      // 写锁等待30秒（从5秒改为30秒）
db.Exec("PRAGMA synchronous=NORMAL")      // 降低fsync频率
db.Exec("PRAGMA cache_size=-64000")       // 64MB缓存
db.Exec("PRAGMA temp_store=MEMORY")       // 临时表存内存
db.Exec("PRAGMA mmap_size=268435456")     // 256MB内存映射

// 健康检查
if err := db.Ping(); err != nil {
    db.Close()
    return nil, fmt.Errorf("数据库连接失败: %w", err)
}
```

### 2. 优化 init() 函数中的 ALTER TABLE 操作

**问题：** 每次启动都执行20+个 ALTER TABLE，可能导致锁定

**解决方案：** 添加版本控制

在 init() 函数开始处添加：
```go
func (s *Store) init() error {
    // 检查数据库版本，避免重复迁移
    var dbVersion int
    s.db.QueryRow(`PRAGMA user_version`).Scan(&dbVersion)
    
    // 当前代码版本
    const currentVersion = 1
    
    if dbVersion >= currentVersion {
        // 数据库已是最新版本，跳过迁移
        return nil
    }
    
    // 执行迁移...// [原有的表创建和 ALTER TABLE 代码]
    
    // 更新版本号
    s.db.Exec(fmt.Sprintf(`PRAGMA user_version = %d`, currentVersion))
    
    return nil
}
```

### 3. 添加数据库操作重试机制

创建新文件 `internal/store/retry.go`:
```go
package store

import (
    "database/sql"
    "strings"
    "time"
)

// execWithRetry 带重试的执行
func (s *Store) execWithRetry(query string, args ...interface{}) error {
    maxRetries := 3
    for i := 0; i < maxRetries; i++ {
        _, err := s.db.Exec(query, args...)
        if err == nil {
            return nil
        }
        
        // 如果是数据库锁定错误，重试
        if strings.Contains(err.Error(), "database is locked") {
            time.Sleep(time.Second * time.Duration(i+1))
            continue
        }
        
        return err
    }
    return fmt.Errorf("执行失败，已重试%d次", maxRetries)
}
```

## 快速修复命令

```bash
# 1. 备份数据库
cp config/dian115.db config/dian115.db.backup

# 2. 检查数据库完整性
sqlite3 config/dian115.db "PRAGMA integrity_check;"

# 3. 清理WAL文件（如果过大）
sqlite3 config/dian115.db "PRAGMA wal_checkpoint(TRUNCATE);"

# 4. 重新编译程序
go build -o strm-manager.exe ./cmd
```

## 监控命令

```bash
# 查看数据库文件大小
ls -lh config/dian115.db*

# 监控日志中的数据库错误
tail -f logs/*.log | grep -i "database\|locked\|busy"
```

## 预期效果

修复后应该能解决：
- ✅ 数据库锁定导致的崩溃
- ✅ 连接耗尽导致的重启
- ✅ 启动时的长时间锁定
- ✅ 并发写入冲突

## 需要修改的文件

1. `internal/store/sqlite.go` - 添加连接池配置和增加 busy_timeout
2. `internal/store/sqlite.go` - 优化 init() 函数添加版本控制
3. `internal/store/retry.go` - 新建重试机制（可选）

修改完成后重新编译并重启服务即可。
