# Current task

## Objective

Complete the narrow provenance-conformance correction identified by the joint
BCI current-account source-boundary checkpoint.

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

## Constraints

Preserve private evidence outside tracked files, keep generic
observation/resolution and Movement semantics unchanged, and do not infer
cross-source identity, lifecycle, deduplication, or canonical sign behavior
from parser outputs.

## Next action

After review and commit of this provenance-only correction, acquire a
same-account Historical statement whose intrinsic printed period covers the
existing Current Cartola source dates. Compare it read-only as candidate
evidence without defining identity, deduplication, or canonical semantics.
