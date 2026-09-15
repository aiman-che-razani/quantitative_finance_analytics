# V0.1 operations

## Environment

Use Python 3.12+. `uv sync --frozen --extra dev --extra yahoo` reproduces the
locked environment. On this Windows machine use `.venv/Scripts/python.exe`.
The system `python` command points to 3.9 and is not the Axiom interpreter.

## Commands

Global `--data` and `--output` flags precede subcommands.

- `axiom universe`: canonical initial metadata (unknown sector/industry/listing
  dates remain null; XNYS is a daily-session proxy, not the listing exchange).
- `axiom demo`: deterministic synthetic ten-symbol pipeline; optional `--seed`,
  `--start`, `--end` and `--symbols`.
- `axiom ingest --provider yahoo|csv|synthetic`: raw capture, validation and snapshot.
  CSV requires `--csv-dir`, containing one `<SYMBOL>.csv` per selected instrument.
- `axiom research --dataset <hash> --strategy ema_trend|rsi_reversion|combined|buy_hold`:
  replay an immutable snapshot; optional `--config configs/default.json`.

For an initial Yahoo import, use 2020-01-01 through 2025-01-01 exclusive.
Downloaded prices are ignored by Git. Repeat imports create raw audit captures
but reuse the validated observation snapshot when canonical contents are identical.
No incremental merge is performed yet; each requested range is a complete snapshot.

## CSV schema

Required header:

```csv
instrument,timestamp,timeframe,open,high,low,close,volume,source,ingested_at,price_basis
```

Timestamp is a UTC daily session-date label (`2020-01-02` or
`2020-01-02T00:00:00+00:00`). `ingested_at` must include a timezone; values are
normalized to UTC. `timeframe` must be `1d`. All OHLC prices are finite and
positive; volume is finite and nonnegative. `source` must be explicit.
`price_basis` is `raw_price` or `synthetic`; a synthetic source name begins with
`synthetic`. Do not label generated data as a real provider. Corporate-action
screening for manually supplied CSV is the operator's responsibility: V0.1
cannot reconstruct absent action records. Dates outside the requested interval
are rejected; supply an exact-range CSV instead of assuming implicit filtering.

## Outputs and recovery

- `data/raw/<symbol>/<capture-id>.parquet`: original adapter output.
- `data/quality/<report-id>.json`: counts, rejected row reasons, missing sessions,
  warnings, requested interval, raw paths and eligibility.
- `data/validated/<sha256>/...`: versioned partitioned data plus manifest.
- `reports/<experiment-id>/report.json`: completed research result and assumptions.
- `reports/<experiment-id>/<symbol>-<strategy|buy_and_hold>-equity.csv`: daily state.
- `reports/<experiment-id>/<symbol>-<strategy|buy_and_hold>-ledger.json`: fills/trades.
- `reports/<experiment-id>/features.parquet`: exact feature matrix used.

Rejected/missing-session inputs do not publish a research-eligible snapshot.
Warnings such as zero volume or a >50% price jump require investigation even if
structurally valid. Quality checks do not establish provider accuracy.
Only a final manifest marks a completed snapshot. Interrupted staging directories
are not read. Only a final `report.json` marks a completed research result.
Retain failures for diagnosis; no automatic recursive cleanup deletes evidence.
Single writer per data directory in V0.1. Snapshot reader verifies file and
canonical hashes. Preserve the snapshot and config to reproduce numeric outputs;
UUIDs, ingestion times and measured durations are intentionally different per run.

## Verification procedure

1. Run all four checks in the README. Expected: tests, lint, format and mypy pass.
2. Run `demo`; expect ten instrument results with `price_basis=["synthetic"]`.
3. Repeat using identical seed/dates. Expect identical dataset ID and metrics,
   but a new experiment ID.
4. Read a fill ledger. Its signal timestamp must precede execution timestamp.
5. Confirm equity CSV satisfies cash + units * close = equity and the report's
   realized + unrealized P&L equals final equity minus initial capital.
6. Run the optional Yahoo import. Verify every symbol has all expected sessions.
   A network error is a failed historical check, never a synthetic success.
7. Research that dataset ID. Inspect both wins and underperformance against the
   same-window benchmark. Do not optimize against this inspected window and later
   call it an untouched test set.

Common failures: wrong Python version, missing Yahoo extra, provider rate limits,
corporate-action rejection, wrong CSV timezone, holiday rows, conflicting duplicate
prices, incomplete requested interval, insufficient feature warm-up and tampered
snapshot files. Preserve the error and quality report before changing data.
