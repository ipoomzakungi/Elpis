"""Pipeline orchestration, output writing, charts, and Markdown report creation."""

from __future__ import annotations

import argparse
from pathlib import Path
from typing import Any

import polars as pl

from research_xau_vol_oi.backtest import backtest_all_scenarios, walk_forward_validate
from research_xau_vol_oi.basis_mapper import add_basis_columns
from research_xau_vol_oi.config import ResearchConfig
from research_xau_vol_oi.data_loader import (
    DataLoadError,
    discover_data_files,
    load_table,
    standardize_options_frame,
    standardize_price_frame,
)
from research_xau_vol_oi.expected_move import add_expected_move_columns
from research_xau_vol_oi.oi_wall_engine import build_oi_walls
from research_xau_vol_oi.volatility_engine import (
    add_bollinger_baseline,
    add_realized_volatility,
    add_volatility_regime,
)
from research_xau_vol_oi.zone_classifier import build_signal_events, choose_wall_for_bar


def run_pipeline(
    *,
    price_path: str | Path | None = None,
    options_path: str | Path | None = None,
    output_dir: str | Path | None = None,
    config: ResearchConfig | None = None,
) -> dict[str, Path]:
    """Run the local research pipeline and write requested outputs."""

    cfg = config or ResearchConfig()
    if output_dir is not None:
        cfg = ResearchConfig(output_dir=Path(output_dir))

    selected_price, selected_options = select_default_inputs(
        price_path=price_path,
        options_path=options_path,
    )
    output_root = cfg.output_dir
    charts_dir = output_root / cfg.chart_dir_name
    output_root.mkdir(parents=True, exist_ok=True)
    charts_dir.mkdir(parents=True, exist_ok=True)

    inventory = discover_data_files(config=cfg)
    inventory.write_csv(output_root / "data_inventory.csv")

    price_raw = load_table(selected_price)
    options_raw = load_table(selected_options)
    price = standardize_price_frame(price_raw, source_path=selected_price, config=cfg)
    options = standardize_options_frame(options_raw, source_path=selected_options, config=cfg)
    options = add_basis_columns(options)
    iv_percent = _default_iv_percent(options)
    reference_price = _reference_price(price, options)
    price_features = add_expected_move_columns(price, annualized_iv_percent=iv_percent, config=cfg)
    price_features = add_realized_volatility(price_features)
    price_features = add_volatility_regime(price_features)
    price_features = add_bollinger_baseline(price_features)

    latest_one_sd = _first_non_null(price_features, "one_sd_remaining")
    walls = build_oi_walls(
        options,
        reference_price=reference_price,
        one_sd_remaining=latest_one_sd,
        config=cfg,
    )
    feature_table = attach_wall_context(price_features, walls, config=cfg)
    signal_events = build_signal_events(feature_table, walls, config=cfg)
    trades, summary = backtest_all_scenarios(feature_table, signal_events, config=cfg)
    walk_forward = walk_forward_validate(feature_table, signal_events, config=cfg)

    feature_path = output_root / "xau_feature_table.parquet"
    events_path = output_root / "signal_events.csv"
    summary_path = output_root / "backtest_summary.csv"
    feature_table.write_parquet(feature_path)
    signal_events.write_csv(events_path)
    summary.write_csv(summary_path)
    trades.write_csv(output_root / "backtest_trades.csv")
    walk_forward.write_csv(output_root / "walk_forward_validation.csv")
    walls.write_csv(output_root / "oi_walls.csv")

    write_charts(
        feature_table=feature_table,
        walls=walls,
        events=signal_events,
        trades=trades,
        summary=summary,
        chart_dir=charts_dir,
    )
    report_path = output_root / "research_report.md"
    write_research_report(
        report_path,
        price_path=selected_price,
        options_path=selected_options,
        inventory=inventory,
        feature_table=feature_table,
        events=signal_events,
        trades=trades,
        summary=summary,
        walk_forward=walk_forward,
        charts_dir=charts_dir,
    )
    return {
        "feature_table": feature_path,
        "signal_events": events_path,
        "backtest_summary": summary_path,
        "research_report": report_path,
        "charts": charts_dir,
    }


