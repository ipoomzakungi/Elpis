# Implementation Plan: Backtest and Reporting Engine

**Branch**: `003-backtest-reporting-engine` | **Date**: 2026-04-27 | **Spec**: [spec.md](spec.md)  
**Input**: Feature specification from `/specs/003-backtest-reporting-engine/spec.md`

## Summary

Add a v0 research-only backtest and reporting engine on top of the existing OI Regime Lab and research data provider layer. The implementation will load processed feature Parquet data through the existing repository path, validate required columns, run deterministic bar-by-bar simulations for regime-aware grid/range, regime-aware breakout, and baseline comparison modes, and save reproducible report artifacts under `data/reports`. Backend changes stay scoped to `backend/src/backtest/`, `backend/src/strategies/`, `backend/src/reports/`, `backend/src/models/backtest.py`, and `backend/src/api/routes/backtests.py`. Frontend changes stay focused on report inspection through a backtest page or panel with run selection, summary metrics, equity/drawdown charts, and trade/comparison tables.

## Technical Context

**Language/Version**: Python 3.11+, TypeScript 5.x  
**Primary Dependencies**: FastAPI, Pydantic, Pydantic Settings, Polars, DuckDB, Parquet/PyArrow, Next.js, Tailwind CSS, lightweight-charts/Recharts  
**Storage**: Existing local `data/processed` for feature input and `data/reports` for generated Parquet/JSON/Markdown report artifacts; no new server database  
**Testing**: pytest, pytest-asyncio, backend unit/integration/contract tests, frontend `npm run build`  
**Target Platform**: Local development on Windows/macOS/Linux  
**Project Type**: Web application with FastAPI backend and Next.js dashboard  
**Performance Goals**: Typical BTCUSDT 15m local v0 run completes within 30 seconds; report API and dashboard load typical local reports within 5 seconds  
**Constraints**: Research-only; no live trading, private API keys, real execution, broker integration, Rust, ClickHouse, PostgreSQL, Kafka/Redpanda/NATS, Kubernetes, or ML model training; do not redesign existing dashboard/provider flows; generated `data/reports` artifacts are not committed  
**Scale/Scope**: v0 local single-user research platform, first required input is BTCUSDT 15m processed features, max one open position by default, no leverage and no compounding by default, no intrabar tick simulation

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Principle | Status | Notes |
|-----------|--------|-------|
| I. Research-First Architecture | PASS | The feature evaluates historical strategy behavior only and explicitly avoids live trading claims. |
| II. Language Split | PASS | Python is used for backtesting/reporting and TypeScript for dashboard inspection; no Rust execution component is added. |
| III. Frontend Stack | PASS | Dashboard changes remain Next.js/TypeScript/Tailwind with existing charting libraries. |
| IV. Backend Stack | PASS | Backtest APIs use FastAPI with Pydantic schemas. |
| V. Data Processing | PASS | Backtests load and process data with Polars and keep timestamp-safe next-bar-open simulation rules. |
| VI. Storage v0 | PASS | Inputs remain Parquet; generated reports are local artifacts under `data/reports`. |
| VII. Storage v1+ | N/A | PostgreSQL and ClickHouse remain out of scope for v0. |
| VIII. Event Architecture | PASS | No Kafka, Redpanda, NATS, or event backbone is introduced. |
| IX. Data-Source Principle | PASS | The engine consumes validated processed features and source metadata where available; it does not add new data connectors. |
| X. TradingView Principle | N/A | No TradingView/Pine dependency is added. |
| XI. Reliability Principle | PASS | Signals are simulated only after feature validation, config validation, and explicit risk/assumption checks. |
| XII. Live Trading Principle | PASS | No paper/live execution, broker integration, private keys, or order routing is added. |

**Gate Result**: PASS. No constitution violations require justification.

## Design Overview

### Data Flow

```text
Processed features Parquet
  -> BacktestConfig validation
  -> feature column validation
  -> strategy signal generation per bar
  -> next-bar-open position entry
  -> portfolio accounting with fee/slippage
  -> stop/take-profit exit evaluation
  -> trade log and equity curve
  -> metrics aggregation and comparisons
  -> report artifact writing under data/reports/{run_id}/
  -> API and dashboard report inspection
```

