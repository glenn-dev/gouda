# BCI Current Cartola source contract v0.1

## Status

Frozen source-recognition and source-native extraction contract. This contract
does not implement a parser or authorize observation resolution or canonical
ledger writes.

The logical source variant is `bci_current_cartola_xls` and the contract
version is `bci_current_cartola_v0.1`. A future implementation parser identity
must include this source variant and contract version.

## Scope and evidence basis

This contract covers the observed BCI Current Cartola legacy XLS profile:

- one readable legacy Microsoft Excel CFB/XLS workbook;
- one visible worksheet;
- a merged title region;
- six metadata rows, one blank separator, one transaction header row, and
  a contiguous transaction region;
- five source columns;
- dates and monetary values stored as text; and
- no formulas, totals, or statement reconciliation block.

The contract is intentionally limited to this observed profile. An unobserved
container, worksheet shape, header arrangement, cell type, or source layout is
unsupported rather than best-effort parsed.

## Explicit non-goals

V0.1 does not define or claim:

- intrinsic BCI, Account, or currency proof from workbook cells;
- Current-to-Recent or Current-to-Historical identity;
- deduplication or rollover behavior;
- transaction versus accounting meaning for `Fecha`;
- canonical meaning for the sign of `Monto $`;
- universal meaning or identity behavior for `Serie`;
- reconciliation semantics for `Saldo Contable $`;
- description stability or matching;
- observation lifecycle or resolution policy;
- provisional views or canonical `Movement` creation/correction; or
- any persistence model.

Trusted source context may route an artifact to this adapter. Account and
currency remain application-boundary concerns and must not be inferred from
the filename, path, description, series, amount, or balance.

## Supported container and worksheet profile

The input is a readable legacy XLS CFB workbook. The adapter uses the pinned
`xlrd==2.0.1` boundary and does not convert or rewrite the workbook.

Exactly one visible worksheet must match the structural fingerprint. The
observed worksheet name `Sheet0` is retained as provenance but is not itself a
source-identity rule.

## Deterministic recognition fingerprint

Recognition succeeds only when all conditions below hold:

1. The input is a readable legacy XLS workbook.
2. Exactly one visible worksheet matches the profile.
3. The first row contains the observed merged title `Movimientos de su
   cuenta`.
4. Rows 2–7 contain the observed metadata labels, in order:
   `Saldo Disponible`, `Saldo Contable`, `Retenciones`, `Sobregiro
   Disponible`, `Sobregiro Utilizado`, and `Linea de Emergencia`.
5. Row 8 is the observed blank separator.
6. Row 9 contains, in order, the exact normalized headers:
   `Fecha`, `Descripción`, `Serie`, `Monto $`, and `Saldo Contable $`.
7. The transaction region has the observed five-column shape and contains no
   unsupported structural interruption.

Recognition uses normalized structural labels and layout only. It does not
use filenames, account values, descriptions, series values, amounts, or
balances.

## Structural regions and row outcomes

The adapter recognizes these regions:

| Region | Rows | Outcome |
| --- | --- | --- |
| Title | 1 | `IGNORED` |
| Account snapshot metadata | 2–7 | `IGNORED` |
| Separator | 8 | `IGNORED` |
| Transaction header | 9 | `IGNORED` |
| Transactions | 10 through the last populated row | `PARSED` or `REJECTED` |

The source does not expose a recognized totals or reconciliation region.

## Source-native extracted fields

Each transaction row preserves:

| Field | Source cell | V0.1 semantics |
| --- | --- | --- |
| `source_date` | `Fecha` | Exact source date parsed from the source grammar. Its transaction/accounting meaning is unresolved. |
| `source_description` | `Descripción` | Source text after deterministic surrounding-whitespace normalization only. |
| `source_series` | `Serie` | Opaque source-native evidence. It is not a reference, identity key, or classification. |
| `source_signed_amount` | `Monto $` | Exact source-signed amount. Its canonical account effect is unresolved. |
| `source_balance` | `Saldo Contable $` | Exact per-row source balance. No reconciliation or closing-balance semantics are asserted. |

The adapter does not synthesize transaction dates, accounting dates, currency,
references, direction labels, or balances.

