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

## CollectionRender 电影分组来源

`movie-community.yaml` 由 [`CollectionRender.txt`](https://github.com/yanghuaioc/QuantumultX/blob/b305943deedeb82bc0f8c6797ef1dae1eb70d5ff/CollectionRender.txt) 的固定版本生成。它是社区目录分组，不是 TMDB 官方 `Collection` 数据，不能用“ID 是电影”推导出官方合集关系。

生成规则以来源保真和避免错分为优先：

- 保留来源目标名称及语义，包括名称末尾的“系列”；只将文件系统非法字符替换为对应全角字符。
- 相同目标名称的多条规则会合并，因为它们在原规则中本来就写入同一个目录。
- 同一 ID 同时出现“名称”和“名称 系列”两个等价目标时，统一保留带“系列”的来源名称。
- 同一 ID 属于两个真正不同的名称时，从所有候选中排除并在生成报告中列出，禁止按文件顺序猜测归属。
- TMDB 电影导出表只用于确认 ID 是现存电影；不存在的电影 ID 会排除，但不会被猜测成电视剧。
- 排除后不足两个有效电影的分组不会发布。

当前固定来源共解析 2526 条规则；346 个等价别名 ID 采用带“系列”的名称，75 个不同名称冲突 ID 被排除，最终发布 2286 个电影分组、8579 个唯一电影 ID。完整统计会在每次生成时输出，词表头部同时记录来源 commit 和校验日期。

```powershell
node online-rules/tools/generate-collection-vocabulary.mjs `
  --export-date MM_DD_YYYY `
  --output online-rules/collections/movie-community.yaml
```

## 提交 Pull Request

1. 电影和电视剧条目必须分别核对 TMDB 媒体类型。
2. 更新来源时必须同时更新固定 commit；不能直接使用会漂移的 `main` 地址发布结果。
3. 新增或调整 ID 时，先确认同类型下没有其他主合集占用；不同名称冲突必须排除或提交可审核的明确依据。
4. 电视剧合集必须提供明确的系列关系依据，不能从电影合集或数字碰撞推断。
5. 批量来源应附带可重复执行的生成工具和清洗策略，不直接提交未经审计的抓取结果。
6. 新增独立词表文件时同步更新 `manifest.json`；普通内容更新不需要版本号。
