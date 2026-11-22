# 快速开始

10 分钟做出第一个插件：一个带页面和后台任务的“115 状态”插件。需要 Node.js 18 以上，只用于检查和打包，插件本身不依赖 Node。

## 1. 建目录

```text
my-plugin/
  plugin.json
  ui/page.js
  jobs/status.js
```

## 2. 写清单

`plugin.json`：

```json
{
  "schema_version": 3,
  "id": "me.status",
  "name": "115 状态",
  "version": "1.0.0",
  "author": "你的名字",
  "description": "查看 115 账号状态并发送通知",
  "requires": { "api": "3.7" },
  "ui": { "entry": "ui/page.js" },
  "jobs": [{ "id": "status", "entry": "jobs/status.js", "title": "检查 115 状态" }]
}
```

全部字段见[清单参考](manifest.md)。

## 3. 写后台任务

`jobs/status.js`：

```js
export async function run(ctx, input) {
  const status = await ctx.api.get('/api/115/status')
  await ctx.task.log(JSON.stringify(status))
  await ctx.notify({ title: '115 状态', body: '检查完成', level: 'success', dedupe_key: ctx.task.id })
  return status
}
```

## 4. 写页面

使用开发 skill 的 `starter` 模板时，页面已有手机导航和滚动区。手工建目录时，可以将下面的最小页面保存为 `ui/page.js`。完整 HTML 和 ESM 模块遵守同一份 [iPhone PWA 适配契约](ui-theme.md#iphone-pwa-页面适配契约)。

```js
export function mount(element, ctx) {
  element.innerHTML = `
    <section class="status-plugin">
      <style>
        .status-plugin { padding: 16px; color: var(--app-text); }
        .status-plugin header { display: flex; flex-wrap: wrap; gap: 8px; }
        .status-plugin button { min-width: 44px; min-height: 44px; font: inherit; }
        .status-plugin pre { white-space: pre-wrap; overflow-wrap: anywhere; }
        .status-plugin [data-menu] { display: none; }
        @media (max-width:768px), (max-height:500px) and (hover:none) and (pointer:coarse) {
          .status-plugin [data-menu]:not([hidden]) { display: inline-block; }
        }
      </style>
      <header><button type="button" data-menu hidden>主菜单</button><button type="button" data-back hidden>返回插件中心</button></header>
      <p><button type="button" data-run>检查</button></p><pre role="status"></pre>
    </section>`
  for (const [selector, method] of [['[data-menu]', 'openSidebar'], ['[data-back]', 'close']]) {
    if (!ctx.navigation?.[method]) continue
    const button = element.querySelector(selector)
    button.hidden = false
    button.onclick = () => ctx.navigation[method]()
  }
  const out = element.querySelector('pre')
  element.querySelector('[data-run]').onclick = async () => {
    try {
      const run = await ctx.tasks.run('status', 'status:' + Date.now())
      out.textContent = '已提交：' + run.id
    } catch (error) {
      out.textContent = '失败：' + error.message
    }
  }
  return () => element.replaceChildren()
}
```

## 5. 检查并打包

```sh
node conformance/project-check.mjs /绝对路径/my-plugin
node conformance/audit.mjs /绝对路径/my-plugin
node conformance/pack.mjs /绝对路径/my-plugin /绝对路径/输出/my-plugin.dian115p
```

输出文件要放在源码目录之外。

这一步生成可读源码包，供自己的 DIAN115 安装调试或作为编译输入，不代表已经正式编译。新格式发布规则与当前编译 MCP 能力见[编译与交付](encrypted-delivery.md#编译-mcp-与正式发布)。

## 6. 安装

1. 打开插件中心的“第三方插件”，选择 `.dian115p` 文件。
2. 看安装确认里的作者和检测到的操作，确认后安装。
3. 打开插件，点“检查”，到任务队列看结果。

安装后代码不能再改，改了插件会被停用。修改后提高 `version`，重新打包，用“更新”安装。

## 下一步

| 想做什么 | 看哪里 |
| --- | --- |
| 找现成写法 | [配方](cookbook.md) |
| 收发 TG、企微消息 | [消息渠道](messaging.md) |
| 长连接、开机常驻 | [长连接与常驻任务](long-connections.md) |
| 所有 ctx 能力 | [API 参考](api-reference.md) |
| 所有宿主接口 | [接口速查](host-api-quick-reference.md) |
| 用 AI 开发 | [开发 skill](skill-installation.md) |
| 安装前查恶意代码 | [安全审查](security-audit.md) |
