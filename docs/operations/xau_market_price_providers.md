# XAU Market Price Providers

The XAU market context snapshot can resolve price inputs automatically, but every source
is still research-only. The provider layer does not place orders, send alerts, read broker
secrets, or make signal-readiness claims.

## Source Ranking

Preferred traded-side source:

```text
Broker / MT5 / actual GO or XAUUSD execution feed
```

This is the right future source for traded price because basis must match the instrument
that would actually be charted or traded.

Research-good sources:

```text
Local XAUUSD/GO CSV or JSON bars
Dukascopy or other saved traded-side candle exports
Latest local import files under backend/data/imports
```

Research fallback:

```text
Yahoo/yfinance XAUUSD=X and GC=F
```

Yahoo/yfinance is useful for filling a local research context snapshot when no local bars
exist, but it is not execution-grade. It can be delayed, sparse, paused, or inconsistent
between symbols, and data usage must follow Yahoo terms.

## CME Versus Traded Instrument

CME/QuikStrike gives GC futures/options structure: OI, volume, IV, and wall levels. XAUUSD,
GO, or GOLDcash charts are traded-side instruments. CME levels must be basis-adjusted:

```text
basis_points = gc_futures_price - xauusd_spot_price
spot_equivalent_level = futures_level - basis_points
```

If basis is missing or stale, mapped walls remain research context and cannot promote a
signal.

## Timestamp Policy

The context timestamp should come from the latest traded-side bar, not wall-clock time:

```text
current_timestamp = latest XAUUSD/GO bar timestamp
xauusd_spot_price = latest XAUUSD/GO bar close
```

GC futures can come from yfinance or latest local QuikStrike fusion. Its timestamp is
tracked separately:

```text
basis_alignment_seconds = abs(spot_timestamp - gc_timestamp)
```

Default basis rule:

```text
aligned:      gap <= 120 seconds
stale:        gap > 120 seconds
unavailable: missing spot, GC, or timestamp alignment
```

`--allow-stale-basis` allows the prices to be passed through for research inspection, but
the snapshot basis status remains stale/partial. Without that flag, stale GC is withheld
from the builder so the context cannot accidentally look aligned.

## Example Commands

Use latest local fusion plus latest local XAU bars:

```powershell
cd backend

python scripts/run_xau_market_context_snapshot.py `
  --use-latest-fusion `
  --price-bars-provider latest_local_import `
  --auto-price-provider latest_local_import `
  --timezone Asia/Bangkok
```

Use yfinance as a research fallback:

```powershell
python scripts/run_xau_market_context_snapshot.py `
  --use-latest-fusion `
  --price-bars-provider yfinance `
  --auto-price-provider yfinance `
  --spot-symbol "XAUUSD=X" `
  --gc-symbol "GC=F" `
  --timezone Asia/Bangkok
```

Manual values still override providers:

```powershell
python scripts/run_xau_market_context_snapshot.py `
  --price-bars-path data/imports/xauusd_1m_today.csv `
  --xauusd-spot-price 4050 `
  --gc-futures-price 4070 `
  --current-timestamp 2026-06-29T14:15:00+07:00
```

