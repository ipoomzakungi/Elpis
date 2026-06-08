# Implementation Plan: XAU Walk-Forward Range Desk Research Runner

**Branch**: `codex/xau-vol-oi-research-pipeline` | **Date**: 2026-06-08 | **Spec**: [spec.md](./spec.md)

## Summary

Add a backend research runner that creates scheduled XAU Range Desk snapshots, resolves native CME SD from saved QuikStrike range-band sidecars, maps futures levels to traded levels with Diff/Basis, generates research-only order/recovery templates, optionally simulates local OHLCV outcomes, persists reports, and exposes API/CLI access.

## Technical Context

**Language/Version**: Python 3.11+
**Dependencies**: Existing FastAPI, Pydantic, pytest, ruff; optional `yfinance`
**Storage**: Local ignored reports under `backend/data/reports/xau_walk_forward`
**Testing**: Focused unit tests for schedule, SD source, order planner, simulation, persistence, API, and CLI
**Constraints**: Research-only, no live/paper trading, no alerts, no broker/order integration, no real PnL

## Constitution Check

- Research-first: PASS. Records are evidence/planning artifacts only.
- Backend stack: PASS. Python/FastAPI/Pydantic only.
- Storage v0: PASS. Local JSON/Markdown artifacts only.
- Data-source principle: PASS. Native CME SD is preferred; Yahoo is labeled fallback.
- Live trading principle: PASS. `signal_allowed=false` everywhere.

## Project Structure

```text
backend/src/models/xau_walk_forward_research.py
backend/src/xau_walk_forward/
|-- __init__.py
|-- order_planner.py
|-- price_provider.py
|-- range_desk_builder.py
|-- report_store.py
|-- schedule.py
|-- sd_source.py
|-- service.py
`-- simulated_order_engine.py
backend/src/api/routes/xau_walk_forward.py
backend/scripts/run_xau_walk_forward_research.py
backend/tests/unit/test_xau_walk_forward_*.py
```

## Post-Design Constitution Check

PASS. The slice is local research automation only. It does not add execution, order placement, alerts, broker access, position management, or strategy claims.
