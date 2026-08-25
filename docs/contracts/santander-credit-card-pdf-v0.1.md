# Santander Credit Card PDF Source Contract v0.1

## Status: v0.1 — FROZEN / APPROVED (parser-contract correction applied)

The source-contract version remains `v0.1`: it identifies the supported source
family and evidence boundary. The corrected observable parser implementation
identifies itself separately as `santander-tdc-pdf-v1.1`; the previously
committed `santander-tdc-pdf-v1` result contract is not reused.

This document defines the frozen conservative source boundary for a future
Santander credit-card PDF parser. It does not implement a parser, define
Django models or migrations, authorize persistence changes, or alter the
frozen Santander current-account XLSX contract or importer.

The source variant is referred to as `santander_credit_card_pdf` / v1 within
this document. Those names are logical contract vocabulary only; no production
source-kind registration is made by this checkpoint.

## Scope and evidence basis

The evidence set is seven private Santander credit-card statements supplied
for the January–July 2026 scope. They were inspected read-only and are
identified here only as TDC source 1 through TDC source 7. The evidence showed:

- valid PDFs with native machine-extractable text;
- no encryption or password protection;
- one US Letter page-geometry family;
- three- or four-page pagination depending on content;
- recurring statement metadata and summary areas;
- recurring billed transaction areas with conditional domestic,
  international, and installment structure;
- recurring payment/credit, financial-charge, and unbilled areas; and
- consistent masked-card final-four evidence and conditional original USD
  operation evidence distinct from the CLP monthly charge; and
- no stable proof of posting dates, total installment counts, future-
  installment schedules, or cross-month transaction identity.

The frozen evidence basis is the seven consecutive January–July 2026 private
Santander TDC PDFs, all with native text and no encryption, one observed US
Letter template family, three-/four-page content-driven pagination, and the
deterministic extraction-boundary study defining `TDC-PDF-GIR-v1`. The
pdfplumber 0.11.8 / pdfminer.six 20251107 profile is the reference conformance
profile for that boundary; it is not yet a repository dependency.

The evidence hierarchy is binding:

1. repeated structure across all seven sources;
2. conditional structure observed in a subset;
3. stable, explicit source labels;
4. hypotheses requiring future evidence; and
5. unknowns.

Each rule below is marked as `REQUIRED`, `OPTIONAL/CONDITIONAL`,
`ACCEPTED VARIATION`, `UNSUPPORTED/FAIL-CLOSED`, or `OPEN QUESTION`.

## Recognition boundary

### Required v1 recognition evidence

A future parser may recognize a document as TDC PDF v1 only when all of the
following are true:

1. The artifact is a valid, readable PDF.
2. Native text extraction returns usable text. OCR-only input is outside v1.
3. The document is not encrypted or password-protected.
4. Every page uses the observed US Letter geometry family.
5. Provider/product context, statement metadata labels, and an exact recognized
   masked-card identity context are present. The four-digit suffix is retained
   as private structured metadata; recognition does not depend on its value.
6. A statement-period/cutoff area and a payment-due area are structurally
   recognized.
7. At least one transaction-table header and one billed transaction section
   are recognized with the expected relative column ordering.
8. Major sections occur in a coherent order: metadata/summary, billed detail,
   optional financial or payment detail, optional unbilled detail, then
   footer/legal/message content.

Recognition must not depend on a fixed page count. Three and four pages are
both `ACCEPTED VARIATION`.

### Recognition failure

Recognition is `UNSUPPORTED/FAIL-CLOSED` for encrypted or unreadable PDFs,
OCR-only text, a different page-geometry family, missing required statement
metadata, absent or ambiguous transaction headers, a changed column order,
contradictory section ordering, or financial-looking rows that cannot be
assigned to a recognized state.

A parser must not best-effort parse an unrecognized document as TDC v1.
Changed pagination, page breaks, optional sections, or footer length alone do
not cause failure.

## Deterministic extraction boundary

