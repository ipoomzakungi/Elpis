# Research: Research Data Provider Layer

**Date**: 2026-04-26  
**Feature**: 002-research-data-provider

## Decision: Use a Typed DataProvider Protocol Under `backend/src/providers/`

**Rationale**: A protocol gives the feature a clear provider contract without forcing providers into a heavy inheritance hierarchy. The existing backend already uses simple service classes, so a typed protocol plus concrete provider classes fits the current style and keeps provider-specific details out of feature engineering, regime classification, and dashboard code.

**Alternatives considered**:

- Abstract base class: workable, but heavier than needed for v0 and less flexible for tests/mocks.
- Keep provider logic inside `DataDownloader`: rejected because it would continue hardcoding provider behavior in orchestration.
- Dynamic plugin interface: rejected for v0 because it adds complexity before the project needs external provider plugins.

## Decision: Use a Static Provider Registry for v0

**Rationale**: The feature needs three initial providers with predictable behavior. A static registry exposes provider lookup, listing, and metadata without adding plugin discovery, package loading, or runtime configuration complexity.

**Alternatives considered**:

- Hardcoded if/else provider selection in routes: rejected because it duplicates logic and makes future providers harder to add.
- Entry-point based plugin discovery: rejected as unnecessary for a local v0 research platform.
- Database-backed provider catalog: rejected because v0 forbids adding PostgreSQL and does not need persistent provider configuration.

## Decision: Normalize Provider Outputs to Polars DataFrames Immediately

**Rationale**: The constitution requires Polars as the primary DataFrame engine and timestamp-safe feature calculations. Normalizing every provider output to common Polars schemas creates one downstream contract for storage, feature computation, regime classification, and tests.

**Alternatives considered**:

- Provider-specific DataFrame schemas: rejected because feature engineering would need provider branches.
- Pydantic row objects for all data processing: rejected because Polars is better suited for local columnar research data.
- Pandas as the shared schema: rejected by the constitution except where library compatibility requires it.

## Decision: Use yfinance Only Inside YahooFinanceProvider and Convert Immediately

**Rationale**: Yahoo Finance is explicitly allowed by AGENTS.md for non-execution OHLCV research. yfinance commonly returns pandas-compatible data; this provider will convert the response to the normalized Polars OHLCV schema before anything leaves the provider boundary.

**Alternatives considered**:

- Direct Yahoo chart API calls: possible, but yfinance is the existing allowed package direction and reduces custom HTTP parsing.
- Treat Yahoo Finance as a derivative data provider: rejected because Yahoo Finance must not be used for crypto OI/funding.
- Make Yahoo symbols unrestricted at first: rejected in favor of curated initial symbols and explicit validation.

## Decision: Represent Unsupported Capabilities as Structured Errors and Skipped Results

**Rationale**: The user needs clear unsupported-capability behavior rather than silent empty datasets. Providers should raise a typed unsupported capability error when a caller directly requests unsupported data. Provider-aware download responses can also list skipped data types with explicit reasons when the request asks for multiple data types.

**Alternatives considered**:

- Return empty DataFrames for unsupported data: rejected because it can look like a valid but empty research result.
- Generic 500 errors: rejected because unsupported capability is expected behavior, not a server failure.
- Hide unsupported data types in the frontend only: rejected because API clients also need correct capability feedback.

## Decision: Preserve Existing Binance Filenames While Adding Provider-Aware Naming

**Rationale**: Existing processing and dashboard flows expect files such as `btcusdt_15m_ohlcv.parquet`, `btcusdt_15m_oi.parquet`, and `btcusdt_15m_funding.parquet`. Preserving those aliases for the default Binance BTCUSDT 15m path protects the completed OI Regime Lab while provider-aware filenames support Yahoo Finance and future sources.

**Alternatives considered**:

- Rename all raw files immediately: rejected because it risks breaking existing tests and dashboard behavior.
- Keep only old names for every provider: rejected because symbols like `GC=F` and provider collisions need safer names.
- Store metadata only in DuckDB: rejected because Parquet files remain the v0 source of truth.

## Decision: Add LocalFileProvider Validation Before Import Is Considered Ready

**Rationale**: Local files can come from vendor exports or manual research data, so schema and timestamp validation must happen before downstream research uses them. The provider should validate required OHLCV columns, optional OI/funding columns, timestamp parseability, duplicate timestamps, and missing required values.

**Alternatives considered**:

- Trust local files after reading them: rejected because it hides data-quality problems.
- Require one rigid file schema for all local files: rejected because vendor exports vary, and optional OI/funding columns should be detected when valid.
- Add a full mapping UI now: rejected because the feature asks for validation support, not a full import wizard.

## Decision: Keep Frontend Changes Minimal and Capability-Driven

**Rationale**: The dashboard already renders the research experience. The plan should add provider selection, symbol/timeframe controls, and capability messaging without redesigning charts or layout.

**Alternatives considered**:

- Full dashboard redesign: rejected by user instruction and unnecessary for this provider layer.
- Hide OI/funding panels for unsupported providers: rejected because explicit "Not supported by this provider" messaging better preserves research assumptions.
- Build separate pages per provider: rejected because one provider-aware dashboard is simpler for v0.

## Decision: Keep Feature Engineering Provider-Agnostic and Optional-Derivative Aware

**Rationale**: Feature processing should require OHLCV but not assume every provider has open interest or funding. OI/funding-dependent features are computed only when columns are present, and derivative-dependent outputs are marked unavailable or skipped with a clear reason.

**Alternatives considered**:

- Require OI/funding for all feature processing: rejected because Yahoo Finance and many local OHLCV datasets would fail.
- Create separate feature engines by provider: rejected because it would encode provider logic in research features.
- Drop rows after computing only common features without checking optional fields: rejected because it can accidentally remove all OHLCV-only rows.