### Backend Modules

- `backend/src/models/backtest.py`: Pydantic enums and schemas for configs, runs, trades, equity points, metrics, report artifacts, and API responses.
- `backend/src/backtest/engine.py`: validates input features, orchestrates selected strategy modes, enforces next-bar-open entries and max-one-position v0 behavior, and produces deterministic run outputs.
- `backend/src/backtest/portfolio.py`: owns position accounting, fee/slippage application, fixed fractional sizing, stop/take-profit exits, equity tracking, and no-leverage/no-compounding defaults.
- `backend/src/backtest/metrics.py`: calculates required metrics and grouped returns by regime, strategy mode, symbol, and provider where available.
- `backend/src/backtest/report_store.py`: reads/writes report artifacts under `data/reports/{run_id}/` and lists available runs.
- `backend/src/strategies/grid_strategy.py`: generates regime-aware RANGE signals with lower-range long, optional upper-range short, TP at range_mid by default, SL outside range plus ATR buffer, and no martingale state.
- `backend/src/strategies/breakout_strategy.py`: generates BREAKOUT_UP/BREAKOUT_DOWN signals with confirmation, stop-back-inside-range or ATR stop, and R-multiple TP.
- `backend/src/strategies/baselines.py`: generates buy-and-hold and price-only breakout baseline outputs under the same accounting assumptions.
- `backend/src/reports/`: report composition helpers for JSON/Markdown outputs, separated from simulation/accounting.
- `backend/src/api/routes/backtests.py`: exposes run, list, detail, trades, metrics, and equity endpoints.

### Backtest Config Schema

Pydantic config is organized as a top-level run request with nested assumptions and strategy settings:

```text
BacktestRunRequest
  symbol: string = BTCUSDT
  provider: string | null = binance
  timeframe: string = 15m
  feature_path: string | null
  initial_equity: decimal > 0
  assumptions: BacktestAssumptions
  strategies: list[StrategyConfig]
  baselines: list[BaselineMode]
  report_format: json | markdown | both

BacktestAssumptions
  fee_rate: decimal >= 0 and <= configured ceiling
  slippage_rate: decimal >= 0 and <= configured ceiling
  risk_per_trade: decimal > 0 and <= configured ceiling
  max_positions: int = 1 for v0
  allow_short: bool
  allow_compounding: bool = false
  leverage: decimal = 1
  ambiguous_intrabar_policy: stop_first
```

Validation rejects missing processed features, invalid fee/slippage/risk values, leverage above 1 for v0, max positions above 1 for v0, and any unexpected live-trading or execution fields.

### Trade Log Schema

Each trade record includes deterministic simulation data:

```text
TradeRecord
  trade_id
  run_id
  strategy_mode
  provider | null
  symbol
  timeframe
  side: long | short
  regime_at_signal
  signal_timestamp
  entry_timestamp
  entry_price
  exit_timestamp
  exit_price
  exit_reason: take_profit | stop_loss | end_of_data | invalidated
  quantity
  notional
  gross_pnl
  fees
  slippage
  net_pnl
  return_pct
  holding_bars
  assumptions_snapshot
```

### Metrics Schema

`MetricsSummary` stores total return, maximum drawdown, profit factor, win rate, average win, average loss, expectancy, trade count, average holding bars, maximum consecutive losses, return by regime, return by strategy mode, return by symbol/provider where available, plus references to equity and drawdown curves. Undefined ratios are represented as `null` with a reason in report notes rather than misleading infinities.

### Report Artifact Schema

Each run writes a deterministic directory under `data/reports/{run_id}/`:

```text
metadata.json
config.json
trades.parquet
equity.parquet
metrics.json
report.json
report.md          # when requested
```

`ReportArtifact` records artifact type, path, format, row count where applicable, created timestamp, and checksum or content hash if implemented during tasks. `data/reports/` is already ignored by git.

