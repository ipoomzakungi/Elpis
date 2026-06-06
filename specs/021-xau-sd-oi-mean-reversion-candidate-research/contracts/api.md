# Contract: XAU SD/OI Mean Reversion Candidate Classifier

**Feature**: 021-xau-sd-oi-mean-reversion-candidate-research

This is a local research helper contract. It is not an HTTP API, alert contract, broker contract, order contract, execution contract, or live-trading contract.

## Function

```python
from datetime import datetime

from src.models.xau import XauDailyStructuralMap
from src.models.xau_sd_oi_candidate import XauSdOiCandidateSet

def build_xau_sd_oi_candidate_set(
    daily_map: XauDailyStructuralMap,
    *,
    timestamp: datetime,
    traded_price: float | None,
    gc_price: float | None = None,
    confirmation_state: str = "unavailable",
    iv_state: str = "unavailable",
    flow_state: str = "unavailable",
) -> XauSdOiCandidateSet:
    ...
```

## Output Guarantees

- `signal_allowed` is false.
- `research_only` is true.
- Missing basis/range/price/open context returns `no_trade`.
- 2SD-3SD stretch creates a candidate only when rejection context is supplied and breakout context is absent.
- Breakout-risk context overrides reversion-candidate classification.
- Null wall OI-change and volume stay null.
- Derived 3.5SD references include a limitation.

## Forbidden Scope

The classifier must not create BUY/SELL live signals, alerts, broker execution, order routing, real position sizing, auto trading, paper trading, PnL, ML training, profitability claims, predictive-proof claims, safety claims, or live-readiness claims.
