# ADR-0007: Santander TDC import lifecycle and account binding

- Status: Accepted
- Date: 2026-08-25

## Context

ADR-0006 established source-neutral artifact, raw-record, and movement
boundaries plus Santander TDC-specific evidence persistence. The frozen
Santander TDC parser v1.1 now needs a synchronous application service that can
verify a target card account and atomically create canonical movements.

The source provides a masked card suffix, but four digits are not globally
unique and cannot serve as canonical account identity. Automatically trusting
the first imported PDF would allow an initial wrong-account selection to
establish a false association.

## Decision

### Explicit Santander binding

Each import target must have an explicit `SantanderTdcAccountBinding` created
before import. It is one-to-one with a `CREDIT_CARD` / `LIABILITY` account and
stores exactly four ASCII decimal characters. The suffix is not globally
unique. It is a source-verification value, not an external or canonical
Account identifier.

Binding configuration is explicit and never reads a PDF. Repeating the same
configuration is idempotent; a different value fails without overwrite.
Automatic first-import binding and card-reissue/rebinding workflows are
excluded.

The parser's structured `card_last_four` must match the persisted binding
before any source evidence or movements are written. A mismatch is a sanitized
`FATAL` boundary failure. Cards sharing the same final four remain
indistinguishable by this source evidence; explicit Account selection remains
necessary.

### Synchronous lifecycle

The service registers the exact artifact and a `PROCESSING` attempt in a short
transaction, then performs PDF extraction, GIR construction, and parser v1.1
execution outside database transactions. The Santander boundary validates and
deterministically prepares the complete parser graph before materialization.

Materialization locks Account, binding, then ImportBatch. It revalidates the
trusted account/binding and the attempt, rechecks canonical artifact/account
identity, then persists batch evidence, every raw/evidence record, every
eligible movement, reconciliation, counts, and terminal status atomically.
No parser or extractor runs while a database lock is held.

If materialization fails, its transaction rolls back the complete graph. A
fresh transaction records a sanitized durable `FATAL` attempt with zero counts
and null reconciliation. If truthful compensation cannot be persisted, the
service raises a sanitized operational error.

### Canonical movement projection

Every `PARSED` current-billed record in the frozen source categories creates
one `Movement`:

```text
occurrence_date = transaction_date
signed_amount = -debt_effect
currency = billed_currency = Account.currency
description = description_detail
source_reference = reference_authorization
running_balance = null
```

Original foreign money, source category, installment evidence, and source
debt effect remain Santander evidence. No FX conversion, exchange rate,
classification, or transfer relationship is inferred. Parsed unbilled records
are a boundary contradiction; legitimate unbilled records remain ignored.

### Status, reconciliation, and duplicates

Row outcomes determine `ACCEPTED`, `PARTIAL`, or `REJECTED`; ignored records do
not cause `PARTIAL`. Reconciliation is validated and persisted independently.
`NOT_RECONCILED` does not discard otherwise valid movements.

Materialized uniqueness remains `(SourceArtifact, Account)`. Same-route exact
reimports become direct duplicates. A materialized different route produces
`FATAL/BOUNDARY/source_kind_conflict`. Fatal history does not block a later
correct attempt, and parser version is not duplicate identity.

## Consequences

The application service now creates auditable canonical liability-account
movements while keeping provider evidence outside `Movement`. Same-account
materialization is serialized without holding locks during parsing. Different
accounts can progress independently.

Four-digit collision risk is contained but not eliminated. Stronger external
card identity, automatic binding, reissue handling, parser supersession,
classification, transfer pairing, installment plans, FX, BCI, and asynchronous
processing require later decisions.
