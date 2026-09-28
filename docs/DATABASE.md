# Axiom data layer

Axiom's durable state is split across two systems that must be reasoned about
together: **PostgreSQL** holds small, queryable operational metadata; the
**Parquet snapshot store** holds the actual (large) market-data bars as
immutable, content-addressed files on disk. A row in `experiments` or
`paper_accounts` is meaningless without the snapshot it references, and a
snapshot without the row that references it is an orphan. Back them up and
restore them together (see "Backup/restore" below).

Schema is owned by `axiom/metadata.py` (SQLAlchemy 2.x declarative models)
and applied via Alembic (`alembic/versions/`). Snapshot layout is owned by
`axiom/data/storage.py`.

## PostgreSQL schema

Source of truth: `axiom/metadata.py`. Migrated by `alembic/versions/0001_metadata.py`
— **this is still the only migration** (`alembic/versions/*.py` glob returns
exactly one file), and CI applies it with `alembic upgrade head` against a
fresh PostgreSQL 18 service container on every push
(`.github/workflows/ci.yml:28`).

### `instruments`
`axiom/metadata.py:15-18`; migration `alembic/versions/0001_metadata.py:16-19`.

| column | type | notes |
|---|---|---|
| `symbol` | `varchar(16)`, PK | |
| `definition` | `JSONB` | full `Instrument` model dump |

One row per known instrument. Upserted (`INSERT ... ON CONFLICT DO UPDATE`)
on every ingest, never inserted any other way
(`axiom/data/incremental.py:74-82`).

### `datasets`
`axiom/metadata.py:21-28`; migration `alembic/versions/0001_metadata.py:20-30`.

| column | type | notes |
|---|---|---|
| `id` | `varchar(64)`, PK | sha256 hex digest — see Invariant 1 |
| `parent_id` | `varchar(64)`, FK → `datasets.id`, nullable | chains an incremental merge to the snapshot it extended |
| `provider` | `varchar(64)` | |
| `symbols` | `JSONB` | sorted list of symbol strings |
| `quality` | `JSONB` | full ingest report: `rows`, `incoming_rows`, `duplicate_rows`, per-instrument reports, `duration_seconds` |
| `created_at` | `timestamptz` | `server_default now()` |

`id` is never assigned by a caller — it is always the return value of
`SnapshotStore.write()`.

### `ingestion_heads`
`axiom/metadata.py:31-34`; migration `alembic/versions/0001_metadata.py:31-35`.

| column | type | notes |
|---|---|---|
| `stream` | `varchar(64)`, PK | sha256 of `(provider, sorted symbol set)`; also the `pg_advisory_xact_lock` key |
| `dataset_id` | `varchar(64)`, FK → `datasets.id`, not null | newest merged dataset for this stream |

One row per `(provider, symbol set)` combination. The pointer
`ingest_incremental` advances.

### `experiments`
`axiom/metadata.py:37-47`; migration `alembic/versions/0001_metadata.py:36-49`.

| column | type | notes |
|---|---|---|
| `id` | `varchar(36)`, PK | uuid4 string |
| `kind` | `varchar(32)` | `"backtest"` \| `"ml"` |
| `status` | `varchar(24)` | `RUNNING` → `SUCCEEDED` \| `FAILED`; see also `INTERRUPTED` below |
| `dataset_id` | `varchar(64)`, FK → `datasets.id`, not null | |
| `config` | `JSONB` | symbols, strategy, execution config, feature config, ml options |
| `result` | `JSONB`, nullable | present only once `SUCCEEDED` |
| `error` | `varchar(1000)`, nullable | present only once `FAILED`/`INTERRUPTED` |
| `created_at` | `timestamptz` | `server_default now()` |
| `finished_at` | `timestamptz`, nullable | |

`status` transitions are written from exactly two places:
`axiom/platform.py` (`RUNNING` → `SUCCEEDED`/`FAILED`, see `run_experiment`,
`axiom/platform.py:44-53` for the `RUNNING` insert, `:117-121` for
`SUCCEEDED`, `:123-129` for `FAILED`) and `scripts/recover_runs.py`
(`RUNNING` → `INTERRUPTED`, explicit maintenance, user-run only — see Known
issues). No code path updates a `SUCCEEDED`/`FAILED` row again.

### `paper_accounts`
`axiom/metadata.py:50-55`; migration `alembic/versions/0001_metadata.py:50-58`.

