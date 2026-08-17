import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'

// 开发模式(npm run dev):页面挂在 /,API 代理到后端,热更新
// 构建模式(npm run build):base=/static/,产物由后端 /static 挂载提供
export default defineConfig(({ mode }) => ({
  base: mode === 'development' ? '/' : '/static/',
  plugins: [vue()],
  build: {
    outDir: 'dist',
    emptyOutDir: true,
  },
  server: {
    port: 5173,
    proxy: {
      '/api': 'http://127.0.0.1:8000',
    },
  },
}))
