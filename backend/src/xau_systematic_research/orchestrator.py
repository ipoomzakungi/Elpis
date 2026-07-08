from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from src.models.xau_market_context import XauPriceBar
from src.models.xau_systematic_research import (
    XauSourceManifest,
    XauSystematicCycleRequest,
    XauSystematicCycleResult,
    XauSystematicPriceProvider,
    XauSystematicReadiness,
    XauSystematicSourceStatus,
)
from src.xau_market_context.latest_artifact import find_latest_price_bars
from src.xau_market_context.price_loader import load_price_bars
from src.xau_market_context.yfinance_provider import fetch_yfinance_bars, save_yfinance_bars
from src.xau_systematic_research.ai_pack_builder import XauAiResearchPackBuilder
from src.xau_systematic_research.alignment_engine import XauSystematicAlignmentEngine
from src.xau_systematic_research.cme_cycle import XauCmeCycle
from src.xau_systematic_research.dukascopy_node_provider import DukascopyNodeProvider
from src.xau_systematic_research.report_store import XauSystematicReportStore, new_cycle_id
from src.xau_systematic_research.source_manifest import build_source_manifest


class XauSystematicResearchOrchestrator:
    def __init__(
        self,
        *,
        reports_dir: Path | None = None,
        import_root: Path | None = None,
        cme_cycle: XauCmeCycle | None = None,
        alignment_engine: XauSystematicAlignmentEngine | None = None,
        pack_builder: XauAiResearchPackBuilder | None = None,
    ) -> None:
        self.reports_dir = reports_dir
        self.import_root = import_root or _default_import_root()
        self.cme_cycle = cme_cycle or XauCmeCycle(reports_dir=reports_dir)
        self.alignment_engine = alignment_engine or XauSystematicAlignmentEngine()
        self.pack_builder = pack_builder or XauAiResearchPackBuilder()

    def run(self, request: XauSystematicCycleRequest) -> XauSystematicCycleResult:
        created_at = datetime.now(UTC)
        cycle_id = new_cycle_id(label=request.cycle_label, created_at=created_at)
        cme_result = self.cme_cycle.run(request)
        bars, bars_path, price_warnings = self._resolve_price_bars(request)
        current_timestamp = bars[-1].timestamp if bars else datetime.now(ZoneInfo(request.timezone))
        state = self.alignment_engine.align(
            request=request,
            cycle_id=cycle_id,
            created_at=created_at,
            fusion_report=cme_result.fusion_report,
            fusion_report_path=cme_result.fusion_report_path,
            price_bars=bars,
            bars_path=bars_path,
            current_timestamp=current_timestamp,
            cme_partial=cme_result.partial,
        )
        manifest = build_source_manifest(
            state,
            cme_partial=cme_result.partial,
            warnings=[*cme_result.warnings, *price_warnings],
            ai_pack_status=XauSystematicSourceStatus.AVAILABLE,
        )
        pack, markdown, handoff = self.pack_builder.build(state=state, manifest=manifest)
        store = XauSystematicReportStore(reports_dir=request.output_root or self.reports_dir)
        artifacts = store.persist_cycle(
            cycle_id=cycle_id,
            request=request,
            manifest=manifest,
            aligned_state=state,
            ai_pack=pack,
            ai_pack_markdown=markdown,
            ai_handoff_context=handoff,
            overwrite=request.overwrite,
        )
        return XauSystematicCycleResult(
            cycle_id=cycle_id,
            output_dir=store.cycle_dir(cycle_id),
            readiness=_readiness_from_manifest_state(manifest, state),
            source_manifest=manifest,
            aligned_state=state,
            ai_pack=pack,
            artifacts=artifacts,
        )

    def _resolve_price_bars(
        self,
        request: XauSystematicCycleRequest,
    ) -> tuple[list[XauPriceBar], Path | None, list[str]]:
        if request.price_provider == XauSystematicPriceProvider.LOCAL_BARS:
            if request.price_bars_path is None:
                return [], None, ["local_bars provider requires price_bars_path."]
            return _load_bars(request.price_bars_path, request)

        if request.price_provider == XauSystematicPriceProvider.LATEST_LOCAL_IMPORT:
            path = find_latest_price_bars(self.import_root, symbol_hint=request.traded_symbol)
            if path is None:
                return [], None, ["No latest local XAU price import was found."]
            return _load_bars(path, request)

        if request.price_provider == XauSystematicPriceProvider.DUKASCOPY_NODE:
            session_date = request.session_date or datetime.now(
                ZoneInfo(request.timezone)
            ).date()
            result = DukascopyNodeProvider(import_root=self.import_root).fetch(
                command_template=request.dukascopy_node_command_template,
                session_date=session_date,
                symbol=request.dukascopy_symbol,
                timeframe=request.dukascopy_timeframe,
                from_time=request.dukascopy_from,
                to_time=request.dukascopy_to,
            )
            if (
                result.bars_path is None
                or result.provider_status != XauSystematicSourceStatus.AVAILABLE
            ):
                return [], result.bars_path, result.warnings
            bars, _, warnings = _load_bars(result.bars_path, request)
            return bars, result.bars_path, [*result.warnings, *warnings]

        if request.price_provider == XauSystematicPriceProvider.YFINANCE:
            bars = fetch_yfinance_bars(
                symbol=request.spot_symbol,
                interval="1m",
                period="1d",
                timezone=request.timezone,
            )
            output = save_yfinance_bars(
                bars=bars,
                output_dir=self.import_root / "yfinance",
                symbol=request.spot_symbol,
                interval="1m",
            )
            warnings = ["yfinance is research fallback only and not execution-grade."]
            return bars, output, warnings

        return [], None, ["manual price provider does not supply traded bars in this feature."]


def _load_bars(
    path: Path,
    request: XauSystematicCycleRequest,
) -> tuple[list[XauPriceBar], Path | None, list[str]]:
    try:
        bars = load_price_bars(
            path,
            default_symbol=request.traded_symbol,
            default_timeframe="1m",
            default_timezone=request.timezone,
        )
    except (OSError, ValueError) as exc:
        return [], path, [f"Could not load price bars: {exc}"]
    return bars, path, []


def _readiness_from_manifest_state(
    manifest: XauSourceManifest,
    state,
) -> XauSystematicReadiness:
    if state.readiness.blocked:
        return XauSystematicReadiness.BLOCKED
    if state.readiness.ready_for_shadow_review:
        return XauSystematicReadiness.READY_FOR_SHADOW_REVIEW
    if manifest.fusion_status == XauSystematicSourceStatus.UNAVAILABLE:
        return XauSystematicReadiness.BLOCKED
    return XauSystematicReadiness.PARTIAL


def _default_import_root() -> Path:
    return Path(__file__).resolve().parents[2] / "data" / "imports"
