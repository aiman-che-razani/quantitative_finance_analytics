# Axiom API

Two interfaces: the authenticated FastAPI research API (`axiom/api.py`) and the
Next.js server-side proxy that fronts it for the browser
(`apps/dashboard/app/api/[...path]/route.ts`). Verified against branch
`audit-fixes-2` at `0e88254` (2026-09-29). Every claim is cited `path:line` so
it can be re-checked quickly; re-verify line numbers after any edit to these
files:

- `axiom/api.py`
- `apps/dashboard/app/api/[...path]/route.ts`
- `apps/dashboard/app/page.tsx`
- `axiom/platform.py`, `axiom/paper.py`, `axiom/features/kernels.py`, `axiom/settings.py`

## Auth

Every route requires `Authorization: Bearer <API_TOKEN>`, enforced by a single
app-level dependency: `auth()` (`axiom/api.py:62-65`) is attached via
`FastAPI(..., dependencies=[Depends(auth)])` (`axiom/api.py:67-69`) and compares
bytes with `secrets.compare_digest` (`axiom/api.py:64`). No route is exempt —
`/health`, `/docs` and `/openapi.json` included. A missing, wrong or non-ASCII
header -> `401 "Authentication required"` (covered by
`tests/test_platform.py::test_api_requires_authentication`).

`API_TOKEN` is never sent to the browser: the proxy reads it server-side from
its own environment (`route.ts:43`), injected by `scripts/dev.py:17` or
`compose.yaml`'s `dashboard` service (`compose.yaml:51`). If it is unset the
proxy returns `503` (`route.ts:44-48`) instead of forwarding.

`Settings.api_token` must be at least 24 characters (`axiom/settings.py:10`).

## Admission gate

`threading.BoundedSemaphore(settings.max_active_runs)` (`axiom/api.py:55`),
default 2, configurable `1..8` (`axiom/settings.py:13`). It applies only to the
two routes that replay bars inside the request: `POST /experiments`
(`axiom/api.py:174-190`) and `POST /paper/{id}/advance`
(`axiom/api.py:222-233`). `POST /paper` does **not** take the gate — it only
writes a row (`axiom/paper.py:29-48`).

Both gated routes call `gate.acquire(blocking=False)` -> `429 "Research
capacity busy"` when full, and release in a `finally` (`axiom/api.py:189-190`,
`axiom/api.py:232-233`), so an exception can't leak a permit. The gate is
acquired *after* request-body validation and (for `/experiments`) the strategy
check, so a 422 never consumes a permit.

## FastAPI routes (`axiom/api.py`)

Bound to `127.0.0.1:8820` by `scripts/dev.py:19-31` (explicit
`--host 127.0.0.1`). The Dockerfile's `CMD` binds `--host 0.0.0.0`
(`Dockerfile:21`); that is required so the `dashboard` container can reach
`http://api:8820` over the Compose network (comment at `Dockerfile:17-20`). The
loopback-only boundary in Docker is `compose.yaml`'s host port mapping
`127.0.0.1:8820:8820` (`compose.yaml:37`). If that mapping is ever loosened,
the API is network-reachable (still behind the bearer token) — a `security`
concern.

Conventions: no trailing slash on any route. Errors are FastAPI/pydantic
defaults — `401`, `404`, `409`, `422`, `429`, `500` — with no custom envelope:
`HTTPException`s give `{"detail": "<string>"}`, request validation gives
`{"detail": [{loc, msg, type, ...}, ...]}`, and an unhandled exception gives
FastAPI's plain-text `Internal Server Error`. Stored timestamps (`created_at`,
equity-curve `timestamp`) are ISO strings, not epoch numbers.

Path parameters are pattern-validated (a mismatch is `422`, before the handler
runs): dataset ids `^[0-9a-f]{64}$` (`DatasetId`, `axiom/api.py:21`); experiment
and paper-account ids `^[0-9a-f-]{36}$` (`RecordId`, `axiom/api.py:22`) — a
36-character hex/dash shape, not a strict UUID check.

### `GET /health`
- Runs a live `SELECT 1` (`axiom/api.py:71-75`); `200 {"status":"ok","execution":"paper-only"}`.
- DB down -> unhandled `500`.

