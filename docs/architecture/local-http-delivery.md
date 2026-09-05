# Local read-only HTTP delivery

## Scope

Gouda exposes exactly two local-MVP HTTP operations:

```text
GET /api/v1/accounts/
GET /api/v1/accounts/<account_uuid>/movements/
```

It is an unauthenticated read adapter supported only through the validated
`runlocal` launcher defined by
[ADR-0010](../decisions/ADR-0010-loopback-only-local-mvp-delivery.md). It is not
supported through generic `runserver`, WSGI, ASGI, LAN, remote, externally
proxied, tunneled, forwarded, shared-host, or production exposure. `runlocal`
supports either a direct numeric-loopback bind or the explicit repository-owned
Compose mode described below.

The adapters use Django REST Framework without Django auth, sessions, tokens,
users, ownership persistence, CORS, routers, ViewSets, model serializers,
pagination, or a browsable API. Only JSON rendering is enabled.

## Trust and application flow

The discovery request path is:

```text
validated runlocal runtime
-> active LocalDeliveryRuntime
-> trusted local principal context
-> list_read_accounts(...)
-> explicit privacy-safe Account summary serialization
```

The Movement report request path is:

```text
validated runlocal runtime
-> active LocalDeliveryRuntime
-> trusted local principal context
-> untrusted Account UUID and date parsing
-> report_authorized_canonical_movements(...)
-> explicit privacy-safe JSON serialization
```

Runtime trust is checked before Account/query validation or database access.
Headers, cookies, query parameters, request bodies, Host, origin, and remote
address do not create or select principal trust. The Account UUID remains an
untrusted selector and is resolved through the
[Account access boundary](account-access.md).

## Account discovery request

`GET /api/v1/accounts/` accepts no query parameters. Any query parameter is
rejected with `query_parameters_not_allowed`; the operation has no filtering,
search, caller-supplied ordering, or pagination.

The response is:

```json
{
  "count": 1,
  "accounts": [
    {
      "id": "11111111-1111-4111-8111-111111111111",
      "display_name": "Synthetic current account",
      "kind": "CURRENT",
      "currency": "CLP"
    }
  ]
}
```

Each entry is an explicit `AccountSummary` projection containing only the
internal UUID needed by the Movement route, canonical display name, canonical
product kind, and currency. Entries are ordered by `display_name`, then UUID.
Economic orientation is canonical but redundant with the current closed
kind/orientation invariant, so it is not exposed. Provider or institution
identity, external or masked account/card identifiers, source/import bindings,
balances, totals, transaction counts, Movements, observations, and provenance
are excluded.

## Movement report request

The route requires one canonical lowercase hyphenated Account UUID. The query
requires exactly one value for each parameter:

- `start_date` — inclusive start date in strict `YYYY-MM-DD` form;
- `end_date` — inclusive end date in strict `YYYY-MM-DD` form.

Both endpoints support GET only. POST, PUT, PATCH, DELETE, OPTIONS, and HEAD
are rejected with HTTP 405. HTML and the DRF browsable API are not enabled.

## Movement report response

The JSON response explicitly contains:

- `account_id`;
- `start_date` and `end_date`;
- `movement_count`;
- `net_signed_amount` as an exact decimal string; and
- `movements` in ascending occurrence-date and Movement-UUID order.

Each Movement contains only:

- `movement_id`;
- `account_id`;
- `occurrence_date`;
- `signed_amount` as an exact decimal string;
- `currency`;
- optional canonical `description`; and
- `source_trace`.

The source trace contains only RawRecord, ImportBatch, and SourceArtifact UUIDs,
source kind, source variant, parser version, import status, and reconciliation
status. It excludes filenames, digests, bytes, raw cells, raw payloads, source
references, running balances, provider account/card identifiers, and opaque
source evidence.

`net_signed_amount` and `signed_amount` retain canonical signed-account-effect
semantics. They are not labeled as income, expense, cash flow, or balance
change.

## Errors

Errors use the minimal JSON shape `{"code": "<stable_code>"}`.

| Condition | Code | HTTP status |
| --- | --- | --- |
| Validated local runtime absent | `local_delivery_not_active` | 503 |
| Principal context rejected | `principal_context_invalid` | 403 |
| Account UUID malformed | `account_selector_invalid` | 400 |
| Account unknown or policy-denied | `account_not_accessible` | 404 |
| Start date missing, duplicated, or invalid | `start_date_invalid` | 400 |
| End date missing, duplicated, or invalid | `end_date_invalid` | 400 |
| Start date after end date | `date_range_invalid` | 400 |
| Any Account discovery query parameter | `query_parameters_not_allowed` | 400 |
| Method other than GET | `method_not_allowed` | 405 |
| Requested representation is not JSON-compatible | `not_acceptable` | 406 |

Unknown and policy-denied Account UUIDs are deliberately indistinguishable.
Responses do not expose Python exception strings or source evidence.

## Security limitations

This boundary guarantees only that Gouda's supported unauthenticated launcher
owns an exact numeric loopback bind and that the adapter requires its active
runtime capability. It does not authenticate local OS users or processes,
prevent deliberate internal Python bypasses or unsupported launchers, or
detect tunnels, proxies, NAT, SSH forwarding, relays, or external
re-publication. Real authentication is required before expanding the trust
perimeter.

## Local React development client

The repository's first browser client is a Vite + React + TypeScript app under
`frontend/`. It calls only the two documented GET operations through relative
`/api` URLs. The Vite development server binds explicitly to
`127.0.0.1:5173` and proxies only the `/api` path to the validated backend at
`http://127.0.0.1:8000`. No backend CORS configuration is added.

The primary startup sequence is:

```text
docker compose up --build
docker compose exec backend python manage.py seed_demo
Browser: http://127.0.0.1:5173/
```

Compose publishes Vite at `127.0.0.1:5173` and does not publish Django. Vite
binds to `0.0.0.0` only inside its container and proxies only `/api` to the
literal `http://backend:8000` target across the internal application network.
Django starts through `runlocal --host 0.0.0.0
--trusted-container-network`; that explicit mode permits only the internal IPv4
wildcard on port `8000`. It does not inspect or attest Docker host publication.
The repository-owned Compose file enforces the loopback browser edge, absence
of a backend publication, and membership of only the backend and frontend on
the internal application network.

For host-process development, use:

```text
Terminal 1: python manage.py runlocal --host 127.0.0.1 --port 8000
Terminal 2: cd frontend && npm run dev
Browser:    http://127.0.0.1:5173/
```

Both proxy arrangements keep browser API requests same-origin during local development,
but it is not authentication and does not issue trusted principal context.
The backend still fails closed unless `runlocal` owns the numeric-loopback
bind and its active `LocalDeliveryRuntime` issues the principal. The frontend
server and proxy are local development machinery, not a production deployment
or authorization boundary.

The client preserves monetary strings exactly and performs no financial
arithmetic. It renders Account display name, kind, and currency; inclusive
report dates; backend count and net signed amount; and each Movement's date,
canonical description, signed amount, and currency. It intentionally drops
the bounded `source_trace` from its client-side report projection and does not
render provenance in the primary UI.
