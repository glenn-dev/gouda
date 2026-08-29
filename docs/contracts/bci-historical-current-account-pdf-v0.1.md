# BCI historical current-account PDF source contract v0.1

## Status: v0.1 design checkpoint

This document defines the smallest deterministic source contract and
implementation test plan for the observed BCI historical current-account PDF
family. It does not implement a parser, register a production source kind,
change persistence, or authorize canonical writes by parser code.

The logical source variant is `bci_historical_current_account_pdf` and the
proposed parser identity is `bci-historical-current-account-pdf-v1`. These
names are contract vocabulary until the implementation checkpoint registers
them.

## Scope and evidence basis

The evidence set is two private historical statements inspected read-only.
Private filenames, account and holder data, contact details, descriptions,
references, amounts, and balances are deliberately absent from this document.
The corpus showed one native-text US Letter layout family with:

- three pages per observed statement;
- a complete provider, product, account, currency, statement, and period
  header on page one;
- a transaction table spanning every page, with repeated column headers on
  continuation pages;
- a final-page period summary containing all required reconciliation
  operands;
- full-year transaction dates in nondecreasing source order;
- blank and repeated document references;
- repeated date-and-amount combinations in at least one statement;
- positive, zero, and negative running-balance states;
- exact row-to-row running-balance continuity; and
- exact agreement between parsed row totals, printed totals, opening balance,
  and printed closing accounting balance.

The printed periods share one boundary date. The observed transaction-date
sets do not overlap across the two statements. This is evidence about the
observed period labels only; it does not establish cross-statement transaction
identity or a universal continuity convention.

The v0.1 contract supports only this layout family. Three pages is supporting
evidence, not a recognition rule: pagination is content-driven and a future
synthetic no-transaction case must remain expressible. Any unobserved layout,
column order, extraction behavior, or ambiguous page continuation fails
closed pending a contract revision.

## Contract boundary

The parser owns source recognition, native-text extraction, structural row
grouping, exact financial parsing, and statement reconciliation. It returns
immutable source-specific values and provenance. It does not select an
`Account`, create a `SourceArtifact`, persist a row, create a
`FinancialObservation`, resolve an observation, or write a `Movement`.

The application boundary owns exact-artifact persistence, trusted Account and
source-account comparison, duplicate handling, transactional evidence and
observation persistence, and any later resolution command.

```text
private PDF bytes
-> BCI historical PDF recognition and extraction
-> immutable parser result plus reconciliation checks
-> SourceArtifact / ImportBatch / RawRecord / BCI evidence
-> unresolved FinancialObservation per parsed transaction
-> separate deterministic resolution policy
-> canonical Movement only after accepted resolution
```

## Source recognition

### Strong required markers

A document is recognized as v0.1 only when all of the following hold:

1. The bytes are a valid, readable, unencrypted PDF.
2. Every page has usable native text and the observed US Letter geometry
   family. OCR is not substituted.
3. The provider context identifies BCI and the product heading identifies a
   current-account statement/cartola.
4. Page one contains exactly one coherent metadata block with labels for the
   statement/cartola identifier, account identifier, currency, and period.
5. The period has exactly one parseable start and end and start is not after
   end.
6. The transaction table establishes, in this order, the semantic columns
   `Fecha`, `Sucursal`, `Descripcion`, `N° Documento`,
   `Cheques/Otros Cargos`, `Depositos/Abonos`, and `Saldo Diario`.
7. Every continuation page repeats compatible table-header geometry before
   transaction content.
8. Page numbering is internally complete and ordered from the first through
   the declared final page.
9. The final page contains exactly one recognized period-summary block with
   period, opening balance, total debits, total credits, and final accounting
   balance.
10. Header and final-summary period evidence agree.

Recognition uses normalized structural labels only. It never depends on the
filename, any holder or transaction text, or a particular financial value.

### Optional or supporting markers

These observed elements support diagnostics but are not required for
recognition unless a later source-contract revision promotes them:

