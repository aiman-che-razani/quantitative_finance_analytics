# Code style

Conventions observed in the current Axiom tree, for keeping new code consistent with what's
already here. This is a description of practice, not a wishlist — where the codebase is
inconsistent, that's called out explicitly rather than papered over.

## Verification

Axiom's Python is enforced by CI (`.github/workflows/ci.yml`): `ruff check`, `ruff format --check`
and `mypy` all run on every push/PR and must pass. As of 2026-09-28, on this tree:

```
$ uv run ruff check axiom tests scripts alembic
All checks passed!

$ uv run ruff format --check axiom tests scripts alembic
61 files already formatted

$ uv run mypy axiom
Success: no issues found in 36 source files
```

All three pass clean. A regression here is a finding, full stop, not a style opinion.

The dashboard has a `typecheck` script (`tsc --noEmit`) that is **not** wired into CI — the
`dashboard` job in `.github/workflows/ci.yml` only runs `npm ci` and `npm run build`. Running it
directly (`npm run typecheck` inside `apps/dashboard/`) currently passes with no errors. There is
no `lint`/`format` script and no ESLint/Prettier config; TypeScript/Next.js style below is
observed-and-matched-by-hand, not enforced.

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
  constants (`UNIVERSE`, `STRATEGIES`, `FEATURES`, `SCHEMA`, `SCHEMA_TYPES`), lowercase module
  names.
- **Formatting**: double quotes, 4-space indent, line-length 100 via `ruff format` — run the
  formatter rather than hand-matching it; it's the standard, not a majority style among several.
- **Import order**: enforced by ruff's `I` (isort) rule — standard library, then third-party, then
  `axiom...`, alphabetized within each group. Local/lazy imports inside a function body are an
  established pattern **for optional or heavy dependencies**: `axiom/api.py:87-90` imports
  `polars`/`SnapshotStore`/`FeaturePipeline` inside the `/market` handler; `axiom/ml/walkforward.py`
  is imported lazily from `platform.py`. Keep that pattern for anything that shouldn't load at
  CLI/API-startup time — it is not a general license to move any import into a function body (see
  Deviations below for a counter-example).
- **Type hints**: the norm for the request/response and domain-model boundary — `mypy` runs with
  `check_untyped_defs = True` and the `pydantic.mypy` plugin, and passes clean. New functions in
  that layer should be typed like the surrounding code (`def target(row: dict, strategy: str,
  current: int = 0, allow_short: bool = False) -> int:`, `axiom/backtest/events.py:40`); pydantic
  models (`ConfigDict(extra="forbid")`, often `allow_inf_nan=False`) are the standard way to
  validate external input (`ResearchRequest`, `FeatureConfig`, `ExecutionConfig`, `RiskConfig`) —
  don't accept a raw untyped `dict` where a pydantic model already exists for the shape.
  **Caveat** (observed, not in the original brief): this is not applied uniformly. The
  orchestration layer that threads a SQLAlchemy `sessions`/`settings` object through — e.g.
  `axiom/paper.py:17` (`create_account`) and `axiom/paper.py:38` (`advance`), `axiom/platform.py:23`
  (`run_experiment`), `axiom/metadata.py:58` (`database`) — is routinely untyped or only
  partially typed (parameters and/or return type omitted). `mypy` still passes because
  `disallow_untyped_defs` is not set. Match whichever pattern the function's own layer already
  uses: fully typed for domain/business logic (`backtest/`, `features/`, `portfolio/`,
  `common/models.py`), pragmatic/untyped for DB-session plumbing and orchestration.
- **Dataclasses**: for internal, non-validated state that pydantic's validation overhead doesn't
  buy anything for (`Order`, `Position`/`Account`, `Decision`, `QualityReport`) — `@dataclass` with
  `field(default_factory=...)`/`field(init=False)` as needed. `Order.__post_init__`
  (`axiom/backtest/orders.py:15`) and `Account.fill`/`mark` (`axiom/portfolio/account.py`) show the
  pattern of validating inputs and raising `ValueError`/`ArithmeticError` inline rather than
  deferring to a separate validator. `__post_init__` methods consistently omit `-> None`
  throughout the codebase — that's the established local convention, not an omission to flag.
