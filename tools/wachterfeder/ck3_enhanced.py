#!/usr/bin/env python3
"""Enhanced Crusader Kings III analysis layer for Wächterfeder.

This module deliberately builds on the conservative read-only CK3 adapter.
It keeps the stable save-envelope/Rakaly parser path, but improves:
- compact deltas (no whole family/vassal lists copied on every change),
- event evidence extraction from nested persistent CK3 structures,
- semantic timeline events (births, marriages, succession, wars, titles),
- succession and vassal watch summaries,
- CK3 control-code cleanup,
- local persistence of the selected Rakaly path.

Geographic neighbour realms and human-readable trait/culture/faith names remain
separate local-game-data tasks; this module never guesses them.
"""
from __future__ import annotations

import json
import re
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Mapping

try:
    from tools.wachterfeder import ck3 as base
except ModuleNotFoundError:
    import ck3 as base

JsonObject = dict[str, Any]
_MISSING = object()

Ck3Error = base.Ck3Error
Ck3AnalysisResult = base.Ck3AnalysisResult
candidate_ck3_save_roots = base.candidate_ck3_save_roots
newest_ck3_save = base.newest_ck3_save
resolve_ck3_save = base.resolve_ck3_save
inspect_ck3_envelope = base.inspect_ck3_envelope
fallback_metadata = base.fallback_metadata

MAX_EVENT_EVIDENCE = 250
MAX_RECURSIVE_NODES = 40_000
MAX_RECURSIVE_DEPTH = 7


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


def _numeric(value: Any) -> float | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, Mapping):
        for key in ("value", "currency", "amount"):
            child = value.get(key)
            if isinstance(child, (int, float)) and not isinstance(child, bool):
                return float(child)
    return None


def _date_tuple(value: Any) -> tuple[int, int, int] | None:
    if not isinstance(value, str):
        return None
    match = re.fullmatch(r"(-?\d+)\.(\d+)\.(\d+)", value.strip())
    if not match:
        return None
    return tuple(int(item) for item in match.groups())


def _approx_age_years(birth: Any, current: Any) -> int | None:
    b = _date_tuple(birth)
    c = _date_tuple(current)
    if not b or not c:
        return None
    years = c[0] - b[0]
    if (c[1], c[2]) < (b[1], b[2]):
        years -= 1
    return max(years, 0)


def clean_ck3_text(value: Any) -> Any:
    """Remove common CK3 UI control sequences while preserving visible text."""
    if not isinstance(value, str):
        return value
    text = value.replace("\r", " ").replace("\n", " ")
    text = text.replace("\x15L; ", "").replace("\x15L;", "")
    text = re.sub(r"\x15(?:[A-Z_]+(?::[^ \x15]+)?|!)", "", text)
    text = re.sub(r"#[A-Za-z0-9_]+", "", text)
    text = text.replace("#!", "")
    text = re.sub(r"\s+", " ", text).strip()
    text = re.sub(r"\b([A-Za-zÄÖÜäöüß]+isch)\s+er\b", r"\1er", text)
    return text


def _compact_record(record_id: str, record: Mapping[str, Any], path: str) -> JsonObject:
    compact: JsonObject = {"id": record_id, "path": path}
    keys = (
        "type", "memory_type", "event", "event_id", "name", "title",
        "date", "start_date", "end_date", "state", "result", "on_action",
        "owner", "character", "actor", "recipient", "target", "scope",
        "participants", "claimant", "attacker", "defender", "casus_belli",
        "target_title", "war_score", "priority",
    )
    for key in keys:
        if key in record:
            compact[key] = clean_ck3_text(record[key])
    return compact


_REFERENCE_KEYS = {
    "owner", "character", "actor", "recipient", "target", "root",
    "scope", "claimant", "attacker", "defender", "participants",
}
_CONTENT_KEYS = {
    "type", "memory_type", "event", "event_id", "name", "title",
    "date", "start_date", "end_date", "state", "result", "on_action",
}


def _directly_references(record: Mapping[str, Any], player_id: str) -> bool:
    for key in _REFERENCE_KEYS:
        if key not in record:
            continue
        value = record[key]
        if _id(value) == player_id:
            return True
        if isinstance(value, list) and player_id in {_id(item) for item in value}:
            return True
        if isinstance(value, Mapping) and player_id in {_id(item) for item in value.values()}:
            return True
    return False


