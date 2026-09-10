import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { App } from "./App";
import { clearFinancialImportCapability } from "./api";
import {
  ACTIVE_CATEGORY_ID,
  accountsResponse,
  CARD_ACCOUNT_ID,
  jsonResponse,
  movementReportResponse,
  PRIMARY_ACCOUNT_ID,
} from "./test/fixtures";

describe("Gouda read-only report flow", () => {
  beforeEach(() => {
    vi.unstubAllGlobals();
  });

  it("loads Accounts and renders canonical labels without visibly exposing UUIDs", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValueOnce(jsonResponse(accountsResponse)));

    render(<App />);

    expect(screen.getByText("Loading accessible Accounts…")).toBeInTheDocument();
    const selector = await screen.findByLabelText("Report Account");
    expect(selector).toHaveValue(PRIMARY_ACCOUNT_ID);
    expect(
      screen.getByRole("option", {
        name: "Synthetic Daily Account — Current account — CLP",
      }),
    ).toBeInTheDocument();
    expect(
      screen.getByRole("option", { name: "Synthetic Card — Credit card — USD" }),
    ).toBeInTheDocument();
    expect(selector).toHaveAccessibleDescription(
      "Synthetic Daily Account · Current account · CLP",
    );
    expect(screen.getByLabelText("Start date")).toBeRequired();
    expect(screen.getByLabelText("End date")).toBeRequired();
    expect(screen.queryByText(PRIMARY_ACCOUNT_ID)).not.toBeInTheDocument();
    expect(screen.queryByText(CARD_ACCOUNT_ID)).not.toBeInTheDocument();
  });

  it("renders a deterministic empty Account state", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValueOnce(jsonResponse({ count: 0, accounts: [] })),
    );

    render(<App />);

    expect(await screen.findByText("No accessible Accounts are available.")).toBeInTheDocument();
    expect(screen.queryByLabelText("Report Account")).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Load Movement report" })).not.toBeInTheDocument();
  });

  it("renders a safe backend-unavailable Account loading error", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockRejectedValueOnce(new Error("SYNTHETIC_PRIVATE_NETWORK_INTERNAL")),
    );

    render(<App />);

    expect(
      await screen.findByText(
        "Cannot reach the local Gouda backend. Confirm both local services are running and try again.",
      ),
    ).toBeInTheDocument();
    expect(screen.queryByText("SYNTHETIC_PRIVATE_NETWORK_INTERNAL")).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Retry Account discovery" })).toBeInTheDocument();
  });

  it("requests the selected Account UUID with exact ISO dates only after explicit action", async () => {
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce(jsonResponse(accountsResponse))
      .mockResolvedValueOnce(
        jsonResponse(movementReportResponse(CARD_ACCOUNT_ID, "2026-06-01", "2026-06-30")),
      );
    vi.stubGlobal("fetch", fetchMock);
    const user = userEvent.setup();

    render(<App />);
    const selector = await screen.findByLabelText("Report Account");
    expect(fetchMock).toHaveBeenCalledTimes(1);
    await user.selectOptions(selector, CARD_ACCOUNT_ID);
    fillDateRange("2026-06-01", "2026-06-30");
    expect(fetchMock).toHaveBeenCalledTimes(1);

    await user.click(screen.getByRole("button", { name: "Load Movement report" }));

    expect(fetchMock).toHaveBeenNthCalledWith(
      2,
      `/api/v1/accounts/${CARD_ACCOUNT_ID}/movements/?start_date=2026-06-01&end_date=2026-06-30`,
      {
        method: "GET",
        headers: { Accept: "application/json" },
      },
    );
    expect(await screen.findByRole("heading", { name: "Synthetic Card" })).toBeInTheDocument();
  });

  it("renders the canonical count, exact strings, and Movement order returned by the backend", async () => {
    vi.stubGlobal(
      "fetch",
      vi
        .fn()
        .mockResolvedValueOnce(jsonResponse(accountsResponse))
        .mockResolvedValueOnce(jsonResponse(movementReportResponse())),
    );
    const user = userEvent.setup();

    render(<App />);
    await screen.findByLabelText("Report Account");
    fillDateRange("2026-04-01", "2026-04-30");
    await user.click(screen.getByRole("button", { name: "Load Movement report" }));

    expect(await screen.findByText("+1.234.567.890.123.456,77 CLP")).toBeInTheDocument();
    expect(screen.getByText("+1.234.567.890.123.456,78 CLP")).toBeInTheDocument();
    expect(screen.getByText("−0,01 CLP")).toBeInTheDocument();
    const summary = screen.getByText("Movement count").closest("div");
    expect(summary).not.toBeNull();
    expect(within(summary!).getByText("2")).toBeInTheDocument();

    const rows = screen.getAllByRole("listitem");
    expect(within(rows[0]).getByText("Synthetic returned first")).toBeInTheDocument();
    expect(within(rows[0]).getByText("Category: Synthetic essentials")).toBeInTheDocument();
    expect(within(rows[0]).getByText("2026-04-30")).toBeInTheDocument();
    expect(within(rows[1]).getByText("Synthetic returned second")).toBeInTheDocument();
    expect(within(rows[1]).getByText("2026-04-01")).toBeInTheDocument();

    for (const hiddenValue of [
      PRIMARY_ACCOUNT_ID,
      "SYNTHETIC_PRIVATE_FILENAME.xlsx",
      "SYNTHETIC_PRIVATE_DIGEST",
      "cccccccc-cccc-4ccc-8ccc-cccccccccccc",
      "dddddddd-dddd-4ddd-8ddd-dddddddddddd",
      "source_trace",
      "raw_record_id",
      "import_batch_id",
    ]) {
      expect(screen.queryByText(hiddenValue)).not.toBeInTheDocument();
    }
  });

  it("renders active, inactive, never-assigned, and cleared classifications read-only", async () => {
    const response = movementReportResponse() as unknown as {
      movement_count: number;
      movements: Array<Record<string, unknown>>;
    };
    response.movement_count = 4;
    response.movements = [
      {
        ...response.movements[0],
        classification: {
          state: "CLASSIFIED",
          category: {
            id: ACTIVE_CATEGORY_ID,
            display_name: "Synthetic active topic",
            is_active: true,
          },
          revision: 731,
        },
      },
      {
        ...response.movements[1],
        movement_id: "cccccccc-cccc-4ccc-8ccc-cccccccccccc",
        classification: {
          state: "CLASSIFIED",
          category: {
            id: "44444444-4444-4444-8444-444444444444",
            display_name: "Synthetic inactive topic with a deliberately long readable label",
            is_active: false,
          },
          revision: 947,
        },
      },
      {
        ...response.movements[1],
        movement_id: "dddddddd-dddd-4ddd-8ddd-dddddddddddd",
        classification: { state: "NEVER_ASSIGNED", category: null, revision: 0 },
      },
      {
        ...response.movements[1],
        movement_id: "eeeeeeee-eeee-4eee-8eee-eeeeeeeeeeee",
        classification: { state: "CLEARED", category: null, revision: 12 },
      },
    ];
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce(jsonResponse(accountsResponse))
      .mockResolvedValueOnce(jsonResponse(response));
    vi.stubGlobal("fetch", fetchMock);
    const user = userEvent.setup();

    render(<App />);
    await screen.findByLabelText("Report Account");
    fillDateRange("2026-04-01", "2026-04-30");
    await user.click(screen.getByRole("button", { name: "Load Movement report" }));

    expect(await screen.findByText("Category: Synthetic active topic")).toBeInTheDocument();
    expect(
      screen.getByText(
        "Category: Synthetic inactive topic with a deliberately long readable label · Inactive",
      ),
    ).toBeInTheDocument();
    expect(screen.getAllByText("Category: Unclassified")).toHaveLength(2);

    for (const hiddenValue of [
      ACTIVE_CATEGORY_ID,
      "44444444-4444-4444-8444-444444444444",
      "NEVER_ASSIGNED",
      "CLASSIFIED",
      "CLEARED",
      "731",
      "947",
      "12",
      "MANUAL",
    ]) {
      expect(screen.queryByText(hiddenValue)).not.toBeInTheDocument();
    }
    expect(fetchMock).toHaveBeenCalledTimes(2);
    expect(fetchMock.mock.calls.every(([, options]) => options.method === "GET")).toBe(true);
    expect(fetchMock.mock.calls.map(([url]) => url)).not.toContain("/api/v1/categories/");
  });

  it("renders an empty canonical Movement result", async () => {
    const emptyReport = {
      ...movementReportResponse(),
      movement_count: 0,
      net_signed_amount: "0.00",
      movements: [],
    };
    vi.stubGlobal(
      "fetch",
      vi
        .fn()
        .mockResolvedValueOnce(jsonResponse(accountsResponse))
        .mockResolvedValueOnce(jsonResponse(emptyReport)),
    );
    const user = userEvent.setup();

    render(<App />);
    await screen.findByLabelText("Report Account");
    fillDateRange("2026-04-01", "2026-04-30");
    await user.click(screen.getByRole("button", { name: "Load Movement report" }));

    expect(
      await screen.findByText("No canonical Movements were found for this date range."),
    ).toBeInTheDocument();
    expect(screen.getByText("0 CLP")).toBeInTheDocument();
  });

  it.each([
    [
      400,
      "date_range_invalid",
      "The backend rejected the date range. The start date must not be after the end date.",
    ],
    [
      404,
      "account_not_accessible",
      "The selected Account is no longer accessible. Reload Accounts and choose again.",
    ],
    [
      503,
      "local_delivery_not_active",
      "The validated local Gouda backend is not active. Start it with runlocal and try again.",
    ],
  ])("renders the safe %s %s API error", async (status, code, message) => {
    vi.stubGlobal(
      "fetch",
      vi
        .fn()
        .mockResolvedValueOnce(jsonResponse(accountsResponse))
        .mockResolvedValueOnce(jsonResponse({ code }, status)),
    );
    const user = userEvent.setup();

    render(<App />);
    await screen.findByLabelText("Report Account");
    fillDateRange("2026-05-01", "2026-04-30");
    await user.click(screen.getByRole("button", { name: "Load Movement report" }));

    expect(await screen.findByText(message)).toBeInTheDocument();
    expect(screen.queryByText(code)).not.toBeInTheDocument();
  });

  it("handles an unexpected successful response without exposing raw data", async () => {
    vi.stubGlobal(
      "fetch",
      vi
        .fn()
        .mockResolvedValueOnce(
          jsonResponse({ count: 1, accounts: [{ private: "SYNTHETIC_PRIVATE_RESPONSE" }] }),
        ),
    );

    render(<App />);

    expect(
      await screen.findByText("The local backend returned an unexpected response."),
    ).toBeInTheDocument();
    expect(screen.queryByText("SYNTHETIC_PRIVATE_RESPONSE")).not.toBeInTheDocument();
  });
});