The parser does not receive an arbitrary extracted-text string. A conforming
native-text extraction adapter must produce `TDC-PDF-GIR-v1`, the canonical
geometric intermediate representation for this source variant. The adapter
may use a PDF library internally, but parser behavior is defined only over the
canonical representation. A different adapter or library is conforming only
when it produces equivalent page, token, line, and coordinate conformance
results.

The reference extraction profile used for conformance review is
`pdfplumber==0.11.8` with `pdfminer.six==20251107`, opened one
page at a time with native text only, `use_text_flow=False`,
`keep_blank_chars=False`, `x_tolerance=3pt`, `y_tolerance=3pt`,
`line_dir="ttb"`, `char_dir="ltr"`, and `return_chars=True`. This reference
profile is not a parser implementation or a persistence dependency yet. A
future dependency upgrade requires equivalent seven-source conformance
results and a parser/source-variant review.

### Canonical geometric intermediate representation

The minimum representation contains no financial semantics:

- document source variant and extraction-profile version;
- page ordinal, starting at `1`, in source order;
- page width and height in PDF points, rounded to `0.01pt`;
- native text words matching the reference profile's word boundaries, with
  source text, normalized bounding box, and extraction ordinal;
- deterministic lines with line ordinal, member token ordinals, and union
  bounding box; and
- deterministic row-group candidates with section-local ordinal and member
  line ordinals, without category or amount interpretation.

The canonical coordinate system uses PDF points (`72 points = 1 inch`), with
origin at the top-left of the page, x increasing rightward, and y increasing
downward. Every bounding box is `[x0, y0, x1, y1]`, with coordinates clamped
to the page and quantized to `0.01pt`. A normalized diagnostic form is also
available as `(x / page_width, y / page_height)` quantized to `1e-6`; it does
not replace the point coordinates.

Canonical extraction order is page ordinal, then top coordinate, then left
coordinate, then right coordinate, then source extraction ordinal. Ties are
resolved by the complete quantized bounding box and preserved token text. A
reader that cannot provide native text objects and coordinates fails document
recognition; OCR is never substituted. An alternative reader must reproduce
the reference word boundaries and quantized boxes within the conformance
tolerance; otherwise it is not a v1 extraction adapter.

## Extraction-level text normalization

The source token text retained in the private intermediate representation is
Unicode NFC, with line endings normalized and non-breaking spaces represented
as ordinary spaces. Punctuation, digits, decimal/thousands separators,
accented characters, and token boundaries are preserved. Numeric content is
not parsed, sign-normalized, rounded, or separator-normalized at this layer.

Recognition keys use Unicode NFKC, case folding, whitespace collapse, and
accent-insensitive comparison for structural labels only. The original token
location and non-destructive token text remain available for provenance.

## Deterministic line and row grouping

Words on one page are assigned to the same physical line when their vertical
center differs from the current line center by at most `2.00pt`. Assignment
uses the nearest line; an exact tie goes to the earlier line. Lines are sorted
by top coordinate and then left coordinate. A line bounding box is the union
of member word boxes, and line ordinals restart at `1` on each page.

The rule was checked structurally across all seven sources: both native-text
strategies produced the same page and derived-line counts and the same count
of date-bearing lines, while their word tokenization differed. That difference
is why parser code must consume the canonical representation rather than raw
library word output.

A transaction row-group candidate is formed only after a recognized table
header establishes column bands:

1. a line occupying the date band starts a group;
2. following lines belong to that group until the next date-band line,
   recognized repeated header, section transition, footer boundary, or end;
3. lines with no date-band token are continuations only when their geometry
   remains inside the established description/location/reference bands;
4. the group bounding box spans all member lines and its ordinal is local to
   the recognized section; and
5. a continuation that crosses a page boundary is accepted only when the next
   page has compatible section/header geometry and no contradictory heading.

No merchant, description, authorization value, or other literal transaction
content is used to group rows. An otherwise plausible group with conflicting
geometry is ambiguous and is not emitted as a financial candidate.

