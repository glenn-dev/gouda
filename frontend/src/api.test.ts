import { describe, expect, it, vi } from "vitest";

import { fetchAccounts, fetchMovementReport } from "./api";
import {
  accountsResponse,
  jsonResponse,
  movementReportResponse,
  PRIMARY_ACCOUNT_ID,
} from "./test/fixtures";

describe("explicit read-only API client", () => {
  it("uses only GET without authentication, tokens, cookies, or write methods", async () => {
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce(jsonResponse(accountsResponse))
      .mockResolvedValueOnce(jsonResponse(movementReportResponse()));
    vi.stubGlobal("fetch", fetchMock);

    await fetchAccounts();
    await fetchMovementReport(PRIMARY_ACCOUNT_ID, "2026-04-01", "2026-04-30");

    expect(fetchMock).toHaveBeenNthCalledWith(1, "/api/v1/accounts/", {
      method: "GET",
      headers: { Accept: "application/json" },
    });
    expect(fetchMock).toHaveBeenNthCalledWith(
      2,
      `/api/v1/accounts/${PRIMARY_ACCOUNT_ID}/movements/?start_date=2026-04-01&end_date=2026-04-30`,
      {
        method: "GET",
        headers: { Accept: "application/json" },
      },
    );

    for (const [, options] of fetchMock.mock.calls) {
      expect(options).not.toHaveProperty("body");
      expect(options).not.toHaveProperty("credentials");
      expect(options.headers).not.toHaveProperty("Authorization");
      expect(options.headers).not.toHaveProperty("Cookie");
    }
  });

  it("drops bounded source provenance from the client-side report model", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValueOnce(jsonResponse(movementReportResponse())),
    );

    const report = await fetchMovementReport(
      PRIMARY_ACCOUNT_ID,
      "2026-04-01",
      "2026-04-30",
    );

    expect(report.movements[0]).toEqual({
      movement_id: "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa",
      account_id: PRIMARY_ACCOUNT_ID,
      occurrence_date: "2026-04-30",
      signed_amount: "1234567890123456.78",
      currency: "CLP",
      description: "Synthetic returned first",
    });
    expect(report.movements[0]).not.toHaveProperty("source_trace");
  });

  it("maps a non-JSON proxy failure to the safe backend-unavailable error", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValueOnce({
        ok: false,
        status: 500,
        json: async () => {
          throw new SyntaxError("synthetic proxy text response");
        },
      } as unknown as Response),
    );

    await expect(fetchAccounts()).rejects.toMatchObject({
      code: "backend_unavailable",
      message:
        "Cannot reach the local Gouda backend. Confirm both local services are running and try again.",
    });
  });
});
