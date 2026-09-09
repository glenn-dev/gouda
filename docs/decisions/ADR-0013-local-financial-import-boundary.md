# ADR-0013: Separate local financial-import authority

- Status: Accepted design; implementation deferred
- Date: 2026-09-08
- Extends: ADR-0010 for Santander current-account XLSX imports only
- Preserves: ADR-0003/0006 lifecycle, ADR-0005 sign, ADR-0008/0009 compatibility,
  and ADR-0011/0012 classification boundaries

## Context

The verified implementation baseline is `ebb8b11c6c90d20c334455bc9ad66af4f0c3a1ab`.
Gouda grew from Glenn and Mei's manual household spreadsheet workflow into a
trust-first ledger. The local React report works, but its reproducible demo is
synthetic. Importing one supported private statement through the application
will let subsequent classification and financial-product decisions use real
events. Synthetic data remains the committed regression and visual-QA source.

The existing Santander service already owns financial acceptance, provenance,
transactions, and exact-artifact duplicates. Browser upload needs separate
authority: classification changes organizational metadata; imports retain
private evidence and create canonical financial facts.

The [flow contract](../architecture/local-financial-import.md) records the
verified implementation, exact HTTP and failure contracts, private storage,
operator procedure, and implementation acceptance criteria. This checkpoint
changes documentation only. Historical ADR status sentences describe their
original checkpoints; code and current architecture confirm ADR-0011/0012 are
already implemented.

## Decision

Permit only a synchronous, single-file Santander current-account XLSX import,
through a separate authorized application operation. It requires all of:

1. The live validated `LocalDeliveryRuntime` under
   [ADR-0010](ADR-0010-loopback-only-local-mvp-delivery.md).
2. Independent default-off financial-import startup activation in the private
   dataset configuration described below.
3. Exact Django request Host and browser Origin checks.
4. An independently generated import capability in its dedicated inbound header.
5. A valid server-issued principal and live, Santander-current-import-only grant.
6. Account read visibility **and** the explicit import policy and source/domain
   compatibility checks, followed by bounded upload admission.
7. The unchanged deterministic Santander recognition and import lifecycle.

Read authority, classification authority, Account UUID possession, matching
Origin, and a plausible file are each insufficient. Import authority cannot
classify, create Accounts/Categories, resolve arbitrary observations, correct
or delete Movements, or authorize a future import adapter automatically.

This satisfies ADR-0010's import revisit trigger without changing its trusted
host perimeter. No User, Household, ownership, authentication, session, cookie,
LAN, cloud, remote access, or background worker is introduced. An arbitrary
process on the trusted host can forge Host/Origin and deliberately bootstrap.
This is an accepted limitation, not an attack the capability claims to stop.
Same-origin compromised code and privileged browser extensions are also trusted
host failures outside this protection.

## Runtime and browser capability

Require both proposed startup flags `--enable-financial-imports` and
`--financial-import-origin http://127.0.0.1:5173`. Reject duplicate/abbreviated
flags, incomplete pairs, DEBUG=true, an unsupported dataset, and any topology
except direct host `127.0.0.1:8000` or the existing explicit trusted-container
`0.0.0.0:8000` mode. Existing IPv6 and other-port reads remain unchanged.
The default launch and `make demo` create no import runtime or secret.

Use a dedicated opaque `LocalFinancialImportRuntime` tied to the active
delivery runtime. Generate an independent 32-byte cryptographically random
secret, encoded as 64 lowercase hex characters, after startup validation.
Keep it only in serving-process memory; clear runtime/secret/grant references
on exit and reject old runtime objects, capabilities, and grants after restart.
Do not derive it from, compare against, or reuse the classification secret.
Do not configure it in environment variables, CLI arguments, files, or a DB.

Bootstrap is explicit JSON POST
`/api/v1/local/financial-import-capability/`. Only its successful response
discloses the import secret. The sole inbound transport is exactly one
`X-Gouda-Financial-Import` header on the source-specific import POST. Check its
shape and compare in constant time; verification returns an opaque live
`SantanderCurrentAccountImportGrant`. Never pass the secret to the importer.
Both capabilities may coexist but neither grant validator accepts the other's
grant or token, even if supplied in the other header.

The bootstrap/distribution and exact Host/Origin properties follow
[ADR-0012](ADR-0012-local-classification-write-boundary.md), with independently
owned state and routes. Host must be exactly `127.0.0.1:5173`; Origin exactly
`http://127.0.0.1:5173`. Reject missing, null, combined, duplicated, malformed,
foreign, and alternative spellings. Invoke `request.get_host()` as well as the
exact comparison. Referer, forwarded headers, internal service names, and
remote address never substitute. Vite preserves originals and duplicate
multiplicity, never injects either capability, and retains disabled CORS,
frame denial, and safe proxy diagnostics.

React acquires import authority only after an explicit Import submission.
Keep it in a dedicated closure/module variable; send only to the fixed relative
import route with `mode: 'same-origin'`, `credentials: 'omit'`,
`cache: 'no-store'`, and `redirect: 'error'`. No shared fetch-header default,
DOM token, cookie, URL, browser storage, service worker, cross-tab message,
analytics, or console logging. Page reload requires bootstrap; invalid capability
clears it. Reacquisition never silently resubmits an import. Bootstrap does not
rotate the token or create a session. Stop/restart is the revocation mechanism;
multi-worker serving and durable client grants are deferred.
Revocation prevents subsequent commands; it is not an undo/cancel operation for
an already admitted import. Orderly shutdown should drain that one in-flight
operation; process termination relies on the existing DB transaction boundaries.