Repeated transaction or section headers with the same normalized anchor family
and compatible column geometry are structural `IGNORED` content. A footer or
legal block recognized by its footer anchors or stable page-bottom geometry is
also `IGNORED` and cannot terminate a valid group incorrectly. A conflicting
header or an unproven page-boundary continuation is document-fatal.

## Document and section state model

The parser should maintain a Santander-specific state rather than classify
financial-looking lines globally.

| State | Status | Meaning | Financial-row treatment |
| --- | --- | --- | --- |
| `PREAMBLE` | REQUIRED | Provider/product and statement context before detail | `IGNORED` |
| `STATEMENT_SUMMARY` | REQUIRED | Balances, totals, payment, and credit-context summary | `IGNORED` |
| `BILLED_DOMESTIC` | OPTIONAL/CONDITIONAL | Billed domestic purchase/charge detail | Candidate rows may be `PARSED` |
| `BILLED_INTERNATIONAL` | OPTIONAL/CONDITIONAL | Billed international detail | Candidate rows may be `PARSED` only with explicit billed currency |
| `BILLED_INSTALLMENT` | OPTIONAL/CONDITIONAL | Current billed installment detail | Candidate rows may be `PARSED`; installment metadata is not a second amount |
| `PAYMENTS_CREDITS` | OPTIONAL/CONDITIONAL | Posted payments, credits, or refunds | Candidate rows may be `PARSED` when direction is explicit |
| `FINANCIAL_CHARGES` | OPTIONAL/CONDITIONAL | Interest, commissions, taxes, insurance, or cash advances | Candidate rows may be `PARSED` when category and amount are explicit |
| `UNBILLED` | OPTIONAL/CONDITIONAL | Future or not-yet-billed activity and installment information | `IGNORED` by v1 |
| `FOOTER_LEGAL` | OPTIONAL/CONDITIONAL | Legal, message, contact, pagination, or decorative content | `IGNORED` |
| `END` | REQUIRED | End of recognized source content | No rows |

Safe state transitions require a recognized heading or a continuation of an
already recognized table. Decorative separators, whitespace, page breaks, and
footer text are not state transitions by themselves. A financial-looking row
after an unknown or contradictory heading causes document recognition failure;
it must not be globally interpreted as a transaction.

Domestic, international, and installment labels are conditional categories,
not required sections. A billed table without one of those distinctions may
use `BILLED_OTHER` only when its header and amount semantics are otherwise
recognized.

## Statement-level metadata

The following table defines the frozen extraction boundary. “Malformed
presence” means a recognized field is present but cannot be safely parsed.

