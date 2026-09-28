# Agent roster

Claude Code subagents defined in `.claude/agents/` for this repo (Axiom). Each
agent's description is its trigger — it says concretely when to use it — and
no two agents claim the same job. See `.claude/agents/agents.md` for the full
ground rules (roster boundaries, tool grants, ML guardrails) this table
summarizes.

Agent files load at session start: a new or edited file in `.claude/agents/`
is not visible to the session that created it and takes effect next session.

| Name | Purpose | Owned doc(s) | Tools |
|---|---|---|---|
| `prd` | Decide whether a feature fits Axiom's V0.2-V1.0 scope; turn ideas into user stories with testable acceptance criteria; record synthetic-vs-provider-sourced (Yahoo) data honesty | `docs/PRD.md` | Read, Grep, Glob, Bash, Write, Edit |
| `architecture` | Decide which layer (data/ingestion, storage, features, backtest/risk/portfolio, ml, api, dashboard) owns a change; write ADRs before adding a data provider, strategy, order type, risk check, or cross-cutting feature | `docs/architecture/system.md`, `docs/decisions/` | Read, Grep, Glob, Bash, Write, Edit |
| `agents` | Own the agent roster itself and the walk-forward ML guardrails (`axiom/ml/walkforward.py`, `axiom/platform.py::run_experiment`); review any new model-based feature or LLM proposal | `docs/AGENTS.md` | Read, Grep, Glob, Bash, Write, Edit |
| `security` | Review diffs/features for vulnerabilities (API auth/exposure, Next.js proxy token handling, snapshot path/hash handling, dependency risk, Docker config); required on every diff touching `axiom/api.py`, the dashboard proxy route, `axiom/data/storage.py`, `axiom/metadata.py`, or `compose.yaml` | `docs/SECURITY.md` | Read, Grep, Glob, Bash, Write, Edit |
| `code-style` | Line-level Python (ruff/mypy-enforced) and TypeScript/Next.js style review; run the actual checkers, not guesswork | `docs/CODE_STYLE.md` | Read, Grep, Glob, Bash, Write, Edit |
| `database` | PostgreSQL/SQLAlchemy/Alembic metadata schema plus the immutable content-addressed Parquet snapshot layout; schema/migration review, stuck-experiment and orphaned-snapshot diagnosis, backup/restore planning | `docs/DATABASE.md` | Read, Grep, Glob, Bash, Write, Edit |
| `api` | The authenticated FastAPI research API (`axiom/api.py`) and the Next.js server-side proxy (`apps/dashboard/app/api/[...path]/route.ts`); endpoint shape, auth, admission gate, paper-account advance flow | `docs/API.md` | Read, Grep, Glob, Bash, Write, Edit |
| `design-system` | Visual language of the Axiom Next.js dashboard (`apps/dashboard/`); tokens/patterns audit, new UI elements, research/paper-trading state treatment | `docs/DESIGN_SYSTEM.md` | Read, Grep, Glob, Bash, Write, Edit |
| `testing` | Run the suite and report exact results; find test-coverage gaps and recommend exact test code (does not edit test files); judge "tests pass" vs. actually verified; the only agent allowed to start/stop the local dev PostgreSQL cluster, and only to run tests | `docs/TESTING.md` | Read, Grep, Glob, Bash, Write, Edit |
| `evidence` | Check a specific claim (README, a doc, `docs/showcase.json`, the portfolio page) against recorded evidence artifacts (`docs/benchmarks/results.json`, `docs/validation-v1.md`, `docs/verification-evidence.json`, `docs/ml-validation.json`); never edits `personalportfolio` or regenerates an artifact itself | `docs/benchmarks/README.md` | Read, Grep, Glob, Bash, Write, Edit |

## Current state (verified 2026-09-28)

- All 10 agent files exist in `.claude/agents/`: `agents.md`, `api.md`,
  `architecture.md`, `code-style.md`, `database.md`, `design-system.md`,
  `evidence.md`, `prd.md`, `security.md`, `testing.md`. Frontmatter `name:`
  in each matches this table.
- All 8 of the original agents' owned docs now exist and have each been
  through at least one real audit pass: `docs/PRD.md`,
  `docs/architecture/system.md` + `docs/decisions/0001-...md`,
  `docs/SECURITY.md`, `docs/CODE_STYLE.md`, `docs/DATABASE.md`,
  `docs/API.md`, `docs/DESIGN_SYSTEM.md`, `docs/AGENTS.md` (this file).
- `testing` and `evidence` were added 2026-09-28, after the first full
  roster audit surfaced work nobody owned: closing five test-coverage gaps
  (paper-account alerting, walk-forward ML models, three risk-engine
  circuit breakers, provenance on both the V0.1 and V0.2+ paths, and a new
  Docker CI job) was done ad hoc by the orchestrating session rather than
  by an owning agent, and no agent checked `docs/showcase.json`/the
  portfolio page against the evidence artifacts. Their owned docs
  (`docs/TESTING.md`, `docs/benchmarks/README.md`) do not exist yet —
  created on first invocation, per the pattern every other agent follows.
- `docs/` already holds versioned historical docs that predate this roster
  and are not owned by any agent: `architecture-v0.1.md`, `architecture-v1.md`,
  `methodology.md`, `methodology-v1.md`, `ml-validation.json`, `operations.md`,
  `project-brief.md`, `roadmap.md`, `v0.1-guide.md`, `validation-v1.md`,
  `verification-evidence.json`, `verification.md`, plus `benchmarks/`
  (now partly owned by `evidence`'s `benchmarks/README.md`), `screenshots/`,
  and `showcase.json`. New agent docs link to these rather than duplicate
  them.
- `ml-evaluation` (dataset eligibility/split-integrity review, distinct
  from `agents`' own ML guardrails) exists on the sibling SentinelDAQ
  project and was considered but not added here — Axiom's ML surface is
  currently one function (`walk_forward`), not yet complex enough to
  justify a role separate from what `agents` already covers. Revisit if
  the ML surface grows (multiple models in production, a persisted-model
  feature, or dataset-eligibility rules that need their own owner).
