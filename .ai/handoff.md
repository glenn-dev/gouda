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

The persistence/service checkpoint implements ADR-0011 and is recorded as
`feat: implement movement classification domain` on `main`; Git history gives
its exact SHA. At implementation start on 2026-09-05, the working tree was
clean and HEAD/`origin/main` both equaled
`964e85ef82c9af7cfdb551f3bf2cb188ac06d966`
(`docs: freeze movement classification semantics`). Commit review verified that
same HEAD/`origin/main` and exactly the 16 expected changed paths. One local
commit is authorized; no push is authorized. The section below records current
capabilities and validation. The following bootstrap results are historical.

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

## Classification implementation checkpoint

The frozen [ADR-0011](../docs/decisions/ADR-0011-movement-classification.md)
is unchanged. The [classification contract](../docs/architecture/movement-classification.md)
now documents the implemented fields, internal API, stable errors, and locks.

- Category has exactly UUID, display name, and active flag. Model saves apply
  repository NFC/trim/control-character semantics while preserving casing.
  PostgreSQL enforces unique `Lower(display_name)` across active/inactive rows.
- MovementClassification has exactly the protected Movement primary key,
  nullable protected Category, MANUAL-only source, positive bigint revision,
  and explicit server update time. No Movement column or provenance changes.
- `set_movement_classification(account, movement_id, category_id,
  expected_revision)` is a keyword-only trusted internal command returning
  immutable state. It accepts UUID selectors and verifies persisted objects.
  It locks Account -> Movement -> selected Category in one atomic transaction.
  First assignment starts at 1; changes/clear/reassign increment once; correct
  no-ops do not save. Stale revisions fail before no-op detection.
- Inactive references remain attached. Same-category no-ops and clear work;
  new inactive targets fail. Retirement coordinates on the Category row lock.
- Migration `0011_movement_classification` follows `0010`, adds only two empty
  tables with constraints, and has no forward data migration/backfill. Reverse
  takes exclusive table locks and refuses if either new table has data.
- Demo implementation is untouched. Seed/reseed creates no categories or
  classifications and preserves later manual assignments/clears. Protected
  cleanup fails atomically for assigned or cleared demo Movements.
- Existing reports, discovery/access, HTTP API, React, and imports are unchanged.
  No API writes, filters, UI, default taxonomy, automation, history, ownership,
  transfer/economic types, notes/tags/hierarchy, or provider mapping was added.

Tests added: six Category tests, twelve service/model/compatibility tests,
six real PostgreSQL concurrency tests, five migration tests, and one demo
protection/reseed test (30 total). Concurrency tests use separate connections
and verify overlapping database lock waits through `pg_blocking_pids`, covering
first-write, identical first-write, competing update, clear/change,
reassignment, and category retirement. Migration tests restore the graph leaf.

Validation on isolated PostgreSQL 16.14, host Django 4.2.30/Python 3.9.6:

- Focused classification/model/service/concurrency: 24 passed.
- Migration/isolation order and reverse order: 52 passed each, sequentially.
- Demo/report/API/Account access/discovery/local delivery/Compose: 102 passed.
- Santander XLSX/TDC and BCI Historical/Current/Recent regression matrix:
  271 passed.
- Full Django suite: 463 passed (baseline 433 plus 30 added).
- Fresh schema and explicit `0010 -> 0011` upgrade passed; new tables stay empty.
- Django system check, migration drift, and `pip check` passed.
- Frontend: 14 tests, TypeScript check, and Vite build passed on Node 24.16.0.
- Markdown links: 41 files and 55 local links passed.
- Added-text privacy scans found no keys/tokens, email addresses, long numeric
  identifiers, or credential literals. Ignored `.env`, `private/`, and
  `data/private/` remain untracked. No private evidence was inspected.
- `git diff --check`, final-newline/whitespace checks including untracked files,
  and review of all 16 changed/new paths passed. Operational state was checked
  for stale implementation claims; only intentionally deferred scope remains.
- Local adversarial review checked lock order, absent-row serialization,
  stale no-ops, inactive targets, protected deletion, deferred-instance
  reparenting, reverse-migration data loss, and financial/provenance isolation.

The commit review checked all 57 requested requirements. No production defect
or ADR contradiction was found. Two review tests explicitly prove raw-SQL
uniqueness/NULL/empty-string rejection and bulk/update/SQL bypass of application
normalization. The database nonempty check does not claim whitespace-only or
Unicode normalization enforcement. Those are model-save rules. Parent FK
integrity is database-enforced; Django `PROTECT` supplies the ORM deletion error.
The reverse guard is retained intentionally, consistent with prior migrations:
empty rollback works; populated rollback requires an explicit data-loss
decision or a forward repair. Schema rollback assumes writers are stopped.
All existing model definitions were compared structurally and remain unchanged.

The first focused run found a deferred-model reparenting validation gap and a
zero-migration test helper error. Both were corrected before the successful
matrix. No unresolved test failures remain. Validation logs are local-only at
`/private/tmp/gouda-classification-validation/`; the runner is
`/private/tmp/gouda-classification-validate.py`. The isolated test container is
`gouda-classification-pg16` on loopback port 55439 used synthetic credentials
and has been stopped and automatically removed. No existing database or private corpus
was read or modified. Full-stack/browser launch was not rerun because runtime,
Compose, HTTP and frontend source are unchanged; their automated regressions
passed.

## Next checkpoint

Extend only the internal canonical Movement report to project current
classification in one consistent read, including absent/cleared assignments
and inactive labels. Preserve Account/date membership, ordering, exact signed
totals, and source trace. Defer HTTP/UI/filter changes to separate work.
Read ADR-0011 and the classification contract after the standard resume
sequence. Recommended reasoning level: High.

## Roadmap reassessment

The implemented foundation now includes two Santander canonical-write routes,
BCI Historical evidence and resolution, Current/Recent source-only parsers,
the first internal canonical query/period-total/source-trace service, and the
minimum backend API read surface for Account selection plus Movement reporting,
the first local browser read client, and the reproducible three-service demo
bootstrap. Manual classification persistence/service is implemented;
authentication/ownership remain absent.

Priorities are:

1. Extend the internal read projection with current classification before
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
