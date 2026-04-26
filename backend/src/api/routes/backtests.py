import logging

from fastapi import APIRouter, HTTPException

from src.api.validation import invalid_backtest_config, processed_features_not_found
from src.backtest.engine import BacktestEngine, BacktestFeatureNotFoundError
from src.models.backtest import BacktestRunRequest, BacktestRunResponse

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