def _nested_player_records(
    value: Any,
    player_id: str,
    *,
    root_label: str,
    limit: int = MAX_EVENT_EVIDENCE,
) -> list[JsonObject]:
    """Find content records below manager wrappers such as ``database``."""
    result: list[JsonObject] = []
    seen: set[tuple[str, str, str]] = set()
    budget = [MAX_RECURSIVE_NODES]

    def walk(node: Any, path: list[str], player_branch: bool, depth: int) -> None:
        if len(result) >= limit or budget[0] <= 0 or depth > MAX_RECURSIVE_DEPTH:
            return
        budget[0] -= 1

        if isinstance(node, Mapping):
            current_path = ".".join([root_label, *path]) if path else root_label
            final = path[-1] if path else root_label
            branch = player_branch or final == player_id
            has_content = bool(_CONTENT_KEYS.intersection(str(key) for key in node.keys()))
            if has_content and (branch or _directly_references(node, player_id)):
                ident = _id(node.get("id") or node.get("identity") or node.get("index")) or final
                compact = _compact_record(ident, node, current_path)
                signature = (
                    str(compact.get("id")),
                    str(compact.get("type") or compact.get("memory_type") or compact.get("event") or ""),
                    str(compact.get("date") or compact.get("start_date") or ""),
                )
                if signature not in seen:
                    seen.add(signature)
                    result.append(compact)
                    if len(result) >= limit:
                        return
            for key, child in node.items():
                walk(child, [*path, str(key)], branch or str(key) == player_id, depth + 1)
        elif isinstance(node, list):
            for index, child in enumerate(node):
                walk(child, [*path, str(index)], player_branch, depth + 1)

    walk(value, [], False, 0)
    return result


def _mapping_records(value: Any) -> dict[str, JsonObject]:
    return base._mapping_records(value)  # noqa: SLF001


def _contains_id(value: Any, char_id: str, budget: list[int] | None = None) -> bool:
    return base._contains_id(value, char_id, budget or [5000])  # noqa: SLF001


def _enhanced_wars(state: JsonObject, player_id: str) -> list[JsonObject]:
    wars_block = _dict(state.get("wars"))
    records = _mapping_records(wars_block.get("active_wars") if wars_block else None)
    rows: list[JsonObject] = []
    for war_id, war in records.items():
        if not _contains_id(war, player_id, [8000]):
            continue
        row = _compact_record(war_id, war, f"wars.active_wars.{war_id}")
        for key in ("name", "title", "casus_belli"):
            if key in row:
                row[key] = clean_ck3_text(row[key])
        rows.append(row)
    return rows[:100]


def _event_state(state: JsonObject, player_id: str) -> JsonObject:
    played_decisions: list[Any] = []
    for item in _list(state.get("played_character")):
        if isinstance(item, Mapping) and _id(item.get("character")) == player_id:
            played_decisions.extend(_list(item.get("important_decisions")))

    memories = _nested_player_records(
        state.get("character_memory_manager"), player_id,
        root_label="character_memory_manager", limit=200,
    )
    stories = _nested_player_records(
        state.get("stories"), player_id, root_label="stories", limit=100,
    )
    actions = _nested_player_records(
        state.get("important_action_manager"), player_id,
        root_label="important_action_manager", limit=150,
    )

    persistent: list[JsonObject] = []
    for key, value in state.items():
        folded = str(key).casefold()
        if "event" not in folded:
            continue
        persistent.extend(_nested_player_records(value, player_id, root_label=str(key), limit=50))
        if len(persistent) >= MAX_EVENT_EVIDENCE:
            break

    return {
        "tracked_important_decisions": played_decisions[:200],
        "player_memories": memories,
        "active_stories": stories,
        "important_actions": actions,
        "persistent_event_state": persistent[:MAX_EVENT_EVIDENCE],
        "evidence_counts": {
            "memories": len(memories),
            "stories": len(stories),
            "important_actions": len(actions),
            "persistent_event_state": min(len(persistent), MAX_EVENT_EVIDENCE),
        },
        "note": (
            "Persistenter Event-Zustand, Memories und Stories sind Belege im Save, "
            "aber kein lückenloses Klickprotokoll. Eine konkrete Eventoption wird "
            "nur als exakt markiert, wenn Save- oder Runtime-Daten sie eindeutig belegen."
        ),
    }


