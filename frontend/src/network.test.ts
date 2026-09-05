import { UserConfig } from "vite";
import { describe, expect, it } from "vitest";

import config, {
  API_PROXY_PATH,
  API_PROXY_TARGET,
  CONTAINER_API_PROXY_TARGET,
  FRONTEND_HOST,
  FRONTEND_PORT,
  HOST_API_PROXY_TARGET,
} from "../vite.config";

describe("local-only Vite network configuration", () => {
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
    expect(userConfig.server?.cors).not.toBe(true);
    expect(userConfig.preview?.host).toBe("127.0.0.1");
  });
});