describe("Gouda Santander import flow", () => {
  beforeEach(() => {
    clearFinancialImportCapability();
    vi.unstubAllGlobals();
  });

  it("renders no compatible import Accounts independently of report availability", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValueOnce(
        jsonResponse({ count: 1, accounts: [accountsResponse.accounts[1]] }),
      ),
    );
    render(<App />);

    expect(
      await screen.findByText("No compatible current Accounts are available for import."),
    ).toBeInTheDocument();
    expect(screen.queryByLabelText("Account")).not.toBeInTheDocument();
    expect(await screen.findByLabelText("Report Account")).toBeInTheDocument();
  });

  it("locks import controls and renders a static importing state", async () => {
    let releaseBootstrap!: (response: Response) => void;
    const pendingBootstrap = new Promise<Response>((resolve) => {
      releaseBootstrap = resolve;
    });
    const importResult = {
      account_id: PRIMARY_ACCOUNT_ID,
      batch_id: "22222222-2222-4222-8222-222222222222",
      status: "ACCEPTED",
      duplicate_of: null,
      created_movement_count: 2,
      statement: {
        status: "ACCEPTED",
        source_row_count: 8,
        parsed_count: 2,
        ignored_count: 6,
        rejected_count: 0,
        reconciliation_status: "RECONCILED",
        period_start: "2026-04-01",
        period_end: "2026-04-30",
      },
    };
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce(jsonResponse(accountsResponse))
      .mockReturnValueOnce(pendingBootstrap)
      .mockResolvedValueOnce(jsonResponse(importResult));
    vi.stubGlobal("fetch", fetchMock);
    const user = userEvent.setup();
    render(<App />);

    const account = await screen.findByLabelText("Account");
    const statement = screen.getByLabelText("Statement");
    await user.selectOptions(account, PRIMARY_ACCOUNT_ID);
    await user.upload(statement, new File(["synthetic"], "synthetic.xlsx"));
    await user.click(screen.getByRole("button", { name: "Import" }));

    expect(screen.getByText("Importing the selected statement…")).toBeInTheDocument();
    expect(account).toBeDisabled();
    expect(statement).toBeDisabled();
    expect(screen.getByRole("button", { name: "Importing…" })).toBeDisabled();

    releaseBootstrap(jsonResponse({ import_capability: "f".repeat(64) }));
    expect(await screen.findByRole("heading", { name: "Import complete" })).toBeInTheDocument();
  });

  it("requires explicit Account and file selection, then renders and navigates a truthful result", async () => {
    const importResult = {
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
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce(jsonResponse(accountsResponse))
      .mockResolvedValueOnce(jsonResponse({ import_capability: "a".repeat(64) }))
      .mockResolvedValueOnce(jsonResponse(importResult))
      .mockResolvedValueOnce(jsonResponse(movementReportResponse()));
    vi.stubGlobal("fetch", fetchMock);
    const user = userEvent.setup();
    render(<App />);

    const account = await screen.findByLabelText("Account");
    const importButton = screen.getByRole("button", { name: "Import" });
    expect(account).toHaveValue("");
    expect(importButton).toBeDisabled();
    await user.selectOptions(account, PRIMARY_ACCOUNT_ID);
    const file = new File(["synthetic"], "synthetic-private-statement.xlsx");
    await user.upload(screen.getByLabelText("Statement"), file);
    expect(fetchMock).toHaveBeenCalledTimes(1);
    expect(importButton).toBeEnabled();
    await user.click(importButton);
    expect(fetchMock).toHaveBeenCalledTimes(3);

    expect(
      await screen.findByRole("heading", { name: "Import completed with rejected records" }),
    ).toBeInTheDocument();
    expect(
      screen.getByText("Statement does not reconcile; valid movements were imported"),
    ).toBeInTheDocument();
    expect(screen.getByText("2 canonical Movements were created.")).toBeInTheDocument();
    expect(screen.queryByText("synthetic-private-statement.xlsx")).not.toBeInTheDocument();
    expect(screen.getByLabelText("Statement")).toHaveValue("");

    await user.click(screen.getByRole("button", { name: "View movements" }));
    expect(fetchMock).toHaveBeenLastCalledWith(
      `/api/v1/accounts/${PRIMARY_ACCOUNT_ID}/movements/?start_date=2026-04-01&end_date=2026-04-30`,
      { method: "GET", headers: { Accept: "application/json" } },
    );
    const reportHeading = await screen.findByRole("heading", { name: "Synthetic Daily Account" });
    await waitFor(() => expect(reportHeading).toHaveFocus());
    expect(screen.getByLabelText("Start date")).toHaveValue("2026-04-01");
    expect(screen.getByLabelText("End date")).toHaveValue("2026-04-30");
  });

  it("renders duplicate and known invalid outcomes without exposing private metadata", async () => {
    const duplicate = {
      account_id: PRIMARY_ACCOUNT_ID,
      batch_id: "22222222-2222-4222-8222-222222222222",
      status: "DUPLICATE",
      duplicate_of: "11111111-1111-4111-8111-111111111111",
      created_movement_count: 0,
      statement: {
        status: "ACCEPTED",
        source_row_count: 8,
        parsed_count: 2,
        ignored_count: 6,
        rejected_count: 0,
        reconciliation_status: "RECONCILED",
        period_start: "2026-04-01",
        period_end: "2026-04-30",
      },
    };
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce(jsonResponse(accountsResponse))
      .mockResolvedValueOnce(jsonResponse({ import_capability: "b".repeat(64) }))
      .mockResolvedValueOnce(jsonResponse(duplicate));
    vi.stubGlobal("fetch", fetchMock);
    const user = userEvent.setup();
    render(<App />);
    await user.selectOptions(await screen.findByLabelText("Account"), PRIMARY_ACCOUNT_ID);
    await user.upload(
      screen.getByLabelText("Statement"),
      new File(["synthetic"], "private-name.xlsx"),
    );
    await user.click(screen.getByRole("button", { name: "Import" }));
    expect(await screen.findByRole("heading", { name: "Statement already imported" })).toBeInTheDocument();
    expect(screen.getByText(/No new canonical Movements/)).toBeInTheDocument();
    for (const hidden of [duplicate.batch_id, duplicate.duplicate_of, "private-name.xlsx"]) {
      expect(screen.queryByText(hidden)).not.toBeInTheDocument();
    }
  });

  it("marks ambiguous network failure and never retries automatically", async () => {
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce(jsonResponse(accountsResponse))
      .mockResolvedValueOnce(jsonResponse({ import_capability: "c".repeat(64) }))
      .mockRejectedValueOnce(new Error("private network details"));
    vi.stubGlobal("fetch", fetchMock);
    const user = userEvent.setup();
    render(<App />);
    await user.selectOptions(await screen.findByLabelText("Account"), PRIMARY_ACCOUNT_ID);
    await user.upload(screen.getByLabelText("Statement"), new File(["x"], "private.xlsx"));
    await user.click(screen.getByRole("button", { name: "Import" }));
    expect(await screen.findByText(/The import outcome is uncertain/)).toBeInTheDocument();
    expect(screen.getByText(/Resubmit only by explicitly selecting/)).toBeInTheDocument();
    expect(fetchMock).toHaveBeenCalledTimes(3);
    expect(screen.queryByText("private network details")).not.toBeInTheDocument();
  });

  it.each(["NOT_RECONCILED", "INSUFFICIENT_DATA"])(
    "never labels an accepted %s statement a clean completion", async (reconciliation) => {
      vi.stubGlobal("fetch", vi.fn()
        .mockResolvedValueOnce(jsonResponse(accountsResponse))
        .mockResolvedValueOnce(jsonResponse({ import_capability: "a".repeat(64) }))
        .mockResolvedValueOnce(jsonResponse({
          account_id: PRIMARY_ACCOUNT_ID,
          batch_id: "22222222-2222-4222-8222-222222222222",
          status: "ACCEPTED", duplicate_of: null, created_movement_count: 2,
          statement: { status: "ACCEPTED", source_row_count: 8, parsed_count: 2,
            ignored_count: 6, rejected_count: 0, reconciliation_status: reconciliation,
            period_start: "2026-04-01", period_end: "2026-04-30" },
        })));
      const user = userEvent.setup();
      render(<App />);
      await user.selectOptions(await screen.findByLabelText("Account"), PRIMARY_ACCOUNT_ID);
      await user.upload(screen.getByLabelText("Statement"), new File(["x"], "synthetic.xlsx"));
      await user.click(screen.getByRole("button", { name: "Import" }));
      await screen.findByText("2 canonical Movements were created.");
      expect(screen.queryByRole("heading", { name: /^Import complete$/ })).not.toBeInTheDocument();
    },
  );

  it("cannot replace report selection while another report is in flight", async () => {
    let finishReport!: (response: Response) => void;
    const pendingReport = new Promise<Response>((resolve) => { finishReport = resolve; });
    const fetchMock = vi.fn().mockResolvedValueOnce(jsonResponse(accountsResponse))
      .mockResolvedValueOnce(jsonResponse({ import_capability: "a".repeat(64) }))
      .mockResolvedValueOnce(jsonResponse({ account_id: PRIMARY_ACCOUNT_ID,
        batch_id: "22222222-2222-4222-8222-222222222222", status: "ACCEPTED",
        duplicate_of: null, created_movement_count: 2,
        statement: { status: "ACCEPTED", source_row_count: 8, parsed_count: 2,
          ignored_count: 6, rejected_count: 0, reconciliation_status: "RECONCILED",
          period_start: "2026-04-01", period_end: "2026-04-30" } }))
      .mockReturnValueOnce(pendingReport);
    vi.stubGlobal("fetch", fetchMock);
    const user = userEvent.setup();
    render(<App />);
    await user.selectOptions(await screen.findByLabelText("Account"), PRIMARY_ACCOUNT_ID);
    await user.upload(screen.getByLabelText("Statement"), new File(["x"], "synthetic.xlsx"));
    await user.click(screen.getByRole("button", { name: "Import" }));
    await screen.findByRole("heading", { name: "Import complete" });
    fillDateRange("2026-04-01", "2026-04-30");
    await user.click(screen.getByRole("button", { name: "Load Movement report" }));
    expect(screen.getByRole("button", { name: "View movements" })).toBeDisabled();
    finishReport(jsonResponse(movementReportResponse()));
    await screen.findByRole("heading", { name: "Synthetic Daily Account" });
  });

  it.each([
    [
      "xlsx_invalid",
      422,
      "The selected file is not a readable, unencrypted XLSX workbook.",
      false,
    ],
    [
      "account_not_accessible",
      404,
      "The selected Account is no longer accessible. Reload Accounts and choose again.",
      false,
    ],
    [
      "account_source_incompatible",
      409,
      "The selected Account is not compatible with Santander current-account statements.",
      false,
    ],
    [
      "financial_import_not_enabled",
      403,
      "Financial imports are disabled. Start the separate private Gouda stack to import a statement.",
      true,
    ],
  ])("renders the safe import failure %s", async (code, status, message, bootstrapFailure) => {
    const fetchMock = vi.fn().mockResolvedValueOnce(jsonResponse(accountsResponse));
    if (bootstrapFailure) {
      fetchMock.mockResolvedValueOnce(jsonResponse({ code }, status));
    } else {
      fetchMock
        .mockResolvedValueOnce(jsonResponse({ import_capability: "d".repeat(64) }))
        .mockResolvedValueOnce(jsonResponse({ code }, status));
    }
    vi.stubGlobal("fetch", fetchMock);
    const user = userEvent.setup();
    render(<App />);

    await user.selectOptions(await screen.findByLabelText("Account"), PRIMARY_ACCOUNT_ID);
    await user.upload(screen.getByLabelText("Statement"), new File(["x"], "private.xlsx"));
    await user.click(screen.getByRole("button", { name: "Import" }));

    expect(await screen.findByText(message)).toBeInTheDocument();
    expect(screen.queryByText(code)).not.toBeInTheDocument();
    expect(screen.queryByText("private.xlsx")).not.toBeInTheDocument();
  });
});

function fillDateRange(startDate: string, endDate: string) {
  fireEvent.change(screen.getByLabelText("Start date"), {
    target: { value: startDate },
  });
  fireEvent.change(screen.getByLabelText("End date"), {
    target: { value: endDate },
  });
}