| column | type | notes |
|---|---|---|
| `id` | `varchar(36)`, PK | uuid4 string |
| `config` | `JSONB` | `dataset_id`, `symbols`, `strategy`, `execution` — **`dataset_id` here is a plain JSON key, not an FK column** |
| `state` | `JSONB` | `last_session`, `input_hash`, `alerts`, `fills`, `equity`, `account` |
| `updated_at` | `timestamptz` | `server_default now()` only — there is no `onupdate`; callers set it by hand on every write (`axiom/paper.py:108`) |

### Engine construction
`axiom/metadata.py:58-62` — `database(url)` builds one `Engine` with
`pool_pre_ping=True, pool_size=5, max_overflow=5,
connect_args={"connect_timeout": 5}` and a
`sessionmaker(expire_on_commit=False)`. There is **no shared global engine**:
`axiom.api.create_app` and every script (`scripts/ingest.py`,
`scripts/paper_tick.py`, `scripts/recover_runs.py`, `scripts/demo_platform.py`,
...) each call `database(Settings().database_url)` themselves and build their
own `Engine`/`sessionmaker` pair.

## Snapshot store layout

Source of truth: `axiom/data/storage.py`, rooted at `settings.data_root`
(default `data/platform`, `axiom/settings.py:11`).

```
<data_root>/
  raw/<symbol>/<uuid4>.parquet                  # as-fetched capture, pre-validation
  validated/<sha256-id>/
    manifest.json                               # {"version":1,"dataset_id":..., "rows":..., "parts":[...]}
    asset_class=etf/timeframe=<tf>/symbol=<S>/year=<Y>/bars.parquet   # <tf> from the frame's own column, e.g. "1d"
  validated/<sha256-id>.partial-<uuid4>/         # staging dir, never a finished snapshot
```

- `capture()` (`axiom/data/storage.py:16-20`) writes the raw, as-fetched
  frame under `raw/<symbol>/<uuid4>.parquet` before validation, and it is
  kept even if the ingest later fails, for audit.
- `write()` (`axiom/data/storage.py:22-52`) computes
  `identity = sha256(canonical JSON of the frame sorted by
  (instrument, timestamp), with `ingested_at` dropped)` (line 25-26), and
  short-circuits if `validated/<identity>/manifest.json` already exists
  (lines 28-29) — two byte-identical ingests produce the same id and the
  second call is a no-op write. Otherwise it stages into
  `validated/<identity>.partial-<uuid4>/`, writes one Parquet part per
  `(instrument, year, timeframe)` group under
  `asset_class=etf/timeframe=<timeframe>/symbol=<symbol>/year=<year>/bars.parquet`
  (compression `zstd`), writes `manifest.json`, then does an atomic
  `Path.rename()` of the staging dir onto the final `validated/<identity>`
  path (lines 30-51).
  - **Fixed 2026-09-28:** the partition path used to hardcode
    `timeframe=1d` regardless of the frame's actual `timeframe` column;
    `partition_by` now includes `timeframe` in its group key and the path
    is built from that value, so a partition's path always matches its
    actual rows (`axiom/data/storage.py:32-38`). `asset_class` is still
    fixed to `"etf"`, since `Instrument.asset_class` remains a single-value
    `Literal` — that part is not a bug, just a real current constraint.
- `read()` (`axiom/data/storage.py:54-73`) validates the `identity` against
  `^[0-9a-f]{64}$`, resolves every part path and rejects any that would
  resolve outside `root` (path-escape guard, lines 63-65), **re-hashes every
  individual part against `manifest.json`'s recorded `sha256`** (lines 66-67)
  and then **re-hashes the whole reconstructed, concatenated frame against
  the `identity` itself** (lines 70-72) before returning it. A snapshot that
  fails either check raises rather than silently serving corrupt or tampered
  data.
- A crash mid-`write()` leaves an orphaned `*.partial-<uuid4>` staging
  directory under `validated/`, never a `manifest.json` that points at
  incomplete parts, because the manifest is written before the rename and
  the rename is the last step.

## Invariants (verified against current code — 2026-09-28)

All eight invariants in `.claude/agents/database.md` were checked against
current `axiom/metadata.py`, `alembic/versions/0001_metadata.py`,
`axiom/data/storage.py`, `axiom/data/incremental.py`, `axiom/platform.py`,
`axiom/paper.py`, and `scripts/recover_runs.py`. **No drift found; all eight
hold as stated in the brief.**

