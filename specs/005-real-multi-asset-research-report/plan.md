# Implementation Plan: Real Multi-Asset Research Report

**Branch**: `005-real-multi-asset-research-report` | **Date**: 2026-04-30 | **Spec**: [spec.md](./spec.md)  
**Input**: Feature specification from `specs/005-real-multi-asset-research-report/spec.md`

## Summary

Feature 005 turns the completed provider, backtest, and validation subsystems into a real multi-asset research workflow. The implementation adds a small orchestration and aggregation layer that preflights processed feature availability, runs existing backtest and validation hardening per available asset, records missing-data blockers per unavailable asset, and writes grouped research reports under `data/reports`. Dashboard work stays focused on inspecting grouped research reports and does not redesign the app.

## Technical Context

**Language/Version**: Python 3.11+ backend and TypeScript dashboard, matching existing repository  
**Primary Dependencies**: Existing FastAPI, Pydantic, Polars, DuckDB, Parquet, Next.js, TypeScript, Tailwind, Recharts/lightweight-charts stack  
**Storage**: Existing local research folders: `data/raw`, `data/processed`, and `data/reports`; no server database  
**Testing**: Existing pytest backend tests, frontend production build, and artifact guard script  
**Target Platform**: Local research workstation workflow with public data sources only  
**Project Type**: Existing backend API plus dashboard web application  
**Performance Goals**: Complete a small configured research run with BTCUSDT and one proxy asset in under 5 minutes when processed features already exist  
**Constraints**: Research-only; no synthetic fallback for missing real data; no live trading, paper trading, shadow trading, private keys, broker integration, real execution, Rust, ClickHouse, PostgreSQL, Kafka, Kubernetes, or ML training  
**Scale/Scope**: v0 multi-asset research set: primary crypto assets BTCUSDT, ETHUSDT, SOLUSDT; optional crypto assets BNBUSDT, XRPUSDT, DOGEUSDT; Yahoo/proxy assets SPY, QQQ, GLD, GC=F, BTC-USD

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

- **Research-first architecture**: PASS. The feature runs historical research reports only and does not introduce execution behavior.
- **Language split**: PASS. Uses existing Python research backend and TypeScript dashboard. No Rust execution engine is added.
- **Frontend stack**: PASS. Dashboard changes remain inside the existing Next.js/TypeScript UI.
- **Backend stack**: PASS. Uses existing FastAPI/Pydantic backend patterns.
- **Data processing**: PASS. Uses existing processed feature Parquet data and Polars-based validation/backtest flows.
- **Storage v0**: PASS. Generated outputs remain under local `data/reports`; generated data remains under `data/raw` and `data/processed`.
- **Event architecture**: PASS. No Kafka, Redpanda, NATS, or Kubernetes.
- **Data-source principle**: PASS. Reuses existing provider metadata and documents Binance/Yahoo/local-file capability limits.
- **Reliability principle**: PASS. Adds preflight and source-limitation reporting before any interpretation.
- **Live trading principle**: PASS. Explicitly excludes live, paper, and shadow trading.

No constitution violations require complexity tracking.

## Project Structure

### Documentation (this feature)

