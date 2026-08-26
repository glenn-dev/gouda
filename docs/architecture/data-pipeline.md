# Data pipeline

The implemented deterministic Santander path is:

```text
source -> ingest batch -> raw/source records -> normalize source-native meaning
       -> validate -> canonical movements -> classify/relate -> summaries
```

The accepted target evolution is:

```text
Artifact
-> identification / routing
-> deterministic extraction and/or AI interpretation
-> Financial Observation Candidate
-> deterministic validation
-> resolution
-> canonical Movement
-> classification / relationships / summaries
```

Resolution may leave an observation unresolved, reject it, confirm a new
movement, match it as support for an existing movement, or preserve
supersession/correction history. No Observation/Resolution schema is
implemented.

Each stage should be deterministic and idempotent for the same source record
and normalization version where a stable deterministic contract exists. The
database currently permits at most one materialized
interpretation for a source artifact and account. A different route cannot
create a second canonical graph; it is a source-kind conflict. Failed attempts
remain retryable through the correct route. Parser-version reprocessing and
supersession are deferred to an explicit later design.

`SourceArtifact` identifies exact bytes. `ImportBatch.source_kind` identifies
the interpretation route. `RawRecord.record_ordinal` supplies stable identity
within the parser result, while XLSX row data and Santander TDC geometric facts
remain separate source-specific evidence.

Source-native direction/effect belongs to the raw/source boundary. The
normalization boundary converts it into one canonical `Movement.signed_amount`
using the referenced account's economic orientation. Classification and
transfer/counterparty relationships are later semantic layers; neither is
encoded by the sign alone.

For future heterogeneous sources, extracted values become untrusted
observation proposals. Deterministic validation and resolution decide whether
they can affect the canonical ledger. Provisional views may display unresolved
evidence only when they remain explicitly separate from authoritative totals.

The persistence schema rejects invalid materialized batch/count combinations.
Exact monetary representability and cross-row duplicate identity remain
application-boundary checks.

The synchronous Santander TDC service registers artifacts and attempts before
parsing, validates parser v1.1 outside database transactions, and atomically
persists source evidence plus one canonical movement per parsed billed record.
It requires an explicit Santander card-suffix binding and maps liability debt
effect with `signed_amount = -debt_effect`. Original foreign money remains
source evidence and is never converted.

The current Santander current-account and TDC services may continue to
interpret, resolve, and materialize atomically under their frozen contracts.
Their behavior does not make `PARSED` a universal canonical-write rule.

## Failure handling

Invalid records are retained with stable safe codes. Unsupported or materially
ambiguous future observations remain unresolved or rejected rather than being
guessed into movements.

## Reprocessing

Normalization changes must be versioned. Reprocessing creates a new derived representation or migration, preserving the original source record and prior audit information.

Future observation reprocessing and resolution changes must likewise preserve
prior evidence and auditable decisions.

## Observability

Import batches should expose duration, record counts, rejection reasons, and normalization version. Logs must use internal batch and record identifiers rather than raw descriptions or account numbers.
