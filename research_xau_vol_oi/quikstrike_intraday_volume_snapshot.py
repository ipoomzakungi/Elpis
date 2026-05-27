"""QuikStrike intraday volume snapshot ingest and wall scenarios.

This layer converts structured QuikStrike intraday option volume snapshots into
research-only wall context for the XAU indicator blueprint. It avoids OCR by
default, prefers CSV/table input when available, and treats intraday volume
walls as context rather than automatic directional evidence.
"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import polars as pl


ALLOWED_ACTIONS = (
    "BLOCK",
    "WATCH_ONLY",
    "TARGET_REFERENCE",
    "ALLOW_RESEARCH_CANDIDATE",
    "INSUFFICIENT_DATA",
)
FINAL_RECOMMENDATIONS = (
    "QUIKSTRIKE_CONTEXT_READY",
    "WATCH_4550_DECISION_WALL",
    "NEED_STRUCTURED_QUIKSTRIKE_CSV",
    "USE_AS_CME_CONTEXT_ONLY",
    "NOT_READY_FOR_MONEY",
)
RESEARCH_WARNING = (
    "Research-only QuikStrike intraday volume context. Intraday volume walls "
    "are target/reference or decision zones only; price reaction confirmation "
    "is required."
)
FORBIDDEN_PATTERNS = (
    r"\bbuy\b",
    r"\bsell\b",
    r"profitable",
    r"profitability",
    r"guaranteed edge",
    r"predicts price",
    r"safe to trade",
    r"live[- ]ready",
    r"paper[- ]ready",
)


@dataclass(frozen=True)
class QuikStrikeIntradayVolumeSnapshotResult:
    """Generated QuikStrike intraday volume artifacts."""

    manual_template: pl.DataFrame
    snapshot: pl.DataFrame
    scenarios: pl.DataFrame
    latest_state: pl.DataFrame
    example_scenarios: pl.DataFrame
    final_recommendation: str
    paths: dict[str, Path]


def run_quikstrike_intraday_volume_snapshot(
    *,
    output_dir: str | Path = "outputs",
    data_dir: str | Path = "data/quikstrike_intraday_volume",
    write_outputs: bool = True,
) -> QuikStrikeIntradayVolumeSnapshotResult:
    """Build manual template, parsed snapshot, scenarios, and latest state."""

    output_root = Path(output_dir)
    output_root.mkdir(parents=True, exist_ok=True)
    paths = _output_paths(output_root)
    manual_template = build_manual_snapshot_template()
    manual_rows = _load_snapshot_input(output_root=output_root, data_dir=Path(data_dir))
    snapshot = build_intraday_volume_snapshot(manual_rows)
    scenarios = build_wall_scenarios(snapshot)
    latest_state = build_latest_indicator_state_with_quikstrike(
        snapshot=snapshot,
        output_root=output_root,
    )
    example_scenarios = build_example_4550_scenarios()
    final = choose_final_recommendation(snapshot=snapshot, latest_state=latest_state)
    result = QuikStrikeIntradayVolumeSnapshotResult(
        manual_template=manual_template,
        snapshot=snapshot,
        scenarios=scenarios,
        latest_state=latest_state,
        example_scenarios=example_scenarios,
        final_recommendation=final,
        paths=paths,
    )
    if write_outputs:
        write_quikstrike_intraday_volume_outputs(result)
    return result


def build_manual_snapshot_template() -> pl.DataFrame:
    """Return the manual CSV schema with the provided 4550 example rows."""

    return _frame(_example_manual_rows(), _manual_schema())


def build_intraday_volume_snapshot(manual_rows: pl.DataFrame) -> pl.DataFrame:
    """Normalize manual/table rows into structured intraday volume walls."""

    normalized = _normalize_manual_rows(manual_rows)
    if normalized.is_empty():
        return _frame([], _snapshot_schema())
    max_total = _max_float(normalized, "total_volume") or 0.0
    active_threshold = max(25.0, max_total * 0.25)
    low_threshold = max(1.0, max_total * 0.08)
    rows: list[dict[str, Any]] = []
    for raw in normalized.sort("strike").to_dicts():
        strike = _float(raw.get("strike"))
        future_price = _float(raw.get("future_price"))
        call_volume = _float(raw.get("call_volume")) or 0.0
        put_volume = _float(raw.get("put_volume")) or 0.0
        total_volume = _float(raw.get("total_volume")) or call_volume + put_volume
        distance = None if strike is None or future_price is None else strike - future_price
        within_window = distance is not None and abs(distance) <= 100.0
        wall_type = _classify_wall_type(
            strike=strike,
            future_price=future_price,
            call_volume=call_volume,
            put_volume=put_volume,
            total_volume=total_volume,
            active_threshold=active_threshold,
            low_threshold=low_threshold,
        )
        is_active = (
            within_window
            and wall_type != "LOW_VOLUME_GAP"
            and total_volume >= active_threshold
        )
        ratio = call_volume / put_volume if put_volume > 0 else None
        rows.append(
            {
                "snapshot_timestamp": raw.get("snapshot_timestamp"),
                "product": raw.get("product"),
                "expiration": raw.get("expiration"),
                "dte": raw.get("dte"),
                "future_price": future_price,
                "strike": strike,
                "call_volume": call_volume,
                "put_volume": put_volume,
                "total_volume": total_volume,
                "call_put_volume_ratio": ratio,
                "distance_from_future": distance,
                "within_100_dollar_window": within_window,
                "is_active_wall": is_active,
                "wall_type": wall_type,
                "freshness": _freshness(total_volume, active_threshold),
                "volatility": raw.get("volatility"),
                "volatility_change": raw.get("volatility_change"),
                "future_change": raw.get("future_change"),
                "range_label": raw.get("range_label"),
                "notes": raw.get("notes"),
            }
        )
    return _frame([_safe_row(row) for row in rows], _snapshot_schema())


def build_wall_scenarios(snapshot: pl.DataFrame) -> pl.DataFrame:
    """Create conservative magnet/rejection/acceptance scenarios for walls."""

    if snapshot.is_empty():
        return _frame([_insufficient_scenario()], _scenario_schema())
    future_price = _latest_future_price(snapshot)
    important = _important_wall_rows(snapshot)
    if not important:
        return _frame([_insufficient_scenario()], _scenario_schema())
    rows: list[dict[str, Any]] = []
    for wall in important:
        wall_type = _text(wall.get("wall_type"))
        level = _float(wall.get("strike"))
        relation = _price_relation(future_price, level)
        if wall_type == "LOW_VOLUME_GAP":
            rows.append(
                _scenario_row(
                    wall_level=level,
                    wall_type=wall_type,
                    relation=relation,
                    scenario="LOW_OI_GAP_CONTINUATION_WATCH",
                    required_confirmation="Prior wall acceptance plus closed-candle hold.",
                    target_reference=_nearest_next_wall(snapshot, level, future_price),
                    invalidation_reference=_nearest_prior_wall(snapshot, level, future_price),
                    action_label="WATCH_ONLY",
                    summary=(
                        f"Low-volume gap near {_format_level(level)} is only a continuation "
                        "watch after acceptance; it is not standalone evidence."
                    ),
                )
            )
            continue
        if wall_type == "ATM_ACTIVITY_CLUSTER":
            rows.append(
                _scenario_row(
                    wall_level=level,
                    wall_type=wall_type,
                    relation=relation,
                    scenario="ATM_NO_TRADE_CLUSTER",
                    required_confirmation="Wait for price to leave the cluster and retest.",
                    target_reference=_nearest_next_wall(snapshot, level, future_price),
                    invalidation_reference=_nearest_prior_wall(snapshot, level, future_price),
                    action_label="BLOCK",
                    summary=(
                        f"Activity cluster near {_format_level(level)} is a middle/decision "
                        "area; directional interpretation is blocked without reaction."
                    ),
                )
            )
            continue
        rows.extend(
            [
                _scenario_row(
                    wall_level=level,
                    wall_type=wall_type,
                    relation=relation,
                    scenario="WALL_MAGNET_TARGET",
                    required_confirmation="None for target/reference use; reaction required for candidate use.",
                    target_reference=level,
                    invalidation_reference=_nearest_prior_wall(snapshot, level, future_price),
                    action_label="TARGET_REFERENCE",
                    summary=(
                        f"Wall near {_format_level(level)} can be target/reference context "
                        "while price is on the approach side."
                    ),
                ),
                _scenario_row(
                    wall_level=level,
                    wall_type=wall_type,
                    relation=relation,
                    scenario="WALL_REJECTION_WATCH",
                    required_confirmation="Touch or test followed by close back away from the wall.",
                    target_reference=_nearest_prior_wall(snapshot, level, future_price),
                    invalidation_reference=level,
                    action_label="WATCH_ONLY",
                    summary=(
                        f"Wall near {_format_level(level)} becomes rejection watch only "
                        "after closed-candle rejection behavior."
                    ),
                ),
                _scenario_row(
                    wall_level=level,
                    wall_type=wall_type,
                    relation=relation,
                    scenario="WALL_ACCEPTANCE_WATCH",
                    required_confirmation="Close and hold beyond the wall.",
                    target_reference=_nearest_next_wall(snapshot, level, future_price),
                    invalidation_reference=level,
                    action_label="WATCH_ONLY",
                    summary=(
                        f"Wall near {_format_level(level)} becomes acceptance watch only "
                        "after a close and hold beyond it."
                    ),
                ),
            ]
        )
    return _frame([_safe_row(row) for row in rows], _scenario_schema())


def build_latest_indicator_state_with_quikstrike(
    *,
    snapshot: pl.DataFrame,
    output_root: Path,
) -> pl.DataFrame:
    """Combine latest indicator state with intraday volume wall context."""

    indicator = _read_optional(output_root / "xau_indicator_latest_state.csv")
    latest_price = _latest_indicator_price(indicator)
    if latest_price is None:
        latest_price = _latest_future_price(snapshot)
    if latest_price is None or snapshot.is_empty():
        row = {
            "latest_price": latest_price,
            "nearest_intraday_volume_wall_above": None,
            "nearest_intraday_volume_wall_below": None,
            "active_intraday_wall": "",
            "quikstrike_context_state": "INSUFFICIENT_DATA",
            "cme_intraday_volume_action": "INSUFFICIENT_DATA",
            "combined_indicator_action": "INSUFFICIENT_DATA",
            "plain_english_summary": "Structured QuikStrike intraday volume rows are unavailable.",
        }
        return _frame([_safe_row(row)], _latest_quikstrike_schema())
    active = _active_wall_rows(snapshot)
    above = _nearest_wall(active, latest_price, side="above")
    below = _nearest_wall(active, latest_price, side="below")
    nearest = _nearest_wall(active, latest_price, side="nearest")
    context_state = _quikstrike_context_state(nearest, latest_price)
    indicator_action = _latest_indicator_action(indicator)
    cme_action = "WATCH_ONLY" if nearest else "INSUFFICIENT_DATA"
    combined = _combine_actions(indicator_action, cme_action)
    row = {
        "latest_price": latest_price,
        "nearest_intraday_volume_wall_above": _float(above.get("strike")) if above else None,
        "nearest_intraday_volume_wall_below": _float(below.get("strike")) if below else None,
        "active_intraday_wall": _wall_label(nearest),
        "quikstrike_context_state": context_state,
        "cme_intraday_volume_action": cme_action,
        "combined_indicator_action": combined,
        "plain_english_summary": _latest_summary(
            latest_price=latest_price,
            above=above,
            below=below,
            nearest=nearest,
            combined=combined,
        ),
    }
    return _frame([_safe_row(row)], _latest_quikstrike_schema())


def build_example_4550_scenarios() -> pl.DataFrame:
    """Return the requested 4550 example scenario replay."""

    rows = [
        {
            "scenario_id": "A_ACCEPTS_ABOVE_4550",
            "starting_context": "Future reference around 4532.60; 4550 active call-volume wall.",
            "price_path": "Price closes and holds above 4550.",
            "wall_level": 4550.0,
            "scenario": "WALL_ACCEPTANCE_WATCH",
            "required_confirmation": "Closed acceptance above 4550 plus hold.",
            "target_reference": 4600.0,
            "invalidation_reference": 4550.0,
            "action_label": "WATCH_ONLY",
            "plain_english_summary": (
                "4550 acceptance makes 4600 the next upper target/reference context; "
                "the wall still is not an automatic entry."
            ),
            "final_recommendation": "WATCH_4550_DECISION_WALL",
        },
        {
            "scenario_id": "B_REJECTS_4550",
            "starting_context": "Future reference around 4532.60; 4550 active call-volume wall.",
            "price_path": "Price tests 4550 and closes back below it.",
            "wall_level": 4550.0,
            "scenario": "WALL_REJECTION_WATCH",
            "required_confirmation": "Test of 4550 plus close back below the wall.",
            "target_reference": 4525.0,
            "invalidation_reference": 4550.0,
            "action_label": "WATCH_ONLY",
            "plain_english_summary": (
                "4550 rejection shifts attention to lower references at 4525 and 4500 "
                "for context only."
            ),
            "final_recommendation": "WATCH_4550_DECISION_WALL",
        },
        {
            "scenario_id": "C_STAYS_4525_4550",
            "starting_context": "Price remains between lower reference 4525 and wall 4550.",
            "price_path": "Price oscillates inside 4525-4550 without acceptance or rejection.",
            "wall_level": 4550.0,
            "scenario": "ATM_NO_TRADE_CLUSTER",
            "required_confirmation": "Break, retest, and closed-candle reaction required.",
            "target_reference": 4550.0,
            "invalidation_reference": 4525.0,
            "action_label": "BLOCK",
            "plain_english_summary": (
                "The 4525-4550 band is a decision area; no confirmation means blocked "
                "or watch-only context."
            ),
            "final_recommendation": "WATCH_4550_DECISION_WALL",
        },
        {
            "scenario_id": "D_BREAKS_BELOW_4525",
            "starting_context": "4525 is a lower intraday reference below 4550.",
            "price_path": "Price closes below 4525 and holds.",
            "wall_level": 4525.0,
            "scenario": "WALL_ACCEPTANCE_WATCH",
            "required_confirmation": "Closed break below 4525 plus hold.",
            "target_reference": 4500.0,
            "invalidation_reference": 4525.0,
            "action_label": "WATCH_ONLY",
            "plain_english_summary": (
                "A confirmed move below 4525 makes 4500 the next lower reference; "
                "confirmation remains required."
            ),
            "final_recommendation": "WATCH_4550_DECISION_WALL",
        },
        {
            "scenario_id": "E_SQUEEZES_TOWARD_4600",
            "starting_context": "4550 accepted; additional call activity exists near 4600.",
            "price_path": "Price holds above 4550 and moves through the low-volume pocket.",
            "wall_level": 4600.0,
            "scenario": "LOW_OI_GAP_CONTINUATION_WATCH",
            "required_confirmation": "4550 acceptance plus continuation hold.",
            "target_reference": 4600.0,
            "invalidation_reference": 4550.0,
            "action_label": "WATCH_ONLY",
            "plain_english_summary": (
                "A push toward 4600 is continuation watch only after 4550 acceptance."
            ),
            "final_recommendation": "WATCH_4550_DECISION_WALL",
        },
    ]
    return _frame([_safe_row(row) for row in rows], _example_schema())


def choose_final_recommendation(
    *,
    snapshot: pl.DataFrame,
    latest_state: pl.DataFrame,
) -> str:
    """Choose a conservative final recommendation for the layer."""

    if snapshot.is_empty() or latest_state.is_empty():
        return "NEED_STRUCTURED_QUIKSTRIKE_CSV"
    active_levels = {
        round(float(row["strike"]), 2)
        for row in _active_wall_rows(snapshot)
        if _float(row.get("strike")) is not None
    }
    if 4550.0 in active_levels:
        return "WATCH_4550_DECISION_WALL"
    action = _text(latest_state.row(0, named=True).get("combined_indicator_action"))
    if action == "INSUFFICIENT_DATA":
        return "NEED_STRUCTURED_QUIKSTRIKE_CSV"
    return "USE_AS_CME_CONTEXT_ONLY"


def write_quikstrike_intraday_volume_outputs(
    result: QuikStrikeIntradayVolumeSnapshotResult,
) -> None:
    """Write all QuikStrike CSV and Markdown artifacts."""

    result.manual_template.write_csv(result.paths["manual_template_csv"])
    result.paths["manual_guide_md"].write_text(
        _safe_report_text(_manual_guide_markdown()),
        encoding="utf-8",
    )
    result.snapshot.write_csv(result.paths["snapshot_csv"])
    result.paths["snapshot_md"].write_text(
        _safe_report_text(
            _artifact_markdown("QuikStrike Intraday Volume Snapshot", result.snapshot)
        ),
        encoding="utf-8",
    )
    result.scenarios.write_csv(result.paths["scenarios_csv"])
    result.paths["scenarios_md"].write_text(
        _safe_report_text(
            _artifact_markdown("QuikStrike Wall Scenarios", result.scenarios)
        ),
        encoding="utf-8",
    )
    result.latest_state.write_csv(result.paths["latest_state_csv"])
    result.paths["latest_state_md"].write_text(
        _safe_report_text(
            _artifact_markdown(
                "XAU Indicator Latest State With QuikStrike",
                result.latest_state,
            )
        ),
        encoding="utf-8",
    )
    result.example_scenarios.write_csv(result.paths["example_csv"])
    result.paths["example_md"].write_text(
        _safe_report_text(_example_markdown(result.example_scenarios)),
        encoding="utf-8",
    )


def quikstrike_intraday_volume_report_lines(
    result: QuikStrikeIntradayVolumeSnapshotResult | None,
) -> list[str]:
    """Return report lines for research_report.md."""

    if result is None:
        return [
            "## QuikStrike Intraday Volume Snapshot",
            "",
            "QuikStrike intraday volume snapshot layer was not run.",
        ]
    return [
        "## QuikStrike Intraday Volume Snapshot",
        "",
        RESEARCH_WARNING,
        "",
        f"- Final recommendation: `{result.final_recommendation}`",
        f"- Manual template: `{_display_path(result.paths['manual_template_csv'])}`",
        "",
        _frame_markdown(result.snapshot),
        "",
        "## Intraday Volume Wall Scenarios",
        "",
        _frame_markdown(result.scenarios),
        "",
        "## Latest Indicator State With QuikStrike",
        "",
        _frame_markdown(result.latest_state),
        "",
        "## 4550 Example Scenario",
        "",
        _frame_markdown(result.example_scenarios),
        "",
        "- Links: `outputs/quikstrike_intraday_volume_snapshot.csv`, "
        "`outputs/quikstrike_wall_scenarios.csv`, "
        "`outputs/xau_indicator_latest_state_with_quikstrike.csv`, "
        "`outputs/quikstrike_example_4550_scenario.md`.",
    ]


def report_text_is_safe(text: str) -> bool:
    """Return true when text avoids restricted phrases and private paths."""

    safe = _safe_report_text(text)
    return safe == text and not any(
        re.search(pattern, text, flags=re.IGNORECASE)
        for pattern in FORBIDDEN_PATTERNS
    )


def _output_paths(output_root: Path) -> dict[str, Path]:
    return {
        "manual_template_csv": output_root / "quikstrike_intraday_volume_manual_template.csv",
        "manual_guide_md": output_root / "quikstrike_intraday_volume_manual_guide.md",
        "snapshot_csv": output_root / "quikstrike_intraday_volume_snapshot.csv",
        "snapshot_md": output_root / "quikstrike_intraday_volume_snapshot.md",
        "scenarios_csv": output_root / "quikstrike_wall_scenarios.csv",
        "scenarios_md": output_root / "quikstrike_wall_scenarios.md",
        "latest_state_csv": output_root / "xau_indicator_latest_state_with_quikstrike.csv",
        "latest_state_md": output_root / "xau_indicator_latest_state_with_quikstrike.md",
        "example_csv": output_root / "quikstrike_example_4550_scenario.csv",
        "example_md": output_root / "quikstrike_example_4550_scenario.md",
    }


def _load_snapshot_input(*, output_root: Path, data_dir: Path) -> pl.DataFrame:
    manual = output_root / "quikstrike_intraday_volume_manual.csv"
    if manual.exists():
        frame = _read_optional(manual)
        if not frame.is_empty():
            return frame
    if data_dir.exists():
        frames = [_read_optional(path) for path in sorted(data_dir.glob("*.csv"))]
        frames = [frame for frame in frames if not frame.is_empty()]
        if frames:
            return pl.concat(frames, how="diagonal_relaxed")
    template = output_root / "quikstrike_intraday_volume_manual_template.csv"
    if template.exists():
        frame = _read_optional(template)
        if not frame.is_empty():
            return frame
    return build_manual_snapshot_template()


def _normalize_manual_rows(frame: pl.DataFrame) -> pl.DataFrame:
    if frame.is_empty():
        return _frame([], _manual_schema())
    out = frame
    for column, dtype in _manual_schema().items():
        if column not in out.columns:
            out = out.with_columns(pl.lit(None).cast(dtype).alias(column))
        else:
            out = out.with_columns(pl.col(column).cast(dtype, strict=False).alias(column))
    out = out.with_columns(
        [
            (
                pl.when(pl.col("total_volume").is_null())
                .then(pl.col("call_volume").fill_null(0.0) + pl.col("put_volume").fill_null(0.0))
                .otherwise(pl.col("total_volume"))
                .alias("total_volume")
            )
        ]
    )
    return out.select(list(_manual_schema()))


def _classify_wall_type(
    *,
    strike: float | None,
    future_price: float | None,
    call_volume: float,
    put_volume: float,
    total_volume: float,
    active_threshold: float,
    low_threshold: float,
) -> str:
    if strike is None or future_price is None or total_volume <= low_threshold:
        return "LOW_VOLUME_GAP"
    distance = abs(strike - future_price)
    if (
        distance <= 12.5
        and total_volume >= active_threshold
        and 0.67 <= _safe_ratio(call_volume, put_volume) <= 1.5
    ):
        return "ATM_ACTIVITY_CLUSTER"
    if call_volume >= max(active_threshold, put_volume * 1.2):
        return "CALL_VOLUME_WALL"
    if put_volume >= max(active_threshold, call_volume * 1.2):
        return "PUT_VOLUME_WALL"
    if total_volume >= active_threshold:
        return "TOTAL_VOLUME_WALL"
    return "LOW_VOLUME_GAP"


def _safe_ratio(call_volume: float, put_volume: float) -> float:
    if put_volume <= 0:
        return math.inf if call_volume > 0 else 1.0
    return call_volume / put_volume


def _freshness(total_volume: float, active_threshold: float) -> str:
    if total_volume >= active_threshold:
        return "INTRADAY_VOLUME_ACTIVE"
    if total_volume > 0:
        return "LOW_ACTIVITY"
    return "UNKNOWN"


def _important_wall_rows(snapshot: pl.DataFrame) -> list[dict[str, Any]]:
    rows = snapshot.to_dicts()
    active = [
        row
        for row in rows
        if bool(row.get("within_100_dollar_window"))
        and (
            bool(row.get("is_active_wall"))
            or _text(row.get("wall_type")) == "LOW_VOLUME_GAP"
        )
    ]
    return sorted(
        active,
        key=lambda row: (
            1 if _text(row.get("wall_type")) == "LOW_VOLUME_GAP" else 0,
            _float(row.get("strike")) or 0.0,
        ),
    )


def _active_wall_rows(snapshot: pl.DataFrame) -> list[dict[str, Any]]:
    if snapshot.is_empty():
        return []
    return [
        row
        for row in snapshot.to_dicts()
        if bool(row.get("is_active_wall"))
        and _text(row.get("wall_type")) != "LOW_VOLUME_GAP"
    ]


def _scenario_row(
    *,
    wall_level: float | None,
    wall_type: str,
    relation: str,
    scenario: str,
    required_confirmation: str,
    target_reference: float | None,
    invalidation_reference: float | None,
    action_label: str,
    summary: str,
) -> dict[str, Any]:
    return {
        "wall_level": wall_level,
        "wall_type": wall_type,
        "current_price_relation": relation,
        "scenario": scenario,
        "required_confirmation": required_confirmation,
        "target_reference": target_reference,
        "invalidation_reference": invalidation_reference,
        "action_label": _allowed_action(action_label),
        "plain_english_summary": summary,
    }


def _insufficient_scenario() -> dict[str, Any]:
    return _scenario_row(
        wall_level=None,
        wall_type="INSUFFICIENT_DATA",
        relation="AT_WALL",
        scenario="ATM_NO_TRADE_CLUSTER",
        required_confirmation="Structured QuikStrike CSV/manual rows required.",
        target_reference=None,
        invalidation_reference=None,
        action_label="INSUFFICIENT_DATA",
        summary="No structured intraday volume wall data is available.",
    )


def _nearest_next_wall(
    snapshot: pl.DataFrame,
    level: float | None,
    future_price: float | None,
) -> float | None:
    if level is None:
        return None
    direction_up = future_price is None or level >= future_price
    candidates = [
        _float(row.get("strike"))
        for row in _active_wall_rows(snapshot)
        if _float(row.get("strike")) is not None
    ]
    if direction_up:
        higher = [value for value in candidates if value is not None and value > level]
        return min(higher) if higher else None
    lower = [value for value in candidates if value is not None and value < level]
    return max(lower) if lower else None


def _nearest_prior_wall(
    snapshot: pl.DataFrame,
    level: float | None,
    future_price: float | None,
) -> float | None:
    if level is None:
        return None
    direction_up = future_price is None or level >= future_price
    candidates = [
        _float(row.get("strike"))
        for row in _active_wall_rows(snapshot)
        if _float(row.get("strike")) is not None
    ]
    if direction_up:
        lower = [value for value in candidates if value is not None and value < level]
        return max(lower) if lower else None
    higher = [value for value in candidates if value is not None and value > level]
    return min(higher) if higher else None


def _price_relation(price: float | None, level: float | None) -> str:
    if price is None or level is None:
        return "AT_WALL"
    if abs(price - level) <= 2.0:
        return "AT_WALL"
    return "BELOW_WALL" if price < level else "ABOVE_WALL"


def _latest_indicator_price(indicator: pl.DataFrame) -> float | None:
    if indicator.is_empty() or "latest_price" not in indicator.columns:
        return None
    rows = indicator.to_dicts()
    return _float(rows[-1].get("latest_price")) if rows else None


def _latest_indicator_action(indicator: pl.DataFrame) -> str:
    if indicator.is_empty() or "final_action" not in indicator.columns:
        return "WATCH_ONLY"
    rows = indicator.to_dicts()
    action = _text(rows[-1].get("final_action")) if rows else ""
    return _allowed_action(action) if action else "WATCH_ONLY"


def _latest_future_price(snapshot: pl.DataFrame) -> float | None:
    if snapshot.is_empty() or "future_price" not in snapshot.columns:
        return None
    values = [_float(value) for value in snapshot.get_column("future_price").to_list()]
    clean = [value for value in values if value is not None]
    return clean[-1] if clean else None


def _nearest_wall(
    rows: list[dict[str, Any]],
    latest_price: float,
    *,
    side: str,
) -> dict[str, Any] | None:
    candidates = []
    for row in rows:
        strike = _float(row.get("strike"))
        if strike is None:
            continue
        if side == "above" and strike <= latest_price:
            continue
        if side == "below" and strike >= latest_price:
            continue
        candidates.append(row)
    if side == "nearest":
        candidates = [row for row in rows if _float(row.get("strike")) is not None]
    if not candidates:
        return None
    return min(candidates, key=lambda row: abs((_float(row.get("strike")) or 0.0) - latest_price))


def _quikstrike_context_state(nearest: dict[str, Any] | None, latest_price: float) -> str:
    if not nearest:
        return "INSUFFICIENT_DATA"
    strike = _float(nearest.get("strike"))
    if strike is not None and abs(strike - 4550.0) <= 0.01:
        return "WATCH_4550_DECISION_WALL"
    relation = _price_relation(latest_price, strike)
    return f"{relation}_{_text(nearest.get('wall_type'))}_CONTEXT"


def _combine_actions(indicator_action: str, cme_action: str) -> str:
    indicator = _allowed_action(indicator_action)
    cme = _allowed_action(cme_action)
    if "INSUFFICIENT_DATA" in {indicator, cme}:
        return "INSUFFICIENT_DATA" if indicator == "INSUFFICIENT_DATA" else indicator
    if indicator == "BLOCK":
        return "BLOCK"
    if cme == "WATCH_ONLY" and indicator == "ALLOW_RESEARCH_CANDIDATE":
        return "WATCH_ONLY"
    return indicator if indicator in ALLOWED_ACTIONS else "WATCH_ONLY"


def _wall_label(row: dict[str, Any] | None) -> str:
    if not row:
        return ""
    return f"{_text(row.get('wall_type'))}_{_format_level(row.get('strike'))}"


def _latest_summary(
    *,
    latest_price: float,
    above: dict[str, Any] | None,
    below: dict[str, Any] | None,
    nearest: dict[str, Any] | None,
    combined: str,
) -> str:
    above_text = _format_level(above.get("strike")) if above else "n/a"
    below_text = _format_level(below.get("strike")) if below else "n/a"
    nearest_text = _wall_label(nearest) or "n/a"
    return (
        f"Latest price {_format_level(latest_price)}; nearest intraday volume wall "
        f"above {above_text}; nearest wall below {below_text}; active context "
        f"{nearest_text}; combined action {combined}."
    )


def _manual_guide_markdown() -> str:
    return "\n".join(
        [
            "# QuikStrike Intraday Volume Manual Guide",
            "",
            RESEARCH_WARNING,
            "",
            "Use structured CSV/table data when available. If only a screenshot exists, "
            "manually transcribe the visible table values into the template and keep "
            "notes about uncertainty.",
            "",
            "Required columns:",
            "",
            "- snapshot_timestamp",
            "- product",
            "- expiration",
            "- dte",
            "- future_price",
            "- strike",
            "- put_volume",
            "- call_volume",
            "- total_volume",
            "- volatility",
            "- volatility_change",
            "- future_change",
            "- range_label",
            "- notes",
            "",
            "Interpretation guardrails:",
            "",
            "- Call-side volume is a decision wall, not a directional claim.",
            "- Put-side volume is a decision wall, not a directional claim.",
            "- CME wall proximity never creates an automatic candidate.",
            "- Closed-candle rejection or acceptance is required for scenario review.",
        ]
    )


def _example_markdown(example: pl.DataFrame) -> str:
    return "\n\n".join(
        [
            "# QuikStrike 4550 Example Scenario",
            RESEARCH_WARNING,
            (
                "The provided example maps 4550 as an active decision wall, 4600 as "
                "the next upper reference if 4550 is accepted, and 4525/4500 as "
                "lower references if 4550 rejects or price breaks lower."
            ),
            _frame_markdown(example),
        ]
    )


def _artifact_markdown(title: str, frame: pl.DataFrame) -> str:
    return "\n\n".join([f"# {title}", RESEARCH_WARNING, _frame_markdown(frame)])


def _frame_markdown(frame: pl.DataFrame, *, limit: int = 40) -> str:
    if frame.is_empty():
        return "_No rows._"
    sample = frame.head(limit)
    lines = [
        "| " + " | ".join(sample.columns) + " |",
        "| " + " | ".join("---" for _ in sample.columns) + " |",
    ]
    for row in sample.to_dicts():
        lines.append(
            "| "
            + " | ".join(_markdown_cell(row.get(column, "")) for column in sample.columns)
            + " |"
        )
    if frame.height > limit:
        lines.append(f"\n_Showing {limit} of {frame.height} rows._")
    return "\n".join(lines)


def _markdown_cell(value: Any) -> str:
    return _safe_text(value).replace("|", "\\|").replace("\n", " ")[:700]


def _safe_report_text(text: str) -> str:
    safe = _safe_text(text)
    for pattern in FORBIDDEN_PATTERNS:
        safe = re.sub(pattern, _replacement_for(pattern), safe, flags=re.IGNORECASE)
    return safe


def _replacement_for(pattern: str) -> str:
    if "buy" in pattern or "sell" in pattern:
        return "direction"
    if "profit" in pattern:
        return "money-result"
    return "blocked phrase"


def _safe_row(row: dict[str, Any]) -> dict[str, Any]:
    return {key: _safe_text(value) if isinstance(value, str) else value for key, value in row.items()}


def _safe_text(value: Any) -> str:
    text = str(value or "")
    text = _redact_paths(text)
    text = re.sub(r"\bbuy\b", "direction", text, flags=re.IGNORECASE)
    text = re.sub(r"\bsell\b", "direction", text, flags=re.IGNORECASE)
    text = re.sub(r"profitable|profitability", "money-result", text, flags=re.IGNORECASE)
    text = re.sub(r"safe to trade|live[- ]ready|paper[- ]ready", "blocked phrase", text, flags=re.IGNORECASE)
    return text.strip()


def _redact_paths(text: str) -> str:
    safe = re.sub(r"[A-Za-z]:\\Users\\[^\s|)<>\"']+", "<REDACTED_PATH>", text)
    safe = re.sub(r"[A-Za-z]:\\[^\s|)<>\"']+", "<REDACTED_PATH>", safe)
    return re.sub(r"/(?:Users|home|mnt|var|tmp)/[^\s|)<>\"']+", "<REDACTED_PATH>", safe)


def _display_path(path: Path) -> str:
    parts = path.parts
    if "outputs" in parts:
        index = parts.index("outputs")
        return "/".join(parts[index:])
    return _safe_text(path.name)


def _read_optional(path: Path) -> pl.DataFrame:
    if not path.exists():
        return pl.DataFrame()
    try:
        if path.suffix.lower() == ".parquet":
            return pl.read_parquet(path)
        return pl.read_csv(path, infer_schema_length=None)
    except Exception:
        return pl.DataFrame()


def _frame(rows: list[dict[str, Any]], schema: dict[str, Any]) -> pl.DataFrame:
    if not rows:
        return pl.DataFrame(schema=schema)
    frame = pl.DataFrame(rows, infer_schema_length=None)
    for column, dtype in schema.items():
        if column not in frame.columns:
            frame = frame.with_columns(pl.lit(None).cast(dtype).alias(column))
        else:
            frame = frame.with_columns(pl.col(column).cast(dtype, strict=False).alias(column))
    return frame.select(list(schema))


def _max_float(frame: pl.DataFrame, column: str) -> float | None:
    if frame.is_empty() or column not in frame.columns:
        return None
    values = [_float(value) for value in frame.get_column(column).to_list()]
    clean = [value for value in values if value is not None]
    return max(clean) if clean else None


def _float(value: Any) -> float | None:
    try:
        if value in (None, ""):
            return None
        number = float(value)
        if math.isnan(number) or math.isinf(number):
            return None
        return number
    except (TypeError, ValueError):
        return None


def _format_level(value: Any) -> str:
    number = _float(value)
    return "n/a" if number is None else f"{number:.2f}"


def _allowed_action(value: Any) -> str:
    action = _text(value)
    return action if action in ALLOWED_ACTIONS else "INSUFFICIENT_DATA"


def _text(value: Any) -> str:
    return str(value or "").strip()


def _example_manual_rows() -> list[dict[str, Any]]:
    timestamp = datetime(2026, 5, 27, 8, 0, tzinfo=UTC).isoformat()
    common = {
        "snapshot_timestamp": timestamp,
        "product": "Gold",
        "expiration": "G4WK6",
        "dte": 0.53,
        "future_price": 4532.6,
        "volatility": 24.56,
        "volatility_change": 0.11,
        "future_change": -2.4,
        "range_label": "provided_example",
    }
    rows = [
        {
            **common,
            "strike": 4500.0,
            "put_volume": 78.0,
            "call_volume": 5.0,
            "total_volume": 83.0,
            "notes": "Lower put-side activity reference.",
        },
        {
            **common,
            "strike": 4525.0,
            "put_volume": 51.0,
            "call_volume": 35.0,
            "total_volume": 86.0,
            "notes": "Lower reference below 4550.",
        },
        {
            **common,
            "strike": 4550.0,
            "put_volume": 20.0,
            "call_volume": 155.0,
            "total_volume": 175.0,
            "notes": "Major call-volume decision wall.",
        },
        {
            **common,
            "strike": 4575.0,
            "put_volume": 0.0,
            "call_volume": 0.0,
            "total_volume": 0.0,
            "notes": "Low-volume pocket between 4550 and 4600.",
        },
        {
            **common,
            "strike": 4600.0,
            "put_volume": 0.0,
            "call_volume": 50.0,
            "total_volume": 50.0,
            "notes": "Additional upper call activity.",
        },
        {
            **common,
            "strike": 4650.0,
            "put_volume": 0.0,
            "call_volume": 28.0,
            "total_volume": 28.0,
            "notes": "Farther upper call activity.",
        },
    ]
    return rows


def _manual_schema() -> dict[str, Any]:
    return {
        "snapshot_timestamp": pl.Utf8,
        "product": pl.Utf8,
        "expiration": pl.Utf8,
        "dte": pl.Float64,
        "future_price": pl.Float64,
        "strike": pl.Float64,
        "put_volume": pl.Float64,
        "call_volume": pl.Float64,
        "total_volume": pl.Float64,
        "volatility": pl.Float64,
        "volatility_change": pl.Float64,
        "future_change": pl.Float64,
        "range_label": pl.Utf8,
        "notes": pl.Utf8,
    }


def _snapshot_schema() -> dict[str, Any]:
    return {
        "snapshot_timestamp": pl.Utf8,
        "product": pl.Utf8,
        "expiration": pl.Utf8,
        "dte": pl.Float64,
        "future_price": pl.Float64,
        "strike": pl.Float64,
        "call_volume": pl.Float64,
        "put_volume": pl.Float64,
        "total_volume": pl.Float64,
        "call_put_volume_ratio": pl.Float64,
        "distance_from_future": pl.Float64,
        "within_100_dollar_window": pl.Boolean,
        "is_active_wall": pl.Boolean,
        "wall_type": pl.Utf8,
        "freshness": pl.Utf8,
        "volatility": pl.Float64,
        "volatility_change": pl.Float64,
        "future_change": pl.Float64,
        "range_label": pl.Utf8,
        "notes": pl.Utf8,
    }


def _scenario_schema() -> dict[str, Any]:
    return {
        "wall_level": pl.Float64,
        "wall_type": pl.Utf8,
        "current_price_relation": pl.Utf8,
        "scenario": pl.Utf8,
        "required_confirmation": pl.Utf8,
        "target_reference": pl.Float64,
        "invalidation_reference": pl.Float64,
        "action_label": pl.Utf8,
        "plain_english_summary": pl.Utf8,
    }


def _latest_quikstrike_schema() -> dict[str, Any]:
    return {
        "latest_price": pl.Float64,
        "nearest_intraday_volume_wall_above": pl.Float64,
        "nearest_intraday_volume_wall_below": pl.Float64,
        "active_intraday_wall": pl.Utf8,
        "quikstrike_context_state": pl.Utf8,
        "cme_intraday_volume_action": pl.Utf8,
        "combined_indicator_action": pl.Utf8,
        "plain_english_summary": pl.Utf8,
    }


def _example_schema() -> dict[str, Any]:
    return {
        "scenario_id": pl.Utf8,
        "starting_context": pl.Utf8,
        "price_path": pl.Utf8,
        "wall_level": pl.Float64,
        "scenario": pl.Utf8,
        "required_confirmation": pl.Utf8,
        "target_reference": pl.Float64,
        "invalidation_reference": pl.Float64,
        "action_label": pl.Utf8,
        "plain_english_summary": pl.Utf8,
        "final_recommendation": pl.Utf8,
    }


def main() -> None:
    """CLI entry point."""

    result = run_quikstrike_intraday_volume_snapshot()
    print(f"final_recommendation: {result.final_recommendation}")
    print(f"snapshot_rows: {result.snapshot.height}")


if __name__ == "__main__":
    main()
