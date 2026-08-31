# Current task

## Objective

Implement the fail-closed local-MVP delivery bootstrap and loopback launch
boundary required before Gouda enables HTTP reporting.

## Current state

ADR-0010 and `docs/security/local-mvp-network-boundary.md` allow a future
unauthenticated read adapter only behind an explicit numeric loopback host
edge on a single-user or fully trusted machine. Wildcard, LAN, remote,
tunneled, proxied, forwarded, shared-host, production, and ambiguous exposure
must fail closed or require real authentication.

Account authorization and authorized reporting orchestration are implemented.
HTTP is not: the repository has no backend listener, endpoint, DRF, auth,
frontend, or runtime guard that couples the trusted principal bootstrap to a
safe bind. Django's development-server default is not sufficient because its
address is operator-overridable.

## Scope

Implement the smallest explicit server-side boundary that:

- enables local unauthenticated delivery only through trusted configuration
  with no permissive default;
- owns a dedicated launch path bound to numeric `127.0.0.1`, with optional
  explicit `::1` support if it can be tested safely;
- refuses wildcard, unspecified, LAN, or caller-selected bind addresses;
- establishes the validated local-delivery mode before any adapter may obtain
  `trusted_local_principal_context()`;
- uses strict Host/origin configuration only as defense in depth, never as
  caller authentication;
- provides deterministic tests for allowed and rejected startup/configuration
  shapes without opening a public listener; and
- documents the exact safe local launch command and fail-closed behavior.

Expected areas are Django configuration, a narrow local-delivery bootstrap or
management-command boundary, focused tests, and local-development/security
documentation.

## Non-goals

Do not implement DRF, URL routes, HTTP response serialization, authentication,
sessions, tokens, users, households, roles, Account ownership/grants, models,
migrations, frontend, Docker backend publication, reverse proxy, TLS, writes,
import authorization, or financial semantics.

## Acceptance criteria

- Trusted mode has no implicit or ambiguous default.
- The supported launcher cannot bind an unauthenticated service to wildcard,
  LAN, or caller-selected interfaces.
- Principal context is issued only from validated server composition and never
  from request-like data.
- Unsupported launch/configuration paths fail before financial delivery.
- Existing Account authorization and reporting services remain unchanged.
- No endpoint, model, migration, write behavior, or ownership semantics are
  added.
- Tests and documentation make clear that local OS processes share the
  temporary trust perimeter and that tunnels/proxies remain prohibited.

Principal risks are relying on Django's overridable defaults, treating Host or
origin checks as authentication, or creating an enforcement seam that a later
endpoint can silently bypass.

Recommended reasoning level: Sol High.