- the BCI logo or expanded provider name;
- document-generation timestamp;
- holder, address, email, office, executive, telephone, or plan blocks;
- overdraft/credit-line section;
- retentions and available-balance section;
- legal, help, guarantee, URL, and decorative footer content; and
- the observed three-page count.

Optional text may move within its observed region without changing financial
semantics. It must never be mistaken for a transaction row.

### Rejection conditions

Recognition fails closed for a non-PDF, corrupt or encrypted PDF, image-only
or scanned pages, wrong provider or product, absent or contradictory required
metadata, ambiguous account or currency evidence, missing or reordered table
columns, inconsistent continuation headers, missing or contradictory page
numbers, missing or repeated summary blocks, truncated content, or financial-
looking text outside a recognized transaction-table state.

A valid BCI PDF from an unobserved layout or column geometry is
`source_variant_unsupported`, not a best-effort v0.1 parse. A future extraction
dependency or layout change requires conformance against the private corpus
and synthetic suite before the parser or source version changes.

## Deterministic extraction and provenance

The proposed native-text boundary is `BCI-HIST-PDF-GIR-v1`, a BCI-specific
geometric intermediate representation analogous in discipline, but not in
financial semantics, to the existing Santander PDF boundary. It contains:

- source-ordered pages with one-based ordinals and PDF-point geometry;
- native words with original Unicode text, bounding box, and extraction
  ordinal;
- deterministic physical lines with member token ordinals;
- recognized table-header bands; and
- logical row groups with member line and token ordinals.

The discovery reference profile is `pdfplumber==0.11.8` with
`pdfminer.six==20251107`, reading one page at a time with native text,
`use_text_flow=False`, `keep_blank_chars=False`, `x_tolerance=3pt`,
`y_tolerance=3pt`, and `return_chars=True`. All observed pages are exactly
`612pt x 792pt`; v0.1 accepts that geometry after quantization to `0.01pt`.
These versions are already pinned repository dependencies for Santander PDF
ingestion. The implementation checkpoint may reuse them only after proving
BCI corpus and synthetic conformance for this separate GIR.

Coordinates use top-left origin, x increasing rightward and y downward.
Original token text is Unicode NFC with normalized line endings and ordinary
spaces for non-breaking spaces. Structural recognition keys may use NFKC,
case folding, whitespace collapse, and accent-insensitive comparison, while
original token text and positions remain available for provenance.

Words belong to one physical line when their vertical centers differ by at
most `2.00pt`. Assignment uses the nearest existing line; an exact tie uses
the earlier line. Lines sort by top, then left, then original extraction
ordinal. Header vector lines establish the column bands; transaction content
must fall inside those bands rather than merely appearing in raw text order.

A date token in the established date band starts a transaction row group.
Following description fragments belong to it until the next date-band token,
repeated header, recognized summary/footer boundary, or page end. A table may
continue after a page break only after a compatible repeated header. A single
transaction row split across pages is not proven by the corpus and is
unsupported in v0.1.

Durable field provenance must identify the immutable artifact plus page, row-
group, line, and token ordinals for every extracted financial field. The
artifact remains the exact-text authority; persistence need not duplicate an
arbitrary full-text blob.

## Statement metadata contract

The classification describes the v0.1 extraction and validation boundary.
Optional evidence that is not normalized remains available in the exact
`SourceArtifact`.

