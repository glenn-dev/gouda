# Ingestion and evidence principles

## Purpose

Gouda should accept useful financial evidence with low friction while keeping
canonical financial truth trustworthy. Inputs may include authoritative bank
statements, provisional bank activity, spreadsheets, APIs, email, messages,
screenshots, receipt photographs, or manually supplied facts.

These principles describe stable product behavior. They do not define a
persistence schema or authorize AI, connector, or parser implementation.

## P1 — Capture first

A safely receivable input should be preservable even when Gouda cannot yet
identify or interpret it confidently. Capture does not imply successful
interpretation, financial validity, or ledger acceptance.

Capture remains subject to privacy, security, size, retention, and supported
media controls.

## P2 — Evidence is distinct from truth

Receiving evidence, interpreting it, resolving it, and accepting a canonical
financial fact are separate events. Gouda must not treat the existence of an
artifact or an extracted value as proof that a movement occurred.

## P3 — Progressive confidence and provisional views

Recent or provisional evidence may support an explicitly provisional view of
current activity before authoritative evidence arrives. Provisional evidence
must not silently contaminate authoritative balances, reconciled periods, or
canonical totals.

## P4 — Multiple evidence, one fact

Several artifacts may describe one economic event. An email, screenshot,
current bank view, and final statement must not necessarily create four
canonical movements. Gouda should preserve each item of evidence while
allowing them to support one accepted fact.

## P5 — Contextual authority

Authority depends on the source, product, period state, field, and intended
use. A closed reconciled statement is normally stronger accounting evidence
than an alert, while a receipt may be stronger evidence for purchased items.

Gouda must not introduce one universal numeric authority or confidence score.
Confidence may be represented only where its meaning is specific, useful, and
validated for the relevant interpretation or matching behavior.

## P6 — Explainability

Every canonical fact must remain explainable through supporting evidence and
resolution history. Gouda should retain enough provenance to explain where a
value came from, how source-native meaning was transformed, and why evidence
was accepted, matched, rejected, superseded, or corrected.

## P7 — Graceful abstention

Unknown formats, incomplete evidence, and materially ambiguous
interpretations should remain unresolved or rejected. Gouda must prefer an
explicit unsupported result over guessing a movement into the ledger.

## P8 — AI-native, deterministic core

AI and agents may reduce friction through routing, extraction,
interpretation, matching, enrichment, investigation, and adapter maintenance.
Their output is always an untrusted structured proposal.

Deterministic code validates money, currency, sign, account compatibility,
identity, lifecycle transitions, transactionality, concurrency, and canonical
write rules. AI cannot bypass those controls.

## P9 — Small and versioned source adapters

When a stable source contract is known, Gouda should use a small, explicit,
versioned adapter. Provider-specific interpretation belongs at the source
boundary rather than in the canonical ledger.

Changed formats require an intentional contract and adapter revision. A
generic plugin framework, universal provider abstraction, or universal
document schema is not justified by the current evidence.

## P10 — Exception-driven human intervention

Human review should be requested when ambiguity materially affects financial
truth, such as account, currency, sign, amount, identity, or duplicate
resolution. Review should not be required for every ingestion event.

The review policy may consider risk and materiality, but must not weaken
deterministic invariants.

## Product promise

Gouda may be early, provisional, or incomplete, but it must be explicit about
which state applies. Probabilistic interpretation must never silently become
accounting truth.
