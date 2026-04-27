# Implementation Plan: Validation and Research Hardening

**Branch**: `004-validation-and-research-hardening` | **Date**: 2026-04-27 | **Spec**: [spec.md](spec.md)  
**Input**: Feature specification from `/specs/004-validation-and-research-hardening/spec.md`

## Summary

Harden the completed Elpis backtest/reporting MVP before any paper, shadow, or live trading work. The implementation keeps the existing research-only architecture and fixes misleading accounting/reporting surfaces: buy-and-hold becomes a capital-based passive baseline, no-leverage exposure is enforced economically, equity curves can show mark-to-market total equity, headline metrics are separated by independent strategy/baseline mode, and reports gain stress, sensitivity, walk-forward, regime coverage, trade concentration, real-data readiness, and CI guardrail validation.

This feature builds on completed features `001-oi-regime-lab`, `002-research-data-provider`, and `003-backtest-reporting-engine`. It does not redesign the app, add execution systems, or introduce forbidden v0 infrastructure.

## Technical Context

**Language/Version**: Python 3.11+, TypeScript 5.x  
**Primary Dependencies**: FastAPI, Pydantic/Pydantic Settings, Polars, DuckDB, Parquet/PyArrow, httpx, Next.js, Tailwind CSS, lightweight-charts/Recharts  
**Storage**: Existing local `data/processed` inputs and `data/reports` generated JSON/Markdown/Parquet artifacts; no server database  
**Testing**: pytest, pytest-asyncio, backend unit/integration/contract tests, frontend `npm run build`, GitHub Actions validation workflow  
**Target Platform**: Local development and CI on Windows/macOS/Linux-compatible commands, with GitHub-hosted CI runners for automated checks  
**Project Type**: Web application with FastAPI backend and Next.js dashboard  
**Performance Goals**: Typical BTCUSDT 15m validation report completes locally within 60 seconds for bounded grids; report API/dashboard loads typical validation output within 5 seconds  
**Constraints**: Research-only; no live trading, private API keys, broker integration, real order execution, wallet/private-key handling, Rust, ClickHouse, PostgreSQL, Kafka/Redpanda/NATS, Kubernetes, ML model training, paper trading, or shadow trading; do not redesign provider/feature/dashboard flows; generated artifacts stay out of git  
**Scale/Scope**: v0 local single-user research hardening for existing processed feature data, first real-data path BTCUSDT 15m, bounded cost profiles and parameter grids, chronological validation splits only

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Principle | Status | Notes |
|-----------|--------|-------|
| I. Research-First Architecture | PASS | The feature improves historical validation and reporting trustworthiness only; no execution workflow is added. |
| II. Language Split | PASS | Python remains the research/backtest language and TypeScript remains dashboard language; no Rust execution component is introduced. |
| III. Frontend Stack | PASS | Dashboard additions stay within the existing Next.js/TypeScript/Tailwind/chart stack. |
| IV. Backend Stack | PASS | New validation APIs use the existing FastAPI/Pydantic backend style. |
| V. Data Processing | PASS | Data processing and report tables use Polars and timestamp-safe chronological splits. |
| VI. Storage v0 | PASS | Generated validation reports remain local artifacts under `data/reports`. |
| VII. Storage v1+ | N/A | PostgreSQL and ClickHouse remain out of scope. |
| VIII. Event Architecture | PASS | No Kafka, Redpanda, NATS, or event backbone is introduced. |
| IX. Data-Source Principle | PASS | Real-data validation reuses the existing provider/data/feature pipeline and does not add private connectors. |
| X. TradingView Principle | N/A | No TradingView/Pine dependency is added. |
| XI. Reliability Principle | PASS | Adds validation layers for sizing, costs, sensitivity, chronological splits, and report guardrails before any later execution phase. |
| XII. Live Trading Principle | PASS | Explicitly excludes paper, shadow, and live trading. |

**Gate Result**: PASS. No constitution violations require justification.

## Design Overview

### Data Flow

