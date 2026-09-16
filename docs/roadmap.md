# Axiom roadmap

## Current milestone: V1.0 local daily research and paper execution

All six extensions requested after V0.1 are implemented: V0.2 metadata/ingestion, V0.3 event execution/accounting/risk, V0.4 API/dashboard/Docker, V0.5 walk-forward ML, V0.6 measured 342-instrument scaling, and V1.0 optional daily data plus paper operations.

The [README](../README.md) defines the tested scope and run commands. [Validation evidence](validation-v1.md) records concrete checks. [Methodology](methodology-v1.md) explains execution assumptions and limitations.

## Potential future work

- Point-in-time instrument membership and corporate-action-aware total returns.
- Multiple timeframes and tick/quote-level execution models.
- Borrow inventory, financing, margin liquidations and exchange calendars beyond US ETFs.
- Persisted event checkpoints to replace whole-prefix paper replay.
- A durable worker queue for asynchronous multiuser research.
- Public authentication, authorization, quotas and managed backups before external hosting.
- Additional ML datasets and embargo-aware model selection across research campaigns.

Real-money automated execution remains outside the implemented scope. The portfolio replacement is on its `dev` branch; production deployment is a separate operation.
