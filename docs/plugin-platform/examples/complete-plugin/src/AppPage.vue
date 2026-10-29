<script setup lang="ts">
import { computed, ref, onMounted } from 'vue'
import {
  NAlert,
  NButton,
  NForm,
  NFormItem,
  NGrid,
  NGridItem,
  NIcon,
  NInput,
  NStatistic,
  NTag,
  useMessage,
} from 'naive-ui'
import { Bell, ExternalLink, FolderSearch, Globe2, HardDrive, RefreshCw, Save } from '@lucide/vue'
import pluginIconURL from '../frontend/icon.svg'
import type { PluginJob, PluginPageProps } from '../../sdk/ui'
import { createBackgroundJobSession } from './background-job'
import { invokeSavedAction } from './actions'

const props = defineProps<PluginPageProps>()

const message = useMessage()
const busyAction = ref('')
const watchPath = ref('')
const localURL = ref('http://127.0.0.1:8080/health')
const networkURLs = ref('')
const networkResult = ref('')
const siteID = ref('site-a')
const siteURL = ref('https://site.example')
const siteLabel = ref('我的站点')
const siteSession = ref('account-a')
const loginURL = ref('https://site.example/login')
const loginUsername = ref('')
const loginPassword = ref('')
const loginFields = ref('{}')
const manualCookie = ref('')
const browserNote = ref('')
const backgroundJob = ref<PluginJob | null>(null)
const jobBusy = ref(false)
const jobReady = ref(false)
const jobSession = createBackgroundJobSession(props.api, value => {
  backgroundJob.value = value.job
  jobBusy.value = value.busy
  jobReady.value = value.ready
})
onMounted(async () => {
  try {
    browserNote.value = String(await props.api.storage.get('browser-note') || '')
  }
  catch (error: any) { message.error(String(error?.message || '读取页面偏好失败')) }
  await backgroundOperation('restore')
})
const canResumeJob = computed(() => backgroundJob.value?.recovery_supported && ['failed','attention_required'].includes(backgroundJob.value.status) && (backgroundJob.value.recovery_attempt || 0) < 3)
const canCancelJob = computed(() => backgroundJob.value?.cancellable && !backgroundJob.value.cancel_requested && (['queued', 'running'].includes(backgroundJob.value.status) || (backgroundJob.value.recovery_supported && ['failed', 'attention_required'].includes(backgroundJob.value.status))))
async function backgroundOperation(op: 'start' | 'get' | 'resume' | 'cancel' | 'restore') {
  try {
    if (op === 'restore') await jobSession.restore()
    else await jobSession.run(op)
  } catch (error: any) { message.error(String(error?.message || '后台任务操作失败')) }
}
const state = computed(() => props.runtimeState)

async function saveBrowserNote() {
  try { await props.api.storage.set('browser-note',browserNote.value);message.success('页面偏好已由宿主保存，卸载后清空') }
  catch (error: any) { message.error(String(error?.message || '保存页面偏好失败')) }
}

