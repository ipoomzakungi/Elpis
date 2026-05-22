"""Monte Carlo and placebo validation for reviewed guru episode logic.

Validation is strictly post-review: review suggestions are assumed frozen before
future outcome fields are joined. Results are research-only and never become
live trading instructions.
"""

from __future__ import annotations

import math
import random
from dataclasses import dataclass
from pathlib import Path
from statistics import mean, pstdev
from typing import Any

import polars as pl

from research_xau_vol_oi.config import ResearchConfig


PRIMARY_WINDOW = "4h"
DEFAULT_MONTE_CARLO_ITERATIONS = 5_000
VALIDATION_DECISIONS = (
    "GURU_RULE_VALIDATION_NOT_READY",
    "GURU_RULE_CONTEXT_ONLY",
    "GURU_RULE_PROMISING",
    "GURU_RULE_PASSED_MONTE_CARLO",
    "GURU_RULE_FAILED_MONTE_CARLO",
)


@dataclass(frozen=True)
class GuruMonteCarloValidationResult:
    """Monte Carlo validation rows and conservative final decision."""

    validation: pl.DataFrame
    markov_transitions: pl.DataFrame
    final_decision: str


def run_guru_monte_carlo_validation_layer(
    *,
    episodes: pl.DataFrame,
    outcomes: pl.DataFrame,
    final_suggestions: pl.DataFrame,
    signal_events: pl.DataFrame,
    output_dir: Path,
    charts_dir: Path,
    config: ResearchConfig | None = None,
    iterations: int = DEFAULT_MONTE_CARLO_ITERATIONS,
) -> GuruMonteCarloValidationResult:
    """Run Monte Carlo, placebo, bootstrap, matched-state, and Markov tests."""

    cfg = config or ResearchConfig()
    output_dir.mkdir(parents=True, exist_ok=True)
    charts_dir.mkdir(parents=True, exist_ok=True)
    validation, markov = guru_monte_carlo_validation(
        episodes=episodes,
        outcomes=outcomes,
        final_suggestions=final_suggestions,
        signal_events=signal_events,
        config=cfg,
        iterations=iterations,
    )
    final_decision = guru_rule_validation_decision(validation)
    validation.write_csv(output_dir / "guru_monte_carlo_validation.csv")
    markov.write_csv(output_dir / "guru_markov_transition_matrix.csv")
    write_guru_monte_carlo_report(
        output_dir / "guru_monte_carlo_report.md",
        validation=validation,
        markov=markov,
        final_decision=final_decision,
        iterations=iterations,
    )
    write_monte_carlo_charts(charts_dir=charts_dir, validation=validation)
    return GuruMonteCarloValidationResult(
        validation=validation,
        markov_transitions=markov,
        final_decision=final_decision,
    )


def guru_monte_carlo_validation(
    *,
    episodes: pl.DataFrame,
    outcomes: pl.DataFrame,
    final_suggestions: pl.DataFrame,
    signal_events: pl.DataFrame,
    config: ResearchConfig | None = None,
    iterations: int = DEFAULT_MONTE_CARLO_ITERATIONS,
) -> tuple[pl.DataFrame, pl.DataFrame]:
    """Return validation rows and Markov transition matrix."""

    cfg = config or ResearchConfig()
    joined = _primary_join(episodes, outcomes, final_suggestions)
    if joined.is_empty():
        return _empty_validation(), _empty_markov()
    rng = random.Random(cfg.random_seed)
    validation_rows = []
    set_masks = build_validation_set_masks(joined)
    all_rows = joined.to_dicts()
    no_trade_rows = _no_trade_count(signal_events)
    for set_name, selected_ids in set_masks.items():
        selected = [row for row in all_rows if row.get("episode_id") in selected_ids]
        controls = [row for row in all_rows if row.get("episode_id") not in selected_ids]
        validation_rows.extend(
            _validation_rows_for_set(
                set_name=set_name,
                selected=selected,
                controls=controls,
                all_rows=all_rows,
                rng=rng,
                iterations=iterations,
                no_trade_rows_retained=no_trade_rows,
            )
        )
    markov = markov_transition_matrix(joined)
    validation_rows.extend(_markov_validation_rows(set_masks, joined, markov, no_trade_rows))
    return (_rows_frame(validation_rows) if validation_rows else _empty_validation()), markov


