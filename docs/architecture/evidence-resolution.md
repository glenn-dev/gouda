# Evidence and resolution architecture

## Status

This document records the implemented observation and resolution boundary
around the current ingestion architecture. `FinancialObservation` and
`ObservationResolution` are implemented as Django/PostgreSQL models with a
deterministic synchronous application service. The BCI Historical
evidence-first adapter and conservative reconciled policy are implemented;
BCI Current/Recent persistence and lifecycle behavior are not. No provisional
view, background workflow, or AI implementation is defined here.

The separation decision is recorded in
[ADR-0008](../decisions/ADR-0008-separate-observations-from-canonical-movements.md),
and its concrete persistence boundary in
[ADR-0009](../decisions/ADR-0009-implement-observation-resolution-boundary.md).

## Architectural goal

Gouda must preserve heterogeneous evidence and allow provisional
interpretation without weakening the canonical ledger. The target pipeline is:

```text
Artifact
→ identification / routing
→ deterministic extraction and/or AI interpretation
→ Financial Observation Candidate
→ deterministic validation
→ resolution
   ├─ unresolved
   ├─ rejected
   ├─ confirmed as new Movement
   ├─ matched as support for existing Movement
   └─ superseded/corrected
→ canonical Movement
→ classification / relationships / summaries
```

This pipeline separates evidence receipt from accounting acceptance. It does
not require every source to use probabilistic interpretation.

## Current authoritative route

The current Santander routes remain valid:

```text
Artifact
→ deterministic parser
→ validated source evidence
→ canonical Movement
```

Their source contracts, account checks, normalization, and persistence rules
are deterministic enough to interpret, resolve, and materialize in one atomic
application-service operation. This compatibility does not establish a
universal rule that every future `PARSED` result becomes a `Movement`.

## Artifact and routing boundary

`SourceArtifact` currently preserves exact bytes, digest, and private receipt
metadata. Exact-byte content addressing remains useful for files, images, raw
messages, text encodings, and preserved connector payloads, but it establishes
artifact identity rather than economic-event identity.

A future source envelope may need media type, acquisition channel, external
receipt identity, or serialization metadata. Those responsibilities should be
designed from a concrete non-file source rather than added speculatively.

Identification and routing may produce a known adapter, an interpretation
strategy, an unsupported result, or a needs-human result. Capture should be
possible before confident identification, subject to security controls.

## Processing attempts and source records

`ImportBatch` remains useful for a deterministic import attempt and may also
represent an AI-assisted import route while that remains coherent. Its current
account-first, closed-route, and source-shaped fields should not be promoted
into a universal workflow abstraction.

`RawRecord` remains the shared identity and outcome envelope for
record-oriented deterministic imports. Source-specific evidence belongs in
source-specific structures. A photo region, email span, message, or model
interpretation should not be forced into spreadsheet-row fields or a
permissive universal evidence object.

## Financial observation

A financial observation is one immutable interpreted claim derived from one
parsed `RawRecord`. It:

- links to its RawRecord and trusted Account;
- records an exact nonzero signed amount and trusted currency;
- records transaction and accounting date candidates, with at least one
  required;
- retains optional normalized description and source reference;
- records interpretation method and version;
- starts unresolved; and
- may resolve to a canonical Movement.

An observation is not a movement. The supported application service and
ordinary model-save boundary reject claim-field changes after creation;
direct SQL, `QuerySet.update()`, and `bulk_update()` are outside that boundary.
Interpretation correction creates a successor observation. Only state, current
Movement, and state version form the mutable current projection. Creation uses
an explicit UUID idempotency key rather than treating parser method/version as
economic or interpretation identity.

## Resolution boundary

Resolution determines how validated observations affect canonical truth. The
implemented commands support:

- confirming an observation as a new movement;
- matching multiple observations as support for one movement;
- retaining provisional evidence when authoritative evidence arrives;
- rejecting mistaken interpretations;
- recording interpretation supersession without erasing prior evidence; and
- preserving an auditable decision history.

The current states are `UNRESOLVED`, `RESOLVED`, `REJECTED`, `CONFLICT`, and
terminal `SUPERSEDED`. `ObservationResolution` is append-only audit history;
the observation carries only its mutable current projection. Application
services perform transitions transactionally under Account-scoped locks.
Resolution idempotency uses an explicit unique UUID command key.
`CONFLICT` means conflict with a known canonical Movement; generic ambiguity
without a known Movement remains `UNRESOLVED`.

`CONFIRM_NEW` accepts a caller-selected exact observation date and abstains if
an exact same-account date/amount/currency Movement candidate already exists.
This is a collision guard, not universal identity. A caller that independently
establishes a distinct event may explicitly override the guard after Account
locking and candidate re-evaluation; doing so creates a second Movement and
never attaches the observation to the colliding Movement.

