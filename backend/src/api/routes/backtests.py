import logging

from fastapi import APIRouter, HTTPException, Query

from src.api.validation import backtest_not_found, invalid_backtest_config, processed_features_not_found
from src.backtest.engine import BacktestEngine, BacktestFeatureNotFoundError
from src.backtest.report_store import ReportStore, ReportStoreError
from src.models.backtest import (
    BacktestEquityResponse,
    BacktestMetricsResponse,
    BacktestRun,
    BacktestRunListResponse,
    BacktestRunRequest,
    BacktestRunResponse,
    BacktestTradesResponse,
    PaginationMeta,
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
