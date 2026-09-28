# Axiom Security

Owner: the `security` agent (`.claude/agents/security.md`). This document is the threat model,
the verified-controls register, the known-issues register, and the diff checklist. Re-run the
walkthrough below on every diff that touches `axiom/api.py`, the dashboard proxy route
(`apps/dashboard/app/api/[...path]/route.ts`), `axiom/data/storage.py`, `axiom/metadata.py`, or
`compose.yaml`.

Last full walkthrough: 2026-09-28.

## Threat model

Axiom is a **local-first tool for a single trusted user**, with an optional Docker Compose
deployment still intended for that one trusted local user (not a multi-tenant or
internet-facing deployment).

**Assets**
- The user's machine — code execution via a dependency or a deserialization path.
- The PostgreSQL database — instrument/dataset/experiment/paper-account state.
- The Parquet snapshot directory (`data_root`) and the integrity of the research evidence it
  holds (synthetic vs. provider-sourced labeling, the provenance record).
- `API_TOKEN` and database credentials in `.env`.

**Threats**
- A malicious web page in the user's browser talking to `127.0.0.1:8820` or `:8821`.
- A compromised or malicious npm/PyPI dependency.
- Path traversal via a stored snapshot path.
- A tampered Parquet file.
- SQL injection.
- Resource exhaustion from an unbounded research request.
- Accidental exposure of the API or the dashboard beyond localhost.
- A misconfigured Docker Compose deployment exposed to a real network.
- Misleading evidence — a synthetic-data result presented as if it demonstrated predictive skill.

## Verified controls

Each item below was re-checked against the current tree; all 11 still hold. No regressions found.

1. **Every FastAPI route requires a bearer token.** `axiom/api.py:46-52` defines
   `auth()` and wires it as a single app-level `dependencies=[Depends(auth)]` on the one and
   only `FastAPI(...)` instance (`axiom/api.py:50-52`). Confirmed there is exactly one
   `FastAPI(` construction in `axiom/` (`axiom/api.py:50`) and no `APIRouter`/`include_router`
   anywhere — every route defined inside `create_app` inherits auth automatically. A route added
   via a second `FastAPI()` instance or a raw ASGI mount would bypass it and is a Critical finding
   on sight.
