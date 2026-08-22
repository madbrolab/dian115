# dian115 规则贡献指南

## 插件平台公开发布边界

本项目的 GitHub 公共分支只公开插件开发契约、第三方插件示例、市场索引和黑盒联调资料。**主项目源码在任何情况下都不得上传到 GitHub。**这条规则不因插件开发、版本发布、问题排查或 CI 调试而改变。

禁止公开 `cmd/`、`internal/`、`frontend/src/`、主项目构建/部署文件、`go.mod`、`go.sum`、生产脚本、构建产物、插件发布包和私钥。允许的第三方插件示例源码只能位于 `docs/plugin-platform/examples/`，其 `build/`、`releases/` 和签名私钥同样不能提交。

提交公共分支前必须运行：

```bash
node docs/plugin-platform/conformance/verify-public-surface.mjs
```

CI 会重复执行该检查。不得通过改名、压缩、复制到文档或生成文件绕过。第三方开发者只依赖 [`docs/plugin-platform/`](docs/plugin-platform/README.md) 中的公开契约，不需要访问主项目源码。

欢迎通过 Pull Request（PR）补充或修正自定义识别词规则。

本仓库接受来自社区的规则贡献。请先 Fork 仓库，在自己的分支中修改，然后向本仓库的 `main` 分支提交 PR。

## 规则文件分类

所有识别词规则都位于 [`rules/recognition/`](rules/recognition/)：

| 文件 | 用途 |
| --- | --- |
| `tmdb-overrides.txt` | TMDB 强制绑定规则；提交到此文件的规则必须包含 `tmdbid` |
| `cleanup.txt` | 通用清理、屏蔽词、季集格式和无法可靠归入单一媒体类型的规则 |
| `anime.txt` | 动漫标题修正、季度映射和集数偏移，不包含 TMDB 强绑 |
| `tv.txt` | 电视剧、纪录片和综艺标题修正，不包含 TMDB 强绑 |
| `movies.txt` | 电影标题修正，不包含 TMDB 强绑 |

请只修改与本次贡献有关的文件，不要顺带格式化、排序或重写无关规则。

## 支持的规则格式

文件必须使用 UTF-8 编码，每行一条规则。空行和以 `#` 开头的行不会执行。

常用写法：

```text
# 注释
(?i)\bCCTV6\b
That\.Time\.I\.Go => That.Time.I.Got
^Kesong\.puti$ => Kesong puti {[tmdbid=1669051;type=movie]}
BLEACH\.S01(?=.*ADWeb) => BLEACH.S02 {[tmdbid=30984;type=tv;s=2]}
The.Witness.*S(\d+)E(\d+) => $0 {[tmdbid=280511;type=tv;s=$1;e=$2]}
S01E <> 1080p >> EP+13
Jigokuraku.S02E => Jigokuraku.S01E && S01E <> 1080p >> EP+13
```

注意事项：

- `=>`、`&&`、`<>`、`>>` 两侧必须保留空格。
- 匹配部分支持正则表达式、捕获组、前后查找和反向引用。
- 替换部分支持 `$1`、`\1` 以及项目现有的捕获值运算写法。
- 规则按照文件内容和规则组优先级从前到后执行，请避免过宽的表达式抢先匹配其他媒体。
- 强制绑定必须提供正确的 TMDB ID 和媒体类型；剧集可按需提供 `s`、`e`。
- 不要提交令牌、Cookie、私有地址、个人目录或其他敏感信息。

## 提交 PR

1. Fork `madbrolab/dian115`。
2. 从最新的 `main` 创建独立分支。
3. 只编辑对应的规则文件。
4. 在 dian115 的“自定义识别词”设置中执行“校验全部”，确认没有语法错误。
5. 使用实际文件名验证规则能命中目标媒体，并确认不会误匹配相似标题。
6. 向本仓库的 `main` 分支提交 PR。

建议 PR 标题：

```text
rules: 修正《媒体名称》的识别
```

PR 描述请至少包含：

- 原始文件名或目录名。
- 修改前的错误识别结果。
- 期望的标题、季集或集数结果。
- 涉及强绑时提供 TMDB 页面或 TMDB ID。
- 已执行的校验及至少一个实际匹配示例。

## 审核原则

维护者会重点检查规则是否放入正确分类、是否存在重复、正则范围是否足够精确，以及强制绑定信息是否可靠。可能造成大范围误匹配的规则会被要求缩小范围。

PR 合并到 `main` 后，GitHub Raw 文件会随之更新。已在 dian115 中启用远程定时更新的用户，会在下一次设置间隔到期后获取新规则。
