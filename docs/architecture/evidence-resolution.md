# Evidence and resolution architecture

## Status

This document records accepted target evolution around the current ingestion
architecture. `FinancialObservation` is a conceptual boundary. No concrete
Django model, migration, API, background workflow, or AI implementation is
defined here.

The decision is recorded in
[ADR-0008](../decisions/ADR-0008-separate-observations-from-canonical-movements.md).

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

## Financial Observation Candidate

A financial observation candidate is an interpreted claim that may eventually
support a canonical movement. Its conceptual responsibilities are:

- link to one or more pieces of source evidence;
- propose an account;
- propose an amount, currency, and relevant date semantics;
- retain proposed description or source reference when supported;
- record the deterministic or probabilistic interpretation method and version;
- retain field-level provenance and uncertainty where meaningful;
- expose a resolution state; and
- permit a relationship to an eventual canonical movement.

An observation is not a movement. It may be incomplete, provisional,
ambiguous, rejected, superseded, or ultimately shown to describe an existing
movement. This checkpoint does not define final fields, cardinalities, state
names, or database constraints.

## Resolution boundary

Resolution determines how validated observations affect canonical truth. It
must support:

- confirming an observation as a new movement;
- matching multiple observations as support for one movement;
- retaining provisional evidence when authoritative evidence arrives;
- rejecting mistaken interpretations;
- recording supersession and correction without erasing prior evidence; and
- preserving an auditable decision history.

Durable resolution state and history are domain responsibilities. Application
services should perform transitions transactionally and apply deterministic
rules. AI may propose candidates or matches, but cannot perform a canonical
write without the same validation and lifecycle controls as deterministic
code.

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

The current one-to-one raw-record relationship describes the implemented
Santander persistence graph. A later implementation checkpoint must determine
the smallest compatible evidence/resolution relationship needed for multiple
evidence to support one movement. The canonical financial semantics do not
need to be rewritten.

## Provisional views

An explicitly provisional product view may combine unresolved observations
with canonical movements to estimate recent activity. It must visibly
distinguish those layers and must not reuse authoritative totals or reconciled
period labels without qualification.

Canonical ledger queries should continue to use accepted movements only.

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

The next design checkpoint should specify only the smallest persistence and
service changes needed for observation and resolution in the first concrete
multi-source lifecycle.
