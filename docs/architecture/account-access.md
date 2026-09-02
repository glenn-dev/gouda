# Account access and read-only delivery boundary

## Status and scope

This document defines the implemented application boundary for deciding which
`Account` one trusted caller principal may read. The first local HTTP adapter
uses it without choosing an authentication mechanism, adding ownership
persistence, or defining write access.

The bounded reporting flow is:

```text
validated local-delivery bootstrap or authentication adapter
-> trusted principal context
-> read-account access resolver
-> authorized persisted Account
-> canonical Movement reporting service
-> explicit local HTTP delivery adapter
```

Discovery uses the same boundary without resolving a client selector:

```text
validated local-delivery bootstrap or authentication adapter
-> trusted principal context
-> read-account discovery policy
-> explicit safe Account summaries
-> explicit local HTTP delivery adapter
```

Authentication establishes who the caller is. Account authorization decides
which Accounts that principal may read. Account ownership describes the domain
relationship between people or households and an Account. Delivery maps an
already-authorized application operation to a transport. These are separate
responsibilities.

## Current repository state

Gouda has no persisted user, principal, household, member, role, permission,
or ownership model. Django authentication is not installed, and `Account`
contains only internal identity, display name, product kind, economic
orientation, and currency. It has no owner or household relationship.

The current import services and lower-level canonical Movement reporting
service accept a persisted `Account` supplied by a trusted caller. They
re-fetch or validate that Account for source and domain invariants, but they do
not establish who may select it. `SantanderTdcAccountBinding` verifies a
selected Account against source evidence; it is not caller authorization or
ownership.

The read boundary is implemented in
`gouda.ledger.services.account_access`. It issues one opaque singleton
`TrustedPrincipalContext` from trusted application composition, lists explicit
safe summaries of Accounts allowed by the read policy, resolves an untrusted
UUID selector to an authorized persisted `Account`, and composes that resolver
with canonical Movement reporting. It adds no model, migration, or write path.

The MVP requires account/date querying, totals, and traceability. Multi-user
sharing and collaborative editing are explicitly out of scope. No product or
architecture document establishes named-person or household access, multiple
independent users, shared versus individual Accounts, per-Account
ownership, or roles. References to household net worth define canonical sign
semantics, not access or ownership.

## Alternatives

| Alternative | MVP fit | Complexity and migration cost | Authorization clarity | Main risk |
| --- | --- | --- | --- | --- |
| One trusted local principal reads all Accounts | Fits the current personal, non-sharing MVP and requires no ownership migration | Lowest | Clear while exactly one principal exists | Unsafe if silently retained when principals need different visibility |
| User directly owns Accounts | No documented user or per-Account ownership requirement | Adds authentication/user persistence and Account ownership migration | Clear for individual Accounts | Prematurely makes sharing and household treatment an ownership rule |
| Household owns Accounts; users are members | Could later support shared finances, but no household/member product contract exists | Adds several entities, lifecycle rules, and migrations | Clear only after membership and household roles are defined | Treats financial aggregation language as unsupported access semantics |
| User/Account membership association | Supports individual and shared Accounts | Highest MVP complexity; requires membership, role, and uniqueness decisions | Flexible | Builds multi-user and role semantics explicitly outside MVP scope |
| Deployment-configured Account allowlist | Avoids database ownership models | Moves durable access facts into configuration and creates synchronization work | Explicit but operationally brittle | Becomes shadow ownership outside the domain model |

The flexible alternatives do not currently unlock a required product behavior.
They should not be introduced solely to make a future HTTP endpoint possible.

## MVP recommendation

Use a temporary **single trusted local principal** read policy. The one
principal recognized by trusted application composition may read every
persisted Gouda `Account`. This is an access policy, not a claim that the
principal owns every Account and not a household model.

The policy is intentionally non-persistent and single-principal:

- no principal, user, household, member, role, or Account ownership row is
  added;
- no client value is itself proof of principal identity;
- only the validated server-side delivery bootstrap or a future authentication
  adapter may obtain the trusted principal context;
- the access resolver, not the transport, converts an Account selector into an
  authorized `Account`; and
- the policy must not be used in a deployment where recognized principals need
  different Account visibility.

This temporary Account-access choice does not freeze durable ownership
semantics. The conditional local network trust decision is recorded separately
in [ADR-0010](../decisions/ADR-0010-loopback-only-local-mvp-delivery.md).
Revisit ownership before adding a second independently authenticated principal,
different Account visibility, individual/shared Account behavior, household
membership, or any persisted grant.

## Trusted read-account boundary

The application-facing `list_read_accounts` service accepts one trusted,
opaque principal context. It validates the principal before database access,
applies the same read policy used by selector resolution, and returns an
immutable tuple of `AccountSummary` values. The summary is not a model
serializer and contains exactly:

- `id`, the internal Account UUID required by the Movement report selector;
- `display_name`, the persisted canonical human-readable label;
- `kind`, the persisted canonical product/account kind; and
- `currency`, the persisted canonical Account currency.

