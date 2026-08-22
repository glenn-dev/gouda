# Domain model

## Core entities

### Account

An account has an internal identifier, a display name, an account kind, a currency, and optional external identifiers. External identifiers must be treated as sensitive.

### Source record

A source record stores the original provider payload or a safely normalized equivalent, its import batch, source identifier, and ingestion timestamp. It supports deduplication and auditability.

### Movement

A movement references an account and source record and contains:

- occurrence date and optional posting date;
- signed amount and currency;
- description and normalized merchant text;
- movement type and optional category;
- provenance and reconciliation status.

### Import batch

An import batch groups one ingestion attempt, its source, validation results, and processing status. Failed records remain inspectable without becoming valid movements.

## Invariants

- A movement has exactly one canonical signed amount.
- A transfer has an explicit relationship between its source and destination movements when both sides are known.
- Source records are never silently overwritten by normalization.
- Monetary arithmetic uses exact decimal semantics, not binary floating point.
