# DIAN115 插件 UI 开发指南

本文说明 Plugin API v2 当前发布的声明式 UI v1。插件提交 `ui.schema.json`，运行时通过 `state` 返回页面数据并处理 `action`；DIAN115 负责渲染完整工作区、主题、移动端布局、确认框、加载状态和错误提示。

UI schema 是严格白名单，未知字段会导致安装校验失败。开发前请同时以 [UI Schema](ui-schema-v1.schema.json) 为机器校验依据。

## 1. 页面工作模型

一个插件页面由三部分组成：

```text
ui.schema.json
  定义导航、view、section、字段和 action
        │
        ▼
运行时 state 响应
  提供 source 所引用的状态、列表和表单初始值
        │
        ▼
用户操作
  宿主把表单、整行数据或空对象送给已声明的 action
```

插件不能注入 Vue、HTML、CSS、JavaScript 或独立弹窗。页面仍然可以像独立程序一样包含多个 view、状态总览、分步表单、卡片、表格、进度、操作工具栏和日志；这些组件统一继承 DIAN115 的明暗主题和交互规范。

## 2. 最小 UI schema

```json
{
  "$schema": "https://raw.githubusercontent.com/madbrolab/dian115/main/docs/plugin-platform/ui-schema-v1.schema.json",
  "schema_version": 1,
  "navigation": {
    "title": "媒体工作台",
    "icon": "cloud-download"
  },
  "appearance": {
    "theme": "system",
    "density": "comfortable",
    "surface": "soft"
  },
  "views": [
    {
      "id": "workspace",
      "title": "工作台",
      "sections": [
        {
          "type": "status",
          "id": "overview",
          "source": "state.overview",
          "fields": [
            {"key": "status", "label": "状态", "format": "status"}
          ]
        }
      ]
    }
  ]
}
```

顶层字段：

| 字段 | 必需 | 说明 |
| --- | --- | --- |
| `schema_version` | 是 | 当前只能是 `1`。 |
| `navigation` | 是 | 插件工作区标题和可选图标。 |
| `appearance` | 否 | 主题强调色、密度和表面风格。 |
| `views` | 是 | 1～12 个页面，每个页面包含 1～24 个 section。 |

标识符只能由字母、数字以及分隔用的 `. _ -` 组成，不能以分隔符开头或结尾。`view.id` 在整个 schema 内唯一；`section.id` 在当前 view 内唯一；所有表单提交、行操作、普通操作和取消操作的 action id 在整个 schema 内共同唯一；字段 `key` 在其所属 section 内唯一。

## 3. state 返回与 source 解析

### 3.1 state 调用和返回

宿主读取 `workspace` view 时，运行时会收到：

```json
{
  "op": "state",
  "invocation_id": "state_workspace",
  "payload": {
    "view": "workspace",
    "if_none_match": ""
  }
}
```

运行时应返回一个对象，`state` 才是所有 UI `source` 的根：

```json
{
  "state_version": "workspace-17",
  "etag": "\"workspace-17\"",
  "state": {
    "overview": {
      "status": "ready",
      "message": "可以创建任务"
    },
    "items": []
  }
}
```

`state_version` 必须是有效标识符。可以省略 `etag`，宿主会用 `state_version` 生成强 ETag；若显式返回，去掉双引号后的值必须与 `state_version` 相同。任意 UI 可见状态发生变化时都要生成新的 `state_version`，否则宿主可能按缓存结果处理。

收到相同 `if_none_match` 且状态未变化时，可以返回：

```json
{
  "not_modified": true,
  "etag": "\"workspace-17\""
}
```

每个 view 会独立触发 state 调用。运行时可以为所有 view 返回同一状态树，也可以按 `payload.view` 返回更小的状态树。

### 3.2 source 路径

`source` 是点号分隔的属性路径，不是 JSONPath：

| source | 解析结果 |
| --- | --- |
| `state` | 整个 state 根对象。 |
| `state.overview` | `state.overview` 对象。 |
| `overview` | 与 `state.overview` 相同。 |
| `state.overview.status` | `state.overview.status`。 |

`state.` 前缀是可选的。推荐始终带上它以便阅读，但不要返回 `{"state":{"state":{...}}}` 这种重复层级。

路径只支持普通属性段，不支持 `[]`、通配符、过滤器或函数。属性不存在时解析为 `undefined`：状态字段显示 `—`，表格得到空列表，条件按实际的空值规则计算。不要依赖数组下标路径；应让 section 直接引用数组，再由列定义读取每一行。