def _add_character_extras(summary: JsonObject, raw: Mapping[str, Any], game_date: Any) -> JsonObject:
    row = dict(summary)
    row["death"] = raw.get("death") or _dict(raw.get("dead_data")).get("death")
    row["age_years"] = _approx_age_years(row.get("birth"), game_date) if not row["death"] else None
    row["alive"] = row["death"] is None
    return row


def _find_title_by_index(titles: Mapping[str, JsonObject], ident: Any) -> tuple[str, JsonObject] | None:
    target = _id(ident)
    if target is None or target not in titles:
        return None
    return target, titles[target]


def _resolve_liege(
    player_id: str,
    primary: Mapping[str, Any] | None,
    characters: Mapping[str, JsonObject],
    titles: Mapping[str, JsonObject],
    game_date: Any,
) -> JsonObject | None:
    if not primary:
        return None
    match = _find_title_by_index(titles, primary.get("de_facto_liege"))
    if not match:
        return None
    title_id, title = match
    holder = _id(title.get("holder"))
    if not holder or holder == player_id or holder not in characters:
        return None
    char = base._character_summary(holder, characters[holder], titles)  # noqa: SLF001
    char = _add_character_extras(char, characters[holder], game_date)
    return {"title": base._title_summary(title_id, title), "holder": char}  # noqa: SLF001


def _succession_summary(
    player: Mapping[str, Any],
    characters: Mapping[str, JsonObject],
    titles: Mapping[str, JsonObject],
    game_date: Any,
) -> JsonObject:
    rows: list[JsonObject] = []
    for order, ident in enumerate(_list(player.get("succession")), start=1):
        cid = _id(ident)
        if not cid:
            continue
        row: JsonObject = {"order": order, "id": cid}
        if cid in characters:
            summary = base._character_summary(cid, characters[cid], titles)  # noqa: SLF001
            summary = _add_character_extras(summary, characters[cid], game_date)
            row.update({
                "name": summary.get("name"), "birth": summary.get("birth"),
                "age_years": summary.get("age_years"),
                "dynasty_house": summary.get("dynasty_house"),
                "faith": summary.get("faith"), "culture": summary.get("culture"),
            })
        rows.append(row)
    return {"primary_heir": rows[0] if rows else None, "line": rows}


def _vassal_watchlist(player: Mapping[str, Any], vassals: Iterable[Mapping[str, Any]]) -> list[JsonObject]:
    player_power = _numeric(player.get("vassal_power_value"))
    player_strength = _numeric(player.get("strength"))
    player_faith = _id(player.get("faith"))
    rows: list[JsonObject] = []
    for vassal in vassals:
        raw_power = _numeric(vassal.get("vassal_power_value"))
        raw_strength = _numeric(vassal.get("strength"))
        score_ratio = raw_power / player_power if raw_power is not None and player_power and player_power > 0 else None
        strength_ratio = raw_strength / player_strength if raw_strength is not None and player_strength and player_strength > 0 else None
        faith_differs = bool(player_faith and _id(vassal.get("faith")) and _id(vassal.get("faith")) != player_faith)

        attention = "low"
        reasons: list[str] = []
        if score_ratio is not None and score_ratio >= 0.25:
            attention = "high"
            reasons.append("hoher Anteil am gespeicherten Vasallen-Machtwert")
        elif score_ratio is not None and score_ratio >= 0.15:
            attention = "medium"
            reasons.append("merklicher Anteil am gespeicherten Vasallen-Machtwert")
        if strength_ratio is not None and strength_ratio >= 0.5:
            attention = "high"
            reasons.append("hohe gespeicherte Truppenstärke relativ zum Herrscher")
        elif strength_ratio is not None and strength_ratio >= 0.25 and attention == "low":
            attention = "medium"
            reasons.append("relevante gespeicherte Truppenstärke")
        if faith_differs:
            reasons.append("abweichender Glaube")
            if attention == "low":
                attention = "medium"

        rows.append({
            "id": vassal.get("id"), "name": vassal.get("name"),
            "primary_title": (_list(vassal.get("titles")) or [None])[0],
            "power_score_ratio": round(score_ratio, 4) if score_ratio is not None else None,
            "military_strength_ratio": round(strength_ratio, 4) if strength_ratio is not None else None,
            "faith_differs": faith_differs,
            "is_powerful_vassal": bool(vassal.get("is_powerful_vassal")),
            "attention": attention, "reasons": reasons,
            "interpretation": (
                "Heuristik aus Save-Werten; kein Ersatz für Meinung, Fraktionsstatus "
                "oder das im UI berechnete militärische Verhältnis."
            ),
        })
    rank = {"high": 0, "medium": 1, "low": 2}
    rows.sort(key=lambda item: (
        rank.get(str(item.get("attention")), 3),
        -(float(item.get("power_score_ratio") or 0)),
        str(item.get("name") or ""),
    ))
    return rows


