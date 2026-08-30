# BCI Recent Movements source contract v0.1

## Status

Frozen source-recognition and source-native extraction contract. This contract
does not implement a parser or authorize observation resolution or canonical
ledger writes.

The logical source variant is `bci_recent_movements_xlsx` and the contract
version is `bci_recent_movements_v0.1`. A future implementation parser identity
must include this source variant and contract version.

## Scope and evidence basis

This contract covers the observed BCI Recent Movements OOXML/XLSX profile:

- one readable OOXML workbook;
- one visible worksheet named `movimientos`;
- a title row, seven metadata rows, and one transaction header row;
- a merged `C:F` description region on every transaction row;
- separate transaction and accounting date columns;
- mutually exclusive Cargo/Abono amount columns; and
- no per-row balance, reference, totals, or reconciliation block.

The contract is limited to this observed profile. An unobserved package,
worksheet, merge topology, header arrangement, cell type, or row structure is
unsupported rather than best-effort parsed.

## Explicit non-goals

V0.1 does not define or claim:

- intrinsic BCI, Account, or currency proof from workbook cells;
- Current-to-Recent or Current-to-Historical identity;
- deduplication or rollover behavior;
- any canonical meaning for Cargo/Abono;
- description stability or matching;
- synthesized balances or references;
- provisional or canonical Movement behavior;
- observation lifecycle or resolution policy; or
- any persistence model.

Trusted source context may route an artifact to this adapter. Account and
currency remain application-boundary concerns and must not be inferred from
the filename, path, description, or amount.

## Supported container and worksheet profile

The input is a readable OOXML/XLSX workbook. The adapter uses a workbook
reader with `data_only=False` and inspects the underlying worksheet cells.

Exactly one visible worksheet named `movimientos` must match the structural
fingerprint. The declared worksheet dimension is advisory only. In the
observed artifact it declares `A1` while actual populated content extends to
`H58`; v0.1 must discover the actual populated extent by iterating worksheet
cells.

## Deterministic recognition fingerprint

Recognition succeeds only when all conditions below hold:

1. The input is a readable OOXML/XLSX workbook.
2. Exactly one visible worksheet named `movimientos` matches.
3. The first row contains the observed merged title `Últimos Movimientos`.
4. Rows 2–7 contain the observed metadata labels in column D, in order:
   `Saldo Disponible`, `Saldo Contable`, `Retenciones`, `Sobregiro
   Disponible`, `Sobregiro Utilizado`, and `Línea de Emergencia`.
5. Row 8 contains the observed header layout:
   - A: `Fecha Transacción`;
   - B: `Fecha Contable`;
   - C: `Descripción`;
   - D:F: blank header layout cells;
   - G: `Cargo $`; and
   - H: `Abono $`.
6. Each transaction row has the observed `C:F` merged description range.
7. The actual populated rows form one contiguous transaction region below the
   header.

Recognition uses normalized structural labels and merge/layout structure. It
does not use filenames, account values, descriptions, amounts, or balances.

## Structural regions and row outcomes

| Region | Rows | Outcome |
| --- | --- | --- |
| Title | 1 | `IGNORED` |
| Account snapshot metadata | 2–7 | `IGNORED` |
| Transaction header | 8 | `IGNORED` |
| Transactions | 9 through the last actual populated row | `PARSED` or `REJECTED` |
| Merged-cell placeholders in D:F | Within transaction rows | `IGNORED` layout cells |

Snapshot fields such as available/accounting balance, retentions, and
overdraft values are not transaction rows. No totals or reconciliation block
is recognized.

## Source-native extracted fields

Each transaction row preserves:

| Field | Source cell/range | V0.1 semantics |
| --- | --- | --- |
| `transaction_date` | `Fecha Transacción` in A | Exact source-native field named by the workbook; parsed from the supported grammar. |
| `accounting_date` | `Fecha Contable` in B | Exact source-native field named by the workbook; parsed independently. |
| `source_description` | merged `C:F` | Source text from the merged description region with deterministic surrounding-whitespace normalization only. |
| `source_direction` | populated G or H | `cargo` or `abono` according to the populated source column; no canonical household-effect claim. |
| `source_amount` | `Cargo $` in G or `Abono $` in H | Exact nonnegative source magnitude; no canonical sign mapping. |

No balance or reference field is synthesized. The two date fields remain
distinct even when their values are equal.

## Date grammar and ordering

The only supported date grammar is full-year `DD/MM/YYYY`. Dates must be real
Gregorian dates. No year inference, locale inference, or filename-date
substitution is allowed.

