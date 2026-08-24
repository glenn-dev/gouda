# ADR-0001: Represent account movements with signed amounts

- Status: Accepted — generalized by [ADR-0005](ADR-0005-canonical-movement-sign-orientation.md)
- Date: 2026-08-02

## Context

Financial sources commonly represent debits and credits differently. Downstream totals become error-prone when direction is inferred repeatedly or encoded only in a separate field.

## Decision

The canonical movement model stores one signed amount: positive means money enters the referenced account; negative means money leaves it. The original source direction is retained in provenance when available.

This decision remains the historical and current-account interpretation. Its
universal application across account products is generalized by
[ADR-0005](ADR-0005-canonical-movement-sign-orientation.md), which defines the
canonical sign through the referenced account's contribution to household net
worth and introduces explicit asset/liability orientation.

## Consequences

Summaries can use ordinary addition, and the sign convention is easy to test. Importers must translate provider-specific conventions carefully. Transfers require pairing or relationship metadata so they can be excluded from consolidated flow totals.

## Rejected alternatives

- Storing only an unsigned amount and debit/credit flag: simpler at ingestion, but direction must be reassembled everywhere.
- Storing separate inflow and outflow columns: convenient for reports, but duplicates the canonical fact and permits contradictory values.
