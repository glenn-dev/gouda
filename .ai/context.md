# AI context

## Product and architecture

Gouda is a trust-first personal-finance movement ledger. Stable intent and
semantics live in:

- `docs/product/vision.md`;
- `docs/product/ingestion-evidence-principles.md`;
- `docs/product/glossary.md`;
- `docs/architecture/evidence-resolution.md`; and
- `docs/decisions/ADR-0008-separate-observations-from-canonical-movements.md`;
- `docs/decisions/ADR-0009-implement-observation-resolution-boundary.md`.

Read `AGENTS.md` and the README documentation map before using this operational
context. `.ai/` is not canonical product documentation.

## Implemented baseline

- Django/PostgreSQL ledger persistence is implemented for `Account`, exact-byte
  `SourceArtifact`, source-typed `ImportBatch`, `RawRecord`, source-specific
  evidence, and canonical `Movement`.
- Canonical signed amount follows ADR-0005: positive increases the referenced
  account's contribution to household net worth; negative decreases it.
- The synchronous Santander current-account XLSX importer is implemented and
  validated against its frozen deterministic contract.
- The synchronous Santander credit-card PDF importer is implemented and
  validated against parser v1.1 and its frozen source contract.
- The TDC route uses explicit account/card-suffix binding and maps source-native
  liability debt effect to canonical signed amount deterministically.
- Current Santander services parse outside transactions and atomically persist
  evidence plus canonical movements with tested duplicate, failure, and
  concurrency behavior.
- `FinancialObservation` and append-only `ObservationResolution` implement the
  pre-canonical interpretation and resolution boundary. Observation claims are
  immutable; only their current lifecycle projection changes.
- Deterministic services support confirm-new, match-existing, reject, conflict,
  reopen, and interpretation supersession under Account-scoped locking.
- Private source corpora remain ignored, untracked, and outside committed test
  fixtures.
- Pinned `xlrd==2.0.1` now enables read-only inspection of legacy XLS
  artifacts; the available BCI Current Cartola XLS has been structurally
  inspected.
- The pure source-only BCI Recent Movements XLSX parser is implemented and
  validated with privacy-safe synthetic fixtures and read-only private
  validation; it independently discovers populated OOXML cells instead of
  trusting worksheet dimension metadata.
- The pure source-only BCI Current Cartola legacy-XLS parser is implemented
  through the pinned `xlrd==2.0.1` boundary and validated with synthetic sheet
  snapshots, synthetic BIFF formula records, and read-only private validation.
- Both BCI current-source parsers require an explicit nonblank trusted artifact
  identity before source reading and preserve it in record and field-level
  provenance. Recent Movements also records the selected Cargo or Abono header
  and cell coordinate for source direction and amount.

## Implemented target evolution

ADR-0008 keeps `Movement` canonical-only. ADR-0009 implements an immutable
FinancialObservation claim, mutable current resolution projection, and
append-only resolution history before canonical acceptance.

No AI interpretation runtime, canonical Movement correction, workflow engine,
or generic provider framework is implemented. The BCI Historical current-account PDF v0.1
parser, narrow evidence persistence, unresolved observation import, and
conservative reconciled Historical policy are implemented and validated.
The source-only contracts `bci_current_cartola_v0.1` and
`bci_recent_movements_v0.1` are frozen and implemented as pure source parsers.

## Current direction

BCI Historical Current Account PDF v0.1 and both current-source parsers are
implemented and validated. Their joint source-boundary review and narrow
provenance-conformance correction are complete. Current Cartola is now the
preferred normal open-period source strategy; Recent Movements remains
research and diagnostic support rather than a parallel pipeline. This choice
prioritizes Current's period-scoped coverage, per-row balance chain, and opaque
series evidence over Recent's lower-maintenance OOXML format and dual dates.

The one-time paired T2 falsification challenge did not falsify Current: all 27
contemporaneous Recent accounting-date candidates have exactly one Current
candidate, while Recent's other 23 rows are older than Current's parsed range.
Current's balance chain passes all 26 adjacent equations. Recent remains at
exactly 50 rows while replacing four oldest-boundary candidates with four newer
candidates, which is strong rolling-window evidence but not proof of a
documented cap. Routine paired capture has stopped.

One Current-to-Historical rollover experiment remains valuable. One shared
T1/T2 Current candidate signature changed description, opaque series, and row
balance while its corresponding Recent candidate fields remained stable; this
is unresolved source volatility, not identity or authority evidence.

BCI produces only three Historical current-account statements per year. As of
August 2026, Current-to-Historical validation is deferred until a naturally
available Historical artifact has an intrinsic printed period covering the
retained Current dates. It is not the immediate Gouda task and does not block
development. No stable cross-source identity rule is frozen, and no canonical
Movement correction is implemented.

The immediate roadmap priority is the first canonical read/reporting boundary:
a read-only application service that queries accepted `Movement` rows for one
trusted Account and inclusive date range, computes exact signed period totals,
and returns a safe provenance trace to originating evidence. This advances the
MVP query/totals/trace path using already stable canonical semantics. It must
not add HTTP endpoints, authentication, migrations, classification, transfer
pairing, provisional observations, BCI integration, identity/deduplication, or
Movement correction.

When uncertain, preserve evidence, abstain explicitly, use deterministic
financial validation, and keep private values out of logs and tracked files.
