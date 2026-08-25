# Handoff

## Objective

Gouda Checkpoint A — generalize the import persistence boundary for future
Santander TDC PDF evidence while preserving frozen XLSX behavior and canonical
movement semantics.

## Frozen baseline

Santander Parser Contract v0.1 is frozen. The approved baseline is validated
against three monthly private Santander source samples and the 29-test synthetic
XLSX suite. Frozen means current behavior is intentional; unsupported source
variants require an explicit contract revision.

## Boundary decisions

ADR-0006 supersedes ADR-0004's source-kind placement and separates three
provenance facts:

- exact bytes and digest belong to route-neutral `SourceArtifact`;
- required source kind belongs to `ImportBatch`;
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
- Designed the TDC contract before its v0.1 freeze in
  `docs/contracts/santander-credit-card-pdf-v0.1.md`. It is explicitly
  recorded in its pre-freeze status and defines fail-closed recognition, stateful section
  interpretation, conservative billed-row extraction, explicit outcomes,
  category-directed debt effects, billed/unbilled and installment boundaries,
  date/currency rules, provenance, and privacy handling.
- The pre-freeze billed-debt reconciliation equation remains unproven across
  all seven statements. The contract records `FAIL` because complete operand
  semantics were insufficient, not because private arithmetic contradicted it.
- Added [ADR-0005](../docs/decisions/ADR-0005-canonical-movement-sign-orientation.md)
  to define the canonical invariant: `Movement.signed_amount` is the change
  in the referenced account's contribution to household net worth. Asset
  increases are positive; liability debt increases are negative. Account
  economic orientation is distinct from product/source kind and belongs in a
  future explicit domain field.
- Preserved source-native meaning separately from canonical movement meaning.
  TDC `debt_effect` is converted at the source/domain boundary; it is not a
  second mutable canonical amount. Classification and transfer/counterparty
  correlation remain separate future layers.
- Minimally redirected ADR-0001, and updated the domain model, data pipeline,
  TDC contract, task record, and handoff. No production code, model,
  migration, parser, importer, test, fixture, or private source changed.
- The private source files were read-only local inputs, remained ignored, were
  not copied into fixtures or CI, and were not added to Git. No production code
  files changed.

## Repository state

Finder `.DS_Store` files are ignored repository-wide and the previously
untracked artifacts were removed. Private sources, caches, secrets, local
databases, and generated artifacts remain excluded.

## Account-domain checkpoint

ADR-0005 is implemented in the Account domain. `Account.Kind` retains the
stable `CURRENT` value and now includes `CREDIT_CARD`. Required
`Account.EconomicOrientation` stores `ASSET` or `LIABILITY` independently from
product kind. Migration `0004_account_economic_orientation` stages the field,
fails closed on unexpected pre-existing kinds, backfills all supported current
accounts to `ASSET`, makes the field non-nullable, and adds the named
`account_kind_orientation_known` database constraint. The supported closed
world is `CURRENT` + `ASSET` and `CREDIT_CARD` + `LIABILITY`.

The Santander current-account XLSX v1 backend importer remains frozen and
unchanged in parser behavior and lifecycle. Its application-service boundary
now explicitly requires `CURRENT` + `ASSET`; invalid orientation is rejected
with the safe `account_orientation_unsupported` code. Existing signed
movement values are not rewritten.

The Santander TDC PDF Source Contract v0.1 is now `FROZEN / APPROVED`. The
freeze covers only the observed native-text template family and
`TDC-PDF-GIR-v1`. No TDC parser, import lifecycle, transfer matching,
classification, balance storage, BCI support, or generic importer abstraction
is authorized by this checkpoint. Private statements remain excluded from CI.

## TDC extraction-boundary checkpoint

The freeze-readiness review identified Category A gaps in deterministic PDF
extraction and recognition. The contract was narrowly revised and approved
without implementing a parser, persistence, model, migration, or application
service.
It now defines the `TDC-PDF-GIR-v1` canonical geometric intermediate
representation: page-ordered native text, top-left PDF-point coordinates,
quantized bounding boxes, deterministic lines and row-group candidates,
header-derived column bands, and coordinate-based provenance. It also defines
extraction normalization, repeated-header/page-break handling, unknown-heading
fail-closed behavior, explicit credit/refund direction evidence, and
`INSUFFICIENT_DATA` when rejected movement-like rows could affect
reconciliation.