def build_validation_set_masks(joined: pl.DataFrame) -> dict[str, set[str]]:
    """Define frozen review/suggestion sets for validation."""

    rows = joined.to_dicts()
    sets = {
        "HUMAN_APPROVED": {
            str(row["episode_id"])
            for row in rows
            if str(row.get("reviewer_decision") or "").upper() == "APPROVE"
        },
        "CODEX_SUGGEST_APPROVE_PREVIEW": {
            str(row["episode_id"])
            for row in rows
            if str(row.get("suggested_review_decision") or "") == "SUGGEST_APPROVE"
        },
        "CONTEXT_ONLY_CONTROL": {
            str(row["episode_id"])
            for row in rows
            if str(row.get("corrected_thesis_type") or row.get("thesis_type") or "") in {"CONTEXT_ONLY", "WATCH_ONLY"}
            or str(row.get("suggested_review_decision") or "") == "SUGGEST_NEEDS_MORE_CONTEXT"
        },
        "REJECTED_POST_EVENT_NEGATIVE": {
            str(row["episode_id"])
            for row in rows
            if str(row.get("suggested_review_decision") or "") in {"SUGGEST_REJECT", "SUGGEST_POST_EVENT_ONLY"}
            or str(row.get("thesis_type") or "") == "POST_EVENT_COMMENTARY"
        },
    }
    return sets


def markov_transition_matrix(joined: pl.DataFrame) -> pl.DataFrame:
    """Build state transition probabilities with and without guru rule tags."""

    if joined.is_empty():
        return _empty_markov()
    counts: dict[tuple[str, str, str], int] = {}
    for row in joined.to_dicts():
        from_state = _from_state(row)
        to_state = _to_state(row)
        group = "with_guru_rule" if row.get("suggested_review_decision") == "SUGGEST_APPROVE" else "without_guru_rule"
        counts[(group, from_state, to_state)] = counts.get((group, from_state, to_state), 0) + 1
    totals: dict[tuple[str, str], int] = {}
    for (group, from_state, _), count in counts.items():
        totals[(group, from_state)] = totals.get((group, from_state), 0) + count
    rows = []
    for (group, from_state, to_state), count in sorted(counts.items()):
        total = totals[(group, from_state)]
        rows.append(
            {
                "group": group,
                "from_state": from_state,
                "to_state": to_state,
                "count": count,
                "probability": count / total if total else None,
            }
        )
    return _rows_frame(rows) if rows else _empty_markov()


def guru_rule_validation_decision(validation: pl.DataFrame) -> str:
    """Return conservative final validation label."""

    if validation.is_empty():
        return "GURU_RULE_VALIDATION_NOT_READY"
    directional = validation.filter(pl.col("rule_set") == "HUMAN_APPROVED")
    preview = validation.filter(pl.col("rule_set") == "CODEX_SUGGEST_APPROVE_PREVIEW")
    candidate = directional if not directional.is_empty() else preview
    if candidate.is_empty() or candidate.get_column("episode_count").max() == 0:
        context = validation.filter(pl.col("rule_set") == "CONTEXT_ONLY_CONTROL")
        return "GURU_RULE_CONTEXT_ONLY" if not context.is_empty() else "GURU_RULE_VALIDATION_NOT_READY"
    pass_rows = candidate.filter(pl.col("monte_carlo_pass"))
    if pass_rows.is_empty():
        failed = candidate.filter(pl.col("episode_count") >= 20)
        return "GURU_RULE_FAILED_MONTE_CARLO" if not failed.is_empty() else "GURU_RULE_PROMISING"
    return "GURU_RULE_PASSED_MONTE_CARLO"