async function openExternal() {
  if (busyAction.value) return
  // Open synchronously from the click, then navigate after the runtime action resolves.
  const popup = window.open('about:blank', '_blank', 'popup,width=1080,height=760')
  if (!popup) {
    message.warning('浏览器阻止了弹窗，请允许当前页面打开新窗口')
    return
  }
  busyAction.value = 'external-link'
  try {
    const response = await invokeSavedAction(props.api, 'external-link', {})
    const result = response.result
    const url = String(result.url || '')
    if (result.status === 'failed' || !/^https?:\/\//i.test(url)) throw new Error(String(result.message || '外部地址无效'))
    if (response.confirmation_pending) message.warning('已收到动作结果，确认状态未保存；重试前请先核对业务结果')
    popup.location.replace(url)
  } catch (error: any) {
    popup.close()
    message.error(String(error?.message || '打开外部页面失败'))
  } finally {
    busyAction.value = ''
  }
}

async function runAction(action: string, input: Record<string, unknown> = {}) {
  if (busyAction.value) return
  busyAction.value = action
  try {
    const response = await invokeSavedAction(props.api, action, input)
    const result = response.result
    if (result.status === 'failed') throw new Error(String(result.message || '插件动作失败'))
    if (response.confirmation_pending) message.warning('已收到动作结果，确认状态未保存；重试前请先核对业务结果')
    else message.success(String(result.message || '操作完成'))
    try { await props.api.refresh() }
    catch { message.warning('动作结果已返回，状态刷新失败，请稍后刷新页面') }
  } catch (error: any) {
    message.error(String(error?.message || '操作失败'))
  } finally {
    busyAction.value = ''
  }
}

async function networkAction(action: 'http-batch' | 'http-cache-info' | 'http-cache-clear') {
  if (busyAction.value) return
  const urls = networkURLs.value.split(/\r?\n/).map(url => url.trim()).filter(Boolean)
  if (action === 'http-batch' && (!urls.length || urls.length > 8 || urls.some(url => !/^https?:\/\//.test(url)))) {
    message.warning('请逐行填写 1–8 个 HTTP(S) 地址')
    return
  }
  busyAction.value = action
  try {
    const response = await invokeSavedAction(props.api, action, action === 'http-batch' ? { urls, session: siteSession.value } : {}, undefined, { transientInput: true })
    if (response.result.status === 'failed') throw new Error(String(response.result.message || '网络操作失败'))
    networkResult.value = JSON.stringify(response.result, null, 2)
    if (response.confirmation_pending) message.warning('结果已返回，确认状态未保存；再次提交前请核实')
    else message.success(String(response.result.message || '操作完成'))
  } catch (error: any) { message.error(String(error?.message || '网络操作失败；重试保留原请求')) }
  finally { busyAction.value = '' }
}

async function createWatch() {
  const path = watchPath.value.trim()
  if (!path) {
    message.warning('请输入宿主文件管理器中的目录路径')
    return
  }
  await runAction('create-watch', { path })
}

async function siteAction(action: 'site-list' | 'site-save' | 'site-delete' | 'site-login' | 'cookie-save') {
  if (busyAction.value) return
  let fields: Record<string, string> = {}
  if (action === 'site-login') {
    try {
      fields = JSON.parse(loginFields.value)
      if (!fields || Array.isArray(fields) || typeof fields !== 'object' || Object.values(fields).some(value => typeof value !== 'string')) throw new Error()
    } catch { message.error('表单字段必须是 JSON 对象，值为字符串；字段名按目标站点填写'); return }
  }
  busyAction.value = action
  try {
    const input = action === 'site-login' ? { url: loginURL.value, session: siteSession.value, username: loginUsername.value, password: loginPassword.value, fields }
      : action === 'cookie-save' ? { url: siteURL.value, session: siteSession.value, cookie: manualCookie.value }
      : action === 'site-save' ? { site_id: siteID.value, url: siteURL.value, label: siteLabel.value }
      : action === 'site-delete' ? { site_id: siteID.value } : {}
    // A configured URL may itself contain private query values.
    const response = await invokeSavedAction(props.api, action, input, undefined, { transientInput: ['site-login', 'cookie-save', 'site-save'].includes(action) })
    if (response.result.status === 'failed') throw new Error(String(response.result.message || '站点操作失败'))
    if (action === 'site-list') {
      const data = response.result.data as { sites?: { id: string; url: string; label?: string }[] } | undefined
      const saved = data?.sites?.find(site => site.id === siteID.value)
      if (saved) { siteURL.value = saved.url; siteLabel.value = saved.label || '' }
      else { message.info('当前编号尚未保存，可填写任意站点地址后保存'); return }
    }
    if (action === 'site-login') { loginPassword.value = ''; loginFields.value = '{}' }
    if (action === 'cookie-save') manualCookie.value = ''
    message.success(String(response.result.message || '操作完成'))
    if (response.confirmation_pending) message.warning('结果已返回，确认状态未保存；再次提交前请核实业务结果')
  } catch (error: any) { message.error(String(error?.message || '操作失败；重试请使用原表单内容')) }
  finally { busyAction.value = '' }
}
</script>

<template>
  <main class="dian-plugin-page example-page">
    <header class="page-header">
      <div>
        <h2>完整插件示例</h2>
        <p>WASM 运行时、Host Call、目录监控、Telegram 与主题契约。</p>
      </div>
      <NTag type="success" size="small">{{ themeContract }}</NTag>
    </header>

    <NAlert v-if="state.lastMessage" :type="state.lastStatus === 'failed' ? 'error' : 'info'" :bordered="false">
      {{ state.lastMessage }}
    </NAlert>

    <section class="metrics" aria-label="插件运行摘要">
      <NGrid cols="1 s:3" responsive="screen" :x-gap="12" :y-gap="12">
        <NGridItem><NStatistic label="状态版本" :value="String(state.revision || 1)" /></NGridItem>
        <NGridItem><NStatistic label="动作次数" :value="Number(state.actionCount || 0)" /></NGridItem>
        <NGridItem><NStatistic label="事件次数" :value="Number(state.eventCount || 0)" /></NGridItem>
      </NGrid>
    </section>

    <section class="actions" aria-label="插件操作">
      <NButton type="primary" :loading="busyAction === 'send-test'" @click="runAction('send-test')">
        <template #icon><NIcon :component="Bell" /></template>
        发送测试通知
      </NButton>
      <NButton :loading="busyAction === 'refresh'" @click="runAction('refresh')">
        <template #icon><NIcon :component="RefreshCw" /></template>
        刷新运行时状态
      </NButton>
      <NButton :loading="busyAction === 'external-link'" @click="openExternal">
        <template #icon><NIcon :component="ExternalLink" /></template>
        打开外部授权页
      </NButton>
    </section>

    <section class="tool-panel">
      <h3>自定义站点、表单登录与手填 Cookie</h3>
      <p>安装后可添加或修改地址。账号密码、验证码及令牌由站点适配器处理，CookieCloud 是可选来源。</p>
      <NForm label-placement="top" @submit.prevent="siteAction('site-save')">
        <NFormItem label="站点编号"><NInput v-model:value="siteID" /></NFormItem>
        <NFormItem label="站点名称"><NInput v-model:value="siteLabel" /></NFormItem>
        <NFormItem label="站点地址"><NInput v-model:value="siteURL" placeholder="https://你的站点/" /></NFormItem>
        <div class="actions">
          <NButton attr-type="submit" :loading="busyAction === 'site-save'">保存地址</NButton>
          <NButton :loading="busyAction === 'site-list'" @click="siteAction('site-list')">读取地址</NButton>
          <NButton :loading="busyAction === 'site-delete'" @click="siteAction('site-delete')">删除地址</NButton>
        </div>
      </NForm>
      <NForm label-placement="top" @submit.prevent="siteAction('site-login')">
        <NFormItem label="账号会话名（不同账号填写不同名称）"><NInput v-model:value="siteSession" /></NFormItem>
        <NFormItem label="登录表单提交地址"><NInput v-model:value="loginURL" /></NFormItem>
        <NFormItem label="账号"><NInput v-model:value="loginUsername" autocomplete="username" /></NFormItem>
        <NFormItem label="密码"><NInput v-model:value="loginPassword" type="password" show-password-on="click" autocomplete="current-password" /></NFormItem>
        <NFormItem label="附加表单字段 JSON（可填写验证码、CSRF 或自定义账号字段）">
          <NInput v-model:value="loginFields" type="password" show-password-on="click" placeholder='{"captcha":"验证码","csrf":"站点令牌"}' />
        </NFormItem>
        <NButton attr-type="submit" :loading="busyAction === 'site-login'">提交登录表单</NButton>
      </NForm>
      <NForm label-placement="top" @submit.prevent="siteAction('cookie-save')">
        <NFormItem label="手动 Cookie"><NInput v-model:value="manualCookie" type="password" show-password-on="click" placeholder="name=value; another=value" /></NFormItem>
        <NButton attr-type="submit" :loading="busyAction === 'cookie-save'">保存 Cookie</NButton>
      </NForm>
      <p>敏感输入仅留在表单内存，宿主加密保存动作回执和 Cookie。示例只报告提交结果；正式插件必须检查站点业务码，处理 CSRF、验证码并核实登录状态。</p>
    </section>

    <section class="tool-panel">
      <div class="section-heading">
        <img class="plugin-preview-image" :src="pluginIconURL" alt="完整插件示例图标">
        <div>
          <h3>图片与浏览器存储</h3>
          <p>图片来自签名包；页面在独立沙箱中运行，持久偏好通过受管存储桥保存。</p>
        </div>
      </div>
      <NForm label-placement="top" @submit.prevent="saveBrowserNote">
        <NFormItem label="浏览器备注">
          <NInput v-model:value="browserNote" placeholder="刷新页面后仍会保留" clearable />
        </NFormItem>
        <NButton attr-type="submit">
          <template #icon><NIcon :component="Save" /></template>
          保存页面偏好
        </NButton>
      </NForm>
    </section>

    <section class="tool-panel">
      <div class="section-heading">
        <NIcon :component="HardDrive" :size="20" />
        <div>
          <h3>Host Storage</h3>
          <p>通过 Host Storage 保存插件私有状态，ETag 和幂等键由宿主保护。</p>
        </div>
      </div>
      <NButton :loading="busyAction === 'storage-demo'" @click="runAction('storage-demo')">
        <template #icon><NIcon :component="HardDrive" /></template>
        读写示例数据
      </NButton>
    </section>

    <section class="tool-panel">
      <div class="section-heading">
        <NIcon :component="Globe2" :size="20" />
        <div>
          <h3>宿主网络 Broker</h3>
          <p>HTTP、HTTPS、localhost、局域网和其他容器地址都由宿主访问；宿主代理规则优先。</p>
        </div>
      </div>
      <NForm label-placement="top" @submit.prevent="runAction('fetch-local', { url: localURL })">
        <NFormItem label="本地或局域网 URL">
          <NInput v-model:value="localURL" placeholder="例如 http://127.0.0.1:8080/health" clearable />
        </NFormItem>
        <NButton attr-type="submit" type="primary" :loading="busyAction === 'fetch-local'">通过宿主请求</NButton>
      </NForm>
    </section>

    <section class="tool-panel">
      <h3>只读并发与响应缓存</h3>
      <p>独立资源逐行填写，最多 8 项、并发 4；每项最多 1 MiB。结果显示耗时、缓存和截断状态，不展示凭据或正文。</p>
      <NForm label-placement="top" @submit.prevent="networkAction('http-batch')">
        <NFormItem label="HTTP(S) 地址（每行一个，使用上方账号会话）">
          <NInput v-model:value="networkURLs" type="textarea" placeholder="https://你的站点/list?page=1" :autosize="{ minRows: 2, maxRows: 8 }" />
        </NFormItem>
        <div class="actions">
          <NButton attr-type="submit" :loading="busyAction === 'http-batch'">并发请求</NButton>
          <NButton :loading="busyAction === 'http-cache-info'" @click="networkAction('http-cache-info')">查看缓存用量</NButton>
          <NButton :loading="busyAction === 'http-cache-clear'" @click="networkAction('http-cache-clear')">清空缓存（保留 Cookie）</NButton>
        </div>
      </NForm>
      <pre v-if="networkResult" role="status" style="white-space: pre-wrap; overflow-wrap: anywhere">{{ networkResult }}</pre>
    </section>

    <section class="tool-panel">
      <h3>可恢复后台任务</h3>
      <p>任务进入宿主统一队列。恢复先只读核对持久结果，再决定完成或从检查点续跑。</p>
      <NButton v-if="!jobReady" :loading="jobBusy" @click="backgroundOperation('restore')">重新读取任务</NButton>
      <NButton :loading="jobBusy" :disabled="!jobReady || jobBusy || backgroundJob?.status === 'queued' || backgroundJob?.status === 'running'" @click="backgroundOperation('start')">启动示例任务</NButton>
      <NButton :disabled="!backgroundJob || jobBusy" @click="backgroundOperation('get')">查询任务</NButton>
      <NButton :disabled="!canResumeJob || jobBusy" @click="backgroundOperation('resume')">核对并恢复</NButton>
      <NButton :disabled="!canCancelJob || jobBusy" @click="backgroundOperation('cancel')">取消任务及后续恢复</NButton>
      <p v-if="backgroundJob" role="status">{{ backgroundJob.job_ref }} · {{ backgroundJob.status }} · {{ backgroundJob.progress }}%</p>
    </section>

    <section class="watch-panel">
      <div class="section-heading">
        <NIcon :component="FolderSearch" :size="20" />
        <div>
          <h3>创建目录监控</h3>
          <p>路径由宿主文件管理器解析，受系统目录和 /config 保护规则限制。</p>
        </div>
      </div>
      <NForm label-placement="top" @submit.prevent="createWatch">
        <NFormItem label="宿主目录路径">
          <NInput v-model:value="watchPath" placeholder="例如 /media/incoming" clearable />
        </NFormItem>
        <NButton attr-type="submit" :loading="busyAction === 'create-watch'">创建监控</NButton>
      </NForm>
    </section>
  </main>
</template>

<style scoped>
.example-page {
  display: grid;
  gap: var(--dian-space-4);
  padding: var(--dian-space-1);
}

.page-header,
.section-heading,
.actions {
  display: flex;
  align-items: center;
  gap: var(--dian-space-3);
}

.page-header {
  justify-content: space-between;
  border-bottom: 1px solid var(--dian-divider);
  padding-bottom: var(--dian-space-4);
}

.page-header > div,
.section-heading > div {
  min-width: 0;
}

h2,
h3,
p {
  margin: 0;
  letter-spacing: 0;
}

h2,
h3 {
  color: var(--dian-text-primary);
}

h2 { font-size: 22px; }
h3 { font-size: 16px; }

p {
  margin-top: var(--dian-space-1);
  color: var(--dian-text-secondary);
  overflow-wrap: anywhere;
}

.metrics,
.watch-panel,
.tool-panel {
  border: 1px solid var(--dian-border);
  border-radius: var(--dian-radius-lg);
  background: var(--dian-surface-raised);
  padding: var(--dian-space-4);
}

.actions {
  flex-wrap: wrap;
}

.section-heading {
  align-items: flex-start;
  margin-bottom: var(--dian-space-4);
  color: var(--dian-primary);
}

.plugin-preview-image {
  width: 48px;
  height: 48px;
  flex: 0 0 48px;
  object-fit: contain;
  border: 1px solid var(--dian-border);
  border-radius: var(--dian-radius-sm);
  background: var(--dian-surface-soft);
}

@media (max-width: 600px) {
  .page-header {
    align-items: flex-start;
    flex-direction: column;
  }

  .actions > * {
    flex: 1 1 100%;
  }
}
</style>
