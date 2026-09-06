# Current task

## Objective

Extend only the internal canonical Movement report with the current
classification projection defined by ADR-0011. Implementation and validation
are complete. The checkpoint is authorized for one commit titled
`feat: project movement classification in reporting`. Do not push.

## Baseline

The session fetched origin and verified clean `main` with HEAD and
`origin/main` both at `bf70b85d56e831e2422c92562eb14ff10f77f548`
(`feat: implement movement classification domain`) before changes.

## Current state

Every internal `MovementReportItem` now has an immutable bounded
classification projection:

- `NEVER_ASSIGNED`: no row, null category, revision `0`;
- `CLASSIFIED`: Category UUID, display name, active state, and persisted
  positive revision; and
- `CLEARED`: retained row, null category, and persisted positive revision.

Never-assigned and cleared remain distinct states but are both unclassified
for future filtering. Inactive Categories remain visible as current
assignments. Assignment source and timestamp are omitted because there is no
current reporting consumer; revision is retained for mutation coordination.

The existing Movement query uses nullable `select_related` joins for current
classification and Category alongside safe provenance. Reports remain two
queries independent of Movement count: Account existence plus one joined
Movement read. Membership, inclusive occurrence-date semantics, Account scope,
ordering, count, exact signed total, financial fields, and provenance are
unchanged. Reporting performs no writes or repair.

The HTTP serializer, routes, request contract, response fields, React client,
classification mutation service, filters, models, migrations, imports, and
demo seed are unchanged. ADR-0011 is unchanged.

## Validation state

- Focused reporting/classification/concurrency/API/Account/demo: 99 passed.
- Full Django suite: 466 passed.
- Migration/isolation forward and reverse orders: 55 passed each.
- Santander and BCI regressions: 271 passed, including the pinned legacy-XLS
  dependency check.
- Local delivery/Compose/API/demo matrix: 75 passed.
- Fresh `0010 -> 0011` migration, Django check, migration drift, Python
  compilation, `pip check`, and `docker compose config` passed.
- Frontend: 14 tests, typecheck, build, and `npm ls` passed.
- Final Markdown-link, privacy, private-file, diff, and Git-status results are
  recorded in `.ai/handoff.md`.

## Next bounded scope

Add internal-only Category/unclassified filtering to canonical Movement
reporting under ADR-0011, keeping category and unclassified selectors mutually
exclusive and preserving signed-account-effect totals. Keep HTTP and UI work
separate. Recommended reasoning level: High.

## Non-goals

No classification HTTP capability, UI, automatic/rule/AI assignments, taxonomy
defaults, demo assignments, bulk edits, assignment history, ownership,
transfer or income/expense semantics, tags, notes, hierarchy, or provider
mapping.
