"""Run QuikStrike through HTTP login plus ASP.NET WebForms postbacks.

Credentials are read only from runtime environment variables or an ignored local
`.env` file and kept in memory:

    QUIKSTRIKE_API_USERNAME
    QUIKSTRIKE_API_PASSWORD

The persisted report is sanitized and intentionally excludes cookies, headers,
tokens, credentials, request bodies, response bodies, viewstate, full URLs, HAR,
and screenshots.
"""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

from src.quikstrike.api_probe import DEFAULT_QUIKSTRIKE_START_URL
from src.quikstrike.webforms_client import (
    MATRIX_EVENT_TARGETS,
    SUPPLEMENTAL_EVENT_TARGETS,
    VOL2VOL_EVENT_TARGETS,
    QuikStrikeWebFormsCredentials,
    QuikStrikeWebFormsError,
    default_webforms_probe_path,
    run_webforms_probe,
    write_webforms_probe_report,
)

ALLOWED_ENV_FILE_KEYS = {
    "QUIKSTRIKE_API_USERNAME",
    "QUIKSTRIKE_API_PASSWORD",
    "QUIKSTRIKE_API_START_URL",
}

DEFAULT_VIEWS = [
    *VOL2VOL_EVENT_TARGETS,
    *MATRIX_EVENT_TARGETS,
    *SUPPLEMENTAL_EVENT_TARGETS,
]


def main() -> int:
    env_parser = argparse.ArgumentParser(add_help=False)
    env_parser.add_argument("--env-file", default=".env")
    env_args, _ = env_parser.parse_known_args()
    env_file_values = _load_env_file(_resolve_env_file(Path(env_args.env_file)))

    parser = argparse.ArgumentParser(
        description="Fetch QuikStrike views with HTTP login and WebForms postbacks.",
        parents=[env_parser],
    )
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
    parser.add_argument(
        "--view",
        action="append",
        choices=DEFAULT_VIEWS,
        help="View to fetch. Repeat to fetch a subset. Defaults to every known view.",
    )
    parser.add_argument("--output-path", default="")
    args = parser.parse_args()

    username = _setting(args.username_env, env_file_values, "")
    password = _setting(args.password_env, env_file_values, "")
    if not username or not password:
        parser.exit(
            status=2,
            message=(
                "Missing local credentials. Set "
                f"{args.username_env} and {args.password_env} in the current shell "
                f"or in ignored env file {args.env_file}. Do not commit them to git.\n"
            ),
        )

    output_path = (
        Path(args.output_path)
        if args.output_path
        else default_webforms_probe_path(repo_backend_dir=Path(__file__).resolve().parents[1])
    )
    if not output_path.is_absolute():
        output_path = Path.cwd() / output_path

    try:
        report = run_webforms_probe(
            credentials=QuikStrikeWebFormsCredentials(
                username=username,
                password=password,
            ),
            start_url=args.start_url,
            views=args.view or DEFAULT_VIEWS,
        )
        write_webforms_probe_report(report, output_path)
    except QuikStrikeWebFormsError as exc:
        parser.exit(status=2, message=f"{exc}\n")

    print(
        json.dumps(
            {
                "status": report["status"],
                "requested_views": report["requested_views"],
                "completed_views": report["completed_views"],
                "login_step_count": len(report["login_steps"]),
                "view_step_count": len(report["view_summaries"]),
                "report_path": str(output_path),
                "limitations": report["limitations"],
            },
            indent=2,
        )
    )
    return 0


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
                f"{path} contains unsupported QuikStrike WebForms env key: {normalized_key}"
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