| Field | Evidence/status | V1 semantics | Absence and malformed presence | Reconciliation |
| --- | --- | --- | --- | --- |
| `statement_period` | `REQUIRED` | Period covered by the statement | Missing or malformed: recognition failure | Context only |
| `billing_cutoff_date` | `REQUIRED` | Provider cutoff/facturation date | Missing or malformed: recognition failure | Defines billed boundary |
| `payment_due_date` | `REQUIRED` | Due date for the statement | Missing or malformed: recognition failure | No arithmetic role |
| `card_product_context` | `REQUIRED` for recognition | Sanitized product/category context | Malformed context: recognition failure | No |
| `card_last_four` | `REQUIRED` for recognized v1 documents | Exactly four decimal characters from recognized masked-card identity contexts; all occurrences must agree | Missing: unsupported; conflict: sanitized document-fatal contradiction | No |
| `statement_currency` | `REQUIRED` when used for monetary normalization | Currency from an explicit source label or trusted import context | Missing/ambiguous: monetary rows rejected; do not infer from symbols | Required for a complete check |
| `previous_balance` | `OPTIONAL/CONDITIONAL` | Prior billed balance only when the label meaning is explicit | Absence: valid; malformed: reconciliation becomes `INSUFFICIENT_DATA` | Candidate input |
| `payments_credits_total` | `OPTIONAL/CONDITIONAL` | Aggregate posted payments/credits when explicitly labeled | Absence: valid; malformed: not used | Candidate input |
| `purchases_charges_total` | `OPTIONAL/CONDITIONAL` | Aggregate billed purchases/charges when explicitly labeled | Absence: valid; malformed: not used | Candidate input |
| `financial_charges_total` | `OPTIONAL/CONDITIONAL` | Explicit aggregate of interest/fees/taxes/insurance | Absence: valid; malformed: not used | Candidate input |
| `interest_total` | `OPTIONAL/CONDITIONAL` | Interest aggregate when separately labeled | Absence: valid; malformed: not used | Candidate input |
| `commissions_total` | `OPTIONAL/CONDITIONAL` | Commission aggregate when separately labeled | Absence: valid; malformed: not used | Candidate input |
| `taxes_total` | `OPTIONAL/CONDITIONAL` | Tax aggregate when separately labeled | Absence: valid; malformed: not used | Candidate input |
| `insurance_total` | `OPTIONAL/CONDITIONAL` | Insurance/protection charge aggregate when separately labeled | Absence: valid; malformed: not used | Candidate input |
| `current_billed_balance` | `OPTIONAL/CONDITIONAL` | Ending billed debt/balance when explicitly labeled | Absence: valid; malformed: reconciliation becomes `INSUFFICIENT_DATA` | Candidate endpoint |
| `minimum_payment` | `OPTIONAL/CONDITIONAL` | Minimum required payment, not the billed balance | Absence: valid; malformed: not used | No |
| `total_payment` | `UNSUPPORTED/FAIL-CLOSED` for v1 | Not a v1 field; do not synthesize from minimum payment or balance | Absence is valid; malformed presence is not used | No |
| `available_credit` | `OPTIONAL/CONDITIONAL` | Available credit only when explicitly labeled | Absence: valid; malformed: not used | No |
| `assigned_credit_limit` | `UNSUPPORTED/FAIL-CLOSED` for v1 | Not a v1 field; do not claim or derive it | Absence is valid; malformed presence is not used | No |

Statement-level fields are not transaction rows. Summary values, minimum
payment, available credit, and credit-limit concepts must never become
movements merely because they are numeric.

## Concrete recognition anchor families

Structural labels are compared using the extraction-level recognition key.
Values adjacent to labels are never part of an anchor. The following families
are the v1 recognition vocabulary observed across the seven-source evidence:

| Anchor family | Normalized evidence | Location/relationship | Absence |
| --- | --- | --- | --- |
| Provider/product | `santander` together with `tarjeta`/`tarjetas` and `credito` | Same metadata block or page header | Document-fatal |
| Statement context | `estado` + `cuenta`, or a recognized `resumen`/`periodo` context | Metadata/summary area before detail | Document-fatal |
| Cutoff | `fecha` near `corte` or `facturacion` | Statement metadata | Document-fatal |
| Due date | `fecha` near `vencimiento` | Payment metadata | Document-fatal |
| Card identity | Exact full masked-card identity line or exact `movimientos tarjeta` masked-card heading | Statement/card section context only; never arbitrary transaction text | Missing or conflicting suffixes are document-fatal |
| Billed detail | `compras`, `cargos`, or `movimientos`, optionally qualified by `nacional`, `internacional`, or `cuotas` | Before any unbilled/future transition and paired with a valid table header | At least one billed section is required; otherwise document-fatal |
| Unbilled/future | `no` near `facturado`/`facturada`/`facturados` or an equivalent recognized future label | After billed detail, before footer/legal content | Optional; absence is valid |
| Payments/credits | `pagos`, `abonos`, or explicit `credito` | Recognized payment/credit section or row label | Optional; absence is valid |
| Financial charges | `intereses`, `comisiones`, `impuestos`, `seguros`, `avances`, or `efectivo` | Recognized financial-charge section | Optional; absence is valid |
| Table header | A recognized date role plus amount role, with detail/location/reference and optional currency/installment roles | Header line immediately before the corresponding table | Missing/ambiguous billed header is document-fatal |
| Footer/legal | Recognized legal/message/contact family or stable repeated page-bottom block | After the last recognized financial state | Optional when page-bottom geometry is unambiguous |