- **Module docstrings**: a one-line design statement, not a summary (`"""Idempotent paper replay;
  never sends orders to a broker."""`, `"""Immutable single-writer Parquet snapshots with
  completion manifests."""`) — most modules have one; a few small/obvious ones don't
  (`risk/engine.py`, `settings.py` — `backtest/orders.py` was in this list too until it was
  given one on 2026-09-28, see "Known deviations" below,
  `data/incremental.py`, `__main__.py`, the package `__init__.py` files use a generic `"""Axiom
  <subsystem>."""` line). Match the file: add a one-liner explaining the non-obvious design
  choice, not a restatement of the filename.
- **Comments**: explain **why**, especially where the math or the ordering is load-bearing: "Close
  before reversing; opposite entry can occur after the next signal." (`events.py:151`), "Cash
  cannot finance new longs; covering shorts is handled above." (`account.py:64` via
  `risk/engine.py:64`), "Strict JSON also catches NaN leaking from analytics before persistence."
  (`platform.py:115`). A one-line inline comment marking a genuinely non-obvious ordering
  constraint, e.g. `# Unknown intrabar sequence: defer limit eligibility.`
  (`axiom/backtest/orders.py:47`), fits this pattern. Flag comments that narrate the code instead.
- **Errors**: `raise ValueError(...)` with a specific human-readable message for bad input/state
  (`"Conflicting overlap: publish an explicitly corrected dataset instead"`, `"Portfolio requires
  aligned daily sessions"`, `"Invalid order"`, `"Invalid fill"`) — these are caught at the API
  boundary and turned into 422s (`api.py:167-168`, `203-204`). Don't raise a bare `Exception` or a
  generic message where the existing pattern names the specific problem. `ArithmeticError` is used
  once, deliberately, for the ledger reconciliation invariant
  (`axiom/portfolio/account.py:103`) — don't catch it.
- **Logging**: no module-level `LOG = logging.getLogger(...)` pattern here (unlike a long-running
  service); `axiom/cli.py` uses `logging.basicConfig` for its own CLI output. Application code
  generally returns/raises rather than logs; keep new code consistent with whichever pattern its
  own module already uses.
- **Numeric/domain conventions**: `*_bps` for basis points; `*_pct`-style suffixes are not used
  here — follow the existing field names in `ExecutionConfig`/`RiskConfig`/`FeatureConfig` exactly
  rather than inventing new ones. Monetary/quantity fields are `float`. A `dataset_id`/experiment/
  paper-account `id` is always validated against its exact regex (`^[0-9a-f]{64}$` for a dataset
  hash, a UUID string elsewhere) at the pydantic boundary, not re-parsed ad hoc downstream.
- **Polars idioms**: prefer expression chains (`pl.col(...).rolling_mean(...)`, `with_columns`,
  `partition_by`) over `.to_numpy()`/Python loops except where a genuinely sequential algorithm
  needs it. Wilder RSI in `axiom/features/pipeline.py:16-28` is the one deliberate exception, with
  a comment-free but self-explanatory loop because RSI's smoothing is inherently sequential.

## Tests (`tests/test_*.py`, pytest, `testpaths = ["tests"]`)

