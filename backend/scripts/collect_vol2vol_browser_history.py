from __future__ import annotations

import argparse
import json
from collections.abc import Sequence
from datetime import date
from pathlib import Path

from src.xau_vol2vol_history_walkforward.browser_collector import (
    Vol2VolBrowserCollectionConfig,
    collect_browser_history,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Collect research-only Vol2Vol JSON through a visible CDP browser.",
    )
    parser.add_argument("--cdp-url", default="http://127.0.0.1:9222")
    parser.add_argument("--base-url", default="https://www.vol2vol.com")
    selection = parser.add_mutually_exclusive_group(required=True)
    selection.add_argument("--all-available", action="store_true")
    selection.add_argument("--session-date")
    parser.add_argument("--output-root", default="data/imports/vol2vol")
    parser.add_argument("--min-delay-seconds", type=float, default=1.5)
    parser.add_argument("--max-retries", type=int, default=3)
    parser.add_argument("--refresh", action="store_true")
    parser.add_argument("--include-current-incomplete-session", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--timezone", default="Asia/Bangkok")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    try:
        args = parser.parse_args(argv)
        manifest = collect_browser_history(
            Vol2VolBrowserCollectionConfig(
                cdp_url=args.cdp_url,
                base_url=args.base_url,
                output_root=Path(args.output_root),
                session_date=date.fromisoformat(args.session_date) if args.session_date else None,
                all_available=args.all_available,
                refresh=args.refresh,
                include_current_incomplete_session=args.include_current_incomplete_session,
                dry_run=args.dry_run,
                min_delay_seconds=args.min_delay_seconds,
                max_retries=args.max_retries,
                timezone=args.timezone,
            )
        )
    except (OSError, RuntimeError, ValueError) as exc:
        parser.error(str(exc))
        return 2
    counts: dict[str, int] = {}
    for row in manifest.rows:
        counts[row.status.value] = counts.get(row.status.value, 0) + 1
    print(
        json.dumps(
            {
                "advertised_session_count": manifest.advertised_session_count,
                "included_session_count": manifest.included_session_count,
                "status_counts": counts,
                "research_only": True,
                "signal_allowed": False,
            },
            indent=2,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
