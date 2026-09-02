# Current task

## Objective

Close the privacy-safe read-only Account discovery checkpoint and validate the
minimum backend read surface for a local frontend.

## Current state

The fail-closed local-MVP host bootstrap and both HTTP read operations are
implemented in the current worktree. `runlocal` requires an explicit
numeric loopback bind, activates a process-local `LocalDeliveryRuntime`, and
is the only supported path that permits trusted local principal issuance.

Django REST Framework is configured for JSON-only rendering without an
authentication backend. The routes are:

```text
GET /api/v1/accounts/
GET /api/v1/accounts/<account_uuid>/movements/?start_date=YYYY-MM-DD&end_date=YYYY-MM-DD
```

Both fail closed without the active runtime and enter through the Account
access service. Discovery explicitly serializes only Account UUID, display
name, kind, and currency in display-name/UUID order; Movement reporting is
unchanged. No user authentication, ownership, write operation, CORS support,
frontend, or backend container is implemented.

## Next bounded scope

Implement one minimal read-only local React client that:

- discovers Accounts from `GET /api/v1/accounts/`;
- selects an Account UUID and inclusive date range;
- requests and renders the existing canonical Movement report; and
- preserves the same loopback-only runtime, JSON, and privacy boundary without
  adding write operations or broad CORS behavior.

## Non-goals

Do not add login, Django auth, sessions, tokens, users, households, roles,
ownership/grants, write/import endpoints, generic Account CRUD, frontend,
CORS convenience, Docker backend publication, proxying, TLS, classification,
or new financial semantics.

## Preconditions and guardrails

- Review and commit the current Account discovery checkpoint before beginning
  the frontend slice.
- Treat both backend responses as already bounded contracts; do not expand
  them merely for display convenience.
- Keep the browser/backend edge within the frozen loopback-only trust contract.
- Loopback remains a single-host operational trust assumption, not user
  authentication.

Recommended reasoning level: Sol High.
