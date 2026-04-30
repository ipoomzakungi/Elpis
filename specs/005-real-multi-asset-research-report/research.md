# Research: Real Multi-Asset Research Report

**Date**: 2026-04-30  
**Feature**: 005-real-multi-asset-research-report

## Decision 1: Add Orchestration, Not a New Research Engine

**Decision**: Add a small `backend/src/research/` package that orchestrates existing provider, backtest, validation, and report-store components.

**Rationale**: Features 002 through 004 already provide provider metadata, processed-feature inputs, backtests, validation hardening, and report artifacts. Feature 005 should use those capabilities for real research rather than duplicating strategy, validation, or storage behavior.

**Alternatives considered**:

- Rebuild a multi-asset backtest engine: rejected because it would duplicate validated single-asset logic and increase risk.
- Add a batch job framework: rejected because v0 is local research and does not need queue or worker infrastructure.

## Decision 2: Preflight All Assets Before Running Available Assets

**Decision**: Run a full preflight over every configured asset before executing backtests for ready assets.

**Rationale**: The feature must clearly distinguish completed, blocked, incomplete, and unsupported assets. A complete preflight provides a predictable report shape even when only some assets have processed features available.

**Alternatives considered**:

- Fail the whole report on the first missing asset: rejected because mixed availability is expected during real research.
- Silently skip missing assets: rejected because the user needs actionable data-preparation instructions.

## Decision 3: Use Provider Capabilities Plus Detected Feature Columns

**Decision**: Determine asset capability from both provider metadata and processed feature columns.

**Rationale**: Provider capabilities explain what the source can support, while file columns explain what this specific processed dataset actually contains. Local files are schema-dependent, and Binance features may still be incomplete if a processing step failed.

**Alternatives considered**:

- Trust provider metadata only: rejected because it cannot identify incomplete processed feature files.
- Trust columns only: rejected because source limitations such as Yahoo OHLCV-only behavior must remain visible.

## Decision 4: Persist Grouped Reports Under `data/reports`

**Decision**: Store grouped research artifacts under `data/reports/{research_run_id}/` alongside existing backtest and validation reports.

**Rationale**: Existing artifact guard and report-store patterns already protect generated report output from commits. Keeping all report artifacts in one local research tree simplifies inspection and cleanup.

**Alternatives considered**:

- Store reports under a new top-level directory: rejected because it would require new ignore and guard rules.
- Store only in memory: rejected because reports must be reproducible and inspectable after the run.

## Decision 5: Classify Assets With Evidence-Based Status Labels

**Decision**: Classify each asset as `robust`, `fragile`, `missing_data`, `inconclusive`, or `not_worth_continuing`.

**Rationale**: The user asked for practical research interpretation without profitability claims. Status labels summarize evidence from stress, sensitivity, walk-forward, regime coverage, and concentration checks while staying within research-only language.

**Alternatives considered**:

- Use pass/fail labels: rejected because research results often have mixed evidence.
- Use profitability labels: rejected because the project must not claim profitability or live readiness.

## Decision 6: Add a Focused `/research` Dashboard Page

**Decision**: Add a new `/research` page for grouped research report inspection instead of expanding `/backtests` further.

**Rationale**: `/backtests` already displays single-run and validation details. A grouped multi-asset report has a different browsing model: asset summary first, then cross-asset comparison. A focused page avoids a broad dashboard redesign.

**Alternatives considered**:

- Extend `/backtests` with grouped research sections: possible, but risks crowding an already dense page.
- Redesign the whole dashboard navigation: rejected by scope.

## Decision 7: Treat Yahoo Gold Proxies as OHLCV-Only

**Decision**: GC=F and GLD are documented as v0 OHLCV proxies only. Gold options OI, futures OI, implied-volatility wall analysis, and XAU/USD spot execution data remain future extensions requiring appropriate data sources.

**Rationale**: Yahoo Finance does not provide the derivative and spot execution datasets needed for those claims. The report must not imply data coverage that is not present.

**Alternatives considered**:

- Infer gold OI or options behavior from OHLCV proxies: rejected as misleading.
- Block all gold research until institutional data exists: rejected because OHLCV proxy comparison is still useful when clearly labeled.

## Decision 8: Reuse Existing Validation Hardening Defaults

**Decision**: Use feature 004 validation defaults for cost stress, parameter sensitivity, walk-forward, regime coverage, and concentration unless the research config overrides them.

**Rationale**: These defaults have already been tested and documented. Feature 005 should aggregate them across assets rather than inventing new robustness criteria.

**Alternatives considered**:

- Add new robustness algorithms: rejected as new scope.
- Run only headline backtests: rejected because the purpose is real research trustworthiness.
