# Gouda UI Foundation v0.1

## Status and boundary

Frozen design, 2026-09-08; read-client implementation completed in the following
checkpoint. This is the small presentation foundation for the local read client,
a later manual classification editor, and eventual household reports. It changes
no financial, persistence, API, authorization, or source contract, so no new ADR
is warranted.

Read the [MVP scope](../product/mvp-scope.md),
[local HTTP contract](../architecture/local-http-delivery.md),
[classification contract](../architecture/movement-classification.md), and
[canonical sign decision](../decisions/ADR-0005-canonical-movement-sign-orientation.md)
before changing presentation. Those contracts outrank styling convenience.

The chosen layers are native HTML / Radix accessible primitives, shadcn component
implementations, Gouda tokens and financial presentation, then product components.
React and Vite remain the application stack. shadcn supplies editable component
source, not Gouda's identity; its own [introduction](https://ui.shadcn.com/docs)
describes that source-ownership model. No additional frontend framework is needed. External conventions linked here
were consulted on 2026-09-08; visual choices are Gouda-specific unless attributed.

## Current client assessment

At baseline `092a22429b2aa4c9d79ca7f5d3436b2f7484d54c`:

- [main.tsx](../../frontend/src/main.tsx) mounts `App`; `App` owns Account
  discovery, form state, and report loading. Its local `ReportResult` renders
  the summary and a five-column HTML table. There is no router or component library.
- [styles.css](../../frontend/src/styles.css) has a warm gradient, large title,
  shadowed rounded panels, uppercase metadata, classification badges, and a
  horizontally scrolling table. It already uses tabular numerals, labeled
  native controls, and a centered shell. The layout offers a useful starting
  structure but gives containers and classification more weight than needed.
- [api.ts](../../frontend/src/api.ts) validates exact decimal strings and a
  strict classification union, rejects unsafe revisions, and drops source
  trace. It fetches Accounts and explicitly requested reports only. It does
  not fetch Categories or consume the implemented write capability.
- [package.json](../../frontend/package.json) pins React/React DOM 19.2.8,
  Vite 8.2.2, TypeScript 7.0.2, Vitest 4.1.11, and Testing Library/jsdom tooling.
  Tailwind, shadcn, Radix, font packages, and icon packages are absent. The CSS
  names Inter but neither bundles nor loads it.
- [App tests](../../frontend/src/App.test.tsx) cover discovery, explicit request
  cadence, errors/empty states, backend order/count, exact money, hidden private
  values, and classification states. [API tests](../../frontend/src/api.test.ts)
  cover projection validation and GET-only behavior. Network tests cover the
  protected Vite edge, including real proxy/header forwarding. Existing tests
  are behavioral safeguards, not evidence of visual quality.
- [vite.config.ts](../../frontend/vite.config.ts) contains security-sensitive
  loopback/proxy, CORS, header, framing, and safe-logging behavior. A styling
  setup must preserve all of it; do not replace this file with a starter template.

## Visual principles

1. Financial information leads: Account, period, description, and amount establish context.
2. Repeated amounts scan vertically; each sign and currency stays explicit.
3. Controls remain discoverable while taking less visual weight than the ledger.
4. Whitespace and typography establish hierarchy before borders or containers.
5. Color supplements text and signs; it never establishes financial meaning.
6. Show known state plainly, including unclassified, inactive, empty, and failed reads.
7. Every visible element should convey information, an action, or useful grouping.

The direction is calm, minimal, and personal. Fintual is a directional reference
for restraint and approachable financial presentation only. No branding, assets,
palette, font, layout, or proprietary design is borrowed. The choices below are
Gouda design decisions, not requirements imposed by that reference or a toolkit.

## Typography

Choose a system sans-serif stack:
`ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif`.
It works offline without downloads or font-loading shifts. One bundled family
would give more consistent metrics across platforms, but that benefit does not
justify asset, licensing, and loading work yet. Do not add Inter or another font
just because a shadcn example uses it. Verify numeric alignment on supported
desktop browsers; platform glyph differences are acceptable.

