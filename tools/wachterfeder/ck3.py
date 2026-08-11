#!/usr/bin/env python3
"""Crusader Kings III adapter for Wächterfeder.

The adapter is read-only. It can always inspect CK3's save envelope and metadata
without third-party packages. Deep world-state analysis uses the small Rakaly
CLI when available; Wächterfeder then keeps only a compact, normalized slice
around the player instead of copying the full CK3 world into JSON history.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import subprocess
import tempfile
import zipfile
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping, Sequence

JsonObject = dict[str, Any]
_MISSING = object()
RANK_WEIGHT = {"b": 1, "c": 2, "d": 3, "k": 4, "e": 5}
MAX_RAW_STRING_PREVIEW = 120
MAX_EVENT_REFERENCES = 300
MAX_MEMORY_REFERENCES = 200


class Ck3Error(RuntimeError):
    """Expected, user-facing CK3 adapter error."""


@dataclass(frozen=True)
class Ck3AnalysisResult:
    save_file: Path
    snapshot_path: Path
    delta_path: Path
    history_delta_path: Path
    initial_snapshot: bool
    has_changes: bool
    deep_analysis: bool
    game_version: str | None
    player_name: str | None
    primary_title: str | None
    family_members: int
    vassals: int
    event_changes: int
    rakaly_path: Path | None


def sha256_file(path: Path, chunk_size: int = 1024 * 1024) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(chunk_size):
            digest.update(chunk)
    return digest.hexdigest()


def candidate_ck3_save_roots(home: Path | None = None) -> list[Path]:
    home = home or Path.home()
    candidates = [home / "Documents" / "Paradox Interactive" / "Crusader Kings III" / "save games"]
    onedrive = os.environ.get("OneDrive")
    if onedrive:
        candidates.append(Path(onedrive) / "Documents" / "Paradox Interactive" / "Crusader Kings III" / "save games")

    for steam in (Path(r"C:\Program Files (x86)\Steam"), Path(r"C:\Program Files\Steam")):
        userdata = steam / "userdata"
        if userdata.is_dir():
            for account in userdata.iterdir():
                candidates.append(account / "1158310" / "remote" / "save games")

    unique: list[Path] = []
    seen: set[str] = set()
    for path in candidates:
        key = str(path).casefold()
        if key not in seen:
            seen.add(key)
            unique.append(path)
    return unique


def newest_ck3_save(save_roots: Sequence[Path] | None = None) -> Path | None:
    saves: list[Path] = []
    for root in save_roots or candidate_ck3_save_roots():
        if root.is_dir():
            saves.extend(path for path in root.rglob("*.ck3") if path.is_file())
    return max(saves, key=lambda path: path.stat().st_mtime, default=None)


def resolve_ck3_save(path: Path) -> Path:
    path = path.expanduser().resolve()
    if path.is_file() and path.suffix.casefold() == ".ck3":
        return path
    if path.is_dir():
        matches = [item for item in path.rglob("*.ck3") if item.is_file()]
        if matches:
            return max(matches, key=lambda item: item.stat().st_mtime)
    raise Ck3Error(f"Kein CK3-.ck3-Spielstand gefunden: {path}")


def _zip_offset(payload: bytes) -> int | None:
    offset = payload.find(b"PK\x03\x04", 0, min(len(payload), 4096))
    return offset if offset >= 0 else None


def inspect_ck3_envelope(save_file: Path) -> JsonObject:
    payload = save_file.read_bytes()
    header = payload[:128].split(b"\n", 1)[0].decode("ascii", errors="replace")
    offset = _zip_offset(payload)
    result: JsonObject = {
        "header": header,
        "compressed": offset is not None,
        "zip_offset": offset,
        "members": [],
        "meta_size": None,
        "gamestate_size": None,
    }
    if offset is None:
        return result

    try:
        import io
        with zipfile.ZipFile(io.BytesIO(payload[offset:])) as archive:
            bad = archive.testzip()
            if bad:
                raise Ck3Error(f"CK3-Archiv ist beschädigt (CRC): {bad}")
            names = archive.namelist()
            result["members"] = names
            if "meta" in names:
                result["meta_size"] = archive.getinfo("meta").file_size
            if "gamestate" in names:
                result["gamestate_size"] = archive.getinfo("gamestate").file_size
    except (zipfile.BadZipFile, OSError) as exc:
        raise Ck3Error(f"CK3-Spielstand konnte nicht als Archiv gelesen werden: {exc}") from exc
    return result


def _envelope_member(save_file: Path, member: str) -> bytes | None:
    payload = save_file.read_bytes()
    offset = _zip_offset(payload)
    if offset is None:
        return payload if member == "gamestate" else None
    import io
    with zipfile.ZipFile(io.BytesIO(payload[offset:])) as archive:
        if member not in archive.namelist():
            return None
        return archive.read(member)


def _printable_strings(payload: bytes, min_length: int = 5) -> list[str]:
    values: list[str] = []
    current = bytearray()
    for byte in payload:
        if 32 <= byte <= 126 or byte >= 0xC2:
            current.append(byte)
        else:
            if len(current) >= min_length:
                try:
                    text = current.decode("utf-8")
                except UnicodeDecodeError:
                    text = current.decode("latin-1", errors="ignore")
                text = text.strip()
                if text:
                    values.append(text)
            current.clear()
        if len(values) >= 5000:
            break
    if len(current) >= min_length:
        try:
            values.append(current.decode("utf-8").strip())
        except UnicodeDecodeError:
            pass
    return values


def fallback_metadata(save_file: Path) -> JsonObject:
    payload = _envelope_member(save_file, "meta") or _envelope_member(save_file, "gamestate") or b""
    strings = _printable_strings(payload)
    version = next((s for s in strings if re.fullmatch(r"\d+\.\d+\.\d+(?:\.\d+)?", s)), None)
    rank_words = ("Jarl ", "King ", "Queen ", "Duke ", "Duchess ", "Count ", "Countess ", "Emperor ", "Empress ")
    player_name = next((s for s in strings if s.startswith(rank_words) and 4 < len(s) < 100), None)
    primary_title = None
    if player_name:
        try:
            start = strings.index(player_name)
            primary_title = next((s for s in strings[start + 1 : start + 8] if 4 < len(s) < 120 and not s.startswith("pattern_")), None)
        except ValueError:
            pass
    return {
        "game_version": version,
        "player_name": player_name,
        "primary_title_name": primary_title,
        "string_preview": strings[:MAX_RAW_STRING_PREVIEW],
    }


def find_rakaly(explicit: Path | None = None, root: Path | None = None) -> Path | None:
    candidates: list[Path] = []
    if explicit:
        candidates.append(explicit.expanduser())
    env = os.environ.get("WACHTERFEDER_RAKALY")
    if env:
        candidates.append(Path(env))
    if root:
        candidates.extend([root / "tools" / "wachterfeder" / "bin" / "rakaly.exe", root / "tools" / "wachterfeder" / "bin" / "rakaly"])
    located = shutil.which("rakaly") or shutil.which("rakaly.exe")
    if located:
        candidates.append(Path(located))
    for candidate in candidates:
        try:
            resolved = candidate.resolve()
        except OSError:
            continue
        if resolved.is_file():
            return resolved
    return None


def load_ck3_json(save_file: Path, rakaly: Path) -> JsonObject:
    if not rakaly.is_file():
        raise Ck3Error(f"Rakaly wurde nicht gefunden: {rakaly}")
    with tempfile.TemporaryDirectory(prefix="wachterfeder-ck3-") as temporary:
        work = Path(temporary)
        copied = work / save_file.name
        shutil.copy2(save_file, copied)
        output = work / "save.json"
        command = [str(rakaly), "json", "--duplicate-keys", "group", str(copied)]
        with output.open("wb") as handle:
            completed = subprocess.run(command, stdout=handle, stderr=subprocess.PIPE, timeout=240, check=False)
        if completed.returncode != 0 or output.stat().st_size == 0:
            message = completed.stderr.decode("utf-8", errors="replace")[-2000:]
            raise Ck3Error("Rakaly konnte den CK3-Save nicht in JSON umwandeln. Bei einer neuen CK3-Version muss Rakaly ggf. aktualisiert werden.\n" + message)
        try:
            with output.open("r", encoding="utf-8") as handle:
                value = json.load(handle)
        except (OSError, json.JSONDecodeError) as exc:
            raise Ck3Error(f"Rakaly-Ausgabe konnte nicht gelesen werden: {exc}") from exc
    if not isinstance(value, dict):
        raise Ck3Error("Rakaly lieferte keinen erwarteten JSON-Wurzelblock.")
    return value


def _dict(value: Any) -> dict[str, Any]:
    return dict(value) if isinstance(value, Mapping) else {}


def _list(value: Any) -> list[Any]:
    if value is None:
        return []
    if isinstance(value, list):
        return value
    if isinstance(value, tuple):
        return list(value)
    return [value]


def _id(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, (str, int)):
        return str(value)
    return None


def _mapping_records(value: Any) -> dict[str, JsonObject]:
    records: dict[str, JsonObject] = {}
    if isinstance(value, Mapping):
        for key, item in value.items():
            if isinstance(item, Mapping):
                records[str(key)] = dict(item)
            elif isinstance(item, list):
                for index, child in enumerate(item):
                    if isinstance(child, Mapping):
                        child_id = _id(child.get("id") or child.get("identity") or child.get("index"))
                        records[child_id or f"{key}:{index}"] = dict(child)
    elif isinstance(value, list):
        for index, item in enumerate(value):
            if isinstance(item, Mapping):
                item_id = _id(item.get("id") or item.get("identity") or item.get("index"))
                records[item_id or str(index)] = dict(item)
    return records


def _unwrap_gamestate(raw: JsonObject) -> JsonObject:
    for key in ("gamestate", "game_state", "state"):
        value = raw.get(key)
        if isinstance(value, Mapping):
            return dict(value)
    return raw


def _player_id(state: JsonObject) -> str | None:
    for value in _list(state.get("currently_played_characters")):
        ident = _id(value)
        if ident:
            return ident
    for item in _list(state.get("played_character")):
        if isinstance(item, Mapping):
            ident = _id(item.get("character"))
            if ident:
                return ident
    return None


def _characters(state: JsonObject) -> dict[str, JsonObject]:
    result = _mapping_records(state.get("living"))
    result.update({key: value for key, value in _mapping_records(state.get("dead_unprunable")).items() if key not in result})
    chars = _dict(state.get("characters"))
    result.update({key: value for key, value in _mapping_records(chars.get("dead_prunable")).items() if key not in result})
    return result


def _titles(state: JsonObject) -> dict[str, JsonObject]:
    block = _dict(state.get("landed_titles"))
    return _mapping_records(block.get("landed_titles") if block else state.get("landed_titles"))


def _title_summary(index: str, title: Mapping[str, Any]) -> JsonObject:
    return {
        "index": index,
        "key": title.get("key"),
        "name": title.get("name") or title.get("localization_key"),
        "holder": _id(title.get("holder")),
        "de_facto_liege": _id(title.get("de_facto_liege")),
        "de_jure_liege": _id(title.get("de_jure_liege")),
        "capital": title.get("capital"),
        "heirs": [_id(item) for item in _list(title.get("heir")) if _id(item)],
        "claims": [_id(item) for item in _list(title.get("claim")) if _id(item)],
    }


def _character_summary(char_id: str, char: Mapping[str, Any], titles: Mapping[str, JsonObject]) -> JsonObject:
    family = _dict(char.get("family_data"))
    alive = _dict(char.get("alive_data"))
    landed = _dict(char.get("landed_data"))
    held = [_title_summary(index, title) for index, title in titles.items() if _id(title.get("holder")) == char_id]
    held.sort(key=lambda item: RANK_WEIGHT.get(str(item.get("key") or "")[:1], 0), reverse=True)
    spouses: list[str] = []
    for key in ("primary_spouse", "spouse"):
        spouses.extend(_id(item) for item in _list(family.get(key)) if _id(item))
    spouses = list(dict.fromkeys(spouses))
    return {
        "id": char_id,
        "name": char.get("first_name") or char.get("name"),
        "nickname": char.get("nickname"),
        "birth": char.get("birth"),
        "female": bool(char.get("female", False)),
        "dynasty_house": _id(char.get("dynasty_house")),
        "culture": _id(char.get("culture")),
        "faith": _id(char.get("faith")),
        "skills": char.get("skill"),
        "traits": _list(char.get("traits")),
        "gold": alive.get("gold"),
        "stress": alive.get("stress"),
        "health": alive.get("health"),
        "prestige": alive.get("prestige"),
        "piety": alive.get("piety"),
        "dread": landed.get("dread"),
        "strength": landed.get("strength"),
        "vassal_power_value": landed.get("vassal_power_value"),
        "is_powerful_vassal": bool(landed.get("is_powerful_vassal", False)),
        "government": landed.get("government"),
        "realm_capital": landed.get("realm_capital"),
        "succession": [_id(item) for item in _list(landed.get("succession")) if _id(item)],
        "spouses": spouses,
        "children": [_id(item) for item in _list(family.get("child")) if _id(item)],
        "real_father": _id(family.get("real_father")),
        "titles": held,
    }


def _family_ids(player_id: str, player: Mapping[str, Any], characters: Mapping[str, JsonObject]) -> dict[str, set[str]]:
    family = _dict(player.get("family_data"))
    spouses = {_id(item) for key in ("primary_spouse", "spouse") for item in _list(family.get(key)) if _id(item)}
    children = {_id(item) for item in _list(family.get("child")) if _id(item)}
    parents: set[str] = set()
    father = _id(family.get("real_father"))
    if father:
        parents.add(father)
    for cid, char in characters.items():
        child_ids = {_id(item) for item in _list(_dict(char.get("family_data")).get("child")) if _id(item)}
        if player_id in child_ids:
            parents.add(cid)
    siblings: set[str] = set()
    for parent in parents:
        pdata = _dict(characters.get(parent, {}).get("family_data"))
        siblings.update(_id(item) for item in _list(pdata.get("child")) if _id(item) and _id(item) != player_id)
    return {"spouses": {item for item in spouses if item}, "children": {item for item in children if item}, "parents": parents, "siblings": {item for item in siblings if item}}


def _direct_vassals(player_id: str, player_titles: list[JsonObject], characters: Mapping[str, JsonObject], titles: Mapping[str, JsonObject]) -> list[JsonObject]:
    liege_title_ids = {str(item["index"]) for item in player_titles}
    vassal_ids: set[str] = set()
    for title in titles.values():
        if _id(title.get("de_facto_liege")) in liege_title_ids:
            holder = _id(title.get("holder"))
            if holder and holder != player_id:
                vassal_ids.add(holder)
    summaries = [_character_summary(cid, characters[cid], titles) for cid in vassal_ids if cid in characters]
    summaries.sort(key=lambda item: (not bool(item.get("is_powerful_vassal")), -(float(item.get("vassal_power_value") or item.get("strength") or 0)), str(item.get("name") or "")))
    return summaries


def _contains_id(value: Any, char_id: str, budget: list[int]) -> bool:
    if budget[0] <= 0:
        return False
    budget[0] -= 1
    if _id(value) == char_id:
        return True
    if isinstance(value, Mapping):
        return any(_contains_id(child, char_id, budget) for child in value.values())
    if isinstance(value, list):
        return any(_contains_id(child, char_id, budget) for child in value)
    return False


def _bounded_references(value: Any, char_id: str, limit: int) -> list[JsonObject]:
    result: list[JsonObject] = []
    for record_id, record in _mapping_records(value).items():
        if len(result) >= limit:
            break
        if _contains_id(record, char_id, [5000]):
            compact: JsonObject = {"id": record_id}
            for key in ("type", "event", "event_id", "name", "date", "start_date", "end_date", "target", "owner", "actor", "recipient", "participants", "state", "result"):
                if key in record:
                    compact[key] = record[key]
            result.append(compact)
    return result


def _event_state(state: JsonObject, player_id: str) -> JsonObject:
    important: list[Any] = []
    for item in _list(state.get("played_character")):
        if isinstance(item, Mapping):
            important.extend(_list(item.get("important_decisions")))

    triggered: list[str] = []
    for key, value in state.items():
        key_name = str(key).casefold()
        if "triggered" in key_name and "event" in key_name:
            if isinstance(value, Mapping):
                triggered.extend(str(item) for item in value.keys())
            elif isinstance(value, list):
                for item in value:
                    if isinstance(item, Mapping):
                        triggered.extend(str(child) for child in item.keys())
                    elif isinstance(item, (str, int)):
                        triggered.append(str(item))
        if len(triggered) >= MAX_EVENT_REFERENCES:
            break

    memories = _bounded_references(state.get("character_memory_manager"), player_id, MAX_MEMORY_REFERENCES)
    stories_block = _dict(state.get("stories"))
    stories = _bounded_references(stories_block.get("active"), player_id, 100)
    actions_block = _dict(state.get("important_action_manager"))
    actions = _bounded_references(actions_block.get("active"), player_id, 100)
    return {
        "important_decisions": important[:200],
        "persistent_event_keys": list(dict.fromkeys(triggered))[:MAX_EVENT_REFERENCES],
        "player_memories": memories,
        "active_stories": stories,
        "important_actions": actions,
        "note": "Persistenter Event-Zustand ist kein vollständiges Klickprotokoll. Exakte Eventoptionen werden nur behauptet, wenn Save/Runtime-Daten sie belegen.",
    }


def _active_wars(state: JsonObject, player_id: str) -> list[JsonObject]:
    wars = _dict(state.get("wars"))
    return _bounded_references(wars.get("active_wars") if wars else None, player_id, 100)


def normalize_ck3_state(raw: JsonObject) -> JsonObject:
    state = _unwrap_gamestate(raw)
    player_id = _player_id(state)
    chars = _characters(state)
    titles = _titles(state)
    if not player_id or player_id not in chars:
        raise Ck3Error("Spielercharakter konnte im gemelteten CK3-Save nicht eindeutig gefunden werden.")

    player_char = chars[player_id]
    player = _character_summary(player_id, player_char, titles)
    family_groups = _family_ids(player_id, player_char, chars)
    family: JsonObject = {}
    for relation, ids in family_groups.items():
        family[relation] = [_character_summary(cid, chars[cid], titles) for cid in sorted(ids) if cid in chars]

    player_titles = player["titles"]
    primary = max(player_titles, key=lambda item: RANK_WEIGHT.get(str(item.get("key") or "")[:1], 0), default=None)
    vassals = _direct_vassals(player_id, player_titles, chars, titles)
    metadata = _dict(state.get("meta_data"))
    return {
        "game_date": state.get("date"),
        "game_version": metadata.get("version") or metadata.get("version_name"),
        "player": player,
        "primary_title": primary,
        "family": family,
        "realm": {"titles": player_titles, "vassals": vassals, "vassal_count": len(vassals)},
        "external": {"neighbor_realms": [], "relevant_external_characters": []},
        "wars": _active_wars(state, player_id),
        "events": _event_state(state, player_id),
    }


def build_ck3_snapshot(save_path: Path, *, rakaly_path: Path | None = None, root: Path | None = None) -> JsonObject:
    save_file = resolve_ck3_save(save_path)
    envelope = inspect_ck3_envelope(save_file)
    stat = save_file.stat()
    resolved_rakaly = find_rakaly(rakaly_path, root)
    fallback = fallback_metadata(save_file)
    normalized: JsonObject | None = None
    warnings: list[str] = []
    if resolved_rakaly:
        normalized = normalize_ck3_state(load_ck3_json(save_file, resolved_rakaly))
    else:
        warnings.append("Tiefe CK3-Analyse ist noch nicht aktiv: Rakaly CLI wurde nicht gefunden. Envelope und sichere Metadaten wurden trotzdem gelesen.")
    warnings.append("Direkte Nachbarreiche werden in Stufe 2 über lokale CK3-Kartendaten ergänzt; der Save allein enthält die Kartenadjazenz nicht in einer stabilen, kleinen Form.")
    warnings.append("Persistente Eventzustände, Memories und Save-Deltas können Events belegen oder rekonstruieren, sind aber kein lückenloses Protokoll jeder angeklickten Eventoption.")
    return {
        "schema_version": 1,
        "kind": "wachterfeder-ck3-snapshot",
        "source_name": save_file.stem,
        "source_file": save_file.name,
        "source_size": stat.st_size,
        "source_modified_utc": datetime.fromtimestamp(stat.st_mtime, tz=timezone.utc).isoformat(),
        "sha256": sha256_file(save_file),
        "inspected_utc": datetime.now(tz=timezone.utc).isoformat(),
        "envelope": envelope,
        "deep_analysis": normalized is not None,
        "rakaly": {"available": resolved_rakaly is not None, "versioned_dependency": "Rakaly CLI / Jomini parser"},
        "fallback_metadata": fallback,
        "state": normalized,
        "warnings": warnings,
    }


def _read_json(path: Path) -> JsonObject | None:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (FileNotFoundError, OSError, json.JSONDecodeError):
        return None
    return value if isinstance(value, dict) else None


def _write_json(value: JsonObject, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _flatten(value: Any, prefix: str = "") -> dict[str, Any]:
    if isinstance(value, Mapping):
        out: dict[str, Any] = {}
        for key, child in value.items():
            path = f"{prefix}.{key}" if prefix else str(key)
            out.update(_flatten(child, path))
        return out
    if isinstance(value, list):
        return {prefix: value}
    return {prefix: value}


def _field_changes(previous: Any, current: Any) -> JsonObject:
    old = _flatten(previous or {})
    new = _flatten(current or {})
    changes: JsonObject = {}
    for key in sorted(set(old) | set(new)):
        before = old.get(key, _MISSING)
        after = new.get(key, _MISSING)
        if before == after:
            continue
        changes[key] = {"from": None if before is _MISSING else before, "to": None if after is _MISSING else after, "change": "added" if before is _MISSING else "removed" if after is _MISSING else "changed"}
    return changes


def _items_by_id(items: Any) -> dict[str, JsonObject]:
    return {str(item.get("id")): dict(item) for item in _list(items) if isinstance(item, Mapping) and item.get("id") is not None}


def _membership_delta(previous: Any, current: Any) -> JsonObject:
    old = _items_by_id(previous)
    new = _items_by_id(current)
    changed: JsonObject = {}
    for ident in sorted(set(old) & set(new)):
        delta = _field_changes(old[ident], new[ident])
        if delta:
            changed[ident] = delta
    return {"added": [new[ident] for ident in sorted(set(new) - set(old))], "removed": [old[ident] for ident in sorted(set(old) - set(new))], "changed": changed}


def _family_flat(state: JsonObject | None) -> list[JsonObject]:
    family = _dict((state or {}).get("family"))
    result: list[JsonObject] = []
    for relation, items in family.items():
        for item in _list(items):
            if isinstance(item, Mapping):
                row = dict(item)
                row["relation"] = relation
                result.append(row)
    return result


def _semantic_events(previous_state: JsonObject | None, current_state: JsonObject | None) -> list[JsonObject]:
    if previous_state is None or current_state is None:
        return []
    result: list[JsonObject] = []
    family = _membership_delta(_family_flat(previous_state), _family_flat(current_state))
    for item in family["added"]:
        result.append({"type": "family_change", "change": "added", "subject": item, "confidence": "save_diff"})
    for item in family["removed"]:
        result.append({"type": "family_change", "change": "removed", "subject": item, "confidence": "save_diff"})

    old_titles = {str(item.get("index")): dict(item) for item in _list(_dict(previous_state.get("realm")).get("titles")) if isinstance(item, Mapping)}
    new_titles = {str(item.get("index")): dict(item) for item in _list(_dict(current_state.get("realm")).get("titles")) if isinstance(item, Mapping)}
    for ident in sorted(set(new_titles) - set(old_titles)):
        result.append({"type": "title_gained", "subject": new_titles[ident], "confidence": "save_diff"})
    for ident in sorted(set(old_titles) - set(new_titles)):
        result.append({"type": "title_lost", "subject": old_titles[ident], "confidence": "save_diff"})

    vassals = _membership_delta(_dict(previous_state.get("realm")).get("vassals"), _dict(current_state.get("realm")).get("vassals"))
    for item in vassals["added"]:
        result.append({"type": "vassal_change", "change": "added", "subject": item, "confidence": "save_diff"})
    for item in vassals["removed"]:
        result.append({"type": "vassal_change", "change": "removed", "subject": item, "confidence": "save_diff"})

    old_mem = _items_by_id(_dict(previous_state.get("events")).get("player_memories"))
    new_mem = _items_by_id(_dict(current_state.get("events")).get("player_memories"))
    for ident in sorted(set(new_mem) - set(old_mem)):
        result.append({"type": "memory_added", "subject": new_mem[ident], "confidence": "persistent_memory"})
    return result


def build_ck3_delta(previous: JsonObject | None, current: JsonObject) -> JsonObject:
    old_state = (previous or {}).get("state") if isinstance((previous or {}).get("state"), Mapping) else None
    new_state = current.get("state") if isinstance(current.get("state"), Mapping) else None
    state_changes = _field_changes(old_state, new_state) if old_state is not None and new_state is not None else {}
    semantic = _semantic_events(dict(old_state) if old_state else None, dict(new_state) if new_state else None)
    initial = previous is None
    sha_changed = (previous or {}).get("sha256") != current.get("sha256")
    has_changes = bool(initial or state_changes or semantic or sha_changed)
    fallback = current.get("fallback_metadata") or {}
    state = new_state or {}
    player = _dict(state.get("player"))
    primary = _dict(state.get("primary_title"))
    return {
        "schema_version": 1,
        "kind": "wachterfeder-ck3-delta",
        "created_utc": datetime.now(tz=timezone.utc).isoformat(),
        "initial_snapshot": initial,
        "previous_save_sha256": (previous or {}).get("sha256"),
        "current_save_sha256": current.get("sha256"),
        "summary": {"has_changes": has_changes, "deep_analysis": bool(current.get("deep_analysis")), "state_changes": len(state_changes), "timeline_candidates": len(semantic)},
        "current_state": {
            "game_date": state.get("game_date"),
            "game_version": state.get("game_version") or fallback.get("game_version"),
            "player_id": player.get("id"),
            "player_name": player.get("name") or fallback.get("player_name"),
            "primary_title": primary.get("key") or fallback.get("primary_title_name"),
            "family_members": len(_family_flat(dict(state))) if state else 0,
            "vassals": int(_dict(state.get("realm")).get("vassal_count") or 0),
        },
        "changes": {"state": state_changes, "timeline_candidates": semantic},
        "notes": ["Timeline-Kandidaten werden aus persistiertem Zustand und Save-Deltas erzeugt.", "Eine konkrete Eventoption gilt erst als exakt, wenn Event-/Runtime-Daten sie eindeutig belegen."],
    }


def analyse_ck3_save(save_path: Path, *, rakaly_path: Path | None = None, root: Path | None = None) -> Ck3AnalysisResult:
    root = (root or Path(__file__).resolve().parents[2]).expanduser().resolve()
    save_file = resolve_ck3_save(save_path)
    local_root = root / ".wachterfeder" / "ck3"
    snapshot_path = local_root / "ck3.snapshot.json"
    delta_path = local_root / "ck3.delta.json"
    previous = _read_json(snapshot_path)
    current = build_ck3_snapshot(save_file, rakaly_path=rakaly_path, root=root)
    delta = build_ck3_delta(previous, current)
    stamp = datetime.fromtimestamp(save_file.stat().st_mtime).strftime("%Y%m%d-%H%M%S")
    history_delta_path = local_root / "history" / f"{stamp}-{current['sha256'][:8]}.delta.json"
    _write_json(current, snapshot_path)
    _write_json(delta, delta_path)
    _write_json(delta, history_delta_path)
    current_state = delta["current_state"]
    summary = delta["summary"]
    return Ck3AnalysisResult(
        save_file=save_file,
        snapshot_path=snapshot_path,
        delta_path=delta_path,
        history_delta_path=history_delta_path,
        initial_snapshot=bool(delta["initial_snapshot"]),
        has_changes=bool(summary["has_changes"]),
        deep_analysis=bool(summary["deep_analysis"]),
        game_version=current_state.get("game_version"),
        player_name=current_state.get("player_name"),
        primary_title=current_state.get("primary_title"),
        family_members=int(current_state.get("family_members") or 0),
        vassals=int(current_state.get("vassals") or 0),
        event_changes=int(summary.get("timeline_candidates") or 0),
        rakaly_path=find_rakaly(rakaly_path, root),
    )


def _cmd_paths(_: argparse.Namespace) -> int:
    for path in candidate_ck3_save_roots():
        print(f"[{'gefunden' if path.is_dir() else 'nicht gefunden'}] {path}")
    newest = newest_ck3_save()
    print(f"\nNeuester CK3-Spielstand: {newest}" if newest else "\nKein CK3-Spielstand gefunden.")
    return 0


def _cmd_inspect(args: argparse.Namespace) -> int:
    result = analyse_ck3_save(Path(args.save), rakaly_path=Path(args.rakaly) if args.rakaly else None, root=Path(args.root) if args.root else None)
    print(f"Save:        {result.save_file}")
    print(f"Version:     {result.game_version or 'unbekannt'}")
    print(f"Spieler:     {result.player_name or 'unbekannt'}")
    print(f"Titel:       {result.primary_title or 'unbekannt'}")
    print(f"Tiefe:       {'voll' if result.deep_analysis else 'Metadaten'}")
    print(f"Familie:     {result.family_members}")
    print(f"Vasallen:    {result.vassals}")
    print(f"Events Δ:    {result.event_changes}")
    print(f"Snapshot:    {result.snapshot_path}")
    print(f"Delta:       {result.delta_path}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Wächterfeder-Adapter für Crusader Kings III")
    sub = parser.add_subparsers(dest="command", required=True)
    paths = sub.add_parser("paths", help="übliche CK3-Speicherorte prüfen")
    paths.set_defaults(func=_cmd_paths)
    inspect = sub.add_parser("inspect", help="CK3-Spielstand analysieren und Delta erzeugen")
    inspect.add_argument("--save", required=True, help=".ck3-Spielstand oder Save-Ordner")
    inspect.add_argument("--rakaly", default=None, help="optional: Pfad zu rakaly.exe")
    inspect.add_argument("--root", default=None, help="Repository-Stamm für Tests")
    inspect.set_defaults(func=_cmd_inspect)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main())
