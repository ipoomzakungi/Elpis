from dataclasses import dataclass
from typing import Any

from src.models.xau_reaction import (
    XauAcceptanceInput,
    XauAcceptanceResult,
    XauConfidenceLabel,
    XauFreshnessResult,
    XauFreshnessState,
    XauIvEdgeState,
    XauOpenFlipState,
    XauOpenRegimeResult,
    XauOpenSide,
    XauOpenSupportResistance,
    XauReactionReport,
    XauReactionReportRequest,
    XauReactionRow,
    XauRvExtensionState,
    XauVolRegimeResult,
    XauVrpRegime,
)
from src.xau_reaction.acceptance import classify_acceptance
from src.xau_reaction.classifier import classify_reaction_rows
from src.xau_reaction.freshness import classify_freshness
from src.xau_reaction.open_regime import evaluate_open_regime
from src.xau_reaction.vol_regime import evaluate_vol_regime


class XauReactionReportNotImplementedError(RuntimeError):
    """Raised until full reaction report loading and persistence are implemented."""


@dataclass(frozen=True)
class XauReactionContextBundle:
    """Computed context passed into the deterministic reaction classifier."""

    freshness_state: XauFreshnessResult
    vol_regime_state: XauVolRegimeResult
    open_regime_state: XauOpenRegimeResult
    acceptance_states: dict[str, XauAcceptanceResult]
    classifier_context: dict[str, Any]


class XauReactionReportOrchestrator:
    """Orchestration boundary for research-only XAU reaction report slices."""

    def run(self, request: XauReactionReportRequest) -> XauReactionReport:
        raise XauReactionReportNotImplementedError(
            "XAU reaction report persistence is not implemented in this integration slice."
        )

    def classify_source_report(
        self,
        *,
        request: XauReactionReportRequest,
        source_report: Any,
    ) -> list[XauReactionRow]:
        """Compute context states and classify source report walls in memory."""

        return classify_source_report_reactions(request=request, source_report=source_report)

    def build_context(
        self,
        *,
        request: XauReactionReportRequest,
        source_report: Any,
    ) -> XauReactionContextBundle:
        """Compute classifier context without creating persisted report artifacts."""

        return build_reaction_context(request=request, source_report=source_report)


def classify_source_report_reactions(
    *,
    request: XauReactionReportRequest,
    source_report: Any,
) -> list[XauReactionRow]:
    """Compute context states and run deterministic wall reaction classification."""

    context_bundle = build_reaction_context(request=request, source_report=source_report)
    walls = list(getattr(source_report, "walls", []) or [])
    zones = list(getattr(source_report, "zones", []) or [])
    return classify_reaction_rows(
        source_report_id=request.source_report_id,
        walls=walls,
        zones=zones,
        context=context_bundle.classifier_context,
    )


def build_reaction_context(
    *,
    request: XauReactionReportRequest,
    source_report: Any,
) -> XauReactionContextBundle:
    """Build computed research context for the classifier from request inputs."""

    freshness_state = (
        classify_freshness(request.freshness_input)
        if request.freshness_input is not None
        else _unknown_freshness()
    )
    vol_regime_state = (
        evaluate_vol_regime(request.vol_regime_input)
        if request.vol_regime_input is not None
        else _unknown_vol_regime()
    )
    open_regime_state = (
        evaluate_open_regime(request.open_regime_input)
        if request.open_regime_input is not None
        else _unknown_open_regime()
    )
    acceptance_states = _acceptance_states(
        request=request,
        source_report=source_report,
    )

    current_price = request.current_price
    session_date = getattr(source_report, "session_date", None)
    expected_range = getattr(source_report, "expected_range", None)
    sigma_position, inside_1sd = _expected_range_context(
        current_price=current_price,
        expected_range=expected_range,
    )

    classifier_context: dict[str, Any] = {
        "freshness_state": freshness_state,
        "vol_regime_state": vol_regime_state,
        "open_regime_state": open_regime_state,
        "acceptance_states": acceptance_states,
        "event_risk_state": request.event_risk_state,
        "current_price": current_price,
        "current_timestamp": request.current_timestamp,
        "session_date": session_date,
        "wall_buffer_points": request.wall_buffer_points,
        "basis_available": _basis_available(source_report),
        "inside_1sd": inside_1sd,
        "sigma_position": sigma_position,
    }
    classifier_context.update(_next_wall_context(getattr(source_report, "walls", []) or []))

    return XauReactionContextBundle(
        freshness_state=freshness_state,
        vol_regime_state=vol_regime_state,
        open_regime_state=open_regime_state,
        acceptance_states=acceptance_states,
        classifier_context=classifier_context,
    )


