# Implementation Plan: XAU Daily Research Workbench

**Branch**: `022-xau-daily-research-workbench` | **Date**: 2026-06-07 | **Spec**: [spec.md](./spec.md)
**Input**: Feature specification from `specs/022-xau-daily-research-workbench/spec.md`

## Summary

Add a backend-only daily research workbench that orchestrates existing XAU components: local bundle loading, structural-map persistence, Feature 021 candidate classification, candidate sidecar persistence, workbench run persistence, and local FastAPI endpoints. The feature stays research-only and signal-disabled.

## Technical Context

**Language/Version**: Python 3.11+
**Primary Dependencies**: Existing FastAPI, Pydantic, Polars, pytest, ruff
**Storage**: Local ignored report artifacts under `data/reports/xau_daily_structural_map/` and `data/reports/xau_daily_workbench/`
**Testing**: Focused pytest service/API tests plus existing map/candidate regression tests
**Target Platform**: Local research workstation and CI-compatible backend test environment
**Project Type**: Existing FastAPI backend
**Performance Goals**: One daily run completes at local artifact speed for fixture-sized inputs
**Constraints**: Research-only, timestamp-safe, no null fabrication, no signal or execution behavior
**Scale/Scope**: One workbench run per request

## Constitution Check

- **Research-First Architecture**: PASS. The workbench produces local research artifacts only.
- **Language Split**: PASS. Python backend only; no Rust execution component.
- **Frontend Stack**: PASS. No frontend change in this slice.
- **Backend Stack**: PASS. Uses existing FastAPI/Pydantic patterns.
- **Data Processing**: PASS. Missing source, basis, traded price, and open context stay explicit.
- **Storage v0**: PASS. Uses local files under ignored `data/reports`.
- **Storage v1+ Avoidance**: PASS. No PostgreSQL or ClickHouse.
- **Event Architecture v0**: PASS. No Kafka/NATS/Redpanda.
- **Data-Source Principle**: PASS. Adds provider interfaces and local implementations.
- **TradingView Principle**: PASS. No TradingView source-of-truth dependency.
- **Reliability Principle**: PASS. Blocked context remains no-trade/no-signal.
- **Live Trading Principle**: PASS. No live/paper/shadow trading, broker access, orders, alerts, PnL, or position sizing.

## Project Structure

```text
specs/022-xau-daily-research-workbench/
|-- spec.md
|-- plan.md
|-- data-model.md
|-- contracts/
|   `-- api.md
|-- quickstart.md
|-- checklists/
|   `-- requirements.md
`-- tasks.md

backend/
|-- src/
|   |-- api/routes/xau_daily_workbench.py
|   |-- models/xau_daily_workbench.py
|   `-- xau_daily_workbench/
|       |-- __init__.py
|       |-- report_store.py
|       `-- service.py
`-- tests/
    |-- contract/test_xau_daily_workbench_api_contracts.py
    `-- unit/test_xau_daily_workbench_service.py
```

## Design Decisions

- Reuse Feature 020A local bundle generation for map creation.
- Reuse Feature 019 structural-map report store for map artifacts.
- Reuse Feature 021 classifier for candidate labels.
- Add a separate workbench report store so daily run metadata can be listed independently.
- Persist candidate sidecars beside `map.json` for map-centered review.
- Return blocked workbench results for missing sources instead of raising tracebacks.
- Defer frontend page changes until the API contract is stable.

## Test Strategy

- Full fixture local bundle workbench run.
- Missing CME bundle source.
- Missing basis.
- Missing session open.
- Candidate sidecar roundtrip.
- API run endpoint.
- API latest empty state.
- API map and candidate roundtrip.
- Signal-disabled invariant.

## Post-Design Constitution Check

- **Research-First Architecture**: PASS.
- **Live Trading Principle**: PASS.
- **Reliability Principle**: PASS.
- **Data-Source Principle**: PASS.

No constitution violations require complexity tracking.
