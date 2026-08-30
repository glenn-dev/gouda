# BCI current-account source lifecycle

## Purpose and scope

This note records sanitized observations from a read-only comparison of BCI
current-account source variants. It contains no private filenames, account
identifiers, descriptions, references, amounts, or balances.

The observations motivate Gouda's evidence and resolution architecture. The
Historical source now has a narrow deterministic design contract in
[the BCI historical PDF contract](../contracts/bci-historical-current-account-pdf-v0.1.md).
The Current and Recent source variants now have separate source-only contracts:
[Current Cartola](../contracts/bci-current-cartola-v0.1.md) and
[Recent Movements](../contracts/bci-recent-movements-v0.1.md). This lifecycle
note selects Current Cartola as the preferred normal open-period source. Recent
Movements remains research and diagnostic support rather than a second
operational pipeline. This selection does not freeze a transaction identity
algorithm or authorize open-period ingestion.

The v0.1 Historical route is implemented as a native-text, geometry-aware
evidence-first import. It creates unresolved observations from reconciled or
non-reconciled parsed rows; only the separate conservative Historical policy
may confirm a reconciled row as a new canonical Movement. Recent and Current
source contracts are frozen and implemented as pure source parsers. Their
lifecycle routes remain unimplemented.

## Observed source roles

### Recent Movements

The Recent Movements source is a rolling or recent activity view. It provides
timely transaction evidence and two source-native dates but is not a
closed-period statement. It is retained as an alternative research and
diagnostic source, not as a coexisting normal open-period pipeline.

### Current Cartola

The Current Cartola source represents an open statement period. It provides a
current accounting view before the period has closed. It is the preferred
normal open-period source strategy, subject to the falsification conditions
below.

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

## Open-period source strategy

Current Cartola is preferred over Recent Movements for normal open-period
acquisition. The decision prioritizes source fidelity and completeness before
format maintainability and download simplicity.

| Criterion | Current Cartola | Recent Movements | Assessment |
| --- | --- | --- | --- |
| Same-capture open-period coverage | 23 rows across 10 source dates in the observed open tail | One unique accounting-date/direction/magnitude candidate for each of those 23 rows, plus 27 older rows already inside the available Historical period | No observed Recent advantage for the uncovered open tail. Candidate alignment is not identity. |
| Temporal depth | Period-scoped open view; observed source-date span is 18 days | Rolling view; observed accounting and transaction-date spans are each 35 days | Recent is deeper, but its extra observed depth duplicates a closed-period coverage window rather than extending the open tail. |
| Source-native transaction evidence | One unresolved source date, description, opaque series, signed source amount, and per-row accounting balance | Distinct transaction and accounting dates, description, and Cargo/Abono magnitude; no row balance or reference | Current carries stronger row-level validation evidence. Recent carries stronger date-disambiguation evidence. |
| Historical comparison | No direct Current-to-Historical rollover is available | Accounting date produces 27 strong Historical candidates, compared with 12 using transaction date | Recent is stronger for the partial lifecycle experiment, but this does not establish identity or make it the better ongoing open source. |
| Internal financial validation | All 22 observed adjacent running-balance equations hold; the newest row balance agrees with the Current snapshot accounting balance | Only snapshot balances are present, and v0.1 deliberately does not extract them; no per-row balance exists | Current is materially stronger for detecting row or ordering anomalies inside one artifact. |
| Reference evidence | `Serie` exists on every observed row but remains opaque | No row reference field | Current retains potentially useful evidence, without claiming identity semantics. |
| Format and parser burden | Legacy CFB/XLS, pinned `xlrd==2.0.1`, and BIFF formula-record inspection | OOXML/XLSX with direct cell discovery, merge handling, and a misleading declared dimension | Recent is easier to maintain. Current's fidelity advantage is accepted despite this cost. |
| Operational shape | One period-scoped download for the open period | One rolling/recent download whose observed 50-row extent may or may not be a service limit | Both are one download. A rolling-view truncation risk is plausible but unproven. |

The observed Recent workbook contains exactly 50 rows. That is direct evidence
of this artifact's extent, not proof of a fixed service cap. Likewise, one
Current artifact does not prove universal open-period completeness. The
selection should be revisited if a future capture shows that Current omits
same-period evidence retained by Recent, Current is capped or unreliable, its
balance chain fails, or Current source dates fail to behave usefully at
Historical rollover while Recent accounting dates remain stable.

Choosing Current means the normal open-period path does not retain Recent's
explicit transaction date, explicit accounting-date label, or Cargo/Abono
column identity. Those fields remain valuable for research, especially date
analysis, but the present evidence does not show them to be essential for
normal open-period acquisition: each observed Current row has a unique Recent
candidate on Recent accounting date plus source-native direction and magnitude,
and the Current rows add per-row balances and series evidence. Recent's older
rows are also covered by the candidate closed-period source, Historical.

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

## Historical coverage checkpoint

A read-only intrinsic-date comparison was performed without using filename
dates. The private corpus contains two recognized, exactly reconciled
Historical statements:

- neither printed Historical period contains any of the 23 Current Cartola
  rows or any of its 10 distinct source dates;
