import { fireEvent, render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { App } from "./App";
import {
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

    expect(await screen.findByText("1234567890123456.77")).toBeInTheDocument();
    expect(screen.getByText("1234567890123456.78")).toBeInTheDocument();
    expect(screen.getByText("-0.01")).toBeInTheDocument();
    const summary = screen.getByText("Movement count").closest("div");
    expect(summary).not.toBeNull();
    expect(within(summary!).getByText("2")).toBeInTheDocument();

    const rows = screen.getAllByRole("row").slice(1);
    expect(within(rows[0]).getByText("Synthetic returned first")).toBeInTheDocument();
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
    expect(screen.getByText("0.00")).toBeInTheDocument();
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
