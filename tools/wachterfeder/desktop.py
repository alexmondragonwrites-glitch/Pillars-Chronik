#!/usr/bin/env python3
"""Desktop-friendly Wächterfeder pipeline.

The functions in this module combine save inspection and local dialogue parsing
without shelling out to PowerShell. Original saves and game resources stay
untouched; generated data is written below the ignored ``.wachterfeder`` folder.
"""
from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path

try:
    from tools.wachterfeder.delta import store_analysis_artifacts
    from tools.wachterfeder.dialogues import build_dialogue_report
    from tools.wachterfeder.local_game import (
        LocalGameAssets,
        read_local_config,
        resolve_local_assets,
        write_local_config,
    )
    from tools.wachterfeder.wachterfeder import (
        SaveSnapshot,
        candidate_save_directories,
        copy_read_only,
        inspect_savegame,
        newest_savegame,
    )
except ModuleNotFoundError:  # Direct execution from tools/wachterfeder.
    from delta import store_analysis_artifacts
    from dialogues import build_dialogue_report
    from local_game import (
        LocalGameAssets,
        read_local_config,
        resolve_local_assets,
        write_local_config,
    )
    from wachterfeder import (
        SaveSnapshot,
        candidate_save_directories,
        copy_read_only,
        inspect_savegame,
        newest_savegame,
    )


@dataclass(frozen=True)
class DesktopAnalysisResult:
    savegame: Path
    snapshot_path: Path
    delta_path: Path
    history_delta_path: Path
    state_report_path: Path
    player_name: str
    scene_title: str
    difficulty: str
    matched_conversations: int
    unresolved_conversations: int
    marked_nodes: int
    initial_snapshot: bool
    has_changes: bool
    new_conversations: int
    new_dialogue_nodes: int
    changed_globals: int
    warnings: list[str]

    @property
    def report_path(self) -> Path:
        """Compatibility alias for callers that opened the former full report."""
        return self.delta_path

    @property
    def history_report_path(self) -> Path:
        """Compatibility alias for the historical compact delta."""
        return self.history_delta_path


def repository_root() -> Path:
    """Return the repository root for a normal checkout."""
    return Path(__file__).resolve().parents[2]


def newest_local_save() -> Path | None:
    """Return the newest save from the usual Windows save directories."""
    return newest_savegame(candidate_save_directories())


def _slug(value: str) -> str:
    normalized = re.sub(r"[^A-Za-z0-9_-]+", "-", value.strip()).strip("-")
    return normalized.casefold() or "save"


def _history_key(savegame: Path, snapshot: SaveSnapshot) -> str:
    stamp = datetime.fromtimestamp(savegame.stat().st_mtime).strftime(
        "%Y%m%d-%H%M%S"
    )
    player_name = "save"
    if snapshot.metadata and snapshot.metadata.player_name:
        player_name = snapshot.metadata.player_name
    elif snapshot.player and snapshot.player.name:
        player_name = snapshot.player.name
    return f"{stamp}-{_slug(player_name)}-{snapshot.sha256[:8]}"


def _resolve_assets(
    game_path: Path | None,
    language: str,
    config_path: Path,
) -> LocalGameAssets:
    if game_path is not None:
        assets = resolve_local_assets(game_path, language)
        write_local_config(assets, config_path)
        return assets
    return read_local_config(config_path)


def _write_report(report: dict, output: Path) -> None:
    """Write JSON for low-level callers that explicitly request a report."""
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def analyse_savegame(
    savegame: Path,
    *,
    game_path: Path | None = None,
    language: str = "de",
    root: Path | None = None,
) -> DesktopAnalysisResult:
    """Inspect a save and write a full current snapshot plus a compact delta."""
    root = (root or repository_root()).expanduser().resolve()
    savegame = savegame.expanduser().resolve()
    local_root = root / ".wachterfeder"
    config_path = local_root / "config.json"

    assets = _resolve_assets(game_path, language, config_path)
    working_copy = copy_read_only(savegame, local_root / "cache")
    snapshot = inspect_savegame(working_copy)
    key = _history_key(savegame, snapshot)
    snapshot_payload = asdict(snapshot)
    report = build_dialogue_report(
        snapshot_payload,
        assets.conversation_root,
        assets.stringtable_root,
    )
    artifacts = store_analysis_artifacts(
        snapshot_payload,
        report,
        local_root=local_root,
        history_key=key,
        language=assets.language,
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
        warnings=list(snapshot.warnings),
    )
