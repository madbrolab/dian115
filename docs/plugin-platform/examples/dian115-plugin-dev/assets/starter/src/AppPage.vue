<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { NAlert, NButton, NInput } from 'naive-ui'
import type { PluginPageProps } from '../.dian115/examples/sdk/ui'
import { readDisplayName, saveDisplayName } from './preferences'
const props=defineProps<PluginPageProps>()
const displayName=ref(''),error=ref(''),notice=ref(''),state=ref('尚未读取'),busy=ref(false),restored=ref(false)
async function restore(){
 if(busy.value)return
 busy.value=true;error.value='';restored.value=false
 try{displayName.value=await readDisplayName(props.api.storage);restored.value=true}
 catch(failure:any){error.value=String(failure?.message||'偏好读取失败，请重试')}
 finally{busy.value=false}
}
async function save(){
 if(busy.value)return
 busy.value=true;error.value='';notice.value=''
 try{await saveDisplayName(props.api.storage,displayName.value,restored.value);notice.value='显示偏好已保存'}
 catch(failure:any){error.value=String(failure?.message||'保存失败')}
 finally{busy.value=false}
}
async function check(){
 if(busy.value)return
 busy.value=true;error.value=''
 try{const result=await props.api.getState();state.value=String(result.state?.message||result.state?.status||'状态已返回')}
 catch(failure:any){error.value=String(failure?.message||'运行时读取失败')}
 finally{busy.value=false}
}
onMounted(restore)
</script>
<template>
 <main class="plugin-page" :aria-busy="busy">
  <header><h2>插件配置</h2><p>按需运行，显示偏好通过宿主受管存储保存。</p></header>
  <NAlert v-if="runtimeState.preview" type="info" :bordered="false">本地模拟预览；真实 WASM 与 Host API 请在宿主中验证。</NAlert>
  <NAlert v-if="error" type="error" role="alert" :bordered="false">{{ error }}</NAlert>
  <NAlert v-if="notice" type="success" role="status" :bordered="false">{{ notice }}</NAlert>
  <section class="panel"><h3>显示偏好</h3><label>显示名称<NInput v-model:value="displayName" :maxlength="120" :disabled="busy||!restored" placeholder="填写便于识别的名称" /></label><div class="actions"><NButton type="primary" :disabled="busy||!restored" @click="save">保存偏好</NButton><NButton :disabled="busy" @click="restore">重新读取</NButton></div><p>重启与休眠保留偏好；卸载会清空本插件数据。</p></section>
  <section class="panel"><h3>运行时状态</h3><p role="status">{{ state }}</p><NButton :disabled="busy" @click="check">读取状态</NButton></section>
 </main>
</template>
<style scoped>
.plugin-page{width:100%;max-width:100%;min-width:0;display:grid;gap:16px;color:var(--dian-text-primary);font-family:var(--dian-font-family);line-height:1.6}h2{margin:0;font-size:24px}h3{margin:0 0 16px;font-size:17px}p{color:var(--dian-text-secondary);overflow-wrap:anywhere}.panel{min-width:0;padding:20px;border:1px solid var(--dian-border);border-radius:var(--dian-radius-lg,12px);background:var(--dian-surface)}label{display:grid;gap:8px;max-width:560px}.actions{display:flex;gap:12px;flex-wrap:wrap;margin-top:16px}.plugin-page :deep(.n-button){min-height:44px}@media(max-width:600px){.panel{padding:16px}}
</style>
