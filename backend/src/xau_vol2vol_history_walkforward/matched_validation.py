from __future__ import annotations

import hashlib
import json
import math
import random
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from statistics import mean, median, pstdev
from typing import Any

from src.models.xau_market_context import XauPriceBar


def protocol_hash(payload: dict[str, Any]) -> str:
    canonical = {key: value for key, value in payload.items() if key != "protocol_hash"}
    encoded = json.dumps(canonical, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(encoded).hexdigest()


def validate_protocol(payload: dict[str, Any]) -> str:
    calculated = protocol_hash(payload)
    if payload.get("protocol_hash") != calculated:
        raise ValueError("protocol hash does not match immutable rule content")
    return calculated


def build_episode_maps(
    result_sets: list[dict[str, Any]],
    features: list[dict[str, Any]],
    bars: list[XauPriceBar],
    variant_outcomes: dict[str, list[dict[str, Any]]],
    *,
    reset_sd: float = 0.5,
) -> dict[str, Any]:
    primary_results = [
        result for result in result_sets if result["mapping_mode"] == "same_time_basis"
    ]
    feature_by_key = {
        (
            row["planning_mode"],
            row["session_date"],
            row["side"],
            row["entry_definition"],
        ): row
        for row in features
        if row["mapping_mode"] == "same_time_basis"
    }
    exit_by_key: dict[tuple, datetime] = {}
    for outcome in variant_outcomes.get("F0", []):
        if not outcome.get("exited_at"):
            continue
        key = (
            outcome["planning_mode"],
            outcome["session_date"],
            outcome["side"],
            outcome["entry_definition"],
        )
        exited = datetime.fromisoformat(outcome["exited_at"])
        exit_by_key[key] = min(exit_by_key.get(key, exited), exited)
    plan_versions = []
    all_plan_version_ids = set()
    for result in primary_results:
        for diagnostic in result.get("diagnostics", []):
            all_plan_version_ids.add(
                f"{result['planning_mode']}:{diagnostic['session_date']}:"
                f"{diagnostic['planning_at']}"
            )
        for row in result["opportunities"]:
            if not row["touched"] or row["entry_definition"] not in {
                "zone_2_entry",
                "zone_2_mid",
            }:
                continue
            all_plan_version_ids.add(
                f"{result['planning_mode']}:{row['session_date']}:{row['planning_at']}"
            )
            plan_versions.append(
                {
                    **row,
                    "plan_version_id": (
                        f"{result['planning_mode']}:{row['session_date']}:"
                        f"{row['planning_at']}"
                    ),
                }
            )
    episodes = []
    for planning_mode in ("fixed_morning", "rolling_30m"):
        mode_rows = [row for row in plan_versions if row["planning_mode"] == planning_mode]
        groups: dict[tuple, list[dict[str, Any]]] = defaultdict(list)
        for row in mode_rows:
            groups[(row["session_date"], row["side"], row["entry_definition"])].append(row)
        for key, rows in sorted(groups.items()):
            rows.sort(key=lambda item: item["first_touch_time"])
            if planning_mode == "fixed_morning":
                for index, row in enumerate(rows, start=1):
                    episodes.append(
                        _episode_record(
                            planning_mode,
                            key,
                            index,
                            [row],
                            reset_timestamp=None,
                            reset_reason="new_trading_session",
                            reset_sd=reset_sd,
                        )
                    )
                continue
            current = []
            episode_number = 1
            prior = None
            for row in rows:
                reset_timestamp = None
                reset_reason = None
                if prior is not None:
                    feature = feature_by_key.get((planning_mode, *key))
                    reset_timestamp, reset_reason = _find_reset(
                        prior,
                        row,
                        feature,
                        bars,
                        reset_sd=reset_sd,
                        exited_at=exit_by_key.get((planning_mode, *key)),
                    )
                if reset_reason and current:
                    episodes.append(
                        _episode_record(
                            planning_mode,
                            key,
                            episode_number,
                            current,
                            reset_timestamp=reset_timestamp,
                            reset_reason=reset_reason,
                            reset_sd=reset_sd,
                        )
                    )
                    episode_number += 1
                    current = []
                current.append(row)
                prior = row
            if current:
                episodes.append(
                    _episode_record(
                        planning_mode,
                        key,
                        episode_number,
                        current,
                        reset_timestamp=None,
                        reset_reason=None,
                        reset_sd=reset_sd,
                    )
                )
    matched_anchor_opportunity_ids = {
        row["opportunity_id"]
        for row in features
        if row["mapping_mode"] == "same_time_basis"
    }
    market_opportunity_ids = {row["opportunity_id"] for row in plan_versions}
    sessions = {row["session_date"] for row in features if row["mapping_mode"] == "same_time_basis"}
    ordered_sessions = sorted(sessions)
    split = max(int(len(ordered_sessions) * 0.7), 1) if ordered_sessions else 0
    holdout_sessions = set(ordered_sessions[split:])
    return {
        "reset_sd": reset_sd,
        "plan_version_count": len(all_plan_version_ids),
        "unique_opportunity_count": len(market_opportunity_ids),
        "matched_anchor_opportunity_count": len(matched_anchor_opportunity_ids),
        "unique_episode_count": len(episodes),
        "independent_session_count": len(sessions),
        "holdout_episode_count": sum(
            episode["session_date"] in holdout_sessions for episode in episodes
        ),
        "configuration_outcome_count": len(variant_outcomes.get("F0", [])),
        "cost_scenario_row_count": len(variant_outcomes.get("F0", [])),
        "episodes": episodes,
        "research_only": True,
        "signal_allowed": False,
    }


def build_matched_comparisons(
    features: list[dict[str, Any]],
    variant_outcomes: dict[str, list[dict[str, Any]]],
    episode_map: dict[str, Any],
    br_condition_records: list[dict[str, Any]],
) -> dict[str, Any]:
    outcomes = {
        name: _outcome_index(rows) for name, rows in variant_outcomes.items()
    }
    f0 = outcomes.get("F0", {})
    f1 = outcomes.get("F1", {})
    f2 = outcomes.get("F2", {})
    f3 = outcomes.get("F3", {})
    f1_retained_keys = set(f1)
    f1_rejected_keys = set(f0) - f1_retained_keys
    f1_retained_rows = [f0[key] for key in f1_retained_keys]
    f1_rejected_rows = [f0[key] for key in f1_rejected_keys]
    f2_pairs = _paired_rows(f0, f2, baseline_name="F0", variant_name="F2")
    f3_pairs = _paired_rows(f2, f3, baseline_name="F2", variant_name="F3")
    f2_opportunities = {key[0] for key in f2}
    f1_opportunities = {key[0] for key in f1}
    episode_by_opportunity = {}
    for episode in episode_map["episodes"]:
        for opportunity_id in episode["opportunity_ids"]:
            episode_by_opportunity[opportunity_id] = episode["episode_id"]
    result = {
        "F1": {
            "comparison_type": "selection_matched_to_F0",
            "retained": _summarize_rows(f1_retained_rows),
            "rejected": _summarize_rows(f1_rejected_rows),
            "chronological": {
                "retained": _chronological_rows(f1_retained_rows),
                "rejected": _chronological_rows(f1_rejected_rows),
            },
            "retained_minus_rejected_mean_net_points": _mean_difference(
                [f0[key]["net_points"] for key in f1_retained_keys],
                [f0[key]["net_points"] for key in f1_rejected_keys],
            ),
        },
        "F2": {
            "comparison_type": "paired_confirmation_vs_touch",
            "pairs": f2_pairs,
            "paired_summary": _paired_summary(f2_pairs),
            "chronological": _chronological_pairs(f2_pairs),
            "missed_opportunity_count": len(f1_opportunities - f2_opportunities),
        },
        "F3": {
            "comparison_type": "paired_flow_filter_vs_F2",
            "pairs": f3_pairs,
            "paired_summary": _paired_summary(f3_pairs),
            "chronological": _chronological_pairs(f3_pairs),
            "retained": _summarize_rows(list(f3.values())),
            "rejected": _summarize_rows(
                [row for key, row in f2.items() if key not in f3]
            ),
            "exploratory": True,
        },
        "BR": {
            "accepted_beyond_wall_count": sum(
                row["accepted_beyond_wall"] for row in br_condition_records
            ),
            "high_volume_delta_count": sum(
                row["high_volume_delta"] for row in br_condition_records
            ),
            "low_activity_gap_count": sum(
                row["low_activity_gap_toward_next_wall"]
                for row in br_condition_records
            ),
            "all_conditions_count": sum(
                row["all_conditions"] for row in br_condition_records
            ),
            "blocked_opportunity_ids": [
                row["opportunity_id"] for row in br_condition_records if row["all_conditions"]
            ],
            "would_have_occurred_without_blocking": _summarize_rows(
                [
                    row
                    for key, row in f0.items()
                    if key[0]
                    in {
                        item["opportunity_id"]
                        for item in br_condition_records
                        if item["all_conditions"]
                    }
                ]
            ),
        },
        "strategy_summaries": _strategy_summaries(
            variant_outcomes, episode_by_opportunity
        ),
        "equal_weighted_configuration_summary": _equal_weighted_summary(
            variant_outcomes
        ),
        "research_only": True,
        "signal_allowed": False,
    }
    return result


def build_feature_quality_audit(features: list[dict[str, Any]]) -> dict[str, Any]:
    violations: list[dict[str, Any]] = []
    checks = defaultdict(int)
    for feature in features:
        if feature["mapping_mode"] != "same_time_basis":
            continue
        for state_name in ("plan_state", "touch_state"):
            state = feature[state_name]
            for age_name in ("oi_feature_age_seconds", "volume_feature_age_seconds"):
                age = state.get(age_name)
                if age is not None and age > 1800:
                    checks[f"stale_{state_name}_{age_name}_count"] += 1
            for kind in ("oi", "volume"):
                value = state[kind]
                if value is None:
                    continue
                if value["all_zero_snapshot"]:
                    checks[f"all_zero_{kind}_snapshot_count"] += 1
                    if value["top_5"] or value["top_10"]:
                        violations.append(
                            _quality_violation(feature, state_name, kind, "zero_rank")
                        )
                if value["insufficient_active_strikes"]:
                    checks[f"insufficient_active_{kind}_snapshot_count"] += 1
                    if value["rank"] is not None:
                        violations.append(
                            _quality_violation(feature, state_name, kind, "insufficient_rank")
                        )
                if value["maximum_value_tie_count"] >= 5:
                    checks[f"large_rank_tie_{kind}_count"] += 1
                if value["derived_change"] == 0 and value["source_provided_change"] not in (
                    None,
                    0,
                ):
                    checks[f"identical_snapshot_change_mismatch_{kind}_count"] += 1
                discrepancy = value["change_discrepancy"]
                if discrepancy is not None and abs(discrepancy) > 1e-9:
                    checks[f"source_derived_change_mismatch_{kind}_count"] += 1
                if value["total"] is not None and value["total"] < 0:
                    violations.append(
                        _quality_violation(feature, state_name, kind, "negative_total")
                    )
        plan_oi = feature["plan_state"]["oi"]
        touch_oi = feature["touch_state"]["oi"]
        if plan_oi and touch_oi and plan_oi["selected_series"] != touch_oi["selected_series"]:
            violations.append(_quality_violation(feature, "plan_touch", "oi", "series_change"))
        if (
            plan_oi
            and touch_oi
            and plan_oi["active_strike_count"] != touch_oi["active_strike_count"]
        ):
            checks["strike_grid_size_change_count"] += 1
        if feature["plan_oi_snapshot_time"] == feature["touch_oi_snapshot_time"]:
            checks["repeated_oi_snapshot_count"] += 1
        if feature["plan_volume_snapshot_time"] == feature["touch_volume_snapshot_time"]:
            checks["repeated_volume_snapshot_count"] += 1
    return {
        **dict(sorted(checks.items())),
        "hard_violation_count": len(violations),
        "violations": violations,
        "settled_oi_described_as_live_flow": False,
        "oi_and_intraday_volume_kept_separate": True,
        "research_only": True,
        "signal_allowed": False,
    }


def build_robustness_report(
    features: list[dict[str, Any]],
    matched: dict[str, Any],
    variant_outcomes: dict[str, list[dict[str, Any]]],
    *,
    seed: int = 31012,
    bootstrap_samples: int = 2000,
) -> dict[str, Any]:
    pairs = matched["F2"]["pairs"]
    deltas_by_session: dict[str, list[float]] = defaultdict(list)
    for row in pairs:
        deltas_by_session[row["session_date"]].append(row["net_points_difference"])
    session_deltas = {
        session: mean(values) for session, values in deltas_by_session.items()
    }
    loso = []
    for removed in sorted(session_deltas):
        remaining = [value for session, value in session_deltas.items() if session != removed]
        loso.append(
            {
                "removed_session": removed,
                "mean_matched_delta": mean(remaining) if remaining else None,
            }
        )
    bootstrap = _session_bootstrap(session_deltas, seed, bootstrap_samples)
    f0_by_opportunity = _opportunity_means(variant_outcomes.get("F0", []))
    session_by_opportunity = {
        row["opportunity_id"]: row["session_date"]
        for row in features
        if row["mapping_mode"] == "same_time_basis"
    }
    eligibility = {
        row["opportunity_id"]: bool(
            row["plan_state"]["oi"]
            and row["plan_state"]["oi"]["top_5"]
            and row["plan_state"]["oi"]["distance_to_entry_sd"] <= 0.25
        )
        for row in features
        if row["mapping_mode"] == "same_time_basis"
    }
    retention_by_session = _retention_by_session(
        variant_outcomes.get("F1", []), variant_outcomes.get("F2", [])
    )
    permutation = _session_permutation_test(
        f0_by_opportunity,
        eligibility,
        session_by_opportunity,
        seed,
        1000,
    )
    distance_only = [
        value
        for opportunity_id, value in f0_by_opportunity.items()
        if _distance_only_eligible(features, opportunity_id)
    ]
    prior_session = _prior_session_control(features, f0_by_opportunity)
    shifted = _shifted_label_control(eligibility, f0_by_opportunity, seed)
    raw_p_values = [
        permutation["raw_p_value"],
        shifted["raw_p_value"],
        prior_session["raw_p_value"],
    ]
    q_values = _benjamini_hochberg(raw_p_values)
    controls = [permutation, shifted, prior_session]
    for control, q_value in zip(controls, q_values, strict=True):
        control["adjusted_q_value"] = q_value
    return {
        "leave_one_session_out": loso,
        "leave_one_session_out_range": {
            "min": min(
                row["mean_matched_delta"]
                for row in loso
                if row["mean_matched_delta"] is not None
            )
            if loso
            else None,
            "max": max(
                row["mean_matched_delta"]
                for row in loso
                if row["mean_matched_delta"] is not None
            )
            if loso
            else None,
        },
        "session_clustered_bootstrap": bootstrap,
        "session_clustered_bootstrap_metrics": _paired_metric_bootstrap(
            pairs, seed, bootstrap_samples, retention_by_session
        ),
        "permutation_test": permutation,
        "random_shifted_wall_control": shifted,
        "prior_session_oi_control": prior_session,
        "distance_only_control": {
            "opportunity_count": len(distance_only),
            "mean_net_points": mean(distance_only) if distance_only else None,
        },
        "multiple_comparison": {
            "hypothesis_count": len(raw_p_values),
            "method": "benjamini_hochberg",
        },
        "chronological_development_holdout": _chronological_episode_split(
            session_deltas
        ),
        "research_only": True,
        "signal_allowed": False,
    }


def build_execution_cost_stress(
    variant_outcomes: dict[str, list[dict[str, Any]]],
    episode_map: dict[str, Any],
) -> dict[str, Any]:
    scenarios = []
    spreads = (0.3, 0.5, 1.0, 1.5)
    slippages = (0.0, 0.2, 0.5)
    for variant, rows in sorted(variant_outcomes.items()):
        for spread in spreads:
            for slippage in slippages:
                adjusted = [
                    float(row["net_points"]) + 1.0 - spread - 2 * slippage
                    for row in rows
                    if row.get("net_points") is not None
                ]
                scenarios.append(
                    {
                        "variant": variant,
                        "spread_points": spread,
                        "slippage_points_per_side": slippage,
                        "configuration_outcome_count": len(adjusted),
                        "unique_opportunity_count": len(
                            {row["opportunity_id"] for row in rows}
                        ),
                        "unique_episode_count": episode_map["unique_episode_count"],
                        "net_expectancy_points": mean(adjusted) if adjusted else None,
                        "strategy_side_summaries": _cost_strategy_summaries(
                            rows, spread, slippage
                        ),
                    }
                )
    return {
        "price_source": "dukascopy_xauusd_bid_m1",
        "long_execution": "entry synthetic ask; exit bid",
        "short_execution": "entry bid; exit synthetic ask",
        "same_bar_policy": "conservative_stop_first",
        "cost_scenarios_multiply_sample": False,
        "scenarios": scenarios,
        "research_only": True,
        "signal_allowed": False,
    }


class AppendOnlyJournal:
    def __init__(self, root: Path, protocol_version: str, protocol_hash_value: str) -> None:
        self.root = root
        self.protocol_version = protocol_version
        self.protocol_hash = protocol_hash_value
        root.mkdir(parents=True, exist_ok=True)

    def append(self, stream: str, row: dict[str, Any]) -> Path:
        allowed = {
            "plans",
            "opportunities",
            "confirmations",
            "outcomes",
            "daily_summary",
        }
        if stream not in allowed:
            raise ValueError(f"unsupported journal stream: {stream}")
        path = self.root / f"{stream}.jsonl"
        existing = self._read(path)
        record_id = row["record_id"]
        finalized = {
            item["record_id"]
            for item in existing
            if item.get("finalized") and not item.get("superseded_by")
        }
        if record_id in finalized and not row.get("supersedes_record_id"):
            raise ValueError("finalized journal records are append-only")
        payload = {
            **row,
            "protocol_version": self.protocol_version,
            "protocol_hash": self.protocol_hash,
            "research_only": True,
            "signal_allowed": False,
        }
        with path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(payload, sort_keys=True) + "\n")
        return path

    def contains(self, stream: str, record_id: str) -> bool:
        return any(
            row.get("record_id") == record_id
            for row in self._read(self.root / f"{stream}.jsonl")
        )

    @staticmethod
    def _read(path: Path) -> list[dict[str, Any]]:
        if not path.exists():
            return []
        return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]


