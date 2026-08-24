# Current task

## Objective

Formalize the canonical signed-movement semantics needed to support both
current-account assets and future credit-card liabilities, while preserving
the now-frozen Santander credit-card PDF contract boundary. Do not implement
the parser, change the frozen current-account importer, or change the
persistence model.

## Completed

- Established the product, architecture, security, and technology baseline.
- Confirmed the signed account-movement convention in ADR-0001.
- Confirmed Django/DRF, PostgreSQL, React/TypeScript, and Docker Compose in
  ADR-0002; AWS and Kubernetes remain deferred.
- Inspected three private Santander XLSX statements read-only and documented
  their sanitized structure and limitations.
- Defined the Santander source-to-raw-to-normalized import contract.
- Added a fully synthetic Santander-shaped XLSX fixture and fixture README.
- Made row outcomes, debit/credit behavior, year derivation, worksheet
  recognition, fail-closed errors, and reconciliation statuses executable.
- Implemented `gouda.santander_parser` with 28 openpyxl-backed synthetic tests.
- Adopted `openpyxl` through `requirements.txt` for XLSX decoding.
- Rejected negative source amounts and zero movement amounts.
- Separated incomplete reconciliation evidence from complete arithmetic mismatch.
- Added worksheet name/ordinal/row provenance and redacted representations.
- Completed privacy-safe smoke validation against all three private samples.
- Added a fully synthetic regression test specifying
  that financial-looking rows inside a recognized commission-summary section
  are ignored and excluded from reconciliation.
- Updated the import contract to distinguish observed source structure, the
  section-aware contract decision, and the implementation boundary.
- Implemented the narrow section-aware state handling required by the
  regression without generic transaction deduplication.
- Corrected section markers to the source-confirmed standalone `Resumen de
  Comisiones` and `MENSAJES` labels; the asterisk separator remains auxiliary
  structure rather than a boundary.
- Completed full synthetic, import/AST, diff-check, status, and privacy-safe
  three-source validation; all three private sources now reconcile.
- Marked Santander Parser Contract v0.1 as a frozen baseline supported by the
  three monthly source samples and 29-test synthetic suite.
- Added ADR-0004 to distinguish source kind, source variant, and parser
  implementation version without introducing a generic importer abstraction.
- Added nullable `ImportBatch.source_variant` with PostgreSQL lifecycle
  constraints and the approved `v1` boundary semantics.
- Added deterministic tagged Santander raw-cell serialization, exact-money
  boundary helpers, authoritative batch-status derivation, safe parser-error
  mapping, parser-result graph validation, and Santander v1 recognition.
- Kept the known Santander section markers optional while rejecting dangerous
  changed layouts, populated columns beyond G, and incoherent parser results.
- Added focused model, serializer, money, status, error, graph, reconciliation,
  and format-recognition tests. The complete 78-test suite passes against
  PostgreSQL 16.
- Removed Finder metadata from the worktree and now ignore `.DS_Store`
  repository-wide. Corrected the application-state and synthetic-fixture
  reconciliation documentation.
- Added the explicit synchronous
  `import_santander_current_account_xlsx` application service.
- Added strict content, filename, persisted-account, account-kind, and trusted
  currency validation plus exact SHA-256 artifact identity and byte-level
  digest-collision verification.
- Added a short registration transaction with nested-savepoint artifact race
  handling, sequential duplicate detection, and durable `PROCESSING` attempts.
- Kept parser execution and all deterministic boundary preparation outside
  database transactions.
- Added atomic raw-record, movement, reconciliation, and final-batch
  materialization with account-then-attempt row locking and account-context
  revalidation.
- Added safe parser, boundary, and persistence failure mapping with fresh-
  transaction durable `FATAL` compensation after materialization rollback.
- Added sequential and normal post-parse duplicate behavior; duplicate attempts
  point directly to a canonical target and contain no canonical rows.
- Added PostgreSQL integration coverage for happy, partial, rejected,
  all-ignored, duplicate, retry, rollback, compensation, boundary, artifact,
  filename, caller-context, and privacy behavior. The complete 98-test suite
  passes against PostgreSQL 16.
- Confirmed architecturally that the proposed simultaneous partial-uniqueness
  loser race cannot occur through the approved lifecycle: same-account
  materialization locks `Account` before the duplicate lookup and PostgreSQL
  holds that row lock through commit.
- Added separate-connection PostgreSQL concurrency tests proving that
  registration and parsing overlap, while same-account materialization is
  serialized without deadlock.
