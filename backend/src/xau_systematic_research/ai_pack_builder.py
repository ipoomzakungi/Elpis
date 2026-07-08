from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from src.models.xau_systematic_research import (
    XauAiResearchPack,
    XauAlignedSourceState,
    XauSourceManifest,
    XauSystematicReadiness,
)

RESEARCH_ONLY_WARNING = "Research-only. Not a buy/sell signal."


class XauAiResearchPackBuilder:
    def build(
        self,
        *,
        state: XauAlignedSourceState,
        manifest: XauSourceManifest,
    ) -> tuple[XauAiResearchPack, str, str]:
        readiness = _readiness_from_flags(state)
        pack = XauAiResearchPack(
            pack_id=f"ai_pack_{state.cycle_id}",
            cycle_id=state.cycle_id,
            created_at=datetime.now(UTC),
            session_date=state.session_date,
            cycle_label=state.cycle_label,
            executive_summary=_executive_summary(readiness, state),
            source_status_table=_source_status_table(manifest),
            key_levels_table=_key_levels_table(state),
            mapped_levels_table=state.mapped_structure.top_mapped_walls,
            volatility_summary=state.volatility.model_dump(mode="json"),
            basis_summary=state.basis.model_dump(mode="json"),
            session_summary=state.session.model_dump(mode="json"),
            candle_summary={
                "candle_state": state.states.candle_state,
                "nearest_mapped_wall": state.mapped_structure.nearest_mapped_wall,
            },
            oi_iv_volume_summary={
                "oi_state": state.states.oi_state,
                "iv_state": state.states.iv_state,
                "volume_state": state.states.volume_state,
                "doctrine": "OI is structural context only and does not create direction.",
            },
            readiness=readiness,
            no_trade_reasons=state.no_trade_reasons,
            questions_for_human=_questions_for_human(state),
            next_actions=_next_actions(readiness, state),
            machine_context={
                "cycle_id": state.cycle_id,
                "fusion_report_id": state.cme.fusion_report_id,
                "bars_path": state.price.bars_path.as_posix() if state.price.bars_path else None,
                "signal_allowed": False,
                "research_only": True,
            },
        )
        markdown = build_ai_research_pack_markdown(pack, state, manifest)
        handoff = build_ai_handoff_context(pack, markdown)
        return pack, markdown, handoff


def build_ai_research_pack_markdown(
    pack: XauAiResearchPack,
    state: XauAlignedSourceState,
    manifest: XauSourceManifest,
) -> str:
    lines = [
        f"# XAU AI Research Pack {pack.cycle_id}",
        "",
        RESEARCH_ONLY_WARNING,
        "",
        "## Summary",
        pack.executive_summary,
        "",
        "## Data Fetched Or Reused",
        f"- Vol2Vol report: `{state.cme.vol2vol_report_id}`",
        f"- Matrix report: `{state.cme.matrix_report_id}`",
        f"- Fusion report: `{state.cme.fusion_report_id}`",
        f"- Price bars: `{state.price.bars_path}`",
        f"- CME fresh status: `{manifest.fusion_status.value}`",
        f"- Price fresh status: `{manifest.traded_price_status.value}`",
        "",
        "## Basis",
        f"- Formula: `{state.basis.basis_formula}`",
        f"- Mapping: `{state.basis.mapping_formula}`",
        f"- GC futures: `{state.basis.gc_futures_price}`",
        f"- XAUUSD/GO traded reference: `{state.basis.xauusd_spot_price}`",
        f"- Basis points: `{state.basis.basis_points}`",
        f"- Status: `{state.basis.basis_status.value}`",
        "",
        "## Top Futures-Side OI Walls",
        *_table_lines(pack.key_levels_table, ("futures_level", "score", "value_types")),
        "",
        "## Top Mapped Traded-Side Walls",
        *_table_lines(
            pack.mapped_levels_table,
            ("futures_level", "mapped_level", "distance_points", "mapping_status"),
        ),
        "",
        "## OI Change / Volume / IV",
        f"- OI state: `{state.states.oi_state}`",
        f"- IV state: `{state.states.iv_state}`",
        f"- Volume state: `{state.states.volume_state}`",
        "",
        "## Session Open",
        f"- Active session: `{state.session.active_session}`",
        f"- Session open: `{state.session.session_open}`",
        f"- Open side: `{state.session.open_side}`",
        f"- Open distance: `{state.session.open_distance_points}`",
        "",
        "## ATR / RV",
        f"- ATR 5m: `{state.volatility.atr_5m}`",
        f"- ATR 15m: `{state.volatility.atr_15m}`",
        f"- ATR 1h: `{state.volatility.atr_1h}`",
        f"- RV 30m: `{state.volatility.realized_vol_30m}`",
        f"- RV session: `{state.volatility.realized_vol_session}`",
        f"- Status: `{state.volatility.status.value}`",
        "",
        "## Candle State",
        f"- State: `{state.states.candle_state}`",
        f"- Nearest mapped wall: `{state.mapped_structure.nearest_mapped_wall}`",
        "",
        "## Readiness",
        f"- Status: `{pack.readiness.value}`",
        *_bullet_lines(pack.no_trade_reasons),
        "",
        "## Next Inspection",
        *_bullet_lines(pack.next_actions),
        "",
        "## Limitations",
        *_bullet_lines(manifest.limitations),
    ]
    return "\n".join(lines) + "\n"


