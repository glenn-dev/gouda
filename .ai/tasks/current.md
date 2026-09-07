# Current task

## Objective

Design the narrowest safe local HTTP write boundary for Movement classification.
Design is frozen in
[ADR-0012](../../docs/decisions/ADR-0012-local-classification-write-boundary.md);
implementation remains deferred. The reviewed documentation-only checkpoint is
committed as `docs: define local classification write boundary`. Do not push.

## Baseline

After `git fetch origin`, clean `main`, HEAD, and `origin/main` all matched
`da9f0c7b7ffb6b9ece9e3ae76629194349f3e6f3`
(`feat: render movement classification in local client`).

## Current state

- The internal manual command, read HTTP projection, Category discovery, and
  read-only React presentation remain the complete implemented classification
  capability. No production code, tests, migrations, or frontend behavior changed.
- ADR-0012 records independent default-off write activation, a separate opaque
  runtime/grant, process-lifetime capability, explicit bootstrap, exact
  Origin/Host checks, and one Account-scoped classification PATCH contract.
- Principal identity remains server-issued and orthogonal to write authority.
  Read access or UUID possession alone cannot authorize mutation. Arbitrary
  local processes/users remain trusted under ADR-0010; the new token is not
  protection against a hostile local host.
- The design preserves all domain revision/no-op/locking semantics and defines
  exact errors, a transaction-consistent classification-only response, and
  explicit refetch without silent retry after conflicts or ambiguous outcomes.
- First write topology is the existing IPv4 Vite edge at port 5173 for host
  development or Compose. IPv6 backend reads remain supported; no IPv6 write
  topology is implicitly added. ADR-0010 and ADR-0011 text is unchanged.

## Validation state

Documentation/local-link and JSON-example checks, ADR/reference consistency,
privacy/private-file checks, exact changed-path review, and `git diff --check`
are recorded in `.ai/handoff.md`. No application test suite is required or run
for this design-only checkpoint. No database or private evidence was accessed.

## Next bounded scope

Implement ADR-0012's backend runtime, capability bootstrap, authorized
classification orchestration, and PATCH adapter, plus required delivery-edge
controls. Prove actual Host/Origin enforcement, absent CORS grants through
Vite, restart/token isolation, safe logs/cache behavior, and PostgreSQL
concurrency/rollback. Keep startup opt-in and the default stack read-only.
No editor controls in that backend slice; follow with a separate React editor
task covering explicit manual choices, memory-only capability handling, safe
integer submissions, and 409/ambiguous-outcome reconciliation.
Recommended reasoning level: High.

## Non-goals

No implementation in this session; no migrations, HTTP endpoints, frontend
changes, test changes, commits, or pushes. Filtering, Category management,
default taxonomy, demo assignments, automatic/rule/AI assignments, bulk edits,
history, ownership, transfer or income/expense semantics remain deferred.
