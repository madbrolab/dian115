# DIAN115 v3 SDK

index.js 提供页面便利客户端；它调用普通 HTTP API，没有 bridge、Host Call 或独立权限协议。宿主挂载页面时已创建 ctx，无需复制 SDK。独立页面可 `createPluginContext(id, request, {generation, revision})`，request(method,path,body,source) 返回原 JSON，并自行使用普通宿主登录。自建客户端可把 source.plugin_id/generation/revision 写到 X-DIAN115-Extension、X-DIAN115-Extension-Generation、X-DIAN115-Extension-Revision 请求头，以获得迟到请求保护；generation/revision 从安装详情读取。宿主提供的 ctx 已自动绑定，无需作者另行处理。

后台不加载此客户端：宿主直接提供 ctx.api/storage/task/http/files/watch/cd2/notify/cookiecloud/sleep。接口差异、错误与任务恢复见开发指南。index.d.ts 描述页面客户端，后台上下文使用本目录 background.d.ts。

host-api.d.ts 由 OpenAPI 生成：`ctx.api.get/post/put/patch/delete(path, body)` 对已公开的路径自动推断请求体和响应类型（路径参数与查询串都能匹配），未公开或动态拼接的路径返回 `unknown`。也可直接使用 `HostResponse<'GET','/api/...'>`、`HostBody<'POST','/api/...'>` 与各个结构类型（如 `OfflineTaskList`）。纯 JavaScript 项目在编辑器中通过 JSDoc 同样获得提示：

```js
/** @param {import('./sdk/background.js').BackgroundContext} ctx */
export async function run(ctx) {
  const { items } = await ctx.api.get('/api/115/offline/tasks?status=downloading')
}
```
