# Design system

The visual language of the Axiom dashboard (`apps/dashboard/`), as it actually exists in
`app/page.tsx` and `app/globals.css` today — a description of practice, not a wishlist. Verified
against the tree as of 2026-09-28 (`npm run typecheck` inside `apps/dashboard/` passes clean, no
errors).

It is a single-user local research workspace, not a marketing site or a consumer trading app.
Prefer clarity of numbers over decoration. Stack: React 19, Next.js 16 (App Router),
`lightweight-charts` 5.2, one plain CSS file (`globals.css`) — no Tailwind, no CSS modules, no
component library, no ESLint/Prettier config. Don't introduce any of those.

## Ground rules

- `docs/DESIGN_SYSTEM.md` (this file) is maintained by the `design-system` agent. Source is never
  edited to fix drift or add a new element — deviations and proposals are reported as the exact
  `path:line` + the exact JSX/CSS, for someone else to apply.
- Colors are literal hex/rgba strings repeated at each use site — there is no CSS custom-property
  palette (`:root` in `globals.css` holds no color tokens, only global resets). Treat the list
  below as the source of truth for what to reuse, not as variables that exist in code.

## Tokens

Verified against `globals.css` and `page.tsx` inline hex.

| Token | Value | Where |
|---|---|---|
| Page background | `#0b1218` | `globals.css:5` (`:root`) |
| Panel / chart background | `#111a21` | `globals.css:122` (`.panel`); `page.tsx:90`, `page.tsx:153` (chart `layout.background`) |
| Panel border / chart gridlines | `#26333d` / `#1a2832` | `globals.css:123` (`.panel`), `globals.css:23,88,265` (header/nav/footer rules); `page.tsx:95-96`, `page.tsx:157-158` (chart grid lines) |
| Primary text | `#dce6ec` | `globals.css:6` (`:root` `color`) |
| Secondary text | `#9eb0bd` | `globals.css:63` (`p`), `globals.css:83` (`.summary span`), `globals.css:138` (`label`), `globals.css:188` (`.metrics span`) |
| Muted / tertiary text | `#7d98aa` | `globals.css:170` (`.source`, `small`), `globals.css:232` (`th`) |
| Accent green (brand) | `#a8ecb4` | `globals.css:47` (`.status`/`.eyebrow`), `globals.css:79` (`.summary strong`), `globals.css:103` (button hover border), `globals.css:118-119` (`nav .active`), `globals.css:157` (`.primary` bg), `globals.css:273` (`a`), `globals.css:276` (focus outline), `page.tsx:102` (strategy equity line), `page.tsx:162,165` (up-candle body/wick) |
| `.primary` button text (dark green, on accent bg) | `#10261a` | `globals.css:158` |
| Secondary blue | `#8199c5` | `page.tsx:112` (benchmark line), `page.tsx:174` (both Bollinger band lines) |
| Amber | `#e5ca8a` | `page.tsx:172` (EMA line) |
| Down/negative red | `#e39d9d` | `page.tsx:163,166` (down-candle body/wick) |
| Error banner | bg `#43282c`, text `#ffb4af` | `globals.css:249-252` (`.error`) |

**Drift found:** the monthly-returns heatmap does **not** use the accent green / down-red hex
tokens above. It uses its own literal rgba pair — `rgba(80,170,115,α)` positive,
`rgba(210,90,90,α)` negative, `α = min(0.8, 0.12 + |return| * 8)` — defined inline at
`page.tsx:673-676`. These are close to, but distinct from, `#a8ecb4` (`rgb(168,236,180)`) and
`#e39d9d` (`rgb(227,157,157)`). Treat the heatmap pair as its own token, not as the brand
green/red — see Components below, reuse the rgba formula verbatim for any new magnitude-scaled
cell rather than substituting the brand hex.

**Fixed 2026-09-28 (font weight):** big numeric values are now uniformly weight 500. `.summary
strong` and `.metrics strong` (`globals.css`) previously used the `font` shorthand without a
weight component, which the CSS spec resets to `normal` (400) rather than inheriting or defaulting
to bold — both now include an explicit `500`, matching `h1`/`h2`.

Fonts: `Space Grotesk` (headings, brand, big numbers) and `DM Sans` (body/default), both loaded
from Google Fonts at `globals.css:1` (weights 400/500/600/700 for both). `color-scheme: dark` is
set globally (`globals.css:3`) — dark theme only, no light-mode branch anywhere in the file.

## Components and patterns

- **Page shell**: `main` max-width 1480px, `36px 5vw` padding (`globals.css:14-18`). `header`
  (`.brand` + status, `globals.css:19-25`), `.intro` (headline + `.summary` stat grid — hidden
  under 800px, `globals.css:49-54,283-285`), `nav` of tab buttons (`Research | Market data |
  Experiments | ML research | Paper accounts`, `page.tsx:338-353`), an optional `role="alert"`
  `.error` banner (`page.tsx:354-358`), an optional `role="status"` busy line — "Running
  research… You can find its durable status in experiment history." (`page.tsx:359-364`).
