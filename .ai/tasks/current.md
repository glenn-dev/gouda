# Current task

## Objective

Implement the frozen BCI Historical current-account PDF v0.1 contract end to
end without changing the generic domain model.

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

- The production BCI parser, narrow evidence models, additive migrations,
  import service, Historical policy, and synthetic fixtures are implemented.
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

Complete focused and full validation, privacy review, and adversarial review.
Keep Recent and Current out of scope and leave Santander production behavior
unchanged.
