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

`ui/page.js`：

```js
export function mount(element, ctx) {
  element.innerHTML = '<button id="run">检查</button><pre id="out"></pre>'
  const out = element.querySelector('#out')
  element.querySelector('#run').onclick = async () => {
    try {
      const run = await ctx.tasks.run('status', 'status:' + Date.now())
      out.textContent = '已提交：' + run.id
    } catch (error) {
      out.textContent = '失败：' + error.message
    }
  }
  return () => { element.innerHTML = '' }
}
```

## 5. 检查并打包

```sh
node conformance/project-check.mjs /绝对路径/my-plugin
node conformance/audit.mjs /绝对路径/my-plugin
node conformance/pack.mjs /绝对路径/my-plugin /绝对路径/输出/my-plugin.dian115p
```

输出文件要放在源码目录之外。

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
