# MVP scope

## In scope

- Import account movements from a documented, deterministic input format.
- Normalize dates, amounts, descriptions, accounts, and source identifiers.
- Store accepted movements with canonical signed amounts and source provenance.
- Explicitly assign zero or one topic category to each accepted Movement.
  Unclassified is valid and distinct from an intentional category.
- Query movements by account and date range; later extend this with current
  category and unclassified filtering under the frozen classification design.
- Show period totals and a trace from totals to underlying movements.
- Reject malformed or ambiguous records without silently changing their meaning.

The implemented deterministic Santander routes may validate and materialize
movements atomically under their frozen contracts. The implemented
observation/resolution boundary does not authorize
probabilistic canonical writes.

Classification semantics and persistence are frozen in
[Movement classification](../architecture/movement-classification.md) and
[ADR-0011](../decisions/ADR-0011-movement-classification.md); implementation is
deferred. Category assignments are mutable organizational metadata separate
from canonical financial facts. They support current grouping, not historical
assignment replay. Signs and bank categories never determine Gouda categories.
This replaces the earlier unqualified MVP type list: income, expense,
transfer, refund, fee, and adjustment remain economic meanings requiring a
separate event/relationship design. Category totals are signed account effects,
not consolidated income or spending. The product vision remains broader than
this first classification slice.

## Out of scope

- Automated bank credential handling.
- Investment performance and tax reporting.
- Predictive budgeting or financial advice.
- Multi-user sharing and collaborative editing.
- Persisted economic-event types, transfer pairing, and consolidated
  income/expense reporting.
- Classification rules/AI, bulk edits, category hierarchy/tags, free-form
  notes, and assignment history or as-of classification reports.
- Irreversible deletion of source records.
- AI interpretation or agent execution.
- BCI Current/Recent ingestion lifecycles or provisional product views; the
  bounded BCI Historical evidence/resolution route is already implemented.
- Generic provider, plugin, workflow, or document frameworks.
