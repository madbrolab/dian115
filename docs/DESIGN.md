# 115 STRM Manager 设计文档

## 项目概述

一个基于Go语言开发的115网盘STRM管理工具，支持Docker部署，提供Web管理界面。

## 核心功能

### 1. STRM生成
- 根据CD2路径生成STRM文件到指定目录
- 支持多规则配置，不同类别生成到不同目录
- 批量生成和增量生成

### 2. 实时监控
- 通过CD2 API监控文件变化
- 当指定目录内文件有变化时，自动按规则生成STRM

### 3. Emby反向代理
- 代理Emby所有流量
- 拦截播放请求，获取STRM文件路径
- 使用115 Cookie获取直链，302跳转给播放端

### 4. 115登录管理
- 扫码登录获取Cookie
- 手动填写Cookie
- Cookie有效性检测

### 5. Web管理界面
- 原生JS + 卡片布局
- 无框架，轻量化

## 系统架构

```
┌─────────────────────────────────────────────────────────────────┐
│                     前端 (原生JS + 卡片布局)                     │
│  ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────┐           │
│  │ STRM规则  │ │ 文件监控  │ │ Emby代理  │ │ 系统设置  │           │
│  └──────────┘ └──────────┘ └──────────┘ └──────────┘           │
└─────────────────────────────────────────────────────────────────┘
                              │ HTTP API
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│                        后端 (Go + Gin)                           │
│                                                                 │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │                    API Server (:8095)                    │   │
│  │  - /api/*          管理API                               │   │
│  │  - /emby/*         Emby反向代理                          │   │
│  │  - /               前端静态文件                          │   │
│  └─────────────────────────────────────────────────────────┘   │
│                                                                 │
│  ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────┐          │
│  │ STRM生成  │ │ 文件监控  │ │ Emby代理  │ │ 115客户端 │          │
│  └──────────┘ └──────────┘ └──────────┘ └──────────┘          │
│                     │              │              │             │
│                     ▼              ▼              ▼             │
│              ┌─────────────────────────────────────┐           │
│              │         CloudDrive2 Client          │           │
│              └─────────────────────────────────────┘           │
└─────────────────────────────────────────────────────────────────┘
```

## 路径转换设计

### 问题分析

CD2路径示例:
```
/CloudNAS/CloudDrive/115open/媒体库/电影/动画电影/你看起来好像很好吃 (2010)/你看起来好像很好吃 (2010) - 1080p.mkv
```

需要解决:
1. CD2路径 → STRM文件路径
2. CD2路径 → 115 pickcode → 115直链

### 路径结构

```
CD2完整路径: /CloudNAS/CloudDrive/115open/媒体库/电影/动画电影/xxx.mkv
             ├─────────────────────┤├────┤├──────────────────────────┤
                  CD2挂载前缀        115云盘       115内部路径
                                    名称
```

### 配置示例

```yaml
# CD2配置
clouddrive2:
  host: "http://192.168.1.100:19798"
  username: "admin"
  password: "xxx"

# 路径映射
path_mapping:
  # CD2中115云盘的挂载路径前缀
  cd2_mount_prefix: "/CloudNAS/CloudDrive/115open"
  
  # STRM输出根目录
  strm_output_root: "/data/strm"

# STRM生成规则
strm_rules:
  - name: "电影"
    # 监控的CD2路径
    source_path: "/CloudNAS/CloudDrive/115open/媒体库/电影"
    # STRM输出目录
    output_path: "/data/strm/电影"
    # 是否递归
    recursive: true
    # 是否启用
    enabled: true
    
  - name: "电视剧"
    source_path: "/CloudNAS/CloudDrive/115open/媒体库/电视剧"
    output_path: "/data/strm/电视剧"
    recursive: true
    enabled: true
```

### 路径转换流程

```
1. CD2路径: /CloudNAS/CloudDrive/115open/媒体库/电影/xxx/xxx.mkv
                                        ↓
2. 提取115内部路径: /媒体库/电影/xxx/xxx.mkv
                                        ↓
3. 通过CD2 API获取文件信息，得到pickcode
                                        ↓
4. 存储映射: CD2路径 ↔ pickcode
                                        ↓
5. 生成STRM文件内容: CD2路径 (供Emby读取)
```

## Emby反向代理流程

