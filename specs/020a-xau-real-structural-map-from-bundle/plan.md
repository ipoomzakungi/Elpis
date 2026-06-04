# Implementation Plan: XAU Real Structural Map From Bundle

**Branch**: `020a-xau-real-structural-map-from-bundle` | **Date**: 2026-06-04 | **Spec**: [spec.md](./spec.md)
**Input**: Feature specification from `specs/020a-xau-real-structural-map-from-bundle/spec.md`

## Summary

Add a research-only local bundle adapter that reads saved XAU Vol-OI report JSON and wall artifacts, normalizes them into Feature 018 map inputs, and persists the result through the Feature 019 report store. The adapter preserves missing basis, unavailable expected range, range-label-only context, null wall fields, and source limitations. It does not add outcomes, signals, alerts, execution, PnL, ML, or backtests.

## Technical Context

**Language/Version**: Python 3.11+ for backend helper and tests; Markdown for Speckit artifacts
**Primary Dependencies**: Existing Pydantic, Polars, pytest, FastAPI import surface; no new dependencies
**Storage**: Existing ignored `data/reports/` tree through Feature 019 report store
**Testing**: Focused pytest unit tests, Feature 017/018/019 regression tests, backend import check, ruff on touched files
**Target Platform**: Local research workstation and CI-compatible backend test environment
**Project Type**: Existing FastAPI backend and local research artifacts
**Performance Goals**: Load one report JSON and a research-sized wall table in milliseconds
**Constraints**: Research-only, no null-to-zero coercion, no fake basis, no fake expected range, no v0-forbidden infrastructure, no live or paper trading
**Scale/Scope**: One persisted map per local bundle invocation

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

- **Research-First Architecture**: PASS. The feature creates saved research evidence only.
- **Language Split**: PASS. Uses Python research/backend code only; no Rust execution component.
- **Frontend Stack**: PASS. No frontend change in this slice.
- **Backend Stack**: PASS. Uses existing Pydantic/local artifact patterns.
- **Data Processing**: PASS. Nulls and source timing remain explicit.
- **Storage v0**: PASS. Uses local ignored report artifacts only.
- **Storage v1+ Avoidance**: PASS. No PostgreSQL or ClickHouse.
- **Event Architecture v0**: PASS. No Kafka, Redpanda, NATS, Kubernetes, or streaming service.
- **Data-Source Principle**: PASS. Local bundle source limitations remain visible.
- **TradingView Principle**: PASS. No TradingView dependency.
- **Reliability Principle**: PASS. Missing range, basis, walls, or session open reduce readiness and block signals.
- **Live Trading Principle**: PASS. No live, paper, shadow, broker, wallet, order, or position behavior.

No constitution violations require complexity tracking.

## Project Structure

### Documentation

```text
specs/020a-xau-real-structural-map-from-bundle/
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
|   `-- xau_daily_structural_map/
|       `-- bundle_adapter.py
`-- tests/
    `-- unit/
        `-- test_xau_daily_structural_map_bundle_adapter.py
```

**Structure Decision**: Keep bundle loading in `backend/src/xau_daily_structural_map/` because it is a persistence-oriented adapter that feeds the existing structural-map builder and store.

## Phase 0 Research Decisions

See [research.md](./research.md).

## Phase 1 Design Decisions

See [data-model.md](./data-model.md), [contracts/api.md](./contracts/api.md), and [quickstart.md](./quickstart.md).

## Adapter Strategy

- Load report JSON from a direct payload or composed wrapper.
- Load parquet walls when present; otherwise use embedded JSON wall rows.
- Normalize wall rows into `XauOiWall` and separate nullable OI-change/volume maps.
- Resolve expected range from Feature 017 snapshot fields when available; build an unavailable Feature 017 snapshot when only label/context is present.
- Resolve basis by manual basis first, then computed basis from GC and traded reference prices, otherwise unavailable.
- Add a local-bundle limitation and persist through `XauDailyStructuralMapReportStore`.

## Test Strategy

- Full-context bundle generation.
- Missing-basis preservation.
- Missing-expected-range preservation.
- Range-label-only no-fabrication.
- Null OI-change/volume preservation.
- Parquet fallback and no-wall persistence.
- Existing Feature 017/018/019 tests.
- Backend import check and ruff.

## Post-Design Constitution Check

- **Research-First Architecture**: PASS. The output is a saved map, not a trading decision.
- **Language Split**: PASS. No Rust or execution component.
- **Frontend Stack**: PASS. No frontend change.
- **Backend Stack**: PASS. Existing model/store patterns are used.
- **Data Processing**: PASS. Nulls and source limitations remain explicit.
- **Storage v0**: PASS. Existing local report paths only.
- **Storage v1+ Avoidance**: PASS. No PostgreSQL or ClickHouse.
- **Event Architecture v0**: PASS. No event infrastructure.
- **Data-Source Principle**: PASS. Local imported data limitations are visible.
- **TradingView Principle**: PASS. No TradingView source-of-truth dependency.
- **Reliability Principle**: PASS. Missing context blocks signal use and lowers readiness.
- **Live Trading Principle**: PASS. No execution behavior or live-readiness claim.

No constitution violations require complexity tracking.
