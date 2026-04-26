# Feature Specification: Backtest and Reporting Engine

**Feature Branch**: `003-backtest-reporting-engine`  
**Created**: 2026-04-27  
**Status**: Draft  
**Input**: User description: "Add a backtest and reporting engine for Elpis research strategies. Evaluate whether regime classification improves strategy behavior compared with price-only baselines, using existing processed feature data, while remaining research-only and avoiding live trading or private execution behavior."

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Run Research Backtests From Processed Features (Priority: P1)

The researcher wants to run reproducible backtests against existing processed feature datasets, starting with BTCUSDT 15m OI Regime Lab outputs, so the OI regime idea can be evaluated with explicit assumptions.

**Why this priority**: The project cannot assess research value until it can turn processed features into deterministic trades, equity curves, and metrics under documented assumptions.

**Independent Test**: Can be fully tested by running a backtest on an existing BTCUSDT 15m processed feature dataset and verifying that run metadata, trade log, equity curve, metrics, and report artifacts are created without any live trading behavior.

**Acceptance Scenarios**:

1. **Given** an existing BTCUSDT 15m processed feature dataset with OHLCV, ranges, ATR, and regime labels, **When** the researcher starts a backtest with a valid regime-aware strategy configuration, **Then** the system produces a completed research run with saved metadata, trades, equity curve, metrics, and report output.
2. **Given** a strategy signal is generated on one bar, **When** the backtest simulates entry, **Then** the entry occurs at the next bar open and applies configured fee and slippage assumptions.
3. **Given** a run configuration sets fixed fractional risk, no leverage, max one position, and no compounding, **When** the backtest executes trades, **Then** each position follows those constraints and records sizing assumptions in the run metadata.
4. **Given** a backtest completes with no valid trade signals, **When** artifacts are saved, **Then** the run is still inspectable with zero trades, flat or baseline equity as applicable, and metrics that clearly show no-trade behavior.

---

### User Story 2 - Compare Regime Strategies Against Baselines (Priority: P2)

The researcher wants to compare regime-aware grid/range and breakout strategies against simple baselines so they can judge whether regime classification changes strategy behavior without claiming profitability.

**Why this priority**: The core research question is comparative: regime-aware logic only matters if its behavior can be measured against price-only and passive alternatives under the same data and assumptions.

**Independent Test**: Can be fully tested by running one report configuration that includes a regime-aware strategy and at least one baseline, then verifying side-by-side return, drawdown, trade, and regime breakdowns.

**Acceptance Scenarios**:

1. **Given** regime-aware grid/range mode is enabled, **When** the dataset is in RANGE regime, **Then** the system can enter long positions near the lower range and optional short positions near the upper range, with configured take-profit and stop-loss rules.
2. **Given** regime-aware grid/range mode is enabled, **When** the dataset is not in RANGE regime, **Then** the strategy does not open new grid/range trades.
3. **Given** regime-aware breakout mode is enabled, **When** the dataset enters BREAKOUT_UP or BREAKOUT_DOWN regime, **Then** the system can enter the matching long or optional short breakout trade with configured stop and take-profit rules.
4. **Given** baseline comparison is requested, **When** the report is generated, **Then** it includes buy-and-hold, price-only breakout, and optional no-trade baseline results where configured.
5. **Given** regime-aware and baseline results are available, **When** the researcher reviews the comparison, **Then** the report presents behavior differences as backtest results under assumptions rather than strategy profitability claims.

---

### User Story 3 - Inspect Backtest Reports Through API and Dashboard (Priority: P3)

The researcher wants to browse completed backtest runs, inspect metrics and trades, and view equity and drawdown curves from the dashboard.

**Why this priority**: Backtest results need to be explorable, not just written to files, so researchers can audit trades, compare strategies, and spot data or assumption issues.

**Independent Test**: Can be fully tested by creating one backtest run and then retrieving the run list, run detail, trades, metrics, and equity data through the reporting views.

**Acceptance Scenarios**:

1. **Given** one or more saved backtest runs exist, **When** the researcher opens the report view, **Then** a run selector displays available runs with enough metadata to choose the correct result.
2. **Given** a run is selected, **When** the dashboard loads the report, **Then** summary metric cards, equity curve, drawdown curve, trade table, regime performance table, strategy mode comparison, and baseline comparison are visible.
3. **Given** a completed run contains trade records, **When** the researcher opens the trade table, **Then** entries, exits, holding bars, direction, regime, strategy mode, fees, slippage, profit/loss, and exit reason are inspectable.
4. **Given** a report artifact is missing or unreadable, **When** the researcher requests the report, **Then** the system returns a clear not-found or validation response instead of a broken dashboard state.

---

### User Story 4 - Preserve Research-Only Reproducibility and Compatibility (Priority: P4)

The researcher wants every backtest report to document assumptions, saved configuration, limitations, and source data identity while preserving existing provider and dashboard behavior.

