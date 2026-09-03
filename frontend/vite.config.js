import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';
import path from 'node:path';
// https://vitejs.dev/config/
export default defineConfig({
    plugins: [react()],
    resolve: {
        alias: {
            '@': path.resolve(__dirname, 'src'),
        },
    },
    build: {
        rollupOptions: {
            output: {
                // 手动分包：大体积第三方库拆为独立 chunk，利用浏览器长缓存
                manualChunks: {
                    react: ['react', 'react-dom', 'react-router-dom'],
                    antd: ['antd', '@ant-design/icons'],
                },
            },
        },
    },
    server: {
        port: 5173,
        host: true,
        proxy: {
            // 后端 REST API 代理（后端启动后再启用）
            '/api': {
                target: 'http://localhost:8000',
                changeOrigin: true,
            },
            // WebSocket 流式对话/提醒推送代理
            '/ws': {
                target: 'ws://localhost:8000',
                ws: true,
                changeOrigin: true,
            },
        },
    },
});
