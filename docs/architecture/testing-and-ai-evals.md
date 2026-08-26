# Testing and AI evals

## Purpose

Gouda uses deterministic tests for code and financial invariants. Future
probabilistic components also require evaluation over representative datasets.
Both are necessary; neither replaces the other.

This document establishes a quality baseline. It does not select an AI model,
evaluation platform, or production threshold.

## Deterministic quality gates

Deterministic components should use the smallest applicable combination of:

- unit tests for pure interpretation and domain rules;
- frozen source-contract tests;
- synthetic adversarial fixtures;
- integration and persistence tests;
- migration and reversal tests;
- concurrency and idempotency tests;
- privacy and safe-error-surface tests; and
- privacy-safe private-source conformance outside committed fixtures.

Money, currency, sign, account compatibility, lifecycle transitions,
canonical writes, and reconciliation equations require exact deterministic
assertions.

## AI behavior evals

Future AI-assisted components should be evaluated for:

- artifact classification accuracy;
- field-level structured extraction accuracy;
- hallucination and unsupported-field rate;
- abstention quality when evidence is insufficient;
- observation and movement matching precision and recall;
- calibration only where confidence is actually used;
- private-data leakage through prompts, output, logs, or traces;
- compliance with deterministic financial invariants; and
- regression across model, prompt, tool, and orchestration changes.

Matching evals should report collisions and false-positive matches, not only
aggregate accuracy. Financial identity resolution normally values precision
and appropriate abstention over automatic coverage.

## Why unit tests are insufficient

Normal unit tests are necessary but insufficient for probabilistic
components. They can verify schemas, deterministic wrappers, fixed examples,
and failure handling, but they do not characterize behavior across a
distribution of inputs. AI output can vary with model versions, prompts,
context, tool behavior, and ambiguous source content.

Evals are therefore needed to measure error rates, abstention, calibration,
privacy behavior, and regressions. Passing an eval does not authorize bypassing
deterministic canonical-write rules.

## Dataset strategy

Primary development and regression datasets should use synthetic or carefully
redacted examples with explicit expected outcomes. Adversarial cases should
include incomplete evidence, conflicting values, repeated descriptions,
duplicate-looking events, changed layouts, malicious instructions embedded in
artifacts, and unsupported fields.

Privacy-safe real-source conformance is a separate controlled gate. Private
artifacts must remain ignored and untracked, and reports must expose only
sanitized structural facts, counts, statuses, or equality results.

## Change gates

A deterministic adapter change should identify its contract and version, pass
synthetic tests, and pass applicable private conformance before trust.

An AI behavior change should identify the model, prompt, tools, and evaluation
set used. Material regressions in financial extraction, matching precision,
abstention, privacy, or invariant compliance block release even when ordinary
unit tests pass.
