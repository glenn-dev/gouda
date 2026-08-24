# Proposed Santander credit-card PDF source contract v0.1

## Status: PROPOSED / NOT FROZEN

This document defines a conservative source boundary for a future Santander
credit-card PDF parser. It is contract design only. It does not implement a
parser, define Django models or migrations, authorize persistence changes, or
alter the frozen Santander current-account XLSX contract or importer.

The proposed source variant is referred to as `santander_credit_card_pdf` / v1
within this document. Those names are logical contract vocabulary only; no
production source-kind registration is made by this checkpoint.

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
- no stable proof of posting dates, original-currency columns, total
  installment counts, future-installment schedules, or cross-month transaction
  identity.

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
5. Provider/product context and statement metadata labels are recognized using
   source-specific normalized label families, without depending on account,
   card, person, merchant, or amount values.
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
after an unknown or contradictory heading is `REJECTED` or causes workbook
recognition failure; it must not be globally interpreted as a transaction.

Domestic, international, and installment labels are conditional categories,
not required sections. A billed table without one of those distinctions may
use `BILLED_OTHER` only when its header and amount semantics are otherwise
recognized.

## Statement-level metadata

The following table defines the proposed extraction boundary. “Malformed
presence” means a recognized field is present but cannot be safely parsed.

| Field | Evidence/status | Proposed semantics | Absence and malformed presence | Reconciliation |
| --- | --- | --- | --- | --- |
| `statement_period` | `REQUIRED` | Period covered by the statement | Missing or malformed: recognition failure | Context only |
| `billing_cutoff_date` | `REQUIRED` | Provider cutoff/facturation date | Missing or malformed: recognition failure | Defines billed boundary |
| `payment_due_date` | `REQUIRED` | Due date for the statement | Missing or malformed: recognition failure | No arithmetic role |
| `card_product_context` | `REQUIRED` for recognition | Sanitized product/category context | Identifiers are never retained in public output; malformed context: failure | No |
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
| `total_payment` | `OPEN QUESTION` | A distinct total-payment field was not proven stable | Do not synthesize from minimum payment or balance | No |
| `available_credit` | `OPTIONAL/CONDITIONAL` | Available credit only when explicitly labeled | Absence: valid; malformed: not used | No |
| `assigned_credit_limit` | `OPEN QUESTION` | Assigned/limit meaning was not proven distinct from availability | Do not claim or derive it | No |

Statement-level fields are not transaction rows. Summary values, minimum
payment, available credit, and credit-limit concepts must never become
movements merely because they are numeric.

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
| `billed_currency` | `REQUIRED` for a monetary candidate | Use explicit row/section label; never infer solely from a symbol |
| `billed_amount` | `REQUIRED` | Exact decimal parse; no silent sign or rounding transformation |
| `original_currency` | `UNSUPPORTED/FAIL-CLOSED` for v1 normalization | No stable distinct field was confirmed |
| `original_amount` | `UNSUPPORTED/FAIL-CLOSED` for v1 normalization | No stable distinct field was confirmed |
| `installment_number` | `OPTIONAL/CONDITIONAL` | Preserve only when explicitly tied to the current billed row |
| `total_installment_count` | `UNSUPPORTED/FAIL-CLOSED` | Not stable across the evidence set |
| `installment_amount` | `OPTIONAL/CONDITIONAL` | Preserve only as a distinct source field; never add it to billed amount automatically |
| `section_category` | `REQUIRED` | Record the recognized section/state that justified parsing |

If a candidate contains multiple competing amounts, an ambiguous currency, an
ambiguous date, or no explicit direction category, it is `REJECTED`. A row
that is recognized as future/unbilled information is `IGNORED`, not parsed as
a current transaction.

## Parser outcomes

Every recognized row or row group has exactly one outcome:

| Outcome | Meaning | Examples |
| --- | --- | --- |
| `PARSED` | A current billed financial row was interpreted unambiguously | Billed purchase, payment, credit, interest, fee, tax, insurance, or cash advance with date, amount, currency, category, and provenance |
| `IGNORED` | Recognized and deliberately not a current movement | Metadata, totals, headers, section markers, page separators, legal/footer text, unbilled activity, future-installment information, and decorative rows |
| `REJECTED` | Movement-like content could not be interpreted safely | Invalid date/amount, missing required field, ambiguous section, ambiguous currency/direction, multiple monetary interpretations, or malformed current billed row |

