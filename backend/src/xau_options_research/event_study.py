from __future__ import annotations

import math
import random
from collections import defaultdict
from statistics import mean, median
from typing import Any

FEATURES = (
    "basis_drift",
    "price_z_from_morning",
    "atm_iv",
    "atm_iv_change_since_morning",
    "iv_slope_30m",
    "oi_distance_sd",
    "oi_rank",
    "oi_percentile",
    "oi_imbalance",
    "oi_change",
    "volume_distance_sd",
    "volume_percentile",
    "volume_change",
    "volume_change_percentile",
    "dte",
)


def build_event_study(
    labels: list[dict[str, Any]],
    *,
    seed: int = 32,
    bootstrap_iterations: int = 500,
) -> dict[str, Any]:
    summaries = []
    for feature in FEATURES:
        rows = [
            row
            for row in labels
            if _number(row.get(feature)) is not None
            and _number(row.get("forward_return_30m")) is not None
        ]
        if not rows:
            summaries.append(_empty(feature))
            continue
        x = [float(row[feature]) for row in rows]
        y = [float(row["forward_return_30m"]) for row in rows]
        rho = _spearman(x, y)
        summaries.append(
            {
                "feature": feature,
                "event_count": len(rows),
                "independent_session_count": len({row["session_date"] for row in rows}),
                "positive_30m_rate": sum(value > 0 for value in y) / len(y),
                "mean_forward_return_30m": mean(y),
                "median_forward_return_30m": median(y),
                "mean_mfe_30m": _average(row.get("mfe_30m") for row in rows),
                "median_mfe_30m": _median(row.get("mfe_30m") for row in rows),
                "mean_mae_30m": _average(row.get("mae_30m") for row in rows),
                "median_mae_30m": _median(row.get("mae_30m") for row in rows),
                "session_clustered_mean_ci95": _session_bootstrap(
                    rows, seed=f"{seed}:{feature}", iterations=bootstrap_iterations
                ),
                "spearman_rho": rho,
                "raw_p_value": _correlation_p_value(rho, len(rows)),
                "quantiles": _quantile_table(rows, feature),
            }
        )
    _add_bh_q_values(summaries)
    return {
        "feature_summaries": summaries,
        "correlation_is_not_causation": True,
        "resampling_unit": "session",
        "research_only": True,
        "signal_allowed": False,
    }


def _quantile_table(rows: list[dict[str, Any]], feature: str) -> list[dict[str, Any]]:
    ordered = sorted(rows, key=lambda row: float(row[feature]))
    groups = []
    for bucket in range(4):
        start = int(len(ordered) * bucket / 4)
        end = int(len(ordered) * (bucket + 1) / 4)
        items = ordered[start:end]
        if not items:
            continue
        groups.append(
            {
                "quartile": bucket + 1,
                "event_count": len(items),
                "feature_min": min(float(row[feature]) for row in items),
                "feature_max": max(float(row[feature]) for row in items),
                "mean_forward_return_30m": mean(float(row["forward_return_30m"]) for row in items),
            }
        )
    return groups


def _session_bootstrap(
    rows: list[dict[str, Any]], *, seed: str, iterations: int
) -> list[float] | None:
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        grouped[row["session_date"]].append(row)
    sessions = sorted(grouped)
    if not sessions:
        return None
    rng = random.Random(seed)
    samples = []
    for _ in range(iterations):
        selected = [rng.choice(sessions) for _ in sessions]
        values = [
            float(row["forward_return_30m"]) for session in selected for row in grouped[session]
        ]
        samples.append(mean(values))
    samples.sort()
    return [samples[int(0.025 * (len(samples) - 1))], samples[int(0.975 * (len(samples) - 1))]]


def _spearman(x: list[float], y: list[float]) -> float | None:
    if len(x) < 3:
        return None
    rx = _ranks(x)
    ry = _ranks(y)
    mx, my = mean(rx), mean(ry)
    numerator = sum((a - mx) * (b - my) for a, b in zip(rx, ry, strict=True))
    denominator = math.sqrt(sum((a - mx) ** 2 for a in rx) * sum((b - my) ** 2 for b in ry))
    return numerator / denominator if denominator else None


def _ranks(values: list[float]) -> list[float]:
    ordered = sorted(enumerate(values), key=lambda item: item[1])
    ranks = [0.0] * len(values)
    index = 0
    while index < len(ordered):
        end = index
        while end + 1 < len(ordered) and ordered[end + 1][1] == ordered[index][1]:
            end += 1
        rank = (index + end + 2) / 2
        for position in range(index, end + 1):
            ranks[ordered[position][0]] = rank
        index = end + 1
    return ranks


def _correlation_p_value(rho: float | None, count: int) -> float | None:
    if rho is None or count < 4 or abs(rho) >= 1:
        return None
    statistic = abs(rho) * math.sqrt((count - 2) / max(1 - rho * rho, 1e-12))
    return math.erfc(statistic / math.sqrt(2))


def _add_bh_q_values(rows: list[dict[str, Any]]) -> None:
    valid = sorted(
        (
            (index, row["raw_p_value"])
            for index, row in enumerate(rows)
            if row.get("raw_p_value") is not None
        ),
        key=lambda item: item[1],
    )
    total = len(valid)
    running = 1.0
    for rank, (index, value) in reversed(list(enumerate(valid, start=1))):
        running = min(running, float(value) * total / rank)
        rows[index]["bh_q_value"] = min(running, 1.0)
    for row in rows:
        row.setdefault("bh_q_value", None)


def _empty(feature: str) -> dict[str, Any]:
    return {
        "feature": feature,
        "event_count": 0,
        "independent_session_count": 0,
        "positive_30m_rate": None,
        "mean_forward_return_30m": None,
        "median_forward_return_30m": None,
        "mean_mfe_30m": None,
        "median_mfe_30m": None,
        "mean_mae_30m": None,
        "median_mae_30m": None,
        "session_clustered_mean_ci95": None,
        "spearman_rho": None,
        "raw_p_value": None,
        "bh_q_value": None,
        "quantiles": [],
    }


def _number(value: Any) -> float | None:
    return float(value) if isinstance(value, int | float) and not isinstance(value, bool) else None


def _average(values: Any) -> float | None:
    valid = [float(value) for value in values if value is not None]
    return mean(valid) if valid else None


def _median(values: Any) -> float | None:
    valid = [float(value) for value in values if value is not None]
    return median(valid) if valid else None
