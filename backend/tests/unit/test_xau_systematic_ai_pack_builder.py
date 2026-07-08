from __future__ import annotations

from src.models.xau_systematic_research import XauSystematicSourceStatus
from src.xau_systematic_research.ai_pack_builder import (
    RESEARCH_ONLY_WARNING,
    XauAiResearchPackBuilder,
)
from src.xau_systematic_research.source_manifest import build_source_manifest
from tests.unit.test_xau_systematic_source_manifest import _state


def test_ai_pack_includes_research_only_warning() -> None:
    state = _state()
    manifest = build_source_manifest(state, ai_pack_status=XauSystematicSourceStatus.AVAILABLE)
    pack, markdown, handoff = XauAiResearchPackBuilder().build(state=state, manifest=manifest)

    assert pack.signal_allowed is False
    assert pack.research_only is True
    assert RESEARCH_ONLY_WARNING in markdown
    assert RESEARCH_ONLY_WARNING in handoff


def test_ai_pack_includes_source_status_table_and_mapped_levels() -> None:
    state = _state()
    manifest = build_source_manifest(state, ai_pack_status=XauSystematicSourceStatus.AVAILABLE)
    pack, markdown, _ = XauAiResearchPackBuilder().build(state=state, manifest=manifest)

    assert pack.source_status_table
    assert pack.mapped_levels_table[0]["mapped_level"] == 4080
    assert "Top Mapped Traded-Side Walls" in markdown
