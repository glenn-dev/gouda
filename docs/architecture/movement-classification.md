# Movement classification

## Status

Accepted MVP design, 2026-09-05; persistence and services are not implemented.
[ADR-0011](../decisions/ADR-0011-movement-classification.md) freezes the
cardinality, ownership, correction, and persistence decisions. This document
defines the concrete contract for the next implementation checkpoint.

## Domain boundary

Classification is an explicit, revisable Gouda category assignment to an
already accepted canonical Movement. It organizes account effects by a chosen
household-finance topic. It does not accept evidence, establish an economic
event, or change any financial fact.

| Concept | Meaning and owner |
| --- | --- |
| Signed account effect | `Movement.signed_amount`: positive increases the referenced Account's contribution to household net worth; negative decreases it. |
| Economic meaning | Whether an event is income, spending, a refund, a transfer, or an adjustment; requires context beyond sign and is deferred as a persisted type. |
| Category | One optional Gouda grouping, such as a synthetic `Groceries` label; has no sign, account-orientation, or flow-type constraint. |
| Transfer relationship | Future relationship between own-account effects of a shared event; pairing and consolidated-flow treatment are separate from category. |
| Provider metadata | Source sections/categories, parser outcomes, and source-native direction remain evidence under frozen adapter contracts. |
| User annotation | A possible future note or tag; not an imported description, category, or field of this classification design. |

Gouda's accepted category is authoritative for its current grouping only. It
does not claim the same evidentiary authority as an accepted financial amount.
Neither a description, signed amount, provider category, nor `DEMO_SYNTHETIC`
creates an assignment. Assignments attach only to persisted Movements, never
to unresolved observations or source records.

## Existing constraints

The verified implementation baseline is `76a1647ab005175418e7b7175fc3e3ec9abb3589`
(`feat: add local demo bootstrap`).

- Account has UUID, display name, kind, economic orientation, and currency.
  Only `CURRENT` / `ASSET` and `CREDIT_CARD` / `LIABILITY` are supported.
  There is no User, Household, owner, or persisted principal.
- Movement has a UUID, required Account and one-to-one originating RawRecord,
  occurrence date, nonzero exact `Decimal(20,2)` amount, currency, and optional
  description, source reference, and running balance. Account/date is indexed.
  Source/account/currency consistency is validated at the model/service
  boundary; local amount/currency constraints also exist in PostgreSQL.
- FinancialObservation claim immutability and append-only resolution history
  protect acceptance and interpretation correction. Movement correction is
  deferred. Movement itself has no general immutable-save override or database
  update prohibition; do not claim classification introduces one.
- Santander XLSX materializes validated asset effects; Santander TDC maps
  `signed_amount = -debt_effect`. TDC section categories remain evidence.
  BCI Historical imports unresolved observations and resolves eligible
  reconciled rows through its separate deterministic policy. BCI Current and
  Recent remain source-only parsers. None assigns a Gouda category.
- Reporting reads persisted Movements for one trusted Account and inclusive
  occurrence dates, ordered by date/UUID, with exact signed total and bounded
  source trace. Observation state never filters the canonical query set.

See [Domain model](domain-model.md), [ADR-0005](../decisions/ADR-0005-canonical-movement-sign-orientation.md),
[ADR-0007](../decisions/ADR-0007-santander-tdc-import-lifecycle-and-binding.md),
and [Evidence and resolution](evidence-resolution.md).

## Cardinality and unclassified meaning

Choose zero or one Category per Movement across the local dataset.

| Alternative | Assessment |
| --- | --- |
| Exactly one | Forces a guess or a sentinel category for every import; obscures unclassified work. Rejected. |
| Zero or one | Keeps every accepted Movement reportable before classification and produces disjoint category groups. Chosen. |
| Multiple categories/tags | Overlapping groups double count without separate allocation semantics. Tags do not implement split transactions. Deferred. |
| Category plus orthogonal tags | Could support projects or occasions, but adds a second labeling vocabulary and query contract without an MVP need. Deferred. |

Uncategorized is absence of a current category, never a Category row. No
`Uncategorized`, `Unknown`, or `Unclassified` sentinel is provisioned. A later
deliberately defined `Other` category would be an intentional grouping, not
missing work; this checkpoint seeds neither it nor a default taxonomy.

