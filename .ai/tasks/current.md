# Current task

## Objective

Freeze the deterministic design, source contract, and synthetic test plan for
BCI historical current-account PDFs before implementing an adapter.

## Completed scope

- Re-verified two private historical PDFs structurally without copying private
  financial or identity values into tracked files.
- Defined fail-closed native-text recognition, metadata and row semantics,
  exact money/date rules, and independent reconciliation checks.
- Defined unresolved observation creation and a conservative Historical-only
  resolution policy without cross-source matching.
- Defined privacy-safe synthetic fixtures and application, persistence,
  concurrency, failure, and regression test requirements.

## Constraints preserved

- No production BCI parser, adapter, model, migration, or fixture was
  implemented.
- No AI, workflow, generic ingestion framework, or fuzzy matching was added.
- No canonical Movement correction or retraction was implemented.
- Existing deterministic Santander production services and historical values
  remain unchanged.
- `Movement` remains canonical-only and `Movement.raw_record` remains its
  required one-to-one originating record.

## Validation

Markdown relative links, private-data leakage checks, and diff hygiene are the
completion gates for this documentation-only checkpoint.

## Next action

Implement the BCI Historical v0.1 extraction/parser, narrow evidence
persistence, observation creation, reconciliation gating, and synthetic tests
exactly as defined in
`docs/contracts/bci-historical-current-account-pdf-v0.1.md`. Keep Recent and
Current out of scope and leave Santander production behavior unchanged.
