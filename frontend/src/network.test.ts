import { UserConfig } from "vite";
import { describe, expect, it, vi } from "vitest";

import config, {
  API_PROXY_PATH,
  API_PROXY_TARGET,
  CONTAINER_API_PROXY_TARGET,
  FRONTEND_HOST,
  FRONTEND_PORT,
  HOST_API_PROXY_TARGET,
} from "../vite.config";

describe("local-only Vite network configuration", () => {
  it("rejects raw debug logging before starting the delivery edge", async () => {
    vi.resetModules();
    vi.stubEnv("DEBUG", "vite:proxy");
    try {
      await expect(import("../vite.config")).rejects.toThrow(
        "Raw debug logging is unsupported at the local delivery edge",
      );
    } finally {
      vi.unstubAllEnvs();
      vi.resetModules();
    }
  });

  it("uses only the supported host or Compose /api proxy target", () => {
    const userConfig = config as UserConfig;

    expect(FRONTEND_HOST).toBe("127.0.0.1");
    expect(FRONTEND_PORT).toBe(5173);
    expect(API_PROXY_PATH).toBe("/api");
    expect(HOST_API_PROXY_TARGET).toBe("http://127.0.0.1:8000");
    expect(CONTAINER_API_PROXY_TARGET).toBe("http://backend:8000");
    expect(API_PROXY_TARGET).toBe(
      process.env.GOUDA_VITE_API_PROXY_TARGET === CONTAINER_API_PROXY_TARGET
        ? CONTAINER_API_PROXY_TARGET
        : HOST_API_PROXY_TARGET,
    );
    expect(userConfig.server?.host).toBe("127.0.0.1");
    expect(userConfig.server?.strictPort).toBe(true);
    expect(Object.keys(userConfig.server?.proxy ?? {})).toEqual(["/api"]);
    expect(userConfig.server?.cors).toBe(false);
    expect(userConfig.preview?.cors).toBe(false);
    expect(userConfig.server?.headers).toEqual({
      "Content-Security-Policy": "frame-ancestors 'none'",
      "X-Frame-Options": "DENY",
    });
    expect(userConfig.preview?.host).toBe("127.0.0.1");
  });
});
