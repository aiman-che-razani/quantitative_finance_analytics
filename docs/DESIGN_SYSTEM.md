# Design system

The visual language of the Axiom dashboard (`apps/dashboard/`), as it actually exists in
`app/page.tsx` and `app/globals.css` today. It describes current practice, not a wishlist. Verified
line by line against branch `audit-fixes-2` at `0e88254` on 2026-09-29 (`npm run typecheck`
inside `apps/dashboard/` passes clean). Every `path:line` below refers to that tree. Re-check the
line numbers after any edit to either file.

It is a single-user local research workspace, not a marketing site or a consumer trading app.
Prefer clarity of numbers over decoration. Stack: React 19, Next.js 16 (App Router),
`lightweight-charts` 5.2, one plain CSS file (`globals.css`). There is no Tailwind, no CSS modules,
no component library and no ESLint/Prettier config. Don't introduce any of those.

## Ground rules

- The `design-system` agent maintains `docs/DESIGN_SYSTEM.md` (this file). It never edits source
  to fix drift or to add a new element. It reports each deviation or proposal as the exact
  `path:line` plus the exact JSX/CSS, for someone else to apply.
- Colors are literal hex/rgba strings repeated at each use site. There is no CSS custom-property
  palette: `:root` (`globals.css:2-7`) sets only `color-scheme`, the default font, the page
  background and the primary text color. Treat the table below as the source of truth for what to
  reuse, not as variables that exist in code.

## Tokens

| Token | Value | Where |
|---|---|---|
| Page background | `#0b1218` | `globals.css:5` (`:root`) |
| Panel / chart background | `#111a21` | `globals.css:125` (`.panel`), `globals.css:185` (`.metrics > div`); `page.tsx:121`, `page.tsx:187` (chart `layout.background`) |
| Panel border / rules | `#26333d` | `globals.css:23` (header), `73` (`.summary`), `88` (nav), `126` (`.panel`), `186` (`.metrics > div`), `245` (`td`/`th`), `260` (`.paper`), `269` (footer) |
| Chart gridlines | `#1a2832` | `page.tsx:126-127`, `page.tsx:191-192` |
| Primary text | `#dce6ec` | `globals.css:6` (`:root` `color`) |
| Secondary text | `#9eb0bd` | `globals.css:63` (`p`), `83` (`.summary span`), `141` (`label`), `192` (`.metrics span`) |
| Chart axis text | `#9eb0bd` (same as secondary text) | `page.tsx:122`, `page.tsx:188` (`layout.textColor`) |
| Muted / tertiary text | `#7d98aa` | `globals.css:173` (`.source`, `small`), `236` (`th`) |
| Accent green (brand) | `#a8ecb4` | `globals.css:47` (`.status`/`.eyebrow`), `79` (`.summary strong`), `103` (button hover border), `121-122` (`nav .active`), `160` (`.primary` bg), `277` (`a`), `280` (focus outline); `page.tsx:133` (strategy equity line), `page.tsx:196,199` (up-candle body/wick) |
| `.primary` button text (dark green on accent) | `#10261a` | `globals.css:161` |
| Secondary blue | `#8199c5` | `page.tsx:143` (benchmark line), `page.tsx:207-208` (both Bollinger band lines) |
| Amber | `#e5ca8a` | `page.tsx:206` (EMA line); `globals.css:326-329` (`.alert-warn`, `.run-running`) |
| Down / negative red | `#e39d9d` | `page.tsx:197,200` (down-candle body/wick); `globals.css:330-334` (`.alert-danger`, `.run-failed`, `.run-interrupted`) |
| Error banner | bg `#43282c`, text `#ffb4af` | `globals.css:252-257` (`.error`) |
| Brand wordmark / subtitle | `#e6f3e9` / `#8eaaa2` | `globals.css:31` (`.brand`), `globals.css:41` (`.brand span`) |
| Control border / input bg / input text | `#334551` / `#0d161d` / `#e4edf2` | `globals.css:95` (`button`), `145-147` (`input`, `select`) |
| Button bg / hover text | `#1a2933` / `#e3ffec` | `globals.css:93`, `globals.css:104` |
| Button text, heatmap month label | `#c5d6df` | `globals.css:94` (`button`), `224` (`.heatmap small`) |
| `<summary>` text | `#b5c9d6` | `globals.css:250` |
| Heatmap positive / negative | `rgba(80,170,115,α)` / `rgba(210,90,90,α)` | `page.tsx:847-848` (see Components) |

