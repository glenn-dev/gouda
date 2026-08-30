# Handoff

## Current repository capability

Gouda has validated synchronous Santander current-account XLSX and Santander
credit-card PDF import lifecycles. Both use deterministic, versioned source
contracts, preserve source evidence, validate source/domain boundaries, and
atomically create canonical signed movements. Duplicate, failure,
transactionality, privacy, and PostgreSQL concurrency behavior are covered by
the existing test suite.

Canonical movement sign follows ADR-0005. `Movement` represents accepted
source-neutral financial truth; provider-native fields remain in evidence.

The observation boundary is now implemented. `FinancialObservation` stores an
immutable interpreted claim and mutable current lifecycle projection.
`ObservationResolution` stores append-only transition history. Deterministic
services support confirm-new, match-existing, reject, conflict, reopen, and
interpretation supersession with Account-scoped concurrency control.

BCI Historical Current Account PDF v0.1 is implemented and validated. Its
evidence-first route preserves unresolved observations and uses a conservative
reconciled Historical-only resolution policy.

## Functional checkpoint

The latest committed functional checkpoint is
`5c9553c1f038dcb9051c4a6a1fdd27309c87860b` (`feat: implement BCI current
cartola XLS parser`). The narrow Current/Recent provenance-conformance
correction is implemented but uncommitted; Git commands at cold start
determine the current working-tree state.

## Observation/resolution checkpoint

This checkpoint implements the accepted ingestion boundary:

```text
Artifact
-> identification / routing
-> deterministic extraction and/or AI interpretation
-> FinancialObservation
-> deterministic validation
-> auditable resolution
-> canonical Movement
```

Resolution may reject evidence, confirm a new movement, match it as support for
an existing movement, mark conflict, reopen review, or retain interpretation
supersession history. Canonical Movement correction remains explicitly
deferred.

Canonical references:

- `docs/product/ingestion-evidence-principles.md`
- `docs/architecture/evidence-resolution.md`
- `docs/architecture/testing-and-ai-evals.md`
- `docs/decisions/ADR-0008-separate-observations-from-canonical-movements.md`
- `docs/decisions/ADR-0009-implement-observation-resolution-boundary.md`
- `docs/sources/bci-current-account-lifecycle.md`

## BCI stress test

The sanitized source note records that Recent Movements is a rolling/recent
view, Current Cartola is an open-period view, and Historical Cartola is a
strongly reconciled closed-period source. The sources overlap, descriptions
are unstable, and no universal transaction identity is proven. Direct
Current-to-Historical rollover overlap has not yet been observed.

This supports an observation/resolution boundary. Historical is now the
implemented BCI slice. Current and Recent source-only parser contracts are
now frozen, but they do not freeze a permanent cross-source identity rule or
authorize lifecycle/canonical interpretation.

## Guardrails

- AI output is always an untrusted structured proposal.
- AI cannot bypass deterministic money, currency, sign, account, identity,
  lifecycle, transactionality, concurrency, or canonical-write rules.
- Provisional evidence may appear only in an explicitly provisional view and
  must not contaminate authoritative totals.
- Do not add confidence, provisional state, parser identity, AI model, or
  source authority to `Movement`.
- Do not introduce a universal numeric confidence/authority score.
- Defer generic plugins, workflows, event sourcing, vector databases,
  embeddings, universal schemas/adapters, multi-agent frameworks, and full
  double-entry accounting.
- Keep financial-domain truth owned by Gouda; a future Atlas may orchestrate
  only through Gouda application boundaries.

## BCI Historical implementation record

The frozen design in
`docs/contracts/bci-historical-current-account-pdf-v0.1.md` is implemented and
validated for BCI Historical only. The parser fails closed on unsupported
native-text geometry, preserves source-specific provenance, computes
independent exact reconciliation checks, and creates unresolved observations
before resolution.

The initial Historical policy may resolve only contract-valid reconciled
statements. Cross-batch exact collisions abstain. A same-batch collision may
use the existing explicit collision override only when distinct ordered rows
in the same reconciled running-balance chain independently prove separate
statement entries. V0.1 performs no automatic `MATCH_EXISTING`.

The implementation reuses `SourceArtifact`, `ImportBatch`, `RawRecord`,
`FinancialObservation`, `ObservationResolution`, and `Movement` without
changing their generic domain semantics. A trusted expected source-account
identifier remains explicit protected caller context for v0.1 rather than a
new binding model.

## Completed source discovery slice

The BCI Current Cartola and Recent Movements source discovery slice is
complete. Their bounded source-only contracts are frozen; unsupported
cross-source identity semantics remain deferred. Universal transaction
identity, canonical Movement correction, overdraft models, AI, and a generic
provider framework remain out of scope.

## Legacy XLS tooling checkpoint

`requirements.txt` pins `xlrd==2.0.1` for read-only legacy XLS inspection.
`tests/test_legacy_xls_dependency.py` verifies the pinned reader dependency;
no synthetic XLS fixture was added because the existing toolchain has no XLS
writer. The available Current Cartola XLS is structurally readable with
`xlrd`; its semantic review is complete and its source-only contract is now
frozen.

## Frozen BCI source-parser contracts

The source-only contracts are frozen at:

- `docs/contracts/bci-current-cartola-v0.1.md`
- `docs/contracts/bci-recent-movements-v0.1.md`

They define deterministic, fail-closed recognition and source-native
extraction only. Current preserves `source_date`, `source_series`,
`source_signed_amount`, and `source_balance` without broader semantics.
Recent preserves distinct transaction/accounting dates, merged `C:F`
descriptions, and Cargo/Abono XOR direction without canonical sign meaning.
The Recent worksheet dimension anomaly is an explicit parser requirement and
is handled by direct OOXML cell discovery. Current uses the pinned legacy-XLS
reader plus a narrow BIFF formula-record check so cached formula values cannot
masquerade as source text. Both implementations have no persistence,
observation resolution, cross-source identity, deduplication, or Movement
behavior.

The joint source-boundary review found one narrow provenance gap. The current
working tree corrects it by requiring explicit nonblank trusted artifact
identity for both current-source parsers, preserving that identity at record
and field level, and recording Recent's selected Cargo or Abono header and
cell coordinate. Frozen recognition and source-native semantics are unchanged.
Historical provenance remains intentionally linked to immutable artifacts at
the `SourceArtifact` / `ImportBatch` / `RawRecord` persistence boundary.

## Current Cartola implementation checkpoint

`bci_current_cartola_v0.1` is implemented as a pure source parser. A thin
`xlrd==2.0.1` adapter produces immutable source-cell snapshots; synthetic
tests exercise recognition, parsing, provenance, formula/type rejection, and
money/date validation without adding an XLS writer or binary fixture. The
available private artifact is recognized read-only with no rejected rows.

## Next checkpoint

After review and commit of the provenance-only correction, acquire a
same-account Historical statement whose intrinsic printed period covers the
existing Current Cartola source dates. Use it only for a read-only rollover
evidence checkpoint; do not define identity, deduplication, lifecycle policy,
or canonical semantics prematurely.

## Cold-start reading order

Read `AGENTS.md`, the README documentation map,
`docs/product/ingestion-evidence-principles.md`,
`docs/architecture/evidence-resolution.md`, relevant ADRs and contracts,
`docs/sources/bci-current-account-lifecycle.md`, then
`.ai/context.md`, `.ai/tasks/current.md`, and this handoff.
