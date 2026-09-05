# Current task

## Objective

Implement and review the frozen ADR-0011 Category/MovementClassification
persistence and internal manual assign/change/clear service. Implementation,
review, and validation are complete. The authorized checkpoint commit is
`feat: implement movement classification domain`; Git history records its SHA.
Do not push.

## Current state

The session verified clean `main` with HEAD and `origin/main` both at
`964e85ef82c9af7cfdb551f3bf2cb188ac06d966`
(`docs: freeze movement classification semantics`).

Migration `0011_movement_classification` adds two initially empty tables with
case-insensitive Category name uniqueness, protected references, MANUAL-only
source, positive revision, and a reverse guard against data loss. It alters no
Movement fields and backfills nothing. ADR-0011 remains unchanged.

`set_movement_classification` locks Account, Movement, then the target Category,
checks expected revision atomically, and returns immutable current state.
Revision 0 represents absence; the first assignment is 1. Actual changes,
clear, and reassign increment once. Correct-revision no-ops retain revision
and timestamp. Inactive categories retain references and allow no-ops/clears;
new assignments to them fail. Financial/provenance state is unchanged.

Existing report/API/client, Account access/discovery, import, and demo code
remain unchanged. Demo seed creates no classifications and preserves manual
changes; cleanup retains its atomic protected failure for classified/cleared
demo Movements.

## Validation state

All 463 Django tests pass, including 30 added tests. Focused classification and
concurrency: 24; sequential migration/isolation orders: 52 each; compatibility:
102; Santander/BCI matrix: 271. Fresh and `0010 -> 0011` migration, Django check,
migration drift, and pip check pass. All 14 frontend tests, typecheck, and build
pass. The handoff records final documentation/privacy/diff hygiene and local
validation artifact locations.

Commit review verified the exact 16-path Git-derived allowlist, unchanged
existing model definitions, and unchanged ADR/API/reporting/frontend/import
contracts. Two added review tests prove raw-SQL constraints and the intentional
application-only normalization boundary. The reverse guard is retained as
documented, deliberate protection against implicit data loss during rollback.

## Next bounded scope

Extend only internal Movement reporting to project current classification in
one consistent read, including absent/cleared rows and inactive categories.
Preserve Account/date membership, exact totals, ordering, and bounded provenance.
Keep HTTP/UI/filter changes separate. Recommended reasoning level: High.

## Non-goals

No classification HTTP capability, UI, filters, automatic/rule/AI assignments,
taxonomy defaults, demo assignments, bulk edits, assignment history, ownership,
transfer or income/expense semantics, tags, notes, hierarchy, or provider mapping.

Read [ADR-0011](../../docs/decisions/ADR-0011-movement-classification.md) and the
[classification contract](../../docs/architecture/movement-classification.md)
after the standard repository resume sequence.
