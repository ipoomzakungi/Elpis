# Implementation Plan: XAU Candidate Forward Outcomes

**Branch**: `023-xau-candidate-forward-outcomes` | **Date**: 2026-06-07 | **Spec**: [spec.md](./spec.md)
**Input**: Feature specification from `specs/023-xau-candidate-forward-outcomes/spec.md`

## Summary

Add a research-only backend outcome layer that consumes Feature 021/022 candidate sets and local OHLCV bars, computes forward outcome windows, persists local artifacts, and exposes API/CLI access. The feature measures candidate evidence only; it does not create PnL, execution, alerts, position sizing, or recommendations.

## Technical Context

**Language/Version**: Python 3.11+
**Primary Dependencies**: Existing FastAPI, Pydantic, Polars, pytest, ruff
**Storage**: Local ignored artifacts under `data/reports/xau_candidate_outcomes/`
**Testing**: Focused unit tests for models, calculator, store, API, and CLI plus Feature 021/022 regressions
**Target Platform**: Local research workstation and CI-compatible backend test environment
**Project Type**: Existing FastAPI backend with local research scripts
**Performance Goals**: One fixture candidate set and local candle file completes at local file speed
**Constraints**: Research-only, no fabricated candles, nulls preserved, no PnL or execution behavior, no v0-forbidden infrastructure
**Scale/Scope**: One outcome run over one candidate set and one local price-bar source

## Constitution Check

- **Research-First Architecture**: PASS. The feature attaches evidence labels only.
- **Language Split**: PASS. Python research/backend code only; no Rust execution component.
- **Frontend Stack**: PASS. No frontend change.
- **Backend Stack**: PASS. Uses existing FastAPI and Pydantic patterns.
- **Data Processing**: PASS. Missing and partial OHLC coverage stays explicit.
- **Storage v0**: PASS. Uses ignored local report files.
- **Storage v1+ Avoidance**: PASS. No PostgreSQL or ClickHouse.
- **Event Architecture v0**: PASS. No Kafka, Redpanda, or NATS.
- **Data-Source Principle**: PASS. Local files are supported as research sources.
- **TradingView Principle**: PASS. No TradingView source-of-truth dependency.
- **Reliability Principle**: PASS. Outcomes remain signal-disabled and do not drive execution.
- **Live Trading Principle**: PASS. No live/paper/shadow trading, broker access, orders, alerts, PnL, or position sizing.

No constitution violations require complexity tracking.

## Project Structure

```text
specs/023-xau-candidate-forward-outcomes/
|-- spec.md
|-- plan.md
|-- research.md
|-- data-model.md
|-- contracts/
|   `-- api.md
|-- quickstart.md
|-- checklists/
|   `-- requirements.md
`-- tasks.md

backend/
|-- src/
|   |-- api/routes/xau_candidate_outcomes.py
|   |-- models/xau_candidate_outcome.py
|   `-- xau_candidate_outcomes/
|       |-- __init__.py
|       |-- calculator.py
|       |-- price_series.py
|       |-- report_store.py
|       `-- service.py
|-- scripts/run_xau_candidate_forward_outcomes.py
`-- tests/
    `-- unit/
        |-- test_run_xau_candidate_forward_outcomes_script.py
        |-- test_xau_candidate_outcome_api.py
        |-- test_xau_candidate_outcome_calculator.py
        |-- test_xau_candidate_outcome_models.py
        `-- test_xau_candidate_outcome_store.py
```

**Structure Decision**: Keep outcome schemas in `backend/src/models/`, pure calculation in `backend/src/xau_candidate_outcomes/calculator.py`, local price-bar loading in `price_series.py`, persistence in `report_store.py`, orchestration in `service.py`, and a separate API router.

## Research Decisions

See [research.md](./research.md).

## Design Decisions

See [data-model.md](./data-model.md), [contracts/api.md](./contracts/api.md), and [quickstart.md](./quickstart.md).

## Test Strategy

- Candidate outcome model guardrail tests.
- Short target-before-stop fixture.
- Short stop-before-target fixture.
- Long target fixture with MFE/MAE assertions.
- Breakout-risk continuation fixture.
- Missing and partial price-bar fixtures.
- Candidate artifact to outcome artifact roundtrip.
- API run/latest/read tests.
- CLI help and fixture run tests.
- Feature 021 candidate and Feature 022 workbench regression tests.
- Backend import check and ruff on touched files.

## Post-Design Constitution Check

- **Research-First Architecture**: PASS. Outcomes are evidence annotations only.
- **Live Trading Principle**: PASS. No execution, PnL, or recommendation behavior.
- **Reliability Principle**: PASS. Missing/partial data remains explicit and signal-disabled.
- **Storage v0**: PASS. Only ignored local report artifacts are written.

No constitution violations require complexity tracking.
