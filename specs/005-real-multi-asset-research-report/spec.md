# Feature Specification: Real Multi-Asset Research Report

**Feature Branch**: `005-real-multi-asset-research-report`  
**Created**: 2026-04-30  
**Status**: Draft  
**Input**: User description: "Add a real multi-asset research report workflow."

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Run Real Multi-Asset Research (Priority: P1)

A researcher can choose a configured set of assets, verify which assets have usable processed feature data, run real-data research reports for the available assets, and receive clear instructions for any missing assets instead of silently falling back to synthetic data.

**Why this priority**: The feature exists to use the completed research platform on real data. The first valuable slice is a repeatable report that works for at least one real crypto asset and clearly identifies blocked assets.

**Independent Test**: Can be tested by starting a multi-asset research run with BTCUSDT and at least one Yahoo Finance proxy asset, with one asset having processed features available and one asset intentionally missing; the report completes available assets and shows missing-data instructions for blocked assets.

**Acceptance Scenarios**:

1. **Given** processed BTCUSDT 15m feature data exists, **When** the researcher runs the default multi-asset research workflow, **Then** the system completes a BTCUSDT research result using real processed features and records the data source, date range, row count, and limitations.
2. **Given** an asset is configured but processed features are missing, **When** the workflow reaches that asset, **Then** the asset is marked as blocked and the report explains which download and feature-processing steps must be completed first.
3. **Given** no configured asset has processed feature data, **When** the researcher starts the workflow, **Then** no synthetic substitute is used and the system returns a report-level missing-data summary.

---

### User Story 2 - Compare Regime Strategies With Baselines (Priority: P2)

A researcher can compare regime-aware grid/range and breakout behavior against price-only baselines for each available asset, while keeping crypto OI/funding research separate from OHLCV-only proxy research.

**Why this priority**: The central research question is whether regime-aware logic adds value compared with price-only approaches. Comparisons must be asset-aware and source-aware to avoid misleading conclusions.

**Independent Test**: Can be tested by running a report on one crypto asset with OI/funding-derived features and one Yahoo Finance proxy asset with OHLCV-only features; the output separates strategy-vs-baseline results for each asset and labels unsupported feature groups.

**Acceptance Scenarios**:

1. **Given** BTCUSDT has price, volume, OI, funding, and regime features, **When** the report is generated, **Then** it includes regime-aware and price-only comparisons and labels OI/funding confirmation as available.
2. **Given** SPY, QQQ, GLD, GC=F, or BTC-USD has OHLCV-only features, **When** the report is generated, **Then** it includes price-based comparison results and clearly labels OI/funding confirmation as not available from that source.
3. **Given** a gold proxy asset is included, **When** the report is reviewed, **Then** the report states that Yahoo Finance proxies do not provide gold options OI, futures OI, or XAU/USD spot execution data.

---

### User Story 3 - Review Robustness Across Assets (Priority: P3)

A researcher can inspect cost stress, parameter sensitivity, walk-forward validation, regime coverage, and trade concentration by asset so weak, fragile, or concentrated results are visible before any future trading work is considered.

**Why this priority**: A research report is not useful if it only shows headline returns. The completed validation hardening must be applied consistently across assets.

**Independent Test**: Can be tested by opening a completed multi-asset report and confirming each available asset has stress, sensitivity, walk-forward, regime coverage, and concentration status, including warnings for fragile or concentrated outcomes.

**Acceptance Scenarios**:

1. **Given** a completed multi-asset report, **When** the researcher reviews the asset summary, **Then** each asset is classified as robust, fragile, missing-data blocked, inconclusive, or not worth continuing based on documented evidence.
2. **Given** an asset's results depend on one narrow parameter setting, **When** parameter sensitivity is reviewed, **Then** the report flags the result as fragile.
3. **Given** an asset's gains are dominated by a few trades or one regime, **When** concentration results are reviewed, **Then** the report shows top-trade contribution and concentration warnings.

---

### User Story 4 - Inspect a Grouped Research Report (Priority: P4)

A researcher can use the dashboard to inspect grouped research runs, compare assets, see missing-data warnings, and open asset-level details without confusing research output with profitability, prediction, safety, or trading readiness.

**Why this priority**: The report must be usable for research decisions, but the dashboard change should remain focused on inspection rather than redesigning the application.

