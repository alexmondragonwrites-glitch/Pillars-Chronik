#!/usr/bin/env python3
"""Compact differences between two Wächterfeder analyses.

The complete current save snapshot remains the local comparison baseline. The
large localized dialogue report is kept below ``.wachterfeder/state`` and the
user-facing delta contains only values and dialogue nodes that changed since the
previous successful run.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping

JsonObject = dict[str, Any]
_MISSING = object()


@dataclass(frozen=True)
class DeltaArtifacts:
    snapshot_path: Path
    delta_path: Path
    history_delta_path: Path
    state_report_path: Path
    initial_snapshot: bool
    has_changes: bool
    new_conversations: int
    new_dialogue_nodes: int
    changed_globals: int


def _read_json(path: Path) -> JsonObject | None:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        return None
    return payload if isinstance(payload, dict) else None


def _write_json(payload: JsonObject, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def _flatten(value: Any, prefix: str = "") -> dict[str, Any]:
    if isinstance(value, Mapping):
        flattened: dict[str, Any] = {}
        for key, child in value.items():
            path = f"{prefix}.{key}" if prefix else str(key)
            flattened.update(_flatten(child, path))
        return flattened
    return {prefix: value}


def _field_changes(previous: Any, current: Any) -> JsonObject:
    old_values = _flatten(previous or {})
    new_values = _flatten(current or {})
    changes: JsonObject = {}
    for key in sorted(set(old_values) | set(new_values)):
        old = old_values.get(key, _MISSING)
        new = new_values.get(key, _MISSING)
        if old == new:
            continue
        changes[key] = {
            "from": None if old is _MISSING else old,
            "to": None if new is _MISSING else new,
            "change": (
                "added"
                if old is _MISSING
                else "removed"
                if new is _MISSING
                else "changed"
            ),
        }
    return changes


def _global_changes(previous: JsonObject | None, current: JsonObject) -> JsonObject:
    old_values = (previous or {}).get("global_variables", {})
    new_values = current.get("global_variables", {})
    if not isinstance(old_values, Mapping):
        old_values = {}
    if not isinstance(new_values, Mapping):
        new_values = {}
    changes: JsonObject = {}
    for key in sorted(set(old_values) | set(new_values)):
        old = old_values.get(key, _MISSING)
        new = new_values.get(key, _MISSING)
        if old == new:
            continue
        changes[str(key)] = {
            "from": None if old is _MISSING else old,
            "to": None if new is _MISSING else new,
            "change": (
                "added"
                if old is _MISSING
                else "removed"
                if new is _MISSING
                else "changed"
            ),
        }
    return changes


def _snapshot_conversations(snapshot: JsonObject | None) -> dict[str, set[int]]:
    result: dict[str, set[int]] = {}
    for item in (snapshot or {}).get("marked_conversations", []):
        if not isinstance(item, Mapping):
            continue
        path = str(item.get("path", ""))
        if not path:
            continue
        result[path] = {
            int(node_id) for node_id in item.get("marked_node_ids", [])
        }
    return result


def _marked_conversation_changes(
    previous: JsonObject | None,
    current: JsonObject,
) -> list[JsonObject]:
    old_items = _snapshot_conversations(previous)
    new_items = _snapshot_conversations(current)
    changes: list[JsonObject] = []
    for path in sorted(set(old_items) | set(new_items)):
        added = sorted(new_items.get(path, set()) - old_items.get(path, set()))
        removed = sorted(old_items.get(path, set()) - new_items.get(path, set()))
        if added or removed or path not in old_items:
            changes.append(
                {
                    "path": path,
                    "is_new_conversation": path not in old_items,
                    "new_node_ids": added,
                    "removed_node_ids": removed,
                }
            )
    return changes


def _conversation_key(item: Mapping[str, Any]) -> str:
    package = str(item.get("source_package", "data"))
    name = str(item.get("conversation", ""))
    return f"{package}:{name}"


def _conversation_index(
    report: JsonObject | None,
) -> dict[str, Mapping[str, Any]]:
    result: dict[str, Mapping[str, Any]] = {}
    for item in (report or {}).get("conversations", []):
        if isinstance(item, Mapping):
            result[_conversation_key(item)] = item
    return result


def _edge_set(
    item: Mapping[str, Any] | None,
    field: str,
) -> set[tuple[int, int]]:
    result: set[tuple[int, int]] = set()
    for edge in (item or {}).get(field, []):
        if isinstance(edge, (list, tuple)) and len(edge) == 2:
            result.add((int(edge[0]), int(edge[1])))
    return result


def _new_ambiguous_branches(
    previous: Mapping[str, Any] | None,
    current: Mapping[str, Any],
) -> JsonObject:
    old = (previous or {}).get("ambiguous_branches", {})
    new = current.get("ambiguous_branches", {})
    if not isinstance(old, Mapping):
        old = {}
    if not isinstance(new, Mapping):
        new = {}
    changes: JsonObject = {}
    for node_id, targets in new.items():
        old_targets = old.get(node_id, [])
        added = sorted(
            {int(value) for value in targets}
            - {int(value) for value in old_targets}
        )
        if added:
            changes[str(node_id)] = added
    return changes


def _new_story_scripts(
    previous: Mapping[str, Any] | None,
    current: Mapping[str, Any],
) -> list[JsonObject]:
    def serialised(items: Any) -> dict[str, JsonObject]:
        result: dict[str, JsonObject] = {}
        for item in items if isinstance(items, list) else []:
            if isinstance(item, dict):
                key = json.dumps(item, ensure_ascii=False, sort_keys=True)
                result[key] = item
        return result

    old = serialised((previous or {}).get("story_scripts", []))
    new = serialised(current.get("story_scripts", []))
    return [new[key] for key in sorted(set(new) - set(old))]


def _dialogue_changes(previous: JsonObject | None, current: JsonObject) -> JsonObject:
    old_items = _conversation_index(previous)
    new_items = _conversation_index(current)
    changed: list[JsonObject] = []
    new_conversation_names: list[str] = []
    removed_conversations: list[str] = []
    new_node_total = 0

    for key, item in sorted(new_items.items()):
        old_item = old_items.get(key)
        old_ids = {
            int(value) for value in (old_item or {}).get("marked_node_ids", [])
        }
        new_ids = {int(value) for value in item.get("marked_node_ids", [])}
        added_ids = sorted(new_ids - old_ids)
        removed_ids = sorted(old_ids - new_ids)
        if old_item is None:
            new_conversation_names.append(str(item.get("conversation", key)))
        if not added_ids and not removed_ids and old_item is not None:
            continue

        node_by_id = {
            int(node.get("node_id")): node
            for node in item.get("marked_nodes", [])
            if isinstance(node, dict) and node.get("node_id") is not None
        }
        new_nodes = [
            node_by_id[node_id]
            for node_id in added_ids
            if node_id in node_by_id
        ]
        new_node_total += len(added_ids)
        played = sorted(
            _edge_set(item, "played_edges")
            - _edge_set(old_item, "played_edges")
        )
        deterministic = sorted(
            _edge_set(item, "deterministic_edges")
            - _edge_set(old_item, "deterministic_edges")
        )
        changed.append(
            {
                "conversation": item.get("conversation"),
                "source_package": item.get("source_package", "data"),
                "is_new_conversation": old_item is None,
                "new_node_ids": added_ids,
                "removed_node_ids": removed_ids,
                "new_nodes": new_nodes,
                "new_played_edges": [list(edge) for edge in played],
                "new_deterministic_edges": [
                    list(edge) for edge in deterministic
                ],
                "new_ambiguous_branches": _new_ambiguous_branches(
                    old_item, item
                ),
                "new_story_scripts": _new_story_scripts(old_item, item),
            }
        )

    for key, item in sorted(old_items.items()):
        if key not in new_items:
            removed_conversations.append(str(item.get("conversation", key)))

    old_unresolved = set((previous or {}).get("unresolved_conversations", []))
    new_unresolved = set(current.get("unresolved_conversations", []))
    return {
        "new_conversations": new_conversation_names,
        "removed_conversations": removed_conversations,
        "conversations": changed,
        "new_unresolved_conversations": sorted(
            new_unresolved - old_unresolved
        ),
        "resolved_conversations": sorted(old_unresolved - new_unresolved),
        "new_node_count": new_node_total,
    }


def build_analysis_delta(
    previous_snapshot: JsonObject | None,
    current_snapshot: JsonObject,
    previous_report: JsonObject | None,
    current_report: JsonObject,
    *,
    language: str,
) -> JsonObject:
    """Return a compact, portable delta for one successful analysis run."""
    metadata_changes = _field_changes(
        (previous_snapshot or {}).get("metadata"),
        current_snapshot.get("metadata"),
    )
    player_changes = _field_changes(
        (previous_snapshot or {}).get("player"),
        current_snapshot.get("player"),
    )
    global_changes = _global_changes(previous_snapshot, current_snapshot)
    marked_changes = _marked_conversation_changes(
        previous_snapshot, current_snapshot
    )
    dialogue_changes = _dialogue_changes(previous_report, current_report)
    initial_snapshot = previous_snapshot is None or previous_report is None

    metadata = current_snapshot.get("metadata") or {}
    player = current_snapshot.get("player") or {}
    marked_node_count = sum(
        len(item.get("marked_node_ids", []))
        for item in current_snapshot.get("marked_conversations", [])
        if isinstance(item, Mapping)
    )
    has_changes = bool(
        initial_snapshot
        or metadata_changes
        or player_changes
        or global_changes
        or marked_changes
        or dialogue_changes["conversations"]
        or dialogue_changes["removed_conversations"]
        or dialogue_changes["new_unresolved_conversations"]
        or dialogue_changes["resolved_conversations"]
    )

    return {
        "schema_version": 1,
        "kind": "wachterfeder-delta",
        "created_utc": datetime.now(tz=timezone.utc).isoformat(),
        "language": language,
        "initial_snapshot": initial_snapshot,
        "previous_save_sha256": (previous_snapshot or {}).get("sha256"),
        "current_save_sha256": current_snapshot.get("sha256"),
        "summary": {
            "has_changes": has_changes,
            "metadata_changes": len(metadata_changes),
            "player_changes": len(player_changes),
            "changed_globals": len(global_changes),
            "changed_marked_conversations": len(marked_changes),
            "new_conversations": len(dialogue_changes["new_conversations"]),
            "conversations_with_node_changes": len(
                dialogue_changes["conversations"]
            ),
            "new_dialogue_nodes": dialogue_changes["new_node_count"],
        },
        "current_state": {
            "player_name": metadata.get("player_name") or player.get("name"),
            "level": player.get("level"),
            "experience": player.get("experience"),
            "map_name": metadata.get("map_name"),
            "scene_title": metadata.get("scene_title"),
            "difficulty": metadata.get("difficulty"),
            "matched_conversations": current_report.get(
                "matched_conversations", 0
            ),
            "unresolved_conversations": current_report.get(
                "unresolved_conversations", []
            ),
            "marked_nodes": marked_node_count,
        },
        "save_changes": {
            "metadata": metadata_changes,
            "player": player_changes,
            "global_variables": global_changes,
            "marked_conversations": marked_changes,
        },
        "dialogue_changes": dialogue_changes,
        "notes": [
            "Nur neue oder geänderte Werte und Dialogknoten sind enthalten.",
            "Der vollständige Dialogreport bleibt ausschließlich als lokale Vergleichsbasis unter .wachterfeder/state.",
            "MarkedAsRead belegt gelesene Knoten, aber keine lückenlose Chronologie bei wiederholbaren Gesprächen.",
        ],
    }


def store_analysis_artifacts(
    current_snapshot: JsonObject,
    current_report: JsonObject,
    *,
    local_root: Path,
    history_key: str,
    language: str,
) -> DeltaArtifacts:
    """Write the current snapshot plus a compact delta and rotate baselines."""
    local_root = local_root.expanduser().resolve()
    snapshot_path = local_root / "serin.snapshot.json"
    delta_path = local_root / "serin.delta.json"
    history_delta_path = (
        local_root / "history" / f"{history_key}.delta.json"
    )
    state_report_path = (
        local_root / "state" / f"serin-dialoge-{language}.json"
    )
    legacy_report_path = local_root / f"serin-dialoge-{language}.json"

    previous_snapshot = _read_json(snapshot_path)
    previous_report = _read_json(state_report_path) or _read_json(
        legacy_report_path
    )
    delta = build_analysis_delta(
        previous_snapshot,
        current_snapshot,
        previous_report,
        current_report,
        language=language,
    )

    _write_json(current_snapshot, snapshot_path)
    _write_json(current_report, state_report_path)
    _write_json(delta, delta_path)
    _write_json(delta, history_delta_path)

    # Migrate the formerly user-facing full report after it became the private
    # baseline. Failure to remove it must not invalidate a successful run.
    if legacy_report_path.is_file() and legacy_report_path != state_report_path:
        try:
            legacy_report_path.unlink()
        except OSError:
            pass

    summary = delta["summary"]
    return DeltaArtifacts(
        snapshot_path=snapshot_path,
        delta_path=delta_path,
        history_delta_path=history_delta_path,
        state_report_path=state_report_path,
        initial_snapshot=bool(delta["initial_snapshot"]),
        has_changes=bool(summary["has_changes"]),
        new_conversations=int(summary["new_conversations"]),
        new_dialogue_nodes=int(summary["new_dialogue_nodes"]),
        changed_globals=int(summary["changed_globals"]),
    )