| Field | Classification | V0.1 treatment and reason |
| --- | --- | --- |
| Provider | REQUIRED FOR CONTRACT | Must identify BCI; represented by the source kind rather than copied into `Movement`. |
| Product type | REQUIRED FOR CONTRACT | Must identify a current-account historical statement; represented by the source kind. |
| Statement/cartola identifier | REQUIRED FOR CONTRACT | Must be one nonempty ASCII-decimal token; preserve it as private source evidence, but never use it as transaction identity. |
| Period start | REQUIRED FOR CONTRACT | Inclusive statement boundary and required reconciliation context; persist on `ImportBatch`. |
| Period end | REQUIRED FOR CONTRACT | Inclusive statement boundary and required reconciliation context; persist on `ImportBatch`. |
| Currency | REQUIRED FOR CONTRACT | Explicit source currency must map deterministically to `CLP` for the observed variant and equal the trusted Account currency. |
| Source account identity | REQUIRED FOR CONTRACT | Require one ASCII-decimal token, preserving leading zeroes after trimming surrounding whitespace; compare it with identically normalized trusted caller context before observation creation. It is private evidence, never a filename or log field. |
| Masked account identity | OUT OF SCOPE FOR V0.1 | The corpus exposes an unmasked identifier, so no masked-identity semantics are invented. |
| Holder identity | OPTIONAL EVIDENCE | Useful for human audit only; preserve in the artifact and do not normalize or use for Account selection in v0.1. |
| Office and plan metadata | OPTIONAL EVIDENCE | Preserve in the artifact; not transaction, account, or reconciliation semantics. |
| Contact and address metadata | OUT OF SCOPE FOR V0.1 | Sensitive and unnecessary for parsing, binding, or reconciliation. |
| Overdraft/credit-line total | OPTIONAL EVIDENCE | Evidence-only; not a Movement and not a reconciliation operand. |
| Overdraft/credit-line utilized | OPTIONAL EVIDENCE | Evidence-only; not a canonical balance or Movement. |
| Overdraft/credit-line available | OPTIONAL EVIDENCE | Evidence-only; not a canonical balance or Movement. |
| Overdraft/credit-line due date | OPTIONAL EVIDENCE | Evidence-only; no lifecycle model in v0.1. |
| Opening balance | REQUIRED FOR CONTRACT | Required first running-balance operand and statement-summary operand; persist on `ImportBatch`. |
| Printed total debits | REQUIRED FOR CONTRACT | Required to prove parsed debit completeness; persist as BCI statement evidence. |
| Printed total credits | REQUIRED FOR CONTRACT | Required to prove parsed credit completeness; persist as BCI statement evidence. |
| Closing/accounting balance | REQUIRED FOR CONTRACT | Required final running-balance and summary endpoint; persist on `ImportBatch`. |
| Retentions | OUT OF SCOPE FOR V0.1 | Not needed for transaction parsing or accounting-balance reconciliation. |
| Available balance | OUT OF SCOPE FOR V0.1 | Distinct from final accounting balance and not needed for v0.1 reconciliation. |

Provider-specific metadata must not leak into `Movement` or generic
observation lifecycle state.

## Transaction row contract

One logical table row is one source financial claim candidate. Its immutable
parser representation contains:

| Field | Required | Semantics |
| --- | --- | --- |
| Source date text | Yes | Exact `Fecha` cell text. |
| Accounting date | Yes for `PARSED` | Full date parsed from `Fecha`; the running balance proves an account-statement date, not the underlying purchase/authorization time. |
| Transaction date | No | Remains unknown/null in v0.1. |
| Branch/sucursal | Optional | Source evidence only; trim surrounding and repeated layout whitespace. |
| Description | Optional | Join wrapped fragments with one space after preserving exact token provenance; do not classify or rewrite content. |
| Document/reference | Optional | Preserve when present; blank and repeated values are valid and never global identity. |
| Debit/cargo | Conditional | Exact positive source magnitude; exactly one of debit and credit is required. |
| Credit/abono | Conditional | Exact positive source magnitude; exactly one of debit and credit is required. |
| Signed amount | Yes for `PARSED` | `credit - debit`; therefore debit is negative and credit is positive for the asset Account. |
| Running/daily balance | Yes for `PARSED` | Exact source balance after applying this row; may be positive, zero, or negative. |
| Currency | Yes for `PARSED` | Statement currency mapped to `CLP`, not inferred per row. |
| Page ordinal | Yes | One-based physical page containing the row start. |
| Source row ordinal | Yes | One-based logical transaction order across the statement. |
| Line/token ordinals | Yes | Exact artifact-local provenance for every populated field. |

