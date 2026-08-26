# Current task

## Objective

Establish the documentation-only AI-native, evidence-first ingestion
architecture and correct stale repository guidance.

## Completed scope

- Added the ten stable ingestion and evidence product principles.
- Added the accepted artifact-to-observation-to-resolution-to-movement target
  architecture without defining a Django schema.
- Added deterministic testing and future AI-eval requirements.
- Accepted ADR-0008, keeping canonical movements separate from interpreted
  observations.
- Added sanitized BCI current-account lifecycle observations without freezing
  a parser contract or permanent source strategy.
- Updated README, agent guidance, product, architecture, glossary, and security
  documentation consistently.
- Condensed `.ai/` into operational pointers to canonical documentation.

## Constraints preserved

- No production code, model, migration, test, parser, or fixture changed.
- No Observation/Resolution persistence was implemented.
- No AI, agent, BCI parser, workflow, or generic ingestion framework was
  implemented.
- Existing deterministic Santander application-service behavior remains valid.
- `Movement` remains canonical-only and source-neutral.

## Validation

Relative Markdown links and required file/ADR references were checked. Stale
and adversarial terminology was reviewed, new files were checked for trailing
whitespace, `git diff --check` passed, and the repository diff contains only
documentation, `AGENTS.md`, and `.ai/` operational files.

## Next action

Design the smallest Observation/Resolution persistence and application-service
boundary required before BCI multi-source canonical ingestion. Freeze
responsibilities and lifecycle invariants before fields or migrations. Do not
implement AI or a generic framework in that checkpoint.
