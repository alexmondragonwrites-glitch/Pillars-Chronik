#!/usr/bin/env python3
"""Resolve and analyse dialogue assets from the base game and all expansions.

Pillars stores dialogue resources in sibling folders such as ``data``,
``data_expansion1``, ``data_expansion2`` and ``data_expansion4``.  This module
keeps those resources local and joins the correct graph with the matching
localized stringtable.
"""
from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Iterable, Sequence

try:
    from tools.wachterfeder.desktop import (
        DesktopAnalysisResult,
        _history_key,
        _write_report,
        repository_root,
    )
    from tools.wachterfeder.dialogues import (
        build_marked_report,
        parse_conversation,
        parse_stringtable,
    )
    from tools.wachterfeder.local_game import (
        LocalGameAssets,
        read_local_config,
        resolve_local_assets,
        write_local_config,
    )
    from tools.wachterfeder.wachterfeder import (
        copy_read_only,
        inspect_savegame,
        write_snapshot,
    )
except ModuleNotFoundError:  # Direct execution from tools/wachterfeder.
    from desktop import DesktopAnalysisResult, _history_key, _write_report, repository_root
    from dialogues import build_marked_report, parse_conversation, parse_stringtable
    from local_game import LocalGameAssets, read_local_config, resolve_local_assets, write_local_config
    from wachterfeder import copy_read_only, inspect_savegame, write_snapshot


@dataclass(frozen=True)
class DialogueAssetPackage:
    """One local Pillars data package with graphs and optional localized text."""

    name: str
    data_root: Path
    conversation_root: Path
    stringtable_root: Path | None


def _package_sort_key(path: Path) -> tuple[int, str]:
    name = path.name.casefold()
    if name == "data":
        return (0, name)
    return (1, name)


def discover_asset_packages(
    path: Path,
    language: str = "de",
) -> tuple[LocalGameAssets, list[DialogueAssetPackage]]:
    """Find the base game and every installed ``data_expansion*`` package.

    ``path`` may point at the game root, the base ``data`` folder or any deeper
    folder already accepted by :func:`resolve_local_assets`.
    """
    base_assets = resolve_local_assets(path, language)
    pillars_data_root = base_assets.data_root.parent

    package_roots = [base_assets.data_root]
    package_roots.extend(
        candidate
        for candidate in pillars_data_root.iterdir()
        if candidate.is_dir()
        and candidate.name.casefold().startswith("data_expansion")
    )

    packages: list[DialogueAssetPackage] = []
    seen: set[str] = set()
    for data_root in sorted(package_roots, key=_package_sort_key):
        key = str(data_root.resolve()).casefold()
        if key in seen:
            continue
        seen.add(key)

        conversation_root = data_root / "conversations"
        if not conversation_root.is_dir():
            continue
        stringtable_root = (
            data_root / "localized" / language / "text" / "conversations"
        )
        packages.append(
            DialogueAssetPackage(
                name=data_root.name,
                data_root=data_root,
                conversation_root=conversation_root,
                stringtable_root=stringtable_root if stringtable_root.is_dir() else None,
            )
        )

    if not packages:
        # Normally impossible because resolve_local_assets already validated base data.
        raise RuntimeError("Keine lokalen Dialogpakete gefunden.")
    return base_assets, packages


def _normalised_parts(value: str) -> tuple[str, ...]:
    return tuple(part for part in value.replace("\\", "/").split("/") if part)


def _package_hint(save_path: str) -> str | None:
    for part in _normalised_parts(save_path):
        folded = part.casefold()
        if folded == "data" or folded.startswith("data_expansion"):
            return folded
    return None


def _relative_dialogue_parts(save_path: str) -> tuple[str, ...]:
    parts = _normalised_parts(save_path)
    folded = [part.casefold() for part in parts]
    if "conversations" in folded:
        index = folded.index("conversations")
        return parts[index + 1 :]
    return parts


def _dedupe_candidates(
    candidates: Iterable[tuple[DialogueAssetPackage, Path]],
) -> list[tuple[DialogueAssetPackage, Path]]:
    result: list[tuple[DialogueAssetPackage, Path]] = []
    seen: set[str] = set()
    for package, path in candidates:
        key = str(path.resolve()).casefold()
        if key not in seen:
            seen.add(key)
            result.append((package, path))
    return result


def _conversation_candidates(
    packages: Sequence[DialogueAssetPackage],
    save_path: str,
) -> list[tuple[DialogueAssetPackage, Path]]:
    relative = _relative_dialogue_parts(save_path)
    basename = Path(save_path.replace("\\", "/")).name
    candidates: list[tuple[DialogueAssetPackage, Path]] = []

    for package in packages:
        if relative:
            direct = package.conversation_root.joinpath(*relative)
            if direct.is_file():
                candidates.append((package, direct))
        direct_name = package.conversation_root / basename
        if direct_name.is_file():
            candidates.append((package, direct_name))
        for match in package.conversation_root.rglob(basename):
            candidates.append((package, match))
    return _dedupe_candidates(candidates)


