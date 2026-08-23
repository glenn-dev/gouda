# Handoff

## Objective

Gouda checkpoint — extend privacy-safe Santander current-account validation to
seven monthly XLSX sources and record read-only structural observations for
seven Santander credit-card PDFs.

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

## Concurrency semantics

Registration and parsing remain concurrent. Parsing runs outside database
transactions, and simultaneous first registration of identical bytes resolves
to one exact `SourceArtifact` without poisoning either transaction.

Materialization is intentionally serialized per account. Each materialization
transaction locks the trusted `Account` first and its own `PROCESSING` batch
second. PostgreSQL holds the Account row lock until commit. Under the configured
`READ COMMITTED` isolation, the second same-account transaction acquires the
lock after the first commits, observes the canonical batch in the existing
post-parse lookup, and finalizes normally as a direct `DUPLICATE`.

Consequently, the previously proposed simultaneous partial-unique-constraint
loser race is unreachable through the approved service lifecycle. The explicit
`one_materialized_batch_per_artifact_account` partial unique constraint remains
unchanged as defense in depth. No Account lock was moved or weakened, no
constraint collision was forced, and no named-constraint recovery handler was
added. Unrelated `IntegrityError` behavior remains the checkpoint-2 safe
`PERSISTENCE`/`materialization_integrity_error` fatal path.

Separate PostgreSQL connections prove:

- identical concurrent imports produce one canonical graph and one post-parse
  duplicate, with no fatal, processing, or partial loser graph;
- different artifacts for one account parse together but materialize serially
  as independent canonical batches;
- different accounts can hold their Account row locks concurrently, so there
  is no application-wide import lock.

The lock order has no reverse edge: each transaction locks only its target
Account and then its own batch. It never locks another processing attempt or a
canonical winner.

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

- Full Django/PostgreSQL and synthetic suite: 101 passed, 0 failed.
- Separate-connection concurrency suite: 3 passed, 0 failed in five
  consecutive final repeat runs (15 concurrency-test executions).
- Migration drift check: no changes detected.
- Django system check: no issues.
- Python compilation validation with an isolated cache: passed.
- `git diff --check`: passed.
- Expanded private application-service validation is complete against seven
  ignored Santander current-account XLSX sources. Each exact byte input reached
  `ACCEPTED` and `RECONCILED` through
  `import_santander_current_account_xlsx`, with sanitized aggregates:
  `(3,29,0)`, `(11,30,0)`, `(9,29,0)`, `(2,29,0)`, `(4,30,0)`, `(6,29,0)`, and
  `(6,29,0)` for parsed, ignored, and rejected rows. All provenance fields
  were populated and no fatal or residual processing attempt remained.
- Exact-byte re-imports produced seven direct `DUPLICATE` attempts. Duplicate
  graphs were empty and canonical graphs remained unchanged.
- The private corpus inventory found seven XLSX and seven PDF sources. All
  sources remained ignored and untracked, with valid signatures, no exact-byte
  duplicate groups, and no unexpected file types.
- Native read-only discovery of the seven TDC PDFs found machine-extractable
  text, no encryption, one US Letter page-size family, and three/four-page
  pagination variation. Detailed privacy-safe observations are in
  `docs/sources/santander-credit-card-pdf-observations.md`.
- The private source files were read-only local inputs, remained ignored, were
  not copied into fixtures or CI, and were not added to Git. No production code
  files changed.

## Repository state

Finder `.DS_Store` files are ignored repository-wide and the previously
untracked artifacts were removed. Private sources, caches, secrets, local
databases, and generated artifacts remain excluded.

## Readiness

The Santander current-account XLSX v1 backend importer remains technically
complete for its approved synchronous scope, now validated across seven private
monthly sources. The TDC PDFs are discovery evidence only; no parser contract,
model, migration, or domain-semantics decision was added. The next checkpoint
requires an explicit product decision about deeper TDC source-contract
discovery. Private statements remain excluded from CI.

Keep the parser frozen. Product work on REST, frontend, asynchronous processing,
other institutions, and generic multi-source abstractions remains out of this
checkpoint's scope.
