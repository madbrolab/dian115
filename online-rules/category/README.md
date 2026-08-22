# 在线整理分类模板

这里维护可由 dian115 前端主动拉取的 10 套 YAML 分类模板。模板只定义静态分类目录、匹配条件和明确声明的动态子层级，不负责合集目录。合集区分由普通/多版命名模板中的独立开关控制，并固定在命名路径最前面。

每套模板都完整包含 `movie` 和 `tv`。两种媒体的第一条规则固定为独立的 `成人内容`，之后才执行模板主题和常规分类。亲子、纪实、动漫等名称表示相关内容优先，不表示模板只管理这一类内容；主题规则未命中的作品仍会继续按题材、节目类型或地区进入正常目录。

每种媒体仍保留唯一的末尾空规则 `{}`，但它只负责接收 TMDB 类型、地区、分级或时长不足以命中前面规则的作品，不能代替常规分类。模板中的常规分类必须写在空规则之前。

## 成人内容与 Emby 可见性

`成人内容` 同时提供 `content_rating` 和 TMDB `keywords` 两个 OR 条件：分级归一化为 `ADULT`，或完整关键词命中 `eroticism`、`erotic drama`、`softcore`、`pornography`、`sexploitation`、`adult film` 时都会进入该目录。它位于每个列表第一条，避免先被动画、纪录片、地区、时长等普通规则截走。

按分类配置创建 Emby 媒体库并选择规则目录层级时，`成人内容` 会成为独立的媒体库候选。用户可以在 Emby 中单独设置该媒体库对哪些账号可见，以控制不同家庭成员的访问权限。模板只负责把内容分流到独立目录，不会代替 Emby 设置账号权限；由于 TMDB 分级可能缺失或错误，仍建议人工检查。

## 模板选择

| 模板 | 目录特点 | 适合需求 | 特别影响 |
| --- | --- | --- | --- |
| 标准完整分类 | 混合一至二级 | 专题、纪实、音乐、动画、节目与地区影视 | 成人内容先隔离，不修改动态子层级 |
| 均衡精简分类 | 统一一级 | 用较少目录兼顾类型与地区浏览 | 成人内容先隔离，不修改动态子层级 |
| 全球地区分类 | 统一一级 | 按制片国家覆盖全球主要区域 | 成人内容先隔离；多国合拍片按顺序首次命中 |
| 完整题材分类 | 统一一级 | 按完整 TMDB 类型表分类 | 成人内容先隔离；多题材按顺序首次命中 |
| 亲子与分级隔离 | 混合一至二级 | 隔离高分级，亲子优先，其他媒体按题材和地区分类 | 分级不完整时仍需人工复核 |
| 纪实节目完整分类 | 混合一至二级 | 纪录、新闻、综艺与脱口秀优先 | 其他媒体继续按动画、题材和地区分类 |
| 动漫细分分类 | 混合一至二级 | 动画按产地优先细分 | 真人内容继续按节目、题材和地区分类 |
| 完整时长分类 | 统一一级 | 以互斥区间覆盖短片、常规和超长内容 | 成人内容先隔离；时长缺失进入未知目录 |
| 标准分类 + 年代 | 一级静态分类后追加年代 | 类型地区浏览后继续按年代浏览 | 成人内容先隔离；覆盖年代动态层级 |
| 完整分类 + 评分段 | 一级静态分类后追加评分段 | 题材浏览后继续按 TMDB 评分浏览 | 成人内容先隔离；缺失评分保留在静态分类目录 |

```yaml
movie:
  成人内容:
    ?content_rating: "ADULT"
    ?keywords: "eroticism,erotic drama,softcore,pornography,sexploitation,adult film"
  动画电影:
    genre_ids: "16"
  华语电影:
    origin_country: "CN,HK,TW,MO"
  其他电影: {}

tv:
  成人内容:
    ?content_rating: "ADULT"
    ?keywords: "eroticism,erotic drama,softcore,pornography,sexploitation,adult film"
  动漫:
    genre_ids: "16"
  华语剧集:
    origin_country: "CN,HK,TW,MO"
  其他剧集: {}
```

## 匹配语义

普通条件为 AND；字段名前加 `?` 表示同一 OR 组。一条规则需要所有 AND 条件成立，并且存在 OR 条件时至少命中一项。模板保存和运行时使用以下 10 个规范字段：`tmdb_id`、`genre_ids`、`original_language`、`origin_country`、`content_rating`、`runtime`、`keywords`、`actors`、`titles`、`include_keywords`。

`keywords` 按 TMDB 关键词完整名称匹配；`actors` 按 TMDB 演职员表中的演员完整姓名匹配；`titles` 按 TMDB 标题、原始标题和别名做包含匹配，且不读取文件名；`include_keywords` 才会额外在识别元数据中的原始文件名片段上做包含匹配。内容分级统一使用 `content_rating`，值可以是 TMDB 原始分级（如 `US:R`）或系统归一化层级 `ADULT`、`MATURE`、`TEEN`、`UNRATED`。导入旧模板时仍兼容旧别名，但保存后会转换为规范字段；同一规则中归一化后的字段不能重复，重复目录和兜底规则后的普通规则也会被拒绝。

仅用于旧配置导入的别名映射为：`tmdbid` → `tmdb_id`，`genre_id` → `genre_ids`，`language` → `original_language`，`country` → `origin_country`，`content_ratings`/`certification`/`parental_rating`/`rating` → `content_rating`，`keyword`/`tmdb_keywords`/`tmdb_keyword` → `keywords`，`actor`/`cast`/`cast_names`/`series_actors` → `actors`，`title`/`tmdb_titles`/`tmdb_title` → `titles`，`series_keywords`/`title_keywords` → `include_keywords`。其他近似拼写不属于兼容字段；同一媒体类型的正向 `tmdb_id` 也不能被多个目录重复占用。

包含正向 `tmdb_id` 的固定规则由后端提升到最高优先级，与 YAML 中的位置无关；之后才按书写顺序执行普通规则和末尾空规则。同一作品有多个类型或产地时，只进入第一条命中的规则。官方模板不使用固定 `tmdb_id` 覆盖，因此 `成人内容` 会先于其他普通规则执行。`classify_by` 已不再支持。

模板只能依据系统支持的 TMDB 元数据分类，不能依据分辨率、编码、HDR、来源站点、文件扩展名或文件大小等技术属性分类。`sub_classify` 只支持 `year_decade`、`year`、`origin_country`、`rating_tier`、`genre_label` 动态层级；它们不是条件字段。TMDB 元数据缺失时，对应条件不会命中并会继续匹配后续规则。

## 提交更新

1. 新增或修改 `online-rules/category/*.yaml`，目录路径保持唯一且最后一级不超过 5 个 Unicode 字符；`movie` 和 `tv` 都必须存在，第一条必须是包含分级和 TMDB 关键词 OR 条件的独立 `成人内容`，且分别只能有一个放在最后的空规则 `{}`。
2. 在 `manifest.json` 登记模板，使用不含凭据的完整 HTTPS 地址。
3. 运行项目测试，确认 YAML 语法、字段、目录层级、固定 TMDB ID 和清单均通过校验。
4. 提交 PR，并在说明中写明适用场景、目录层级和是否包含 `sub_classify`。

在线模板只有在用户主动打开弹窗并拉取时访问，不做自动更新检查。应用时只覆盖 YAML 实际包含的媒体类型；其他本地配置保持不变。
