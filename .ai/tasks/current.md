# Current task

## Objective

Close the first minimal local React read-only client checkpoint over the
existing Account discovery and canonical Movement report APIs.

## Current state

The fail-closed local-MVP host bootstrap and both HTTP read operations are
committed. `runlocal` requires an explicit numeric loopback bind, activates a
process-local `LocalDeliveryRuntime`, and is the only supported path that
permits trusted local principal issuance.

Django REST Framework is configured for JSON-only rendering without an
authentication backend. The routes are:

```text
GET /api/v1/accounts/
GET /api/v1/accounts/<account_uuid>/movements/?start_date=YYYY-MM-DD&end_date=YYYY-MM-DD
```

Both fail closed without the active runtime and enter through the Account
access service. The current worktree adds a Vite + React + TypeScript client
that discovers Accounts, selects one internal UUID, accepts inclusive dates,
and renders canonical Movement fields and backend totals without numeric
conversion. Vite binds to `127.0.0.1:5173` and proxies only `/api` to
`127.0.0.1:8000`; no backend change or CORS rule is added.

## Next bounded scope

Define and freeze canonical Movement classification semantics and persistence
for the MVP types before implementing classification filters or UI. Provider
categories and amount signs must not be treated as canonical classification.

## Non-goals

Do not add login, Django auth, sessions, tokens, users, households, roles,
ownership/grants, write/import endpoints, generic Account CRUD, broad CORS,
Docker backend publication, remote proxying, TLS, classification behavior, or
new financial semantics as part of the frontend checkpoint.

## Preconditions and guardrails

- Review the committed Account discovery checkpoint before changing the
  frontend slice.
- Treat both backend responses as already bounded contracts; do not expand
  them merely for display convenience.
- Keep the browser/backend edge within the frozen loopback-only trust contract.
- Loopback remains a single-host operational trust assumption, not user
  authentication.

Recommended reasoning level: Sol High.
