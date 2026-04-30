import logging

from fastapi import APIRouter, HTTPException, Query

from src.api.validation import (
    backtest_not_found,
    invalid_backtest_config,
    invalid_validation_config,
    processed_features_not_found,
    validation_not_implemented,
    validation_processed_features_not_found,
    validation_report_not_found,
)
from src.backtest.engine import BacktestEngine, BacktestFeatureNotFoundError
from src.backtest.report_store import ReportStore, ReportStoreError
from src.backtest.validation import ValidationExecutionNotImplementedError, ValidationReportService
from src.models.backtest import (
    BacktestEquityResponse,
    BacktestMetricsResponse,
    BacktestRun,
    BacktestRunListResponse,
    BacktestRunRequest,
    BacktestRunResponse,
    BacktestTradesResponse,
    PaginationMeta,
    ValidationConcentrationResponse,
    ValidationRun,
    ValidationRunListResponse,
    ValidationRunRequest,
    ValidationSensitivityResponse,
    ValidationStressResponse,
    ValidationWalkForwardResponse,
)

router = APIRouter()
logger = logging.getLogger(__name__)


@router.post("/backtests/run", response_model=BacktestRunResponse)
async def run_backtest(request: BacktestRunRequest) -> BacktestRunResponse:
    """Run a synchronous local v0 research backtest."""
    try:
        return BacktestEngine().run(request)
    except BacktestFeatureNotFoundError as exc:
        processed_features_not_found(
            symbol=exc.symbol,
            timeframe=exc.timeframe,
            feature_path=exc.feature_path.as_posix(),
        )
    except ValueError as exc:
        invalid_backtest_config(str(exc))
    except HTTPException:
        raise
    except Exception as exc:
        logger.exception("Backtest run failed for %s %s", request.symbol, request.timeframe)
        raise HTTPException(status_code=500, detail="Backtest run failed") from exc

    raise HTTPException(status_code=500, detail="Backtest run failed")


@router.get("/backtests", response_model=BacktestRunListResponse)
async def list_backtests() -> BacktestRunListResponse:
    """List saved local research backtest runs."""
    return BacktestRunListResponse(runs=ReportStore().list_run_summaries())


@router.post("/backtests/validation/run", response_model=ValidationRun)
async def run_validation_report(request: ValidationRunRequest) -> ValidationRun:
    """Run a synchronous local research validation report."""
    try:
        return ValidationReportService().run(request)
    except BacktestFeatureNotFoundError as exc:
        validation_processed_features_not_found(
            symbol=exc.symbol,
            timeframe=exc.timeframe,
            feature_path=exc.feature_path.as_posix(),
        )
    except ValidationExecutionNotImplementedError:
        validation_not_implemented()
    except ValueError as exc:
        invalid_validation_config(str(exc))

    raise HTTPException(status_code=500, detail="Validation report run failed")


@router.get("/backtests/validation", response_model=ValidationRunListResponse)
async def list_validation_reports() -> ValidationRunListResponse:
    """List saved local research validation reports."""
    return ValidationReportService().list_runs()


@router.get("/backtests/validation/{validation_run_id}", response_model=ValidationRun)
async def get_validation_report(validation_run_id: str) -> ValidationRun:
    """Return saved validation report metadata and sections."""
    try:
        return ValidationReportService().read_run(validation_run_id)
    except (FileNotFoundError, ReportStoreError):
        validation_report_not_found(validation_run_id)

    raise HTTPException(status_code=500, detail="Validation report read failed")


@router.get(
    "/backtests/validation/{validation_run_id}/stress", response_model=ValidationStressResponse
)
async def get_validation_stress(validation_run_id: str) -> ValidationStressResponse:
    """Return saved validation stress rows."""
    try:
        return ValidationReportService().read_stress_results(validation_run_id)
    except (FileNotFoundError, ReportStoreError):
        validation_report_not_found(validation_run_id)

    raise HTTPException(status_code=500, detail="Validation stress read failed")


@router.get(
    "/backtests/validation/{validation_run_id}/sensitivity",
    response_model=ValidationSensitivityResponse,
)
async def get_validation_sensitivity(validation_run_id: str) -> ValidationSensitivityResponse:
    """Return saved validation sensitivity rows."""
    try:
        return ValidationReportService().read_sensitivity_results(validation_run_id)
    except (FileNotFoundError, ReportStoreError):
        validation_report_not_found(validation_run_id)

    raise HTTPException(status_code=500, detail="Validation sensitivity read failed")