No classification row means no classification command has changed this
Movement. A retained row with null category means a prior assignment was
cleared. Both are unclassified for reporting. This distinction does not mean
reviewed, approved, rejected, or permanently exempt from classification; no
review workflow/state is introduced.

## Category

Categories belong to the local database dataset and may be used across its
Accounts and currencies. They are neither universal application constants nor
temporarily global Household rows. No dataset table, fake owner, null
household foreign key, or ownership backfill is introduced.

| Field | Persistence and semantics |
| --- | --- |
| `id` | UUID primary key generated by Gouda; stable through label edits and retirement. |
| `display_name` | Required string, maximum 80 characters; a short controlled topic label, trimmed and nonblank, without control characters. |
| `is_active` | Required boolean, default true; retirement prevents new assignments while preserving existing ones and their reports. |

Use a case-insensitive unique display name within this dataset, including
inactive rows, with database uniqueness on `Lower(display_name)` and service
validation of whitespace/control characters. UUID is identity; names are not
selectors. Database collation determines case folding; do not claim universal
Unicode synonym detection. Presentation ordering is deferred; there is no
persisted sort order or category-ordering contract in this checkpoint.

No machine code is needed without a fixed application taxonomy, integrations,
or localization contract. No parent is needed without rollups; no sort order
is needed without curated presentation. All three are deferred, as are tags,
category descriptions, economic types, colors, icons, and arbitrary metadata.

Trusted explicit provisioning may create a few reviewed topic labels later;
there is no category-management UI/API or source-driven creation. Cosmetic
renames preserve identity and affect current reports of old dates; repurposing
a category's meaning is forbidden. Use a new UUID for a different meaning.
Supported retirement uses `is_active=false`, never deletion or reassignment of
existing references. Reactivation preserves the same meaning and UUID.

## Current assignment

Choose a separate `MovementClassification` current-state model:

| Field | Persistence and semantics |
| --- | --- |
| `movement` | Required one-to-one to Movement, also primary key, `on_delete=PROTECT`. Its UUID identifies the classification resource; no extra assignment UUID. |
| `category` | Nullable foreign key to Category, `on_delete=PROTECT`, indexed; null only represents a cleared assignment in a retained row. |
| `source` | Required constrained string, maximum 16 characters; only `MANUAL` is supported. Describes the last actual category change, including clearing. |
| `revision` | Positive big integer, starts at 1 and increments on actual changes; optimistic concurrency token, not history. |
| `updated_at` | Required timezone-aware server timestamp of the last actual change. Not a financial occurrence date. |

There is no category or mutable classification field on Movement, and no
duplicated Account, amount, currency, date, raw-record reference, or financial
snapshot on the assignment. No assignment history table exists.

Classification changes must never alter Movement's `signed_amount`,
`occurrence_date`, Account, currency, originating RawRecord, description,
source reference, running balance, or any source/provenance or import state.

Database constraints enforce one row per Movement, valid foreign keys,
`source=MANUAL`, and `revision >= 1`. The supported service enforces allowed
transitions, immutable Movement reference, active category selection, revision
increments, and server timestamps. Ordinary model writes must validate the
local shape and reject reparenting; only the service supports corrections.
Direct SQL and bulk ORM updates are outside that application boundary, as in
the observation design. They are not authorized correction paths.

## Manual provenance and corrections

`MANUAL` means an explicit category choice or clear command by the trusted
local operator. It does not identify a persisted User, record the origin of
the Movement, or certify that source evidence was manually entered. The
service supplies this value; source/model payloads cannot claim it.

Store source now because even a single supported origin makes the manual-only
write contract explicit and avoids treating a future unknown origin as manual.
`RULE`, `AI`, `IMPORTED`, and `SYSTEM` are not valid stored choices now.
Provider classifications remain evidence; deterministic imports and seed
commands are not manual decisions merely because a person launched them.
Future human acceptance of a machine suggestion must first define how proposal
origin and human acceptance are distinguished; do not erase that provenance.

The future transport-independent command accepts a trusted persisted Account,
a Movement UUID scoped to that Account, a Category UUID or null, and required
`expected_revision` (0 for an absent row). It accepts no financial fields,
source string, timestamps, notes, or arbitrary update dictionary.

