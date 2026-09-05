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

The Account read boundary, discovery operation, and authorized reporting
orchestration are implemented. One opaque module-issued local principal may
read all persisted Accounts under the temporary non-ownership policy.
`list_read_accounts` returns only Account UUID, canonical display name, product
kind, and currency in display-name/UUID order. Unknown and policy-denied
selectors remain indistinguishable, and reporting returns the existing
`MovementReport` without widening provenance or writing state.

The local-MVP caller-trust and network contract is frozen in ADR-0010. An
unauthenticated read adapter is permitted only behind an explicit numeric
loopback host edge on a single-user or fully trusted machine. Wildcard, LAN,
remote, tunneled, proxied, forwarded, shared-host, production, and ambiguous
exposure requires real authentication or fails closed. This is deployment
trust, not caller authentication.

The runtime checkpoint implements the direct host and Compose boundaries.
`runlocal` owns an explicit `127.0.0.1` or `::1` host bind. Its separate
trusted-container-network mode owns only an internal `0.0.0.0` bind and is
restricted to Compose's fixed port `8000`; it is valid solely with the
repository Compose perimeter. Both activate an opaque
in-memory runtime only while Django's server runner is active. The runtime may
issue the existing principal without request input. Direct `runserver`, WSGI,
or ASGI launches do not activate it.

The local React/TypeScript client consumes the two read endpoints. It
discovers Accounts, keeps UUIDs as internal
selectors, accepts inclusive dates, and renders backend count, exact net signed
amount, and canonical Movement date/description/amount/currency. It does not
retain or render `source_trace`, recompute totals, convert decimal strings to
numbers, or issue writes or authentication material.

For host development, Vite binds explicitly to `127.0.0.1:5173` and proxies
only `/api` to `http://127.0.0.1:8000`. The primary Compose path publishes Vite
at the same numeric-loopback URL, leaves Django unpublished, and fixes the
container proxy target to `http://backend:8000` on an internal network. Neither
proxy arrangement authenticates callers or issues principal context; Django
still requires the active `runlocal` runtime.

The committed baseline includes the complete Compose bootstrap and deterministic
demo commands. `seed_demo` creates two CLP Accounts and eleven fixed-date
canonical Movements with overtly synthetic provenance envelopes. `clear_demo`
uses the fixed UUIDv5 set and reverse dependency order to remove only that
graph. One narrow migration adds `DEMO_SYNTHETIC` source/record choices because
the existing closed provenance constraints would otherwise require a false
bank-source claim. No `is_demo` financial field, classification, transfer, or
production-import behavior is added.

Account-access validation exposed a pre-existing migration-test isolation
defect: the checkpoint migration module restored hard-coded migration `0008`
instead of the graph leaf, so modules executed afterward saw an old schema.
The migration test class now restores the current graph leaf in `tearDown`;
explicit migration-before-reporting and reporting-before-migration orders are
part of this checkpoint's validation.

The observation boundary is now implemented. `FinancialObservation` stores an
immutable interpreted claim and mutable current lifecycle projection.
`ObservationResolution` stores append-only transition history. Deterministic
services support confirm-new, match-existing, reject, conflict, reopen, and
interpretation supersession with Account-scoped concurrency control.

BCI Historical Current Account PDF v0.1 is implemented and validated. Its
evidence-first route preserves unresolved observations and uses a conservative
reconciled Historical-only resolution policy.

## Functional checkpoint

The latest implementation checkpoint is
`76a1647ab005175418e7b7175fc3e3ec9abb3589` (`feat: add local demo bootstrap`).
On 2026-09-05, a fresh fetch verified HEAD and `origin/main` at this commit on
`main`, with a clean starting tree. The classification design below is the
subsequent documentation-only checkpoint, identified in Git history by
`docs: freeze movement classification semantics`. Its commit review verified
the same baseline and exactly the ten expected paths. The user authorized one
commit and no push; Git commands at cold start determine exact state.

