# MVP scope

## In scope

- Import account movements from a documented, deterministic input format.
- Normalize dates, amounts, descriptions, accounts, and source identifiers.
- Store accepted movements with canonical signed amounts and source provenance.
- Classify movements with a small set of explicit types: income, expense, transfer, refund, fee, and adjustment.
- Query movements by account, date range, type, and category.
- Show period totals and a trace from totals to underlying movements.
- Reject malformed or ambiguous records without silently changing their meaning.

The implemented deterministic Santander routes may validate and materialize
movements atomically under their frozen contracts. The accepted future
observation/resolution architecture does not expand this MVP or authorize
probabilistic canonical writes.

## Out of scope

- Automated bank credential handling.
- Investment performance and tax reporting.
- Predictive budgeting or financial advice.
- Multi-user sharing and collaborative editing.
- Irreversible deletion of source records.
- AI interpretation or agent execution.
- Observation/Resolution persistence or provisional product views.
- Generic provider, plugin, workflow, or document frameworks.
