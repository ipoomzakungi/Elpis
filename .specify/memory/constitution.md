<!--
  Sync Impact Report
  ==================
  Version change: N/A → 1.0.0 (initial ratification)
  Modified principles: N/A (new constitution)
  Added sections:
    - Core Principles (12 principles)
    - Technology Stack Details
    - Development Workflow
    - Governance
  Removed sections: N/A
  Templates requiring updates:
    - .specify/templates/plan-template.md ✅ compatible (Constitution Check section exists)
    - .specify/templates/spec-template.md ✅ compatible (no constitution-specific refs)
    - .specify/templates/tasks-template.md ✅ compatible (no constitution-specific refs)
  Follow-up TODOs: None
-->

# Elpis Constitution

## Core Principles

### I. Research-First Architecture

The system MUST begin as a research and validation platform, NOT a live
trading bot. The first goal is to prove or reject strategy logic using
reliable data, reproducible backtests, and visual/statistical dashboards.

**Rationale**: Premature live trading without validated logic leads to
capital loss. Research-first ensures strategies are proven before risk.

### II. Language Split

Python MUST be used for research, data processing, feature engineering,
backtesting, reporting, and orchestration.

Rust MUST be used only for latency-sensitive or reliability-sensitive
execution components: exchange adapters, local order books, risk checks,
order routing, and live/paper trading state machines.

TypeScript MUST be used for the web dashboard and user interface.

**Rationale**: Python enables fast iteration for research. Rust provides
deterministic performance for execution. TypeScript ensures type-safe UI.

### III. Frontend Stack

The dashboard MUST use Next.js, TypeScript, Tailwind CSS, and charting
libraries such as lightweight-charts or Recharts.

The dashboard MUST inspect: market data, OI zones, regimes, trades,
equity curves, drawdowns, and parameter robustness.

**Rationale**: Next.js provides SSR/SSG for dashboards. Tailwind enables
rapid styling. Charting libraries handle financial visualization.

### IV. Backend Stack

The research API MUST use FastAPI with Pydantic schemas.

The backend MUST expose endpoints for: market data, features, regimes,
backtest runs, trades, metrics, and data-quality checks.

**Rationale**: FastAPI provides async performance and auto-generated docs.
Pydantic ensures type-safe request/response validation.

### V. Data Processing

Polars MUST be the primary DataFrame engine. Pandas MAY be used only when
library compatibility requires it.

All feature calculations MUST be reproducible and timestamp-safe.

**Rationale**: Polars offers Rust-level performance with Python ergonomics.
Reproducibility ensures backtest integrity.

### VI. Storage v0

DuckDB and Parquet MUST be used for local research storage.

Raw data, processed data, features, backtest results, and reports MUST be
stored in a reproducible folder structure.

**Rationale**: DuckDB provides fast local SQL over Parquet without server
overhead. Parquet is columnar and compressed for efficient storage.

### VII. Storage v1+

PostgreSQL MUST be used for authoritative application state, ledger events,
configuration, run metadata, and reconciliation records.

ClickHouse MUST be used for large-scale market data, execution analytics,
dashboard queries, and replay analysis.

**Rationale**: PostgreSQL ensures ACID compliance for ledger. ClickHouse
handles high-volume analytical queries efficiently.

### VIII. Event Architecture

Kafka, Redpanda, or NATS MUST NOT be required in v0.

They MAY be introduced only when durable replay, high-volume streaming,
or multi-service fan-out becomes necessary.

**Rationale**: Event systems add operational complexity. Introduce only
when scale demands it.

### IX. Data-Source Principle

Exchange-native official APIs MUST be used first for live and near-live
data. Binance is acceptable for v0 crypto OI monitoring.

Bybit, OKX, Deribit, and vendor data (Kaiko, Tardis) SHOULD be considered
for serious multi-year research.

**Rationale**: Official APIs provide reliable, sanctioned data. Vendor
data enables broader historical coverage.

### X. TradingView Principle

TradingView/Pine Script MAY be used for visualization, idea prototyping,
and manual inspection.

TradingView MUST NOT be treated as the production source of truth for
execution, backtesting realism, or multi-exchange strategy validation.

**Rationale**: TradingView excels at visual analysis but lacks the
programmatic rigor required for production trading systems.

### XI. Reliability Principle

No live or paper execution decision may be made from raw connector output
alone.

Signals MUST pass through: feature validation, regime classification, risk
checks, stale-data checks, and logging.

**Rationale**: Raw data is unreliable. Multi-layer validation prevents
erroneous execution decisions.

### XII. Live Trading Principle

Live trading is NOT allowed until the system has passed ALL of:

- Historical backtest validation
- Data-quality checks
- Paper/shadow trading
- Fee/slippage validation
- Risk-limit validation

**Rationale**: Each gate catches different failure modes. Skipping any
gate increases probability of capital loss.

## Technology Stack Details

### v0 — Research Dashboard

```text
Frontend:
    Next.js
    TypeScript
    Tailwind
    lightweight-charts or Recharts

Backend:
    Python
    FastAPI
    Pydantic
    Polars
    DuckDB
    Parquet

Data:
    Binance official API
    Bybit official API later
    OKX later
```

### v1 — Serious Research / Larger Data

```text
DuckDB + Parquet
→ ClickHouse for fast analytics
→ PostgreSQL for structured app state
```

ClickHouse is required when: many symbols, many timeframes, tick/order-book
data, many backtest runs, or large dashboards.

### v2 — Live/Paper Execution

```text
Rust:
    exchange adapters
    websocket collectors
    local order book
    risk engine
    order router
    paper/live execution state machine
```

### v3 — ML Overlay

```text
ML models
vendor OI data
real live canary
```

### Prohibited in v0

The following MUST NOT be introduced in v0:

- Kafka
- Kubernetes
- Microservices
- Rust everywhere
- ClickHouse from day one
- ML platform
- Live trading bot

## Development Workflow

### Phase Progression

Development MUST follow the v0 → v1 → v2 → v3 progression. Each phase
MUST be validated before advancing to the next.

### Validation Gates

Before advancing from v0 to v1:

- Research dashboard fully functional
- Backtest engine validated with historical data
- Data-quality checks implemented and passing
- Parameter robustness testing complete

Before advancing from v1 to v2:

- PostgreSQL ledger operational
- ClickHouse analytics queries optimized
- Multi-exchange data ingestion validated
- Backtest report system complete

Before advancing from v2 to v3:

- Paper trading running reliably
- Risk engine validated
- Order router tested
- Shadow trading matches backtest expectations

## Governance

This constitution supersedes all other development practices for the Elpis
project. Any deviation from these principles MUST be documented with:

1. Justification for the deviation
2. Risk assessment
3. Mitigation plan
4. Approval from project owner

Amendments to this constitution MUST:

1. Be documented in this file
2. Increment the version number (MAJOR.MINOR.PATCH)
3. Update the Last Amended date
4. Propagate changes to dependent templates

Compliance reviews MUST occur:

- Before each phase transition
- When introducing new technologies
- When modifying core architecture decisions

**Version**: 1.0.0 | **Ratified**: 2026-04-26 | **Last Amended**: 2026-04-26
