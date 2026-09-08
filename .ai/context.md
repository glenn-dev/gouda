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
  source payloads or filenames. Each item also projects current classification
  as `NEVER_ASSIGNED`, `CLASSIFIED`, or `CLEARED`, with bounded Category display
  fields and revision.
- The account-orientation migration test now restores the current ledger leaf
  migration, removing its pre-existing schema leakage into later test modules.
- The fail-closed local-delivery bootstrap is implemented. The dedicated
  `runlocal` command accepts explicit numeric `127.0.0.1` or `::1` for direct
  host delivery and the exact internal `0.0.0.0:8000` endpoint only under its
  explicit trusted Compose-network mode. It owns Django's downstream bind and
  activates one
  non-persisted opaque runtime only during the server runner lifetime.
  Principal issuance requires that runtime.
- Django REST Framework 3.16.x is configured without authentication and with
  JSON-only rendering. Account/Category discovery and canonical Movement report GET
  endpoints fail closed without the active runtime.
- A minimal Vite + React + TypeScript client implements Account discovery,
  internal UUID selection, inclusive date input, and canonical Movement report
  rendering. It preserves exact decimal strings, omits source provenance, and
  now renders validated current classification without issuing write requests.
- The primary local Compose path starts pinned PostgreSQL, Django, and Node
  images with health dependencies. Only Vite and PostgreSQL are published on
  numeric host loopback; Django is unpublished behind the internal application
  network. Explicit commands seed and clear a deterministic two-Account,
  eleven-Movement synthetic demo graph through fixed UUIDv5 identities. Narrow
  `DEMO_SYNTHETIC` source/record choices preserve truthful mandatory provenance
  without adding an Account/Movement demo field or production import route.

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

The current completed design checkpoint is
[Gouda UI Foundation v0.1](../docs/design/ui-foundation.md), frozen on
2026-09-08 after fetching and verifying clean `main`, with HEAD and `origin/main`
both `092a22429b2aa4c9d79ca7f5d3436b2f7484d54c`
(`feat: implement local classification write boundary`) and a valid SSH signature.
The foundation is documentation only: system typography, neutral semantic
colors, a restrained ledger list, exact signed-money presentation, and four
approved shadcn controls. Tailwind/shadcn and the restyle are not implemented.
The next bounded task is its read-client implementation; the manual editor
follows separately under ADR-0012. This checkpoint authorizes one signed
`docs: define Gouda UI foundation` commit and no push.

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

ADR-0010 and `docs/security/local-mvp-network-boundary.md` freeze the temporary
delivery trust contract. An unauthenticated read adapter may issue the local
principal only under explicit numeric loopback host exposure on a single-user
or fully trusted host, with no wildcard/LAN bind, unspecified Docker
publication, tunnel, proxy, forwarding, or production exposure. Request data
never establishes principal trust. LAN, remote, shared-host, ambiguous, or
broader exposure requires real authentication.

The repository exposes three read operations under the same active `runlocal`
runtime. `GET /api/v1/accounts/` returns only authorized Account UUID,
canonical display name, product kind, and currency, ordered by display name
then UUID. It rejects all query parameters.
`GET /api/v1/categories/` returns only Category UUID, display name, and active
flag for all active/inactive Categories, ordered by display name then UUID,
under the same temporary dataset read policy. Its response has only a
`categories` array; no counts, pagination, or query parameters are accepted.
`GET /api/v1/accounts/<account_uuid>/movements/` retains its strict inclusive
`start_date` and `end_date` contract and approved `MovementReport` projection.
Each Movement now includes the immutable current classification projection.
Discovery uses `list_read_accounts` or `list_read_categories`; reporting resolves through
`report_authorized_canonical_movements`. Generic `runserver`, WSGI, ASGI,
headers, cookies, query values, and bodies do not establish trust.

DRF has no authentication classes or Django anonymous auth user, and only the
JSON renderer is enabled. Django auth, sessions, tokens, users, ownership,
CORS, and Account CRUD remain absent. In direct host development, React binds
Vite to `127.0.0.1:5173` and proxies only `/api` to the validated backend at
`127.0.0.1:8000`. In Compose, only Vite is browser-facing at that loopback URL;
it proxies `/api` to the unpublished Django service. Neither proxy arrangement
is authentication or principal issuance. The container runtime does not claim
to verify Docker publication; repository configuration and tests enforce it.

The historical 2026-09-07 implementation checkpoint started from fetched clean `main` with
HEAD and `origin/main` exactly `bb09f7c0d281f68010baed9ed56055b45a02b88e`
(`docs: define local classification write boundary`), verified with a good local
SSH signature. The authorized implementation commit is
`feat: implement local classification write boundary`; Git history supplies its
resulting SHA. Its reviewed result is the fetched `092a224` baseline above.

