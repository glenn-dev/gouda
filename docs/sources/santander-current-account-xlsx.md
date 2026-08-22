# Santander current-account XLSX source

## Purpose and scope

This document records the structure observed in three private Santander
current-account statement workbooks representing consecutive monthly periods.
The real filenames, account values, dates, descriptions, references, balances,
and amounts are intentionally not recorded.

The inspection was structural and read-only. It covered workbook metadata,
cell types, layout, labels, row shapes, and aggregate arithmetic checks. It did
not copy, modify, anonymize, or retain the source files.

## Confirmed observations

### Workbook structure

- Each inspected workbook has one visible worksheet.
- No hidden worksheets were observed.
- The used range is `A1:G35` for two workbooks and `A1:G34` for one.
- Each worksheet has seven columns and eight merged ranges.
- No formulas were found.
- No fully empty row is emitted as a populated XML row; rows absent from the
  worksheet data can still be empty inside the reported used range. Some cells
  in metadata and table rows are empty or empty strings.
- The three workbooks use the same general layout; the number of movement and
  footer rows varies by period.

### Metadata sections

Conceptual sections appear in these areas:

| Area | Observed content | Treatment in Gouda |
| --- | --- | --- |
| Rows 1–6 | Institution/account context and period start/end | Capture as artifact or account-period metadata; do not treat as movements |
| Rows 9–14 | Account context, opening/ending balance, credit total, debit total | Capture as batch metadata and reconciliation inputs |
| Rows 16–18 | Additional summary/balance context | Preserve in raw metadata; map only when its meaning is confirmed |
| Rows 20–21 | Movement section title and column header | Use to detect the movement table; ignore as records |

The observed metadata includes institution, account type, account identifier,
period boundaries, opening balance, ending balance, total credits, and total
debits. A currency label was not independently confirmed in the inspected
layout. The currency must therefore be supplied only from a trusted source or
explicit import configuration; it must not be guessed from a currency symbol.

Account identifiers and all metadata values are sensitive. They belong in the
private raw layer and must be redacted from logs and documentation.

### Movement table

The movement header is detected at row 21 after the section marker at row 20.
The observed column order is:

| Column | Observed semantic | Required for an accepted movement |
| --- | --- | --- |
| A | Date | Yes |
| B | Textual auxiliary field; exact domain meaning is not yet confirmed | No |
| C | Description/detail | No, but preserve when present |
| D | Textual or numeric-looking reference/document field | No, preserve when present |
| E | Cargo/debit | Exactly one of E or F |
| F | Abono/credit | Exactly one of E or F |
| G | Running balance | Optional at row level; useful for reconciliation |

The header labels for date, description, and balance are generic banking labels.
The observed debit and credit headers are longer banking labels containing the
generic cargo and abono terms; the parser matches those terms only in their
documented fixed columns E and F. The B and D fields require a future sample
comparison before they receive stronger semantics.

Observed rows after the header include:

- movement-like rows with a date and exactly one populated debit or credit;
- rows with a date but a missing, ambiguous, or non-numeric supporting value;
- auxiliary text rows, including footer or note-like content;
- blank rows/cells;
- no repeated movement header was observed in these three files.

The private-source inspection also established the following sequence in all
three samples:

`movement detail → Resumen de Comisiones → asterisk separator → commission-summary rows → MENSAJES → footer/messages`

`Resumen de Comisiones` is a standalone marker in column C, the asterisk row
is standalone structure in that auxiliary section, and `MENSAJES` is a
standalone marker in column A. The labels are retained here as sanitized
structural observations. The parser uses the two exact normalized markers as
section boundaries; the asterisk separator is not used as the primary start
or end boundary.

The validated parser classifies rows by structure, not by row number alone. A
future statement may add or remove metadata and footer rows; unsupported
variants require an intentional contract revision.

## Dates, currency, and amounts

### Dates