def select_default_inputs(
    *,
    price_path: str | Path | None,
    options_path: str | Path | None,
) -> tuple[Path, Path]:
    """Select local defaults when explicit paths are not supplied."""

    if price_path is not None and options_path is not None:
        return Path(price_path), Path(options_path)

    default_price = Path("data/raw/yahoo/gc=f_15m_ohlcv_20260513_20260521.parquet")
    default_options = Path("backend/data/raw/xau/quikstrike_20260513_101537_xau_vol_oi_input.csv")
    if price_path is None and not default_price.exists():
        candidates = sorted(Path("data/raw/yahoo").glob("*ohlcv*.parquet"))
        if not candidates:
            raise DataLoadError("No default Yahoo/price OHLCV parquet file was found.")
        default_price = candidates[-1]
    if options_path is None and not default_options.exists():
        candidates = sorted(Path("backend/data/raw/xau").glob("*xau*oi*.csv"))
        if not candidates:
            raise DataLoadError("No default XAU options OI CSV file was found.")
        default_options = candidates[-1]
    return Path(price_path or default_price), Path(options_path or default_options)


def attach_wall_context(
    price_features: pl.DataFrame,
    walls: pl.DataFrame,
    *,
    config: ResearchConfig | None = None,
) -> pl.DataFrame:
    """Attach nearest available wall fields to every price feature row."""

    cfg = config or ResearchConfig()
    wall_rows = walls.to_dicts() if not walls.is_empty() else []
    rows: list[dict[str, Any]] = []
    for row in price_features.to_dicts():
        wall = choose_wall_for_bar(row, wall_rows, config=cfg)
        rows.append(
            {
                **row,
                "wall_id": wall.get("wall_id") if wall else None,
                "wall_level": wall.get("wall_level") if wall else None,
                "wall_score": wall.get("wall_score") if wall else None,
                "wall_score_bucket": _wall_score_bucket(wall.get("wall_score") if wall else None),
                "wall_side": wall.get("wall_side") if wall else None,
                "dte": wall.get("dte") if wall else None,
                "dte_bucket": _dte_bucket(wall.get("dte") if wall else None),
                "basis": wall.get("basis") if wall else None,
                "basis_source": wall.get("basis_source") if wall else None,
            }
        )
    return pl.DataFrame(rows) if rows else price_features


def write_charts(
    *,
    feature_table: pl.DataFrame,
    walls: pl.DataFrame,
    events: pl.DataFrame,
    trades: pl.DataFrame,
    summary: pl.DataFrame,
    chart_dir: Path,
) -> None:
    """Write lightweight SVG chart artifacts without adding plotting dependencies."""

    prices = [(row["timestamp"], row["close"]) for row in feature_table.to_dicts()]
    _write_line_svg(
        chart_dir / "xau_price_sd_bands.svg",
        title="XAU price with IV 1SD/2SD/3SD bands",
        series=[float(row["close"]) for row in feature_table.to_dicts()],
    )
    _write_bar_svg(
        chart_dir / "spot_adjusted_oi_walls.svg",
        title="Spot-adjusted OI walls",
        labels=[str(row.get("strike")) for row in walls.to_dicts()],
        values=[float(row.get("wall_level") or 0.0) for row in walls.to_dicts()],
    )
    _write_bar_svg(
        chart_dir / "wall_score_heatmap.svg",
        title="Wall score heatmap",
        labels=[str(row.get("strike")) for row in walls.to_dicts()],
        values=[float(row.get("wall_score") or 0.0) for row in walls.to_dicts()],
    )
    _write_marker_svg(
        chart_dir / "signal_markers.svg",
        title="Signal markers",
        count=len(events),
        labels=[str(row.get("signal")) for row in events.head(20).to_dicts()],
    )
    _write_line_svg(
        chart_dir / "equity_curve_by_signal_type.svg",
        title="Equity curve by signal type",
        series=_equity_curve(trades),
    )
    _write_bar_svg(
        chart_dir / "expectancy_by_sigma_zone.svg",
        title="Expectancy by sigma zone",
        labels=_summary_labels(summary, "sigma_zone"),
        values=_summary_values(summary, "sigma_zone"),
    )
    _write_bar_svg(
        chart_dir / "expectancy_by_wall_score_bucket.svg",
        title="Expectancy by wall_score bucket",
        labels=_summary_labels(summary, "wall_score_bucket"),
        values=_summary_values(summary, "wall_score_bucket"),
    )
    _write_marker_svg(
        chart_dir / "confusion_wall_reject_vs_break.svg",
        title="Confusion table: wall reject vs wall break",
        count=len(prices),
        labels=_confusion_labels(events),
    )


