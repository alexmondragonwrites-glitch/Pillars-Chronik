#!/usr/bin/env python3
"""Read-only helpers for EET save resources beyond BALDUR.GAM.

Enhanced Edition saves keep persistent area/store resources in BALDUR.SAV and
embed the live CRE records of party members inside BALDUR.GAM. These helpers
extract chronology-relevant facts without copying game assets into the repo.
"""
from __future__ import annotations

import struct
import zlib
from collections import Counter
from pathlib import Path
from typing import Any, Callable, Mapping

JsonObject = dict[str, Any]
CRE_SIGNATURE = b"CRE V1.0"
SAV_SIGNATURE = b"SAV V1.0"
ARE_SIGNATURE = b"AREAV1.0"
AREA_VARIABLE_SIZE = 0x54
AREA_ACTOR_SIZE = 0x110

CLASS_NAMES = {
    1: "Mage", 2: "Fighter", 3: "Cleric", 4: "Thief", 5: "Bard",
    6: "Paladin", 7: "Fighter/Mage", 8: "Fighter/Cleric",
    9: "Fighter/Thief", 10: "Fighter/Mage/Thief", 11: "Druid",
    12: "Ranger", 13: "Mage/Thief", 14: "Cleric/Mage",
    15: "Cleric/Thief", 16: "Fighter/Druid", 17: "Fighter/Mage/Cleric",
    18: "Cleric/Ranger", 19: "Sorcerer", 20: "Monk",
}
RACE_NAMES = {1: "Human", 2: "Elf", 3: "Half-Elf", 4: "Dwarf", 5: "Halfling", 6: "Gnome", 7: "Half-Orc"}
ALIGNMENT_NAMES = {
    0x11: "Lawful Good", 0x12: "Lawful Neutral", 0x13: "Lawful Evil",
    0x21: "Neutral Good", 0x22: "True Neutral", 0x23: "Neutral Evil",
    0x31: "Chaotic Good", 0x32: "Chaotic Neutral", 0x33: "Chaotic Evil",
}
KIT_NAMES = {
    0x00000000: None,
    0x40000000: "Trueclass",
    0x02000000: "Enchanter",
    0x04000000: "Illusionist",
    0x08000000: "Invoker",
    0x10000000: "Necromancer",
    0x20000000: "Transmuter",
    0x40250000: "Sun Soul Monk",
}


def _u16(data: bytes, offset: int) -> int:
    return struct.unpack_from("<H", data, offset)[0]


def _u32(data: bytes, offset: int) -> int:
    return struct.unpack_from("<I", data, offset)[0]


def _i16(data: bytes, offset: int) -> int:
    return struct.unpack_from("<h", data, offset)[0]


def _i32(data: bytes, offset: int) -> int:
    return struct.unpack_from("<i", data, offset)[0]


def _text(raw: bytes) -> str:
    raw = raw.split(b"\x00", 1)[0]
    try:
        return raw.decode("utf-8").strip()
    except UnicodeDecodeError:
        return raw.decode("cp1252", errors="replace").strip()