def _episode_record(
    planning_mode,
    key,
    number,
    rows,
    *,
    reset_timestamp,
    reset_reason,
    reset_sd,
):
    return {
        "episode_id": f"{key[0]}:{planning_mode}:{key[1]}:{key[2]}:E{number}",
        "session_date": key[0],
        "planning_mode": planning_mode,
        "side": key[1],
        "entry_definition": key[2],
        "reset_sd": reset_sd,
        "first_plan_time": min(row["planning_at"] for row in rows),
        "last_plan_time": max(row["planning_at"] for row in rows),
        "first_touch_time": min(row["first_touch_time"] for row in rows),
        "opportunity_ids": sorted({row["opportunity_id"] for row in rows}),
        "plan_version_ids": [row["plan_version_id"] for row in rows],
        "reset_timestamp": reset_timestamp.isoformat() if reset_timestamp else None,
        "reset_reason": reset_reason,
    }


def _find_reset(prior, current, feature, bars, *, reset_sd, exited_at):
    start = datetime.fromisoformat(prior["first_touch_time"])
    end = datetime.fromisoformat(current["first_touch_time"])
    if exited_at and start < exited_at <= end:
        return exited_at, "previous_filled_trade_exited"
    if feature is None:
        return None, None
    entry = float(prior["entry_level"])
    one_sd = float(feature["one_sd_points"])
    center = float(feature["xau_reference"])
    side = prior["side"]
    for bar in bars:
        if not start < bar.timestamp <= end:
            continue
        if side == "long_reversion":
            if bar.high >= center:
                return bar.timestamp, "crossed_mapped_center"
            if bar.high >= entry + reset_sd * one_sd:
                return bar.timestamp, f"returned_{reset_sd}sd_inside"
        else:
            if bar.low <= center:
                return bar.timestamp, "crossed_mapped_center"
            if bar.low <= entry - reset_sd * one_sd:
                return bar.timestamp, f"returned_{reset_sd}sd_inside"
    return None, None


