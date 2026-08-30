# Current task

## Objective

Perform a joint BCI current-account source-boundary checkpoint across
Historical, Current Cartola, and Recent Movements, confirming contract/parser
consistency and identifying the next bounded lifecycle evidence task.

The source-only contract checkpoint is complete. Legacy XLS inspection tooling
is available through the pinned `xlrd==2.0.1` dependency.

## Current state

BCI Historical Current Account PDF v0.1 is implemented and validated. The
source-only contracts `bci_current_cartola_v0.1` and
`bci_recent_movements_v0.1` are frozen and implemented as pure source parsers
with synthetic tests and sanitized private validation. No stable cross-source
identity rule or canonical Movement correction has been frozen.

## Constraints

Preserve private evidence outside tracked files, keep generic
observation/resolution and Movement semantics unchanged, and do not infer
cross-source identity, lifecycle, deduplication, or canonical sign behavior
from parser outputs.

## Next action

Compare all three frozen BCI boundaries and implementations for consistency,
then identify the smallest evidence-gathering checkpoint needed before any
lifecycle policy is designed or implemented.
