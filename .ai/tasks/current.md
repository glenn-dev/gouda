# Current task

## Objective

Completed the implementation checkpoint for
[Gouda UI Foundation v0.1](../../docs/design/ui-foundation.md). The read client
now implements the frozen presentation foundation without the classification
editor or any new product/API behavior. The commit contract is exactly one
signed `feat: implement Gouda UI foundation` commit; no push is authorized.

## Baseline

On 2026-09-08, `git fetch origin` succeeded. Branch `main` and a clean working
tree were verified; HEAD and `origin/main` both equaled
`16f07047d5c08d44bfc1094fcc9a45712ae7d7dd`, titled
`docs: define Gouda UI foundation`, with a good ED25519 SSH Git signature.

## Implemented foundation

The frontend uses Tailwind's current CSS-first Vite integration and narrowly
owned shadcn Radix-collection sources for Button, Input, Label, and Native
Select. Gouda semantic tokens, the frozen system font stack, 44px controls,
visible focus, a pure string-only `MoneyAmount`, `ClassificationDisplay`, and a
responsive semantic `MovementList` replace the old panel/table presentation.

All report values and ordering still come directly from the backend. Exact
decimal strings are never converted to numbers or used in client arithmetic.
Positive and negative values retain signed Account-effect meaning and neutral
color. Classification remains read-only; active/inactive and both unclassified
states preserve their frozen presentation and internal distinctions.

## Validation

All 59 frontend tests pass, including the real Vite proxy test. Typecheck,
production build, and the top-level dependency tree pass. Forty-five focused
local-delivery/reporting tests and all 523 Django tests pass. Django check,
migration drift, and `pip check` pass. Browser inspection covered settled and
loading selection states, populated desktop, 375px and 320px populated layouts,
empty report, and safe report error. At 320px there is no page overflow and all
four controls measure 44px high. Native keyboard order and the visible 2px focus
ring were verified. Temporary screenshots remain untracked; demo rows were
cleared and the isolated stack was stopped without deleting its volume.

## Next bounded scope

Design and implement the separate manual classification editor under ADR-0012.
Retain explicit choices, memory-only capability handling, safe revisions, and
refetch after conflicts or ambiguous outcomes without silent replay. Filtering
remains separate.

## Deferred

Final brand accent, logo, dark mode, chart vocabulary, dashboard, category
visual identity, motion, mobile navigation, and complex visualization remain
open. Category management, default taxonomy, demo assignments, rules/AI, bulk
editing, history, ownership, transfers, and income/expense semantics remain
outside the UI foundation.
