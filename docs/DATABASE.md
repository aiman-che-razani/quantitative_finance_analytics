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

Last verified against code at commit `0e88254` (branch `audit-fixes-2`),
2026-09-29. Line numbers below refer to that commit.

## PostgreSQL schema

Source of truth: `axiom/metadata.py`. There are **two** Alembic migrations:

| revision | file | what it does |
|---|---|---|
| `0001` | `alembic/versions/0001_metadata.py` | creates the five tables (`upgrade()` lines 14-58) |
| `0002` (down_revision `0001`) | `alembic/versions/0002_indexes_and_checks.py` | purely additive: indexes `ix_datasets_created_at`, `ix_datasets_parent_id`, `ix_experiments_created_at`, `ix_experiments_status_created_at` (`status, created_at`), `ix_experiments_dataset_id`, `ix_paper_accounts_updated_at`, plus CHECK constraints `ck_experiments_status` and `ck_experiments_kind` (lines 15-27); `downgrade()` drops them all (lines 30-38) |

`0002`'s docstring asks you to confirm `SELECT DISTINCT status, kind FROM
experiments` returns only allowed values before upgrading a cluster that
already has rows, because the CHECK constraints are created validated.

The ORM models mirror `0002`: `DatasetRow.parent_id` and
`ExperimentRow.dataset_id` carry `index=True`, and the named indexes and
CHECK constraints live in `__table_args__` (`axiom/metadata.py:23,25,49-54,58,68`).
The CHECK text is built by `_one_of()` from the `EXPERIMENT_STATUSES` /
`EXPERIMENT_KINDS` constants (`axiom/metadata.py:38-44`) and renders to the
same SQL as the literals frozen in migration `0002`
(`status IN ('RUNNING','SUCCEEDED','FAILED','INTERRUPTED')`,
`kind IN ('backtest','ml')`). If either tuple changes, a new migration is still
required: `0002` keeps its own literals on purpose.

CI applies both migrations with `uv run alembic upgrade head` against a fresh
`postgres:18-alpine` service container on every push/PR
(`.github/workflows/ci.yml:13-23,35`). The Windows CI job has no PostgreSQL
service, so database tests skip there (`.github/workflows/ci.yml:41-52`).

**Live dev cluster (last observed 2026-09-29):** `0002` is applied; the
cluster held 4 datasets, 35+ experiments and 4 paper accounts. The cluster is
currently stopped and was not queried for this revision.

### `instruments`
`axiom/metadata.py:15-18`; migration `0001_metadata.py:15-19`.

| column | type | notes |
|---|---|---|
| `symbol` | `varchar(16)`, PK | |
| `definition` | `JSONB`, not null | full `Instrument` model dump (`model_dump(mode="json")`) |

One row per known instrument. Upserted (`INSERT ... ON CONFLICT DO UPDATE`)
on every ingest, never written any other way
(`axiom/data/incremental.py:75-83`).

### `datasets`
`axiom/metadata.py:21-29`; migration `0001_metadata.py:20-30`, indexes in `0002:16-17`.

| column | type | notes |
|---|---|---|
| `id` | `varchar(64)`, PK | sha256 hex digest, see Invariant 1 |
| `parent_id` | `varchar(64)`, FK → `datasets.id`, nullable, indexed | chains an incremental merge to the snapshot it extended |
| `provider` | `varchar(64)`, not null | |
| `symbols` | `JSONB`, not null | sorted list of symbol strings |
| `quality` | `JSONB`, not null | ingest report: `rows`, `incoming_rows`, `duplicate_rows`, `instruments` (per-symbol validation report plus `raw_capture`, the path of that symbol's raw Parquet capture), `duration_seconds` (`axiom/data/incremental.py:38,66-74`) |
| `created_at` | `timestamptz`, not null, indexed | `server_default now()` |

`id` is never assigned by a caller: it is always the return value of
`SnapshotStore.write()`. The row is only inserted if no row with that `id`
exists yet (`axiom/data/incremental.py:84-94`); re-ingesting identical
content reuses the existing row.

### `ingestion_heads`
`axiom/metadata.py:32-35`; migration `0001_metadata.py:31-35`.

| column | type | notes |
|---|---|---|
| `stream` | `varchar(64)`, PK | sha256 of JSON `[provider, sorted symbols]`; `int(stream[:15], 16)` is the `pg_advisory_xact_lock` key (`axiom/data/incremental.py:41-45`) |
| `dataset_id` | `varchar(64)`, FK → `datasets.id`, not null | newest merged dataset for this stream |

One row per `(provider, symbol set)` combination. The pointer
`ingest_incremental` advances (`axiom/data/incremental.py:95-98`).

### `experiments`
`axiom/metadata.py:47-63`; migration `0001_metadata.py:36-49`, indexes and checks in `0002:18-20,22-27`.

| column | type | notes |
|---|---|---|
| `id` | `varchar(36)`, PK | uuid4 string |
| `kind` | `varchar(32)`, not null | CHECK `ck_experiments_kind`: `backtest` \| `ml` |
| `status` | `varchar(24)`, not null | CHECK `ck_experiments_status`: `RUNNING` \| `SUCCEEDED` \| `FAILED` \| `INTERRUPTED` |
| `dataset_id` | `varchar(64)`, FK → `datasets.id`, not null, indexed | |
| `config` | `JSONB`, not null | `symbols`, `strategy`, `execution`, `features`, `ml` (`axiom/platform.py:37-43`) |
| `result` | `JSONB`, nullable | set only on `SUCCEEDED`; includes `provenance` (dataset id, provider, git commit, code-tree sha256, dirty flag, config) |
| `error` | `varchar(1000)`, nullable | set on `FAILED` (`str(exc)` or the exception type name, truncated to 1000) or `INTERRUPTED` |
| `created_at` | `timestamptz`, not null | `server_default now()` |
| `finished_at` | `timestamptz`, nullable | |

`status` transitions are written from exactly two places:

- `axiom/platform.py` `run_experiment`: inserts `RUNNING` in its own
  transaction (lines 44-53), then `SUCCEEDED` (lines 116-120) or `FAILED`
  (lines 122-133). The `FAILED` handler catches **`BaseException`**, so
  Ctrl-C (`KeyboardInterrupt`) and `SystemExit` also mark the row, and a
  failure while marking is swallowed so it cannot mask the original error;
  the original exception is always re-raised.
- `scripts/recover_runs.py` (`RUNNING` → `INTERRUPTED`, explicit maintenance,
  user-run only; see Known issues).

No code path updates a `SUCCEEDED`/`FAILED` row again. Because of the CHECK
on `kind`, a call with an unknown kind now fails at the `RUNNING` insert (an
`IntegrityError`, no row written) instead of reaching the
`"Unknown experiment kind"` branch at `axiom/platform.py:85-86`; the API
already restricts `kind` to `Literal["backtest", "ml"]` (`axiom/api.py:42`).

### `paper_accounts`
`axiom/metadata.py:66-72`; migration `0001_metadata.py:50-58`, index in `0002:21`.

| column | type | notes |
|---|---|---|
| `id` | `varchar(36)`, PK | uuid4 string |
| `config` | `JSONB`, not null | `dataset_id`, `symbols`, `strategy`, `execution`, `features` (`axiom/paper.py:38-44`). **`dataset_id` is a plain JSON key, not an FK column.** Accounts created before `features` was stored replay with `FeatureConfig()` defaults (`axiom/paper.py:107-108`). `advance()` rewrites `config.dataset_id` to the dataset it just replayed (`axiom/paper.py:133`), so the key points at the newest dataset, not the one the account was created on |
| `state` | `JSONB`, not null | created as `{"last_session": null, "alerts": [], "fills": []}` (`axiom/paper.py:45`); after the first replay: `last_session`, `input_hash`, `provider`, `mode` (`"historical paper replay"`), `alerts`, `fills`, `equity`, `account` (`axiom/paper.py:122-131`); plus `last_error` after a failed scheduled tick (see below) |
| `updated_at` | `timestamptz`, not null, indexed | `server_default now()` only, no `onupdate`; every writer sets it by hand (`axiom/paper.py:105,134,155`) |

Alerts: `STALE_INPUT` (no new bar for more than `STALE_AFTER_DAYS = 4`
calendar days), `RISK_REJECTION` (a rejection in the latest session only),
and `TICK_FAILED`. `record_tick_failure()` (`axiom/paper.py:138-155`) takes
the row lock (`FOR UPDATE`), merges `TICK_FAILED` into the existing alerts,
stores `last_error` (the caller passes only the exception type name, e.g.
`"OperationalError (details in the tick log)"`, `scripts/paper_tick.py:76-79`)
and sets `updated_at`. A later successful tick clears both: the no-new-bar
path drops `TICK_FAILED`/`STALE_INPUT` and `last_error`
(`axiom/paper.py:93-106`), and a full replay writes a fresh `state` without
them.

### Engine construction
`axiom/metadata.py:75-79`: `database(url)` builds one `Engine` with
`pool_pre_ping=True, pool_size=5, max_overflow=5,
connect_args={"connect_timeout": 5}` and a
`sessionmaker(expire_on_commit=False)`. There is **no shared global engine**:
`axiom.api.create_app` and every script (`scripts/ingest.py`,
`scripts/paper_tick.py`, `scripts/recover_runs.py`,
`scripts/prune_snapshots.py`, `scripts/demo_platform.py`, ...) each call
`database(Settings().database_url)` themselves.

## Snapshot store layout

Source of truth: `axiom/data/storage.py`, rooted at `settings.data_root`
(default `data/platform`, `axiom/settings.py:11`; gitignored via `/data/`,
`.gitignore:11`).

```
<data_root>/
  raw/<symbol>/<uuid4>.parquet                  # as-fetched capture, pre-validation
  validated/<sha256-id>/
    manifest.json                               # {"version":1,"dataset_id":..., "rows":..., "parts":[{"path","rows","sha256"}, ...]}
    asset_class=etf/timeframe=<tf>/symbol=<S>/year=<Y>/bars.parquet   # <tf> from the frame's own column, e.g. "1d"
  validated/<sha256-id>.partial-<uuid4>/         # staging dir, never a finished snapshot
  validated/<sha256-id>.corrupt-<uuid4>/         # a published snapshot whose parts failed their hashes, set aside
