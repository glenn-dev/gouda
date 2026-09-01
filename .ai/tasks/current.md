# Current task

## Objective

Define and implement one privacy-safe read-only Account summary discovery
operation through the existing validated local-delivery runtime.

## Current state

The fail-closed local-MVP host bootstrap and the first HTTP delivery surface
are implemented in the current worktree. `runlocal` requires an explicit
numeric loopback bind, activates a process-local `LocalDeliveryRuntime`, and
is the only supported path that permits trusted local principal issuance.

Django REST Framework is configured for JSON-only rendering without an
authentication backend. The sole route is:

```text
GET /api/v1/accounts/<account_uuid>/movements/?start_date=YYYY-MM-DD&end_date=YYYY-MM-DD
```

It fails closed without the active runtime, resolves Account access through
the existing non-enumerating account-access service, and explicitly serializes
only the approved canonical Movement report fields. No user authentication,
ownership, write operation, CORS support, frontend, or backend container is
implemented.

## Next bounded scope

The next slice should:

- define the minimum privacy-safe Account summary fields needed to discover an
  Account before requesting its Movement report;
- add exactly one read-only Account summary operation under the same active
  runtime and trusted-principal boundary;
- reuse the account-access policy rather than querying arbitrary Accounts in
  the HTTP adapter;
- keep identifiers and labels synthetic in tests; and
- document a small stable response contract without adding generic Account
  serialization or CRUD.

## Non-goals

Do not add login, Django auth, sessions, tokens, users, households, roles,
ownership/grants, write/import endpoints, generic Account CRUD, frontend,
CORS convenience, Docker backend publication, proxying, TLS, classification,
or new financial semantics.

## Preconditions and guardrails

- Review and commit the current HTTP checkpoint before beginning this slice.
- Account discovery must fail closed without the active local-delivery
  runtime; request data cannot establish principal trust.
- Expose only fields justified for local report selection. Do not leak source
  evidence, account numbers, card identifiers, or provider secrets.
- Loopback remains a single-host operational trust assumption, not user
  authentication.

Recommended reasoning level: Sol High.