def write_research_report(
    path: Path,
    *,
    price_path: Path,
    options_path: Path,
    inventory: pl.DataFrame,
    feature_table: pl.DataFrame,
    events: pl.DataFrame,
    trades: pl.DataFrame,
    summary: pl.DataFrame,
    walk_forward: pl.DataFrame,
    charts_dir: Path,
) -> None:
    """Write a research report that answers the requested evaluation questions."""

    signal_counts = events.group_by("signal").len().sort("signal") if not events.is_empty() else pl.DataFrame()
    directional = summary.filter(pl.col("group_type") == "signal") if not summary.is_empty() else pl.DataFrame()
    answers = _answer_questions(directional)
    text = [
        "# XAU/USD Vol-OI Research Report",
        "",
        "This report is a local research artifact. It is not a live trading bot, "
        "not an order system, and not evidence of live readiness.",
        "",
        "## Inputs",
        "",
        f"- Price data: `{price_path}`",
        f"- CME/options data: `{options_path}`",
        f"- Inventory files found: {inventory.height}",
        f"- Feature rows: {feature_table.height}",
        f"- Signal events: {events.height}",
        f"- Backtest trades/control observations: {trades.height}",
        f"- Walk-forward splits: {walk_forward.height}",
        "",
        "## Available Data Inventory",
        "",
        *_inventory_lines(inventory),
        "",
        "## Signal Counts",
        "",
        _frame_markdown(signal_counts),
        "",
        "## Backtest Summary",
        "",
        _frame_markdown(directional),
        "",
        "## Required Questions",
        "",
        *answers,
        "",
        "## Charts",
        "",
        *[f"- `{path.name}`" for path in sorted(charts_dir.glob('*.svg'))],
        "",
        "## Limitations",
        "",
        "- Yahoo GC=F is a futures OHLCV proxy and is not true XAUUSD spot.",
        "- OI wall data quality depends on imported CME/QuikStrike-style files.",
        "- The current pipeline uses deterministic thresholds and walk-forward splits; "
        "thresholds should be selected in formation periods only.",
        "- No result here should be read as a profitability, prediction, safety, or "
        "live-readiness claim.",
        "",
        "## Next Tests",
        "",
        "- Add longer CME options history with verified timestamp availability.",
        "- Compare basis-adjusted walls against unadjusted walls on the same windows.",
        "- Separate news-disabled windows and session-specific behavior.",
        "- Validate transcript-derived rules one rule at a time before combining them.",
    ]
    path.write_text("\n".join(text), encoding="utf-8")


def _default_iv_percent(options: pl.DataFrame) -> float:
    values = [value for value in options.get_column("iv_percent").to_list() if value is not None]
    return float(sum(values) / len(values)) if values else 16.0


def _reference_price(price: pl.DataFrame, options: pl.DataFrame) -> float:
    spot_values = [value for value in options.get_column("spot_price").to_list() if value is not None]
    if spot_values:
        return float(spot_values[-1])
    return float(price.get_column("close").head(1).item())


def _first_non_null(frame: pl.DataFrame, column: str) -> float | None:
    if column not in frame.columns:
        return None
    for value in frame.get_column(column).to_list():
        if value is not None:
            return float(value)
    return None


