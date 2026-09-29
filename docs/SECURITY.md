# Axiom Security

Owner: the `security` agent (`.claude/agents/security.md`). This document is the threat model,
the verified-controls register, the known-issues register, and the diff checklist. Re-run the
walkthrough below on every diff that touches `axiom/api.py`, the dashboard proxy route
(`apps/dashboard/app/api/[...path]/route.ts`), `axiom/data/storage.py`, `axiom/metadata.py`, or
`compose.yaml`.

Last full walkthrough: 2026-09-29, against `audit-fixes-2` at `0e88254` (includes `4f4d702`).
Every `path:line` below was re-read against that tree.

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
- A malicious web page in the user's browser talking to `127.0.0.1:8820` or `:8821`
  (including via DNS rebinding).
- A compromised or malicious npm/PyPI dependency, base image, or CI action.
- Path traversal via a stored snapshot path.
- A tampered Parquet file.
- SQL injection.
- Resource exhaustion from an unbounded research request.
- Accidental exposure of the API or the dashboard beyond localhost.
- A misconfigured Docker Compose deployment exposed to a real network.
- Misleading evidence — a synthetic-data result presented as if it demonstrated predictive skill,
  or a provenance record that overstates what is known about the code that produced it.

## Verified controls

Each item below was re-checked against the current tree; all 11 hold. No regressions found.

1. **Every FastAPI route requires a bearer token.** `auth()` (`axiom/api.py:62-65`) compares
   `authorization.encode()` with `("Bearer " + settings.api_token).encode()` via
   `secrets.compare_digest` and raises 401 otherwise. It is wired once, app-wide, as
   `dependencies=[Depends(auth)]` on the only `FastAPI(...)` instance (`axiom/api.py:67-69`).
   Grep of `axiom/` for `FastAPI(`, `APIRouter`, `include_router`, `.mount(` finds only
   `axiom/api.py:67` — every route defined inside `create_app` inherits auth. A route added via
   a second `FastAPI()` instance or a raw ASGI mount would bypass it and is Critical on sight.
2. **The API is bound to `127.0.0.1` in every non-container invocation.**
   `scripts/dev.py:27-28` passes `--host 127.0.0.1` to uvicorn (and `scripts/dev.py:36-37`
   passes `--hostname 127.0.0.1` to `next start`). In Docker, `Dockerfile:21` binds `0.0.0.0`
   inside the container, which is required for the dashboard container to reach
   `http://api:8820` over the Compose bridge; `compose.yaml:37` and `compose.yaml:52` publish
   only `127.0.0.1:8820:8820` and `127.0.0.1:8821:8821`. Loopback-only end to end.
3. **The API token never reaches the browser.** Only
   `apps/dashboard/app/api/[...path]/route.ts:43` reads `process.env.API_TOKEN`; it is attached
   server-side as `Authorization: Bearer ${token}` on the upstream fetch (`route.ts:60`). If it is
   unset the proxy returns 503 with a message naming the variable, never a value
   (`route.ts:44-48`). Grep of `apps/dashboard` (excluding `node_modules`/`.next`) for
   `"use client"` matches only `app/page.tsx:1`; for `API_TOKEN` only `route.ts:43,46`. The
   client-side `api()` helper (`app/page.tsx:58`) fetches same-origin `/api/${path}` with no
   credential. Holds.
