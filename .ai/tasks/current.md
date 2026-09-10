# Current task

## Objective

Complete independent adversarial review and narrow correction of signed
`7bc34f6`, preserving the existing Santander import lifecycle and Movement report.

## Baseline and commit contract

Reviewed 2026-09-10 from clean `main` at signed `7bc34f6`, parent `bbca93e5`.
Fetched origin/main already contained the original implementation commit,
contrary to older handoff notes. Amend that commit, keep it signed, and do not
push. The amendment creates local divergence from origin/main.

## Implemented scope

- Separate default-off, process-memory financial-import runtime/capability/grant.
- Strict JSON bootstrap and Account-scoped multipart Santander XLSX endpoint.
- Principal, read visibility, demo exclusion, and CURRENT/ASSET/currency checks
  before upload parsing.
- Five-MiB upload and bounded ZIP/XML/worksheet admission before openpyxl.
- Existing importer reuse, safe fatal mapping, duplicate summary, and redaction.
- Fixed private Compose project/database/volume with no seed, reset, or incoming
  directory mount; unchanged import-disabled demo.
- Minimal React Account/file/import/result/report flow with no automatic retry
  after an ambiguous request.

No source contract, model, migration, signed-amount semantics, reconciliation,
classification, observation, transfer, taxonomy, auth, or remote-access behavior
was changed.

## Checkpoint result

Independent review corrected three BLOCK issues: unbounded Django unread-body
cleanup, OOXML allocation bypasses and PostgreSQL error/SQL log disclosure.
Four IMPORTANT issues are corrected: ambiguous framing, missing same-origin
fetch mode, unreconciled completion wording and report-selection races.
158 focused Django tests and 72 additional parser/report/runtime tests pass,
as do all 75 frontend tests, typecheck/build, production-container admission,
migration drift, hostile Compose/Make overrides, live synthetic import/report,
retained bytes, restart/exact duplicates and log/reconnect privacy checks.
The expensive complete backend suite was not repeated for ceremony.
No private financial artifact was read. Minor result-navigation/setup-help and
container-test mount omissions remain deferred; see
`docs/development/local-import-adversarial-review.md`.

The next action after review is Glenn's one-file private acceptance procedure in
`docs/architecture/local-financial-import.md`, retaining only sanitized pass/fail
notes. Classification editing, other providers/sources, overlapping-export
identity, retention/export/deletion tooling, and remote/authenticated delivery
remain deliberately deferred.
