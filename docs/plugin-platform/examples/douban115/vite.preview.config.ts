import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'
import federation from '@originjs/vite-plugin-federation'

// 仅用于本地可视化预览（npm run build:preview）：
// 与正式构建的唯一区别是共享依赖允许打包进产物（generate 默认 true），
// 因为没有 dian115 宿主提供 vue/naive-ui/@lucide/vue 的 singleton。
// 正式打包仍使用 vite.config.ts（generate: false，体积最小）。
export default defineConfig({
  plugins: [
    vue(),
    federation({
      name: 'dian115_douban115',
      filename: 'remoteEntry.js',
      exposes: {
        './AppPage': './src/AppPage.vue',
      },
      shared: {
        vue: { requiredVersion: false },
        'naive-ui': { requiredVersion: false },
        '@lucide/vue': { requiredVersion: false },
      } as any,
    }),
  ],
  build: {
    target: 'esnext',
    outDir: 'build/preview',
    assetsDir: 'assets',
    cssCodeSplit: true,
    emptyOutDir: true,
  },
})
