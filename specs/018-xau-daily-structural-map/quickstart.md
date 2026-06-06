# Quickstart: XAU Daily Structural Map

**Feature**: 018-xau-daily-structural-map
**Date**: 2026-06-04

## Scope

This feature creates a research-only daily structural map. It combines Feature 017 expected-range context, basis mapping, existing XAU Vol-OI walls, optional session open, readiness, and limitations.

It does not create buy/sell signals, alerts, broker execution, order instructions, position instructions, ML, or strategy backtests.

## Focused Validation

Run the new backend map tests from `backend/`:

```powershell
cd backend
python -m pytest tests/unit/test_xau_daily_structural_map.py -q
```

Run Feature 017 regression tests from `backend/`:

```powershell
python -m pytest tests/unit/test_xau_expected_range_context_parity.py -q
python -c "from src.main import app; print('backend import ok')"
```

Run inventory tests from the repository root:

```powershell
python -m pytest research_xau_vol_oi/tests/test_systematic_engine_field_inventory.py -q
```

Run ruff on touched Python files from `backend/`:

```powershell
ruff check src/models/xau.py src/xau_quikstrike_fusion/daily_structural_map.py tests/unit/test_xau_daily_structural_map.py
```

Expected results:

- Full context creates a structural map with mapped wall levels and readiness `structural_map_ready`.
- Missing basis keeps mapped wall fields null.
- Missing expected range keeps SD fields null.
- Missing session open creates a partial map.
- Blank Matrix cells preserve null numeric values.
- Feature 017 snapshots populate expected-range fields.
- `signal_allowed` remains false in every case.

## Required Price Inputs For Later Evidence

Feature 018 defines but does not ingest the later evidence inputs:

- GC 1m/5m OHLCV
- XAUUSD or GO 1m/5m OHLCV
- session open
- session high/low
- VWAP if available
- prior settlement and CME settlement reference
- event-risk calendar context

These are future research inputs and are not trading signals.