def _acceptance_states(
    *,
    request: XauReactionReportRequest,
    source_report: Any,
) -> dict[str, XauAcceptanceResult]:
    walls = list(getattr(source_report, "walls", []) or [])
    states: dict[str, XauAcceptanceResult] = {}
    for acceptance_input in request.acceptance_inputs:
        normalized_input = _normalize_acceptance_input(acceptance_input, walls=walls)
        result = classify_acceptance(normalized_input)
        if result.wall_id is not None:
            states[result.wall_id] = result
    return states


def _normalize_acceptance_input(
    input_data: XauAcceptanceInput,
    *,
    walls: list[Any],
) -> XauAcceptanceInput:
    if input_data.wall_id is not None or len(walls) != 1:
        return input_data
    wall_id = getattr(walls[0], "wall_id", None)
    if wall_id is None:
        return input_data
    return input_data.model_copy(update={"wall_id": wall_id})


def _expected_range_context(
    *,
    current_price: float | None,
    expected_range: Any,
) -> tuple[float, bool]:
    if current_price is None or expected_range is None:
        return 0.0, False

    expected_move = _optional_float(getattr(expected_range, "expected_move", None))
    reference_price = _optional_float(getattr(expected_range, "reference_price", None))
    lower_1sd = _optional_float(getattr(expected_range, "lower_1sd", None))
    upper_1sd = _optional_float(getattr(expected_range, "upper_1sd", None))

    sigma_position = 0.0
    if expected_move is not None and expected_move > 0 and reference_price is not None:
        sigma_position = (current_price - reference_price) / expected_move

    inside_1sd = (
        lower_1sd is not None
        and upper_1sd is not None
        and lower_1sd <= current_price <= upper_1sd
    )
    return sigma_position, inside_1sd


def _next_wall_context(walls: list[Any]) -> dict[str, Any]:
    sorted_walls = sorted(
        (
            wall
            for wall in walls
            if _optional_float(getattr(wall, "spot_equivalent_level", None)) is not None
        ),
        key=lambda wall: _optional_float(getattr(wall, "spot_equivalent_level", None)) or 0.0,
    )
    if len(sorted_walls) < 2:
        return {
            "next_wall_reference": "unavailable",
            "next_wall_distance": 0.0,
            "low_oi_gap": False,
        }

    first_level = _optional_float(getattr(sorted_walls[0], "spot_equivalent_level", None))
    second_level = _optional_float(getattr(sorted_walls[1], "spot_equivalent_level", None))
    next_wall_distance = (
        abs(second_level - first_level)
        if first_level is not None and second_level is not None
        else 0.0
    )
    return {
        "next_wall_reference": str(getattr(sorted_walls[1], "wall_id", "unavailable")),
        "next_wall_distance": next_wall_distance,
        "low_oi_gap": False,
    }


def _basis_available(source_report: Any) -> bool:
    basis_snapshot = getattr(source_report, "basis_snapshot", None)
    if basis_snapshot is None:
        return False
    return bool(getattr(basis_snapshot, "mapping_available", False))


def _unknown_freshness() -> XauFreshnessResult:
    return XauFreshnessResult(
        state=XauFreshnessState.UNKNOWN,
        age_minutes=None,
        confidence_label=XauConfidenceLabel.BLOCKED,
        no_trade_reason="Freshness input is unavailable.",
        notes=["Freshness input is unavailable; classifier must block candidate promotion."],
    )


def _unknown_vol_regime() -> XauVolRegimeResult:
    return XauVolRegimeResult(
        realized_volatility=None,
        vrp=None,
        vrp_regime=XauVrpRegime.UNKNOWN,
        iv_edge_state=XauIvEdgeState.UNKNOWN,
        rv_extension_state=XauRvExtensionState.UNKNOWN,
        confidence_label=XauConfidenceLabel.UNKNOWN,
        notes=["Volatility input is unavailable; classifier must block candidate promotion."],
    )


def _unknown_open_regime() -> XauOpenRegimeResult:
    return XauOpenRegimeResult(
        open_side=XauOpenSide.UNKNOWN,
        open_distance_points=None,
        open_flip_state=XauOpenFlipState.UNKNOWN,
        open_as_support_or_resistance=XauOpenSupportResistance.UNKNOWN,
        confidence_label=XauConfidenceLabel.UNKNOWN,
        notes=["Opening-price input is unavailable; classifier must block candidate promotion."],
    )


def _optional_float(value: Any) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None
