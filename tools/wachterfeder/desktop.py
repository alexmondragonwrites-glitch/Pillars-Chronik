#!/usr/bin/env python3
"""Desktop-friendly Wächterfeder pipeline.

The functions in this module combine save inspection and local dialogue parsing
without shelling out to PowerShell. Original saves and game resources stay
untouched; generated data is written below the ignored ``.wachterfeder`` folder.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

try:
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
        write_snapshot,
    )
except ModuleNotFoundError:  # Direct execution from tools/wachterfeder.
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
        write_snapshot,
    )


@dataclass(frozen=True)
class DesktopAnalysisResult:
    savegame: Path
    snapshot_path: Path
    report_path: Path
    history_snapshot_path: Path
    history_report_path: Path
    player_name: str
    scene_title: str
    difficulty: str
    matched_conversations: int
    unresolved_conversations: int
    marked_nodes: int
    warnings: list[str]


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
    stamp = datetime.fromtimestamp(savegame.stat().st_mtime).strftime("%Y%m%d-%H%M%S")
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
    """Inspect a save and create current plus historical local reports."""
    root = (root or repository_root()).expanduser().resolve()
    savegame = savegame.expanduser().resolve()
    local_root = root / ".wachterfeder"
    config_path = local_root / "config.json"
    history_root = local_root / "history"

    assets = _resolve_assets(game_path, language, config_path)
    working_copy = copy_read_only(savegame, local_root / "cache")
    snapshot = inspect_savegame(working_copy)
    key = _history_key(savegame, snapshot)

    snapshot_path = local_root / "serin.snapshot.json"
    history_snapshot_path = history_root / f"{key}.snapshot.json"
    write_snapshot(snapshot, snapshot_path)
    write_snapshot(snapshot, history_snapshot_path)

    snapshot_payload = json.loads(snapshot_path.read_text(encoding="utf-8"))
    report = build_dialogue_report(
        snapshot_payload,
        assets.conversation_root,
        assets.stringtable_root,
    )
    report_path = local_root / f"serin-dialoge-{assets.language}.json"
    history_report_path = history_root / f"{key}.dialoge-{assets.language}.json"
    _write_report(report, report_path)
    _write_report(report, history_report_path)

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
        snapshot_path=snapshot_path,
        report_path=report_path,
        history_snapshot_path=history_snapshot_path,
        history_report_path=history_report_path,
        player_name=player_name,
        scene_title=metadata.scene_title if metadata and metadata.scene_title else "Unbekannt",
        difficulty=metadata.difficulty if metadata and metadata.difficulty else "Unbekannt",
        matched_conversations=int(report["matched_conversations"]),
        unresolved_conversations=len(report["unresolved_conversations"]),
        marked_nodes=marked_nodes,
        warnings=list(snapshot.warnings),
    )
