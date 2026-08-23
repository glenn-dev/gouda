# ADR-0003: Establish the v0.1 import/persistence boundary

- Status: Accepted
- Date: 2026-08-23

## Context

Gouda has a frozen Santander Parser Contract v0.1 implemented as an isolated
pure-Python parser. The next slice needs durable PostgreSQL persistence while
keeping parser interpretation separate from Django concerns.

The product requires the original artifact, its immutable row interpretation,
and canonical signed movements to remain traceable. The first implementation
supports one Santander source and does not yet have users, households, an API,
or a reprocessing framework.

## Decisions

### Django boundary

Use a minimal top-level `config/` Django project and a single `gouda.ledger`
application. `gouda.santander_parser` remains pure Python and is not modified
or made aware of Django.

DRF is deferred until an API task. Financial models are not registered in
Django admin in this slice.

### Persistence entities

Implement `Account`, `SourceArtifact`, `ImportBatch`, `RawRecord`, and
`Movement`.

`SourceArtifact` stores the exact received XLSX bytes in PostgreSQL, its
SHA-256 digest, the first-seen filename basename, source kind, and receipt
time. The import boundary computes the digest. Identical bytes resolve to one
artifact; digest conflicts are compared by bytes and fail closed if the bytes
differ.

`RawRecord` is immutable and retains every parser row outcome. `Movement` is
created only for `PARSED` rows and has a one-to-one relationship with its raw
record. Movement deduplication by transaction values is explicitly forbidden.

### Batch lifecycle and materialization

`ImportBatch` supports `PROCESSING`, `ACCEPTED`, `PARTIAL`, `REJECTED`,
`FATAL`, and `DUPLICATE`.

`REJECTED` means the workbook was structurally interpretable but produced
rejected movement candidates without valid movements. It is not a workbook or
persistence failure.

At most one successfully materialized interpretation may exist for a
`SourceArtifact` and `Account`. This database uniqueness rule deliberately does
not include parser version. Parser version remains immutable provenance on each
attempt. Fatal and duplicate attempts may coexist. Future reprocessing and
supersession semantics require a separate decision.

Materialization of raw records, movements, reconciliation evidence, counts,
and final batch state is atomic. Artifact registration and the processing
attempt survive a fatal parser error.

PostgreSQL constrains nonnegative counts and the materialized status/count
relationships, including the valid accepted zero-movement case. Duplicate
target identity (same artifact and account, finalized materialized target) is a
cross-row invariant enforced by model validation and must be revalidated
transactionally by the future import service.

### Monetary representation

Monetary fields use `DecimalField(max_digits=20, decimal_places=2)`. A small
explicit validator rejects non-finite, over-precision, and over-magnitude
`Decimal` values without quantizing them. PostgreSQL `numeric(20,2)` alone can
round excess fractional places, so the future import boundary must call or
obey this validator before any financial persistence. The parser is not
changed to impose this database constraint.

### Parser version naming

The contract label `v0.1` and the implementation value
`PARSER_VERSION = "santander-v0.2"` are distinct concepts in this baseline.
Persistence stores the exact implementation value and does not rename the
parser constant.

### Privacy

Filenames, digests, artifact bytes, worksheet names, raw cells, descriptions,
references, amounts, and balances are sensitive. They are not logged or
exposed through an API. Internal UUIDs and stable error codes are used for
operational references.

## Consequences

The first schema is intentionally explicit and small. It provides durable
provenance and database-backed duplicate protection without introducing a
generic importer, event system, correction model, or reprocessing framework.

Foreign-key, one-to-one, digest, amount-shape, lifecycle, and uniqueness rules
that can be expressed locally are database-enforced. Cross-row duplicate
identity and movement account/currency/raw-outcome consistency remain
model/service-enforced because they require related-row context.

The PostgreSQL binary artifact column is appropriate for this initial local
scope but may require a later retention or storage decision as volume grows.
