# ADR-0006: Generalize import persistence evidence

- Status: Accepted
- Date: 2026-08-25
- Supersedes: the source-kind placement in ADR-0003 and ADR-0004

## Context

The first persistence boundary was intentionally shaped around Santander
current-account XLSX imports. Santander credit-card PDF parser v1.1 now
provides auditable document, record, and geometric provenance that cannot be
represented as spreadsheet rows or columns. The persistence boundary must
accept that evidence without changing canonical movement semantics or adding a
generic parser/provider framework.

## Decision

### Artifact and interpretation identity

`SourceArtifact` identifies exact received bytes. It stores the global SHA-256
digest, first-seen filename, bytes, and receipt time, but no source format.
Identical bytes remain one artifact regardless of the route used to interpret
them.

Required `ImportBatch.source_kind` identifies the interpretation route. The
closed set is currently Santander current-account XLSX and Santander
credit-card PDF. At most one canonical materialized graph may exist for an
artifact and account. A later attempt through the same source kind is a
duplicate; a later attempt through a different source kind is a fail-closed
source-kind conflict. Failed attempts are not materialized and therefore do
not prevent a later correct route from succeeding. Parser version remains
provenance rather than deduplication identity.

### Shared raw-record envelope

`RawRecord` remains the common record identity and outcome envelope. Required
`record_kind` identifies its source-specific evidence shape, and positive
`record_ordinal` is unique within the batch. XLSX uses the source row number;
PDF uses the one-based position in `TdcPdfParserResult.records`. PDF page,
section, row-group, line, and token coordinates are evidence, not identity.

The existing `row_number`, `raw_cells`, and `row_class` fields are retained as
nullable XLSX-only fields. `xlsx_amount_source_column` stores parsed XLSX E/F
provenance on the raw record. PDF records must not populate any of these
spreadsheet fields.

### Santander TDC evidence

One `SantanderTdcPdfBatchEvidence` belongs to a Santander TDC batch and stores
document metadata, card suffix, extractor/GIR/provenance versions, metadata
provenance, reconciliation provenance, missing operands, and the explicit
source-specific reconciliation operands not already represented by generic
batch balances and difference.

One `SantanderTdcPdfRecordEvidence` belongs to each Santander TDC raw record.
It stores source outcome evidence, geometric ordinals and provenance,
transaction facts, billed and original amounts/currencies, category,
source-native debt effect, installment evidence, and header profile. Variable
ordinal and field-provenance structures use strictly versioned JSON; source
facts with stable scalar shapes remain relational. Geometry decimals are JSON
strings, never binary floats. No page/line/token tables are introduced.

### Canonical movement boundary

`Movement` contains canonical account-effect facts only. XLSX column E/F is
removed from it. Original foreign evidence, Santander category, installment
facts, and source-native debt effect remain TDC source evidence. This
checkpoint creates no TDC movements; a later source adapter will map
`transaction_date` to `occurrence_date` and, for a liability card, set
`Movement.signed_amount = -debt_effect` in the trusted account currency.

No classification, transfer pairing, installment plan, FX conversion, source
account binding, or TDC import lifecycle is part of this decision.

## Migration and reversibility

The migration first adds nullable target fields, validates all historical
source kinds and XLSX shapes, then backfills batch source kind, raw-record
identity, and XLSX amount-column evidence. Only after validation are required
fields and final constraints applied and obsolete artifact/movement fields
removed. Existing artifacts, raw cells, outcomes, movements, signed amounts,
currencies, balances, references, and reconciliation facts are not rewritten.

Reverse migration fails closed if TDC batches/evidence exist or if an
artifact's old source kind cannot be recovered unambiguously. It does not
invent an artifact source kind or discard PDF evidence silently.

## Consequences

The existing current-account service changes mechanically at persistence
calls but retains its parser, lifecycle, duplicate behavior, locks,
reconciliation, and canonical values. The TDC parser contract can now be
projected synthetically for persistence tests without creating artifacts,
calling extraction/parsing, implementing duplicate lifecycle, or creating
movements.

Source-specific evidence models are preferred over one permissive generic JSON
record because their ownership and scalar invariants remain explicit. Fully
relational geometric provenance is rejected because it would multiply tables
without a current query or integrity requirement.
