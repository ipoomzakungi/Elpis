from __future__ import annotations

import argparse
import sys
from dataclasses import dataclass
from datetime import date
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from src.models.xau_daily_structural_map import XauDailyStructuralMapReportResult  # noqa: E402
from src.xau_daily_structural_map.bundle_adapter import (  # noqa: E402
    generate_xau_daily_structural_map_from_bundle,
)
from src.xau_daily_structural_map.sample_run import (  # noqa: E402
    stable_xau_daily_structural_map_id,
)

REPORT_JSON_FILENAME = "04_xau_vol_oi_report_report.json"
WALLS_PARQUET_FILENAME = "04_xau_vol_oi_report_walls.parquet"
ZONES_PARQUET_FILENAME = "04_xau_vol_oi_report_zones.parquet"
FUSED_ROWS_FILENAME = "03_xau_quikstrike_fusion_fused_rows.json"


@dataclass(frozen=True)
class LocalBundleRunConfig:
    input_dir: Path
    session_date: date
    expiration_code: str
    traded_instrument: str
    gc_reference_price: float | None = None
    traded_reference_price: float | None = None
    manual_basis: float | None = None
    session_open_price: float | None = None
    session_open_source: str | None = None
    output_root: Path | None = None
    map_id: str | None = None
    overwrite_allowed: bool = False


def generate_from_local_bundle(
    config: LocalBundleRunConfig,
) -> XauDailyStructuralMapReportResult:
    input_dir = config.input_dir.resolve()
    if not input_dir.exists():
        raise FileNotFoundError(f"Input directory does not exist: {input_dir}")
    if not input_dir.is_dir():
        raise NotADirectoryError(f"Input path is not a directory: {input_dir}")

    report_path = input_dir / REPORT_JSON_FILENAME
    if not report_path.exists():
        raise FileNotFoundError(
            "Missing required XAU Vol-OI report JSON: "
            f"{report_path.name} in {input_dir}"
        )

    walls_path = _optional_path(input_dir / WALLS_PARQUET_FILENAME)
    fused_rows_path = _optional_path(input_dir / FUSED_ROWS_FILENAME)
    map_id = config.map_id or stable_xau_daily_structural_map_id(
        session_date=config.session_date,
        expiration_code=config.expiration_code,
    )
    return generate_xau_daily_structural_map_from_bundle(
        map_id=map_id,
        session_date=config.session_date,
        xau_vol_oi_report_path=report_path,
        walls_path=walls_path,
        fused_rows_path=fused_rows_path,
        traded_instrument=config.traded_instrument,
        traded_reference_price=config.traded_reference_price,
        gc_reference_price=config.gc_reference_price,
        manual_basis=config.manual_basis,
        session_open_price=config.session_open_price,
        session_open_source=config.session_open_source,
        output_root=_normalize_output_root(config.output_root),
        overwrite_allowed=config.overwrite_allowed,
    )


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Generate a research-only XAU daily structural map from a local "
            "QuikStrike/XAU Vol-OI bundle."
        )
    )
    parser.add_argument("--input-dir", type=Path, required=True)
    parser.add_argument("--session-date", type=_parse_date, required=True)
    parser.add_argument("--expiration-code", required=True)
    parser.add_argument("--traded-instrument", required=True)
    parser.add_argument("--gc-reference-price", type=float)
    parser.add_argument("--traded-reference-price", type=float)
    parser.add_argument("--manual-basis", type=float)
    parser.add_argument("--session-open-price", type=float)
    parser.add_argument("--session-open-source", default="manual_research_input")
    parser.add_argument("--output-root", type=Path, default=BACKEND_ROOT / "data" / "reports")
    parser.add_argument("--map-id")
    parser.add_argument("--overwrite-allowed", action="store_true")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    result = generate_from_local_bundle(
        LocalBundleRunConfig(
            input_dir=args.input_dir,
            session_date=args.session_date,
            expiration_code=args.expiration_code,
            traded_instrument=args.traded_instrument,
            gc_reference_price=args.gc_reference_price,
            traded_reference_price=args.traded_reference_price,
            manual_basis=args.manual_basis,
            session_open_price=args.session_open_price,
            session_open_source=args.session_open_source,
            output_root=args.output_root,
            map_id=args.map_id,
            overwrite_allowed=args.overwrite_allowed,
        )
    )
    print(f"map_id={result.metadata.map_id}")
    print(f"readiness={result.metadata.readiness.value}")
    print(f"wall_count={result.metadata.wall_count}")
    print(f"signal_allowed={result.metadata.signal_allowed}")
    for artifact in result.artifacts:
        print(f"{artifact.artifact_type.value}={artifact.path}")
    return 0


def _optional_path(path: Path) -> Path | None:
    return path if path.exists() else None


def _normalize_output_root(output_root: Path | None) -> Path | None:
    if output_root is None:
        return None
    resolved = output_root.resolve()
    if resolved.name == "xau_daily_structural_map":
        return resolved.parent
    return resolved


def _parse_date(value: str) -> date:
    try:
        return date.fromisoformat(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("date must use YYYY-MM-DD format") from exc


if __name__ == "__main__":
    raise SystemExit(main())
