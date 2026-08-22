# Data pipeline

```text
source -> ingest batch -> raw/source records -> normalize -> validate -> canonical movements -> summaries
```

Each stage should be deterministic and idempotent for the same source record and normalization version.

## Failure handling

Invalid records are quarantined with a stable error code and human-readable detail. A partial import reports accepted, rejected, duplicate, and pending counts separately.

## Reprocessing

Normalization changes must be versioned. Reprocessing creates a new derived representation or migration, preserving the original source record and prior audit information.

## Observability

Import batches should expose duration, record counts, rejection reasons, and normalization version. Logs must use internal batch and record identifiers rather than raw descriptions or account numbers.
