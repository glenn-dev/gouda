# Gouda

Gouda is a personal-finance data product for understanding signed account movements across accounts, categories, and time.

## Initial technology direction

The initial stack is a Django modular monolith with Django REST Framework,
PostgreSQL, React with TypeScript, and Docker Compose. AWS and Kubernetes are
deferred until after Sprint 0.

## Project status

The repository currently contains the product and architecture baseline. Implementation work should follow the MVP scope and the security rules in `docs/security/financial-data-handling.md`.

## Documentation map

- Product: `docs/product/`
- Architecture: `docs/architecture/`
- Decisions: `docs/decisions/`
- Security: `docs/security/`
- Current AI context and work: `.ai/`

## Working agreement

Read `AGENTS.md` before making changes. Keep domain terminology aligned with `docs/product/glossary.md`, and record material architectural choices as ADRs.
