from __future__ import annotations

from dataclasses import dataclass

from src.models.xau_vol2vol_history_walkforward import (
    XauEntryType,
    XauSdEntryLevel,
    XauSdMeanReversionPlan,
    XauSlMode,
    XauTpMode,
)
from src.xau_vol2vol_history_walkforward.planning import XauPlanningSelection
from src.xau_vol2vol_history_walkforward.range_plan_builder import (
    XauRangePlanBuildConfig,
    build_sd_mean_reversion_plans,
)


@dataclass(frozen=True)
class XauBaselineDefinition:
    baseline_id: str
    entry_sd: XauSdEntryLevel
    entry_type: XauEntryType
    tp_mode: XauTpMode
    sl_mode: XauSlMode


BASELINES = {
    item.baseline_id: item
    for item in (
        XauBaselineDefinition(
            "B1",
            XauSdEntryLevel.TWO_SD,
            XauEntryType.TOUCH,
            XauTpMode.HALF_SD,
            XauSlMode.THREE_SD,
        ),
        XauBaselineDefinition(
            "B2",
            XauSdEntryLevel.TWO_SD,
            XauEntryType.REJECTION_CONFIRMED,
            XauTpMode.HALF_SD,
            XauSlMode.THREE_SD,
        ),
        XauBaselineDefinition(
            "B3",
            XauSdEntryLevel.TWO_SD,
            XauEntryType.TOUCH,
            XauTpMode.ONE_SD,
            XauSlMode.THREE_5SD,
        ),
        XauBaselineDefinition(
            "B4",
            XauSdEntryLevel.THREE_SD,
            XauEntryType.TOUCH,
            XauTpMode.HALF_SD,
            XauSlMode.THREE_5SD,
        ),
        XauBaselineDefinition(
            "B5",
            XauSdEntryLevel.TWO_SD,
            XauEntryType.TOUCH,
            XauTpMode.FIXED_12_5,
            XauSlMode.FIXED_25,
        ),
        XauBaselineDefinition(
            "B6",
            XauSdEntryLevel.TWO_SD,
            XauEntryType.REJECTION_CONFIRMED,
            XauTpMode.FIXED_12_5,
            XauSlMode.FIXED_25,
        ),
    )
}


def build_predefined_baseline_plans(
    selections: list[XauPlanningSelection],
    baseline_ids: list[str],
) -> list[XauSdMeanReversionPlan]:
    plans: list[XauSdMeanReversionPlan] = []
    for selection in selections:
        for baseline_id in baseline_ids:
            definition = BASELINES[baseline_id]
            generated = build_sd_mean_reversion_plans(
                range_snapshot=selection.range_snapshot,
                strike_rows=selection.strike_rows,
                config=XauRangePlanBuildConfig(
                    cycle_label=selection.cycle_label,
                    entry_sds=(definition.entry_sd,),
                    tp_modes=(definition.tp_mode,),
                    sl_modes=(definition.sl_mode,),
                ),
            )
            for plan in generated:
                plans.append(
                    plan.model_copy(
                        update={
                            "plan_id": f"{baseline_id}_{plan.plan_id}",
                            "baseline_config": baseline_id,
                            "entry_type": definition.entry_type,
                            "selected_vol2vol_snapshot_time": (
                                selection.range_snapshot.observed_at
                            ),
                            "selected_xau_price_time": selection.selected_xau_price_time,
                            "basis_alignment_seconds": selection.basis_alignment_seconds,
                            "plan_created_at": selection.planning_at,
                            "simulation_window_start": selection.simulation_window_start,
                            "simulation_window_end": selection.simulation_window_end,
                        }
                    )
                )
    return plans