[ADR-0011](../docs/decisions/ADR-0011-movement-classification.md) and
[Movement classification](../docs/architecture/movement-classification.md)
now have implemented Category and MovementClassification persistence plus
`set_movement_classification`. Two new initially empty tables, PostgreSQL
case-insensitive label uniqueness, protected references, manual-only source,
positive revision, and a guarded reverse migration preserve the frozen design.
Account -> Movement -> target Category locking protects first assignments and
revision-checked change/clear/reassign. Correct-revision no-ops retain time and
revision; inactive categories retain existing references, allow no-ops/clear,
and reject new assignments. Source/financial fields remain untouched.

The internal canonical report now adds a frozen current-classification
projection to each Movement. Never-assigned rows use revision 0; classified
rows expose Category UUID, display name, active state, and revision; cleared
rows retain their positive revision without a Category. Never-assigned and
cleared are distinguishable and both remain unclassified. Source and timestamp
are excluded. Nullable joins extend the existing Movement/provenance query, so
reports remain two queries independent of Movement count.

Classification changes never affect Account/date membership, ordering, count,
exact signed total, financial fields, or provenance. Inactive Category
assignments remain visible. HTTP now serializes that projection directly and
adds only read-only Category discovery through frozen service summaries.
Account behavior, internal reporting query, mutation service, imports, models,
migrations, and demo code remain unchanged. The React client now validates and
retains the bounded classification union and renders a dedicated column. Active
Category names appear directly; inactive names carry an `Inactive` marker;
never-assigned and cleared both appear as `Unclassified`. Revisions, UUIDs,
raw states, provenance, and source/time/history remain hidden. The client does
not fetch Category discovery because Movement projections are sufficient.
ADR-0010 and ADR-0011 are unchanged; no filtering, editing controls, totals,
taxonomy, transfer, or
income/expense semantics are added.

Current validation results and environment cleanup are recorded in the handoff.

The local classification write boundary is implemented under unchanged
[ADR-0012](../docs/decisions/ADR-0012-local-classification-write-boundary.md).
It requires independent default-off runtime activation, a process-lifetime
secret distributed through a dedicated Origin-checked bootstrap, exact
Origin/Host checks, and separate principal/grant/Account authorization before
one revision-checked PATCH. It does not protect against arbitrary local
processes already trusted by ADR-0010.

`runlocal --enable-classification-writes --classification-write-origin
http://127.0.0.1:5173` requires both options, DEBUG=false, and either host
`127.0.0.1:8000` or the existing trusted-container `0.0.0.0:8000` mode.
Default host/Compose startup is read-only; IPv6 read support is retained.
No migration, model, domain command, React editor, or Compose topology changed.
The runtime creates a 256-bit capability in memory after startup validation,
clears it on exit, and rejects old tokens/runtime objects/grants after recreation.
The sole bootstrap is JSON POST `/api/v1/local/classification-write-capability/`;
the sole mutation is Account-scoped classification PATCH. Principal identity,
live write grant, Account access, domain validation, and optimistic concurrency
remain separate conjunctive gates. The authorized wrapper calls the domain
command once and materializes the existing immutable projection before releasing
its locks. Success returns classification only; failure rolls back.

Exact Host/Origin, strict parsing/order/error mapping, full bigint revisions,
zero-query security denials, no-store responses, safe HTTP/proxy logging, and
explicit Vite CORS disablement are implemented and covered by focused tests.
Real Vite tests preserve duplicate header multiplicity for Django rejection;
browser/Compose/restart validation is recorded in the handoff.

After the read-client foundation implementation, a separate React manual editor
task under ADR-0012 will cover explicit choices, memory-only capability
acquisition, safe-integer submissions, stale-view handling, and refetch after
conflicts or ambiguous outcomes without silent retry. Filtering remains deferred.

The completed independent review of signed commit `e7223f4` found an Accept-negotiation
contract mismatch: parameters on unrelated media ranges incorrectly rejected
otherwise acceptable JSON. The narrow correction uses quote-aware HTTP list
splitting and considers only matching representation ranges, retaining explicit
JSON q=0 rejection. A regression test first failed on the original implementation.
Current product/architecture status sentences were also corrected. The review
amended the same signed implementation commit, resulting in the now-fetched
`092a224` baseline. See the handoff for historical validation and environment cleanup.

When uncertain, preserve evidence, abstain explicitly, use deterministic
financial validation, and keep private values out of logs and tracked files.