- Proved identical concurrent imports create exactly one artifact, one
  canonical graph, and one direct post-parse `DUPLICATE`, with no `FATAL`,
  `PROCESSING`, or partial loser graph.
- Proved different artifacts for the same account still parse concurrently and
  then materialize serially as independent canonical batches.
- Proved different accounts can hold their own Account row locks concurrently;
  locking is account-scoped rather than application-wide.
- Kept `one_materialized_batch_per_artifact_account` unchanged as defense in
  depth. No named-constraint recovery or production-code change was needed.
- Completed the optional private application-service smoke validation against
  all three ignored Santander current-account XLSX sources. All three exact
  byte imports materialized as `ACCEPTED` and `RECONCILED`; two had 35 raw
  records (6 parsed, 29 ignored) and one had 34 raw records (4 parsed, 30
  ignored), with zero rejected rows.
- Re-imported each exact source byte sequence. All three attempts became direct
  `DUPLICATE` results pointing to their canonical batch, with empty duplicate
  graphs and unchanged canonical graphs. No private source bytes remain in the
  isolated validation database.
- Re-ran the full PostgreSQL 16 suite (101 tests), the separate-connection
  concurrency suite (3 tests), migration drift check, Django system check, and
  `git diff --check`; all passed.
- Confirmed the expanded ignored private corpus contains seven XLSX and seven
  PDF sources, with valid signatures, no exact-byte duplicates, no unexpected
  file types, and no tracked private sources.
- Ran the frozen `import_santander_current_account_xlsx` service against all
  seven chronological XLSX sources in disposable PostgreSQL 16. Every source
  reached `ACCEPTED` and `RECONCILED`, with zero rejected rows, populated
  provenance, no `FATAL` or residual `PROCESSING`, and complete raw/movement
  graph counts. Exact-byte reimports produced seven direct `DUPLICATE`
  attempts with empty duplicate graphs and unchanged canonical graphs.
- Performed native text and document-structure discovery on all seven TDC PDFs.
  All were machine-extractable and unencrypted, used US Letter dimensions,
  and shared one broad template family with three/four-page pagination
  variation. Added the privacy-safe observation note at
  `docs/sources/santander-credit-card-pdf-observations.md`.
- Designed the contract before its v0.1 freeze at
  `docs/contracts/santander-credit-card-pdf-v0.1.md`. It defines a
  fail-closed recognition boundary, section state model, conservative billed
  transaction candidate rules, explicit row outcomes, category-directed debt
  effects, billed/unbilled and installment boundaries, currency/date rules,
  provenance/privacy requirements, and unsupported variations.
- The pre-freeze reconciliation equation was not proven complete across all
  seven statements. The contract records `FAIL` due to insufficient operand
  semantics, not arithmetic contradiction, and permits
  `INSUFFICIENT_DATA` without weakening the equation.
- Added ADR-0005 to generalize canonical movement signs across asset and
  liability accounts: positive increases the referenced account's contribution
  to household net worth and negative decreases it. Current-account asset
  values remain unchanged; liability debt increases map negative and debt
  reductions map positive.
- Kept source-native provider meaning separate from canonical movement meaning.
  Santander TDC `debt_effect` is converted at the source/domain boundary and
  is not a second canonical amount. Classification and transfer correlation
  remain separate future layers.
- Minimally redirected ADR-0001 to ADR-0005 and updated the domain model,
  data-pipeline, TDC contract, and handoff documentation. No production code,
  model, migration, parser, importer, test, fixture, or private source changed.

## Current checkpoint

Implemented the minimum Account-domain support required by accepted ADR-0005:

- added `Account.Kind.CREDIT_CARD` without changing `CURRENT`;
- added required `Account.EconomicOrientation` with explicit `ASSET` and
  `LIABILITY` values;
- backfilled existing `CURRENT` accounts to `ASSET` in migration 0004;
- added the closed-world database invariant for supported kind/orientation
  combinations;
- made Santander current-account imports require `CURRENT` + `ASSET` at the
  application-service boundary;
- kept `Movement.signed_amount`, parser behavior, and import lifecycle
  unchanged.

The Santander TDC PDF Source Contract v0.1 is now `FROZEN / APPROVED`. This
freeze covers only the observed native-text template family and
`TDC-PDF-GIR-v1`; it does not authorize parser, persistence, application-
service lifecycle, transfer matching, classification, balance storage, BCI
support, or generic importer work.

## TDC extraction-boundary checkpoint

