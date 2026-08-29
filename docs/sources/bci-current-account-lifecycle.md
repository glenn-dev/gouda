# BCI current-account source lifecycle

## Purpose and scope

This note records sanitized observations from a read-only comparison of BCI
current-account source variants. It contains no private filenames, account
identifiers, descriptions, references, amounts, or balances.

The observations motivate Gouda's evidence and resolution architecture. The
Historical source now has a narrow deterministic design contract in
[the BCI historical PDF contract](../contracts/bci-historical-current-account-pdf-v0.1.md).
This lifecycle note still does not freeze a permanent multi-source strategy or
transaction identity algorithm.

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

The two inspected historical statements use one native-text, three-page US
Letter layout family. Page one contains statement and account context plus the
transaction table, continuation pages repeat the table header, and the final
page contains opening balance, debit and credit totals, and closing accounting
balance. Every observed row-to-row and statement-summary equation reconciled
exactly.

The two printed periods share a boundary date rather than using disjoint
next-day boundaries. Their observed transaction-date sets do not overlap.
This is period-label evidence only and must not be interpreted as transaction
identity or a permanent continuity rule.

## Overlap and identity

- The current source variants overlap.
- Descriptions are not stable across variants.
- No universal transaction identifier has been proven across the lifecycle.
- Naively importing every source into the canonical ledger would duplicate
  economic movements.
- The expected Current Cartola to Historical Cartola rollover has not yet been
  observed with direct overlapping transactions in the available corpus.
- Historical document/reference values may be blank or repeated, and an
  observed statement contains repeated date-and-amount combinations. Neither
  is a safe identity key.

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