- **`.panel`** (`#111a21` bg, `1px solid #26333d`, 8px radius, 24px padding —
  `globals.css:121-127`) is the one container class used for every section: controls form, each
  chart, the metrics grid tiles (own smaller card, see below), tables, the paper-accounts list.
- **`.controls`** (`globals.css:150-155`) 4-column grid, collapsing to 2 columns under 800px
  (`globals.css:286-288`) then 1 column under 450px (`globals.css:308-310`); holds `<label>` +
  `<input>`/`<select>` pairs for dataset, symbols, strategy, cost/risk/order-type fields.
  `.primary` spans 2 columns for the submit button (`globals.css:156-161`), reverting to a single
  column at 450px (`globals.css:311-313`).
- **`Plot`** (`page.tsx:74-132`) wraps `lightweight-charts` for an equity curve: a green (`#a8ecb4`)
  strategy line plus an optional thinner blue (`#8199c5`) benchmark line, `fitContent()` on load
  (`page.tsx:120`), caption "Drag to pan · Scroll to zoom · Green: strategy · Blue: buy and hold"
  (`page.tsx:127-129`) — keep that caption's color-to-meaning mapping if this component is touched,
  it is the only legend. Its chart container has `role="img"` plus an `aria-label` (a bare `aria-label` on a role-less `<div>` is ignored by screen readers; fixed 2026-09-28). The caption names only the series actually drawn (a `caption` prop overrides it, e.g. the drawdown chart).
- **`MarketPlot`** (`page.tsx:145-198`): a candlestick chart (green up / red down,
  `page.tsx:161-167`) plus EMA (amber, `page.tsx:172`) and both Bollinger bands (blue,
  `page.tsx:173-174`) as line overlays, height 420 (`page.tsx:151`), caption noting the 3,000-session
  cap (`page.tsx:193-195`). **Fixed 2026-09-28:** its chart container now carries
  `role="img"` and an `aria-label` matching the heading text, consistent with `Plot`.
- **`Table`** (`page.tsx:199-235`): a generic key-driven table for any `Record<string, unknown>[]`.
  Numeric cells are locale-formatted to 4 decimal places (`page.tsx:216-219`), everything else is
  `String(...)` with `—` for null/undefined (`page.tsx:220`); column headers are the raw field name
  with underscores replaced by spaces, not title-cased or relabeled (`page.tsx:207`); capped at the
  first 100 rows with a note to export JSON for the rest (`page.tsx:212,227-232`).
  **Fixed 2026-09-28:** this generic `Table` now also renders fills, closed trades, and risk
  decisions as three separate `<details className="panel">` blocks (`page.tsx`, right after
  "Execution ledger"), alongside market-data OHLCV rows, the full metrics dump, and ML fold
  results. `Result.simulation.trades` was previously typed and populated by the API but never
  rendered anywhere in the UI — it now has its own "Closed trades" panel.
- **Metrics grid** (`.metrics`, `globals.css:173-178`; 6 columns collapsing to 3 under 800px
  `globals.css:289-291`, then 2 under 450px `globals.css:305-307`): each `<div>` is a label
  (`span`, 11px, secondary text `#9eb0bd`) over a big value (`strong`, `Space Grotesk` 24px, weight
  500 — see note above) — Total return, CAGR, Sharpe, Max drawdown, Win rate, Trades
  (`page.tsx:630-641`), formatted by the shared `pct()` helper (`page.tsx:236-237`, `×100` + 2
  decimals, or `—` for a non-number) or `.toFixed(2)` for Sharpe (`page.tsx:634-637`).
- **Monthly-returns heatmap** (`.heatmap`, `globals.css:203-207`; 12-column grid collapsing to 6
  under 800px `globals.css:292-294`): each cell's background is `rgba(80,170,115, α)` for a
  positive month or `rgba(210,90,90, α)` for a negative one, `α = min(0.8, 0.12 + |return| * 8)` —
  intensity scales with magnitude, not a fixed threshold (`page.tsx:667-684`, formula at
  `page.tsx:673-676`). Reuse this exact formula (including the rgba pair, not the brand hex — see
  token drift above) for any new magnitude-scaled heat cell.
- **Paper accounts list**: each account's `state.alerts` array is joined and shown as plain text
  (`page.tsx:591`, `p.state.alerts.join(" · ")`) — no colored badges today. If badges are added,
  map `STALE_INPUT`/`RISK_REJECTION`/`TICK_FAILED` to a consistent warn/danger treatment rather
  than one-off colors, and document that mapping here.
- **Buttons** (`globals.css:92-120`): default (`#1a2933` bg, `#c5d6df` text, hover border
  `#a8ecb4` / text `#e3ffec`), `.primary` (solid `#a8ecb4` bg, `#10261a` text, weight 700), `nav`
  buttons are borderless/transparent with the active tab underlined in accent green
  (`globals.css:110-119`), disabled state (`opacity: .45`, `cursor: not-allowed`,
  `globals.css:106-109`); the busy message lives in a persistent `role="status"` region that
  names the running action. Nav tabs mark the selected tab with `aria-current="page"` and use an
  inset focus ring so the scrolling `nav` does not clip it.

## Semantic rules (content that must stay honest)

