import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'
import federation from '@originjs/vite-plugin-federation'

// The plugin runtime supports these Federation singleton flags, but the
// published TypeScript declaration does not currently expose `singleton`.
const hostSharedDependencies = {
  vue: { singleton: true, requiredVersion: false, generate: false },
  'naive-ui': { singleton: true, requiredVersion: false, generate: false },
  '@lucide/vue': { singleton: true, requiredVersion: false, generate: false },
} as any

export default defineConfig({
  plugins: [
    vue(),
    federation({
      name: 'dian115_complete_plugin_example',
      filename: 'remoteEntry.js',
      exposes: {
        './AppPage': './src/AppPage.vue',
      },
      shared: hostSharedDependencies,
    }),
  ],
  build: {
    target: 'esnext',
    outDir: 'build/frontend/dist',
    assetsDir: 'assets',
    cssCodeSplit: true,
    emptyOutDir: true,
  },
})
