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

Gouda is organized as a pipeline with clear boundaries:

1. **Ingest** accepts a source file or connector payload.
2. **Normalize** maps source fields into the canonical movement model.
3. **Validate** checks required fields, signs, dates, currencies, and identifiers.
4. **Persist** stores source records and normalized movements immutably where possible.
5. **Query** produces filtered movements and derived summaries.
6. **Present** exposes explainable views over those summaries.

The canonical model is the contract between ingestion and every downstream consumer. Derived totals must be reproducible from persisted movements and must retain enough references to explain their inputs.

## v0.1 persistence foundation

The implemented persistence slice is the `gouda.ledger` Django app. It
contains `Account`, route-neutral `SourceArtifact`, source-typed `ImportBatch`,
the shared `RawRecord` identity/outcome envelope, source-specific evidence,
and canonical `Movement`, backed by PostgreSQL. Exact artifact bytes are
content-addressed by a boundary-computed SHA-256 digest. Each canonical
movement traces to exactly one raw record without carrying source layout
fields.

The Santander parsers remain pure-Python components. Synchronous application
services now support current-account XLSX and Santander TDC PDF. The TDC route
requires an explicit account/card-suffix binding, parses outside transactions,
and atomically persists source evidence and canonical liability movements.
Classification, transfer pairing, FX, and asynchronous processing remain
outside this foundation.
