"""Fill normal QuikStrike browser login fields in an existing CDP browser."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

from src.quikstrike.api_probe import DEFAULT_QUIKSTRIKE_START_URL
from src.quikstrike.browser_login import (
    QuikStrikeBrowserLoginCdpError,
    QuikStrikeBrowserLoginUnavailableError,
    run_browser_login,
)
from src.quikstrike.playwright_local import DEFAULT_CDP_URL

ALLOWED_ENV_FILE_KEYS = {
    "QUIKSTRIKE_API_USERNAME",
    "QUIKSTRIKE_API_PASSWORD",
    "QUIKSTRIKE_API_START_URL",
}


def main() -> int:
    env_parser = argparse.ArgumentParser(add_help=False)
    env_parser.add_argument("--env-file", default=".env")
    env_args, _ = env_parser.parse_known_args()
    env_file_values = _load_env_file(_resolve_env_file(Path(env_args.env_file)))

    parser = argparse.ArgumentParser(
        description="Fill QuikStrike normal browser login fields.",
        parents=[env_parser],
    )
    parser.add_argument("--cdp-url", default=DEFAULT_CDP_URL)
    parser.add_argument(
        "--start-url",
        default=_setting(
            "QUIKSTRIKE_API_START_URL",
            env_file_values,
            DEFAULT_QUIKSTRIKE_START_URL,
        ),
    )
    parser.add_argument("--username-env", default="QUIKSTRIKE_API_USERNAME")
    parser.add_argument("--password-env", default="QUIKSTRIKE_API_PASSWORD")
    parser.add_argument("--wait-seconds", type=int, default=90)
    args = parser.parse_args()

    username = _setting(args.username_env, env_file_values, "")
    password = _setting(args.password_env, env_file_values, "")
    try:
        result = run_browser_login(
            cdp_url=args.cdp_url,
            username=username,
            password=password,
            start_url=args.start_url,
            wait_seconds=args.wait_seconds,
        )
    except (QuikStrikeBrowserLoginCdpError, QuikStrikeBrowserLoginUnavailableError) as exc:
        parser.exit(status=2, message=f"{exc}\n")

    print(json.dumps(result, indent=2))
    return 0 if result["status"] in {"authenticated_page_reachable", "missing_credentials"} else 2


def _setting(key: str, env_file_values: dict[str, str], default: str) -> str:
    value = os.environ.get(key)
    if value is not None:
        return value
    return env_file_values.get(key, default)


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
        normalized_key = key.strip()
        if normalized_key not in ALLOWED_ENV_FILE_KEYS:
            raise ValueError(
                f"{path} contains unsupported QuikStrike login env key: {normalized_key}"
            )
        values[normalized_key] = value.strip().strip('"').strip("'")
    return values


def _resolve_env_file(path: Path) -> Path:
    if path.exists() or path.is_absolute():
        return path
    parent_path = Path("..") / path
    if parent_path.exists():
        return parent_path
    return path


if __name__ == "__main__":
    raise SystemExit(main())
