from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from src.models.xau_options_research import XauOptionsResearchExperiment


def experiment_hash(payload: dict[str, Any]) -> str:
    canonical = {key: value for key, value in payload.items() if key != "experiment_hash"}
    return hashlib.sha256(
        json.dumps(canonical, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()


def load_experiment_registry(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if payload.get("research_only") is not True or payload.get("signal_allowed") is not False:
        raise ValueError("Options experiment registry must remain research-only")
    experiments = []
    for raw in payload.get("experiments", []):
        expected = experiment_hash(raw)
        if raw.get("experiment_hash") != expected:
            raise ValueError(f"Experiment hash mismatch: {raw.get('experiment_id')}")
        experiments.append(XauOptionsResearchExperiment.model_validate(raw))
    if len(experiments) != 7:
        raise ValueError("Registry v1 must contain exactly seven preregistered experiments")
    registry_hash = hashlib.sha256(path.read_bytes()).hexdigest()
    return {
        **payload,
        "experiments": [item.model_dump(mode="json") for item in experiments],
        "registry_hash": registry_hash,
    }
