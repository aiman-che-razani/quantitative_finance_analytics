# Agent roster

Claude Code subagents defined in `.claude/agents/` for this repo (Axiom). Each
agent's description is its trigger — it says concretely when to use it — and
no two agents claim the same job. See `.claude/agents/agents.md` for the full
ground rules (roster boundaries, tool grants, forbidden scripts, ML guardrails)
this table summarizes.

Agent files load at session start: a new or edited file in `.claude/agents/`
is not visible to the session that created it and takes effect next session.
Sibling repos (SentinelDAQ, GreyQueue) have agents with the same names; say
which project's file you are using when more than one is loaded.

| Name | Purpose | Owned doc(s) | Tools |
|---|---|---|---|
| `prd` | Decide whether a feature fits Axiom's V0.2-V1.0 scope; turn ideas into user stories with testable acceptance criteria; set the synthetic-vs-provider-sourced (Yahoo) honesty policy | `docs/PRD.md` | Read, Grep, Glob, Bash, Write, Edit |
| `architecture` | Decide which layer (data/ingestion, storage, features, backtest/risk/portfolio, ml, api, dashboard) owns a change; keep the invariants (incl. platform-dependent dataset IDs); write ADRs before adding a data provider, strategy, order type, risk check, or cross-cutting feature | `docs/architecture/system.md`, `docs/decisions/` | Read, Grep, Glob, Bash, Write, Edit |
| `agents` | Own the agent roster itself and the walk-forward ML guardrails (`axiom/ml/walkforward.py`, `axiom/platform.py::run_experiment`), including "AUC counts as skill only above the null p95"; review any new model-based feature or LLM proposal | `docs/AGENTS.md` | Read, Grep, Glob, Bash, Write, Edit |
| `security` | Review diffs/features for vulnerabilities (API auth/exposure, proxy host/origin/token handling, snapshot path/hash handling, Docker/CI hardening); own supply-chain pinning (Dependabot, image digests, Action SHAs); required on every diff touching `axiom/api.py`, the dashboard proxy route, `axiom/data/storage.py`, `axiom/metadata.py`, `alembic/versions/`, `compose.yaml`, `Dockerfile`, `apps/dashboard/Dockerfile`, or `.github/` | `docs/SECURITY.md` | Read, Grep, Glob, Bash, Write, Edit |
| `code-style` | Line-level Python (ruff/mypy-enforced) and TypeScript/Next.js style review; run the actual checkers, not guesswork | `docs/CODE_STYLE.md` | Read, Grep, Glob, Bash, Write, Edit |
| `database` | PostgreSQL/SQLAlchemy/Alembic schema plus the immutable content-addressed Parquet snapshot layout; schema/migration review, stuck-experiment and orphaned/corrupt-snapshot diagnosis, `scripts/prune_snapshots.py` and raw-capture growth, backup/restore planning | `docs/DATABASE.md` | Read, Grep, Glob, Bash, Write, Edit |
| `api` | The authenticated FastAPI research API (`axiom/api.py`) and the Next.js server-side proxy (`apps/dashboard/app/api/[...path]/route.ts`); endpoint shape, status codes, admission gate, paper-account advance flow | `docs/API.md` | Read, Grep, Glob, Bash, Write, Edit |
| `design-system` | Visual language of the Axiom Next.js dashboard (`apps/dashboard/`); tokens/patterns audit, new UI elements, research/paper-trading state and provenance treatment | `docs/DESIGN_SYSTEM.md` | Read, Grep, Glob, Bash, Write, Edit |
| `testing` | Run the suite and report exact results; own the CI OS/runtime matrix (Linux Python 3.12/3.14, Windows job, Node 26 dashboard, Docker job); find coverage gaps and recommend exact test code (does not edit tests); judge "tests pass" vs. actually verified; the only agent allowed to start/stop the local dev PostgreSQL cluster, and only to run tests | `docs/TESTING.md` | Read, Grep, Glob, Bash, Write, Edit |
| `evidence` | Check a specific claim (README, a doc, `docs/showcase.json`, the portfolio page) against recorded evidence artifacts (`docs/benchmarks/results.json`, `docs/validation-v1.md`, `docs/verification-evidence.json`, `docs/ml-validation.json`, `docs/showcase.json` provenance); never edits `personalportfolio` or regenerates an artifact | `docs/benchmarks/README.md` | Read, Grep, Glob, Bash, Write, Edit |

## Scripts no agent runs

