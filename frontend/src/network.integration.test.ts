// @vitest-environment node
import { createServer as createHttpServer, request } from "node:http";
import type { AddressInfo } from "node:net";
import { createServer, type ProxyOptions, type UserConfig } from "vite";
import { expect, it, vi } from "vitest";
import config from "../vite.config";

it("preserves actual proxy headers, adds no CORS grants, and sanitizes proxy failures", async () => {
  const sentinel = "synthetic-capability-sentinel";
  const backend = createHttpServer((req, res) => {
    res.setHeader("Content-Type", "application/json");
    res.end(JSON.stringify({ host: req.headers.host, origin: req.headers.origin,
      capability: req.headers["x-gouda-classification-write"],
      importCapability: req.headers["x-gouda-financial-import"] }));
  });
  await new Promise<void>((resolve) => backend.listen(0, "127.0.0.1", resolve));
  const backendPort = (backend.address() as AddressInfo).port;
  const actual = config as UserConfig;
  const proxy = actual.server!.proxy!["/api"] as ProxyOptions;
  const server = await createServer({
    ...actual, configFile: false,
    server: { ...actual.server, port: 0, proxy: {
      "/api": { ...proxy, target: `http://127.0.0.1:${backendPort}` },
    } },
  });
  const errors = vi.spyOn(console, "error").mockImplementation(() => {});
  try {
    await server.listen();
    const port = (server.httpServer!.address() as AddressInfo).port;
    const send = (method: string, headers: string[], path = "/api/test") =>
      new Promise<{ status: number; headers: Record<string, unknown>; body: string }>((resolve, reject) => {
        const req = request({ hostname: "127.0.0.1", port, path, method, headers }, (res) => {
          let body = "";
          res.on("data", (data: Buffer) => { body += data.toString(); });
          res.on("end", () => resolve({ status: res.statusCode!, headers: res.headers, body }));
        });
        req.on("error", reject);
        req.end();
      });
    for (const method of ["POST", "PATCH", "OPTIONS"]) {
      for (const origin of ["http://127.0.0.1:5173", "https://evil.invalid", "http://localhost:5173", "null"]) {
        const response = await send(method, ["Host", "127.0.0.1:5173", "Origin", origin,
          "X-Gouda-Classification-Write", sentinel, "X-Gouda-Financial-Import", sentinel,
          "Access-Control-Request-Method", "PATCH"]);
        expect(response.status).toBe(200); // Synthetic upstream; Django owns authorization.
        expect(JSON.parse(response.body)).toEqual({ host: "127.0.0.1:5173", origin,
          capability: sentinel, importCapability: sentinel });
        expect(Object.keys(response.headers).filter((key) => key.startsWith("access-control-"))).toEqual([]);
      }
    }
    for (const name of ["Host", "Origin", "X-Gouda-Classification-Write", "X-Gouda-Financial-Import"]) {
      const headers = ["Host", "127.0.0.1:5173", "Origin", "http://127.0.0.1:5173",
        "X-Gouda-Classification-Write", sentinel, "X-Gouda-Financial-Import", sentinel,
        name, "duplicate"];
      const response = await send("PATCH", headers);
      const echoed = JSON.parse(response.body) as Record<string, string>;
      const key = name === "Host" ? "host" : name === "Origin" ? "origin" :
        name === "X-Gouda-Classification-Write" ? "capability" : "importCapability";
      expect(echoed[key]).toContain(",duplicate");
    }
    await new Promise<void>((resolve, reject) => backend.close((error) => error ? reject(error) : resolve()));
    const failed = await send("PATCH", ["Host", "127.0.0.1:5173",
      "X-Gouda-Classification-Write", sentinel], "/api/" + sentinel + "?token=" + sentinel);
    expect(failed.status).toBe(500);
    expect(JSON.parse(failed.body)).toEqual({ code: "internal_error" });
    expect(failed.headers["cache-control"]).toContain("no-store");
    expect(failed.headers["location"]).toBeUndefined();
    expect(failed.headers["access-control-allow-origin"]).toBeUndefined();
    expect(JSON.stringify(errors.mock.calls)).not.toContain(sentinel);
    expect(JSON.stringify(errors.mock.calls)).toContain("code=internal_error");
  } finally {
    errors.mockRestore();
    await server.close();
    if (backend.listening) await new Promise<void>((resolve) => backend.close(() => resolve()));
  }
}, 20000);