```text
specs/005-real-multi-asset-research-report/
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

### Source Code (repository root)

```text
backend/
|-- src/
|   |-- research/
|   |   |-- __init__.py
|   |   |-- orchestration.py      # Multi-asset run coordinator
|   |   |-- preflight.py          # Processed-feature and capability checks
|   |   |-- aggregation.py        # Cross-asset summary and classifications
|   |   `-- report_store.py       # Grouped research report persistence
|   |-- models/
|   |   `-- research.py           # Research config and response schemas
|   |-- api/
|   |   `-- routes/
|   |       `-- research.py       # Research report endpoints
|   |-- providers/                # Existing provider layer reused
|   |-- backtest/                 # Existing engine and validation reused
|   `-- reports/                  # Existing writers extended for grouped reports
|-- tests/
|   |-- unit/
|   |   |-- test_research_config.py
|   |   |-- test_research_capabilities.py
|   |   `-- test_research_preflight.py
|   |-- integration/
|   |   |-- test_research_crypto_flow.py
|   |   `-- test_research_yahoo_flow.py
|   `-- contract/
|       `-- test_research_api_contracts.py

frontend/
|-- src/
|   |-- app/
|   |   `-- research/
|   |       `-- page.tsx          # Grouped report inspection page
|   |-- services/
|   |   `-- api.ts                # Research endpoint client methods
|   `-- types/
|       `-- index.ts              # Research report types
```

**Structure Decision**: Add a narrow `backend/src/research/` package for orchestration and aggregation only. Existing provider, backtest, validation, and report code remains the source of truth for data access and single-asset research behavior. Add a focused dashboard page for grouped research reports rather than redesigning `/backtests`.

## Data Preflight Flow

1. Read requested assets from `ResearchRunRequest`.
2. Resolve provider capability metadata for each asset using the existing provider registry.
3. Determine expected processed feature path using existing feature naming conventions unless an explicit feature path is supplied.
4. Check whether processed feature Parquet exists and can be read.
5. Inspect required columns:
   - All assets: timestamp, open, high, low, close, volume.
   - Regime research: regime, range boundaries, ATR where required by strategy config.
   - Crypto confirmation: OI/funding columns when provider supports and feature file contains them.
6. Mark each asset as:
   - `ready`: usable for the configured research workflow.
   - `missing_data`: processed feature file does not exist.
   - `incomplete_features`: file exists but required columns are missing.
   - `unsupported_capability`: requested OI/funding research is not supported by source.
7. Return actionable missing-data instructions and continue only with ready assets.

## Research Orchestration Flow

1. Create a grouped research run id and persist the normalized request.
2. Run preflight for all configured assets.
3. For each ready asset:
   - Build the existing single-asset backtest/validation request using the asset feature path and source capabilities.
   - Run existing backtest comparison and validation hardening.
   - Read validation sections and single-asset report metadata from existing stores.
   - Aggregate per-asset result into the grouped report.
4. For each blocked asset:
   - Persist blocker status, missing-data instructions, and source limitation notes.
5. Compute cross-asset summary:
   - strategy-vs-baseline comparison by asset.
   - stress survival by asset.
   - walk-forward stability by asset.
   - regime coverage by asset.
   - trade concentration warnings by asset.
   - source capability and limitation matrix.
6. Persist grouped report artifacts under `data/reports/{research_run_id}/`.
7. Expose list/detail/section endpoints and dashboard views for inspection.

## Asset Capability Matrix

| Provider/source | Example assets | OHLCV | OI | Funding | v0 research use | Required limitation text |
|-----------------|----------------|-------|----|---------|-----------------|--------------------------|
| Binance public USD-M futures | BTCUSDT, ETHUSDT, SOLUSDT, optional crypto symbols | Yes | Yes | Yes | Crypto regime research with OI/funding/volume confirmation where processed features exist | Binance official OI/funding history is acceptable for v0 but not enough for serious multi-year derivatives research |
| Yahoo Finance | SPY, QQQ, GLD, GC=F, BTC-USD | Yes | No | No | OHLCV-only proxy/baseline comparison | Yahoo Finance does not provide crypto OI/funding, gold options OI, futures OI, or XAU/USD spot execution data |
| Local file | User imported CSV/Parquet | Schema-dependent | Schema-dependent | Schema-dependent | Research datasets with explicit schema validation | Capabilities are based only on validated columns in the imported file |

## Research Config Schema

The plan introduces Pydantic schemas under `backend/src/models/research.py`:

- `ResearchRunRequest`: grouped run config, default asset groups, assumptions, strategy set, validation config, and report format.
- `ResearchAssetConfig`: symbol, provider, asset class, optional feature path, enabled flag, required feature groups, and display label.
- `ResearchCapabilitySnapshot`: provider capability and detected feature-column availability.
- `ResearchPreflightResult`: asset readiness, missing data instructions, unsupported capability notes, and source limitations.
- `ResearchAssetResult`: per-asset run status, linked validation run id, metrics summaries, validation summaries, classification, warnings, and artifacts.
- `ResearchRun`: grouped run metadata, configured assets, completed assets, blocked assets, cross-asset summary, warnings, limitations, and artifacts.
- `ResearchRunSummary`: list-row representation for dashboard selectors.

## Report Aggregation Schema

Grouped report artifacts:

- `research_metadata.json`: canonical `ResearchRun` metadata and summary.
- `research_config.json`: normalized request.
- `asset_summary.parquet`: one row per configured asset.
- `strategy_comparison.parquet`: per asset and strategy/baseline mode.
- `stress_summary.parquet`: stress survival and cost sensitivity by asset.
- `walk_forward_summary.parquet`: chronological split stability by asset.
- `regime_coverage_summary.parquet`: regime bar/trade/return coverage by asset.
- `concentration_summary.parquet`: top-trade contribution and concentration warnings by asset.
- `research_report.json`: dashboard-ready report payload.
- `research_report.md`: human-readable research report with limitations and disclaimers.

## API Design

Planned v0 endpoints:

- `POST /api/v1/research/runs`: run a synchronous local multi-asset research report.
- `GET /api/v1/research/runs`: list saved grouped research reports.
- `GET /api/v1/research/runs/{research_run_id}`: read grouped report metadata and summary.
- `GET /api/v1/research/runs/{research_run_id}/assets`: read asset-level summary rows.
- `GET /api/v1/research/runs/{research_run_id}/comparison`: read strategy/baseline comparison rows.
- `GET /api/v1/research/runs/{research_run_id}/validation`: read stress, sensitivity, walk-forward, regime, and concentration summary sections.

Errors must distinguish missing processed features, incomplete features, unsupported capability requests, invalid config, and missing reports. No endpoint may require authentication secrets, private exchange credentials, broker credentials, or execution permissions in v0.

## Dashboard Design

Add a focused research report page at `/research` with existing visual style:

- Run selector and status summary.
- Asset-level summary table with capability badges.
- Missing-data warning panel with action instructions.
- Strategy-vs-baseline comparison by asset.
- Stress-test survival table by asset.
- Walk-forward stability table by asset.
- Regime coverage table by asset.
- Trade concentration warnings by asset.
- Source limitation panel for Binance, Yahoo Finance, local files, and gold proxy assets.
- Research-only disclaimer visible on grouped report view.

## Test Strategy

- Unit tests:
  - Research config validation and forbidden live-trading field rejection.
  - Asset capability handling for Binance, Yahoo Finance, and local files.
  - Missing-data preflight for absent files, incomplete features, and unsupported OI/funding requests.
  - Aggregation classification for robust, fragile, blocked, inconclusive, and not-worth-continuing outcomes.
- Integration tests:
  - One synthetic crypto-like processed feature file exercising crypto capability paths.
  - One Yahoo OHLCV-only processed feature file exercising unsupported OI/funding labeling.
  - Mixed run with one completed asset and one missing-data blocked asset.
  - Generated artifact guard after report creation.
- Contract tests:
  - Research run/list/detail endpoints and section endpoints.
  - Structured error responses for missing processed features and unsupported capabilities.
- Frontend checks:
  - TypeScript build.
  - Dashboard smoke for grouped report selector, asset summary, missing-data warning, capability badges, and validation summary tables.
- Regression checks:
  - Existing backend tests must continue passing.
  - Existing `/backtests`, `/backtests/validation`, and provider endpoints remain compatible.

## Implementation Phases

1. **Foundation**: Add research models, preflight helpers, report store skeleton, and API route skeletons.
2. **Asset Preflight MVP**: Implement provider capability detection, processed feature existence checks, missing-data instructions, and config validation tests.
3. **Single Crypto Research Slice**: Run BTCUSDT through existing validation/backtest flow and persist grouped report artifacts.
4. **Yahoo OHLCV Slice**: Add OHLCV-only proxy support and unsupported OI/funding labeling for Yahoo assets.
5. **Aggregation**: Add asset summary, comparison, stress, walk-forward, regime, and concentration aggregation.
6. **API Contracts**: Complete run/list/detail/section endpoints and structured errors.
7. **Dashboard Inspection**: Add `/research` grouped report view with tables, capability badges, warnings, and disclaimers.
8. **Final Validation**: Run backend tests, frontend build, artifact guard, API smoke, dashboard smoke, and forbidden-scope review.

## Constitution Check: Post-Design

- **Research-first architecture**: PASS. The design orchestrates existing historical research and explicitly avoids trading workflows.
- **Language split**: PASS. No Rust or execution engine is introduced.
- **Frontend stack**: PASS. Existing dashboard stack is extended minimally.
- **Backend stack**: PASS. Uses existing API/schema patterns.
- **Data processing**: PASS. Uses existing processed feature files and Polars-compatible outputs.
- **Storage v0**: PASS. Uses local generated artifacts under `data/reports` and existing data folders.
- **Storage v1+ avoidance**: PASS. No PostgreSQL or ClickHouse.
- **Event architecture**: PASS. No Kafka, Redpanda, NATS, Kubernetes, or service redesign.
- **Data-source principle**: PASS. Provider capability limits and Yahoo/gold proxy limitations are explicit.
- **Reliability and live-trading principles**: PASS. Adds research validation and reporting only; no paper, shadow, live, broker, wallet, private-key, or order-execution behavior.

## Complexity Tracking

No constitution violations are introduced.
