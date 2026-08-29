# Current task

## Objective

Implement the smallest durable Observation/Resolution persistence and service
boundary before BCI multi-source ingestion.

## Completed scope

- Added immutable `FinancialObservation` claims with explicit creation
  idempotency and a mutable current lifecycle projection.
- Added append-only `ObservationResolution` transition history.
- Added deterministic confirm-new, match-existing, reject, conflict, reopen,
  and interpretation-supersession services.
- Added Account-scoped locking, strict support matching, candidate collision
  abstention, database constraints, and PostgreSQL concurrency coverage.
- Accepted ADR-0009 and updated canonical architecture documentation.

## Constraints preserved

- No AI, BCI parser, workflow, generic ingestion framework, or fuzzy matching
  was implemented.
- No canonical Movement correction or retraction was implemented.
- Existing deterministic Santander production services and historical values
  remain unchanged.
- `Movement` remains canonical-only and `Movement.raw_record` remains its
  required one-to-one originating record.

## Validation

The deterministic Django/PostgreSQL suite, observation concurrency tests,
migration drift, system checks, compilation, link checks, and diff hygiene are
the completion gates for this checkpoint.

## Next action

Design a concrete BCI source contract and adapter only after validating source
roles and rollover evidence. Keep Recent and Current unresolved by default;
defer canonical Movement correction until real corrected-source evidence.
