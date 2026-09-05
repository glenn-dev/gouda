import react from "@vitejs/plugin-react";
import { defineConfig } from "vitest/config";

export const FRONTEND_HOST = "127.0.0.1";
export const FRONTEND_PORT = 5173;
export const API_PROXY_PATH = "/api";
export const HOST_API_PROXY_TARGET = "http://127.0.0.1:8000";
export const CONTAINER_API_PROXY_TARGET = "http://backend:8000";

const configuredApiProxyTarget = process.env.GOUDA_VITE_API_PROXY_TARGET;
if (
  configuredApiProxyTarget !== undefined &&
  configuredApiProxyTarget !== CONTAINER_API_PROXY_TARGET
) {
  throw new Error("GOUDA_VITE_API_PROXY_TARGET must use the trusted Compose backend");
}
export const API_PROXY_TARGET = configuredApiProxyTarget ?? HOST_API_PROXY_TARGET;

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