```text
Processed feature Parquet
  -> Backtest/validation config validation
  -> feature column and data identity validation
  -> corrected baseline and strategy simulation
  -> portfolio accounting with no-leverage notional cap
  -> realized and mark-to-market equity curve generation
  -> per-mode metrics and comparison summary
  -> stress profile runner
  -> parameter sensitivity runner
  -> chronological walk-forward runner
  -> regime coverage and trade concentration analysis
  -> validation report artifacts under data/reports/{validation_run_id}/
  -> API and dashboard validation report inspection
```

### Accounting Changes

- Keep all position sizing, fee/slippage application, no-leverage notional cap, cap-event notes, realized/unrealized equity, total equity, and drawdown accounting in `backend/src/backtest/portfolio.py`.
- Extend position/trade/equity schemas so cap events and mark-to-market fields are auditable without losing compatibility with existing report readers.
- Enforce `notional <= available equity` whenever `leverage=1`. If a risk-based position would exceed available equity, reduce quantity and record the cap in trade assumptions or trade notes.
- Mark-to-market equity uses bar close for open positions. Active strategy drawdown should use total equity when total equity exists. Realized-only values remain only as explicitly labeled compatibility fields.

### Baseline Changes

- Keep signal generation in `backend/src/strategies/baselines.py`, but make buy-and-hold a distinct capital-based passive baseline path.
- Add configurable buy-and-hold capital fraction with default 1.0. Buy-and-hold should deploy available equity by capital fraction rather than relying on fixed fractional risk and a distant stop.
- Preserve price-only breakout and no-trade baseline behavior.
- Keep baseline results structurally separated from active strategy results in metrics, reports, and dashboard tables.

### Metrics Changes

- Keep metric calculations in `backend/src/backtest/metrics.py`.
- Promote per-mode metrics to first-class output for each active strategy and each baseline.
- Relabel or replace the current global headline summary so it cannot be mistaken for combined portfolio performance when modes are independent comparisons.
- Add concentration metrics: top 1, top 5, and top 10 trade profit contribution; best 10 trades; worst 10 trades; maximum consecutive losses; and drawdown recovery status/time when calculable.
- Add regime coverage calculations for bar counts, trades per regime, and return by regime.

### Validation Report Design

- Add `backend/src/backtest/validation.py` as the orchestration layer for hardening reports.
- Stress runner reruns the same validated config under bounded fee/slippage profiles: `normal`, `high_fee`, `high_slippage`, and `worst_reasonable_cost`.
- Parameter sensitivity runner performs bounded grids over grid entry threshold, ATR stop buffer, breakout risk/reward multiple, and fee/slippage profile.
- Walk-forward runner creates simple chronological splits and evaluates each split without training or fitting models.
- Real-data validation uses existing BTCUSDT 15m processed features when present. Missing processed features should return clear download/process instructions instead of falling back to synthetic data for final research reports.
- Validation report artifacts reuse `ReportStore` and `backend/src/reports/writer.py`, adding sections for stress tests, sensitivity, walk-forward splits, regime coverage, concentration, real-data identity, limitations, and research-only disclaimers.

### API Design

Add validation endpoints under the existing backtest API namespace. Static validation routes must be registered before dynamic `/{run_id}` routes if they share the same router.

- `POST /api/v1/backtests/validation/run`: run a synchronous local research validation report from a validation config.
- `GET /api/v1/backtests/validation`: list saved validation reports.
- `GET /api/v1/backtests/validation/{validation_run_id}`: return validation metadata and report sections.
- `GET /api/v1/backtests/validation/{validation_run_id}/stress`: return stress profile rows.
- `GET /api/v1/backtests/validation/{validation_run_id}/sensitivity`: return parameter sensitivity rows.
- `GET /api/v1/backtests/validation/{validation_run_id}/walk-forward`: return chronological split rows.
- `GET /api/v1/backtests/validation/{validation_run_id}/concentration`: return regime coverage and concentration sections.