At that bootstrap checkpoint, the focused demo/Compose/local-delivery suite
passed 42 tests and the full Django suite passed 433 tests in a fresh
PostgreSQL 16 Compose stack. Both 18-test migration/demo orderings passed.
Pinned image builds, clean automatic
migrations, all service health checks, repeated seeding, the frontend root,
Account discovery, and an April Movement report through the browser-facing
proxy pass. Live cleanup succeeds twice, leaves the Account API empty, and
`docker compose down` preserves the named volume.

All 14 frontend tests, TypeScript checking, the Vite build, `npm ls`, Django
system checking, migration drift, `pip check`, `docker compose config`, Python
compilation, 39-file Markdown link validation, diff whitespace, and ignored
`.env`/`private` checks pass. The default pre-existing Gouda volume was not
deleted or altered to repair its historical migration-ledger mismatch; clean
startup validation used the isolated `gouda-bootstrap-test` project instead.

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

## Account access implementation checkpoint

Gouda currently has no Django authentication app and no persisted user,
principal, household, member, role, permission, Account owner, or Account grant.
The product makes multi-user sharing out of scope and does not document
named-person access or individual/shared Account behavior. Household net-worth
language defines canonical sign, not ownership.

The bounded MVP implementation uses one opaque module-issued trusted local
principal with read access to every persisted Account. This is a temporary
non-persistent access policy, not ownership or authentication.
`resolve_read_account` validates that principal and an untrusted UUID selector,
returns a persisted authorized `Account`, and uses one
`account_not_accessible` result for unknown and policy-denied selectors.
`list_read_accounts` validates the same principal before database access,
applies the same temporary read policy, and returns immutable privacy-safe
summaries rather than ORM objects.
`report_authorized_canonical_movements` composes the resolver with the existing
canonical report and returns `MovementReport` unchanged. It translates only a
post-resolution Account disappearance to the non-enumerating access failure;
date failures propagate unchanged. Both services are read-only.

The module exposes `trusted_local_principal_context()` solely for trusted
server-side composition. Strings, other context instances, Accounts, UUIDs,
artifacts, and provider evidence cannot establish principal context. This is
an application convention, not a Python-level security claim. The HTTP
delivery adapter calls the authorized orchestration operation rather than
fetching an Account directly.

Revisit ownership persistence before a second independently authenticated
principal, different Account visibility, individual/shared Account behavior,
household membership, or persisted grants. ADR-0010 records only the temporary
network exposure contract; durable ownership semantics remain deferred.

## Local delivery trust checkpoint

The repository exposes two JSON-only endpoints at `/api/v1/accounts/` and
`/api/v1/accounts/<account_uuid>/movements/`. DRF is configured with no
authentication classes, no Django anonymous user, and no browsable renderer.
Django auth, CORS, CSRF middleware, and Account CRUD remain absent. The frontend
uses only relative GET requests and retains no authentication or
source-provenance state. Compose publishes PostgreSQL at `127.0.0.1:5432` and
Vite at `127.0.0.1:5173`; it publishes no Django port.

The canonical host launch remains `python manage.py runlocal --host 127.0.0.1
--port 8000`, with deliberate `::1` support. The host is required and exact;
the port is an ASCII decimal 1 through 65535. Unsafe or ambiguous values fail
before server delegation. Generic Django startup reaches the route but receives
`local_delivery_not_active` before selector parsing or database access.

`gouda.local_delivery` activates one opaque non-persisted runtime for the
validated server lifetime. Its no-argument method may obtain the existing
trusted local principal; the active-runtime lookup fails closed outside that
lifetime. The command constructs the only downstream Django bind argument and
disables autoreload. Direct mode allows only numeric loopback. Explicit
container mode allows only internal `0.0.0.0:8000`; it does not inspect Docker
NAT or publication.

`docs/security/local-mvp-network-boundary.md` still defines local as
machine-local numeric IP loopback, not process locality or LAN proximity.
Container-internal wildcard binding remains allowed only behind explicit
loopback host publication and a trusted private application network. The
repository Compose file and static tests enforce that configuration. Gouda
cannot detect external overrides, tunnels, proxies, NAT, SSH forwarding,
unsupported launchers, untrusted containers attached by a Docker-privileged
operator, or hostile local processes.

