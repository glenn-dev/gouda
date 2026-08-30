# Current task

## Objective

Implement the two frozen BCI source-parser contracts using synthetic fixtures
and deterministic tests, with Recent Movements first and Current Cartola
second, without persistence or lifecycle semantics.

The source-only contract checkpoint is complete. Legacy XLS inspection tooling
is available through the pinned `xlrd==2.0.1` dependency.

## Current state

BCI Historical Current Account PDF v0.1 is implemented and validated. The
source-only contracts `bci_current_cartola_v0.1` and
`bci_recent_movements_v0.1` are frozen. Both parser implementations and their
tests remain unimplemented. No stable cross-source identity rule or canonical
Movement correction has been frozen.

## Constraints

Use synthetic fixtures only, preserve private evidence outside tracked files,
keep the generic observation/resolution and Movement semantics unchanged, and
fail closed on unsupported source assumptions. Recent must be implemented
before Current; neither parser may persist evidence or write a Movement.

## Next action

Implement `bci_recent_movements_v0.1` first with synthetic fixtures and
deterministic tests, then implement `bci_current_cartola_v0.1`; keep both
boundaries pure source recognition/extraction only.
