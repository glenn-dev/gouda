# Local HTTP delivery

## Scope

Gouda exposes three read operations by default:

```text
GET /api/v1/accounts/
GET /api/v1/categories/
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

The opt-in backend classification write boundary is implemented under
[ADR-0012](../decisions/ADR-0012-local-classification-write-boundary.md).
It adds exactly one capability bootstrap and one classification PATCH, described
below. The three GET contracts remain unchanged. React editing is deferred.

## Trust and application flow

The Account and Category discovery request paths are:

```text
validated runlocal runtime
-> active LocalDeliveryRuntime
-> trusted local principal context
-> list_read_accounts(...) or list_read_categories(...)
-> explicit privacy-safe summary serialization
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

## Category discovery request

`GET /api/v1/categories/` accepts no query parameters. Any query parameter
fails closed in the same style as Account discovery. It returns all active
and inactive Categories in the local dataset, ordered by `display_name`, then
UUID. This is the temporary trusted-principal read policy, not ownership or
household scope. `list_read_categories` validates the same opaque principal
before one ordered database read and returns a tuple of frozen `CategorySummary`
values, never ORM objects.

```json
{
  "categories": [
    {
      "id": "22222222-2222-4222-8222-222222222222",
      "display_name": "Synthetic topic",
      "is_active": false
    }
  ]
}
```

These are the exact response fields. There are no counts, pagination,
hierarchy, taxonomy semantics, filtering, search, or other metadata. An empty
dataset returns HTTP 200 with `{"categories": []}`. Inactive labels remain
discoverable because existing classifications may reference them.

## Movement report request

The route requires one canonical lowercase hyphenated Account UUID. The query
requires exactly one value for each parameter:

- `start_date` — inclusive start date in strict `YYYY-MM-DD` form;
- `end_date` — inclusive end date in strict `YYYY-MM-DD` form.

All three endpoints support GET only. POST, PUT, PATCH, DELETE, OPTIONS, and HEAD
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
- optional canonical `description`;
- `source_trace`; and
- `classification` with exactly `state`, `category`, and integer `revision`.

The three classification shapes are:

```json
{"state": "NEVER_ASSIGNED", "category": null, "revision": 0}
```

```json
{
  "state": "CLASSIFIED",
  "category": {
    "id": "22222222-2222-4222-8222-222222222222",
    "display_name": "Synthetic topic",
    "is_active": false
  },
  "revision": 3
}
```

```json
{"state": "CLEARED", "category": null, "revision": 2}
```

Classified and cleared revisions are the persisted positive integer, without
float conversion. An inactive Category remains `CLASSIFIED`. The serializer
maps the immutable internal reporting projection directly, without additional
classification queries or transition logic. Source, update time, history, and
ORM metadata are excluded. HTTP reporting still performs three SELECTs:
Account authorization, Account existence, and the existing joined Movement
read, independent of Movement count. Classification does not change financial
fields, membership, inclusive dates, order, count, exact total, or provenance.

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
| Any Account or Category discovery query parameter | `query_parameters_not_allowed` | 400 |
| Method other than GET | `method_not_allowed` | 405 |
| Requested representation is not JSON-compatible | `not_acceptable` | 406 |

Unknown and policy-denied Account UUIDs are deliberately indistinguishable.
Responses do not expose Python exception strings or source evidence.
Existing DRF content negotiation remains in effect before the GET handler,
including its format override behavior. Discovery does not accept even a
JSON format query parameter. Movement date parsing and treatment of additional
query parameters are unchanged; no classification filtering is implemented.

## Security limitations

This boundary guarantees only that Gouda's supported unauthenticated launcher
owns an exact numeric loopback bind and that the adapter requires its active
runtime capability. It does not authenticate local OS users or processes,
prevent deliberate internal Python bypasses or unsupported launchers, or
detect tunnels, proxies, NAT, SSH forwarding, relays, or external
re-publication. Real authentication is required before expanding the trust
perimeter.

ADR-0012 extends ADR-0010 only for the separately enabled classification
operation. There is no editing UI, filtering, transfer pairing, or
income/expense interpretation.

## Opt-in classification writes

The supported host startup is exactly:

```text
python manage.py runlocal --host 127.0.0.1 --port 8000 \
  --enable-classification-writes \
  --classification-write-origin http://127.0.0.1:5173
```

Both write options are required together. Duplicate or abbreviated startup
flags, another origin, DEBUG=true, IPv6, or another backend port fail before
serving or generating a capability. Read startup retains its existing IPv6
and port support. Omitting both write options creates no write runtime or secret.

Compose remains read-only by default. An explicit local Compose override may
replace only the backend command with this list, retaining all existing networks,
publications, environment, and mounts:

```yaml
services:
  backend:
    command: ["python", "manage.py", "runlocal", "--host", "0.0.0.0", "--port", "8000", "--trusted-container-network", "--enable-classification-writes", "--classification-write-origin", "http://127.0.0.1:5173"]
```

Apply migrations through the normal default startup first. Use
`docker compose -f docker-compose.yml -f <local-override.yml> up --build`
for explicit opt-in; the backend must remain unpublished. Returning to default
Compose configuration recreates a read-only backend. No capability belongs in
the override or an environment variable.

`LocalClassificationWriteRuntime` is independent of principal identity and tied
to the active read runtime. It creates `secrets.token_hex(32)` once after startup
validation, stores the 256-bit secret only in private process memory, and
compares correctly shaped inputs in constant time. Exit clears the active
reference and secret; recreation invalidates old tokens, runtime objects, and
grants. There is no persistence, session, cookie, user, or ownership model.