def normalize_ck3_state(raw: JsonObject) -> JsonObject:
    normalized = base.normalize_ck3_state(raw)
    state = base._unwrap_gamestate(raw)  # noqa: SLF001
    player_id = _id(_dict(normalized.get("player")).get("id"))
    if not player_id:
        return normalized

    characters = base._characters(state)  # noqa: SLF001
    titles = base._titles(state)  # noqa: SLF001
    game_date = normalized.get("game_date")

    if player_id in characters:
        normalized["player"] = _add_character_extras(
            _dict(normalized.get("player")), characters[player_id], game_date
        )

    family = _dict(normalized.get("family"))
    for relation, items in list(family.items()):
        enriched: list[JsonObject] = []
        for item in _list(items):
            if not isinstance(item, Mapping):
                continue
            cid = _id(item.get("id"))
            if cid and cid in characters:
                enriched.append(_add_character_extras(dict(item), characters[cid], game_date))
            else:
                enriched.append(dict(item))
        family[relation] = enriched
    normalized["family"] = family

    wars = _enhanced_wars(state, player_id)
    events = _event_state(state, player_id)
    normalized["wars"] = wars
    normalized["events"] = events

    player = _dict(normalized.get("player"))
    realm = _dict(normalized.get("realm"))
    vassals = [dict(item) for item in _list(realm.get("vassals")) if isinstance(item, Mapping)]
    primary = _dict(normalized.get("primary_title"))
    liege = _resolve_liege(player_id, primary, characters, titles, game_date)

    external = _dict(normalized.get("external"))
    external["liege"] = liege
    external["neighbor_realms"] = external.get("neighbor_realms") or []
    external["neighbor_status"] = (
        "Geografische Nachbarn benötigen lokale Karten-/Provinzdaten; "
        "Wächterfeder behauptet ohne diese Daten keine Nachbarschaft."
    )
    normalized["external"] = external

    normalized["analysis"] = {
        "succession": _succession_summary(player, characters, titles, game_date),
        "vassal_watchlist": _vassal_watchlist(player, vassals),
        "family_counts": {key: len(_list(value)) for key, value in family.items()},
        "active_war_count": len(wars),
        "event_evidence_counts": events.get("evidence_counts", {}),
        "limitations": [
            "Vasallen-Aufmerksamkeit ist eine Heuristik aus gespeicherten Macht-/Stärkewerten.",
            "Meinung, Fraktionsmitgliedschaft und geografische Nachbarn werden erst ausgewiesen, wenn sie sicher aufgelöst sind.",
            "Numerische Trait-/Kultur-/Glaubens-IDs werden nicht geraten; lesbare Namen brauchen lokale CK3-Daten.",
        ],
    }
    return normalized


def _read_json(path: Path) -> JsonObject | None:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (FileNotFoundError, OSError, json.JSONDecodeError):
        return None
    return value if isinstance(value, dict) else None


