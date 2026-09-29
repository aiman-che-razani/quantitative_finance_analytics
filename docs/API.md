# Axiom API

Two interfaces: the authenticated FastAPI research API (`axiom/api.py`) and the
Next.js server-side proxy that fronts it for the browser
(`apps/dashboard/app/api/[...path]/route.ts`). This doc is verified against the
code as of the commits below; every claim is cited `path:line` so it can be
re-checked quickly.

- `axiom/api.py`
- `apps/dashboard/app/api/[...path]/route.ts`
- `apps/dashboard/app/page.tsx`
- `axiom/platform.py`, `axiom/paper.py`, `axiom/metadata.py`, `axiom/settings.py`

## Auth

Every route requires `Authorization: Bearer <API_TOKEN>`, enforced by a single
`Depends(auth)` at the app level (`axiom/api.py:46-52`), compared with
`secrets.compare_digest` (`axiom/api.py:47`). No route is exempt — `/health`
included. Missing/incorrect header -> `401 Authentication required`.

`API_TOKEN` is never sent to the browser: it's read server-side only, inside
the Next.js route handler (`route.ts:20`), from the dashboard's own process
environment (injected by `scripts/dev.py:15` or `compose.yaml`'s `dashboard`
service). If it's unset, the proxy returns `503` (`route.ts:21-25`) rather than
forwarding an unauthenticated request.

`Settings.api_token` itself is validated to be at least 24 characters
(`axiom/settings.py:10`).

## Admission gate

`threading.BoundedSemaphore(settings.max_active_runs)` (`axiom/api.py:39`),
default 2, configurable `1..8` (`axiom/settings.py:13`). Applies only to the
two routes that run a backtest/ML replay end-to-end in the request:
`POST /experiments` and `POST /paper/{id}/advance`. `POST /paper` (account
creation) does **not** acquire the gate — it only writes a row
(`axiom/paper.py:17-35`), it doesn't replay bars.

Both gated routes: `gate.acquire(blocking=False)` -> `429 Research capacity
busy` if full; the permit is always released in a `finally` block
(`axiom/api.py:154-170`, `axiom/api.py:199-206`), so a mid-run exception can't
leak a permit.

## FastAPI routes (`axiom/api.py`)

Bound to `127.0.0.1:8820` when run via `scripts/dev.py:24-31` (explicit
`--host 127.0.0.1`). **Note:** the Dockerfile's own `CMD` binds uvicorn to
`--host 0.0.0.0` inside the container (`Dockerfile:13`) — the loopback-only
restriction in the Docker path comes entirely from `compose.yaml`'s port
mapping `127.0.0.1:8820:8820` (`compose.yaml:26`), not from the uvicorn host
flag. If that port mapping is ever loosened (e.g. to `8820:8820`), the API
would be reachable from the network despite still requiring the bearer token.
Worth a security-agent look if the compose file changes.

No trailing slash on any route. Errors are FastAPI/pydantic defaults (`422`
validation, `404`, `429`, `401`) — no custom error envelope. Stored timestamps
(`created_at`, equity-curve `timestamp`) are ISO strings, not epoch numbers.

### `GET /health`
- Auth: required. Gate: no.
- Runs a live `SELECT 1` (`axiom/api.py:56-57`); `200 {"status":"ok","execution":"paper-only"}`.
- No failure path documented beyond FastAPI's default 500 if the DB is down.

### `GET /instruments`
- Auth: required. Gate: no.
- `200 [Instrument, ...]` — each `InstrumentRow.definition` dumped as-is, ordered by `symbol` (`axiom/api.py:60-66`).

### `GET /datasets`
- Auth: required. Gate: no.
- `200 [{id, parent_id, provider, symbols, rows, created_at}, ...]`, up to 100, newest first (`ORDER BY created_at DESC LIMIT 100`, `axiom/api.py:68-83`).
- `id` is the dataset's sha256 identity; `rows` is read from `quality["rows"]` — a `KeyError` here (a `DatasetRow` written by a future ingest path without that key) would surface as a 500, not a documented error.

### `GET /market/{identity}?symbol=SPY`
- Auth: required. Gate: no.
- `symbol` defaults to `SPY`. `404 "Unknown dataset or symbol"` if the dataset id doesn't exist or `symbol` isn't in `dataset.symbols` (`axiom/api.py:92-95`).
- Otherwise reads the Parquet snapshot via `SnapshotStore`, runs `FeaturePipeline(FeatureConfig())` (hardcoded defaults — no way to pass custom feature params here), returns the **tail 3000 rows** of `timestamp, open, high, low, close, volume, ema, rsi, bb_upper, bb_lower` as a list of dicts (`axiom/api.py:96-115`).
- Edge case not covered by the 404 check: the DB row is validated inside the `with sessions()` block, but `SnapshotStore(...).read(identity)` runs *after* that block, against the filesystem. A `DatasetRow` whose Parquet file is missing (orphaned row) would raise an unhandled exception (500), not the documented 404. Cross-check with `database` agent if this matters.