Rows are ordered by page ordinal, then visual top position, with source
extraction ordinal as the deterministic tie-breaker. Equal dates retain this
source order. Description, branch, document/reference, date, and amount are
evidence; no combination of them is a universal economic-event identifier.

## Row classification

Every recognized logical record receives exactly one outcome:

| Outcome | Meaning | Examples |
| --- | --- | --- |
| `PARSED` | A transaction row is structurally and financially unambiguous | valid full date, one positive debit or credit, valid running balance |
| `IGNORED` | Recognized non-transaction structure | page-one metadata, repeated table header, final summary, overdraft block, retentions, legal/footer/help content, layout blank |
| `REJECTED` | Transaction-shaped evidence cannot be interpreted safely | malformed/out-of-period date, missing/both/malformed amount sides, negative directional amount, invalid running balance, ambiguous geometry |

The parser may omit purely geometric whitespace from returned records. If it
emits a blank logical record, it is `IGNORED` with `blank_layout`. Summary
records are transaction-`IGNORED` while their typed values still participate
in statement reconciliation.

Initial stable row reason codes are:

- `transaction_parsed`;
- `metadata`, `table_header`, `page_continuation`, `period_summary`,
  `overdraft_metadata`, `retentions_available`, `footer_legal`, and
  `blank_layout`;
- `date_invalid`, `date_outside_period`, and `date_order_invalid`;
- `amount_missing`, `amount_invalid`, `amount_both_sides`,
  `negative_directional_amount`, `zero_amount_unsupported`, and
  `money_precision_overflow`;
- `running_balance_missing`, `running_balance_invalid`, and
  `row_geometry_ambiguous`.

Any `REJECTED` transaction candidate prevents authoritative reconciliation
because parsed rows can no longer prove statement completeness.

## Exact money rules

- Use `Decimal` throughout; binary floating point is forbidden.
- The observed v0.1 source money grammar is an integer magnitude with optional
  dot thousands groups. Decimal commas, fractional source units, currency
  symbols inside cells, or irregular grouping are unsupported.
- Normalize a valid source integer to a two-decimal Gouda `Decimal` without
  rounding. All persisted money must satisfy the existing 20-digit,
  two-decimal exact-money boundary.
- A transaction requires exactly one populated debit or credit cell, strictly
  greater than zero. Both populated is `amount_both_sides`; neither populated
  is `amount_missing`; zero is `zero_amount_unsupported`.
- Negative printed debit or credit magnitudes are
  `negative_directional_amount`; the parser must not reverse or double-negate
  them. A leading minus is accepted only where a balance field permits it.
- Running, opening, and closing balances may be positive, zero, or negative.
  Printed debit and credit totals are nonnegative magnitudes.
- Overflow, excess scale, or a value not exactly representable by Gouda's
  money field is `money_precision_overflow` and is never rounded.
- Canonical asset-account sign is deterministic: debit/cargo yields a negative
  signed amount and credit/abono yields a positive signed amount, per
  [ADR-0005](../decisions/ADR-0005-canonical-movement-sign-orientation.md).

## Date rules

- Transaction rows accept only the observed full-year `DD/MM/YYYY` format.
- Statement header periods accept only the observed full-year
  `DD-MM-YYYY` pair associated with the period label.
- Dates are Gregorian, must exist, and require no year inference.
- Period boundaries are inclusive. Every parsed row date must be inside them.
- Transaction dates must be nondecreasing in source order; same-day rows are
  ordered by source row ordinal.
- A malformed date is `date_invalid`; a valid date outside the period is
  `date_outside_period`; a backward source date is `date_order_invalid`.
  Each rejects the candidate and prevents authoritative reconciliation.
- The row `Fecha` is persisted as `FinancialObservation.accounting_date` and
  `transaction_date` remains null. This source-specific mapping reflects the
  row's direct participation in the account running balance; it makes no
  universal claim about purchase, authorization, or occurrence time.

## Reconciliation contract

