import { defineConfig } from 'vitest/config';
import react from '@vitejs/plugin-react';
const apiTarget = process.env.OBS_API_PROXY_TARGET ?? 'http://127.0.0.1:8000';
export default defineConfig({
  plugins: [react()],
  build: {
    rollupOptions: {
      output: {
        manualChunks: (id) => {
          if (id.includes('zrender')) return 'chart-renderer';
          if (id.includes('echarts')) return 'charts';
        },
      },
    },
  },
  server: {
    host: '127.0.0.1',
    port: 8080,
    strictPort: true,
    proxy: { '/api': { target: apiTarget, changeOrigin: false } },
  },
  preview: { host: '127.0.0.1', port: 8080, proxy: { '/api': apiTarget } },
  test: {
    pool: 'forks',
    maxWorkers: 1,
    fileParallelism: false,
    environment: 'jsdom',
    setupFiles: ['./src/test-setup.ts'],
    include: ['src/**/*.test.{ts,tsx}'],
  },
});
