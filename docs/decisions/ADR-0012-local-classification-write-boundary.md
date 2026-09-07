# ADR-0012: Require a separate local classification write capability

- Status: Accepted design; implementation deferred
- Date: 2026-09-06
- Extends: ADR-0010 only for the classification operation defined here
- Preserves: ADR-0011 and all canonical financial/source invariants

## Context and decision

The verified design baseline is clean `main`, with fetched HEAD and
`origin/main` at `da9f0c7b7ffb6b9ece9e3ae76629194349f3e6f3`
(`feat: render movement classification in local client`). The implemented
HTTP/client surface remains read-only. The internal
`set_movement_classification` command already owns manual transitions, Account
scoping, revision comparison, and transaction locks. This ADR implements nothing.
See the existing [classification service contract](../architecture/movement-classification.md),
[Account access boundary](../architecture/account-access.md), and
[read HTTP contract](../architecture/local-http-delivery.md).

Permit a future single-Movement classification write only with all of:

1. The active validated `LocalDeliveryRuntime` and unchanged trusted-host,
   numeric-loopback exposure constraints of
   [ADR-0010](ADR-0010-loopback-only-local-mvp-delivery.md).
2. An independently enabled, process-local classification write runtime.
3. Exact browser Origin and request Host validation in Django.
4. A process-lifetime secret capability supplied explicitly in a custom header.
5. A separate application classification-authorization operation validating
   both the server-issued principal and the live classification grant before
   Account resolution and delegation to the existing command.

These are conjunctive requirements. Neither a valid read request, local runtime
activation, same-origin request, nor UUID possession alone authorizes mutation.
This is a browser write boundary on an already trusted host, not authentication
of a person, browser tab, or OS process. The capability cannot authorize Category
management, imports, resolution, financial correction, deletion, bulk edits,
automatic classification, or any other write.

This new ADR explicitly satisfies ADR-0010's write revisit trigger. ADR-0010
continues to define the read capability and deployment perimeter; only its
read-only restriction is extended by this separately activated operation.
Its text is left intact. [ADR-0011](ADR-0011-movement-classification.md) needs
no change: classification remains current organizational metadata, MANUAL only,
with no history, fake Unclassified Category, transfer pairing, or income/expense
meaning. Canonical Movement and source/evidence records are never update targets.

## Threat model

Assume an ordinary uncompromised browser can visit attacker-controlled public
pages while Gouda runs. Do not rely on browser private/local-network prompts,
mixed-content blocking, preflight caching behavior, or port secrecy. Gouda's
own origin, frontend dependencies, browser extensions with privileged access,
OS, and permitted containers are trusted. A compromised Gouda origin can act
with its authority; neither an Origin check nor a JavaScript-visible token
prevents that.

