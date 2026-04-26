# Implementation Plan: OI Regime Lab v0

**Branch**: `001-oi-regime-lab` | **Date**: 2026-04-26 | **Spec**: [spec.md](spec.md)
**Input**: Feature specification from `/specs/001-oi-regime-lab/spec.md`

## Summary

Build a local research dashboard for validating whether Open Interest, funding rate, volume, and price range features can classify crypto market regimes (RANGE, BREAKOUT_UP, BREAKOUT_DOWN, AVOID). The system downloads BTCUSDT 15m data from Binance Futures, computes features, classifies regimes, and displays results in a web dashboard. This is a v0 research-only implementation with no live trading.

## Technical Context

**Language/Version**: Python 3.11+, TypeScript 5.x
**Primary Dependencies**: FastAPI, Pydantic, Polars, DuckDB, Next.js, Tailwind CSS, lightweight-charts, Recharts
**Storage**: DuckDB (data/elpis.duckdb) + Parquet files (data/raw, data/processed)
**Testing**: pytest (backend), Jest/Vitest (frontend)
**Target Platform**: Local development (Windows/macOS/Linux)
**Project Type**: Web application (frontend + backend)
**Performance Goals**: Download 30 days of data in <2 min, process in <30 sec, dashboard loads in <5 sec
**Constraints**: No private API keys, no live trading, no Rust/ClickHouse/Kafka/Kubernetes/ML in v0
**Scale/Scope**: Single user, single symbol (BTCUSDT), single timeframe (15m), 30+ days history

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Principle | Status | Notes |
|-----------|--------|-------|
| I. Research-First Architecture | ✅ PASS | System is research dashboard, not live trading bot |
| II. Language Split | ✅ PASS | Python for research, TypeScript for frontend, no Rust |
| III. Frontend Stack | ✅ PASS | Next.js, TypeScript, Tailwind, lightweight-charts/Recharts |
| IV. Backend Stack | ✅ PASS | FastAPI with Pydantic schemas |
| V. Data Processing | ✅ PASS | Polars as primary DataFrame engine |
| VI. Storage v0 | ✅ PASS | DuckDB + Parquet for local research storage |
| VII. Storage v1+ | ✅ N/A | Not using PostgreSQL/ClickHouse in v0 |
| VIII. Event Architecture | ✅ PASS | No Kafka/Redpanda/NATS in v0 |
| IX. Data-Source Principle | ✅ PASS | Binance official API first |
| X. TradingView Principle | ✅ N/A | Not using TradingView in this feature |
| XI. Reliability Principle | ✅ PASS | Multi-layer validation (feature, regime, risk, logging) |
| XII. Live Trading Principle | ✅ PASS | No live trading, research only |

**Gate Result**: PASS - All applicable principles satisfied. No violations requiring justification.

## Project Structure

### Documentation (this feature)

```text
specs/001-oi-regime-lab/
├── plan.md              # This file (/speckit.plan command output)
├── research.md          # Phase 0 output
├── data-model.md        # Phase 1 output
├── quickstart.md        # Phase 1 output
├── contracts/           # Phase 1 output
│   └── api.md           # REST API contracts
└── tasks.md             # Phase 2 output (/speckit.tasks command)
```

### Source Code (repository root)

```text
backend/
├── pyproject.toml
├── src/
│   ├── __init__.py
│   ├── main.py              # FastAPI app entry point
│   ├── config.py            # Configuration settings
│   ├── models/
│   │   ├── __init__.py
│   │   ├── market_data.py   # OHLCV, OI, FundingRate Pydantic models
│   │   ├── features.py      # Feature computation models
│   │   └── regime.py        # Regime classification models
│   ├── services/
│   │   ├── __init__.py
│   │   ├── binance_client.py    # Binance API client
│   │   ├── data_downloader.py   # Data download orchestration
│   │   ├── feature_engine.py    # Feature computation
│   │   ├── regime_classifier.py # Regime classification logic
│   │   └── data_quality.py      # Data quality checks
│   ├── repositories/
│   │   ├── __init__.py
│   │   ├── parquet_repo.py      # Parquet file operations
│   │   └── duckdb_repo.py       # DuckDB operations
│   └── api/
│       ├── __init__.py
│       ├── routes/
│       │   ├── market_data.py   # Market data endpoints
│       │   ├── features.py      # Feature endpoints
│       │   ├── regimes.py       # Regime endpoints
│       │   └── data_quality.py  # Data quality endpoints
│       └── dependencies.py      # FastAPI dependencies
└── tests/
    ├── unit/
    ├── integration/
    └── contract/

frontend/
├── package.json
├── tsconfig.json
├── tailwind.config.ts
├── src/
│   ├── app/
│   │   ├── layout.tsx
│   │   ├── page.tsx
│   │   └── globals.css
│   ├── components/
│   │   ├── charts/
│   │   │   ├── CandlestickChart.tsx
│   │   │   ├── OIChart.tsx
│   │   │   ├── FundingChart.tsx
│   │   │   └── VolumeChart.tsx
│   │   ├── panels/
│   │   │   ├── RegimePanel.tsx
│   │   │   └── DataQualityPanel.tsx
│   │   └── ui/
│   │       ├── Header.tsx
│   │       └── LoadingSpinner.tsx
│   ├── services/
│   │   └── api.ts           # API client
│   ├── hooks/
│   │   └── useMarketData.ts # Data fetching hooks
│   └── types/
│       └── index.ts         # TypeScript types
└── tests/

data/
├── raw/                 # Raw downloaded Parquet files
│   ├── btcusdt_15m_ohlcv.parquet
│   ├── btcusdt_15m_oi.parquet
│   └── btcusdt_15m_funding.parquet
├── processed/           # Processed feature data
│   └── btcusdt_15m_features.parquet
├── reports/             # Generated reports
└── elpis.duckdb         # DuckDB database file
```

**Structure Decision**: Web application with separate backend (Python/FastAPI) and frontend (Next.js/TypeScript). Data stored in Parquet files with DuckDB for SQL queries.

## Complexity Tracking

> **No violations requiring justification** - All constitution principles are satisfied.