不同位置的解析基准如下：

| 使用位置 | 解析基准 |
| --- | --- |
| section 的 `source` | state 根对象。 |
| `visible_when.source` | 始终是 state 根对象。 |
| status 的 `fields[].key` | status section 的 source 对象。 |
| table 的 `columns[].key` | 当前行对象。 |
| form 的初始字段值 | form section 的 source 对象中同名的 `field.key`。 |
| picker 字段的 `source` | state 根对象中的动态选项数组。 |

### 3.3 form 初始化

form 的 `source` 和 picker 字段的 `source` 用途不同：

```json
{
  "type": "form",
  "id": "account_setup",
  "source": "state.form",
  "submit_action": "select_account",
  "fields": [
    {
      "key": "account_key",
      "label": "执行账号",
      "control": "account-picker",
      "source": "state.account_options",
      "required": true
    }
  ]
}
```

- section 的 `source: state.form` 提供初始值，因此初始值来自 `state.form.account_key`。
- 字段的 `source: state.account_options` 提供 picker 选项，不提供字段初始值。
- 首次读取 state 时，宿主按 form `id` 建立本地表单，并为每个尚不存在的字段读取 `section.source[field.key]`。
- 建议首次 state 就为所有表单字段返回明确默认值，例如空字符串、`false`、`null` 或空数组；不要等待后续 action 才首次增加这些 key。
- 隐藏字段也会初始化，但提交时只包含当前可见字段。必填校验也只检查当前可见字段。
- `undefined`、`null`、空字符串和空数组被视为空值；`false` 和 `0` 是有效值。

宿主保留用户已经编辑的本地表单值。action 后虽然会重新读取 state，但新的 `state.form.*` 不会覆盖已经存在的本地字段。这一限制见本文末尾的“已知限制”。

## 4. action 输入与返回

所有 action 都会收到同一外层信封：

```json
{
  "op": "action",
  "invocation_id": "inv_01",
  "payload": {
    "id": "submit_transfer",
    "input": {},
    "context": {
      "locale": "zh-CN",
      "timezone": "Asia/Shanghai"
    }
  }
}
```

`payload.input` 有三种固定形状。

### 4.1 form 提交：字段对象

```json
{
  "id": "submit_transfer",
  "input": {
    "transfer_type": "auto",
    "source_text": "magnet:?xt=urn:btih:...",
    "notify_on_submit": true
  }
}
```

对象只包含当前可见且非空的字段，key 就是 `fields[].key`。`number` 会转换为 JSON number；`switch` 是 boolean；`multiselect` 是数组；其他选择器提交其选项的标量 value。运行时必须再次验证字段、账号、目录、选项可用性和业务边界，不能把 UI 校验当作授权。

### 4.2 table 行操作：完整行对象

```json
{
  "id": "retry_task",
  "input": {
    "row": {
      "id": "task-42",
      "summary": "离线任务提交失败",
      "status": "failed",
      "available": true
    }
  }
}
```

行操作会把 state 中的整行放入 `input.row`。不要在行对象中放 Cookie、Token、下载地址或其他秘密；运行时只能把 row id 当作查询线索，必须从自己的可信状态重新读取真实记录。

### 4.3 actions 与 progress 取消：空对象

```json
{
  "id": "refresh_directory",
  "input": {}
}
```

`actions` section 中的按钮以及 `progress.cancel_action` 都收到 `{}`。需要参数时，把所需选择先通过 form action 写入插件状态，再提供普通 action。

### 4.4 action 返回

```json
{
  "status": "succeeded",
  "code": "transfer_created",
  "message": "已提交 3 个离线任务",
  "result": {
    "task_count": 3
  }
}
```

`status` 必须是：

- `succeeded`：同步完成。
- `failed`：业务失败；`message` 应能直接展示给用户。
- `accepted`：已接受并转入后台，后续进度通过 state 展示。
- `skipped`：因当前状态无需执行。

宿主根据状态显示统一消息，并在 action 结束后重新读取当前 view 的 state。action 应按 `invocation_id` 幂等处理。

## 5. section 完整目录

每个 section 都可以使用 `id`、`title`、`description`、`presentation`、`requires_capabilities` 和 `visible_when`，但各类型的必需数据不同。

