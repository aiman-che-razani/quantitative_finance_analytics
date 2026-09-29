# Code style

Conventions observed in the current Axiom tree, for keeping new code consistent with what's
already here. This is a description of practice, not a wishlist — where the codebase is
inconsistent, that's called out explicitly rather than papered over.

## Verification

Axiom's Python is enforced by CI (`.github/workflows/ci.yml`, `python` job): `ruff check`,
`ruff format --check` and `mypy axiom scripts` run on every push/PR and must pass. That job runs
on a Python 3.12/3.14 matrix (3.12 for development and the native build, 3.14 because the Docker
image ships it); ruff (`target-version = "py312"`) and mypy (`python_version = "3.12"`) still
target 3.12, so new code must stay 3.12-compatible. A separate `windows` job runs `pytest` on
3.12 without PostgreSQL (the database tests skip there). As of 2026-09-29, on this tree
(`audit-fixes-2` at `0e88254`):

```
$ uv run ruff check axiom tests scripts alembic
All checks passed!

$ uv run ruff format --check axiom tests scripts alembic
63 files already formatted

$ uv run mypy axiom scripts
Success: no issues found in 51 source files
```

(On this Windows checkout, use `.venv\Scripts\python.exe -m ruff ...` / `-m mypy ...` instead of
`uv run`.) All three pass clean. A regression here is a finding, full stop, not a style opinion.

The dashboard's `typecheck` script (`tsc --noEmit`) **is** gated in CI: the `dashboard` job runs
`npm ci`, `npm run typecheck`, then `npm run build`. It passes clean on this tree. There is no
`lint`/`format` script and no ESLint/Prettier config, so TypeScript formatting below is
observed-and-matched-by-hand; only type errors are enforced.

## Ground rules

- `docs/CODE_STYLE.md` (this file) is maintained by the `code-style` agent. Source is never edited
  to chase style; deviations are reported as `file:line` + the exact fix, for someone else to apply.
- Don't reformat untouched code, add type hints to code a diff didn't touch, or restyle the V0.1
  legacy modules (`axiom/cli.py`, `axiom/research.py`, `axiom/backtest/engine.py`,
  `axiom/strategies/simple.py`, `axiom/analytics/metrics.py`) to match V0.2+ conventions, unless a
  diff already touches them.

## Python (`axiom/`, `tests/`, `scripts/`, `alembic/`)

Python 3.12+, `ruff` line-length 100, rules `E4,E7,E9,F,I`.

- **Naming**: `snake_case` functions/variables, `CapWords` classes, `UPPER_CASE` module-level
  constants (`UNIVERSE`, `STRATEGIES`, `FEATURES`, `SCHEMA`, `SCHEMA_TYPES`, `STALE_AFTER_DAYS`,
  `EXPERIMENT_STATUSES`, `EXPERIMENT_KINDS`), lowercase module names; a leading underscore for
  module-private helpers (`_one_of` in `axiom/metadata.py:42`).
- **Formatting**: double quotes, 4-space indent, line-length 100 via `ruff format` — run the
  formatter rather than hand-matching it; it's the standard, not a majority style among several.
- **Import order**: enforced by ruff's `I` (isort) rule — standard library, then third-party, then
  `axiom...`, alphabetized within each group. **Imports belong at module level by default.** A
  function-body import is justified only for an optional or genuinely heavy dependency that
  shouldn't load at CLI/API-startup time:
  - `axiom/platform.py:62` imports `axiom.ml.walkforward` (scikit-learn/XGBoost) only when an
    `ml` experiment runs;
  - `axiom/data/providers.py:80` imports `yfinance` (the optional `yahoo` extra) inside
    `YahooProvider.fetch`.

  `axiom/ml/walkforward.py` itself imports `FeaturePipeline`/`FeatureConfig` at module level
  (`walkforward.py:18-19`) — in-tree modules are never "heavy" enough to defer. See Known
  deviations for the remaining function-body imports that don't meet this bar.