Anchor families do not authorize a row by themselves. The section state,
header geometry, row-group geometry, and candidate-field rules must also hold.
An unknown or contradictory label that interrupts a recognized financial
structure is not silently ignored.

## Transaction candidate contract

A row or row group may become a candidate only when it is inside a recognized
billed transaction state or the explicit payments/credits/financial-charges
state and has the following minimum evidence:

- a source date that is valid and unambiguously a transaction/purchase date;
- exactly one source amount field with a supported monetary representation;
- an explicit billed-currency context, either row-level or unambiguous section/
  statement-level context; and
- a section/category that determines account-debt direction.

The source date is called `transaction_date`. It must not be renamed to
`posting_date` or `billing_date` without new evidence.

| Candidate field | Status | Rule |
| --- | --- | --- |
| `transaction_date` | `REQUIRED` | Parse only a valid date in the recognized transaction row; reject invalid or ambiguous dates |
| `posting_date` | `UNSUPPORTED/FAIL-CLOSED` | No separate posting date was confirmed; remain absent, never infer |
| `description_detail` | `OPTIONAL/CONDITIONAL` | Preserve only as private raw/provenance data; do not invent or publish text |
| `location` | `OPTIONAL/CONDITIONAL` | Preserve only when structurally separate from description |
| `reference_authorization` | `OPTIONAL/CONDITIONAL` | Preserve as sensitive provenance; not assumed globally unique |
| `billed_currency` | `REQUIRED` for a monetary candidate | Use explicit row/section/statement context; never infer solely from a symbol |
| `billed_amount` | `REQUIRED` | Exact account-currency amount from the debt-affecting role; in the national-currency profile, parse CLP grouping separators without rounding |
| `original_currency` | `OPTIONAL/CONDITIONAL` | Preserve only from the source-confirmed original-operation role; v1 accepts the observed `US`/USD representation as `USD` |
| `original_amount` | `OPTIONAL/CONDITIONAL` | Preserve only from the source-confirmed original-operation amount role and only together with `original_currency` |
| `installment_number` | `OPTIONAL/CONDITIONAL` | Preserve only when explicitly tied to the current billed row |
| `total_installment_count` | `UNSUPPORTED/FAIL-CLOSED` | Not stable across the evidence set |
| `installment_amount` | `OPTIONAL/CONDITIONAL` | Preserve only as a distinct source field; never add it to billed amount automatically |
| `section_category` | `REQUIRED` | Record the recognized section/state that justified parsing |

If a candidate contains multiple competing amounts, an ambiguous currency, an
ambiguous date, or no explicit direction category, it is `REJECTED`. A row
that is recognized as future/unbilled information is `IGNORED`, not parsed as
a current transaction.

`original_amount` and `original_currency` form an inseparable pair and retain
separate field provenance. They never compete with or replace the amount in
the debt-affecting `Cargo del mes` role. No exchange rate is inferred or
returned. An amount-like value in that contextual band without a supported,
role-local currency marker does not populate either original field.

### Column geometry

The observed tables use a stable relative role order even when page breaks and
section lengths vary. A recognized header establishes the bands for its table;
absolute page coordinates are not reused across pages. The required ordering
is:

```text
date -> description/detail -> optional location/reference -> currency -> amount
```

The observed national-currency multi-line profile additionally establishes a
source-confirmed original-operation band before contextual installment bands,
and a distinct rightmost `Cargo del mes` band. Only the rightmost band supplies
`billed_amount`; an original-operation currency marker is recognized only
inside its own role band.