Within one transaction, lock Account then Movement, re-fetch any current
classification, and compare the expected revision before considering a no-op.
Account locking follows the existing import/resolution ordering and also
serializes first assignment when no classification row exists. Lock and
revalidate a non-null target Category after those locks; category retirement
must coordinate on that Category lock. Independent Accounts can proceed unless
they contend for the same category. A stale revision fails without overwrite.
The revision check and resulting write must remain in this locked transaction;
a non-atomic Python read/check/save sequence does not satisfy the contract.

- First non-null assignment creates revision 1.
- Replacing or clearing an assigned category updates only classification,
  increments revision, and updates source/time. Clearing retains the row.
- Assigning after clear increments the retained revision; it never resets it.
- Repeating the current category or clearing an already unclassified Movement
  with the correct revision is a no-op, with no timestamp change or new row.
  Retaining an already assigned inactive category is permitted as a no-op;
  selecting it as a new assignment is rejected.

An old request cannot silently overwrite a newer decision, including an
assign/clear/reassign cycle. This is state-based concurrency, not durable
command-key replay: after an ambiguous response, the caller reads current
state and reconciles before retrying. No idempotency-log framework is added.

Corrections overwrite current category/source/time. Previous categories,
timestamps, and actors are not recoverable; revision alone is not an audit
trail. Reports for a past financial period use today's assignment and label,
so regrouped results may change after an edit. No as-of-classification or undo
promise is made. Exact canonical totals and evidence history remain intact.

This narrower mutable policy is adequate for explicit manual organization.
Observation resolution deserves stronger history now because it determines
which financial facts are accepted. Before rules, AI, imported assignments,
automated replacement, bulk edits, audit/undo, or as-of reports, revisit
append-only assignment history and actor/proposal provenance. A future
migration can capture current state as a baseline, but cannot reconstruct
overwritten assignments or label history and must not fabricate them.

## Transfer and economic-type boundaries

Do not provision or use a `Transfer` category as an MVP workaround, including
a presentation alias that would imply pairing or exclusion. Transfer semantics
are deferred. A known own-account payment can remain unclassified. Future
verified relationship presentation may display transfer status independently
of any topic category; category membership never pairs or excludes rows.

MVP classification contains category only, with no income/expense flag and no
economic-event type on either Category or assignment. The following synthetic
examples explain why:

| Known context | Signed effect | What classification may claim |
| --- | --- | --- |
| Asset receives own-account transfer | Positive | Not proof of income; requires a future relationship. |
| Card purchase | Negative liability effect | A topic may be assigned explicitly; sign alone does not establish spending. |
| Payment from current account to own card | Negative asset side, positive liability side | Payment is not a second expense or income; no pair is inferred from matching values. |
| Grocery purchase and confirmed grocery refund | Negative purchase, positive refund | Both may explicitly use the same topic; net category effect is not gross spending or income. |
| Reversal or unexplained balance adjustment | Either sign | Do not guess type or category; unclassified remains valid. |

Categories do not establish refund/reversal linkage, ownership, transfer
identity, allocation, or cash-flow semantics. Economic types and consolidated
income/spending reporting require a later event/relationship decision with
transfer, refund, reversal, liability, and currency treatment. Category-only
MVP still supports useful account/date grouping and finding unclassified work.

## Reporting and API evolution

No existing service result, HTTP parameter, serializer, or frontend changes in
this design or the first persistence checkpoint. The current two GET routes
retain their [documented contract](local-http-delivery.md).

A later bounded read extension may add one `classification` object to each
Movement item: `category` (null or `{id, display_name, is_active}`), `source`,
`revision`, and `updated_at`. Absent rows project category/source/time as null
and revision 0; cleared rows have null category, `MANUAL`, positive revision,
and last-change time. Thus current state can be read without exposing ORM or
source evidence. This is an illustrative candidate shape, not a frozen response
schema. ADR-0011 freezes only current-category reporting semantics and mutually
exclusive category/unclassified selection; field names, query spelling, and
transport errors require the later reporting/API checkpoint.

