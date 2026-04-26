# Research: Backtest and Reporting Engine

**Date**: 2026-04-27  
**Feature**: 003-backtest-reporting-engine

## Decision: Use a Deterministic Bar-by-Bar Engine

**Rationale**: The feature needs reproducible historical simulation from processed feature bars, not live execution or tick replay. A bar-by-bar engine can enforce next-bar-open entries, max-one-position behavior, stop/take-profit exits, and deterministic artifacts using the existing feature Parquet files.

**Alternatives considered**:

- Tick-level or intrabar replay: rejected for v0 because no tick source or intrabar execution model exists and the spec explicitly excludes intrabar tick simulation.
- Vector-only signal backtest: rejected because stop/take-profit exits and position accounting need sequential state.
- External backtesting framework: rejected to keep assumptions explicit, small, and aligned with Elpis data models.

## Decision: Keep Strategy Logic Separate From Accounting

**Rationale**: `backend/src/strategies/` should only produce signals and proposed stop/take-profit levels. `backend/src/backtest/portfolio.py` should own sizing, fees, slippage, position state, exits, and equity accounting. This prevents grid/breakout logic from becoming hidden execution code.

**Alternatives considered**:

- Put accounting inside each strategy: rejected because it duplicates fee/slippage/sizing logic and makes comparisons inconsistent.
- Put all strategies directly in engine.py: rejected because it would make strategy behavior hard to test independently.

## Decision: Save Reports as Local Artifacts Under `data/reports/{run_id}`

**Rationale**: The constitution requires reproducible local storage. A run directory containing metadata/config JSON, trade/equity Parquet, metrics JSON, and report JSON/Markdown gives the dashboard and API a simple read path without adding a server database.

**Alternatives considered**:

- Store run metadata in PostgreSQL: rejected because PostgreSQL is forbidden in v0.
- Store everything in one Markdown file: rejected because charts and tables need structured data.
- Commit report artifacts: rejected because `data/reports` is generated output and already ignored by git.

## Decision: Use Pydantic for Config and API Shapes, Polars for Calculations

**Rationale**: Pydantic matches existing FastAPI validation patterns for requests/responses, while Polars matches the constitution and current feature-processing pipeline for DataFrame calculations.

**Alternatives considered**:

- Dataclasses only: rejected because API validation and error detail would be weaker.
- Pandas as the main engine: rejected because Polars is the constitutional default except for compatibility cases.

## Decision: Keep API Runs Synchronous for v0

**Rationale**: Local BTCUSDT 15m backtests should be small enough to complete within v0 performance goals. A synchronous `POST /api/v1/backtests/run` keeps the first implementation simple and returns artifact references immediately.

**Alternatives considered**:

- Background task queue: rejected because it implies more orchestration and persistence than the current local v0 app needs.
- Streaming progress API: rejected for the first slice; run listing and status fields are sufficient.

## Decision: Use Conservative Same-Bar Stop/Take-Profit Policy

**Rationale**: v0 has OHLC bars but no intrabar tick ordering. When both stop and take-profit are inside a bar, assuming stop-first avoids overstating results and documents uncertainty.

**Alternatives considered**:

- Assume take-profit first: rejected because it can bias results positively.
- Randomize intrabar order: rejected because it hurts reproducibility.
- Ignore ambiguous bars: rejected because it hides a key limitation.

## Decision: Metrics Represent Undefined Ratios as Null With Notes

**Rationale**: Profit factor, average loss, and expectancy can be undefined for no-trade or one-sided trade distributions. Returning `null` plus report notes is clearer than fake zeroes or infinities.

**Alternatives considered**:

- Return 0 for undefined values: rejected because it misrepresents math.
- Return infinity: rejected because JSON/dashboard handling becomes awkward and can imply exaggerated quality.

## Decision: Keep Dashboard Additions Report-Focused

**Rationale**: The existing dashboard already handles market data and provider visibility. A minimal `/backtests` page or equivalent panel can inspect runs without redesigning the research app.

**Alternatives considered**:

- Redesign the main dashboard around backtests: rejected by user instruction.
- Build parameter optimization UI now: rejected because the feature asks for initial backtest/report inspection, not robustness sweeps.

## Decision: Guardrails Reject Live-Trading Fields

**Rationale**: The feature must remain research-only. Pydantic models should forbid extra fields and reject concepts such as broker, account, order type, exchange credentials, private keys, and live execution flags if accidentally supplied.

**Alternatives considered**:

- Ignore unexpected fields: rejected because accidental live-trading concepts could slip into saved configs unnoticed.
- Allow leverage greater than 1 by default: rejected because no-leverage is a required v0 default.