## Classification design checkpoint

The 2026-09-05 session freezes category organization in
[ADR-0011](../docs/decisions/ADR-0011-movement-classification.md) and the
[classification contract](../docs/architecture/movement-classification.md).
It compares nullable Movement fields, separate current state, append-only
assignments, many-to-many labels, and current state plus revisions.

The choice is zero/one local dataset Category in a separate mutable
MovementClassification, with manual-only source, optimistic revision, and
last-change timestamp. An absent row means never assigned; a retained null
category means cleared. Both remain unclassified. Category has UUID, short
display name, and active flag; no code, hierarchy, notes, economic type, or
fake household owner. Prior assignments are not recoverable, and automated
classification/history/ownership have explicit revisit triggers.

The design does not infer classification from signs or provider categories,
does not permit a Transfer category workaround, and keeps income/expense and
shared-event semantics deferred. Product scope/glossary/vision and architecture
entry points reflect this decision. The earlier MVP type list is deliberately
narrowed; no income/spending report is promised by topic categories.

The two new tables will start empty, with no financial rewrite or backfill.
The current demo stays classification-free. A later demo extension should use
explicit deterministic fixture mappings after a separate provenance decision,
preserve manual edits/clears, and validate bounded cleanup. No future source
value is frozen or reserved by this checkpoint.
The first persistence task retains existing `clear_demo` protected failure
when a demo Movement has classification state.

Classification code, migrations, report/API/client changes, and demo edits have
not been implemented. The runtime test counts above belong to the prior
bootstrap and were not rerun for this documentation-only session.

Classification-design checks passed on 2026-09-05:

- Markdown local-link validation: 41 files and 55 local links; no fragment
  links were present. All destinations exist.
- `git diff --check` plus whitespace/final-newline checks on new files pass.
- All 10 changed files are Markdown under product, architecture, decisions,
  or `.ai/`; no production code, migration, source contract, or demo changed.
- Added-text privacy scanning found no credential/token, private-key, long
  numeric-identifier, or email patterns. Manual review confirmed only generic
  labels and synthetic examples, with no private source content copied.
- `.env`, `private/`, and `data/private/` remain ignored and untracked.
  No database, private evidence, or source artifact was read
  or modified for this design.
- Design adversarial review checked stale-write/clear/reassign behavior,
  retired categories, history limitations, sign and provider separation,
  reporting row cardinality, and demo protected cleanup.

The commit review checked all 31 requested requirements. It removed the
preselection of future demo provenance, marked detailed API shapes as
illustrative rather than frozen, and made PostgreSQL uniqueness, atomic
revision enforcement, and financial/import-state preservation explicit.
Only the eight modified and two new expected documentation paths belong in
the commit. No production code or migration is included. No push is authorized;
`origin/main` remains at the bootstrap baseline. Check local Git state for the
classification commit SHA and any subsequent work.

## Next checkpoint

Implement the two classification models and transport-independent manual
assign/change/clear service under the frozen contract, with focused PostgreSQL
invariant, migration, concurrency, and import/report/demo regression coverage.
This is one persistence/service task; no reporting/HTTP/UI, taxonomy seeding,
demo extension, automated classification, transfer, or ownership scope.
Read ADR-0011 and the classification contract first after the standard resume
sequence. Recommended reasoning level: Sol High.

## Roadmap reassessment

The implemented foundation now includes two Santander canonical-write routes,
BCI Historical evidence and resolution, Current/Recent source-only parsers,
the first internal canonical query/period-total/source-trace service, and the
minimum backend API read surface for Account selection plus Movement reporting,
the first local browser read client, and the reproducible three-service demo
bootstrap. Classification design is frozen, while classification persistence
and authentication/ownership remain absent.

Priorities are:

1. Implement the frozen manual category persistence/service boundary before
   category filters or UI. Economic types and transfer semantics remain deferred.
2. Add an operational import/API surface for the already implemented
   Santander services only after the account-access and upload-security
   boundary is explicit.
3. Resume Current-to-Historical validation only on the external artifact
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