def _outcome_index(rows):
    return {(row["opportunity_id"], row["strategy_id"]): row for row in rows}


def _paired_rows(baseline, variant, *, baseline_name, variant_name):
    pairs = []
    for key in sorted(set(baseline) & set(variant)):
        left = baseline[key]
        right = variant[key]
        pairs.append(
            {
                "opportunity_id": key[0],
                "strategy_id": key[1],
                "session_date": left["session_date"],
                "side": left["side"],
                "planning_mode": left["planning_mode"],
                "baseline_variant": baseline_name,
                "comparison_variant": variant_name,
                "entry_slippage_points": (
                    float(right.get("entry_price", left.get("entry_level", 0)))
                    - float(left.get("entry_level", left.get("entry_price", 0)))
                ),
                "baseline_status": left["status"],
                "comparison_status": right["status"],
                "baseline_net_points": float(left["net_points"]),
                "comparison_net_points": float(right["net_points"]),
                "baseline_mae_points": float(left["mae_points"]),
                "comparison_mae_points": float(right["mae_points"]),
                "net_points_difference": float(right["net_points"])
                - float(left["net_points"]),
                "mfe_difference": float(right["mfe_points"])
                - float(left["mfe_points"]),
                "mae_difference": float(right["mae_points"])
                - float(left["mae_points"]),
                "duration_difference_minutes": _duration(right) - _duration(left),
            }
        )
    return pairs


