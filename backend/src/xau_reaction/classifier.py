from collections.abc import Mapping, Sequence
from typing import Any

from src.models.xau_reaction import XauReactionRow


class XauReactionClassifierNotImplementedError(RuntimeError):
    """Raised when classifier behavior is requested before the classifier slice exists."""


def classify_reaction_rows(
    *,
    source_report_id: str,
    walls: Sequence[Any],
    zones: Sequence[Any],
    context: Mapping[str, Any] | None = None,
) -> list[XauReactionRow]:
    """Return reaction rows after later classifier tasks implement deterministic labels.

    This setup slice intentionally does not classify reaction labels. OI walls remain
    research zones until the classifier user-story tasks add deterministic rules.
    """

    return []