def write_guru_monte_carlo_report(
    path: Path,
    *,
    validation: pl.DataFrame,
    markov: pl.DataFrame,
    final_decision: str,
    iterations: int,
) -> None:
    """Write Markdown Monte Carlo validation report."""

    lines = [
        "# Guru Monte Carlo Validation Report",
        "",
        "Research-only validation after blind review suggestions are frozen.",
        "",
        f"- Final decision: `{final_decision}`",
        f"- Monte Carlo iterations: {iterations}",
        "",
        "## Validation Rows",
        "",
        _frame_markdown(validation),
        "",
        "## Permutation Test",
        "",
        _frame_markdown(_method_rows(validation, "PERMUTATION")),
        "",
        "## Date-Shift Placebo",
        "",
        _frame_markdown(_method_rows(validation, "DATE_SHIFT_PLACEBO")),
        "",
        "## Matched Market-State Placebo",
        "",
        _frame_markdown(_method_rows(validation, "MATCHED_MARKET_STATE_PLACEBO")),
        "",
        "## Bootstrap Confidence Interval",
        "",
        _frame_markdown(_method_rows(validation, "BOOTSTRAP_CI")),
        "",
        "## Markov Transition Test",
        "",
        _frame_markdown(markov),
        "",
        "## Final Guru Logic Decision",
        "",
        "- `GURU_RULE_PASSED_MONTE_CARLO` is blocked unless reviewed or clearly preview-labeled suggested rules pass "
        "permutation/placebo checks, have sufficient samples, have a stable bootstrap interval, use no future data "
        "in review, and exclude post-event commentary.",
    ]
    path.write_text("\n".join(lines), encoding="utf-8")


def write_monte_carlo_charts(*, charts_dir: Path, validation: pl.DataFrame) -> None:
    """Write SVG charts for Monte Carlo validation."""

    charts_dir.mkdir(parents=True, exist_ok=True)
    rows = validation.filter(pl.col("method") == "PERMUTATION").to_dicts() if not validation.is_empty() else []
    _write_bar_svg(
        charts_dir / "guru_monte_carlo_supported_rate.svg",
        title="Guru Monte Carlo support rate",
        labels=[str(row.get("rule_set")) for row in rows],
        values=[_float_or_zero(row.get("support_rate")) for row in rows],
    )
    _write_bar_svg(
        charts_dir / "guru_monte_carlo_expectancy_proxy.svg",
        title="Guru Monte Carlo expectancy proxy",
        labels=[str(row.get("rule_set")) for row in rows],
        values=[_float_or_zero(row.get("expectancy_proxy")) for row in rows],
    )
    _write_bar_svg(
        charts_dir / "guru_rule_placebo_distribution.svg",
        title="Guru placebo mean by set",
        labels=[str(row.get("rule_set")) for row in rows],
        values=[_float_or_zero(row.get("placebo_mean")) for row in rows],
    )


def _validation_rows_for_set(
    *,
    set_name: str,
    selected: list[dict[str, Any]],
    controls: list[dict[str, Any]],
    all_rows: list[dict[str, Any]],
    rng: random.Random,
    iterations: int,
    no_trade_rows_retained: int,
) -> list[dict[str, Any]]:
    selected_metrics = _metrics(selected)
    permutation = _random_metric_distribution(all_rows, len(selected), rng, iterations)
    date_shift = _random_metric_distribution(all_rows, len(selected), rng, iterations)
    matched_controls = _matched_controls(selected, controls, all_rows, rng)
    matched_metrics = _metrics(matched_controls)
    bootstrap = _bootstrap_distribution(selected, rng, iterations)
    base = {
        **selected_metrics,
        "rule_set": set_name,
        "no_trade_rows_retained": no_trade_rows_retained,
        "sample_size_warning": len(selected) < 20,
    }
    return [
        _validation_row(
            base,
            method="PERMUTATION",
            distribution=permutation,
            observed_metric=selected_metrics["support_rate"],
        ),
        _validation_row(
            base,
            method="DATE_SHIFT_PLACEBO",
            distribution=date_shift,
            observed_metric=selected_metrics["support_rate"],
        ),
        _validation_row(
            base,
            method="MATCHED_MARKET_STATE_PLACEBO",
            distribution=[matched_metrics["support_rate"]] if matched_controls else [],
            observed_metric=selected_metrics["support_rate"],
        ),
        _validation_row(
            base,
            method="BOOTSTRAP_CI",
            distribution=bootstrap,
            observed_metric=selected_metrics["support_rate"],
        ),
    ]


