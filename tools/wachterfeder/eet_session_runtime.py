#!/usr/bin/env python3
"""Combat-aware wrapper around the normal EET session analysis."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

try:
    from tools.wachterfeder.eet_combat_logger import (
        log_metadata,
        read_new_events,
        runtime_log_path,
        summarise_events,
    )
    from tools.wachterfeder.eet_session import EetSessionResult, analyse_session as analyse_base_session
except ModuleNotFoundError:  # direct execution from tools/wachterfeder
    from eet_combat_logger import log_metadata, read_new_events, runtime_log_path, summarise_events
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


def _augment_delta(delta: JsonObject, events: list[JsonObject], *, initial_runtime_baseline: bool) -> JsonObject:
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
    return delta


def analyse_session(
    *,
    save_path: Path | None,
    game_path: Path | None,
    language: str = "de_DE",
    root: Path | None = None,
) -> EetSessionResult:
    root = (root or Path(__file__).resolve().parents[2]).expanduser().resolve()

    result = analyse_base_session(
        save_path=save_path,
        game_path=game_path,
        language=language,
        root=root,
    )

    log_path = runtime_log_path(root)
    had_cursor, start_offset = _read_cursor(root)
    if had_cursor:
        events, metadata = read_new_events(log_path, start_offset)
    else:
        events = []
        metadata = log_metadata(log_path)
        metadata["malformed_lines"] = 0

    snapshot = _read_json(result.snapshot_path)
    snapshot["runtime_combat"] = {
        "schema_version": 1,
        "enabled": bool(metadata.get("exists")),
        "cursor": int(metadata.get("cursor", 0) or 0),
        "size": int(metadata.get("size", 0) or 0),
        "malformed_lines_since_previous": int(metadata.get("malformed_lines", 0) or 0),
    }
    _write_json(result.snapshot_path, snapshot)

    delta = _read_json(result.delta_path)
    delta = _augment_delta(delta, events, initial_runtime_baseline=not had_cursor)
    _write_json(result.delta_path, delta)
    _write_json(result.history_delta_path, delta)
    _store_cursor(root, metadata)
    return result
