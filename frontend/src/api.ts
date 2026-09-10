export type AccountKind = "CURRENT" | "CREDIT_CARD";

export type AccountSummary = Readonly<{
  id: string;
  display_name: string;
  kind: AccountKind;
  currency: string;
}>;

export type MovementCategory = Readonly<{
  id: string;
  display_name: string;
  is_active: boolean;
}>;

export type MovementClassification =
  | Readonly<{
      state: "NEVER_ASSIGNED";
      category: null;
      revision: 0;
    }>
  | Readonly<{
      state: "CLASSIFIED";
      category: MovementCategory;
      revision: number;
    }>
  | Readonly<{
      state: "CLEARED";
      category: null;
      revision: number;
    }>;

export type MovementReportItem = Readonly<{
  movement_id: string;
  account_id: string;
  occurrence_date: string;
  signed_amount: string;
  currency: string;
  description: string | null;
  classification: MovementClassification;
}>;

export type MovementReport = Readonly<{
  account_id: string;
  start_date: string;
  end_date: string;
  movement_count: number;
  net_signed_amount: string;
  movements: ReadonlyArray<MovementReportItem>;
}>;

export type SantanderImportStatementResult = Readonly<{
  status: "ACCEPTED" | "PARTIAL" | "REJECTED";
  source_row_count: number;
  parsed_count: number;
  ignored_count: number;
  rejected_count: number;
  reconciliation_status:
    | "RECONCILED"
    | "NOT_RECONCILED"
    | "INSUFFICIENT_DATA"
    | "NOT_APPLICABLE";
  period_start: string;
  period_end: string;
}>;

export type SantanderImportResult = Readonly<{
  account_id: string;
  batch_id: string;
  status: "ACCEPTED" | "PARTIAL" | "REJECTED" | "DUPLICATE";
  duplicate_of: string | null;
  created_movement_count: number;
  statement: SantanderImportStatementResult;
}>;

export class ApiError extends Error {
  readonly code: string;
  readonly status: number | null;

  constructor(message: string, code: string, status: number | null = null) {
    super(message);
    this.name = "ApiError";
    this.code = code;
    this.status = status;
  }
}

export class FinancialImportError extends ApiError {
  readonly outcomeUncertain: boolean;

  constructor(message: string, code: string, status: number | null, outcomeUncertain: boolean) {
    super(message, code, status);
    this.name = "FinancialImportError";
    this.outcomeUncertain = outcomeUncertain;
  }
}

let financialImportCapability: string | null = null;

/** Discard page-memory authority without exposing it. Primarily models page restart in tests. */
export function clearFinancialImportCapability(): void {
  financialImportCapability = null;
}

const GET_OPTIONS = Object.freeze({
  method: "GET",
  headers: Object.freeze({ Accept: "application/json" }),
});

