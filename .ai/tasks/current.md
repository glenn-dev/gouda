# Current task

## Objective

Define and freeze MVP Movement classification semantics and persistence before
implementation. This documentation-only design is complete; production
classification implementation remains deferred.

## Current state

On 2026-09-05, branch `main`, HEAD, and freshly fetched `origin/main` all matched
`76a1647ab005175418e7b7175fc3e3ec9abb3589` (`feat: add local demo bootstrap`).
The design session started with a clean tree. The subsequent commit review
verified the same baseline and exactly the ten expected documentation paths.
The user authorized one commit, `docs: freeze movement classification semantics`,
without pushing. Git history records its exact SHA; implementation remains
the next task.

[ADR-0011](../../docs/decisions/ADR-0011-movement-classification.md) records the
alternatives and decision. The
[classification contract](../../docs/architecture/movement-classification.md)
owns fields, cardinality, corrections, source values, migration, demo,
reporting, privacy, and ownership revisit triggers. Product scope now separates
category organization from deferred economic-event types and transfers.

Use one optional local dataset Category through a separate mutable
MovementClassification, with manual source, revision, and update time.
Previous assignments are not retained. An absent row is never assigned; a
retained null-category row is cleared. Both are unclassified. No financial
fact, source contract, code, migration, API, or demo has changed.

## Validation state

Markdown local-link validation passes for 41 files and 55 links (no fragment
links present). Documentation-only scope, added-text privacy checks, ignored
and untracked private paths, diff review, and `git diff --check` pass. The
handoff records the complete results. No runtime suite was rerun; prior
bootstrap results are historical validation of the committed baseline.

## Next bounded scope

Implement Category and MovementClassification persistence plus the internal
manual assign/change/clear service exactly under ADR-0011. Add meaningful
PostgreSQL tests for cardinality, category retirement, source rejection,
revision conflicts including first-write and clear/reassign races, financial
immutability through the command, migrations/no backfill/reverse guard, and
existing import/report/demo compatibility. Keep `clear_demo`'s atomic protected
failure for classified demo Movements. Run applicable regression and migration
checks. Category provisioning is a trusted internal boundary, without taxonomy
seeding or category-management UI/API.

## Non-goals

No HTTP write capability, classification UI, API/report filters or projection
changes, heuristics, AI/rules, transfer pairing, income/expense enum, bulk edits,
tags, hierarchy, notes, ownership, history engine, or demo seed changes.

Recommended reasoning level: Sol High.
