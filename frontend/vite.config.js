import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';

// В dev-режиме API проксируется на backend, в production это делает Nginx.
export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: { '/api': { target: 'http://localhost:8000', changeOrigin: true } },
  },
});