The new routes use a narrow Django View with explicit ordered dispatch, avoiding
DRF's early negotiation and format overrides. Existing DRF GET views are unchanged.
For either matched route, validation order is local runtime, write runtime,
`request.get_host()` and exact Host, method, exact Origin, capability (PATCH
only), server principal, Accept, query, media/encoding, bounded JSON, shape,
then Account/Movement/Category/revision selectors. Security and parsing failures
before Account resolution perform zero database queries.

### Capability bootstrap

`POST /api/v1/local/classification-write-capability/` accepts exactly `{}`.
Successful JSON is exactly `{"write_capability": "<64 lowercase hex characters>"}`.
Repeated calls return the same process capability without touching the database.
Bootstrap requires a valid server-issued principal and every gate except the
capability being obtained. No read response includes it.

### Classification PATCH

`PATCH /api/v1/accounts/<account_uuid>/movements/<movement_uuid>/classification/`
requires exactly these JSON keys:

```json
{"category_id": "22222222-2222-4222-8222-222222222222", "expected_revision": 0}
```

Category null is an explicit clear. UUIDs must be canonical lowercase hyphenated
strings. Revision must be a JSON integer from 0 through `2**63 - 1`; booleans,
fractional/exponent tokens, strings, and null are rejected. Zero requires no
existing row. Both routes reject all queries, duplicate/extra keys, non-objects,
invalid UTF-8/JSON/constants, unsupported media parameters, and non-identity
encoding. Only UTF-8 `application/json`, optionally `charset=utf-8`, is accepted;
body reads are capped at 1025 bytes to detect the 1024-byte limit. Accept may
be absent or JSON-compatible, including wildcards, but an explicit JSON q=0
fails with 406. There are no format or method overrides.

`classify_authorized_movement` independently validates principal and live grant,
then reuses Account visibility authorization and calls the existing domain
command exactly once. Its outer atomic transaction retains Account -> Movement
-> selected Category locks until the bounded immutable classification projection
is materialized. Projection failure rolls back the edit. Success commits before
HTTP 200 and returns only `{"classification": {...}}`, using the same three
state/category/revision shapes as reporting. It never updates canonical Movement
fields or returns financial/source data.

Unknown and policy-denied Accounts remain indistinguishable. Movement lookup is
scoped to the authorized Account before target Category lookup. Domain revision,
no-op, retirement, and error precedence are unchanged; stale identical commands
receive 409. No HTTP retry occurs. PostgreSQL tests cover first-write, update,
clear/change, reassignment, retirement, locked projection, and rollback.

### Host, Origin, errors, and privacy

Django independently requires Host `127.0.0.1:5173` and Origin
`http://127.0.0.1:5173`, even for raw clients. Missing, null, foreign, malformed,
combined/duplicate, and alternate spellings fail closed. Referer and forwarded
headers are never substitutes. PATCH additionally requires exactly one
`X-Gouda-Classification-Write` header; body, query, cookies, and Authorization
cannot supply it. Vite preserves these headers with `changeOrigin: false` and
preserves duplicate header multiplicity for Django rejection. It injects no token.
Both Vite server and preview explicitly set `cors: false`; actual proxy and
preflight tests prove no Access-Control grants. Framing is denied at the Vite
app edge through CSP `frame-ancestors 'none'` and `X-Frame-Options: DENY`.

The exact stable error table in ADR-0012 is implemented unchanged. Every error
contains only `{"code":"..."}`; unsupported methods return 405 with the route's
single Allow method, and HEAD has no body. Unknown failures/codes become 500
`internal_error`, never exception text. Matched-route responses are JSON with
`Cache-Control: no-store, no-cache, max-age=0`, `Pragma: no-cache`, nosniff, and
same-origin Cross-Origin-Resource-Policy. No redirect, Set-Cookie, or CORS grant
is produced. Unknown paths retain ordinary 404 routing, without slash redirects.

Django HTTP logs contain only allowlisted method/route/status fields. The new
adapter logs unexpected failures only as a fixed operational message; exception
reporting explicitly redacts the capability header/bootstrap field and suppresses
classification request bodies, exception values, and locals. Vite proxy failures
use a fixed diagnostic and a no-store JSON 500, omitting URL/query/stack text.
Vite refuses nonempty `DEBUG` (including CLI `--debug`) before listening because
that optional raw-debug channel bypasses the safe logger. Ordinary development
diagnostics remain enabled.
No browser editor or capability consumer is included in the application bundle.

A malicious local process may deliberately spoof Host/Origin and bootstrap:
this is accepted under ADR-0010's trusted-host perimeter, not prevented by the
capability. A future React editor must hold the token only in closure memory,
guard safe-integer submissions below `Number.MAX_SAFE_INTEGER`, and refetch
after conflicts or ambiguous outcomes without silently replaying a write.

## Local React development client

The repository's first browser client is a Vite + React + TypeScript app under
`frontend/`. It calls only Account discovery and Movement reporting through relative
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
canonical description, current Category presentation, signed amount, and
currency. The parser retains the bounded classification projection only after
validating its state/category/revision combinations. A dedicated table column
shows an active Category label, shows an inactive Category label with an
`Inactive` marker, and presents both `NEVER_ASSIGNED` and `CLEARED` as
`Unclassified`. It does not render UUIDs, revisions, or raw state names.

The client intentionally drops the bounded `source_trace` from its projection
and does not render provenance. It does not fetch Category discovery because
each classified Movement already carries the necessary Category summary.
Request cadence remains one Account discovery request followed by explicit
Movement report requests. There are no classification writes, filters, totals,
or editing controls.
