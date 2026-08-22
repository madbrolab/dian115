# 插件黑盒联调工具

这里的工具只依赖公开的插件进程协议，不导入、不编译、也不读取 DIAN115 主项目源码。第三方作者可以用它在目标 Linux 容器或 CI 中验证自己的 runtime 是否满足 Plugin API v2 的基本生命周期。

## 验证范围

`runtime-smoke.mjs` 会：

1. 启动指定的静态 Linux ELF；
2. 发送 `runtime.initialize`，并处理插件在初始化期间发出的 `host.telegram.register`、`host.log` 和 `host.call`；
3. 发送 `runtime.invoke` 的 `state` 请求，检查状态响应包含 `state_version`、`etag` 和对象状态；
4. 发送 `runtime.shutdown`，检查进程返回 JSON object 并正常退出。

它不会模拟主项目数据库、文件系统或管理员身份，也不会给插件额外权限。Host Call 的默认响应只用于让协议测试可以完成；业务接口仍必须在安装到实际宿主时按 OpenAPI 逐项声明和批准。

## 使用完整示例

在 `docs/plugin-platform/examples/complete-plugin/` 中：

```bash
npm ci
npm run build
node ../../conformance/runtime-smoke.mjs --runtime build/runtime/plugin
```

Windows 或 macOS 上可以构建插件，但 Linux ELF 联调必须在 WSL、Linux CI 或与宿主相同架构的容器中执行。ARM64 示例：

```bash
DIAN115_PLUGIN_GOARCH=arm64 npm run build
node ../../conformance/runtime-smoke.mjs --runtime build/runtime/plugin
```

## 联调自己的插件

```bash
node docs/plugin-platform/conformance/runtime-smoke.mjs --runtime ./build/runtime/plugin
```

可选参数：

```text
--timeout-ms <整数>       每个协议阶段的超时，默认 5000
--verbose                 输出收到的 JSON-RPC method 名
```

工具只要求 runtime 使用标准输入/输出上的 `Content-Length` JSON-RPC 2.0。不要向 stdout 写日志；调试信息写 stderr，并确保所有入站请求都能在处理嵌套 Host Call 时继续被读取。

## UI 联调

UI 仍然使用主项目同一套 Vue 3、Naive UI 和 `@lucide/vue` singleton。示例的 `npm run dev` 提供本地 mock bridge，可验证组件 props、主题变量、弹窗用户手势和错误状态；正式包通过 `ui-federation-v1.md` 规定的 opaque-origin iframe 加载。浏览器弹窗必须由用户点击同步创建，不能由定时任务或初始化回调创建。

## 通过标准

- runtime smoke 命令退出码为 `0`；
- 入口是目标架构的静态 ELF，且没有 `PT_INTERP`；
- `.d115p` 由示例 `scripts/package.mjs` 生成并能通过包格式、完整性和签名校验；
- UI 暴露 Manifest 中声明的 Federation module，且所有静态资源进入签名包；
- Host API、网络路由、Telegram 注册和文件操作都与公开文档一致。

黑盒联调通过不等于插件获得了未声明权限；最终安装仍由宿主重新校验签名、Manifest、权限、静态 ELF、UI 和运行时状态。