Rows are emitted in worksheet order. The observed `Fecha Transacción` sequence
is newest-to-oldest; v0.1 requires non-increasing transaction dates and allows
equal dates. `Fecha Contable` is preserved in source order and is not required
to be monotonic. These are source-order rules, not identity rules.

## Exact monetary grammar and Decimal behavior

The observed Cargo/Abono grammar is:

```text
(?:\d+|\d{1,3}(?:\.\d{3})+)
```

Values are nonnegative integer monetary units with optional dot thousands
grouping. Fractional values, decimal commas, currency symbols inside cells,
negative directional values, and malformed grouping are unsupported.

The raw source text and populated source side are preserved. Any parsed numeric
value is created with `Decimal`; no binary floating point, implicit sign
reversal, or rounding is permitted. Integer source units may be represented at
Gouda's exact two-decimal boundary without changing their value.

## Row validation

A transaction row is valid only when:

- both date cells are text values matching the date grammar;
- the description region is text or explicitly empty source content;
- exactly one of G and H is populated;
- the populated amount is text matching the nonnegative amount grammar; and
- transaction dates remain non-increasing in source order.

The adapter preserves Cargo/Abono direction exactly as source-native data. It
does not calculate `credit - debit`, canonical signed amount, or household
effect.

## Ignored and rejected structures

Ignored structures are limited to the title, recognized metadata, header, and
merged-cell placeholders. No balance, reference, period total, or
reconciliation field is fabricated from nearby cells.

Recognition or parsing rejects:

- corrupt, unreadable, or unsupported OOXML input;
- missing, duplicated, hidden, or ambiguous matching worksheets;
- missing or changed title, metadata, or header markers;
- missing or altered `C:F` merge topology;
- a declared dimension used as the parsing boundary;
- formulas or unsupported cell types;
- malformed or invalid dates;
- non-monotonic transaction-date order;
- both Cargo and Abono populated;
- neither Cargo nor Abono populated;
- malformed, negative, fractional, or ambiguously grouped amounts;
- unexpected populated cells or structural gaps in the transaction region; and
- any unobserved layout variant.

No partial financial interpretation is returned for a recognition-fatal
failure. A recognized row-level rejection must retain only sanitized reason
codes in any outer application result.

## Formula and cell-type handling

The observed transaction cells are inline strings in the OOXML worksheet. V0.1
accepts the observed text representation and rejects formulas, formula-backed
values, unsupported native numeric/date cells, and ambiguous cell types.
Cached formula values must never be treated as source facts.

The reader must iterate actual worksheet cell elements/rows independently of
the worksheet `<dimension>` value. Merged ranges are interpreted logically:
`C:F` is one description field, not four independent source fields.

## Provenance and privacy

Every extracted field must identify:

- the immutable artifact identity supplied by the outer boundary;
- worksheet name and ordinal;
- row and source-column coordinates;
- merged-range membership where applicable;
- original source cell type and text provenance;
- source field name; and
- contract/parser version.

Private filenames, account identifiers, descriptions, amounts, balances, raw
cells, and workbook XML must not enter logs, public representations, tracked
fixtures, or documentation. Synthetic tests use wholly synthetic values.

## Minimum synthetic test matrix

- valid OOXML profile with title, metadata, header, and transaction rows;
- worksheet declaring dimension `A1` while actual populated content extends
  beyond `A1`;
- actual-cell iteration through the final populated row;
- exact `C:F` merged description topology;
- equal and differing transaction/accounting dates;
- newest-to-oldest transaction dates;
- non-monotonic accounting dates accepted and preserved;
- one Cargo-only row and one Abono-only row;
- both-populated and neither-populated rows rejected;
- malformed/negative/fractional/grouping-invalid amounts;
- empty/repeated descriptions;
- ignored snapshot metadata and merged placeholders;
- formulas, unsupported cell types, changed merges, extra sheets, corrupt
  OOXML, and unexpected populated regions;
- deterministic repeated parsing and complete field provenance; and
- privacy checks proving no private values or paths occur in diagnostics or
  fixtures.

## Deferred lifecycle and identity questions

The following belong to later observation/resolution work and do not block
source parsing:

- whether transaction date or accounting date is authoritative for a later
  observation;
- whether Cargo/Abono maps to canonical signed amount;
- Current/Recent/Historical correspondence;
- duplicate and rollover policy;
- description matching;
- provisional views;
- observation state transitions; and
- canonical Movement acceptance or correction.
