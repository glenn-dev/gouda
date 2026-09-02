export type AccountKind = "CURRENT" | "CREDIT_CARD";

export type AccountSummary = Readonly<{
  id: string;
  display_name: string;
  kind: AccountKind;
  currency: string;
}>;

export type MovementReportItem = Readonly<{
  movement_id: string;
  account_id: string;
  occurrence_date: string;
  signed_amount: string;
  currency: string;
  description: string | null;
}>;

export type MovementReport = Readonly<{
  account_id: string;
  start_date: string;
  end_date: string;
  movement_count: number;
  net_signed_amount: string;
  movements: ReadonlyArray<MovementReportItem>;
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

const GET_OPTIONS = Object.freeze({
  method: "GET",
  headers: Object.freeze({ Accept: "application/json" }),
});

const UUID_PATTERN =
  /^[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/;
const ISO_DATE_PATTERN = /^[0-9]{4}-[0-9]{2}-[0-9]{2}$/;
const DECIMAL_PATTERN = /^-?(?:0|[1-9][0-9]*)\.[0-9]{2}$/;
const CURRENCY_PATTERN = /^[A-Z]{3}$/;

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
});

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

  return Object.freeze({
    movement_id: value.movement_id,
    account_id: value.account_id,
    occurrence_date: value.occurrence_date,
    signed_amount: value.signed_amount,
    currency: value.currency,
    description: value.description,
  });
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
