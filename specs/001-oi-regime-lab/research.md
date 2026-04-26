# Research: OI Regime Lab v0

**Date**: 2026-04-26
**Feature**: 001-oi-regime-lab

## Research Questions

### Q1: Binance Futures API for OHLCV Data

**Decision**: Use Binance USD-M Futures public API `/fapi/v1/klines` endpoint.

**Rationale**:
- No authentication required for public market data
- Supports 15m interval (`interval=15m`)
- Returns up to 1500 candles per request
- Well-documented with consistent response format
- Rate limit: 1200 requests/minute (sufficient for 30 days)

**Alternatives considered**:
- Binance Spot API: Different endpoint, may not have futures OI data
- WebSocket streaming: Overkill for historical batch download
- Third-party data vendors: Unnecessary complexity for v0

**API Details**:
```
GET https://fapi.binance.com/fapi/v1/klines
Parameters:
  - symbol: BTCUSDT
  - interval: 15m
  - startTime: Unix timestamp ms
  - endTime: Unix timestamp ms
  - limit: 1500 (max)

Response: Array of arrays [
  [open_time, open, high, low, close, volume, close_time, 
   quote_volume, trades, taker_buy_volume, taker_buy_quote_volume, ignore]
]
```

### Q2: Binance Futures API for Open Interest

**Decision**: Use Binance USD-M Futures public API `/futures/data/openInterestHist` endpoint.

**Rationale**:
- Provides historical open interest data at 15m granularity
- No authentication required
- Returns up to 500 records per request
- Includes both OI value and OI in quote currency

**Alternatives considered**:
- Real-time WebSocket only: Cannot get historical data
- Calculated from trades: Complex and inaccurate

**API Details**:
```
GET https://fapi.binance.com/futures/data/openInterestHist
Parameters:
  - symbol: BTCUSDT
  - period: 15m
  - startTime: Unix timestamp ms
  - endTime: Unix timestamp ms
  - limit: 500 (max)

Response: Array of objects [
  {
    "symbol": "BTCUSDT",
    "sumOpenInterest": "12345.678",
    "sumOpenInterestValue": "987654321.12",
    "timestamp": 1234567890000
  }
]
```

### Q3: Binance Futures API for Funding Rate

**Decision**: Use Binance USD-M Futures public API `/fapi/v1/fundingRate` endpoint.

**Rationale**:
- Provides historical funding rate data
- Funding rate occurs every 8 hours (00:00, 08:00, 16:00 UTC)
- No authentication required
- Can be forward-filled to 15m intervals

**Alternatives considered**:
- Calculated from mark price: Complex, not directly available
- Real-time only: Cannot get historical rates

**API Details**:
```
GET https://fapi.binance.com/fapi/v1/fundingRate
Parameters:
  - symbol: BTCUSDT
  - startTime: Unix timestamp ms
  - endTime: Unix timestamp ms
  - limit: 1000 (max)

Response: Array of objects [
  {
    "symbol": "BTCUSDT",
    "fundingRate": "0.00010000",
    "fundingTime": 1234567890000,
    "markPrice": "98765.43"
  }
]
```

### Q4: ATR (Average True Range) Calculation

**Decision**: Use 14-period ATR as default, computed with Polars.

**Rationale**:
- 14-period is standard for ATR
- Polars provides efficient rolling window operations
- Can be computed in vectorized manner

**Formula**:
```
True Range = max(
  high - low,
  abs(high - previous_close),
  abs(low - previous_close)
)
ATR = rolling_mean(True Range, 14)
```

**Implementation**:
```python
import polars as pl

def compute_atr(df: pl.DataFrame, period: int = 14) -> pl.DataFrame:
    df = df.with_columns([
        (pl.col("high") - pl.col("low")).alias("tr1"),
        (pl.col("high") - pl.col("close").shift(1)).abs().alias("tr2"),
        (pl.col("low") - pl.col("close").shift(1)).abs().alias("tr3"),
    ]).with_columns([
        pl.max_horizontal("tr1", "tr2", "tr3").alias("true_range")
    ]).with_columns([
        pl.col("true_range").rolling_mean(window_size=period).alias("atr")
    ])
    return df
```

### Q5: Range High/Low/Mid Calculation

**Decision**: Use rolling 20-period high/low for range detection.

**Rationale**:
- 20 periods (5 hours at 15m) captures meaningful price ranges
- Provides dynamic support/resistance levels
- Standard for range detection in technical analysis

**Formula**:
```
range_high = rolling_max(high, 20)
range_low = rolling_min(low, 20)
range_mid = (range_high + range_low) / 2
```

**Implementation**:
```python
def compute_range_levels(df: pl.DataFrame, period: int = 20) -> pl.DataFrame:
    return df.with_columns([
        pl.col("high").rolling_max(window_size=period).alias("range_high"),
        pl.col("low").rolling_min(window_size=period).alias("range_low"),
    ]).with_columns([
        ((pl.col("range_high") + pl.col("range_low")) / 2).alias("range_mid")
    ])
```

### Q6: OI Change Percentage

**Decision**: Compute as percentage change from previous period.

**Rationale**:
- Percentage change normalizes across different OI magnitudes
- Captures momentum in open interest
- Simple and interpretable

**Formula**:
```
oi_change_pct = (current_oi - previous_oi) / previous_oi * 100
```