def _choose_conversation(
    packages: Sequence[DialogueAssetPackage],
    save_path: str,
    marked_ids: Iterable[int],
) -> tuple[DialogueAssetPackage, Path] | None:
    candidates = _conversation_candidates(packages, save_path)
    if not candidates:
        return None
    if len(candidates) == 1:
        return candidates[0]

    hint = _package_hint(save_path)
    if hint:
        hinted = [item for item in candidates if item[0].name.casefold() == hint]
        if len(hinted) == 1:
            return hinted[0]
        if hinted:
            candidates = hinted

    marked = {int(node_id) for node_id in marked_ids}
    coverage: list[tuple[int, tuple[DialogueAssetPackage, Path]]] = []
    for candidate in candidates:
        graph = parse_conversation(candidate[1])
        missing_count = len(marked.difference(graph.nodes))
        coverage.append((missing_count, candidate))

    best_missing = min(item[0] for item in coverage)
    best = [candidate for missing, candidate in coverage if missing == best_missing]
    return best[0] if len(best) == 1 else None


def _find_matching_stringtable(
    package: DialogueAssetPackage,
    conversation_path: Path,
    packages: Sequence[DialogueAssetPackage],
) -> Path | None:
    target_name = conversation_path.with_suffix(".stringtable").name

    if package.stringtable_root is not None:
        try:
            relative = conversation_path.relative_to(package.conversation_root)
        except ValueError:
            relative = Path(target_name)
        direct = package.stringtable_root / relative.with_suffix(".stringtable")
        if direct.is_file():
            return direct
        same_package = list(package.stringtable_root.rglob(target_name))
        if len(same_package) == 1:
            return same_package[0]

    all_matches: list[Path] = []
    for candidate_package in packages:
        if candidate_package.stringtable_root is not None:
            all_matches.extend(candidate_package.stringtable_root.rglob(target_name))
    unique = {str(path.resolve()).casefold(): path for path in all_matches}
    return next(iter(unique.values())) if len(unique) == 1 else None


def build_expanded_dialogue_report(
    snapshot: dict,
    packages: Sequence[DialogueAssetPackage],
) -> dict:
    """Join marked save nodes with the matching base-game or expansion assets."""
    reports: list[dict] = []
    unresolved: list[str] = []

    for item in snapshot.get("marked_conversations", []):
        save_path = str(item.get("path", ""))
        marked_ids = item.get("marked_node_ids", [])
        selected = _choose_conversation(packages, save_path, marked_ids)
        if selected is None:
            unresolved.append(save_path)
            continue

        package, conversation_path = selected
        string_path = _find_matching_stringtable(package, conversation_path, packages)
        strings = parse_stringtable(string_path) if string_path else None
        graph = parse_conversation(conversation_path, strings)
        report = asdict(build_marked_report(graph, marked_ids))
        report["source_package"] = package.name
        report["stringtable_path"] = str(string_path) if string_path else None
        reports.append(report)

    conversation_roots = [str(package.conversation_root.resolve()) for package in packages]
    stringtable_roots = [
        str(package.stringtable_root.resolve())
        for package in packages
        if package.stringtable_root is not None
    ]
    return {
        "schema_version": 2,
        "save_sha256": snapshot.get("sha256"),
        # Legacy singular fields remain for existing consumers.
        "conversation_root": conversation_roots[0] if conversation_roots else None,
        "stringtable_root": stringtable_roots[0] if stringtable_roots else None,
        "conversation_roots": conversation_roots,
        "stringtable_roots": stringtable_roots,
        "asset_packages": [
            {
                "name": package.name,
                "data_root": str(package.data_root.resolve()),
                "localized_text_available": package.stringtable_root is not None,
            }
            for package in packages
        ],
        "matched_conversations": len(reports),
        "unresolved_conversations": unresolved,
        "localized_text_available": bool(stringtable_roots),
        "conversations": reports,
    }


def _resolve_packages(
    game_path: Path | None,
    language: str,
    config_path: Path,
) -> list[DialogueAssetPackage]:
    if game_path is not None:
        base_assets, packages = discover_asset_packages(game_path, language)
        write_local_config(base_assets, config_path)
        return packages

    base_assets = read_local_config(config_path)
    _, packages = discover_asset_packages(base_assets.data_root, base_assets.language)
    return packages


def analyse_savegame(
    savegame: Path,
    *,
    game_path: Path | None = None,
    language: str = "de",
    root: Path | None = None,
) -> DesktopAnalysisResult:
    """Desktop pipeline including every installed Pillars dialogue package."""
    root = (root or repository_root()).expanduser().resolve()
    savegame = savegame.expanduser().resolve()
    local_root = root / ".wachterfeder"
    config_path = local_root / "config.json"
    history_root = local_root / "history"

    packages = _resolve_packages(game_path, language, config_path)
    working_copy = copy_read_only(savegame, local_root / "cache")
    snapshot = inspect_savegame(working_copy)
    key = _history_key(savegame, snapshot)

    snapshot_path = local_root / "serin.snapshot.json"
    history_snapshot_path = history_root / f"{key}.snapshot.json"
    write_snapshot(snapshot, snapshot_path)
    write_snapshot(snapshot, history_snapshot_path)

    snapshot_payload = json.loads(snapshot_path.read_text(encoding="utf-8"))
    report = build_expanded_dialogue_report(snapshot_payload, packages)
    report_path = local_root / f"serin-dialoge-{language}.json"
    history_report_path = history_root / f"{key}.dialoge-{language}.json"
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
    warnings = list(snapshot.warnings)
    package_names = ", ".join(package.name for package in packages)
    warnings.append(f"Dialogpakete: {package_names}")

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
        warnings=warnings,
    )
