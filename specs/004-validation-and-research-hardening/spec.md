# Feature Specification: Validation and Research Hardening

**Feature Branch**: `004-validation-and-research-hardening`  
**Created**: 2026-04-27  
**Status**: Draft  
**Input**: User description: "Add validation and research hardening for Elpis backtest results. Harden the completed backtest/reporting MVP for correctness, robustness, and research trustworthiness before any paper, shadow, or live trading work."

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Correct Baselines, Sizing, and Equity (Priority: P1)

The researcher wants passive baselines, active strategy sizing, no-leverage limits, headline metrics, and equity curves to reflect the intended research assumptions so backtest results cannot be misread because of accounting artifacts.

**Why this priority**: If baseline sizing, notional exposure, or headline metrics are wrong, every later robustness or research report can be misleading even when the software runs successfully.

**Independent Test**: Can be fully tested by running controlled backtests that include buy-and-hold, active strategies, tiny stop distances, open positions, and multiple strategy modes, then verifying sizing, capping, equity, drawdown, and metric labels.

**Acceptance Scenarios**:

1. **Given** a buy-and-hold baseline is selected with default settings, **When** a backtest runs, **Then** the baseline deploys 100% of available starting equity unless another capital fraction is configured.
2. **Given** an active strategy uses fixed fractional risk and a very small stop distance, **When** requested notional would exceed available equity with no leverage, **Then** the position notional is capped at available equity and the cap is recorded in the trade assumptions or notes.
3. **Given** one run compares multiple independent strategy and baseline modes, **When** headline results are displayed, **Then** each mode has separate metrics and any aggregate section is labeled as a comparison summary rather than a combined portfolio result.
4. **Given** a trade remains open across multiple bars, **When** the equity curve is produced, **Then** the report distinguishes realized equity from mark-to-market total equity where close prices allow that calculation.
5. **Given** a buy-and-hold baseline and active strategies appear in the same report, **When** the researcher inspects results, **Then** passive baseline results are visually and structurally separated from active strategy results.

---

### User Story 2 - Stress Costs and Parameter Robustness (Priority: P2)

The researcher wants to evaluate whether strategy behavior survives higher trading costs and modest parameter changes before treating any result as research evidence.

**Why this priority**: A result that depends on one narrow setting or unrealistically low trading costs is fragile and should be flagged before further research decisions.

**Independent Test**: Can be fully tested by running one saved configuration through predefined fee/slippage stress profiles and a bounded parameter grid, then verifying that tabular robustness outputs and report summaries are generated without profitability claims.

**Acceptance Scenarios**:

1. **Given** a completed baseline configuration, **When** cost stress validation is requested, **Then** normal, high-fee, high-slippage, and worst-reasonable-cost profiles are evaluated under identical signal assumptions.
2. **Given** stress results are available, **When** the report is generated, **Then** it states whether each strategy remained positive, turned negative, or had no trades under higher costs without claiming profitability.
3. **Given** a bounded parameter grid is requested, **When** the validation run completes, **Then** results are exported for grid entry threshold, ATR stop buffer, breakout risk/reward multiple, and fee/slippage profile variations.
4. **Given** a strategy performs well only for one isolated parameter setting, **When** sensitivity results are summarized, **Then** the report flags that outcome as fragile.

---

### User Story 3 - Validate Across Time Windows (Priority: P3)

The researcher wants to split historical data into chronological validation windows so results can be compared across different market periods without introducing model training.

**Why this priority**: A single full-period backtest can hide regime-specific or time-period-specific failures; chronological splits make robustness easier to audit.

**Independent Test**: Can be fully tested by running a backtest over a dataset with enough rows for multiple chronological windows and verifying per-window metrics, data ranges, and clear handling of windows with too few bars.

**Acceptance Scenarios**:

1. **Given** a dataset spans multiple time windows, **When** walk-forward validation is requested, **Then** the system reports performance by chronological split with each split's date range and row count.
2. **Given** a split has too few bars for the selected strategy, **When** the validation report is created, **Then** that split is marked insufficient rather than silently omitted.
3. **Given** walk-forward results are displayed, **When** the researcher reviews them, **Then** the report makes clear that no machine learning training or paper/shadow trading occurred.
4. **Given** full-period and split-period results differ materially, **When** the report is summarized, **Then** the discrepancy is visible in the validation output.

