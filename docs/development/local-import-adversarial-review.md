# Local Santander import adversarial review

Reviewed 2026-09-10. Original commit: `7bc34f645f3ca291b12d7b70494bfa8761167037`;
parent: `bbca93e54e93dfa94fb7a37623820088b56fbe44`. Only committed/generated
synthetic workbooks and isolated synthetic databases were used. No private file
was read and no push was performed. The containing amended commit supplies the
final SHA and signature.

## Decision

The original commit was **not ready** for a private import. The corrections in
this amended checkpoint resolve three BLOCK findings and four IMPORTANT
findings. After the recorded checks, **YES** to one controlled import of an
untouched, supported private Santander Current Account XLSX through the
documented private stack, with deliberate operator Account/currency selection.
This is readiness for the private acceptance procedure, not a claim that an
unseen statement has already passed it.

## Private acceptance result

On 2026-09-10, after the corrected review above, Gouda completed its first
controlled private real-data acceptance. One real Santander Current Account
XLSX was imported through the intended private local workflow. The import
processed 36 source rows, created 7 canonical Movements, ignored 29 rows,
rejected 0 rows, and reconciled successfully. The operator manually compared
all 7 resulting Movements with the private source and confirmed that the
relevant dates, descriptions, canonical signed amounts, and complete movement
set matched.

Uploading the same untouched file to the same Account was recognized as an
exact duplicate. The retry created 0 new canonical Movements and returned the
original bounded import summary. After the private stack was stopped and
restarted, the Account and imported Movements remained persisted and readable
through the existing Movement report.

This acceptance demonstrates real Santander Current Account XLSX ingestion,
canonical Movement materialization for the accepted statement, reconciliation,
exact-file/same-Account duplicate convergence, private-stack restart
persistence, and operator comparison with the private source. It does not
demonstrate semantic deduplication of overlapping statements; deduplication of
changed or re-exported statements; strong persisted Santander provider or
account-number identity binding; Santander credit-card or BCI browser import;
other institutions or source contracts; production or remote-deployment
security; or correctness for arbitrary future Santander statement variants.

Only the approved aggregate counts and pass/fail outcomes above are retained
as evidence. No filename, account or personal identifier, source-derived value,
private artifact, or screenshot is recorded in Git.

## BLOCK findings, corrected

1. **Unbounded server cleanup.** Django 4.2's `ServerHandler.close()` calls an
   unbounded read of the remaining Content-Length after the view finishes.
   Application size limits and the upload slot did not cover this allocation.
   The supported launcher now uses a WSGI handler that sends Connection: close
   and never drains unread bodies. The regression sends an oversized declared
   body without transmitting it and verifies immediate rejection/connection
   closure. It timed out on the original handler. Orderly server exit waits
   for request threads before runtime revocation.
2. **OOXML allocation bypasses.** Six sheet declarations referring to one
   physical worksheet passed the four-sheet limit; a hyperlink range allocated
   row 10001 despite the row bound. A relationship could point to XML stored
   under an uninspected extension. Namespace expansion and repeated shared
   strings/number formats could multiply memory and evidence text beyond the
   physical ZIP budgets. Six new resource regressions fail against the original
   committed admission module. Admission now validates workbook references,
   expanded ranges, supported relationship loaders, XML name expansion before
   tree allocation, and text use across cells. Unsupported forms are rejected;
   admitted bytes are never rewritten.
3. **PostgreSQL log disclosure.** An actual synthetic constraint failure
   recorded the failing row and INSERT text in the database container log.
   Django's filter cannot sanitize this independent logger. Private Django
   connections now disable raw SQL/duration/sampling/parameter diagnostics and
   suppress ordinary server error logging before any query. A live failure and
   reconnect check confirms the corrected synthetic sentinel is absent from
   server logs. This trades raw database diagnostics for the ADR's privacy rule.

## IMPORTANT findings, corrected

