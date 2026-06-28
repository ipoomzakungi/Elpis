from fastapi import APIRouter, Depends

from src.models.xau_data_capability_audit import (
    XauDataCapabilityAuditRequest,
    XauDataCapabilityAuditResult,
)
from src.xau_data_capability_audit.service import XauDataCapabilityAuditService

router = APIRouter()


def get_xau_data_capability_audit_service() -> XauDataCapabilityAuditService:
    return XauDataCapabilityAuditService()


@router.post(
    "/research/xau/data-capability-audit/run",
    response_model=XauDataCapabilityAuditResult,
)
async def run_xau_data_capability_audit(
    request: XauDataCapabilityAuditRequest,
    service: XauDataCapabilityAuditService = Depends(
        get_xau_data_capability_audit_service
    ),
) -> XauDataCapabilityAuditResult:
    """Run a read-only local audit of XAU CME/QuikStrike data capabilities."""

    return service.run(request)
