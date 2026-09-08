# Current task

## Objective

Completed the bounded local-development ergonomics checkpoint. After one-time
`.env` setup, the supported deterministic synthetic visual demo is `make demo`
and its volume-preserving teardown is `make down`. The commit contract is
exactly one signed `chore: simplify local demo workflow` commit; no push is
authorized.

## Baseline

On 2026-09-08, branch `main` and a clean working tree were verified. HEAD and
`origin/main` both equaled
`582ff3c7c9b343e70d188a95d83a01fd499e72af`, titled
`feat: implement Gouda UI foundation`, with a good ED25519 SSH Git signature.

## Implemented interface

The Make workflow hardcodes Compose project `gouda-demo`, validates required
`.env` values without printing them, validates Compose configuration,
force-recreates the isolated graph, waits for declared PostgreSQL/backend/
frontend health, and explicitly invokes the existing idempotent `seed_demo`.
Only Vite is host-published. PostgreSQL and Django remain internal to Compose.

`make status` and `make logs` inspect only the isolated project. `make down`
removes its containers and networks without deleting its volume. Destructive
`make demo-reset` removes only the literal
`gouda-demo_gouda-postgres-data` volume; neither its project nor volume target
is variable. Host-process development that genuinely needs PostgreSQL on the
host uses `docker-compose.host-db.yml` with the separate fixed
`gouda-host-dev` project.

## Validation

A real fresh `make demo` migrated through ledger `0011`, reached all three
health checks, served the Vite/API path, and seeded exactly 2 Accounts and 11
Movements while a disposable PostgreSQL container occupied host port 5432.
Repeating `make demo` retained those exact counts. `make down` preserved the
demo volume, and restart after teardown succeeded with the same data and no
container/network repair steps. Missing and blank `.env` fixtures failed before
Compose startup and revealed only variable names. Demo logs contained neither
configured secret value.

Both base and host-database Compose configurations pass validation. All 528
Django tests and all 59 frontend tests pass. Django system checks, migration
drift, `pip check`, frontend typecheck/build, and `npm ls` pass. The first full
containerized Django run exposed missing read-only mounts for the new operator
files; those mounts were added and the full rerun passed.

The pre-existing isolated synthetic `gouda-demo` containers, networks, and
volume were deliberately removed once with the new reset to establish the fresh
test. Its volume was recreated and is preserved after final `make down`. The
temporary port-5432 collision container was stopped and auto-removed. The
historical default `gouda_gouda-postgres-data` volume was metadata-inspected
only and was not attached, read, mutated, or deleted; no default Gouda container
was started.

## Next bounded scope

Design and implement the separate manual classification editor under ADR-0012.
Retain explicit choices, memory-only capability handling, safe revisions, and
refetch after conflicts or ambiguous outcomes without silent replay. Filtering
remains separate.
