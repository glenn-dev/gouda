# Current task

## Objective

Completed the architecture/design checkpoint for local financial import v0.1.
Only Santander Current Account XLSX is designed: explicit browser Account/file
selection, independent import authority, existing deterministic lifecycle,
PostgreSQL persistence, and existing Movement report/React display.
No production code, tests, migrations, runtime, or private data changed.

## Baseline and commit contract

On 2026-09-08, verified clean `main` after fetching origin. HEAD and
`origin/main` both equaled `ebb8b11c6c90d20c334455bc9ad66af4f0c3a1ab`,
`chore: simplify local demo workflow`, with a valid ED25519 SSH signature.
This checkpoint authorizes exactly one signed
`docs: define local financial import flow` commit and no push. Git history
records the resulting SHA and signature; it is not embedded in its own commit.

## Durable result

- [ADR-0013](../../docs/decisions/ADR-0013-local-financial-import-boundary.md)
  owns import authority, source/Account policy, and private dataset separation.
- [Local financial import](../../docs/architecture/local-financial-import.md)
  owns exact endpoints/errors, upload limits, evidence/transaction outcomes,
  React flow, adversarial requirements, and private operator acceptance.
- README and operational context now prioritize real-event validation before
  classification editing. ADR-0010/0011/0012 and source contracts are unchanged.

## Validation

Inspected production parser/importer, persistence, existing Santander tests,
Account access, reports, classification/runtime/HTTP/logging, React, and demo
startup/cleanup. Ran the existing parser and import-helper tests: 60 passed;
Django system check passed. No database was needed or opened for these tests.
Documentation validation passed for 43 Markdown files, 119 local links/anchors,
and 11 JSON examples. Added-text privacy, ignored/untracked private-path checks,
exact six-file scope, and diff hygiene passed. The handoff records adversarial
review. Runtime acceptance belongs to implementation.

## Next bounded scope

Await explicit implementation instruction, then implement this v0.1 contract,
including independent grants, bounded admission, safe logging, isolated private
startup, existing service reuse, and minimum React flow. Verify using synthetic
fixtures/isolated databases before Glenn's deliberate private acceptance run.
Do not import private files as part of this design checkpoint.

Classification editor follows local import validation. TDC/BCI browser imports,
account/provider identity verification, changed-export/cross-source deduplication,
reprocessing, canonical correction, transfer semantics, taxonomy, AI, background
jobs, remote access, ownership/authentication, and generic frameworks remain
deferred. Current-to-Historical BCI validation still waits for its external
artifact trigger.
