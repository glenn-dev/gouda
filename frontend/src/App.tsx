import { FormEvent, useCallback, useEffect, useMemo, useState } from "react";

import {
  AccountKind,
  AccountSummary,
  ApiError,
  fetchAccounts,
  fetchMovementReport,
  MovementReport,
} from "@/api";
import { MoneyAmount } from "@/components/gouda/MoneyAmount";
import { MovementList } from "@/components/movements/MovementList";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { NativeSelect, NativeSelectOption } from "@/components/ui/native-select";

type AccountsState =
  | { status: "loading" }
  | { status: "error"; message: string }
  | { status: "ready"; accounts: ReadonlyArray<AccountSummary> };

type ReportState =
  | { status: "idle" }
  | { status: "loading" }
  | { status: "error"; message: string }
  | { status: "success"; report: MovementReport };

export function App() {
  const [accountsState, setAccountsState] = useState<AccountsState>({ status: "loading" });
  const [selectedAccountId, setSelectedAccountId] = useState("");
  const [startDate, setStartDate] = useState("");
  const [endDate, setEndDate] = useState("");
  const [reportState, setReportState] = useState<ReportState>({ status: "idle" });

  const loadAccounts = useCallback(async () => {
    setAccountsState({ status: "loading" });
    setSelectedAccountId("");
    setReportState({ status: "idle" });
    try {
      const accounts = await fetchAccounts();
      setAccountsState({ status: "ready", accounts });
      setSelectedAccountId(accounts[0]?.id ?? "");
    } catch (error) {
      setAccountsState({ status: "error", message: errorMessage(error) });
    }
  }, []);

  useEffect(() => {
    void loadAccounts();
  }, [loadAccounts]);

  const accounts = accountsState.status === "ready" ? accountsState.accounts : [];
  const selectedAccount = useMemo(
    () => accounts.find((account) => account.id === selectedAccountId) ?? null,
    [accounts, selectedAccountId],
  );
  const canRequestReport =
    selectedAccount !== null &&
    startDate !== "" &&
    endDate !== "" &&
    reportState.status !== "loading";

  async function handleReportSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!canRequestReport || selectedAccount === null) {
      return;
    }

    setReportState({ status: "loading" });
    try {
      const report = await fetchMovementReport(selectedAccount.id, startDate, endDate);
      setReportState({ status: "success", report });
    } catch (error) {
      setReportState({ status: "error", message: errorMessage(error) });
    }
  }

  function handleAccountChange(accountId: string) {
    setSelectedAccountId(accountId);
    setReportState({ status: "idle" });
  }

  return (
    <main className="mx-auto w-full max-w-5xl px-4 py-6 md:px-8 md:py-8">
      <header className="border-b border-border pb-6">
        <p className="text-sm font-medium text-muted-foreground">Gouda</p>
        <h1 className="mt-2 text-2xl font-semibold leading-tight tracking-tight text-foreground md:text-3xl">
          Movements
        </h1>
      </header>

      <section className="py-6" aria-labelledby="report-controls-heading">
        <h2 id="report-controls-heading" className="text-lg font-semibold text-foreground">
          Report selection
        </h2>

        {accountsState.status === "loading" && (
          <p className="mt-4 text-sm text-muted-foreground" role="status">
            Loading accessible Accounts…
          </p>
        )}

        {accountsState.status === "error" && (
          <div className="mt-4 space-y-3 border-l-2 border-error pl-4 text-error" role="alert">
            <p>{accountsState.message}</p>
            <Button type="button" variant="outline" onClick={() => void loadAccounts()}>
              Retry Account discovery
            </Button>
          </div>
        )}

        {accountsState.status === "ready" && accounts.length === 0 && (
          <p className="mt-4 bg-muted px-4 py-3 text-sm text-muted-foreground" role="status">
            No accessible Accounts are available.
          </p>
        )}

        {accountsState.status === "ready" && accounts.length > 0 && (
          <form
            className="mt-4 grid gap-4 md:grid-cols-2 lg:grid-cols-[minmax(0,2fr)_minmax(9rem,1fr)_minmax(9rem,1fr)_auto] lg:items-start"
            onSubmit={handleReportSubmit}
          >
            <div className="min-w-0 space-y-2 md:col-span-2 lg:col-span-1">
              <Label htmlFor="account">Account</Label>
              <NativeSelect
                id="account"
                aria-describedby="selected-account-context"
                value={selectedAccountId}
                disabled={reportState.status === "loading"}
                onChange={(event) => handleAccountChange(event.target.value)}
              >
                {accounts.map((account) => (
                  <NativeSelectOption key={account.id} value={account.id}>
                    {account.display_name} — {kindLabel(account.kind)} — {account.currency}
                  </NativeSelectOption>
                ))}
              </NativeSelect>
              <p id="selected-account-context" className="text-sm leading-normal text-muted-foreground">
                {selectedAccount?.display_name} · {selectedAccount && kindLabel(selectedAccount.kind)} ·{" "}
                {selectedAccount?.currency}
              </p>
            </div>

            <div className="min-w-0 space-y-2">
              <Label htmlFor="start-date">Start date</Label>
              <Input
                id="start-date"
                type="date"
                required
                value={startDate}
                disabled={reportState.status === "loading"}
                onChange={(event) => {
                  setStartDate(event.target.value);
                  setReportState({ status: "idle" });
                }}
              />
            </div>

            <div className="min-w-0 space-y-2">
              <Label htmlFor="end-date">End date</Label>
              <Input
                id="end-date"
                type="date"
                required
                value={endDate}
                disabled={reportState.status === "loading"}
                onChange={(event) => {
                  setEndDate(event.target.value);
                  setReportState({ status: "idle" });
                }}
              />
            </div>

            <Button
              className="w-full md:col-span-2 lg:col-span-1 lg:mt-6 lg:w-auto"
              type="submit"
              disabled={!canRequestReport}
            >
              {reportState.status === "loading" ? "Loading report…" : "Load Movement report"}
            </Button>
          </form>
        )}
      </section>

      {reportState.status === "idle" && selectedAccount !== null && (
        <p className="border-t border-border py-4 text-sm text-muted-foreground" role="status">
          Select both dates, then load the report.
        </p>
      )}

      {reportState.status === "loading" && (
        <p className="border-t border-border py-4 text-sm text-muted-foreground" role="status">
          Loading canonical Movements…
        </p>
      )}

      {reportState.status === "error" && (
        <p className="border-l-2 border-error py-2 pl-4 text-error" role="alert">
          {reportState.message}
        </p>
      )}

      {reportState.status === "success" && selectedAccount !== null && (
        <ReportResult account={selectedAccount} report={reportState.report} />
      )}
    </main>
  );
}