def _paired_summary(pairs):
    return {
        "pair_count": len(pairs),
        "unique_opportunity_count": len({row["opportunity_id"] for row in pairs}),
        "mean_net_points_difference": _average(
            row["net_points_difference"] for row in pairs
        ),
        "median_net_points_difference": _median(
            row["net_points_difference"] for row in pairs
        ),
        "mean_mfe_difference": _average(row["mfe_difference"] for row in pairs),
        "mean_mae_difference": _average(row["mae_difference"] for row in pairs),
        "mean_duration_difference_minutes": _average(
            row["duration_difference_minutes"] for row in pairs
        ),
    }


def _summarize_rows(rows):
    return {
        "configuration_outcome_count": len(rows),
        "unique_opportunity_count": len({row["opportunity_id"] for row in rows}),
        "mean_net_points": _average(row["net_points"] for row in rows),
        "median_net_points": _median(row["net_points"] for row in rows),
        "win_rate": (
            sum(float(row["net_points"]) > 0 for row in rows) / len(rows) if rows else None
        ),
    }


def _strategy_summaries(variant_outcomes, episode_by_opportunity):
    summaries = []
    for variant, rows in sorted(variant_outcomes.items()):
        grouped = defaultdict(list)
        for row in rows:
            grouped[row["strategy_id"]].append(row)
        for strategy, items in sorted(grouped.items()):
            net = [float(row["net_points"]) for row in items]
            summaries.append(
                {
                    "variant": variant,
                    "strategy_id": strategy,
                    "unique_opportunity_count": len(
                        {row["opportunity_id"] for row in items}
                    ),
                    "unique_episode_count": len(
                        {
                            episode_by_opportunity[row["opportunity_id"]]
                            for row in items
                            if row["opportunity_id"] in episode_by_opportunity
                        }
                    ),
                    "independent_session_count": len(
                        {row["session_date"] for row in items}
                    ),
                    "target_hit_count": sum(
                        row["status"] == "target_hit" for row in items
                    ),
                    "stop_hit_count": sum(row["status"] == "stop_hit" for row in items),
                    "time_exit_count": sum(
                        row["status"].startswith("time_exit") for row in items
                    ),
                    "mean_net_points": mean(net) if net else None,
                    "median_net_points": median(net) if net else None,
                    "standard_deviation_points": pstdev(net) if len(net) > 1 else 0.0,
                    "win_rate": sum(value > 0 for value in net) / len(net) if net else None,
                    "average_mfe_points": _average(row["mfe_points"] for row in items),
                    "average_mae_points": _average(row["mae_points"] for row in items),
                    "maximum_drawdown_points": _max_drawdown(net),
                    "maximum_consecutive_losses": _max_consecutive_losses(net),
                }
            )
    return summaries


