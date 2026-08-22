# Handoff

## Objective

Gouda v0.1 — freeze the validated Santander Parser Contract and prepare the
first Git checkpoint without beginning persistence.

## Frozen baseline

Santander Parser Contract v0.1 is frozen. The approved baseline is validated
against three monthly private Santander source samples and the 29-test synthetic
XLSX suite. Frozen means current behavior is intentional; unsupported source
variants require an explicit contract revision.

## Validated implementation

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

- Full synthetic suite: 29 passed, 0 failed.
- Import and AST validation: passed.
- `git diff --check`: passed.
- `SOURCE_1`: recognized, 6 parsed, 29 ignored, 0 rejected,
  4 `commission_summary` ignored, `RECONCILED`.
- `SOURCE_2`: recognized, 6 parsed, 29 ignored, 0 rejected,
  4 `commission_summary` ignored, `RECONCILED`.
- `SOURCE_3`: recognized, 4 parsed, 30 ignored, 0 rejected,
  5 `commission_summary` ignored, `RECONCILED`.

All three current private sources reconcile. No private values, filenames,
rows, identifiers, or hashes were emitted or persisted.

## Repository state

The repository's first checkpoint includes only the reviewed project files,
synthetic fixture, documentation, tests, and configuration. Private source
locations, caches, secrets, local databases, and editor/OS artifacts remain
excluded. The working tree should remain clean after the checkpoint.

No Django models, PostgreSQL schema, migrations, import persistence, APIs,
frontend, correction flows, or generic multi-bank abstractions exist yet.

## Next development phase

The next development phase is the import/persistence boundary. It must begin in
a separate task after this checkpoint; do not expand the frozen parser scope.