def _validation_row(
    base: dict[str, Any],
    *,
    method: str,
    distribution: list[float],
    observed_metric: float | None,
) -> dict[str, Any]:
    placebo_mean = mean(distribution) if distribution else None
    placebo_std = pstdev(distribution) if len(distribution) > 1 else None
    p_value = _p_value(distribution, observed_metric)
    ci_low, ci_high = _ci(distribution) if method == "BOOTSTRAP_CI" else (None, None)
    pass_flag = (
        bool(observed_metric is not None and p_value is not None and p_value <= 0.05)
        and not base["sample_size_warning"]
        and (ci_high is None or (ci_high - (ci_low or 0.0)) <= 0.50)
    )
    return {
        **base,
        "method": method,
        "observed_metric": observed_metric,
        "placebo_mean": placebo_mean,
        "placebo_std": placebo_std,
        "p_value": p_value,
        "bootstrap_ci_low": ci_low,
        "bootstrap_ci_high": ci_high,
        "monte_carlo_pass": pass_flag,
    }


def _markov_validation_rows(
    set_masks: dict[str, set[str]],
    joined: pl.DataFrame,
    markov: pl.DataFrame,
    no_trade_rows_retained: int,
) -> list[dict[str, Any]]:
    rows = []
    all_rows = joined.to_dicts()
    for set_name, ids in set_masks.items():
        selected = [row for row in all_rows if row.get("episode_id") in ids]
        expected = [_expected_transition(row) for row in selected]
        observed = [_to_state(row) for row in selected]
        correct = [exp == obs or (isinstance(exp, tuple) and obs in exp) for exp, obs in zip(expected, observed, strict=False)]
        metrics = _metrics(selected)
        transition_prob = mean(correct) if correct else None
        rows.append(
            {
                **metrics,
                "rule_set": set_name,
                "method": "MARKOV_TRANSITION",
                "observed_metric": transition_prob,
                "placebo_mean": _markov_without_rule_mean(markov),
                "placebo_std": None,
                "p_value": None,
                "bootstrap_ci_low": None,
                "bootstrap_ci_high": None,
                "monte_carlo_pass": False,
                "no_trade_rows_retained": no_trade_rows_retained,
                "sample_size_warning": len(selected) < 20,
            }
        )
    return rows


def _primary_join(episodes: pl.DataFrame, outcomes: pl.DataFrame, final_suggestions: pl.DataFrame) -> pl.DataFrame:
    if episodes.is_empty() or outcomes.is_empty():
        return pl.DataFrame()
    primary = outcomes.filter(pl.col("outcome_window") == PRIMARY_WINDOW)
    if primary.is_empty():
        primary = outcomes.group_by("episode_id").first()
    joined = episodes.join(primary, on="episode_id", how="left", suffix="_outcome")
    if final_suggestions.is_empty():
        return joined
    return joined.join(final_suggestions, on="episode_id", how="left", suffix="_suggestion")


def _metrics(rows: list[dict[str, Any]]) -> dict[str, Any]:
    episode_count = len(rows)
    supported = sum(1 for row in rows if row.get("outcome_label") == "THESIS_SUPPORTED")
    failed = sum(1 for row in rows if row.get("outcome_label") == "THESIS_FAILED")
    direction_values = [_bool_or_none(row.get("direction_correct")) for row in rows]
    target_values = [_bool_or_none(row.get("target_hit")) for row in rows]
    invalidation_values = [_bool_or_none(row.get("invalidation_hit")) for row in rows]
    expectancy_values = [_float_or_none(row.get("signed_close_return")) for row in rows]
    return {
        "episode_count": episode_count,
        "supported_count": supported,
        "failed_count": failed,
        "support_rate": supported / episode_count if episode_count else None,
        "direction_accuracy": _mean_bool(direction_values),
        "target_hit_rate": _mean_bool(target_values),
        "invalidation_hit_rate": _mean_bool(invalidation_values),
        "expectancy_proxy": _mean_float(expectancy_values),
    }


def _random_metric_distribution(
    rows: list[dict[str, Any]],
    sample_size: int,
    rng: random.Random,
    iterations: int,
) -> list[float]:
    if sample_size <= 0 or not rows:
        return []
    sample_size = min(sample_size, len(rows))
    values = []
    for _ in range(iterations):
        sample = rng.sample(rows, sample_size)
        metric = _metrics(sample)["support_rate"]
        if metric is not None:
            values.append(metric)
    return values


def _bootstrap_distribution(rows: list[dict[str, Any]], rng: random.Random, iterations: int) -> list[float]:
    if not rows:
        return []
    values = []
    for _ in range(iterations):
        sample = [rng.choice(rows) for _ in rows]
        metric = _metrics(sample)["support_rate"]
        if metric is not None:
            values.append(metric)
    return values


