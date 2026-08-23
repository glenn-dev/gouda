# Gouda

Gouda is a personal-finance data product for understanding signed account movements across accounts, categories, and time.

## Initial technology direction

The initial stack is a Django modular monolith with Django REST Framework,
PostgreSQL, React with TypeScript, and Docker Compose. AWS and Kubernetes are
deferred until after Sprint 0.

## Project status

The repository contains the product and architecture baseline plus the first
Django/PostgreSQL persistence foundation. The Santander import service is the
next checkpoint; implementation work should follow the MVP scope and the
security rules in `docs/security/financial-data-handling.md`.

## Local persistence setup

Copy `.env.example` to `.env`, fill in a local Django secret and PostgreSQL
password, then start PostgreSQL with `docker compose up -d postgres`. The
`.env` file is ignored and must not be committed.

## Documentation map

- Product: `docs/product/`
- Architecture: `docs/architecture/`
- Decisions: `docs/decisions/`
- Security: `docs/security/`
- Current AI context and work: `.ai/`

## Working agreement

Read `AGENTS.md` before making changes. Keep domain terminology aligned with `docs/product/glossary.md`, and record material architectural choices as ADRs.