### API Design

Add `backend/src/api/routes/backtests.py` and register it in `backend/src/main.py` with `/api/v1` prefix:

- `POST /api/v1/backtests/run`: validate request, run synchronous local v0 backtest, write artifacts, return run summary.
- `GET /api/v1/backtests`: list saved runs from report metadata.
- `GET /api/v1/backtests/{run_id}`: return run detail and artifact references.
- `GET /api/v1/backtests/{run_id}/trades`: return trade log rows with optional pagination/limit.
- `GET /api/v1/backtests/{run_id}/metrics`: return metrics and comparison tables.
- `GET /api/v1/backtests/{run_id}/equity`: return equity and drawdown curve points.

Errors use the existing structured API style: validation failures return `VALIDATION_ERROR`, missing processed features or report artifacts return `NOT_FOUND`, and unreadable artifacts return a backtest/report-specific structured error.

### Dashboard Design

Keep the dashboard change narrow and work-focused:

- Add `frontend/src/app/backtests/page.tsx` for report inspection, or an equivalent panel if routing is kept minimal during implementation.
- Add backtest API methods and TypeScript types in the existing service/type files.
- Show a compact run selector with run ID, symbol, timeframe, strategy modes, status, and created time.
- Show summary metric cards for total return, max drawdown, profit factor, win rate, expectancy, and trade count.
- Use Recharts or existing chart patterns for equity and drawdown curves.
- Show a trade table with deterministic trade fields.
- Show regime performance, strategy mode comparison, and baseline comparison tables.
- Display assumption/limitation notes near the report, without any claim of profitability or live readiness.

### Test Strategy

- Unit tests for metrics calculation, including no trades, only wins, only losses, undefined profit factor, drawdown, expectancy, and max consecutive losses.
- Unit tests for portfolio accounting, including fee/slippage, fixed fractional sizing, long/short PnL, stop/take-profit exits, and max-one-position behavior.
- Unit tests for grid strategy signal generation using RANGE and non-RANGE rows.
- Unit tests for breakout strategy signal generation using BREAKOUT_UP/BREAKOUT_DOWN and non-breakout rows.
- Unit tests for baseline generation for buy-and-hold and price-only breakout.
- Integration test running a full backtest on synthetic processed feature data and verifying artifacts are written under an isolated reports path.
- API contract tests for all backtest endpoints and structured error cases.
- Frontend `npm run build` after report page/panel and API client/type changes.
- Existing provider, feature, and dashboard tests remain in place to detect compatibility regressions.

## Project Structure

### Documentation (this feature)

```text
specs/003-backtest-reporting-engine/
|-- plan.md
|-- research.md
|-- data-model.md
|-- quickstart.md
|-- contracts/
|   `-- api.md
`-- tasks.md              # Created later by /speckit.tasks
```

### Source Code (repository root)

```text
backend/
|-- src/
|   |-- api/
|   |   `-- routes/
|   |       `-- backtests.py          # Backtest run/list/detail/report endpoints
|   |-- backtest/
|   |   |-- __init__.py
|   |   |-- engine.py                 # Bar-by-bar simulation orchestration
|   |   |-- portfolio.py              # Position accounting, fees, slippage, equity
|   |   |-- metrics.py                # Required metrics and grouping calculations
|   |   `-- report_store.py          # Artifact persistence under data/reports
|   |-- strategies/
|   |   |-- __init__.py
|   |   |-- grid_strategy.py          # RANGE-only grid/range signal logic
|   |   |-- breakout_strategy.py      # BREAKOUT_UP/DOWN signal logic
|   |   `-- baselines.py             # Buy-and-hold and price-only baselines
|   |-- reports/
|   |   |-- __init__.py
|   |   `-- writer.py                # Report JSON/Markdown composition
|   |-- models/
|   |   `-- backtest.py              # Pydantic configs/responses/artifact schemas
|   |-- repositories/
|   |   `-- parquet_repo.py          # Reuse existing processed feature loading
|   `-- main.py                      # Register backtests router
`-- tests/
    |-- contract/
    |   `-- test_backtest_api_contracts.py
    |-- integration/
    |   `-- test_backtest_engine_flow.py
    `-- unit/
        |-- test_backtest_metrics.py
        |-- test_backtest_portfolio.py
        |-- test_grid_strategy.py
        |-- test_breakout_strategy.py
        `-- test_baselines.py