```
┌─────────────────────────────────────────────────────────────────┐
│                     Emby反向代理流程                             │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│  1. 客户端访问本程序代理端口 (:8095)                             │
│     GET http://192.168.1.100:8095/emby/...                      │
│                                                                 │
│  2. 本程序转发请求给Emby (:8096)                                 │
│     GET http://127.0.0.1:8096/emby/...                          │
│                                                                 │
│  3. 当检测到播放请求时:                                          │
│     GET /emby/videos/{itemId}/stream                            │
│                                                                 │
│  4. 获取媒体信息，读取STRM文件路径                               │
│     Path: /CloudNAS/CloudDrive/115open/媒体库/电影/xxx.mkv       │
│                                                                 │
│  5. 从数据库查询pickcode                                         │
│     SELECT pick_code FROM files WHERE cd2_path = ?              │
│                                                                 │
│  6. 使用115 Cookie获取直链                                       │
│     POST https://proapi.115.com/app/chrome/downurl              │
│                                                                 │
│  7. 302跳转到直链                                                │
│     HTTP 302 Location: https://cdnfhnfile.115.com/xxxxx         │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

## 115扫码登录流程

```
┌─────────────────────────────────────────────────────────────────┐
│                     115扫码登录流程                              │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│  1. 前端请求获取二维码                                           │
│     GET /api/115/qrcode                                         │
│                                                                 │
│  2. 后端调用115 API获取二维码                                    │
│     GET https://qrcodeapi.115.com/api/1.0/web/1.0/token         │
│     返回: { uid, sign, time, qrcode_url }                       │
│                                                                 │
│  3. 前端显示二维码，用户扫码                                     │
│                                                                 │
│  4. 前端轮询登录状态                                             │
│     GET /api/115/qrcode/status?uid=xxx                          │
│                                                                 │
│  5. 后端检查扫码状态                                             │
│     GET https://qrcodeapi.115.com/get/status/?uid=xxx           │
│     状态: 0=等待扫码, 1=已扫码待确认, 2=已确认                   │
│                                                                 │
│  6. 扫码成功后获取Cookie                                         │
│     POST https://passportapi.115.com/app/1.0/web/1.0/login      │
│     返回Cookie: UID, CID, SEID等                                │
│                                                                 │
│  7. 保存Cookie到配置                                             │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

## 数据库设计

```sql
-- 文件映射表
CREATE TABLE file_mappings (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    cd2_path TEXT UNIQUE NOT NULL,      -- CD2完整路径
    pick_code TEXT NOT NULL,            -- 115 pickcode
    file_name TEXT NOT NULL,            -- 文件名
    file_size INTEGER DEFAULT 0,        -- 文件大小
    strm_path TEXT,                     -- 生成的STRM路径
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
);

-- 直链缓存表
CREATE TABLE link_cache (
    pick_code TEXT PRIMARY KEY,
    url TEXT NOT NULL,
    expires_at DATETIME NOT NULL
);

-- STRM规则表
CREATE TABLE strm_rules (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    source_path TEXT NOT NULL,
    output_path TEXT NOT NULL,
    recursive BOOLEAN DEFAULT 1,
    enabled BOOLEAN DEFAULT 1,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
);
```

## API设计

### STRM规则管理

```
GET    /api/rules              获取所有规则
POST   /api/rules              创建规则
PUT    /api/rules/:id          更新规则
DELETE /api/rules/:id          删除规则
POST   /api/rules/:id/sync     手动同步规则
```

### 文件监控

```
GET    /api/monitor/status     获取监控状态
POST   /api/monitor/start      启动监控
POST   /api/monitor/stop       停止监控
```

### 115登录

```
GET    /api/115/qrcode         获取登录二维码
GET    /api/115/qrcode/status  获取扫码状态
POST   /api/115/cookie         手动设置Cookie
GET    /api/115/status         获取登录状态
```

### 系统设置

```
GET    /api/settings           获取设置
PUT    /api/settings           更新设置
POST   /api/settings/test/cd2  测试CD2连接
POST   /api/settings/test/emby 测试Emby连接
```

### Emby代理

```
/*     /emby/*                 所有Emby请求代理
```

## 前端页面设计

### 页面结构