### `GET /strategies`
- Auth: required. Gate: no.
- `200 {"strategies": [...STRATEGIES minus "ml"], "features": list(FeatureConfig.model_fields)}` (`axiom/api.py:117-122`).
- Full `STRATEGIES` list (`axiom/backtest/events.py:14-23`): `buy_hold, ema_trend, ema_crossover, rsi_reversion, bollinger_reversion, momentum, combined, ml`. `"ml"` is excluded from this list because it's selected via `kind="ml"`, not `strategy="ml"`.

### `GET /experiments`
- Auth: required. Gate: no.
- `200 [{id, kind, status, dataset_id, config, created_at, error}, ...]`, up to 100, newest first (`axiom/api.py:124-140`).

### `GET /experiments/{identity}`
- Auth: required. Gate: no.
- `404 "Unknown experiment"` or `200 {id, status, result, error}` (`axiom/api.py:142-148`). Note this shape omits `config`/`created_at`/`kind`/`dataset_id`, which the list route includes — a client that only calls the detail route won't get those fields.

### `POST /experiments` (`ResearchRequest`, `extra="forbid"`)
- Auth: required. Gate: **yes**.
- Body: `dataset_id` (`^[0-9a-f]{64}$`, `axiom/api.py:23`), `symbols` (1–342 items, `axiom/api.py:24`), `strategy` (default `"ema_trend"`), `execution` (`ExecutionConfig`, defaults below), `features` (`FeatureConfig`, defaults below), `kind` (`"backtest" | "ml"`, default `"backtest"`).
- `422 "Unknown rule strategy"` if `strategy` isn't in `STRATEGIES`, or if `strategy == "ml"` (that value is rejected explicitly since ML is selected via `kind`, `axiom/api.py:152-153`).
- `429 "Research capacity busy"` if the gate is full.
- A `ValueError` from `run_experiment` (unknown dataset/symbols, bad research input — `axiom/platform.py:46-47`) -> `422`. Any other exception propagates as an unhandled 500 **and** is recorded on the `ExperimentRow` first (`status="FAILED"`, `error=str(exc)[:1000]`, `axiom/platform.py:123-129`) before re-raising — so a 500 still leaves a durable, inspectable record.
- Gate permit always released in `finally` (`axiom/api.py:169-170`).
- Success: `200 {id, simulation?, benchmark?, metrics?, asset_correlations?, folds?, out_of_sample_trading?, provenance}` — exact shape depends on `kind` (backtest vs ml walk-forward); see `axiom/platform.py:60-84`.

### `GET /paper`
- Auth: required. Gate: no.
- `200 [{id, config, state}, ...]`, up to 100, ordered by `updated_at DESC` (`axiom/api.py`).

### `POST /paper` (`PaperRequest`: `ResearchRequest` without `kind`)
- `features` is stored on the account and used on every replay (accounts created before 2026-09-29 replay with default features). Sending `kind` is a 422.
- Auth: required. Gate: no (only writes a row — `axiom/paper.py:17-35` does no bar replay).
- `422 "Unknown paper strategy"` if `strategy` isn't in `STRATEGIES` or is `"ml"` (`axiom/api.py:182-183`); `422` also on unknown dataset/symbols via `ValueError` from `paper.create_account` (`axiom/paper.py:21-22`).
- Success: `200 {"id": <uuid>}`.

### `POST /paper/{identity}/advance` (`AdvanceRequest`)
- Auth: required. Gate: **yes**, same pattern as `/experiments` (`axiom/api.py:199-206`).
- Body: `as_of: date` (required), `dataset_id: str | None` (same hex-64 pattern, `axiom/api.py:33`).
- `404 "Unknown paper account"` when the id is unknown (`LookupError` in `axiom/paper.py`); `422` when the id is not a UUID-shaped string.
- `422` on `ValueError` — including: `as_of` not before today (`axiom/paper.py:39-40`), incompatible dataset/provider/symbols (`axiom/paper.py:49-54`), no bars at the requested date (`axiom/paper.py:71`), or no bars at the requested date.
- `409` (`paper.PaperConflict`) when the request conflicts with recorded state: the clock moving backwards, or previously processed bars having changed under a fixed `last_session`.
- Delegates to `axiom.paper.advance`, which takes a Postgres row lock (`with_for_update`, `axiom/paper.py:42`) and replays the account's full history deterministically — see the `database` agent for the locking/idempotency contract.
- Same response shape on both branches: `{last_session, input_hash, provider, mode, alerts, fills, equity, account}`. The idempotent-repeat branch returns the stored `row.state` (only ever written by the fresh-session branch) with `alerts` refreshed.

