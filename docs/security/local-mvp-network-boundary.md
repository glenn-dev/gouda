# Local MVP caller trust and network boundary

## Status and scope

This document defines the temporary network and caller-trust contract for a
future read-only Gouda HTTP surface and records its implemented local launch
boundary. It does not implement an endpoint, authentication, DRF, frontend
behavior, or deployment infrastructure.

The decision is recorded in
[ADR-0010](../decisions/ADR-0010-loopback-only-local-mvp-delivery.md).

## Terms

For this contract, **local** means machine-local access through the IP
loopback interface on one single-user or otherwise fully trusted host. It does
not mean merely that the Django process runs on the same machine as its
database, that a caller is on the same LAN, or that a service is running in a
container.

These concepts remain distinct:

- process locality says where one process executes;
- machine locality says whether caller and service execute on one host;
- loopback exposure constrains host-facing network reachability;
- Docker publication maps a container listener to a host-facing interface;
- trusted principal context is a server-issued application value; and
- authentication proves caller identity through a separate mechanism.

Loopback restriction is a temporary deployment trust assumption, not user
authentication. Every local OS user and process able to reach the listener is
inside this MVP trust perimeter. The unauthenticated mode is therefore
unsupported on a shared or otherwise untrusted host.

## Current effective exposure

The repository currently exposes no backend HTTP service:

- `config.urls` has no URL patterns;
- DRF and Django authentication are not installed;
- no CORS or CSRF middleware is configured;
- `ALLOWED_HOSTS` contains only numeric IPv4 and bracketed IPv6 loopback, and
  `DEBUG` defaults to false;
- ASGI and WSGI application objects exist but do not open listeners;
- the dedicated `runlocal` command enforces the supported host-process bind,
  but no container image or backend Compose service is defined; and
- no frontend implementation or browser-to-backend connection exists.

The only Compose host-port publication is PostgreSQL on
`127.0.0.1:5432`. It is a loopback-bound database development port, not an
HTTP caller-trust boundary.

Generic Django `runserver`, WSGI, and ASGI launches remain unsupported for
unauthenticated financial delivery because they do not activate Gouda's local
delivery capability. The supported `runlocal` path requires an explicit host,
accepts only `127.0.0.1` or `::1`, validates the port, and constructs the
downstream Django address itself.

## Exposure models considered

| Model | Caller trust and attack surface | Convenience and Docker behavior | MVP decision |
| --- | --- | --- | --- |
| No HTTP; in-process services only | Smallest attack surface, but no browser delivery | Current repository state | Safe current state, but does not deliver the reporting feature |
| Host loopback only | Treats all processes able to reach loopback as the temporary local caller; excludes direct LAN reachability | Works for a same-host browser and direct Django process | Preferred host-facing model |
| LAN-accessible bind | Every reachable LAN peer becomes a potential caller without authentication | Convenient for other devices, but materially expands exposure | Forbidden without real authentication |
| Docker-published backend | Trust depends on the host publication, not the container bind | Container may listen internally on a wildcard address only when the published host edge is explicit loopback | Allowed implementation of the loopback model, not a separate trust model |
| Unix-domain socket behind a proxy | Can use host file permissions, but browser access requires another network edge | Adds proxy and deployment machinery absent from the repository | Deferred |

Maintainability or convenience does not justify broadening unauthenticated
financial-data exposure.

## Frozen local MVP network contract

An unauthenticated read-only HTTP adapter may exist only when all of these
conditions hold:

1. The host-facing listener or port publication is explicitly bound to the
   numeric IPv4 loopback address `127.0.0.1`, the numeric IPv6 loopback address
   `::1`, or both.
2. No listener or host publication uses `0.0.0.0`, `::`, an unspecified host
   address, a LAN address, or another externally routable interface.
3. The host is single-user or all local users and processes with loopback
   access are inside the same trusted MVP boundary.
4. No reverse proxy, remote tunnel, SSH forwarding, relay, port-forwarding
   rule, or similar mechanism re-exposes the listener.
5. The operation is read-only and enters through the authorized reporting
   orchestration service. Import, resolution, correction, deletion, and other
   writes are not authorized by this mode.
6. Host and browser-origin controls are strict defense in depth; no permissive
   CORS rule exposes financial responses to arbitrary origins.
7. The server-side local-delivery mode and loopback edge are explicit and
   fail closed. They are not inferred from a Host header, request origin,
   client-supplied IP text, or the mere absence of deployment metadata.

Binding only one loopback family is valid. If IPv6 is offered, it must use
`::1`; the IPv6 wildcard `::` is forbidden. A hostname such as `localhost` may
be used by a browser after the listener is safely bound, but hostname
resolution is not the bind guarantee. Gouda's current launcher and Host-header
allowlist deliberately require the numeric form instead.

### Docker boundary