```

- `capture()` (`axiom/data/storage.py:23-27`) writes the raw, as-fetched
  frame under `raw/<symbol>/<uuid4>.parquet` before validation. It is kept
  even if the ingest later fails, for audit, and **nothing ever deletes it**
  (see Known issues).
- `write()` (`axiom/data/storage.py:29-60`):
  - Rejects an empty frame, then computes
    `identity = sha256(frame.sort(instrument, timestamp).drop("ingested_at").write_json())`
    (lines 30-33).
  - **Short-circuit is conditional** (lines 35-45): if
    `validated/<identity>/manifest.json` exists *and* `_parts_intact()`
    re-hashes every part listed in the manifest successfully, it returns the
    existing id without writing. If the manifest exists but any part is
    missing, unreadable, escapes the snapshot root, or fails its sha256,
    the directory is renamed to `<identity>.corrupt-<uuid4>` for inspection
    and the same content is republished from the in-memory frame. If that
    rename raises `OSError` (another writer is healing it, or a Windows
    reader holds a file open) it is ignored and the publish race below
    decides the outcome. `_parts_intact()` (lines 116-125) checks part
    hashes only, not the whole-frame content hash that `read()` also checks,
    and uses the same path-containment helper `_part_path()` as `read()`.
  - Otherwise it stages into `validated/<identity>.partial-<uuid4>/`
    (`_stage`, lines 62-89): one zstd Parquet part per
    `(instrument, year, timeframe)` group, each fsynced, then
    `manifest.json` (fsynced), then the part directories and the staging
    directory, then an atomic `Path.rename()` onto `validated/<identity>`
    (line 49), then an fsync of `validated/` (line 59).
  - Staging cleanup (lines 50-58): on an `OSError` the staging directory is
    removed, and if `validated/<identity>/manifest.json` now exists (a
    concurrent writer published the same content first) the call returns
    that id as success; otherwise it re-raises. On any other exception,
    including `KeyboardInterrupt`, the staging directory is removed and the
    exception re-raised.
  - `asset_class` is fixed to `"etf"` because `Instrument.asset_class` is
    still a single-value `Literal`; `timeframe` comes from the group key
    (fixed 2026-09-28; previously hardcoded to `1d`).
- `_fsync()` (lines 128-137): on Windows, **directory fsync is skipped**
  (Windows cannot open a directory for fsync) and files are opened
  `O_RDWR` because Windows `_commit` needs a writable descriptor. So on
  Windows the rename itself is not made durable against power loss; on
  POSIX both the parts and the directory entries are.
- `read()` (lines 91-106) validates `identity` against `^[0-9a-f]{64}$`,
  resolves each part through `_part_path()` (lines 109-113, rejects any path
  that resolves outside the snapshot directory), **re-hashes every part
  against `manifest.json`'s `sha256`**, then **re-hashes the whole
  reconstructed frame against `identity`**. A snapshot that fails either
  check raises rather than serving corrupt or tampered data. `read()` does
  not heal; only a later `write()` of the same content does.

### What is left on disk after a failure

- **Ordinary exception or Ctrl-C inside `write()`**: the staging directory
  is removed by the `except` handlers; nothing is left in `validated/`.
- **Hard crash / kill / power loss mid-`write()`**: the handlers never run,
  so an orphaned `*.partial-<uuid4>` directory can remain. It never
  masquerades as a published snapshot, because only the final rename
  creates `validated/<identity>/`.
- **Torn publish discovered later** (e.g. power loss on Windows after the
  rename, disk corruption): the next `write()` of the same content moves it
  to `*.corrupt-<uuid4>` and republishes.
- **Ingest rolled back after the snapshot was published** (e.g. a DB error
  after `store.write()` at `axiom/data/incremental.py:65`): a complete
  `validated/<id>/` exists that no `datasets` row references.

All four kinds of leftover are listed (and with `--delete` removed) by
`scripts/prune_snapshots.py`; see Known issues.

### Content IDs are not portable across platforms

The id is a hash of Polars' JSON serialization of the frame. Synthetic
floating-point values can differ in the last bits between platform math
libraries, so the same synthetic ingest can produce **different dataset ids
on Windows and Linux** even when numerical results agree
(`docs/validation-v1.md:16`). The id also depends on Polars'
`write_json()` output format; a Polars upgrade that changes it would change
the id of newly written snapshots, and `read()` of old snapshots would fail
its content-hash check. Do not compare ids across machines or assume a
snapshot copied between OSes will be recognised as "the same" by a fresh
ingest.

## Invariants (verified against code at `0e88254`, 2026-09-29)

1. **Dataset identity is derived, never assigned.** `axiom/data/storage.py:32-33`
   computes `identity`; the only `DatasetRow(id=...)` construction is
   `axiom/data/incremental.py:84-94`, using the id returned by
   `store.write()` at line 65. Identical content returns the existing id
   only when its parts verify (conditional short-circuit above).

2. **`ingestion_heads` moves forward only via the advisory-locked merge
   path.** `ingest_incremental` (`axiom/data/incremental.py:44-98`) is the
   only reader/writer of `HeadRow`. It takes
   `pg_advisory_xact_lock(int(stream[:15], 16))` at line 45 and holds it
   through the parent read (line 48), merge, validation, `store.write()`,
   instrument upsert, dataset insert and head update (lines 95-98), all in
   one `sessions.begin()` transaction. No second writer of
   `HeadRow.dataset_id` exists.

3. **Foreign keys encode real lineage.** `datasets.parent_id`
   (`axiom/metadata.py:25`) and `experiments.dataset_id` (line 58) are real
   FK columns; `paper_accounts.config["dataset_id"]` is a JSON key with no FK
   (`axiom/paper.py:38-39`) and is rewritten on every full replay
   (`axiom/paper.py:133`), so the account keeps no history of which earlier
   datasets it replayed (only `datasets.parent_id` chains can reconstruct it).

4. **JSONB columns are the schema's extension point.** `definition`,
   `symbols`, `quality`, `config`, `result`, `state` are all `JSONB`
   (`axiom/metadata.py:18,27-28,59-60,70-71`). Their shape is not enforced by
   the database; readers must tolerate old rows. Example already in code:
   paper accounts created before `config.features` existed fall back to
   defaults (`axiom/paper.py:107-108`). The only database-level value
   constraints are the two CHECKs on `experiments.status`/`kind` (non-JSONB
   columns).

5. **No `DELETE`/`UPDATE` path exists for `datasets` or `instruments` rows.**
   The only writes are the upsert (`axiom/data/incremental.py:75-83`) and the
   insert (lines 84-94). Snapshot **directories**, however, can now be
   deleted: `scripts/prune_snapshots.py --delete` removes directories under
   `validated/` whose name is not a `datasets.id` (lines 31,35-40,47-50). It
   never deletes a referenced snapshot and never touches rows or `raw/`. Its
   guards: dry run by default; skips directories modified within
   `--min-age-minutes` (default 60, lines 23,34,40-42) so an in-flight
   ingest's just-published snapshot (written before its dataset row commits)
   survives; refuses `--delete` when the database has no dataset rows unless
   `--force` (lines 43-46), because a wrong or empty `DATABASE_URL` would
   make every snapshot look orphaned; and prints the database host/port/name
   and resolved data root first (line 28) so the operator can see which pair
   it is comparing.

6. **Paper-account replay is row-locked and content-verified.**
   `axiom/paper.py:55` takes `SELECT ... FOR UPDATE` on the `PaperRow`; the
   backwards-clock guard is at lines 88-89 (`PaperConflict`, HTTP 409) and
   the `input_hash` fingerprint check at lines 90-92. `advance()` also checks
   the target dataset exists, shares the original dataset's provider, and
   covers the account's symbols (lines 60-68). `record_tick_failure` takes
   the same row lock (line 148).

7. **Frozen experiment results.** Only `axiom/platform.py:116-120`
   (`SUCCEEDED`) and `:122-133` (`FAILED`) set `status`/`result`/`error`
   after the `RUNNING` insert; `scripts/recover_runs.py` only touches rows
   still `RUNNING` (its `WHERE`, lines 21-25). No path rewrites a finished
   row or its `provenance`.

8. **Schema changes are real Alembic migrations.** Two migrations exist
   (`0001`, `0002`); the ORM keeps `metadata.py` in step with them. A new
   column/table/constraint needs a new revision with `upgrade()`/`downgrade()`,
   applied by the user with `alembic upgrade head`. CI runs
   `alembic upgrade head` on a fresh PostgreSQL 18 container
   (`.github/workflows/ci.yml:35`). Note that the integration-test fixture
   uses `Base.metadata.create_all()` (`tests/test_platform.py:116-123`), which
   is a no-op after migrations have run but means tests alone do not prove a
   migration matches the models.

## Known issues (re-verified at `0e88254`, 2026-09-29)

- **Stuck `RUNNING` rows are rarer but still possible.** Since
  `run_experiment` marks `FAILED` on any `BaseException`, ordinary errors,
  Ctrl-C and `SystemExit` no longer leave `RUNNING`. It still stays
  `RUNNING` after a hard kill / power loss, or if the database itself is
  unreachable when the `FAILED` update is attempted (that failure is
  swallowed, `axiom/platform.py:131-132`). `scripts/recover_runs.py`
  (docstring: "Explicit maintenance: mark old interrupted synchronous runs
  after stopping API workers") marks `RUNNING` experiments older than
  `--older-than-hours` (default 24, minimum 1; lines 12-15) as `INTERRUPTED`
  under `FOR UPDATE` (lines 17-32). It is user-run only, with API workers
  stopped first. A crash mid-`advance()` needs no cleanup: it is one
  transaction, and PostgreSQL rolls it back and releases the row lock.

- **`paper_accounts.config["dataset_id"]` is not a real foreign key.**
  `advance()` re-validates it against `DatasetRow` by hand on every call
  (`axiom/paper.py:60-68`). A proper FK column would be a genuine
  improvement (a `database`-owned proposal).

- **Orphaned snapshot directories need manual pruning.** Crash leftovers
  (`*.partial-*`), set-aside `*.corrupt-*` directories, and snapshots from
  rolled-back ingests accumulate until the user runs
  `scripts/prune_snapshots.py` (dry run) and then `--delete`. Residual race:
  the age guard uses the directory's own mtime. If an ingest's `write()`
  short-circuits onto an *old* unreferenced snapshot of the same content
  (e.g. one left by an earlier rolled-back ingest), that directory can be
  older than the cutoff while the ingest's dataset row is not yet committed;
  a concurrent `prune --delete` could remove it, leaving a committed
  `datasets` row whose snapshot is gone. Run prune with ingests and
  `paper_tick.py --live-data` stopped.

- **`raw/` captures grow without bound.** Every ingest (including every
  `paper_tick.py --live-data` tick) writes one raw Parquet file per symbol
  (`axiom/data/storage.py:23-27`) and nothing, including
  `prune_snapshots.py`, ever removes them. `datasets.quality` records their
  paths, so deleting them by hand loses that audit link. No retention policy
  exists yet.

- **A corrupt snapshot is not healed if the set-aside rename fails.** If
  `target.rename(...corrupt-...)` raises `OSError`
  (`axiom/data/storage.py:40-45`), the corrupt directory stays in place, the
  subsequent `stage.rename(target)` fails because the target exists, and the
  `except OSError` branch sees the (corrupt) manifest and returns the id as
  success (lines 50-54). The caller then records a dataset whose `read()`
  will raise. Retrying the ingest once the file lock is gone heals it.

- **Windows durability is weaker.** Directory fsync is skipped on Windows
  (`axiom/data/storage.py:130-131`), so a power loss shortly after publishing
  can lose or tear the rename; the conditional short-circuit repairs a torn
  publish on the next identical write, but not a lost one.

- **Two separate PostgreSQL clusters exist for this project.**
  `scripts/local_db.py` manages an isolated dev cluster at
  `.runtime/postgres`, port 55442 on 127.0.0.1, initialized with
  `initdb -U axiom --auth=scram-sha-256 --encoding=UTF8 --locale=C`
  (lines 48-59), database `postgres`. Separately, `compose.yaml` runs
  `postgres:18-alpine` with user/db `axiom` and named volume `pgdata`
  (`compose.yaml:2-14,56-59`), reachable as `postgres:5432` inside the
  Compose network only, migrated by the `migrate` service
  (`compose.yaml:15-26`). CI uses a third, ephemeral container
  (`.github/workflows/ci.yml:13-23`). A backup or restore plan must say which
  one it covers.

- **`.env` holds the database password and API token in plaintext.** It is
  gitignored (`.gitignore:13-15`). `scripts/local_db.py` writes it (and the
  temporary `initdb` password file) through `write_secret()`, which creates
  the file with mode `0600` and re-applies `chmod 0600`
  (`scripts/local_db.py:15-20,62-66`); **on Windows that mode has no
  effect**, so the file inherits the directory's ACLs. `local_db.py start`
  refuses to initialize a new cluster if `.env` already exists
  (lines 39-43), to avoid generating a password that no longer matches the
  running cluster. `local_db.py` writes only `DATABASE_URL`,
  `POSTGRES_PASSWORD` and `API_TOKEN`; the current checkout's `.env`
  (key names checked, values not read) additionally holds `WORKER_TOKEN` and
  `COORDINATOR_URL`, which Axiom's `Settings` ignores (`extra="ignore"`,
  `axiom/settings.py:8`).

## Backup/restore (document only; do not perform)

**Local dev cluster** (`.runtime/postgres`, port 55442): stop the app first
(`scripts/stop_dev.py`, user-run), then use `pg_dump` (cluster running) or a
file-level copy of `.runtime/postgres` (after `scripts/local_db.py stop`)
**together with** a copy of `settings.data_root` (default `data/platform`).
The two must travel together: `experiments`, `paper_accounts` and `datasets`
rows are meaningless without the snapshots they reference
(`dataset_id` → `validated/<id>/`), and snapshots are meaningless without the
rows that give them lineage. Include `raw/` if the audit trail in
`datasets.quality.instruments.*.raw_capture` matters. Restore onto the same
OS family where possible (see "Content IDs are not portable").

**Docker Compose cluster**: back up the `pgdata`, `bars` and `reports` named
volumes together (`compose.yaml:56-59`). `bars` is mounted at `/app/data`
(`compose.yaml:38`), so it holds the API's default `data/platform` snapshot
root; `reports` is mounted at `/app/reports`.

**Verifying a restore**: for sampled `dataset_id`s, confirm
`SnapshotStore.read()` succeeds (its per-part and whole-frame hash checks are
the integrity proof). Run `scripts/prune_snapshots.py` in dry-run mode: it
should list only known leftovers (`*.partial-*`, `*.corrupt-*`, rolled-back
ingests); a large unexpected orphan list means the database and data root
came from different backups. (It does not detect the reverse case, a
`datasets` row whose snapshot is missing; the `read()` sampling covers that.) `scripts/check_platform.py` runs the full
pytest suite with `AXIOM_TEST_DATABASE_URL` set to the configured database
(`scripts/check_platform.py:1-8`); the integration fixture works inside a
rolled-back transaction with a temporary data root
(`tests/test_platform.py:116-134`), so it exercises the restored cluster
without keeping rows.

## Live-cluster status

Last observed 2026-09-29 (by an earlier read-only check): migration `0002`
applied; 4 datasets, 35+ experiments, 4 paper accounts. For this revision the
cluster was deliberately left stopped; no SQL was run and nothing was started,
stopped or modified. Everything else above is verified from source at
`0e88254`.
