# ADR-0010: Constrain unauthenticated local MVP delivery to loopback

- Status: Accepted
- Date: 2026-08-31

## Context

Gouda now has a read-only canonical Movement report and an application
boundary that resolves one untrusted Account UUID for one opaque, module-issued
trusted local principal. It has no HTTP endpoint, authentication, user model,
or ownership persistence.

Calling the principal bootstrap merely because an HTTP request arrived would
trust every network caller. Process locality, LAN membership, Host headers,
CORS, CSRF, and Account UUID possession do not establish caller identity. The
MVP needs the smallest delivery boundary that does not force speculative
multi-user semantics or expose financial data beyond the intended host.

## Decision

The temporary unauthenticated local MVP may expose read-only reporting only
through a host-facing listener explicitly constrained to numeric IP loopback:
`127.0.0.1`, `::1`, or both. The machine must be single-user or all local
users and processes able to reach loopback must be trusted within the MVP
boundary.

LAN and externally routable binds, wildcard binds, unspecified Docker host
publications, reverse proxies, tunnels, port forwarding, shared untrusted
hosts, and production exposure are outside this mode. They require a real
authentication boundary before Gouda may issue trusted principal context.

A server-side local-delivery bootstrap may inject
`trusted_local_principal_context()` only after trusted startup/composition has
established the loopback-only mode. It accepts no request data. The request may
supply only the untrusted Account UUID and reporting dates; the adapter must
call `report_authorized_canonical_movements` and explicitly serialize its
privacy-safe result.

The runtime implementation must fail closed when trust mode or host-facing
exposure is absent, ambiguous, or broader than loopback. This ADR freezes the
security contract but does not implement bind enforcement, HTTP, DRF,
authentication, or deployment infrastructure.

The complete operational contract is documented in
[Local MVP caller trust and network boundary](../security/local-mvp-network-boundary.md).

## Consequences

- A same-host browser can eventually use Gouda without a user-login system
  under a narrow, explicit trust assumption.
- Every local process able to reach loopback is trusted; this mode is unsafe on
  a shared or hostile host.
- LAN or remote convenience cannot silently broaden the trust perimeter.
- Docker may use an internal wildcard listener only behind explicit loopback
  host publication and a trusted private application network.
- Authentication, Account ownership, household semantics, and write
  authorization remain deferred and distinct.
- A fail-closed local-delivery bootstrap must be implemented before an
  unauthenticated endpoint is enabled.

## Revisit triggers

Revisit this decision before LAN, remote, tunneled, proxied, shared-host, or
production access; before a second independent principal or different Account
visibility; or before any HTTP write/import capability.

## Rejected alternatives

- Trust any request because Django runs locally: process locality does not
  constrain callers.
- Bind to `0.0.0.0` for convenience: this exposes the unauthenticated service
  to every reachable interface.
- Trust LAN peers: network proximity is not authentication.
- Use Host, CORS, CSRF, port obscurity, or Account UUID secrecy as caller
  authentication: these controls do not prove identity.
- Add users, households, or persisted grants now: the product does not yet
  require those durable ownership semantics.
