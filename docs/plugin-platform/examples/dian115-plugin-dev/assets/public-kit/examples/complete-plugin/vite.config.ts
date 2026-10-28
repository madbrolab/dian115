import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'

export default defineConfig({
  base: './',
  plugins: [vue()],
  build: {
    target: 'esnext',
    outDir: 'build/frontend/dist',
    assetsDir: 'assets',
    cssCodeSplit: true,
    emptyOutDir: true,
  },
})