| Threat | Required protection and residual limit |
| --- | --- |
| Malicious public webpage targets loopback | Exact Origin rejects its requests at bootstrap and mutation; it cannot obtain the secret through a permitted cross-origin response. Merely being reachable by the browser confers no write right. |
| Cross-site forms, navigation, images, beacons, simple requests | GET never mutates or releases the secret. Mutation accepts PATCH only, JSON only, and requires the secret header. Bootstrap accepts JSON POST only. Forms cannot supply that media type or the mutation header. Origin is checked even for requests whose responses a browser cannot read. |
| Foreign fetch/XHR | Reject foreign Origin in Django even if a proxy answers preflight or a browser sends the actual request. No CORS allowance at either edge is part of this write mode. |
| Forged or absent Origin/Referer | Browser scripts cannot freely choose Origin; raw clients can. Missing, null, malformed, multiple, and unlisted Origins fail closed. Referer never substitutes for Origin. A forged matching Origin without the secret cannot mutate. A local raw client can obtain the secret through bootstrap; that limit is explicit below. |
| Same-origin React | May deliberately obtain a capability and send one explicit manual choice. Server still checks every gate, Account access, Category validity, and revision. No request parameter, URL-driven action, or cross-window message may initiate an edit or supply principal identity. |
| Another loopback process | Unknown tokens fail and guessing a 256-bit token is impractical. However a process can forge Host/Origin and call bootstrap. There is no protection against an arbitrary hostile local process in this model. |
| Another local OS user | Loopback is not per-user. Every such user with access is trusted under ADR-0010. An untrusted shared host is unsupported; this token does not repair that assumption. |
| Browser -> Vite -> internal Django | Preserve original Host, Origin, and capability header. Django validates them independently. Trusted Vite sees the secret in transit; it cannot manufacture authority by inserting a token for all clients. |
| Accidental direct Django exposure | Generic runserver/WSGI/ASGI lacks both runtimes. Direct wildcard/LAN launch fails validation. An operator publishing an already enabled container backend defeats the assumed topology; Django cannot attest Docker NAT. Tokens and Origin do not rescue such exposure. |
| Replay and stale writes | Revision comparison under locks rejects stale changes, including old requests after assign/clear/reassign. Correct-revision no-ops may repeat. Restart invalidates old capabilities, not persisted revisions. No durable request deduplication or exactly-once promise. |
| Valid read client sends PATCH | Without separate activation and token, reject before database work. Ordinary read responses contain no capability. Explicit bootstrap is the authority-acquisition step. A trusted local client can intentionally acquire it while enabled; this is not a persistent read-only-client role. |
| DNS rebinding / attacker hostname | Validate Host on the actual write and bootstrap paths and require the exact numeric frontend Origin. A hostname that rebinds to loopback remains an untrusted Host/Origin. Never derive the trusted origin from request Host. |
| XSS, clickjacking, or compromised frontend | Preserve escaped text rendering and trusted code dependencies; before editing is delivered, serve the app with `Content-Security-Policy: frame-ancestors 'none'` and `X-Frame-Options: DENY`. An actual same-origin script compromise can bootstrap and write; real isolation is a different design. |