## Account policy and limits of binding

The temporary import policy permits the singleton trusted principal with the
live source-specific grant to import into a visible, persisted, non-demo
`CURRENT` / `ASSET` Account with a valid persisted ISO-like currency. Reuse
`resolve_read_account` as a visibility constraint inside the separate import
orchestration, after principal and grant validation. Unknown and policy-denied
Accounts share `account_not_accessible`; visibility alone grants no import right.

Explicit operator selection supplies the intended Account. Account has no
provider field, bank account identifier, or Santander current-account binding;
the frozen parser does not verify a source account number or currency label.
Consequently the operator must verify that this original statement belongs to
the selected Account and its displayed currency. This is deliberate trusted
import context, not independently verified bank identity. Names, references,
amounts, and transaction descriptions cannot establish it. Do not invent a
provider registry, configuration allowlist, or TDC-style suffix binding here.
Revisit with source evidence before promising bank-account identity verification.

The existing importer re-fetches Account before registration and checks
kind/orientation/currency again under its materialization lock. The new wrapper
also rejects the fixed demo Account identities before any evidence persistence.
Account creation/configuration stays a deliberate local operator setup through
existing Django/model facilities, outside the browser API.

## Preserve financial and evidence semantics

Call `import_santander_current_account_xlsx` exactly once per admitted request,
outside any caller transaction. Preserve registration, parsing, materialization,
and fatal compensation as separate phases. Do not copy classification's outer
atomic wrapper: this importer explicitly rejects an existing transaction.

The service directly materializes one Movement per valid parsed row and no
observations or resolution rows, as allowed by ADR-0008/0009. Valid subsets of
`PARTIAL` batches and valid rows from `NOT_RECONCILED` statements remain
canonical. A persistence failure must roll back the entire materialization
graph. These are different meanings of “partial”; the UI must distinguish them.
Requiring reconciliation for acceptance would change the frozen source contract
and is not authorized here.

Reuse exact-byte SHA-256 identity, byte comparison on digest reuse, the existing
artifact/Account materialized uniqueness constraint, and Account locking. A
repeated exact file for the same Account records a `DUPLICATE` attempt with no
new Movements and reports the original result. This is not transaction-value
or cross-export deduplication. Different bytes or a different Account can create
another graph; the UI explicitly states that limit and requires correct Account
selection. Do not resave a workbook or use overlapping exports as a retry.

## Private dataset separation

Before enabling the browser slice, implement a distinct supported local startup
for fixed Compose project `gouda-private`, PostgreSQL database `gouda_private`,
and volume `gouda-private_gouda-private-postgres-data`. It preserves the existing
Vite-only loopback edge and unpublished Django/PostgreSQL topology. The private
override must replace the database mount, not attach the demo/default volume.
It neither seeds demo data nor mounts a private statement directory. Its stop
operation preserves the volume; it has no reset/delete target.

Import startup requires the configured database name `gouda_private`; this is
an accidental-dataset guard, not DB authentication or volume attestation.
Repository composition/tests must prove actual volume separation from
`gouda-demo`, `gouda-host-dev`, and the historical default volume. Host-process
development may explicitly connect to that same isolated private database using
a separately tested loopback DB publication. Neither mode may reuse the demo
database. Arbitrary operator overrides remain inside the trusted-host limit.
The proposed entry points are `make private` and `make private-down`, using a
fixed `docker-compose.private.yml` override and project name. `make private`
is explicit import opt-in: validate required local secrets without printing,
build/start/migrate, enable the two import flags, and wait for health; never seed
or create an Account automatically. `make private-down` preserves the private
volume. Keep the demo project/volume variables non-redirectable. These commands
and the override do not exist yet; they are part of the implementation scope.

`make demo-reset` deletes its entire fixed demo volume, regardless of row
provenance; `clear_demo` instead targets fixed UUIDs and rolls back on protected
references. Neither is private-data cleanup. Default demo commands gain no
import activation, file discovery, directory mount, or private-volume target.

## Alternatives and consequences

Choose one-step selection plus explicit Import. File selection itself makes no
request. A short instruction explains Account responsibility, exact-file retry,
private evidence retention, and valid-subset acceptance. Results expose counts
and independent reconciliation state, then reuse the existing report.

A validate/confirm flow would require parsing twice or managing bound expiring
server-side upload receipts, Account/content/parser-version consistency, cleanup,
and concurrent confirmation. It adds little verification because the frozen
source cannot identify the target bank account. Defer it until preview supports
a concrete decision. No wizard or generic upload/session engine is justified.

Origin-only imports would omit deliberately carried operation authority; reusing
classification grants would widen an unrelated privilege. Persistent login or
out-of-band tokens would address a different host threat model. A new import
engine, value-based deduplication, blanket transaction, or reconciliation gate
would replace tested financial semantics. All are rejected for this slice.

Later Santander TDC and BCI work may reuse transport/privacy concepts with
explicit additional grants, routes, and source adapters; TDC retains its binding
and BCI retains its separate observation/resolution policy. This ADR grants none
of those writes. Revisit before broader sources, differentiated principals,
remote exposure, background jobs, durable capabilities, or canonical correction.
