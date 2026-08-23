# Santander credit-card PDF source observations

## Purpose and scope

This note records a privacy-safe, read-only structural inspection of seven
private Santander credit-card statement PDFs supplied for the January–July
2026 scope. The files are identified here only as TDC source 1 through TDC
source 7. No private filenames, values, account or card identifiers, names,
transaction descriptions, or raw PDF text are retained.

This is source discovery, not a parser contract. No parser, model, migration,
or persistence behavior is defined by this note.

## Confirmed observations

### Document-level structure

- Seven PDFs were present; all had a valid PDF signature.
- All seven exposed machine-extractable text through native PDF extraction.
  OCR was not needed and was not used.
- None was encrypted or password-protected.
- All seven used the same observed page dimensions: US Letter, 612 × 792 PDF
  points.
- Pagination varied: four sources had three pages and three sources had four
  pages. This is a pagination/content variation, not evidence of a second
  page-size template.
- No exact-byte duplicate PDF was observed.
- The broad template family was shared across the seven sources, with
  month-dependent section length and page breaks.

### Statement-level concepts

Recurring text and layout evidence was observed for:

- statement-period and cutoff/billing-date concepts;
- payment due date;
- card/product context;
- currency context;
- previous/current statement summary and payment-minimum concepts;
- payments or credits and purchases/charges;
- interest, commissions, and taxes;
- available or assigned credit;
- installment activity;
- international activity;
- cash-advance activity; and
- insurance or another protection-related charge section.

The exact private values and labels are intentionally omitted. The extracted
text alone did not establish a stable, unambiguous mapping for every balance
label or every fee subtype.

### Repeated transaction-row fields

The recurring transaction-area structure provides evidence for:

- transaction date;
- description/detail;
- city or country context;
- reference or authorization context;
- billed currency;
- billed amount;
- installment number/current installment context; and
- installment amount.

No separate posting-date field was confirmed. Original-currency and
original-amount fields were not confirmed as stable distinct columns. A
stable total-installment-count field was not confirmed.

### Sections

The seven sources repeatedly expose broad areas corresponding to:

- statement summary and payment information;
- domestic purchases;
- international purchases;
- installment transactions;
- unbilled or future activity;
- payments;
- interest, commissions, and taxes;
- cash advances; and
- insurance or related financial charges.

No repeated standalone refunds/credits section was confirmed by the safe
structural scan. A payment or credit may still occur as a row or summary item;
that distinction requires a future row-level review.

## Cross-month comparison

### Invariants

- Native text extraction worked for every source.
- Page dimensions were invariant.
- Statement metadata, payment information, purchase/charge areas, installment
  terminology, and summary concepts recurred across all seven.
- Domestic and international activity areas, fee/interest/tax terminology, and
  the broad statement-summary layout recurred across the set.

### Conditional or variable structure

- Page count changed from three to four pages.
- Page breaks moved with section length.
- International, installment, unbilled, fee, tax, insurance, and cash-advance
  content should be treated as conditional until row-level rules are proven.
- Footer/legal content and pagination are expected to vary with page count;
  their exact text was not retained.

No obvious second page-size or wholly different template variant was observed.

## Installment observations

Installment terminology and a current-installment/amount area recur, so the
documents appear to distinguish at least some installment-related activity
from ordinary purchase activity. The seven-source scan did not confirm a
stable explicit total-installment-count field, a future-installment schedule,
or a reliable separation of installment principal from interest and fees.
Those are open discovery questions, not Gouda semantics.

## Candidate reconciliation evidence

The PDFs provide statement-summary and payment-minimum areas, together with
purchase/charge, payment/credit, interest, commission, and tax concepts. These
are candidate inputs for a future billed-balance reconciliation.

The following conceptual relationship is plausible but not yet contractually
supported:

```text
ending billed balance = prior billed balance
                       + billed charges
                       - payments/credits
                       + interest/fees/taxes
```

The evidence is insufficient to implement this equation now because billed
versus unbilled activity, fee inclusion, installment treatment, and balance
label semantics have not been proven across enough row-level examples.

## Relationship to the current Gouda model

### Natural conceptual fit

- `Account` can conceptually identify a credit-card account, but the current
  `Account.Kind` enum only approves current accounts.
- `Movement` can represent a signed card transaction at a coarse level:
  money entering the card account is positive and money leaving it is negative,
  preserving Gouda’s signed-movement convention.
- Source records and provenance are natural places to retain source-row
  traceability.

### Future design decisions

- transaction date versus posting, billing, and statement dates;
- installment identity, current/total counts, and future installments;
- billed versus unbilled amounts;
- multiple currencies and original-versus-billed amounts;
- payments, credits, interest, commissions, taxes, and insurance as movement
  rows versus statement-level concepts; and
- statement debt, credit limit, available credit, and reconciliation evidence.

No model or persistence change is authorized by this observation note.

## Confirmed observations, hypotheses, and open questions

### Confirmed observations

- Seven valid, non-encrypted, machine-text PDFs were inspected read-only.
- All used US Letter dimensions and one broad template family.
- Pagination varied between three and four pages.
- The recurring concepts and row-field evidence listed above were present in
  the source set.

### Hypotheses

- The broad statement-summary, transaction, and financial-charge areas can be
  parsed with a single source-specific template plus conditional sections.
- A deterministic billed-balance reconciliation may be possible after the
  statement-level and row-level inclusions are explicitly mapped.

### Open questions

- Are transaction and posting dates both present under a different label or
  only one date is supplied?
- How are original and billed currencies represented for international rows?
- How are installment principal, interest, fees, and future installments
  represented and linked across statements?
- Which statement totals include unbilled activity and which fees or taxes?
- Are payment/credit rows and refunds distinguishable without relying on
  descriptions?
- Do later statements introduce another template, page size, or terminology
  variant?
