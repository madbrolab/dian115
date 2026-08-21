<script setup lang="ts">
import { computed, ref } from 'vue'
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
import { Bell, FolderSearch, RefreshCw } from '@lucide/vue'

interface RuntimeCallback {
  invocation_id?: string
  replayed?: boolean
  result?: {
    status?: 'succeeded' | 'failed' | 'accepted' | 'skipped'
    message?: string
    [key: string]: unknown
  }
}

interface HostBridge {
  getState(view?: string): Promise<{ state?: Record<string, unknown>; state_version?: string; etag?: string }>
  invokeAction(action: string, input?: unknown): Promise<RuntimeCallback>
  refresh(): Promise<Record<string, unknown>>
}

const props = defineProps<{
  api: HostBridge
  hostApi?: HostBridge
  installationId?: number
  pluginId?: string
  runtimeState?: Record<string, unknown>
  themeContract?: string
}>()

const message = useMessage()
const busyAction = ref('')
const watchPath = ref('')
const state = computed(() => props.runtimeState || {})

async function runAction(action: string, input: Record<string, unknown> = {}) {
  busyAction.value = action
  try {
    const response = await props.api.invokeAction(action, input)
    const result = response.result || {}
    if (result.status === 'failed') throw new Error(String(result.message || '插件动作失败'))
    await props.api.refresh()
    message.success(String(result.message || '操作完成'))
  } catch (error: any) {
    message.error(String(error?.message || '操作失败'))
  } finally {
    busyAction.value = ''
  }
}

async function createWatch() {
  const path = watchPath.value.trim()
  if (!path) {
    message.warning('请输入宿主文件管理器中的目录路径')
    return
  }
  await runAction('create-watch', { path })
}
</script>

<template>
  <main class="dian-plugin-page example-page">
    <header class="page-header">
      <div>
        <h2>完整插件示例</h2>
        <p>进程状态、Host Call、目录监控、Telegram 与主题契约。</p>
      </div>
      <NTag type="success" size="small">{{ themeContract || 'dian115-theme-v1' }}</NTag>
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
.watch-panel {
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