1. **Dataset identity is derived, never assigned.** Confirmed:
   `axiom/data/storage.py:25-29` computes `identity` from a sha256 of the
   canonicalized frame and short-circuits on an existing manifest. Nothing
   in `axiom/data/incremental.py`, `axiom/platform.py`, or `axiom/paper.py`
   constructs a `DatasetRow` with a caller-supplied `id`; the only
   `DatasetRow(id=...)` call site is `axiom/data/incremental.py:83-92`,
   using `identity` returned from `store.write()`.

2. **`ingestion_heads` moves forward only via the advisory-locked merge
   path.** Confirmed: `ingest_incremental` (`axiom/data/incremental.py:44-98`)
   is the only place `HeadRow` is read or written. It acquires
   `pg_advisory_xact_lock(int(stream[:15], 16))` at the top of the
   transaction (line 45) and holds it through validation and the final
   `head.dataset_id = identity` / `db.add(HeadRow(...))` update (lines
   94-97). Grepping the codebase found no second writer of
   `HeadRow.dataset_id`.

3. **Foreign keys encode real lineage.** Confirmed as described:
   `datasets.parent_id` (`axiom/metadata.py:24`) and
   `experiments.dataset_id` (`axiom/metadata.py:42`) are real FK columns;
   `paper_accounts.config["dataset_id"]` is a JSON key with no FK
   (`axiom/metadata.py:53`, `axiom/paper.py:26-31`) — matches the
   "Known issues" gap below.

4. **JSONB columns are the schema's extension point.** Confirmed:
   `definition`, `symbols`, `quality`, `config`, `result`, `state` are all
   `JSONB` (`axiom/metadata.py:18,26-27,43-44,53-54`). No structural
   constraint (e.g. a Postgres `CHECK` or JSON schema) enforces their
   shape at the database level — enforcement is entirely at the Python
   call sites (e.g. `axiom/paper.py:45-54` re-deriving `dataset_id` from
   `cfg["dataset_id"]`).

5. **No `DELETE`/`UPDATE` path exists for `datasets` or `instruments`.**
   Confirmed by search: no `DELETE`, `session.delete(...)`, or SQLAlchemy
   `delete()` construct appears anywhere under `axiom/` referencing
   `DatasetRow` or `InstrumentRow`. The only writes are the insert in
   `axiom/data/incremental.py:83-92` and the upsert in
   `axiom/data/incremental.py:74-82`.