Movement dates are stored as text in a day/month shape without a year. Period
metadata contains the context needed to resolve the year. The initial parser
contract should accept the movement date only when the period context makes the
result unambiguous and should reject impossible calendar dates.

The year-resolution rule is a contract hypothesis, not a guarantee of the
source: infer the year from the statement period and reject a date that cannot
belong to that period rather than silently rolling it into another year.

### Amounts

The source separates cargos/debits and abonos/credits. The inspected files use
a mixed XLSX representation: many values are shared strings, while some amount
cells are numeric cells. Summary values visibly use a currency marker and
thousands separators; movement values include integer-like numeric text and
numeric cells. No decimal example was relied upon to define the parser.

The parser must normalize both cell types with exact decimal arithmetic. It must
handle the statement's observed thousands separator and reject malformed or
ambiguous formatting. Empty amount cells mean “not populated”; they are not
zero unless the source contract for a later variant explicitly establishes
that rule.

### Signed movement convention

Following [ADR-0001](../decisions/ADR-0001-signed-account-movements.md):

- a populated cargo/debit becomes a negative `signed_amount`;
- a populated abono/credit becomes a positive `signed_amount`;
- both populated is ambiguous and must be rejected;
- neither populated is not a movement and should be ignored or rejected based
  on the row context;
- a source running balance is evidence for reconciliation, not a replacement
  for the signed amount.

This is account effect, not an assertion that “income”, “expense”,
“entry/exit”, or “debit/credit” are interchangeable domain concepts.

## Row identification rules

The validated parser:

1. locate the movement header using recognized header labels and their relative
   order;
2. treat metadata, section titles, headers, footers, notes, and blank rows as
   non-movement rows;
3. recognize a candidate movement by a valid day/month date and a populated
   debit or credit cell;
4. require exactly one of debit or credit to parse as an amount;
5. preserve the original row position in provenance;
6. keep a non-empty running balance when it parses, but allow it to be absent;
7. reject a candidate with conflicting amount columns, an invalid date, or an
   invalid non-empty amount instead of silently changing its meaning.

## Reconciliation capability

The workbooks contain opening and ending balance metadata, debit/credit totals,
and a running-balance column. That is sufficient to attempt checks such as:

```text
ending_balance = opening_balance + sum(signed_movements)
```

Some date-like rows lack a numeric running balance, so running-balance evidence
is optional. After the confirmed commission-summary section was excluded from
primary movement normalization, the strict opening/ending balance check
reconciled all three samples. The parser reports the result independently from
row validity and retains otherwise valid movements when evidence is incomplete.

## Confirmed observations, hypotheses, and open questions

### Confirmed observations

- One visible sheet per workbook, no formulas, and the same seven-column
  general layout.
- Metadata precedes the movement table.
- Debit and credit are separate columns.
- Movement dates omit the year.
- The running balance is present as a column but is not numeric/populated for
  every date-like row.
- The source uses both string and numeric XLSX cell representations.

### Hypotheses

- The year for a movement date should come from the statement period.
- Column B is a provider-specific movement descriptor and column D is a
  provider reference/document value.
- The currency marker and account context may imply a local currency, but this
  must not be accepted without an explicit trusted currency field or config.

### Open questions

- Does column B have a stable meaning across other statement exports?
- Are rows without a numeric running balance legitimate movements, or are some
  of them continuation/footer rows?
- Can a later export contain decimal amounts or a different thousands/decimal
  convention?
- Can movement dates cross a year boundary within a statement period?
- Is there a stable provider transaction identifier beyond the observed
  reference/document field?

## Variations to validate with other months

Before treating this layout as stable, compare additional statements for:

- year-boundary periods;
- zero-value and refund-like rows;
- descriptions wrapping across rows;
- repeated headers or pagination footers;
- different account types or currencies;
- decimal amounts and negative display formats;
- rows where both debit and credit are present;
- statements with no movements;
- changed column order or added provider columns.