**Why this priority**: Reproducibility and guardrails prevent backtest output from being mistaken for a live trading recommendation and keep the v0 platform aligned with the Elpis constitution.

**Independent Test**: Can be fully tested by re-running a saved configuration on the same input data and confirming the same trades and metrics are produced, with no live trading, private API, or broker behavior introduced.

**Acceptance Scenarios**:

1. **Given** a saved backtest report, **When** the researcher inspects metadata, **Then** the report includes strategy configuration, data identity, provider/symbol/timeframe where available, fee/slippage assumptions, sizing assumptions, and known limitations.
2. **Given** a saved run configuration is re-executed against unchanged input data, **When** the backtest completes, **Then** the resulting trades, equity curve, and metrics are reproducible.
3. **Given** existing market data, provider, feature, and dashboard workflows are used, **When** the backtest feature is added, **Then** those workflows remain compatible.
4. **Given** the user reviews a report, **When** strategy results are displayed, **Then** the system avoids language that claims profitability or live-trading readiness.

### Edge Cases

- Processed feature data is missing, empty, unreadable, or has no rows after validation.
- Required columns for a requested strategy mode are absent, null, or inconsistent.
- A signal occurs on the final bar and no next bar open exists for entry.
- Stop loss and take profit are both reachable within the same bar, but v0 has no intrabar tick simulation.
- Short trading is disabled while SHORT or BREAKOUT_DOWN opportunities occur.
- Max-one-position mode blocks a new signal while a trade is already open.
- Fee or slippage settings are zero, unusually high, or invalid.
- Fixed fractional sizing produces a position too small or too large for configured constraints.
- A strategy produces no trades, only losses, or only wins, making ratios such as profit factor or average loss potentially undefined.
- Baseline comparison is requested for a dataset that lacks enough bars to compute the baseline.
- Report artifacts exist on disk but their metadata, trades, metrics, or equity files are missing or inconsistent.
- Multiple runs have similar names or configurations and must remain distinguishable by run metadata.
- A provider, symbol, or timeframe is unavailable in older feature artifacts.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: System MUST allow researchers to run backtests from processed feature datasets produced by the existing research pipeline.
- **FR-002**: System MUST support BTCUSDT 15m processed features from the OI Regime Lab as the first required backtest input.
- **FR-003**: System MUST validate that required data fields for the selected strategy mode are available before a backtest run begins.
- **FR-004**: System MUST support a regime-aware grid/range strategy mode that trades only during RANGE regime.
- **FR-005**: Regime-aware grid/range mode MUST support long entries near lower range boundaries and optional short entries near upper range boundaries.
- **FR-006**: Regime-aware grid/range mode MUST support take profit at range midpoint or a configured next grid level.
- **FR-007**: Regime-aware grid/range mode MUST support stop loss outside the range with a configurable ATR buffer.
- **FR-008**: Regime-aware grid/range mode MUST prohibit martingale behavior.
- **FR-009**: System MUST support a regime-aware breakout strategy mode that trades only during BREAKOUT_UP or BREAKOUT_DOWN regimes.
- **FR-010**: Regime-aware breakout mode MUST support long entries on BREAKOUT_UP and optional short entries on BREAKOUT_DOWN.
- **FR-011**: Regime-aware breakout mode MUST support stops based on movement back inside the range or an ATR-based stop.
- **FR-012**: Regime-aware breakout mode MUST support take profit by configured risk multiple for v0.
- **FR-013**: System MUST support baseline comparison modes including buy-and-hold, price-only breakout without OI regime filter, and optional no-trade baseline.
- **FR-014**: System MUST use next-bar-open entry after a signal for simulated trades.
- **FR-015**: System MUST simulate exits using configured stop-loss and take-profit rules.
- **FR-016**: System MUST include configurable fee rate and slippage rate in backtest results.
- **FR-017**: System MUST support fixed fractional position sizing.
- **FR-018**: System MUST default to no leverage, no compounding, and maximum one open position unless the run configuration explicitly changes supported research assumptions.
- **FR-019**: System MUST NOT add live trading, private exchange API keys, real order execution, broker integration, wallet/private-key handling, leverage execution, real position management, Rust, ClickHouse, PostgreSQL, Kafka, Redpanda, NATS, Kubernetes, or ML model training in this feature.
- **FR-020**: System MUST calculate total return, maximum drawdown, profit factor, win rate, average win, average loss, expectancy, number of trades, average holding bars, maximum consecutive losses, return by regime, return by strategy mode, return by symbol/provider where available, equity curve, and drawdown curve.
- **FR-021**: System MUST generate and save backtest run metadata, trade log, equity curve data, metrics JSON, and report JSON or Markdown for each completed run.
- **FR-022**: Generated backtest artifacts MUST be saved under `data/reports` and MUST be treated as generated research output that is not committed to source control.
- **FR-023**: Saved run metadata MUST include enough configuration and data identity to reproduce the run from unchanged input data.
- **FR-024**: System MUST expose external reporting operations for starting a backtest run, listing runs, retrieving run details, retrieving trades, retrieving metrics, and retrieving equity data.
- **FR-025**: The external reporting operations MUST include `POST /api/v1/backtests/run`, `GET /api/v1/backtests`, `GET /api/v1/backtests/{run_id}`, `GET /api/v1/backtests/{run_id}/trades`, `GET /api/v1/backtests/{run_id}/metrics`, and `GET /api/v1/backtests/{run_id}/equity`.
- **FR-026**: Dashboard MUST include a backtest report page or panel with run selector, summary metric cards, equity curve, drawdown curve, trade table, regime performance table, strategy mode comparison, and baseline comparison.
- **FR-027**: System MUST clearly document v0 backtest limitations, including no intrabar tick simulation and assumptions for ambiguous same-bar stop/take-profit outcomes.
- **FR-028**: System MUST report backtest results only as historical simulation outputs under documented assumptions and MUST NOT claim a strategy is profitable, predictive, safe, or ready for live trading.
- **FR-029**: Existing provider, feature, regime, and dashboard behavior MUST remain compatible after adding backtest reporting.

