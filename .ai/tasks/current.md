# Current task

## Objective

Implement the temporary single-principal read-Account access boundary and the
authorized canonical Movement reporting orchestration service.

## Current state

`docs/architecture/account-access.md` defines the pre-HTTP boundary. Gouda has
no persisted user, principal, household, member, role, permission, or Account
ownership model. Multi-user sharing is outside MVP scope, and no documented
product rule establishes named-person access or individual/shared Accounts.

The temporary MVP policy recognizes one trusted local principal supplied by
trusted application composition and allows that principal to read all
persisted Accounts. This is an access policy, not ownership. An untrusted
Account UUID must be resolved together with principal context; unknown and
unauthorized Accounts are indistinguishable as `account_not_accessible`.

The existing `report_canonical_movements` service already accepts a trusted
persisted `Account` and returns the canonical immutable report.

## Scope

Implement a small read-only application service that:

- represents an opaque trusted principal context without authentication
  mechanics or persistence;
- is configured for exactly one recognized local principal;
- validates one untrusted internal Account UUID selector;
- resolves principal access and Account lookup in one boundary;
- returns the authorized persisted `Account` object;
- uses `principal_context_invalid`, `account_selector_invalid`, and uniform
  `account_not_accessible` failures; and
- provides one orchestration function that resolves access and then invokes
  `report_canonical_movements`, returning the existing `MovementReport`.

Expected code areas are small modules under `gouda/ledger/services/` and
focused PostgreSQL-backed tests under `tests/ledger/`.

## Non-goals

Do not add authentication, DRF/HTTP, serializers, permissions frameworks,
frontend, models, migrations, users, households, members, roles, persisted
grants, tokens, sessions, JWT, imports/writes, classification, transfers, BCI
lifecycle behavior, or new financial semantics. Read access must not imply
write/import permission.

## Acceptance criteria

- Only the configured trusted principal can resolve Accounts.
- A valid principal can resolve every current persisted Account under the
  explicitly temporary policy.
- Invalid principal context and selector shapes fail deterministically.
- Unknown and unauthorized Account selectors produce the same safe failure.
- Arbitrary Account UUIDs never reach reporting without resolver success.
- Authorized reporting preserves inclusive dates, Account isolation,
  canonical ordering, exact Decimal totals, and the existing result type.
- The boundary is read-only, deterministic, and does not expose Account
  existence or private source data through errors.
- Tests cover repeated calls and multiple Accounts without private values.

Principal risks are accidentally treating a client value as trusted principal
context, leaking Account existence through distinguishable failures, or
letting the temporary all-Accounts policy masquerade as ownership.

Recommended reasoning level: Sol High.
