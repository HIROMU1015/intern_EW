import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// ローカルホスト限定。APIはバックエンド(127.0.0.1:8000)へプロキシする。
export default defineConfig({
  plugins: [react()],
  server: {
    host: '127.0.0.1',
    port: 5173,
    strictPort: true,
    proxy: {
      '/api': {
        target: 'http://127.0.0.1:8000',
        changeOrigin: false,
      },
    },
  },
})
