# Current task

## Objective

Design the smallest trusted local-caller bootstrap/authentication contract for
Gouda's first read-only delivery surface.

## Current state

The pre-HTTP Account authorization boundary is implemented in
`gouda.ledger.services.account_access`. One opaque module-issued local
principal receives temporary read access to all persisted Accounts. The
resolver validates principal context and a UUID Account selector, returns an
authorized persisted `Account`, and uses one `account_not_accessible` failure
for unknown and policy-denied selectors. The authorized orchestration service
delegates to the existing immutable `MovementReport` result.

This is authorization policy only. Gouda still has no authentication app,
persisted user/principal/household/role/grant model, HTTP endpoint, or DRF
installation. Calling `trusted_local_principal_context()` merely because an
HTTP request arrived would make every reachable caller trusted and is not an
acceptable network boundary.

## Scope

Perform a design/security checkpoint that:

- defines the local MVP's intended network/process exposure;
- identifies how trusted server-side code establishes the one local caller
  before issuing principal context;
- evaluates the smallest viable mechanisms without inferring identity from
  request bodies, headers, Account UUIDs, artifacts, or provider data;
- specifies failure and deployment assumptions needed by a later DRF adapter;
- determines whether DRF can be installed and a read-only endpoint safely
  implemented in one following bounded slice; and
- records the event that would require replacing the temporary singleton
  policy with durable multi-principal access semantics.

## Non-goals

Do not implement DRF/HTTP, middleware, authentication, sessions, tokens, users,
households, roles, Account ownership/grants, models, migrations, frontend,
writes/import authorization, or new financial semantics during the design
checkpoint.

## Acceptance criteria

- Client-controlled data cannot establish trusted principal context.
- The selected mechanism has an explicit local deployment/threat boundary.
- Network reachability is not silently treated as identity unless that is an
  explicit, justified, fail-closed local-only deployment contract.
- Account authorization remains delegated to the implemented resolver.
- A future endpoint is required to call
  `report_authorized_canonical_movements` rather than fetch an Account itself.
- Authentication, authorization, ownership, and delivery remain distinct.
- The design identifies exact implementation prerequisites and privacy-safe
  transport errors without broad multi-tenant architecture.

Principal risks are creating a bearer secret accidentally through client
input, exposing an unauthenticated endpoint beyond its assumed local boundary,
or adding durable ownership semantics without product evidence.

Recommended reasoning level: Sol High.
