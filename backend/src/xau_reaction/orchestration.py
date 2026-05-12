from src.models.xau_reaction import XauReactionReport, XauReactionReportRequest


class XauReactionReportNotImplementedError(RuntimeError):
    """Raised until reaction report orchestration is implemented in a later slice."""


class XauReactionReportOrchestrator:
    """Placeholder orchestration boundary for feature 010 reaction reports."""

    def run(self, request: XauReactionReportRequest) -> XauReactionReport:
        raise XauReactionReportNotImplementedError(
            "XAU reaction report orchestration is not implemented in this foundation slice."
        )
