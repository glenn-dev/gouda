import react from "@vitejs/plugin-react";
import { createLogger, type Plugin } from "vite";
import { defineConfig } from "vitest/config";

export const FRONTEND_HOST = "127.0.0.1";
export const FRONTEND_PORT = 5173;
export const API_PROXY_PATH = "/api";
export const HOST_API_PROXY_TARGET = "http://127.0.0.1:8000";
export const CONTAINER_API_PROXY_TARGET = "http://backend:8000";

const configuredApiProxyTarget = process.env.GOUDA_VITE_API_PROXY_TARGET;
// Vite's DEBUG channel bypasses customLogger and logs raw proxy URLs.
// Fail before listening instead of allowing that optional diagnostic channel.
if (process.env.DEBUG) {
  throw new Error("Raw debug logging is unsupported at the local delivery edge");
}
if (
  configuredApiProxyTarget !== undefined &&
  configuredApiProxyTarget !== CONTAINER_API_PROXY_TARGET
) {
  throw new Error("GOUDA_VITE_API_PROXY_TARGET must use the trusted Compose backend");
}
export const API_PROXY_TARGET = configuredApiProxyTarget ?? HOST_API_PROXY_TARGET;

// Vite's default proxy failure log includes raw URLs and exception stacks.
// Keep other development diagnostics, but bound proxy diagnostics explicitly.
export const safeLogger = createLogger();
const originalError = safeLogger.error.bind(safeLogger);
safeLogger.error = (message, options) => {
  if (/proxy (?:socket |bypass )?error:/.test(message)) {
    originalError("http route=api status=500 code=internal_error");
  } else {
    originalError(message, options);
  }
};

export function preserveBoundaryHeaders(): Plugin {
  return {
    name: "gouda-boundary-headers",
    configureServer(server) {
      server.middlewares.use((req, _res, next) => {
        if (req.url?.startsWith(API_PROXY_PATH)) {
          // Node normally discards repeated Host fields. Preserve multiplicity
          // as a combined invalid value so Django can reject it independently.
          for (const name of ["host", "origin", "x-gouda-classification-write"]) {
            const values: string[] = [];
            for (let i = 0; i < req.rawHeaders.length; i += 2) {
              if (req.rawHeaders[i].toLowerCase() === name) values.push(req.rawHeaders[i + 1]);
            }
            if (values.length > 1) req.headers[name] = values.join(",");
          }
        }
        next();
      });
    },
  };
}

export default defineConfig({
  plugins: [react(), preserveBoundaryHeaders()],
  customLogger: safeLogger,
  server: {
    host: FRONTEND_HOST,
    port: FRONTEND_PORT,
    strictPort: true,
    cors: false,
    headers: {
      "Content-Security-Policy": "frame-ancestors 'none'",
      "X-Frame-Options": "DENY",
    },
    proxy: {
      [API_PROXY_PATH]: {
        target: API_PROXY_TARGET,
        changeOrigin: false,
        configure(proxy) {
          proxy.on("error", (_error, _req, res) => {
            if ("writeHead" in res && !res.headersSent && !res.writableEnded) {
              res.writeHead(500, {
                "Content-Type": "application/json",
                "Cache-Control": "no-store, no-cache, max-age=0",
                "X-Content-Type-Options": "nosniff",
                "Cross-Origin-Resource-Policy": "same-origin",
              });
              res.end('{"code":"internal_error"}');
            }
          });
        },
      },
    },
  },
  preview: {
    cors: false,
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
