# Implementation Plan: XAU Data Capability Audit

**Branch**: `codex/xau-vol-oi-research-pipeline` | **Date**: 2026-06-07 | **Spec**: [spec.md](./spec.md)
**Input**: Feature specification from `specs/024b-xau-data-capability-audit/spec.md`

## Summary

Add a research-only backend audit that reads saved local CME/QuikStrike and XAU artifacts, reports which data fields are source-backed, marks weak or missing fields explicitly, and exposes one local API endpoint. The slice does not fetch fresh data, calculate signals, calculate PnL, or execute trades.

## Technical Context

**Language/Version**: Python 3.11+
**Primary Dependencies**: Existing FastAPI, Pydantic, pytest, ruff
**Storage**: Existing local ignored report artifacts under the configured reports directory
**Testing**: Focused unit tests for audit service and API route plus adjacent XAU regressions
**Target Platform**: Local research workstation and CI-compatible backend test environment
**Project Type**: Existing FastAPI backend
**Performance Goals**: A default audit over latest local reports completes at local file-read speed
**Constraints**: Research-only, read-only audit, no fresh external fetch, no fabricated unavailable fields, no v0-forbidden infrastructure
**Scale/Scope**: Latest or selected saved Vol2Vol, Matrix, Fusion, and XAU Vol-OI reports

## Constitution Check

- **Research-First Architecture**: PASS. The feature reports data readiness only.
- **Language Split**: PASS. Python backend code only; no Rust execution component.
- **Frontend Stack**: PASS. No frontend change.
- **Backend Stack**: PASS. Uses existing FastAPI and Pydantic patterns.
- **Data Processing**: PASS. Source-backed evidence is reported and missing context is preserved.
- **Storage v0**: PASS. Reuses local file artifacts; no new database.
- **Storage v1+ Avoidance**: PASS. No PostgreSQL or ClickHouse.
- **Event Architecture v0**: PASS. No Kafka, Redpanda, or NATS.
- **Data-Source Principle**: PASS. Source limitations remain explicit.
- **TradingView Principle**: PASS. No TradingView source-of-truth dependency.
- **Reliability Principle**: PASS. Unavailable fields are not inferred.
- **Live Trading Principle**: PASS. No live/paper/shadow trading, broker access, orders, alerts, PnL, or position sizing.

No constitution violations require complexity tracking.

## Project Structure

```text
specs/024b-xau-data-capability-audit/
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
|   |-- api/routes/xau_data_capability_audit.py
|   |-- models/xau_data_capability_audit.py
|   `-- xau_data_capability_audit/
|       |-- __init__.py
|       `-- service.py
`-- tests/
    `-- unit/
        `-- test_xau_data_capability_audit.py
```

## Design Decisions

See [data-model.md](./data-model.md), [contracts/api.md](./contracts/api.md), and [quickstart.md](./quickstart.md).

## Test Strategy

- Fixture audit over Vol2Vol and Matrix reports.
- Fixture audit with XAU Vol-OI source rows containing delta and gamma.
- API route fixture with dependency override.
- Adjacent XAU Range Desk, fusion loader, and candidate/outcome regressions.
- Backend import check and ruff on touched Python files.

## Post-Design Constitution Check

- **Research-First Architecture**: PASS. Audit output is data readiness only.
- **Live Trading Principle**: PASS. No execution, PnL, alerting, or recommendation behavior.
- **Reliability Principle**: PASS. Missing or weak source data remains explicit and signal-disabled.