### `GET /instruments`
- `200 [Instrument, ...]` — each `InstrumentRow.definition` as stored, ordered by `symbol` (`axiom/api.py:77-83`).

### `GET /datasets`
- `200 [{id, parent_id, provider, symbols, rows, created_at}, ...]`, up to 100, newest first (`axiom/api.py:85-100`).
- `id` is the dataset's sha256 identity; `rows` comes from `quality["rows"]` (`axiom/api.py:94`) — a row without that key would 500.

### `GET /market/{identity}?symbol=SPY`
- `symbol` defaults to `SPY`. `404 "Unknown dataset or symbol"` if the dataset doesn't exist or `symbol` isn't in `dataset.symbols` (`axiom/api.py:109-112`).
- Otherwise reads the snapshot via `SnapshotStore(...).read`, runs `FeaturePipeline(FeatureConfig())` with hardcoded defaults (no custom feature params here), and returns the **tail 3000 rows** of `timestamp, open, high, low, close, volume, ema, rsi, bb_upper, bb_lower` (`axiom/api.py:113-132`).
- The snapshot read happens after the DB check and is not guarded: a missing snapshot (`FileNotFoundError`) or a hash mismatch (`ValueError` from `axiom/data/storage.py:99-105`) both surface as `500` here, not 404/422. No `ValueError` handler exists on this route.

### `GET /strategies`
- `200 {"strategies": [...STRATEGIES minus "ml"], "features": list(FeatureConfig.model_fields)}` (`axiom/api.py:134-139`).
- `STRATEGIES` (`axiom/backtest/events.py:16-25`): `buy_hold, ema_trend, ema_crossover, rsi_reversion, bollinger_reversion, momentum, combined, ml`. `"ml"` is hidden because ML is selected with `kind="ml"`, not `strategy="ml"`.

### `GET /experiments`
- `200 [{id, kind, status, dataset_id, config, created_at, error}, ...]`, up to 100, newest first (`axiom/api.py:141-160`).
- The query defers the `result` column (`defer(ExperimentRow.result)`, `axiom/api.py:156`), so listing never loads result JSON; `result` is not in the list shape (asserted in `tests/test_platform.py::test_api_list_and_market_endpoints_return_recorded_rows`).

### `GET /experiments/{identity}`
- `404 "Unknown experiment"` or `200 {id, status, result, error}` (`axiom/api.py:162-168`). This omits `kind`/`dataset_id`/`config`/`created_at`, which only the list route returns. `result` is `null` for a `RUNNING` or `FAILED` row.

### `POST /experiments` (`ResearchRequest`)
- Gate: **yes**.
- Body: see `ResearchRequest` below.
- `422` (pydantic) for any schema violation, including unknown fields, a non-hex-64 `dataset_id`, 0 or >342 `symbols`, or duplicate symbols.
- `422 "Unknown rule strategy"` if `strategy` isn't in `STRATEGIES` or is `"ml"` (`axiom/api.py:172-173`) — checked before the gate.
- `429 "Research capacity busy"` if the gate is full (`axiom/api.py:174-175`).
- Any `ValueError` from `run_experiment` -> `422` with its message (`axiom/api.py:187-188`). Sources include: unknown dataset/symbols (`axiom/platform.py:45-47`, raised *before* any row is written); `FeaturePipeline` "no bars"; `features.rolling_backend="native"` when the native library isn't built — `422 "native rolling kernel is not built on this machine"` (`axiom/features/kernels.py:18-20`; the Docker image never builds `native/`); walk-forward input errors (`axiom/ml/walkforward.py:34-134`, e.g. more than one symbol for `kind="ml"`); engine input errors (`axiom/backtest/events.py:76-120`); snapshot hash mismatches (`axiom/data/storage.py:99-105`); and NaN leaking into the result (`json.dumps(..., allow_nan=False)`, `axiom/platform.py:115`).
- Any exception after the `RUNNING` row is written — `ValueError` (422) or anything else (500, e.g. a missing snapshot file) — first marks the `ExperimentRow` `status="FAILED"`, `error=(str(exc) or type name)[:1000]` (`axiom/platform.py:122-133`) and re-raises. So a 422 raised after the row exists (native kernel, walk-forward input, NaN) and every 500 still leave a durable, inspectable record; only the unknown-dataset/symbols 422 leaves none.
- Success `200`: `{"id": <uuid>, **result}` (`axiom/platform.py:121`), where `result` always has `provenance` (`axiom/platform.py:105-113`) plus:
  - `kind="backtest"`: `simulation`, `benchmark {equity, metrics}`, `metrics`, `asset_correlations` (`axiom/platform.py:65-84`).
  - `kind="ml"`: `features`, `horizon`, `seed`, `folds`, `pooled_test_auc` (model -> AUC or `null`), `out_of_sample_trading`, `assumptions` (`axiom/ml/walkforward.py:164-172`).