const UUID_PATTERN =
  /^[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/;
const ISO_DATE_PATTERN = /^[0-9]{4}-[0-9]{2}-[0-9]{2}$/;
const DECIMAL_PATTERN = /^-?(?:0|[1-9][0-9]*)\.[0-9]{2}$/;
const CURRENCY_PATTERN = /^[A-Z]{3}$/;
const CONTROL_CHARACTER_PATTERN = /\p{Cc}/u;

const ERROR_MESSAGES: Readonly<Record<string, string>> = Object.freeze({
  local_delivery_not_active:
    "The validated local Gouda backend is not active. Start it with runlocal and try again.",
  principal_context_invalid:
    "The local backend rejected its trusted principal context.",
  account_not_accessible:
    "The selected Account is no longer accessible. Reload Accounts and choose again.",
  account_selector_invalid:
    "The selected Account identifier was rejected by the backend.",
  start_date_invalid: "The backend rejected the start date. Check the date and try again.",
  end_date_invalid: "The backend rejected the end date. Check the date and try again.",
  date_range_invalid:
    "The backend rejected the date range. The start date must not be after the end date.",
  not_acceptable: "The backend could not provide the required JSON response.",
  method_not_allowed: "The backend rejected this read request.",
  financial_import_not_enabled:
    "Financial imports are disabled. Start the separate private Gouda stack to import a statement.",
  host_not_allowed: "The local financial-import boundary rejected the browser Host.",
  origin_not_allowed: "The local financial-import boundary rejected the browser Origin.",
  import_capability_invalid:
    "The financial-import permission expired. Select Import again to obtain a fresh permission.",
  account_source_incompatible:
    "The selected Account is not compatible with Santander current-account statements.",
  statement_missing: "Choose one non-empty Santander current-account XLSX statement.",
  request_body_too_large: "The upload exceeds the allowed request size.",
  statement_too_large: "The statement exceeds the 5 MiB file limit.",
  import_busy: "Another import is in progress. Wait for it to finish, then try again.",
  statement_resource_limit: "The workbook exceeds Gouda’s safe XLSX resource limits.",
  xlsx_invalid: "The selected file is not a readable, unencrypted XLSX workbook.",
  source_unrecognized: "This workbook is not a supported Santander current-account statement.",
  statement_not_importable: "The Santander statement could not be imported safely.",
  account_context_changed: "The selected Account changed while the statement was being imported.",
  source_kind_conflict: "These exact bytes were already imported through another source route.",
  import_persistence_failed: "Gouda could not safely persist the import.",
});

export async function importSantanderCurrentAccountXlsx(
  accountId: string,
  statement: File,
): Promise<SantanderImportResult> {
  if (!isUuid(accountId) || !(statement instanceof File)) {
    throw new FinancialImportError(
      "Choose a compatible Account and one statement.",
      "request_invalid",
      null,
      false,
    );
  }
  if (financialImportCapability === null) {
    financialImportCapability = await bootstrapFinancialImportCapability();
  }

  const body = new FormData();
  body.append("statement", statement);
  let response: Response;
  try {
    response = await fetch(
      `/api/v1/accounts/${encodeURIComponent(accountId)}/imports/santander-current-account-xlsx/`,
      {
        method: "POST",
        headers: {
          Accept: "application/json",
          "X-Gouda-Financial-Import": financialImportCapability,
        },
        body,
        mode: "same-origin",
        cache: "no-store",
        credentials: "omit",
        redirect: "error",
      },
    );
  } catch {
    throw uncertainImportError();
  }

  let responseBody: unknown;
  try {
    responseBody = await response.json();
  } catch {
    throw response.status >= 500
      ? uncertainImportError(response.status)
      : new FinancialImportError(
          "The local backend returned an unreadable import response.",
          "unexpected_response",
          response.status,
          response.ok,
        );
  }
  if (!response.ok) {
    const error = apiResponseError(response.status, responseBody);
    if (error.code === "import_capability_invalid") {
      financialImportCapability = null;
    }
    throw new FinancialImportError(
      error.message,
      error.code,
      error.status,
      response.status >= 500,
    );
  }
  try {
    return parseSantanderImportResult(responseBody, accountId);
  } catch {
    throw uncertainImportError(response.status);
  }
}

async function bootstrapFinancialImportCapability(): Promise<string> {
  let response: Response;
  try {
    response = await fetch("/api/v1/local/financial-import-capability/", {
      method: "POST",
      headers: { Accept: "application/json", "Content-Type": "application/json" },
      body: "{}",
      mode: "same-origin",
      cache: "no-store",
      credentials: "omit",
      redirect: "error",
    });
  } catch {
    throw new FinancialImportError(
      "Cannot reach the private local Gouda import service.",
      "backend_unavailable",
      null,
      false,
    );
  }
  let body: unknown;
  try {
    body = await response.json();
  } catch {
    throw new FinancialImportError(
      "The local backend returned an unreadable capability response.",
      "unexpected_response",
      response.status,
      false,
    );
  }
  if (!response.ok) {
    const error = apiResponseError(response.status, body);
    throw new FinancialImportError(error.message, error.code, error.status, false);
  }
  if (
    !isRecord(body) ||
    !hasExactKeys(body, ["import_capability"]) ||
    typeof body.import_capability !== "string" ||
    !/^[0-9a-f]{64}$/.test(body.import_capability)
  ) {
    throw new FinancialImportError(
      "The local backend returned an invalid capability response.",
      "unexpected_response",
      response.status,
      false,
    );
  }
  return body.import_capability;
}

export async function fetchAccounts(): Promise<ReadonlyArray<AccountSummary>> {
  const response = await performGet("/api/v1/accounts/");
  const body = await readJson(response);
  if (!response.ok) {
    throw apiResponseError(response.status, body);
  }
  return parseAccounts(body);
}

export async function fetchMovementReport(
  accountId: string,
  startDate: string,
  endDate: string,
): Promise<MovementReport> {
  if (!isUuid(accountId) || !isIsoDate(startDate) || !isIsoDate(endDate)) {
    throw unexpectedResponse("The report request contained an invalid selector or date.");
  }

  const query = new URLSearchParams({
    start_date: startDate,
    end_date: endDate,
  });
  const response = await performGet(
    `/api/v1/accounts/${encodeURIComponent(accountId)}/movements/?${query.toString()}`,
  );
  const body = await readJson(response);
  if (!response.ok) {
    throw apiResponseError(response.status, body);
  }
  return parseMovementReport(body, accountId, startDate, endDate);
}

async function performGet(url: string): Promise<Response> {
  try {
    return await fetch(url, GET_OPTIONS);
  } catch {
    throw backendUnavailable();
  }
}

async function readJson(response: Response): Promise<unknown> {
  try {
    return await response.json();
  } catch {
    if (!response.ok) {
      if (response.status >= 500) {
        throw backendUnavailable(response.status);
      }
      throw new ApiError(
        "The local backend returned an unreadable error response.",
        "unexpected_response",
        response.status,
      );
    }
    throw unexpectedResponse();
  }
}

function apiResponseError(status: number, body: unknown): ApiError {
  const code = isRecord(body) && typeof body.code === "string" ? body.code : "unexpected_response";
  if (code === "unexpected_response" && status >= 500) {
    return backendUnavailable(status);
  }
  const message =
    ERROR_MESSAGES[code] ?? "The local backend returned an unexpected error response.";
  return new ApiError(message, code, status);
}

function parseAccounts(body: unknown): ReadonlyArray<AccountSummary> {
  if (!isRecord(body) || !Number.isInteger(body.count) || !Array.isArray(body.accounts)) {
    throw unexpectedResponse();
  }

  const accounts = body.accounts.map(parseAccount);
  if (body.count !== accounts.length) {
    throw unexpectedResponse();
  }
  return Object.freeze(accounts);
}

function parseAccount(value: unknown): AccountSummary {
  if (
    !isRecord(value) ||
    !isUuid(value.id) ||
    typeof value.display_name !== "string" ||
    (value.kind !== "CURRENT" && value.kind !== "CREDIT_CARD") ||
    typeof value.currency !== "string" ||
    !CURRENCY_PATTERN.test(value.currency)
  ) {
    throw unexpectedResponse();
  }
  return Object.freeze({
    id: value.id,
    display_name: value.display_name,
    kind: value.kind,
    currency: value.currency,
  });
}

function parseMovementReport(
  body: unknown,
  requestedAccountId: string,
  requestedStartDate: string,
  requestedEndDate: string,
): MovementReport {
  if (
    !isRecord(body) ||
    body.account_id !== requestedAccountId ||
    body.start_date !== requestedStartDate ||
    body.end_date !== requestedEndDate ||
    !Number.isInteger(body.movement_count) ||
    !isDecimal(body.net_signed_amount) ||
    !Array.isArray(body.movements)
  ) {
    throw unexpectedResponse();
  }

  const movements = body.movements.map((movement) =>
    parseMovement(movement, requestedAccountId),
  );
  if (body.movement_count !== movements.length) {
    throw unexpectedResponse();
  }

  return Object.freeze({
    account_id: body.account_id,
    start_date: body.start_date,
    end_date: body.end_date,
    movement_count: body.movement_count,
    net_signed_amount: body.net_signed_amount,
    movements: Object.freeze(movements),
  });
}

function parseSantanderImportResult(body: unknown, requestedAccountId: string): SantanderImportResult {
  if (
    !isRecord(body) ||
    !hasExactKeys(body, [
      "account_id",
      "batch_id",
      "status",
      "duplicate_of",
      "created_movement_count",
      "statement",
    ]) ||
    body.account_id !== requestedAccountId ||
    !isUuid(body.batch_id) ||
    !["ACCEPTED", "PARTIAL", "REJECTED", "DUPLICATE"].includes(String(body.status)) ||
    (body.duplicate_of !== null && !isUuid(body.duplicate_of)) ||
    !isNonnegativeInteger(body.created_movement_count)
  ) {
    throw unexpectedResponse();
  }
  const statement = parseSantanderStatementResult(body.statement);
  if (
    (body.status === "DUPLICATE") !== (body.duplicate_of !== null) ||
    (body.status === "DUPLICATE" && body.created_movement_count !== 0) ||
    (body.status !== "DUPLICATE" && body.status !== statement.status)
  ) {
    throw unexpectedResponse();
  }
  return Object.freeze({
    account_id: body.account_id,
    batch_id: body.batch_id,
    status: body.status as SantanderImportResult["status"],
    duplicate_of: body.duplicate_of,
    created_movement_count: body.created_movement_count,
    statement,
  });
}

function parseSantanderStatementResult(value: unknown): SantanderImportStatementResult {
  if (
    !isRecord(value) ||
    !hasExactKeys(value, [
      "status",
      "source_row_count",
      "parsed_count",
      "ignored_count",
      "rejected_count",
      "reconciliation_status",
      "period_start",
      "period_end",
    ]) ||
    !["ACCEPTED", "PARTIAL", "REJECTED"].includes(String(value.status)) ||
    !isNonnegativeInteger(value.source_row_count) ||
    !isNonnegativeInteger(value.parsed_count) ||
    !isNonnegativeInteger(value.ignored_count) ||
    !isNonnegativeInteger(value.rejected_count) ||
    ![
      "RECONCILED",
      "NOT_RECONCILED",
      "INSUFFICIENT_DATA",
      "NOT_APPLICABLE",
    ].includes(String(value.reconciliation_status)) ||
    !isIsoDate(value.period_start) ||
    !isIsoDate(value.period_end)
  ) {
    throw unexpectedResponse();
  }
  return Object.freeze({
    status: value.status as SantanderImportStatementResult["status"],
    source_row_count: value.source_row_count,
    parsed_count: value.parsed_count,
    ignored_count: value.ignored_count,
    rejected_count: value.rejected_count,
    reconciliation_status:
      value.reconciliation_status as SantanderImportStatementResult["reconciliation_status"],
    period_start: value.period_start,
    period_end: value.period_end,
  });
}

function parseMovement(value: unknown, requestedAccountId: string): MovementReportItem {
  if (
    !isRecord(value) ||
    !isUuid(value.movement_id) ||
    value.account_id !== requestedAccountId ||
    !isIsoDate(value.occurrence_date) ||
    !isDecimal(value.signed_amount) ||
    typeof value.currency !== "string" ||
    !CURRENCY_PATTERN.test(value.currency) ||
    (value.description !== null && typeof value.description !== "string")
  ) {
    throw unexpectedResponse();
  }
  const classification = parseMovementClassification(value.classification);

  return Object.freeze({
    movement_id: value.movement_id,
    account_id: value.account_id,
    occurrence_date: value.occurrence_date,
    signed_amount: value.signed_amount,
    currency: value.currency,
    description: value.description,
    classification,
  });
}

function parseMovementClassification(value: unknown): MovementClassification {
  if (
    !isRecord(value) ||
    !hasExactKeys(value, ["state", "category", "revision"]) ||
    !Number.isSafeInteger(value.revision)
  ) {
    throw unexpectedResponse();
  }

  if (value.state === "NEVER_ASSIGNED") {
    if (value.category !== null || value.revision !== 0) {
      throw unexpectedResponse();
    }
    return Object.freeze({ state: value.state, category: null, revision: 0 });
  }

  if (value.state === "CLEARED") {
    if (value.category !== null || typeof value.revision !== "number" || value.revision <= 0) {
      throw unexpectedResponse();
    }
    return Object.freeze({ state: value.state, category: null, revision: value.revision });
  }

  if (value.state === "CLASSIFIED") {
    if (typeof value.revision !== "number" || value.revision <= 0) {
      throw unexpectedResponse();
    }
    return Object.freeze({
      state: value.state,
      category: parseMovementCategory(value.category),
      revision: value.revision,
    });
  }

  throw unexpectedResponse();
}

function parseMovementCategory(value: unknown): MovementCategory {
  if (
    !isRecord(value) ||
    !hasExactKeys(value, ["id", "display_name", "is_active"]) ||
    !isUuid(value.id) ||
    !isCategoryDisplayName(value.display_name) ||
    typeof value.is_active !== "boolean"
  ) {
    throw unexpectedResponse();
  }
  return Object.freeze({
    id: value.id,
    display_name: value.display_name,
    is_active: value.is_active,
  });
}

function isCategoryDisplayName(value: unknown): value is string {
  return (
    typeof value === "string" &&
    value.length > 0 &&
    [...value].length <= 80 &&
    value.normalize("NFC") === value &&
    value.trim() === value &&
    !CONTROL_CHARACTER_PATTERN.test(value)
  );
}

function hasExactKeys(value: Record<string, unknown>, keys: ReadonlyArray<string>): boolean {
  const actual = Object.keys(value);
  return actual.length === keys.length && keys.every((key) => actual.includes(key));
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function isUuid(value: unknown): value is string {
  return typeof value === "string" && UUID_PATTERN.test(value);
}

function isIsoDate(value: unknown): value is string {
  if (typeof value !== "string" || !ISO_DATE_PATTERN.test(value)) {
    return false;
  }
  const [year, month, day] = value.split("-").map(Number);
  const parsed = new Date(Date.UTC(year, month - 1, day));
  return (
    parsed.getUTCFullYear() === year &&
    parsed.getUTCMonth() === month - 1 &&
    parsed.getUTCDate() === day
  );
}

function isDecimal(value: unknown): value is string {
  return typeof value === "string" && DECIMAL_PATTERN.test(value);
}

function isNonnegativeInteger(value: unknown): value is number {
  return Number.isSafeInteger(value) && typeof value === "number" && value >= 0;
}

function unexpectedResponse(
  message = "The local backend returned an unexpected response.",
): ApiError {
  return new ApiError(message, "unexpected_response");
}

function backendUnavailable(status: number | null = null): ApiError {
  return new ApiError(
    "Cannot reach the local Gouda backend. Confirm both local services are running and try again.",
    "backend_unavailable",
    status,
  );
}

function uncertainImportError(status: number | null = null): FinancialImportError {
  return new FinancialImportError(
    "The import outcome is uncertain. Gouda may already have committed it. Do not assume it failed; inspect Movements or explicitly retry the same unchanged file.",
    "import_outcome_uncertain",
    status,
    true,
  );
}
