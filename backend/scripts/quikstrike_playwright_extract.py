"""Run local QuikStrike extraction from a manually logged-in Playwright/CDP browser."""

from __future__ import annotations

import argparse
import json

from src.models.quikstrike import QuikStrikeViewType
from src.quikstrike.playwright_local import (
    DEFAULT_CDP_URL,
    QuikStrikeBrowserPageNotReadyError,
    QuikStrikeCdpConnectionError,
    QuikStrikePlaywrightUnavailableError,
    extract_from_cdp,
)


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Attach to a user-controlled Chrome/Edge CDP session and extract sanitized "
            "Gold QUIKOPTIONS VOL2VOL Highcharts data."
        )
    )
    parser.add_argument("--cdp-url", default=DEFAULT_CDP_URL)
    parser.add_argument(
        "--view",
        action="append",
        choices=[view.value for view in QuikStrikeViewType],
        help="View to extract. Repeat for multiple views. Defaults to all supported views.",
    )
    parser.add_argument(
        "--drive-views",
        action="store_true",
        help="Click supported Vol2Vol view tabs after the user has logged in and selected Gold.",
    )
    args = parser.parse_args()

    try:
        extraction = extract_from_cdp(
            cdp_url=args.cdp_url,
            views=args.view,
            drive_views=args.drive_views,
        )
    except (
        QuikStrikeBrowserPageNotReadyError,
        QuikStrikeCdpConnectionError,
        QuikStrikePlaywrightUnavailableError,
    ) as exc:
        parser.exit(status=2, message=f"{exc}\n")
    print(
        json.dumps(
            {
                "extraction_id": extraction.report.extraction_id,
                "status": extraction.report.status.value,
                "row_count": extraction.report.row_count,
                "view_summaries": extraction.report.view_summaries,
                "strike_mapping": extraction.report.strike_mapping.confidence.value,
                "conversion_status": (
                    extraction.report.conversion_result.status.value
                    if extraction.report.conversion_result
                    else None
                ),
                "artifacts": [artifact.path for artifact in extraction.report.artifacts],
                "limitations": extraction.report.limitations,
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
