#!/usr/bin/env python3
"""Desktop analysis with base-game and expansion dialogue packages plus deltas."""
from __future__ import annotations

from dataclasses import asdict
from pathlib import Path

try:
    from tools.wachterfeder.delta import store_analysis_artifacts
    from tools.wachterfeder.desktop import (
        DesktopAnalysisResult,
        _history_key,
        repository_root,
    )
    from tools.wachterfeder.expansion_assets import (
        _resolve_packages,
        build_expanded_dialogue_report,
    )
    from tools.wachterfeder.wachterfeder import copy_read_only, inspect_savegame
except ModuleNotFoundError:  # Direct execution from tools/wachterfeder.
    from delta import store_analysis_artifacts
    from desktop import DesktopAnalysisResult, _history_key, repository_root
    from expansion_assets import _resolve_packages, build_expanded_dialogue_report
    from wachterfeder import copy_read_only, inspect_savegame


def analyse_savegame(
    savegame: Path,
    *,
    game_path: Path | None = None,
    language: str = "de",
    root: Path | None = None,
) -> DesktopAnalysisResult:
    """Analyse one save across all installed dialogue packages.

    The current full snapshot is overwritten as the next comparison baseline.
    The localized full report is stored privately below ``.wachterfeder/state``;
    the user-facing ``serin.delta.json`` contains only changes since the previous
    successful run.
    """
    root = (root or repository_root()).expanduser().resolve()
    savegame = savegame.expanduser().resolve()
    local_root = root / ".wachterfeder"
    config_path = local_root / "config.json"

    packages = _resolve_packages(game_path, language, config_path)
    working_copy = copy_read_only(savegame, local_root / "cache")
    snapshot = inspect_savegame(working_copy)
    snapshot_payload = asdict(snapshot)
    report = build_expanded_dialogue_report(snapshot_payload, packages)
    key = _history_key(savegame, snapshot)
    artifacts = store_analysis_artifacts(
        snapshot_payload,
        report,
        local_root=local_root,
        history_key=key,
        language=language,
    )

    metadata = snapshot.metadata
    player_name = (
        metadata.player_name
        if metadata and metadata.player_name
        else snapshot.player.name
        if snapshot.player
        else savegame.stem
    )
    marked_nodes = sum(
        len(item.marked_node_ids) for item in snapshot.marked_conversations
    )
    warnings = list(snapshot.warnings)
    package_names = ", ".join(package.name for package in packages)
    warnings.append(f"Dialogpakete: {package_names}")
    if artifacts.initial_snapshot:
        warnings.append(
            "Erste Vergleichsbasis: Dieses Delta kann noch den vollständigen Ausgangsstand enthalten."
        )
    elif not artifacts.has_changes:
        warnings.append("Seit der letzten Auswertung wurden keine Änderungen erkannt.")

    return DesktopAnalysisResult(
        savegame=savegame,
        snapshot_path=artifacts.snapshot_path,
        delta_path=artifacts.delta_path,
        history_delta_path=artifacts.history_delta_path,
        state_report_path=artifacts.state_report_path,
        player_name=player_name,
        scene_title=(
            metadata.scene_title
            if metadata and metadata.scene_title
            else "Unbekannt"
        ),
        difficulty=(
            metadata.difficulty
            if metadata and metadata.difficulty
            else "Unbekannt"
        ),
        matched_conversations=int(report["matched_conversations"]),
        unresolved_conversations=len(report["unresolved_conversations"]),
        marked_nodes=marked_nodes,
        initial_snapshot=artifacts.initial_snapshot,
        has_changes=artifacts.has_changes,
        new_conversations=artifacts.new_conversations,
        new_dialogue_nodes=artifacts.new_dialogue_nodes,
        changed_globals=artifacts.changed_globals,
        warnings=warnings,
    )
