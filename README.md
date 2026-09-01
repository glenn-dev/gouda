# Gouda

Gouda is a personal-finance data product for understanding signed account movements across accounts, categories, and time.

## Initial technology direction

The initial stack is a Django modular monolith with Django REST Framework,
PostgreSQL, React with TypeScript, and Docker Compose. AWS and Kubernetes are
deferred until after Sprint 0.

## Project status

The repository contains the product and architecture baseline, the first
Django/PostgreSQL persistence foundation, validated synchronous Santander
current-account XLSX and Santander credit-card PDF import lifecycles, and the
BCI Historical current-account PDF evidence-first import boundary. The BCI
route preserves unresolved observations and requires a separate reconciled
Historical policy before canonical signed movements are created.

The evidence-first boundary is implemented for durable immutable financial
observations and auditable deterministic resolution before canonical ledger
acceptance. Provisional product views, AI execution, and canonical Movement
correction are not implemented. The first HTTP surface delivers one
authorized, read-only canonical Movement report under the loopback-only local
runtime boundary.

## Local persistence setup

Copy `.env.example` to `.env`, fill in a local Django secret and PostgreSQL
password, then start PostgreSQL with `docker compose up -d postgres`. The
`.env` file is ignored and must not be committed.

## Local delivery launch

The canonical launch path for Gouda's unauthenticated local-MVP financial
delivery is an explicit numeric-loopback bind:

```text
python manage.py runlocal --host 127.0.0.1 --port 8000
```

IPv6 loopback is also supported with `--host ::1`. Only `127.0.0.1` and `::1`
are accepted; hostnames, wildcard, LAN, public, empty, and ambiguous binds fail
before Django's server runner starts. The command requires the same Django and
database environment as other management commands.

The one supported operation is a JSON-only canonical Movement report:

```text
GET /api/v1/accounts/<account-uuid>/movements/?start_date=2026-04-01&end_date=2026-04-30
```

For example, using an obviously synthetic UUID:

```text
curl 'http://127.0.0.1:8000/api/v1/accounts/11111111-1111-4111-8111-111111111111/movements/?start_date=2026-04-01&end_date=2026-04-30'
```

See [Local canonical Movement HTTP delivery](docs/architecture/local-http-delivery.md)
for the request, response, and error contract. This local mode has no user
authentication. Account UUID possession is not authorization.

Generic `runserver` is not a supported launch path for unauthenticated
financial delivery. The local mode assumes a single-user or otherwise fully
trusted host and must not be re-published through a proxy, tunnel, forwarding
rule, or container port mapping.

## Documentation map

- Product: `docs/product/`
- Architecture: `docs/architecture/`
- Decisions: `docs/decisions/`
- Deterministic source contracts: `docs/contracts/`
- Sanitized source observations: `docs/sources/`
- Security: `docs/security/`
- Agent/session workflow: `docs/development/agent-workflow.md`
- Current operational context and handoff: `.ai/`

## Working agreement

Read `AGENTS.md` before making changes. Keep domain terminology aligned with
`docs/product/glossary.md`, and record material architectural choices as ADRs.
