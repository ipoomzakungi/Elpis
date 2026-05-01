"""XAU OI wall scoring skeleton.

Wall scoring is intentionally not implemented in this slice.
"""

from src.models.xau import XauOptionsOiRow


def wall_scoring_inputs_available(rows: list[XauOptionsOiRow]) -> bool:
    """Return whether normalized rows exist for a future wall-scoring phase."""

    return bool(rows)