The reference conformance profile is pdfplumber 0.11.8 with pdfminer.six
20251107. A privacy-safe comparison of two native-text strategies across all
seven ignored TDC PDFs found repeatable page/line/date-line structure but
different word tokenization and raw coordinate boxes, supporting the canonical
IR boundary. No private text or values were added to documentation.

The contract is now `FROZEN / APPROVED`.

## TDC parser-only extraction implementation

`requirements.txt` now pins `pdfplumber==0.11.8` and
`pdfminer.six==20251107`. The source-specific pure-Python package
`gouda.santander_tdc_pdf` implements `TDC-PDF-GIR-v1` with frozen dataclasses
for the document, pages, tokens, lines, and 0.01pt top-left PDF-point boxes.
The reference profile is explicit: native text, `use_text_flow=False`,
`keep_blank_chars=False`, `x_tolerance=3`, `y_tolerance=3`,
`line_dir="ttb"`, `char_dir="ltr"`, and `return_chars=True`.

Source text uses NFC, normalized line endings, and NBSP-to-space conversion;
recognition keys are a separate NFKC/casefold/whitespace-collapse,
accent-insensitive helper. Lines use nearest compatible vertical centers within
2.00pt, earlier-line exact ties, deterministic left-to-right token order, and
union boxes. Canonical serialization is represented by a stable SHA-256 hash.

The extraction layer intentionally stops at line-level GIR. Contractual row
groups need recognized table headers and column bands, so implementing them here
would cross into future parser recognition and financial semantics. Synthetic
ReportLab tests cover supported 3/4-page Letter documents, repeated headers,
multiline/page boundaries, geometry and native-text failures, malformed bytes,
normalization, tie behavior, encryption, repeatability, and absence of committed
private fixtures. Focused extraction tests pass (10). A read-only smoke run accepted all
seven ignored TDC PDFs and matched repeated canonical hashes; no private text or
GIR was persisted.

Keep the current-account parser/importer frozen. Product work on REST, frontend,
asynchronous processing, other institutions, and generic multi-source
abstractions remains out of scope. The next checkpoint is source-specific
document recognition and financial row parsing.

Keep the parser frozen. Product work on REST, frontend, asynchronous processing,
other institutions, and generic multi-source abstractions remains out of this
checkpoint's scope.

## TDC parser-only checkpoint

The GIR-to-parser stage is implemented in
`gouda/santander_tdc_pdf/parser.py`, with immutable parser result/provenance
types in `gouda/santander_tdc_pdf/types.py`. `parse_tdc_pdf_gir` consumes only
`TdcPdfGir`; `parse_tdc_pdf` composes the existing extraction adapter with that
GIR-only parser.

An adversarial review found false acceptance through substring section
transitions, arbitrary currency inheritance, rightmost-amount selection,
unproven page continuation, mutable result mappings, inaccurate header
provenance, and transaction-description reconciliation. The hardening pass
reproduced every issue synthetically before replacing those paths.

Recognition now uses exact Santander section headings, an explicit legal
transition table, source-specific header profiles, complete multi-line header
signatures, 3pt geometry compatibility, section-local row ordinals, and
description/location/reference continuation bands. The observed installment
profile maps `Cargo del mes` as the sole primary billed amount; context columns
cannot compete with it. Repeated headers must match role and geometry, and an
unproven cross-page continuation is fatal.

Currency comes only from an explicit row role or labeled statement context;
the frozen-family `moneda nacional` product label supplies CLP with its actual
source provenance. Unrelated currency-like tokens are ignored. Reconciliation
uses only exact summary-state labels, never transaction descriptions, and
retains operand provenance. Complete synthetic operands cover both
`RECONCILED` and `NOT_RECONCILED`; the private corpus remains correctly
`INSUFFICIENT_DATA` because no document has all trusted operands.

All result mappings are defensively copied `MappingProxyType` instances.
Parsed fields retain actual header, statement-period, inherited-currency,
section/category, date, amount, description, optional location/reference, and
multi-page span provenance. No canonical signed amount or `Movement` is
created.

The synthetic parser suite has 39 tests, including all adversarial cases and
positive domestic/international/installment/payment/credit/charge, repeated-
header, multiline, page-boundary, provenance, immutability, and reconciliation
cases. Focused parser/extraction/current-account validation passes 78 tests.

Privacy-safe read-only validation recognized all seven PDFs and repeated both
GIR and parser results. Parsed/ignored/rejected counts are `(50,94,7)`,
`(20,86,8)`, `(27,86,7)`, `(36,86,6)`, `(41,94,8)`, `(31,86,10)`, and
`(44,94,6)`. All parsed provenance is complete. Aggregate rejects are
`date_invalid` 36, `amount_malformed` 12, and `zero_amount_unsupported` 4;
none is a complete supported-v1 candidate.