An installment table may add an installment-number/context band and an
installment-amount band adjacent to the detail or amount roles. A candidate
field must intersect its header-derived band and must not overlap a competing
monetary band. Header-derived bands use the canonical `0.01pt` boxes with a
maximum `3.00pt` edge tolerance, matching the extraction profile. A monetary
token outside the amount band is ambiguous: inside a recognized billed state
the row is `REJECTED`; outside a recognized financial state the document is
fatal. A changed role order or incompatible multiple table geometry is
document-fatal.

## Parser outcomes

Every recognized row or row group has exactly one outcome:

| Outcome | Meaning | Examples |
| --- | --- | --- |
| `PARSED` | A current billed financial row was interpreted unambiguously | Billed purchase, payment, credit, interest, fee, tax, insurance, or cash advance with date, amount, currency, category, and provenance |
| `IGNORED` | Recognized and deliberately not a current movement | Metadata, masked-card identity context, totals, headers, section markers, page separators, legal/footer text, unbilled activity, future-installment information, and decorative rows |
| `REJECTED` | Movement-like content could not be interpreted safely | Invalid date/amount, missing required field, ambiguous section, ambiguous currency/direction, multiple monetary interpretations, or malformed current billed row |

An unrecognized document-level layout is a fatal recognition failure, not a
set of ignored rows. Financial-looking summary or future rows must retain an
explicit ignore reason or rejection reason.

### Deterministic unknown-heading policy

- an unknown or contradictory heading that interrupts a recognized financial
  structure is document-fatal;
- financial-looking content outside every recognized financial state is
  document-fatal, because parser state is unsafe;
- a malformed movement-like row inside a recognized billed state is
  `REJECTED`; and
- recognized unbilled/future, summary, header, footer, and decorative content
  is `IGNORED` with a safe reason code.

This policy distinguishes document recognition failure from row-level
interpretation failure and does not use best-effort recovery after an unknown
state transition.

## v1 amount and direction semantics

The PDFs present categories and monetary amounts rather than a proven universal
signed debit/credit column. The v1 source-level value is therefore a
`debt_effect`, separate from household income/expense semantics:

- purchase/charge: positive, increases billed card debt;
- cash advance: positive, increases billed card debt;
- interest, commission, tax, or insurance: positive, increases billed card debt;
- payment, credit, or refund: negative, reduces billed card debt.

This direction is accepted only when the recognized source section or label
makes the category unambiguous. A payment, credit, or refund is a debt
reduction only when explicit source section/label evidence establishes that
meaning. A bare amount, a negative-looking amount, a description-only hint, or
an otherwise ambiguous debt-reduction row has no safe sign and is `REJECTED`.
The contract must not automatically reuse the current-account XLSX
debit/cargo and credit/abono rule, and it must not translate debt effect into
household income or expense.

`debt_effect` is source-native normalized meaning, not the canonical Gouda
`Movement.signed_amount`. At the Gouda source/domain boundary, a supported
liability-account adapter converts it as:

```text
canonical Movement.signed_amount = -debt_effect
```

Therefore a debt increase becomes a negative canonical movement and a debt
reduction becomes a positive canonical movement. Existing Santander
current-account cargo/debit and abono/credit values retain their current
canonical meanings. Source-native debt effect may remain in parser results,
raw records, or provenance, but must not become a second independently
mutable canonical amount.

A card payment/credit is not an expense merely because it is parsed from a
statement. Expense, income, refund, fee, tax, and transfer classification are
outside this source contract. Transfer/counterparty correlation is also outside
this source contract.

## Billed and unbilled activity

The seven documents expose structurally distinguishable billed transaction
areas and unbilled/future areas. Frozen v1 behavior is:

- current billed transaction rows may be `PARSED`;
- recognized unbilled rows and future activity are `IGNORED` with an explicit
  unbilled/future reason;
- unbilled amounts are excluded from billed-balance reconciliation; and
- no second current movement is created merely because a future item is listed.