4. **The proxy validates before forwarding**, in this order (`route.ts:18-53`):
   1. **Host allow-list (DNS-rebinding guard), 403 first.** `ALLOWED_HOSTS` defaults to
      `127.0.0.1,localhost,[::1]`, overridable with `AXIOM_ALLOWED_HOSTS` (`route.ts:5-9`); the
      `Host` header's hostname (port stripped via `new URL`, `route.ts:10-17`) must be in the set
      or the request gets 403 `Host rejected` (`route.ts:22-23`) before anything else is
      evaluated. This blocks a malicious page that rebinds its own name to 127.0.0.1 and would
      otherwise pass the Origin-equals-Host check. Setting `AXIOM_ALLOWED_HOSTS` to a
      non-loopback name widens this and needs review.
   2. **Path allow-list, 404.** `^(health|instruments|datasets|strategies|experiments|paper|market)(\/[a-zA-Z0-9-]+)?(\/advance)?$`
      (`route.ts:26-31`). Matches the current backend route set exactly; the backend then applies
      its own `DatasetId`/`RecordId` patterns (control 7).
   3. **Origin check on POST, 403.** A present `Origin` whose `host` differs from the `Host`
      header, or that fails to parse (e.g. `null`), is rejected (`route.ts:32-42`). An absent
      `Origin` is allowed (non-browser clients; browsers always send it on cross-origin POST).
   4. **Body cap, 413.** A declared `Content-Length` over 65,536 bytes is rejected before the body
      is read (`route.ts:49-50`); the body is then read and its UTF-8 byte length (not character
      count) is re-checked (`route.ts:51-53`). See known gap 8 for the chunked-body caveat.
   5. **Upstream call** uses `cache: "no-store"` and a 300 s `AbortSignal.timeout`
      (`route.ts:64-65`); the response carries `Cache-Control: no-store` (`route.ts:72`), and a
      timeout/connection failure returns a fixed 502 message with no upstream detail
      (`route.ts:75-82`).
   Loosening the regex, dropping the Host or Origin check, or removing either size check are each
   findings — check the regex against any new backend route before approving it.
5. **Snapshot reads are hash-verified and path-contained, on both the read and write sides.**
   `SnapshotStore.read` (`axiom/data/storage.py:91-106`) validates `identity` against
   `[0-9a-f]{64}` (line 92) before building a path, resolves every manifest part through the
   shared `_part_path` helper (`storage.py:109-113`, which raises if
   `root.resolve() not in path.parents`), re-hashes each part against its manifest sha256
   (line 99), and re-hashes the reconstructed canonical frame against `identity` (line 104). The
   write side's `_parts_intact` (`storage.py:116-125`), which decides whether an existing publish
   can be reused, now goes through the same `_part_path` containment check (line 120), so a
   manifest edited to point outside the snapshot directory cannot make `write()` hash a file
   elsewhere; any containment/parse failure counts as "not intact". The only callers of `read`
   are `axiom/api.py:114` (`/market`), `axiom/paper.py:71` (`advance`) and
   `axiom/platform.py:57` (`run_experiment`) — no code path reads a part without it. When a
   corrupt publish is found, `write()` renames it aside as `<id>.corrupt-<uuid>`, tolerating
   `OSError` from that rename (`storage.py:38-45`); see fresh finding L2 for what happens then.
6. **Bound parameters and an ORM everywhere for SQL.** The only `execute()` calls in `axiom/`,
   `scripts/` and `alembic/` are `text("SELECT 1")` (`axiom/api.py:74`),
   `text("SELECT pg_advisory_xact_lock(:key)")` with a bound `{"key": ...}`
   (`axiom/data/incremental.py:45`), and an ORM `insert(...).on_conflict_do_update(...)`
   (`axiom/data/incremental.py:76-83`); everything else is `db.get`/`db.scalar(s)(select(...))`/
   `db.add`. Migrations use `op.create_index`/`op.create_check_constraint` with literal
   constraint text only (`alembic/versions/0002_indexes_and_checks.py:15-27`). Grep for
   f-string/`.format`/`text(f` SQL across `axiom/ scripts/ alembic/` — no matches. Holds.
7. **Request bodies and path parameters are strictly validated.**
   - `PaperRequest` (`axiom/api.py:25-38`) is the base request model: `extra="forbid"`,
     `dataset_id` pattern `^[0-9a-f]{64}$`, `symbols` 1–342 entries, and a `field_validator` that
     rejects duplicate symbols (lines 33-38). `ResearchRequest(PaperRequest)` only adds
     `kind: Literal["backtest","ml"]` (lines 41-42), so `POST /paper` and `POST /experiments`
     share the same validation. `AdvanceRequest` (lines 45-49) is `extra="forbid"` with a `date`
     and an optional pattern-checked `dataset_id`.
   - Path parameters use `DatasetId = Path(pattern="^[0-9a-f]{64}$")` and
     `RecordId = Path(pattern="^[0-9a-f-]{36}$")` (`axiom/api.py:21-22`) on `/market/{identity}`
     (line 103), `/experiments/{identity}` (line 163) and `/paper/{identity}/advance` (line 221).
   - `FeatureConfig` (`axiom/common/models.py:40-49`), `ExecutionConfig`
     (`axiom/backtest/events.py:28-39`) and `RiskConfig` (`axiom/risk/engine.py:8-15`) all set
     `extra="forbid", allow_inf_nan=False` and bound every numeric tunable (`max_leverage le=3`,
     commission/slippage/spread `le=100` bps, `stop_loss gt=0, lt=1`, `risk_per_trade le=0.2`,
     `initial_capital le=1e10`, periods `le=1000`); `order_type` and `rolling_backend` are
     `Literal`s. `strategy` is checked against `STRATEGIES` (excluding `ml`) with 422 on both POST
     routes (`axiom/api.py:172-173`, `204-205`).
   - Individual `symbols` entries are plain `str` (no per-item pattern); they are only compared
     against the dataset's stored symbol list (`axiom/platform.py:46`, `axiom/paper.py:33`), never
     used in a path or query string, so this is not an injection vector. Holds.
