#!/usr/bin/env python3
"""Real-save refinements for the Wächterfeder CK3 analysis layer.

This layer uses findings from an actual CK3 1.19.0.5 Ironman save. It keeps the
conservative enhanced parser and adds strategic context without pretending that
ambiguous save fields have stronger semantics than the save proves.
"""
from __future__ import annotations

from typing import Any, Mapping

try:
    from tools.wachterfeder import ck3_enhanced as enhanced
except ModuleNotFoundError:
    import ck3_enhanced as enhanced

JsonObject = dict[str, Any]

# Keep the original enhanced normalizer even if this module is imported twice.
_ORIGINAL_NORMALIZE = getattr(
    enhanced,
    "_wachterfeder_refined_original_normalize",
    enhanced.normalize_ck3_state,
)
setattr(enhanced, "_wachterfeder_refined_original_normalize", _ORIGINAL_NORMALIZE)

Ck3Error = enhanced.Ck3Error
Ck3AnalysisResult = enhanced.Ck3AnalysisResult
candidate_ck3_save_roots = enhanced.candidate_ck3_save_roots
newest_ck3_save = enhanced.newest_ck3_save
resolve_ck3_save = enhanced.resolve_ck3_save
inspect_ck3_envelope = enhanced.inspect_ck3_envelope
fallback_metadata = enhanced.fallback_metadata
find_rakaly = enhanced.find_rakaly
remember_rakaly = enhanced.remember_rakaly
rakaly_version = enhanced.rakaly_version
clean_ck3_text = enhanced.clean_ck3_text


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
    if isinstance(value, (str, int)) and not isinstance(value, bool):
        return str(value)
    return None


def _num(value: Any) -> float | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    return None


def _date_tuple(value: Any) -> tuple[int, int, int] | None:
    return enhanced._date_tuple(value)  # noqa: SLF001


def _future_of(value: Any, game_date: Any) -> bool | None:
    parsed = _date_tuple(value)
    current = _date_tuple(game_date)
    if not parsed or not current:
        return None
    return parsed > current


def _display_name(value: Any) -> Any:
    if not isinstance(value, str):
        return value
    return value.replace("_", " ") if "_" in value else value


def _character_lookup(raw: JsonObject) -> tuple[JsonObject, dict[str, JsonObject], dict[str, JsonObject]]:
    state = enhanced.base._unwrap_gamestate(raw)  # noqa: SLF001
    characters = enhanced.base._characters(state)  # noqa: SLF001
    titles = enhanced.base._titles(state)  # noqa: SLF001
    return state, characters, titles


def _short_character(character_id: Any, characters: Mapping[str, JsonObject]) -> JsonObject | None:
    cid = _id(character_id)
    if not cid or cid not in characters:
        return {"id": cid, "name": None} if cid else None
    raw = characters[cid]
    return {
        "id": cid,
        "name": _display_name(raw.get("first_name") or raw.get("name")),
        "dynasty_house": _id(raw.get("dynasty_house")),
    }


def _resolve_event_references(
    event: Mapping[str, Any],
    characters: Mapping[str, JsonObject],
    game_date: Any,
) -> JsonObject:
    row = dict(event)
    row["type"] = row.get("type") or row.get("memory_type")

    participants = row.get("participants")
    if isinstance(participants, Mapping):
        resolved: JsonObject = {}
        for role, value in participants.items():
            if _id(value):
                resolved[str(role)] = _short_character(value, characters)
        if resolved:
            row["participant_details"] = resolved

    references: JsonObject = {}
    for key in ("owner", "character", "actor", "recipient", "target", "claimant", "attacker", "defender"):
        if _id(row.get(key)):
            references[key] = _short_character(row.get(key), characters)
    if references:
        row["character_references"] = references

    temporal: JsonObject = {"observed_in_save_date": game_date}
    recorded = row.get("date") or row.get("start_date")
    if recorded is not None:
        temporal["recorded_event_date"] = recorded
        temporal["recorded_event_date_is_future"] = _future_of(recorded, game_date)
    if row.get("end_date") is not None:
        temporal["raw_end_date"] = row.get("end_date")
        temporal["raw_end_date_is_future"] = _future_of(row.get("end_date"), game_date)
        temporal["end_date_interpretation"] = (
            "Persistenter End-/Ablaufwert des Save-Datensatzes; wird nicht als Datum des Ereignisses interpretiert."
        )
    if recorded is None:
        temporal["event_date_status"] = "im Save nicht eindeutig als Ereignisdatum belegt"
    else:
        temporal["event_date_status"] = "persistenter Datumswert am Ereignisdatensatz"
    row["temporal_evidence"] = temporal
    return row


