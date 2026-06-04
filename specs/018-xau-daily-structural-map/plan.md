# Implementation Plan: XAU Daily Structural Map

**Branch**: `018-xau-daily-structural-map` | **Date**: 2026-06-04 | **Spec**: [spec.md](./spec.md)
**Input**: Feature specification from `specs/018-xau-daily-structural-map/spec.md`

## Summary

Add a research-only daily structural map layer that combines Feature 017 expected-range snapshots, existing basis-state behavior, existing XAU Vol-OI walls, optional session-open context, readiness state, and forward-journal-compatible limitations. This feature does not create trading signals, alerts, execution, strategy classifiers, or backtests.

## Technical Context

**Language/Version**: Python 3.11+ for backend schemas and helper logic; Markdown for Speckit artifacts
**Primary Dependencies**: Existing Pydantic, pytest, FastAPI import surface; no new dependencies
**Storage**: No new persistence in this slice
**Testing**: Focused pytest unit tests, Feature 017 regression tests, inventory tests, backend import check, ruff on touched Python
**Target Platform**: Local research workstation and CI-compatible backend test environment
**Project Type**: Existing FastAPI backend and research scripts
**Performance Goals**: Constant-time per wall; typical daily maps should build in milliseconds for local research-sized wall lists
**Constraints**: Research-only, no live/paper/shadow trading, no private credentials, no endpoint replay, no null-to-zero coercion, no v0-forbidden infrastructure, no predictive or profitability claims
**Scale/Scope**: One map per session/expiration context with a bounded wall list from existing XAU Vol-OI output

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

- **Research-First Architecture**: PASS. The feature creates a map and readiness payload only.
- **Language Split**: PASS. Uses Python research/backend models only; no Rust execution component.
- **Frontend Stack**: PASS. No frontend change in this slice.
- **Backend Stack**: PASS. Extends existing Pydantic schemas and helper modules.
- **Data Processing**: PASS. No timestamp-unsafe feature calculation or backtest.
- **Storage v0**: PASS. No new database or generated data commit.
- **Storage v1+ Avoidance**: PASS. No PostgreSQL or ClickHouse.
- **Event Architecture v0**: PASS. No Kafka, Redpanda, NATS, Kubernetes, or streaming service.
- **Data-Source Principle**: PASS. Source limitations remain explicit.
- **TradingView Principle**: PASS. No TradingView dependency.
- **Reliability Principle**: PASS. Missing basis, range, session open, or walls reduce readiness and block signals.
- **Live Trading Principle**: PASS. No live, paper, shadow, broker, wallet, order, or position behavior.

No constitution violations require complexity tracking.

## Project Structure

### Documentation

```text
specs/018-xau-daily-structural-map/
|-- spec.md
|-- plan.md
|-- research.md
|-- data-model.md
|-- quickstart.md
|-- contracts/
|   `-- api.md
|-- checklists/
|   `-- requirements.md
`-- tasks.md
```

### Source Code

```text
backend/
|-- src/
|   |-- models/
|   |   `-- xau.py
|   `-- xau_quikstrike_fusion/
|       `-- daily_structural_map.py
`-- tests/
    `-- unit/
        `-- test_xau_daily_structural_map.py
```

**Structure Decision**: Use additive XAU schemas in `backend/src/models/xau.py` and a builder helper in `backend/src/xau_quikstrike_fusion/` because the map consumes fusion basis behavior and Feature 017 expected-range snapshots without changing the wall engine.

## Phase 0 Research Decisions

See [research.md](./research.md).

## Phase 1 Design Decisions

See [data-model.md](./data-model.md), [contracts/api.md](./contracts/api.md), and [quickstart.md](./quickstart.md).

## Map Strategy

- Expected range comes from Feature 017 snapshots.
- Basis mapping uses `spot_equivalent_level = futures_strike - basis` only when basis is available.
- Wall scores and freshness remain sourced from existing XAU Vol-OI wall rows.
- Session-open annotations are optional and affect readiness only.
- `signal_allowed` remains false even for full-context maps.

## Test Strategy

- Full-context map creation.
- Missing-basis preservation.
- Missing-expected-range preservation.
- Missing-session-open partial readiness.
- Blank Matrix cell null preservation.
- Feature 017 expected-range snapshot integration.
- Feature 017 regression tests and inventory tests.
- Backend import check and ruff on touched Python.

## Post-Design Constitution Check

- **Research-First Architecture**: PASS. The output is a daily research map.
- **Language Split**: PASS. No Rust or execution component.
- **Frontend Stack**: PASS. No frontend change.
- **Backend Stack**: PASS. Existing Pydantic model patterns are used.
- **Data Processing**: PASS. Nulls and source timing remain explicit.
- **Storage v0**: PASS. No new persistent database.
- **Storage v1+ Avoidance**: PASS. No PostgreSQL or ClickHouse.
- **Event Architecture v0**: PASS. No event infrastructure.
- **Data-Source Principle**: PASS. Source limitations are visible.
- **TradingView Principle**: PASS. No TradingView source-of-truth dependency.
- **Reliability Principle**: PASS. Missing basis/range/open context blocks signal use.
- **Live Trading Principle**: PASS. No execution behavior or live-readiness claim.

No constitution violations require complexity tracking.
