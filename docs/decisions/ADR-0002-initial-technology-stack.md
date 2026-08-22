# ADR-0002: Use Django as the initial backend stack

- Status: Accepted
- Date: 2026-08-09

## Context

Gouda needs an initial backend that can support a modular monolith, relational
persistence, schema migrations, domain validation, administration, and an API.
The project is documentation-first and Sprint 0 should establish a practical
local development foundation without prematurely solving deployment operations.

## Decision

The initial backend is Django with Django REST Framework. Django is the
application framework and ORM boundary; Django migrations, validation, and
administration are part of the initial platform. Django REST Framework exposes
the HTTP API.

The initial stack also includes:

- PostgreSQL for persistence;
- React with TypeScript for the web client;
- Docker Compose for local service orchestration.

AWS and Kubernetes remain later objectives and are explicitly out of scope for
Sprint 0.

## Consequences

The first implementation can keep domain logic, persistence, administration,
and API delivery within one deployable application while preserving modular
boundaries. The team can practice and validate a current professional Django
stack early. Local development requires a PostgreSQL service, and API and
client contracts must be kept explicit as the two layers evolve.

Deployment-specific AWS and Kubernetes decisions are deferred until the
application has implementation evidence and operational requirements.

## Rejected alternatives

- FastAPI as the initial backend: not selected for this phase because Django's
  integrated ORM, migrations, validation, administration, and API ecosystem
  better fit the initial monolith requirements and learning objective.