| type | 必需字段 | 数据形状与用途 |
| --- | --- | --- |
| `status` | `source`、`fields` | source 应是对象；显示状态、指标和摘要。最多 24 个字段。 |
| `form` | `id`、`submit_action`、`fields` | source 可选，用于表单初始值；最多 40 个字段。 |
| `table` | `source`、`columns` | source 应是对象数组；最多 20 列、8 个行操作。 |
| `log` | `source` | source 可以是字符串、数组或单值；只展示 state 中的业务日志。 |
| `progress` | `source` | source 可以是 number，或含 `percent`、`progress`、`value` 的对象。 |
| `actions` | `actions` | 1～12 个无输入按钮，适合刷新、确认当前目标和导航操作。 |

### 5.1 status 字段格式

`fields[].format` 支持：

| format | 行为 |
| --- | --- |
| `text` | 字符串直接显示；简单数组以顿号连接。 |
| `number` | 按当前区域格式化数字。 |
| `boolean` | 显示“是/否”并使用状态标签。 |
| `datetime` | 建议返回 ISO 8601 时间。 |
| `bytes` | 当前按数字分组显示，不自动添加容量单位。 |
| `duration` | 当前按数字分组显示，不自动添加时间单位。 |
| `status` | 根据常见状态词使用成功、警告、错误或信息色。 |
| `percent` | `0～1` 转成百分比；大于 1 的数按百分数处理。 |

对象会优先显示其 `label`、`name`、`title`、`message` 或 `status`；都不存在时只显示信息项数量。需要精确文本时，应在 state 中预先生成面向用户的字符串。

### 5.2 table

```json
{
  "type": "table",
  "id": "tasks",
  "source": "state.tasks",
  "row_key": "id",
  "selected_source": "state.selected_task_id",
  "selected_row_key": "id",
  "columns": [
    {"key": "summary", "label": "任务"},
    {"key": "status", "label": "状态", "format": "status"}
  ],
  "row_actions": [
    {"id": "retry_task", "label": "重试", "icon": "refresh-cw"}
  ],
  "page_size": 20
}
```

- `row_key` 应指向每行稳定且唯一的标量字段。
- `selected_source` 与 `selected_row_key` 必须同时出现。卡片或 picker 视图会用它们标记当前选择，比较时按字符串值比较。
- `page_size` 可设为 5～200，只截取运行时已经返回的前 N 行，不是服务端分页。
- 行中 `available: false` 会禁用该行操作。
- 空数组会显示宿主空状态；需要自定义空状态时，应另设布尔状态并用条件 status section 展示。

### 5.3 log

`log` section 与宿主自动提供的“运行日志”页面不是同一功能。前者显示插件通过 state 返回的少量、面向用户的业务记录；后者显示当前安装实例受容量和保留期限制的诊断日志。

`max_rows` 可设为 10～1000，默认按 200 行呈现。字符串按换行符拆分，数组按每项一行显示。

### 5.4 progress

以下值都表示 36%：

```json
0.36
```

```json
{"percent": 36}
```

```json
{"progress": 0.36}
```

结果会限制在 0～100。设置 `cancel_action` 后显示取消按钮，该 action 收到空对象。

## 6. presentation 完整目录

所有 presentation 都支持：

- `span`：`"full"` 或 `1～4`；只有 grid 布局中数字跨度才有意义。
- `tone`：`default`、`primary`、`info`、`success`、`warning`、`danger`。
- `icon`：小写 kebab-case 图标名。

每种 section 可选的 `variant`：

| section | variant |
| --- | --- |
| `status` | `plain`、`card`、`metric` |
| `form` | `plain`、`card` |
| `table` | `plain`、`card`、`table`、`cards`、`picker` |
| `log` | `plain`、`card`、`console` |
| `progress` | `plain`、`card`、`bar` |
| `actions` | `plain`、`card`、`toolbar`、`stack` |

`cards` 和 `picker` 适合账号、目录、任务选择；普通大量数据使用 `table`。`tone` 用来表达语义，不应只为装饰而把所有 section 设成不同颜色。

当前稳定可识别的常用图标包括 `activity`、`arrow-up`、`check`、`check-circle`、`chevron-left`、`chevron-right`、`cloud-download`、`file-text`、`folder`、`folder-check`、`folder-open`、`info`、`plug`、`refresh-cw`、`user`、`user-check`。其他合法名称会使用通用后备图标，不影响功能。

## 7. form control 完整目录