---

### User Story 4 - Audit Regime Coverage and Trade Concentration (Priority: P4)

The researcher wants reports to reveal whether results depend on too few regimes, too few trades, a small number of winners, or long drawdown recovery periods.

**Why this priority**: Research conclusions are weak if performance comes from concentrated outliers or from market regimes that barely appear in the sample.

**Independent Test**: Can be fully tested by running a known trade set and feature dataset, then verifying regime counts, trade concentration, top/worst trade tables, consecutive loss counts, and drawdown recovery calculations.

**Acceptance Scenarios**:

1. **Given** processed features contain regime labels, **When** a validation report is generated, **Then** it includes counts for RANGE, BREAKOUT_UP, BREAKOUT_DOWN, and AVOID bars.
2. **Given** completed trades exist, **When** trade concentration is calculated, **Then** the report includes profit share from the top 1, top 5, and top 10 trades.
3. **Given** completed trades exist, **When** the researcher inspects trade distributions, **Then** the report lists the best 10 trades, worst 10 trades, trades per regime, return by regime, and maximum consecutive losses.
4. **Given** drawdown recovers before the dataset ends, **When** recovery statistics are computed, **Then** drawdown recovery time is reported; otherwise the report states that recovery did not occur within the sample.

---

### User Story 5 - Run Real-Data Research Validation and Automated Checks (Priority: P5)

The researcher wants the hardening workflow to support a real BTCUSDT 15m research run using existing processed feature data and to be protected by automated repository validation that does not require private secrets.

**Why this priority**: Synthetic tests prove correctness in controlled cases, but research trust requires real-data validation and repeatable checks before future work builds on the feature.

**Independent Test**: Can be fully tested by attempting a real-data validation run, verifying clear instructions when data is missing, and running automated validation for backend tests, frontend build, and generated artifact guardrails.

**Acceptance Scenarios**:

1. **Given** existing BTCUSDT 15m processed features are available, **When** a real-data validation run is requested, **Then** the report uses that dataset and shows source, date range, row count, and limitations.
2. **Given** BTCUSDT 15m processed features are missing, **When** a real-data validation run is requested, **Then** the system returns clear instructions to download and process data first.
3. **Given** repository validation runs in an automated environment, **When** checks execute, **Then** backend tests, frontend build, and generated artifact guard checks run without private secrets.
4. **Given** validation outputs are generated, **When** source control status is inspected, **Then** report artifacts remain excluded from committed source.

### Edge Cases