Freeze-readiness review found no new source-discovery requirement, and the
approved contract now defines `TDC-PDF-GIR-v1`, canonical page coordinates,
extraction-level normalization, geometric line/row grouping, repeated-header
behavior, fail-closed unknown-heading behavior, explicit credit/refund
evidence, rejected-row reconciliation behavior, and coordinate-based
provenance. The reference conformance profile is pdfplumber 0.11.8 with
pdfminer.six 20251107; this is not yet a repository dependency or parser
implementation.

Two native-text strategies were compared privately across all seven PDFs.
Both were repeatable and agreed on page/line/date-line structure, but differed
in word tokenization and raw coordinates. This supports the canonical
geometric IR decision. The contract is frozen, while parser implementation
remains a separate future checkpoint.

## Completed parser-only extraction checkpoint

- Added the Santander-specific pure-Python package
  `gouda.santander_tdc_pdf`, with frozen dependencies `pdfplumber==0.11.8`
  and `pdfminer.six==20251107`.
- Implemented immutable `TdcPdfGir`, `Page`, `Token`, `Line`, and quantized
  `BoundingBox` structures with explicit GIR/profile versions, page ordinals,
  native token text, and deterministic page-local lines.
- Implemented explicit reference-profile extraction parameters, native-text /
  encryption / invalid-PDF / page-access / Letter-geometry conformance errors,
  NFC source normalization, and separate NFKC recognition-key normalization.
- Implemented nearest-compatible geometric line grouping with 2.00pt center
  tolerance, earlier-line exact ties, deterministic token/line ordering, and
  union boxes. Canonical GIR hashes support repeatability checks.
- Deliberately stopped before structural row groups: the frozen row-group rule
  requires recognized table headers and column bands, which would introduce
  financial/parser recognition semantics into this extraction-only checkpoint.
- Added in-memory synthetic ReportLab fixtures/tests covering 3/4-page Letter
  documents, repeated headers, multiline/page-boundary structure, unsupported
  geometry, image-only PDFs, malformed bytes, normalization, geometry,
  tie-breaking, encryption, repeatability, and privacy-safe fixture absence.
- Focused tests pass (10 tests). A read-only smoke run against all seven ignored
  TDC PDFs accepted the native-text/Letter boundary and produced stable hashes
  across repeated extraction; no private text or extracted GIR was persisted.

## Next action

Implement Santander-specific document recognition and financial row parsing as
the next separately scoped checkpoint. Persistence and the application-service
lifecycle remain separate later checkpoints.

## Current parser-only checkpoint

Implemented the GIR-only Santander TDC v1 parser in
`gouda/santander_tdc_pdf/parser.py`, with immutable result and provenance
types in `gouda/santander_tdc_pdf/types.py`. Adversarial hardening replaced
substring transitions, global currency scanning, rightmost-amount selection,
and transaction-text reconciliation with explicit Santander header profiles,
a closed section-transition table, role-band continuation rules, labeled
currency contexts, and summary-state reconciliation operands.

The observed current-period installment profile recognizes its complete
multi-line header, treats only `Cargo del mes` as the primary billed amount,
keeps numeric location/reference evidence out of monetary interpretation, and
requires compatible repeated-header geometry. Cross-page continuations need a
compatible repeated header; otherwise parsing is document-fatal. Unknown
headings, contradictory section order, conflicting columns, and unsafe page
transitions fail closed.

Parser mappings are defensively copied and immutable. Parsed field provenance
now identifies the actual header, labeled inherited currency, statement
period, section/category source, field role, and per-page spans for multi-page
evidence. Row-group ordinals restart per recognized financial section.
Reconciliation reads only explicit summary-state labels and retains operand
provenance.

The synthetic parser suite now has 39 tests; focused parser, extraction, and
current-account parser validation passes 78 tests. Privacy-safe validation of
all seven ignored PDFs produced parsed/ignored/rejected counts
`(50,94,7)`, `(20,86,8)`, `(27,86,7)`, `(36,86,6)`, `(41,94,8)`,
`(31,86,10)`, and `(44,94,6)`. Every source is recognized and repeatable,
every parsed field has complete provenance, and every reconciliation result is
`INSUFFICIENT_DATA`. Remaining rejects are `date_invalid` 36,
`amount_malformed` 12, and `zero_amount_unsupported` 4; none has the complete
date/positive-primary-amount shape required by frozen v1.

No-volume PostgreSQL 16 validation passed: complete Django suite 157 tests,
explicit concurrency suite 3 tests, system check, migration drift, compilation,
and diff check. The disposable container was removed. The parser remains GIR-
only and has no Django, account/domain, persistence, transfer, classification,
BCI, or generic parser dependency.
