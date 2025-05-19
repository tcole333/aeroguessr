import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import path from "path";

// https://vite.dev/config/
export default defineConfig({
  plugins: [react()],
  resolve: {
    alias: {
      "@": path.resolve(__dirname, "./src"),
    },
  },
  server: {
    proxy: {
      '/api': {
        target: 'http://localhost:8000',
        changeOrigin: true,
        ws: true,
      },
      // If you also have WebSockets to proxy, you might add a ws proxy here
      // For example, if your WS backend is on port 8000 at /ws
      '/ws': {
        target: 'ws://localhost:8000',
        ws: true,
      },
    },
  },
});