- Buy-and-hold capital fraction is zero, missing, above 100%, or otherwise invalid.
- Buy-and-hold is configured to use fixed fractional risk explicitly and must still remain separate from active strategies.
- Active strategy stop distance is zero, negative, extremely small, or larger than entry price.
- No-leverage notional cap changes position quantity and must be recorded without mutating the user's requested assumptions.
- A compared mode has no trades while other modes trade normally.
- A run includes multiple independent equity curves with different timestamp coverage.
- A dataset has open positions at the final bar.
- Close price is missing or invalid for mark-to-market calculation.
- Stress profile costs are zero, unusually high, duplicated, or invalid.
- Parameter grid size would be too large for a local research run.
- Walk-forward split windows have too few rows or no trades.
- Regime labels are missing, malformed, or contain regimes outside the expected research set.
- Fewer than 10 completed trades exist for best/worst trade reports.
- Drawdown never recovers within the sample.
- Real-data feature files are missing, stale, unreadable, or do not include source metadata.
- Automated validation produces generated artifacts while source control guardrails must still remain clean.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: System MUST provide a capital-based buy-and-hold sizing mode.
- **FR-002**: Buy-and-hold MUST deploy a configurable capital fraction, defaulting to 100% of available starting equity.
- **FR-003**: Buy-and-hold MUST NOT use fixed fractional risk sizing unless the run configuration explicitly selects that behavior.
- **FR-004**: Buy-and-hold baseline results MUST be reported separately from active strategy results.
- **FR-005**: Existing active strategy fixed fractional risk sizing MUST continue to work for non-baseline strategy modes.
- **FR-006**: System MUST enforce no-leverage exposure economically by capping position notional at available equity when leverage is 1.
- **FR-007**: System MUST record every notional cap event in trade assumptions, trade notes, or equivalent auditable output.
- **FR-008**: System MUST include testable behavior for very small stop distances that would otherwise create oversized notional exposure.
- **FR-009**: System MUST compute metrics separately for each strategy mode and each baseline mode.
- **FR-010**: System MUST avoid presenting a global total return as a portfolio result when independent strategy or baseline curves are compared without portfolio-combination mode.
- **FR-011**: Any aggregate comparison summary MUST be labeled as a comparison summary, not as combined portfolio performance.
- **FR-012**: Dashboard and report language MUST state that strategy and baseline modes are independent comparisons unless a future portfolio-combination mode exists.
- **FR-013**: Equity curves for active strategy modes MUST include realized equity and, where close prices are available, mark-to-market total equity during open positions.
- **FR-014**: Drawdown for active strategy curves MUST be based on total equity when mark-to-market total equity is available.
- **FR-015**: If realized-only equity is preserved for compatibility, reports MUST label it clearly as realized-only.
- **FR-016**: System MUST support predefined fee/slippage stress profiles named normal, high_fee, high_slippage, and worst_reasonable_cost.
- **FR-017**: Stress results MUST report each strategy and baseline result under each cost profile.
- **FR-018**: Stress reports MUST state whether each mode remained positive, turned negative, produced no trades, or could not be evaluated under higher costs, without claiming profitability.
- **FR-019**: System MUST support bounded parameter sensitivity grids for grid entry threshold, ATR stop buffer, breakout risk/reward multiple, and fee/slippage profile.
- **FR-020**: Sensitivity results MUST be exportable as a table that includes parameter values, mode identity, key metrics, and fragility indicators.
- **FR-021**: Sensitivity summaries MUST flag results that depend on one isolated parameter setting.
- **FR-022**: System MUST support simple chronological walk-forward validation splits.
- **FR-023**: Walk-forward reports MUST include each split's date range, row count, trade count, and key metrics.
- **FR-024**: Walk-forward validation MUST NOT introduce machine learning training, paper trading, shadow trading, or live trading.
- **FR-025**: Reports MUST include regime bar counts for RANGE, BREAKOUT_UP, BREAKOUT_DOWN, and AVOID when regime labels are available.
- **FR-026**: Reports MUST include trades per regime and return by regime.
- **FR-027**: Reports MUST include percentage of total profit contributed by the top 1, top 5, and top 10 trades.
- **FR-028**: Reports MUST include the best 10 trades, worst 10 trades, maximum consecutive losses, and drawdown recovery time when calculable.
- **FR-029**: If drawdown recovery time is not calculable, reports MUST state why it is unavailable.
- **FR-030**: System MUST support a real-data research validation run using existing BTCUSDT 15m processed features when they are available.
- **FR-031**: If required processed features are missing, the system MUST return clear instructions to download and process data before running a real-data research report.
- **FR-032**: Real-data research reports MUST show data source, date range, row count, input identity, and limitations.
- **FR-033**: Automated repository validation MUST run backend tests, frontend build validation, and generated artifact guard checks without requiring private secrets.
- **FR-034**: Generated validation outputs and report artifacts MUST remain excluded from committed source control.
- **FR-035**: System MUST remain research-only and MUST NOT add live trading, private exchange API keys, broker integration, real order execution, wallet/private-key handling, Rust execution, ClickHouse, PostgreSQL, Kafka, Redpanda, NATS, Kubernetes, machine learning training, paper trading, or shadow trading.
- **FR-036**: Reports and dashboards MUST NOT describe results as proof of profitability, predictive power, safety, or live-trading readiness.

### Key Entities *(include if feature involves data)*