1. **Synthetic vs. provider-sourced is surfaced in the UI — this closes a gap the previous version
   of this doc's source brief flagged as open. Do not regress it.** `page.tsx` shows dataset
   provenance in two places:
   - Before running, the `.source` line reads either `"SYNTHETIC DATA — engineering demonstration,
     not observed market performance."` when the selected dataset's provider name contains
     `"synthetic"`, or `"Provider: " + provider` otherwise (`page.tsx:467-473`).
   - After a result loads, a second `.source` line renders `result.provenance?.provider`, the
     first 12 characters of `result.provenance?.dataset_id`, and the experiment/result id
     (`page.tsx:624-627`).

   Both caveats below were **fixed 2026-09-28**:
   - The post-run `.source` line now mirrors the pre-run selector's `.includes("synthetic")`
     check, instead of only printing the raw provider string.
   - `result.provenance?.dataset_id.slice(0, 12)` (unguarded past the first `?.`, would throw on
     a result with no `provenance`) is now `result.provenance?.dataset_id?.slice(0, 12) ?? "—"`,
     consistent with rule 4 below.
2. **A lost connection is not a failed run.** The busy-state copy points the user at experiment
   history rather than implying failure (`page.tsx:359-364`) — keep that framing in any new
   async-action UI; do not add a generic "Something went wrong, try again" that invites duplicate
   POSTs. (The 502 proxy message itself lives outside `page.tsx`/`globals.css` — in the API route —
   so it is out of this file's verified scope, but the client-side busy/error copy pattern here is
   consistent with that framing.)
3. **Classification metrics and trading metrics are kept apart, correctly.** The ML-research result
   view renders `out_of_sample_trading` (total return/drawdown text + a `Plot`, one section per
   model, `page.tsx:703-713`) and `folds` (a `Table` of `f.models` accuracy/log-loss-style fields,
   headed "Prediction evaluation by test fold", `page.tsx:714-727`) as two separate, separately
   headed sections — they are not merged into the shared `.metrics` tile grid. No violation found;
   keep this separation for any new ML view.
4. **Missing/null values render as `—`, never `0` or a blank cell.** Confirmed in `Table`
   (`page.tsx:220`), `pct()` (`page.tsx:236-237`), and the paper-account equity line
   (`page.tsx:589`, `... || "—"`). The provenance `dataset_id` line under rule 1 above now
   follows this too, after the 2026-09-28 fix.
5. **Units/precision are shown consistently.** Returns and drawdowns as `%` to 2 decimals via
   `pct()`; Sharpe as an unitless 2-decimal number (`.toFixed(2)`); the "Full performance and risk
   metrics" `Table` instead uses the generic 4-decimal numeric formatting for every metric it lists
   (`page.tsx:687-691`) — that's a real, if minor, precision inconsistency between the tile grid
   (2dp) and the full-metrics table (4dp) for the same underlying numbers, but it matches the
   brief's description of `Table`'s generic formatting, so it's treated as intended rather than a
   bug. Prices in the market chart carry no explicit currency label (everything is USD, per the
   `Instrument.currency: Literal["USD"]` contract on the backend) — if a non-USD instrument is ever
   proposed, say so explicitly, since the UI has no currency-formatting path today.

## Known gaps to keep in the register (re-verify each time)

- No accessibility pass beyond native semantics (`role="alert"`, `role="status"`,
  both `Plot` and `MarketPlot` now carry a chart `aria-label`, fixed 2026-09-28). No
  `prefers-reduced-motion` handling
  (charts don't animate on data change, only on mount, so this is low-risk but undocumented). No
  screen-reader-usable alternative to the charts or the heatmap.
- No configured linter/formatter/CI check for the dashboard beyond `npm run build` in CI and
  `npm run typecheck` locally (see `docs/CODE_STYLE.md`) — a visual regression here is caught by
  review, not CI. `npm run typecheck` passes clean as of 2026-09-28.
- Colors are literal hex/rgba strings repeated at every use site rather than CSS custom
  properties; introducing `:root` variables would reduce drift risk the next time a color changes,
  but is a real refactor, not a one-line fix — propose it rather than doing it inline in an
  unrelated change.
- The heatmap's rgba pair (`rgba(80,170,115,α)` / `rgba(210,90,90,α)`) is a de-facto second
  green/red token distinct from the brand `#a8ecb4`/`#e39d9d` hex — worth formalizing (e.g. naming
  both pairs explicitly) if a `:root`-variable refactor ever happens.

## Designing something new

Reuse `.panel`, the metrics-grid/heatmap/table patterns, and the token list above; avoid new
colors, fonts or libraries — including avoiding the heatmap's rgba pair for anything that isn't a
magnitude-scaled cell, and avoiding the brand hex for a heat cell (they're documented as separate
tokens above). Give explicit empty, loading (`busy`), and error states matching the existing copy
style. Keep it usable at the two already-handled breakpoints (800px, 450px). Respect the semantic
rules above, especially provenance/synthetic-vs-real labeling — which is already live in two
places, so a new result-summary view should match `page.tsx:624-627`'s pattern, not omit it.
