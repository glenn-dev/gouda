# BCI current-account source lifecycle

## Purpose and scope

This note records sanitized observations from a read-only comparison of BCI
current-account source variants. It contains no private filenames, account
identifiers, descriptions, references, amounts, or balances.

The observations motivate Gouda's evidence and resolution architecture. They
do not freeze a BCI parser contract, permanent source strategy, transaction
identity algorithm, or persistence design.

## Observed source roles

### Recent Movements

The Recent Movements source is a rolling or recent activity view. It provides
timely transaction evidence but is not a closed-period statement.

### Current Cartola

The Current Cartola source represents an open statement period. It provides a
current accounting view before the period has closed.

### Historical Cartola

The Historical Cartola source represents a closed period and exposes strong
statement reconciliation evidence. It is the strongest observed source for
closed-period accounting authority.

## Overlap and identity

- The current source variants overlap.
- Descriptions are not stable across variants.
- No universal transaction identifier has been proven across the lifecycle.
- Naively importing every source into the canonical ledger would duplicate
  economic movements.
- The expected Current Cartola to Historical Cartola rollover has not yet been
  observed with direct overlapping transactions in the available corpus.

These facts prevent a permanent automatic identity or supersession rule from
being frozen today. Exact byte identity and source-local references do not by
themselves establish cross-variant economic identity.

## Architectural implication

Recent and open-period evidence may eventually support an explicitly
provisional view. Later closed-period evidence may confirm or supersede its
accounting interpretation while all source evidence remains auditable.

This lifecycle is a concrete reason to place interpreted observations and
resolution before canonical `Movement`. It does not authorize BCI ingestion,
select one permanent production source, or define final matching rules.

## Open questions

- Which fields, if any, remain stable across an observed current-to-historical
  rollover?
- What collision rate would candidate matching produce across periods and
  source variants?
- When can a match be resolved deterministically, and when is human review
  required?
- Which provisional product views are useful without implying closed-period
  authority?
