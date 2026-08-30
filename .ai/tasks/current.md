# Current task

## Objective

Acquire the minimum same-account BCI evidence chain needed to observe one open
Current/Recent period rolling into its Historical statement.

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

## Constraints

Preserve private evidence outside tracked files, keep generic
observation/resolution and Movement semantics unchanged, and do not infer
cross-source identity, lifecycle, deduplication, or canonical sign behavior
from parser outputs.

## Next action

If the existing Current period is still open, capture one additional
same-account Current Cartola and Recent Movements pair before closure. Then
retain the Historical statement whose intrinsic printed period covers all
existing Current source dates and the uncovered Recent accounting-date tail.
If the statement is already available, capture it now and record that a second
pre-close snapshot is unavailable. Do not begin identity or lifecycle design.
