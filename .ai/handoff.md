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
references, running balances, or parser payloads. Each item also carries a
bounded immutable current-classification projection: never assigned, currently
classified with Category UUID/display/active state, or explicitly cleared,
plus the applicable revision.

The Account read boundary, discovery operation, and authorized reporting
orchestration are implemented. One opaque module-issued local principal may
read all persisted Accounts under the temporary non-ownership policy.
`list_read_accounts` returns only Account UUID, canonical display name, product
kind, and currency in display-name/UUID order. Unknown and policy-denied
selectors remain indistinguishable, and reporting returns the existing
`MovementReport` without widening provenance or writing state. The HTTP
serializer now includes its immutable current classification projection.
`list_read_categories` adds frozen Category summaries and
`GET /api/v1/categories/` discovers active/inactive labels with only UUID,
display name, and active flag in display-name/UUID order. There are no counts,
pagination, or accepted query parameters. Category visibility is a temporary
dataset read policy, not ownership or write permission.

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

The local React/TypeScript client consumes Account discovery and Movement
reporting. It discovers Accounts, keeps UUIDs as internal
selectors, accepts inclusive dates, and renders backend count, exact net signed
amount, and canonical Movement date/description/amount/currency. It does not
retain or render `source_trace`, recompute totals, convert decimal strings to
numbers, or issue writes or authentication material. Its strict client
projection now retains current classification, and the Movement table renders
Category names, inactive state, or the shared `Unclassified` presentation.

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
same HEAD/`origin/main` and exactly the 16 expected changed paths. That commit
authorization was specific to the completed persistence checkpoint; the current
HTTP task permits neither commit nor push. The following bootstrap results are
historical.

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

The repository exposes three JSON-only endpoints at `/api/v1/accounts/`,
`/api/v1/categories/`, and `/api/v1/accounts/<account_uuid>/movements/`.
DRF is configured with no
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
- At this persistence checkpoint, reports, discovery/access, HTTP API, React,
  and imports were unchanged. No API writes, filters, UI, default taxonomy,
  automation, history, ownership, transfer/economic types,
  notes/tags/hierarchy, or provider mapping was added.

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

## Completed internal classification reporting checkpoint

This checkpoint extends only `gouda.ledger.services.movement_reporting` from
the clean, fetched baseline
`bf70b85d56e831e2422c92562eb14ff10f77f548`. The resulting committed baseline is
`8973eb8c25a2334323a8bb932966059bba49259e`
(`feat: project movement classification in reporting`). The following results
are historical; the current HTTP checkpoint is described below.

Every internal `MovementReportItem` has an immutable
`MovementClassificationProjection` with bounded state, optional immutable
Category summary, and revision:

- `NEVER_ASSIGNED` means no row and uses null category plus revision 0;
- `CLASSIFIED` includes Category UUID, display name, active state, and the
  persisted positive revision; and
- `CLEARED` preserves a retained row as null category plus its persisted
  positive revision.

Never-assigned and cleared remain distinct but both are unclassified for
future filtering. Inactive Categories stay visible as current assignments.
Assignment source and timestamp are omitted because no current reporting
consumer needs them; revision supplies mutation coordination. No ORM object,
historical assignment, provider metadata, or raw persistence field is exposed.

The existing Movement query adds nullable `select_related` joins through the
one-to-one classification and Category. Together with the existing safe
provenance join, the report remains two queries independent of Movement count:
one Account existence check and one consistent joined Movement read. Left joins
cannot remove or multiply Movements. Tests prove classification changes do not
alter membership, inclusive occurrence-date bounds, Account scope, ordering,
count, exact signed total, provenance, date, signed amount, currency, or
description.

At that internal checkpoint, the HTTP serializer omitted classification. The
two routes, request/error contracts, React client types/parsing/rendering,
manual mutation API, filters, models, migrations, imports, and demo seed are
unchanged. ADR-0011 is unchanged.

Validation on isolated PostgreSQL 16.14, host Django 4.2.30/Python 3.9.6:

- Focused reporting/classification/concurrency/API/Account/demo: 99 passed.
- Full Django suite: 466 passed.
- Migration/isolation forward and reverse orders: 55 passed each.
- Santander XLSX/TDC and BCI Historical/Current/Recent coverage: 271 passed,
  including the pinned legacy-XLS dependency check.
