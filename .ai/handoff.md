# Handoff

## Current repository capability

Gouda has validated synchronous Santander current-account XLSX and Santander
credit-card PDF import lifecycles. Both use deterministic, versioned source
contracts, preserve source evidence, validate source/domain boundaries, and
atomically create canonical signed movements. Duplicate, failure,
transactionality, privacy, and PostgreSQL concurrency behavior are covered by
the existing test suite.

Canonical movement sign follows ADR-0005. `Movement` represents accepted
source-neutral financial truth; provider-native fields remain in evidence.

## Documentation checkpoint

This checkpoint establishes the accepted future ingestion boundary:

```text
Artifact
-> identification / routing
-> deterministic extraction and/or AI interpretation
-> Financial Observation Candidate
-> deterministic validation
-> auditable resolution
-> canonical Movement
```

Resolution may leave evidence unresolved, reject it, confirm a new movement,
match it as support for an existing movement, or retain supersession/correction
history. `FinancialObservation` remains conceptual; no schema or implementation
was added.

Canonical references:

- `docs/product/ingestion-evidence-principles.md`
- `docs/architecture/evidence-resolution.md`
- `docs/architecture/testing-and-ai-evals.md`
- `docs/decisions/ADR-0008-separate-observations-from-canonical-movements.md`
- `docs/sources/bci-current-account-lifecycle.md`

## BCI stress test

The sanitized source note records that Recent Movements is a rolling/recent
view, Current Cartola is an open-period view, and Historical Cartola is a
strongly reconciled closed-period source. The sources overlap, descriptions
are unstable, and no universal transaction identity is proven. Direct
Current-to-Historical rollover overlap has not yet been observed.

This supports an observation/resolution boundary but does not freeze a BCI
adapter or source strategy.

## Guardrails

- AI output is always an untrusted structured proposal.
- AI cannot bypass deterministic money, currency, sign, account, identity,
  lifecycle, transactionality, concurrency, or canonical-write rules.
- Provisional evidence may appear only in an explicitly provisional view and
  must not contaminate authoritative totals.
- Do not add confidence, provisional state, parser identity, AI model, or
  source authority to `Movement`.
- Do not introduce a universal numeric confidence/authority score.
- Defer generic plugins, workflows, event sourcing, vector databases,
  embeddings, universal schemas/adapters, multi-agent frameworks, and full
  double-entry accounting.
- Keep financial-domain truth owned by Gouda; a future Atlas may orchestrate
  only through Gouda application boundaries.

## Next checkpoint

Design the smallest compatible Observation/Resolution persistence and service
boundary before BCI multi-source canonical ingestion. Determine lifecycle,
evidence-to-observation, observation-to-movement, idempotency, correction, and
concurrency responsibilities without implementing AI or a generic framework.

Read `AGENTS.md`, the README documentation map, product principles,
architecture, active ADRs/contracts, and only then this operational handoff.
