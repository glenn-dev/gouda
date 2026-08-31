# Current task

## Objective

Design the trusted account-access/authentication boundary and narrow read-only
delivery contract for the implemented canonical Movement reporting service.

## Current state

The internal reporting service accepts one trusted persisted `Account` and an
inclusive `Movement.occurrence_date` range. It returns immutable canonical
Movement items ordered by occurrence date and Movement UUID, exact Decimal net
signed account effect and count, and safe provenance identifiers plus source
kind, variant, parser, import status, and reconciliation status. It performs no
writes and avoids source filenames, bytes, digests, raw cells, references,
balances, and parser payloads.

Persisted `Movement` is the existing accepted canonical query boundary.
Unresolved, rejected, or superseded observations do not independently appear
in reports. Observation state does not filter existing Movements; canonical
Movement correction or retraction remains unimplemented.

No HTTP API, DRF dependency/configuration, authentication, authorization,
user/household ownership model, or frontend exists. ADR-0002 accepts DRF as a
technology direction but does not establish an account-access policy.

BCI Current-to-Historical validation remains an event-triggered deferred task
because BCI emits only three Historical current-account statements per year.
It does not block this system-level design work.

## Constraints

This is a design checkpoint. Do not add endpoints, authentication code,
models, migrations, writes, UI, classification, household-flow semantics,
transfers, provisional observations, BCI Current persistence, cross-source
identity/deduplication, lifecycle policy, or Movement correction.

## Next action

Review product, security, account-model, API, and deployment documentation and
propose the smallest explicit boundary that can turn authenticated caller
context into one authorized Account before invoking the reporting service.
Specify a narrow read-only request/result/error contract, privacy-safe source
trace representation, and test strategy. Identify whether the absent
user/household ownership model blocks implementation; do not invent ownership
semantics to avoid that decision.

Expected artifacts are an architecture/design note and durable state updates.
Create an ADR only if the accepted decision establishes persistent ownership,
security, integration, or domain semantics. Do not implement the delivery
surface during the design checkpoint.

Recommended reasoning level: Sol High.