| control | 值类型 | 可用约束 | 说明 |
| --- | --- | --- | --- |
| `text` | string | `min_length`、`max_length` | 单行文本。 |
| `textarea` | string | `min_length`、`max_length` | 多行文本，适合链接列表和说明。 |
| `number` | number | `min`、`max`、`step` | 提交前转成有限数字。 |
| `switch` | boolean | 无 | 开关。 |
| `select` | string/number/boolean | `options` | 单选；静态选项必需。 |
| `multiselect` | scalar[] | `options` | 多选；静态选项必需。 |
| `secret-ref` | string | 无 | 选择或填写宿主管理的 `credential_ref`，不提交秘密明文。 |
| `account-picker` | scalar | `source`、可选 `options` | 可搜索的账号选择器。 |
| `directory-picker` | scalar | `source`、可选 `options` | 可搜索的目录选择器。 |

静态 `options` 为 1～200 个对象：

```json
[
  {"label": "自动识别", "value": "auto"},
  {"label": "离线下载", "value": "offline"}
]
```

value 只能是 string、number 或 boolean。`select` 和 `multiselect` 不支持从 state 动态生成选项；动态账号和目录应使用对应 picker。

### 7.1 动态 picker option

`account-picker` 和 `directory-picker` 的字段 `source` 应指向 state 数组。宿主最多读取前 500 项，并按下列规则构造选项。

value 使用第一个非 null/undefined 字段：

```text
value -> account_ref -> entry_ref -> cid -> path -> id -> name -> 数组下标
```

label 使用第一个非 null/undefined 字段：

```text
label -> name -> directory_name -> path -> 已解析的 value
```

`user_name`、`cloud_name`、`mode_label`、`path` 会按顺序作为辅助说明，最多追加前两个非空值。只有严格的 `available: false` 会禁用选项。

账号选项示例：

```json
[
  {
    "value": "account_main",
    "label": "主账号",
    "user_name": "media-admin",
    "mode_label": "主账号",
    "available": true
  },
  {
    "value": "account_backup_A7K2",
    "label": "影视备用号",
    "cloud_name": "影视库",
    "mode_label": "指定备用账号",
    "available": true
  },
  {
    "value": "account_backup_Q9P4",
    "label": "已停用备用号",
    "available": false
  }
]
```

目录选项示例：

```json
[
  {
    "value": "directory_root",
    "directory_name": "根目录",
    "path": "根目录",
    "available": true
  },
  {
    "value": "directory_M20001",
    "directory_name": "电影",
    "path": "媒体库 / 电影",
    "available": true
  }
]
```

动态 value 也必须是稳定、唯一的 string/number/boolean。不要把账号对象或目录对象直接放入 `value`；当前选择器不会保留对象结构。推荐由插件生成不含秘密的 opaque key，并在运行时自己的可信状态中把它映射回宿主账号选择对象或目录上下文。picker option 中的 `path` 只能是面向用户的相对显示文本，例如 `媒体库 / 电影`；运行时 state 会拒绝 `/media/...`、Windows 盘符和 UNC 等绝对路径，真实操作必须使用 opaque ref 映射。

如果字段 source 不是数组，picker 会回退到字段的静态 `options`。无论 UI 是否禁用选项，运行时都必须再次验证 value 当前仍存在且 `available`，并确认目录属于已锁定的账号。

### 7.2 account-picker 与 directory-picker 的分阶段流程

当前 picker 选择变化不会自动调用 action，`visible_when` 也不会读取尚未提交的本地表单。因此账号与目录应按以下阶段设计：

1. state 返回 `account_options`，显示账号 form；目录 form 暂时隐藏。
2. 用户选择账号并提交 `select_account`。
3. 运行时验证 opaque account key，通过已声明的账号/目录 Host API 锁定实际账号，更新 `account_loaded`、当前账号摘要和根目录选项。
4. 宿主重新读取 state；目录 form 通过 `visible_when` 出现。
5. 用户选择一个子目录并提交 `open_directory`。运行时按账号上下文读取该层目录，再更新 `directory_options`、`current_cid` 和 `current_path`。
6. 用户到达目标层后点击普通 action `select_current_directory`；运行时把当前 CID 固定为任务目标，并设置 `target_ready`。
7. 转存 form 只在 `target_ready` 为真时显示。

不要让目录 form 的可见性依赖本地 `account_key`。应依赖运行时确认后的 `state.flags.account_loaded`，这样备用号池已经解析并锁定到具体账号，目录和后续操作不会漂移。

## 8. visible_when 与 requires_capabilities

### 8.1 visible_when

```json
{
  "visible_when": {
    "source": "state.flags.target_ready",
    "operator": "truthy",
    "value": true
  }
}
```

支持的 operator：

