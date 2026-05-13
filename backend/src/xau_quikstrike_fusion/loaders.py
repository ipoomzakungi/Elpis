from __future__ import annotations

from src.models.xau_quikstrike_fusion import XauQuikStrikeSourceRef


def load_vol2vol_source_ref(report_id: str) -> XauQuikStrikeSourceRef:
    """Load a sanitized Vol2Vol source report reference.

    Full report loading is implemented in a later 014 slice. This placeholder keeps
    the import surface stable without reading real QuikStrike artifacts yet.
    """
    raise NotImplementedError("Vol2Vol source loading is planned for a later 014 slice.")


def load_matrix_source_ref(report_id: str) -> XauQuikStrikeSourceRef:
    """Load a sanitized Matrix source report reference.

    Full report loading is implemented in a later 014 slice. This placeholder keeps
    the import surface stable without reading real QuikStrike artifacts yet.
    """
    raise NotImplementedError("Matrix source loading is planned for a later 014 slice.")
