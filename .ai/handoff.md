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

The internal canonical Movement reporting service is implemented. It queries
one trusted persisted Account over an inclusive `Movement.occurrence_date`
range, orders by occurrence date and Movement UUID, computes exact Decimal
count and signed-account-effect total from the returned tuple, and exposes a
bounded source trace without filenames, bytes, digests, raw cells, source
references, running balances, or parser payloads.

Review found and fixed a pre-existing test-isolation defect: the account
orientation migration test restored hard-coded migration `0008` instead of
the current ledger leaf. It now snapshots and restores the leaf target, and
the reporting and migration modules pass in either explicit execution order.

The observation boundary is now implemented. `FinancialObservation` stores an
immutable interpreted claim and mutable current lifecycle projection.
`ObservationResolution` stores append-only transition history. Deterministic
services support confirm-new, match-existing, reject, conflict, reopen, and
interpretation supersession with Account-scoped concurrency control.

BCI Historical Current Account PDF v0.1 is implemented and validated. Its
evidence-first route preserves unresolved observations and uses a conservative
reconciled Historical-only resolution policy.

## Functional checkpoint

The latest committed checkpoint is
`1097f9104f9a5279eb396c842a4f2f5f2094b60e` (`feat: add canonical movement
reporting service`). The Account-access design documentation is currently
uncommitted; Git commands at cold start determine exact state.

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

The joint source-boundary review found one narrow provenance gap. The committed
provenance checkpoint corrected it by requiring explicit nonblank trusted
artifact identity for both current-source parsers, preserving that identity at
record and field level, and recording Recent's selected Cargo or Abono header
and cell coordinate. Frozen recognition and source-native semantics are
unchanged.
Historical provenance remains intentionally linked to immutable artifacts at
the `SourceArtifact` / `ImportBatch` / `RawRecord` persistence boundary.

## Lifecycle evidence-acquisition checkpoint

Intrinsic parser dates, not filenames, show that neither available Historical
statement covers any Current row. The newer Historical period covers a partial
Recent subset, while no available statement covers the complete Recent
capture. Existing evidence therefore cannot test Current rollover or the
uncovered Recent tail.

The open-period chain now contains T1 and T2 Current snapshots plus the
completed one-time paired Recent challenge. BCI produces only three Historical
current-account statements per year. As of August 2026, rollover validation is
deferred until a naturally available Historical artifact has an intrinsic
printed period covering the retained Current dates. It does not block Gouda
development, and no exact future publication date is established.

Later analysis must use source-native candidate sets and sanitized counts only.
Repeated keys stay ambiguous; descriptions and references are hints; bounded
sum groups are split/merge hypotheses. No identity, deduplication, lifecycle,
or canonical rule is authorized by this plan.

## Open-period source strategy checkpoint

Current Cartola is the preferred normal open-period source strategy. Recent
Movements is retained as research and diagnostic support, not as a parallel
operational pipeline. At T1 all 23 Current rows and at T2 all 27 Current rows
have one unique Recent candidate using accounting date, source-native
direction, and magnitude. Recent's deeper rows fall outside Current's parsed
open-tail range. These are candidate observations, not identity.

Current is preferred because it is period-scoped and preserves a source-signed
amount, opaque series, and per-row accounting balance. All 22 T1 and 26 T2
adjacent balance equations hold. Recent provides dual dates and is easier to
maintain as OOXML, but those advantages do not outweigh Current's row-level
validation evidence under the fidelity-first priority. Both Recent captures
contain exactly 50 rows and show boundary replacement consistent with a fixed
rolling shape, but that is not proof of a documented service cap.

The selection must be revisited if later evidence shows Current omitting
same-period rows, truncating or becoming unreliable, failing its balance
chain, or rolling into Historical less usefully than Recent accounting dates.
No parser is deleted or deprecated. An ADR should precede operational
integration after direct rollover evidence is available.

## T2 falsification checkpoint

The one-time paired T2 challenge did not falsify Current as the preferred
normal open-period source. Current recognizes 27 rows and passes all 26
adjacent balance equations. Within the date range defined by parsed Current
source dates, all 27 Recent accounting-date rows have exactly one Current
candidate using source-native direction and magnitude; Recent's other 23 rows
are older, and none is newer than Current's maximum parsed date.

