# Domain model

## Core entities

### Account

An account has an internal identifier, a display name, an account kind, and a
currency. External bank account identifiers are deferred.

### Source artifact and source record

An artifact stores the exact received source bytes, a boundary-computed content
digest, and private receipt metadata. A source record is the immutable row
interpretation associated with an import batch.

### Movement

A movement references an account and exactly one source record and contains:

- occurrence date;
- signed amount and currency;
- optional description, source reference, and running balance;
- source-column provenance.

### Import batch

An import batch groups one ingestion attempt, its source, validation results, and processing status. Failed records remain inspectable without becoming valid movements.

## Invariants

- A movement has exactly one canonical signed amount.
- A transfer relationship is deferred; it is not inferred by this persistence slice.
- Source records are never silently overwritten by normalization.
- Monetary arithmetic uses exact decimal semantics, not binary floating point.
