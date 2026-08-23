# Current task

## Objective

Implement checkpoint 2 of the Santander current-account import service by
connecting the frozen parser and approved boundary helpers to durable Django
registration, materialization, duplicate, and fatal-attempt lifecycles.

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

## Next action

Implement checkpoint 3: recover the named partial-uniqueness loser during
simultaneous finalization into a direct `DUPLICATE`, and prove one winner/one
duplicate using separate PostgreSQL connections and barrier-based tests. Keep
the parser frozen and do not broaden into REST, frontend, async processing, or
generic multi-source abstractions.
