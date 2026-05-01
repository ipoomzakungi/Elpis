"""XAU research zone classification skeleton.

Zone classification is intentionally not implemented in this slice.
"""

from src.models.xau import XauOiWall


def zone_classification_inputs_available(walls: list[XauOiWall]) -> bool:
    """Return whether wall rows exist for a future zone-classification phase."""

    return bool(walls)