| Role | Relative hierarchy and Tailwind starting point |
| --- | --- |
| Page title | Largest heading, restrained semibold; `text-2xl`, `md:text-3xl`, `leading-tight`. |
| Section heading | One step above body; `text-lg font-semibold`. |
| Primary body / description | Readable default; `text-base`, normal weight, `leading-normal`. |
| Secondary metadata | One step below body; `text-sm`, normal weight, full readable contrast. |
| Financial amount | Row: body size and medium weight; report total: `text-2xl font-semibold`. Always `tabular-nums`. |
| Small field label | Same size as metadata, medium weight; sentence case, never tiny uppercase text. |

Use normal, medium, and semibold weights only. Amounts never shrink below body
size to fit. No second financial font, decorative display style, or custom type
scale. Body starts at 1rem and respects browser text sizing.

## Semantic color

Light mode only. These are deliberately neutral v0.1 values, not a permanent
brand palette. CSS variables own meaning; utility classes reference them.

| Semantic token | Initial value | Use |
| --- | --- | --- |
| `background` | `#FAFAF9` | Plain page. |
| `foreground` | `#1C1917` | Main text and neutral financial values. |
| `surface` | `#FFFFFF` | Controls and any justified contained surface. |
| `muted` | `#F5F5F4` | Quiet state/group background and interaction highlight. |
| `muted-foreground` | `#57534E` | Metadata, classification, helper text. |
| `border` | `#D6D3D1` | Nonessential row and section separators. |
| `input` | `#78716C` | Control boundary where needed to identify a control. |
| `primary` | `#292524` | Single main action / primary interaction accent. |
| `primary-foreground` | `#FFFFFF` | Text on primary actions. |
| `ring` | `#1D4ED8` | Visible focus only, not another decorative accent. |
| `financial-positive` | Alias of `foreground` | Explicit positive account effect. |
| `financial-negative` | Alias of `foreground` | Explicit negative account effect. |
| `error` | `#991B1B` | Existing request/validation failure text and invalid boundary. |

Both financial directions are neutral in v0.1: neither is intrinsically good,
bad, income, or spending. Their separate semantic names prevent later product
code from hard-coding green/red; signs already distinguish them. Zero and totals
use foreground. Error is not financial-negative. No warning palette is needed:
future conflict/refetch messages can use a neutral surface with explicit text.

Use shadcn's [semantic foreground/background convention](https://ui.shadcn.com/docs/theming).
Map its `accent` to `muted` and `accent-foreground` to `foreground` for hover;
this is not a second brand accent. If approved source requires `secondary`,
alias it likewise. Map `destructive` to `error` only where needed for invalid
styling; no destructive Button variant is required. White surfaces use foreground.
Do not carry unused chart, sidebar, dark, or overlay tokens into the foundation.

Contrast must pass on actual rendered pairs, including hover, error, and focus.
The pale separator is not sufficient for a required control boundary; use
`input`. Do not apply opacity to a whole row or inactive Category label.

## Spacing, density, and shape

Use Tailwind's 4px-based rhythm: `1`, `2`, `3`, `4`, `6`, `8` (0.25–2rem).
Avoid one-off gaps; typography and content growth determine final row height.

| Area | Density |
| --- | --- |
| Page | `px-4`, increasing to `md:px-8`; `py-6` to `md:py-8`. |
| Sections | `gap-6` or `gap-8`; no viewport-sized empty areas. |
| Movement row | `py-3`, `gap-4` between tracks, `gap-1` within description/classification; normally about 4–5rem tall with two text lines, allowed to grow. |
| Forms | `gap-4` between fields; `gap-2` between label, input, and help. |
| Inline controls | `gap-2`; modest horizontal padding and a usable target independent of text size. |

One radius: 0.375rem (`rounded-md` after mapping the Gouda radius). Use it for
controls and any future bounded overlay; no pills. Thin 1px borders separate
rows or identify fields. No shadows on page content, forms, totals, or rows.

Use the plain page for the report, summary, and selection form. A bordered
group is justified for an inline editor or related error/recovery content when
it needs a visible boundary. A card-like container requires a genuinely
independent object/task; none is needed on the current report page. A future
popover/dialog may use surface, border, this radius, and one small shadow to
communicate overlap. Do not create an elevation scale or install overlays now.