`MATCH_EXISTING` validates an explicitly selected target using exact Account,
currency, and signed amount compatibility. It does not select a candidate or
determine economic identity. Dates, descriptions, references, periods, and
other source evidence belong to source-specific policy. No fuzzy matching is
implemented.

Resolution authority is contextual. A source may be authoritative for posted
account effect but not for purchase time, merchant details, classification, or
the identity of an underlying economic event. No global numeric authority
ranking is introduced.

## Canonical Movement

`Movement` remains source-neutral financial truth accepted by Gouda. It keeps
its canonical amount, currency, date, account, and optional explanatory source
fields.

The following do not belong directly on `Movement`:

- confidence;
- provisional state;
- parser or extraction method;
- AI model or prompt identity; or
- source authority.

Those facts describe evidence, interpretation, or resolution. Mixing them
into `Movement` would make canonical queries depend on ingestion mechanics and
would allow probabilistic state to contaminate accounting truth.

The required one-to-one `Movement.raw_record` is the RawRecord from which the
Movement was originally materialized. It is not necessarily the only evidence
supporting that Movement. Additional supporting evidence is represented by
observations resolved to it; no separate Movement evidence join exists.

Canonical Movement correction is explicitly deferred. Conflict resolution in
this checkpoint never changes, retracts, deletes, zeroes, or supersedes a
Movement.

## Provisional views

An explicitly provisional product view may combine unresolved observations
with canonical movements to estimate recent activity. It must visibly
distinguish those layers and must not reuse authoritative totals or reconciled
period labels without qualification.

Canonical ledger queries should continue to use accepted movements only.

The implemented BCI Historical route creates unresolved observations from
preserved source evidence. Its separate conservative policy may confirm an
eligible reconciled observation as a new Movement while abstaining at
unsupported collisions; it performs no automatic cross-source match. Current
Cartola and Recent Movements remain source-only parsers with no observation,
persistence, or lifecycle route. This source-specific behavior is not a
generic observation state or model invariant.

## Agent and deterministic cooperation

Agents may:

- classify and route unknown artifacts;
- extract candidate facts from images, email, text, or semistructured input;
- suggest matches between observations, movements, accounts, and sources;
- investigate anomalies or changed formats; and
- propose adapter, fixture, test, and documentation changes.

Deterministic code must:

- validate exact money, currency, sign, dates, and account compatibility;
- validate source and domain identity where contracts exist;
- enforce resolution lifecycle transitions and canonical write rules;
- provide transactionality, idempotency, and concurrency control; and
- reject unsupported or ambiguous states.

AI output is untrusted input to this boundary. It is never an alternate write
path around it.

## Adapter maintenance

When a deterministic adapter stops matching a provider format:

1. Preserve the artifact.
2. Record a contract mismatch without creating movements.
3. Let an agent compare the artifact with supported variants.
4. Let the agent propose an adapter or version change.
5. Generate or update synthetic and adversarial fixtures, tests, and source
   documentation.
6. Require deterministic tests, privacy-safe real-source conformance, and an
   appropriate review gate before the version is trusted.

The agent accelerates diagnosis and proposal work. Versioned code and review
establish production trust.

## Domain ownership

Gouda owns financial evidence, resolution, canonical movements, and financial
invariants. A broader system such as Atlas may later orchestrate workflows
through clean Gouda application boundaries, but it must not own or bypass
Gouda's financial truth.

## Documentation ownership

- `docs/product/` owns stable product intent and user-facing semantics.
- `docs/architecture/` owns current architecture and accepted target
  evolution.
- `docs/decisions/` owns immutable and superseding ADR history.
- `docs/contracts/` owns frozen deterministic adapter contracts.
- `docs/sources/` owns sanitized source observations and unresolved
  hypotheses.
- `docs/security/` owns privacy and security rules, including AI boundaries.
- `.ai/` owns current operational context and handoff only; it is never the
  sole canonical source of product truth.
- `AGENTS.md` owns stable development-agent instructions.

Agents should read `AGENTS.md`, then the README documentation map, product
principles, architecture, active ADRs and contracts, and finally `.ai/`
operational state. Durable doctrine should be linked rather than copied into
`.ai/`.

## Deferred abstractions

The following are not justified by current evidence:

- a generic plugin framework;
- a general workflow engine;
- event sourcing;
- vector databases or embeddings;
- a universal document schema;
- a universal provider abstraction;
- universal numeric confidence;
- a multi-agent orchestration framework; and
- full double-entry accounting.

BCI Current/Recent persistence and lifecycle behavior, permanent identity
policy, provisional product views, and canonical Movement correction remain
later source-driven checkpoints.
