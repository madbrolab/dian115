
# 115 STRM Manager

一个基于Go语言开发的115网盘STRM管理工具，支持Docker部署，提供Web管理界面。

## 功能特性

- 🎬 **STRM生成**: 根据CD2路径生成STRM文件，支持多规则配置
- 👁️ **实时监控**: 监控CD2文件变化，自动生成STRM
- 🔄 **Emby代理**: 反向代理Emby，播放时自动获取115直链
- 📱 **扫码登录**: 支持115扫码登录和手动Cookie设置
- 🎨 **Web界面**: 原生JS卡片布局，轻量无框架

## 快速开始

### Docker部署

```bash
# 1. 克隆项目
git clone https://github.com/yourname/strm-manager.git
cd strm-manager

# 2. 创建目录
mkdir -p config data

# 3. 启动服务
docker-compose up -d

# 4. 访问管理界面
# http://localhost:8095
```

### 配置说明

首次启动后，通过Web界面配置：

1. **CloudDrive2设置**
   - 服务地址：CD2的API地址
   - 用户名/密码：CD2登录凭据
   - 115挂载路径前缀：115在CD2中的挂载路径

2. **115网盘设置**
   - 扫码登录：使用115 APP扫码
   - 手动Cookie：从浏览器复制Cookie

3. **Emby设置**
   - 服务地址：Emby服务器地址
   - API Key：从Emby设置中获取

## 使用流程

### 1. 添加STRM规则

```
规则名称: 电影
源路径: /CloudNAS/CloudDrive/115/媒体库/电影
输出路径: /data/strm/电影
```

### 2. 同步生成STRM

点击"同步"按钮，程序会：
- 扫描CD2源路径下的视频文件
- 获取每个文件的pickcode
- 生成对应的STRM文件

### 3. 配置Emby媒体库

将STRM输出目录添加到Emby媒体库。

### 4. 使用Emby代理播放

客户端连接到本程序的代理端口（8095），播放时会自动获取115直链。

## 工作原理

### STRM文件内容

STRM文件内容是CD2的完整路径：
```
/CloudNAS/CloudDrive/115/媒体库/电影/xxx.mkv
```

### Emby代理流程

```
1. 客户端 → 本程序(:8095) → Emby(:8096)
2. 播放请求时，本程序拦截
3. 读取STRM路径 → 查询pickcode → 通过115 Android接口获取直链
4. 302
```

### 直链获取模式（cookie）

- 使用`proapi.115.com/android/2.0/ufile/download`获取直链，并根据URL里的`t`参数计算过期时间（提前5分钟）。
- 直链缓存按`pickcode + User-Agent`维度存储。
- 可选多端播放：开启后复制文件生成新`pickcode`获取直链，随后异步删除复制文件。
- 配置项（settings表）：
  - `115_same_playback`: `true/false`
  - `115_same_playback_pid`: 复制文件的目标目录ID（pid）