| operator | 规则 |
| --- | --- |
| `eq` | 与 `value` 严格相等。 |
| `neq` | 与 `value` 严格不等。 |
| `in` | `value` 必须是数组，判断实际值是否在其中。 |
| `not_in` | `value` 必须是数组，判断实际值是否不在其中。 |
| `truthy` | 使用实际值的布尔真值；schema 仍要求提供 `value`，通常填 `true`。 |
| `falsy` | 使用实际值的布尔假值；schema 仍要求提供 `value`，通常填 `true`。 |

空数组和空对象在布尔判断中仍是真值。若要判断“列表是否为空”，请让运行时额外返回 `has_items: false`，不要直接对数组使用 `falsy`。

一次只能声明一个条件，不支持 `and`、`or` 或嵌套表达式。复杂判断应由运行时计算成明确布尔字段。条件只读取最近一次 state，不读取用户尚未提交的表单值。

`visible_when` 可用于 section、display field、form field 和 action。

### 8.2 requires_capabilities

```json
{
  "requires_capabilities": [
    "/api/115/directories",
    "/api/115/offline/add"
  ]
}
```

- 所有列出的能力都存在时才显示，数组是 AND 关系。
- Host API 填 manifest 已声明的 `/api/...` path，不带 method；外部网络填 manifest 已声明的 HTTPS origin。
- 不能填写未在 manifest 中声明的路径或 origin，否则包校验失败。
- 不要填写宿主内部派生的旧 capability 名称。
- 这是 UI 显示门控，不是授权替代品。实际 host call 仍按完整 method + path 和安装授权检查。

当前应把功能门控放在 view、section 或 action 上；form/display 字段没有 `requires_capabilities`。顶层 navigation 的同名字段属于 schema 元数据，不应用作业务安全边界。

## 9. 主题、布局与移动端

### 9.1 appearance

```json
{
  "appearance": {
    "theme": "system",
    "density": "comfortable",
    "surface": "soft"
  }
}
```

- `theme`：`system`、`blue`、`green`、`amber`、`red`、`violet`、`cyan`、`neutral`。它只提供克制的品牌强调色，表单和组件仍继承宿主明暗主题。
- `density`：`comfortable` 或 `compact`。
- `surface`：`plain`、`soft` 或 `glass`。

推荐默认使用 `system + comfortable + soft`。只有插件确有品牌色时再选择固定 theme；错误、警告和成功仍应使用对应 tone。

### 9.2 view layout

```json
{
  "layout": {
    "type": "grid",
    "columns": 2,
    "gap": "normal",
    "header": "hero",
    "max_width": "wide"
  }
}
```

| 字段 | 值 | 建议 |
| --- | --- | --- |
| `type` | `stack`、`grid` | 分步流程用 stack；仪表盘用 grid。 |
| `columns` | 1～4 | 只控制桌面端最大列数。 |
| `gap` | `compact`、`normal`、`spacious` | 工作台通常用 normal。 |
| `header` | `hero`、`compact`、`none` | 主工作台用 hero，辅助页用 compact。 |
| `max_width` | `full`、`wide`、`narrow` | 表单流程用 narrow，数据台用 wide/full。 |

少量 view 使用页签；view 较多时宿主自动采用侧栏，并始终附加当前安装实例的“运行日志”入口。窄屏时侧栏变为横向可滚动导航；手机宽度下 grid、状态指标、picker 和表单自动变成单列，操作按钮会扩展为易点击布局。

不要用字段顺序或固定列宽模拟复杂网页。把最关键的状态放在第一屏，把破坏性操作放到独立 action 并使用 `confirm`，让宿主负责不同屏幕尺寸的最终布局。

## 10. 加载、空状态和错误状态

宿主自动处理基础交互状态：

- 首次 state 尚未返回时显示加载动画。
- state 调用失败时显示错误和重试按钮。
- action 执行时对应按钮显示 loading，并暂时阻止冲突操作。
- table/picker 数组为空时显示统一空状态。
- 运行时未准备、插件已停用或没有可见 view 时显示宿主级提示。

插件仍需在 state 中描述业务状态。推荐返回稳定的 `phase` 和显式 flags：

```json
{
  "phase": "loading_directories",
  "flags": {
    "loading": true,
    "has_items": false,
    "has_error": false,
    "account_loaded": true,
    "target_ready": false
  },
  "error": {
    "code": "",
    "message": "",
    "hint": ""
  }
}
```

设计建议：

