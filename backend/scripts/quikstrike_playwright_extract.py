"""Run local QuikStrike extraction from a manually logged-in Playwright/CDP browser."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from src.models.quikstrike import QuikStrikeViewType
from src.quikstrike.playwright_local import (
    DEFAULT_CDP_URL,
    DEFAULT_START_URL,
    DEFAULT_TARGET_URL,
    QuikStrikeBrowserLaunchError,
    QuikStrikeBrowserPageNotReadyError,
    QuikStrikeCdpConnectionError,
    QuikStrikePlaywrightUnavailableError,
    extract_from_cdp,
    extract_from_launched_browser,
)

FORBIDDEN_ENV_KEYS = (
    "AUTH",
    "COOKIE",
    "CREDENTIAL",
    "HEADER",
    "PASSWORD",
    "SECRET",
    "SESSION",
    "TOKEN",
    "USERNAME",
    "VIEWSTATE",
)


def main() -> int:
    env_parser = argparse.ArgumentParser(add_help=False)
    env_parser.add_argument("--env-file", default=".env.quikstrike.local")
    env_args, _ = env_parser.parse_known_args()
    env = _load_env_file(_resolve_env_file(Path(env_args.env_file)))

    parser = argparse.ArgumentParser(
        description=(
            "Attach to a user-controlled Chrome/Edge CDP session and extract sanitized "
            "Gold QUIKOPTIONS VOL2VOL Highcharts data."
        ),
        parents=[env_parser],
    )
    parser.add_argument(
        "--mode",
        choices=["cdp", "launch"],
        default=env.get("QUIKSTRIKE_MODE", "cdp"),
        help="cdp attaches to an existing browser; launch opens a visible local browser.",
    )
    parser.add_argument("--cdp-url", default=env.get("QUIKSTRIKE_CDP_URL", DEFAULT_CDP_URL))
    parser.add_argument(
        "--start-url",
        default=env.get("QUIKSTRIKE_START_URL", DEFAULT_START_URL),
        help="Public QuikStrike start URL. Do not include private/session query values.",
    )
    parser.add_argument(
        "--target-url",
        default=env.get("QUIKSTRIKE_TARGET_URL", DEFAULT_TARGET_URL),
        help="Known Gold Vol2Vol browser URL used after manual login reaches the mode page.",
    )
    parser.add_argument(
        "--view",
        action="append",
        choices=[view.value for view in QuikStrikeViewType],
        default=_env_views(env),
        help="View to extract. Repeat for multiple views. Defaults to all supported views.",
    )
    parser.add_argument(
        "--drive-views",
        action="store_true",
        default=_env_bool(env.get("QUIKSTRIKE_DRIVE_VIEWS")),
        help="Click supported Vol2Vol view tabs after the user has logged in and selected Gold.",
    )
    parser.add_argument(
        "--manual-views",
        action="store_true",
        default=_env_bool(env.get("QUIKSTRIKE_MANUAL_VIEWS")),
        help="Wait for the user to manually select each requested view before capture.",
    )
    parser.add_argument(
        "--wait-seconds",
        type=int,
        default=int(env.get("QUIKSTRIKE_WAIT_SECONDS", "600")),
        help="Launch mode wait time for manual login and Gold Vol2Vol navigation.",
    )
    parser.add_argument(
        "--poll-seconds",
        type=int,
        default=int(env.get("QUIKSTRIKE_POLL_SECONDS", "5")),
        help="Launch mode polling interval while waiting for manual navigation.",
    )
    parser.add_argument(
        "--browser-channel",
        default=env.get("QUIKSTRIKE_BROWSER_CHANNEL", "chrome"),
        help="Installed browser channel for launch mode, for example chrome or msedge.",
    )
    parser.add_argument(
        "--headless",
        action="store_true",
        default=_env_bool(env.get("QUIKSTRIKE_HEADLESS")),
        help="For fixture/debug use only. Manual QuikStrike login normally needs headed mode.",
    )
    parser.add_argument(
        "--debug-page-state",
        action="store_true",
        default=_env_bool(env.get("QUIKSTRIKE_DEBUG_PAGE_STATE")),
        help="Print sanitized visible QuikStrike page state while polling.",
    )
    args = parser.parse_args()

    try:
        if args.mode == "launch":
            extraction = extract_from_launched_browser(
                start_url=args.start_url,
                target_url=args.target_url,
                views=args.view,
                drive_views=args.drive_views,
                manual_views=args.manual_views,
                wait_seconds=args.wait_seconds,
                poll_seconds=args.poll_seconds,
                headless=args.headless,
                channel=args.browser_channel,
                debug_page_state=args.debug_page_state,
            )
        else:
            extraction = extract_from_cdp(
                cdp_url=args.cdp_url,
                views=args.view,
                drive_views=args.drive_views,
            )
    except (
        QuikStrikeBrowserLaunchError,
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


def _load_env_file(path: Path) -> dict[str, str]:
    if not path.exists():
        return {}
    values: dict[str, str] = {}
    for line_number, raw_line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if "=" not in line:
            raise ValueError(f"Invalid env line {line_number}: expected KEY=VALUE")
        key, value = line.split("=", 1)
        key = key.strip()
        if any(token in key.upper() for token in FORBIDDEN_ENV_KEYS):
            raise ValueError(
                f"{path} contains forbidden QuikStrike credential/session key: {key}"
            )
        values[key] = value.strip().strip('"').strip("'")
    return values


def _resolve_env_file(path: Path) -> Path:
    if path.exists() or path.is_absolute():
        return path
    parent_path = Path("..") / path
    if parent_path.exists():
        return parent_path
    return path


def _env_views(env: dict[str, str]) -> list[str] | None:
    value = env.get("QUIKSTRIKE_VIEWS")
    if not value:
        return None
    return [item.strip() for item in value.split(",") if item.strip()]


def _env_bool(value: str | None) -> bool:
    return str(value or "").strip().lower() in {"1", "true", "yes", "on"}


if __name__ == "__main__":
    raise SystemExit(main())
