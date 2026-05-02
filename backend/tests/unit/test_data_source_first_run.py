from datetime import datetime

from src.data_sources.first_run import (
    FirstEvidenceRunOrchestrator,
    build_research_execution_request,
)
from src.data_sources.preflight import DataSourcePreflightService
from src.data_sources.report_store import DataSourceFirstRunReportStore
from src.models.data_sources import FirstEvidenceRunRequest
from src.models.research_execution import (
    ResearchEvidenceDecision,
    ResearchEvidenceSummary,
    ResearchExecutionRun,
    ResearchExecutionRunRequest,
    ResearchExecutionWorkflowStatus,
)
from tests.helpers.research_data import write_synthetic_research_features


def test_first_evidence_request_normalizes_report_ids_and_requires_ack():
    request = FirstEvidenceRunRequest.model_validate(
        {
            "name": "  Evidence smoke  ",
            "research_only_acknowledged": True,
            "use_existing_research_report_ids": [
                " report_alpha ",
                "report_alpha",
                "",
                "report_beta",
            ],
            "use_existing_xau_report_id": " xau_report_1 ",
            "preflight": {"research_only_acknowledged": True},
        }
    )

    assert request.name == "Evidence smoke"
    assert request.use_existing_research_report_ids == ["report_alpha", "report_beta"]
    assert request.use_existing_xau_report_id == "xau_report_1"


def test_first_evidence_request_rejects_unsafe_report_ids():
    payload = {
        "research_only_acknowledged": True,
        "use_existing_research_report_ids": ["../outside"],
        "preflight": {"research_only_acknowledged": True},
    }

    try:
        FirstEvidenceRunRequest.model_validate(payload)
    except ValueError as exc:
        assert "safe report id" in str(exc)
    else:  # pragma: no cover - defensive assertion
        raise AssertionError("unsafe report id was accepted")


def test_preflight_maps_to_research_execution_request_without_dropping_blocked_assets(
    isolated_data_paths,
):
    processed_root = isolated_data_paths / "processed"
    write_synthetic_research_features(
        processed_root / "btcusdt_15m_features.parquet",
        symbol="BTCUSDT",
        rows=10,
    )
    write_synthetic_research_features(
        processed_root / "spy_1d_features.parquet",
        symbol="SPY",
        rows=8,
        include_regime=False,
        include_open_interest=False,
        include_funding=False,
    )
    request = FirstEvidenceRunRequest.model_validate(
        {
            "name": "mapping test",
            "research_only_acknowledged": True,
            "use_existing_research_report_ids": ["research_existing"],
            "use_existing_xau_report_id": "xau_existing",
            "preflight": {
                "crypto_assets": ["BTCUSDT", "ETHUSDT"],
                "optional_crypto_assets": ["SOLUSDT"],
                "proxy_assets": ["SPY"],
                "processed_feature_root": str(processed_root),
                "requested_capabilities": ["ohlcv", "open_interest", "funding", "iv"],
                "research_only_acknowledged": True,
            },
        }
    )
    preflight = DataSourcePreflightService().run(request.preflight, environ={})

    execution_request = build_research_execution_request(request, preflight)

    assert execution_request.research_only_acknowledged is True
    assert execution_request.reference_report_ids == ["research_existing"]
    assert execution_request.crypto is not None
    assert execution_request.crypto.primary_assets == ["BTCUSDT", "ETHUSDT"]
    assert execution_request.crypto.optional_assets == ["SOLUSDT"]
    assert execution_request.crypto.processed_feature_root == processed_root
    assert execution_request.proxy is not None
    assert execution_request.proxy.assets == ["SPY"]
    assert execution_request.proxy.required_capabilities == [
        "ohlcv",
        "open_interest",
        "funding",
        "iv",
    ]
    assert execution_request.xau is not None
    assert execution_request.xau.existing_xau_report_id == "xau_existing"


def test_first_evidence_orchestrator_delegates_and_persists_wrapper(isolated_data_paths):
    processed_root = isolated_data_paths / "processed"
    write_synthetic_research_features(
        processed_root / "btcusdt_15m_features.parquet",
        symbol="BTCUSDT",
        rows=10,
    )
    fake_executor = _FakeResearchExecutionOrchestrator()
    store = DataSourceFirstRunReportStore(reports_root=isolated_data_paths / "reports")
    orchestrator = FirstEvidenceRunOrchestrator(
        research_execution_orchestrator=fake_executor,
        report_store=store,
    )
    request = FirstEvidenceRunRequest.model_validate(
        {
            "name": "delegate test",
            "research_only_acknowledged": True,
            "preflight": {
                "crypto_assets": ["BTCUSDT", "ETHUSDT"],
                "proxy_assets": [],
                "processed_feature_root": str(processed_root),
                "xau_options_oi_file_path": str(
                    isolated_data_paths / "raw" / "xau" / "missing.csv"
                ),
                "research_only_acknowledged": True,
            },
        }
    )

    result = orchestrator.run(request)

    assert fake_executor.captured_request is not None
    assert result.execution_run_id == "rex_fake_evidence"
    assert result.decision == "refine"
    assert result.status == "partial"
    assert result.evidence_report_path.endswith("/evidence.json")
    assert any(action.asset == "ETHUSDT" for action in result.missing_data_actions)

    loaded = store.read_first_run(result.first_run_id)
    assert loaded.first_run_id == result.first_run_id
    assert loaded.execution_run_id == "rex_fake_evidence"


class _FakeResearchExecutionOrchestrator:
    def __init__(self) -> None:
        self.captured_request: ResearchExecutionRunRequest | None = None

    def run(self, request: ResearchExecutionRunRequest) -> ResearchExecutionRun:
        self.captured_request = request
        created_at = datetime.utcnow()
        evidence = ResearchEvidenceSummary(
            execution_run_id="rex_fake_evidence",
            status=ResearchExecutionWorkflowStatus.PARTIAL,
            decision=ResearchEvidenceDecision.REFINE,
            workflow_results=[],
            missing_data_checklist=["ETHUSDT processed features are missing."],
            limitations=["Synthetic fixtures are test-only."],
            research_only_warnings=[
                "Evidence labels are research decisions only, not trading approvals."
            ],
            created_at=created_at,
        )
        return ResearchExecutionRun(
            execution_run_id="rex_fake_evidence",
            name=request.name,
            normalized_config=request,
            preflight_results=[],
            evidence_summary=evidence,
            artifact_paths={"evidence": "data/reports/research_execution/rex/evidence.json"},
            created_at=created_at,
            updated_at=created_at,
        )
