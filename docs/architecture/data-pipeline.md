# Data pipeline

```text
source -> ingest batch -> raw/source records -> normalize source-native meaning -> validate -> canonical movements -> classify/relate -> summaries
```

Each stage should be deterministic and idempotent for the same source record
and normalization version. In v0.1, the database permits at most one
materialized interpretation for a source artifact and account; parser-version
reprocessing and supersession are deferred to an explicit later design.

Source-native direction/effect belongs to the raw/source boundary. The
normalization boundary converts it into one canonical `Movement.signed_amount`
using the referenced account's economic orientation. Classification and
transfer/counterparty relationships are later semantic layers; neither is
encoded by the sign alone.

The persistence schema rejects invalid materialized batch/count combinations.
Exact monetary representability and cross-row duplicate identity remain
application-boundary checks for the future import service.

## Failure handling

Invalid records are quarantined with a stable error code and human-readable detail. A partial import reports accepted, rejected, duplicate, and pending counts separately.

## Reprocessing

Normalization changes must be versioned. Reprocessing creates a new derived representation or migration, preserving the original source record and prior audit information.

## Observability

Import batches should expose duration, record counts, rejection reasons, and normalization version. Logs must use internal batch and record identifiers rather than raw descriptions or account numbers.