def _write_json(value: JsonObject, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _config_path(root: Path) -> Path:
    return root / ".wachterfeder" / "ck3" / "config.json"


def read_ck3_config(root: Path) -> JsonObject:
    return _read_json(_config_path(root)) or {}


def remember_rakaly(root: Path, rakaly: Path) -> None:
    try:
        resolved = rakaly.expanduser().resolve()
    except OSError:
        return
    if not resolved.is_file():
        return
    config = read_ck3_config(root)
    config.update({
        "schema_version": 1,
        "rakaly_path": str(resolved),
        "updated_utc": datetime.now(tz=timezone.utc).isoformat(),
    })
    _write_json(config, _config_path(root))


def find_rakaly(explicit: Path | None = None, root: Path | None = None) -> Path | None:
    if explicit:
        found = base.find_rakaly(explicit, root)
        if found:
            return found
    if root:
        configured = read_ck3_config(root).get("rakaly_path")
        if isinstance(configured, str) and configured.strip():
            candidate = Path(configured)
            if candidate.is_file():
                return candidate.resolve()
    return base.find_rakaly(None, root)


def rakaly_version(rakaly: Path) -> str | None:
    for command in ([str(rakaly), "--version"], [str(rakaly), "-V"]):
        try:
            completed = subprocess.run(
                command, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                timeout=10, check=False,
            )
        except (OSError, subprocess.SubprocessError):
            continue
        text = completed.stdout.decode("utf-8", errors="replace").strip()
        if text:
            return text.splitlines()[0][:200]
    return None


def build_ck3_snapshot(
    save_path: Path,
    *,
    rakaly_path: Path | None = None,
    root: Path | None = None,
) -> JsonObject:
    save_file = resolve_ck3_save(save_path)
    root = (root or Path(__file__).resolve().parents[2]).expanduser().resolve()
    envelope = inspect_ck3_envelope(save_file)
    stat = save_file.stat()
    resolved_rakaly = find_rakaly(rakaly_path, root)
    fallback = fallback_metadata(save_file)
    normalized: JsonObject | None = None
    warnings: list[str] = []

    if resolved_rakaly:
        normalized = normalize_ck3_state(base.load_ck3_json(save_file, resolved_rakaly))
    else:
        warnings.append(
            "Tiefe CK3-Analyse ist nicht aktiv: Rakaly CLI wurde nicht gefunden. "
            "Envelope und sichere Metadaten wurden trotzdem gelesen."
        )

    warnings.append(
        "Geografische Nachbarreiche bleiben leer, bis lokale CK3-Karten-/Provinzdaten "
        "angebunden sind; politische Nähe wird nicht als geografische Nachbarschaft ausgegeben."
    )
    warnings.append(
        "Persistente Eventzustände, Memories, Stories und Save-Deltas sind Belege, "
        "aber kein lückenloses Protokoll jeder angeklickten Eventoption."
    )

    return {
        "schema_version": 2,
        "kind": "wachterfeder-ck3-snapshot",
        "source_name": save_file.stem,
        "source_file": save_file.name,
        "source_size": stat.st_size,
        "source_modified_utc": datetime.fromtimestamp(stat.st_mtime, tz=timezone.utc).isoformat(),
        "sha256": base.sha256_file(save_file),
        "inspected_utc": datetime.now(tz=timezone.utc).isoformat(),
        "envelope": envelope,
        "deep_analysis": normalized is not None,
        "rakaly": {
            "available": resolved_rakaly is not None,
            "version": rakaly_version(resolved_rakaly) if resolved_rakaly else None,
            "versioned_dependency": "Rakaly CLI / Jomini parser",
        },
        "fallback_metadata": fallback,
        "state": normalized,
        "warnings": warnings,
    }


def _items_by_id(items: Any, *, fallback_key: str = "id") -> dict[str, JsonObject]:
    result: dict[str, JsonObject] = {}
    for index, item in enumerate(_list(items)):
        if not isinstance(item, Mapping):
            continue
        ident = _id(item.get("id") or item.get(fallback_key)) or f"index:{index}"
        result[ident] = dict(item)
    return result


def _family_by_relation(state: Mapping[str, Any] | None) -> dict[str, dict[str, JsonObject]]:
    family = _dict((state or {}).get("family"))
    return {str(relation): _items_by_id(items) for relation, items in family.items()}


def _event_identity(item: Mapping[str, Any], index: int) -> str:
    for key in ("id", "event_id", "event", "type", "memory_type"):
        value = item.get(key)
        if value is not None:
            suffix = item.get("date") or item.get("start_date") or item.get("path") or index
            return f"{key}:{value}:{suffix}"
    return f"index:{index}:{item.get('path')}"


def _event_map(items: Any) -> dict[str, JsonObject]:
    result: dict[str, JsonObject] = {}
    for index, item in enumerate(_list(items)):
        if isinstance(item, Mapping):
            result[_event_identity(item, index)] = dict(item)
    return result


def _headline_state(state: Mapping[str, Any] | None) -> JsonObject:
    if not state:
        return {}
    player = _dict(state.get("player"))
    primary = _dict(state.get("primary_title"))
    realm = _dict(state.get("realm"))
    analysis = _dict(state.get("analysis"))
    succession = _dict(analysis.get("succession"))
    family = _family_by_relation(state)
    return {
        "game_date": state.get("game_date"),
        "game_version": state.get("game_version"),
        "player": {
            "id": player.get("id"), "name": player.get("name"),
            "gold": _numeric(player.get("gold")), "stress": player.get("stress"),
            "health": player.get("health"), "prestige": _numeric(player.get("prestige")),
            "piety": _numeric(player.get("piety")), "dread": player.get("dread"),
            "strength": player.get("strength"), "faith": player.get("faith"),
            "culture": player.get("culture"), "government": player.get("government"),
            "traits": list(player.get("traits") or []),
            "succession": list(player.get("succession") or []),
        },
        "primary_title": primary.get("key"),
        "vassal_count": realm.get("vassal_count"),
        "family_ids": {relation: sorted(records.keys()) for relation, records in family.items()},
        "war_ids": sorted(
            str(item.get("id")) for item in _list(state.get("wars"))
            if isinstance(item, Mapping) and item.get("id") is not None
        ),
        "primary_heir": _dict(succession.get("primary_heir")).get("id"),
    }


def _flatten(value: Any, prefix: str = "") -> dict[str, Any]:
    if isinstance(value, Mapping):
        result: dict[str, Any] = {}
        for key, child in value.items():
            path = f"{prefix}.{key}" if prefix else str(key)
            result.update(_flatten(child, path))
        return result
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
        changes[key] = {
            "from": None if before is _MISSING else before,
            "to": None if after is _MISSING else after,
            "change": "added" if before is _MISSING else "removed" if after is _MISSING else "changed",
        }
    return changes


def _semantic_events(
    previous_state: Mapping[str, Any] | None,
    current_state: Mapping[str, Any] | None,
) -> list[JsonObject]:
    if previous_state is None or current_state is None:
        return []
    events: list[JsonObject] = []

    old_family = _family_by_relation(previous_state)
    new_family = _family_by_relation(current_state)
    for relation in sorted(set(old_family) | set(new_family)):
        old = old_family.get(relation, {})
        new = new_family.get(relation, {})
        for ident in sorted(set(new) - set(old)):
            subject = new[ident]
            event_type = "child_added" if relation == "children" else "spouse_added" if relation == "spouses" else "family_member_added"
            events.append({
                "type": event_type, "relation": relation, "subject": subject,
                "date": subject.get("birth") if relation == "children" else current_state.get("game_date"),
                "confidence": "save_diff",
            })
        for ident in sorted(set(old) - set(new)):
            subject = old[ident]
            event_type = "spouse_removed" if relation == "spouses" else "family_member_removed"
            events.append({
                "type": event_type, "relation": relation, "subject": subject,
                "date": current_state.get("game_date"), "confidence": "save_diff",
            })
        for ident in sorted(set(old) & set(new)):
            before_death = old[ident].get("death")
            after_death = new[ident].get("death")
            if before_death != after_death and after_death:
                events.append({
                    "type": "death", "relation": relation, "subject": new[ident],
                    "date": after_death, "confidence": "persistent_state",
                })

    old_titles = {
        str(item.get("index")): dict(item)
        for item in _list(_dict(previous_state.get("realm")).get("titles"))
        if isinstance(item, Mapping) and item.get("index") is not None
    }
    new_titles = {
        str(item.get("index")): dict(item)
        for item in _list(_dict(current_state.get("realm")).get("titles"))
        if isinstance(item, Mapping) and item.get("index") is not None
    }
    for ident in sorted(set(new_titles) - set(old_titles)):
        events.append({"type": "title_gained", "subject": new_titles[ident], "confidence": "save_diff"})
    for ident in sorted(set(old_titles) - set(new_titles)):
        events.append({"type": "title_lost", "subject": old_titles[ident], "confidence": "save_diff"})

    old_vassals = _items_by_id(_dict(previous_state.get("realm")).get("vassals"))
    new_vassals = _items_by_id(_dict(current_state.get("realm")).get("vassals"))
    for ident in sorted(set(new_vassals) - set(old_vassals)):
        events.append({"type": "vassal_added", "subject": new_vassals[ident], "confidence": "save_diff"})
    for ident in sorted(set(old_vassals) - set(new_vassals)):
        events.append({"type": "vassal_removed", "subject": old_vassals[ident], "confidence": "save_diff"})

    old_wars = _items_by_id(previous_state.get("wars"))
    new_wars = _items_by_id(current_state.get("wars"))
    for ident in sorted(set(new_wars) - set(old_wars)):
        events.append({"type": "war_observed_started", "subject": new_wars[ident], "confidence": "save_diff"})
    for ident in sorted(set(old_wars) - set(new_wars)):
        events.append({"type": "war_observed_ended", "subject": old_wars[ident], "confidence": "save_diff"})

    old_player = _dict(previous_state.get("player"))
    new_player = _dict(current_state.get("player"))
    old_succession = [_id(item) for item in _list(old_player.get("succession")) if _id(item)]
    new_succession = [_id(item) for item in _list(new_player.get("succession")) if _id(item)]
    if old_succession != new_succession:
        events.append({"type": "succession_changed", "from": old_succession, "to": new_succession, "confidence": "save_diff"})

    old_traits = {str(item) for item in _list(old_player.get("traits"))}
    new_traits = {str(item) for item in _list(new_player.get("traits"))}
    for trait in sorted(new_traits - old_traits):
        events.append({"type": "trait_gained", "trait_id": trait, "confidence": "save_diff"})
    for trait in sorted(old_traits - new_traits):
        events.append({"type": "trait_lost", "trait_id": trait, "confidence": "save_diff"})

    for key in ("faith", "culture", "government"):
        if old_player.get(key) != new_player.get(key):
            events.append({
                "type": f"{key}_changed", "from": old_player.get(key),
                "to": new_player.get(key), "confidence": "save_diff",
            })

    old_events = _dict(previous_state.get("events"))
    new_events = _dict(current_state.get("events"))
    for category, event_type, confidence in (
        ("player_memories", "memory_added", "persistent_memory"),
        ("active_stories", "story_observed_started", "persistent_state"),
        ("important_actions", "important_action_added", "persistent_state"),
        ("persistent_event_state", "event_state_added", "persistent_state"),
    ):
        old_map = _event_map(old_events.get(category))
        new_map = _event_map(new_events.get(category))
        for ident in sorted(set(new_map) - set(old_map)):
            events.append({"type": event_type, "subject": new_map[ident], "confidence": confidence})

    return events


def build_ck3_delta(previous: JsonObject | None, current: JsonObject) -> JsonObject:
    old_state = dict((previous or {}).get("state")) if isinstance((previous or {}).get("state"), Mapping) else None
    new_state = dict(current.get("state")) if isinstance(current.get("state"), Mapping) else None
    initial = previous is None
    headline_changes = (
        _field_changes(_headline_state(old_state), _headline_state(new_state))
        if old_state is not None and new_state is not None else {}
    )
    semantic = _semantic_events(old_state, new_state)
    sha_changed = (previous or {}).get("sha256") != current.get("sha256")
    has_changes = bool(initial or headline_changes or semantic or sha_changed)

    fallback = _dict(current.get("fallback_metadata"))
    state = new_state or {}
    player = _dict(state.get("player"))
    primary = _dict(state.get("primary_title"))
    realm = _dict(state.get("realm"))
    analysis = _dict(state.get("analysis"))
    heir = _dict(_dict(analysis.get("succession")).get("primary_heir"))
    watchlist = _list(analysis.get("vassal_watchlist"))
    top_vassal = watchlist[0] if watchlist and isinstance(watchlist[0], Mapping) else None

    category_counts: dict[str, int] = {}
    for item in semantic:
        category = str(item.get("type") or "unknown")
        category_counts[category] = category_counts.get(category, 0) + 1

    return {
        "schema_version": 2,
        "kind": "wachterfeder-ck3-delta",
        "created_utc": datetime.now(tz=timezone.utc).isoformat(),
        "initial_snapshot": initial,
        "previous_save_sha256": (previous or {}).get("sha256"),
        "current_save_sha256": current.get("sha256"),
        "summary": {
            "has_changes": has_changes, "deep_analysis": bool(current.get("deep_analysis")),
            "headline_state_changes": len(headline_changes),
            "timeline_candidates": len(semantic), "timeline_by_type": category_counts,
            "compact_delta": True,
        },
        "current_state": {
            "game_date": state.get("game_date"),
            "game_version": state.get("game_version") or fallback.get("game_version"),
            "player_id": player.get("id"), "player_name": player.get("name") or fallback.get("player_name"),
            "primary_title": primary.get("key") or fallback.get("primary_title_name"),
            "primary_heir_id": heir.get("id"), "primary_heir_name": heir.get("name"),
            "family_members": sum(len(_list(items)) for items in _dict(state.get("family")).values()) if state else 0,
            "vassals": int(realm.get("vassal_count") or 0),
            "active_wars": len(_list(state.get("wars"))),
            "top_vassal_watch": dict(top_vassal) if isinstance(top_vassal, Mapping) else None,
        },
        "changes": {"headline_state": headline_changes, "timeline_candidates": semantic},
        "notes": [
            "Das Delta vergleicht nur einen kompakten Kernzustand; große Familien-, Vasallen- und Eventlisten werden nicht bei jeder Änderung vollständig dupliziert.",
            "Timeline-Kandidaten werden aus persistiertem Zustand und Save-Deltas erzeugt.",
            "Eine konkrete Eventoption gilt erst als exakt, wenn Save- oder Runtime-Daten sie eindeutig belegen.",
        ],
    }


def analyse_ck3_save(
    save_path: Path,
    *,
    rakaly_path: Path | None = None,
    root: Path | None = None,
) -> Ck3AnalysisResult:
    root = (root or Path(__file__).resolve().parents[2]).expanduser().resolve()
    save_file = resolve_ck3_save(save_path)
    local_root = root / ".wachterfeder" / "ck3"
    snapshot_path = local_root / "ck3.snapshot.json"
    delta_path = local_root / "ck3.delta.json"
    previous = _read_json(snapshot_path)

    resolved_rakaly = find_rakaly(rakaly_path, root)
    if resolved_rakaly:
        remember_rakaly(root, resolved_rakaly)

    current = build_ck3_snapshot(save_file, rakaly_path=resolved_rakaly, root=root)
    delta = build_ck3_delta(previous, current)

    stamp = datetime.fromtimestamp(save_file.stat().st_mtime).strftime("%Y%m%d-%H%M%S")
    history_delta_path = local_root / "history" / f"{stamp}-{current['sha256'][:8]}.delta.json"
    _write_json(current, snapshot_path)
    _write_json(delta, delta_path)
    _write_json(delta, history_delta_path)

    current_state = _dict(delta.get("current_state"))
    summary = _dict(delta.get("summary"))
    return Ck3AnalysisResult(
        save_file=save_file, snapshot_path=snapshot_path, delta_path=delta_path,
        history_delta_path=history_delta_path, initial_snapshot=bool(delta.get("initial_snapshot")),
        has_changes=bool(summary.get("has_changes")), deep_analysis=bool(summary.get("deep_analysis")),
        game_version=current_state.get("game_version"), player_name=current_state.get("player_name"),
        primary_title=current_state.get("primary_title"),
        family_members=int(current_state.get("family_members") or 0),
        vassals=int(current_state.get("vassals") or 0),
        event_changes=int(summary.get("timeline_candidates") or 0),
        rakaly_path=resolved_rakaly,
    )