- 长任务先返回 `accepted`，state 中显示 progress section；完成后改为成功或失败 status。
- 列表为空时用 `has_items` 控制一个带说明的 status section，而不是只留下空表格。
- 业务错误使用 `tone: danger` 的 status section，提供可行动的 `message` 和 `hint`；诊断细节写插件日志，不把堆栈显示给用户。
- 账号或目录暂不可用时返回空 options，并显示专门的错误/重试 action。
- state 和表格行不得包含凭据、Cookie、Token、私密下载地址或原始敏感响应，因为行操作会把整行送回 action。

## 11. 完整工作台示例

以下 schema 是可直接按 UI v1 校验的多账号转存工作台。示例假定 manifest 已声明它在 `requires_capabilities` 中使用的 Host API。

```json
{
  "$schema": "https://raw.githubusercontent.com/madbrolab/dian115/main/docs/plugin-platform/ui-schema-v1.schema.json",
  "schema_version": 1,
  "navigation": {
    "title": "多账号转存工作台",
    "icon": "cloud-download"
  },
  "appearance": {
    "theme": "system",
    "density": "comfortable",
    "surface": "soft"
  },
  "views": [
    {
      "id": "workspace",
      "title": "转存工作台",
      "description": "依次确认账号、目录和任务内容。",
      "layout": {
        "type": "grid",
        "columns": 2,
        "gap": "normal",
        "header": "hero",
        "max_width": "wide"
      },
      "sections": [
        {
          "type": "status",
          "id": "overview",
          "title": "当前目标",
          "source": "state.workspace",
          "presentation": {
            "variant": "metric",
            "span": "full",
            "tone": "info",
            "icon": "cloud-download"
          },
          "fields": [
            {"key": "account_name", "label": "执行账号"},
            {"key": "current_path", "label": "浏览位置"},
            {"key": "target_path", "label": "保存目录"},
            {"key": "status", "label": "状态", "format": "status"}
          ]
        },
        {
          "type": "status",
          "id": "account_error",
          "title": "账号暂不可用",
          "source": "state.error",
          "presentation": {
            "variant": "card",
            "span": "full",
            "tone": "danger",
            "icon": "info"
          },
          "fields": [
            {"key": "message", "label": "原因"},
            {"key": "hint", "label": "建议"}
          ],
          "visible_when": {
            "source": "state.flags.has_error",
            "operator": "truthy",
            "value": true
          }
        },
        {
          "type": "form",
          "id": "account_setup",
          "title": "1. 选择执行账号",
          "description": "选择主账号、备用号池或指定备用账号。",
          "source": "state.form",
          "submit_action": "select_account",
          "submit_label": "载入账号",
          "presentation": {
            "variant": "card",
            "span": 1,
            "tone": "default",
            "icon": "user-check"
          },
          "requires_capabilities": ["/api/115/accounts/options"],
          "fields": [
            {
              "key": "account_key",
              "label": "115 执行账号",
              "description": "提交后再加载该账号的目录。",
              "control": "account-picker",
              "source": "state.account_options",
              "required": true
            }
          ],
          "visible_when": {
            "source": "state.flags.accounts_ready",
            "operator": "truthy",
            "value": true
          }
        },
        {
          "type": "form",
          "id": "directory_browser",
          "title": "2. 浏览保存目录",
          "description": "每次提交进入一个子目录。",
          "source": "state.form",
          "submit_action": "open_directory",
          "submit_label": "进入目录",
          "presentation": {
            "variant": "card",
            "span": 1,
            "tone": "default",
            "icon": "folder-open"
          },
          "requires_capabilities": ["/api/115/directories"],
          "fields": [
            {
              "key": "directory_ref",
              "label": "当前层目录",
              "description": "可搜索目录名称或路径。",
              "control": "directory-picker",
              "source": "state.directory_options",
              "required": true
            }
          ],
          "visible_when": {
            "source": "state.flags.account_loaded",
            "operator": "truthy",
            "value": true
          }
        },
        {
          "type": "actions",
          "id": "directory_actions",
          "title": "目录操作",
          "presentation": {
            "variant": "toolbar",
            "span": "full",
            "tone": "default",
            "icon": "folder-check"
          },
          "actions": [
            {
              "id": "select_current_directory",
              "label": "使用当前目录",
              "icon": "folder-check",
              "style": "primary",
              "visible_when": {
                "source": "state.flags.account_loaded",
                "operator": "truthy",
                "value": true
              }
            },
            {
              "id": "go_parent_directory",
              "label": "返回上级",
              "icon": "arrow-up",
              "style": "secondary",
              "visible_when": {
                "source": "state.navigator.can_go_parent",
                "operator": "truthy",
                "value": true
              }
            },
            {
              "id": "refresh_directory",
              "label": "刷新目录",
              "icon": "refresh-cw",
              "style": "secondary"
            }
          ]
        },
        {
          "type": "form",
          "id": "transfer_request",
          "title": "3. 创建转存任务",
          "source": "state.form",
          "submit_action": "submit_transfer",
          "submit_label": "开始转存",
          "presentation": {
            "variant": "card",
            "span": "full",
            "tone": "primary",
            "icon": "cloud-download"
          },
          "requires_capabilities": ["/api/115/offline/add"],
          "fields": [
            {
              "key": "transfer_type",
              "label": "任务类型",
              "control": "select",
              "required": true,
              "options": [
                {"label": "自动识别", "value": "auto"},
                {"label": "离线下载", "value": "offline"}
              ]
            },
            {
              "key": "source_text",
              "label": "115 链接或离线地址",
              "description": "每行一个离线地址。",
              "control": "textarea",
              "required": true,
              "min_length": 1,
              "max_length": 8192
            },
            {
              "key": "notify_on_submit",
              "label": "完成后发送插件通知",
              "control": "switch",
              "required": false
            }
          ],
          "visible_when": {
            "source": "state.flags.target_ready",
            "operator": "truthy",
            "value": true
          }
        },
        {
          "type": "status",
          "id": "last_result",
          "title": "最近结果",
          "source": "state.last_result",
          "presentation": {
            "variant": "card",
            "span": "full",
            "tone": "success",
            "icon": "check-circle"
          },
          "fields": [
            {"key": "status", "label": "状态", "format": "status"},
            {"key": "message", "label": "结果"},
            {"key": "finished_at", "label": "完成时间", "format": "datetime"}
          ],
          "visible_when": {
            "source": "state.last_result.status",
            "operator": "eq",
            "value": "succeeded"
          }
        }
      ]
    },
    {
      "id": "activity",
      "title": "任务与记录",
      "description": "查看后台进度和最近任务。",
      "layout": {
        "type": "stack",
        "columns": 1,
        "gap": "normal",
        "header": "compact",
        "max_width": "wide"
      },
      "sections": [
        {
          "type": "progress",
          "id": "running_progress",
          "title": "当前任务",
          "source": "state.progress",
          "cancel_action": "cancel_transfer",
          "presentation": {
            "variant": "bar",
            "span": "full",
            "tone": "primary",
            "icon": "activity"
          },
          "visible_when": {
            "source": "state.flags.task_running",
            "operator": "truthy",
            "value": true
          }
        },
        {
          "type": "status",
          "id": "task_empty",
          "title": "暂无任务",
          "source": "state.empty_state",
          "presentation": {
            "variant": "card",
            "span": "full",
            "tone": "info",
            "icon": "activity"
          },
          "fields": [
            {"key": "message", "label": "下一步"}
          ],
          "visible_when": {
            "source": "state.flags.has_tasks",
            "operator": "falsy",
            "value": true
          }
        },
        {
          "type": "table",
          "id": "recent_tasks",
          "title": "最近任务",
          "source": "state.tasks",
          "row_key": "id",
          "selected_source": "state.selected_task_id",
          "selected_row_key": "id",
          "presentation": {
            "variant": "cards",
            "span": "full",
            "tone": "default",
            "icon": "file-text"
          },
          "columns": [
            {"key": "summary", "label": "任务"},
            {"key": "status", "label": "状态", "format": "status"},
            {"key": "created_at", "label": "创建时间", "format": "datetime"}
          ],
          "row_actions": [
            {
              "id": "retry_task",
              "label": "重试",
              "icon": "refresh-cw",
              "style": "secondary",
              "confirm": {
                "title": "重试任务",
                "message": "将使用原账号和目标目录重新提交，是否继续？"
              },
              "requires_capabilities": ["/api/115/offline/add"],
              "visible_when": {
                "source": "state.flags.retry_enabled",
                "operator": "truthy",
                "value": true
              }
            }
          ],
          "page_size": 20,
          "visible_when": {
            "source": "state.flags.has_tasks",
            "operator": "truthy",
            "value": true
          }
        },
        {
          "type": "log",
          "id": "activity_log",
          "title": "业务摘要",
          "source": "state.activity_log",
          "max_rows": 100,
          "presentation": {
            "variant": "console",
            "span": "full",
            "tone": "default",
            "icon": "file-text"
          }
        }
      ]
    }
  ]
}
```

