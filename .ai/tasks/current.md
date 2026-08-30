# Current task

## Objective

Implement the remaining frozen BCI Current Cartola source-parser contract
using synthetic fixtures and deterministic tests, without persistence or
lifecycle semantics.

The source-only contract checkpoint is complete. Legacy XLS inspection tooling
is available through the pinned `xlrd==2.0.1` dependency.

## Current state

BCI Historical Current Account PDF v0.1 is implemented and validated. The
source-only contracts `bci_current_cartola_v0.1` and
`bci_recent_movements_v0.1` are frozen. Recent Movements is implemented and
validated as a pure source parser with synthetic tests and sanitized private
validation. Current Cartola remains unimplemented. No stable cross-source
identity rule or canonical Movement correction has been frozen.

## Constraints

Use synthetic fixtures only, preserve private evidence outside tracked files,
keep the generic observation/resolution and Movement semantics unchanged, and
fail closed on unsupported source assumptions. Current must be implemented
next; neither parser may persist evidence or write a Movement.

## Next action

Implement `bci_current_cartola_v0.1` with synthetic fixtures and deterministic
tests; keep the boundary pure source recognition/extraction only.
