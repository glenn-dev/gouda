# Contribution guidance

## Before changing the project

1. Read `.ai/context.md` and `.ai/tasks/current.md`.
2. Check the relevant product and architecture documents.
3. Preserve the signed-movement model: money entering an account is positive and money leaving an account is negative.

## Documentation conventions

- Use Markdown and short, descriptive headings.
- Prefer domain language from `docs/product/glossary.md`.
- Keep examples synthetic; never commit real financial data, credentials, or account identifiers.
- Add or update an ADR when a decision affects persistence, integrations, security, or domain semantics.

## Change hygiene

- Keep changes focused and reviewable.
- Update `.ai/handoff.md` when handing work to another agent or session.
- Validate links and examples when editing documentation.
