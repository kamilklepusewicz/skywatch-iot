import react from '@vitejs/plugin-react';
import { defineConfig } from 'vitest/config';

const backend = process.env.SKYWATCH_BACKEND_URL ?? 'http://127.0.0.1:8000';
const proxy = {
  '/api': { target: backend },
  '/ws': { target: backend, ws: true },
};

export default defineConfig({
  plugins: [react()],
  server: { host: '127.0.0.1', strictPort: true, proxy },
  preview: { host: '127.0.0.1', port: 5173, strictPort: true, proxy },
  test: { environment: 'jsdom' },
});
