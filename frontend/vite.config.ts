import react from "@vitejs/plugin-react";
import { defineConfig } from "vitest/config";

export const FRONTEND_HOST = "127.0.0.1";
export const FRONTEND_PORT = 5173;
export const API_PROXY_PATH = "/api";
export const API_PROXY_TARGET = "http://127.0.0.1:8000";

export default defineConfig({
  plugins: [react()],
  server: {
    host: FRONTEND_HOST,
    port: FRONTEND_PORT,
    strictPort: true,
    proxy: {
      [API_PROXY_PATH]: {
        target: API_PROXY_TARGET,
        changeOrigin: false,
      },
    },
  },
  preview: {
    host: FRONTEND_HOST,
    port: 4173,
    strictPort: true,
  },
  test: {
    environment: "jsdom",
    setupFiles: "./src/test/setup.ts",
    clearMocks: true,
  },
});
