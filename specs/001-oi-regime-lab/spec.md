# Feature Specification: OI Regime Lab v0

**Feature Branch**: `feature/001-oi-regime-lab`
**Created**: 2026-04-26
**Status**: Draft
**Input**: Build OI Regime Lab v0 - a local research dashboard for validating whether Open Interest, funding rate, volume, and price range features can classify crypto market regimes.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Download Market Data (Priority: P1)

The user wants to download BTCUSDT 15-minute market data from Binance Futures, including OHLCV (candlestick), open interest, and funding rate data.

**Why this priority**: Data acquisition is the foundation for all analysis. Without reliable data, no research can proceed.

**Independent Test**: Can be fully tested by triggering a data download and verifying that Parquet files are created with correct timestamps and values.

**Acceptance Scenarios**:

1. **Given** the system is running, **When** the user requests BTCUSDT 15m data download, **Then** the system fetches OHLCV data from Binance Futures public API and saves to Parquet.
2. **Given** OHLCV data is downloaded, **When** the user requests open interest data, **Then** the system fetches open interest history and saves to Parquet.
3. **Given** OHLCV data is downloaded, **When** the user requests funding rate data, **Then** the system fetches funding rate history and aligns it with OHLCV timestamps.

---

### User Story 2 - Compute Features and Classify Regimes (Priority: P2)

The user wants the system to merge all data by timestamp, compute features (ATR, range high/low/mid, OI change percentage, volume ratio, funding features), and classify each bar into regimes: RANGE, BREAKOUT_UP, BREAKOUT_DOWN, or AVOID.

**Why this priority**: Feature engineering and regime classification are the core research value - they transform raw data into actionable insights.

**Independent Test**: Can be fully tested by processing downloaded data through the feature pipeline and verifying regime labels are assigned correctly.

**Acceptance Scenarios**:

1. **Given** raw data exists, **When** the user runs feature computation, **Then** the system merges data by timestamp and computes ATR, range_high, range_low, range_mid, OI change, volume ratio, and funding features.
2. **Given** features are computed, **When** the user runs regime classification, **Then** each bar is labeled as RANGE, BREAKOUT_UP, BREAKOUT_DOWN, or AVOID based on defined rules.
3. **Given** a bar has high OI change with price near range high, **When** classification runs, **Then** it is labeled as BREAKOUT_UP.

---

### User Story 3 - Research Dashboard (Priority: P3)

The user wants a web dashboard to visually inspect market data, features, and regime classifications. The dashboard should display candlestick charts, range levels, open interest, OI change, funding rate, volume, and regime labels.

**Why this priority**: Visualization enables the user to validate whether OI helps identify range or breakout behavior visually and statistically.

**Independent Test**: Can be fully tested by opening the dashboard in a browser and verifying all charts and data panels display correctly.

**Acceptance Scenarios**:

1. **Given** data is processed, **When** the user opens the dashboard, **Then** they see a candlestick chart with range high/low/mid lines overlaid.
2. **Given** data is processed, **When** the user views the dashboard, **Then** they see open interest, OI change, funding rate, and volume charts below the price chart.
3. **Given** regimes are classified, **When** the user views the dashboard, **Then** regime labels are displayed on the chart (e.g., colored background or markers).
4. **Given** data quality issues exist, **When** the user views the dashboard, **Then** they see data-quality status showing missing data, duplicate timestamps, and last updated time.

---

### Edge Cases

- What happens when Binance API is unavailable or rate-limited?
- How does the system handle duplicate timestamps in downloaded data?
- What happens when open interest data has gaps or missing timestamps?
- How does the system handle funding rate data that doesn't align perfectly with 15m intervals?
- What happens when the user requests data for a date range with no trading activity?

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: System MUST download BTCUSDT 15m OHLCV data from Binance Futures public API.
- **FR-002**: System MUST download BTCUSDT open interest history from Binance Futures public API.
- **FR-003**: System MUST download or align BTCUSDT funding rate data with OHLCV timestamps.
- **FR-004**: System MUST merge all data by timestamp into a unified dataset.
- **FR-005**: System MUST compute ATR (Average True Range) for volatility measurement.
- **FR-006**: System MUST compute range_high, range_low, and range_mid from price action.
- **FR-007**: System MUST compute OI change percentage (delta OI / OI).
- **FR-008**: System MUST compute volume ratio (current volume / average volume).
- **FR-009**: System MUST compute funding rate features (current rate, rate change, cumulative).
- **FR-010**: System MUST classify each bar into one of four regimes: RANGE, BREAKOUT_UP, BREAKOUT_DOWN, or AVOID.
- **FR-011**: System MUST display candlestick chart with range high/low/mid lines.
- **FR-012**: System MUST display open interest chart with OI change overlay.
- **FR-013**: System MUST display funding rate chart.
- **FR-014**: System MUST display volume chart with volume ratio indicator.
- **FR-015**: System MUST display regime labels on the price chart.
- **FR-016**: System MUST display data-quality status (missing data, duplicates, last updated).
- **FR-017**: System MUST store raw data in Parquet format for reproducibility.
- **FR-018**: System MUST expose data via REST API endpoints for frontend consumption.
- **FR-019**: System MUST NOT perform live trading or connect to private exchange APIs.
- **FR-020**: System MUST NOT require Rust, ClickHouse, Kafka, Kubernetes, or ML in v0.

### Key Entities

- **MarketData**: Represents OHLCV candlestick data with timestamp, open, high, low, close, volume.
- **OpenInterest**: Represents open interest at a specific timestamp with OI value and change.
- **FundingRate**: Represents funding rate at a specific timestamp with rate value and cumulative.
- **Feature**: Represents computed features for a bar (ATR, range levels, OI change, volume ratio).
- **Regime**: Represents regime classification for a bar (RANGE, BREAKOUT_UP, BREAKOUT_DOWN, AVOID).
- **DataQuality**: Represents data quality metrics (missing count, duplicate count, last updated).

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: User can download BTCUSDT 15m data covering at least 30 days of history.
- **SC-002**: Data download completes within 2 minutes for 30 days of 15m data.
- **SC-003**: Feature computation processes 30 days of data within 30 seconds.
- **SC-004**: Dashboard loads and displays all charts within 5 seconds.
- **SC-005**: Regime classification correctly identifies at least 80% of known breakout events (validated manually).
- **SC-006**: Data-quality panel shows accurate counts of missing data and duplicates.
- **SC-007**: User can visually correlate OI spikes with regime transitions in the dashboard.
- **SC-008**: System processes data without errors for at least 95% of downloaded bars.

## Assumptions

- Binance Futures public API is accessible without authentication for market data.
- BTCUSDT is the primary symbol for v0 research; other symbols may be added later.
- 15-minute timeframe is sufficient for initial regime classification research.
- Open interest data is available at 15-minute granularity from Binance.
- Funding rate data is available every 8 hours and can be forward-filled to 15m intervals.
- The user has local development environment with Python and Node.js installed.
- The user understands this is a research tool, not a live trading system.