8. **Admission is bounded.** `threading.BoundedSemaphore(settings.max_active_runs)`
   (`axiom/api.py:55`; default 2, `ge=1, le=8` at `axiom/settings.py:13`) gates
   `POST /experiments` (acquire `axiom/api.py:174`, release in `finally` line 190) and
   `POST /paper/{identity}/advance` (acquire line 222, release in `finally` line 233), returning
   429 when full. `symbols` is capped at 342 (`axiom/api.py:28`). `POST /paper`
   (`axiom/api.py:202-218`) is not gated but only does a DB lookup and insert
   (`axiom/paper.py:29-48`). `GET /market/{identity}` (`axiom/api.py:102-132`) is not gated —
   known gap 2. Holds.
9. **Docker runs as a non-root user on both images, with no secrets baked in.** API image:
   `useradd --uid 10001 ... axiom` then `USER axiom` (`Dockerfile:11-12`). Dashboard image:
   multi-stage, final stage copies `--chown=node:node` and runs `USER node`
   (`apps/dashboard/Dockerfile:11-13`). `compose.yaml:7` and `compose.yaml:22` require
   `POSTGRES_PASSWORD`/`API_TOKEN` via `${VAR:?Set VAR}`, so Compose refuses to interpolate the
   file without them (the dashboard's `API_TOKEN: ${API_TOKEN}` at `compose.yaml:51` is covered
   by the same file-wide check). Volumes are named (`pgdata`, `bars`, `reports`;
   `compose.yaml:9,38,56-59`), no host bind-mounts. Both build contexts exclude `.env*`
   (`.dockerignore:9`, `apps/dashboard/.dockerignore:3`) and the root one excludes `.git`
   (`.dockerignore:1`). Holds.
10. **No model-artifact deserialization trust boundary exists today.** Grep of `axiom/` and
    `scripts/` source for `pickle`, `joblib.load`, `eval(`, `exec(`, `os.system`, `shell=True`
    finds nothing. `axiom/ml/walkforward.py` fits estimators in-request (`.fit` at lines 81 and
    118) and returns only metrics; nothing is persisted or reloaded. Two adjacent, lower-risk
    load paths exist and share the source tree's trust level rather than a user's: numba's
    on-disk cache (`njit(cache=True)`, `axiom/features/kernels.py:25`, which numba stores and
    reloads from `__pycache__`), and `ctypes.CDLL` of the repo's own `native/` build
    (`axiom/features/kernels.py:39-50`), reachable from an API request via
    `FeatureConfig.rolling_backend="native"` but always from that fixed path. Anyone who can
    write those files can already edit `axiom/` itself. Re-flag the moment any feature persists
    and reloads a model, or lets a request influence either path.
