# Handoff

## Objective

Gouda v0.1 — checkpoint 2 implements the first end-to-end synchronous
Santander current-account XLSX import service.

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

## Implemented service

Migration `0003_importbatch_source_variant` adds the field and PostgreSQL
constraints that reject empty variants and require non-null variants for
`ACCEPTED`, `PARTIAL`, `REJECTED`, and `DUPLICATE` batches.

`gouda.ledger.services.santander_import` retains the checkpoint-1 helpers for:

- deterministic tagged raw-cell serialization;
- exact movement and reconciliation money validation without rounding;
- batch-status derivation independent of reconciliation;
- whitelisted parser-error mapping;
- complete parser-result graph validation;
- Santander v1 structural recognition.

The same Santander-specific module now exposes
`import_santander_current_account_xlsx(*, content, original_filename, account)`.
It accepts exact bytes and a persisted trusted current account, normalizes only
the artifact basename, hashes the unmodified bytes, and owns source kind,
parser version, variant, currency, and external parser account reference.
An invalid trusted database currency is rejected before artifact registration
with the stable safe code `account_currency_invalid`.

The service uses three short phases:

1. A registration transaction refetches and validates the account, resolves or
   creates the exact artifact, detects a sequential canonical duplicate, and
   otherwise commits a durable `PROCESSING` attempt.
2. The frozen parser, graph/variant/money validation, tagged raw serialization,
   and final-status derivation run with no database transaction or row lock.
3. A materialization transaction locks the account and this service's attempt
   in that order, revalidates context, checks again for a materialized target,
   and atomically writes every `RawRecord`, parsed `Movement`, reconciliation
   evidence, provenance, counts, variant `v1`, and final batch status.

Parser, boundary, and persistence failures use stable safe codes. Any failed
materialization rolls back before a fresh transaction locks the still-
`PROCESSING` attempt and records a durable `FATAL`. If compensation cannot be
persisted, callers receive only a sanitized Santander operational exception.
The service rejects invocation inside an existing transaction because such a
caller context cannot commit registration before openpyxl parsing.

Sequential duplicates skip parsing. The normal post-parse duplicate path also
finalizes directly to the canonical materialized target with zero canonical
rows and zero counts. Fatal attempts do not block later successful retries.
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

- Full Django/PostgreSQL and synthetic suite: 98 passed, 0 failed.
- Migration drift check: no changes detected.
- Django system check: no issues.
- Python compilation validation with an isolated cache: passed.
- `git diff --check`: passed.

Validation used only synthetic fixtures and an isolated PostgreSQL 16 test
container. No private source statements were accessed.

## Repository state

Finder `.DS_Store` files are ignored repository-wide and the previously
untracked artifacts were removed. Private sources, caches, secrets, local
databases, and generated artifacts remain excluded.

## Next development phase

Implement only the simultaneous-finalization race recovery deferred from this
checkpoint:

1. identify the named partial unique constraint without parsing database error
   text;
2. recover the losing materialization attempt into a direct `DUPLICATE` in a
   fresh transaction;
3. prove exactly one canonical winner and one duplicate with separate database
   connections and barrier-based PostgreSQL tests.

Keep the parser frozen. Do not add REST, frontend, asynchronous processing,
other institutions, or generic importer abstractions.