- **Type hints**: the norm for the request/response and domain-model boundary — `mypy` runs with
  `check_untyped_defs = True` and the `pydantic.mypy` plugin, and passes clean. New functions in
  that layer should be typed like the surrounding code (`def target(row: dict, strategy: str,
  current: int = 0, allow_short: bool = False) -> int:`, `axiom/backtest/events.py:42`); pydantic
  models (`ConfigDict(extra="forbid")`, often `allow_inf_nan=False`) are the standard way to
  validate external input (`ResearchRequest`, `FeatureConfig`, `ExecutionConfig`, `RiskConfig`) —
  don't accept a raw untyped `dict` where a pydantic model already exists for the shape.
  **Caveat**: this is not applied uniformly. The orchestration layer that threads a SQLAlchemy
  `sessions`/`settings` object through — e.g. `axiom/paper.py:29` (`create_account`),
  `axiom/paper.py:51` (`advance`), `axiom/platform.py:23` (`run_experiment`), `axiom/api.py:52`
  (`create_app(settings=None)`), `axiom/metadata.py:75` (`database(url: str)`, no return type) —
  is routinely untyped or only partially typed. `mypy` still passes because
  `disallow_untyped_defs` is not set. Match whichever pattern the function's own layer already
  uses: fully typed for domain/business logic (`backtest/`, `features/`, `portfolio/`,
  `common/models.py`, `ml/walkforward.py`'s public surface), pragmatic/untyped for DB-session
  plumbing and orchestration.
- **Dataclasses**: for internal, non-validated state that pydantic's validation overhead doesn't
  buy anything for (`Order`, `Position`/`Account`, `Decision`, `QualityReport`) — `@dataclass` with
  `field(default_factory=...)`/`field(init=False)` as needed. `Order.__post_init__`
  (`axiom/backtest/orders.py:18`) and `Account.fill`/`mark` (`axiom/portfolio/account.py:28`,
  `:93`) show the pattern of validating inputs and raising `ValueError`/`ArithmeticError` inline
  rather than deferring to a separate validator. `__post_init__` methods consistently omit
  `-> None` throughout the codebase — that's the established local convention, not an omission
  to flag.
- **Derived constants over duplicated literals**: when the same set of values appears in Python
  and in generated SQL, build the SQL from the constant. `ExperimentRow`'s `CheckConstraint`s are
  built with `_one_of("status", EXPERIMENT_STATUSES)` / `_one_of("kind", EXPERIMENT_KINDS)`
  (`axiom/metadata.py:38-53`); Alembic migrations deliberately keep their own frozen literals, as
  the comment in `_one_of` says — don't "fix" a migration to import the constant.
- **Module docstrings**: a one-line design statement, not a summary (`"""Idempotent paper replay;
  never sends orders to a broker."""`, `"""Immutable single-writer Parquet snapshots with
  completion manifests."""`, `"""Order objects and conservative daily-bar execution-price
  rules."""`). Most modules have one. Without one: `risk/engine.py`, `settings.py`,
  `data/incremental.py`, `__main__.py`, and the empty `ml/`, `risk/`, `portfolio/` `__init__.py`
  files; the other package `__init__.py` files use a generic `"""Axiom <subsystem> subsystem."""`
  line. Match the file: add a one-liner explaining the non-obvious design choice, not a
  restatement of the filename.
- **Comments**: explain **why**, especially where the math or the ordering is load-bearing: "Close
  before reversing; opposite entry can occur after the next signal." (`axiom/backtest/events.py:160`),
  "Cash cannot finance new longs; covering shorts is handled above." (`axiom/risk/engine.py:64`),
  "Strict JSON also catches NaN leaking from analytics before persistence."
  (`axiom/platform.py:114`), "Calendar days without a new bar after which a paper account is
  flagged STALE_INPUT." (`axiom/paper.py:25`). A trailing inline comment marking a genuinely
  non-obvious ordering constraint, e.g. `# Unknown intrabar sequence: defer limit eligibility.`
  (`axiom/backtest/orders.py:48`), fits this pattern. Flag comments that narrate the code instead.
- **Errors**: `raise ValueError(...)` with a specific human-readable message for bad input/state
  (`"Conflicting overlap: publish an explicitly corrected dataset instead"`, `"Portfolio requires
  aligned daily sessions"`, `"Invalid order"`, `"Invalid fill"`). Where the API must distinguish
  a failure's HTTP status, define a small named subclass in the owning module with a docstring
  stating the status, rather than matching on message text — `axiom/paper.py:17-22`:
  - `UnknownPaperAccount(LookupError)` → **404** (deliberately *not* a `ValueError`, so a generic
    `except ValueError` can't turn it into a 422);
  - `PaperConflict(ValueError)` → **409** (valid request that conflicts with recorded state).

  At the API boundary (`axiom/api.py`), handlers catch the **more specific exceptions first**,
  then `ValueError` → 422, always re-raising with `from exc`: `POST /paper/{id}/advance`
  (`api.py:226-231`) catches `UnknownPaperAccount` → 404, `PaperConflict` → 409, then
  `ValueError` → 422; `POST /experiments` (`api.py:187-188`) and `POST /paper` (`api.py:217-218`)
  only need `ValueError` → 422. Since `PaperConflict` is a `ValueError`, putting the
  `except ValueError` first would silently downgrade a 409 to a 422 — keep the order. Don't raise
  a bare `Exception` or a generic message where the existing pattern names the specific problem.
  `ArithmeticError` is reserved for **ledger/accounting invariants** that should be impossible —
  `axiom/portfolio/account.py:103` ("Portfolio ledger failed reconciliation") and, in the V0.1
  engine, `axiom/backtest/engine.py:125` and `:155`. Don't catch it; it signals a bug, not bad
  input. Message casing is inconsistent (see Known deviations): V0.2+ domain code uses sentence
  case (`"Invalid fill"`), the data layer and V0.1 engine mostly lowercase (`"invalid dataset ID"`);
  match the module you're in.
- **Logging**: no module-level `LOG = logging.getLogger(...)` pattern here (unlike a long-running
  service); `axiom/cli.py` uses `logging.basicConfig` for its own CLI output. Application code
  generally returns/raises rather than logs; keep new code consistent with whichever pattern its
  own module already uses.
- **Numeric/domain conventions**: `*_bps` for basis points; `*_pct`-style suffixes are not used
  here — follow the existing field names in `ExecutionConfig`/`RiskConfig`/`FeatureConfig` exactly
  rather than inventing new ones. Monetary/quantity fields are `float`. A `dataset_id`/experiment/
  paper-account `id` is always validated against its exact regex (`^[0-9a-f]{64}$` for a dataset
  hash, a UUID string elsewhere) at the pydantic/`Path` boundary, not re-parsed ad hoc downstream.
- **Polars idioms**: prefer expression chains (`pl.col(...).rolling_mean(...)`, `with_columns`,
  `partition_by`) over `.to_numpy()`/Python loops except where a genuinely sequential algorithm
  needs it. Wilder RSI (`wilder_rsi`, `axiom/features/pipeline.py:16-28`) is the one deliberate
  exception: its smoothing is inherently sequential, so it loops over a NumPy array.

## Tests (`tests/test_*.py`, pytest, `testpaths = ["tests"]`)

Flat files by subsystem (`test_analytics`, `test_backtest`, `test_execution`, `test_features`,
`test_integration`, `test_kernels`, `test_platform`, `test_validation`). Function names are
`test_<behaviour>` in snake_case stating the behavior under test
(`test_reversal_reconciles_fees_and_short_profit`,
`test_missing_session_does_not_publish_research_snapshot`,
`test_rolling_kernels_agree_on_warmup_and_values`), not `test_1`/`test_edge_case`.

- **Fixtures**: `tests/conftest.py` provides a small `bars` fixture built from `SyntheticProvider`
  + `validate`. PostgreSQL tests use the shared `pg` fixture (`tests/test_platform.py:116-133`):
  it skips with `pytest.skip(...)` if `AXIOM_TEST_DATABASE_URL` is unset, creates the schema,
  opens one outer transaction, hands out a `sessionmaker` with
  `join_transaction_mode="create_savepoint"` plus a `Settings` pointing `data_root` at
  `tmp_path`, and **rolls the whole transaction back** afterwards — so each test's commits are
  isolated without truncating tables. Tests unpack it as `sessions, settings = pg`. Request `pg`
  for any new database test rather than opening your own engine, and prefer extending shared
  fixtures over duplicating setup.
- **Database URL**: CI sets `AXIOM_TEST_DATABASE_URL` in the `python` job (and not in the
  `windows` job, where those tests skip); locally, `scripts/check_platform.py` sets it from
  `Settings().database_url` before invoking pytest for this checkout's isolated cluster. Don't
  hardcode a connection string in a test.
- **Parametrize** for boundary sweeps and rule tables (`tests/test_execution.py:43`,
  `test_sell_orders_and_gap_above_stop_limit`; `:66`; `:114`, `test_event_strategy_targets`).
- **Imports**: module level, like application code — `numpy`, `threading` and
  `random_walk_surrogate` were hoisted to the top of `tests/test_platform.py` in `4f4d702`. A
  handful of function-body imports of in-tree modules remain (see Known deviations); don't add
  more.
- A new failure mode or invariant needs a test in the matching file; don't report an empty or
  skipped suite as a pass.

## TypeScript / Next.js (`apps/dashboard/`, React 19, Next 16, `strict: true` in `tsconfig.json`)

`tsc --noEmit` is gated in CI; formatting is not (no ESLint/Prettier config) — match the observed
style by hand.

- `"use client"` at the top of client components that use hooks/state (`app/page.tsx:1`); plain
  server components (`app/layout.tsx`) omit it. Function components; hooks (`useState`, `useEffect`,
  `useRef`, `useMemo`) at the top of the component body, grouped by concern (the comma-chained
  `useState` declarations at `page.tsx:310-327` group related state, e.g.
  `const [tab, setTab] = useState("Research"), [busy, setBusy] = useState(""), ...`).
- Double quotes, semicolons, 2-space indent, trailing commas in multiline literals/call args — the
  observed style throughout `page.tsx`/`route.ts`/`next.config.ts`, not enforced by a formatter.
- Explicit `type` aliases for API response shapes (`Equity`, `Metrics`, `Result`, `Dataset`,
  `Experiment`, `Paper` at `page.tsx:10-57`, `Bar` at `page.tsx:167`) rather than `any`;
  `strict: true` means a new field consumed from an API response should be typed, not cast away.
- The one `api()` helper (`page.tsx:58-102`) is the only place that calls `fetch` in the client
  bundle; it also turns FastAPI error bodies (string or validation-array `detail`) into
  readable `Error` messages. Never `fetch` directly from a new component — extend or reuse `api()`.
- **Styling** is a single plain CSS file (`app/globals.css`), class names in kebab-case, no
  CSS-in-JS, no component library, no Tailwind. Static presentation goes in a class (the
  experiment error uses `className="run-error"`, `page.tsx:669`). An inline `style={{...}}` is
  acceptable only when the value is **data-driven** at render time — the monthly-returns heatmap
  cell background computed from the return (`page.tsx:844-849`) is the one current instance.
  CSS comments explain why, e.g. "Status colors reuse the chart palette's amber and red (page.tsx
  candles)." (`globals.css:319`).
- **Environment variables**: `process.env` is read only server-side. The proxy route
  (`app/api/[...path]/route.ts`) is the only file that reads `API_TOKEN`, `AXIOM_API_URL` and
  `AXIOM_ALLOWED_HOSTS` (the DNS-rebinding host allow-list, `route.ts:4-9`); `next.config.ts`
  reads `AXIOM_STANDALONE` to switch `output: "standalone"` for the Docker build. Never read
  environment variables in a client component. The proxy route also owns request validation
  (host allow-list, route allow-list regex, origin check on `POST`, `MAX_BODY_BYTES` body cap,
  fetch timeout via `AbortSignal.timeout`) — new proxied routes should extend its route regex
  rather than adding a second proxy file.

## Known deviations in the current tree

Ranked by importance; none are regressions in the enforced checkers (ruff/mypy/tsc all pass
clean), so these are style-consistency notes for the next diff that touches these files, not
blockers.

1. **Function-body imports that aren't optional/heavy.** `axiom/api.py:104-107` imports
   `polars`, `SnapshotStore` and `FeaturePipeline` inside the `/market` handler, but `api.py`
   already imports `axiom.paper` and `axiom.platform` at module level, which load all three at
   startup — the deferral buys nothing. Fix: move them to the module-level import block.
   `axiom/data/providers.py:46` imports stdlib `hashlib` inside `SyntheticProvider.fetch` — move
   to the top. (`axiom/research.py:71`'s `from datetime import timedelta` is in a V0.1 legacy
   module; leave it unless a diff touches it.)
2. **Function-body imports in tests.** `tests/test_execution.py:134,141` (`target`, already
   importable alongside the file's other `axiom.backtest.events` imports),
   `tests/test_platform.py:340-342` (`ValidationError`, `AdvanceRequest`), `:349` (`Account`),
   `:482` (`HeadRow`, next to the existing `from axiom.metadata import ...` line),
   `tests/test_validation.py:106-108` (`UNIVERSE`, `CSVProvider`, `parse_time`), and
   `tests/test_kernels.py:14-19` (`os`, `Path`, `pytest`, `native_mean` — `native_mean` lives in
   the same `axiom.features.kernels` module already imported at the top and only skips on a
   missing built library at call time, so nothing here is optional). Fix: hoist each into the
   module-level import block and let `ruff check --fix` sort them.
3. **Error-message casing.** V0.2+ domain code uses sentence case (`"Invalid fill"`,
   `"Portfolio requires aligned daily sessions"`); `axiom/data/storage.py`,
   `axiom/data/validation.py`, `axiom/data/providers.py`, `axiom/data/incremental.py:28` and the
   V0.1 engine use lowercase (`"invalid dataset ID"`, `"not a market session"`). These strings
   reach users as 422 `detail`s. Not worth churn; match the module being edited.