1. **Ambiguous framing:** wsgiref silently selected the first duplicate
   Content-Length, and bootstrap lacked upload's transfer-encoding checks.
   Direct raw HTTP returned a capability for duplicate lengths. The launcher
   now preserves duplicate length/type values, and both financial routes
   validate framing before reading. Vite's duplicate-header handling remains
   independently enforced.
2. **Fetch confinement:** bootstrap and upload omitted ADR-0013's explicit
   `mode: "same-origin"`. Both now set it, with regression assertions, alongside
   omitted credentials, no-store caching and redirect rejection.
3. **False clean completion:** ACCEPTED + NOT_RECONCILED or INSUFFICIENT_DATA
   displayed “Import complete”. These outcomes now use a reconciliation-review
   heading. PARTIAL/REJECTED/DUPLICATE remain distinct. Two UI regressions
   failed before correction.
4. **Report-selection race:** import result/recovery actions could change the
   selected Account/period while another report request was pending, allowing
   a late response to be displayed under another selection. Those actions now
   respect the existing report loading lock; the regression failed before fix.

## MINOR findings, deferred

- View movements is still enabled for an effective result with zero Movements,
  and its whole-Account-period scope is not stated beside the button. The
  returned report itself is the existing Account/date report, not batch-filtered.
- Empty import Account discovery lacks the design's local-operator-setup help.
- The base development container does not mount `docker-compose.private.yml`,
  although its static Compose test reads that file. The tests run on the host;
  this is a container test-reproducibility omission, not runtime isolation.

These UI/test ergonomics do not block controlled acceptance; defer to a small
follow-up. They remain minor differences from the detailed flow document.

## Authority and startup

Principal validation recognizes the module singleton by identity. Financial
grant validation recognizes only the live financial runtime's exact grant.
Constructing another grant/context instance does not confer authority. The
classification runtime owns an independent random secret and independent grant
identity; cross-token and cross-grant tests fail closed in both directions.
There is no general financial-write grant validator or generic write route.
Future routes would require an explicit implementation decision, not automatic
authorization from today's grant.

Startup requires the explicit pair of financial flags, DEBUG=false,
`gouda_private`, and the exact host/container topology. Argparse rejects
abbreviations and repeats. No request value or environment-configured capability
constructs trusted state. Generic runserver/WSGI/ASGI cannot activate it.
Runtime exit clears secret/grant references; restart rejects old tokens and
objects. The source operation revalidates principal and live grant after
admission, before calling the importer once without an outer transaction.

Account visibility is necessary but insufficient. Persisted CURRENT/ASSET/
currency compatibility and fixed demo-ID exclusion precede admission; the
importer re-fetches Account and checks context under its materialization lock.
Demo IDs matter because synthetic cleanup/reset targets that dataset. Request
currency/source/version/identity fields cannot bypass these checks.

**Accepted binding limitation:** the operator knows the selected Account and
currency. Gouda has no persisted Santander provider/account-number binding,
and structural recognition does not authenticate bank identity. Trusted local
processes can forge Host/Origin and deliberately bootstrap. DevTools, privileged
extensions, compromised same-origin code and OS memory inspection are accepted
trusted-host access, not prevented disclosure claims.

## Transport, resources and privacy

Exact Host/Origin checks are independent of CORS. Live Vite and direct WSGI
checks reject absent/null/foreign/alternative/combined Origins, duplicate Host
and Origin, and forwarded Host substitution. Methods and simple-form media fail
before import. Vite preserves duplicate capability multiplicity; Node rejects
ambiguous framing or the application rejects its combined value. A raw local
client using the accepted pair can bootstrap as documented.

The supported WSGI path reads the bounded raw stream directly, never Django
POST/FILES/upload handlers. It does not spool uploads. ASGI's framework body
spooling exists but is outside the supported runtime and cannot enable import;
this review does not claim a generic ASGI no-tempfile guarantee. Missing/false
length and chunked framing cannot become an admitted unbounded upload.
Multipart parsing rejects extra/duplicate parts, unsupported headers/media,
missing content and malformed boundaries before evidence registration.

