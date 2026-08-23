# Handoff

## Objective

Gouda v0.1 — establish the first Santander current-account import-service
boundary checkpoint without implementing the end-to-end service.

## Frozen baseline

Santander Parser Contract v0.1 is frozen. The approved baseline is validated
against three monthly private Santander source samples and the 29-test synthetic
XLSX suite. Frozen means current behavior is intentional; unsupported source
variants require an explicit contract revision.

## Boundary decisions

ADR-0004 separates three provenance facts:

- source kind remains `SourceArtifact.SourceKind.SANTANDER_CURRENT_ACCOUNT_XLSX`;
- source variant is nullable `ImportBatch.source_variant`, with approved value
  `v1` after successful recognition;
- parser implementation version remains the frozen parser's existing constant.

Materialized and duplicate batches require a source variant. Processing and
fatal attempts may have a null or recognized variant. The variant belongs to
the attempt because recognition happens after artifact registration.

Santander v1 recognition is explicit and fail-closed. Known commission-summary
and post-summary markers are optional, but their structure and order must be
valid when present. Dangerous populated columns beyond G, incoherent result
graphs, and changed auxiliary boundaries followed by financial rows are not v1.
No source registry, plugin system, or generic importer abstraction exists.

## Implemented boundary

Migration `0003_importbatch_source_variant` adds the field and PostgreSQL
constraints that reject empty variants and require non-null variants for
`ACCEPTED`, `PARTIAL`, `REJECTED`, and `DUPLICATE` batches.

`gouda.ledger.services.santander_import` contains pure helpers for:

- deterministic tagged raw-cell serialization;
- exact movement and reconciliation money validation without rounding;
- batch-status derivation independent of reconciliation;
- whitelisted parser-error mapping;
- complete parser-result graph validation;
- Santander v1 structural recognition.

It intentionally contains no artifact registration, parser orchestration,
failure compensation, ORM materialization, concurrency handling, or logging.
The frozen parser was not modified.

## Frozen parser behavior

The parser uses a Santander-specific section state model:

- `PRE_MOVEMENT`
- `MOVEMENT_DETAIL`
- `COMMISSION_SUMMARY`
- `POST_SUMMARY`

Exact standalone normalized markers are `resumendecomisiones` in column C and
`mensajes` in column A. Financial-looking rows inside the commission-summary
section are `IGNORED` with `commission_summary`, produce no normalized movement,
and are excluded from reconciliation. The asterisk separator is auxiliary
structure, not a primary boundary. No transaction deduplication is used.

The parser also validates the supported seven-column layout, period-derived
dates, explicit row outcomes, signed Decimal amounts, negative/zero policies,
formula handling, provenance, redacted representations, worksheet selection,
and independent reconciliation statuses.

## Validation state

- Full Django/PostgreSQL and synthetic suite: 78 passed, 0 failed.
- Migration drift check: no changes detected.
- Django system check: no issues.
- Python AST validation: passed.
- `git diff --check`: passed.

Validation used only synthetic fixtures and an isolated PostgreSQL 16 test
container. No private source statements were accessed.

## Repository state

Finder `.DS_Store` files are ignored repository-wide and the previously
untracked artifacts were removed. Private sources, caches, secrets, local
databases, and generated artifacts remain excluded.

## Next development phase

Implement orchestration in the existing Santander service module:

1. trusted account and artifact/attempt registration;
2. duplicate detection before parsing;
3. parser invocation outside database transactions;
4. graph, variant, serialization, and exact-money validation;
5. atomic raw-record/movement/reconciliation materialization;
6. fatal compensation after rollback;
7. conditional-uniqueness race recovery.

Keep the parser frozen. Do not add REST, frontend, asynchronous processing,
other institutions, or generic importer abstractions.
