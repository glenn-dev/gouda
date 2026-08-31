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
- The internal canonical Movement reporting service queries one trusted
  persisted Account over an inclusive `Movement.occurrence_date` range. It
  returns deterministically ordered immutable items, exact Decimal total and
  count, and safe UUID-based provenance plus route status metadata without
  source payloads or filenames.
- The account-orientation migration test now restores the current ledger leaf
  migration, removing its pre-existing schema leakage into later test modules.

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

The first canonical read/reporting boundary is implemented. Persisted
`Movement` rows are the accepted query set; observation state is not a query
filter, and superseding evidence does not retract an existing Movement while
canonical correction remains deferred.

The pre-HTTP Account-access boundary is implemented in
`gouda.ledger.services.account_access`. Gouda still has no user, principal,
household, member, role, permission, or Account ownership persistence. One
opaque module-issued trusted local principal receives temporary read access to
all persisted Accounts; this is authorization policy, not ownership or
authentication. The resolver accepts an untrusted UUID value, returns an
authorized persisted `Account`, and gives unknown and policy-denied selectors
the same `account_not_accessible` failure. The authorized reporting operation
then delegates unchanged to the existing `MovementReport` service. Both paths
are deterministic and read-only.

HTTP/DRF remains unimplemented. Account authorization is no longer the
prerequisite, but a network adapter still needs a trusted server-side
caller-bootstrap or authentication boundary. It must not issue principal
context from request data. DRF is accepted architecturally but is not installed
or configured.

The next bounded task is a design checkpoint to choose and freeze the smallest
local-MVP caller-trust/bootstrap contract and network exposure constraints
before implementing a read-only endpoint.

When uncertain, preserve evidence, abstain explicitly, use deterministic
financial validation, and keep private values out of logs and tracked files.