## Date grammar and ordering

The only supported date grammar is full-year `DD-MM-YYYY`. Dates must be real
Gregorian dates. No year inference, locale inference, or filename-date
substitution is allowed.

Rows are emitted in worksheet order. The observed `Fecha` sequence is
newest-to-oldest; v0.1 requires non-increasing parsed dates and allows equal
dates. A backward source-order violation is rejected. This ordering rule is a
source-shape validation, not an identity rule.

## Exact monetary grammar and Decimal behavior

The observed source grammar is:

```text
-?(?:\d+|\d{1,3}(?:\.\d{3})+)
```

It represents integer monetary units with optional dot thousands grouping.
Fractional values, decimal commas, currency symbols inside cells, malformed
grouping, and other signs are unsupported.

`Monto $` may carry a leading minus. `Saldo Contable $` may be positive, zero,
or negative. The raw source text is preserved and any parsed numeric value is
created with `Decimal`; no binary floating point or rounding is permitted.
Integer source units may be represented at Gouda's exact two-decimal boundary
as `Decimal` values without changing their value.

## Row validation

A transaction row is valid only when:

- its date cell is a text value matching the date grammar;
- its amount and balance cells are text values matching the monetary grammar;
- its date is in non-increasing source order; and
- description and series cells are text or explicitly empty source cells.

The adapter preserves source signs exactly. It does not calculate a debit,
credit, or canonical signed amount from the row.

## Ignored and rejected structures

Ignored structures are limited to the title, recognized metadata, separator,
and header regions listed above. Snapshot fields such as overdraft and
retentions are evidence-only and never become transaction rows.

Recognition or parsing rejects:

- corrupt, encrypted, or unreadable XLS input;
- multiple or missing matching worksheets;
- missing, duplicated, or reordered title/metadata/header markers;
- unsupported merged-region or row geometry;
- unsupported cell types or formulas;
- missing or malformed dates;
- dates outside the observed full-date grammar;
- non-monotonic source date order;
- malformed amount or balance text;
- unexpected populated rows or structural gaps in the transaction region; and
- any unobserved layout variant.

No partial financial interpretation is returned for a recognition-fatal
failure. A recognized row-level rejection must retain only sanitized reason
codes in any outer application result.

## Formula and cell-type handling

The observed transaction representation is all text. V0.1 accepts text cells
for source fields and rejects formulas, formula-backed values, unsupported
native numeric/date cells, and ambiguous cell types. `xlrd` is used only for
read-only decoding.

## Provenance and privacy

Every extracted field must identify:

- the immutable artifact identity supplied by the outer boundary;
- worksheet name and ordinal;
- row and column coordinates;
- original source cell type and text provenance;
- source field name; and
- contract/parser version.

Private filenames, account identifiers, descriptions, series values, amounts,
balances, and raw cells must not enter logs, public representations, tracked
fixtures, or documentation. Synthetic tests use wholly synthetic values.

## Minimum synthetic test matrix

- valid one-sheet legacy XLS profile with the exact title, metadata, separator,
  headers, and transaction region;
- newest-to-oldest dates, equal dates, invalid dates, and order violations;
- positive and negative source amounts;
- positive, zero, and negative balances;
- grouped integer amounts, malformed grouping, excess precision, and overflow;
- blank/repeated descriptions and opaque/repeated series values;
- ignored metadata and separator rows;
- formulas, native numeric/date cells, unsupported merges, extra sheets, and
  unexpected populated rows;
- corrupt/unreadable workbook and unsupported layout;
- deterministic repeated parsing and complete field provenance; and
- privacy checks proving no private values or paths occur in diagnostics or
  fixtures.

Because the current repository has no XLS writer, fixture manufacture is a
separate implementation concern. This contract does not add a writer
dependency or commit a private-derived binary fixture.

## Deferred lifecycle and identity questions

The following belong to later observation/resolution work and do not block
source parsing:

- whether `source_date` is transaction or accounting date;
- whether `source_signed_amount` equals canonical signed amount;
- the economic meaning of `Serie`;
- matching to Recent or Historical evidence;
- duplicate and rollover policy;
- provisional views;
- observation state transitions; and
- canonical Movement acceptance or correction.
