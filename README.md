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
Accounts and active/inactive Categories, and delivers authorized, read-only
canonical Movement reports with current classification state under
the loopback-only local runtime boundary. A React/TypeScript client now provides
the complete Account-selection, inclusive-date-range, and Movement report flow
through that existing backend contract. Gouda UI Foundation v0.1 supplies its
calm, responsive ledger presentation, exact signed-money formatting, and
read-only current classification labels.

An independently enabled local classification write boundary is also implemented
under ADR-0012. Default startup and React remain read-only. The backend offers
only an ephemeral capability bootstrap and revision-checked classification PATCH;
there are no editing controls, Category CRUD, or canonical financial writes.

The next product slice is browser import of one private Santander current-account
XLSX into a separate local PostgreSQL dataset, then inspection through the
existing Movement report. The accepted
[financial-import design](docs/architecture/local-financial-import.md) and
[ADR-0013](docs/decisions/ADR-0013-local-financial-import-boundary.md) define
independent import authority, exact-file duplicate behavior, private evidence
handling, and separation from the synthetic demo. This is designed, not
implemented; classification editing follows that product-validation slice.

## Local Docker demo

The primary local path requires Docker with Compose and Make, but does not
require host Python or Node. Copy the environment template once and fill both
values with local-only secrets:

```text
cp .env.example .env
# Edit .env and set DJANGO_SECRET_KEY and POSTGRES_PASSWORD.
```

Neither value has an insecure fallback. `.env` is ignored and must not be
committed. Start PostgreSQL, the validated Django backend, and the Vite client;
wait for all three health checks; and explicitly seed the deterministic
synthetic demo:

```text
make demo
```

The command validates that both required `.env` entries are non-empty without
printing their values. It always uses the fixed isolated Compose project
`gouda-demo`, force-recreates its containers to repair partial prior creation,
waits for service health instead of sleeping, and then runs the existing
idempotent `seed_demo` command. On success, open
`http://127.0.0.1:5173/`.

The normal demo publishes only `127.0.0.1:5173` for the browser-facing Vite
client. PostgreSQL and Django have no host publication; Vite reaches Django at
internal service port `8000`, and Django reaches PostgreSQL at internal service
port `5432`. Another local PostgreSQL listener on host port `5432` therefore
does not conflict with the demo.

Useful operator commands are:

```text
make status
make logs
make down
```

`make down` removes only the `gouda-demo` containers and networks and preserves
the `gouda-demo_gouda-postgres-data` volume. It never targets the default Gouda
Compose project and never requests volume deletion. Restart with `make demo`;
seeding is idempotent and creates no duplicates.

Only when the isolated synthetic database itself should be discarded, run:

```text
make demo-reset
```

This destructive command names and removes only the literal
`gouda-demo_gouda-postgres-data` volume. It cannot be redirected to the default
Gouda volume through a Make or Compose project-name variable. Run `make demo`
afterward to create a fresh isolated database.

Generic `docker compose up` remains available for repository-level debugging,
but it does not seed data automatically and is not the supported visual-demo
workflow. Never use generic Compose startup or demo reset as an attempted repair
for an older default Gouda volume with incompatible historical migration state;
that state requires a separate deliberate migration/remediation decision.

The demo contains one CLP current Account, one CLP credit-card Account, and
canonical Movements from `2026-01-05` through `2026-04-23`. Use `2026-01-01`
through `2026-04-30` for the complete sample; March intentionally has no
Movements. Positive and negative values retain canonical signed-account-effect
meaning for each Account orientation. Demo rows are independent Account-effect
examples; equal or nearby values do not assert transfer pairing or shared
economic-event identity.

For narrowly scoped demo-data cleanup without deleting its database, the
underlying explicit command remains:

```text
docker compose -p gouda-demo exec backend python manage.py clear_demo
```

Do not use `docker compose down -v` as demo cleanup. Source directories are
mounted read-only into the development containers. Frontend source changes use
Vite reload; restart `backend` after Python changes and rebuild after dependency
changes.

## Manual host development

The direct host launch path for Gouda's unauthenticated local-MVP financial
delivery remains an explicit numeric-loopback bind. Host PostgreSQL access is
separate from the normal demo because it genuinely requires a published
database port. Start a fixed `gouda-host-dev` PostgreSQL project with the
explicit loopback-only override:

```text
docker compose -p gouda-host-dev \
  -f docker-compose.yml -f docker-compose.host-db.yml \
  up -d postgres
```

This is the only documented Compose path that publishes
`127.0.0.1:5432`. It has its own persistent volume and may conflict with an
existing host PostgreSQL listener by design. It does not reuse or remediate the
default Gouda volume or the isolated demo volume. Then run:

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

To explicitly enable only classification writes in host development, start the
backend with both flags (and keep `DJANGO_DEBUG=false`):

```text
python manage.py runlocal --host 127.0.0.1 --port 8000 \
  --enable-classification-writes \
  --classification-write-origin http://127.0.0.1:5173
```

Use the same Vite browser edge. The capability is generated only in backend
memory and expires on restart; never configure, save, or log it. The complete
[local write contract](docs/architecture/local-http-delivery.md#opt-in-classification-writes)
documents bootstrap/PATCH, the equally explicit Compose opt-in, and the accepted
trusted-local-process limitation. The frozen
[Gouda UI Foundation v0.1](docs/design/ui-foundation.md) is implemented for the
read client. React capability consumption and editing follow in a separate
checkpoint.

## Documentation map

- Product: `docs/product/`
- Architecture: `docs/architecture/`
- Local import design: [Local financial import v0.1](docs/architecture/local-financial-import.md)
- UI design: [Gouda UI Foundation v0.1](docs/design/ui-foundation.md)
- Decisions: `docs/decisions/`
- Deterministic source contracts: `docs/contracts/`
- Sanitized source observations: `docs/sources/`
- Security: `docs/security/`
- Agent/session workflow: `docs/development/agent-workflow.md`
- Current operational context and handoff: `.ai/`

## Working agreement

Read `AGENTS.md` before making changes. Keep domain terminology aligned with
`docs/product/glossary.md`, and record material architectural choices as ADRs.