For that later checkpoint, a candidate interface is one `category_id` UUID or
`uncategorized=true`, mutually exclusive. Omission would mean all categories and
unclassified rows. Reject malformed, duplicate, unsupported, and conflicting
selectors; do not overload an empty string or sentinel UUID. Uncategorized
selects absent rows OR null category. Category filtering includes existing
assignments to inactive categories. A valid accessible category with no rows
returns an empty report; unknown or inaccessible categories share one safe
not-accessible result. Transport status/error details belong to that later
API checkpoint.

Resolve Account access before category lookup; UUID possession is not access.
Categories inherit dataset visibility only under the existing trusted local
read policy. Write authorization is separate: the current read principal and
loopback runtime do not grant HTTP classification writes. Any write endpoint
must revisit [ADR-0010](../decisions/ADR-0010-loopback-only-local-mvp-delivery.md)
and define a capability-specific write boundary first.

Use a left join to current classification so no Movement disappears or is
duplicated. Category-filtered count and exact Decimal total cover precisely
the returned tuple. Preserve date/UUID order, currency boundaries, and bounded
source trace. Read financial and classification projections in one consistent
query; do not issue a separate aggregate that may race with a correction.
Including the unclassified group makes category buckets a disjoint partition
of the same Account/date report. Label every total as signed account effect,
never income, spending, or consolidated cash flow. Do not sum mixed currencies.
Assignments do not change unfiltered Movement membership, counts, or totals.

## Migration and demo sequence

The next persistence task adds two empty tables and their constraints/indexes
after `0010_demo_synthetic_provenance` (expected migration `0011`, subject to
the actual graph leaf). It does not alter Account/Movement tables or source
choices. No category seed, financial rewrite, assignment backfill, or inferred
classification is allowed. Existing and newly imported Movements start
unclassified. Reverse migration should fail closed if either new table has
data; removing classifications requires a separate explicit data-loss decision.

`seed_demo` currently creates two CLP Accounts and eleven independent
Movements over January-April 2026, with March empty. Its repeated/nearby values
and synthetic descriptions do not establish shared events. Leave
[demo_data.py](../../gouda/ledger/demo_data.py) unchanged and classification-free
through the first persistence task. `DEMO_SYNTHETIC` remains source provenance.

Once persistence exists, a separate demo extension should include a small,
explicit, deterministic category mapping keyed by fixed demo Movement IDs,
with some examples deliberately unclassified. Do not infer assignments by
description or amount or present them as manual. That extension must first
introduce its source semantics through a separate explicit decision, including
validation and migration. No future source name or value is chosen or reserved
by this checkpoint. Repeated seeding must preserve subsequent
manual choices and cleared states. Category/assignment cleanup must validate
the fixed demo graph and protect categories referenced outside it.

With the proposed `PROTECT` Movement relationship, existing `clear_demo`
will fail atomically if a demo Movement has a classification row, including
a cleared row. Retain and test that conservative behavior in the first
persistence task; extending cleanup is part of the later demo task. Do not
add cascading financial deletion to make cleanup convenient.

## Privacy and ownership revisit

No free-form notes, category description, source payload, provider reference,
account/card identifier, merchant detail, filename, or arbitrary JSON belongs
in Category or classification. Labels must be explicitly reviewed general
topics; never copy raw bank descriptions or source categories into labels.
Length/shape validation cannot prove a string lacks sensitive data, which is
why unrestricted category authoring is not part of the MVP boundary.
Assignments and labels are still sensitive financial metadata: use safe IDs
and error codes in logs, exclude labels from exception messages, and apply
Account/dataset access controls to reports. No external AI disclosure occurs.

Revisit scope before a second independent principal, different Account or
category visibility, individual/shared Accounts, household membership,
cross-dataset import/merge, or persisted grants. That design must explicitly
map legacy categories to the new scope, decide whether shared labels are
copied or mapped, scope name uniqueness, and enforce assignment compatibility
with the Movement's Account scope transactionally. Existing global references
cannot imply ownership or authorization. Stable UUIDs help migration but do
not determine that policy.

## Explicit non-goals

Classification UI, HTTP writes, API filters or response changes, category
management, large default taxonomy, notes, tags, hierarchy, split amounts,
rules/AI/heuristics, imported assignments, transfer pairing, EconomicEvent,
income/expense types, bulk editing, assignment/label history, canonical
financial correction, User/Household persistence, new adapters, and demo code
changes are outside this design checkpoint.
