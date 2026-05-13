"""Local browser adapter boundary for future user-controlled Matrix extraction.

This module intentionally does not connect to a browser, replay endpoints, or persist
session material. It validates sanitized shape inputs for later local integration.
"""

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from src.models.quikstrike_matrix import ensure_no_forbidden_quikstrike_matrix_content

SUPPORTED_MATRIX_SURFACE = "OPEN INTEREST"
SUPPORTED_MATRIX_PRODUCT_CODE = "OG|GC"


class QuikStrikeMatrixLocalBrowserNotImplementedError(RuntimeError):
    """Raised when real browser extraction is requested in the skeleton slice."""


@dataclass(frozen=True)
class QuikStrikeMatrixLocalBrowserReadiness:
    ready: bool
    status: str
    message: str
    limitations: list[str]


class QuikStrikeMatrixLocalBrowserAdapter:
    """Safe placeholder adapter for a manually controlled local browser session."""

    def __init__(self, sanitized_context: Mapping[str, Any] | None = None) -> None:
        if sanitized_context is not None:
            validate_sanitized_browser_context(sanitized_context)
        self.sanitized_context = dict(sanitized_context or {})

    def readiness(
        self,
        *,
        surface: str | None = None,
        product: str | None = None,
    ) -> QuikStrikeMatrixLocalBrowserReadiness:
        """Return manual-readiness status without touching a browser or network."""

        normalized_surface = (surface or self.sanitized_context.get("surface") or "").lower()
        normalized_product = (product or self.sanitized_context.get("product") or "").lower()
        surface_ready = "open interest" in normalized_surface and "matrix" in normalized_surface
        product_ready = "gold" in normalized_product or "og|gc" in normalized_product
        ready = surface_ready and product_ready
        if ready:
            return QuikStrikeMatrixLocalBrowserReadiness(
                ready=True,
                status="manual_ready",
                message=(
                    "User-controlled browser context appears to describe Gold "
                    "OPEN INTEREST Matrix."
                ),
                limitations=_limitations(),
            )
        return QuikStrikeMatrixLocalBrowserReadiness(
            ready=False,
            status="manual_navigation_required",
            message=(
                "Open QuikStrike manually, sign in manually, navigate to OPEN INTEREST "
                "Matrix, and select Gold (OG|GC)."
            ),
            limitations=_limitations(),
        )

    def collect_current_table_payload(self) -> None:
        """Placeholder only; real browser collection is intentionally not implemented."""

        raise QuikStrikeMatrixLocalBrowserNotImplementedError(
            "Real browser extraction is user-controlled and not implemented in this slice."
        )


def validate_sanitized_browser_context(payload: Mapping[str, Any]) -> None:
    """Reject secret/session-bearing local browser context inputs."""

    ensure_no_forbidden_quikstrike_matrix_content(dict(payload))


def _limitations() -> list[str]:
    return [
        "No browser cookies, tokens, headers, viewstate values, HAR files, screenshots, "
        "credentials, or private full URLs are accepted or persisted.",
        "No endpoint replay, OCR, private account access, or network calls are performed.",
        "The user must control authentication and page navigation manually.",
    ]