Cross-origin requests can cause effects even when CORS prevents reading the
response; simple requests do not require preflight. PATCH, JSON media type,
and the custom header help exclude those browser request forms, but server
checks remain mandatory. See [MDN CORS](https://developer.mozilla.org/en-US/docs/Web/HTTP/Guides/CORS).
CORS is relevant to response disclosure and browser preflight, insufficient
as write authorization, and irrelevant to authentication of raw local clients.

## Runtime and capability lifecycle

Use a dedicated opaque `LocalClassificationWriteRuntime`, tied by identity and
lifetime to the active `LocalDeliveryRuntime`. Do not add write booleans,
secret strings, or request claims to `TrustedPrincipalContext`. The latter
still comes only from the existing no-argument server composition seam.
Principal authorization and authority to perform this operation are orthogonal.

Require the secret even though strict Origin validation is already a browser
CSRF defense. It gives mutation a separately carried capability, keeps ordinary
read clients from writing accidentally, and adds a check independent of the
per-request Origin check. Because bootstrap trusts that same configured origin,
it does not create a stronger local-process identity boundary. Origin alone
is not caller authentication; runtime activation alone leaves browser requests
without any proof of deliberate write authority.

Write mode defaults off in both host and Compose launches. The proposed
`runlocal` options are `--enable-classification-writes` and
`--classification-write-origin http://127.0.0.1:5173`. Both are required
together; absent activation keeps reads working with no write runtime or
secret. Reject ambiguous flags, an origin supplied without activation, invalid
topology, and `DEBUG=true` before starting a write-enabled server. No HTTP
request can enable the mode or change its configuration. The repository's
default Compose launch stays read-only; future opt-in startup configuration
must preserve its exact publications and networks.

Generate 32 random bytes with Python's cryptographic `secrets` facility once,
after successful startup validation, in the Django process that serves the
requests. Encode as 64 lowercase hexadecimal characters. Store only in the
runtime's private memory. Do not derive it from Django SECRET_KEY, database
credentials, Account IDs, time, or request content. Never accept a configured
token from an environment variable or command-line option. There is no token
in `.env.example`, source, static HTML, Vite environment/bundle, a file, database,
cache service, browser storage, or cookie.

The token is per serving process/runtime, shared by its permitted browser tabs,
not per session or authenticated principal. The current single-process,
threaded, no-autoreload launcher fits this lifetime. Clear the runtime reference
on normal exit or exception; old runtime objects and grants must fail liveness
checks. Restart creates a new independent secret. Python memory disposal is
not a secure-erasure guarantee. Multi-worker processes, hot reload, per-tab
revocation, expiration sessions, and persistent capabilities are out of scope.
Stop/restart disables or rotates authority; no HTTP rotation endpoint is added.

For mutation accept exactly one `X-Gouda-Classification-Write` header with that
64-character value. Reject absent, duplicate/combined, malformed, and incorrect
values as `write_capability_invalid`. Compare valid-shaped values using a
constant-time comparison. Do not accept the token through Authorization,
cookies, body fields, URL path, query string, or fragment. A successful check
produces an opaque, live, classification-only application grant; the secret
itself never reaches the domain service or selects principal identity.
On inbound HTTP requests, this dedicated header is the only permitted transport
for the capability. The successful bootstrap response described below is the
only operation that discloses it to React.

## Capability delivery to React

Add one dedicated bootstrap operation in the future implementation:

```text
POST /api/v1/local/classification-write-capability/
Host: 127.0.0.1:5173
Content-Type: application/json
Accept: application/json
Origin: http://127.0.0.1:5173

{}
```

It returns HTTP 200 and exactly one `write_capability` string field containing
the runtime's token. It reads no database, creates no session, performs no
classification mutation, and does not rotate the token on repeated calls.
It requires active read and write runtimes, exact Host/Origin, a valid
server-issued principal, JSON negotiation, no query parameters, and exactly
an empty JSON object. It deliberately does not require the token being obtained.
No request header, cookie, query parameter, body field, Host, Origin, remote
address, or Referer may create or select the principal, runtime, write mode, or
grant. Host and Origin are mandatory checks against protected startup state;
they do not establish principal identity. Foreign or absent Origin fails before
capability disclosure. CORS behavior is never consulted as authorization.
Only POST is allowed; after the runtime/write/Host gates, every other method,
including OPTIONS/HEAD, returns 405 (HEAD has no response body). This is one
authority-distribution operation in addition to the one classification mutation
surface, not a second edit action.

POST avoids a special exception for same-origin GET's often absent Origin,
keeps secrets out of cacheable read discovery, and cannot be satisfied by
navigation. Browsers supply Origin on same-origin POST/PATCH; unsupported
clients omitting it fail closed. See [MDN Origin](https://developer.mozilla.org/en-US/docs/Web/HTTP/Reference/Headers/Origin).

A future React editor explicitly bootstraps when entering editing, keeps the
token only in private module/closure memory, and attaches it only to the fixed
relative classification PATCH route. Requests use `mode: 'same-origin'`,
`credentials: 'omit'`, `cache: 'no-store'`, and `redirect: 'error'`. Never attach
the header to general fetch helpers, read operations, external requests,
telemetry, DOM fields, URLs, or error messages. No localStorage, sessionStorage,
IndexedDB, service-worker cache, or cross-tab messaging carries it. Reloading
a page requires bootstrap again. This ADR changes no frontend behavior now.

Bootstrap and mutation responses, including errors, require
`Cache-Control: no-store`, `Content-Type: application/json`,
`X-Content-Type-Options: nosniff`, and `Cross-Origin-Resource-Policy: same-origin`.
No CORS grant, Set-Cookie, JSONP, redirect, or token reflection is permitted.
Prevent browser/proxy caching and automatic request replay. The token appears
only in the successful bootstrap JSON response and the approved request header.

Server/proxy logging must use an allowlist of safe operational fields such as
route name, method, status, and stable code. Never log bodies, arbitrary headers,
raw URLs/queries, token fragments/hashes, labels, or exception local variables.
Explicitly redact this header and bootstrap field in Django exception reporting
and any future tracing; disabling DEBUG alone is not sufficient. Use synthetic
sentinel tests to check error, access-log, proxy-failure, and client-error paths.
Privileged browser developer tools and OS memory inspection remain trusted-host
access, not an accidental-logging protection promise.

The bootstrap intentionally trusts the configured browser origin within an
explicitly enabled trusted local runtime. Its public protocol is not a second
password prompt. A native local read client can impersonate that origin and
deliberately acquire authority. To prohibit that, Gouda would need a different
host/user authentication and out-of-band provisioning boundary; silently adding
a token cannot achieve it. Read/write capabilities remain separate despite
sharing this explicit temporary distribution policy.

## Origin, Host, proxy, and CSRF

The first write-enabled topology accepts exactly the serialized Origin
`http://127.0.0.1:5173`, with request Host exactly `127.0.0.1:5173`.
The protected startup option fixes this value; it is never learned from a
request or expanded to all loopback origins. No wildcard, suffix, hostname,
regular-expression loopback range, path, trailing slash, userinfo, query,
fragment, missing port, or alternative spelling is accepted. Require exactly
one Origin; reject `null`, missing, duplicate/combined, and malformed values.
Referer is neither required nor a fallback. Forwarded headers, remote address,
and internal service names cannot supply trusted origin or principal context.

| Topology | Browser Origin / forwarded Host | First write-mode decision |
| --- | --- | --- |
| Current host development | `http://127.0.0.1:5173` / `127.0.0.1:5173` | Supported after implementation, with Vite's fixed proxy to validated `127.0.0.1:8000`. |
| Current Compose | Same browser Origin / Host | Supported after implementation, via Vite -> `http://backend:8000`; Django remains unpublished. Internal `backend:8000` and `0.0.0.0:8000` are not browser origins. |
| Direct browser -> Django port 8000 | `http://127.0.0.1:8000` | Not a permitted write origin; the current React app is served by Vite. Direct numeric-loopback reads remain supported. |
| IPv6 host development | A browser origin would be `http://[::1]:5173` | Backend `runlocal --host ::1` remains a read mode. Current Vite binds/proxies IPv4; reject enabling writes with that unmatched topology. Do not automatically allow IPv6 just because ALLOWED_HOSTS contains it. |
| Other frontend port, preview 4173, localhost, HTTPS, or dual-family edge | Distinct origin | Outside this first write configuration. A later explicit, tested topology may replace the single origin, including exact bracketed IPv6; no implicit aliases or fallback ports. |

The first implementation must validate the supported startup pair: direct host
`127.0.0.1:8000` or existing trusted-container `0.0.0.0:8000`, each with the
single Vite origin above. Existing read launch ports/families remain unchanged.
The current no-wildcard rule applies to host listeners/publications; the
existing isolated Compose wildcard exception remains exactly as in ADR-0010.
No new wildcard or LAN exposure is authorized.

Django must call `request.get_host()` on both new routes and then enforce the
exact frontend authority including port, in addition to checking Origin.
The current empty middleware list and views do not invoke this validation;
the existing Host test only calls `get_host()` on a RequestFactory request.
An ALLOWED_HOSTS setting alone does not prove route enforcement. See
[Django ALLOWED_HOSTS](https://docs.djangoproject.com/en/4.2/ref/settings/#allowed-hosts).
Reject invalid/unexpected Host with `host_not_allowed`, without echoing it.
Retain `USE_X_FORWARDED_HOST=false` and no forwarded-protocol trust.

Vite participates in the trusted delivery chain by serving executable frontend
code and carrying the secret, but Django owns authorization. Preserve
`changeOrigin: false`, original Origin/Host, and the client header. Vite must
never add a secret or rewrite foreign Origin into the trusted value. The
installed Vite middleware handles CORS before the proxy and its default permits
several local origins; checking only that `cors` is not `true` is insufficient.
Before write activation, explicitly disable Vite CORS (`server.cors: false`)
and verify that proxied responses and preflights add no CORS grants. Preserve
strict ports, loopback publication, and bounded application-network membership.
See [Vite server options](https://vite.dev/config/server-options#server-cors).

Django's built-in CSRF protection can work without login/session authentication:
its default secret is carried in a CSRF cookie and paired with a submitted
token. It cannot operate as that built-in model without either cookie state
or session state (`CSRF_USE_SESSIONS`). It checks Origin when supplied, but
plain HTTP has no strict Referer fallback. This design's unconditional Origin
requirement is stronger than merely inheriting those defaults. See
[Django CSRF](https://docs.djangoproject.com/en/4.2/ref/csrf/).

DRF APIViews are CSRF-exempt by default, and SessionAuthentication enforces
CSRF for authenticated sessions, not anonymous callers. Adding that class or
middleware alone would not protect these existing anonymous APIViews. Any
future use of built-in CSRF requires explicit enforcement and request-path
tests. Here the mandatory non-ambient secret header plus exact Origin/Host
checks form the explicit CSRF defense, independent of DRF authentication.
See [DRF SessionAuthentication](https://www.django-rest-framework.org/api-guide/authentication/#sessionauthentication).

Do not introduce cookies or sessions for this slice. SameSite=Strict can help
against cross-site sends, but same-site is broader than same-origin and cookies
do not isolate TCP ports. HttpOnly prevents script reading a cookie, not its
automatic attachment or same-origin malicious actions; a second mechanism
would be needed to put the secret in a request header. Secure cookies normally
require HTTPS with localhost exceptions that should not be assumed portable
across both numeric loopback spellings; exceptions do not encrypt local HTTP.
Neither SameSite nor Secure is a replacement for explicit authorization.
See [MDN Set-Cookie](https://developer.mozilla.org/en-US/docs/Web/HTTP/Reference/Headers/Set-Cookie).

## Application authorization and transaction

Introduce a classification-specific authorized orchestration boundary; the
HTTP view must not load Account/Movement models or call the trusted internal
command with arbitrary selected models. Its inputs are the server-issued
principal, opaque verified write grant, untrusted Account/Movement UUIDs,
Category UUID or null, and expected revision. Validate principal and live grant
before any selector lookup. A read principal with no grant fails.

The explicit temporary write policy permits this grant and the singleton
principal to classify Movements only in Accounts accessible under the Account
read policy. Reuse `resolve_read_account` as that visibility constraint inside
the separate write orchestration; it does not itself grant write permission.
Unknown and policy-denied Accounts share `account_not_accessible`. Resolve
Movement only under that authorized Account; a Movement in another Account
shares `movement_not_found` with an unknown UUID. Only then look up Category.
Categories are the current shared local dataset vocabulary, with no narrower
owner scope; their UUIDs do not bypass the principal, grant, or Account checks.
Revisit both policies before differentiated Accounts/principals/datasets.

Call the existing command exactly once. Preserve its Account -> Movement ->
selected Category lock order, absent-row serialization, revision comparison
before no-op detection, active-target validation, and MANUAL-only writes.
Wrap command and resulting projection materialization in one outer atomic
transaction, retaining the command's locks until the immutable result is
built. Read only the bounded classification/Category projection for that same
Movement while locks are held; never re-read a whole report after commit to
construct success. This prevents responding with another writer's revision or
combining one revision with another assignment. Commit before returning 200;
projection failure rolls back the edit. A subsequent writer may of course
change state after commit. Do not change the internal command's public result
or implement competing transition logic in HTTP.

## HTTP classification contract

Exactly one mutation surface:

```text
PATCH /api/v1/accounts/<account_uuid>/movements/<movement_uuid>/classification/
Content-Type: application/json
Accept: application/json
Origin: http://127.0.0.1:5173
X-Gouda-Classification-Write: <ephemeral capability>
```

```json
{
  "category_id": "22222222-2222-4222-8222-222222222222",
  "expected_revision": 0
}
```

Both keys are mandatory and no other keys or query parameters are accepted.
All UUID strings must use canonical lowercase hyphenated form. A Category UUID
means assign/change/reassign; explicit JSON null means clear. Omission or an
empty string never means clear. Revision 0 requires absence of a classification
row, not a cleared row. Source, timestamp, principal, financial values, label
creation, and generic update dictionaries are not accepted.

Accept only UTF-8 `application/json`, optionally `charset=utf-8`; reject other
media types/parameters and non-identity Content-Encoding. Bound actual body
reads to 1024 bytes, regardless of declared length. Empty or syntactically
invalid JSON, invalid UTF-8, and non-JSON constants are `malformed_json`.
Non-object bodies, duplicate keys, unknown keys, or missing required keys are
`request_body_invalid`. A present category or revision with an invalid type
uses its field-specific code. Parse revision losslessly as a JSON integer
token from 0 through `2**63 - 1`; reject booleans, strings, null, negative values,
fractions, and exponent notation. No float conversion or coercion is allowed.

PATCH here is a versioned application-specific JSON document, not JSON Patch
or JSON Merge Patch. It sets the one editable property of the classification
projection with an explicit concurrency precondition. PUT could also model a
replacement, but suggests replacing server-owned state/revision and adds no
benefit. Separate POST assign/change/clear actions duplicate one command.
DELETE wrongly suggests removing the retained cleared row and complicates the
required revision body. Do not add those alternatives, method overrides,
If-Match as a second revision source, or trailing-slash redirects. After the
runtime/write/Host gates, other methods return 405 with `Allow: PATCH`;
bootstrap uses `Allow: POST`.

Every success, including no-op, returns HTTP 200 with exactly one
`classification` field in the existing report shape:

```json
{
  "classification": {
    "state": "CLASSIFIED",
    "category": {
      "id": "22222222-2222-4222-8222-222222222222",
      "display_name": "Synthetic topic",
      "is_active": true
    },
    "revision": 1
  }
}
```

```json
{"classification": {"state": "CLEARED", "category": null, "revision": 2}}
```

```json
{"classification": {"state": "NEVER_ASSIGNED", "category": null, "revision": 0}}
```

The last shape is the clear-of-absent no-op only. A same-category no-op may
return a CLASSIFIED inactive Category. Persisted revisions remain positive
integers. Source/time/history and token are absent. Returning a whole Movement
would repeat financial/provenance fields and require broader projection work
without improving mutation safety. The request identifies the Movement; the
client must retain that identity and discard responses for superseded views.

## Revision lifecycle and client behavior

Read the authoritative Movement projection and keep its exact revision. After
an explicit user choice, submit that revision and the chosen Category/null.
An actual successful change increments once; update the matching client
classification from the returned projection, never by predicting its revision.
Keep financial values, membership, ordering, count, and totals unchanged.

Both stale existing rows and a positive revision for an absent row return 409.
React must not retry silently, substitute a new revision, or replay the user's
choice automatically. Refetch the selected Account/date report, replace stale
state, and show a short message such as “Classification changed. Reloaded the
latest value; choose again.” If refetch fails, keep editing unavailable until
an authoritative read succeeds. On inactive/missing Category conflicts, refresh
the Category catalog and require a fresh choice. On network failure, invalid
success JSON, timeout, or 5xx, the commit outcome can be ambiguous: refetch and
reconcile before a new user-initiated attempt. A token failure clears the cached
token; reacquisition never automatically resends the edit.

Correct-revision idempotent no-ops remain exactly the service behavior:
same-category, clear-of-cleared, and clear-of-absent preserve revision/time;
the absent clear creates no row. A stale identical command still conflicts.
The token is reusable authority, not a nonce or deduplication key. Replays of
successful actual changes carry old revisions and conflict, including an
assign/clear/reassign cycle. A correct no-op can repeat until state changes.
No-op at the maximum bigint revision succeeds; actual change at that revision
fails with `classification_revision_exhausted`.

The HTTP contract preserves bigint rather than narrowing the domain to
JavaScript numbers. Current React rejects non-safe integer revisions. A future
editor must never round/coerce them and must disable submission at or above
`Number.MAX_SAFE_INTEGER`, so a successful increment cannot leave its parser's
safe range. Reports above that range continue failing closed under the existing
parser. Full-range browser editing requires a separate lossless transport/parser
decision; no string-revision or read-format change is made here. Raw clients
using lossless JSON integers may exercise the full domain range.

## Stable errors and evaluation order

Responses contain exactly `{"code": "<stable_code>"}`; HEAD has no body.
No database, Python, proxy exception, submitted secret, header, or label text
is exposed. Unknown exceptions/codes map to 500 `internal_error` through a
safe JSON handler, with rollback where applicable.

| Code | HTTP status | Meaning |
| --- | --- | --- |
| `local_delivery_not_active` | 503 | Validated read runtime absent or expired. |
| `mutation_not_enabled` | 403 | Local runtime active but classification write mode absent. |
| `host_not_allowed` | 400 | Missing, malformed, or unexpected Host authority. |
| `origin_not_allowed` | 403 | Origin missing, null, malformed, duplicated, or not exactly configured. |
| `write_capability_invalid` | 403 | Missing, malformed, incorrect, old-runtime token or invalid application grant. |
| `principal_context_invalid` | 403 | Server-issued principal rejected. |
| `account_selector_invalid` | 400 | Invalid Account UUID. |
| `account_not_accessible` | 404 | Unknown, denied, or subsequently disappeared Account. |
| `movement_id_invalid` | 400 | Invalid Movement UUID. |
| `movement_not_found` | 404 | Movement absent from the authorized Account. |
| `category_id_invalid` | 400 | Present Category selector is neither a canonical UUID nor null. |
| `category_not_found` | 404 | Target Category unknown, after authorization and Movement resolution. |
| `category_inactive` | 409 | New assignment targets a retired Category. |
| `expected_revision_invalid` | 400 | Present revision violates the exact integer contract. |
| `classification_not_present` | 409 | Positive expected revision supplied for an absent row. |
| `classification_revision_conflict` | 409 | Persisted revision differs, even for an otherwise identical command. |
| `classification_revision_exhausted` | 409 | Actual change cannot increment maximum bigint. |
| `malformed_json` | 400 | Body is not valid UTF-8 JSON. |
| `request_body_invalid` | 400 | Body is not the exact allowed object shape. |
| `query_parameters_not_allowed` | 400 | Any query parameter, including format/method overrides. |
| `request_body_too_large` | 413 | Actual body exceeds 1024 bytes. |
| `method_not_allowed` | 405 | Method outside the route's one allowed method. |
| `not_acceptable` | 406 | Accept excludes JSON (including JSON with q=0); absent Accept or a compatible wildcard is allowed. |
| `unsupported_media_type` | 415 | Content-Type/charset or Content-Encoding unsupported. |
| `internal_error` | 500 | Unexpected failure, unmapped code, or invalid internal Account object. |

The internal command's `account_not_found` maps to `account_not_accessible`;
`account_not_persisted` is an orchestration defect and maps to `internal_error`.
Do not turn arbitrary database exceptions into revision conflicts.

For a matched route, require local runtime, write activation, Host, allowed
method, Origin, token (mutation only), then valid server principal. Only after
those gates perform Accept negotiation, query rejection, media/encoding checks,
bounded JSON parsing, shape validation, and selector validation in Account,
Movement, Category, revision order. Then resolve authorized Account and invoke
the service, preserving its existing domain error precedence. Denials before
Account resolution perform zero database queries. Unknown paths use ordinary
404 routing; malformed HTTP rejected below Django need not have this envelope.

These two routes need an explicit pre-handler security gate: DRF's current
content negotiation runs before handler code, so copying the GET handler
pattern would not implement this order. Disable format overrides on the new
routes. No DRF browsable API, implicit parsers, automatic HEAD/OPTIONS, HTML
debug response, or fallback authentication may widen them. Existing three GET
contracts remain read-only and retain their current behavior.

## Implementation acceptance and deferred work

The next bounded task is the backend runtime/bootstrap/authorized PATCH slice
and the required delivery-edge controls, under this ADR, with editor controls
still deferred. Validate before enabling writes:

- Default-off startup, supported host/Compose opt-in, invalid modes/origins,
  debug rejection, runtime cleanup/restart, and old-grant rejection.
- Real request-path Host validation and the complete security/error matrix,
  including missing/null/foreign Origins, simple form bodies, hostile headers,
  valid read clients lacking tokens, and identical safe denial bodies.
- A real same-origin browser bootstrap/PATCH and public-origin adversarial
  attempts through Vite, plus direct-backend attempts, absent CORS headers,
  rejected preflights, no redirects, and safe cache/log behavior. Mock fetch
  tests alone cannot establish browser header behavior.
- Explicit proof of the limitation: a trusted raw local client can spoof
  Origin and bootstrap while writes are enabled. Do not label that blocked.
- Separate principal/grant/Account policy checks, cross-Account Movement IDs,
  invalid/inactive Categories, strict body parsing, and bigint/no-op boundaries.
- Real PostgreSQL races through the authorized adapter, including first-write,
  same-revision updates, clear/reassign, retirement, projection consistency,
  rollback, and unchanged canonical/source graph. Reuse the existing domain
  command; avoid migration or unrelated ingestion changes.
- A separate later React editor task covers explicit choices, Category catalog
  use, safe revision submission, view/request races, refetch on 409 or ambiguous
  outcomes, no silent retry, and memory-only capability handling.

Revisit this ADR before untrusted local users/processes, remote/LAN access,
re-publication, independent users, multi-worker serving, new write operations,
automated clients with durable grants, or protection from same-origin code
compromise. No persistent authentication, ownership, category management,
financial mutation, history, transfer, or economic-event design is implied.
