# ADR-0011: Keep optional Movement categories in separate current state

- Status: Accepted design; implementation deferred
- Date: 2026-09-05
- Refines: MVP classification scope; preserves ADR-0005 and ADR-0008/0009

## Context

Gouda has canonical signed asset/liability effects, immutable observation
claims, append-only resolution decisions, and account/date reporting. It has
no classification or User/Household persistence. Earlier MVP scope listed
income, expense, transfer, refund, fee, and adjustment as types without a
contract for their relationship to account effects or shared economic events.
Provider categories remain source evidence, and amount sign cannot establish
these economic meanings.

The MVP needs explicit topic grouping without forcing guesses at import,
mutating financial facts, or prematurely building a taxonomy or event system.
Persistence location and loss of past assignments are durable decisions: a
future history migration cannot recover overwritten decisions. This warrants
an ADR, even though the implementation is a separate checkpoint.

## Decision

Use zero or one category per canonical Movement. Category has a stable UUID,
short display name unique without regard to case in the local dataset through
a PostgreSQL unique index on `Lower(display_name)`, and
active flag. It has no code, parent, sort order, owner, or economic type.
Categories are local dataset vocabulary, not universal application constants
or placeholder Household-owned rows. No default taxonomy is seeded.

Store assignment separately in one optional `MovementClassification` row per
Movement: Movement primary-key/one-to-one reference, nullable protected
Category, `source=MANUAL`, positive revision, and last-change timestamp.
No row means never assigned; a retained null-category row means cleared. Both
are unclassified, never a sentinel Category. Source records the last actual
classification change; it is not import provenance or an authenticated actor.

Explicit manual assign/change/clear commands mutate only current assignment.
Revision comparison, locking, and persistence occur atomically in one database
transaction to prevent stale overwrites; a non-atomic Python read/check/save
sequence is insufficient.
Previous values are not retained, and no historical replay, audit trail, undo,
or as-of category reporting is promised. This limited policy applies only to
organizational metadata; evidence/resolution immutability remains intact.

Category is independent of sign and economic-event type. Do not provision a
temporary Transfer category or use categories to exclude transfers, infer
income/expense, or pair refund/reversal events. Reports may later expose and
filter current categories while retaining signed-account-effect totals.
A future category selector and unclassified selector are mutually exclusive;
exact response fields, parameter spelling, and transport errors are deferred.

Only `MANUAL` is supported initially. Revisit history and provenance before
rules, AI, imports, automatic replacements, bulk editing, audit/undo needs,
or historical classification reporting. Future demo assignments require
classification persistence and a separate explicit provenance decision before
implementation. No additional source value or its semantics is frozen here,
and seed execution must not impersonate manual assignment. Revisit
ownership before multiple principals, differentiated visibility, households,
or dataset merging. Do not fabricate actors or reconstruct unavailable history.

The complete schema, concurrency, migration, security, demo, and future read
contract is in [Movement classification](../architecture/movement-classification.md).
No production code, migration, API, or demo change is made by this decision.

## Persistence alternatives

| Alternative | Conceptual fit and corrections | Auditability | Complexity and migration impact | Query ergonomics |
| --- | --- | --- | --- | --- |
| A. Nullable `Movement.category_id` | Fits zero/one; correction writes a column on the canonical fact row. | None unless extra fields/history are added. | Lowest; Category table plus alteration of Movement, no value backfill needed. Classification metadata would further widen Movement. | Simplest direct join/filter. |
| B. Separate one-to-one current state (chosen) | Fits zero/one and isolates mutable assignment; overwrite current value, retain clears and revision. | Last change only; no past values or actors. | Low: two new empty tables, narrow transactional service, no financial schema rewrite. | One optional join; absent/cleared handling explicit, no row multiplication. |
| C. Append-only assignment history | Fits zero/one when latest ordered assignment, including clear, is authoritative. Corrections append. | Preserves decisions from introduction; actor and label-history policy still needed. | Medium: Category plus assignment log, per-Movement ordering, command identity and concurrency; current projection optional but adds synchronization. No financial backfill. | Latest-row subquery for every report/filter, or maintained current projection. Historical labels need further design. |
| D. Category/tag many-to-many | Models several simultaneous labels, not the chosen single group. Corrections add/remove edges; split allocation still absent. | No history from a join table alone. | Medium: taxonomy plus join constraints/services; history would add more. | EXISTS/distinct needed for overlapping filters; grouping can double count. |
| E. Category plus current assignment and append-only revisions | Separates simple current reads from explicit past decisions. Corrections atomically update and append. | Strong assignment audit from introduction; no automatic label/actor history. | Highest here: three tables and projection/history consistency, ordering, replay and concurrency obligations. No financial rewrite. | Straight current join plus dedicated historical queries. |

| Alternative | Future Household ownership | Future AI/rules |
| --- | --- | --- |
| A | Scope Category later and validate it against Movement's Account; the financial row remains the assignment write target. | Add origin/history around Movement; cannot recover old changes. |
| B | Scope Category later and validate the separate relation against Account; no fake owner to unwind. Legacy scope mapping still required. | Add proposal/actor/history design before enabling it; preserve current baseline without inventing history. |
| C | Scope Category and validate new log entries; historical references also require explicit legacy mapping. | Can retain each accepted decision, but requires proposal origin, human precedence, and actor rules; a log is not an engine. |
| D | Scope every category/tag and validate every edge; more cross-scope relationships. | Multiple labels do not solve proposal acceptance, conflicts, or audit; additional lifecycle needed. |
| E | Scope categories/current references/history consistently during an explicit migration. | Supports accepted-decision audit with efficient reads, but still needs proposal and precedence rules. |

## Rationale and consequences

B costs one optional join over A and avoids making ordinary organizational
edits updates to Movement. C or E would preserve useful history but add
ordering/replay or projection consistency for a currently manual-only label.
Classification does not decide whether an amount exists in canonical totals;
the stronger acceptance-history requirement of ADR-0009 does not automatically
apply to it. D solves a different cardinality problem and makes household
grouping ambiguous without an allocation policy.

The accepted cost is loss of prior organizational decisions. Revisiting this
choice later is possible, but retroactive history is impossible. Category
regrouping for past periods reflects current assignments, while unfiltered
canonical totals, provenance, and resolution history remain unchanged.

Income/expense and transfer interpretation remain later product capabilities.
This explicitly narrows the earlier MVP type list to category organization;
it does not claim category-only reports fulfill consolidated spending analysis.
All existing imports and the first persistence migration leave Movements
unclassified. Demo classification, transport changes, and write authorization
are separate follow-up decisions/tasks under the linked contract.
