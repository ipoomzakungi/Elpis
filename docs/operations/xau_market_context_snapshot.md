# XAU Market Context Snapshot

The XAU Market Context Snapshot Builder creates a local research-only context object for
mapping CME/QuikStrike gold futures/options levels onto traded-side XAUUSD/GO charts.
It does not fetch internet data, store credentials, place orders, create alerts, or enable
signals.

## Why Basis Mapping Is Required

CME gold option and futures levels are futures-side levels. XAUUSD, GO, and GOLDcash
charts are traded-side spot/CFD-style prices. A CME wall must be adjusted before it is
drawn on the traded chart:

```text
basis_points = gc_futures_price - xauusd_spot_price
spot_equivalent_level = futures_level - basis_points
```

If spot is 4050, GC futures is 4070, and a CME wall is 4100, the mapped XAUUSD level is
4080. Missing basis keeps mapped levels unavailable and blocks signal readiness.

## Why Session Open Comes From Traded-Side Bars

The useful day-trade session anchor is the open on the traded chart, not a CME analytics
page value. The builder derives Asia, London, New York macro, New York cash, and daily
roll opens from local traded-side bars using IANA time zones so daylight-saving changes
are handled by the runtime.

## Why ATR And RV Come From Traded-Side Candles

CME provides the options battlefield. ATR and realized volatility describe whether the
current traded chart can realistically reach or reject a mapped wall. The builder derives
ATR and realized volatility from local XAUUSD/GO candles and leaves values null when bar
coverage is insufficient.

## Why Candle Acceptance Is Required

OI does not say buy or sell. It only marks structure. The context snapshot classifies the
last closed candle around mapped walls as accepted, rejected, failed breakout, neutral,
or unavailable. Signal promotion remains disabled unless a later research-only signal
layer has basis, session, volatility, and candle context.

## Example

```powershell
cd backend

python scripts/run_xau_market_context_snapshot.py `
  --price-bars-path data/imports/xauusd_1m_today.csv `
  --xauusd-spot-price 4050 `
  --gc-futures-price 4070 `
  --current-timestamp 2026-06-29T14:15:00+07:00 `
  --traded-symbol XAUUSD
```

Artifacts are written under:

```text
backend/data/reports/xau_market_context/<snapshot_id>/
```