## Page and responsive layout

One centered content column, `w-full max-w-5xl mx-auto`, with the page gutters
above. Use a simple product header (`Gouda`), one page title (`Movements`), the
Account/date form, then the report context and ledger. No sidebar, nav tabs,
breadcrumb, card grid, dashboard, or router is needed for one screen.

On success, show Account display name, kind, and the returned inclusive date
range together. Present the backend net signed amount as **Net account effect**
with visible currency, and the backend Movement count as secondary context in
the same report heading area. Do not repeat the Account name as several titles.
Retain a short explanation: “Positive increases this Account's contribution to
household net worth; negative decreases it.” API serialization terminology
belongs in developer docs, not the main product introduction.

Preserve the current flow: discover Accounts, select the first when available,
enter both dates, explicitly load the report. Changing selection clears the old
report; loading disables the current selection controls. Dates in a loaded
heading come from the returned report, never unsent draft fields.

Use unprefixed styles for narrow layouts; `md` (48rem) enables ledger tracks
and paired date fields, and `lg` (64rem) allows a single-row selection form
if its content fits. Account is full width below `lg`; date fields and submit
stack below `md`. Labels and long values wrap without overlapping. No fixed
viewport heights, sticky overlays, or device-specific navigation.

At 320 CSS px, the ledger becomes a vertical list: compact date, description,
classification, then a right-aligned full-width amount area. Currency can sit
on its own line with the numeric run kept intact. At wider sizes the amount
shares the description's first baseline. Use one DOM representation; do not
duplicate mobile/desktop content or reorder keyboard navigation with CSS.
If a maximum-length exact total still exceeds a narrow line, give that amount
alone accessible local overflow; do not shrink, truncate, or make the page
scroll sideways. Ordinary Movement amounts must fit the narrow layout.

## Exact financial presentation

`Movement.signed_amount` is ACCOUNT EFFECT under ADR-0005. Positive increases
the referenced Account's contribution to household net worth; negative decreases
it. A positive card effect can reduce debt. Sign never licenses an income,
expense, cash-flow, transfer, or balance-change label.

- Always display `+` for a nonzero positive and the typographic minus `−` for
  a negative, directly before the magnitude. Never substitute parentheses,
  arrows, color, or an unsigned absolute value for the sign.
- Use a fixed Chilean numeric presentation for this local slice: dot grouping
  in groups of three and comma decimal separator. This is Gouda's initial
  display choice, independent of browser locale; UI copy remains English.
- Show the ISO currency code on every row and total. Avoid ambiguous `$`.
  The code may be secondary-sized but must retain readable contrast.
- CLP: omit only an exactly `.00` fractional part. When either fractional digit
  is nonzero, show both digits, including a trailing zero. Never round accepted
  CLP data. Other accepted currencies retain the API's two fractional digits;
  no FX conversion or expanded currency/minor-unit contract is implied.
- Format validated decimal strings with string operations only: isolate sign,
  group integer digits, and preserve the fractional substring. No `Number`,
  `parseFloat`, numeric coercion, floating-point `Intl` input, rounding,
  summation, absolute-value arithmetic, or client-side financial calculation.
  Keep the original string in the model. Formatting does not mutate API data.
- Right-align financial runs and use tabular numerals. No abbreviated `k`/`M`,
  clipping, ellipsis, or fractional digits hidden in tooltips.
- Zero displays without a sign (`0 CLP`, `0,00 USD`) in foreground; recognize
  textual negative zero as zero for display only. Canonical Movements are
  nonzero; zero is chiefly a report-total case. Never synthesize zero when
  loading, missing, or failed: show the actual state instead.
- Totals use only `net_signed_amount` and `movement_count` from the backend.
  Total currency comes from the selected Account under the report contract;
  row currency comes from each Movement. Never sum across Accounts/currencies
  or infer household balances, category totals, income, or spending.

Synthetic formatting examples (illustrations, not a dataset or a reconciliation):

