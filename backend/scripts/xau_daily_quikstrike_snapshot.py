"""Run the local daily XAU QuikStrike research snapshot workflow.

The workflow is semi-automated. It attaches to a user-controlled browser over
local CDP after manual login and page navigation. It never stores credentials,
cookies, headers, HAR files, screenshots, viewstate values, or private URLs.
"""

from __future__ import annotations

import argparse
import json
from datetime import UTC, datetime

from src.models.xau_forward_journal import (
    XauForwardJournalCreateRequest,
    XauForwardJournalNote,
)
from src.models.xau_quikstrike_fusion import XauQuikStrikeFusionRequest
from src.quikstrike.playwright_local import (
    DEFAULT_CDP_URL,
    QuikStrikeBrowserPageNotReadyError,
    QuikStrikeCdpConnectionError,
    QuikStrikePlaywrightUnavailableError,
)
from src.quikstrike.playwright_local import (
    extract_from_cdp as extract_vol2vol_from_cdp,
)
from src.quikstrike_matrix.playwright_local import (
    QuikStrikeMatrixBrowserPageNotReadyError,
    QuikStrikeMatrixCdpConnectionError,
    QuikStrikeMatrixPlaywrightUnavailableError,
)
from src.quikstrike_matrix.playwright_local import (
    extract_from_cdp as extract_matrix_from_cdp,
)
from src.xau_forward_journal.orchestration import create_xau_forward_journal_entry
from src.xau_quikstrike_fusion.orchestration import create_xau_quikstrike_fusion_report


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Create one local-only daily XAU research snapshot from QuikStrike."
    )
    parser.add_argument("--cdp-url", default=DEFAULT_CDP_URL)
    parser.add_argument("--wait-seconds", type=int, default=900)
    parser.add_argument("--poll-seconds", type=int, default=5)
    parser.add_argument("--capture-session", default=None)
    parser.add_argument("--xauusd-spot-reference", type=float, default=None)
    parser.add_argument("--gc-futures-reference", type=float, default=None)
    parser.add_argument("--session-open-price", type=float, default=None)
    parser.add_argument("--realized-volatility", type=float, default=None)
    parser.add_argument("--no-prompt", action="store_true")
    args = parser.parse_args()

    try:
        if not args.no_prompt:
            _prompt(
                "Log in manually, open Gold QUIKOPTIONS VOL2VOL, then press Enter "
                "to capture Vol2Vol."
            )
        vol2vol = extract_vol2vol_from_cdp(
            cdp_url=args.cdp_url,
            drive_views=True,
        )

        if not args.no_prompt:
            _prompt(
                "Open Gold OPEN INTEREST Matrix. Select each requested Matrix view "
                "when prompted by the page state, then press Enter to start waiting."
            )
        matrix = extract_matrix_from_cdp(
            cdp_url=args.cdp_url,
            manual_views=True,
            view_prompt=None if args.no_prompt else _prompt_matrix_view,
            wait_seconds=args.wait_seconds,
            poll_seconds=args.poll_seconds,
        )
    except (
        QuikStrikeBrowserPageNotReadyError,
        QuikStrikeCdpConnectionError,
        QuikStrikePlaywrightUnavailableError,
        QuikStrikeMatrixBrowserPageNotReadyError,
        QuikStrikeMatrixCdpConnectionError,
        QuikStrikeMatrixPlaywrightUnavailableError,
    ) as exc:
        raise SystemExit(str(exc)) from exc

    fusion = create_xau_quikstrike_fusion_report(
        XauQuikStrikeFusionRequest(
            vol2vol_report_id=vol2vol.report.extraction_id,
            matrix_report_id=matrix.report.extraction_id,
            xauusd_spot_reference=args.xauusd_spot_reference,
            gc_futures_reference=args.gc_futures_reference,
            session_open_price=args.session_open_price,
            realized_volatility=args.realized_volatility,
            create_xau_vol_oi_report=True,
            create_xau_reaction_report=True,
            run_label="daily_snapshot",
            research_only_acknowledged=True,
        )
    )
    downstream = fusion.downstream_result
    xau_vol_oi_report_id = downstream.xau_vol_oi_report_id if downstream else None
    xau_reaction_report_id = downstream.xau_reaction_report_id if downstream else None

    journal = None
    journal_blocker = None
    if xau_vol_oi_report_id and xau_reaction_report_id:
        journal = create_xau_forward_journal_entry(
            XauForwardJournalCreateRequest(
                snapshot_time=datetime.now(UTC),
                capture_window="daily_snapshot",
                capture_session=args.capture_session,
                vol2vol_report_id=vol2vol.report.extraction_id,
                matrix_report_id=matrix.report.extraction_id,
                fusion_report_id=fusion.report_id,
                xau_vol_oi_report_id=xau_vol_oi_report_id,
                xau_reaction_report_id=xau_reaction_report_id,
                spot_price_at_snapshot=args.xauusd_spot_reference,
                futures_price_at_snapshot=args.gc_futures_reference,
                session_open_price=args.session_open_price,
                notes=[
                    XauForwardJournalNote(
                        text=(
                            "Daily research snapshot created from local user-controlled "
                            "QuikStrike reports."
                        ),
                        source="xau_daily_quikstrike_snapshot",
                    )
                ],
                research_only_acknowledged=True,
            )
        )
    else:
        journal_blocker = (
            "Forward journal entry was not created because linked XAU Vol-OI and "
            "XAU reaction reports were not both created."
        )

    summary = _summary(vol2vol.report, matrix.report, fusion, journal, journal_blocker)
    print(json.dumps(summary, indent=2))
    return 0


def _prompt(message: str) -> None:
    input(f"\n{message}\n")


def _prompt_matrix_view(view: object) -> None:
    input(f"\nSelect QuikStrike Matrix view '{view.value}', then press Enter to capture.\n")


def _summary(
    vol2vol: object,
    matrix: object,
    fusion: object,
    journal: object | None,
    blocker: str | None,
) -> dict:
    downstream = fusion.downstream_result
    return {
        "vol2vol_report_id": vol2vol.extraction_id,
        "vol2vol_rows": vol2vol.row_count,
        "matrix_report_id": matrix.extraction_id,
        "matrix_rows": matrix.row_count,
        "matrix_strikes": matrix.strike_count,
        "matrix_expirations": matrix.expiration_count,
        "fusion_report_id": fusion.report_id,
        "fusion_rows": fusion.fused_row_count,
        "fused_xau_input_rows": fusion.xau_vol_oi_input_row_count,
        "xau_vol_oi_report_id": downstream.xau_vol_oi_report_id if downstream else None,
        "xau_reaction_report_id": downstream.xau_reaction_report_id if downstream else None,
        "reaction_count": downstream.reaction_row_count if downstream else None,
        "no_trade_count": downstream.no_trade_count if downstream else None,
        "journal_id": journal.journal_id if journal else None,
        "snapshot_key": journal.snapshot_key if journal else None,
        "pending_outcome_windows": (
            [outcome.window.value for outcome in journal.outcomes] if journal else []
        ),
        "journal_blocker": blocker,
        "fusion_artifacts": [artifact.path for artifact in fusion.artifacts],
        "journal_artifacts": [artifact.path for artifact in journal.artifacts] if journal else [],
        "limitations": [
            "Local-only research workflow.",
            "Manual QuikStrike authentication is required.",
            (
                "No credentials, cookies, headers, HAR, screenshots, viewstate, "
                "or private URLs are saved."
            ),
        ],
    }


if __name__ == "__main__":
    raise SystemExit(main())