Every role file forbids: `scripts/local_db.py` (except `testing`, to run
tests), `scripts/dev.py` / `scripts/stop_dev.py`, `scripts/demo_platform.py`,
`scripts/demo_ml.py`, `scripts/ingest.py`, `scripts/paper_tick.py`,
`scripts/recover_runs.py`, `scripts/prune_snapshots.py --delete`,
`scripts/export_showcase.py`, `scripts/benchmark.py`,
`scripts/check_docker.py`, `scripts/check_browser.py`, and
`alembic upgrade/downgrade`. These start or stop services, write to the
database, `data/`, `reports/` or `docs/*.json` evidence, or drive a browser
or Docker stack — they are the user's explicit actions.
`scripts/prune_snapshots.py` without `--delete` is a read-only dry run.

## Ownership of cross-cutting items

| Item | Owner |
|---|---|
| CI OS/runtime matrix (`python` 3.12/3.14, `windows`, `dashboard` Node 26, `docker`) | `testing` |
| Dependabot config, base-image digest pins, GitHub Action SHA pins, workflow permissions | `security` |
| `scripts/prune_snapshots.py`, raw-capture and snapshot disk growth | `database` |
| Platform-dependent dataset IDs (same rows hash differently on Windows vs Linux) | `architecture` (invariant); `testing`/`evidence` apply it |
| Null-AUC rule for ML skill claims | `agents` (guardrail); `evidence` audits claims; `design-system` keeps the dashboard disclaimer |
| Next ADR number | `architecture` — `0001` accepted, `0002` in progress, next new ADR is `0003` |

## Current state (verified 2026-09-29, branch `audit-fixes-2` at `0e88254`)

- All 10 agent files exist in `.claude/agents/`: `agents.md`, `api.md`,
  `architecture.md`, `code-style.md`, `database.md`, `design-system.md`,
  `evidence.md`, `prd.md`, `security.md`, `testing.md`. Frontmatter `name:`
  in each matches this table.
- All 10 owned docs exist: `docs/PRD.md`, `docs/architecture/system.md` +
  `docs/decisions/` (ADR `0001`; `0002` being written), `docs/AGENTS.md`
  (this file), `docs/SECURITY.md`, `docs/CODE_STYLE.md`, `docs/DATABASE.md`,
  `docs/API.md`, `docs/DESIGN_SYSTEM.md`, `docs/TESTING.md`,
  `docs/benchmarks/README.md`.
- Role files were re-derived against the code after `4f4d702` (storage
  `_part_path` and tolerant corrupt-rename, paper 404/409 split and
  `TICK_FAILED` clearing, `_one_of` CHECK builder, native-kernel 422,
  prune guards, dashboard provenance/ARIA/UTC fixes, CI matrix + Windows +
  Node 26 + SHA pins, Dependabot for uv/npm/github-actions, 84 tests).
  Every citation is `path:line` against that tree; re-verify after code moves.
- Found while refreshing: FastAPI's `/docs`, `/redoc` and `/openapi.json` are
  served **without** the bearer token (app-level dependencies don't cover
  them; checked with `TestClient`). Schema only, not forwarded by the proxy.
  Recorded in `api` and `security` as a Low register item.
- `security`'s review trigger list: `axiom/api.py`,
  `apps/dashboard/app/api/[...path]/route.ts`, `axiom/data/storage.py`,
  `axiom/metadata.py`, `alembic/versions/`, `compose.yaml`, `Dockerfile`,
  `apps/dashboard/Dockerfile`, `.github/`.
- `docs/` also holds versioned historical docs that predate this roster and
  no agent owns: `architecture-v0.1.md`, `architecture-v1.md`,
  `methodology.md`, `methodology-v1.md`, `ml-validation.json`,
  `operations.md`, `project-brief.md`, `roadmap.md`, `v0.1-guide.md`,
  `validation-v1.md`, `verification-evidence.json`, `verification.md`, plus
  `benchmarks/` (the ledger `benchmarks/README.md` is `evidence`'s),
  `screenshots/`, and `showcase.json`. Agent docs link to these rather than
  duplicate them.
- `ml-evaluation` (dataset eligibility/split-integrity review) exists on the
  sibling SentinelDAQ project and was not added here: Axiom's ML surface is
  still `walk_forward` plus its `null_auc` reference, covered by `agents`.
  Revisit if it grows (multiple production models, a persisted-model
  feature, or dataset-eligibility rules needing their own owner).