def _matched_controls(
    selected: list[dict[str, Any]],
    controls: list[dict[str, Any]],
    all_rows: list[dict[str, Any]],
    rng: random.Random,
) -> list[dict[str, Any]]:
    matches = []
    fallback = controls or all_rows
    for row in selected:
        candidates = [
            item
            for item in controls
            if _state_key(item) == _state_key(row) and item.get("episode_id") != row.get("episode_id")
        ]
        if not candidates:
            candidates = [item for item in fallback if item.get("episode_id") != row.get("episode_id")]
        if candidates:
            matches.append(rng.choice(candidates))
    return matches


def _state_key(row: dict[str, Any]) -> tuple[Any, ...]:
    return (
        _sigma_bucket(row.get("sigma_position")),
        row.get("wall_score_bucket"),
        row.get("open_side"),
        row.get("vol_regime"),
    )


def _from_state(row: dict[str, Any]) -> str:
    thesis = str(row.get("corrected_thesis_type") or row.get("thesis_type") or "")
    sigma = _float_or_none(row.get("sigma_position"))
    wall_bucket = str(row.get("wall_score_bucket") or "")
    if thesis == "NO_TRADE":
        return "NO_TRADE"
    if thesis == "PIN_OR_MAGNET":
        return "PIN"
    if thesis == "SQUEEZE_CONTINUATION":
        return "SQUEEZE"
    if wall_bucket == "high":
        return "APPROACH_WALL"
    if sigma is not None and abs(sigma) >= 0.8:
        return "EDGE_1SD"
    return "MIDDLE_1SD"


def _to_state(row: dict[str, Any]) -> str:
    if _bool(row.get("wall_accepted")):
        return "BREAK_ACCEPT"
    if _bool(row.get("wall_rejected")):
        return "REJECT_WALL"
    if _bool(row.get("broke_1sd")):
        return "EDGE_1SD"
    if _bool(row.get("stayed_inside_1sd")):
        return "MIDDLE_1SD"
    if str(row.get("expected_direction") or "") == "NO_TRADE":
        return "NO_TRADE"
    return "MIDDLE_1SD"


def _expected_transition(row: dict[str, Any]) -> str | tuple[str, ...]:
    thesis = str(row.get("corrected_thesis_type") or row.get("thesis_type") or "")
    if thesis == "REJECT_LEVEL":
        return "REJECT_WALL"
    if thesis == "BREAK_LEVEL":
        return "BREAK_ACCEPT"
    if thesis == "NO_TRADE":
        return ("NO_TRADE", "MIDDLE_1SD")
    if thesis == "RANGE_ROTATION":
        return "MIDDLE_1SD"
    if thesis == "SQUEEZE_CONTINUATION":
        return ("SQUEEZE", "BREAK_ACCEPT", "EDGE_1SD")
    if thesis == "PIN_OR_MAGNET":
        return ("PIN", "MIDDLE_1SD")
    return "MIDDLE_1SD"


def _markov_without_rule_mean(markov: pl.DataFrame) -> float | None:
    if markov.is_empty():
        return None
    rows = markov.filter(pl.col("group") == "without_guru_rule")
    if rows.is_empty():
        return None
    return rows.get_column("probability").mean()


def _p_value(distribution: list[float], observed: float | None) -> float | None:
    if observed is None or not distribution:
        return None
    return sum(1 for value in distribution if value >= observed) / len(distribution)


def _ci(values: list[float]) -> tuple[float | None, float | None]:
    if not values:
        return None, None
    ordered = sorted(values)
    low_index = int(0.025 * (len(ordered) - 1))
    high_index = int(0.975 * (len(ordered) - 1))
    return ordered[low_index], ordered[high_index]


def _sigma_bucket(value: Any) -> str:
    parsed = _float_or_none(value)
    if parsed is None:
        return "unknown"
    if abs(parsed) < 0.5:
        return "middle"
    if abs(parsed) < 1.0:
        return "edge"
    return "outside"


def _no_trade_count(signal_events: pl.DataFrame) -> int:
    if signal_events.is_empty() or "signal" not in signal_events.columns:
        return 0
    return signal_events.filter(pl.col("signal").str.contains("NO_TRADE")).height


