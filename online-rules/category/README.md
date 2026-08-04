# 在线整理分类规则

这里维护 dian115 可主动拉取的 YAML 整理模板，并接受 Pull Request。拉取操作分为“在线获取并校验”和“用户确认覆盖”两步；读取列表或预览不会修改本地规则。

## 基本格式

```yaml
movie:
  "合集":
    classify_by: collection_vocabulary
  "动画":
    genre_ids: "16"
  "其他电影": {}

tv:
  "合集":
    classify_by: collection_vocabulary
  "其他剧集": {}
```

顶层只允许：

- `movie`：电影规则。
- `tv`：电视剧规则。
- `sub_classify`：可选的局部层级设置。没有写出的设置由本地现有配置保留。

普通条件为 AND；字段名前加 `?` 表示同一 OR 组。支持字段包括 `tmdb_id`、`genre_ids`、`original_language`、`origin_country`、`content_rating`、`runtime`、`keywords` 和 `include_keywords` 及界面中列出的兼容别名。

## 优先级和合集目录

包含正向 `tmdb_id` 的固定规则由后端提升到最高优先级，与 YAML 中的位置无关。之后才按书写顺序执行合集词表规则、普通规则和兜底规则。

`classify_by: collection_vocabulary` 表示：先按当前媒体类型和 TMDB ID 查询本地合集词表，命中后把合集名称追加在当前静态路径后面。例如静态路径为 `合集`，实际整理目录为 `电影/合集/<合集名称>`。Emby 对账只处理静态的 `电影/合集`，不会为每个合集创建媒体库。

合集词表规则不能同时填写正向 `tmdb_id`。需要固定覆盖时，请新建一条普通 `tmdb_id` 规则。

## 提交 Pull Request

1. 从现有模板复制一个新文件，保持 UTF-8 和 `.yaml` 后缀。
2. 目录路径应稳定、易读；兜底规则必须放在同媒体类型最后。
3. 避免重复路径、未知字段、空条件以及同一 TMDB ID 对应多个固定目录。
4. 若新增模板，在 `manifest.json` 增加唯一 ID、说明、媒体类型和 raw URL。
5. 运行 `go test ./internal/api ./internal/organize ./internal/store` 与 `cd frontend && npx vue-tsc --noEmit`。

`standard.yaml`、`collections.yaml` 和 `decade.yaml` 由 `go run ./online-rules/tools/generate-category-templates` 生成。修改项目默认模板后应重新生成，避免在线标准模板与内置模板漂移。