frontend/
|-- src/
|   |-- app/
|   |   `-- backtests/
|   |       `-- page.tsx             # Backtest report inspection screen
|   |-- components/
|   |   |-- charts/
|   |   |   |-- EquityCurveChart.tsx
|   |   |   `-- DrawdownChart.tsx
|   |   `-- panels/
|   |       `-- BacktestSummaryCards.tsx
|   |-- services/
|   |   `-- api.ts                   # Backtest API client methods
|   `-- types/
|       `-- index.ts                 # Backtest TypeScript types
```

**Structure Decision**: Keep the current backend/frontend split. Add purpose-specific backend packages for simulation, strategy signals, and report writing because the user explicitly requested those ownership boundaries. Keep frontend additions limited to report inspection and reuse existing API/type/chart patterns.

## Implementation Phases

### Phase 0: Research Decisions

Documented in [research.md](research.md). Decisions cover the bar-by-bar engine, strategy module ownership, portfolio accounting, metrics semantics, artifact layout, API execution model, dashboard scope, and guardrails.

### Phase 1: Design and Contracts

Documented in [data-model.md](data-model.md), [contracts/api.md](contracts/api.md), and [quickstart.md](quickstart.md). Outputs define config, trades, equity, metrics, report artifacts, endpoint shapes, and verification steps.

### Phase 2: Task Generation

Use `/speckit.tasks` to create dependency-ordered tasks grouped by user story. Tasks must preserve test-first work for metrics, portfolio accounting, strategy signals, full-engine integration, API contracts, and frontend build.

### Phase 3: Backtest Foundation

Implement models, report store, portfolio primitives, metrics helpers, and synthetic fixtures. Validate config guardrails and missing feature handling before strategy behavior.

### Phase 4: Strategy Modes and Engine

Implement grid/range signals, breakout signals, baselines, bar-by-bar engine orchestration, deterministic trade logs, and equity curves.

### Phase 5: API and Report Artifacts

Register backtest routes, run backtests from processed features, save/read artifacts under `data/reports`, and expose run/trades/metrics/equity endpoints.

### Phase 6: Dashboard Report Inspection

Add the minimal backtest report page or panel with run selector, metrics cards, equity/drawdown charts, trade table, regime performance, strategy comparison, and baseline comparison.

### Phase 7: Verification and Guardrails

Run backend import, full backend tests, frontend build, synthetic backtest smoke, artifact ignore review, and forbidden-tech review. Do not commit generated report files.

## Complexity Tracking

No constitution violations or excess architectural complexity are introduced. The new backend packages map directly to requested boundaries and avoid broad rewrites of existing provider, feature, or dashboard flows.

## Post-Design Constitution Re-Check

| Principle | Status | Notes |
|-----------|--------|-------|
| Research-first and no live trading | PASS | Design simulates historical behavior only and stores assumptions in reports. |
| Allowed language/stack | PASS | Python, FastAPI, Pydantic, Polars, Parquet/JSON/Markdown, Next.js, TypeScript, Tailwind, and existing chart libraries only. |
| Timestamp safety | PASS | Strategy signals enter next bar open and no intrabar tick claims are made. |
| Local storage | PASS | Inputs and outputs remain local Parquet/JSON/Markdown artifacts; no server database is added. |
| Reliability and reproducibility | PASS | Run configs, assumptions, data identity, trades, equity, and metrics are persisted. |
| Forbidden v0 technologies | PASS | No live trading, private keys, broker integrations, Rust, ClickHouse, PostgreSQL, Kafka/Redpanda/NATS, Kubernetes, or ML training are added. |

**Gate Result**: PASS. Ready for `/speckit.tasks` after review.