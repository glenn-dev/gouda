# Current task

## Objective

Expose the existing immutable Movement classification projection through the
read-only local HTTP report, and add minimal read-only Category discovery.
Implementation and review validation are complete. The checkpoint is recorded
in one commit titled `feat: expose movement classification read api`. Do not push.

## Baseline

After `git fetch origin`, clean `main`, HEAD, and `origin/main` all matched
`8973eb8c25a2334323a8bb932966059bba49259e`
(`feat: project movement classification in reporting`).

## Current state

- `GET /api/v1/categories/` returns `{"categories": [...]}` with exactly
  `id`, `display_name`, and `is_active` per entry. Active and inactive labels
  are included in display-name/UUID order. No counts or pagination metadata.
- `list_read_categories` reuses the access module's opaque principal validator
  before one ordered read, returning frozen `CategorySummary` values. Dataset
  read visibility does not imply ownership or write permission.
- Every HTTP Movement now includes `classification`: `NEVER_ASSIGNED` with
  null Category and revision 0; `CLASSIFIED` with Category id/display/active
  fields and positive persisted revision; or `CLEARED` with null Category and
  positive persisted revision. Inactive assignments remain visible.
- HTTP serializes the internal report directly, with no classification query
  or transition logic. Reporting remains two internal queries, three including
  Account authorization. Financial fields, membership, dates, order, counts,
  exact Decimal totals, and safe provenance are unchanged.
- The new endpoint follows existing runtime, principal, GET-only, JSON-only,
  query-rejection, and error policies. ADR-0010 and ADR-0011 remain unchanged.
- No frontend file changed. The existing parser accepts additional server
  fields and discards classification; no client state or UI is added.

## Validation state

- Focused API/reporting/classification/concurrency/Account/local/demo: 144 passed.
- Santander/BCI source regression matrix: 271 passed.
- Sequential migration isolation, forward and reverse orders: 98 passed each.
- Full Django suite: 481 passed (15 added).
- Fresh migrations, Django system check, migration drift, and pip check passed.
- Frontend: 14 tests, typecheck, build, and npm ls passed. An additional local
  parser check accepted and discarded all three classification states without
  changing frontend files or monetary strings.
- Final hygiene and isolated test environment cleanup are in `.ai/handoff.md`.

## Next bounded scope

Recommend frontend read-only classification rendering next: consume the
existing report projection without changing financial arithmetic or trust.
The separate design of a narrow local classification write capability remains
valuable afterward; it must revisit ADR-0010 before any endpoint is built.
Filtering is deferred. Recommended reasoning level: High.

## Non-goals

No HTTP writes, classification UI or filtering, default taxonomy, demo
assignments, automatic/rule/AI assignments, bulk edits, history, ownership,
transfer or income/expense semantics, tags, notes, hierarchy, or provider mapping.