| API amount | Currency | Display |
| --- | --- | --- |
| `12345.00` | CLP | `+12.345 CLP` |
| `-12345.00` | CLP | `−12.345 CLP` |
| `12345.60` | CLP | `+12.345,60 CLP` |
| `-0.01` | CLP | `−0,01 CLP` |
| `12345.00` | USD | `+12.345,00 USD` |
| `0.00` | CLP | `0 CLP` |

Screen readers must receive “positive”, “negative”, or “zero”, the complete
formatted magnitude, and currency once. Use real text (including visually
hidden sign words) rather than CSS-generated signs; avoid duplicate readings
of visible and hidden amounts. The report explanation supplies account-effect
meaning without repeating a long definition on every row.

## Movement anatomy

Choose a semantic list (`ul` / `li`) styled as a ledger with CSS grid, not an
ARIA grid or shadcn DataTable. Each item is one Movement, not a selectable row.
The current table's five independent columns offer little comparison benefit:
currency belongs with amount and classification belongs with description.
There is no sorting, column management, pagination, or bulk-selection need.

Wide layout: compact date | flexible description/classification | amount.
Use the full `YYYY-MM-DD` occurrence date in a `time` element, small and muted;
no timezone conversion, omitted year, or date inferred from classification.
Keep backend occurrence-date/UUID order exactly, even when test fixtures return
another order; never sort or regroup in the client. Description uses body text
and wraps; retain `No description` when absent.

Classification sits directly beneath the description in secondary text, not
a separate column or badge. Its readable prefix is `Category:` followed by the
display name or `Unclassified`; add `· Inactive` when applicable. No category
colors, icons, ellipsis, or hover-only labels. Amount is right-aligned, visually
stronger than classification, with currency adjacent or beneath it. Thin
separators and aligned tracks connect the list; no card per Movement or zebra
striping. Read-only rows have no pointer cursor or misleading hover affordance.

Only current projected fields appear. Do not add merchant identity, payment
method, institution, balance, transaction type, review status, source metadata,
or assignment timestamp. UUIDs and revisions remain internal. Provenance stays
out of normal presentation and out of the client projection; a later explainability
view needs its own scope rather than a tooltip full of source metadata.

## Classification and control conventions

These are compatibility constraints for the later editor, not a full editor
design. A future secondary text button (`Assign category` / `Change category`)
fits beside or below the classification line and stays visible without hover.
The natural expansion space is beneath that line within the same Movement.
Keep financial data readable during editing; never make the whole row a button.

| State / action | Required foundation behavior |
| --- | --- |
| Active Category | Plain current display name; can later be changed or explicitly cleared. |
| Inactive Category | Retain name and `Inactive` text at readable contrast. Never hide or treat as unclassified; unavailable for new assignments. Existing no-op/clear semantics remain the backend's. |
| Never assigned / cleared | Both read `Unclassified`; preserve distinct validated states/revisions internally. Neither means reviewed, rejected, or erroneous. |
| Assign / change | Later: explicit active Category choice, separate commit action, cancel without writing; choosing/focusing an option alone does not save. |
| Clear | Later: explicit `Clear category` action, not empty input or a fake Category option; no generic destructive/delete styling or confirmation modal by default. |
| Loading / saving | Nearby stable text and busy state; prevent duplicate submission and retain row identity. Never announce success before an authoritative response. |
| Conflict / refetch | Nearby explanation, refetch before editing resumes, fresh user choice; no silent overwrite or automatic replay. Failed refetch leaves editing unavailable. |

The [write ADR](../decisions/ADR-0012-local-classification-write-boundary.md)
owns revision safety, memory-only capability, view/request races, inactive or
missing target refresh, ambiguous-outcome reconciliation, and no silent retry.
The editor must honor it later. The restyle must not bootstrap capabilities,
fetch the Category catalog, enable writes, add editor controls, or change startup.

Use visible associated labels, native form submission, and native `select` for
Accounts and the initial future Category choice. The current option set needs
no search; a searchable combobox must earn its complexity through actual catalog
use. Keep long selected Account context readable outside the select as well.
Date input stays native `type="date"` with labeled inclusive start/end fields
and unchanged ISO submission. Native picker appearance may differ by platform.

