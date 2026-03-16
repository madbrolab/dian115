# 115生活事件轮询集成方案

## 一、架构设计

### 1.1 核心组件
```
LifeEventMonitor (新增)
├── 轮询器: 定期调用115生活事件API
├── 事件处理器: 根据事件类型执行相应操作
├── 数据存储: 保存事件记录到数据库
└── 与现有系统集成: 触发STRM生成/删除
```

### 1.2 数据流
```
115 API → 拉取事件 → 过滤处理 → 更新目录树 → 生成/删除STRM → 刷新媒体库
```

## 二、实现方案

### 2.1 数据库表结构

```sql
-- 生活事件表
CREATE TABLE life_events (
    id INTEGER PRIMARY KEY,           -- 事件ID
    type INTEGER NOT NULL,            -- 事件类型(1=上传,2=上传文件,5=移动图片,6=移动文件,14=接收,22=删除)
    file_id TEXT NOT NULL,            -- 文件ID
    parent_id TEXT NOT NULL,          -- 父目录ID
    file_name TEXT,                   -- 文件名
    file_category INTEGER,            -- 文件分类
    file_type INTEGER,                -- 文件类型
    file_size INTEGER,                -- 文件大小
    sha1 TEXT,                        -- SHA1值
    pick_code TEXT,                   -- PickCode
    update_time INTEGER,              -- 更新时间戳
    create_time INTEGER,              -- 创建时间戳
    processed BOOLEAN DEFAULT 0,      -- 是否已处理
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_life_events_type ON life_events(type);
CREATE INDEX idx_life_events_file_id ON life_events(file_id);
CREATE INDEX idx_life_events_processed ON life_events(processed);

-- 轮询状态表
CREATE TABLE life_event_state (
    id INTEGER PRIMARY KEY,
    from_time INTEGER NOT NULL,       -- 上次拉取的时间戳
    from_id INTEGER NOT NULL,         -- 上次拉取的事件ID
    last_pull_at DATETIME,            -- 最后拉取时间
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
);
```

### 2.2 115 API接口

需要在`Driver115Client`中添加生活事件API：

```go
// LifeEvent 生活事件结构
type LifeEvent struct {
    ID           int64  `json:"id"`
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
}

// GetLifeEvents 获取生活事件
// API: https://life.115.com/api/1.0/web/1.0/life/life_list
func (c *Driver115Client) GetLifeEvents(fromTime int64, fromID int64) ([]LifeEvent, error)
```

### 2.3 服务层实现

创建`internal/service/life_event.go`:

```go
type LifeEventService struct {
    store      *store.Store
    driver115  *client.Driver115Client
    treeSvc    *TreeService
    strmSvc    *STRMService
    running    bool
    stopCh     chan struct{}
    mu         sync.RWMutex
}

// 核心方法
- Start(): 启动轮询
- Stop(): 停止轮询
- pollOnce(): 单次拉取事件
- processEvent(event): 处理单个事件
- handleUpload(event): 处理上传事件
- handleMove(event): 处理移动事件
- handleDelete(event): 处理删除事件
```

### 2.4 轮询逻辑

```go
func (s *LifeEventService) pollLoop() {
    ticker := time.NewTicker(20 * time.Second)
    defer ticker.Stop()
    
    for {
        select {
        case <-s.stopCh:
            return
        case <-ticker.C:
            if err := s.pollOnce(); err != nil {
                log.Printf("[LifeEvent] 拉取失败: %v", err)
            }
        }
    }
}

func (s *LifeEventService) pollOnce() error {
    // 1. 获取上次状态
    state := s.store.GetLifeEventState()
    
    // 2. 调用115 API拉取事件
    events, err := s.driver115.GetLifeEvents(state.FromTime, state.FromID)
    if err != nil {
        return err
    }
    
    if len(events) == 0 {
        return nil // 无新事件
    }
    
    // 3. 保存事件到数据库
    s.store.SaveLifeEvents(events)
    
    // 4. 处理事件
    for _, event := range events {
        s.processEvent(&event)
    }
    
    // 5. 更新状态
    lastEvent := events[len(events)-1]
    s.store.UpdateLifeEventState(lastEvent.UpdateTime, lastEvent.ID)
    
    return nil
}
```

### 2.5 事件处理逻辑

```go
func (s *LifeEventService) processEvent(event *LifeEvent) {
    switch event.Type {
    case 1, 2: // 上传图片/文件
        s.handleUpload(event)
    case 5, 6: // 移动图片/文件
        s.handleMove(event)
    case 14: // 接收文件
        s.handleReceive(event)
    case 22: // 删除文件
        s.handleDelete(event)
    default:
        // 忽略其他事件类型
    }
}

func (s *LifeEventService) handleUpload(event *LifeEvent) {
    // 1. 检查文件是否在监控规则的源路径下
    rules := s.store.GetAllRules()
    for _, rule := range rules {
        if s.isFileInRulePath(event.FileID, rule) {
            // 2. 获取文件完整路径
            filePath := s.getFilePath(event.FileID)
            
            // 3. 触发快速扫描（复用现有逻辑）
            s.treeSvc.FastScanDirectory(rule, filePath, filePath)
            
            // 4. 标记事件已处理
            s.store.MarkLifeEventProcessed(event.ID)
        }
    }
}
```

## 三、集成步骤

### 3.1 最小化实现（推荐）

1. **添加数据库表** (store/migrations)
2. **实现115 API** (client/driver115.go)
3. **创建服务** (service/life_event.go)
4. **集成到主程序** (cmd/main.go)

### 3.2 配置项

```yaml
life_event:
  enabled: true              # 是否启用生活事件监控
  poll_interval: 20          # 轮询间隔(秒)
  initial_mode: "latest"     # 初始模式: latest(最新)/all(全部)/last(上次)
  event_types:               # 监控的事件类型
    - 1   # 上传图片
    - 2   # 上传文件
    - 5   # 移动图片
    - 6   # 移动文件
    - 14  # 接收文件
    - 22  # 删除文件
```

## 四、优势

1. **实时性**: 比定时全量扫描更快捷
2. **效率**: 只处理变化的文件，减少API调用
3. **准确性**: 直接从115获取事件，不会遗漏
4. **兼容性**: 与现有监控系统互补，不冲突

## 五、注意事项

1. **API限流**: 115生活事件API可能有频率限制，建议20秒轮询一次
2. **事件延迟**: 生活事件可能有几秒延迟，可配置等待时间
3. **重复处理**: 需要去重机制，避免重复生成STRM
4. **路径匹配**: 需要判断事件文件是否在规则监控路径下
5. **Cookie过期**: 需要处理登录失效情况

## 六、与现有系统的关系

```
现有系统:
- 实时监控(CloudDrive2文件系统事件) → 适合本地挂载场景
- 定时扫描(定期全量扫描) → 适合补漏和初始化

新增系统:
- 生活事件监控(115原生事件) → 适合直接操作115网盘的场景

三者互补，可同时启用
```
