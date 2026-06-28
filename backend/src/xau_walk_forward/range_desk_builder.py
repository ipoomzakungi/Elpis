from __future__ import annotations

from src.models.xau_range_desk import (
    XauRangeDeskLevelInput,
    XauRangeDeskLevelKind,
    XauRangeDeskPlan,
    XauRangeDeskPlanRequest,
)
from src.models.xau_walk_forward_research import (
    XauWalkForwardPriceSnapshot,
    XauWalkForwardSdSnapshot,
)
from src.xau_range_desk.planner import build_xau_range_desk_plan


def build_range_desk_from_walk_forward_snapshot(
    *,
    session_date,
    price_snapshot: XauWalkForwardPriceSnapshot,
    sd_snapshot: XauWalkForwardSdSnapshot,
    traded_instrument: str = "XAUUSD",
    futures_symbol: str = "GC",
) -> XauRangeDeskPlan | None:
    if (
        price_snapshot.future_reference_price is None
        or price_snapshot.traded_reference_price is None
        or sd_snapshot.future_reference_price is None
    ):
        return None
    if any(
        value is None
        for value in (
            sd_snapshot.lower_1sd,
            sd_snapshot.upper_1sd,
            sd_snapshot.lower_2sd,
            sd_snapshot.upper_2sd,
            sd_snapshot.lower_3sd,
            sd_snapshot.upper_3sd,
        )
    ):
        return None

    levels = [
        XauRangeDeskLevelInput(
            label=XauRangeDeskLevelKind.LOWER_3SD,
            futures_level=sd_snapshot.lower_3sd,
            source=sd_snapshot.sd_source.value,
        ),
        XauRangeDeskLevelInput(
            label=XauRangeDeskLevelKind.LOWER_2SD,
            futures_level=sd_snapshot.lower_2sd,
            source=sd_snapshot.sd_source.value,
        ),
        XauRangeDeskLevelInput(
            label=XauRangeDeskLevelKind.LOWER_1SD,
            futures_level=sd_snapshot.lower_1sd,
            source=sd_snapshot.sd_source.value,
        ),
        XauRangeDeskLevelInput(
            label=XauRangeDeskLevelKind.MEAN,
            futures_level=sd_snapshot.future_reference_price,
            source=sd_snapshot.sd_source.value,
        ),
        XauRangeDeskLevelInput(
            label=XauRangeDeskLevelKind.UPPER_1SD,
            futures_level=sd_snapshot.upper_1sd,
            source=sd_snapshot.sd_source.value,
        ),
        XauRangeDeskLevelInput(
            label=XauRangeDeskLevelKind.UPPER_2SD,
            futures_level=sd_snapshot.upper_2sd,
            source=sd_snapshot.sd_source.value,
        ),
        XauRangeDeskLevelInput(
            label=XauRangeDeskLevelKind.UPPER_3SD,
            futures_level=sd_snapshot.upper_3sd,
            source=sd_snapshot.sd_source.value,
        ),
    ]
    return build_xau_range_desk_plan(
        XauRangeDeskPlanRequest(
            session_date=session_date,
            traded_instrument=traded_instrument,
            futures_symbol=futures_symbol,
            future_reference_price=price_snapshot.future_reference_price,
            traded_reference_price=price_snapshot.traded_reference_price,
            levels=levels,
            research_only_acknowledged=True,
        )
    )


__all__ = ["build_range_desk_from_walk_forward_snapshot"]
