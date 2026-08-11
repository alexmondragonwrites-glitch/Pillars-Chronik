#!/usr/bin/env python3
"""Runtime entrypoint for enhanced CK3 analysis with safe schema migration."""
from __future__ import annotations

from pathlib import Path

try:
    import tools.wachterfeder.ck3_enhanced as core
except ModuleNotFoundError:  # Direct execution from tools/wachterfeder.
    import ck3_enhanced as core

Ck3Error = core.Ck3Error
Ck3AnalysisResult = core.Ck3AnalysisResult
candidate_ck3_save_roots = core.candidate_ck3_save_roots
newest_ck3_save = core.newest_ck3_save
resolve_ck3_save = core.resolve_ck3_save
inspect_ck3_envelope = core.inspect_ck3_envelope
fallback_metadata = core.fallback_metadata
find_rakaly = core.find_rakaly
remember_rakaly = core.remember_rakaly
rakaly_version = core.rakaly_version
normalize_ck3_state = core.normalize_ck3_state
build_ck3_snapshot = core.build_ck3_snapshot
clean_ck3_text = core.clean_ck3_text

_ORIGINAL_BUILD_DELTA = core.build_ck3_delta


def build_ck3_delta(previous, current):
    old_schema = previous.get("schema_version") if isinstance(previous, dict) else None
    new_schema = current.get("schema_version") if isinstance(current, dict) else None
    if previous is not None and old_schema != new_schema:
        # Build the current-state shell without comparing differently shaped
        # parser output. This prevents parser improvements from masquerading as
        # historical events in the user's campaign.
        delta = _ORIGINAL_BUILD_DELTA(None, current)
        delta["initial_snapshot"] = False
        delta["previous_save_sha256"] = previous.get("sha256")
        summary = delta.get("summary", {})
        summary["schema_migration"] = {"from": old_schema, "to": new_schema}
        summary["headline_state_changes"] = 0
        summary["timeline_candidates"] = 0
        summary["timeline_by_type"] = {}
        delta["changes"] = {"headline_state": {}, "timeline_candidates": []}
        notes = list(delta.get("notes", []))
        notes.insert(
            0,
            "Parser-Schemamigration: Der aktuelle Save wurde als neue Vergleichsbasis übernommen; aus der Parseränderung wurden keine Timeline-Ereignisse erzeugt.",
        )
        delta["notes"] = notes
        return delta
    return _ORIGINAL_BUILD_DELTA(previous, current)


# analyse_ck3_save resolves build_ck3_delta from its module globals at runtime.
# Patch only that hook while reusing the tested read-only analysis pipeline.
core.build_ck3_delta = build_ck3_delta


def analyse_ck3_save(
    save_path: Path,
    *,
    rakaly_path: Path | None = None,
    root: Path | None = None,
) -> Ck3AnalysisResult:
    return core.analyse_ck3_save(save_path, rakaly_path=rakaly_path, root=root)
