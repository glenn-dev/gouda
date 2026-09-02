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
correction are not implemented. The local HTTP surface discovers accessible
Accounts and delivers authorized, read-only canonical Movement reports under
the loopback-only local runtime boundary. A minimal React/TypeScript client now
provides the complete Account-selection, inclusive-date-range, and Movement
report flow through that existing backend contract.

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

The supported local client sequence is:

```text
GET /api/v1/accounts/
-> select an Account UUID
GET /api/v1/accounts/<account-uuid>/movements/?start_date=2026-04-01&end_date=2026-04-30
```

For example, using an obviously synthetic UUID:

```text
curl 'http://127.0.0.1:8000/api/v1/accounts/11111111-1111-4111-8111-111111111111/movements/?start_date=2026-04-01&end_date=2026-04-30'
```

See [Local read-only HTTP delivery](docs/architecture/local-http-delivery.md)
for the request, response, and error contract. This local mode has no user
authentication. Account UUID possession is not authorization.

Generic `runserver` is not a supported launch path for unauthenticated
financial delivery. The local mode assumes a single-user or otherwise fully
trusted host and must not be re-published beyond loopback through a remote
proxy, tunnel, forwarding rule, or container port mapping.

## Local frontend development

The supported browser-development setup keeps both processes on numeric IPv4
loopback and requires the backend's validated runtime.

Terminal 1:

```text
python manage.py runlocal --host 127.0.0.1 --port 8000
```

Terminal 2, using Node `^20.19.0`, `^22.13.0`, or `>=24.0.0` and after one
initial `npm install` in `frontend/`:

```text
cd frontend
npm run dev
```

Open `http://127.0.0.1:5173/` in the same trusted host's browser. Vite is
configured to bind only `127.0.0.1` and proxy only `/api` to
`http://127.0.0.1:8000`. This avoids adding backend CORS. The proxy does not
authenticate the browser or establish principal trust; the active
`LocalDeliveryRuntime` remains the backend trust gate. Wildcard, LAN, remote,
tunneled, proxied beyond this loopback-only development edge, shared-host, and
production exposure remain unsupported.

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
