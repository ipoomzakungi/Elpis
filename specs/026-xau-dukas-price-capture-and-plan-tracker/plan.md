# Implementation Plan: XAU Dukascopy Price Capture And Plan Tracker

**Branch**: `codex/xau-vol-oi-research-pipeline` | **Date**: 2026-06-08 | **Spec**: [spec.md](./spec.md)

## Summary

Add a backend research-only layer that imports or captures XAUUSD bars, extracts 10:10 and 18:10 traded reference prices, reuses Feature 025 native-SD plan generation, tracks simulated plan status/PnL/drawdown from local bars, persists local reports, and exposes API/CLI access.

## Technical Context

**Language/Version**: Python 3.11+
**Dependencies**: Existing FastAPI, Pydantic, pytest, ruff
**Storage**: Local ignored reports under `backend/data/reports/xau_plan_tracker`
**Testing**: Focused unit tests for bar parsing, CLI failure, reference extraction, order tracking, service, API, and CLI help/fixture run
**Constraints**: Research-only, local file/CLI price data, no broker execution, no real PnL, no alerts

## Constitution Check

- Research-first: PASS. The feature creates simulated evidence records only.
- Backend stack: PASS. Python/FastAPI/Pydantic only.
- Storage v0: PASS. Local JSON/Markdown artifacts only.
- Data-source principle: PASS. CME remains futures/options source; Dukascopy is traded-side research price only.
- Reliability: PASS. Missing bars and missing references remain unavailable.
- Live trading principle: PASS. No live/paper/shadow trading, broker integration, alerts, or order placement.

## Project Structure

```text
backend/src/models/xau_price_plan_tracker.py
backend/src/xau_price_plan_tracker/
|-- __init__.py
|-- dukas_cli.py
|-- order_tracker.py
|-- reference_price.py
|-- report_store.py
`-- service.py
backend/src/api/routes/xau_plan_tracker.py
backend/scripts/run_xau_plan_tracker.py
backend/tests/unit/test_xau_plan_tracker_*.py
```

## Design Decisions

- Reuse Feature 025 `resolve_sd_snapshot` and `generate_research_order_plans`.
- Keep Dukascopy CLI command templates generic and caller-provided.
- Store simulated PnL in points only and label it as research simulation.
- Default ambiguous same-candle TP/SL behavior is conservative stop-first.

## Post-Design Constitution Check

PASS. This feature does not add execution, order placement, alerts, broker access, position management, or strategy claims.
