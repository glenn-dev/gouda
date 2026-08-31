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
| Same-capture open-period coverage | T1 has 23 rows; T2 has 27 | At both captures, every Current row has exactly one accounting-date/direction/magnitude candidate; T2 has 23 additional older rows outside Current's parsed date range | No observed Recent advantage for either contemporaneous open tail. Candidate alignment is not identity. |
| Temporal depth | Period-scoped open view; source-date span grows from 18 to 24 days | Rolling view; accounting-date span grows from 35 to 40 days | Recent is deeper, but its extra T2 depth remains older than Current's parsed window. |
| Source-native transaction evidence | One unresolved source date, description, opaque series, signed source amount, and per-row accounting balance | Distinct transaction and accounting dates, description, and Cargo/Abono magnitude; no row balance or reference | Current carries stronger row-level validation evidence. Recent carries stronger date-disambiguation evidence. |
| Historical comparison | No direct Current-to-Historical rollover is available | Accounting date produces 27 strong Historical candidates, compared with 12 using transaction date | Recent is stronger for the partial lifecycle experiment, but this does not establish identity or make it the better ongoing open source. |
| Internal financial validation | All 22 T1 and all 26 T2 adjacent running-balance equations hold | Only snapshot balances are present, and v0.1 deliberately does not extract them; no per-row balance exists | Current is materially stronger for detecting row or ordering anomalies inside one artifact. |
| Reference evidence | `Serie` exists on every observed row but remains opaque | No row reference field | Current retains potentially useful evidence, without claiming identity semantics. |
| Format and parser burden | Legacy CFB/XLS, pinned `xlrd==2.0.1`, and BIFF formula-record inspection | OOXML/XLSX with direct cell discovery, merge handling, and a misleading declared dimension | Recent is easier to maintain. Current's fidelity advantage is accepted despite this cost. |
| Operational shape | One period-scoped download that grows from 23 to 27 rows between captures | Both captures contain exactly 50 rows; T2 replaces four oldest-boundary candidate signatures with four newer candidates | Recent strongly resembles a fixed-size rolling window, but no explicit hard-cap marker has been observed. |

Both observed Recent workbooks contain exactly 50 rows. Between T1 and T2, four
oldest-boundary accounting-date/direction/magnitude candidates disappear and
four newer candidates appear while the common candidate order remains stable.
This is strong evidence of a fixed-size rolling shape, but it is not proof of
a documented service cap. Current grows by four rows, retains all 23 T1
candidate signatures in source order, and adds four T2 candidates. Two
captures still do not prove universal open-period completeness. The selection
should be revisited if a future capture shows that Current omits same-period
evidence retained by Recent, Current is capped or unreliable, its balance
chain fails, or Current source dates fail to behave usefully at Historical
rollover while Recent accounting dates remain stable.

Choosing Current means the normal open-period path does not retain Recent's
explicit transaction date, explicit accounting-date label, or Cargo/Abono
column identity. Those fields remain valuable for research, especially date
analysis, but the present evidence does not show them to be essential for
normal open-period acquisition: each observed Current row has a unique Recent
candidate on Recent accounting date plus source-native direction and magnitude,
and the Current rows add per-row balances and series evidence. Recent's older
rows are also covered by the candidate closed-period source, Historical.

## T2 source-selection falsification checkpoint

The one-time paired T2 challenge did not falsify the Current preference. The
comparison window was defined from parsed evidence as the inclusive minimum to
maximum T2 Current `source_date` range; filenames were not used as source-date
evidence.

Direct parser and source-local observations are:

- Current recognizes 27 transaction rows over 13 distinct source dates and a
  24-day span, with no rejected row;
- Recent recognizes 50 transaction rows over 22 distinct accounting dates and
  a 40-day accounting-date span, with no rejected row;
- every one of the 27 Current rows has exactly one Recent candidate using
  accounting date, compatible source direction, and magnitude;
- all 27 Recent rows inside the Current date range have exactly one Current
  candidate, no Recent accounting-date row is newer than the Current maximum,
  and the remaining 23 Recent rows are older than the Current minimum;
- using Recent transaction date instead leaves 12 Current rows without a
  candidate, yields 14 unique candidates, and makes one Current candidate
  ambiguous between two Recent rows; and
- only 4 of the 27 accounting-date candidates have equal descriptions after
  limited text normalization, confirming that description equality is weak
  evidence.

Across captures, all 23 T1 Current candidate signatures remain in T2 and four
new signatures appear; no T1 signature disappears. Twenty-two of the 23
shared unique candidate signatures retain equal descriptions, opaque series,
and row balances. One shared candidate signature changes all three fields even
though its date, source-sign category, and magnitude signature remains present.
The corresponding Recent candidate retains its transaction date and
description. This is direct evidence of open-source field volatility, not
proof that the two rows are one transaction or that either representation is
more authoritative. It weakens any use of `Serie`, description, or row balance
as stable identity evidence but does not show a contemporaneous financial
observation omitted by Current. Both Current balance chains remain internally
exact.

The result therefore confirms Current Cartola as the preferred normal
open-period source under the existing fidelity-first criteria. Routine paired
Current/Recent capture can stop. Recent remains available only for a targeted
diagnostic if later evidence triggers one of the falsification conditions.

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

- neither printed Historical period contains any T1 or T2 Current Cartola row;
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

The smallest useful operational evidence set is one same-account
Current-to-Historical capture chain. Its open-period captures are complete:

1. Retain the T1 and T2 Current Cartola artifacts as the two open-period
   snapshots. Retain their paired Recent artifacts as completed research
   evidence, not as an operational dependency. Treat exact bytes as evidence
   and filenames as non-evidence.
2. When a new Historical statement becomes naturally available, retain it and
   verify whether its own printed period contains the Current source dates.
   Coverage comes from parsed statement metadata, not from its filename.
3. If the printed period covers the retained Current dates, resume the
   read-only rollover candidate experiment. Otherwise keep validation deferred
   until a covering statement becomes available.

The one-time paired Current/Recent selection challenge is complete. Future
routine acquisition should use Current and the corresponding Historical
statement only. Another Recent capture is warranted only if contradictory
evidence triggers a documented falsification condition.

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

## Historical publication cadence

BCI operationally emits only three Historical current-account statements per
year. As of August 2026, no available Historical statement covers the retained
T1/T2 Current dates. No exact future publication date is established by the
repository evidence.

Current-to-Historical rollover validation is therefore an event-triggered,
deferred evidence task rather than a development blocker. Gouda development
continues independently. Resume the validation only when a new Historical
artifact becomes naturally available and its intrinsic printed period covers
the retained Current dates. This cadence does not weaken the Current source
preference or authorize lifecycle, identity, deduplication, persistence, or
canonical behavior.

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
does not authorize BCI ingestion or define final matching rules. The T2
challenge resolves the bounded open-source preference but not rollover. An ADR
remains deferred until direct Current-to-Historical evidence can be reviewed
and should be created before operational integration is authorized.

## Open questions

- Which fields, if any, remain stable across an observed current-to-historical
  rollover?
- What collision rate would candidate matching produce across periods and
  source variants?
- When can a match be resolved deterministically, and when is human review
  required?
- Which provisional product views are useful without implying closed-period
  authority?
- Does Historical preserve or clarify the one T1-to-T2 candidate signature
  whose Current description, opaque series, and row balance changed?
- Does the closed statement preserve, split, merge, or omit open-period rows,
  and can any such behavior be distinguished from candidate ambiguity?
