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
- The fail-closed local-delivery bootstrap is implemented. The dedicated
  `runlocal` command accepts explicit numeric `127.0.0.1` or `::1` for direct
  host delivery and the exact internal `0.0.0.0:8000` endpoint only under its
  explicit trusted Compose-network mode. It owns Django's downstream bind and
  activates one
  non-persisted opaque runtime only during the server runner lifetime.
  Principal issuance requires that runtime.
- Django REST Framework 3.16.x is configured without authentication and with
  JSON-only rendering. Account discovery and canonical Movement report GET
  endpoints fail closed without the active runtime.
- A minimal Vite + React + TypeScript client implements Account discovery,
  internal UUID selection, inclusive date input, and canonical Movement report
  rendering. It preserves exact decimal strings and omits source provenance.
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

The repository exposes two backend operations under the same active `runlocal`
runtime. `GET /api/v1/accounts/` returns only authorized Account UUID,
canonical display name, product kind, and currency, ordered by display name
then UUID. It rejects all query parameters.
`GET /api/v1/accounts/<account_uuid>/movements/` retains its strict inclusive
`start_date` and `end_date` contract and approved `MovementReport` projection.
Discovery uses `list_read_accounts`; reporting resolves through
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

The first end-to-end browser read flow and local demo bootstrap are committed
at `76a1647ab005175418e7b7175fc3e3ec9abb3589` (`feat: add local demo bootstrap`).
The 2026-09-05 classification-design session verified clean `main` with HEAD
and refreshed `origin/main` at that exact baseline.

Classification design is now frozen in
[ADR-0011](../docs/decisions/ADR-0011-movement-classification.md) and
[Movement classification](../docs/architecture/movement-classification.md).
The `docs: freeze movement classification semantics` checkpoint contains only
documentation and operational state. It selects zero/one local
dataset category through a separate mutable current-state relation, with
manual-only provenance and revision-checked corrections. There is no
classification persistence or service yet; economic types and transfers are
separate deferred semantics.

The next bounded task is implementing the two empty tables and internal
manual assign/change/clear service with focused invariant, migration, and
concurrency tests. Keep reporting/HTTP/client/demo contracts unchanged.
Recommended reasoning level: Sol High.

When uncertain, preserve evidence, abstain explicitly, use deterministic
financial validation, and keep private values out of logs and tracked files.
