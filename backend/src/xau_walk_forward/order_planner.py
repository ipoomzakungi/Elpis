from __future__ import annotations

from datetime import datetime

from src.models.xau_walk_forward_research import (
    XauResearchOrderPlan,
    XauResearchOrderPlanConfig,
    XauResearchOrderSide,
    XauResearchOrderStage,
    XauResearchRiskConfig,
    XauResearchRiskStatus,
    XauWalkForwardPriceSnapshot,
    XauWalkForwardSdSnapshot,
)


def generate_research_order_plans(
    *,
    snapshot_id: str,
    timestamp: datetime,
    price_snapshot: XauWalkForwardPriceSnapshot,
    sd_snapshot: XauWalkForwardSdSnapshot,
    config: XauResearchOrderPlanConfig,
    risk_config: XauResearchRiskConfig,
) -> list[XauResearchOrderPlan]:
    if price_snapshot.traded_offset is None:
        return []

    plans: list[XauResearchOrderPlan] = []
    if config.allow_long_lower_side:
        plans.append(
            _initial_plan(
                snapshot_id=snapshot_id,
                timestamp=timestamp,
                side=XauResearchOrderSide.LONG_REVERSION,
                entry_level=_map(sd_snapshot.lower_2sd, price_snapshot.traded_offset),
                target_level=_map(sd_snapshot.lower_1sd, price_snapshot.traded_offset),
                stop_level=_map(sd_snapshot.lower_2_5sd, price_snapshot.traded_offset),
                entry_sd=-config.entry_sd_abs,
                target_sd=-config.target_sd_abs,
                stop_sd=-config.stop_sd_abs,
            )
        )
        if config.max_recovery_steps >= 1:
            plans.append(
                _recovery_plan(
                    snapshot_id=snapshot_id,
                    timestamp=timestamp,
                    side=XauResearchOrderSide.LONG_REVERSION,
                    entry_level=_map(sd_snapshot.lower_3sd, price_snapshot.traded_offset),
                    target_level=_map(
                        _level_for_sd(sd_snapshot, -config.recovery_target_sd_abs),
                        price_snapshot.traded_offset,
                    ),
                    stop_level=_map(sd_snapshot.lower_3_5sd, price_snapshot.traded_offset),
                    entry_sd=-config.recovery_entry_sd_abs,
                    target_sd=-config.recovery_target_sd_abs,
                    stop_sd=-3.5,
                    risk_config=risk_config,
                    cumulative_loss_to_recover=_distance(
                        _map(sd_snapshot.lower_2sd, price_snapshot.traded_offset),
                        _map(sd_snapshot.lower_2_5sd, price_snapshot.traded_offset),
                    ),
                    desired_net_profit=_distance(
                        _map(sd_snapshot.lower_2sd, price_snapshot.traded_offset),
                        _map(sd_snapshot.lower_1sd, price_snapshot.traded_offset),
                    ),
                )
            )
    if config.allow_short_upper_side:
        plans.append(
            _initial_plan(
                snapshot_id=snapshot_id,
                timestamp=timestamp,
                side=XauResearchOrderSide.SHORT_REVERSION,
                entry_level=_map(sd_snapshot.upper_2sd, price_snapshot.traded_offset),
                target_level=_map(sd_snapshot.upper_1sd, price_snapshot.traded_offset),
                stop_level=_map(sd_snapshot.upper_2_5sd, price_snapshot.traded_offset),
                entry_sd=config.entry_sd_abs,
                target_sd=config.target_sd_abs,
                stop_sd=config.stop_sd_abs,
            )
        )
        if config.max_recovery_steps >= 1:
            plans.append(
                _recovery_plan(
                    snapshot_id=snapshot_id,
                    timestamp=timestamp,
                    side=XauResearchOrderSide.SHORT_REVERSION,
                    entry_level=_map(sd_snapshot.upper_3sd, price_snapshot.traded_offset),
                    target_level=_map(
                        _level_for_sd(sd_snapshot, config.recovery_target_sd_abs),
                        price_snapshot.traded_offset,
                    ),
                    stop_level=_map(sd_snapshot.upper_3_5sd, price_snapshot.traded_offset),
                    entry_sd=config.recovery_entry_sd_abs,
                    target_sd=config.recovery_target_sd_abs,
                    stop_sd=3.5,
                    risk_config=risk_config,
                    cumulative_loss_to_recover=_distance(
                        _map(sd_snapshot.upper_2sd, price_snapshot.traded_offset),
                        _map(sd_snapshot.upper_2_5sd, price_snapshot.traded_offset),
                    ),
                    desired_net_profit=_distance(
                        _map(sd_snapshot.upper_2sd, price_snapshot.traded_offset),
                        _map(sd_snapshot.upper_1sd, price_snapshot.traded_offset),
                    ),
                )
            )
    return [
        plan
        for plan in plans
        if plan.entry_level > 0 and plan.target_level > 0 and plan.stop_level > 0
    ]