The evidence does not prove whether a later billed row is the same underlying
purchase as an earlier unbilled row. No stable provider transaction identity
was confirmed. Exact statement-artifact identity prevents only byte-level
reimport, not semantic duplication across monthly statements. Cross-month
correlation and deduplication are deferred; a parser must not invent them.

## Installment semantics

Installment terminology, a current installment context, and an installment
amount area recur. The following conservative rules are frozen for v1:

- a current billed installment row may be `PARSED` as one current debt effect;
- `installment_number` is optional and only retained when explicitly tied to
  that current row;
- `installment_amount` is descriptive source data unless it is the sole
  unambiguous billed amount;
- total installment count, future-installment schedules, outstanding future
  amount, and installment-plan principal are not v1 fields; and
- future or informational installment rows are `IGNORED` and never normalized
  as current-period charges.

The underlying purchase agreement is not a movement. The current billing
charge and future informational schedule must remain distinct until later
evidence establishes a safe identity relationship.

## Currency semantics

The contract recognizes only currency values supported by explicit source
labels or trusted import context. A currency symbol alone is insufficient.

- A billed currency must be available for every `PARSED` monetary candidate.
- A section-level currency may be inherited only when the section boundary and
  label are unambiguous.
- In the observed national-currency profile, statement/account currency is CLP
  and `Cargo del mes` is the sole basis for `billed_amount` and `debt_effect`.
- Conditional international rows may also expose original USD operation amount
  and currency in a distinct source-confirmed role. Those fields are evidence,
  not the billed amount or installment amount.
- If multiple billed currencies appear and the source does not identify each
  row, those rows are `REJECTED`.
- Currency conversion, exchange-rate inference, and USD-statement behavior are
  outside this contract.

## Date semantics

The contract keeps these concepts separate:

- `statement_period`: coverage interval;
- `billing_cutoff_date`: end-of-billing event;
- `payment_due_date`: payment deadline; and
- `transaction_date`: the one transaction-level date observed in the stable
  row structure.

No `posting_date` is created by inference. A malformed statement-level date is
a recognition failure; a malformed transaction date rejects that candidate.

## Reconciliation contract

The deterministic v1 equation is:

```text
ending billed debt = previous billed debt
                   + billed purchases/charges
                   + billed financial charges
                   - posted payments/credits
```

Financial charges may include interest, commissions, taxes, insurance, and
other explicitly included charges. Unbilled activity and future-installment
information are excluded. International detail does not require a separate
equation when it is already included in the billed-charge aggregate and uses
the same billed currency.

The equation is eligible only when every operand is explicitly labeled,
semantically mapped, expressed in one currency, and parsed with exact decimal
semantics. Minimum payment and available credit are not operands.

If any `REJECTED` movement-like row could participate in billed financial
activity, reconciliation must be `INSUFFICIENT_DATA`, not `RECONCILED`, unless
complete independent evidence proves that the rejected row cannot affect every
required operand. This preserves the equation and follows the current-account
reconciliation rule that incomplete movement evidence cannot claim a complete
check.

### Seven-source privacy-safe test result

`FAIL` for complete deterministic reconciliation contract evidence across all
seven statements. This is an insufficiency result, not a claim that arithmetic
contradicted the equation: the observations did not prove a stable mapping for
all prior-balance, billed-charge, payment/credit, financial-charge, and ending-
billed-balance operands. A future parser may return `INSUFFICIENT_DATA`; it
must not weaken the equation or force reconciliation.

Frozen reconciliation states are `RECONCILED`, `NOT_RECONCILED`,
`INSUFFICIENT_DATA`, and `NOT_APPLICABLE`. The parser must retain which
operands were absent or ambiguous without logging their private values.

## Provenance and privacy

Every row result, including ignored and rejected results, must retain private
raw provenance sufficient for later audit without emitting it publicly:

- artifact identity and source kind;
- logical source variant and parser version;
- extraction-profile and canonical-intermediate-representation version;
- sanitized source identifier and page number;
- token and line ordinals, section/state, and table/row-group ordinal;
- canonical page width/height and normalized bounding box for every extracted
  field, plus its field-role relationship to the recognized column band;
- exact row outcome and safe reason code; and
- raw source representation only in the private raw boundary.

The structured final four digits and their field provenance are private source
metadata. Full or masked card text remains only in GIR/source evidence and is
never copied into parser error messages or unrestricted text fields.

Raw PDF text is not required in normalized records. The authoritative source
bytes remain in the private source-artifact boundary; deterministic locations
are sufficient to re-open the source for audit.

Filenames, account/card identifiers, names, descriptions, merchant data,
references, authorization codes, addresses, balances, limits, amounts, and raw
PDF text must not appear in logs, fixtures, documentation, or public errors.

## Confirmed variations and unsupported variations

### Confirmed or accepted variation

- three versus four pages;
- page breaks and section lengths driven by content;
- optional domestic/international, installment, unbilled, cash-advance,
  interest, commission, tax, insurance, and payment areas; and
- conditional legal/footer/message content.

### Unsupported or fail-closed variation for frozen v1

- encrypted, password-protected, or OCR-only PDFs;
- non-Letter page geometry without a deliberate contract revision;
- missing or ambiguous statement metadata or transaction headers;
- changed column ordering or multiple incompatible transaction tables;
- financial rows outside recognized section context;
- unlabelled currency, ambiguous direction, malformed amounts, or malformed
  dates;
- original-currency spellings, columns, or layouts not explicitly covered by
  the observed national-currency profile; and
- any new template whose section ordering cannot be proven equivalent.

## Explicit v1 exclusions

Frozen v1 does not promise:

- OCR or arbitrary Santander PDF layouts;
- posting dates where unavailable;
- inferred original currency or original amount;
- unlabeled refunds or credits;
- materialized unbilled/future activity;
- semantic cross-month identity;
- transaction deduplication across source products;
- transfer matching;
- expense/income classification;
- complete installment lifecycle modeling; or
- complete reconciliation for every supported statement.

These are intentional boundaries, not parser implementation TODOs. Any
extension requires an explicit source-contract revision.

## Confirmed observations and out-of-v1 questions

### Confirmed observations

- Seven PDFs share native text extraction, no encryption, US Letter geometry,
  and one broad template family.
- Pagination varies between three and four pages.
- Billed and unbilled/future areas are structurally distinguishable.
- Transaction date, billed amount/currency context, descriptive detail,
  location/reference context, and installment context recur.
- Masked-card final-four evidence recurs consistently, and conditional
  international rows expose original USD operation evidence separately from
  the CLP monthly charge.
- Posting date, total installment count, and stable cross-month identity were
  not confirmed.

### Out-of-v1 hypotheses

- Category-directed debt effects can be mapped consistently for the observed
  purchase, payment, credit, fee, tax, insurance, and cash-advance sections.
- A complete billed-balance reconciliation may become possible after exact
  aggregate labels and inclusions are mapped in a future evidence pass.
- A source-specific parser can share one state model across the observed
  three/four-page pagination variation.

### Out-of-v1 questions

These questions do not weaken or reopen the frozen v1 boundary. They are
future product, source-variant, or lifecycle concerns and require an explicit
contract revision before they can affect parser behavior.

- How should card-payment rows be classified as transfers versus other payment
  or credit activity?
- Can future cross-account evidence support reliable payment correlation and
  transfer matching?
- Can billed/unbilled lifecycle identity be established across statements?
- Can a later source variant expose a stable posting date, a different original
  currency representation, or a genuinely non-CLP statement currency?
- Can installment current/total identity, future schedules, and lifecycle
  correlation be proven?
- Can a stable provider reference correlate unbilled and later billed rows?
- Which fees and taxes are included in each billed aggregate?
- Does a later Santander TDC export introduce another template or terminology
  family?