- Local delivery/Compose/API/demo matrix: 75 passed.
- Explicit `0010 -> 0011` upgrade, Django system check, migration drift,
  Python compilation, `pip check`, and `docker compose config` passed.
- Frontend: 14 tests, TypeScript check, Vite build, and `npm ls` passed.
- Markdown links: 41 files and 53 local links passed. `git diff --check` and
  final Git-path review passed.
- Added-text privacy scanning found no key, credential, email, or long numeric
  identifier patterns. `.env` and `private/` remain ignored; no private path is
  tracked or changed, and no private evidence was inspected.
- Commit review validation used only the isolated synthetic PostgreSQL container
  `gouda-classification-reporting-review-pg16` on loopback port 55441. It was
  stopped and removed after validation; no existing database was read or
  modified.

## Completed read-only classification HTTP checkpoint

Started from clean fetched `main` with HEAD and `origin/main` both exactly
`8973eb8c25a2334323a8bb932966059bba49259e`. Review revalidated the checkpoint
for one commit titled `feat: expose movement classification read api`; Git
history records the exact resulting SHA. Do not push.

The HTTP report now maps the immutable classification projection directly:
state, optional Category (`id`, `display_name`, `is_active`), and persisted
revision. All three states and inactive assignments remain distinct and
faithful. No extra classification query or semantics exist in HTTP.
The new `GET /api/v1/categories/` returns only `{"categories": [...]}` with
the same three Category fields. It includes inactive labels and rejects query
parameters using the Account discovery policy. The access module's
`list_read_categories` validates the existing opaque principal before one
ordered query and materializes frozen summaries.

No model, migration, internal reporting query, classification command, source
adapter, demo, runtime, settings, or frontend file changed. Account behavior,
financial membership/order/count/total/fields, and safe provenance are retained.
ADR-0010 and ADR-0011 are unchanged: mutations remain internal only, with no
classification filtering/UI or transfer/income-expense semantics.

Validation on isolated PostgreSQL 16.14, Django 4.2.30/Python 3.9.6, and Node
24.16.0:

- Focused discovery/API/reporting/classification/concurrency/Account/local
  delivery/Compose/demo matrix: 144 passed (initial focused slice: 50 passed).
- Santander Current/TDC and BCI Historical/Current/Recent regressions, including
  the legacy-XLS dependency check: 271 passed.
- Migration isolation in forward and reverse orders, run sequentially: 98
  passed each. The matrix includes all migration modules, reports, new
  discovery, models, and demo; explicit 0010 upgrade is covered.
- Full Django suite: 481 passed, including 15 new tests. No unresolved failures.
- Fresh migrations through 0011, system check, migration drift, Python syntax,
  `pip check`, and `docker compose config --quiet` passed. No migration added.
- Frontend: all 14 tests, typecheck, build, and `npm ls` passed. A separate
  local check exercised the unchanged TypeScript parser with all three
  classification shapes, proving accept-and-discard behavior and exact amounts.
- Real numeric-loopback `runlocal` HTTP smoke test passed for both discovery
  operations, all classification transitions, inactive labels, unchanged
  financial payloads, GET-only policy, JSON negotiation, and query rejection.
  The temporary HTTP server was stopped. A full Compose/browser rebuild was
  not rerun; frontend, runtime, and deployment files are unchanged.
- Markdown validation: 41 files, 53 local links, and 5 HTTP JSON examples pass.
  Added-text privacy scans found no credentials, keys/tokens, or email addresses;
  large numeric literals are established synthetic Decimal test values.
  `.env`, `private/`, and `data/private/` remain ignored and untracked.
- All 17 changed/new paths were reviewed. Python syntax, final-newline and
  whitespace checks, `git diff --check`, and empty-index checks pass. No private
  evidence was inspected and no frontend, ADR, model, or migration file changed.

The first database attempt was blocked by sandbox loopback networking; the
approved retry and complete matrix passed. Commit review reran the 144-test
focused matrix, 271 source regressions, both 98-test migration orders, the
481-test full suite, and all static/frontend checks with identical passing
results. Docker Desktop was started for validation. The implementation used
`gouda-classification-api-pg16` on loopback port 55442; commit review used
`gouda-classification-api-review-pg16` on port 55443. Both disposable containers
and synthetic databases were stopped and automatically removed. No existing
application database or volume was read or changed. Local-only logs remain at
`/private/tmp/gouda-classification-api-validation/`; validation, HTTP smoke, and
hygiene scripts are `/private/tmp/gouda-classification-api-validate.py`,
`/private/tmp/gouda-classification-api-smoke.py`, and
`/private/tmp/gouda-classification-api-hygiene.py`.

