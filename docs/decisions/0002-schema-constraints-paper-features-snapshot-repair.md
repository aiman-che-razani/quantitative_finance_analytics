# 0002: Constrain experiment status/kind in the schema, persist paper-account features, and self-repair corrupt snapshots

## Status

Accepted (reflects the shipped state of branch `audit-fixes-2` at `0e88254`;
not a proposal). Recorded under architecture invariant 14 (schema and
protocol changes get an ADR): all three changes touch `metadata.py`'s tables,
a persisted config shape, or the snapshot storage protocol.

## Context

Three gaps were closed together during the agent audits (commits `856baa9`,
`4f4d702`):

1. **Experiment status/kind were free text.** `experiments.status` and
   `experiments.kind` (`alembic/versions/0001_metadata.py:39-40`) accepted any
   string. The code only ever writes `RUNNING`/`SUCCEEDED`/`FAILED`
   (`axiom/platform.py:51`, `:118`, `:128`) and `INTERRUPTED`
   (`scripts/recover_runs.py:30`), and only accepts kinds `backtest`/`ml`
   (`axiom/api.py:42`, `axiom/platform.py:61-86`), but nothing in the
   database enforced that. The list/recovery queries (`GET /experiments`
   ordered by `created_at`, `api.py:154-159`; `GET /datasets`, `api.py:97-99`;
   `GET /paper` ordered by `updated_at`, `api.py:197-199`;
   `recover_runs.py` filtering on `status` and `created_at`,
   `recover_runs.py:19-27`) also had no supporting indexes.
2. **Paper accounts ignored their feature settings.** `paper.advance()`
   always replayed with `FeatureConfig()` defaults, so an account could not
   be created with, e.g., a different EMA period, and nothing recorded which
   feature parameters an account's fills came from.
3. **A torn snapshot publish was permanent.** `SnapshotStore.write` returned
   early whenever `validated/<id>/manifest.json` existed. A publish whose
   parts were later truncated or corrupted (crash after rename on a
   filesystem that did not persist the parts, disk error, manual damage)
   would therefore never be rewritten: every later ingest of the same content
   "succeeded" while every `read()` failed its hash check.

## Decision

### Migration 0002: indexes and CHECK constraints

`alembic/versions/0002_indexes_and_checks.py` (revision `0002`,
`down_revision = "0001"`) is purely additive:

- Indexes `ix_datasets_created_at`, `ix_datasets_parent_id`,
  `ix_experiments_created_at`, `ix_experiments_status_created_at`,
  `ix_experiments_dataset_id`, `ix_paper_accounts_updated_at`
  (`0002_indexes_and_checks.py:16-21`).
- `ck_experiments_status`: `status IN ('RUNNING','SUCCEEDED','FAILED','INTERRUPTED')`
  and `ck_experiments_kind`: `kind IN ('backtest','ml')` (`:22-27`).
- `downgrade()` drops all of them (`:30-38`).

**Upgrade precondition.** Adding a CHECK constraint validates existing rows,
so the upgrade fails on a cluster holding any other value. Before upgrading a
populated database, confirm `SELECT DISTINCT status, kind FROM experiments`
returns only the allowed values (`0002_indexes_and_checks.py:3-4`).

**Where the value lists live.** The ORM model builds its CHECK text from
`EXPERIMENT_STATUSES` and `EXPERIMENT_KINDS` (`axiom/metadata.py:38-44`,
`:52-53`), so `metadata.py` has one source of truth. The migration keeps its
own **frozen literals** on purpose: a migration describes the schema as of
that revision and must not change meaning when application constants change
later. The model's `_one_of` output renders to exactly the migration's
strings today.

**Adding a status or kind** therefore requires, together:

1. a new Alembic migration that drops and recreates the relevant
   `ck_experiments_*` constraint with the new literal list (never editing
   0002);
2. updating `EXPERIMENT_STATUSES`/`EXPERIMENT_KINDS` in `axiom/metadata.py`;
3. updating the API's accepted values — `ResearchRequest.kind`'s
   `Literal["backtest", "ml"]` (`axiom/api.py:42`) for a kind — and the
   dispatch in `run_experiment` (`platform.py:61-86`);