Reconciliation is computed from parsed exact values, never from display-
rounded floats. The parser returns each check independently with stable reason
codes and one aggregate status.

### Required checks

`A. running_balance_continuity`

- First row: `opening_balance + first_signed_amount = first_running_balance`.
- Later rows: `previous_running_balance + signed_amount = running_balance`.
- Continue through page breaks in global source-row order.

`B. summary_balance_equation`

- `opening_balance + printed_total_credits - printed_total_debits =
  printed_closing_balance`.

`C. parsed_totals_match_printed`

- Sum of parsed debit magnitudes equals printed total debits.
- Sum of parsed credit magnitudes equals printed total credits.

`D. final_running_balance_matches`

- The last parsed running balance equals the printed closing accounting
  balance.
- For a valid zero-transaction statement, printed debit and credit totals must
  be zero and opening must equal closing; check A has no rows and check D uses
  the opening balance as the effective last balance.

`E. period_continuity_metadata`

- This is a separate cross-batch diagnostic, not a statement arithmetic check
  and not transaction identity.
- Adjacent statements may report a shared boundary date in the observed
  family. Exact equality, next-day adjacency, gaps, and overlaps are reported
  explicitly without changing either statement's self-reconciliation status.
- No cross-batch row is matched, suppressed, or created from this metadata.

Check E belongs to an application-level comparison of already parsed batches.
It is not part of the pure single-document parser's aggregate A-D result and
does not change `ImportBatch.reconciliation_status`.

### Aggregate statuses

| Status | Meaning | Canonical consequence |
| --- | --- | --- |
| `RECONCILED` | Required contract metadata is present, no transaction candidate is rejected, and A-D all pass exactly | Parsed observations are eligible for the separate historical resolution policy. |
| `NOT_RECONCILED` | All required operands and transaction candidates are parseable, but one or more exact equations disagree | Preserve evidence and observations; no automated canonicalization. |
| `INSUFFICIENT_DATA` | The document is recognized enough to preserve evidence, but a required reconciliation operand or transaction candidate is missing, malformed, ambiguous, or truncated | Preserve safely parsed evidence and observations; no automated canonicalization. |
| `NOT_APPLICABLE` | Reconciliation was not attempted because the artifact did not reach a supported statement parse, or an exact-artifact duplicate was short-circuited | No financial observations from that attempt. |

Recognition-fatal errors may prevent a materialized batch under current
`ImportBatch` rules. Where safe source identity is established, the
`SourceArtifact` and fatal attempt remain preserved. Parsed observations from
`NOT_RECONCILED` or `INSUFFICIENT_DATA` batches stay `UNRESOLVED`; they never
affect canonical totals.

## Observation creation policy

Observation creation is an application-service step after evidence
persistence, not parser behavior.

1. The caller supplies an existing trusted asset `Account` and a trusted
   expected BCI source-account identifier. Neither is selected from holder,
   filename, description, or other untrusted PDF text.
   The trusted identifier must come from configuration or explicit human
   input independent of the artifact; the application must never copy the
   parser result into both sides of the comparison.
2. The application compares the exact normalized source-account identifier
   and explicit source currency against that trusted context. A mismatch
   stops before observation creation and is never logged with the identifiers.
3. Each `PARSED` transaction `RawRecord` creates one initially `UNRESOLVED`
   `FinancialObservation` with:
   - trusted Account;
   - null `transaction_date` and parsed `accounting_date`;
   - exact signed amount and Account currency;
   - whitespace-only normalized description and optional source reference;
   - `interpretation_method = bci_historical_current_account_pdf`;
   - `interpretation_version = bci-historical-current-account-pdf-v1`; and
   - its own parsed `RawRecord`.
4. Observation idempotency is an explicit UUID command identity derived from
   non-financial internal identifiers: a repository-owned UUID namespace plus
   `RawRecord.id`, Account id, interpretation method, and interpretation
   version. It must not include source amounts, dates, descriptions,
   references, account numbers, or other private financial values.