@router.get(
    "/backtests/validation/{validation_run_id}/walk-forward",
    response_model=ValidationWalkForwardResponse,
)
async def get_validation_walk_forward(validation_run_id: str) -> ValidationWalkForwardResponse:
    """Return saved validation walk-forward rows."""
    try:
        return ValidationReportService().read_walk_forward_results(validation_run_id)
    except (FileNotFoundError, ReportStoreError):
        validation_report_not_found(validation_run_id)

    raise HTTPException(status_code=500, detail="Validation walk-forward read failed")


@router.get(
    "/backtests/validation/{validation_run_id}/concentration",
    response_model=ValidationConcentrationResponse,
)
async def get_validation_concentration(validation_run_id: str) -> ValidationConcentrationResponse:
    """Return saved validation regime coverage and concentration sections."""
    try:
        return ValidationReportService().read_concentration_results(validation_run_id)
    except (FileNotFoundError, ReportStoreError):
        validation_report_not_found(validation_run_id)

    raise HTTPException(status_code=500, detail="Validation concentration read failed")


@router.get("/backtests/{run_id}", response_model=BacktestRun)
async def get_backtest_run(run_id: str) -> BacktestRun:
    """Return saved backtest run metadata and artifact references."""
    try:
        return ReportStore().read_run(run_id)
    except (FileNotFoundError, ReportStoreError):
        backtest_not_found(run_id)

    raise HTTPException(status_code=500, detail="Backtest report read failed")


@router.get("/backtests/{run_id}/trades", response_model=BacktestTradesResponse)
async def get_backtest_trades(
    run_id: str,
    limit: int = Query(default=500, ge=1, le=5000),
    offset: int = Query(default=0, ge=0),
) -> BacktestTradesResponse:
    """Return paginated saved trade log rows for a backtest run."""
    try:
        trades, count = ReportStore().read_trades_log(run_id, limit=limit, offset=offset)
        return BacktestTradesResponse(
            data=trades,
            meta=PaginationMeta(count=count, limit=limit, offset=offset),
        )
    except (FileNotFoundError, ReportStoreError):
        backtest_not_found(run_id)

    raise HTTPException(status_code=500, detail="Backtest trades read failed")


@router.get("/backtests/{run_id}/metrics", response_model=BacktestMetricsResponse)
async def get_backtest_metrics(run_id: str) -> BacktestMetricsResponse:
    """Return saved summary metrics and comparison tables for a backtest run."""
    try:
        metrics = ReportStore().read_metrics_summary(run_id)
        return BacktestMetricsResponse(
            run_id=run_id,
            summary=metrics,
            return_by_regime=_grouped_dict_to_rows(metrics.return_by_regime, "regime"),
            return_by_strategy_mode=_grouped_dict_to_rows(
                metrics.return_by_strategy_mode,
                "strategy_mode",
            ),
            return_by_symbol_provider=_grouped_dict_to_rows(
                metrics.return_by_symbol_provider,
                "symbol_provider",
            ),
            baseline_comparison=metrics.baseline_comparison,
            notes=metrics.notes,
        )
    except (FileNotFoundError, ReportStoreError):
        backtest_not_found(run_id)

    raise HTTPException(status_code=500, detail="Backtest metrics read failed")


@router.get("/backtests/{run_id}/equity", response_model=BacktestEquityResponse)
async def get_backtest_equity(run_id: str) -> BacktestEquityResponse:
    """Return saved equity and drawdown curve points for a backtest run."""
    try:
        equity = ReportStore().read_equity_curve(run_id)
        return BacktestEquityResponse(
            run_id=run_id,
            data=equity,
            meta={"count": len(equity)},
        )
    except (FileNotFoundError, ReportStoreError):
        backtest_not_found(run_id)

    raise HTTPException(status_code=500, detail="Backtest equity read failed")


def _grouped_dict_to_rows(grouped: dict, key_name: str) -> list[dict]:
    return [{key_name: key, **value} for key, value in grouped.items()]
