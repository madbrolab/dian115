# 在线整理分类模板

分类模板只维护静态目录与匹配条件，不负责合集目录。合集区分已移到普通/多版命名模板，并由后端锁定在命名路径最前面。

```yaml
movie:
  动画电影:
    genre_ids: "16"
  其他电影: {}

tv:
  动漫:
    genre_ids: "16"
  其他剧集: {}
```

普通条件为 AND；字段名前加 `?` 表示同一 OR 组。支持字段包括 `tmdb_id`、`genre_ids`、`original_language`、`origin_country`、`content_rating`、`runtime`、`keywords` 和 `include_keywords` 及界面列出的兼容别名。

包含正向 `tmdb_id` 的固定规则由后端提升到最高优先级，与 YAML 中的位置无关；之后才按书写顺序执行普通规则和兜底规则。`classify_by` 已不再支持。

在线模板只有在用户主动打开弹窗并拉取时访问，不做自动更新检查。应用时只覆盖 YAML 实际包含的媒体类型；其他本地配置保持不变。