5. A corrected interpretation requires a new interpretation version and new
   observation, followed by the existing supersession service. V0.1 does not
   correct or retract a canonical `Movement`.

## Historical resolution policy

The initial source-specific policy is deliberately conservative:

- The parser and evidence persistence transaction create no `Movement`.
- `NOT_RECONCILED` and `INSUFFICIENT_DATA` observations remain unresolved.
- A contract-valid `RECONCILED` statement makes its parsed observations
  eligible for deterministic resolution in source-row order; it does not make
  them Movements by model invariant.
- `CONFIRM_NEW` may be called only after the policy has re-read the reconciled
  batch and Account under the existing Account-scoped resolution transaction.
  It supplies the observation accounting date as the source-specific Movement
  occurrence date.
- The generic exact account/date/amount/currency collision guard remains on.
  A collision with evidence from another batch or source causes abstention and
  leaves the observation unresolved.
- The source policy may explicitly set `allow_exact_collision=True` only when
  every colliding canonical Movement originated from a different parsed row
  of the same reconciled historical statement and no external-batch/source
  candidate is present. The independently ordered source rows and exact
  running-balance chain then prove separate statement entries. The override
  does not make the tuple an identity key and never matches the observation to
  an earlier Movement.
- V0.1 performs no automatic `MATCH_EXISTING`. That command is available only
  after a caller or later BCI-specific policy has explicitly selected a
  compatible existing Movement using evidence outside the generic service.
  Generic Account, currency, and amount compatibility checks still apply.
- No description, reference, date, or period tuple authorizes matching. No
  fuzzy comparison or universal duplicate identity is introduced.
- A historical contradiction may leave an observation unresolved or mark it
  `CONFLICT` only against a known Movement. It never changes the Movement.

Automated accepted transitions use decision source `DETERMINISTIC_POLICY`,
policy name `bci_historical_reconciled`, policy version `v1`, and stable reason
codes distinguishing ordinary new confirmation from independently proven
same-batch collision override. Human-selected matches use decision source
`HUMAN` and an explicit reason; no parser result may impersonate human
confirmation.

This policy can materialize a new, internally complete historical statement
while abstaining at cross-batch or cross-source collisions. Canonical totals
continue to read `Movement` only.

## Deferred cross-source questions

V0.1 does not parse or define policy for BCI Current Cartola or Recent
Movements. The following require direct same-transaction rollover evidence:

- whether any source reference is stable across variants;
- how `Fecha` relates to Current transaction and accounting dates;
- safe date-window candidate generation;
- description normalization useful only as a hint;
- whether running balances or period containment can disambiguate candidates;
- how disappearing or changed open-period rows relate to closed statements;
- when a Historical observation should `MATCH_EXISTING` rather than
  `CONFIRM_NEW`; and
- what a corrected historical statement means for an existing Movement.

No permanent identity, supersession, or canonical-correction rule is frozen by
this contract.

## Overdraft and line-of-credit evidence

The observed page-one header contains a labeled overdraft/credit-line block
with total, utilized, available, and due-date facts. It is structurally
separate from the transaction table and final accounting-balance summary.

For v0.1 these fields are evidence-only in the exact artifact. They are not
required for recognition or reconciliation, do not create observations or
Movements, and do not justify debt, facility, credit-line, or transfer models.
They are a future domain candidate only after a product use case and source
lifecycle are established.

## Proposed parser API

The smallest parser boundary is a BCI-specific package, not a provider plugin
framework:

```python
extract_bci_historical_pdf(source) -> BciHistoricalPdfGir
parse_bci_historical_pdf_gir(gir) -> BciHistoricalParseResult
parse_bci_historical_pdf(source) -> BciHistoricalParseResult
```

The result uses frozen, non-sensitive `repr` dataclasses:

- `BciHistoricalStatementMetadata`: statement id, period, currency, source
  account identity, opening balance, printed totals, closing balance, and field
  provenance;