def _wall_score_bucket(value: Any) -> str:
    if value is None:
        return "unknown"
    value = float(value)
    if value >= 0.30:
        return "high"
    if value >= 0.15:
        return "medium"
    return "low"


def _dte_bucket(value: Any) -> str:
    if value is None:
        return "unknown"
    value = float(value)
    if value <= 3:
        return "0_3d"
    if value <= 10:
        return "4_10d"
    if value <= 30:
        return "11_30d"
    return "over_30d"


def _inventory_lines(inventory: pl.DataFrame) -> list[str]:
    if inventory.is_empty():
        return ["No local research data files found."]
    grouped = inventory.group_by(["category", "extension"]).len().sort(["category", "extension"])
    lines = ["| category | extension | count |", "|---|---:|---:|"]
    for row in grouped.to_dicts():
        lines.append(f"| {row['category']} | {row['extension']} | {row['len']} |")
    return lines


def _answer_questions(summary: pl.DataFrame) -> list[str]:
    if summary.is_empty():
        return [
            "- Does 1SD/2SD range logic work by itself? Not established; no completed "
            "control observations were available.",
            "- Does adding CME OI wall data improve it? Not established without paired "
            "control and wall-signal samples.",
            "- Does basis-adjusted OI wall mapping improve it? Not established here; "
            "compare against an unadjusted-wall ablation next.",
            "- Which signal works better: fade wall or break wall? Not established.",
            "- Which zones should be no-trade zones? Bad data, stale data, missing IV, "
            "missing basis, no nearby wall, and middle 1SD without wall evidence.",
            "- Which transcript-derived rules are supported by data? The formulas and "
            "classification gates are implemented; statistical support requires more data.",
            "- Which rules fail? No deterministic rule is marked failed until it has "
            "adequate sample coverage.",
            "- What should be tested next? Longer CME history, basis ablations, and "
            "session/news segmentation.",
        ]
    return [
        "- Does 1SD/2SD range logic work by itself? Check `SD_ONLY_BASELINE` rows in "
        "the signal summary; this is the range-only control.",
        "- Does adding CME OI wall data improve it? Compare fade/break wall expectancy "
        "against `SD_ONLY_BASELINE` and `RANDOM_BASELINE`.",
        "- Does basis-adjusted OI wall mapping improve it? The pipeline maps strikes "
        "with basis; add an unadjusted ablation before making that claim.",
        "- Which signal works better: fade wall or break wall? Use the signal-level "
        "expectancy/profit-factor rows, subject to sample size.",
        "- Which zones should be no-trade zones? Bad quality, stale, missing IV, "
        "missing basis, no nearby wall, and middle 1SD without high-score walls.",
        "- Which transcript-derived guru rules are supported by data? Basis mapping, "
        "IV expected move, acceptance confirmation, no-trade gates, and wall scoring "
        "are implemented as testable rules.",
        "- Which rules fail? The report does not declare failures without adequate "
        "walk-forward sample coverage.",
        "- What should be tested next? Add unadjusted-wall and no-basis ablations, "
        "news-disabled labels, and separate near-expiry pin tests.",
    ]


def _frame_markdown(frame: pl.DataFrame) -> str:
    if frame.is_empty():
        return "_No rows._"
    columns = frame.columns
    rows = ["| " + " | ".join(columns) + " |", "|" + "|".join(["---"] * len(columns)) + "|"]
    for raw in frame.head(20).to_dicts():
        rows.append("| " + " | ".join(str(raw.get(column, "")) for column in columns) + " |")
    return "\n".join(rows)