def _refine_events(
    normalized: JsonObject,
    characters: Mapping[str, JsonObject],
    game_date: Any,
) -> None:
    events = _dict(normalized.get("events"))
    for category in ("player_memories", "active_stories", "important_actions", "persistent_event_state"):
        events[category] = [
            _resolve_event_references(item, characters, game_date)
            for item in _list(events.get(category))
            if isinstance(item, Mapping)
        ]
    normalized["events"] = events


def _war_side_observation(side: Any) -> JsonObject:
    block = _dict(side)
    participant_casualties = 0
    casualty_rows = 0
    for participant in _list(block.get("participants")):
        if not isinstance(participant, Mapping):
            continue
        casualties = participant.get("casualties")
        if isinstance(casualties, (int, float)) and not isinstance(casualties, bool):
            participant_casualties += int(casualties)
            casualty_rows += 1
    attrition = _dict(block.get("casualties")).get("attrition")
    return {
        "recorded_participant_casualties": participant_casualties if casualty_rows else None,
        "recorded_attrition": attrition if isinstance(attrition, (int, float)) else None,
        "note": "Werte werden getrennt ausgegeben; Wächterfeder summiert sie nicht ohne belegte CK3-Semantik.",
    }


def _war_context(
    war: Mapping[str, Any],
    player_id: str,
    characters: Mapping[str, JsonObject],
    titles: Mapping[str, JsonObject],
    liege_id: str | None,
) -> JsonObject:
    cb = _dict(war.get("casus_belli"))
    attacker = _id(cb.get("attacker"))
    defender = _id(cb.get("defender"))
    if attacker == player_id:
        role = "attacker"
        opponent_id = defender
        own_side = war.get("attacker")
        enemy_side = war.get("defender")
    elif defender == player_id:
        role = "defender"
        opponent_id = attacker
        own_side = war.get("defender")
        enemy_side = war.get("attacker")
    else:
        role = "participant"
        opponent_id = None
        own_side = None
        enemy_side = None

    targets: list[JsonObject] = []
    for ident in _list(cb.get("targeted_titles")):
        tid = _id(ident)
        if tid and tid in titles:
            title = enhanced.base._title_summary(tid, titles[tid])  # noqa: SLF001
            targets.append(title)
        elif tid:
            targets.append({"index": tid, "key": None})

    return {
        "id": war.get("id"),
        "name": war.get("name") or war.get("title"),
        "start_date": war.get("start_date"),
        "role": role,
        "opponent": _short_character(opponent_id, characters) if opponent_id else None,
        "against_liege": bool(opponent_id and liege_id and opponent_id == liege_id),
        "casus_belli_type": cb.get("type"),
        "claimant": _short_character(cb.get("claimant"), characters) if _id(cb.get("claimant")) else None,
        "target_titles": targets,
        "player_side_observation": _war_side_observation(own_side),
        "opponent_side_observation": _war_side_observation(enemy_side),
        "interpretation": "Strategischer Kontext aus dem persistenten aktiven Kriegsdatensatz.",
    }


def _inheritance_opportunities(player_id: str, vassals: list[JsonObject]) -> list[JsonObject]:
    rows: list[JsonObject] = []
    for vassal in vassals:
        succession = [_id(item) for item in _list(vassal.get("succession")) if _id(item)]
        if player_id not in succession:
            continue
        rows.append({
            "vassal_id": vassal.get("id"),
            "vassal_name": _display_name(vassal.get("name")),
            "player_succession_position": succession.index(player_id) + 1,
            "primary_title": (_list(vassal.get("titles")) or [None])[0],
            "note": (
                "Der Spieler steht im aktuell gespeicherten Nachfolgefeld dieses Vasallen. "
                "Das ist eine Momentaufnahme und keine Garantie für eine spätere Erbschaft."
            ),
        })
    return rows