Flat files by subsystem (`test_analytics`, `test_backtest`, `test_execution`, `test_features`,
`test_integration`, `test_kernels`, `test_platform`, `test_validation`). Function names are
`test_<behaviour>` in snake_case stating the behavior under test
(`test_reversal_reconciles_fees_and_short_profit`,
`test_missing_session_does_not_publish_research_snapshot`,
`test_rolling_kernels_agree_on_warmup_and_values`), not `test_1`/`test_edge_case`.
`tests/conftest.py` provides a small `bars` fixture built from `SyntheticProvider` + `validate`;
prefer extending shared fixtures over duplicating setup. `pytest.mark.parametrize` is used for
boundary sweeps (`test_execution.py::test_sell_orders_and_gap_above_stop_limit`). Tests needing
PostgreSQL read `AXIOM_TEST_DATABASE_URL` and `pytest.skip(...)` if it isn't set
(`tests/test_platform.py:69-71`) — `scripts/check_platform.py` sets it from `Settings().database_url`
before invoking pytest for this checkout's isolated cluster; don't hardcode a connection string in
a test. A conditional/heavy import inside a test function (e.g. `os`, `pathlib.Path`, `pytest` and
the module under test all imported inside `test_native_matches_reference_when_built`,
`tests/test_kernels.py:14-19`, guarding a `pytest.skip` for an optional native build) mirrors the
same "optional dependency" rationale as the lazy imports in application code. A new failure mode
or invariant needs a test in the matching file; don't report an empty or skipped suite as a pass.

## TypeScript / Next.js (`apps/dashboard/`, React 19, Next 16, `strict: true` in `tsconfig.json`)

No ESLint/Prettier config present, and no `lint`/`format`/`typecheck` step in CI — match the
observed style by hand.

- `"use client"` at the top of client components that use hooks/state (`app/page.tsx:1`); plain
  server components (`app/layout.tsx`) omit it. Function components; hooks (`useState`, `useEffect`,
  `useRef`) at the top of the component body, grouped by concern (the comma-chained `useState`
  calls at `page.tsx:239-255` group related state, e.g. `const [tab, setTab] = useState("Research"),
  [busy, ...] = ...`).
- Double quotes, semicolons, 2-space indent, trailing commas in multiline literals/call args — this
  is the observed style throughout `page.tsx`/`route.ts`, not enforced by a configured linter or
  formatter (`package.json` has no `lint`/`format` script, and `.github/workflows/ci.yml`'s
  `dashboard` job only runs `npm ci` and `npm run build`, not `npm run typecheck`). Match it by
  hand. **Recommendation**: add `npm run typecheck` to the `dashboard` CI job — it currently passes
  clean and costs nothing to gate on; there's no ESLint/Prettier config to add a lint/format gate
  for without first choosing and committing one, which is a bigger call than this doc should make
  unasked.
- Explicit `type` aliases for API response shapes (`Equity`, `Metrics`, `Result`, `Dataset`,
  `Experiment`, `Paper` in `page.tsx:10-53`) rather than `any`; `strict: true` means a new field
  consumed from an API response should be typed, not cast away.
- The one `api()` helper (`page.tsx:54-73`) is the only place that calls `fetch` in the client
  bundle; never `fetch` directly from a new component — extend or reuse `api()`.
- Styling is a single plain CSS file (`app/globals.css`), class names in kebab-case, no CSS-in-JS,
  no component library, no Tailwind.
- The proxy route (`app/api/[...path]/route.ts`) is the only file allowed to reference
  `process.env.API_TOKEN`/`process.env.AXIOM_API_URL`; never read those in a client component. It
  also owns request validation (route allow-list regex, origin check on `POST`, body-size cap,
  fetch timeout via `AbortSignal.timeout`) — new proxied routes should extend its allow-list regex
  rather than adding a second proxy file.

## Known deviations in the current tree

Ranked by importance; none are regressions in the enforced checkers (ruff/mypy all pass clean),
so these are style-consistency notes for the next diff that touches these files, not blockers.

1. **Fixed 2026-09-28** — `import math` in `axiom/backtest/orders.py` has been moved to the
   top of the file, alongside `from dataclasses import dataclass` / `from typing import Literal`,
   and the local import inside `Order.__post_init__` removed. `ruff`/`mypy` still pass clean.
2. **Fixed 2026-09-28** — `axiom/backtest/orders.py` now has a one-line module docstring
   (`"""Order objects and conservative daily-bar execution-price rules."""`), matching the
   convention used by its sibling small modules.
