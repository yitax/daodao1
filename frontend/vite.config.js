import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'
import { resolve } from 'path'

// https://vitejs.dev/config/
export default defineConfig({
    plugins: [vue()],
    base: '/',
    resolve: {
        alias: {
            '@': resolve(__dirname, 'src')
        }
    },
    server: {
        port: 5173,
        open: true,
        proxy: {
            '/users': {
                target: 'http://localhost:8000',
                changeOrigin: true,
            },
            '/transactions': {
                target: 'http://localhost:8000',
                changeOrigin: true,
            },
            '/reports': {
                target: 'http://localhost:8000',
                changeOrigin: true,
            },
            '/chat': {
                target: 'http://localhost:8000',
                changeOrigin: true,
            }
        }
    },
    build: {
        outDir: 'dist',
        assetsDir: 'assets'
    }
}) 