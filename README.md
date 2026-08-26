# Gouda

Gouda is a personal-finance data product for understanding signed account movements across accounts, categories, and time.

## Initial technology direction

The initial stack is a Django modular monolith with Django REST Framework,
PostgreSQL, React with TypeScript, and Docker Compose. AWS and Kubernetes are
deferred until after Sprint 0.

## Project status

The repository contains the product and architecture baseline, the first
Django/PostgreSQL persistence foundation, and validated synchronous Santander
current-account XLSX and Santander credit-card PDF import lifecycles. Their
deterministic source contracts, evidence persistence, canonical signed
movements, and concurrency behavior are implemented.

The next architectural boundary is evidence-first ingestion: preserving
heterogeneous or provisional evidence, interpreting it as an observation, and
resolving it before canonical ledger acceptance. The responsibility boundary
is documented, but Observation/Resolution persistence and AI execution are not
implemented.

## Local persistence setup

Copy `.env.example` to `.env`, fill in a local Django secret and PostgreSQL
password, then start PostgreSQL with `docker compose up -d postgres`. The
`.env` file is ignored and must not be committed.

## Documentation map

- Product: `docs/product/`
- Architecture: `docs/architecture/`
- Decisions: `docs/decisions/`
- Deterministic source contracts: `docs/contracts/`
- Sanitized source observations: `docs/sources/`
- Security: `docs/security/`
- Current operational context and handoff: `.ai/`

## Working agreement

Read `AGENTS.md` before making changes. Keep domain terminology aligned with
`docs/product/glossary.md`, and record material architectural choices as ADRs.