```
┌─────────────────────────────────────────────────────────────────┐
│  115 STRM Manager                              [设置] [关于]    │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │                    状态卡片区域                          │   │
│  │  ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────┐   │   │
│  │  │ CD2状态   │ │ 115状态  │ │ Emby状态  │ │ 监控状态  │   │   │
│  │  │ ✓ 已连接  │ │ ✓ 已登录 │ │ ✓ 已连接  │ │ ● 运行中  │   │   │
│  │  └──────────┘ └──────────┘ └──────────┘ └──────────┘   │   │
│  └─────────────────────────────────────────────────────────┘   │
│                                                                 │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │                    STRM规则卡片                          │   │
│  │  ┌─────────────────────────────────────────────────┐    │   │
│  │  │ 电影                                    [同步] [编辑] │    │   │
│  │  │ 源: /CloudNAS/.../媒体库/电影                       │    │   │
│  │  │ 目标: /data/strm/电影                              │    │   │
│  │  │ 状态: 已同步 1234 个文件                           │    │   │
│  │  └─────────────────────────────────────────────────┘    │   │
│  │  ┌─────────────────────────────────────────────────┐    │   │
│  │  │ 电视剧                                  [同步] [编辑] │    │   │
│  │  │ ...                                                │    │   │
│  │  └─────────────────────────────────────────────────┘    │   │
│  │                                        [+ 添加规则]      │   │
│  └─────────────────────────────────────────────────────────┘   │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

### 设置页面

```
┌─────────────────────────────────────────────────────────────────┐
│  设置                                                [返回]     │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │ CloudDrive2 设置                                        │   │
│  │ 地址: [http://192.168.1.100:19798    ]                 │   │
│  │ 用户名: [admin                        ]                 │   │
│  │ 密码: [••••••••                       ]                 │   │
│  │ 115挂载路径: [/CloudNAS/CloudDrive/115open]            │   │
│  │                                          [测试连接]     │   │
│  └─────────────────────────────────────────────────────────┘   │
│                                                                 │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │ 115网盘 设置                                            │   │
│  │                                                         │   │
│  │ [扫码登录]  或  [手动填写Cookie]                        │   │
│  │                                                         │   │
│  │ 当前状态: ✓ 已登录 (用户: xxx)                         │   │
│  └─────────────────────────────────────────────────────────┘   │
│                                                                 │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │ Emby 设置                                               │   │
│  │ 地址: [http://192.168.1.100:8096     ]                 │   │
│  │ API Key: [xxxxxxxxxxxxxxxx            ]                 │   │
│  │                                          [测试连接]     │   │
│  └─────────────────────────────────────────────────────────┘   │
│                                                                 │
│                                              [保存设置]         │
└─────────────────────────────────────────────────────────────────┘
```

## 目录结构

```
strm-manager/
├── cmd/
│   └── main.go                 # 主程序入口
├── internal/
│   ├── api/                    # HTTP API
│   │   ├── router.go           # 路由定义
│   │   ├── rules.go            # 规则API
│   │   ├── monitor.go          # 监控API
│   │   ├── auth115.go          # 115登录API
│   │   ├── settings.go         # 设置API
│   │   └── embyproxy.go        # Emby代理
│   ├── service/                # 业务逻辑
│   │   ├── strm.go             # STRM生成
│   │   ├── monitor.go          # 文件监控
│   │   └── emby.go             # Emby代理
│   ├── client/                 # 外部客户端
│   │   ├── clouddrive.go       # CD2客户端
│   │   └── driver115.go        # 115客户端
│   ├── model/                  # 数据模型
│   │   └── model.go
│   ├── store/                  # 数据存储
│   │   └── sqlite.go
│   └── config/                 # 配置管理
│       └── config.go
├── web/                        # 前端静态文件
│   ├── index.html
│   ├── css/
│   │   └── style.css
│   └── js/
│       └── app.js
├── config.yaml                 # 配置文件
├── Dockerfile
├── docker-compose.yml
└── README.md
```

## Docker配置

```yaml
# docker-compose.yml
version: '3.8'

services:
  strm-manager:
    build: .
    container_name: strm-manager
    restart: unless-stopped
    ports:
      - "8095:8095"
    volumes:
      - ./config:/app/config
      - ./data:/app/data
      - /mnt/strm:/data/strm        # STRM输出目录
    environment:
      - TZ=Asia/Shanghai