Spacing is ad hoc (12/15/20/22/24/26/36/38/45/50px). There is no spacing scale yet.

**The heatmap pair is its own token.** The monthly-returns heatmap does not use the brand green and
red. It uses its own rgba pair, `rgba(80,170,115,α)` for positive months and `rgba(210,90,90,α)`
for negative ones, with `α = min(0.45, 0.12 + |return| * 8)` (`page.tsx:845-848`). Those values
are close to, but distinct from, `#a8ecb4` (`rgb(168,236,180)`) and `#e39d9d` (`rgb(227,157,157)`).
The 0.45 cap keeps cell text legible. Measured over the `#111a21` panel, the value text
(`#dce6ec`) stays at 6.2:1 or better and the month label (`#c5d6df`) at 5.2:1 or better at full
intensity. Reuse this formula verbatim for any new magnitude-scaled cell. Don't substitute the
brand hex.

**Weight:** big numeric values use weight 500 (`.summary strong` `globals.css:76-78`,
`.metrics strong` `globals.css:196-198`), the same as `h1` (`globals.css:57`) and `h2`
(`globals.css:133`). Only the brand wordmark uses 700 (`globals.css:28`), along with the `.primary`
button text (`globals.css:162`).

**Fonts:** `Space Grotesk` is used for headings, the brand and big numbers. `DM Sans` is the
body/default font (`globals.css:4`). Both load from Google Fonts at `globals.css:1`, weights
400/500/600/700. `color-scheme: dark` is set globally (`globals.css:3`). The theme is dark only.
There is no light-mode branch anywhere in the file.

## Status and alert colour mapping

Both mappings reuse the chart palette: amber means warning or in progress, red means failure. The
comment at `globals.css:319` records that intent.