对应的 `workspace` mock state：

```json
{
  "state_version": "workspace-42",
  "state": {
    "workspace": {
      "account_name": "影视备用号",
      "current_path": "媒体库 / 电影",
      "target_path": "媒体库 / 电影",
      "status": "ready"
    },
    "flags": {
      "accounts_ready": true,
      "account_loaded": true,
      "target_ready": true,
      "has_error": false,
      "task_running": false,
      "has_tasks": true,
      "retry_enabled": true
    },
    "error": {
      "message": "",
      "hint": ""
    },
    "form": {
      "account_key": "account_backup_A7K2",
      "directory_ref": "directory_M20001",
      "transfer_type": "auto",
      "source_text": "",
      "notify_on_submit": true
    },
    "account_options": [
      {
        "value": "account_main",
        "label": "主账号",
        "user_name": "media-admin",
        "mode_label": "主账号",
        "available": true
      },
      {
        "value": "account_backup_A7K2",
        "label": "影视备用号",
        "cloud_name": "影视库",
        "mode_label": "指定备用账号",
        "available": true
      }
    ],
    "directory_options": [
      {
        "value": "directory_M20001",
        "directory_name": "电影",
        "path": "媒体库 / 电影",
        "available": true
      },
      {
        "value": "directory_T20002",
        "directory_name": "剧集",
        "path": "媒体库 / 剧集",
        "available": true
      }
    ],
    "navigator": {
      "can_go_parent": true
    },
    "last_result": {
      "status": "succeeded",
      "message": "已提交 2 个离线任务",
      "finished_at": "2026-08-21T08:54:00Z"
    },
    "progress": {
      "percent": 100
    },
    "empty_state": {
      "message": "在工作台创建第一个任务"
    },
    "selected_task_id": "task-42",
    "tasks": [
      {
        "id": "task-42",
        "summary": "提交 2 个离线地址",
        "status": "succeeded",
        "created_at": "2026-08-21T08:53:00Z",
        "available": false
      }
    ],
    "activity_log": [
      "08:53 已锁定账号：影视备用号",
      "08:54 已提交 2 个离线任务"
    ]
  }
}
```