- `BciHistoricalSourceRecord`: outcome, reason codes, page and row ordinals,
  source date/accounting date, branch, description, reference, debit, credit,
  signed amount, running balance, and field provenance;
- `BciHistoricalReconciliationCheck`: check name, status, difference when
  meaningful, reason code, and operand provenance;
- `BciHistoricalReconciliation`: aggregate status plus single-document checks
  A-D; and
- `BciHistoricalParseResult`: `RECOGNIZED` or `FATAL`, provider/product,
  source variant, parser/GIR/extraction-profile versions, metadata, ordered
  records, reconciliation, and stable errors.

Sensitive values are excluded from object representations and logs. Parser
input is bytes or a binary stream; path and filename do not enter recognition.
The same bytes and parser/extraction versions must return equivalent results.

## Persistence and application integration

The generic domain boundary remains unchanged:

- reuse exact-byte `SourceArtifact`;
- reuse one adapter-attempt `ImportBatch`;
- reuse one `RawRecord` per logical parser record;
- create one `FinancialObservation` per parsed transaction;
- reuse `ObservationResolution`; and
- leave canonical `Movement` and `Movement.raw_record` unchanged.

The later implementation requires an additive migration, but no generic domain
redesign:

1. register one BCI Historical value in `ImportBatch.SourceKind` and its
   database allow-list;
2. register one BCI Historical value in `RawRecord.RecordKind`, its allow-list,
   source-kind compatibility, and source-specific shape; and
3. add two narrow evidence models:
   - one protected one-to-one batch evidence row for statement identifier,
     private source-account identity, explicit currency, printed debit and
     credit totals, extraction/GIR versions, explicit A-D check outcomes and
     reason codes, and metadata/reconciliation provenance; and
   - one protected one-to-one record evidence row for page/row-group/line/token
     provenance and the source-native row fields needed to audit sign and
     running-balance reconciliation.

`ImportBatch` already owns Account, period, opening/ending balances, aggregate
reconciliation status/difference, counts, parser version, and source variant;
those values should not be redundantly added to the BCI batch evidence model.
The exact artifact remains the authority for optional holder, contact,
office/plan, overdraft, retentions, available-balance, and legal text, so those
fields do not justify columns or models in v0.1.

No BCI binding, authority, confidence, workflow, processing-run, economic-
event, or generic metadata model is required. The first application API may
accept trusted expected account identity as explicit protected caller context;
a durable BCI account-binding model requires a separate demonstrated product
need.

## Failure behavior

| Failure | Deterministic behavior |
| --- | --- |
| Not a PDF | Preserve received artifact when ingestion owns it; fatal `pdf_invalid`. |
| Corrupted PDF | Fatal `pdf_invalid`; no rows, observations, or Movements. |
| Encrypted PDF | Fatal `pdf_encrypted_unsupported`; do not request or guess a password. |
| Image-only/scanned PDF | Fatal `native_text_required`; OCR is outside v0.1. |
| Wrong bank or product | Fatal `source_identity_mismatch`; do not route as BCI Historical. |
| Unsupported BCI format | Fatal `source_variant_unsupported`; no best-effort financial parse. |
| Missing statement period | Fatal `period_missing` or `period_invalid`; no observations. |
| Malformed transaction section | Fatal when table state/geometry is unrecognized; otherwise retain candidate as `REJECTED` and reconciliation `INSUFFICIENT_DATA`. |
| Truncated statement | Fatal for broken pagination or missing summary; preserve artifact and safe failure evidence only. |
| Reconciliation failure | Preserve parsed rows and unresolved observations; create no Movement automatically. |
| Account mismatch | Fail at application boundary before observations; retain artifact/attempt without exposing identifiers. |
| Duplicate exact artifact | Reuse existing `SourceArtifact`; create a `DUPLICATE` attempt under existing semantics and no duplicate rows/observations/Movements. |
| Parser exception | Convert only expected parser failures to stable sanitized codes; unexpected exceptions roll back the attempt transaction and expose no source content. |