11. **Dependencies, images and CI actions are pinned; updates arrive as reviewable PRs.**
    - Python: every `pyproject.toml` dependency has a `<major` upper bound (`fastapi>=0.121,<1`,
      `sqlalchemy>=2,<3`, `psycopg[binary]>=3.2,<4`, `pydantic>=2.10,<3`, `numba>=0.61,<1`,
      `yfinance>=0.2.65,<2`, …), locked in `uv.lock`; the image installs with `uv sync --frozen`
      (`Dockerfile:6,11`) and CI with `uv sync --frozen` (`.github/workflows/ci.yml:34,51`).
      Dashboard: `package-lock.json` with `npm ci` in the image (`apps/dashboard/Dockerfile:4`)
      and CI (`ci.yml:65`).
    - Images pinned by digest: `python:3.14-slim@sha256:51dafde8…` and
      `ghcr.io/astral-sh/uv:0.12.15@sha256:62f8c047…` (`Dockerfile:2-3`),
      `node:26-alpine@sha256:0b36e8c1…` (`apps/dashboard/Dockerfile:1,8`),
      `postgres:18-alpine@sha256:77f58511…` (`compose.yaml:3`, and the CI service container at
      `ci.yml:15`).
    - CI: workflow-wide `permissions: contents: read` (`ci.yml:3-4`); every action is pinned to a
      full commit SHA with a version comment (`actions/checkout`, `astral-sh/setup-uv`,
      `actions/setup-node`; `ci.yml:29-30,46-47,59-60,72`). Jobs: Linux Python on a
      3.12/3.14 matrix with PostgreSQL (`ci.yml:6-40`), Windows Python 3.12 without a DB
      (`ci.yml:41-52`), dashboard typecheck/build (`ci.yml:53-67`), and a Docker Compose smoke
      test with ephemeral random secrets from `openssl rand` (`ci.yml:68-105`). The CI DB
      password/token (`ci.yml:18,25-27`) are throwaway values for a job-local service.
    - `.github/dependabot.yml` opens weekly PRs for `docker` (`/` and `/apps/dashboard`),
      `docker-compose`, `uv`, `npm` (`/apps/dashboard`) and `github-actions`
      (`.github/dependabot.yml:4-28`).
    - Audit status: `npm audit --package-lock-only` re-run 2026-09-29 — 0 vulnerabilities.
      `pip-audit` is not installed in `.venv` and was not re-run this pass (last clean result
      2026-09-28, before the Python 3.14 base-image bump). Still a periodic manual task;
      Dependabot proposes version moves but is not a CVE audit of what is locked today.

## Known gaps (register)

Each re-verified against the current tree.

1. **No rate limiting beyond the admission semaphore.** A client with a valid token can call
   cheap routes (`GET /datasets`, `/experiments`, `/paper`, `/market/...`, and `POST /paper`) as
   fast as it wants; only `POST /experiments` and `POST /paper/{id}/advance` are gated
   (`axiom/api.py:174`, `axiom/api.py:222`). Low risk for a single-user local tool; call this out
   explicitly before pointing Docker Compose at anything but a fully trusted local user.
2. **`/market/{identity}` and the research paths re-run `FeaturePipeline` synchronously on every
   call with no caching** (`axiom/api.py:116`, `axiom/platform.py:60`, `axiom/paper.py:108`).
   `/market` is ungated and reads and hash-verifies the whole snapshot before filtering to one
   symbol (`axiom/api.py:113-115`), so a large snapshot makes each call expensive.
   `max_active_runs` bounds concurrency of the gated routes, not per-request cost.
   Capacity-planning item, not a vulnerability — `Depends(auth)` runs before any of this work.
3. **The Yahoo provider makes outbound network calls** (`YahooProvider.fetch`,
   `axiom/data/providers.py:78-92`, `yf.download`). No API route triggers it: the only callers
   are the CLI (`axiom/cli.py:67`), `scripts/ingest.py:28`, and `scripts/paper_tick.py:50` with
   an explicit `--live-data` flag. Intended, opt-in, documented. Flag any change that lets an API
   request (authenticated or not) trigger outbound fetches.
4. **`git rev-parse`/`git status --porcelain` run as subprocesses on every experiment**
   (`axiom/platform.py:89-99`, only when `shutil.which("git")` finds git; mirrored in the CLI
   report path at `axiom/research.py:119-127`) — fixed argv lists, no `shell=True`, `cwd` is the
   code root, no request data reaches either call. Not an injection vector; re-check if this is
   ever refactored to take a path/ref from a request.
5. **Compose's `migrate` service runs `alembic upgrade head` automatically on every
   `docker compose up`** (`compose.yaml:15-26`, command at line 23) before the API starts
   (`compose.yaml:39-41`). A compromised or malicious migration file would run automatically.
   Current migrations: `alembic/versions/0001_metadata.py` and
   `alembic/versions/0002_indexes_and_checks.py` (additive indexes plus CHECK constraints on
   `experiments.status`/`kind`; reviewed, no data access beyond DDL). Mitigation is source review
   of `alembic/versions/`, not a runtime control.