**Implementation**:
```python
def compute_oi_change(df: pl.DataFrame) -> pl.DataFrame:
    return df.with_columns([
        ((pl.col("open_interest") - pl.col("open_interest").shift(1)) 
         / pl.col("open_interest").shift(1) * 100).alias("oi_change_pct")
    ])
```

### Q7: Volume Ratio

**Decision**: Compute as current volume divided by 20-period average volume.

**Rationale**:
- Identifies volume spikes relative to recent average
- 20-period average provides stable baseline
- Values > 1 indicate above-average volume

**Formula**:
```
volume_avg = rolling_mean(volume, 20)
volume_ratio = volume / volume_avg
```

**Implementation**:
```python
def compute_volume_ratio(df: pl.DataFrame, period: int = 20) -> pl.DataFrame:
    return df.with_columns([
        pl.col("volume").rolling_mean(window_size=period).alias("volume_avg")
    ]).with_columns([
        (pl.col("volume") / pl.col("volume_avg")).alias("volume_ratio")
    ])
```

### Q8: Funding Rate Features

**Decision**: Compute current rate, rate change, and cumulative rate.

**Rationale**:
- Current rate: immediate funding pressure
- Rate change: momentum in funding
- Cumulative rate: total funding cost over period

**Formula**:
```
funding_rate_current = forward_fill(funding_rate, 15m)
funding_rate_change = current_rate - previous_rate
funding_rate_cumsum = cumulative_sum(funding_rate)
```

### Q9: Regime Classification Rules

**Decision**: Rule-based classification using price position, OI change, and volume.

**Rationale**:
- Rule-based is interpretable for research
- Can be adjusted based on visual inspection
- No ML required in v0

**Classification Rules**:
```
RANGE:
  - price near range_mid (within 20% of range)
  - OI change < 5% (stable OI)
  - volume_ratio < 1.5 (normal volume)

BREAKOUT_UP:
  - price > range_high * 0.98 (near or above range high)
  - OI change > 5% (increasing OI)
  - volume_ratio > 1.2 (above average volume)

BREAKOUT_DOWN:
  - price < range_low * 1.02 (near or below range low)
  - OI change > 5% (increasing OI)
  - volume_ratio > 1.2 (above average volume)

AVOID:
  - Does not fit any of the above criteria
  - Conflicting signals (e.g., high OI but low volume)
```

### Q10: DuckDB Schema Design

**Decision**: Use DuckDB for SQL queries over Parquet files.

**Rationale**:
- Zero-configuration local database
- Direct query over Parquet files without import
- Fast analytical queries
- Compatible with Polars

**Schema**:
```sql
-- Raw data tables (Parquet-backed)
CREATE VIEW ohlcv AS SELECT * FROM 'data/raw/btcusdt_15m_ohlcv.parquet';
CREATE VIEW open_interest AS SELECT * FROM 'data/raw/btcusdt_15m_oi.parquet';
CREATE VIEW funding_rate AS SELECT * FROM 'data/raw/btcusdt_15m_funding.parquet';

-- Processed features table
CREATE VIEW features AS SELECT * FROM 'data/processed/btcusdt_15m_features.parquet';
```

### Q11: FastAPI Endpoint Design

**Decision**: RESTful API with 4 resource groups.

**Rationale**:
- Clear separation of concerns
- Standard REST conventions
- Pydantic for request/response validation

**Endpoints**:
```
GET /api/v1/market-data/ohlcv
GET /api/v1/market-data/open-interest
GET /api/v1/market-data/funding-rate
GET /api/v1/features
GET /api/v1/regimes
GET /api/v1/data-quality
POST /api/v1/download
POST /api/v1/process
```

### Q12: Frontend Chart Library

**Decision**: Use lightweight-charts for candlestick, Recharts for auxiliary charts.

**Rationale**:
- lightweight-charts: Optimized for financial charts, lightweight, TradingView quality
- Recharts: Good for simple line/bar charts, React-native, easy to use
- Both are well-maintained and have good TypeScript support

**Alternatives considered**:
- Chart.js: Less suitable for financial data
- D3.js: Too low-level for this use case
- ApexCharts: Heavier than lightweight-charts

## Resolved Unknowns

All technical questions have been resolved. No NEEDS CLARIFICATION markers remain.

## Dependencies

| Dependency | Version | Purpose |
|------------|---------|---------|
| Python | 3.11+ | Backend runtime |
| FastAPI | 0.104+ | Web framework |
| Pydantic | 2.5+ | Data validation |
| Polars | 0.20+ | DataFrame operations |
| DuckDB | 0.9+ | Local SQL database |
| httpx | 0.25+ | Async HTTP client |
| Next.js | 14+ | Frontend framework |
| TypeScript | 5.3+ | Type safety |
| Tailwind CSS | 3.4+ | Styling |
| lightweight-charts | 4.1+ | Candlestick charts |
| Recharts | 2.10+ | Auxiliary charts |

## Risk Assessment

| Risk | Likelihood | Impact | Mitigation |
|------|------------|--------|------------|
| Binance API rate limiting | Low | Medium | Implement exponential backoff, batch requests |
| Missing OI data for some timestamps | Medium | Low | Forward-fill with warning, track data quality |
| Funding rate alignment issues | Medium | Low | Forward-fill to 15m intervals |
| Large data download times | Low | Low | Use pagination, progress indicators |
| Polars learning curve | Low | Low | Use well-documented patterns, fallback to pandas if needed |