def _equal_weighted_summary(variant_outcomes):
    results = []
    for variant, rows in sorted(variant_outcomes.items()):
        by_strategy = defaultdict(list)
        for row in rows:
            by_strategy[row["strategy_id"]].append(float(row["net_points"]))
        means = [mean(values) for values in by_strategy.values() if values]
        results.append(
            {
                "variant": variant,
                "strategy_count": len(means),
                "equal_weighted_mean_net_points": mean(means) if means else None,
            }
        )
    return results


def _quality_violation(feature, state, kind, reason):
    return {
        "opportunity_id": feature["opportunity_id"],
        "state": state,
        "feature_kind": kind,
        "reason": reason,
    }


def _session_bootstrap(session_deltas, seed, samples):
    if not session_deltas:
        return {"samples": samples, "mean": None, "ci95": [None, None]}
    rng = random.Random(seed)
    values = list(session_deltas.values())
    estimates = [mean(rng.choices(values, k=len(values))) for _ in range(samples)]
    estimates.sort()
    return {
        "seed": seed,
        "unit": "independent_session",
        "samples": samples,
        "mean": mean(estimates),
        "ci95": [
            estimates[int(samples * 0.025)],
            estimates[min(int(samples * 0.975), samples - 1)],
        ],
    }


def _session_permutation_test(values, eligibility, session_by_id, seed, samples):
    session_values = defaultdict(list)
    session_labels = defaultdict(list)
    for opportunity_id in sorted(set(values) & set(eligibility)):
        session = session_by_id.get(opportunity_id)
        if session is None:
            continue
        session_values[session].append(values[opportunity_id])
        session_labels[session].append(eligibility[opportunity_id])
    sessions = sorted(session_values)
    values_by_session = {key: mean(session_values[key]) for key in sessions}
    labels = [any(session_labels[key]) for key in sessions]
    observed = _label_difference(sessions, values_by_session, labels)
    rng = random.Random(seed)
    estimates = []
    for _ in range(samples):
        shuffled = labels[:]
        rng.shuffle(shuffled)
        estimates.append(_label_difference(sessions, values_by_session, shuffled))
    p = (
        (sum(abs(value) >= abs(observed) for value in estimates) + 1) / (samples + 1)
        if observed is not None
        else 1.0
    )
    return {
        "name": "session_label_permutation",
        "unit": "independent_session",
        "seed": seed,
        "samples": samples,
        "observed_difference": observed,
        "raw_p_value": p,
    }