An unrecognized document-level layout is a fatal recognition failure, not a
set of ignored rows. Financial-looking summary or future rows must retain an
explicit ignore reason or rejection reason.

## Proposed amount and direction semantics

The PDFs present categories and monetary amounts rather than a proven universal
signed debit/credit column. The proposed source-level value is therefore a
`debt_effect`, separate from household income/expense semantics:

- purchase/charge: positive, increases billed card debt;
- cash advance: positive, increases billed card debt;
- interest, commission, tax, or insurance: positive, increases billed card debt;
- payment, credit, or refund: negative, reduces billed card debt.

This direction is accepted only when the recognized source section or label
makes the category unambiguous. A bare amount has no safe sign and is
`REJECTED`. The contract must not automatically reuse the current-account
XLSX debit/cargo and credit/abono rule, and it must not translate debt effect
into household income or expense.

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
areas and unbilled/future areas. Proposed v1 behavior is:

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
amount area recur. The following conservative rules are proposed:

- a current billed installment row may be `PARSED` as one current debt effect;
- `installment_number` is optional and only retained when explicitly tied to
  that current row;
- `installment_amount` is descriptive source data unless it is the sole
  unambiguous billed amount;
- total installment count, future-installment schedules, outstanding future
  amount, and original purchase amount are not v1 fields; and
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
- International activity is recognized as a conditional section, but original
  currency and original amount were not proven as stable distinct fields.
- If multiple billed currencies appear and the source does not identify each
  row, those rows are `REJECTED`.
- Currency conversion is outside this contract.

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

The only proposed deterministic equation is:

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

### Seven-source privacy-safe test result

`FAIL` for complete deterministic reconciliation contract evidence across all
seven statements. This is an insufficiency result, not a claim that arithmetic
contradicted the equation: the observations did not prove a stable mapping for
all prior-balance, billed-charge, payment/credit, financial-charge, and ending-
billed-balance operands. A future parser may return `INSUFFICIENT_DATA`; it
must not weaken the equation or force reconciliation.

Proposed reconciliation states are `RECONCILED`, `NOT_RECONCILED`,
`INSUFFICIENT_DATA`, and `NOT_APPLICABLE`. The parser must retain which
operands were absent or ambiguous without logging their private values.

## Provenance and privacy

Every row result, including ignored and rejected results, must retain private
raw provenance sufficient for later audit without emitting it publicly:

- logical source variant and parser version;
- sanitized source identifier and page number;
- section/state and table/row ordinal;
- source column/field positions for every extracted value;
- exact row outcome and safe reason code; and
- raw source representation only in the private raw boundary.

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

### Unsupported or fail-closed variation for proposed v1

- encrypted, password-protected, or OCR-only PDFs;
- non-Letter page geometry without a deliberate contract revision;
- missing or ambiguous statement metadata or transaction headers;
- changed column ordering or multiple incompatible transaction tables;
- financial rows outside recognized section context;
- unlabelled currency, ambiguous direction, malformed amounts, or malformed
  dates;
- stable original-currency/original-amount columns not covered by this
  contract; and
- any new template whose section ordering cannot be proven equivalent.

## Confirmed observations, hypotheses, and open questions

### Confirmed observations

- Seven PDFs share native text extraction, no encryption, US Letter geometry,
  and one broad template family.
- Pagination varies between three and four pages.
- Billed and unbilled/future areas are structurally distinguishable.
- Transaction date, billed amount/currency context, descriptive detail,
  location/reference context, and installment context recur.
- Posting date, original currency/amount, total installment count, and stable
  cross-month identity were not confirmed.

### Hypotheses

- Category-directed debt effects can be mapped consistently for the observed
  purchase, payment, credit, fee, tax, insurance, and cash-advance sections.
- A complete billed-balance reconciliation may become possible after exact
  aggregate labels and inclusions are mapped in a future evidence pass.
- A source-specific parser can share one state model across the observed
  three/four-page pagination variation.

### Open questions

- How should card-payment rows be classified as transfers versus other payment
  or credit activity?
- Can future cross-account evidence support reliable payment correlation and
  transfer matching?
- Can billed/unbilled lifecycle identity be established across statements?
- Can a later statement expose stable posting dates or original currencies?
- Can installment current/total identity, future schedules, and lifecycle
  correlation be proven?
- Can a stable provider reference correlate unbilled and later billed rows?
- Which fees and taxes are included in each billed aggregate?
- Does a later Santander TDC export introduce another template or terminology
  family?