6. **`.gitignore` coverage confirmed**: `.env`, `.env.*` with `!.env.example`
   (`.gitignore:13-15`), `/data/`, `/reports/` (lines 11-12), `.venv/` (line 1), `/.runtime/`
   (line 23, which holds `dev.py`'s logs and PIDs), `/apps/dashboard/node_modules/`,
   `/apps/dashboard/.next/` (lines 24-25), native build artifacts (lines 26-30), and the ad-hoc
   root output files (lines 19-21). `git ls-files | grep -i env` returns only `.env.example`,
   `alembic/env.py` and `apps/dashboard/next-env.d.ts`; `.env.example` holds placeholders only.
7. **The API token has a minimum length (`Field(min_length=24)`, `axiom/settings.py:10`) but no
   rotation mechanism.** A leaked token is valid until `.env` is changed and every process
   restarted. Fine for a single local user; flag if the trust model ever expands.
8. **The proxy's byte cap is enforced after buffering when no `Content-Length` is sent.** The
   `Content-Length` pre-check (`route.ts:49-50`) stops honest oversized requests without reading
   them, but a chunked POST with no `Content-Length` is read fully into memory by `req.text()`
   (`route.ts:51`) before its byte length is checked (`route.ts:52-53`). Reaching that line
   already requires a loopback `Host`, an allow-listed path and a same-origin or absent `Origin`,
   so in practice only a local non-browser process can do it. Low; a streaming reader that stops
   at 64 KiB would close it.
9. **Provenance is only as strong as its inputs, and the container case is weaker.**
   `run_experiment` starts from `commit = os.environ.get("GIT_COMMIT", "unavailable")` and
   `dirty = None` (`axiom/platform.py:87-88`), and only overwrites them if a `git` binary is
   present (`axiom/platform.py:89-99`). The slim API image has no git, so in Docker
   `code_commit` is whatever was passed as the `GIT_COMMIT` build arg (`Dockerfile:13-15`,
   `compose.yaml:18-19,30-31`, default `unavailable`; CI passes `$GITHUB_SHA`, `ci.yml:77`) and
   `working_tree_dirty` is always `null`. That value is self-asserted at build time — nothing
   checks it against the copied source, and a build from a modified tree still records the clean
   commit it was given. Outside Docker, if `git rev-parse` fails, an inherited `GIT_COMMIT`
   environment variable is used the same way. The independent evidence is `code_tree_sha256`, a
   hash of every `axiom/**/*.py` actually loaded (`axiom/platform.py:100-104`). Anyone presenting
   a container-produced result should cite `code_tree_sha256`, and treat `code_commit` with
   `working_tree_dirty: null` as "claimed commit, cleanliness unknown", not as verified.

## Fresh findings from this pass (beyond the existing register)

No Critical, High or Medium findings.

- **L1 (Low, narrowed by `4f4d702`) — raw exception text still reaches some API responses.**
  Fixed part: `paper.record_tick_failure` (`axiom/paper.py:138-155`) now documents that callers
  pass a summary, and its only caller passes `f"{type(exc).__name__} (details in the tick log)"`
  (`scripts/paper_tick.py:77-79`), so `last_error` served by `GET /paper` no longer carries raw
  exception text (the full text goes only to the local tick log, `scripts/paper_tick.py:75`).
  Remaining:
  - `axiom/platform.py:129` stores `(str(exc) or type(exc).__name__)[:1000]` on
    `ExperimentRow.error` for any failure inside `run_experiment`, returned by
    `GET /experiments` (`axiom/api.py:152`) and `GET /experiments/{identity}`
    (`axiom/api.py:168`). Concrete case: a missing snapshot raises `FileNotFoundError` whose text
    includes the manifest's filesystem path under `data_root`; a DB failure mid-run could include
    driver detail.
  - `str(exc)` is returned as the HTTP `detail` for `ValueError` → 422
    (`axiom/api.py:188,218,231`), `UnknownPaperAccount` → 404 (line 227) and `PaperConflict` →
    409 (line 229). These are mostly Axiom's own fixed messages, but any library `ValueError`
    (including a pydantic `ValidationError` raised while rebuilding a stored config in
    `axiom/paper.py:108-110`) passes through verbatim.
  In today's single-user model the token holder is the `.env` holder, so this is informational;
  redact to the exception type (as the tick path now does) before the trust model expands.
- **L2 (Low, code) — a corrupt snapshot can survive a republish when the set-aside rename
  fails.** In `SnapshotStore.write` (`axiom/data/storage.py:35-55`), if `_parts_intact` is false
  and the `.corrupt-` rename raises `OSError` (e.g. a reader holding a part open on Windows),
  execution continues; staging succeeds but `stage.rename(target)` then fails because `target`
  still exists, and the `except OSError` branch returns `identity` because
  `target / "manifest.json"` exists (lines 50-54). The caller records the dataset as published
  while the bytes on disk are still the corrupt ones. Integrity is not lost — every later
  `read()` fails its hash check with a 422 — but the self-healing the comment promises only
  happens if another writer actually heals it. Fix: after the fallback, re-check
  `_parts_intact(target)` and raise if still false.
- **Info — `scripts/prune_snapshots.py` hardened.** It lists snapshot directories with no dataset
  row, dry-run by default; `--delete` is refused when the database has no dataset rows at all
  unless `--force` (`scripts/prune_snapshots.py:43-46`), and directories modified within
  `--min-age-minutes` (default 60) are skipped so an in-flight ingest's snapshot isn't removed
  before its row commits (lines 23, 34-42). It prints only the DB host/port/name, never the
  password (line 28). It is a manual, destructive maintenance script; review the dry-run listing
  before `--delete`.

Grep sweeps run and clean (no matches beyond what's cited above):
`pickle|joblib\.load|eval\(|exec\(|os\.system|shell=True` across `axiom/` and `scripts/`
source; `dangerouslySetInnerHTML|eval\(|new Function\(|child_process` across `apps/dashboard/`
(excluding `node_modules`/`.next`); f-string/`.format`/`text(f` SQL across `axiom/`, `scripts/`,
`alembic/`; `FastAPI(|APIRouter|include_router|.mount(` in `axiom/`; `"use client"` / `API_TOKEN`
in `apps/dashboard/`.

## Checklist for any diff

- [x] Auth still required on every route (including any new one)? — single app-level
      `Depends(auth)` (`axiom/api.py:67-69`), one `FastAPI()` instance, no `APIRouter`.
- [x] Proxy Host allow-list (403 first), path allow-list and Origin check unchanged or correctly
      widened? — `route.ts:22-42`; regex matches the backend route set.
- [x] Proxy body cap still enforced (Content-Length pre-check and UTF-8 byte count) and responses
      still `Cache-Control: no-store`? — `route.ts:49-53,72`; see gap 8.
- [x] Any new pydantic field or path parameter has explicit bounds/patterns and
      `allow_inf_nan=False` where numeric? — `PaperRequest`/`ResearchRequest`/`AdvanceRequest`,
      `DatasetId`/`RecordId`, and the three config models all verified.
- [x] Snapshot reads still hash-verified and path-contained, and the write-side intact check
      still uses `_part_path`? — `axiom/data/storage.py:91-125`.
- [x] SQL still parameterized? — ORM/`text()` with bound params only.
- [x] Admission gate still acquired (and released in `finally`) for any new slow/DB-heavy route?
      — both gated routes unchanged; `POST /paper` is cheap and ungated.
- [x] No secrets logged, printed, or returned in a response? — token never returned or logged;
      `last_error` now type-only; `ExperimentRow.error` and 404/409/422 details still carry
      `str(exc)` (L1).
- [x] `.gitignore`/`.dockerignore` coverage unchanged for `.env`/`data/`/`reports/`? — confirmed.
- [x] No new `pickle.load`/`joblib.load` on anything not produced and immediately consumed within
      the same trusted process? — none.
- [x] Images still digest-pinned, CI actions SHA-pinned, CI `permissions` still read-only? —
      confirmed (control 11).

**Result: 11/11 verified controls hold, 9 known gaps registered (8 and 9 new this pass),
0 Critical, 0 High, 0 Medium, 2 Low (L1 narrowed by `4f4d702`; L2 new, in code), 1 info.**