def parse_cre_summary(
    cre: bytes,
    *,
    fallback_name: str | None = None,
    resolve_strref: Callable[[int], str | None] | None = None,
) -> JsonObject:
    """Parse the stable character fields from an embedded CRE V1.0 record."""
    if len(cre) < 0x2D4 or cre[:8] != CRE_SIGNATURE:
        return {}
    long_ref = _i32(cre, 0x08)
    short_ref = _i32(cre, 0x0C)
    resolved_name = None
    if resolve_strref is not None:
        for ref in (short_ref, long_ref):
            if ref >= 0:
                resolved_name = resolve_strref(ref)
                if resolved_name:
                    break
    class_id = cre[0x273]
    race_id = cre[0x272]
    alignment_id = cre[0x27B]
    kit = _u32(cre, 0x244)
    return {
        "name": fallback_name or resolved_name,
        "long_name_strref": long_ref,
        "short_name_strref": short_ref,
        "experience": _u32(cre, 0x18),
        "hit_points": {"current": _i16(cre, 0x24), "maximum": _i16(cre, 0x26)},
        "levels": [cre[0x234], cre[0x235], cre[0x236]],
        "attributes": {
            "strength": cre[0x238],
            "strength_percent": cre[0x239],
            "intelligence": cre[0x23A],
            "wisdom": cre[0x23B],
            "dexterity": cre[0x23C],
            "constitution": cre[0x23D],
            "charisma": cre[0x23E],
        },
        "class_id": class_id,
        "class_name": CLASS_NAMES.get(class_id),
        "race_id": race_id,
        "race_name": RACE_NAMES.get(race_id),
        "alignment_id": alignment_id,
        "alignment_name": ALIGNMENT_NAMES.get(alignment_id),
        "kit": f"0x{kit:08X}",
        "kit_name": KIT_NAMES.get(kit),
        "small_portrait": _text(cre[0x34:0x3C]),
        "large_portrait": _text(cre[0x3C:0x44]),
        "death_variable": _text(cre[0x280:0x2A0]),
        "dialog": _text(cre[0x2CC:0x2D4]),
    }


def enrich_party_from_embedded_cre(
    game_payload: bytes,
    party: list[JsonObject],
    *,
    resolve_strref: Callable[[int], str | None] | None = None,
) -> list[JsonObject]:
    enriched: list[JsonObject] = []
    for member in party:
        item = dict(member)
        offset = int(item.get("cre_offset") or 0)
        size = int(item.get("cre_size") or 0)
        if offset > 0 and size > 0 and offset + size <= len(game_payload):
            fallback = str(item.get("name") or "").strip()
            if fallback.startswith("*") or fallback.startswith("PartyMember"):
                fallback = ""
            cre = parse_cre_summary(
                game_payload[offset : offset + size],
                fallback_name=fallback or None,
                resolve_strref=resolve_strref,
            )
            if cre:
                if not cre.get("name"):
                    cre["name"] = cre.get("death_variable") or item.get("resource")
                item["character"] = cre
                item["name"] = cre.get("name") or item.get("name")
        enriched.append(item)
    return enriched


def parse_sav_v1(payload: bytes) -> dict[str, bytes]:
    """Decompress every resource from a SAV V1.0 archive."""
    if len(payload) < 8 or payload[:8] != SAV_SIGNATURE:
        raise ValueError("Nicht unterstütztes BALDUR.SAV-Format")
    offset = 8
    resources: dict[str, bytes] = {}
    while offset < len(payload):
        if offset + 4 > len(payload):
            raise ValueError("Abgeschnittener SAV-Dateiname")
        filename_length = _u32(payload, offset)
        offset += 4
        if filename_length <= 0 or offset + filename_length + 8 > len(payload):
            raise ValueError("Ungültiger SAV-Dateieintrag")
        filename = _text(payload[offset : offset + filename_length])
        offset += filename_length
        uncompressed_size = _u32(payload, offset)
        compressed_size = _u32(payload, offset + 4)
        offset += 8
        end = offset + compressed_size
        if end > len(payload):
            raise ValueError(f"Abgeschnittene SAV-Ressource: {filename}")
        raw = zlib.decompress(payload[offset:end])
        offset = end
        if len(raw) != uncompressed_size:
            raise ValueError(f"Falsche Größe nach SAV-Dekompression: {filename}")
        resources[filename] = raw
    return resources


def parse_area_variables(area: bytes) -> JsonObject:
    if len(area) < 0xE4 or area[:8] != ARE_SIGNATURE:
        return {}
    offset = _u32(area, 0x88)
    count = _u32(area, 0x8C)
    values: JsonObject = {}
    for index in range(count):
        start = offset + index * AREA_VARIABLE_SIZE
        if start + AREA_VARIABLE_SIZE > len(area):
            break
        name = _text(area[start : start + 0x20])
        if name:
            values[name] = _i32(area, start + 0x28)
    return values