def build_ai_handoff_context(pack: XauAiResearchPack, markdown: str) -> str:
    return "\n".join(
        [
            f"# AI Handoff Context {pack.cycle_id}",
            "",
            RESEARCH_ONLY_WARNING,
            "",
            "Use this file to brief another AI or human reviewer. Do not infer a trade, "
            "direction, entry, stop, target, size, order, or live readiness from this pack.",
            "",
            markdown,
        ]
    )


def _readiness_from_flags(state: XauAlignedSourceState) -> XauSystematicReadiness:
    if state.readiness.blocked:
        return XauSystematicReadiness.BLOCKED
    if state.readiness.ready_for_shadow_review:
        return XauSystematicReadiness.READY_FOR_SHADOW_REVIEW
    return XauSystematicReadiness.PARTIAL


def _executive_summary(readiness: XauSystematicReadiness, state: XauAlignedSourceState) -> str:
    return (
        f"Cycle {state.cycle_id} is {readiness.value}. CME structure, traded-side price "
        "context, basis mapping, session, volatility, and candle state were aligned for "
        "research review only."
    )


def _source_status_table(manifest: XauSourceManifest) -> list[dict[str, Any]]:
    return [
        {"source": name, "status": getattr(manifest, name).value}
        for name in (
            "cme_vol2vol_status",
            "cme_matrix_status",
            "fusion_status",
            "traded_price_status",
            "basis_status",
            "session_open_status",
            "volatility_status",
            "candle_state_status",
            "ai_pack_status",
        )
    ]


def _key_levels_table(state: XauAlignedSourceState) -> list[dict[str, Any]]:
    return [
        {
            "futures_level": wall.get("futures_level"),
            "score": wall.get("score"),
            "value_types": wall.get("value_types"),
        }
        for wall in state.mapped_structure.top_mapped_walls
    ]


def _questions_for_human(state: XauAlignedSourceState) -> list[str]:
    questions = []
    if state.basis.basis_points is None:
        questions.append("Confirm the GC futures reference and XAUUSD/GO traded reference.")
    if not state.mapped_structure.top_mapped_walls:
        questions.append("Confirm whether the CME fusion report contains usable OI walls.")
    if state.states.candle_state == "unavailable":
        questions.append("Confirm traded-side candle coverage around mapped walls.")
    return questions or ["Review mapped walls and candle state before any later shadow feature."]


def _next_actions(readiness: XauSystematicReadiness, state: XauAlignedSourceState) -> list[str]:
    if readiness == XauSystematicReadiness.BLOCKED:
        return ["Resolve missing context listed in no_trade_reasons and rerun the cycle."]
    if readiness == XauSystematicReadiness.PARTIAL:
        return ["Inspect partial sources and decide whether to rerun after fresh data arrives."]
    return [
        "Review mapped walls, basis, ATR/RV, and candle state manually.",
        "Do not treat this pack as a signal; it only prepares shadow-review context.",
    ]


def _table_lines(rows: list[dict[str, Any]], columns: tuple[str, ...]) -> list[str]:
    if not rows:
        return ["- unavailable"]
    return [
        "- " + ", ".join(f"{column}=`{row.get(column)}`" for column in columns)
        for row in rows[:10]
    ]


def _bullet_lines(values: list[str]) -> list[str]:
    return [f"- {value}" for value in values] if values else ["- none"]
