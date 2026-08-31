# Current task

## Objective

Implement a narrow read-only canonical Movement reporting application service
for one trusted Account and inclusive date range.

## Current state

BCI Historical Current Account PDF v0.1 is implemented and validated. The
source-only contracts `bci_current_cartola_v0.1` and
`bci_recent_movements_v0.1` are frozen and implemented as pure source parsers
with synthetic tests and sanitized private validation. Current and Recent now
require trusted nonblank artifact identity and preserve it in field
provenance; Recent also records the selected Cargo or Abono source header and
coordinate. No stable cross-source identity rule or canonical Movement
correction has been frozen.

Canonical `Movement`, Account orientation, exact money validation, originating
RawRecord provenance, source-typed ImportBatch, and exact SourceArtifact
identity are implemented. Santander current-account and credit-card routes
already materialize validated canonical movements. BCI Historical may also
resolve reconciled observations conservatively. There is no query/reporting
application service, HTTP API, or frontend.

The one-time T2 paired challenge is complete. T2 Current has 27 parsed rows and
an exact 26-step balance chain. Every contemporaneous T2 Recent accounting-date
candidate has exactly one Current candidate; Recent's other 23 rows are older
than Current's parsed range. Recent remains at 50 rows while its oldest
boundary advances, strongly supporting a rolling fixed-size shape without
proving a service cap. One shared T1/T2 Current candidate signature changes
description, opaque series, and row balance; it remains unresolved source
volatility rather than a transaction identity. BCI emits only three Historical
statements per year, so rollover validation is deferred until a naturally
available statement's printed period covers the retained Current dates.

## Constraints

Use only accepted canonical `Movement` rows. Preserve exact Decimal semantics
and Account isolation. Do not add migrations or writes. Do not infer income,
expense, refund, fee, adjustment, transfer, household flow, cross-source
identity, deduplication, lifecycle, or provisional meaning from sign or source
fields.

## Next action

Design and implement one internal application service that:

- validates a trusted Account and inclusive date range;
- lists only canonical Movements in deterministic documented order;
- returns an exact Decimal net signed account-effect total and count;
- returns safe provenance identifiers and source kind/variant/parser and
  reconciliation status without artifact bytes, filenames, raw cells, or other
  private source payloads; and
- proves through PostgreSQL-backed tests that Account/date filtering is exact,
  unresolved or rejected observations never affect results, asset and
  liability signs retain the same canonical meaning, and repeated queries are
  deterministic.

Expected implementation areas are a small module under
`gouda/ledger/services/`, focused tests under `tests/ledger/`, and only the
minimum architecture/state documentation warranted by the final boundary.
Do not add DRF/HTTP, authentication, UI, classification/category models,
transfer pairing, BCI routes, persistence changes, or correction behavior.

Recommended reasoning level: Sol Medium.
