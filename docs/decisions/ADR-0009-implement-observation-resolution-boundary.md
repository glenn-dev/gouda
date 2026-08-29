# ADR-0009: Implement the observation and resolution boundary

- Status: Accepted
- Date: 2026-08-29

## Context

[ADR-0008](ADR-0008-separate-observations-from-canonical-movements.md)
established that provisional or heterogeneous interpretations must remain
separate from canonical `Movement`. BCI Recent Movements, Current Cartola, and
Historical Cartola may overlap without a proven universal transaction
identifier. The existing one-to-one `Movement.raw_record` provenance is valid
for the deterministic Santander routes but cannot alone express unresolved
claims or several source observations supporting one Movement.

The smallest durable implementation must add interpretation and resolution
state without changing canonical movement semantics, rewriting Santander, or
introducing a generic evidence or workflow framework.

## Decision

### Immutable FinancialObservation claim

`FinancialObservation` stores one interpreted financial claim derived from one
parsed `RawRecord`. It retains the trusted Account, transaction and accounting
date candidates, exact signed amount and currency, optional description and
source reference, and interpretation method/version.

At least one financial date is required. Money, currency, source/account
compatibility, and nonzero amount are validated deterministically. Claim
fields are immutable after creation through the supported application service
and ordinary model-save boundary. Direct SQL, `QuerySet.update()`, and
`bulk_update()` are outside that write boundary. A corrected interpretation
creates a new observation; it never edits the prior claim.

Observation creation uses a required unique UUID idempotency key. The schema
does not use `(RawRecord, interpretation method, interpretation version)` as
identity because the same interpreter version may legitimately produce a new
human-directed or corrected interpretation. Reusing an idempotency key is
accepted only when the entire normalized claim is identical.

### Mutable current resolution projection

Only the observation's current lifecycle projection is mutable:

- state;
- optional current Movement; and
- monotonically increasing state version.

States are `UNRESOLVED`, `RESOLVED`, `REJECTED`, `CONFLICT`, and terminal
`SUPERSEDED`. The implemented transition table is:

| Action | From | To | Movement | Successor |
| --- | --- | --- | --- | --- |
| `CONFIRM_NEW` | `UNRESOLVED` | `RESOLVED` | required, newly created | none |
| `MATCH_EXISTING` | `UNRESOLVED` | `RESOLVED` | required, existing | none |
| `REJECT` | `UNRESOLVED` | `REJECTED` | none | none |
| `MARK_CONFLICT` | `UNRESOLVED`, `RESOLVED` | `CONFLICT` | required | none |
| `REOPEN` | `REJECTED`, `CONFLICT` | `UNRESOLVED` | prior conflict target retained only in history | none |
| `SUPERSEDE` | any non-superseded state | `SUPERSEDED` | prior target retained only in history | required |

The successor for `SUPERSEDE` must be a fresh unresolved observation for the
same RawRecord and Account with a changed claim or interpretation identity.
`CONFLICT` specifically means an observation conflicts with a known canonical
Movement. Ambiguity without a known Movement remains `UNRESOLVED`.

### Append-only ObservationResolution history

`ObservationResolution` records each accepted transition with an observation
sequence, action, from/to state, optional Movement, optional successor,
decision source, named/versioned policy, stable reason code, UUID idempotency
key, and creation time.

Resolution history is append-only through the application boundary. It
contains no confidence, authority score, arbitrary metadata, AI details,
generic evidence, or Movement snapshots.

### Canonical Movement and originating RawRecord

`Movement` remains canonical-only. `Movement.raw_record` remains required and
one-to-one and means the RawRecord from which the Movement was originally
materialized. It is not necessarily the only evidence supporting that
Movement. Additional support is represented by observations resolved to it.

No `MovementEvidence` or `ObservationEvidence` model is introduced.

`CONFIRM_NEW` creates one Movement atomically from the observation. The caller
supplies which of the observation's exact dates is the canonical occurrence
date. After locking the Account, the service abstains when an exact
account/date/amount/currency candidate already exists. This is a collision
guard, not a universal economic-event identity rule. The caller may explicitly
override the guard only after independently establishing that the candidate is
a distinct event. The override creates a second Movement; it never attaches to
the colliding Movement. Decision source, policy version, and reason code retain
the decision context.

`MATCH_EXISTING` validates an explicitly supplied Movement using exact Account,
currency, and signed amount compatibility. It does not select candidates or
determine economic identity. Dates, descriptions, references, periods, and
other evidence belong to source-specific matching policy and are not generic
hard identity fields. No fuzzy matching is implemented.

### Transactionality and concurrency

Resolution commands lock Account, observation, and any Movement in that order,
then re-read lifecycle and candidate state. Same-account competing creation is
serialized; a second exact candidate abstains instead of creating a duplicate.
An explicit distinct-event override is evaluated only after that lock and
re-read. Successor lookup is scoped to the predecessor Account before acquiring
the successor row lock. Different accounts do not share a global lock. Database
constraints provide defense in depth for lifecycle shapes, sequences, and
idempotency.

### Santander compatibility and migration

The Santander current-account and credit-card services are unchanged. Their
direct deterministic materialization remains valid. Migration 0008 creates
empty observation and resolution tables and does not rewrite, reinterpret, or
backfill existing Santander data or Movements.

### Explicitly deferred canonical correction

This decision supports interpretation correction only through observation
supersession. It does not implement Movement value correction, snapshots,
retraction, deletion, zeroing, or supersession. A contradiction involving an
existing Movement is recorded as `CONFLICT` without altering the Movement.
Canonical correction requires a later decision grounded in real corrected
source evidence.

## Consequences

- Unresolved, rejected, conflicted, and superseded interpretations remain
  outside canonical totals.
- Multiple observations can support one Movement without weakening its
  originating provenance.
- Resolution decisions are explainable and idempotent without a universal
  confidence or identity model.
- BCI source contracts, parsers, matching policy, and ingestion remain future
  work.
- Existing Santander behavior and historical values remain unchanged.

## Rejected alternatives

- A many-to-many replacement for `Movement.raw_record`.
- `MovementEvidence`, `ObservationEvidence`, or `EconomicEvent` tables.
- Provisional state or confidence on `Movement`.
- Accidental interpretation identity from RawRecord plus method/version.
- Fuzzy matching or date/amount/description as universal identity.
- Canonical Movement correction before corrected-source evidence exists.
- Generic authority, workflow, rule, processing-run, agent, or evidence-graph
  abstractions.
