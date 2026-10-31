import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import path from "path";

// The canonical airport dataset lives at the repo root so the backend can score
// against the same file the autocomplete searches.
const dataDir = path.resolve(__dirname, "../data");

// scripts/dev.sh picks free ports for each checkout's stack and passes them here.
const apiPort = process.env.DEV_API_PORT || "8000";
const webPort = process.env.DEV_WEB_PORT;

// https://vite.dev/config/
export default defineConfig({
  plugins: [react()],
  resolve: {
    alias: {
      "@": path.resolve(__dirname, "./src"),
      "@data": dataDir,
    },
  },
  server: {
    host: '0.0.0.0', // Allow access from other devices on network
    port: webPort ? Number(webPort) : 5173,
    // dev.sh prints the URL with its port, so fail rather than move to another one.
    strictPort: Boolean(webPort),
    // Vite only serves files under the frontend root by default; without this
    // the dev server answers 403 for the dataset.
    fs: {
      allow: [__dirname, dataDir],
    },
    proxy: {
      '/api': {
        // uvicorn listens on IPv4. "localhost" may resolve to ::1 first, where another
        // process can hold the same port.
        target: `http://127.0.0.1:${apiPort}`,
        changeOrigin: true,
        ws: true, // Enable WebSocket proxying
      },
    },
  },
});
