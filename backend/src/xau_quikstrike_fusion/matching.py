from __future__ import annotations

from src.models.xau_quikstrike_fusion import XauFusionMatchKey


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
        value_type=value_type,
    )


def match_source_rows() -> None:
    """Placeholder for source-row coverage and mismatch calculation."""
    raise NotImplementedError("Source-row matching is planned for a later 014 slice.")
