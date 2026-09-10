import { beforeEach, describe, expect, it, vi } from "vitest";

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

const IMPORT_RESULT = {
  account_id: PRIMARY_ACCOUNT_ID,
  batch_id: "22222222-2222-4222-8222-222222222222",
  status: "PARTIAL",
  duplicate_of: null,
  created_movement_count: 2,
  statement: {
    status: "PARTIAL",
    source_row_count: 9,
    parsed_count: 2,
    ignored_count: 6,
    rejected_count: 1,
    reconciliation_status: "NOT_RECONCILED",
    period_start: "2026-04-01",
    period_end: "2026-04-30",
  },
};

describe("financial-import API client", () => {
  beforeEach(() => {
    vi.resetModules();
    vi.unstubAllGlobals();
  });

  it("bootstraps only on explicit import and submits exactly one multipart field", async () => {
    const capability = "a".repeat(64);
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce(jsonResponse({ import_capability: capability }))
      .mockResolvedValueOnce(jsonResponse(IMPORT_RESULT));
    vi.stubGlobal("fetch", fetchMock);
    const storageSet = vi.spyOn(Storage.prototype, "setItem");
    const { importSantanderCurrentAccountXlsx } = await import("./api");
    expect(fetchMock).not.toHaveBeenCalled();

    const file = new File(["synthetic"], "synthetic.xlsx", {
      type: "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    });
    const result = await importSantanderCurrentAccountXlsx(PRIMARY_ACCOUNT_ID, file);

    expect(result.status).toBe("PARTIAL");
    expect(fetchMock).toHaveBeenNthCalledWith(1, "/api/v1/local/financial-import-capability/", {
      method: "POST",
      headers: { Accept: "application/json", "Content-Type": "application/json" },
      body: "{}",
      mode: "same-origin",
      cache: "no-store",
      credentials: "omit",
      redirect: "error",
    });
    const [url, options] = fetchMock.mock.calls[1] as [string, RequestInit];
    expect(url).toBe(
      `/api/v1/accounts/${PRIMARY_ACCOUNT_ID}/imports/santander-current-account-xlsx/`,
    );
    expect(options.method).toBe("POST");
    expect(options.mode).toBe("same-origin");
    expect(options.credentials).toBe("omit");
    expect(options.headers).toEqual({
      Accept: "application/json",
      "X-Gouda-Financial-Import": capability,
    });
    expect(options.headers).not.toHaveProperty("Authorization");
    expect(options.headers).not.toHaveProperty("Cookie");
    expect(options.headers).not.toHaveProperty("Content-Type");
    const form = options.body as FormData;
    expect([...form.keys()]).toEqual(["statement"]);
    expect(form.get("statement")).toBe(file);
    expect(storageSet).not.toHaveBeenCalled();
  });

  it("accepts a truthful duplicate and never derives financial values", async () => {
    const duplicate = {
      ...IMPORT_RESULT,
      status: "DUPLICATE",
      duplicate_of: "11111111-1111-4111-8111-111111111111",
      created_movement_count: 0,
    };
    vi.stubGlobal(
      "fetch",
      vi
        .fn()
        .mockResolvedValueOnce(jsonResponse({ import_capability: "b".repeat(64) }))
        .mockResolvedValueOnce(jsonResponse(duplicate)),
    );
    const { importSantanderCurrentAccountXlsx } = await import("./api");
    const result = await importSantanderCurrentAccountXlsx(
      PRIMARY_ACCOUNT_ID,
      new File(["synthetic"], "synthetic.xlsx"),
    );
    expect(result).toEqual(duplicate);
    expect(result.statement.reconciliation_status).toBe("NOT_RECONCILED");
  });

  it("does not automatically replay ambiguous uploads or invalid capabilities", async () => {
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce(jsonResponse({ import_capability: "c".repeat(64) }))
      .mockRejectedValueOnce(new Error("synthetic network loss"));
    vi.stubGlobal("fetch", fetchMock);
    const { importSantanderCurrentAccountXlsx } = await import("./api");
    await expect(
      importSantanderCurrentAccountXlsx(
        PRIMARY_ACCOUNT_ID,
        new File(["synthetic"], "synthetic.xlsx"),
      ),
    ).rejects.toMatchObject({ code: "import_outcome_uncertain", outcomeUncertain: true });
    expect(fetchMock).toHaveBeenCalledTimes(2);

    vi.resetModules();
    const invalidFetch = vi
      .fn()
      .mockResolvedValueOnce(jsonResponse({ import_capability: "d".repeat(64) }))
      .mockResolvedValueOnce(jsonResponse({ code: "import_capability_invalid" }, 403));
    vi.stubGlobal("fetch", invalidFetch);
    const fresh = await import("./api");
    await expect(
      fresh.importSantanderCurrentAccountXlsx(
        PRIMARY_ACCOUNT_ID,
        new File(["synthetic"], "synthetic.xlsx"),
      ),
    ).rejects.toMatchObject({ code: "import_capability_invalid", outcomeUncertain: false });
    expect(invalidFetch).toHaveBeenCalledTimes(2);
  });

  it("treats a 5xx or malformed success response as ambiguous", async () => {
    for (const response of (
      [jsonResponse({ code: "internal_error" }, 500), jsonResponse({ private: "row" })]
    )) {
      vi.resetModules();
      vi.stubGlobal(
        "fetch",
        vi
          .fn()
          .mockResolvedValueOnce(jsonResponse({ import_capability: "e".repeat(64) }))
          .mockResolvedValueOnce(response),
      );
      const { importSantanderCurrentAccountXlsx } = await import("./api");
      await expect(
        importSantanderCurrentAccountXlsx(
          PRIMARY_ACCOUNT_ID,
          new File(["synthetic"], "synthetic.xlsx"),
        ),
      ).rejects.toMatchObject({ outcomeUncertain: true });
    }
  });
});