**Independent Test**: Can be tested by opening the research report dashboard view for a completed run and verifying grouped summaries, comparison tables, warnings, source limitations, and research-only disclaimers are visible.

**Acceptance Scenarios**:

1. **Given** a completed multi-asset report exists, **When** the researcher opens the dashboard report view, **Then** the asset summary, strategy-vs-baseline comparison, stress survival, walk-forward, regime coverage, and concentration sections are visible.
2. **Given** some configured assets are missing data, **When** the dashboard report is viewed, **Then** missing-data warnings are grouped by asset and do not block inspection of assets that completed.
3. **Given** any research result is shown, **When** the researcher reads the page, **Then** the page states that results are historical research outputs only and do not imply profitability, predictive power, safety, or live readiness.

### Edge Cases

- All configured assets are missing processed features: produce a report-level blocked status with actionable data-preparation instructions and no synthetic fallback.
- Some assets complete and others are blocked: preserve completed asset results and list blocked assets separately.
- A crypto asset lacks OI or funding columns: label OI/funding confirmation as unavailable or incomplete for that asset while still reporting price-only comparisons if usable.
- A Yahoo Finance proxy asset is requested for OI/funding analysis: mark OI/funding as unsupported by source rather than inferring or fabricating the data.
- Gold or XAU research is requested: use GC=F and GLD only as OHLCV proxies in v0 and document true gold options, futures OI, and spot execution research as future extensions requiring appropriate data.
- Validation produces no trades for an asset or strategy: classify the result as inconclusive or no-trade rather than treating it as success.
- Cost stress, walk-forward, or concentration results conflict with headline metrics: surface the weakness in the asset classification.
- Generated report and data artifacts are created locally: keep them out of version control.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: The system MUST let researchers define a multi-asset research run containing crypto assets and Yahoo Finance or proxy assets.
- **FR-002**: The default crypto primary set MUST include BTCUSDT, ETHUSDT, and SOLUSDT.
- **FR-003**: The system MUST allow optional crypto assets BNBUSDT, XRPUSDT, and DOGEUSDT to be included without making them mandatory for success.
- **FR-004**: The system MUST allow Yahoo Finance or proxy assets SPY, QQQ, GLD, GC=F, and BTC-USD to be included when processed feature data is available.
- **FR-005**: Before running research for an asset, the system MUST check whether required processed feature data exists.
- **FR-006**: If processed features are missing, the system MUST return asset-specific instructions to download and process data first.
- **FR-007**: The system MUST NOT use synthetic data as a substitute for missing real-data research inputs.
- **FR-008**: For each available asset, the system MUST run the existing backtest comparison between regime-aware strategies and relevant baselines.
- **FR-009**: For each available asset, the system MUST run validation hardening that includes cost stress, parameter sensitivity, walk-forward validation, regime coverage, and trade concentration.
- **FR-010**: The system MUST compare regime-aware grid/range logic against price-only baselines for RANGE regime research when required feature data exists.
- **FR-011**: The system MUST compare regime-aware breakout logic against price-only breakout baselines for BREAKOUT regime research when required feature data exists.
- **FR-012**: The system MUST distinguish crypto OI/funding/volume confirmation research from OHLCV-only Yahoo Finance and proxy research.
- **FR-013**: The system MUST label OI and funding as unsupported for Yahoo Finance and proxy assets unless real OI/funding source data is explicitly present.
- **FR-014**: The system MUST document GC=F and GLD as initial gold OHLCV proxies and MUST NOT represent them as gold options OI, futures OI, or XAU/USD spot execution data.
- **FR-015**: The system MUST document a gold IV/OI wall engine as a future extension unless appropriate CME, QuikStrike, COT, CME options, or equivalent data is available.
- **FR-016**: The system MUST save a multi-asset summary report with asset-level status, source identity, date range, row count, strategy comparisons, validation results, warnings, and limitations.
- **FR-017**: The report MUST classify each asset as robust, fragile, missing-data blocked, inconclusive, or not worth continuing based on documented research evidence.
- **FR-018**: The report MUST show stress-test survival by asset and identify cases where higher costs materially change results.
- **FR-019**: The report MUST show parameter sensitivity by asset and flag results that depend on isolated parameter settings.
- **FR-020**: The report MUST show walk-forward results by asset and identify assets with inconsistent time-window performance.
- **FR-021**: The report MUST show regime coverage by asset, including bar counts and trade activity by regime.
- **FR-022**: The report MUST show trade concentration warnings by asset, including top-trade contribution where available.
- **FR-023**: The dashboard MUST provide a grouped research report view with asset-level summary, strategy-vs-baseline comparison, stress survival, walk-forward results, regime coverage, concentration warnings, missing-data warnings, and source limitations.
- **FR-024**: The dashboard and report MUST state that outputs are research results under assumptions and do not claim profitability, predictive power, safety, or live readiness.
- **FR-025**: Generated research reports and generated data artifacts MUST remain local research outputs and MUST NOT be committed.
- **FR-026**: The feature MUST NOT add live trading, paper trading, shadow trading, private exchange keys, broker integration, real order execution, wallet handling, new execution engines, new analytical infrastructure, orchestration platforms, or model training.