### `GET /paper`
- `200 [{id, config, state}, ...]`, up to 100, ordered by `updated_at DESC` (`axiom/api.py:192-200`).
- `config` = `{dataset_id, symbols, strategy, execution, features}` (`axiom/paper.py:38-44`; accounts created before `features` was stored lack that key). `state` starts as `{last_session: null, alerts: [], fills: []}` (`axiom/paper.py:45`); after a successful advance it has `last_session, input_hash, provider, mode, alerts, fills, equity, account` (`axiom/paper.py:122-131`); after a failed scheduled tick it also carries `last_error` (see below).

### `POST /paper` (`PaperRequest`)
- Gate: no (only writes a row).
- Body: `PaperRequest` — `ResearchRequest` without `kind` (`axiom/api.py:25-38`). Sending `kind` is a `422` (`extra="forbid"`). `features` **is** stored on the account (`axiom/paper.py:43`) and used on every replay (`axiom/paper.py:108`); accounts created before features were stored replay with `FeatureConfig()` defaults.
- `422 "Unknown paper strategy"` if `strategy` isn't in `STRATEGIES` or is `"ml"` (`axiom/api.py:204-205`); `422 "Unknown dataset or symbols"` via `ValueError` from `paper.create_account` (`axiom/paper.py:33-34`, mapped at `axiom/api.py:217-218`).
- Not validated at creation: `rolling_backend="native"` is accepted even where the library is missing; every later advance of that account then fails with 422 (see below).
- Success: `200 {"id": <uuid>}`.

### `POST /paper/{identity}/advance` (`AdvanceRequest`)
- Gate: **yes** (`axiom/api.py:222-223`).
- Body: `AdvanceRequest` (`axiom/api.py:45-49`, `extra="forbid"`): `as_of: date` (required), `dataset_id: str | None` (hex-64). Unknown fields -> 422.
- Status mapping (`axiom/api.py:224-233`), in handler order:
  - `404 "Unknown paper account"` — only for `paper.UnknownPaperAccount` (`axiom/paper.py:21-22`, a `LookupError` subclass raised at `axiom/paper.py:56-57`). Other `KeyError`/`IndexError`/`LookupError`s from the replay are **not** caught and become `500`.
  - `409` — `paper.PaperConflict` (`axiom/paper.py:17-18`, a `ValueError` subclass caught first): `"Paper clock cannot move backwards"` (`axiom/paper.py:88-89`) or `"Previously processed bars changed"` (`axiom/paper.py:90-92`).
  - `422` — any other `ValueError`: `as_of` not before today UTC (`axiom/paper.py:52-53`, checked *before* the account lookup, so an unknown id with a future date is 422, not 404); `"Incompatible dataset"` (`axiom/paper.py:62-68`); `"No bars at requested date"` (`axiom/paper.py:83-85`); the native-kernel error (`axiom/features/kernels.py:18-20`); engine input errors; snapshot hash mismatches.
  - `500` — anything else (e.g. missing snapshot file). The whole advance runs in one transaction (`axiom/paper.py:54`), so a failed request rolls back and leaves no record on the account (unlike `/experiments`).