2. **The API is bound to `127.0.0.1` in every non-container invocation.**
   `scripts/dev.py:25-27` passes `--host 127.0.0.1 --port 8820` to uvicorn (line numbers shifted
   by one from the agent brief's `26-28` due to unrelated edits; value unchanged). In Docker,
   `Dockerfile:14` binds `0.0.0.0` inside the container, which is correct for Docker's network
   namespace; `compose.yaml:27` and `compose.yaml:42` publish only `127.0.0.1:8820:8820` and
   `127.0.0.1:8821:8821`. Still loopback-only end to end.
3. **The API token never reaches the browser.** Only
   `apps/dashboard/app/api/[...path]/route.ts:20` reads `process.env.API_TOKEN` and attaches it
   server-side (`route.ts:35`, `Authorization: Bearer ${token}`) to the upstream fetch. Grepped
   the whole `apps/dashboard` tree for `"use client"` — the only match is `app/page.tsx:1` — and
   for `API_TOKEN`/`process.env.API_TOKEN` — the only matches are in `route.ts:20,23`. The
   client-side `api()` helper (`app/page.tsx:54-60`) calls same-origin `/api/...` with no
   credential attached. Holds.
4. **The proxy validates before forwarding.** First, it answers only requests whose `Host`
   hostname is loopback (`127.0.0.1`, `localhost`, `[::1]`; override with `AXIOM_ALLOWED_HOSTS`)
   and otherwise returns 403 — this blocks DNS rebinding, where a malicious page resolves its own
   name to 127.0.0.1 and would otherwise pass the Origin-equals-Host check (added 2026-09-28).
   It then rejects any path outside
   `health|instruments|datasets|strategies|experiments|paper|market` (plus the narrow
   `/[a-zA-Z0-9-]+` segment and `/advance`) with 404; it rejects a POST with a
   cross-origin or malformed (e.g. `null`) `Origin` header with 403; it rejects a body over
   64 KiB (declared `Content-Length`, then UTF-8 bytes) with 413;
   `route.ts:40` sets a 300s `AbortSignal.timeout`. All four still present and unchanged from the
   brief's description; the regex has not been loosened and matches the current route set exactly
   (`health, instruments, datasets, strategies, experiments, paper, market`).
5. **Snapshot reads are hash-verified, not just path-checked.** `SnapshotStore.read`
   (`axiom/data/storage.py:54-73`) validates `identity` against `^[0-9a-f]{64}$` (line 57) before
   using it in a path, resolves each part's path and rejects an escape via
   `root.resolve() not in path.parents` (line 64), re-hashes every part against its
   manifest-recorded sha256 (line 66), and re-hashes the reconstructed whole frame against
   `identity` itself (line 71). `axiom/api.py:97` and `axiom/paper.py:57` and
   `axiom/platform.py:57` all call this same `SnapshotStore.read` — no code path reads a part
   without going through it.
6. **Bound parameters and an ORM everywhere for SQL.** Reviewed every DB-touching module
   (`axiom/metadata.py`, `axiom/api.py`, `axiom/paper.py`, `axiom/data/incremental.py`): all
   access is SQLAlchemy ORM (`db.get`, `db.scalars(select(...))`, `db.add`) or parameterized
   `text()` (`axiom/api.py:57` `text("SELECT 1")`,
   `axiom/data/incremental.py:45` `text("SELECT pg_advisory_xact_lock(:key)")` with a bound
   `{"key": ...}` dict). Grepped the whole `axiom/` tree for f-string/`%`-formatted SQL
   (`f"SELECT`, `text(f"`, `.format(...SELECT`, etc.) — no matches. Holds.
7. **Request bodies are strictly validated pydantic models.** `ResearchRequest`/`AdvanceRequest`
   (`axiom/api.py:21-33`) use `ConfigDict(extra="forbid")`. `FeatureConfig`
   (`axiom/common/models.py:40-49`), `ExecutionConfig` (`axiom/backtest/events.py:26-37`), and
   `RiskConfig` (`axiom/risk/engine.py:8-16`) all set `allow_inf_nan=False` and give every
   tunable an explicit `Field(..., ge=/le=/gt=/lt=)` bound (leverage `max_leverage: le=3`,
   commission/slippage `le=100` bps, `stop_loss: gt=0, lt=1`, `risk_per_trade: le=0.2`, etc.).
   `Instrument.symbol` is itself pattern-constrained (`^[A-Z][A-Z0-9.]{0,9}$`,
   `axiom/common/models.py:11`). Holds.
8. **Admission is bounded.** `threading.BoundedSemaphore(settings.max_active_runs)`
   (`axiom/api.py:39`, default 2, capped `1..8` by `Settings.max_active_runs`,
   `axiom/settings.py:13`) gates `POST /experiments` (`axiom/api.py:154,170`) and
   `POST /paper/{id}/advance` (`axiom/api.py:199,206`), releasing in a `finally` in both cases.
   `ResearchRequest.symbols` is capped `max_length=342` (`axiom/api.py:24`). The only other
   compute-heavy route, `GET /market/{identity}` (`axiom/api.py:85-115`), is a `GET`, takes a
   single `symbol` (not a list), and is not gated — this is unchanged from the documented "known
   gap" #2, not a new finding. Holds.
9. **Docker runs as a non-root user on both images.** API image:
   `useradd --uid 10001 --create-home axiom ... USER axiom` (`Dockerfile:10-11,15`). Dashboard
   image: multi-stage build, final stage runs `USER node` (`apps/dashboard/Dockerfile:11-13`, the
   `COPY --chown=node:node` lines plus `USER node`). `compose.yaml:7,19` require
   `POSTGRES_PASSWORD`/`API_TOKEN` via `${VAR:?Set VAR}` — Compose refuses to start without them.
   Volumes are named (`pgdata`, `bars`, `reports`; `compose.yaml:8,28,46-49`), no host bind-mounts.
   Holds.
10. **No model-artifact deserialization trust boundary exists today.** Grepped all of `axiom/`
    for `pickle`, `joblib.load`, `eval(`, `exec(`. No matches anywhere. `axiom/ml/walkforward.py`
    fits and discards every scikit-learn/XGBoost estimator in-request (lines 66-119); nothing is
    persisted or reloaded. Holds — re-flag this the moment any feature persists and reloads a
    model.
11. **Dependency versions are pinned with explicit upper bounds.** `pyproject.toml` — every
    dependency has a `<major` upper bound (`fastapi>=0.121,<1`, `sqlalchemy>=2,<3`,
    `psycopg[binary]>=3.2,<4`, `pydantic>=2.10,<3`, `alembic>=1.14,<2`, `uvicorn>=0.34,<1`,
    `xgboost>=3,<4`, etc.). Both Dockerfiles install with `--frozen`
    (`Dockerfile:6`, `apps/dashboard/Dockerfile:4` `npm ci`). Lock files (`uv.lock`,
    `apps/dashboard/package-lock.json`) present. On 2026-09-28 `npm audit --package-lock-only`
    reported 0 vulnerabilities and `pip-audit` over the exported `uv.lock` (all extras) reported
    none. This remains a periodic manual task. Docker base images (`python:3.12-slim`,
    `node:22-alpine`, `postgres:18-alpine`) are pinned by tag, not digest — an open decision.

## Known gaps (register)

Each re-verified against the current tree; no changes since the last documented state.

1. **No rate limiting beyond the admission semaphore.** A client with a valid token can call
   cheap `GET` routes (`/datasets`, `/experiments`, `/market/...`) as fast as it wants; only the
   two POST research routes are gated (`axiom/api.py:154`, `axiom/api.py:199`). Low risk for a
   single-user local tool; call this out explicitly before pointing Docker Compose at anything but
   a fully trusted local user.
2. **`/market/{identity}` and the walk-forward ML path both re-run `FeaturePipeline`
   synchronously on every call with no caching** (`axiom/api.py:85-115`,
   `axiom/platform.py:60`). A very large snapshot makes a single request expensive.
   `max_active_runs` bounds concurrency, not per-request cost. Capacity-planning item, not a
   vulnerability — auth (`Depends(auth)`) is checked before any of this work runs, so it is not
   reachable pre-auth.
3. **The Yahoo provider makes outbound network calls** (`axiom/data/providers.py:78-92`,
   `yfinance`) triggered by an authenticated ingest/paper-tick request. Intended, opt-in,
   documented. Flag any change that lets an unauthenticated path or a lower-privilege token
   trigger this.
4. **`git rev-parse`/`git status --porcelain` run as subprocesses on every experiment**
   (`axiom/platform.py:91-99`, mirrored in `axiom/research.py:120-125`) to stamp provenance —
   fixed argv list, `shell=False` (implicit default), no user input reaches either call. Not an
   injection vector today; re-check if this is ever refactored to take a path/ref from a request.
5. **Compose's `migrate` service runs `alembic upgrade head` automatically on every
   `docker compose up`** (`compose.yaml:15-23`) before the API starts. Intended behavior; a
   compromised or malicious migration file (currently only `alembic/versions/0001_metadata.py`)
   would run automatically. Mitigation is source review of `alembic/versions/`, not a runtime
   control.
6. **`.gitignore` coverage confirmed unchanged**: `.env`, `.env.*` (with `!.env.example`),
   `/data/`, `/reports/`, `.venv/`, `/apps/dashboard/node_modules/`, `/apps/dashboard/.next/`,
   native build artifacts, and the ad-hoc root output files (`/demo-output.json`,
   `/yahoo-ingestion.json`, `/historical-output.json`) are all still listed
   (`.gitignore:1-32`). `git ls-files | grep -i env` returns only `.env.example`, which contains
   placeholder values only (`replace-password`, `replace-with-a-random-token-...`), never a real
   secret. `git status` is clean of any `.env`/data/report artifact.
7. **The API token has a minimum length (`Field(min_length=24)`, `axiom/settings.py:10`) but no
   rotation mechanism.** A leaked token is valid until `.env` is changed and every process
   restarted. Fine for a single local user; flag if the trust model ever expands.

## Fresh findings from this pass (beyond the existing register)

No Critical or High findings. Two Low/informational items worth tracking:

- **Low — internal exception text is persisted and returned via the API with no redaction.**
  `axiom/platform.py:127`: `row.error = str(exc)[:1000]` stores the raw exception message from
  any failure inside `run_experiment` (feature computation, ML fit, JSON serialization, the git
  subprocess calls, or a mid-run DB write) onto `ExperimentRow.error`, which is then returned
  verbatim by the authenticated `GET /experiments/{identity}` route (`axiom/api.py:142-148`).
  Concrete scenario: if the second `sessions.begin()` write (marking the row `SUCCEEDED`,
  `axiom/platform.py:117-121`) fails because of a transient DB error, the resulting exception text
  — which could in principle include driver-level connection detail — gets stored and handed back
  to any caller holding the (single, shared) API token. In today's single-user threat model this
  is low risk (the only holder of the token is the same user who holds `.env`), but it is the one
  place an unbounded, unredacted internal error string reaches an API response. No fix required
  now; note it if the trust model ever expands beyond one user, or truncate/redact before that
  point.
- **Fixed 2026-09-28 — vestigial, unused secret-shaped keys in generated `.env`.**
  `scripts/local_db.py` used to write `WORKER_TOKEN` and `COORDINATOR_URL` into the generated
  `.env` alongside `DATABASE_URL`/`POSTGRES_PASSWORD`/`API_TOKEN`, even though neither key is
  read anywhere in `axiom/` (`Settings` uses `extra="ignore"`). It now only writes the three keys
  that are actually consumed. Note this only affects newly generated `.env` files; an existing
  one from before this fix still has the two stray keys, harmlessly ignored.

Grep sweeps run and clean (no matches beyond what's already cited above):
`pickle|joblib\.load|eval\(|exec\(|os\.system|shell=True` across all of `axiom/`;
`dangerouslySetInnerHTML|eval\(|new Function\(|child_process` across `apps/dashboard/`;
f-string/`%`-formatted SQL patterns across `axiom/`; a second `FastAPI(`/`APIRouter` construction
anywhere in `axiom/`; `"use client"` / `API_TOKEN` usage outside the one expected file each in
`apps/dashboard/`.

## Checklist for any diff

- [x] Auth still required on every route (including any new one)? — single `Depends(auth)` at
      app level, one `FastAPI()` instance, no `APIRouter`.
- [x] Proxy Host allow-list, path allow-list and Origin check unchanged or correctly widened? —
      loopback Host allow-list added 2026-09-28; path regex unchanged.
- [x] Any new pydantic field has explicit bounds (`ge`/`le`) and `allow_inf_nan=False` where
      numeric? — no new fields introduced this pass; existing fields all bounded.
- [x] Snapshot reads still hash-verified and path-contained? — `SnapshotStore.read`
      (`axiom/data/storage.py:54-73`) unchanged, sole read path.
- [x] SQL still parameterized? — ORM/`text()` everywhere, no raw string-built SQL found.
- [x] Admission gate still acquired (and released in `finally`) for any new slow/DB-heavy route?
      — both existing gated routes unchanged; no new slow route added.
- [x] No secrets logged, printed, or returned in a response? — token itself never logged/returned;
      see the Low finding above on unredacted exception text (not a secret, but flagged for
      awareness).
- [x] `.gitignore` coverage unchanged for `.env`/`data/`/`reports/`? — confirmed unchanged and
      effective (`git ls-files` shows only `.env.example`).
- [x] No new `pickle.load`/`joblib.load` on anything not produced and immediately consumed within
      the same trusted process? — none found anywhere in `axiom/`.

**Result: 11/11 verified controls hold, 7/7 known gaps unchanged, 0 Critical, 0 High, 0 Medium,
2 Low (informational, no action required).**
