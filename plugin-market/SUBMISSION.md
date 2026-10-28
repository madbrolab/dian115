# 插件市场开发者提交指南

本文档说明第三方开发者如何通过 Pull Request 将插件提交到 DIAN115 官方插件市场。

## 前提条件

在提交 PR 之前，你必须完成以下步骤：

1. **开发并测试插件** — 按照 [开发者指南](../docs/plugin-platform/developer-guide.md) 完成插件开发
2. **打包并签名** — 生成完整的 `.d115p` 签名包（包含 `manifest.json`、`integrity.json`、`signature.json`）
3. **发布插件包** — 将 `.d115p` 文件上传到你控制的 HTTPS 地址（如 GitHub Releases、自有服务器等）

> 插件包必须托管在**你自己控制的 HTTPS 地址**，市场仓库不接收 `.d115p` 文件本身。

## 提交步骤

### 1. Fork 市场仓库

Fork [madbrolab/dian115](https://github.com/madbrolab/dian115) 仓库到你的账号。

### 2. 添加市场条目

编辑 `plugin-market/index.json`，在 `plugins` 数组中添加你的插件条目：

```json
{
  "id": "com.example.my-plugin",
  "name": "我的插件",
  "version": "1.0.0",
  "description": "插件功能简述",
  "author": "你的名字或团队名",
  "homepage": "https://github.com/yourname/my-plugin",
  "package_url": "https://github.com/yourname/my-plugin/releases/download/v1.0.0/my-plugin-1.0.0.d115p",
  "sha256": "你的插件包SHA256（小写64位十六进制）",
  "runtime": {
    "kind": "wasm",
    "protocol": "dian115:wasm@1",
    "autostart": true,
    "trust_level": "wasm-sandbox"
  },
  "permissions": {
    "apis": [
      {
        "method": "POST",
        "path": "/api/notifications/plugin",
        "reason": "发送任务完成通知"
      }
    ],
    "network": [
      {
        "origin": "https://api.example.com",
        "methods": ["GET", "POST"],
        "proxy_mode": "system",
        "reason": "调用外部API获取数据"
      }
    ]
  },
  "tags": ["工具", "自动化"]
}
```

### 3. 字段说明

| 字段 | 必需 | 说明 |
|------|:----:|------|
| `id` | ✅ | 反向域名格式，如 `com.example.my-plugin`，发布后不可变 |
| `name` | ✅ | 插件显示名称 |
| `version` | ✅ | SemVer 版本号，如 `1.0.0` |
| `package_url` | ✅ | `.d115p` 包的 HTTPS 下载地址 |
| `sha256` | ✅ | 包文件的小写 SHA-256（64位十六进制） |
| `runtime` | ✅ | 运行时披露，必须与包内 Manifest 一致 |
| `permissions` | ✅ | 权限声明，必须与包内 Manifest 一致 |
| `description` | ⬜ | 插件功能描述 |
| `author` | ⬜ | 作者或发布者名称 |
| `homepage` | ⬜ | 插件主页或文档地址 |
| `icon_url` | ⬜ | 插件图标地址（HTTPS 或相对路径） |
| `tags` | ⬜ | 分类标签数组 |

### 4. 运行时披露说明

**WASM 插件（唯一受支持的运行时）：**
```json
"runtime": {
  "kind": "wasm",
  "protocol": "dian115:wasm@1",
  "autostart": true,
  "trust_level": "wasm-sandbox"
}
```

原生进程运行时已经移除，`kind=process` 的市场条目会被拒绝。

> `autostart=true` 表示启用插件后由宿主自动监管运行时，不表示插件可以脱离宿主自行常驻。

### 5. 提交 Pull Request

1. 提交你的修改到你的 Fork 仓库
2. 创建 Pull Request 到 `madbrolab/dian115` 的 `main` 分支
3. PR 标题格式：`[Plugin] 添加插件 com.example.my-plugin v1.0.0`
4. PR 描述中请包含：
   - 插件功能简介
   - 插件仓库地址（如有）
   - 测试说明
   - 截图（如有）

## 插件包技术要求

### 包大小限制

| 项目 | 限制 |
|------|------|
| ZIP 压缩包大小 | 最大 32 MiB |
| 解压后总大小 | 最大 128 MiB |
| 单个文件大小 | 最大 32 MiB |
| ZIP 文件数量 | 最多 1024 个 |

### 必需文件

插件包根目录必须包含以下文件：

```
manifest.json      # 插件清单
integrity.json     # 完整性清单
signature.json     # Ed25519 签名
frontend/dist/index.html           # 完整 HTML 页面入口
frontend/dist/assets/...           # 页面脚本、样式和其他静态资源
runtime/plugin.wasm  # WASM 运行时（唯一受支持）
```

### 签名要求

- 使用 Ed25519 算法签名
- 签名内容：`DIAN115-PLUGIN-PACKAGE-V1` + `0x00` + `RFC8785-JCS(manifest.json)` + `0x00` + `RFC8785-JCS(integrity.json)`
- 私钥必须妥善保管，不得提交到任何仓库

## DIAN115 安装时验证流程

DIAN115 从市场拉取插件时会执行以下验证：

### 1. 下载阶段

- 从 `package_url` 下载插件包
- 验证包大小不超过 32 MiB
- 验证 SHA-256 与市场条目一致

### 2. 包验证阶段

- 验证 ZIP 结构完整性
- 验证必需文件存在（`manifest.json`、`integrity.json`、`signature.json`）
- 验证 Manifest ID 和 Version 与市场条目一致
- 验证完整性清单
- 验证 Ed25519 签名
- 验证运行时配置（WASM ABI）

### 3. 权限验证阶段

- 验证声明的 API 权限在 OpenAPI 中存在
- 验证权限声明与市场条目一致
- 生成权限同意摘要（consent_digest）

### 4. 安装阶段

- 安全解压到 `/config/package/<plugin-id>/`
- 注册插件运行时
- 启动插件进程（如启用）

## 审核标准

PR 会按以下标准审核：

### ✅ 必须满足

- [ ] 市场条目与包内 `manifest.json` 完全一致（ID、版本、运行时、权限）
- [ ] `sha256` 与实际 `.d115p` 文件匹配
- [ ] `package_url` 使用 HTTPS 且可正常下载
- [ ] 包大小符合限制（ZIP ≤ 32 MiB，解压 ≤ 128 MiB）
- [ ] 权限声明合理且每项都有明确的 `reason`
- [ ] 不包含 DIAN115 主项目源码、构建产物或私钥
- [ ] 通过 `node docs/plugin-platform/conformance/verify-public-surface.mjs` 检查

### ❌ 会被拒绝的情况

- 市场条目与包内 Manifest 不一致
- 权限声明过于宽泛或缺少合理理由
- 插件包无法下载或 SHA-256 不匹配
- 包大小超过限制
- 包含恶意代码或违反法律法规的内容
- 试图通过市场条目授予包内未声明的权限

## 更新插件版本

发布新版本时，**添加新条目**而不是修改旧条目：

```json
{
  "plugins": [
    {
      "id": "com.example.my-plugin",
      "version": "1.0.0",
      ...
    },
    {
      "id": "com.example.my-plugin",
      "version": "1.1.0",
      ...
    }
  ]
}
```

用户可以选择安装特定版本或更新到最新版本。

## 常见问题

### Q: 我可以把 `.d115p` 文件直接提交到市场仓库吗？

**不可以。** 市场仓库只接收索引、Schema、图标和插件作者发布地址。`.d115p` 文件必须托管在你控制的 HTTPS 地址。

### Q: 插件包有大小限制吗？

**有。** ZIP 压缩包最大 32 MiB，解压后最大 128 MiB，单个文件最大 32 MiB。

### Q: 我的插件需要审核多久？

通常在 1-3 个工作日内完成初审。如果发现问题，会在 PR 中留言说明需要修改的地方。

### Q: 插件被拒绝后可以重新提交吗？

可以。修复问题后，在同一个 PR 中更新或创建新 PR 即可。

### Q: 我可以在市场条目中声明额外的权限吗？

**不可以。** 市场条目中的权限必须与包内 `manifest.json` 完全一致，任何差异都会导致安装被拒绝。

### Q: DIAN115 会验证插件包的签名吗？

**会。** DIAN115 会验证 Ed25519 签名，确保插件包未被篡改且来自可信发布者。

## 相关文档

- [开发者指南](../docs/plugin-platform/developer-guide.md) — 插件开发完整流程
- [插件包格式](../docs/plugin-platform/package-format-v1.md) — `.d115p` 包结构详细说明
- [市场索引 Schema](../docs/plugin-platform/market-index.schema.json) — 市场条目 JSON Schema
- [公开发布边界](../docs/plugin-platform/publication-policy.md) — 可公开内容规范

## 联系与支持

- 提交 Issue: [GitHub Issues](https://github.com/madbrolab/dian115/issues)
- 插件开发问题：请在 Issue 中标注 `[Plugin]` 前缀
