# AI context

Gouda is being developed as a trust-first personal-finance movement ledger. The
repository began documentation-first and now contains the first Django/PostgreSQL
persistence foundation and synchronous Santander current-account import service.

Initial technology direction:

- Django with Django REST Framework as a modular-monolith backend;
- PostgreSQL as the persistence layer;
- React with TypeScript as the web client;
- Docker Compose for local development.

AWS and Kubernetes are deferred beyond Sprint 0.

Santander source discovery baseline:

- Three private monthly XLSX statements were inspected read-only and only as
  sanitized structure.
- The observed workbook has one visible sheet, seven columns, metadata before
  a movement table, and separate debit/credit columns.
- Movement dates omit the year; period metadata is needed for year resolution.
- Source rows may omit a numeric running balance, so reconciliation is not
  guaranteed by the source.
- The Santander-to-Gouda contract and a fully synthetic XLSX fixture are now
  available under `docs/` and `tests/fixtures/santander/`.
- The first isolated Santander parser is implemented at
  `gouda/santander_parser.py`; it uses `openpyxl` only for XLSX decoding and
  has no Django or persistence coupling.
- The parser rejects negative source debit/credit magnitudes and zero movement
  amounts, treats rejected movement-like rows as insufficient reconciliation
  evidence, and fails closed on formula-backed financial cells.
- Smoke validation against the three private samples recognized all three
  workbooks without persisting or emitting source content.
- A synthetic regression records the diagnosed section boundary: a
  financial-looking row in a recognized commission-summary section is ignored
  rather than parsed or deduplicated.
- The parser now implements the narrow source-confirmed section state:
  primary movement detail, commission summary, and post-summary auxiliary
  rows. It does not use transaction-value deduplication.
- Privacy-safe smoke validation now recognizes the confirmed markers in all
  three private samples; all three reconcile with commission-summary rows
  ignored.
- Santander Parser Contract v0.1 remains frozen as the validated baseline.
- `gouda.ledger.services.santander_import` now registers exact artifacts and
  attempts, parses outside database transactions, validates the frozen parser
  result, atomically materializes raw records and movements, and records safe
  durable fatal attempts after failures.
- Sequential and normal post-parse duplicates are supported. Separate-
  connection PostgreSQL tests confirm that identical imports can register and
  parse concurrently, then serialize same-account materialization on
  `select_for_update(Account)`. The second transaction observes the committed
  canonical batch and finalizes through the normal post-parse duplicate path.
- `one_materialized_batch_per_artifact_account` remains a database defense in
  depth across source kinds. Same-route retries become duplicates; a different
  route after materialization becomes a source-kind conflict. Failed attempts
  do not block a later correct route.
  because same-account materialization is serialized; no speculative named-
  constraint recovery exists.
- The Santander current-account XLSX v1 backend importer is technically
  complete for its approved synchronous scope, pending optional manual
  validation with private source statements.

Canonical semantics:

- positive signed amount: the referenced account's household net-worth
  contribution increases;
- negative signed amount: that contribution decreases;
- for Santander TDC liability accounts, canonical signed amount is the
  negation of source-native `debt_effect`;
- transfers are excluded from consolidated income and spending totals;
- source records remain traceable after normalization.

When uncertain, favor explicit provenance, deterministic behavior, reversible changes, and synthetic data.

## TDC parser-contract correction

The observed national-currency source contract now distinguishes conditional
original USD operation evidence from the debt-affecting CLP `Cargo del mes`.
`SourceRecord.original_amount` and `original_currency` are an optional pair
with independent provenance; `billed_amount`, `billed_currency`, installment
evidence, and `debt_effect` retain separate roles. No exchange rate is inferred.

`StatementMetadata.card_last_four` is required for this v1 family and comes
only from exact masked-card identity contexts. All recognized occurrences must
agree. Card movement headings are retained as `card_identity_context` ignored
evidence instead of invalid-date financial rejects. The parser remains GIR-
only; persistence generalization is the next separate checkpoint. These
observable corrections use parser version `santander-tdc-pdf-v1.1`; the source
contract independently remains v0.1.

## Persistence boundary Checkpoint A

`SourceArtifact` now identifies exact bytes only; required
`ImportBatch.source_kind` identifies the interpretation route. `RawRecord`
remains the shared identity/outcome envelope with required `record_kind` and
batch-local `record_ordinal`. Existing row/cell/class and E/F amount-column
facts are XLSX-only raw evidence, and `Movement` contains no spreadsheet
column state.

Santander TDC batch and record evidence use dedicated one-to-one models.
Stable source facts are relational; variable page/line/token and field
provenance use the strict `santander-tdc-field-provenance-v1` JSON schema with
Decimal geometry encoded as strings. An internal projector materializes only
a prepared synthetic v1.1 parser result and deliberately creates no artifact,
movement, duplicate lifecycle, extraction, or parser call. The TDC application
service remains the next checkpoint.