## 12. 已知限制与发布检查

当前 UI v1 的限制：

1. **没有 `refresh` 字段。** UI schema 中加入 view/section `refresh`、刷新间隔、focus refresh 或 action refresh 配置都会因未知字段被拒绝。宿主统一提供工具栏手动刷新、页面可见时的状态轮询和 action 后 state 重读，插件不能修改频率。
2. **action 后不会用新 state 覆盖已有本地表单值。** form 初始化只填充尚不存在的 key；包括值为 `undefined` 的 key 一旦建立也不会被后续 state 更新。把任务结果放在独立 status 中，不要依赖 action 返回 state 清空输入框或替换 picker 选择。
3. **字段变化没有 `change_action`。** picker/select 的变化只发生在浏览器本地，必须由用户提交 form 后运行时才能加载下一阶段。
4. **条件只读取 state。** `visible_when` 不会读取未提交的本地表单，也不支持组合表达式或列表长度运算。
5. **动态 picker 只提交标量。** 当前没有自定义 `option_value`、`option_label` 或对象 value 配置；请使用本文约定的 state 字段，并在运行时维护 opaque key 映射。
6. **普通 select 只有静态 options。** 需要 state 动态选项时使用 `account-picker` 或 `directory-picker`。
7. **没有自定义前端代码。** 不能注入 CSS、HTML、Vue 组件、iframe 或自行创建弹窗；确认框由 action `confirm` 声明。
8. **table 不是远程分页组件。** `page_size` 只裁剪 state 已返回的数组。
9. **state log 不是持久化插件日志。** 持久化诊断请使用运行时日志能力，页面上的 log section 只显示本次 state 数据。

发布前逐项检查：

- 用 `ui-schema-v1.schema.json` 校验完整 JSON，确认没有额外字段。
- 所有 view、section、action 和字段 id 符合命名规则及其唯一性作用域。
- form 第一次 state 已包含每个字段的明确默认值。
- 每个 picker value 唯一、稳定、无秘密，并验证 `available`。
- 账号选择提交后才加载目录；备用号池已经锁定具体账号再浏览和提交任务。
- `visible_when` 依赖运行时确认后的 flags，不依赖未提交表单。
- `requires_capabilities` 只填写 manifest 已声明的 path/origin。
- action 对 form、row 和空对象三种输入都进行严格、可信的服务端验证。
- state 变化同步更新 `state_version`，action 按 `invocation_id` 幂等。
- 在 Docker/Linux 环境和手机宽度下实际检查工作台；不要用 Windows 原生运行时验证插件。