- **ValidationRun**: A research hardening run that ties together corrected backtest outputs, stress profiles, sensitivity grids, walk-forward splits, regime coverage, and generated artifacts.
- **CapitalSizingConfig**: The sizing assumptions for passive and active modes, including buy-and-hold capital fraction, fixed fractional risk settings, leverage assumption, and notional cap behavior.
- **ModeMetrics**: Per-strategy or per-baseline measurements for returns, drawdown, trades, costs, equity, and notes, explicitly separated by mode type.
- **EquityObservation**: A timestamped equity record that can distinguish realized equity, unrealized profit/loss, and total equity where available.
- **CostStressProfile**: A named fee/slippage assumption set used to rerun the same strategy configuration under higher transaction cost conditions.
- **ParameterSensitivityResult**: One row of a controlled parameter sweep, including parameter values, mode identity, metrics, and fragility indicators.
- **WalkForwardSplit**: One chronological validation window with date range, row count, trade count, metrics, and insufficiency notes when applicable.
- **RegimeCoverageReport**: Counts and performance summaries by regime, including bar counts, trades per regime, and return by regime.
- **TradeConcentrationReport**: Concentration and distribution summaries, including top-trade profit contribution, best/worst trades, loss streaks, and drawdown recovery information.
- **RealDataResearchReport**: A validation report produced from existing processed market features, including data source identity, date range, row count, and known limitations.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: Buy-and-hold baseline tests prove that the default baseline deploys 100% of starting equity and does not use fixed fractional risk sizing unless explicitly configured.
- **SC-002**: No-leverage notional cap tests prove that oversized position notional is capped to available equity for at least one very small stop-distance case.
- **SC-003**: Reports for multi-mode runs show separate metrics for 100% of included strategy and baseline modes and do not display an unlabeled global portfolio return.
- **SC-004**: Equity reports for open-position scenarios include realized equity and mark-to-market total equity, or explicitly label realized-only behavior where mark-to-market cannot be computed.
- **SC-005**: A cost stress report evaluates all four required stress profiles for each eligible mode in a validation run.
- **SC-006**: A parameter sensitivity report exports at least one table covering grid entry threshold, ATR stop buffer, breakout risk/reward multiple, and fee/slippage profile variations.
- **SC-007**: A walk-forward report covers at least three chronological windows when the input dataset has enough rows, and marks insufficient windows clearly when it does not.
- **SC-008**: Regime coverage reports include bar counts for all four expected regimes when labels exist and include trades per regime and return by regime.
- **SC-009**: Trade concentration reports include top 1, top 5, and top 10 profit contribution, best 10 trades, worst 10 trades, maximum consecutive losses, and drawdown recovery status.
- **SC-010**: A real BTCUSDT 15m processed-feature validation run can complete when data exists, or returns clear download/process instructions within 5 seconds when data is missing.
- **SC-011**: Automated repository validation completes backend tests, frontend build validation, and generated artifact guard checks without private secrets.
- **SC-012**: Dependency and behavior review confirms no live trading, private keys, broker integration, Rust execution, forbidden storage, event infrastructure, Kubernetes, machine learning training, paper trading, or shadow trading capability is introduced.

## Assumptions

- The completed backtest/reporting MVP remains the foundation for this hardening feature.
- This feature improves research correctness and trustworthiness only; paper trading, shadow trading, and live trading remain out of scope.
- Buy-and-hold capital fraction defaults to 100% because passive baselines should represent full-capital passive exposure unless the researcher chooses otherwise.
- No-leverage means both schema validation and simulated notional exposure are constrained to available equity.
- Mark-to-market equity uses close prices when available; if close prices are unavailable, realized-only equity remains allowed only with explicit labeling.
- Parameter sweeps are intentionally bounded for local research use and are not a large-scale optimization system.
- Walk-forward validation uses chronological splits only and does not train or fit predictive models.
- Real-data validation starts with existing BTCUSDT 15m processed features and should reuse existing provider/data/feature workflows.
- Automated validation must be able to run without private secrets or private exchange credentials.
