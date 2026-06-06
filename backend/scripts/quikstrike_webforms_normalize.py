"""Fetch and normalize QuikStrike WebForms data without opening a browser."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

from src.quikstrike.webforms_client import QuikStrikeWebFormsCredentials, QuikStrikeWebFormsError
from src.quikstrike.webforms_normalizer import (
    DEFAULT_NORMALIZED_VIEWS,
    run_webforms_normalized_fetch,
)

DEFAULT_GOLD_START_URL = (
    "https://cmegroup-sso.quikstrike.net/User/QuikStrikeView.aspx?pid=40&pf=6"
)
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
        description="Fetch QuikStrike WebForms views and persist normalized artifacts.",
        parents=[env_parser],
    )
    parser.add_argument(
        "--start-url",
        default=_setting(
            "QUIKSTRIKE_API_START_URL",
            env_file_values,
            DEFAULT_GOLD_START_URL,
        ),
    )
    parser.add_argument("--username-env", default="QUIKSTRIKE_API_USERNAME")
    parser.add_argument("--password-env", default="QUIKSTRIKE_API_PASSWORD")
    parser.add_argument(
        "--view",
        action="append",
        choices=list(DEFAULT_NORMALIZED_VIEWS),
        help="View to normalize. Repeat to fetch a subset. Defaults to every known view.",
    )
    parser.add_argument("--output-root", default="")
    parser.add_argument("--overwrite", action="store_true")
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

    try:
        artifacts = run_webforms_normalized_fetch(
            credentials=QuikStrikeWebFormsCredentials(username=username, password=password),
            start_url=args.start_url,
            views=args.view or list(DEFAULT_NORMALIZED_VIEWS),
            output_root=Path(args.output_root) if args.output_root else None,
            overwrite_allowed=args.overwrite,
        )
    except QuikStrikeWebFormsError as exc:
        parser.exit(status=2, message=f"{exc}\n")

    digest = artifacts.digest
    print(
        json.dumps(
            {
                "status": digest["status"],
                "digest_path": str(artifacts.digest_path),
                "completed_views": digest["completed_views"],
                "vol2vol_report_id": artifacts.vol2vol_report_id,
                "vol2vol_rows": digest["vol2vol"]["row_count"],
                "vol2vol_conversion_rows": digest["vol2vol"]["conversion_row_count"],
                "matrix_report_id": artifacts.matrix_report_id,
                "matrix_rows": digest["matrix"]["row_count"],
                "matrix_conversion_rows": digest["matrix"]["conversion_row_count"],
                "supplemental_view_count": digest["supplemental"]["view_count"],
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