4. reviewing `scripts/recover_runs.py`, which assumes `RUNNING` is the only
   non-terminal status and writes `INTERRUPTED` (`recover_runs.py:22`,
   `:30`), and any dashboard code that switches on status.

### Paper-account feature persistence

`paper.create_account` stores the account's `FeatureConfig` as
`config["features"]` (`axiom/paper.py:43`; defaults when none is given), and
`POST /paper` accepts a `features` object (`api.py:31`, `:214`).
`paper.advance` replays with `FeatureConfig(**cfg.get("features", {}))`
(`paper.py:107-108`). Rows created before this change have no `features` key
and replay with the defaults — exactly what every tick used before, so their
replay is unchanged and no data migration is needed. No column was added:
`config` is already JSONB.

### Corrupt-snapshot repair

`SnapshotStore.write` returns early only when the manifest exists **and**
`_parts_intact` confirms every part exists within the snapshot directory
(path containment through the shared `_part_path` helper) and matches its
recorded sha256 (`axiom/data/storage.py:35-37`, `:109-125`). Otherwise it
renames the existing directory aside to `<id>.corrupt-<uuid>` (kept for
inspection, never deleted automatically) and republishes the same content from
the verified in-memory frame via the normal stage-then-rename path
(`storage.py:38-49`). If the set-aside rename raises `OSError` (a concurrent
healer, or a Windows reader holding a file open) it is ignored and the publish
race decides (`:42-45`, `:50-55`). The module docstring now states the
contract as "concurrent writers of the same content are tolerated; first
publish wins" (`storage.py:1-5`), replacing the earlier single-writer claim.
`scripts/prune_snapshots.py` is the explicit, dry-run-by-default cleanup path
for `*.corrupt-*` and `*.partial-*` directories.

This keeps invariant 1: the content ID is unchanged, and a repair produces a
new directory whose content hashes to that same ID; nothing is modified in
place.

## Consequences

- **The database now rejects unknown statuses/kinds**, turning a silent
  data-quality problem into an immediate `IntegrityError`. The cost is a
  four-place change (migration, constants, API `Literal`, `recover_runs.py`)
  for any new status/kind; skipping the migration makes inserts fail against
  a migrated database while tests still pass, because the test suite creates
  its schema with `Base.metadata.create_all` (`tests/test_platform.py:122`)
  rather than running migrations. Nothing currently checks that the model and
  the migration chain agree (e.g. an Alembic autogenerate diff in CI).
- **Upgrading an old cluster can fail** at the CHECK step if stray values
  exist; the operator must inspect and fix those rows first. The migration is
  transactional on PostgreSQL, so a failed upgrade leaves revision `0001`
  intact.
- **Paper accounts are now tied to `FeatureConfig`'s shape.**
  `FeatureConfig` is `extra="forbid"` (`axiom/common/models.py:41`), so
  removing or renaming a field makes every stored account that has it fail to
  replay; adding a field, or changing a default, silently changes the replay
  of accounts that stored an older shape (they pick up the new default). The
  prefix-hash check in `advance` covers input bars only (`paper.py:90-92`),
  not configuration, so such a change would rewrite historical paper fills
  without a `PaperConflict`. Any future `FeatureConfig` change is therefore
  an invariant-14 change for paper accounts as well as experiments. The same
  already held for the persisted `ExecutionConfig`.
- **A corrupt snapshot heals on the next ingest of the same content** rather
  than staying broken, and the damaged copy is preserved for diagnosis. The
  cost is disk: set-aside directories accumulate until an operator runs
  `prune_snapshots.py --delete`.
- **`write()` hashes every part on each idempotent call**, so re-ingesting
  unchanged large content now reads all its Parquet parts once more. For the
  benchmarked scale this is the same order as one `read()`; no timing was
  measured.
- **Healing is best-effort under contention.** If the set-aside rename fails
  and the stage rename then fails because the damaged directory is still in
  place, `write()` sees a manifest at the target and returns the ID without
  having repaired it (`storage.py:40-45`, `:50-54`). `read()` still refuses
  the damaged data, so this can never serve corrupt bars, but the repair then
  waits for a later write.