## Shared request models

**`ResearchRequest`** (`axiom/api.py:21-28`, `extra="forbid"`):
`dataset_id: str` (hex-64), `symbols: list[str]` (1–342), `strategy: str = "ema_trend"`,
`execution: ExecutionConfig`, `features: FeatureConfig`, `kind: "backtest" | "ml" = "backtest"`.

**`AdvanceRequest`** (`axiom/api.py:31-33`): `as_of: date`, `dataset_id: str | None` (hex-64).

**`ExecutionConfig`** (`axiom/backtest/events.py:26-37`, `extra="forbid"`, no inf/nan):
`initial_capital` (0, 1e10], `commission_bps` [0,100], `slippage_bps` [0,100],
`spread_bps` [0,100], `participation` (0,1], `stop_loss` (0,1) | null,
`take_profit` (0,10] | null, `order_type` in `market|limit|stop|stop_limit`,
`order_offset` [0,0.2], `risk: RiskConfig`.

**`RiskConfig`** (`axiom/risk/engine.py:8-16`, `extra="forbid"`, no inf/nan):
`max_leverage` (0,3], `max_concentration` (0,1], `max_drawdown` (0,1],
`daily_loss_limit` (0,1], `portfolio_loss_limit` (0,1], `risk_per_trade` (0,0.2],
`allow_short: bool`.

**`FeatureConfig`** (`axiom/common/models.py:40-49`, `extra="forbid"`, frozen, no inf/nan):
`rolling_backend` in `polars|numba|native`, `rsi_period` [2,1000],
`ema_period` [2,1000], `bollinger_period` [2,1000], `atr_period` [2,1000],
`rolling_period` [2,1000], `momentum_period` [1,1000], `bollinger_std` (0,10].

Every one of these models sets `extra="forbid"`, so an unknown field in a POST
body is a `422`, not silently ignored.

## `/docs` and `/openapi.json`

FastAPI's defaults work normally — same auth applies, no custom OpenAPI
generation. This repo requires Python 3.12+ (`pyproject.toml:9`), so there's
no 3.9-pinned FastAPI/Pydantic version issue here.

## Next.js proxy (`apps/dashboard/app/api/[...path]/route.ts`)

One `proxy()` handler serves both `GET` and `POST` (`route.ts:60`). Order of
checks:

1. **Allow-list** (`route.ts:9-14`): joined path must match
   `^(health|instruments|datasets|strategies|experiments|paper|market)(\/[a-zA-Z0-9-]+)?(\/advance)?$`,
   else `404 "Unknown route"`. This regex is looser than the actual FastAPI
   surface — e.g. `health/x`, `strategies/x`, `instruments/x/advance` all pass
   the proxy's check even though no such FastAPI route exists. That's not a
   security hole (FastAPI still requires auth and 404s the unmatched path
   itself) but it means the proxy isn't a precise mirror of the API surface;
   don't rely on the regex alone to reason about what's reachable. The regex
   also doesn't vary by HTTP verb, so e.g. a `POST /health` passes the
   allow-list and is forwarded, then gets FastAPI's default `405`.
2. **Origin check**, POST only (`route.ts:15-19`): `403 "Origin rejected"` if
   an `Origin` header is present and its host doesn't match the request's
   `Host` header. A request with no `Origin` header at all skips this check.
3. **Token presence** (`route.ts:20-25`): `503` if `API_TOKEN` isn't set in
   the dashboard's own environment.
4. **Body size**, POST only (`route.ts:26-28`): `413 "Request too large"` if
   the body exceeds 65536 bytes (64 KB).
5. **Forward** (`route.ts:29-42`): `${AXIOM_API_URL || "http://127.0.0.1:8820"}/${route}${search}`,
   bearer token attached, `Content-Type: application/json`, 300s timeout
   (`AbortSignal.timeout(300000)`), `cache: "no-store"`. Response status and
   body are passed through verbatim (`route.ts:43-49`).
6. **Fetch failure/timeout** -> `502` with
   `"Research API unavailable or request timed out. Check experiment history
   before retrying."` (`route.ts:50-58`). Keep this wording if you touch this
   handler — per `README.md`, "Research POSTs are synchronous with durable
   status records... A lost browser connection does not imply the run
   failed," and this message is what tells the user that.

## Frontend sync (`apps/dashboard/app/page.tsx`)

- `api()` helper (`page.tsx:54-73`): calls `fetch(\`/api/${path}\`, ...)`,
  throws `Error(data.detail)` (stringifying non-string `detail`) when
  `!r.ok`.
- Tabs: `Research | Market data | Experiments | ML research | Paper accounts`
  (`page.tsx:338-352`); `Research` and `ML research` share one controls panel
  and only differ in the `kind` sent on submit (`page.tsx:455`).
