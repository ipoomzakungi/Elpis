# Implementation Plan: XAU SD OI Mean Reversion Candidate Research

**Branch**: `021-xau-sd-oi-mean-reversion-candidate-research` | **Date**: 2026-06-07 | **Spec**: [spec.md](./spec.md)
**Input**: Feature specification from `specs/021-xau-sd-oi-mean-reversion-candidate-research/spec.md`

## Summary

Add a research-only candidate classifier that consumes an existing `XauDailyStructuralMap`, one observed traded price, and caller-supplied confirmation/IV/flow/OI-wall context. It returns strict Pydantic candidate models with target and invalidation reference levels, preserves missing data and null wall fields, derives 3.5SD only from valid 1SD bands with a limitation, and keeps `signal_allowed=false`.

## Technical Context

**Language/Version**: Python 3.11+ for backend models and tests; Markdown for Speckit artifacts
**Primary Dependencies**: Existing Pydantic and pytest; no new dependencies
**Storage**: None in this slice; consumes in-memory or loaded structural maps
**Testing**: Focused pytest unit tests, Feature 018/017 regression tests, inventory regression test, backend import check, ruff on touched files
**Target Platform**: Local research workstation and CI-compatible backend test environment
**Project Type**: Existing FastAPI backend and local research modules
**Performance Goals**: Constant-time classification for one map and one observed price
**Constraints**: Research-only, no null-to-zero coercion, no hard-coded 2SD entry, no direction inferred from OI alone, no v0-forbidden infrastructure, no live or paper trading
**Scale/Scope**: One candidate set per map/timestamp invocation

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

- **Research-First Architecture**: PASS. The feature produces research candidate labels only.
- **Language Split**: PASS. Python research/backend code only; no Rust execution component.
- **Frontend Stack**: PASS. No frontend change.
- **Backend Stack**: PASS. Uses existing Pydantic model patterns.
- **Data Processing**: PASS. Timestamp, missing data, and nulls remain explicit.
- **Storage v0**: PASS. No new storage is added.
- **Storage v1+ Avoidance**: PASS. No PostgreSQL or ClickHouse.
- **Event Architecture v0**: PASS. No event infrastructure.
- **Data-Source Principle**: PASS. Consumes the existing data-provider-derived structural map.
- **TradingView Principle**: PASS. No TradingView source-of-truth dependency.
- **Reliability Principle**: PASS. Missing context and breakout risk block reversion candidate labels.
- **Live Trading Principle**: PASS. No live, paper, shadow, broker, wallet, order, alert, PnL, or position behavior.

No constitution violations require complexity tracking.

## Project Structure

### Documentation

```text
specs/021-xau-sd-oi-mean-reversion-candidate-research/
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
|   |   `-- xau_sd_oi_candidate.py
|   `-- xau_sd_oi_candidate/
|       |-- __init__.py
|       `-- classifier.py
`-- tests/
    `-- unit/
        `-- test_xau_sd_oi_mean_reversion_candidate.py
```

**Structure Decision**: Keep candidate schemas in `backend/src/models/` and the classifier in a new `backend/src/xau_sd_oi_candidate/` package so the existing structural-map builder and report store remain unchanged.

## Phase 0 Research Decisions

See [research.md](./research.md).

## Phase 1 Design Decisions

See [data-model.md](./data-model.md), [contracts/api.md](./contracts/api.md), and [quickstart.md](./quickstart.md).

## Classifier Strategy

- Validate required context before classifying: basis, numeric SD bands, traded price, and session open.
- Derive stretch zone from traded price and numeric SD bands.
- Derive 3.5SD from the 1SD center/distance when native 3.5SD is absent.
- Select nearest mapped wall by `spot_equivalent_level` distance to traded price.
- Treat IV expansion plus flow-through-wall plus acceptance as breakout risk.
- Require rejection or close-back-inside confirmation before assigning a reversion candidate.
- Emit no-trade monitor state inside +/-2SD.
- Always attach research-only no-signal reasons.

## Test Strategy

- Missing basis.
- Upper 2SD-3SD rejection candidate.
- Lower 2SD-3SD rejection candidate.
- Breakout risk from IV expansion plus flow-through-wall plus acceptance.
- Inside +/-2SD no-trade monitor.
- Null wall OI-change and volume preservation.
- Derived 3.5SD limitation.
- Existing Feature 018/017 and inventory regression tests.
- Backend import check and ruff.

## Post-Design Constitution Check

- **Research-First Architecture**: PASS. Candidate labels are not profitability evidence or instructions.
- **Language Split**: PASS. No Rust or execution component.
- **Frontend Stack**: PASS. No frontend change.
- **Backend Stack**: PASS. Existing backend conventions are used.
- **Data Processing**: PASS. Missing and null context is not fabricated.
- **Storage v0**: PASS. No new persistence.
- **Event Architecture v0**: PASS. No event infrastructure.
- **Reliability Principle**: PASS. Candidate labels require confirmation context and stay signal-disabled.
- **Live Trading Principle**: PASS. No execution behavior or live-readiness claim.

No constitution violations require complexity tracking.
