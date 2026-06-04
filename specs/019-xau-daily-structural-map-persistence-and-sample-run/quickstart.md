# Quickstart: XAU Daily Structural Map Persistence And Sample Run

**Feature**: 019-xau-daily-structural-map-persistence-and-sample-run
**Date**: 2026-06-04

## Scope

This feature persists Feature 018 daily structural maps under ignored local report paths and adds a testable sample-run helper. It does not add outcomes, candidate classifiers, buy/sell signals, alerts, broker execution, ML, or backtests.

## Focused Validation

Run from `backend/`:

```powershell
python -m pytest tests/unit/test_xau_daily_structural_map_store.py -q
python -m pytest tests/unit/test_xau_daily_structural_map.py -q
python -m pytest tests/unit/test_xau_expected_range_context_parity.py -q
python -c "from src.main import app; print('backend import ok')"
```

Run ruff from `backend/`:

```powershell
ruff check src/models/xau_daily_structural_map.py src/xau_daily_structural_map/report_store.py src/xau_daily_structural_map/sample_run.py tests/unit/test_xau_daily_structural_map_store.py
```

Expected results:

- Full-context persistence writes `metadata.json`, `map.json`, `map.md`, and `walls.json`.
- Missing context maps still save.
- Null OI-change and volume values remain null.
- `map.json` loads back into `XauDailyStructuralMap`.
- Sample-run helper returns map id, readiness, wall count, and artifact paths.
- `signal_allowed` remains false in every persisted artifact.

## Local Sample Generation

Use `generate_xau_daily_structural_map_report(...)` with supplied local inputs:

- session date
- expiration code
- expected-range snapshot
- walls
- basis state or manual basis inputs
- optional session open
- output `data/reports` root

The helper does not fetch CME pages or browser/session data.
