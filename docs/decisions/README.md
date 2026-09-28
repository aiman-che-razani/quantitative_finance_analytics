# Architecture decision records

Format: status / decision / consequences. New ADRs are numbered sequentially
and are never edited to reverse a decision — a changed decision gets a new
ADR that supersedes the old one.

| ADR | Status | Decision |
| --- | --- | --- |
| [0001](0001-keep-v0.1-and-v0.2-coexisting.md) | Accepted | Keep the V0.1 CLI/engine (`axiom/cli.py` → `axiom/research.py` → `axiom/backtest/engine.py`) and the V0.2+ PostgreSQL-backed platform as two coexisting, independently runnable code paths rather than migrating or removing V0.1. |