The deterministic order is `display_name`, then Account UUID. Economic
orientation is safe canonical data but is unnecessary in this first summary
because the current database invariant permits only `CURRENT` + `ASSET` and
`CREDIT_CARD` + `LIABILITY`. Provider/institution data, external or masked
identifiers, Santander TDC bindings, source artifacts, import batches, raw
records, Movements, observations, balances, totals, and provenance are not
part of the projection. Provider identity is source evidence rather than a
canonical Account field, and external Account identifiers remain deferred.

Under the frozen temporary policy, the recognized principal receives one
summary for every persisted Account. The HTTP adapter cannot query `Account`
directly; a future policy may therefore narrow the returned tuple without
changing the delivery contract or treating Account existence as access.

The application-facing `resolve_read_account` service accepts:

- a trusted, opaque principal context produced outside the domain service; and
- one internal Account UUID selector received as untrusted input.

Principal context must not contain provider account numbers or be constructed
from an artifact. The selector is only a lookup request; possession of a UUID
does not grant access.

The resolver validates the principal before the selector, checks the principal
against the single-principal policy, and loads the Account in one boundary. On
success it returns the persisted `Account` object. Downstream financial
services continue receiving that authorized object rather than an arbitrary
UUID. The application selector is a `UUID` value; raw transport strings are
not silently parsed at this trusted application boundary.

`trusted_local_principal_context()` is a server-side composition seam, not an
authentication function. It returns the only principal object recognized by
the temporary policy and accepts no client input. Other instances of the same
Python type, strings, Account values, provider data, and artifacts are not
recognized. This is an explicit application convention, not a claim that
Python imports enforce a security boundary.

Stable failures are:

- `principal_context_invalid` when trusted application context is absent or
  malformed;
- `account_selector_invalid` when the selector is not a supported UUID; and
- `account_not_accessible` for both an unknown Account and an Account the
  principal may not read.

The last failure deliberately does not reveal whether another Account UUID
exists. Delivery adapters should preserve that indistinguishability. They may
map it to one transport-level not-found response, but transport status codes
are not fixed here.

The resolver is read-only. A future import or other write operation must use a
separate capability-specific authorization boundary; read access must not
silently imply permission to upload, bind, import, resolve, correct, or delete.

## Read-only reporting operation

The implemented transport-independent
`report_authorized_canonical_movements` operation accepts:

- trusted principal context;
- untrusted internal Account UUID selector;
- inclusive `start_date`; and
- inclusive `end_date`.

It:

1. resolve the selector through the read-account access boundary;
2. pass only the resulting authorized `Account` to
   `report_canonical_movements`; and
3. return the existing immutable `MovementReport` without creating a competing
   reporting representation.

Account access failure uses `account_not_accessible`. Date validation
continues to use the reporting service's stable `start_date_invalid`,
`end_date_invalid`, and `date_range_invalid` failures without translation. If
the Account disappears between access resolution and reporting, the
orchestration operation translates the lower-level absence to
`account_not_accessible`, not a distinct existence signal.

The implemented delivery layer explicitly serializes approved result fields.
The current result contains Account and Movement UUIDs, occurrence date, exact
canonical signed amount, currency, optional canonical `Movement.description`,
and the bounded source trace documented in
[Architecture overview](overview.md). It must not introspect Django models or
expose filenames, digests, bytes, raw cells, source payloads, source
references, running balances, provider account/card identifiers, or opaque
bank-specific evidence.

## Future compatibility

The reporting service already accepts an authorized `Account`, so future
ownership work can replace only the resolver policy. A later product decision
may back the same conceptual boundary with user ownership, household
membership, or Account grants. Write/import authorization can remain a
separate capability. Those models, roles, and migrations should be designed
from concrete multi-principal requirements rather than anticipated here.

## Delivery prerequisite

The local caller-trust and exposure contract is frozen in
[Local MVP caller trust and network boundary](../security/local-mvp-network-boundary.md).
The unauthenticated read adapter may obtain the singleton only through a
validated server-side loopback delivery mode. Request bodies, headers, query
parameters, cookies, Account selectors, and source data cannot issue that
context.

The required fail-closed bind/bootstrap enforcement is implemented by
`python manage.py runlocal --host <numeric-loopback> --port <port>`. While its
validated server runner is active, the process-local `LocalDeliveryRuntime`
may issue this module's existing principal context without request input. A
direct `runserver`, WSGI, or ASGI launch has no active local-delivery runtime,
so the adapter fails closed.

The JSON-only DRF adapter is implemented at the versioned routes documented in
[Local read-only HTTP delivery](local-http-delivery.md). It requires the active
runtime before financial database access. Discovery calls `list_read_accounts`;
reporting calls `report_authorized_canonical_movements`. Both explicitly
serialize approved fields. LAN, remote, tunneled, proxied, shared-host, or
production access still requires real authentication instead.