def _method_rows(frame: pl.DataFrame, method: str) -> pl.DataFrame:
    if frame.is_empty() or "method" not in frame.columns:
        return frame
    return frame.filter(pl.col("method") == method)


def _mean_bool(values: list[bool | None]) -> float | None:
    clean = [value for value in values if value is not None]
    if not clean:
        return None
    return sum(1 for value in clean if value) / len(clean)


def _mean_float(values: list[float | None]) -> float | None:
    clean = [value for value in values if value is not None]
    return mean(clean) if clean else None


def _bool_or_none(value: Any) -> bool | None:
    if value in (None, ""):
        return None
    if isinstance(value, bool):
        return value
    text = str(value).lower()
    if text in {"true", "1"}:
        return True
    if text in {"false", "0"}:
        return False
    return None


def _bool(value: Any) -> bool:
    resolved = _bool_or_none(value)
    return bool(resolved)


def _float_or_none(value: Any) -> float | None:
    if value in (None, ""):
        return None
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return None
    return None if math.isnan(parsed) else parsed


def _float_or_zero(value: Any) -> float:
    parsed = _float_or_none(value)
    return parsed if parsed is not None else 0.0


def _frame_markdown(frame: pl.DataFrame) -> str:
    if frame.is_empty():
        return "_No rows._"
    columns = frame.columns
    rows = ["| " + " | ".join(columns) + " |", "|" + "|".join(["---"] * len(columns)) + "|"]
    for raw in frame.head(20).to_dicts():
        rows.append("| " + " | ".join(str(raw.get(column, "")) for column in columns) + " |")
    return "\n".join(rows)


def _rows_frame(rows: list[dict[str, Any]]) -> pl.DataFrame:
    return pl.DataFrame(rows, infer_schema_length=None)


def _empty_validation() -> pl.DataFrame:
    return pl.DataFrame(
        schema={
            "rule_set": pl.String,
            "method": pl.String,
            "episode_count": pl.Int64,
            "supported_count": pl.Int64,
            "failed_count": pl.Int64,
            "support_rate": pl.Float64,
            "direction_accuracy": pl.Float64,
            "target_hit_rate": pl.Float64,
            "invalidation_hit_rate": pl.Float64,
            "expectancy_proxy": pl.Float64,
            "observed_metric": pl.Float64,
            "placebo_mean": pl.Float64,
            "placebo_std": pl.Float64,
            "p_value": pl.Float64,
            "bootstrap_ci_low": pl.Float64,
            "bootstrap_ci_high": pl.Float64,
            "monte_carlo_pass": pl.Boolean,
            "sample_size_warning": pl.Boolean,
        }
    )


def _empty_markov() -> pl.DataFrame:
    return pl.DataFrame(
        schema={
            "group": pl.String,
            "from_state": pl.String,
            "to_state": pl.String,
            "count": pl.Int64,
            "probability": pl.Float64,
        }
    )


def _write_bar_svg(path: Path, *, title: str, labels: list[str], values: list[float]) -> None:
    width, height = 900, 300
    if not values:
        path.write_text(_svg(title, '<text x="40" y="80">No data.</text>'), encoding="utf-8")
        return
    maximum = max(max(abs(value) for value in values), 1.0)
    bar_width = max(4, (width - 80) / max(len(values), 1))
    body = []
    for index, value in enumerate(values):
        x = 40 + index * bar_width
        bar_height = abs(value) / maximum * (height - 90)
        y = height - 40 - bar_height
        color = "#0f766e" if value >= 0 else "#b91c1c"
        body.append(
            f'<rect x="{x:.1f}" y="{y:.1f}" width="{bar_width * 0.8:.1f}" '
            f'height="{bar_height:.1f}" fill="{color}"><title>{labels[index]}</title></rect>'
        )
    path.write_text(_svg(title, "\n".join(body)), encoding="utf-8")


def _svg(title: str, body: str) -> str:
    return (
        '<svg xmlns="http://www.w3.org/2000/svg" width="900" height="300" viewBox="0 0 900 300">'
        '<rect width="900" height="300" fill="#ffffff" />'
        f'<text x="40" y="30" font-size="18" font-family="Arial">{title}</text>'
        f"{body}</svg>"
    )