Final state after that review: `main` had one local commit above unchanged
`origin/main`; the working tree and index were clean, and nothing was pushed.
Local adversarial review found no financial, trust, or query
regression: serializers consume explicit values, principal validation precedes
database access, and classification joins remain owned by the unchanged report.

## Current frontend classification checkpoint

Started from clean fetched `main` with HEAD and `origin/main` both exactly
`a4877af9d20e67f13a508301977a0b16a356272a`
(`feat: expose movement classification read api`). Review revalidated the
checkpoint for one commit titled
`feat: render movement classification in local client`; Git history records
the exact resulting SHA. Do not push.

The React API projection now retains classification as a strict discriminated
union. The parser validates exact nested keys, bounded state/category/revision
combinations, Category UUID/display/active fields, and safe integer revisions.
Invalid combinations fail the whole report closed. Existing Decimal strings
remain strings, and source provenance continues to be discarded.

The Movement table adds a compact dedicated Classification column. Active
assignments show the Category display name; inactive assignments add an
`Inactive` marker. `NEVER_ASSIGNED` and `CLEARED` remain internally distinct
but both render as `Unclassified`. UUIDs, revisions, raw enum values, source,
timestamps, and history are not shown. Valid long names wrap, while empty,
overlong, padded, or control-character names fail parsing.

The client does not fetch `GET /api/v1/categories/`: each classified Movement
already carries the complete display projection. Existing Account discovery
and explicit report-load cadence are unchanged. No write method, edit control,
filter/search, category total, auth/principal material, CORS change, taxonomy,
transfer meaning, or income/expense meaning was added. ADR-0010 and ADR-0011
are unchanged.

Validation used the existing frontend dependencies and a disposable PostgreSQL
16.14 container with only synthetic credentials and data:

- Frontend: 36 tests passed; TypeScript checking, Vite production build, and
  `npm ls` passed.
- Backend compatibility: all 20 Movement HTTP API tests passed.
- Full Django suite: all 481 tests passed with no unresolved failures.
- Markdown links, added-text privacy scans, ignored/private-path checks, exact
  changed-path review, and `git diff --check` passed.
- Commit review reran the same frontend checks, all 20 Movement API tests, the
  481-test full Django suite, `pip check`, and all static hygiene checks with
  identical passing results. The initial backend attempt was blocked only by
  sandbox loopback policy; its approved retry passed.
- The isolated implementation and review containers
  `gouda-classification-ui-pg16` and
  `gouda-classification-ui-review-pg16`, on loopback ports 55444 and 55445,
  were stopped and automatically removed. No existing database or private
  corpus was read or changed.

Final state after review: `main` has one local commit above unchanged
`origin/main`; the working tree and index are clean, and nothing was pushed.

## Next checkpoint

Design the narrowest safe local classification write boundary before
implementing any HTTP mutation endpoint. Gouda now has the internal
revision-checked command, read HTTP projection, and read-only client needed to
specify a concrete manual-edit workflow. The design must revisit ADR-0010,
separate write authorization from read access, and define CSRF/origin and
optimistic-concurrency behavior. Filtering remains deferred. No write boundary
or mutation is implemented in this checkpoint.
Recommended reasoning level: High.

## Roadmap reassessment

The implemented foundation now includes two Santander canonical-write routes,
BCI Historical evidence and resolution, Current/Recent source-only parsers,
the first internal canonical query/period-total/source-trace service, and the
minimum backend API read surface for Account selection plus Movement reporting,
the first local browser read client, and the reproducible three-service demo
bootstrap. Manual classification persistence/service is implemented;
its internal and read-only HTTP projections are also implemented, alongside
read-only Category discovery and read-only React rendering.
Authentication/ownership remain absent.

Priorities are:

1. Design the narrowest safe local classification write boundary before
   enabling any manual HTTP edit. The design must revisit ADR-0010; filtering,
   economic types, and transfer semantics remain deferred.
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