function ReportResult({ account, report }: { account: AccountSummary; report: MovementReport }) {
  return (
    <section className="border-t border-border pt-6" aria-labelledby="movement-report-heading">
      <p className="sr-only" role="status">
        Movement report loaded.
      </p>
      <div className="grid gap-6 md:grid-cols-[minmax(0,1fr)_auto] md:items-start">
        <div className="min-w-0">
          <h2 id="movement-report-heading" className="text-lg font-semibold text-foreground">
            {account.display_name}
          </h2>
          <p className="mt-1 text-sm leading-normal text-muted-foreground">
            {kindLabel(account.kind)} · {account.currency} · {report.start_date} through{" "}
            {report.end_date}
          </p>
        </div>
        <dl className="grid gap-4 sm:grid-cols-[auto_auto] sm:gap-8 md:text-right">
          <div>
            <dt className="text-sm text-muted-foreground">Net account effect</dt>
            <dd className="mt-1 max-w-full overflow-x-auto text-2xl font-semibold leading-tight md:overflow-visible">
              <MoneyAmount
                amount={report.net_signed_amount}
                currency={account.currency}
                className="font-semibold"
              />
            </dd>
          </div>
          <div>
            <dt className="text-sm text-muted-foreground">Movement count</dt>
            <dd className="mt-1 text-base font-medium tabular-nums text-foreground">
              {report.movement_count}
            </dd>
          </div>
        </dl>
      </div>

      <p className="mt-4 max-w-3xl text-sm leading-normal text-muted-foreground">
        Positive increases this Account&apos;s contribution to household net worth; negative
        decreases it.
      </p>

      <div className="mt-6">
        {report.movements.length === 0 ? (
          <p className="bg-muted px-4 py-3 text-sm text-muted-foreground">
            No canonical Movements were found for this date range.
          </p>
        ) : (
          <MovementList movements={report.movements} />
        )}
      </div>
    </section>
  );
}

function kindLabel(kind: AccountKind): string {
  return kind === "CURRENT" ? "Current account" : "Credit card";
}

function errorMessage(error: unknown): string {
  if (error instanceof ApiError) {
    return error.message;
  }
  return "The local client encountered an unexpected error. Try again.";
}
