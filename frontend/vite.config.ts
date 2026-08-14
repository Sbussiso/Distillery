import { defineConfig } from "vite";
import { svelte } from "@sveltejs/vite-plugin-svelte";
import tailwindcss from "@tailwindcss/vite";

// Dev: Vite serves the frontend at :5173 and proxies /api (incl. the
// /api/distill/{id}/stream WebSocket) to the FastAPI backend at :8000.
// Prod: `npm run build` emits `dist/`, which FastAPI serves directly, so the
// frontend and API share an origin and the relative `/api` paths just work.
export default defineConfig({
  plugins: [svelte(), tailwindcss()],
  server: {
    port: 5173,
    proxy: {
      "/api": {
        target: "http://127.0.0.1:8000",
        changeOrigin: true,
        ws: true,
      },
    },
  },
  build: {
    outDir: "dist",
    emptyOutDir: true,
  },
});