- the newer Historical period contains 27 of the 50 Recent Movements rows by
  `Fecha Contable`, spanning 10 distinct accounting dates;
- the same period contains 27 Recent rows by `Fecha Transacción`, spanning 13
  distinct transaction dates;
- the remaining 23 Recent rows, including 10 distinct accounting dates, fall
  after the latest available Historical period; and
- no available Historical statement covers the complete Current or Recent
  capture.

The partial Recent-to-Historical coverage can test candidate behavior for that
subset. It cannot test Current-to-Historical rollover, the uncovered Recent
tail, or changes between an open period and its final statement.

## Minimum rollover evidence protocol

The smallest useful operational evidence set is now one same-account
Current-to-Historical capture chain:

1. Retain the existing Current Cartola artifact as the first open-period
   snapshot. Retain the existing paired Recent artifact as research evidence,
   not as an operational dependency. Treat exact bytes as evidence and
   filenames as non-evidence.
2. If Current Cartola still contains source dates from that first snapshot,
   capture one additional Current Cartola snapshot as close to period closure
   as practical from the same trusted account context.
3. After closure, download the Historical statement whose own printed period
   contains all source dates from the Current captures. Verify coverage from
   parsed statement metadata, not from its filename.
4. If that Historical statement is already available, retain it immediately.
   A missed second open-period snapshot must be recorded as an evidence gap;
   it cannot be reconstructed from the closed statement.

One additional paired Current/Recent capture is still useful if it can be made
consecutively at the second snapshot. It is a one-time selection challenge,
not part of the normal acquisition protocol. It should test whether Current
continues to cover the contemporaneous open tail, whether Recent appears
truncated, and whether their candidate alignment persists in a later or
higher-activity sample. After that challenge, future acquisition can use only
Current and the corresponding Historical statement unless a falsification
condition occurs.

For every capture, keep a private acquisition note outside tracked fixtures
and documentation containing:

- an opaque trusted same-account context;
- capture timestamp and timezone;
- source variant and download order;
- an immutable exact-byte artifact identity or digest; and
- whether the Current capture still overlapped the first capture's source
  dates.

The protocol does not require a persistence change. It preserves evidence for
a later read-only experiment only.

## Candidate-analysis method

The later experiment should validate each artifact independently with its
frozen parser, preserve source order, and compare candidate sets rather than
forcing one-to-one matches.

Primary candidate dimensions are:

- Current `source_date`, source-sign category, and amount magnitude;
- Recent `accounting_date`, `source_direction`, and `source_amount`;
- Historical `accounting_date`, debit/credit side, and magnitude; and
- artifact-local row order and provenance.

Recent `transaction_date` is a separate comparison dimension, not a substitute
for `accounting_date`. Repeated date/direction/magnitude keys remain ambiguous.
Zero Current amounts have no supported Recent or Historical counterpart and
must remain unmatched rather than being coerced.

For each candidate set, report only sanitized counts and equality results for:

- exact and differing dates across source-native date fields;
- direction and magnitude continuity;
- exact and whitespace-only-normalized descriptions;
- exact, blank, repeated, or changed Current series and Historical references;
- Current row-balance continuity, Current/Recent snapshot-balance equality,
  and exact balance endpoints visible in Historical;
- source row counts and source order; and
- candidates unmatched, newly appearing, changed, or participating in a
  possible one-to-many or many-to-one amount grouping.

One-to-many and many-to-one analysis may enumerate only bounded same-direction
groups whose exact magnitudes sum and whose source dates are within the
observed candidate window. Such groups are hypotheses, not split/merge facts.
Description or reference similarity may rank inspection candidates but may
not establish identity.

Directly observable facts are source fields, parser outcomes, provenance,
printed period containment, exact equality, row order, row counts, and balance
equations within one artifact. Candidate signatures and bounded sum groups are
analysis heuristics. Current `Fecha` becoming Historical accounting date,
Cargo/Abono or Current sign continuity, series/reference persistence, and
open-row rollover are hypotheses until the missing capture chain is observed.

The evidence available today is insufficient to freeze cross-source identity,
deduplication, disappearance, change, split/merge, balance supersession,
lifecycle resolution, or canonical Movement rules.

## Architectural implication

Current open-period evidence may eventually support an explicitly
provisional view. Later closed-period evidence may confirm or supersede its
accounting interpretation while all source evidence remains auditable.

This lifecycle is a concrete reason to place interpreted observations and
resolution before canonical `Movement`. The source-strategy recommendation
does not authorize BCI ingestion or define final matching rules. An ADR should
be created before operational integration is authorized, after the one-time
selection challenge or direct Current-to-Historical rollover evidence can be
reviewed.

## Open questions

- Which fields, if any, remain stable across an observed current-to-historical
  rollover?
- What collision rate would candidate matching produce across periods and
  source variants?
- When can a match be resolved deterministically, and when is human review
  required?
- Which provisional product views are useful without implying closed-period
  authority?
- Does one additional pre-close snapshot show rows disappearing or changing
  before the closed statement is produced?
- Does the closed statement preserve, split, merge, or omit open-period rows,
  and can any such behavior be distinguished from candidate ambiguity?
