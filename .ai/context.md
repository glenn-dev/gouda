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
- Sequential and normal post-parse duplicates are supported. Recovery of the
  simultaneous materialization uniqueness race is intentionally deferred to
  the next checkpoint.

Canonical semantics:

- positive signed amount: money enters an account;
- negative signed amount: money leaves an account;
- transfers are excluded from consolidated income and spending totals;
- source records remain traceable after normalization.

When uncertain, favor explicit provenance, deterministic behavior, reversible changes, and synthetic data.
