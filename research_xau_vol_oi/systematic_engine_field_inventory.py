"""Field inventory for a research-only CME/Vol2Vol-style engine.

This module maps the current Elpis QuikStrike/XAU outputs to the fields needed
for a point-in-time daily structural map and a later five-minute research engine.
It is intentionally descriptive: it does not create signals, execution behavior,
or strategy claims.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Mapping

import polars as pl


RESEARCH_ONLY_WARNING = (
    "Research-only field inventory. This is a data-parity checklist, not a "
    "trading signal, execution path, profitability claim, predictive claim, "
    "safety claim, or live-readiness claim."
)


STATUS_AVAILABLE = "available"
STATUS_DERIVED = "derived"
STATUS_PARTIAL = "partial"
STATUS_MISSING = "missing"


@dataclass(frozen=True)
class EngineFieldRequirement:
    """One engine field and how it maps to current Elpis artifacts."""

    priority: str
    engine_layer: str
    engine_field: str
    target_fields: tuple[str, ...]
    source_fields: tuple[str, ...]
    all_target_fields_required: bool = False
    derivable_if_all: tuple[str, ...] = ()
    required_action: str = ""
    blocks_daily_map: bool = False
    blocks_intraday_engine: bool = False
    blocks_backtest: bool = False
    notes: str = ""


DEFAULT_CURRENT_OUTPUT_FIELDS: dict[str, tuple[str, ...]] = {
    "quikstrike_vol2vol_rows": (
        "capture_timestamp",
        "product",
        "option_product_code",
        "futures_symbol",
        "expiration",
        "expiration_code",
        "dte",
        "future_reference_price",
        "strike",
        "option_type",
        "value",
        "value_type",
        "vol_settle",
        "range_label",
        "sigma_label",
    ),
    "quikstrike_matrix_rows": (
        "capture_timestamp",
        "product",
        "option_product_code",
        "futures_symbol",
        "expiration",
        "dte",
        "future_reference_price",
        "strike",
        "option_type",
        "value",
        "open_interest",
        "oi_change",
        "volume",
        "cell_state",
        "raw_value",
    ),
    "xau_quikstrike_fusion_rows": (
        "future_reference_price",
        "dte",
        "vol_settle",
        "range_label",
        "sigma_label",
        "basis_points",
        "spot_equivalent_level",
        "open_interest",
        "oi_change",
        "volume",
        "intraday_volume",
        "eod_volume",
        "churn",
        "implied_volatility",
        "underlying_futures_price",
        "source_agreement_status",
    ),
    "xau_vol_oi_report": (
        "basis",
        "basis_source",
        "mapping_available",
        "expected_move",
        "lower_1sd",
        "upper_1sd",
        "lower_2sd",
        "upper_2sd",
        "days_to_expiry",
        "oi_share",
        "expiry_weight",
        "freshness_factor",
        "wall_score",
    ),
    "xau_reaction_report": (
        "session_open",
        "current_price",
        "sigma_position",
        "inside_1sd",
        "freshness_state",
        "basis_available",
    ),
    "xau_forward_journal": (
        "journal_id",
        "snapshot_time",
        "spot_price_at_snapshot",
        "futures_price_at_snapshot",
        "basis",
        "session_open_price",
        "outcome_windows",
    ),
    "research_history_normalizer": (
        "expected_range",
        "dte",
        "delta",
        "gamma",
        "intraday_volume",
        "underlying_futures_price",
    ),
    "cme_expected_range_snapshot": (
        "official_release_ts",
        "source_status",
        "reference_futures_price",
        "report_level_iv",
        "fractional_dte",
        "cme_numeric_1sd",
        "cme_numeric_2sd",
        "cme_numeric_3sd",
        "upper_1sd",
        "lower_1sd",
        "upper_2sd",
        "lower_2sd",
        "upper_3sd",
        "lower_3sd",
        "range_source",
        "extraction_quality",
    ),
}


ENGINE_FIELD_REQUIREMENTS: tuple[EngineFieldRequirement, ...] = (
    EngineFieldRequirement(
        "P0",
        "point_in_time",
        "capture_ts",
        ("capture_ts", "capture_timestamp", "timestamp", "snapshot_time"),
        ("capture_timestamp", "timestamp", "snapshot_time"),
        required_action="Normalize capture timestamps into one canonical capture_ts field.",
        blocks_backtest=True,
    ),
    EngineFieldRequirement(
        "P0",
        "point_in_time",
        "official_release_ts",
        ("official_release_ts",),
        (),
        required_action="Add official CME preliminary/final release timestamps per snapshot.",
        blocks_backtest=True,
        notes="Needed to prevent same-day bulletin lookahead.",
    ),
    EngineFieldRequirement(
        "P0",
        "point_in_time",
        "source_status",
        ("source_status",),
        (),
        required_action="Persist preliminary/final/source-status metadata instead of only capture status.",
        blocks_backtest=True,
    ),
    EngineFieldRequirement(
        "P0",
        "daily_structural_map",
        "reference_futures_price",
        ("reference_futures_price",),
        ("future_reference_price", "underlying_futures_price", "futures_price_at_snapshot"),
        required_action="Normalize Vol2Vol and Matrix futures references into one settle/reference field.",
        blocks_daily_map=True,
    ),
    EngineFieldRequirement(
        "P0",
        "daily_structural_map",
        "fractional_dte",
        ("fractional_dte",),
        ("dte", "days_to_expiry"),
        required_action="Preserve raw fractional DTE through fusion and XAU report outputs.",
        blocks_daily_map=True,
        notes="Current backend carries dte in source/fusion values, while XAU report models use integer days.",
    ),
    EngineFieldRequirement(
        "P0",
        "daily_structural_map",
        "report_level_iv",
        ("report_level_iv", "iv_report"),
        ("vol_settle", "implied_volatility"),
        required_action="Capture the Vol2Vol title/report-level volatility separately from strike IV.",
        blocks_daily_map=True,
        notes="Per-strike IV exists, but the CME SD-band anchor is not materialized distinctly.",
    ),
    EngineFieldRequirement(
        "P0",
        "daily_structural_map",
        "cme_numeric_sd_bands",
        ("cme_numeric_1sd", "cme_numeric_2sd", "cme_numeric_3sd"),
        ("range_label", "sigma_label", "expected_range", "lower_1sd", "upper_1sd"),
        all_target_fields_required=True,
        derivable_if_all=("reference_futures_price", "report_level_iv", "fractional_dte"),
        required_action="Persist CME numeric 1SD/2SD/3SD bands; computed bands are a fallback.",
        blocks_daily_map=True,
        blocks_backtest=True,
        notes="Range labels and local expected ranges are not exact CME numeric band parity.",
    ),
    EngineFieldRequirement(
        "P0",
        "daily_structural_map",
        "open_interest",
        ("open_interest",),
        ("open_interest",),
        required_action="Keep preserving OI without coercing blank Matrix cells to zero.",
    ),
    EngineFieldRequirement(
        "P0",
        "daily_structural_map",
        "oi_change",
        ("oi_change",),
        ("oi_change",),
        required_action="Keep preserving OI-change and blank/null semantics.",
    ),
    EngineFieldRequirement(
        "P0",
        "daily_structural_map",
        "intraday_volume",
        ("intraday_volume",),
        ("intraday_volume", "volume"),
        required_action="Promote same-session electronic volume into the intraday engine input.",
        blocks_intraday_engine=True,
    ),
    EngineFieldRequirement(
        "P0",
        "intraday_engine",
        "session_open_price",
        ("session_open_price", "session_open"),
        ("session_open_price", "session_open"),
        required_action="Derive the exchange-session open from trusted futures bars instead of only manual request input.",
        blocks_intraday_engine=True,
    ),
    EngineFieldRequirement(
        "P0",
        "intraday_engine",
        "futures_1m_5m_bars",
        ("futures_bar_1m", "futures_bar_5m"),
        ("open", "high", "low", "close", "timestamp"),
        required_action="Add a dedicated local futures bar ingestion path for 1m/5m research bars.",
        blocks_intraday_engine=True,
        blocks_backtest=True,
    ),
    EngineFieldRequirement(
        "P1",
        "daily_structural_map",
        "basis_drift",
        ("basis_drift",),
        ("basis", "basis_points", "spot_price_at_snapshot", "futures_price_at_snapshot"),
        required_action="Persist synchronized spot/futures basis snapshots and block spot mapping when missing.",
        blocks_intraday_engine=True,
    ),
    EngineFieldRequirement(
        "P1",
        "daily_structural_map",
        "delta_gamma",
        ("delta", "gamma"),
        ("delta", "gamma"),
        required_action="Add a pricing-sheet extractor or local Black-Scholes fallback with explicit assumptions.",
        notes="Some schemas can hold delta/gamma, but current fusion/report rows do not make them reliable.",
    ),
    EngineFieldRequirement(
        "P1",
        "daily_structural_map",
        "gex_and_gamma_regime",
        ("gross_gex", "net_gex_assumed", "gamma_regime"),
        ("delta", "gamma", "open_interest", "underlying_futures_price"),
        all_target_fields_required=True,
        derivable_if_all=("delta", "gamma", "open_interest", "underlying_futures_price"),
        required_action="Materialize gross GEX, heuristic net GEX, and gamma regime with documented sign convention.",
        blocks_intraday_engine=True,
    ),
    EngineFieldRequirement(
        "P1",
        "daily_structural_map",
        "walls_json",
        ("walls_json",),
        ("oi_share", "expiry_weight", "freshness_factor", "wall_score"),
        required_action="Package current wall-score components into a versioned daily structural-map payload.",
        blocks_daily_map=True,
    ),
    EngineFieldRequirement(
        "P1",
        "intraday_engine",
        "flow_ratio",
        ("flow_ratio",),
        ("intraday_volume", "open_interest"),
        derivable_if_all=("intraday_volume", "open_interest"),
        required_action="Compute rolling option-flow ratio at strike or local band level.",
        blocks_intraday_engine=True,
    ),
    EngineFieldRequirement(
        "P1",
        "intraday_engine",
        "z_expiry",
        ("z_expiry",),
        ("current_price", "reference_futures_price", "sd1_expiry"),
        derivable_if_all=("current_price", "reference_futures_price", "sd1_expiry"),
        required_action="Compute expiry-horizon z-score from the daily structural map and 5m bars.",
        blocks_intraday_engine=True,
    ),
    EngineFieldRequirement(
        "P1",
        "backtest",
        "next_bar_execution_protocol",
        ("signal_bar_close_ts", "next_bar_open_ts"),
        (),
        required_action="Add a no-lookahead fixture for signal-at-5m-close and next-bar-open execution.",
        blocks_backtest=True,
    ),
    EngineFieldRequirement(
        "P1",
        "validation",
        "cme_sd_parity_report",
        ("cme_1sd_minus_computed_1sd", "dte_precision_comparison"),
        ("expected_range", "lower_1sd", "upper_1sd"),
        all_target_fields_required=True,
        required_action="Generate CME numeric-vs-computed SD parity and rounded-vs-fractional DTE reports.",
        blocks_backtest=True,
    ),
)


def build_systematic_engine_field_inventory(
    current_fields_by_source: Mapping[str, Iterable[str]] | None = None,
) -> pl.DataFrame:
    """Return the required engine fields with current availability and gaps."""

    sources = {
        source: tuple(fields)
        for source, fields in (current_fields_by_source or DEFAULT_CURRENT_OUTPUT_FIELDS).items()
    }
    all_fields = {field for fields in sources.values() for field in fields}
    rows = [_inventory_row(requirement, all_fields, sources) for requirement in ENGINE_FIELD_REQUIREMENTS]
    return pl.DataFrame(rows, schema=_inventory_schema()).sort(
        ["priority", "engine_layer", "engine_field"]
    )


def build_engine_inventory_summary(inventory: pl.DataFrame) -> pl.DataFrame:
    """Summarize field availability by engine layer and status."""

    if inventory.is_empty():
        return pl.DataFrame(
            schema={
                "engine_layer": pl.Utf8,
                "status": pl.Utf8,
                "field_count": pl.Int64,
            }
        )
    return (
        inventory.group_by(["engine_layer", "status"])
        .agg(pl.len().alias("field_count"))
        .sort(["engine_layer", "status"])
    )


def engine_inventory_markdown(inventory: pl.DataFrame) -> str:
    """Render a compact Markdown checklist."""

    lines = [
        "# Systematic CME Engine Field Inventory",
        "",
        RESEARCH_ONLY_WARNING,
        "",
        "## Field Map",
        "",
        _frame_markdown(inventory),
    ]
    return "\n".join(lines)


def _inventory_row(
    requirement: EngineFieldRequirement,
    all_fields: set[str],
    sources: Mapping[str, tuple[str, ...]],
) -> dict[str, object]:
    target_present = [field for field in requirement.target_fields if field in all_fields]
    source_present = [field for field in requirement.source_fields if field in all_fields]
    derivation_present = [field for field in requirement.derivable_if_all if field in all_fields]

    status = _status_for_requirement(
        requirement=requirement,
        target_present=target_present,
        source_present=source_present,
        derivation_present=derivation_present,
    )
    missing = _missing_fields(requirement, all_fields, status)
    return {
        "priority": requirement.priority,
        "engine_layer": requirement.engine_layer,
        "engine_field": requirement.engine_field,
        "status": status,
        "current_sources": ",".join(_sources_for_fields(sources, source_present + target_present)),
        "present_fields": ",".join(dict.fromkeys(target_present + source_present)),
        "missing_fields": ",".join(missing),
        "required_action": requirement.required_action,
        "blocks_daily_map": requirement.blocks_daily_map,
        "blocks_intraday_engine": requirement.blocks_intraday_engine,
        "blocks_backtest": requirement.blocks_backtest,
        "notes": requirement.notes,
    }


def _status_for_requirement(
    *,
    requirement: EngineFieldRequirement,
    target_present: list[str],
    source_present: list[str],
    derivation_present: list[str],
) -> str:
    if requirement.target_fields and set(requirement.target_fields).issubset(target_present):
        return STATUS_AVAILABLE
    if (
        requirement.target_fields
        and target_present
        and not requirement.all_target_fields_required
    ):
        return STATUS_AVAILABLE
    if not requirement.target_fields and source_present:
        return STATUS_AVAILABLE
    if requirement.derivable_if_all and set(requirement.derivable_if_all).issubset(
        derivation_present
    ):
        return STATUS_DERIVED
    if source_present or target_present or derivation_present:
        if requirement.target_fields and not target_present:
            return STATUS_PARTIAL
        return STATUS_DERIVED
    return STATUS_MISSING


def _missing_fields(
    requirement: EngineFieldRequirement,
    all_fields: set[str],
    status: str,
) -> list[str]:
    if status == STATUS_AVAILABLE:
        return []
    missing_targets = [field for field in requirement.target_fields if field not in all_fields]
    missing_derivation = [
        field for field in requirement.derivable_if_all if field not in all_fields
    ]
    return list(dict.fromkeys([*missing_targets, *missing_derivation]))


def _sources_for_fields(
    sources: Mapping[str, tuple[str, ...]],
    fields: list[str],
) -> list[str]:
    output: list[str] = []
    field_set = set(fields)
    for source, source_fields in sources.items():
        if field_set.intersection(source_fields):
            output.append(source)
    return output


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


def _markdown_cell(value: object) -> str:
    return str(value or "").replace("|", "\\|").replace("\n", " ")[:700]


def _inventory_schema() -> dict[str, pl.DataType]:
    return {
        "priority": pl.Utf8,
        "engine_layer": pl.Utf8,
        "engine_field": pl.Utf8,
        "status": pl.Utf8,
        "current_sources": pl.Utf8,
        "present_fields": pl.Utf8,
        "missing_fields": pl.Utf8,
        "required_action": pl.Utf8,
        "blocks_daily_map": pl.Boolean,
        "blocks_intraday_engine": pl.Boolean,
        "blocks_backtest": pl.Boolean,
        "notes": pl.Utf8,
    }


if __name__ == "__main__":
    print(engine_inventory_markdown(build_systematic_engine_field_inventory()))