def _initial_plan(
    *,
    snapshot_id: str,
    timestamp: datetime,
    side: XauResearchOrderSide,
    entry_level: float,
    target_level: float,
    stop_level: float,
    entry_sd: float,
    target_sd: float,
    stop_sd: float,
) -> XauResearchOrderPlan:
    return XauResearchOrderPlan(
        plan_id=f"{snapshot_id}_{side.value}_initial",
        snapshot_id=snapshot_id,
        timestamp=timestamp,
        side=side,
        stage=XauResearchOrderStage.INITIAL,
        entry_level=entry_level,
        target_level=target_level,
        stop_level=stop_level,
        entry_sd=entry_sd,
        target_sd=target_sd,
        stop_sd=stop_sd,
        tp_points=_distance(entry_level, target_level),
        sl_points=_distance(entry_level, stop_level),
        risk_status=XauResearchRiskStatus.ALLOWED,
        risk_reasons=["Initial plan is a conditional research template, not an order."],
    )


def _recovery_plan(
    *,
    snapshot_id: str,
    timestamp: datetime,
    side: XauResearchOrderSide,
    entry_level: float,
    target_level: float,
    stop_level: float,
    entry_sd: float,
    target_sd: float,
    stop_sd: float,
    risk_config: XauResearchRiskConfig,
    cumulative_loss_to_recover: float,
    desired_net_profit: float,
) -> XauResearchOrderPlan:
    risk_status = XauResearchRiskStatus.MISSING_CONFIG
    risk_reasons = ["Recovery sizing requires point_value_per_size_unit."]
    planned_size = None
    costs = risk_config.costs_per_order or 0.0
    target_points = _distance(entry_level, target_level)
    if not risk_config.recovery_enabled:
        risk_status = XauResearchRiskStatus.BLOCKED
        risk_reasons = ["Recovery simulation is disabled by risk_config."]
    elif risk_config.point_value_per_size_unit is not None and target_points > 0:
        planned_size = (
            cumulative_loss_to_recover + desired_net_profit + costs
        ) / (target_points * risk_config.point_value_per_size_unit)
        risk_status = XauResearchRiskStatus.ALLOWED
        risk_reasons = ["Recovery size is calculated for research simulation only."]
        if risk_config.max_size is not None and planned_size > risk_config.max_size:
            risk_status = XauResearchRiskStatus.BLOCKED
            risk_reasons = ["Recovery size exceeds max_size."]
    return XauResearchOrderPlan(
        plan_id=f"{snapshot_id}_{side.value}_recovery_1",
        snapshot_id=snapshot_id,
        timestamp=timestamp,
        side=side,
        stage=XauResearchOrderStage.RECOVERY_1,
        entry_level=entry_level,
        target_level=target_level,
        stop_level=stop_level,
        entry_sd=entry_sd,
        target_sd=target_sd,
        stop_sd=stop_sd,
        tp_points=target_points,
        sl_points=_distance(entry_level, stop_level),
        planned_size=planned_size,
        cumulative_loss_to_recover=cumulative_loss_to_recover,
        desired_net_profit=desired_net_profit,
        recovery_formula=(
            "next_size = (cumulative_realized_loss + desired_net_profit + "
            "estimated_costs) / (recovery_target_points * point_value_per_size_unit)"
        ),
        risk_status=risk_status,
        risk_reasons=risk_reasons,
    )


def _level_for_sd(sd_snapshot: XauWalkForwardSdSnapshot, sd: float) -> float:
    mapping = {
        -1.0: sd_snapshot.lower_1sd,
        -2.0: sd_snapshot.lower_2sd,
        -3.0: sd_snapshot.lower_3sd,
        1.0: sd_snapshot.upper_1sd,
        2.0: sd_snapshot.upper_2sd,
        3.0: sd_snapshot.upper_3sd,
    }
    value = mapping.get(float(sd))
    if value is None:
        raise ValueError(f"unsupported recovery target SD: {sd}")
    return value


def _map(level: float | None, traded_offset: float | None) -> float:
    if level is None or traded_offset is None:
        return -1.0
    return level + traded_offset


def _distance(first: float, second: float) -> float:
    return abs(first - second)


__all__ = ["generate_research_order_plans"]