A future backend container may listen on `0.0.0.0` inside its isolated
container network when required for host publication. The host-facing
publication must still name `127.0.0.1` explicitly and may separately publish
on `::1`. A short form such as `8000:8000`, which publishes on unspecified or
all host interfaces, is forbidden for the unauthenticated mode.

Only trusted application containers may share the backend's internal network.
Publishing a loopback host port does not make an otherwise reachable container
network trusted. No backend container is added by the current host-process
implementation; container exposure enforcement remains future work.

## Caller-trust bootstrap

The future delivery adapter may obtain
`trusted_local_principal_context()` unconditionally per request only after a
trusted server-side startup or composition boundary has established the
frozen loopback-only mode above. This is deployment-scoped injection of the
one temporary principal, not identification of an HTTP caller.

The bootstrap accepts no request data. In particular, no header, query
parameter, body field, cookie, username, email address, magic local/trusted
string, token-like value, Account UUID, provider identifier, source artifact,
or bank evidence may select or create principal trust.

The Account UUID remains untrusted after principal context exists. It must pass
through `resolve_read_account` via
`report_authorized_canonical_movements`.

The initial HTTP operation is conceptually:

```text
request
-> server-side validated loopback delivery mode
-> trusted_local_principal_context()
-> untrusted Account UUID and date parsing
-> report_authorized_canonical_movements(...)
-> explicit privacy-safe serialization
```

Only the Account UUID selector, inclusive start date, and inclusive end date
may come from the request. Principal identity or trust, ownership claims,
provider/account binding claims, and authorization decisions must not.

### Implemented host-process bootstrap

The supported direct host launch is:

```text
python manage.py runlocal --host 127.0.0.1 --port 8000
```

`--host ::1` deliberately supports IPv6 loopback. The host is required and is
matched exactly; `localhost`, empty values, wildcards, LAN/public addresses,
and arbitrary hostnames are rejected. The port defaults to `8000` and accepts
only an unambiguous ASCII decimal integer from 1 through 65535.

The command validates configuration before delegation, derives Django's
address/port argument itself, and disables autoreload so the in-memory trust
lifetime and server process are the same. During that runner lifetime it
activates one opaque, non-persisted `LocalDeliveryRuntime`. A future adapter
must require that active runtime and use its no-argument principal issuance
method before calling `report_authorized_canonical_movements`. The runtime is
cleared when the runner exits or raises. Direct `runserver` and arbitrary
WSGI/ASGI composition do not activate it.

This is an architectural/application boundary, not protection from arbitrary
internal Python code deliberately importing or bypassing internals. It couples
Gouda's supported unauthenticated launcher to its validated bind; it does not
infer the machine's external network topology.

## Fail-closed behavior

The unauthenticated delivery adapter must not start or must remain unavailable
when the host-facing exposure cannot be established as loopback-only, local
delivery mode is unset or ambiguous, or an unsupported launch path bypasses
the controlled bind. It must not fall back to issuing principal context.

LAN or remote access, reverse proxies, tunnels, shared-host operation,
production deployment, or any interface broader than loopback requires a
separately designed real authentication boundary before principal context is
issued. The temporary singleton Account policy may remain behind that boundary
only if its all-Accounts visibility is still an explicit product decision.

Host validation, CORS, CSRF, port obscurity, source evidence, and Account UUID
secrecy are not authentication or Account authorization. They cannot rescue a
non-loopback deployment. Strict Host and browser-origin policy remain useful
defense in depth against browser-origin confusion and DNS-rebinding-style
attacks.

The implemented boundary guarantees that Gouda's supported unauthenticated
host launch delegates only an exact numeric loopback bind and makes trusted
local principal issuance available only during that validated runner. It does
not prevent a developer from starting an unsupported server, detect or block
OS-level proxies, tunnels, NAT, or SSH forwarding, exclude other local users
and processes, or make loopback equivalent to user authentication. A future
adapter must require the active runtime; otherwise an unsupported launch could
still expose adapter code incorrectly.

## Frontend compatibility

A React client running in a browser on the same trusted host can use a
loopback-only backend. A same-origin local development proxy is the simplest
browser arrangement. If frontend and backend use distinct loopback origins,
any future CORS allowlist must name only the exact required local origin; CORS
still does not establish caller trust.

For a containerized frontend/backend, containers may communicate over a
private trusted application network while only the browser-facing host edge is
published on loopback. A browser on another device is LAN/remote access and is
outside this unauthenticated contract.

## Revisit triggers

This temporary contract must be replaced or reassessed before any of the
following:

- LAN, remote-device, tunnel, proxy, or production access;
- a shared or untrusted local host;
- a second independently authenticated principal;
- different Account visibility among principals;
- write/import HTTP operations; or
- deployment where the loopback host edge cannot be guaranteed fail closed.
