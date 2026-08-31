# Current task

## Objective

Implement one narrow read-only canonical Movement report endpoint through the
validated local-delivery runtime.

## Current state

The fail-closed local-MVP host bootstrap is implemented in the current
worktree. `runlocal` requires an explicit `127.0.0.1` or `::1` bind, validates
an unambiguous port, derives Django's server address itself, and activates a
process-local `LocalDeliveryRuntime` only during the server runner lifetime.
Direct `runserver`, WSGI, and ASGI launches do not activate the capability.

The runtime may issue the existing singleton trusted principal with no request
input. Account authorization and canonical Movement reporting are already
implemented and remain read-only. URLs are still empty; DRF, authentication,
CORS, CSRF middleware, frontend behavior, and HTTP serialization are absent.

## Scope

The next bounded delivery slice should:

- install and minimally configure DRF;
- add one read-only endpoint for an internal Account UUID plus inclusive start
  and end dates;
- require the active `LocalDeliveryRuntime` before obtaining
  `trusted_local_principal_context()`;
- call `report_authorized_canonical_movements` rather than querying Account or
  Movement directly;
- explicitly serialize only the privacy-safe `MovementReport` fields already
  approved by architecture; and
- preserve indistinguishable Account access failures and stable date failures
  without leaking source evidence.

## Non-goals

Do not add login, Django auth, sessions, tokens, users, households, roles,
ownership/grants, write/import endpoints, frontend, CORS convenience, Docker
backend publication, proxying, TLS, financial semantics, classification, or
reporting representation changes.

## Preconditions and guardrails

- Begin the endpoint slice from the reviewed, committed runtime checkpoint and
  a clean worktree.
- The endpoint must fail closed when no active local-delivery runtime exists;
  a Host header or direct `runserver` is not trust.
- Only Account UUID and dates may come from request data. Principal trust may
  not.
- Loopback remains a single-host operational trust assumption, not user
  authentication.

Recommended reasoning level: Sol High.