Current retains all 23 T1 candidate signatures in source order and adds four.
Recent remains at exactly 50 rows, drops four candidates at its oldest
boundary, and adds four newer candidates while preserving common order. This
strongly supports a fixed-size rolling shape but does not prove a documented
hard cap. Routine paired capture can stop.

One shared unique Current candidate signature changes description, opaque
series, and row balance between T1 and T2 while the corresponding Recent
candidate retains its transaction date and description. The date,
source-direction category, and magnitude candidate signature remains present.
This is source volatility, not cross-source or cross-capture identity and not
proof of authority. It must remain explicit in the later rollover experiment.

## Current Cartola implementation checkpoint

`bci_current_cartola_v0.1` is implemented as a pure source parser. A thin
`xlrd==2.0.1` adapter produces immutable source-cell snapshots; synthetic
tests exercise recognition, parsing, provenance, formula/type rejection, and
money/date validation without adding an XLS writer or binary fixture. The
available private artifacts are recognized read-only with no rejected rows.

## Account access design checkpoint

Gouda currently has no Django authentication app and no persisted user,
principal, household, member, role, permission, Account owner, or Account grant.
The product makes multi-user sharing out of scope and does not document
named-person access or individual/shared Account behavior. Household net-worth
language defines canonical sign, not ownership.

The bounded MVP design therefore uses one trusted local principal with read
access to every persisted Account. This is a temporary non-persistent access
policy, not ownership. A future delivery adapter must pass untrusted internal
Account UUID selectors through one read-access resolver; it cannot instantiate
or fetch an Account and call reporting directly. The resolver returns a
persisted authorized `Account`, uses one `account_not_accessible` result for
unknown and unauthorized selectors, and grants no import/write capability.

Revisit ownership persistence before a second independently authenticated
principal, different Account visibility, individual/shared Account behavior,
household membership, or persisted grants. No ADR is created because those
durable semantics remain intentionally deferred.

## Next checkpoint

Implement the temporary single-principal read-Account resolver and authorized
reporting orchestration service defined in
`docs/architecture/account-access.md`. Keep principal context opaque and
trusted by application composition, resolve untrusted Account UUIDs before
calling reporting, and use one indistinguishable `account_not_accessible`
failure for unknown or unauthorized Accounts. Do not add HTTP/DRF,
authentication, ownership persistence, models, migrations, UI, or writes.
Recommended reasoning level: Sol High.

## Roadmap reassessment

The implemented foundation now includes two Santander canonical-write routes,
BCI Historical evidence and resolution, Current/Recent source-only parsers,
and the first internal canonical query/period-total/source-trace service.
Classification, API, authentication/ownership, and frontend product surfaces
remain absent.

Priorities are:

1. Implement the temporary single-principal read-Account resolver and
   authorized reporting orchestration boundary without HTTP or authentication.
2. Choose and implement authentication plus a narrow read-only delivery layer
   only after the resolver is enforced. DRF is accepted by ADR-0002 but is not
   installed or configured.
3. Define classification semantics and persistence for the MVP types before
   implementing category/type filters. Provider categories and amount signs
   are not canonical income/expense semantics.
4. Add an operational import/API surface for the already implemented
   Santander services only after the account-access and upload-security
   boundary is explicit.
5. Resume Current-to-Historical validation only on the external artifact
   trigger described above.

Cross-source identity/deduplication, transfer pairing, household-flow
classification, provisional/open-period views, BCI Current persistence,
canonical Movement correction/replacement, AI ingestion, additional source
adapters without evidence, and generic workflow/provider frameworks remain
deferred.

## Cold-start reading order

Read `AGENTS.md`, the README documentation map,
`docs/product/mvp-scope.md`, `docs/product/ingestion-evidence-principles.md`,
`docs/architecture/domain-model.md`, `docs/architecture/evidence-resolution.md`,
relevant ADRs and contracts,
`docs/sources/bci-current-account-lifecycle.md`, then
`.ai/context.md`, `.ai/tasks/current.md`, and this handoff.
