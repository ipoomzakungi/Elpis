# Implementation Plan: XAU Daily Structural Map Persistence And Sample Run

**Branch**: `019-xau-daily-structural-map-persistence-and-sample-run` | **Date**: 2026-06-04 | **Spec**: [spec.md](./spec.md)
**Input**: Feature specification from `specs/019-xau-daily-structural-map-persistence-and-sample-run/spec.md`

## Summary

Add a research-only persistence layer and sample-run helper for Feature 018 daily structural maps. The implementation writes path-safe local artifacts, preserves null values, supports loading saved map JSON back into the map schema, and returns a small report result for local generation. It does not add signals, alerts, candidate classification, backtests, execution, or live data access.

## Technical Context

**Language/Version**: Python 3.11+ for backend schemas, report store, and sample-run helper; Markdown for Speckit artifacts
**Primary Dependencies**: Existing Pydantic, pytest, FastAPI import surface; no new dependencies
**Storage**: Existing ignored `data/reports/` tree; no new database
**Testing**: Focused pytest unit tests, Feature 018/017 regression tests, backend import check, ruff on touched Python
**Target Platform**: Local research workstation and CI-compatible backend test environment
**Project Type**: Existing FastAPI backend and local research artifacts
**Performance Goals**: Persist one map and wall list in milliseconds for research-sized wall lists
**Constraints**: Research-only, no live/paper/shadow trading, no private credentials, no endpoint replay, no null-to-zero coercion, no v0-forbidden infrastructure, no predictive or profitability claims
**Scale/Scope**: One persisted map directory per map id

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

- **Research-First Architecture**: PASS. Feature persists research evidence only.
- **Language Split**: PASS. Uses Python research/backend code only; no Rust execution component.
- **Frontend Stack**: PASS. No frontend change in this slice.
- **Backend Stack**: PASS. Uses existing Pydantic/local artifact patterns.
- **Data Processing**: PASS. No timestamp-unsafe calculations or backtest.
- **Storage v0**: PASS. Uses local ignored report artifacts.
- **Storage v1+ Avoidance**: PASS. No PostgreSQL or ClickHouse.
- **Event Architecture v0**: PASS. No Kafka, Redpanda, NATS, Kubernetes, or streaming service.
- **Data-Source Principle**: PASS. Source ids and limitations remain explicit.
- **TradingView Principle**: PASS. No TradingView dependency.
- **Reliability Principle**: PASS. Missing context remains visible and blocks signals.
- **Live Trading Principle**: PASS. No live, paper, shadow, broker, wallet, order, or position behavior.

No constitution violations require complexity tracking.

## Project Structure

### Documentation

```text
specs/019-xau-daily-structural-map-persistence-and-sample-run/
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
|   |   `-- xau_daily_structural_map.py
|   `-- xau_daily_structural_map/
|       |-- __init__.py
|       |-- report_store.py
|       `-- sample_run.py
`-- tests/
    `-- unit/
        `-- test_xau_daily_structural_map_store.py
```

**Structure Decision**: Keep persistence-specific models in a dedicated model module and keep the store/helper in a dedicated package. Reuse Feature 018 `XauDailyStructuralMap` unchanged.

## Phase 0 Research Decisions

See [research.md](./research.md).

## Phase 1 Design Decisions

See [data-model.md](./data-model.md), [contracts/api.md](./contracts/api.md), and [quickstart.md](./quickstart.md).

## Persistence Strategy

- `metadata.json` stores compact report metadata and artifact references.
- `map.json` stores the complete `XauDailyStructuralMap`.
- `walls.json` stores only wall rows and preserves null fields.
- `map.md` provides a short local research readout with no signal language.
- `map.json` is the canonical round-trip payload.

## Test Strategy

- Full-context persistence.
- Missing-basis persistence.
- Missing-expected-range persistence.
- Missing-session-open persistence.
- Null preservation for wall OI change and volume.
- Round-trip loading from `map.json`.
- Sample-run helper output.
- Feature 018/017 regression tests, backend import check, and ruff.

## Post-Design Constitution Check

- **Research-First Architecture**: PASS. The output is a saved local research artifact.
- **Language Split**: PASS. No Rust or execution component.
- **Frontend Stack**: PASS. No frontend change.
- **Backend Stack**: PASS. Existing Pydantic/local store patterns are used.
- **Data Processing**: PASS. Nulls and source timing remain explicit.
- **Storage v0**: PASS. Uses ignored local artifacts only.
- **Storage v1+ Avoidance**: PASS. No PostgreSQL or ClickHouse.
- **Event Architecture v0**: PASS. No event infrastructure.
- **Data-Source Principle**: PASS. Source ids and limitations are visible.
- **TradingView Principle**: PASS. No TradingView source-of-truth dependency.
- **Reliability Principle**: PASS. Missing context remains explicit and signal-disabled.
- **Live Trading Principle**: PASS. No execution behavior or live-readiness claim.

No constitution violations require complexity tracking.