def _shifted_label_control(eligibility, values, seed):
    ids = sorted(set(values) & set(eligibility))
    labels = [eligibility[item] for item in ids]
    rng = random.Random(seed + 1)
    shifted = labels[:]
    rng.shuffle(shifted)
    observed = _label_difference(ids, values, shifted)
    return {
        "name": "random_shifted_wall",
        "seed": seed + 1,
        "observed_difference": observed,
        "raw_p_value": 1.0,
    }


def _prior_session_control(features, values):
    rows = sorted(
        [row for row in features if row["mapping_mode"] == "same_time_basis"],
        key=lambda row: (row["session_date"], row["opportunity_id"]),
    )
    session_labels = {}
    for row in rows:
        oi = row["plan_state"]["oi"] or {}
        session_labels.setdefault(row["session_date"], []).append(
            bool(oi.get("top_5") and (oi.get("distance_to_entry_sd") or math.inf) <= 0.25)
        )
    sessions = sorted(session_labels)
    prior = {
        sessions[index]: any(session_labels[sessions[index - 1]])
        for index in range(1, len(sessions))
    }
    selected = [
        value
        for row in rows
        if prior.get(row["session_date"], False)
        for value in [values.get(row["opportunity_id"])]
        if value is not None
    ]
    return {
        "name": "prior_session_oi",
        "opportunity_count": len(selected),
        "mean_net_points": mean(selected) if selected else None,
        "raw_p_value": 1.0,
    }