def _refine_vassal_watchlist(analysis: JsonObject) -> None:
    refined: list[JsonObject] = []
    for item in _list(analysis.get("vassal_watchlist")):
        if not isinstance(item, Mapping):
            continue
        row = dict(item)
        row["display_name"] = _display_name(row.get("name"))
        reasons = [str(reason) for reason in _list(row.get("reasons"))]
        context_flags: list[str] = []
        if "abweichender Glaube" in reasons:
            reasons.remove("abweichender Glaube")
            context_flags.append("abweichender Glaube")
            if row.get("attention") == "medium" and not reasons:
                row["attention"] = "low"
        row["reasons"] = reasons
        row["context_flags"] = context_flags
        row["interpretation"] = (
            "Aufmerksamkeit wird aus gespeicherten Macht-/Stärkewerten abgeleitet. "
            "Glaubensunterschiede sind nur Kontext und erhöhen allein nicht die Risikostufe."
        )
        refined.append(row)
    rank = {"high": 0, "medium": 1, "low": 2}
    refined.sort(key=lambda item: (
        rank.get(str(item.get("attention")), 3),
        -(float(item.get("power_score_ratio") or 0)),
        str(item.get("display_name") or item.get("name") or ""),
    ))
    analysis["vassal_watchlist"] = refined


def normalize_ck3_state(raw: JsonObject) -> JsonObject:
    normalized = _ORIGINAL_NORMALIZE(raw)
    state, characters, titles = _character_lookup(raw)
    player = _dict(normalized.get("player"))
    player_id = _id(player.get("id"))
    if not player_id:
        return normalized

    game_date = normalized.get("game_date")
    _refine_events(normalized, characters, game_date)

    family = _dict(normalized.get("family"))
    for relation, members in family.items():
        for member in _list(members):
            if isinstance(member, dict):
                member["display_name"] = _display_name(member.get("name"))
    player["display_name"] = _display_name(player.get("name"))
    normalized["player"] = player

    realm = _dict(normalized.get("realm"))
    vassals = [dict(item) for item in _list(realm.get("vassals")) if isinstance(item, Mapping)]
    for vassal in vassals:
        vassal["display_name"] = _display_name(vassal.get("name"))
    realm["vassals"] = vassals
    normalized["realm"] = realm

    analysis = _dict(normalized.get("analysis"))
    _refine_vassal_watchlist(analysis)
    analysis["inheritance_opportunities"] = _inheritance_opportunities(player_id, vassals)

    succession = _dict(analysis.get("succession"))
    heir = _dict(succession.get("primary_heir"))
    analysis["succession_context"] = {
        "primary_heir_id": heir.get("id"),
        "primary_heir_name": _display_name(heir.get("name")),
        "primary_heir_age": heir.get("age_years"),
        "primary_heir_under_16": (
            isinstance(heir.get("age_years"), int) and heir.get("age_years") < 16
        ),
        "note": "Nur beobachtete Nachfolgelinie; Titelaufteilung bei Erbfall wird noch nicht simuliert.",
    }

    external = _dict(normalized.get("external"))
    liege = _dict(external.get("liege"))
    liege_holder = _dict(liege.get("holder"))
    liege_id = _id(liege_holder.get("id"))

    wars = [dict(item) for item in _list(normalized.get("wars")) if isinstance(item, Mapping)]
    war_contexts = [
        _war_context(war, player_id, characters, titles, liege_id)
        for war in wars
    ]
    analysis["wars"] = war_contexts

    player_strength = _num(player.get("strength"))
    liege_strength = _num(liege_holder.get("strength"))
    analysis["liege_context"] = {
        "liege_id": liege_id,
        "liege_name": _display_name(liege_holder.get("name")),
        "liege_primary_title": _dict(liege.get("title")).get("key"),
        "player_strength_ratio_to_liege": (
            round(player_strength / liege_strength, 4)
            if player_strength is not None and liege_strength and liege_strength > 0
            else None
        ),
        "at_war_with_liege": any(bool(item.get("against_liege")) for item in war_contexts),
        "note": "Stärkeverhältnis nutzt nur den im Save gespeicherten strength-Wert und ist kein vollständiger Kriegsprognosewert.",
    }
    normalized["analysis"] = analysis
    return normalized


# Patch the enhanced module's global normalizer. Its snapshot/analyse functions resolve
# this global at runtime, so all stable I/O, schema-migration and delta code stays reused.
enhanced.normalize_ck3_state = normalize_ck3_state

build_ck3_snapshot = enhanced.build_ck3_snapshot
build_ck3_delta = enhanced.build_ck3_delta
analyse_ck3_save = enhanced.analyse_ck3_save
read_ck3_config = enhanced.read_ck3_config


__all__ = [
    "Ck3Error", "Ck3AnalysisResult", "analyse_ck3_save", "build_ck3_delta",
    "build_ck3_snapshot", "candidate_ck3_save_roots", "clean_ck3_text",
    "find_rakaly", "inspect_ck3_envelope", "newest_ck3_save",
    "normalize_ck3_state", "read_ck3_config", "remember_rakaly",
]
