# Gouda agent workflow

This is Gouda's lightweight lifecycle for ChatGPT/Codex work. The repository
is the durable source of truth. ChatGPT/Codex conversation history is useful
working memory, but is not authoritative project state.

## State precedence and ownership

For implementation reality, current code, tests, and Git state outrank stale
operational notes. For accepted domain semantics, accepted product
principles, ADRs, and frozen contracts outrank `.ai/` notes. `.ai/` describes
current operational work only.

- `docs/product/` — product and domain intent.
- `docs/architecture/` — architecture.
- `docs/decisions/` — accepted decisions.
- `docs/contracts/` — deterministic source contracts.
- `docs/sources/` — sanitized source observations.
- `.ai/` — operational session state.
- `tests/` — executable invariants.
- Git history and the current repository — exact accepted implementation state.

## Resume

For a fresh ChatGPT/Codex coding session:

1. Read `AGENTS.md`.
2. Follow the documentation map in `README.md`.
3. Read relevant product, architecture, ADR, and contract documents.
4. Read `.ai/context.md`, `.ai/tasks/current.md`, and `.ai/handoff.md`.
5. Run `git status --short`, `git branch --show-current`, `git rev-parse HEAD`,
   and `git rev-parse origin/main`.
6. Confirm repository state before work.
7. Surface contradictions instead of silently choosing one source.

## Discover

When a new external financial source is involved, inspect actual source
evidence before defining behavior. Keep private evidence untracked and use
only synthetic fixtures in tracked files.

## Model / Contract

Before non-trivial ingestion, determine financial semantics and invariants.
Record a durable architectural decision as an ADR when justified, and freeze
a deterministic source contract before implementation when applicable. Stop
if source evidence contradicts the frozen contract.

## Implement

Keep changes narrow and source-specific; do not broaden generic architecture
to solve source-specific uncertainty. Preserve evidence, and let deterministic
financial boundaries own canonical writes. Fail closed when source assumptions
change. AI output is an untrusted structured proposal and cannot bypass
deterministic money, currency, sign, account, identity, lifecycle,
transactionality, concurrency, or canonical-write rules.

## Validate, adversarial review, and correct

Use the smallest applicable combination of focused tests, full regression,
migration-drift checks, concurrency checks, privacy checks, documentation-link
checks, and diff hygiene. Meaningful financial checkpoints receive adversarial
review that tries to invalidate correctness. Concrete reproducible findings
normally become regression tests. Fix concrete findings only; do not redesign
unrelated architecture during a correction pass.

## Checkpoint

Before declaring a non-trivial checkpoint ready, confirm validations pass;
operational docs describe current reality; completed work is not described as
future work; `.ai/context.md`, `.ai/tasks/current.md`, and `.ai/handoff.md` are
updated; no private or generated files are included; and the diff is reviewed.
Ask: “Does any operational document describe work completed by this diff as
future or pending work?” Also check `.ai/` for contextually stale phrases such
as “will implement”, “next action”, “not implemented”, “pending”, and “TODO”.
This is a review and Definition-of-Done rule, not an automated script.

Codex does not commit or push unless explicitly asked. After an authorized
push, verify the remote commit and main/origin state.

## Session boundaries

Start a new ChatGPT project chat preferably when a major functional checkpoint
closes, the domain problem changes materially, or a new source/lifecycle slice
starts. Token count is not the primary boundary.

Start a new Codex coding session preferably when the prior checkpoint is
committed and the worktree is clean, and the new task is a separate semantic
unit. Continuing the same session is appropriate for implementation, focused
review, and correction of that same checkpoint. These are guidance, not rigid
technical constraints.

## Handoff

Before handing work to another session, make `.ai/handoff.md` sufficient for a
cold start without conversation history. State current capabilities, the
latest completed functional checkpoint, the current objective, the explicit
next action, important constraints, relevant documents to read, and
intentionally deferred work. Do not duplicate full architecture explanations.