- Delegates to `axiom.paper.advance`, which locks the row (`with_for_update`, `axiom/paper.py:55`) and replays the account's full history deterministically — see the `database` agent for the locking/idempotency contract.
- Response shape — two success branches, same keys:
  - **New session** (`axiom/paper.py:107-135`): full replay; returns a fresh `{last_session, input_hash, provider, mode, alerts, fills, equity, account}` with alerts recomputed from scratch (`STALE_INPUT`, `RISK_REJECTION`), so no `TICK_FAILED` and no `last_error`. Also records the dataset used in `config.dataset_id` and bumps `updated_at`.
  - **Repeat tick, no new bar** (`axiom/paper.py:93-106`): no replay; returns the stored state with `alerts` refreshed — prior `STALE_INPUT` and `TICK_FAILED` removed, `STALE_INPUT` re-added if the latest bar is more than `STALE_AFTER_DAYS = 4` days before `as_of` (`axiom/paper.py:26`) — and `last_error` dropped; persists that and bumps `updated_at`. A successful repeat tick therefore clears a prior tick failure (`tests/test_platform.py::test_successful_repeat_tick_clears_tick_failure`).
  - Edge case: a repeat tick on an account that has never completed a fresh advance can't reach the repeat branch (`last_session` is null), so both branches always return the full key set.

### Tick failures (`paper.record_tick_failure`, not an HTTP route)
`scripts/paper_tick.py` catches any exception from a scheduled tick and calls
`record_tick_failure` (`scripts/paper_tick.py:74-80`) with a type summary,
`"<ExceptionType> (details in the tick log)"`, not the raw exception text.
`record_tick_failure` (`axiom/paper.py:138-155`) merges `TICK_FAILED` into the
existing alerts (sorted), stores `last_error` (truncated to 1000 chars), and
bumps `updated_at`, so the account moves to the top of `GET /paper`. A missing
account is ignored. The next successful advance clears both (above).

## Request models

**`PaperRequest`** (`axiom/api.py:25-38`, `extra="forbid"`):
`dataset_id: str` (`^[0-9a-f]{64}$`), `symbols: list[str]` (1–342, no
duplicates — `unique_symbols` validator, `axiom/api.py:33-38`),
`strategy: str = "ema_trend"`, `execution: ExecutionConfig`,
`features: FeatureConfig`.

**`ResearchRequest`** (`axiom/api.py:41-42`): `PaperRequest` plus
`kind: "backtest" | "ml" = "backtest"`.

**`AdvanceRequest`** (`axiom/api.py:45-49`, `extra="forbid"`): `as_of: date`,
`dataset_id: str | None = None` (hex-64).

**`ExecutionConfig`** (`axiom/backtest/events.py:28-39`, `extra="forbid"`, no inf/nan):
`initial_capital` (0, 1e10] = 100000, `commission_bps` [0,100] = 2.5,
`slippage_bps` [0,100] = 1, `spread_bps` [0,100] = 1, `participation` (0,1] = 0.01,
`stop_loss` (0,1) | null, `take_profit` (0,10] | null,
`order_type` in `market|limit|stop|stop_limit` = `market`,
`order_offset` [0,0.2] = 0.005, `risk: RiskConfig`.

**`RiskConfig`** (`axiom/risk/engine.py:8-16`, `extra="forbid"`, no inf/nan):
`max_leverage` (0,3] = 1, `max_concentration` (0,1] = 1, `max_drawdown` (0,1] = 0.3,
`daily_loss_limit` (0,1] = 0.1, `portfolio_loss_limit` (0,1] = 0.4,
`risk_per_trade` (0,0.2] = 0.02, `allow_short: bool = false`.

**`FeatureConfig`** (`axiom/common/models.py:40-49`, `extra="forbid"`, frozen, no inf/nan):
`rolling_backend` in `polars|numba|native` = `polars`, `rsi_period` [2,1000] = 26,
`ema_period` [2,1000] = 200, `bollinger_period` [2,1000] = 200,
`atr_period` [2,1000] = 14, `rolling_period` [2,1000] = 20,
`momentum_period` [1,1000] = 20, `bollinger_std` (0,10] = 1.19.
`native` loads `native/rolling.dll`/`rolling.so` at replay time and raises the
422 `ValueError` above if it's absent (`axiom/features/kernels.py:10-20`);
schema validation alone does not catch it.

Every model sets `extra="forbid"`, so an unknown field anywhere in a POST body
is a `422`, not silently ignored.

