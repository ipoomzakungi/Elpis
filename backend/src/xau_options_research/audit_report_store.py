from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


class XauOptionsFeatureAuditReportStore:
    def __init__(self, root: Path) -> None:
        self.root = root

    def persist(self, *, run_id: str, payloads: dict[str, Any], handoff: str) -> Path:
        report_dir = self.root / run_id
        report_dir.mkdir(parents=True, exist_ok=False)
        markdown_names = {
            "feature_semantics_audit",
            "event_independence_audit",
            "clustered_inference_audit",
            "matched_negative_control_report",
            "candidate_manifest_v2",
        }
        for name, payload in payloads.items():
            _write_json(report_dir / f"{name}.json", payload)
            if name in markdown_names:
                (report_dir / f"{name}.md").write_text(_markdown(name, payload), encoding="utf-8")
        (report_dir / "review_handoff.md").write_text(handoff, encoding="utf-8")
        _write_json(
            report_dir / "metadata.json",
            {
                "run_id": run_id,
                "created_at": datetime.now(UTC).isoformat(),
                "report_dir": report_dir.resolve().as_posix(),
                "evidence_status": "insufficient_sample",
                "research_only": True,
                "signal_allowed": False,
            },
        )
        return report_dir


def _write_json(path: Path, payload: Any) -> None:
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _markdown(name: str, payload: dict[str, Any]) -> str:
    title = name.replace("_", " ").title()
    lines = [f"# {title}", "", "Research-only audit. No signal or order permission.", ""]
    if name == "feature_semantics_audit":
        lines.extend(
            [
                f"- OI Change: `{payload['oi_change_status']}`",
                f"- Intraday volume: `{payload['intraday_volume']['semantics']}`",
                "- IV actual updates: "
                f"`{payload['iv_update_semantics']['actual_value_update_count']}`",
                f"- Informative feature count: `{payload['informative_feature_count']}`",
            ]
        )
    elif name == "event_independence_audit":
        lines.extend(
            [
                f"- Raw events: `{payload['raw_event_count']}`",
                f"- Continuous excursions: `{payload['continuous_excursion_count']}`",
                "- Non-overlapping opportunities: "
                f"`{payload['non_overlapping_tradable_opportunity_count']}`",
                f"- Blocked concurrent rows: `{payload['concurrent_position_block_count']}`",
            ]
        )
    elif name == "clustered_inference_audit":
        lines.extend(
            [
                f"- Trials: `{payload['trial_count']}`",
                f"- Resampling unit: `{payload['resampling_unit']}`",
                f"- Consistency violations: `{payload['inference_consistency_violation_count']}`",
            ]
        )
    elif name == "matched_negative_control_report":
        lines.extend(
            [
                f"- MR2 beats matched controls: `{payload['mr2_beats_controls']}`",
                f"- Permutations: `{payload['permutation_iterations']}`",
            ]
        )
    elif name == "candidate_manifest_v2":
        for candidate in payload["candidates"]:
            lines.append(
                f"- `{candidate['candidate_id']}` enabled="
                f"`{candidate['enabled_for_validation_v2']}` hash=`{candidate['candidate_hash']}`"
            )
    lines.extend(["", "research_only=true", "signal_allowed=false"])
    return "\n".join(lines) + "\n"
