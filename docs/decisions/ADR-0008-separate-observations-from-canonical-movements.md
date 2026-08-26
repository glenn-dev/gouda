# ADR-0008: Separate observations from canonical movements

- Status: Accepted
- Date: 2026-08-25

## Context

Gouda currently supports synchronous deterministic Santander current-account
XLSX and credit-card PDF imports. Their frozen source contracts validate
source evidence and atomically create canonical movements.

Future inputs may be provisional, overlapping, unstructured, or interpreted
probabilistically. A current bank view, final statement, email, message,
screenshot, receipt, and connector payload may provide several pieces of
evidence for one economic event. Treating each successfully extracted value as
a movement would double count events and allow uncertain interpretation to
become accounting truth.

The current `Movement` model is deliberately source-neutral. Adding ingestion
confidence or parser state to it would weaken that boundary.

## Decision

### Canonical Movement

`Movement` remains canonical financial truth accepted by Gouda. Confidence,
provisional status, parser method, AI model, and source authority do not belong
on `Movement`.

Canonical signed-amount semantics established by
[ADR-0005](ADR-0005-canonical-movement-sign-orientation.md) remain unchanged.

### Observation boundary

Future unresolved or provisional interpreted evidence lives before
`Movement`, behind a conceptual Financial Observation Candidate boundary. An
observation may propose financial fields and link to source evidence, but it
is not canonical truth.

`FinancialObservation` is a conceptual name in this decision. This ADR does
not define a Django model, final fields, cardinalities, or database lifecycle.

### Multiple evidence and resolution

Multiple pieces of evidence may support one canonical movement. A resolution
boundary must be able to leave an observation unresolved, reject it, confirm a
new movement, match it as support for an existing movement, or retain an
auditable supersession or correction.

Resolution decisions and their supporting evidence must remain explainable.
Authority is contextual; this decision does not introduce a universal numeric
authority or confidence score.

### AI participation

AI and agents may propose artifact routes, interpreted observations, matches,
anomaly explanations, and adapter changes. Their output is untrusted
structured input.

Deterministic code validates money, currency, sign, account compatibility,
identity, lifecycle transitions, transactionality, concurrency, and canonical
write rules. AI cannot bypass those invariants or write directly to the
canonical ledger.

### Existing Santander compatibility

The current deterministic Santander routes remain valid. Their application
services may continue to interpret, resolve, and materialize atomically
because their current contracts and boundary validation are authoritative
enough for that path.

This compatibility is source-specific. It does not make `PARSED` a universal
authorization for future sources to create movements.

### Deferred implementation

The concrete Observation and Resolution persistence schema is deferred to the
next implementation design checkpoint. That checkpoint must seek the smallest
change compatible with existing imports and must not introduce a generic
plugin framework, workflow engine, event-sourced ledger, universal document
schema, or universal confidence model.

## Consequences

- Gouda can present provisional information without treating it as canonical.
- Several artifacts can eventually explain one financial fact.
- Canonical movement queries remain independent of parser and model mechanics.
- Resolution history becomes an explicit future audit responsibility.
- The existing one-raw-record-to-one-movement implementation will require a
  small compatible boundary extension before multi-source provisional imports.
- New ingestion paths must abstain when deterministic validation or resolution
  cannot establish a safe canonical result.

## Rejected alternatives

- Add confidence and provisional fields to `Movement`: this mixes evidence
  lifecycle with canonical truth.
- Create a movement for every interpreted artifact and deduplicate later: this
  makes authoritative totals temporarily or permanently wrong.
- Use one universal authority score: authority varies by source, field,
  product, period state, and purpose.
- Let AI decide canonical writes directly: probabilistic interpretation cannot
  replace deterministic financial invariants.
- Build a generic ingestion framework now: current evidence supports a small
  observation/resolution boundary, not a universal framework.
