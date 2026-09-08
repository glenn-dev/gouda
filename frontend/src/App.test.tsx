import { fireEvent, render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { App } from "./App";
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
    const selector = await screen.findByLabelText("Account");
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
    expect(screen.queryByLabelText("Account")).not.toBeInTheDocument();
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
    const selector = await screen.findByLabelText("Account");
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
    await screen.findByLabelText("Account");
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
    await screen.findByLabelText("Account");
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
    await screen.findByLabelText("Account");
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
    await screen.findByLabelText("Account");
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

function fillDateRange(startDate: string, endDate: string) {
  fireEvent.change(screen.getByLabelText("Start date"), {
    target: { value: startDate },
  });
  fireEvent.change(screen.getByLabelText("End date"), {
    target: { value: endDate },
  });
}
