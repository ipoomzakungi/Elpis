"""Run local QuikStrike Matrix extraction from a manually controlled CDP browser."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from src.models.quikstrike_matrix import QuikStrikeMatrixViewType
from src.quikstrike_matrix.playwright_local import (
    DEFAULT_CDP_URL,
    QuikStrikeMatrixBrowserPageNotReadyError,
    QuikStrikeMatrixCdpConnectionError,
    QuikStrikeMatrixPlaywrightUnavailableError,
    extract_from_cdp,
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
            "Gold OPEN INTEREST Matrix table data."
        ),
        parents=[env_parser],
    )
    parser.add_argument("--cdp-url", default=env.get("QUIKSTRIKE_CDP_URL", DEFAULT_CDP_URL))
    parser.add_argument(
        "--view",
        action="append",
        choices=[view.value for view in QuikStrikeMatrixViewType],
        default=_env_views(env),
        help="Matrix view to extract. Repeat for multiple views. Defaults to all supported views.",
    )
    parser.add_argument(
        "--manual-views",
        action="store_true",
        default=_env_bool(env.get("QUIKSTRIKE_MATRIX_MANUAL_VIEWS", "true")),
        help="Wait for the user to manually select each requested Matrix view before capture.",
    )
    parser.add_argument(
        "--prompt-views",
        action="store_true",
        default=_env_bool(env.get("QUIKSTRIKE_MATRIX_PROMPT_VIEWS")),
        help="Prompt before each requested Matrix view and capture after Enter.",
    )
    parser.add_argument(
        "--drive-views",
        action="store_true",
        default=_env_bool(env.get("QUIKSTRIKE_MATRIX_DRIVE_VIEWS")),
        help="Best-effort click of Matrix view labels after the user has opened Gold Matrix.",
    )
    parser.add_argument(
        "--auto-views",
        action="store_true",
        default=_env_bool(env.get("QUIKSTRIKE_MATRIX_AUTO_VIEWS")),
        help="Use best-effort view clicks instead of waiting for manual view changes.",
    )
    parser.add_argument(
        "--wait-seconds",
        type=int,
        default=int(env.get("QUIKSTRIKE_WAIT_SECONDS", "600")),
    )
    parser.add_argument(
        "--poll-seconds",
        type=int,
        default=int(env.get("QUIKSTRIKE_POLL_SECONDS", "5")),
    )
    args = parser.parse_args()

    try:
        extraction = extract_from_cdp(
            cdp_url=args.cdp_url,
            views=args.view,
            drive_views=args.drive_views,
            manual_views=False if args.auto_views else args.manual_views,
            view_prompt=_prompt_view if args.prompt_views else None,
            wait_seconds=args.wait_seconds,
            poll_seconds=args.poll_seconds,
        )
    except (
        QuikStrikeMatrixBrowserPageNotReadyError,
        QuikStrikeMatrixCdpConnectionError,
        QuikStrikeMatrixPlaywrightUnavailableError,
    ) as exc:
        parser.exit(status=2, message=f"{exc}\n")

    print(
        json.dumps(
            {
                "extraction_id": extraction.report.extraction_id,
                "status": extraction.report.status.value,
                "row_count": extraction.report.row_count,
                "strike_count": extraction.report.strike_count,
                "expiration_count": extraction.report.expiration_count,
                "view_summaries": extraction.report.view_summaries,
                "mapping_status": extraction.report.mapping.status.value,
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
    value = env.get("QUIKSTRIKE_MATRIX_VIEWS")
    if not value:
        return None
    return [item.strip() for item in value.split(",") if item.strip()]


def _env_bool(value: str | None) -> bool:
    return str(value or "").strip().lower() in {"1", "true", "yes", "on"}


def _prompt_view(view: QuikStrikeMatrixViewType) -> None:
    input(f"\nSelect QuikStrike Matrix view '{view.value}', then press Enter to capture.\n")


if __name__ == "__main__":
    raise SystemExit(main())
