# 监控模式功能实现总结

## 已完成的后端实现

### 1. 数据库层 (Store)
- ✅ 添加了 `monitor_config` 表存储全局监控模式配置
- ✅ 添加了 `life_events` 表存储115生活事件
- ✅ 添加了 `life_event_state` 表存储轮询状态
- ✅ 实现了相关的CRUD操作方法

### 2. 模型层 (Model)
- ✅ 定义了 `MonitorMode` 枚举：`cd2` 和 `life_event`
- ✅ 定义了 `MonitorConfig`、`LifeEvent`、`LifeEventState` 结构体

### 3. 客户端层 (Client)
- ✅ 在 `Driver115Client` 中实现了 `GetLifeEvents()` API
- ✅ 调用115生活事件接口：`https://life.115.com/api/1.0/web/1.0/life/life_list`

### 4. 服务层 (Service)
- ✅ 创建了 `LifeEventService` 处理115生活事件轮询（30秒间隔）
- ✅ 创建了 `MonitorManager` 统一管理两种监控模式
- ✅ 实现了模式切换逻辑

### 5. API层
- ✅ 添加了 `GET /api/monitor/config` 获取监控配置
- ✅ 添加了 `PUT /api/monitor/mode` 设置监控模式

## 待完成的前端实现

### 需要在前端添加的功能：

1. **在STRM规则页面添加监控模式切换按钮**
   - 位置：在"添加规则"按钮左边
   - 两个选项：CD2监控 / 115生活事件监控
   - 调用API：`GET /api/monitor/config` 和 `PUT /api/monitor/mode`

2. **前端实现建议**：
```javascript
// 获取当前监控模式
fetch('/api/monitor/config')
  .then(res => res.json())
  .then(data => {
    currentMode = data.mode; // 'cd2' 或 'life_event'
  });

// 切换监控模式
fetch('/api/monitor/mode', {
  method: 'PUT',
  headers: { 'Content-Type': 'application/json' },
  body: JSON.stringify({ mode: 'life_event' }) // 或 'cd2'
})
  .then(res => res.json())
  .then(data => {
    console.log('监控模式已切换');
  });
```

## 工作原理

### CD2监控模式
- 监听CloudDrive2文件系统事件
- 实时响应文件变化
- 适合本地挂载场景

### 115生活事件监控模式
- 每30秒轮询115生活事件API
- 处理上传(1,2)、移动(5,6)、接收(14)、删除(22)事件
- 适合直接操作115网盘的场景
- 通过事件中的ParentID和FileID匹配目录树节点
- 触发快速扫描更新STRM文件

## 注意事项

1. **全局模式**：所有启用实时监控的规则共用同一个监控模式
2. **自动切换**：切换模式时会自动停止旧模式，启动新模式
3. **数据库初始化**：首次运行会自动创建表并初始化为CD2模式
4. **事件处理**：115生活事件需要目录树已构建才能正确匹配节点