## `/docs` and `/openapi.json`

FastAPI's defaults, behind the same bearer auth (so a browser can't open
`/docs` without a header-injecting tool). The repo requires Python 3.12+
(`pyproject.toml:9`); no FastAPI/Pydantic version caveat applies.

## Next.js proxy (`apps/dashboard/app/api/[...path]/route.ts`)

One `proxy()` handler serves `GET` and `POST` (`route.ts:18-85`, exported at
`route.ts:85`; `dynamic = "force-dynamic"`, `route.ts:2`). Order of checks:

1. **Host allow-list** (`route.ts:5-9`, `route.ts:22-23`): the hostname of the
   `Host` header must be in `AXIOM_ALLOWED_HOSTS` (comma-separated, default
   `127.0.0.1,localhost,[::1]`), else `403 "Host rejected"`. This is a
   DNS-rebinding guard and applies to every method. A dashboard served under
   any other name (a LAN IP, a reverse-proxy hostname) must set
   `AXIOM_ALLOWED_HOSTS`; `compose.yaml` does not set it, which is fine for its
   `127.0.0.1:8821` mapping.
2. **Route allow-list** (`route.ts:24-31`): the joined path must match
   `^(health|instruments|datasets|strategies|experiments|paper|market)(\/[a-zA-Z0-9-]+)?(\/advance)?$`,
   else `404 "Unknown route"`. The regex is looser than the real surface and
   verb-agnostic (e.g. `health/x`, `instruments/x/advance`, `POST health` pass
   and get FastAPI's own 404/405), so don't read it as documentation of the API.
3. **Origin check**, POST only (`route.ts:32-42`): if an `Origin` header is
   present and its `host` (including port) differs from the `Host` header ->
   `403 "Origin rejected"`. An unparseable `Origin` is also rejected; a POST
   with no `Origin` skips the check.
4. **Token presence** (`route.ts:43-48`): `503 "API_TOKEN is not configured on
   the dashboard server"`.
5. **Body size, two stages** (`route.ts:49-53`): first a declared
   `Content-Length` over 65536 bytes -> `413 "Request too large"` without
   reading the body (checked for every method); then, for POST, the body is
   read as text and its UTF-8 byte length is checked against the same limit
   (catches chunked/undeclared bodies).
6. **Forward** (`route.ts:54-67`):
   `${AXIOM_API_URL || "http://127.0.0.1:8820"}/${route}${search}`, same
   method, the POST body text passed through unchanged, headers
   `Authorization: Bearer <token>` and `Content-Type: application/json` (the
   browser's own headers are not forwarded), `cache: "no-store"`, 300s timeout
   (`AbortSignal.timeout(300000)`).
7. **Response** (`route.ts:68-74`): upstream status and body text passed
   through, but response headers are replaced — `Content-Type` is always
   `application/json` (even for FastAPI's plain-text 500) and
   `Cache-Control: no-store` is added.
8. **Fetch failure/timeout** (`route.ts:75-83`) -> `502` with `"Research API
   unavailable or request timed out. Check experiment history before
   retrying."` Keep this wording if you touch the handler: per `README.md`,
   research POSTs have durable status records and a lost connection does not
   imply the run failed.

## Frontend sync (`apps/dashboard/app/page.tsx`)

- `api<T>(path, body?)` helper (`page.tsx:58-102`): `fetch(\`/api/${path}\`)`,
  as a JSON `POST` when `body` is given.
  - Network failure reaching the dashboard server -> throws `"Dashboard server
    unreachable. Check experiment history before retrying."` (`page.tsx:71-75`).
  - Reads the body as text and parses JSON defensively (`page.tsx:76-81`).
  - `!r.ok`: throws `detail` if it is a string; if it is an array (pydantic
    422), joins each entry as `<loc minus the first element>: <msg>` with
    ` · `; otherwise (no/unparseable JSON, e.g. a plain-text 500)
    `"Research API error <status>. Check experiment history before
    retrying."` (`page.tsx:82-96`).
  - OK but unparseable body -> `"Research API returned an unreadable response.
    Check experiment history before retrying."` (`page.tsx:97-100`).
- Tabs (ARIA `role="tablist"`/`"tab"`): `Research | Market data | Experiments |
  ML research | Paper accounts` (`page.tsx:428-446`). `Research` and
  `ML research` share one controls panel and differ only in the `kind` sent
  (`page.tsx:543-546`).
- `refresh()` (`page.tsx:328-340`) loads `datasets`, `strategies`,
  `experiments`, `paper` in parallel on mount and after every action;
  `action()` (`page.tsx:344-358`) refreshes even after a failure and surfaces
  refresh errors.
- Paper accounts: `POST paper` with the shared Research `request`
  (`page.tsx:712`, no `kind`), `POST paper/{id}/advance` with only `as_of`
  (`page.tsx:757-759`); `TICK_FAILED` renders as a danger alert and
  `state.last_error` as "Last tick error" (`page.tsx:733-751`).
- ML results: `pooled_test_auc` is typed (`page.tsx:27`) and shown as a
  "Pooled test AUC" table with a caveat that it must be compared with a
  random-walk null, not 0.5 (`page.tsx:893-908`).
- Any FastAPI route rename, a new required field on `PaperRequest` /
  `ResearchRequest` / `AdvanceRequest`, or a new strategy must be reflected in
  **both** `route.ts`'s allow-list regex and `page.tsx`'s calls/types, and
  checked with `npm run build` / `npm run typecheck` in `apps/dashboard`.
- HTTP-level tests live in `tests/test_platform.py` (`TestClient`):
  `test_api_requires_authentication`,
  `test_api_rejects_duplicate_symbols_and_unknown_accounts`,
  `test_advance_request_rejects_unknown_fields`,
  `test_api_experiment_and_paper_round_trip` (200/404/409/422/429, stored
  `features`, `kind` rejected on `/paper`),
  `test_api_list_and_market_endpoints_return_recorded_rows`.
  `tests/test_integration.py` exercises `axiom.research`/ingest directly, not
  the HTTP surface. The proxy (`route.ts`) has no automated tests.

## Reviewing an endpoint — checklist

When adding or changing a route, confirm: path/verb; auth (everything needs
the bearer token — flag any proposed unauthenticated route); request/response
shape including nullable fields; status codes (and which exception types map
to them — catch narrow types, as `advance` now does); whether the admission
gate applies (any route calling `run_experiment` or `paper.advance` should);
the matching `route.ts` allow-list entry; the `page.tsx` change; and a
`TestClient` test in `tests/test_platform.py`.

## Open findings (2026-09-29)

1. **Low — `/market/{identity}` snapshot errors are 500s.** The DB check
   (`axiom/api.py:109-112`) and the snapshot read (`axiom/api.py:113-115`) are
   separate and the route has no `ValueError` handler, so a missing snapshot
   or a hash mismatch returns 500 rather than 404/422. Possibly a `database`
   concern (how rows and snapshots drift apart).
2. **Low — `rolling_backend="native"` isn't rejected at `POST /paper`.** An
   account can be created with it on a machine (e.g. Docker) without the
   library; every advance then returns 422. `POST /experiments` also only
   fails after writing a `FAILED` row. Validating at request time would be
   clearer.
3. **Low — proxy allow-list is looser than the real routes** (see step 2
   above). Not exploitable today; FastAPI 404/405s the extras.
4. **Info — Docker host binding.** `0.0.0.0` in the Dockerfile is required;
   the boundary is `compose.yaml:37`. Flag to `security` only if that mapping
   changes.

Resolved since the 2026-09-28 audit: `GET /paper` orders by `updated_at DESC`;
duplicate symbols are 422; `AdvanceRequest` forbids unknown fields; path ids
are pattern-validated; `advance` maps only `UnknownPaperAccount` to 404; a
successful repeat tick clears `TICK_FAILED`/`last_error`; the native-kernel
failure is a 422 instead of a 500.

## Test status

With `AXIOM_TEST_DATABASE_URL` pointing at a disposable PostgreSQL database,
`pytest -q -rs` (e.g. `.venv\Scripts\python.exe -m pytest -q -rs` on Windows,
or `uv run pytest -q -rs`) runs the whole suite including the API tests above.
Without it, PostgreSQL-backed tests skip. See `docs/TESTING.md`.
