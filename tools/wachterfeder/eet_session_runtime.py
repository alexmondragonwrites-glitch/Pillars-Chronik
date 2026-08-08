#!/usr/bin/env python3
"""Runtime-aware wrapper around the normal EET session analysis."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Mapping

try:
    from tools.wachterfeder.eet import EetError
    from tools.wachterfeder.eet_combat_logger import (
        log_metadata,
        logger_status,
        read_new_events,
        runtime_log_path,
        summarise_events,
    )
    from tools.wachterfeder.eet_dialogue import resolve_delta_dialogues
    from tools.wachterfeder.eet_session import EetSessionResult, analyse_session as analyse_base_session
except ModuleNotFoundError:  # direct execution from tools/wachterfeder
    from eet import EetError
    from eet_combat_logger import log_metadata, logger_status, read_new_events, runtime_log_path, summarise_events
    from eet_dialogue import resolve_delta_dialogues
    from eet_session import EetSessionResult, analyse_session as analyse_base_session

JsonObject = dict[str, Any]


def _read_json(path: Path) -> JsonObject:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return value if isinstance(value, dict) else {}


def _write_json(path: Path, value: JsonObject) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _cursor_path(root: Path) -> Path:
    return root / ".wachterfeder" / "eet" / "runtime" / "cursor.json"


def _read_cursor(root: Path) -> tuple[bool, int]:
    path = _cursor_path(root)
    data = _read_json(path)
    if not data:
        return False, 0
    try:
        return True, max(0, int(data.get("cursor", 0)))
    except (TypeError, ValueError):
        return True, 0


def _store_cursor(root: Path, metadata: JsonObject) -> None:
    payload = {
        "schema_version": 1,
        "cursor": int(metadata.get("cursor", 0) or 0),
        "size": int(metadata.get("size", 0) or 0),
        "modified_ns": metadata.get("modified_ns"),
    }
    _write_json(_cursor_path(root), payload)


def _config_game_root(root: Path) -> Path | None:
    data = _read_json(root / ".wachterfeder" / "eet" / "config.json")
    value = data.get("game_root")
    return Path(str(value)) if value else None


def _party_identity(item: Mapping[str, Any]) -> str:
    character = item.get("character") if isinstance(item.get("character"), Mapping) else {}
    for value in (
        character.get("death_variable"),
        character.get("dialog"),
        item.get("resource"),
        item.get("name"),
        item.get("index"),
    ):
        text = str(value or "").strip()
        if text and text.casefold() != "none":
            return text
    return "unknown"


def _party_map(snapshot: Mapping[str, Any] | None) -> dict[str, Mapping[str, Any]]:
    result: dict[str, Mapping[str, Any]] = {}
    for item in (snapshot or {}).get("party", []) if isinstance((snapshot or {}).get("party", []), list) else []:
        if isinstance(item, Mapping):
            result[_party_identity(item)] = item
    return result


def _hit_points(item: Mapping[str, Any]) -> int | None:
    character = item.get("character") if isinstance(item.get("character"), Mapping) else {}
    hp = character.get("hit_points") if isinstance(character.get("hit_points"), Mapping) else {}
    try:
        return int(hp.get("current")) if hp.get("current") is not None else None
    except (TypeError, ValueError):
        return None


def _party_runtime_changes(previous: Mapping[str, Any] | None, current: Mapping[str, Any]) -> tuple[JsonObject, list[JsonObject]]:
    old = _party_map(previous)
    new = _party_map(current)
    hp_changes: JsonObject = {}
    conversations: list[JsonObject] = []
    for key in sorted(set(old) & set(new)):
        before_hp = _hit_points(old[key])
        after_hp = _hit_points(new[key])
        if before_hp is not None and after_hp is not None and before_hp != after_hp:
            hp_changes[key] = {
                "name": new[key].get("name") or key,
                "from": before_hp,
                "to": after_hp,
                "delta": after_hp - before_hp,
            }

        try:
            before_talk = int(old[key].get("talk_count", 0) or 0)
            after_talk = int(new[key].get("talk_count", 0) or 0)
        except (TypeError, ValueError):
            continue
        if after_talk > before_talk:
            character = new[key].get("character") if isinstance(new[key].get("character"), Mapping) else {}
            conversations.append(
                {
                    "area": new[key].get("current_area"),
                    "actor": new[key].get("name") or key,
                    "dialog": character.get("dialog"),
                    "from": before_talk,
                    "to": after_talk,
                    "source": "party_cre",
                }
            )
    return hp_changes, conversations


def _augment_party_runtime(delta: JsonObject, previous: Mapping[str, Any] | None, current: Mapping[str, Any]) -> None:
    summary = delta.setdefault("summary", {})
    changes = delta.setdefault("changes", {})
    hp_changes, conversations = _party_runtime_changes(previous, current)
    changes["party_hit_points"] = hp_changes
    changes["party_conversations"] = conversations
    summary["party_hit_point_changes"] = len(hp_changes)
    summary["party_conversations"] = len(conversations)
    if hp_changes or conversations:
        summary["has_changes"] = True


def _augment_combat(delta: JsonObject, events: list[JsonObject], *, initial_runtime_baseline: bool) -> None:
    summary = delta.setdefault("summary", {})
    changes = delta.setdefault("changes", {})
    notes = delta.setdefault("notes", [])
    combat = summarise_events(events)

    summary["combat_events"] = combat["events"]
    summary["combat_damage_events"] = combat["damage_events"]
    summary["combat_damage_total"] = combat["damage_total"]
    summary["combat_lethal_candidates"] = combat["lethal_candidates"]
    summary["combat_logger_errors"] = combat["logger_errors"]
    if events:
        summary["has_changes"] = True
    changes["combat_log"] = events

    if initial_runtime_baseline:
        notes.append(
            "Combat-Logger: erste Laufzeit-Basis erstellt; vorhandene ältere Logzeilen wurden nicht als neue Session-Ereignisse übernommen."
        )
    notes.append(
        "Combat-Logger v1 erfasst tatsächlichen HP-Verlust aus EEex-Damage-Effekten. lethal_candidate bedeutet HP <= 0 nach diesem Effekt und ist noch kein separat bestätigter Tod."
    )


def _augment_dialogues(delta: JsonObject, *, game_path: Path, language: str) -> None:
    summary = delta.setdefault("summary", {})
    changes = delta.setdefault("changes", {})
    notes = delta.setdefault("notes", [])
    try:
        report = resolve_delta_dialogues(delta, game_path=game_path, language=language)
    except (OSError, EetError, ValueError) as exc:
        report = {
            "weidu_available": False,
            "events_considered": 0,
            "high_confidence": 0,
            "medium_confidence": 0,
            "low_confidence": 0,
            "resolved": [],
            "errors": [{"error": str(exc)}],
        }
    changes["dialogue_resolution"] = report
    summary["dialogue_events_considered"] = int(report.get("events_considered", 0) or 0)
    summary["dialogue_high_confidence"] = int(report.get("high_confidence", 0) or 0)
    summary["dialogue_medium_confidence"] = int(report.get("medium_confidence", 0) or 0)
    summary["dialogue_low_confidence"] = int(report.get("low_confidence", 0) or 0)
    notes.append(
        "Dialogauflösung: Nur ein eindeutiger Pfad mit beobachtbarer Save-Evidenz darf confirmed_reply setzen; mehrdeutige Pfade bleiben medium/low."
    )


def analyse_session(
    *,
    save_path: Path | None,
    game_path: Path | None,
    language: str = "de_DE",
    root: Path | None = None,
) -> EetSessionResult:
    root = (root or Path(__file__).resolve().parents[2]).expanduser().resolve()
    snapshot_path = root / ".wachterfeder" / "eet" / "eet.snapshot.json"
    previous_snapshot = _read_json(snapshot_path)
    resolved_game = game_path or _config_game_root(root)

    result = analyse_base_session(
        save_path=save_path,
        game_path=game_path,
        language=language,
        root=root,
    )

    current_snapshot = _read_json(result.snapshot_path)
    delta = _read_json(result.delta_path)
    _augment_party_runtime(delta, previous_snapshot or None, current_snapshot)

    log_path = runtime_log_path(root)
    had_cursor, start_offset = _read_cursor(root)
    if had_cursor:
        events, metadata = read_new_events(log_path, start_offset)
    else:
        events = []
        metadata = log_metadata(log_path)
        metadata["malformed_lines"] = 0
    _augment_combat(delta, events, initial_runtime_baseline=not had_cursor)

    status = None
    if resolved_game is not None:
        try:
            status = logger_status(resolved_game, root=root, language=language)
        except (OSError, EetError):
            status = None
        _augment_dialogues(delta, game_path=resolved_game, language=language)

    current_snapshot["runtime_combat"] = {
        "schema_version": 2,
        "eeex_available": bool(status and status.eeex_available),
        "logger_installed": bool(status and status.installed),
        "enabled": bool(status and status.installed),
        "log_exists": bool(metadata.get("exists")),
        "cursor": int(metadata.get("cursor", 0) or 0),
        "size": int(metadata.get("size", 0) or 0),
        "malformed_lines_since_previous": int(metadata.get("malformed_lines", 0) or 0),
    }
    _write_json(result.snapshot_path, current_snapshot)
    _write_json(result.delta_path, delta)
    _write_json(result.history_delta_path, delta)
    _store_cursor(root, metadata)
    return result