### Key Entities *(include if feature involves data)*

- **BacktestRun**: A single reproducible research simulation, including run identifier, creation time, status, input data identity, selected strategy modes, assumptions, and artifact references.
- **BacktestConfig**: The saved configuration used to reproduce a run, including strategy mode settings, fee/slippage assumptions, sizing rules, baseline selections, and limitations.
- **StrategyModeResult**: The result for one strategy or baseline mode within a run, including metrics, equity data, drawdown data, and trade references.
- **TradeRecord**: One simulated trade with entry, exit, side, strategy mode, regime, size, fees, slippage, profit/loss, holding bars, and exit reason.
- **EquityPoint**: A timestamped equity and drawdown observation used to plot run performance over time.
- **MetricsSummary**: Aggregated measurements such as return, drawdown, profit factor, win rate, expectancy, trade count, holding time, and consecutive loss statistics.
- **RegimePerformance**: Return and trade behavior grouped by regime label for a run or strategy mode.
- **BaselineComparison**: Side-by-side comparison between regime-aware strategy modes and baseline modes under shared assumptions.
- **ReportArtifact**: A saved file reference for metadata, trades, equity curve, metrics, or report output.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: A researcher can run a backtest using existing BTCUSDT 15m processed features and receive a completed run with metadata, trade log, equity curve, metrics, and report artifacts.
- **SC-002**: At least one regime-aware strategy mode can be compared with buy-and-hold and price-only breakout baselines in a single report.
- **SC-003**: Reports include all required metrics: total return, maximum drawdown, profit factor, win rate, average win, average loss, expectancy, number of trades, average holding bars, maximum consecutive losses, return by regime, return by strategy mode, return by symbol/provider where available, equity curve, and drawdown curve.
- **SC-004**: A saved run configuration can be re-run on unchanged input data and reproduce the same trade log, equity curve, and metrics.
- **SC-005**: Researchers can inspect a completed run, trades, metrics, and equity data through the reporting interface within 5 seconds for a typical local v0 run.
- **SC-006**: Dashboard report view shows summary metrics, equity curve, drawdown curve, trade table, regime performance, strategy comparison, and baseline comparison for a completed run.
- **SC-007**: Backtest outputs clearly display fee, slippage, sizing, no-intrabar, leverage, compounding, and execution-timing assumptions for 100% of completed reports.
- **SC-008**: Invalid run requests, missing input data, unsupported strategy configurations, and missing report artifacts return structured user-readable responses.
- **SC-009**: Existing provider metadata, data download, feature processing, regime display, and dashboard workflows continue to operate after the backtest feature is added.
- **SC-010**: Dependency and behavior review confirms no live trading, private API, broker, forbidden storage, event system, Kubernetes, Rust execution, or ML training capability is introduced.

## Assumptions

- This feature remains a local v0 research and reporting capability, not a paper or live trading system.
- Existing processed feature datasets already contain the OHLCV, range, ATR, and regime fields needed for the first BTCUSDT 15m backtest path.
- Provider, symbol, and timeframe metadata are used when available and may be absent for older artifacts.
- v0 does not simulate intrabar tick order. If stop loss and take profit are both reachable within the same bar, the conservative default is to assume the stop loss is hit first and record the ambiguity in run limitations.
- ATR trailing exits are out of scope for the first v0 implementation unless explicitly added later; v0 breakout take profit uses configured risk multiple.
- Position sizing uses research assumptions only and does not imply account balances, broker constraints, margin availability, or executable order sizes.
- Generated files under `data/reports` are reproducible artifacts and should remain excluded from source control.
- Backtest reports are descriptive and comparative only; they must not be worded as investment advice or strategy validation claims.