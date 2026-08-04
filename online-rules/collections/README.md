# 在线合集词表

合集词表独立于整理模板维护，并接受 Pull Request。它只描述 `(媒体类型, TMDB ID) → 合集名称`，不描述 Emby 媒体库，也不决定静态分类路径。

## 格式

```yaml
schema_version: 1
movie:
  - name: "某电影合集"
    tmdb_ids: [1001, 1002]
tv:
  - name: "某电视剧合集"
    tmdb_ids: [2001, 2002]
```

保存前会完整检查：

- `schema_version` 必须为 `1`。
- `movie` 和 `tv` 使用独立 TMDB 命名空间；不能因数字相同而跨类型复制。
- 一个合集至少包含两个不同的正整数 TMDB ID。
- 同一合集内不能重复填写同一个 TMDB ID，整个词表也不能保存为空。
- 同一媒体类型下，一个 TMDB ID 只能属于一个主合集。
- 合集名称不能为空、不能重复、不能包含路径分隔符或控制字符，也不能使用 `.`、`..` 及系统保留设备名。
- 任何错误都会拒绝整次保存，已有本地词表和运行时索引保持不变。

## 社区电影合集来源

`movie-community.yaml` 参考 [`CollectionRender.txt`](https://github.com/yanghuaioc/QuantumultX/blob/main/CollectionRender.txt) 生成。原文件没有媒体类型字段，因此本项目不会根据“同号也存在电视剧条目”猜测类型；生成器只保留 TMDB 官方电影 ID 导出表中存在的编号，并只写入 `movie`。

生成器还会合并同名项、替换名称中的路径分隔符、去除无效电影 ID，并按来源顺序为同 ID 多归属选择唯一主合集。少于两个有效电影的项会移除。

```powershell
node online-rules/tools/generate-collection-vocabulary.mjs `
  --export-date MM_DD_YYYY `
  --output online-rules/collections/movie-community.yaml
```

## 提交 Pull Request

1. 电影和电视剧条目必须分别核对 TMDB 媒体类型。
2. 新增或调整 ID 时，先确认同类型下没有其他主合集占用。
3. 电视剧合集必须提供明确的系列关系依据，不能从电影合集或数字碰撞推断。
4. 批量来源应附带可重复执行的生成工具和清洗策略，不直接提交未经审计的抓取结果。
5. 新增独立词表文件时同步更新 `manifest.json`；普通内容更新不需要版本号。