ZIP declared and actual expansion, CRC, methods, encryption, duplicate/unsafe
names, all inspected XML, hidden worksheets, references and rectangular extents
are bounded. DTD/entities/external resources are disabled. Ancillary object,
image, comment, pivot and chartsheet loaders are deliberately unsupported.
The five-MiB file limit is not a five-MiB RSS ceiling: bounded copies, ZIP
metadata and parser objects consume additional memory. No hard process-wide
memory quota or protection from unlimited trusted-local connections is claimed.

Filename normalization is metadata-only; no path is opened or derived for
storage. Exact bytes and the first normalized basename live in SourceArtifact
in PostgreSQL. Live checks compare retained bytes with the committed fixture.
The capability stays in process/module memory, enters only its header, and is
returned only by bootstrap. No cookie, URL, DOM token, browser storage, logging
or shared fetch default carries it. Application/exception/proxy logs and
responses omit filename, digest, private row values, SQL and capability.
Database files/WAL/backups remain private retained evidence, not secure erasure.

## Atomicity, duplicate and outcome review

Registration creates artifact and attempt in one transaction; injected failure
after attempt creation rolls both back. Parse/graph validation run outside the
materialization transaction. Parser/FATAL evidence may survive independently.
Account then batch locking precedes full RawRecord/Movement/reconciliation
materialization. Failure after second raw insertion, second Movement insertion,
or completed final-state save leaves no partial graph; separate compensation
retains a FATAL attempt. Existing compensation-failure tests preserve PROCESSING
evidence without fabricating completion. Connection loss at commit can leave a
complete graph with an ambiguous acknowledgement, never half a transaction.

Projection is after commit. Injected projection failure returns sanitized 500
while retaining the complete graph; explicit exact-file retry reports DUPLICATE
and leaves original Movement values unchanged. Same bytes/same Account share
one artifact and retain a second attempt with zero new Movements. Existing
PostgreSQL tests demonstrate concurrent parsing followed by actual Account lock
contention and canonical convergence. At the HTTP boundary the process slot
admits one upload and returns 429 to an overlapping upload; its later explicit
retry is DUPLICATE. Changed exports/overlap deduplication is not promised.

Result counts project completed lifecycle counts and duplicates reference their
validated direct target. Period navigation uses strict server ISO dates and
inclusive occurrence-date reporting without timezone conversion. PARTIAL means
the complete valid subset committed; reconciliation is independently reported.
Transport failure, unreadable success or 5xx is uncertain in React. No financial
request is automatically replayed; expired capability is cleared, and a fresh
explicit action is required. Reacquisition alone never resubmits a File.

## Isolation and validation

Resolved Compose configs resist tested inherited POSTGRES_DB,
COMPOSE_PROJECT_NAME, COMPOSE_FILE and command-variable overrides. Private mode
uses the private DB/mount, no seed or incoming/private host directory; demo has
no import activation. Reset names only the literal demo volume, private-down
preserves private data, and PostgreSQL is unpublished without the explicit host
override. The DB name is an accidental-dataset guard, not volume attestation
against a Docker-privileged operator. No schema/model/parser/sign/classification
semantics changed; migration drift reports no changes.

Validation comprises 158 focused Django import/runtime/transport/classification
tests, 72 additional parser/report/runtime tests, all 75 frontend tests, typecheck
and build, production-container admission tests, live PostgreSQL log/reconnect
checks, resolved Compose/Make checks, and a freshly built isolated Compose stack.
The live stack passed synthetic import, retained-byte comparison, report,
backend restart, expired-token denial, exact duplicate and secret-free logs.
The expensive entire backend suite was not repeated merely for ceremony.
Individual failing baseline regressions were observed before their fixes.

The isolated review stack is stopped with its synthetic named volume preserved.
The standalone disposable synthetic test database container was stopped and
automatically removed; its synthetic database is no longer retained. The demo
frontend was restored, and all three demo services are healthy. No existing
user database or volume was deleted.

The original SHA was already at fetched origin/main when this review began;
historical handoff statements saying “nothing pushed” were stale. The amendment
therefore creates local divergence from that remote commit. No push or remote
history rewrite is part of this review.
