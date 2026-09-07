# Current task

## Objective

Render the existing Movement classification projection read-only in the React
client. Implementation and review validation are complete. The checkpoint is
recorded in one commit titled
`feat: render movement classification in local client`. Do not push.

## Baseline

After `git fetch origin`, clean `main`, HEAD, and `origin/main` all matched
`a4877af9d20e67f13a508301977a0b16a356272a`
(`feat: expose movement classification read api`).

## Current state

- The frontend Movement projection is a strict discriminated union for
  `NEVER_ASSIGNED`, `CLASSIFIED`, and `CLEARED`. It validates exact nested
  keys, state/category/revision combinations, Category UUID/display/active
  shape, and safe integer revisions before retaining immutable client data.
- The existing Movement table has one dedicated Classification column.
  Classified rows display the Category name; inactive labels include a visible
  `Inactive` marker. Never-assigned and cleared rows both display
  `Unclassified`, while their internal states stay distinct.
- Revision numbers, UUIDs, raw enum values, source, timestamps, history, and
  provenance are not rendered. Long valid labels wrap within the column; empty,
  overlong, padded, control-character, and structurally invalid labels fail
  closed in parsing.
- Account/date behavior, explicit report loading, backend count/total, exact
  Decimal strings, Movement order and financial fields remain unchanged. The
  client performs no financial arithmetic.
- Category discovery is not fetched or otherwise consumed. Classified Movement
  items already carry the exact Category summary needed for rendering, so
  request cadence remains Account discovery plus explicit Movement reports.
- All requests remain same-origin GETs without credentials, cookies, tokens,
  auth/principal headers, CORS changes, or write methods. ADR-0010 and ADR-0011
  are unchanged. There is no classification editing, filtering, category
  totals, transfer/income-expense meaning, or taxonomy assumption.

## Validation state

- Frontend: 36 tests passed; typecheck, Vite build, and `npm ls` passed.
- Backend Movement HTTP compatibility: 20 tests passed.
- Full Django suite: 481 tests passed.
- Markdown links, privacy/private-file checks, diff hygiene, and exact changed
  paths are recorded in `.ai/handoff.md`.
- The isolated PostgreSQL 16 test container and synthetic database were stopped
  and automatically removed. No existing database or private corpus was read.

## Next bounded scope

Design the narrowest safe local classification write boundary before
implementing any mutation HTTP endpoint. Gouda now has the persistence,
revision-checked internal command, read HTTP projection, and read-only UI needed
to define a concrete manual-edit workflow. The design must revisit ADR-0010,
separate write authorization from read access, define CSRF/origin and optimistic
concurrency behavior, and keep the current endpoint surface read-only until a
new decision is accepted. Recommended reasoning level: High.

## Non-goals

No HTTP writes, editing controls, filters/search, Category discovery consumption,
category totals, default taxonomy, demo assignments, automatic/rule/AI
assignments, bulk edits, history, ownership, transfer or income/expense
semantics, tags, notes, hierarchy, or provider mapping.