| Where | Value | Class | Colour |
|---|---|---|---|
| Experiment status (`page.tsx:665-667`, class is `` `run-${status.toLowerCase()}` ``) | `RUNNING` | `.run-running` | amber `#e5ca8a` |
| | `FAILED` | `.run-failed` | red `#e39d9d` |
| | `INTERRUPTED` | `.run-interrupted` | red `#e39d9d` |
| | `SUCCEEDED` | `.run-succeeded` (no rule) | inherits the table text colour |
| Experiment error (`page.tsx:668-672`) | `e.error` | `small.run-error` | muted `#7d98aa`, block, wraps at 360px (`globals.css:335-339`, overriding `td`'s `nowrap`) |
| Paper alert (`page.tsx:733-746`) | `TICK_FAILED` | `.alert-danger` | red `#e39d9d` |
| | `STALE_INPUT`, `RISK_REJECTION`, and any other alert | `.alert-warn` | amber `#e5ca8a` |

The experiment statuses are the backend's `EXPERIMENT_STATUSES` (`axiom/metadata.py:38`). Paper
alerts render with underscores replaced by spaces ("TICK FAILED"), at 11px with 1px letter-spacing
(`globals.css:320-325`). The paper alert mapping is a whitelist of one danger value, so any new
alert type is shown as a warning by default. If a new alert is more severe than a warning, add it
to the `TICK_FAILED` branch at `page.tsx:739`. Don't invent a third colour. Both colours clear
contrast comfortably on the panel (amber 11.0:1, red 8.0:1). The colour is never the only signal,
because the status or alert text is always printed.

## Components and patterns

- **Page shell**: `main` has max-width 1480px and `36px 5vw` padding (`globals.css:14-18`), which
  drops to `24px 5vw` under 800px (`globals.css:284-286`). The page is built from:
  - `header` (`.brand` plus the "PAPER EXECUTION ONLY" status, `page.tsx:403-408`,
    `globals.css:19-48`).
  - `.intro` (headline plus the `.summary` stat grid, `page.tsx:409-427`). The summary is hidden
    under 800px (`globals.css:287-289`).
  - A `nav` of tab buttons: `Research | Market data | Experiments | ML research | Paper accounts`
    (`page.tsx:428-446`).
  - An optional `role="alert"` `.error` banner (`page.tsx:447-451`).
  - A `role="status" aria-live="polite"` region that is **always in the DOM**, so screen readers
    announce changes to it (`page.tsx:452-454`). While an action runs it holds a `<p>` with that
    action's own copy. The copy for each action is listed under Loading/busy below.
- **Nav tabs**: `nav` has `role="tablist"`. Each button has `role="tab"` and
  `aria-selected={tab === t}` (`page.tsx:428-446`). The buttons are borderless and transparent,
  and the active tab is underlined in accent green (`globals.css:113-123`). The focus ring is inset
  (`outline-offset: -3px`, `globals.css:110-112`) so the horizontally scrolling `nav` does not clip
  it. Padding tightens under 450px (`globals.css:312-314`).
- **`.panel`** (`#111a21` bg, `1px solid #26333d`, 8px radius, 24px padding, 22px vertical margin,
  `globals.css:124-130`) is the container for every section: the controls form, each chart, the
  heatmap, the tables and `<details>` blocks, experiment history, the paper ledger and the pooled
  AUC panel. Padding drops to 15px under 800px (`globals.css:301-303`). Exception: each ML
  out-of-sample model block is a bare `<section>` (`page.tsx:884-891`). Only its `Plot` inside is
  a panel.
- **`.controls`** (`globals.css:153-158`) is a 4-column grid that collapses to 2 columns under
  800px (`globals.css:290-292`) and to 1 column under 450px (`globals.css:306-308`). It holds
  `<label>` + `<input>`/`<select>` pairs for dataset, symbols, strategy, commission, EMA window,
  drawdown circuit breaker and entry order, plus the `.check` "Allow short signals" checkbox
  (`page.tsx:457-536`, `globals.css:165-169`). `.primary` spans 2 columns for the submit button
  (`globals.css:159-164`) and reverts to a single column at 450px (`globals.css:309-311`).
- **`Plot`** (`page.tsx:103-166`) wraps `lightweight-charts` for an equity-style line:
  - A green (`#a8ecb4`) primary line, plus an optional thinner (width 1) blue (`#8199c5`)
    benchmark line.
  - Height 300. `fitContent()` runs once per data change (`page.tsx:151`).
  - The container has `role="img"` and `aria-label={title}` (`page.tsx:157`).
  - The caption names only the series actually drawn: "Drag to pan · Scroll to zoom · Green:
    strategy · Blue: buy and hold", or just "… · Green: strategy" when there is no benchmark. A
    `caption` prop overrides it; the drawdown chart uses "Percent below running peak"
    (`page.tsx:158-163`, `829-830`).
  - That caption is the only legend. Keep its colour-to-meaning mapping if this component changes.
- **`MarketPlot`** (`page.tsx:179-236`) is a candlestick chart:
  - Candles are green up and red down (`page.tsx:195-201`).
  - EMA (amber) and both Bollinger bands (blue) are line overlays (`page.tsx:205-209`).
  - Height 420 (`page.tsx:185`).
  - The heading "Daily prices · EMA 200 · Bollinger 200 / 1.19" is repeated as the container's
    `aria-label` with `role="img"` (`page.tsx:225-230`).
  - The caption is "Last 3,000 sessions at most. Pan and zoom to inspect daily bars."
    (`page.tsx:231-233`).
  - The heading's periods are hard-coded. They match the backend `FeatureConfig` defaults
    (`axiom/common/models.py:44-49`), which `GET /market` always uses (`axiom/api.py:117`). The
    Research "EMA window" input does not affect this chart.
- **`Table`** (`page.tsx:237-273`) is a generic key-driven table for any
  `Record<string, unknown>[]`:
  - Column headers are the raw field names with underscores replaced by spaces
    (`page.tsx:245`). They are uppercased by CSS (`th`, `globals.css:234-241`), not relabelled.
  - Numeric cells are formatted with the `en-US` locale to at most 4 decimals
    (`page.tsx:254-257`). Everything else is `String(...)`, with `—` for null or undefined
    (`page.tsx:258`).
  - Only the first 100 rows are shown, followed by "First 100 of N records. Export JSON for the
    complete ledger." (`page.tsx:250`, `265-270`).
  - It renders the market OHLCV rows (last 100 bars, `page.tsx:617-620`), the full metrics dump,
    the execution ledger (fills), closed trades and risk decisions (each in its own
    `<details className="panel">`, `page.tsx:857-879`), pooled test AUC (`page.tsx:903-907`) and
    ML fold results (`page.tsx:913-921`).
- **Metrics grid** (`.metrics`, `globals.css:176-182`):
  - It uses `repeat(auto-fit, minmax(150px, 1fr))`. There are no fixed column counts and no
    breakpoint rules; tiles wrap when they would drop below 150px, which is about the width of
    "-23.45%" at 24px.
  - Each tile is its own small card (`.metrics > div`: `#111a21`, `1px solid #26333d`, 6px
    radius, 20px padding, `globals.css:183-188`). It shows a label (`span`, 11px, `#9eb0bd`,
    `globals.css:189-193`) over a big value (`strong`, `Space Grotesk` 500 24px,
    `globals.css:194-200`).
  - The six tiles are Total return, CAGR, Sharpe, Max drawdown, Win rate and Trades
    (`page.tsx:794-820`).
  - Formatting: `pct()` (`page.tsx:274-275`: ×100, 2 decimals, `—` for a non-number) for the
    percentage tiles. Sharpe uses `.toFixed(2)`, or `—` (`page.tsx:799-804`). Trades uses an
    `en-US` locale integer, or `—` when missing (`page.tsx:807-812`).
- **Monthly-returns heatmap** (`.heatmap`, `globals.css:207-225`):
  - It is a 12-column grid, collapsing to 6 columns under 800px (`globals.css:293-295`) and to 4
    columns under 450px (`globals.css:315-317`).
  - Each cell shows its month (`small`, 9px, `#c5d6df`) over `pct(v)` (`strong`, 11px). The cell
    background uses the heatmap rgba pair with `α = min(0.45, 0.12 + |return| * 8)`
    (`page.tsx:833-856`, formula at `847-848`), so intensity scales with magnitude rather than a
    fixed threshold.
- **ML result sections** (`page.tsx:882-923`), in this order:
  - One block per model: "`<name>` · Out-of-sample trading", a text line with total return and
    drawdown via `pct()`, and a `Plot` of that model's equity.
  - A **Pooled test AUC** panel (`page.tsx:893-909`). Its `.source` caveat says per-fold AUC on
    short windows reads above 0.5 even with no signal, that pooled AUC must be compared with a
    random-walk null (`scripts/demo_ml.py`) rather than with 0.5, and that the dashboard does not
    compute that null, so the values are not evidence of skill. It is followed by a `Table` of
    model → `pooled_test_auc` (null shown as `—`).
  - The "Prediction evaluation by test fold" table (`page.tsx:910-923`), below the AUC panel.
- **Paper accounts** (`page.tsx:700-777`): each account is an `article.paper` (top rule,
  `globals.css:258-262`) containing:
  - The id in `<code>`.
  - A `.source` provenance line (see rule 1).
  - "Last session: … · Equity: …", where equity is `$` to 2 decimals, or `—` when missing, and
    the session is "Not started" when null (`page.tsx:729-732`).
  - Coloured alert labels (see the mapping above).
  - An optional `<small>` "Last tick error: …" line when `state.last_error` is set
    (`page.tsx:747-751`).
  - A "Replay through" date form with an "Advance ledger" button (`page.tsx:752-773`,
    `globals.css:263-267`).
- **Buttons** (`globals.css:92-109`):
  - Default: `#1a2933` bg, `#c5d6df` text, `#334551` border. On hover the border turns
    `#a8ecb4` and the text `#e3ffec`.
  - `.primary`: solid `#a8ecb4` bg, `#10261a` text, weight 700.
  - Disabled: `opacity: .45`, `cursor: not-allowed`.
  - Every action button is disabled while `busy` is non-empty. Buttons that need a dataset are
    also disabled when none is selected, and "Open" is disabled unless the experiment `SUCCEEDED`
    (`page.tsx:539`, `593`, `634`, `677`, `709`, `772`). "Export JSON ↓" (`page.tsx:785`) is never
    disabled.
- **Focus**: every element uses a global `:focus-visible` 2px accent-green outline, offset 3px
  (`globals.css:279-282`). The nav overrides the offset to be inset.

### States

- **Loading / busy.** Every mutating or fetching action goes through `action(fn, label)`
  (`page.tsx:344-358`). It sets `busy` to that action's label, clears the error, runs `fn`, and
  then always calls `refresh()`, even after a failure. If that refresh fails, its error is shown
  only when the action did not already set one (`page.tsx:353-355`: `setError(old => old || …)`).
  Labels:
  - "Running research… You can find its durable status in experiment history." (`page.tsx:548`)
  - "Loading market data…" (`602`)
  - "Refreshing…" (`635`)
  - "Opening experiment…" (`687`)
  - "Creating paper account…" (`713`)
  - "Updating paper ledger…" (`760`)
  - The default label, "Working…" (`344`), is unused today.
- **Error.** Errors appear in a single `.error` banner with `role="alert"` (`page.tsx:447-451`).
  An error from the initial load also lands here (`page.tsx:341-343`). The client error copy is in
  `api()` (`page.tsx:58-102`):
  - "Dashboard server unreachable. Check experiment history before retrying." when the fetch
    itself throws (`72-74`).
  - The API's `detail` string, or validation errors joined as `field: msg · …` (`82-93`).
  - "Research API error N. Check experiment history before retrying." for a non-JSON error body
    (`94`).
  - "Research API returned an unreadable response. Check experiment history before retrying." for
    a 2xx response that isn't JSON (`97-100`).
  - The per-row experiment error (`small.run-error`) and the paper "Last tick error" line are
    in-context, not banners.
- **Empty.** Two views have explicit empty-state copy:
  - Research/ML with no datasets: "No dataset versions yet. Ingest one with scripts/ingest.py,
    then reload." (`page.tsx:557-562`). The source line then shows "Provider: unknown · — bars".
  - Market data with nothing loaded: "No market data loaded. Enter a symbol and choose Load market
    data." (`page.tsx:622-626`).

  The experiment table, the paper-account list, a zero-row `Table` and an empty heatmap have no
  empty state (see Known gaps).

## Semantic rules (content that must stay honest)

1. **Synthetic vs. provider-sourced is surfaced wherever data is shown. Do not regress it.** One
   helper, `provenanceNote(provider)` (`page.tsx:386-389`), returns "SYNTHETIC DATA — engineering
   demonstration, not observed market performance." when the provider name contains `"synthetic"`,
   and "Provider: <name>" otherwise. It returns "Provider: unknown" when the name is missing. It is
   used in four places:
   - **Research / ML controls** (before running): `provenanceNote(selected?.provider)`, then the bar
     count (`—` if no dataset is selected) and the fill/slippage assumptions (`page.tsx:563-567`).
   - **Market data**: once bars are loaded, the line describes **the loaded bars**. It uses
     `barsSource`, the dataset captured at load time (`page.tsx:601`), not whatever Research
     currently selects. It falls back to the current selection only when nothing is loaded
     (`page.tsx:608-613`).
   - **Each paper account**: it uses `p.state.provider` first, falls back to looking up
     `p.config.dataset_id` in the datasets list, and shows "Provider: unknown" when both are missing
     (`page.tsx:721-728`).
   - **The result header**: `provenanceNote(result.provenance.provider)`, the first 12 characters of
     `dataset_id` (`?.slice(0, 12) ?? "—"`), and the experiment id (`page.tsx:787-793`). Unlike the
     other three, a result with no provider shows a bare `—` in place of the note, not "Provider:
     unknown".

   A new result-summary view should follow the `page.tsx:787-793` pattern, not omit it.
2. **A lost connection is not a failed run.** The research busy copy (`page.tsx:548`) and every
   generic client error in `api()` (`page.tsx:72-74`, `94`, `97-100`) point the user at experiment
   history ("Check experiment history before retrying.") rather than implying failure. The proxy's
   own 502 says the same ("Research API unavailable or request timed out. Check experiment history
   before retrying.", `apps/dashboard/app/api/[...path]/route.ts:75-83`). `action()` refreshes
   history even after a failure, so the Experiments tab reflects what actually happened
   (`page.tsx:352-355`). Keep that framing in any new async-action UI. Do not add a generic
   "Something went wrong, try again", which invites duplicate POSTs.
3. **Classification metrics and trading metrics are kept apart.** The ML view renders the
   out-of-sample trading results (return/drawdown text plus a `Plot` per model,
   `page.tsx:882-892`), the pooled test AUC panel (`page.tsx:893-909`) and the per-fold
   classification table (`page.tsx:910-923`) as separately headed sections. None of them is merged
   into the `.metrics` tile grid. Keep this separation, and keep the AUC null-reference caveat next
   to any AUC figure.
4. **Missing/null values render as `—`, never `0` or a blank cell.** This holds in:
   - `Table` (`page.tsx:258`)
   - `pct()` (`page.tsx:274-275`) and `formatMetric()` (`page.tsx:303`)
   - the Sharpe and Trades tiles (`page.tsx:801-803`, `809-811`)
   - the pooled AUC null (`page.tsx:905`)
   - paper equity (`page.tsx:731`)
   - the result `dataset_id` (`page.tsx:791`)
   - the Research bar count (`page.tsx:565`)
   - the market-data dataset id (`page.tsx:612`)
5. **Units are consistent between the tiles and the table.**
   - Returns, drawdowns and other fraction metrics (`PCT_METRICS`, `page.tsx:278-290`) are `%` to 2
     decimals via `pct()`.
   - `MONEY_METRICS`, meaning the per-trade P&L metrics `average_winner`, `average_loser` and
     `expectancy` (`page.tsx:291-295`), are `$` to 2 decimals via `money()` (`page.tsx:296-301`).
   - **Turnover is a multiple, "N.NN×"** (`page.tsx:306`), not dollars.
   - Everything else is at most 4 decimals in the `en-US` locale (`page.tsx:307`).
   - Sharpe is a unitless 2-decimal number.
   - Paper equity is `$` to 2 decimals.
   - Experiment creation times go through `new Date(created_at).toISOString()` before being
     printed as `YYYY-MM-DD HH:MM UTC`, so the "UTC" label is true whatever offset the API sends
     (`page.tsx:654-660`).
   - Prices in the market chart carry no currency label, because everything is USD per the
     backend's `Instrument.currency: Literal["USD"]`. If a non-USD instrument is ever proposed, say
     so explicitly, since the UI has no currency-formatting path.

## Known gaps to keep in the register (re-verify each time)

- **Accessibility.** The dashboard relies on native semantics plus a few ARIA attributes: the
  `role="alert"` error banner, the always-present `role="status" aria-live="polite"` busy region,
  `role="tablist"`/`role="tab"`/`aria-selected` on the nav, and `role="img"` with an `aria-label`
  on both chart components. Gaps:
  - The tab pattern is incomplete. There is no `role="tabpanel"` and no
    `aria-controls`/`aria-labelledby`, and there is no arrow-key navigation or roving
    `tabindex`, so every tab is a separate Tab stop.
  - There is no `prefers-reduced-motion` handling. This is low risk, because the charts don't
    animate on data change.
  - The equity and drawdown charts have no text or tabular alternative. The market chart has the
    collapsed OHLCV table, and the heatmap is readable as text (month + percentage).
- **Small type.** `.status` shrinks to 8px under 800px (`globals.css:296-300`). The heatmap month
  label is 9px (`globals.css:222-225`).
- **Missing empty states.** Experiment history renders an empty table body when there are no
  experiments (`page.tsx:652`). The paper list renders nothing when there are no accounts
  (`page.tsx:718`). A zero-row `Table` (for example, "Closed trades" for a run with no trades)
  renders an empty table with no header and no message (`page.tsx:238`). An empty
  `monthly_returns` renders an empty "Monthly returns" panel.
- **Inconsistent missing-provider text.** The result header shows a bare `—` for a missing
  provider (`page.tsx:788-790`). The other three provenance lines show "Provider: unknown".
- **ML out-of-sample blocks sit outside a panel.** They are bare `<section>`s
  (`page.tsx:884-891`), so their heading and summary text sit outside any panel, unlike every
  other result section.
- **Hard-coded market chart heading.** The `MarketPlot` heading hard-codes "EMA 200 · Bollinger
  200 / 1.19" (`page.tsx:225`, `229`). It is correct only while the backend `FeatureConfig`
  defaults stay unchanged.
- **Tooling.** The dashboard has no configured linter, formatter or CI check beyond
  `npm run build` in CI and `npm run typecheck` locally (see `docs/CODE_STYLE.md`), so review, not
  CI, catches visual regressions.
- **Literal colours.** Colours are literal hex/rgba strings repeated at every use site rather than
  CSS custom properties. The heatmap rgba pair is effectively a second green/red token. Introducing
  `:root` variables, and naming both pairs, would reduce drift. That is a real refactor, so propose
  it rather than doing it inline in an unrelated change.

## Designing something new

Reuse `.panel`, the metrics-grid, heatmap and table patterns, the status/alert classes and the token
list above. Avoid new colours, fonts or libraries:

- Don't use the heatmap's rgba pair for anything that isn't a magnitude-scaled cell.
- Don't use the brand hex for a heat cell.
- Use amber/red only through the existing `.alert-*`/`.run-*` meaning (warning or in progress vs.
  failure).

Route every async action through `action()` with its own busy label. Give explicit empty, busy and
error states that match the copy style above. Keep the element usable at the handled breakpoints
(800px, 450px) and in the auto-fit metrics grid. Respect the semantic rules, especially the
provenance line and the synthetic-vs-real label.
