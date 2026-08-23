# ADR-0004: Record Santander source-format identity

- Status: Accepted
- Date: 2026-08-23

## Context

The frozen Santander current-account parser is the first concrete import
boundary. Banks can change external layouts independently from changes to
Gouda's parser implementation, so source product, external format, and parser
version must remain distinct facts.

## Decision

Keep `SANTANDER_CURRENT_ACCOUNT_XLSX` as the `SourceArtifact.source_kind`. Add
nullable `ImportBatch.source_variant`; `v1` identifies the currently supported
Santander current-account XLSX structural profile. `None` means that no variant
was successfully recognized.

The variant belongs to the import attempt because it is a recognition result.
An artifact is registered before parsing and may remain unsupported, while a
batch records the exact source variant and parser implementation used for its
interpretation. `PROCESSING` and `FATAL` may have a null variant. Materialized
and duplicate batches require a non-null variant.

Santander v1 recognition is explicit and fail-closed. It requires the trusted
worksheet, period, column, row, movement, and reconciliation structure needed
for safe interpretation. The known `Resumen de Comisiones` and `MENSAJES`
section markers are optional; when present, their structure and order must be
coherent. An unknown layout that could cause summary rows to be interpreted as
movements is unsupported rather than guessed.

No source registry, plugin system, or generic importer abstraction is added.
Future abstractions require evidence from multiple real source implementations.

## Consequences

Historical attempts retain source kind, source variant, parser version, and
exact source bytes as separate provenance. Adding a supported variant should
change a Santander-specific adapter boundary rather than canonical financial
persistence.

Multiple `PROCESSING` attempts may coexist. A process can terminate after
attempt registration, so abandoned attempts remain possible; cleanup and stale
attempt policy are deferred until there is operational evidence.
