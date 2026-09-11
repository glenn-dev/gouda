# Local financial import v0.1

## Status and scope

Accepted design, 2026-09-08; implemented 2026-09-09 for the single Santander
Current Account XLSX browser route, dedicated runtime, private Compose workflow,
bounded admission, and React import form. The first controlled private
real-data acceptance completed on 2026-09-10; its sanitized evidence and limits
are recorded in the
[adversarial review](../development/local-import-adversarial-review.md#private-acceptance-result).
[ADR-0013](../decisions/ADR-0013-local-financial-import-boundary.md) owns the
new authority decision. This document owns its narrow transport, product flow,
and acceptance contract. Existing read APIs remain unchanged.

Only Santander Current Account XLSX is in scope: one browser-selected file,
one explicitly selected Account, deterministic import into PostgreSQL, and
navigation to the existing canonical Movement report. No source selector,
provider inference, TDC/BCI upload, receipts, OCR, AI, classification editor,
multi-file batch, import history dashboard, cloud storage, or background jobs.

## Verified implementation

Verified against baseline `ebb8b11c6c90d20c334455bc9ad66af4f0c3a1ab`, not solely
historical documentation:

| Boundary | Current implementation and evidence |
| --- | --- |
| Parser | [santander_parser.py](../../gouda/santander_parser.py): `parse_workbook` uses openpyxl with `data_only=False`, `keep_links=False`; snapshots worksheets and recognizes exactly one visible fixed-column candidate. [Parser tests](../../tests/test_santander_parser.py) cover dates, directions, formulas, malformed/ambiguous sources, row outcomes, and independent reconciliation. |
| Import | [santander_import.py](../../gouda/ledger/services/santander_import.py): registration, parse, complete graph validation, `assert_santander_v1_structure`, money preparation, materialization, fatal compensation. `recognize_santander_v1` composes the same graph/structure checks; it is not a filename detector. |
| Lifecycle tests | [Service tests](../../tests/ledger/test_santander_import_service.py) prove exact evidence, pre-parse duplicate, partial/rejected/zero-row results, context changes, fatal retry, rollback seams, and compensation failure. [Concurrency tests](../../tests/ledger/test_santander_import_concurrency.py) demonstrate real PostgreSQL Account lock contention and exact-file duplicate convergence. [Helper tests](../../tests/ledger/test_santander_import_helpers.py) validate the complete parser graph and source variant. |
| Persistence | [models.py](../../gouda/ledger/models.py): exact-byte `SourceArtifact`; source-typed `ImportBatch`; immutable row evidence in `RawRecord`; one originating RawRecord per `Movement`. Materialized uniqueness is artifact + Account, excluding parser version. |
| Observations | `FinancialObservation` and `ObservationResolution` exist, but this Santander service calls neither. [Evidence architecture](evidence-resolution.md) and ADR-0008/0009 explicitly preserve this deterministic route. BCI Historical separately creates unresolved observations and runs its conservative policy; do not transplant it here. |
| Access/report | [account_access.py](../../gouda/ledger/services/account_access.py) issues/validates the opaque singleton principal and resolves read visibility. [movement_reporting.py](../../gouda/ledger/services/movement_reporting.py) reads canonical Movements by Account/inclusive occurrence dates, orders by date/UUID, and provides exact Decimal totals and bounded provenance/classification. Observation state and reconciliation are not report filters. |
| Delivery/client | [local_delivery.py](../../gouda/local_delivery.py), [financial runtime](../../gouda/local_financial_import.py), [financial import adapter](../../gouda/ledger/financial_import_api.py), [authorized orchestration](../../gouda/ledger/services/financial_import_access.py), and [URLs](../../config/urls.py) implement the independent opt-in import route. [App.tsx](../../frontend/src/App.tsx) and [api.ts](../../frontend/src/api.ts) implement one-step explicit selection, memory-only capability use, bounded results, uncertain-outcome handling, and report navigation. |
| Admission/privacy | [xlsx_admission.py](../../gouda/ledger/xlsx_admission.py) applies the frozen ZIP/XML/worksheet bounds before openpyxl. [docker-compose.private.yml](../../docker-compose.private.yml) and [Makefile](../../Makefile) isolate the private database/volume without seed/reset/file mounts. [safe_http_logging.py](../../gouda/safe_http_logging.py) protects both import routes, header names, request data, and exception reports. |

The frozen [Santander contract](../contracts/santander-import-contract.md)
remains authoritative for source semantics, although its original future-tense
persistence statements predate implementation. ADR-0006 superseded the older
placement of source kind on SourceArtifact. Account has no bank/provider field
or current-account identifier binding. Structural recognition establishes a
supported layout, not cryptographic bank authenticity.

## Operator and React flow

Add one small “Import data” section consistent with
[UI Foundation v0.1](../design/ui-foundation.md). Reuse native Select, Label,
Input, and Button, with a native single-file input. Show the fixed source label
“Santander Current Account XLSX”. Discover Accounts through the existing GET;
show current Accounts and currency, with an initially empty selection even when
there is only one. Do not inherit the report's automatic first selection.
Display the chosen Account context outside the select as the current UI does.

Before submission, show concise instructions:

> Choose the Account this original statement belongs to and check its currency.
> Gouda keeps the statement privately in the local database and imports valid
> rows even if other rows are rejected or the statement does not reconcile.
> To retry, use the same original file and Account. Resaved or overlapping
> exports are not detected as the same statement.

File selection performs no upload or filesystem scanning. “Import” explicitly
bootstraps import authority, then submits the captured Account/file pair once.
No preview/confirmation endpoint or upload receipt exists. Client size/media
hints improve feedback but never replace server checks. Empty Account discovery
explains that an Account needs local operator setup; no Account CRUD is added.
Disabled import runtime shows a safe startup instruction after bootstrap denial.

Lock import controls while submitting; use static “Importing…” status, not
percentages or animations. Keep report and import state separate; never attach
an import result to a subsequently selected Account/file. No optimistic rows,
automatic retry, URL-triggered import, or cross-window action. On completion,
release the File reference and reset its input; on failure allow explicit
reselection/retry without storing bytes in persistent browser state.

For a normal accepted/reconciled result, show “Import complete”, accepted and
rejected record counts, “Statement reconciled”, and “View movements”. Also
show ignored rows as explanatory secondary text. Use “Import completed with
rejected records” for PARTIAL, “No movements imported; records rejected” for
REJECTED, and “No movement records found” for an all-ignored accepted statement.
NOT_RECONCILED says “Statement does not reconcile; valid movements were
imported”; INSUFFICIENT_DATA says “Not enough evidence to reconcile”; and
NOT_APPLICABLE says “Reconciliation not applicable”. No clean-success claim
may hide these outcomes.

Duplicate means “Already processed for this Account; no new movements” and
displays the original outcome, including original rejection/reconciliation
warnings. It never labels a prior REJECTED/PARTIAL result a clean import.

“View movements” sets the existing report Account and inclusive statement
period from the server result, explicitly loads that report, and moves focus
to its heading. This is the Account's whole period, possibly containing other
imports, not a new batch-filtered view. Keep that scope visible. Disable this
action when the effective result has no Movements. Existing exact money
strings, order, counts, totals, classification labels, and privacy projection
remain unchanged. Errors are safe mapped text near the form, with `role=alert`;
status uses polite announcements. Preserve keyboard focus, 44px controls,
320px reflow, and wrapping text. No new UI library, router, dialog, drag/drop,
charts, Category controls, or file manager is needed.

## HTTP contract

Two new plain Django views with explicit dispatch gates; no generic CRUD,
ViewSet, router, model serializer, DRF automatic multipart parsing, or method
override. Paths require the trailing slash; do not redirect slashless requests.

| Operation | Exact request | Successful response |
| --- | --- | --- |
| Capability | `POST /api/v1/local/financial-import-capability/`; UTF-8 `application/json` (optional `charset=utf-8`), body exactly `{}`, at most 1024 actual bytes | 200, exactly `{"import_capability":"<runtime secret>"}` |
| Import | `POST /api/v1/accounts/<account_uuid>/imports/santander-current-account-xlsx/`; `multipart/form-data` with one boundary parameter and exactly one file part named `statement`; import capability header required | 200, bounded result below for ACCEPTED, PARTIAL, REJECTED, or DUPLICATE |

No text fields are accepted. Account appears only as a canonical lowercase
hyphenated UUID path selector. Reject extra/duplicate parts, duplicate or unknown
part headers, multiple files, nested multipart, and missing/empty file content.
The file part has exactly `Content-Disposition: form-data` with one `name` and
one `filename` parameter, plus optional Content-Type; reject other disposition
parameters (including `filename*`). The outer boundary is one valid ASCII MIME
boundary of 1–70 characters, optionally quoted. Ordinary browser transport
headers are allowed but grant no authority; repeated Host/Origin/capability or
ambiguous framing headers fail closed. A single filename metadata value is required;
reuse the importer's basename/NFC/control-character/255-character validation.
Do not use a client path to open a file. No source kind, parser version,
currency, financial field, digest, principal, token body field, confirmation
flag, or idempotency key is accepted.

The browser's `.xlsx` accept hint and part MIME are advisory about content.
Permit file part MIME absent, `application/octet-stream`, or
`application/vnd.openxmlformats-officedocument.spreadsheetml.sheet`, with no
parameters. Other part types are 415. No suffix establishes or overrides source
identity: a valid XLSX with a different basename suffix may pass; a renamed PDF
cannot. Reject non-identity Content-Encoding on either route. Accept negotiation
uses the tested ADR-0012 JSON rule (absent/compatible wildcard allowed; JSON
excluded means 406). Reject any nonempty query string, including overrides.

Result example uses synthetic counts, dates, and UUIDs:

```json
{
  "account_id": "11111111-1111-4111-8111-111111111111",
  "batch_id": "22222222-2222-4222-8222-222222222222",
  "status": "ACCEPTED",
  "duplicate_of": null,
  "created_movement_count": 2,
  "statement": {
    "status": "ACCEPTED",
    "source_row_count": 8,
    "parsed_count": 2,
    "ignored_count": 6,
    "rejected_count": 0,
    "reconciliation_status": "RECONCILED",
    "period_start": "2026-02-01",
    "period_end": "2026-02-28"
  }
}
```

These are the exact keys. Counts are nonnegative JSON integers; dates are
strict ISO dates. `source_row_count` is parsed + ignored + rejected and includes
metadata/header/blank/footer rows in the parser snapshot; movement candidates
are parsed + rejected. `created_movement_count` equals parsed count for a newly
materialized attempt and zero for DUPLICATE. For duplicates, `duplicate_of`
is the target batch UUID and `statement` is that same-Account target's bounded
summary; its status is ACCEPTED/PARTIAL/REJECTED. For other results it is the
returned batch summary and `duplicate_of` is null. Exclude balances, differences,
raw row codes/cells, descriptions, filenames, digests, bytes, and source paths.
No arbitrary ORM serialization or artifact-download endpoint.

Build a frozen result from the returned completed batch and, for duplicates,
its validated direct target. Projection occurs after the service's commits;
failure cannot undo them. Return no PROCESSING/FATAL success shape. 200 means a
completed, accurately reported lifecycle result, not necessarily reconciliation
or any newly created Movement. Do not add 202, jobs, or a polling endpoint.

## Gate order and safe errors

For matched routes, evaluate in this order:

1. Active local delivery; enabled valid import runtime/private-dataset startup.
2. `get_host()` and exact Host; then POST-only method; exact Origin.
3. Import capability verification (upload only); issue and validate the existing
   server principal. Bootstrap skips the token it is obtaining.
4. JSON Accept, no query string, media/encoding validation. Bootstrap now reads
   bounded JSON, verifies exactly `{}`, and returns without database queries.
5. For upload, validate Account UUID; the separate authorized import operation
   revalidates principal/live grant, resolves read visibility, excludes fixed demo
   IDs, and checks CURRENT/ASSET/valid persisted currency before body parsing.
6. Acquire one nonblocking process-local upload slot; if occupied, return
   `import_busy`. Bound/read/validate multipart and archive admission, revalidate
   the live grant, then invoke the existing importer once, without an outer
   transaction. Release the slot and request buffers in `finally`.

The slot bounds memory-heavy work; it is not deduplication, a job queue, or a
replacement for database locks. No body parsing, file reading, DB access, or
secret disclosure occurs before the relevant security gates. Account lookups
are the first request DB work; bootstrap and earlier denials have zero queries.
Use a lazy admitted-upload reader at the new application orchestration seam so
the HTTP view cannot pass an arbitrarily fetched Account to the trusted service.

All errors contain exactly `{"code":"<stable_code>"}`. Never echo input,
parser exception messages, SQL, paths, filename, digest, cells, financial values,
or capability. Unmapped failures become `internal_error`. HEAD returns no body.

| Failure / stable code | Status | Persistence implication |
| --- | --- | --- |
| `local_delivery_not_active` | 503 | No request persistence. |
| `financial_import_not_enabled` | 403 | No request persistence; separate from classification's mutation flag. |
| `host_not_allowed` | 400 | No request persistence. |
| `method_not_allowed` | 405 | `Allow: POST`; includes OPTIONS/HEAD, no implicit preflight success. |
| `origin_not_allowed` | 403 | No request persistence. |
| `import_capability_invalid` | 403 | Missing, bad, expired capability or wrong/forged grant; no request persistence. |
| `principal_context_invalid` | 403 | No request persistence. |
| `not_acceptable` | 406 | JSON excluded. |
| `query_parameters_not_allowed` | 400 | No request persistence. |
| `unsupported_media_type` | 415 | Unsupported outer/part media or encoding. |
| `malformed_json` / `request_body_invalid` | 400 | Bootstrap syntax/shape or multipart shape/metadata invalid. |
| `account_selector_invalid` | 400 | UUID malformed. |
| `account_not_accessible` | 404 | Unknown, denied, or disappeared Account; no enumeration distinction. |
| `account_source_incompatible` | 409 | Wrong kind/orientation/currency or reserved demo Account; no artifact registration. |
| `statement_missing` | 400 | Missing or zero-byte statement. |
| `request_body_too_large` / `statement_too_large` | 413 | Exceeds request/file bound; no registration. |
| `import_busy` | 429 | Another upload holds admission slot; no registration; no automatic retry. |
| `statement_resource_limit` | 413 | Archive/XML/worksheet resource budget exceeded; no registration. |
| `xlsx_invalid` | 422 | Malformed/truncated/password-encrypted package; no registration when admission rejects, FATAL retained when importer detects it. |
| `source_unrecognized` | 422 | Unsupported/ambiguous worksheet or v1 structure; normally retained FATAL. |
| `statement_not_importable` | 422 | Known source period/formula or exact-money boundary rejection; retained FATAL. |
| `account_context_changed` | 409 | Existing importer's post-parse context guard failed; retained FATAL, no new graph. |
| `source_kind_conflict` | 409 | Existing materialized different route; retained FATAL, no new graph. |
| `import_persistence_failed` | 503 | Registration/materialization/compensation database or operational failure; see transaction table. |
| `internal_error` | 500 | Unexpected parser/boundary/adapter/projection failure; outcome may be ambiguous after commit. |

Map only known service codes: `xlsx_invalid` directly; header-not-found,
ambiguous worksheets and `source_variant_unsupported` to `source_unrecognized`;
period-context/formula and known exact-money validation codes to
`statement_not_importable`; Account kind/orientation/currency errors to
`account_source_incompatible`; `account_not_found` to `account_not_accessible`.
Known registration/materialization persistence and fatal-compensation failures
map to `import_persistence_failed`. Digest collision, invalid parser graph,
changed attempt, unknown parser code, unexpected exceptions, unsaved Account,
or unsupported caller transaction are internal failures, not user rejections.
Inspect FATAL stage/code even when the service returns normally; do not infer
success merely from a returned model. Row-level parser rejection instead uses
the completed PARTIAL/REJECTED result, with independent reconciliation.

Every matched-route response, including errors, has JSON content type,
`Cache-Control: no-store, no-cache, max-age=0`, `Pragma: no-cache`,
`X-Content-Type-Options: nosniff`, and
`Cross-Origin-Resource-Policy: same-origin`. No cookies, CORS grants, redirects,
or capability reflection. Lower-level malformed HTTP may close the connection
without this JSON envelope. Preserve strict framing rejection in the real
Vite/Django chain; do not trust Content-Length to bound actual reads.

## Private bytes and admission

Set file maximum to **5 MiB (5,242,880 bytes)** and total multipart body maximum
to **5 MiB + 16 KiB (5,259,264 bytes)**, including boundaries/headers. Read no
more than total limit + 1, reject excess, and independently enforce file size.
Early declared-length rejection is allowed only after the gates; it does not
replace actual bounds. Require well-formed request framing; test unknown/false
lengths and transfer encoding through the real proxy. No API URL accepts a
filesystem path. Browser uploads only the explicitly chosen File.

Use an explicitly memory-only multipart reader over the bounded bytes, with
exact one-part validation. Do not access `request.POST`, `request.FILES`, DRF
automatic parsers, or Django's default disk-spooling handlers first. Do not
change global read API parsing. No temporary upload files, media directory,
static copy, ZIP extraction directory, or filesystem artifact store is needed.

The supported `runlocal` WSGI transport closes each connection without draining
unread request bytes. Django 4.2's default request cleanup performs an unbounded
read even after a view denial and therefore cannot supply this guarantee.
The transport also preserves repeated Content-Length/Content-Type values for
rejection. Both import routes reject transfer encoding and ambiguous framing.
Orderly launcher exit waits for request threads before revoking runtime state.

Compressed size alone is insufficient: the current parser loads a complete
workbook and iterates its rectangular used ranges. Before invoking it, admit
only a bounded OOXML ZIP package: at most 128 entries, 20 MiB total expanded
bytes, 10 MiB per entry, four worksheets, 10,000 rows and 64 columns per sheet,
and 100,000 rectangular cells summed across all sheets, including hidden ones.
Bound actual streamed decompression as well as declared sizes; reject corrupt
CRC, encryption, duplicate/unsafe member names, unsupported ZIP methods (only
stored/deflate), and macro-enabled workbook content. Never execute formulas,
macros, relationships, embedded programs, or external links.

Use an entity/DTD/external-resource-disabled XML reader for resource inspection;
include actual cell, row, merge extents, inferred indices when omitted, and
declared dimensions so sparse cells and merges cannot inflate openpyxl allocation
beyond the budget. Bound XML
depth to 64 and element count to 500,000 across the package. Resource inspection
must complete before openpyxl allocation and must not repair, rewrite, select
financial rows, or decide Santander semantics. Required implementation validation
must establish a safe pinned XML reader configuration; a byte substring check
for DTD is insufficient. These are browser admission limits, not revisions to
the frozen source parser. Reject unsupported package forms safely; do not
decrypt, prompt for a password, or fall back to another parser.

Count workbook sheet references as well as physical worksheet members; reject
aliases and relationships that would load a worksheet more than once. Hyperlink
ranges participate in extent limits, and repeated merge/hyperlink work is also
bounded. Only the ordinary workbook/worksheet/style/shared-string/theme/property
relationships are admitted; comments, drawings, images, pivots, chartsheets and
other secondary loaders are unsupported. XML relationship/content-type targets
must remain inside inspected XML members. Reject, rather than rewrite, these
unsupported package forms.

A callback-based XML preflight applies the element/depth budget before building
trees and limits namespace and expanded XML names to 1024 characters. Account
for repeated shared-string and number-format use across cells within a 20 MiB
text budget (four bytes per character). This prevents small package tables from
multiplying private parser/evidence text. These are admission controls, not
source interpretation changes. The 5 MiB file limit is not a 5 MiB process-RAM
ceiling: bounded transport copies, ZIP metadata and parser objects have overhead.

Once admitted, pass the unchanged file bytes and original filename metadata to
the existing service. It computes SHA-256, compares bytes on digest reuse, and
stores exact content in PostgreSQL `SourceArtifact.content`. The first normalized
basename is retained privately; later names do not overwrite it. An extension
or filename is never trusted as source/account identity. Admission-denied files
leave no artifact/attempt; this explicit receive policy is allowed by P1's
privacy/security/size controls. Safely admitted but source-unrecognized files
retain normal FATAL evidence. Raw rows persist only on materialization.

Close byte streams/archives and release request/parser/File references on every
exit. Python/browser memory cleanup is not secure erasure; the selected original
stays where the operator kept it. Retain registered evidence in the private DB
across errors, duplicates, app teardown, and restart; no automatic TTL or deletion.
DB files/WAL/backups are private evidence too, outside the repository and static
paths, subject to host access and encrypted-disk/backup controls. This local
HTTP/database stack does not claim application-level encryption at rest or TLS.
Retention/export/deletion tooling is deferred; no browser delete is introduced.

Extend the existing safe logging boundary for both new routes, import header,
bootstrap field, and whole import request exception reporting. Allow only fixed
method/route/status/code diagnostics. Suppress bodies, arbitrary headers/URLs,
filenames/digests, parser warnings containing source values, SQL parameters,
exception chains/locals, and response payloads across Django, parser libraries,
proxy, and React. DEBUG=false alone is insufficient. No telemetry or external
error reporter is added. Test with synthetic sentinel values, including failures
outside normal view execution. Never record a real-data browser screenshot/HAR.

Every Django connection configured for `gouda_private` sets PostgreSQL logging
options before its first query, including reconnects and host development.
Disable statement/duration/sampling/parameter logging and suppress ordinary
server error messages: PostgreSQL otherwise logs failing row DETAIL and SQL
independently of application redaction. A DB role unable to apply the protected
connection options fails to connect. This deliberately sacrifices raw private
SQL/error diagnostics; application diagnostics remain fixed route/status/codes.

## Transactions and duplicate evidence

| Phase / outcome | Durable evidence | New canonical facts |
| --- | --- | --- |
| Security, Account, upload admission denial | None from this request. | None. |
| Registration transaction | Resolve/create exact artifact and create PROCESSING attempt together. Account is re-fetched and validated first. Failure rolls back this transaction; pre-existing artifact remains. | None. |
| Sequential duplicate at registration | New DUPLICATE batch points directly to same-route materialized target. Artifact reused. Parser skipped. | None. |
| Parse and boundary validation | Run outside transactions/locks. Fatal failure is recorded in a fresh transaction as FATAL with safe stage/code, zero counts and null reconciliation. Artifact/attempt survive. | None. |
| Materialization transaction | Lock Account then ImportBatch; recheck context and materialized artifact/Account target. Persist all RawRecords, reconciliation, counts and terminal status atomically. | Exactly one per PARSED row, all committed together. No observations/resolutions. |
| Concurrent duplicate found under lock | Losing attempt becomes DUPLICATE, zero counts, no RawRecords; target is the winning materialized attempt. | None for loser. DB uniqueness is additional defense. |
| Materialization failure | Entire raw/Movement/final-state transaction rolls back; separate compensation records FATAL. Earlier registration survives. | No partial graph from the failed transaction. |
| Compensation fails / process dies before commit | Artifact and possibly PROCESSING attempt survive; never invent a final status. Stale-attempt cleanup stays deferred. | No partial graph; a lost commit acknowledgement can leave a complete graph. |
| Response projection/serialization/network failure after commit | Completed evidence is retained. Do not delete it or mark it FATAL from HTTP. | Complete graph may already exist; report uncertain outcome. |

ACCEPTED/PARTIAL/REJECTED are materialized statuses, determined only by parsed
and rejected counts. NOT_RECONCILED is a recorded arithmetic mismatch, not a
transaction failure. PARTIAL intentionally retains rejected rows plus the full
valid subset. Neither permits half of the intended canonical graph to commit
because an insertion failed. Do not change these semantics to an all-rows or
reconciled-only policy.

Exact bytes share one artifact globally. Materialized uniqueness is
`(source_artifact, account)` across routes and parser versions, not the filename
or financial values. Duplicate detection occurs before parsing when a target
already exists and again after parsing under the Account lock for races. Each
duplicate retains its own attempt and direct target reference, zero counts,
null reconciliation, no copied RawRecords/Movements. Original summaries are
read from the target, never fabricated on the duplicate batch.

FATAL/PROCESSING attempts do not block a subsequent explicit retry. Materialized
REJECTED and PARTIAL results do block reinterpretation of the same bytes into
that Account, including with another parser version; reprocessing is deferred.
Different Account selection intentionally permits another graph in the current
service. Changed-byte exports and overlapping statements are not economic-event
duplicates under this contract. State this limit before import; do not add a
second dedupe engine, date/amount collision heuristic, or global digest denial.

After a timeout, invalid response, or 5xx, React says the outcome is uncertain
and must not retry automatically or claim zero writes. Offer the existing
Account/date report and an explicit retry of the same original file/Account.
That retry is safe for exact-file canonical duplication and returns the known
original result if already committed. It creates an attempt, not exactly-once
delivery. Refreshing a report alone cannot prove an import failed.

## Private operator acceptance after implementation

The first controlled run of this procedure completed on 2026-09-10 after the
implementation review was accepted. Its sanitized outcome is recorded in the
[adversarial review](../development/local-import-adversarial-review.md#private-acceptance-result).
Retain these steps for later controlled runs: first pass all committed
regression/adversarial tests with synthetic fixtures, then validate locally
with one original private statement.

1. Start the separate ADR-0013 private stack with `make private`
   command (explicit import opt-in, DEBUG=false). Verify resolved
   project/database/volume names, migrations and
   numeric-loopback publication without printing secrets. Stop the demo to free
   port 5173. Never attach, migrate, fake, reset, or repair the historical default
   volume as part of this flow. Private start/stop commands must preserve data.
2. Through the existing local Django shell/model facilities, deliberately create
   or select a persisted non-demo CURRENT/ASSET Account with the operator-known
   currency and a non-identifying display name. Validate before saving; do not
   infer this configuration from the statement or create a bank binding. This
   is one-time setup, not a seed fixture or browser Account API.
3. Keep the original in its existing external private directory (or already
   ignored private corpus). Check ignored/untracked status locally without
   printing private paths into retained reports. Do not copy into repository
   source, test fixtures, frontend, Docker build context, or static directories;
   no private-directory mount is needed. Do not resave or export it for upload.
4. Locally inspect the original row count, primary movement candidates, amounts,
   dates and descriptions. If using the existing pure parser for comparison,
   keep values in memory and record only boolean comparison outcomes in retained
   notes. Separately compare source content to canonical values so comparing two
   calls to the same parser is not the sole correctness check.
5. Select the intended Account/file in the browser and Import. Compare parser
   source rows (including ignored metadata), parsed/rejected/ignored counts,
   reconciliation, and the batch-specific canonical count through private local
   DB inspection. Verify exact amounts, currency, resolved dates and deterministic
   descriptions by RawRecord ordinal; report order instead uses date/UUID.
   No real values, UUIDs, period, basename, digest, or row-level source details
   enter committed docs/tests/fixtures, screenshots, logs, prompts, or external
   services. Retain aggregate counts only when they are explicitly approved as
   sanitized acceptance evidence.
6. Use View movements. Verify selected Account/period, every canonical item,
   exact signed account effect, count and backend total. No source metadata or
   inferred category appears; new Movements show Unclassified. If the Account
   already has data, compare the batch graph separately from the whole-period
   report. A deliberately empty Account makes this comparison simplest.
7. Upload the same untouched file to the same Account again, optionally with a
   different upload basename without modifying bytes. Expect DUPLICATE, zero
   new Movements, unchanged original IDs/values, one SourceArtifact, a second
   attempt, and the original summary. Restart and repeat to verify DB persistence
   and expired old capability; new bootstrap requires another explicit action.
8. Check local logs/error surfaces without copying their private contents into
   reports. Confirm no private upload temp/static file or tracked artifact was
   created. Use `make private-down` to stop while preserving the
   volume. Verify demo cleanup
   targets only demo resources using metadata/tests; do not destructively test
   cleanup against real evidence. Retain only a sanitized pass/fail outcome.

## Required implementation review

The design self-review found four traps and addressed them: classification's
outer transaction would destroy importer semantics; source kind/Account identity
cannot be inferred from names; demo volume reset is broader than `clear_demo`;
compressed upload size does not bound openpyxl allocation. No production defect
was repaired here. The new admission, logging, dataset, and authority controls
are implementation requirements, not claims about the current read-only app.

| Falsification attempt | Required result / residual limit |
| --- | --- |
| Classification token in import header or import token in classification header; forged grant | Reject independently, including when both modes are enabled. No implicit cross-activation. |
| Valid UUID/read principal without import grant | Reject before persistence. Read resolver is only a visibility constraint; inaccessible selectors remain indistinguishable. |
| Browser asserts source/version/currency or renames PDF/BCI file | Reject fields/media/structure. Only the fixed server adapter can recognize v1; identical-looking forged banking layouts cannot be authenticated by this contract. |
| Same bytes twice or concurrently | Existing pre-parse/locked duplicate path, one materialized graph per Account. Test HTTP retry and underlying real PostgreSQL races. |
| Invalid workbook, row rejection, DB insertion failure | Distinct admission/FATAL/PARTIAL semantics above; fault-inject after raw creation, Movement creation and finalization to prove complete graph rollback. |
| ZIP bomb, sparse far cell/merge, XML entity or oversized multipart | Reject before workbook allocation/registration; prove actual memory-only bounded reads, no temp files, and one-slot cleanup. |
| Private filename/digest/cell/exception leaks | Synthetic sentinels absent from HTTP errors, logs, proxy/client diagnostics and exception reports, including unknown failures. |
| Restart retains token/grant | Both old objects and headers rejected; persisted import graph survives. Bootstrap produces independent fresh randomness. |
| Foreign Origin, duplicate Host, simple form, preflight, DNS rebinding | Reject in actual Django request path through Vite and direct backend, independent of CORS/private-network browser behavior. |
| Generic read client gains writes | Default launch has no import capability; reads disclose none. Explicit native-client bootstrap is possible inside trusted-host perimeter, as acknowledged. |
| Demo reads private files or reset deletes imported facts | No directory discovery/mounts; private DB/volume is separate, default demo has imports disabled, fixed demo Accounts denied. Test resolved mounts and literal reset targets. |
| Response fails after successful commit | Preserve completed graph, safe uncertain-outcome message, no automatic replay; explicit exact-file retry converges to duplicate. |
| TDC/BCI requires a replacement framework | Add separately authorized narrow routes/adapters later. Preserve TDC binding and BCI lifecycle; do not route them through Santander XLSX or grant access now. |

The implementation review completed the focused HTTP/bootstrap/authorization,
resource/admission, Santander service/concurrency/reporting,
private-vs-demo Compose, browser, restart, retry, framing, logging, and UI
checks before the first private operator acceptance above. Repeat the applicable
checks before later changes or controlled runs. Unimplemented protections must
never be reported as passing runtime tests.