Errors should use the existing structured API style: missing processed data returns `NOT_FOUND` with actionable download/process instructions; invalid validation grids/profiles return `VALIDATION_ERROR`; missing report artifacts return the existing backtest not-found shape.

### Dashboard Design

- Prefer extending `/backtests` with a validation report area if the UI remains readable; add `/validation` only if the report surface becomes too dense.
- Keep the UI work-focused and report-inspection oriented.
- Show per-strategy metrics, per-baseline metrics, fee/slippage stress table, parameter sensitivity table, walk-forward split table, regime coverage table, best/worst trades, concentration warnings, notional cap warnings, and no-profitability/no-live-readiness disclaimer.
- Make clear that strategy and baseline modes are independent comparisons unless a future portfolio-combination mode is explicitly added.

### Test Strategy

- Unit tests for buy-and-hold capital-based sizing and explicit risk-sizing override behavior.
- Unit tests for no-leverage notional cap, cap-event notes, and very small stop-distance cases.
- Unit tests for per-strategy and per-baseline metrics, comparison summary labeling, and removal/relabeling of misleading global metrics.
- Unit tests for mark-to-market equity and realized-only compatibility labeling.
- Unit tests for fee/slippage stress profile generation and aggregation.
- Unit tests for parameter sensitivity aggregation and fragility flags.
- Unit tests for chronological walk-forward split generation and insufficient-window handling.
- Unit tests for regime coverage, concentration metrics, best/worst trade tables, and drawdown recovery.
- Integration test for a full validation report on synthetic processed features with saved artifacts.
- Integration test for real-data validation missing BTCUSDT processed features returning clear instructions.
- API contract tests for new validation endpoints.
- Frontend `npm run build` after type, client, and dashboard changes.
- CI workflow validation for backend, frontend, and artifact guard checks.

### CI Strategy

- Add `.github/workflows/validation.yml` if no workflow exists.
- Backend job: check out repo, set up Python, install backend dev dependencies, run `pytest tests/ -v` from `backend`.
- Frontend job: set up Node, run `npm install`, run `npm run build` from `frontend`.
- Artifact guard job or step: fail if committed files include `data/reports`, `data/processed`, `node_modules`, `.venv`, `.env`, Parquet, DuckDB, or build outputs.
- CI must not require private secrets or private exchange credentials.

## Project Structure

### Documentation (this feature)

```text
specs/004-validation-and-research-hardening/
|-- plan.md
|-- research.md
|-- data-model.md
|-- quickstart.md
|-- contracts/
|   `-- api.md
|-- checklists/
|   `-- requirements.md
`-- tasks.md              # Created later by /speckit.tasks
```

### Source Code (repository root)

```text
backend/
|-- src/
|   |-- api/
|   |   `-- routes/
|   |       `-- backtests.py          # Add validation endpoints or delegate to validation router
|   |-- backtest/
|   |   |-- engine.py                 # Keep orchestration and route validation modes through engine/report store
|   |   |-- portfolio.py              # No-leverage cap, cap notes, realized/unrealized/total equity
|   |   |-- metrics.py                # Per-mode metrics, concentration, drawdown recovery
|   |   |-- report_store.py           # Persist validation artifacts under data/reports
|   |   `-- validation.py             # New stress, sensitivity, walk-forward, coverage orchestration
|   |-- strategies/
|   |   `-- baselines.py              # Capital-based buy-and-hold baseline, preserve other baselines
|   |-- reports/
|   |   `-- writer.py                 # Validation report JSON/Markdown sections
|   |-- models/
|   |   `-- backtest.py               # Validation configs/results and extended equity/trade schemas
|   `-- main.py                       # Register any new validation router if split from backtests.py
`-- tests/
  |-- contract/
  |   `-- test_backtest_validation_contracts.py
  |-- integration/
  |   |-- test_backtest_validation_flow.py
  |   `-- test_real_data_validation_flow.py
  `-- unit/
    |-- test_buy_hold_sizing.py
    |-- test_backtest_notional_cap.py
    |-- test_backtest_validation.py
    |-- test_backtest_concentration.py
    `-- test_backtest_walk_forward.py

