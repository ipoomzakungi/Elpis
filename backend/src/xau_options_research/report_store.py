from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import polars as pl


class XauOptionsResearchReportStore:
    def __init__(self, root: Path) -> None:
        self.root = root

    def persist(
        self,
        *,
        run_id: str,
        manifest: dict[str, Any],
        checkpoints: list[dict[str, Any]],
        raw_events: list[dict[str, Any]],
        episode_events: list[dict[str, Any]],
        labels: list[dict[str, Any]],
        feature_coverage: dict[str, Any],
        event_study: dict[str, Any],
        strategy_results: dict[str, Any],
        negative_controls: dict[str, Any],
        validation_report: dict[str, Any],
        holdout_report: dict[str, Any],
        trial_registry: dict[str, Any],
        review_handoff: str,
        evidence_status: str,
    ) -> Path:
        report_dir = self.root / run_id
        report_dir.mkdir(parents=True, exist_ok=False)
        _write_json(report_dir / "experiment_manifest.json", manifest)
        _write_parquet(report_dir / "feature_panel.parquet", checkpoints)
        _write_parquet(report_dir / "checkpoint_rows.parquet", checkpoints)
        _write_parquet(report_dir / "event_rows.parquet", raw_events)
        _write_parquet(report_dir / "event_labels.parquet", labels)
        _write_json(report_dir / "feature_coverage.json", feature_coverage)
        _write_json(report_dir / "event_study.json", event_study)
        _write_json(report_dir / "strategy_results.json", strategy_results)
        _write_json(report_dir / "negative_controls.json", negative_controls)
        _write_json(report_dir / "validation_report.json", validation_report)
        _write_json(report_dir / "holdout_report.json", holdout_report)
        _write_json(report_dir / "trial_registry.json", trial_registry)
        (report_dir / "event_study.md").write_text(_event_markdown(event_study), encoding="utf-8")
        (report_dir / "strategy_results.md").write_text(
            _strategy_markdown(strategy_results), encoding="utf-8"
        )
        (report_dir / "review_handoff.md").write_text(review_handoff, encoding="utf-8")
        _write_json(
            report_dir / "metadata.json",
            {
                "run_id": run_id,
                "created_at": datetime.now(UTC).isoformat(),
                "report_dir": report_dir.resolve().as_posix(),
                "checkpoint_count": len(checkpoints),
                "raw_event_count": len(raw_events),
                "unique_episode_count": len(episode_events),
                "evidence_status": evidence_status,
                "research_only": True,
                "signal_allowed": False,
            },
        )
        return report_dir


def _write_parquet(path: Path, rows: list[dict[str, Any]]) -> None:
    pl.DataFrame(
        rows if rows else {"empty": []},
        strict=False,
        infer_schema_length=None,
    ).write_parquet(path)


def _write_json(path: Path, payload: Any) -> None:
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _event_markdown(payload: dict[str, Any]) -> str:
    lines = ["# XAU Options Event Study", "", "Research-only; correlations are not causal.", ""]
    for row in payload["feature_summaries"]:
        lines.append(
            f"- `{row['feature']}` events=`{row['event_count']}` "
            f"rho=`{row['spearman_rho']}` q=`{row['bh_q_value']}`"
        )
    return "\n".join(lines) + "\n"


def _strategy_markdown(payload: dict[str, Any]) -> str:
    lines = ["# Preregistered Strategy Results", "", "No best strategy is selected.", ""]
    for row in payload["summaries"]:
        if row["spread_points"] == 1.0 and row["slippage_points_per_side"] == 0.0:
            lines.append(
                f"- `{row['experiment_id']}/{row['planning_mode']}` "
                f"episodes=`{row['unique_episode_count']}` "
                f"expectancy=`{row['net_expectancy_points']}`"
            )
    return "\n".join(lines) + "\n"