Buttons have primary (load/save), outline (retry/cancel), and quiet text (future
row action) treatments. One primary action per task region. Hover uses a subtle
muted surface for quiet controls and an outline for the primary button; pressed
adds an inset outline without motion. Focus remains visible in every state.
Disabled uses actual `disabled`, readable text and a nearby reason when unclear;
retain the current report-loading lock. No icon-only essential action.

Errors stay near the field or report they affect, with safe explanatory text,
`aria-invalid` and `aria-describedby` where applicable. Use `role="alert"` for
new failures and a concise polite status region for loading/completion. Do not
announce the entire ledger as a live region. Existing safe error mapping remains.
No animated skeletons, fake progress percentages, or toast-only feedback.

Popover is for a future bounded nonmodal contextual interaction only if inline
space proves insufficient. Dialog is for a task truly needing modal attention,
not routine classification. If introduced, use accessible primitives for focus,
dismissal, Escape and trigger return; do not implement these from scratch.
Tooltip may supplement a nonessential abbreviation later, never replace a label,
error, exact amount, classification, or necessary instruction. None is needed now.

## Accessibility baseline

Target WCAG 2.2 AA; this document is not a claim of achieved conformance.
Established requirements and interaction guidance:

- Semantic headings, landmarks, list items, labels and native controls; logical
  Tab/Shift+Tab order, native Enter/Space behavior, no positive tabindex or traps.
  Use [Radix accessibility guidance](https://www.radix-ui.com/primitives/docs/overview/accessibility)
  for complex primitives and [APG combobox patterns](https://www.w3.org/WAI/ARIA/apg/patterns/combobox/)
  if a future searchable selector is justified. Primitives do not supply product labels.
- [Text contrast](https://www.w3.org/WAI/WCAG22/Understanding/contrast-minimum.html):
  at least 4.5:1 for normal text, 3:1 for qualifying large text. Gouda chooses
  4.5:1 for all financial and classification text regardless of size.
- Required control boundaries and state indicators meet
  [3:1 non-text contrast](https://www.w3.org/WAI/WCAG22/Understanding/non-text-contrast.html).
  Decorative separators need not meet the control-boundary threshold.
- [Visible keyboard focus](https://www.w3.org/WAI/WCAG22/Understanding/focus-visible.html)
  is mandatory. Gouda chooses a 2px solid ring with 2px offset, never clipped
  or obscured. Preserve it in forced-colors mode; hover is not focus.
- WCAG's [minimum target criterion](https://www.w3.org/WAI/WCAG22/Understanding/target-size-minimum.html)
  specifies 24 by 24 CSS px with exceptions. Gouda chooses at least 44 by 44
  for standalone controls and future row actions, including quiet text buttons;
  padding may extend beyond the visible label.
- Support 200% text enlargement and
  [reflow at 320 CSS px](https://www.w3.org/WAI/WCAG22/Understanding/reflow.html),
  including 400% browser zoom from a 1280px viewport. Do not rely on fixed row
  heights, hover, or color. Test long descriptions, Category names, and amounts.
- Keep native selection indicators, meaningful amount sign words, and explicit
  inactive/unclassified text. Preserve user selection/copying of financial text.
  If motion is introduced later, honor `prefers-reduced-motion`; v0.1 needs none.

## Toolkit allowlist and ownership

Only four shadcn components are approved for the next restyle:

| Component | Concrete usage |
| --- | --- |
| Button | Report load and Account-discovery retry; later explicit editor actions. |
| Input | The two existing native date inputs; no speculative search field. |
| Label | Associated Account/start/end labels; later Category label. |
| Native Select | Existing Account selection, retaining native keyboard/touch behavior; later a simple Category selector. |

The [Radix collection's Native Select](https://ui.shadcn.com/docs/components/radix/native-select)
wraps native HTML; it does not require inventing a custom listbox. Choose the
Radix collection for shadcn infrastructure, while using native behavior wherever
sufficient. Do not add Radix interaction packages without a component need.
Defer custom Select, Combobox, Command, Popover, Dialog, Tooltip, Separator,
Card, Badge, Skeleton, Calendar/Date Picker, Table/DataTable, Sidebar, and charts.
CSS row borders and native labels/status text suffice for the remaining needs.

Use [Tailwind's Vite integration](https://tailwindcss.com/docs/installation/using-vite)
and [CSS-first theme variables](https://tailwindcss.com/docs/theme) from the
current v4 conventions. Follow the [shadcn Vite setup](https://ui.shadcn.com/docs/installation/vite)
selectively within this existing project: TypeScript, no React Server Components,
semantic CSS variables enabled, no new app scaffold. Verify compatible versions
and pin them at implementation time; this document is not a dependency lockfile.

- Global CSS: Tailwind import, the small semantic token set, `@theme inline`
  mapping, base typography, body defaults, and essential accessibility rules.
  No second large component stylesheet or automatic dark-mode theme/provider.
- Tailwind utilities: local layout, spacing, responsive tracks, typography,
  and state composition. Prefer named utilities and semantic colors; use complete
  literal class names, no runtime-generated fragments. A rare arbitrary grid
  template is acceptable where named tracks cannot express the ledger; repeated
  arbitrary spacing/colors are not.
- `components/ui/`: owned shadcn source for generic controls only. Adapt its
  density, radius, colors, and variants to this document. No Category, sign,
  permission, request, or financial rules in a generic Button/Input.
- Gouda financial presentation: `MoneyAmount` deserves a shared boundary because
  rows and the report total must agree on exact sign/currency/formatting and
  accessible text. A pure string-formatting helper is its testable implementation
  detail, not a new financial calculation library.
- Product components: `MovementList` owns ledger semantics/order/layout;
  `MovementRow` stays local to that module until another consumer exists.
  `ClassificationDisplay` isolates the repeated active/inactive/unclassified
  label mapping and provides a clear seam for the later editor.
- Keep the one `App` shell/header and local `ReportResult` composition in
  `App.tsx`. Do not create `AppShell`, `PageHeader`, typography wrappers, generic
  data grids, a form framework, or a package just to name a single usage.

## Non-goals and review

Avoid enterprise-admin chrome, giant sidebars, excessive cards/badges, gratuitous
icons, unexplained category colors, charts before a reporting question, tiny
muted financial text, hidden signs, unnecessary motion, dense configurable
tables, and copied shadcn-demo aesthetics. No editor, Category CRUD, filtering,
sorting, pagination, summary grid, taxonomy, client-side totals, financial
mutation, new endpoint, or demo classification is part of the next restyle.

Intentionally undecided: final brand accent, logo, dark mode, chart vocabulary,
full dashboard, category visual identity, motion system, mobile-specific
navigation, and complex visualization. Semantic tokens and exact amount
presentation can support later backend-provided household reports, but neither
the layout nor categories establish ownership, transfers, FX, or spending totals.

Proposal challenge: four controls and three extracted presentation components
are enough; no unused overlay or navigation library is approved. The page uses
type and spacing instead of cards. Neutral signed amounts cannot imply
income/expense. Classification has inline expansion space without freezing the
complete editor. Future reports can reuse amount presentation and section
hierarchy without requiring a dashboard today. No persistence, integration,
security, or domain decision is changed; accepted ADRs remain authoritative.

## Visual acceptance

Implementation review must inspect synthetic screenshots and real browser
behavior, not just automated assertions:

- At desktop widths (1024 and 1440px), Account/period, net account effect, and
  Movement amounts are immediately identifiable. Controls and classification
  have less visual weight; no gradient, shadowed panel grid, or admin sidebar.
- A mixed-sign ledger scans vertically: dates compact, descriptions readable,
  amount right edges aligned, all signs/currencies visible. Long content wraps
  without obscuring another row or shrinking financial text.
- Check active, inactive, and both unclassified states in synthetic frontend
  fixtures; the default demo remains classification-free. Names and `Inactive`
  remain legible in grayscale, as do positive/negative signs.
- At 320 and 375px, and 200%/400% zoom, selection controls stack, list content
  stays usable, and financial strings remain complete. Exercise a long exact
  total's local overflow with keyboard and touch if needed.
- Keyboard-only use reaches every control in logical order, submits the form,
  and retains visible unclipped focus. Test native date/select behavior in the
  supported local browsers and a screen reader's amount/classification reading.
- Inspect initial, loading, empty-Account, empty-report, report-error, retry,
  and long-content states. No fake zero totals, stale report context, disappearing
  error text, color-only meaning, or optimistic classification is allowed.
- Measure actual contrast pairs and target sizes; check forced colors and
  reduced motion. Behavioral tests protect API and exact-value invariants;
  human review decides calmness, hierarchy, and visual quality.

## Read-client implementation checkpoint

The implementation checkpoint added Tailwind and only approved shadcn
infrastructure/components, mapped semantic tokens, and restyled the existing
read client while preserving behavior and trust boundaries. Presentation changes
to labels, number formatting, and list anatomy are intentional; requests,
validation, exact values, order, count, privacy, and read-only behavior remain.
No classification write editor or capability consumption was added.

Expected path-by-path scope (new paths below are plans, not existing files):

| Path | Expected change |
| --- | --- |
| `frontend/package.json` | Add compatible pinned Tailwind/toolkit support dependencies only; retain React/Vite and current scripts. |
| `frontend/package-lock.json` | Update from the bounded dependency change. |
| `frontend/components.json` | Minimal shadcn configuration using Radix collection, TypeScript, CSS variables, and existing source paths. |
| `frontend/tsconfig.json` | Add only the source alias needed by generated imports. |
| `frontend/vite.config.ts` | Add Tailwind plugin and matching alias while retaining every proxy/network/security/logger/test option. |
| `frontend/src/styles.css` | Replace existing bespoke presentation with Tailwind import, tokens, theme mapping, and small base rules. |
| `frontend/src/lib/utils.ts` | Minimal class composition/merge helper required by approved shadcn source. |
| `frontend/src/components/ui/button.tsx` | Approved Button source and restrained variants. |
| `frontend/src/components/ui/input.tsx` | Approved Input source, including native date support. |
| `frontend/src/components/ui/label.tsx` | Approved associated Label source. |
| `frontend/src/components/ui/native-select.tsx` | Approved Native Select source for Accounts. |
| `frontend/src/components/gouda/MoneyAmount.tsx` | Shared visible and accessible exact amount presentation. |
| `frontend/src/lib/money.ts` | Pure validated-string formatting; no monetary arithmetic. |
| `frontend/src/components/movements/MovementList.tsx` | Semantic ledger list and local MovementRow. |
| `frontend/src/components/movements/ClassificationDisplay.tsx` | Read-only state presentation. |
| `frontend/src/App.tsx` | Restyle shell/form/summary; compose approved components without request changes. |
| `frontend/src/App.test.tsx` | Adapt table/raw-string assertions to intended list/display while preserving behavior/privacy checks. |
| `frontend/src/lib/money.test.ts` | Exact string/sign/grouping, CLP nonzero fraction, other currency, zero, and large-value cases. |
| `frontend/src/components/gouda/MoneyAmount.test.tsx` | Meaningful accessible amount reading without duplication or precision loss. |
| `frontend/src/test/fixtures.ts` | Synthetic edge cases only if existing fixtures are insufficient. |
| `README.md`, `docs/architecture/overview.md`, `docs/architecture/local-http-delivery.md` | Update setup and actual presentation descriptions after implementation. |
| `docs/design/ui-foundation.md`, `.ai/context.md`, `.ai/handoff.md`, `.ai/tasks/current.md` | Record implementation, review evidence, and the later editor as next scope. |

Keep `api.ts`, its validation tests, the two network-test files, Docker topology,
backend, models, migrations, source contracts, and demo code unchanged. Run the
existing frontend tests, typecheck/build, and dependency-tree check after that
implementation, including real Vite proxy tests. Exercise the supported local
browser path with isolated synthetic data and the visual criteria above; apply
the [agent workflow](../development/agent-workflow.md) for local-stack validation
if that setup changes. Documentation-only validation applies to the present
design checkpoint: links/Markdown, exact paths, privacy, and diff hygiene.