## Synthetic implementation test matrix

All fixtures must be generated from wholly synthetic names, identifiers,
descriptions, references, amounts, balances, and contact data. No fixture may
be derived by redacting or editing a private statement.

| Case | Required assertions |
| --- | --- |
| Normal multi-row statement | Recognized layout, ordered rows, immutable provenance, exact A-D reconciliation. |
| Debit row | Positive source debit magnitude produces negative signed amount. |
| Credit row | Positive source credit magnitude produces positive signed amount. |
| Repeated identical date/amount rows | Both source rows survive; same-batch reconciled policy can explicitly confirm both as distinct. |
| Document/reference collisions | Repeated references survive and do not deduplicate or match rows. |
| Blank document/reference | Row remains parsed when all financial fields are valid. |
| Page-boundary table continuation | Repeated header is ignored; row ordering and running balance continue across pages. |
| Exact reconciliation | A-D pass and aggregate is `RECONCILED`. |
| Broken running balance | Check A fails, aggregate `NOT_RECONCILED`, observations remain unresolved. |
| Wrong printed totals | Check C or B fails as applicable; no automated canonicalization. |
| Closing-balance mismatch | Check D fails independently. |
| Missing reconciliation operand | Aggregate `INSUFFICIENT_DATA`; preserve safe parsed observations unresolved. |
| Malformed amount | Candidate `REJECTED` with stable reason; no observation for that row. |
| Both debit and credit | Candidate `REJECTED`; never calculate a net value. |
| Neither debit nor credit | Transaction-shaped candidate `REJECTED`. |
| Negative directional amount | Candidate `REJECTED`; no sign reversal. |
| Zero transaction amount | Candidate `REJECTED`; zero balances remain allowed. |
| Precision/overflow | Candidate rejected without rounding. |
| Malformed date | Candidate `REJECTED` with `date_invalid`. |
| Out-of-period date | Candidate `REJECTED` with `date_outside_period`. |
| Backward date order | Candidate rejected and reconciliation cannot be authoritative. |
| Unsupported layout/version | Fatal fail-closed result with no financial output. |
| Non-PDF or corrupted input | Stable fatal result and no financial output. |
| Encrypted or image-only PDF | Stable unsupported fatal result; no OCR or password fallback. |
| Wrong provider/product | Source-identity fatal result; no BCI records. |
| Missing/contradictory period | Fatal result; no observations. |
| Truncated pagination/summary | Fatal result with no partial financial persistence. |
| Statement with no transactions | Zero printed totals and equal opening/closing reconcile; no observations. |
| Overdraft metadata | Recognized as evidence-only/ignored and never becomes an observation or Movement. |
| Account mismatch | No observations or Movements and no identifier in logs/errors. |
| Exact artifact retry | Existing duplicate behavior creates no duplicate financial records. |
| Sanitized parser exception | No partial batch records, observations, or source content in the error. |
| Reconciliation-gated resolution | Only `RECONCILED` batch observations enter automatic `CONFIRM_NEW`. |
| Cross-batch exact collision | Default abstention; no implicit match and no second Movement. |
| Same-batch real collision | Explicit source-policy override creates the independently proven second row Movement. |
| Canonical totals | Unresolved/rejected evidence has no effect; totals read `Movement` only. |
| Privacy leakage | Captured logs, exception text, snapshots, fixture strings, and version-control diff contain none of the private-corpus literals or paths. |

Implementation tests should separately cover pure extraction/parser behavior,
PostgreSQL evidence and observation persistence, duplicate/account locking,
resolution gating, exact-collision handling, transaction rollback, migration
drift, and the unchanged Santander regression suites.

## Explicit non-goals

This contract does not implement BCI Current Cartola or Recent Movements,
cross-source matching, fuzzy search, AI interpretation, a generic PDF adapter,
a workflow/rule engine, universal transaction identity, a provisional ledger,
confidence or authority scores, canonical Movement correction, overdraft
domain models, or changes to Santander production behavior.
