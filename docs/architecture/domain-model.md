# Domain model

## Core entities

### Account

An account has an internal identifier, a display name, a product/account kind,
an economic orientation, and a currency. Product kind and economic orientation
are separate concepts: a current account or credit card describes the product,
while `ASSET` or `LIABILITY` describes how its contribution to household net
worth changes. The supported combinations are `CURRENT` + `ASSET` and
`CREDIT_CARD` + `LIABILITY`; the database rejects other combinations until a
future schema decision expands the closed-world invariant. Existing current
accounts are backfilled as `ASSET`. External bank account identifiers are
deferred.

### Source artifact and source record

An artifact stores the exact received source bytes, a boundary-computed content
digest, and private receipt metadata. Source format belongs to the import
batch, which represents one interpretation route. A raw record is the shared
identity/outcome envelope; source-specific XLSX or Santander TDC evidence is
kept alongside it without fabricated cross-format fields.

### Movement

A movement references an account and exactly one source record and contains:

- occurrence date;
- signed amount and currency;
- optional description, source reference, and running balance;

Source-column, PDF geometry, provider category, installment, original-currency,
and provider-native amount evidence do not belong to `Movement`.

`signed_amount` is canonical and source-independent: positive means the
referenced account's contribution to household net worth increases; negative
means it decreases. For assets this normally matches money entering/leaving
the account. For liabilities, debt reduction is positive and debt increase is
negative. Provider-native direction remains raw/provenance data and is
converted at the source adapter boundary.

The sign does not itself classify a movement as income, expense, refund, fee,
tax, or transfer. A transfer relationship connects two account movements and
is excluded from consolidated flow reporting when paired.

### Import batch

An import batch groups one ingestion attempt, its source kind, validation
results, and processing status. Failed and ignored records remain inspectable
without becoming valid movements.

## Invariants

- A movement has exactly one canonical signed amount.
- Account orientation is an economic domain concept distinct from provider or
  product kind.
- A transfer relationship is deferred; it is not inferred by this persistence slice.
- Source records are never silently overwritten by normalization.
- Monetary arithmetic uses exact decimal semantics, not binary floating point.
