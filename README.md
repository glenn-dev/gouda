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

## Local Docker demo

The primary local path requires Docker with Compose, but does not require host
Python or Node. Copy the environment template once and fill both values with
local-only secrets:

```text
cp .env.example .env
# Edit .env and set DJANGO_SECRET_KEY and POSTGRES_PASSWORD.
```

Neither value has an insecure fallback. `.env` is ignored and must not be
committed. Start PostgreSQL, the validated Django backend, and the Vite client:

```text
docker compose up --build
```

The backend applies migrations before starting. When all three services are
healthy, open `http://127.0.0.1:5173/`. Compose publishes only these host ports:

- `127.0.0.1:5173` — browser-facing Vite client;
- `127.0.0.1:5432` — optional host access to PostgreSQL; and
- no backend host port. Vite reaches Django at internal service port `8000`.

Populate the deterministic, synthetic-only demo dataset explicitly:

```text
docker compose exec backend python manage.py seed_demo
```

Running the command again is safe and creates no duplicates. The demo contains
one CLP current Account, one CLP credit-card Account, and canonical Movements
from `2026-01-05` through `2026-04-23`. Use `2026-01-01` through `2026-04-30`
for the complete sample; March intentionally has no Movements. Positive and
negative values retain canonical signed-account-effect meaning for each
Account orientation. Demo rows are independent Account-effect examples; equal
or nearby values do not assert transfer pairing or shared economic-event
identity.

Remove only this fixed demo graph, leaving every unrelated Account, import,
Movement, private file, and the PostgreSQL volume untouched:

```text
docker compose exec backend python manage.py clear_demo
```

Stop the services without deleting PostgreSQL data:

```text
docker compose down
```

Do not use `docker compose down -v` as demo cleanup. Source directories are
mounted read-only into the development containers. Frontend source changes use
Vite reload; restart `backend` after Python changes and rebuild after dependency
changes.

## Manual host development

The direct host launch path for Gouda's unauthenticated local-MVP financial
delivery remains an explicit numeric-loopback bind. Start PostgreSQL alone with
`docker compose up -d postgres`, then run:

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

The manual browser-development setup keeps both processes on numeric IPv4
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
