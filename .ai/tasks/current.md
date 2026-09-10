# Current task

## Objective

Implement ADR-0013's first local browser-import vertical slice for Santander
Current Account XLSX only, preserving the existing import lifecycle and Movement
report.

## Baseline and commit contract

Started 2026-09-09 from clean `main` with HEAD and fetched `origin/main` both
`bbca93e54e93dfa94fb7a37623820088b56fbe44`, the signed
`docs: define local financial import flow` commit. Create one signed
`feat: add local Santander import flow` commit after clean validation. Do not
push.

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

Implementation and adversarial review are complete with no ADR-0013 deviation.
All 554 Django tests on PostgreSQL and all 72 frontend tests pass, as do
typecheck, build, dependency, migration, Compose, demo, documentation, privacy,
and whitespace checks. A generated Santander workbook passed same-origin import,
Movement reporting, restart persistence, and exact duplicate validation. No
private financial artifact was read.

The next action after review is Glenn's one-file private acceptance procedure in
`docs/architecture/local-financial-import.md`, retaining only sanitized pass/fail
notes. Classification editing, other providers/sources, overlapping-export
identity, retention/export/deletion tooling, and remote/authenticated delivery
remain deliberately deferred.
