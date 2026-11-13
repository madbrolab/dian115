# DIAN115 PT 连接插件

供 MoviePilot V2 / V3 加载的 Python 插件，版本 **1.1.0**，协议版本 **1**。它复用 MoviePilot 已安装的站点解析器、认证配置与取种链，为 DIAN115 提供站点搜索、RSS、账号统计和种子获取能力。默认禁用，安装后需要手动启用。

本插件安装在 **MoviePilot**，与 DIAN115 插件中心使用的 `.dian115p` 格式无关。订阅、候选筛选、种子解析和下载器操作由 DIAN115 管理；本插件不新增订阅、定时任务或数据库表。

## 下载与安装

本目录提供完整源码和打包脚本，不提供 MoviePilot 插件商店索引；不能将本仓库地址作为 MoviePilot 商店直接添加。

### 直接下载安装

下载 [dian115bridge-1.1.0.zip](https://github.com/madbrolab/dian115/releases/download/moviepilot-bridge-v1.1.0/dian115bridge-1.1.0.zip)，在 MoviePilot 的 **LocalPluginInstall → 本地安装** 中上传，然后启用“DIAN115 PT 连接”。无需自行打包或解压。

[发布页面](https://github.com/madbrolab/dian115/releases/tag/moviepilot-bridge-v1.1.0)提供版本说明和 SHA-256 校验文件。请选择 `dian115bridge-1.1.0.zip` 附件，GitHub 自动生成的 Source code ZIP 不能用于插件本地安装。

### 从源码打包

1. 下载本目录的 [package.py](package.py) 和 [插件源码](plugins.v2/dian115bridge/__init__.py)，保留相对目录结构；也可以下载整个仓库。
2. 在本目录运行以下命令，使用 Python 3 生成本地安装包：

   ```sh
   python3 package.py /tmp/dian115bridge-1.1.0.zip
   ```

   输出路径必须尚不存在。ZIP 中只有 `dian115bridge/__init__.py`，脚本同时输出 SHA-256 摘要。
3. 在已安装 **LocalPluginInstall** 的 MoviePilot 实例中，通过该插件的“本地安装”上传 ZIP。
4. 在 MoviePilot 插件配置中启用“DIAN115 PT 连接”。

LocalPluginInstall 负责热加载和持久化恢复；仅将文件放在容器中未持久化的 `/app/app/plugins` 下不能保证容器更新后保留。未安装 LocalPluginInstall 时，请使用目标 MoviePilot 实例支持的插件安装渠道。

## 连接 DIAN115

1. 在 DIAN115“系统设置 → PT 与 MoviePilot”保存并启用公共连接器，填写 MoviePilot 地址与 API 密钥。V2 使用 `API_TOKEN`，V3 使用 `API_KEY`，均通过 `X-API-KEY` 请求头传递。
2. 需要导入站点时，在站点管理页使用“从 MoviePilot 导入”，预览后勾选新增站点；已有同域名站点会保留原配置。
3. 将 PT 站点来源选择为“外置 MoviePilot”，检查远端站点并保存。DIAN115 按域名识别对应站点，必须通过插件协议和能力检查。
4. 在 DIAN115 配置自己的下载器和工作目录。MoviePilot 端无需为本插件配置下载器。

站点认证由 MoviePilot 管理。DIAN115 收到种子后使用自己的规则筛选候选、解析文件、计算缺集和逐文件选集，再直连下载器提交任务；成功提交即结算本轮获取，不在 MoviePilot 创建订阅或轮询下载进度。

## HTTP 合同

所有端点均为 `POST /api/v1/plugin/Dian115Bridge/{operation}`，由 MoviePilot 原生 `apikey` 鉴权，使用 `X-API-KEY`。成功返回 `{success:true,data:...}`，禁用返回 HTTP 409，拒绝或故障返回明确 HTTP 错误。

| operation | 参数 | 返回或行为 |
| --- | --- | --- |
| `capabilities` | `{}` | `protocol=1` 和支持的操作 |
| `search` | `site_id`、`keyword`、`media_type`、`category`、`page`（0 起）、`mteam_mode`、`published_after` / `published_before` | `torrents`、`page_size`、`raw_count`；使用原始爬虫，无远端订阅过滤 |
| `torrent` | `site_id`、`torrent` | `content`（Base64）；用当前 MoviePilot 站点凭据获取种子 |
| `rss` | `site_id` | `torrents`；无资源或失败返回明确错误 |
| `rss_url` | `site_id` | `url`；自动发现 RSS，不自动保存站点配置 |
| `userdata` | `site_id` | 账号统计允许字段，不返回 Cookie 或 API Key |

种子内容上限为 5 MiB。`mteam_window` 是 `capabilities` 返回的能力标记，通过 `search` 参数使用，不是独立端点。

1.1.0 已移除原型的 `downloader` 转发接口及 `file_selection` / `delete_keep_files` 标记。公共 MoviePilot 连接器仍可供 DIAN115 第三方插件独立调用 MoviePilot 原生 HTTP API，详见[公共连接器文档](../../dianying-and-moviepilot.md)。

## 验证与兼容性

```sh
python3 -B test_bridge.py
```

协议测试使用模拟 MoviePilot 模块，不需要实例或站点凭据，覆盖默认禁用、接口鉴权声明、停用站点拒绝执行、当前凭据取种、接口范围及 M-Team 时间窗口参数。

MoviePilot V2.15.6 已完成安装、原始搜索、取种与账号统计验证。源码包含 V3 导入路径兼容逻辑，但 V3 尚未完成实例验证；有效 RSS 资源场景也尚未完成实例验证。站点能力以目标 MoviePilot 版本、解析器和账号配置为准。

## 卸载

先在 DIAN115 将 PT 站点来源切回内置，再在 MoviePilot 停用或卸载本插件。已有下载、托管刷流和后处理继续使用 DIAN115 原有下载器；卸载不会取消 MoviePilot 订阅或删除下载器任务。
