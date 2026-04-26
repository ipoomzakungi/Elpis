# Data Model: OI Regime Lab v0

**Date**: 2026-04-26
**Feature**: 001-oi-regime-lab

## Entities

### MarketData (OHLCV)

Represents candlestick data from Binance Futures.

| Field | Type | Description | Validation |
|-------|------|-------------|------------|
| timestamp | datetime | Bar open time (UTC) | Required, valid datetime |
| open | float | Opening price | > 0 |
| high | float | Highest price | >= open, >= close |
| low | float | Lowest price | <= open, <= close |
| close | float | Closing price | > 0 |
| volume | float | Trading volume | >= 0 |
| quote_volume | float | Quote asset volume | >= 0 |
| trades | int | Number of trades | >= 0 |
| taker_buy_volume | float | Taker buy volume | >= 0 |

**Source**: Binance `/fapi/v1/klines` endpoint
**Storage**: `data/raw/btcusdt_15m_ohlcv.parquet`
**Primary Key**: timestamp

### OpenInterest

Represents open interest at a specific timestamp.

| Field | Type | Description | Validation |
|-------|------|-------------|------------|
| timestamp | datetime | Measurement time (UTC) | Required, valid datetime |
| symbol | string | Trading pair | Must be "BTCUSDT" |
| open_interest | float | Open interest in base asset | > 0 |
| open_interest_value | float | Open interest in quote currency | > 0 |

**Source**: Binance `/futures/data/openInterestHist` endpoint
**Storage**: `data/raw/btcusdt_15m_oi.parquet`
**Primary Key**: timestamp

### FundingRate

Represents funding rate data.

| Field | Type | Description | Validation |
|-------|------|-------------|------------|
| timestamp | datetime | Funding time (UTC) | Required, valid datetime |
| symbol | string | Trading pair | Must be "BTCUSDT" |
| funding_rate | float | Funding rate | -0.05 to 0.05 |
| mark_price | float | Mark price at funding time | > 0 |

**Source**: Binance `/fapi/v1/fundingRate` endpoint
**Storage**: `data/raw/btcusdt_15m_funding.parquet`
**Primary Key**: timestamp

### Feature

Represents computed features for a bar.

| Field | Type | Description | Validation |
|-------|------|-------------|------------|
| timestamp | datetime | Bar time (UTC) | Required |
| open | float | Opening price | > 0 |
| high | float | Highest price | >= open |
| low | float | Lowest price | <= open |
| close | float | Closing price | > 0 |
| volume | float | Trading volume | >= 0 |
| atr | float | Average True Range (14-period) | >= 0 |
| range_high | float | 20-period rolling high | >= high |
| range_low | float | 20-period rolling low | <= low |
| range_mid | float | Midpoint of range | (range_high + range_low) / 2 |
| open_interest | float | Open interest | > 0 |
| oi_change_pct | float | OI change percentage | -100 to 1000 |
| volume_ratio | float | Volume / 20-period avg | >= 0 |
| funding_rate | float | Funding rate (forward-filled) | -0.05 to 0.05 |
| funding_rate_change | float | Rate change from previous | -0.1 to 0.1 |
| funding_rate_cumsum | float | Cumulative funding rate | unbounded |

**Computation**: From raw data via feature pipeline
**Storage**: `data/processed/btcusdt_15m_features.parquet`
**Primary Key**: timestamp

### Regime

Represents regime classification for a bar.

| Field | Type | Description | Validation |
|-------|------|-------------|------------|
| timestamp | datetime | Bar time (UTC) | Required |
| regime | enum | Regime classification | RANGE, BREAKOUT_UP, BREAKOUT_DOWN, AVOID |
| confidence | float | Classification confidence | 0.0 to 1.0 |
| reason | string | Human-readable reason | Optional |

**Classification Rules**:

| Regime | Price Position | OI Change | Volume Ratio |
|--------|---------------|-----------|--------------|
| RANGE | Within 20% of range | < 5% | < 1.5 |
| BREAKOUT_UP | > 98% of range_high | > 5% | > 1.2 |
| BREAKOUT_DOWN | < 102% of range_low | > 5% | > 1.2 |
| AVOID | Other | Any | Any |

**Storage**: Included in features Parquet file
**Primary Key**: timestamp

### DataQuality

Represents data quality metrics.

| Field | Type | Description | Validation |
|-------|------|-------------|------------|
| data_type | string | Type of data (ohlcv, oi, funding) | Required |
| total_records | int | Total number of records | >= 0 |
| missing_timestamps | int | Number of gaps | >= 0 |
| duplicate_timestamps | int | Number of duplicates | >= 0 |
| first_timestamp | datetime | Earliest record | Optional |
| last_timestamp | datetime | Latest record | Optional |
| last_updated | datetime | When data was last fetched | Required |

**Computation**: From raw data quality checks
**Storage**: In-memory, exposed via API

## Relationships

```
MarketData (1) ←→ (1) OpenInterest
    via timestamp (15m alignment)

MarketData (1) ←→ (1) FundingRate
    via timestamp (forward-filled from 8h)

MarketData (1) ←→ (1) Feature
    via timestamp (computed from MarketData + OI + Funding)

Feature (1) ←→ (1) Regime
    via timestamp (classified from Feature)
```

## State Transitions

### Data Download Flow
```
[Not Started] → [Downloading] → [Completed] → [Processing] → [Ready]
                              ↘ [Failed] → [Retry]
```

### Regime Classification Flow
```
[Raw Data] → [Features Computed] → [Classified] → [Displayed]
```

## Validation Rules

### Timestamp Validation
- All timestamps must be in UTC
- Timestamps must be aligned to 15-minute intervals
- No duplicate timestamps allowed
- Gaps in timestamps are tracked as data quality issues

### Price Validation
- High must be >= Open and >= Close
- Low must be <= Open and <= Close
- All prices must be > 0

### Volume Validation
- Volume must be >= 0
- Quote volume must be >= 0
- Taker buy volume must be <= volume

### OI Validation
- Open interest must be > 0
- OI change percentage must be reasonable (-100% to +1000%)

### Funding Rate Validation
- Funding rate must be between -5% and 5% (Binance limits)
- Mark price must be > 0
