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

## Implemented target evolution

ADR-0008 keeps `Movement` canonical-only. ADR-0009 implements an immutable
FinancialObservation claim, mutable current resolution projection, and
append-only resolution history before canonical acceptance.

No AI interpretation runtime, canonical Movement correction, workflow engine,
or generic provider framework is implemented. The BCI Historical current-account PDF v0.1
parser, narrow evidence persistence, unresolved observation import, and
conservative reconciled Historical policy are implemented and validated.

## Current direction

BCI Historical Current Account PDF v0.1 is implemented and validated. BCI
Current and BCI Recent remain unimplemented, no stable cross-source identity
rule is frozen, and no canonical Movement correction is implemented. Do not
finalize cross-source identity or canonical correction rules without direct
rollover or corrected-source evidence.

When uncertain, preserve evidence, abstain explicitly, use deterministic
financial validation, and keep private values out of logs and tracked files.
