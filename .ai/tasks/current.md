# Current task

## Objective

Determine the next BCI Current Cartola checkpoint from existing source
evidence without freezing unsupported cross-source identity semantics.

Implementation has not started. Legacy XLS inspection tooling is now
available through the pinned `xlrd==2.0.1` dependency.

## Current state

BCI Historical Current Account PDF v0.1 is implemented and validated. The
available BCI Current Cartola legacy XLS has been structurally inspected;
semantic review and Current parser work remain unimplemented. BCI Recent also
remains unimplemented. No stable cross-source identity rule or canonical
Movement correction has been frozen. Recent Movements work is not authorized
by this task.

## Constraints

Inspect sanitized source observations and private evidence safely before
defining behavior. Preserve private evidence outside tracked files, use
synthetic fixtures only, keep the generic observation/resolution and Movement
semantics unchanged, and fail closed on unsupported source assumptions.

## Next action

Review the BCI source lifecycle and the read-only structural findings for the
available Current Cartola artifact, identify what can be proven semantically,
and propose a bounded contract/design checkpoint. Do not implement BCI
Current until a contract is approved.
