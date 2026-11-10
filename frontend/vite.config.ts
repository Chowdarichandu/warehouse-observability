import { defineConfig } from 'vitest/config';
import react from '@vitejs/plugin-react';
export default defineConfig({
  plugins: [react()],
  build: {
    rollupOptions: {
      output: {
        manualChunks: (id) => {
          if (id.includes('zrender')) return 'chart-renderer';
          if (id.includes('echarts')) return 'charts';
          if (id.includes('node_modules')) return 'vendor';
        },
      },
    },
  },
  server: {
    host: '127.0.0.1',
    port: 8080,
    strictPort: true,
    proxy: { '/api': { target: 'http://127.0.0.1:8000', changeOrigin: false } },
  },
  preview: { host: '127.0.0.1', port: 8080, proxy: { '/api': 'http://127.0.0.1:8000' } },
  test: {
    pool: 'forks',
    maxWorkers: 1,
    fileParallelism: false,
    environment: 'jsdom',
    setupFiles: ['./src/test-setup.ts'],
    include: ['src/**/*.test.{ts,tsx}'],
  },
});
