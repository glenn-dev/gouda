import { describe, expect, it, vi } from "vitest";

import { fetchAccounts, fetchMovementReport } from "./api";
import {
  ACTIVE_CATEGORY_ID,
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

  it("retains validated classification while dropping bounded source provenance", async () => {
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
      classification: {
        state: "CLASSIFIED",
        category: {
          id: ACTIVE_CATEGORY_ID,
          display_name: "Synthetic essentials",
          is_active: true,
        },
        revision: 3,
      },
    });
    expect(report.movements[0]).not.toHaveProperty("source_trace");
    expect(report.movements[0].classification).not.toHaveProperty("source");
    expect(report.movements[0].classification).not.toHaveProperty("updated_at");
  });

  it("retains never-assigned and cleared as distinct validated internal states", async () => {
    const response = movementReportResponse();
    response.movements[0].classification = {
      state: "NEVER_ASSIGNED",
      category: null,
      revision: 0,
    };
    response.movements[1].classification = {
      state: "CLEARED",
      category: null,
      revision: 7,
    };
    vi.stubGlobal("fetch", vi.fn().mockResolvedValueOnce(jsonResponse(response)));

    const report = await fetchMovementReport(
      PRIMARY_ACCOUNT_ID,
      "2026-04-01",
      "2026-04-30",
    );

    expect(report.movements.map((movement) => movement.classification)).toEqual([
      { state: "NEVER_ASSIGNED", category: null, revision: 0 },
      { state: "CLEARED", category: null, revision: 7 },
    ]);
    expect(report.movements[0].signed_amount).toBe("1234567890123456.78");
    expect(report.net_signed_amount).toBe("1234567890123456.77");
  });

  it.each([
    ["missing classification", undefined],
    ["never-assigned revision", { state: "NEVER_ASSIGNED", category: null, revision: 1 }],
    [
      "never-assigned category",
      {
        state: "NEVER_ASSIGNED",
        category: { id: ACTIVE_CATEGORY_ID, display_name: "Synthetic", is_active: true },
        revision: 0,
      },
    ],
    ["classified null category", { state: "CLASSIFIED", category: null, revision: 1 }],
    [
      "classified zero revision",
      {
        state: "CLASSIFIED",
        category: { id: ACTIVE_CATEGORY_ID, display_name: "Synthetic", is_active: true },
        revision: 0,
      },
    ],
    [
      "cleared category",
      {
        state: "CLEARED",
        category: { id: ACTIVE_CATEGORY_ID, display_name: "Synthetic", is_active: true },
        revision: 2,
      },
    ],
    ["cleared zero revision", { state: "CLEARED", category: null, revision: 0 }],
    ["unknown state", { state: "PENDING", category: null, revision: 1 }],
    [
      "malformed category UUID",
      {
        state: "CLASSIFIED",
        category: { id: "not-a-uuid", display_name: "Synthetic", is_active: true },
        revision: 1,
      },
    ],
    [
      "empty category name",
      {
        state: "CLASSIFIED",
        category: { id: ACTIVE_CATEGORY_ID, display_name: "", is_active: true },
        revision: 1,
      },
    ],
    [
      "long category name",
      {
        state: "CLASSIFIED",
        category: { id: ACTIVE_CATEGORY_ID, display_name: "x".repeat(81), is_active: true },
        revision: 1,
      },
    ],
    [
      "non-string category name",
      {
        state: "CLASSIFIED",
        category: { id: ACTIVE_CATEGORY_ID, display_name: 42, is_active: true },
        revision: 1,
      },
    ],
    [
      "category name with a control character",
      {
        state: "CLASSIFIED",
        category: { id: ACTIVE_CATEGORY_ID, display_name: "Synthetic\nTopic", is_active: true },
        revision: 1,
      },
    ],
    [
      "non-normalized category name",
      {
        state: "CLASSIFIED",
        category: { id: ACTIVE_CATEGORY_ID, display_name: "Cafe\u0301", is_active: true },
        revision: 1,
      },
    ],
    [
      "malformed active flag",
      {
        state: "CLASSIFIED",
        category: { id: ACTIVE_CATEGORY_ID, display_name: "Synthetic", is_active: "true" },
        revision: 1,
      },
    ],
    [
      "string revision",
      {
        state: "CLASSIFIED",
        category: { id: ACTIVE_CATEGORY_ID, display_name: "Synthetic", is_active: true },
        revision: "1",
      },
    ],
    [
      "fractional revision",
      {
        state: "CLASSIFIED",
        category: { id: ACTIVE_CATEGORY_ID, display_name: "Synthetic", is_active: true },
        revision: 1.5,
      },
    ],
    [
      "unsafe integer revision",
      {
        state: "CLASSIFIED",
        category: { id: ACTIVE_CATEGORY_ID, display_name: "Synthetic", is_active: true },
        revision: Number.MAX_SAFE_INTEGER + 1,
      },
    ],
    [
      "extra classification metadata",
      { state: "CLEARED", category: null, revision: 2, source: "MANUAL" },
    ],
    [
      "extra category metadata",
      {
        state: "CLASSIFIED",
        category: {
          id: ACTIVE_CATEGORY_ID,
          display_name: "Synthetic",
          is_active: true,
          provider: "SYNTHETIC_PRIVATE_PROVIDER",
        },
        revision: 1,
      },
    ],
  ])("rejects %s fail closed", async (_label, classification) => {
    const response = movementReportResponse() as unknown as {
      movements: Array<Record<string, unknown>>;
    };
    if (classification === undefined) {
      delete response.movements[0].classification;
    } else {
      response.movements[0].classification = classification;
    }
    vi.stubGlobal("fetch", vi.fn().mockResolvedValueOnce(jsonResponse(response)));

    await expect(
      fetchMovementReport(PRIMARY_ACCOUNT_ID, "2026-04-01", "2026-04-30"),
    ).rejects.toMatchObject({ code: "unexpected_response" });
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
