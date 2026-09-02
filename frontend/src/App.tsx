import { FormEvent, useCallback, useEffect, useMemo, useState } from "react";

import {
  AccountKind,
  AccountSummary,
  ApiError,
  fetchAccounts,
  fetchMovementReport,
  MovementReport,
} from "./api";

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
    <main className="page-shell">
      <header className="page-header">
        <p className="eyebrow">Local read-only client</p>
        <h1>Gouda Movement report</h1>
        <p className="intro">
          Choose an accessible Account and request canonical Movements for an inclusive date
          range.
        </p>
      </header>

      <section className="panel" aria-labelledby="report-controls-heading">
        <h2 id="report-controls-heading">Report selection</h2>

        {accountsState.status === "loading" && (
          <p className="status-message" role="status">
            Loading accessible Accounts…
          </p>
        )}

        {accountsState.status === "error" && (
          <div className="status-message error-message" role="alert">
            <p>{accountsState.message}</p>
            <button className="secondary-button" type="button" onClick={() => void loadAccounts()}>
              Retry Account discovery
            </button>
          </div>
        )}

        {accountsState.status === "ready" && accounts.length === 0 && (
          <p className="status-message" role="status">
            No accessible Accounts are available.
          </p>
        )}

        {accountsState.status === "ready" && accounts.length > 0 && (
          <form className="report-form" onSubmit={handleReportSubmit}>
            <div className="field field-wide">
              <label htmlFor="account">Account</label>
              <select
                id="account"
                value={selectedAccountId}
                disabled={reportState.status === "loading"}
                onChange={(event) => handleAccountChange(event.target.value)}
              >
                {accounts.map((account) => (
                  <option key={account.id} value={account.id}>
                    {account.display_name} — {kindLabel(account.kind)} — {account.currency}
                  </option>
                ))}
              </select>
            </div>

            <div className="field">
              <label htmlFor="start-date">Start date</label>
              <input
                id="start-date"
                type="date"
                value={startDate}
                disabled={reportState.status === "loading"}
                onChange={(event) => {
                  setStartDate(event.target.value);
                  setReportState({ status: "idle" });
                }}
              />
            </div>

            <div className="field">
              <label htmlFor="end-date">End date</label>
              <input
                id="end-date"
                type="date"
                value={endDate}
                disabled={reportState.status === "loading"}
                onChange={(event) => {
                  setEndDate(event.target.value);
                  setReportState({ status: "idle" });
                }}
              />
            </div>

            <button className="primary-button" type="submit" disabled={!canRequestReport}>
              {reportState.status === "loading" ? "Loading report…" : "Load Movement report"}
            </button>
          </form>
        )}
      </section>

      {reportState.status === "idle" && selectedAccount !== null && (
        <p className="report-placeholder" role="status">
          Select both dates, then load the report.
        </p>
      )}

      {reportState.status === "loading" && (
        <p className="report-placeholder" role="status">
          Loading canonical Movements…
        </p>
      )}

      {reportState.status === "error" && (
        <p className="status-message error-message" role="alert">
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
    <section className="panel report-panel" aria-labelledby="movement-report-heading">
      <div className="report-heading-row">
        <div>
          <p className="eyebrow">Canonical report</p>
          <h2 id="movement-report-heading">{account.display_name}</h2>
          <p className="account-context">
            {kindLabel(account.kind)} · {account.currency} · {report.start_date} through{" "}
            {report.end_date}
          </p>
        </div>
        <dl className="report-summary">
          <div>
            <dt>Movement count</dt>
            <dd>{report.movement_count}</dd>
          </div>
          <div>
            <dt>Net signed amount</dt>
            <dd className="exact-money">{report.net_signed_amount}</dd>
          </div>
        </dl>
      </div>

      <p className="sign-note">
        Amounts retain Gouda&apos;s canonical signed account-effect convention and exact decimal
        strings.
      </p>

      {report.movements.length === 0 ? (
        <p className="status-message">No canonical Movements were found for this date range.</p>
      ) : (
        <div className="table-scroll">
          <table>
            <caption className="visually-hidden">Canonical Movements in backend order</caption>
            <thead>
              <tr>
                <th scope="col">Date</th>
                <th scope="col">Description</th>
                <th scope="col" className="numeric-column">
                  Signed amount
                </th>
                <th scope="col">Currency</th>
              </tr>
            </thead>
            <tbody>
              {report.movements.map((movement) => (
                <tr key={movement.movement_id}>
                  <td>{movement.occurrence_date}</td>
                  <td>{movement.description ?? "No description"}</td>
                  <td className="numeric-column exact-money">{movement.signed_amount}</td>
                  <td>{movement.currency}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
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
