from fastapi import APIRouter, Query

from src.models.data_quality import DataQualityResponse
from src.services.data_quality import DataQualityService

router = APIRouter()


@router.get("/data-quality", response_model=DataQualityResponse)
async def get_data_quality(
    symbol: str = Query(default="BTCUSDT"),
):
    """Get data quality metrics for all data types."""
    service = DataQualityService()
    result = service.check_data_quality(symbol=symbol)
    return DataQualityResponse(**result)
