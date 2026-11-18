import react from '@vitejs/plugin-react';
import type { ProxyOptions } from 'vite';
import { defineConfig } from 'vitest/config';

const backend = process.env.SKYWATCH_BACKEND_URL ?? 'http://127.0.0.1:8000';
const proxy: Record<string, ProxyOptions> = {
  '/api': { target: backend },
  '/ws': { target: backend, ws: true },
};
for (const [camera, port] of [['camera_1', 8765], ['camera_2', 8766]] as const) {
  const prefix = `/preview/${camera}`;
  proxy[`${prefix}/`] = {
    target: process.env[`SKYWATCH_PREVIEW_${camera.toUpperCase()}_URL`] ?? `http://127.0.0.1:${port}`,
    rewrite: (path) => path.slice(prefix.length),
  };
}

export default defineConfig({
  plugins: [react()],
  server: { host: '127.0.0.1', strictPort: true, proxy },
  preview: { host: '127.0.0.1', port: 5173, strictPort: true, proxy },
  test: { environment: 'jsdom' },
});