6. **Paper-account replay is row-locked and content-verified.** Confirmed:
   `axiom/paper.py:42` takes `SELECT ... FOR UPDATE` via
   `db.scalar(select(PaperRow).where(...).with_for_update())`; the
   `input_hash` fingerprint check is at `axiom/paper.py:76-78`
   (`fingerprint(prefix) != row.state["input_hash"]` raises "Previously
   processed bars changed"); the backwards-clock guard is at
   `axiom/paper.py:74-75` (`as_of.isoformat() < last` raises "Paper clock
   cannot move backwards"). Both checks are intact in current code.

7. **Frozen experiment results.** Confirmed: `axiom/platform.py:117-121`
   (`SUCCEEDED`) and `:123-129` (`FAILED`) are the only two places that set
   `ExperimentRow.status`/`.result`/`.error` outside the initial `RUNNING`
   insert (`axiom/platform.py:44-53`); `scripts/recover_runs.py` only
   touches rows still in `RUNNING` (its `WHERE` clause at lines 21-25), so
   it never rewrites a `SUCCEEDED`/`FAILED` row's `result`/`provenance`.

8. **Schema changes are real Alembic migrations.** Confirmed: exactly one
   file under `alembic/versions/` (`0001_metadata.py`), and
   `.github/workflows/ci.yml:28` runs `uv run alembic upgrade head` against
   a fresh `postgres:18-alpine` service container (lines 6-16) before tests
   run — a migration that only worked against a hand-patched database would
   fail CI.

## Known issues (re-verified 2026-09-28)

- **Stuck `RUNNING` rows after a crash are not automatic.** Confirmed:
  `scripts/recover_runs.py` (docstring: "Explicit maintenance: mark old
  interrupted synchronous runs after stopping API workers") only runs when
  the user invokes it; it marks `RUNNING` experiments older than
  `--older-than-hours` (default 24, `scripts/recover_runs.py:12-13`) as
  `INTERRUPTED` under `.with_for_update()` (lines 18-28). Nothing in
  `axiom/paper.py` reconciles a stuck `advance()` call the same way — it is
  a single locked transaction, not a background job, so a crash mid-`advance()`
  simply releases the row lock (Postgres rolls back the open transaction)
  rather than leaving a `RUNNING`-equivalent state to clean up.
- **`paper_accounts.config["dataset_id"]` is not a real foreign key.**
  Confirmed: it is a plain JSON key (`axiom/metadata.py:53`,
  `axiom/paper.py:26-31`), unlike `experiments.dataset_id`
  (`axiom/metadata.py:42`, a real FK). `axiom/paper.py:47-54`
  re-validates it against `DatasetRow` by hand on every `advance()` call
  instead of relying on referential integrity — a proper FK column here
  would be a genuine improvement; flag it as a `database`-owned proposal if
  raised again.
- **Two separate PostgreSQL clusters exist for this project.** Confirmed:
  `scripts/local_db.py` manages an isolated dev cluster at
  `.runtime/postgres`, port 55442, initialized with `initdb -U axiom
  --auth=scram-sha-256` (lines 40-51) and its own generated `.env`. Separately,
  `compose.yaml` defines a `postgres` service (`postgres:18-alpine`) with its
  own named volume `pgdata` on the default port 5432 inside the Compose
  network (`compose.yaml:1-13,44-47`), migrated by a dedicated `migrate`
  service running `alembic upgrade head` (`compose.yaml:14-22`). These are
  independent data stores with independent lifecycles; a backup or restore
  plan must say which one it covers. CI uses a third, ephemeral instance
  (`postgres:18-alpine` service container, `.github/workflows/ci.yml:6-16`)
  that is not persisted at all.
- **`.env` holds the database password and API token in plaintext,
  gitignored.** Confirmed: `.gitignore:13-15` excludes `.env`, `.env.*`
  (keeping `.env.example`); `scripts/local_db.py:31-35` refuses to
  re-initialize a cluster if `.env` already exists, specifically to avoid
  silently generating a new password that no longer matches the running
  cluster's actual password. The repo's `.env` (checked read-only, values
  redacted) currently holds `DATABASE_URL`, `POSTGRES_PASSWORD`,
  `API_TOKEN`, `WORKER_TOKEN`, `COORDINATOR_URL` — all plaintext secrets on
  disk, gitignored but not otherwise protected (no OS-level encryption, no
  secret manager).

## Backup/restore (document only — do not perform)

**Local dev cluster** (`.runtime/postgres`, port 55442): stop the app first
(`scripts/stop_dev.py` — user-run), then use `pg_ctl`/`pg_dump` against
`.runtime/postgres` **together with** a copy of `settings.data_root`
(default `data/platform`). The two must travel together: `experiments`,
`paper_accounts`, and `datasets` rows are meaningless without the Parquet
snapshots they reference (`dataset_id` → `validated/<id>/`), and the
snapshots are meaningless without the rows that give them lineage and
consumers.

**Docker Compose cluster**: back up the `pgdata`, `bars`, `reports` named
volumes together (`compose.yaml:44-47`) — `bars` is the API container's
`data/platform`-equivalent Parquet root and `reports` its report root
(`compose.yaml:20`), so the same "travel together" rule applies.

**Verifying a restore**: for a sampled `dataset_id`, confirm
`SnapshotStore.read()` succeeds (its own manifest + content hash checks,
`axiom/data/storage.py:54-73`, are the integrity proof — a restore that
silently corrupted a Parquet part or dropped a manifest will raise, not
serve bad data), and confirm `scripts/check_platform.py`'s suite passes
against the restored cluster (it sets `AXIOM_TEST_DATABASE_URL` and runs the
full `pytest` suite — `scripts/check_platform.py:1-8`).

## Live-cluster check (2026-09-28)

The local dev cluster's configured endpoint
(`127.0.0.1:55442`, from the repo's `.env`) was probed read-only before any
query was attempted, per the ground rule to never assume a cluster is
running just because `.env` exists. The TCP connection was refused
(`Connection refused`) — **the local cluster is not currently running**, so
no SQL was executed against it and no row counts or stuck-`RUNNING`
diagnostics could be gathered this session. Everything above was verified
from source code alone. Nothing was started, stopped, or otherwise touched.