frontend/
|-- src/
|   |-- app/
|   |   |-- backtests/
|   |   |   `-- page.tsx              # Extend if validation report fits existing report page
|   |   `-- validation/
|   |       `-- page.tsx              # Optional only if validation inspection needs its own route
|   |-- services/
|   |   `-- api.ts                    # Validation API client methods
|   `-- types/
|       `-- index.ts                  # Validation report TypeScript types

.github/
`-- workflows/
  `-- validation.yml                # Backend, frontend, and artifact guard checks
```

**Structure Decision**: Keep the current backend/frontend split and existing feature ownership boundaries. Add `backend/src/backtest/validation.py` for hardening orchestration because stress, sensitivity, walk-forward, coverage, and concentration logic cross-cut the existing engine/metrics/report store. Do not move strategy signal generation or accounting out of their current modules.

## Implementation Phases

### Phase 0: Research Decisions

Documented in [research.md](research.md). Decisions cover capital-based passive baseline sizing, no-leverage notional caps, mark-to-market equity, per-mode metric semantics, bounded validation runners, real-data handling, dashboard scope, and CI guardrails.

### Phase 1: Design and Contracts

Documented in [data-model.md](data-model.md), [contracts/api.md](contracts/api.md), and [quickstart.md](quickstart.md). Outputs define validation configs, stress profiles, sensitivity results, walk-forward results, coverage/concentration reports, endpoint shapes, and verification steps.

### Phase 2: Task Generation

Use `/speckit.tasks` to create dependency-ordered tasks grouped by the five user stories in [spec.md](spec.md). Tasks must preserve test-first work for accounting correctness, baseline correctness, validation runners, API contracts, dashboard display, real-data flow, and CI guardrails.

### Phase 3: Correctness Foundation

Fix buy-and-hold sizing, notional cap enforcement, cap notes, per-mode metric separation, and mark-to-market equity. Validate with focused unit tests before adding new validation runners.

### Phase 4: Validation Depth

Implement fee/slippage stress profiles, parameter sensitivity grids, walk-forward splits, regime coverage, trade concentration, and drawdown recovery calculations.

### Phase 5: Reports and API

Persist validation artifacts and expose validation report endpoints while preserving existing backtest run/list/detail/trades/metrics/equity endpoints.

### Phase 6: Dashboard Inspection

Extend the backtest report UI or add a focused validation page to inspect validation report tables, warnings, cap events, and disclaimers.

### Phase 7: CI and Final Verification

Add the repository validation workflow, run backend tests, run frontend build, verify artifact guardrails, run synthetic validation smoke, verify real-data missing-data guidance, and review forbidden-tech guardrails.

## Complexity Tracking

No constitution violations or excess architectural complexity are introduced. The new validation module is justified because stress, sensitivity, walk-forward, and concentration analysis are cross-cutting research validation concerns that should not be embedded in strategy signal generation or portfolio accounting.

## Post-Design Constitution Re-Check

| Principle | Status | Notes |
|-----------|--------|-------|
| Research-first and no live trading | PASS | Design hardens historical validation only and excludes paper/shadow/live trading. |
| Allowed language/stack | PASS | Python, FastAPI, Pydantic, Polars, DuckDB, Parquet, Next.js, TypeScript, Tailwind, and existing chart libraries only. |
| Timestamp safety | PASS | Walk-forward uses chronological splits and no intrabar tick claims are added. |
| Local storage | PASS | Validation outputs remain generated artifacts under `data/reports`. |
| Reliability and reproducibility | PASS | Adds cost, sensitivity, split, coverage, concentration, and artifact guard checks. |
| Forbidden v0 technologies | PASS | No live trading, private keys, broker integrations, Rust, ClickHouse, PostgreSQL, Kafka/Redpanda/NATS, Kubernetes, ML training, paper trading, or shadow trading. |

**Gate Result**: PASS. Ready for `/speckit.tasks` after review.
