# Quickstart: XAU SD OI Mean Reversion Candidate Research

**Feature**: 021-xau-sd-oi-mean-reversion-candidate-research
**Date**: 2026-06-07

## Scope

This feature creates research-only candidate labels from existing daily structural maps. It does not create live signals, alerts, broker execution, PnL, ML, or backtests.

## Local Usage

```python
from datetime import UTC, datetime

from src.xau_sd_oi_candidate.classifier import build_xau_sd_oi_candidate_set

candidate_set = build_xau_sd_oi_candidate_set(
    daily_map,
    timestamp=datetime(2026, 6, 2, 14, 30, tzinfo=UTC),
    traded_price=4785.0,
    gc_price=4797.5,
    confirmation_state="rejection",
    iv_state="stable",
    flow_state="not_breakout_confirmed",
)
```

Expected behavior:

- Candidate set contains one candidate for the observed timestamp.
- Candidate output remains `signal_allowed=false` and `research_only=true`.
- Missing context produces `no_trade`.
- Strong breakout context produces `breakout_risk`.

## Focused Validation

Run from `backend/`:

```powershell
python -m pytest tests/unit/test_xau_sd_oi_mean_reversion_candidate.py -q
python -m pytest tests/unit/test_xau_daily_structural_map.py -q
python -m pytest tests/unit/test_xau_expected_range_context_parity.py -q
python -c "from src.main import app; print('backend import ok')"
```

Run from the repository root:

```powershell
python -m pytest research_xau_vol_oi/tests/test_systematic_engine_field_inventory.py -q
```

Run ruff from `backend/`:

```powershell
ruff check src/models/xau_sd_oi_candidate.py src/xau_sd_oi_candidate/classifier.py tests/unit/test_xau_sd_oi_mean_reversion_candidate.py
```

Expected results:

- Missing basis blocks candidates.
- Upper 2SD-3SD rejection creates a short reversion research candidate.
- Lower 2SD-3SD rejection creates a long reversion research candidate.
- IV expansion plus flow-through-wall plus acceptance creates breakout risk.
- Inside +/-2SD produces no-trade monitor output.
- Null wall OI-change and volume remain null.
- Derived 3.5SD limitation is visible.