def parse_area_actor_talks(
    area: bytes,
    *,
    resolve_strref: Callable[[int], str | None] | None = None,
) -> list[JsonObject]:
    """Return persistent actor talk counters and their embedded dialog identity."""
    if len(area) < 0xE4 or area[:8] != ARE_SIGNATURE:
        return []
    actor_offset = _u32(area, 0x54)
    actor_count = _u16(area, 0x58)
    actors: list[JsonObject] = []
    for index in range(actor_count):
        start = actor_offset + index * AREA_ACTOR_SIZE
        if start + AREA_ACTOR_SIZE > len(area):
            break
        talk_count = _u32(area, start + 0x44)
        if talk_count == 0:
            continue
        actor: JsonObject = {
            "index": index,
            "name": _text(area[start : start + 0x20]),
            "talk_count": talk_count,
            "actor_dialog": _text(area[start + 0x48 : start + 0x50]),
            "cre_resource": _text(area[start + 0x80 : start + 0x88]),
        }
        cre_offset = _u32(area, start + 0x88)
        cre_size = _u32(area, start + 0x8C)
        if cre_offset > 0 and cre_size > 0 and cre_offset + cre_size <= len(area):
            cre = parse_cre_summary(
                area[cre_offset : cre_offset + cre_size],
                fallback_name=actor["name"] if actor["name"] not in ("", "None") else None,
                resolve_strref=resolve_strref,
            )
            if cre:
                actor["name"] = cre.get("name") or cre.get("death_variable") or actor["name"]
                actor["dialog"] = cre.get("dialog") or actor["actor_dialog"]
                actor["death_variable"] = cre.get("death_variable")
        actors.append(actor)
    return actors


def collect_sav_state(
    sav_path: Path,
    *,
    resolve_strref: Callable[[int], str | None] | None = None,
) -> JsonObject:
    resources = parse_sav_v1(sav_path.read_bytes())
    types = Counter(Path(name).suffix.casefold() for name in resources)
    area_variables: JsonObject = {}
    actor_talks: JsonObject = {}
    for name, data in resources.items():
        if not name.casefold().endswith(".are"):
            continue
        area = Path(name).stem.upper()
        variables = parse_area_variables(data)
        if variables:
            area_variables[area] = variables
        # Keep every saved area in the snapshot, even when no actor has ever
        # been spoken to. This makes the area count exact while actor_talk_delta
        # simply ignores empty lists.
        actor_talks[area] = parse_area_actor_talks(data, resolve_strref=resolve_strref)
    return {
        "resource_count": len(resources),
        "resource_types": {key or "<none>": value for key, value in sorted(types.items())},
        "area_count": int(types.get(".are", 0)),
        "area_variables": area_variables,
        "actor_talks": actor_talks,
        "has_default_toh": any(name.casefold() == "default.toh" for name in resources),
    }


def actor_talk_delta(previous: Mapping[str, Any] | None, current: Mapping[str, Any]) -> list[JsonObject]:
    """Return actors whose persistent NumTimesTalkedTo counter increased."""
    def index(state: Mapping[str, Any] | None) -> dict[tuple[str, str], JsonObject]:
        result: dict[tuple[str, str], JsonObject] = {}
        for area, actors in (state or {}).get("actor_talks", {}).items():
            if not isinstance(actors, list):
                continue
            for actor in actors:
                if not isinstance(actor, Mapping):
                    continue
                identity = str(actor.get("death_variable") or actor.get("dialog") or actor.get("name") or actor.get("index"))
                result[(str(area), identity)] = dict(actor)
        return result

    old = index(previous)
    new = index(current)
    changed: list[JsonObject] = []
    for key, actor in new.items():
        old_count = int(old.get(key, {}).get("talk_count", 0))
        new_count = int(actor.get("talk_count", 0))
        if new_count > old_count:
            changed.append({
                "area": key[0],
                "actor": actor.get("name") or key[1],
                "dialog": actor.get("dialog"),
                "from": old_count,
                "to": new_count,
            })
    return changed
