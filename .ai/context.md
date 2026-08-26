# AI context

## Product and architecture

Gouda is a trust-first personal-finance movement ledger. Stable intent and
semantics live in:

- `docs/product/vision.md`;
- `docs/product/ingestion-evidence-principles.md`;
- `docs/product/glossary.md`;
- `docs/architecture/evidence-resolution.md`; and
- `docs/decisions/ADR-0008-separate-observations-from-canonical-movements.md`.

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
- Private source corpora remain ignored, untracked, and outside committed test
  fixtures.

## Accepted target evolution

ADR-0008 keeps `Movement` canonical-only and establishes a conceptual
Financial Observation Candidate plus auditable resolution before canonical
acceptance. The boundary supports future provisional and heterogeneous
evidence without making probabilistic interpretation accounting truth.

No Observation/Resolution schema, AI execution, BCI parser, workflow engine,
or generic provider framework is implemented.

## Current direction

The next implementation-design checkpoint should determine the smallest model
and application-service boundary needed for multiple evidence items to support
one movement, using the BCI current-account lifecycle as a concrete stress
test. It must preserve existing Santander behavior and avoid finalizing a
permanent BCI source strategy without direct rollover evidence.

When uncertain, preserve evidence, abstain explicitly, use deterministic
financial validation, and keep private values out of logs and tracked files.
