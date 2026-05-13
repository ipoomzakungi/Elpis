from __future__ import annotations

from dataclasses import dataclass

from src.models.xau_quikstrike_fusion import (
    XauFusionAgreementStatus,
    XauFusionCoverageSummary,
    XauFusionMatchKey,
    XauFusionMatchStatus,
    XauFusionSourceType,
    XauFusionSourceValue,
)


@dataclass(frozen=True)
class MatchedSourcePair:
    match_key: XauFusionMatchKey
    match_status: XauFusionMatchStatus
    vol2vol_values: tuple[XauFusionSourceValue, ...] = ()
    matrix_values: tuple[XauFusionSourceValue, ...] = ()
    warnings: tuple[str, ...] = ()

    @property
    def vol2vol_value(self) -> XauFusionSourceValue | None:
        return self.vol2vol_values[0] if self.vol2vol_values else None

    @property
    def matrix_value(self) -> XauFusionSourceValue | None:
        return self.matrix_values[0] if self.matrix_values else None


@dataclass(frozen=True)
class FusionMatchResult:
    pairs: list[MatchedSourcePair]
    coverage: XauFusionCoverageSummary
    blocked_reasons: list[str]


def build_match_key(
    *,
    strike: float,
    option_type: str,
    value_type: str,
    expiration: str | None = None,
    expiration_code: str | None = None,
) -> XauFusionMatchKey:
    """Build a normalized fusion match key from sanitized source row fields."""
    return XauFusionMatchKey(
        strike=strike,
        expiration=expiration,
        expiration_code=expiration_code,
        option_type=option_type,
        value_type=normalize_value_type(value_type),
    )


def build_match_key_from_source(value: XauFusionSourceValue) -> XauFusionMatchKey:
    if value.strike is None:
        raise ValueError("source value is missing strike")
    if value.option_type is None:
        raise ValueError("source value is missing option_type")
    return build_match_key(
        strike=value.strike,
        expiration=value.expiration,
        expiration_code=value.expiration_code,
        option_type=value.option_type,
        value_type=value.value_type,
    )


def normalize_value_type(value_type: str) -> str:
    normalized = value_type.strip().lower()
    if normalized == "eod_volume":
        return "volume"
    if normalized == "volume_matrix":
        return "volume"
    return normalized


def match_source_rows(
    vol2vol_values: list[XauFusionSourceValue],
    matrix_values: list[XauFusionSourceValue],
) -> FusionMatchResult:
    """Match normalized source values by deterministic fusion key."""

    vol2vol_index, vol2vol_blocked = _index_values(vol2vol_values, XauFusionSourceType.VOL2VOL)
    matrix_index, matrix_blocked = _index_values(matrix_values, XauFusionSourceType.MATRIX)
    pairs: list[MatchedSourcePair] = []

    for key in sorted(set(vol2vol_index) | set(matrix_index)):
        vol_values = tuple(vol2vol_index.get(key, []))
        matrix_values_for_key = tuple(matrix_index.get(key, []))
        warnings: list[str] = []
        if len(vol_values) > 1:
            warnings.append("Duplicate Vol2Vol source rows share the same fusion key.")
        if len(matrix_values_for_key) > 1:
            warnings.append("Duplicate Matrix source rows share the same fusion key.")

        if warnings:
            status = XauFusionMatchStatus.CONFLICT
        elif vol_values and matrix_values_for_key:
            status = XauFusionMatchStatus.MATCHED
        elif vol_values:
            status = XauFusionMatchStatus.VOL2VOL_ONLY
        else:
            status = XauFusionMatchStatus.MATRIX_ONLY

        sample_value = (vol_values or matrix_values_for_key)[0]
        pairs.append(
            MatchedSourcePair(
                match_key=build_match_key_from_source(sample_value),
                match_status=status,
                vol2vol_values=vol_values,
                matrix_values=matrix_values_for_key,
                warnings=tuple(warnings),
            )
        )

    blocked_reasons = [*vol2vol_blocked, *matrix_blocked]
    return FusionMatchResult(
        pairs=pairs,
        coverage=calculate_coverage_summary(pairs, blocked_key_count=len(blocked_reasons)),
        blocked_reasons=blocked_reasons,
    )


def calculate_coverage_summary(
    pairs: list[MatchedSourcePair],
    *,
    blocked_key_count: int = 0,
) -> XauFusionCoverageSummary:
    return XauFusionCoverageSummary(
        matched_key_count=sum(
            pair.match_status == XauFusionMatchStatus.MATCHED for pair in pairs
        ),
        vol2vol_only_key_count=sum(
            pair.match_status == XauFusionMatchStatus.VOL2VOL_ONLY for pair in pairs
        ),
        matrix_only_key_count=sum(
            pair.match_status == XauFusionMatchStatus.MATRIX_ONLY for pair in pairs
        ),
        conflict_key_count=sum(
            pair.match_status == XauFusionMatchStatus.CONFLICT for pair in pairs
        ),
        blocked_key_count=blocked_key_count,
        strike_count=len({pair.match_key.strike for pair in pairs}),
        expiration_count=len({pair.match_key.expiration_key for pair in pairs}),
        option_type_count=len({pair.match_key.option_type for pair in pairs}),
        value_type_count=len({pair.match_key.value_type for pair in pairs}),
    )


def evaluate_source_agreement(
    vol2vol_value: XauFusionSourceValue | None,
    matrix_value: XauFusionSourceValue | None,
    *,
    tolerance: float = 0.0,
) -> tuple[XauFusionAgreementStatus, list[str]]:
    if vol2vol_value is None or matrix_value is None:
        return XauFusionAgreementStatus.UNAVAILABLE, ["Only one source has this fusion key."]
    if vol2vol_value.value is None or matrix_value.value is None:
        return (
            XauFusionAgreementStatus.UNAVAILABLE,
            ["At least one source value is unavailable for comparison."],
        )
    if normalize_value_type(vol2vol_value.value_type) != normalize_value_type(
        matrix_value.value_type
    ):
        return (
            XauFusionAgreementStatus.NOT_COMPARABLE,
            ["Source values have different value types and were not compared."],
        )
    if abs(vol2vol_value.value - matrix_value.value) <= tolerance:
        return (
            XauFusionAgreementStatus.AGREEMENT,
            [f"Comparable {normalize_value_type(vol2vol_value.value_type)} values agree."],
        )
    return (
        XauFusionAgreementStatus.DISAGREEMENT,
        [
            (
                f"Comparable {normalize_value_type(vol2vol_value.value_type)} values differ: "
                f"Vol2Vol={vol2vol_value.value}, Matrix={matrix_value.value}."
            )
        ],
    )


def _index_values(
    values: list[XauFusionSourceValue],
    source_type: XauFusionSourceType,
) -> tuple[dict[tuple[float, str, str, str], list[XauFusionSourceValue]], list[str]]:
    indexed: dict[tuple[float, str, str, str], list[XauFusionSourceValue]] = {}
    blocked: list[str] = []
    for value in values:
        try:
            match_key = build_match_key_from_source(value)
        except ValueError as exc:
            blocked.append(
                f"{source_type.value} row {value.source_row_id or '<unknown>'} blocked: {exc}"
            )
            continue
        indexed.setdefault(_key_tuple(match_key), []).append(value)
    return indexed, blocked


def _key_tuple(match_key: XauFusionMatchKey) -> tuple[float, str, str, str]:
    return (
        round(match_key.strike, 8),
        (match_key.expiration_key or "").lower(),
        match_key.option_type.lower(),
        match_key.value_type.lower(),
    )