- `refresh()` (`page.tsx:256-268`) fetches `datasets`, `strategies`,
  `experiments`, `paper` in parallel on mount and after every mutating
  action (`action()`, `page.tsx:272-283`).
- Any FastAPI route rename, a new required field on `ResearchRequest` /
  `AdvanceRequest`, or a new strategy name must be reflected in **both**
  `route.ts`'s allow-list regex and `page.tsx`'s calls/types, and checked
  against `npm run build` / `npm run typecheck` in `apps/dashboard`.
- **Note:** `tests/test_integration.py` (despite its name) exercises
  `axiom.research`/`ingest` directly, not the FastAPI app — it does not cover
  the HTTP surface. The route-level coverage that exists lives in
  `tests/test_platform.py` (`test_api_requires_authentication`, using
  `fastapi.testclient.TestClient`); that's the file to extend when adding a
  route-level test, not `test_integration.py`.

## Reviewing an endpoint — checklist

When adding or changing a route, confirm: path/verb; auth (everything needs
the bearer token — flag any proposed unauthenticated route as rare/unusual);
request/response shape including nullable fields; status codes; whether the
admission gate applies (any route calling `run_experiment` or `paper.advance`
should); the matching `route.ts` allow-list entry; the `page.tsx` change; and
add/extend a `TestClient`-based test in `tests/test_platform.py`.

## Audit findings (2026-09-28), ranked by severity

1. **Addressed 2026-09-28 (documented, not rebound) — Docker host binding.**
   `Dockerfile`'s `uvicorn` `CMD` binds `--host 0.0.0.0`, not `127.0.0.1`.
   This is **required, not a bug**: `apps/dashboard`'s proxy reaches this
   service at `http://api:8820` over the Compose bridge network (not
   loopback), so binding `127.0.0.1` inside the container would make the
   `api` service unreachable from `dashboard` and break `docker compose up`
   entirely. The real isolation boundary is `compose.yaml`'s
   `ports: ["127.0.0.1:8820:8820"]` host mapping, which was already
   correct. Both files now carry an explicit comment saying so, so a future
   reader doesn't "fix" this into a regression. Flag to `security` only if
   the host port mapping itself is ever loosened.
2. **Fixed 2026-09-28 — `GET /paper` now orders by `updated_at DESC`**
   before `LIMIT 100` (`axiom/api.py`), matching `/datasets` and
   `/experiments`. (Was previously the only list endpoint with no explicit
   ordering, risking a newly created/updated account dropping out of the
   dashboard's Paper accounts tab once there are more than 100 rows.)
3. **Withdrawn 2026-09-28 — `/paper/{id}/advance` response shape.** Re-checked: both branches return
   the same keys (see the route above).
4. **Low — proxy allow-list is looser than the real route set.**
   `route.ts:10`'s regex accepts path shapes (e.g. `health/x`, verb-agnostic
   matching) that don't correspond to any real FastAPI route; FastAPI's own
   404/405 catches these today, so this is not currently exploitable, but the
   regex shouldn't be read as documentation of the actual API surface.
5. **Info — orphaned-dataset edge case on `/market/{identity}`.** The DB
   existence check (`axiom/api.py:92-95`) and the filesystem read
   (`axiom/api.py:96-98`) aren't in the same guarded block; a `DatasetRow`
   whose Parquet snapshot is missing would 500 instead of the documented 404.
   Likely a `database`-agent concern (how datasets/snapshots can go out of
   sync) more than an `api` one — noted here for visibility.

No auth gaps found: every route sits behind the single app-level
`Depends(auth)`; no route bypasses it. No missing gate on either
state-mutating slow route. Fixed 2026-09-28: duplicate `symbols` were accepted and
crashed `POST /experiments` with a plain-text 500; `ResearchRequest` now rejects
them with 422. `AdvanceRequest` now forbids unknown fields, and path ids are
pattern-validated (hex-64 datasets, UUID experiments/paper accounts).

## Drift from the source `.claude/agents/api.md` brief

Checked every specific claim in the brief against the code above; found one
factual gap (item 1 above — the brief states the API is "bound to
`127.0.0.1:8820` by `scripts/dev.py` / the Dockerfile's uvicorn command,"
which is true for `scripts/dev.py` but not for the Dockerfile's own `CMD`).
Everything else in the brief — route list, status codes, validation bounds,
gate behavior, proxy allow-list/origin/size/timeout/error wording, and the
`page.tsx` `api()`/tabs citations — matches the current code with the specific
line numbers cited throughout this document.

## Test status

With `AXIOM_TEST_DATABASE_URL` pointing at a PostgreSQL database, `uv run pytest -q`
runs the whole suite including the API tests in `tests/test_platform.py`
(auth, duplicate symbols, unknown account 404, malformed ids). See `docs/TESTING.md`
for setup.
