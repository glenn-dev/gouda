# Current task

## Objective

Close the bounded local developer/demo bootstrap checkpoint for the existing
read-only Account/Movement flow.

## Current state

The worktree adds a complete three-service Docker Compose path:

- PostgreSQL 16 with its existing named volume and `127.0.0.1:5432`
  publication;
- Django with automatic migrations, no host publication, and the validated
  `runlocal --trusted-container-network` bootstrap; and
- Vite with the only browser-facing publication at `127.0.0.1:5173` and a
  fixed `/api` proxy to the internal backend service.

The internal application network is limited to Vite and Django. Django's
container mode permits only the exact internal `0.0.0.0:8000` endpoint and does
not claim to verify Docker host publication. Repository-owned Compose
configuration and static tests own that guarantee. Direct host `runlocal`
remains loopback-only.

The explicit `seed_demo` command creates two Accounts and eleven canonical
Movements over fixed January-April 2026 dates. Synthetic provenance envelopes
satisfy the existing mandatory Movement origin contract without invoking
production import routes. Fixed UUIDv5 identities make seeding repeatable and
allow `clear_demo` to delete only that graph without an `is_demo` financial
field. One narrow migration adds truthful synthetic source/record choices to
the existing closed provenance constraints, avoiding false bank-source claims.

## Validation state

The focused 42-test demo/Compose/local-delivery suite and the full 433-test
Django suite pass inside a fresh PostgreSQL 16 Compose stack. Both
migration/demo orderings pass 18 tests. Image builds, automatic migrations,
all service health checks, repeated seeding, the frontend root, Account
discovery, and an April Movement report through `127.0.0.1:5173` pass. The 14
frontend tests, typecheck, build, dependency checks, Django system check,
migration drift check, Python dependency check, Compose rendering, Markdown
links, privacy boundary, and diff hygiene pass. Live cleanup is idempotent and
the stack stops while preserving its named volume.

## Next bounded scope

Define and freeze canonical Movement classification semantics and persistence
for the MVP types before implementing classification filters or UI. Provider
categories and amount signs must not be treated as canonical classification.

## Non-goals

Do not add classification, login, Django auth, sessions, tokens, users,
households, roles, ownership/grants, write/import HTTP endpoints, broad CORS,
LAN/remote exposure, TLS, production orchestration, or new source semantics.

Recommended reasoning level: Sol High.
