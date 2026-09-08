# Current task

## Objective

Completed the design/documentation checkpoint for
[Gouda UI Foundation v0.1](../../docs/design/ui-foundation.md).
No UI implementation, dependency installation, frontend build, or production
frontend change belongs to this checkpoint. The commit contract is exactly one
signed `docs: define Gouda UI foundation` commit; no push is authorized.

## Baseline

On 2026-09-08, `git fetch origin` succeeded. Branch `main` and a clean working
tree were verified; HEAD and `origin/main` both equaled
`092a22429b2aa4c9d79ca7f5d3436b2f7484d54c`, titled
`feat: implement local classification write boundary`, with a good ED25519 SSH
Git signature. This supersedes the previous review's pre-amend operational state.

## Completed design

The foundation freezes calm ledger hierarchy, one system sans-serif stack,
neutral semantic colors, a small Tailwind spacing rhythm, restrained shapes,
plain centered layout, exact signed-money formatting, classification beneath
description, accessibility, responsive adaptation, and a four-component shadcn
allowlist: Button, Input, Label, Native Select. It includes ownership boundaries,
non-goals, visual acceptance criteria, and a path-by-path implementation scope.
No ADR is added: financial, persistence, integration, and security contracts
remain unchanged. Current official Tailwind/shadcn/Radix/W3C sources are linked
in the design, with established conventions distinguished from Gouda choices.

## Validation

Documentation validation covers Markdown structure and local links/anchors,
synthetic formatting examples, exact five-path scope, added-text privacy,
ignored/untracked private paths, and `git diff --check`. Results are recorded
in the handoff. No frontend or backend tests/builds are rerun for this docs-only
change; earlier functional results remain historical.

## Next bounded scope

Implement the foundation's read-client restyle: add Tailwind and minimal shadcn
infrastructure, only approved controls and presentation components, semantic
tokens, and responsive ledger styling. Preserve current request cadence,
validation, order/count/exact values, error states, privacy, and Vite trust gates.
No Category catalog request, capability bootstrap, or classification editor yet.

Then design/implement the separate manual editor under ADR-0012, retaining
explicit choices, memory-only capability handling, safe revisions, and refetch
after conflicts or ambiguous outcomes without silent replay.
Recommended reasoning level: High.

## Deferred

Final brand accent, logo, dark mode, chart vocabulary, dashboard, category
visual identity, motion, mobile navigation, and complex visualization remain
open. Filtering, Category management, default taxonomy, demo assignments,
rules/AI, bulk editing, history, ownership, transfers, and income/expense
semantics remain outside the UI foundation.
