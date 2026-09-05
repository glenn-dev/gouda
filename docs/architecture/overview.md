# Architecture overview

## Initial technology direction

Gouda will start as a modular monolith with Django and Django REST Framework.
Django provides the ORM, migrations, validation, and administration needed by
the initial product; Django REST Framework exposes the API over the same
application boundaries.

The initial persistence layer is PostgreSQL. The web client will use React with
TypeScript, and Docker Compose will provide the local development environment
for the application services.

AWS and Kubernetes are later deployment and operations targets. They are not
part of Sprint 0 and must not be implemented as part of the initial slice.

The implemented deterministic pipeline has clear boundaries:

1. **Ingest** accepts a source file or connector payload.
2. **Normalize** maps source fields into the canonical movement model.
3. **Validate** checks required fields, signs, dates, currencies, and identifiers.
4. **Persist** stores source records and normalized movements immutably where possible.
5. **Query** produces filtered movements and derived summaries.
6. **Present** exposes explainable views over those summaries.

The canonical model is the contract between ingestion and every downstream consumer. Derived totals must be reproducible from persisted movements and must retain enough references to explain their inputs.

The accepted target evolution inserts observation and resolution before the
canonical ledger so heterogeneous or provisional evidence does not become
financial truth merely because it was extracted:

```text
Artifact -> identify/route -> extract/interpret -> FinancialObservation
         -> deterministic validation -> resolution -> canonical Movement
         -> classify/relate -> summaries
```

See [Evidence and resolution architecture](evidence-resolution.md). The
observation and resolution persistence/service boundary and the BCI Historical
evidence-first route are implemented. BCI Current/Recent persistence and
lifecycle behavior, AI interpretation, and provisional product views are not.

## v0.1 persistence foundation

The implemented persistence slice is the `gouda.ledger` Django app. It
contains `Account`, route-neutral `SourceArtifact`, source-typed `ImportBatch`,
the shared `RawRecord` identity/outcome envelope, source-specific evidence,
and canonical `Movement`, backed by PostgreSQL. Exact artifact bytes are
content-addressed by a boundary-computed SHA-256 digest. Each canonical
movement traces to exactly one raw record without carrying source layout
fields. That relationship describes the current Santander implementation, not
a permanent claim that one piece of evidence must always equal one financial
fact.

The Santander parsers remain pure-Python components. Synchronous application
services now support current-account XLSX and Santander TDC PDF. The TDC route
requires an explicit account/card-suffix binding, parses outside transactions,
and atomically persists source evidence and canonical liability movements.
Classification, transfer pairing, FX, and asynchronous processing remain
outside this foundation.

## Accepted classification design

[ADR-0011](../decisions/ADR-0011-movement-classification.md) freezes an optional
local dataset Category per Movement in a separate mutable current-state
relation. The [classification contract](movement-classification.md) specifies
manual-only provenance, revision-checked corrections, explicit unclassified
semantics, and two new empty tables for a later implementation. No financial
fields or source contracts change. Classification is not implemented, and
the existing report/API/client and synthetic demo remain classification-free.
Economic-event types, transfer relationships, and assignment history remain
deferred with explicit revisit triggers.

## Internal Movement reporting boundary

The first read-only canonical reporting service is implemented under
`gouda.ledger.services`. It accepts one trusted persisted `Account` and an
inclusive date range, using `Movement.occurrence_date` as the existing
canonical reporting date. It returns matching Movements ordered by occurrence
date and Movement UUID, their exact Decimal signed-account-effect total and
count, and a bounded source trace through the originating `RawRecord` and
`ImportBatch` to the `SourceArtifact` UUID.

Persisted `Movement` rows are the current accepted canonical query boundary.
The service does not combine or filter them using `FinancialObservation`
state: unresolved, rejected, and superseded evidence is not a Movement, while
superseding an observation does not retract an existing Movement because
canonical correction remains unimplemented. The source trace exposes only
database identifiers and batch source kind, variant, parser version, import
status, and reconciliation status. It excludes filenames, artifact digests or
bytes, raw cells, source payloads, source references, and running balances.
`Movement.description` remains an optional canonical reporting field on each
item; it is not copied into the source trace, and raw source descriptions or
parser evidence are not exposed as provenance.

This service remains transport-independent. The HTTP adapter exposes only its
authorized orchestration path and explicit result projection. It adds
no authentication, household ownership, classification, transfer, lifecycle,
provisional-view, or write behavior.

The pre-HTTP caller-to-Account boundary is defined separately in
[Account access and read-only delivery](account-access.md). Delivery must
resolve an untrusted Account selector through that boundary before invoking
reporting; possession of an Account UUID is never authorization.

That boundary is implemented as an opaque module-issued local principal, a
read-only Account discovery operation, an Account resolver, and an authorized
reporting orchestration service. Discovery returns only internal UUID,
canonical display name, product kind, and currency, ordered by display name
and UUID. Reporting returns the existing `MovementReport`. Neither path adds
ownership, authentication, model, migration, or write semantics. The
conditional unauthenticated local delivery contract is enforced by the
dedicated `runlocal` command and
its process-local bootstrap capability. The command owns an explicit numeric
loopback bind and activates principal issuance only for the lifetime of its
server runner. Direct `runserver` has no active capability, and client input
cannot create principal context.

The implemented JSON-only DRF adapter provides one GET route to discover
authorized Account summaries and one GET route for an Account UUID and
inclusive date range. Both require the active runtime before financial
database access. Discovery delegates to `list_read_accounts`; reporting
delegates to `report_authorized_canonical_movements` and retains the approved
`MovementReport` projection with exact decimal strings. See
[Local read-only HTTP delivery](local-http-delivery.md).

## Local read-only frontend

The first React/TypeScript presentation slice is implemented in `frontend/`.
It is a thin consumer of the existing Account discovery and authorized
Movement report contracts: it discovers Accounts, keeps the selected UUID as
an internal selector, accepts an inclusive date range, and renders the
backend-provided canonical report without recomputing totals or converting
decimal strings to JavaScript numbers.

For direct host development, Vite binds to numeric loopback and proxies only
`/api` to the numeric-loopback `runlocal` backend. The primary Compose path
instead publishes only Vite on numeric loopback, leaves Django unpublished,
and uses a trusted internal application network. Django's narrowly validated
container mode permits only its internal `0.0.0.0:8000` endpoint without
claiming to inspect Docker publication. Both arrangements avoid CORS and retain
the active `LocalDeliveryRuntime` trust gate. The client stores no auth tokens, issues no
write methods, retains no source trace in its report model, and adds no
financial semantics or production deployment behavior.

The explicit `seed_demo` and `clear_demo` commands manage a deterministic
synthetic-only Account/Movement graph for local demonstration. Fixed UUIDv5
identities provide the cleanup boundary without adding an `is_demo` field to
Account or Movement. Because canonical Movement requires provenance and the
source/record choices are closed, a narrow migration adds explicit
`DEMO_SYNTHETIC` envelope choices instead of falsely labeling the data as a bank
import. The seed creates those synthetic artifacts, batches, and records
directly; it does not invoke or generalize production import workflows.