def _distance_only_eligible(features, opportunity_id):
    row = next(
        (
            item
            for item in features
            if item["mapping_mode"] == "same_time_basis"
            and item["opportunity_id"] == opportunity_id
        ),
        None,
    )
    if not row or not row["plan_state"]["oi"]:
        return False
    return row["plan_state"]["oi"]["distance_to_entry_sd"] <= 0.25


def _opportunity_means(rows):
    grouped = defaultdict(list)
    for row in rows:
        grouped[row["opportunity_id"]].append(float(row["net_points"]))
    return {key: mean(values) for key, values in grouped.items()}


def _label_difference(ids, values, labels):
    retained = [values[item] for item, label in zip(ids, labels, strict=True) if label]
    rejected = [values[item] for item, label in zip(ids, labels, strict=True) if not label]
    if not retained or not rejected:
        return None
    return mean(retained) - mean(rejected)


def _benjamini_hochberg(p_values):
    ordered = sorted(enumerate(p_values), key=lambda item: item[1])
    adjusted = [1.0] * len(p_values)
    running = 1.0
    for rank, (index, value) in reversed(list(enumerate(ordered, start=1))):
        running = min(running, value * len(p_values) / rank)
        adjusted[index] = min(running, 1.0)
    return adjusted


def _chronological_episode_split(session_deltas):
    sessions = sorted(session_deltas)
    split = max(int(len(sessions) * 0.7), 1) if sessions else 0
    development = sessions[:split]
    holdout = sessions[split:]
    return {
        "development_session_count": len(development),
        "holdout_session_count": len(holdout),
        "development_mean_delta": _average(session_deltas[item] for item in development),
        "holdout_mean_delta": _average(session_deltas[item] for item in holdout),
    }


