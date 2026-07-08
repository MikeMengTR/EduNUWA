import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

export default defineConfig({
  plugins: [react()],
  server: {
    host: true,       // 监听 0.0.0.0，允许同一局域网内其它电脑通过本机 IP:3000 访问
    port: 3000,
    proxy: {
      // 必须用 127.0.0.1：node 17+ 把 localhost 优先解析为 IPv6 ::1，
      // 而 Flask 只监听 IPv4，会造成偶发 502/Failed to fetch（流式请求首当其冲）
      '/api': 'http://127.0.0.1:5000',
      '/runtime': 'http://127.0.0.1:5000'
    }
  }
})