def _write_line_svg(path: Path, *, title: str, series: list[float]) -> None:
    width, height = 900, 260
    if not series:
        _write_empty_svg(path, title)
        return
    minimum, maximum = min(series), max(series)
    span = max(maximum - minimum, 1.0)
    points = []
    for index, value in enumerate(series):
        x = 40 + index * (width - 80) / max(len(series) - 1, 1)
        y = height - 40 - ((value - minimum) / span) * (height - 80)
        points.append(f"{x:.1f},{y:.1f}")
    path.write_text(
        _svg(title, f'<polyline fill="none" stroke="#2563eb" stroke-width="2" points="{" ".join(points)}" />'),
        encoding="utf-8",
    )


def _write_bar_svg(path: Path, *, title: str, labels: list[str], values: list[float]) -> None:
    width, height = 900, 300
    if not values:
        _write_empty_svg(path, title)
        return
    maximum = max(max(abs(value) for value in values), 1.0)
    bar_width = max(4, (width - 80) / max(len(values), 1))
    bars = []
    for index, value in enumerate(values):
        x = 40 + index * bar_width
        bar_height = abs(value) / maximum * (height - 90)
        y = height - 40 - bar_height
        bars.append(
            f'<rect x="{x:.1f}" y="{y:.1f}" width="{bar_width * 0.8:.1f}" '
            f'height="{bar_height:.1f}" fill="#0f766e"><title>{labels[index]}</title></rect>'
        )
    path.write_text(_svg(title, "\n".join(bars)), encoding="utf-8")


def _write_marker_svg(path: Path, *, title: str, count: int, labels: list[str]) -> None:
    body = [f'<text x="40" y="70" font-size="16">count: {count}</text>']
    for index, label in enumerate(labels[:20]):
        y = 105 + index * 18
        body.append(f'<circle cx="50" cy="{y}" r="4" fill="#dc2626" />')
        body.append(f'<text x="65" y="{y + 4}" font-size="12">{label}</text>')
    path.write_text(_svg(title, "\n".join(body)), encoding="utf-8")


def _write_empty_svg(path: Path, title: str) -> None:
    path.write_text(_svg(title, '<text x="40" y="80">No data available.</text>'), encoding="utf-8")


def _svg(title: str, body: str) -> str:
    return (
        '<svg xmlns="http://www.w3.org/2000/svg" width="900" height="300" '
        'viewBox="0 0 900 300">'
        f'<rect width="900" height="300" fill="#ffffff" />'
        f'<text x="40" y="30" font-size="18" font-family="Arial">{title}</text>'
        f"{body}</svg>"
    )


def _equity_curve(trades: pl.DataFrame) -> list[float]:
    running = 0.0
    curve = [0.0]
    for row in trades.to_dicts():
        running += float(row.get("pnl_points") or 0.0)
        curve.append(running)
    return curve


def _summary_labels(summary: pl.DataFrame, group_type: str) -> list[str]:
    if summary.is_empty():
        return []
    return [
        str(row["bucket"])
        for row in summary.filter(pl.col("group_type") == group_type).to_dicts()
    ]


def _summary_values(summary: pl.DataFrame, group_type: str) -> list[float]:
    if summary.is_empty():
        return []
    return [
        float(row.get("expectancy") or 0.0)
        for row in summary.filter(pl.col("group_type") == group_type).to_dicts()
    ]


def _confusion_labels(events: pl.DataFrame) -> list[str]:
    if events.is_empty():
        return []
    labels = []
    for signal in ["FADE_WALL_LONG", "FADE_WALL_SHORT", "BREAK_WALL_LONG", "BREAK_WALL_SHORT"]:
        count = events.filter(pl.col("signal") == signal).height
        labels.append(f"{signal}: {count}")
    return labels


def main() -> None:
    """CLI entry point."""

    parser = argparse.ArgumentParser(description="Run XAU Vol-OI research pipeline.")
    parser.add_argument("--price", type=Path, default=None)
    parser.add_argument("--options", type=Path, default=None)
    parser.add_argument("--output-dir", type=Path, default=Path("outputs"))
    args = parser.parse_args()
    paths = run_pipeline(price_path=args.price, options_path=args.options, output_dir=args.output_dir)
    for name, path in paths.items():
        print(f"{name}: {path}")


if __name__ == "__main__":
    main()
