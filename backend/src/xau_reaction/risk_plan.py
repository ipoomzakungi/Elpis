from collections.abc import Mapping, Sequence
from typing import Any

from src.models.xau_reaction import XauReactionRow, XauRiskPlan


class XauRiskPlannerNotImplementedError(RuntimeError):
    """Raised when bounded risk-planner behavior is requested before its slice exists."""


def plan_bounded_research_risk(
    *,
    reactions: Sequence[XauReactionRow],
    risk_config: Mapping[str, Any] | None = None,
) -> list[XauRiskPlan]:
    """Return bounded risk-plan rows after later risk-planner tasks implement behavior.

    This setup slice intentionally emits no risk plans and performs no execution-related work.
    """

    return []