The disposable PostgreSQL 16 gate passed the complete 157-test suite, the
separate 3-test concurrency suite, system check, migration drift, compilation,
and diff check. The container was removed. No ORM, domain, persistence,
application-service, transfer, classification, BCI, or generic parser work was
introduced.

## TDC parser-contract correction before persistence

The parser contract now retains conditional original USD operation amount and
currency separately from the national-currency statement's CLP `Cargo del
mes`. Only the latter supplies `billed_amount` and `debt_effect`; installment
amount remains independent and no exchange rate is inferred. Each new source
field has its own immutable provenance.

Structured statement metadata now includes an exactly four-character card
suffix sourced only from exact masked-card identity lines and exact movement-
card headings. Every recognized occurrence must agree; conflicts fail with the
sanitized `card_identity_conflict` code. Recognized card headings are ignored
with `card_identity_context` rather than rejected as invalid dates.

Privacy-safe comparison of the seven ignored PDFs is recorded in the task's
final report. The implementation remains parser-only: no ORM, migration,
persistence, import service, classification, transfer, FX, BCI, or generic
provider work was added.

All seven private PDFs remain recognized and deterministic. Sanitized parsed/
ignored/rejected tuples are `(50,95,6)`, `(21,87,6)`, `(27,87,6)`,
`(36,87,5)`, `(41,95,7)`, `(32,87,8)`, and `(44,95,5)`. Ten rows expose paired
original USD evidence with complete provenance; each document has two trusted
card-identity context records. Aggregate rejects changed from `date_invalid`
36, `amount_malformed` 12, `zero_amount_unsupported` 4 to `date_invalid` 29,
`amount_malformed` 10, `zero_amount_unsupported` 4.

The private comparison also exposed the pre-existing interpretation of CLP
period grouping as decimal fractions. Correcting the required `22.303` to
`22303` semantics changed 232 previously parsed billed/debt magnitudes by the
exact factor of 1000 and admitted two formerly malformed multi-group CLP rows;
source role, currency, category, and debt direction remained unchanged. This
is disclosed rather than hidden as an unchanged-value regression.

Final gates pass: 62 focused TDC parser/extraction tests, 29 focused current-
account parser tests, 52 focused current-account import/helper tests, the 170-
test PostgreSQL 16 suite, separate 3-test concurrency suite, system check,
migration drift check, compilation, and `git diff --check`. The disposable
PostgreSQL container was removed. The corrected observable result contract uses
`PARSER_VERSION = "santander-tdc-pdf-v1.1"`; the source-family evidence
contract independently remains v0.1.

## Checkpoint A: generalized persistence evidence

The persistence boundary now separates exact artifact identity from source
interpretation. `SourceArtifact` contains exact bytes/digest/receipt metadata;
`ImportBatch.source_kind` selects Santander XLSX or TDC PDF. Materialized
uniqueness remains artifact plus account across routes. Same-route attempts
become duplicates; different-route attempts after canonical materialization
become `source_kind_conflict`. Non-materialized failures do not block a later
correct route.

`RawRecord` remains the shared record identity and outcome envelope. XLSX uses
`record_ordinal = row_number` and retains row/cell/class plus E/F amount-column
evidence. PDF uses one-based parser-result order and has null spreadsheet
fields. `Movement.amount_source_column` is removed; no canonical signed amount,
currency, date, reference, description, balance, reconciliation, or lifecycle
semantics changed for current-account imports.

Dedicated one-to-one Santander TDC batch/record evidence models preserve the
v1.1 metadata, reconciliation operands, source facts, original and billed
money separately, source-native debt effect, installment evidence, and full
geometric provenance. Variable provenance is strict
`santander-tdc-field-provenance-v1` JSON with Decimal strings; stable values
remain relational.

The internal projector accepts only an already-created processing TDC batch
and a prepared recognized v1.1 result. It neither handles bytes nor calls the
extractor/parser, creates artifacts or movements, nor implements duplicate or
failure lifecycle. Those responsibilities, including card/account binding,
remain for the future TDC application-service checkpoint.

Migrations 0005/0006 validate and backfill all historical XLSX rows before
removing artifact source kind and movement E/F state. Reversal refuses TDC
data or absent/ambiguous artifact interpretations instead of inventing old
identity or discarding evidence.