def _chronological_rows(rows):
    sessions = sorted({row["session_date"] for row in rows})
    split = max(int(len(sessions) * 0.7), 1) if sessions else 0
    development = set(sessions[:split])
    holdout = set(sessions[split:])
    return {
        "development": _summarize_rows(
            [row for row in rows if row["session_date"] in development]
        ),
        "holdout": _summarize_rows(
            [row for row in rows if row["session_date"] in holdout]
        ),
    }


def _chronological_pairs(pairs):
    sessions = sorted({row["session_date"] for row in pairs})
    split = max(int(len(sessions) * 0.7), 1) if sessions else 0
    development = set(sessions[:split])
    holdout = set(sessions[split:])
    return {
        "development": _paired_summary(
            [row for row in pairs if row["session_date"] in development]
        ),
        "holdout": _paired_summary(
            [row for row in pairs if row["session_date"] in holdout]
        ),
    }


def _paired_metric_bootstrap(pairs, seed, samples, retention_by_session):
    grouped = defaultdict(list)
    for row in pairs:
        grouped[row["session_date"]].append(row)
    if not grouped:
        return {
            "unit": "independent_session",
            "net_points_difference_ci95": [None, None],
            "win_rate_difference_ci95": [None, None],
            "mae_difference_ci95": [None, None],
            "opportunity_retention_rate_ci95": [None, None],
        }
    session_metrics = {}
    for session, rows in grouped.items():
        session_metrics[session] = {
            "net": mean(row["net_points_difference"] for row in rows),
            "win": mean(
                (row["comparison_net_points"] > 0) - (row["baseline_net_points"] > 0)
                for row in rows
            ),
            "mae": mean(row["mae_difference"] for row in rows),
            "retention": retention_by_session.get(session, 0.0),
        }
    rng = random.Random(seed + 10)
    sessions = sorted(session_metrics)
    estimates = defaultdict(list)
    for _ in range(samples):
        selected = rng.choices(sessions, k=len(sessions))
        for metric in ("net", "win", "mae", "retention"):
            estimates[metric].append(
                mean(session_metrics[session][metric] for session in selected)
            )
    return {
        "unit": "independent_session",
        "seed": seed + 10,
        "samples": samples,
        "net_points_difference_ci95": _ci95(estimates["net"]),
        "win_rate_difference_ci95": _ci95(estimates["win"]),
        "mae_difference_ci95": _ci95(estimates["mae"]),
        "opportunity_retention_rate_ci95": _ci95(estimates["retention"]),
    }


def _cost_strategy_summaries(rows, spread, slippage):
    groups = defaultdict(list)
    for row in rows:
        if row.get("net_points") is None:
            continue
        groups[(row["strategy_id"], row["side"])].append(
            float(row["net_points"]) + 1.0 - spread - 2 * slippage
        )
    return [
        {
            "strategy_id": key[0],
            "side": key[1],
            "configuration_outcome_count": len(values),
            "net_expectancy_points": mean(values),
        }
        for key, values in sorted(groups.items())
    ]


def _retention_by_session(baseline_rows, retained_rows):
    baseline = defaultdict(set)
    retained = defaultdict(set)
    for row in baseline_rows:
        baseline[row["session_date"]].add(row["opportunity_id"])
    for row in retained_rows:
        retained[row["session_date"]].add(row["opportunity_id"])
    return {
        session: len(retained.get(session, set())) / len(opportunities)
        for session, opportunities in baseline.items()
        if opportunities
    }


def _ci95(values):
    if not values:
        return [None, None]
    ordered = sorted(values)
    return [
        ordered[int(len(ordered) * 0.025)],
        ordered[min(int(len(ordered) * 0.975), len(ordered) - 1)],
    ]


def _mean_difference(left, right):
    return mean(left) - mean(right) if left and right else None


def _duration(row):
    if not row.get("triggered_at") or not row.get("exited_at"):
        return 0.0
    return (
        datetime.fromisoformat(row["exited_at"])
        - datetime.fromisoformat(row["triggered_at"])
    ).total_seconds() / 60


def _average(values):
    present = [float(value) for value in values if value is not None]
    return mean(present) if present else None


def _median(values):
    present = [float(value) for value in values if value is not None]
    return median(present) if present else None


def _max_drawdown(values):
    peak = equity = maximum = 0.0
    for value in values:
        equity += value
        peak = max(peak, equity)
        maximum = max(maximum, peak - equity)
    return maximum


def _max_consecutive_losses(values):
    current = maximum = 0
    for value in values:
        current = current + 1 if value < 0 else 0
        maximum = max(maximum, current)
    return maximum
