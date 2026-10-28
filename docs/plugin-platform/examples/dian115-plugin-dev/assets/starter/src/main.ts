import { createApp, defineComponent, h } from 'vue'
import { NConfigProvider } from 'naive-ui'
import type { PluginUIBridge } from '../.dian115/examples/sdk/ui'
import AppPage from './AppPage.vue'
import './preview.css'
let name: unknown=null
const unsupported=async():Promise<never>=>{throw new Error('本地预览未连接宿主')}
const api:PluginUIBridge={
 capabilities:{isolation:'opaque-origin-v1',storage:'host-ui-v1',jobs:true},
 storage:{get:async<T,>()=>structuredClone(name) as T|null,set:async(key,value)=>{if(key!=='display-name'||typeof value!=='string'||value.length>120)throw new Error('invalid preference');name=value},remove:async()=>{name=null},clear:async()=>{name=null}},
 getState:async()=>({state_version:'state-v1',etag:'"state-v1"',state:{message:'模拟状态已就绪'}}),refresh:async()=>({preview:true}),invokeAction:unsupported,
 jobs:{start:unsupported,get:unsupported,cancel:unsupported,resume:unsupported},
}
const Preview=defineComponent({setup:()=>()=>h(NConfigProvider,null,{default:()=>h(AppPage,{api,installationId:1,pluginId:'example.complete-plugin',runtime:null,runtimeState:{preview:true},navKey:'main',themeContract:'dian115-theme-v1'})})})
createApp(Preview).mount('#app')
