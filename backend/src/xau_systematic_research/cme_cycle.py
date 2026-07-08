from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from src.models.xau_quikstrike_fusion import (
    XauFusionReportStatus,
    XauQuikStrikeFusionReport,
    XauQuikStrikeFusionRequest,
)
from src.models.xau_systematic_research import (
    XauSystematicCmeSourceMode,
    XauSystematicCycleRequest,
)
from src.xau_quikstrike_fusion.orchestration import create_xau_quikstrike_fusion_report
from src.xau_quikstrike_fusion.report_store import XauQuikStrikeFusionReportStore


@dataclass(frozen=True)
class XauCmeCycleResult:
    fusion_report: XauQuikStrikeFusionReport | None
    fusion_report_path: Path | None
    partial: bool = False
    warnings: list[str] = field(default_factory=list)


class XauCmeCycle:
    def __init__(self, *, reports_dir: Path | None = None) -> None:
        self.store = XauQuikStrikeFusionReportStore(reports_dir=reports_dir)

    def run(self, request: XauSystematicCycleRequest) -> XauCmeCycleResult:
        if request.fusion_report_id:
            return self._read_existing(request.fusion_report_id)
        if (
            request.cme_source_mode == XauSystematicCmeSourceMode.LATEST_EXISTING
            and request.use_latest_fusion
        ):
            return self._latest_existing()
        if request.cme_source_mode == XauSystematicCmeSourceMode.SUPPLIED_REPORTS:
            return self._supplied_reports(request)
        if request.cme_source_mode in {
            XauSystematicCmeSourceMode.API_ONLY,
            XauSystematicCmeSourceMode.BROWSER_CDP,
        }:
            latest = self._latest_existing()
            if latest.fusion_report is not None:
                return XauCmeCycleResult(
                    fusion_report=latest.fusion_report,
                    fusion_report_path=latest.fusion_report_path,
                    partial=True,
                    warnings=[
                        (
                            f"{request.cme_source_mode.value} fetch path is not directly "
                            "available in this local orchestrator; reused latest fusion report."
                        ),
                        *latest.warnings,
                    ],
                )
            return XauCmeCycleResult(
                fusion_report=None,
                fusion_report_path=None,
                partial=True,
                warnings=[
                    (
                        f"{request.cme_source_mode.value} did not produce a local fusion "
                        "report. Run the existing QuikStrike extraction first or supply reports."
                    )
                ],
            )
        return XauCmeCycleResult(
            fusion_report=None,
            fusion_report_path=None,
            partial=True,
            warnings=[f"Unsupported CME source mode: {request.cme_source_mode.value}"],
        )

    def _read_existing(self, report_id: str) -> XauCmeCycleResult:
        try:
            report = self.store.read_report(report_id)
        except FileNotFoundError:
            return XauCmeCycleResult(
                fusion_report=None,
                fusion_report_path=None,
                partial=True,
                warnings=[f"Fusion report {report_id} was not found."],
            )
        return XauCmeCycleResult(
            fusion_report=report,
            fusion_report_path=self.store.report_dir(report.report_id),
            partial=report.status != XauFusionReportStatus.COMPLETED,
        )

    def _latest_existing(self) -> XauCmeCycleResult:
        summaries = self.store.list_reports().reports
        if not summaries:
            return XauCmeCycleResult(
                fusion_report=None,
                fusion_report_path=None,
                partial=True,
                warnings=["No existing XAU QuikStrike fusion report was found."],
            )
        return self._read_existing(summaries[0].report_id)

    def _supplied_reports(self, request: XauSystematicCycleRequest) -> XauCmeCycleResult:
        if not request.vol2vol_report_id or not request.matrix_report_id:
            return XauCmeCycleResult(
                fusion_report=None,
                fusion_report_path=None,
                partial=True,
                warnings=["supplied_reports requires vol2vol_report_id and matrix_report_id."],
            )
        try:
            fusion = create_xau_quikstrike_fusion_report(
                XauQuikStrikeFusionRequest(
                    vol2vol_report_id=request.vol2vol_report_id,
                    matrix_report_id=request.matrix_report_id,
                    create_xau_vol_oi_report=True,
                    create_xau_reaction_report=True,
                    run_label=request.cycle_label,
                    persist_report=True,
                    research_only_acknowledged=True,
                ),
                report_store=self.store,
            )
        except Exception as exc:  # pragma: no cover - operational safety boundary
            return XauCmeCycleResult(
                fusion_report=None,
                fusion_report_path=None,
                partial=True,
                warnings=[f"Supplied CME report fusion failed: {exc}"],
            )
        return XauCmeCycleResult(
            fusion_report=fusion,
            fusion_report_path=self.store.report_dir(fusion.report_id),
            partial=fusion.status != XauFusionReportStatus.COMPLETED,
        )
