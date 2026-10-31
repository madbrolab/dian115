# API 测试台 v3

无 npm、WASM 或编译步骤。将本目录作为服务器源码目录安装，或生成 .dian115p 包后从插件中心上传。根目录包含 plugin.json、ui/page.js、ui/icon.svg、jobs/job.js、jobs/http.js（Webhook 与监听端口处理器）和 jobs/events.js（宿主业务事件）。安装后填写站点、账号密码、CK、FlareSolverr 与目录；默认没有站点账号，也不会自动登录、发通知或修改宿主文件。

按钮逐项测试宿主 GET、HTTP、二进制下载与下载链接、持久 Cookie、CookieCloud 读写、FlareSolverr、插件文件、CD2 列表、目录轮询与实时监听、监听端口与回调地址、宿主事件记录、存储分页、磁盘统计、统一任务与通知。插件页“设置”标签由清单 settings 生成，可填写公开回调令牌与测试端口；侧栏资源分组会出现本插件入口。账号密码表单字段演示 username/password；具体站点需按真实登录接口调整，不声称可以绕过交互验证码。

probe 任务仅修改插件自己的计数并记录检查点。重复业务标识应返回同一任务；更换标识才新增任务。通知也使用稳定 dedupe_key。目录轮询会启动 probe，点击后请删除监听以结束测试。卸载清空全部默认插件数据。

自动测试只运行本地源码/SDK模拟接口，不访问真实站点、不发送通知：

```sh
node --test docs/plugin-platform/conformance/*.test.mjs
node docs/plugin-platform/conformance/project-check.mjs docs/plugin-platform/examples/complete-plugin
```
