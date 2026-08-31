# Current task

## Objective

Acquire the Historical statement needed to observe the captured open Current
Cartola period rolling into a closed period.

The source-only contract checkpoint is complete. Legacy XLS inspection tooling
is available through the pinned `xlrd==2.0.1` dependency.

## Current state

BCI Historical Current Account PDF v0.1 is implemented and validated. The
source-only contracts `bci_current_cartola_v0.1` and
`bci_recent_movements_v0.1` are frozen and implemented as pure source parsers
with synthetic tests and sanitized private validation. Current and Recent now
require trusted nonblank artifact identity and preserve it in field
provenance; Recent also records the selected Cargo or Abono source header and
coordinate. No stable cross-source identity rule or canonical Movement
correction has been frozen.

The existing two Historical statements cover none of the Current capture and
only a partial Recent subset. No available statement covers the complete open
capture.

Current Cartola is the preferred normal open-period source. Recent Movements
is retained as research and diagnostic support, not as a coexisting production
pipeline. This source selection is not an identity or lifecycle rule.

The one-time T2 paired challenge is complete. T2 Current has 27 parsed rows and
an exact 26-step balance chain. Every contemporaneous T2 Recent accounting-date
candidate has exactly one Current candidate; Recent's other 23 rows are older
than Current's parsed range. Recent remains at 50 rows while its oldest
boundary advances, strongly supporting a rolling fixed-size shape without
proving a service cap. One shared T1/T2 Current candidate signature changes
description, opaque series, and row balance; it remains unresolved source
volatility rather than a transaction identity.

## Constraints

Preserve private evidence outside tracked files, keep generic
observation/resolution and Movement semantics unchanged, and do not infer
cross-source identity, lifecycle, deduplication, or canonical sign behavior
from parser outputs.

## Next action

After closure, retain the Historical statement whose intrinsic printed period
covers all Current source dates. Then run a read-only Current-to-Historical
candidate experiment, including the one volatile T1/T2 candidate signature.
Do not resume routine Recent capture and do not begin identity or lifecycle
design.
