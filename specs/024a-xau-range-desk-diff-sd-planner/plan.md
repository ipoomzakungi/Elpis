# Implementation Plan: XAU Range Desk / Diff-SD Planner

**Branch**: `codex/xau-vol-oi-research-pipeline` | **Date**: 2026-06-07 | **Spec**: [spec.md](./spec.md)
**Input**: Feature specification from `specs/024a-xau-range-desk-diff-sd-planner/spec.md`

## Summary

Add a research-only backend Range Desk calculator that maps CME futures-side SD and OI levels into traded XAU/GO chart levels using future-vs-traded diff. The slice exposes one local API endpoint and keeps all outputs signal-disabled.

## Technical Context

**Language/Version**: Python 3.11+
**Primary Dependencies**: Existing FastAPI, Pydantic, pytest, ruff
**Storage**: None for this slice
**Testing**: Focused unit tests for planner and API route plus adjacent Feature 021/022/023 regressions
**Target Platform**: Local research workstation and CI-compatible backend test environment
**Project Type**: Existing FastAPI backend
**Performance Goals**: One plan request completes at local calculation speed
**Constraints**: Research-only, explicit missing inputs, no PnL/execution/alerts/position sizing, no v0-forbidden infrastructure
**Scale/Scope**: One request over supplied SD levels and optional OI walls

## Constitution Check

- **Research-First Architecture**: PASS. The feature emits planning context only.
- **Language Split**: PASS. Python backend code only; no Rust execution component.
- **Frontend Stack**: PASS. No frontend change.
- **Backend Stack**: PASS. Uses existing FastAPI and Pydantic patterns.
- **Data Processing**: PASS. Inputs are explicit and missing context is preserved.
- **Storage v0**: PASS. No new storage.
- **Storage v1+ Avoidance**: PASS. No PostgreSQL or ClickHouse.
- **Event Architecture v0**: PASS. No Kafka, Redpanda, or NATS.
- **Data-Source Principle**: PASS. Manual/source-supplied research inputs are explicit.
- **TradingView Principle**: PASS. No TradingView source-of-truth dependency.
- **Reliability Principle**: PASS. Plans remain signal-disabled.
- **Live Trading Principle**: PASS. No live/paper/shadow trading, broker access, orders, alerts, PnL, or position sizing.

No constitution violations require complexity tracking.

## Project Structure

```text
specs/024a-xau-range-desk-diff-sd-planner/
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
|   |-- api/routes/xau_range_desk.py
|   |-- models/xau_range_desk.py
|   `-- xau_range_desk/
|       |-- __init__.py
|       `-- planner.py
`-- tests/
    `-- unit/
        |-- test_xau_range_desk_api.py
        `-- test_xau_range_desk_planner.py
```

## Design Decisions

See [data-model.md](./data-model.md), [contracts/api.md](./contracts/api.md), and [quickstart.md](./quickstart.md).

## Test Strategy

- Diff mapping fixture.
- Full SD/wall zone and target-plan fixture.
- Missing SD context fixture.
- API route fixture.
- Feature 021, 022, and 023 adjacent regression tests.
- Backend import check and ruff on touched Python files.

## Post-Design Constitution Check

- **Research-First Architecture**: PASS. Range Desk output is planning context only.
- **Live Trading Principle**: PASS. No execution, PnL, alerting, or recommendation behavior.
- **Reliability Principle**: PASS. Missing context remains explicit and signal-disabled.