### Key Entities

- **Multi-Asset Research Run**: A grouped research execution request and result set covering configured assets, assumptions, run status, completed assets, blocked assets, warnings, and generated report references.
- **Research Asset**: A configured market or proxy asset with symbol, provider/source category, asset class, feature availability, required data status, and source limitations.
- **Asset Research Result**: The per-asset output containing data identity, strategy-vs-baseline comparison, validation hardening results, classification, warnings, and limitations.
- **Strategy Comparison**: A per-asset comparison of regime-aware grid/range and breakout logic against applicable price-only or passive baselines.
- **Validation Summary**: A per-asset summary of stress costs, parameter sensitivity, walk-forward results, regime coverage, and trade concentration.
- **Missing Data Instruction**: A structured explanation of what data is missing for an asset and what the researcher must do before the asset can be included.
- **Source Limitation**: A documented boundary explaining which market features are available from a source and which are unsupported or future work.
- **Grouped Research Report**: A persisted summary artifact that combines asset-level results, cross-asset conclusions, blocked assets, limitations, and research-only disclaimers.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: A researcher can run a multi-asset research report including BTCUSDT in under 5 minutes once processed BTCUSDT features are already available.
- **SC-002**: When processed BTCUSDT features exist, the report completes a BTCUSDT real-data result with source identity, date range, row count, strategy comparison, and validation sections.
- **SC-003**: When at least one Yahoo Finance or proxy asset has processed OHLCV features, the report completes that asset's OHLCV-only comparison and labels OI/funding as unsupported.
- **SC-004**: For missing configured assets, 100% of blocked assets include clear download/process instructions and no synthetic fallback is used.
- **SC-005**: The grouped report contains asset-level rows for every configured asset, with each row marked completed, blocked, inconclusive, fragile, robust, or not worth continuing.
- **SC-006**: The grouped report includes strategy-vs-baseline, stress survival, walk-forward, regime coverage, and concentration summaries for every completed asset.
- **SC-007**: The dashboard report view displays the asset summary, strategy-vs-baseline comparison, stress table, walk-forward table, regime coverage table, concentration warnings, missing-data warnings, and source limitations for a completed report.
- **SC-008**: The report and dashboard include research-only disclaimers on every grouped report view and do not contain claims of profitability, predictive power, safety, or live readiness.
- **SC-009**: Generated research outputs remain excluded from version control after a completed report run.
- **SC-010**: The workflow supports at least the three primary crypto assets and five Yahoo Finance or proxy assets as configurable research targets, even when some are blocked by missing local data.

## Assumptions

- Feature 005 uses the completed provider, backtest, reporting, and validation hardening capabilities from features 002 through 004 rather than adding a new research engine.
- The first successful real-data run is expected to use locally available processed features; this feature does not guarantee that all listed assets already have historical data prepared.
- BTCUSDT is the minimum required crypto success target when processed features are available.
- SPY or GC=F is the minimum required Yahoo Finance or proxy success target when processed OHLCV features are available.
- Binance public futures data remains the v0 source for crypto OI and funding research, with known limitations that must be shown in reports.
- Yahoo Finance and proxy assets are OHLCV-only unless another validated public data source provides additional features.
- GC=F and GLD are acceptable v0 gold OHLCV proxies, not substitutes for gold options OI, futures OI, implied-volatility walls, or XAU/USD spot execution data.
- Multi-asset conclusions are comparative research summaries, not portfolio allocation advice or trading recommendations.
- Report artifacts and generated data remain local and excluded from commits.
