#!/usr/bin/env python3
"""Baldur's Gate EET adapter for Wächterfeder.

The adapter intentionally stays read-only. It reads ``BALDUR.GAM`` from an
Enhanced Edition Trilogy save, resolves journal text through the local
``dialog.tlk`` where possible, and writes one current snapshot plus a compact
delta below ``.wachterfeder/eet``.

Dialogue reconstruction is deliberately a second step. EET installs already
contain WeiDU-compatible resources, so a later resolver can use the local game
installation without copying copyrighted assets into the repository.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import struct
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping, Sequence

JsonObject = dict[str, Any]
_MISSING = object()
NPC_STRUCT_SIZE_V20 = 0x160
GLOBAL_STRUCT_SIZE_V20 = 0x54
JOURNAL_STRUCT_SIZE_V20 = 0x0C


class EetError(RuntimeError):
    """Expected, user-facing EET adapter error."""


@dataclass(frozen=True)
class EetGameAssets:
    game_root: Path
    chitin_key: Path
    dialog_tlk: Path
    language: str
    weidu: Path | None


@dataclass(frozen=True)
class EetAnalysisResult:
    baldurgam: Path
    snapshot_path: Path
    delta_path: Path
    history_delta_path: Path
    initial_snapshot: bool
    has_changes: bool
    current_area: str
    party_members: int
    changed_globals: int
    new_journal_entries: int
    party_changes: int
    weidu_available: bool


def _read_u16(payload: bytes, offset: int) -> int:
    return struct.unpack_from("<H", payload, offset)[0]


def _read_u32(payload: bytes, offset: int) -> int:
    return struct.unpack_from("<I", payload, offset)[0]


def _read_i32(payload: bytes, offset: int) -> int:
    return struct.unpack_from("<i", payload, offset)[0]


def _decode_fixed(raw: bytes) -> str:
    return raw.split(b"\x00", 1)[0].decode("ascii", errors="replace").strip()


def _decode_text(raw: bytes) -> str:
    raw = raw.split(b"\x00", 1)[0]
    try:
        return raw.decode("utf-8")
    except UnicodeDecodeError:
        return raw.decode("cp1252", errors="replace")


def sha256_file(path: Path, chunk_size: int = 1024 * 1024) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(chunk_size):
            digest.update(chunk)
    return digest.hexdigest()


def candidate_eet_save_roots(home: Path | None = None) -> list[Path]:
    """Return common BG2EE/EET save roots on Windows."""
    home = home or Path.home()
    documents = [home / "Documents"]
    onedrive = os.environ.get("OneDrive")
    if onedrive:
        documents.append(Path(onedrive) / "Documents")

    candidates: list[Path] = []
    for root in documents:
        base = root / "Baldur's Gate II - Enhanced Edition"
        candidates.extend((base / "save", base / "mpsave"))

    unique: list[Path] = []
    seen: set[str] = set()
    for path in candidates:
        key = str(path).casefold()
        if key not in seen:
            seen.add(key)
            unique.append(path)
    return unique


def newest_eet_save(save_roots: Sequence[Path] | None = None) -> Path | None:
    """Return the save directory containing the newest BALDUR.GAM."""
    roots = list(save_roots or candidate_eet_save_roots())
    candidates: list[Path] = []
    for root in roots:
        if not root.is_dir():
            continue
        for gam in root.rglob("BALDUR.GAM"):
            if gam.is_file():
                candidates.append(gam)
    newest = max(candidates, key=lambda path: path.stat().st_mtime, default=None)
    return newest.parent if newest else None


def resolve_baldur_gam(path: Path) -> Path:
    """Resolve a save directory or BALDUR.GAM path to the game-state file."""
    path = path.expanduser().resolve()
    if path.is_file() and path.name.casefold() == "baldur.gam":
        return path
    if path.is_dir():
        direct = path / "BALDUR.GAM"
        if direct.is_file():
            return direct
        matches = sorted(path.rglob("BALDUR.GAM"))
        if len(matches) == 1:
            return matches[0]
        if len(matches) > 1:
            return max(matches, key=lambda item: item.stat().st_mtime)
    raise EetError(f"BALDUR.GAM wurde nicht gefunden: {path}")


def _find_dialog_tlk(game_root: Path, language: str) -> Path | None:
    candidates = [
        game_root / "lang" / language / "dialog.tlk",
        game_root / "lang" / language.casefold() / "dialog.tlk",
        game_root / "dialog.tlk",
        game_root / "DIALOG.TLK",
    ]
    for candidate in candidates:
        if candidate.is_file():
            return candidate
    return None


def _find_weidu(game_root: Path) -> Path | None:
    preferred = (
        game_root / "weidu.exe",
        game_root / "WeiDU.exe",
        game_root / "weidu",
    )
    for candidate in preferred:
        if candidate.is_file():
            return candidate
    setup_tools = sorted(game_root.glob("setup-*.exe"))
    return setup_tools[0] if setup_tools else None


def resolve_eet_game_assets(path: Path, language: str = "de_DE") -> EetGameAssets:
    """Resolve an EET/BG2EE game root from the root or a nested resource path."""
    path = path.expanduser().resolve()
    starts = [path] if path.is_dir() else [path.parent]
    for start in starts:
        for candidate in (start, *start.parents):
            chitin = candidate / "chitin.key"
            if not chitin.is_file():
                chitin = candidate / "CHITIN.KEY"
            if not chitin.is_file():
                continue
            tlk = _find_dialog_tlk(candidate, language)
            if tlk is None:
                # German installs are commonly ``de_DE``; accept ``de`` as a
                # convenience and probe the installed language folders.
                lang_root = candidate / "lang"
                if lang_root.is_dir():
                    for folder in sorted(lang_root.iterdir()):
                        if folder.is_dir() and folder.name.casefold().startswith(language[:2].casefold()):
                            probe = folder / "dialog.tlk"
                            if probe.is_file():
                                tlk = probe
                                language = folder.name
                                break
            if tlk is None:
                continue
            return EetGameAssets(
                game_root=candidate,
                chitin_key=chitin,
                dialog_tlk=tlk,
                language=language,
                weidu=_find_weidu(candidate),
            )
    raise EetError(
        "Keine EET/BG2EE-Installation mit chitin.key und dialog.tlk gefunden."
    )


def read_tlk_string(tlk_path: Path, strref: int) -> str | None:
    """Read one TLK V1 string without extracting the complete string table."""
    if strref < 0:
        return None
    payload = tlk_path.read_bytes()
    if len(payload) < 0x12 or payload[:4] != b"TLK ":
        raise EetError(f"Ungültige dialog.tlk: {tlk_path}")
    count = _read_u32(payload, 0x0A)
    strings_offset = _read_u32(payload, 0x0E)
    if strref >= count:
        return None
    entry_offset = 0x12 + strref * 0x1A
    if entry_offset + 0x1A > len(payload):
        return None
    relative = _read_u32(payload, entry_offset + 0x12)
    length = _read_u32(payload, entry_offset + 0x16)
    start = strings_offset + relative
    end = start + length
    if start < 0 or end > len(payload):
        return None
    return _decode_text(payload[start:end])


def _parse_party_member(payload: bytes, offset: int, index: int) -> JsonObject:
    if offset + NPC_STRUCT_SIZE_V20 > len(payload):
        raise EetError("BALDUR.GAM enthält einen abgeschnittenen Party-Eintrag.")
    cre_offset = _read_u32(payload, offset + 0x04)
    cre_size = _read_u32(payload, offset + 0x08)
    resource = _decode_fixed(payload[offset + 0x0C : offset + 0x14])
    current_area = _decode_fixed(payload[offset + 0x18 : offset + 0x20])
    name = _decode_text(payload[offset + 0xC0 : offset + 0xE0])
    return {
        "index": index,
        "party_order": _read_u16(payload, offset + 0x02),
        "resource": resource,
        "name": name or resource or f"PartyMember{index + 1}",
        "current_area": current_area,
        "x": _read_u16(payload, offset + 0x20),
        "y": _read_u16(payload, offset + 0x22),
        "cre_offset": cre_offset,
        "cre_size": cre_size,
        "talk_count": _read_u32(payload, offset + 0xE0),
    }


def _parse_globals(payload: bytes, offset: int, count: int) -> JsonObject:
    variables: JsonObject = {}
    for index in range(count):
        start = offset + index * GLOBAL_STRUCT_SIZE_V20
        end = start + GLOBAL_STRUCT_SIZE_V20
        if end > len(payload):
            raise EetError("BALDUR.GAM enthält einen abgeschnittenen GLOBAL-Block.")
        name = _decode_text(payload[start : start + 0x20])
        if not name:
            continue
        variables[name] = _read_i32(payload, start + 0x28)
    return variables


def _parse_journal(
    payload: bytes,
    offset: int,
    count: int,
    tlk_path: Path | None,
) -> list[JsonObject]:
    entries: list[JsonObject] = []
    for index in range(count):
        start = offset + index * JOURNAL_STRUCT_SIZE_V20
        end = start + JOURNAL_STRUCT_SIZE_V20
        if end > len(payload):
            raise EetError("BALDUR.GAM enthält einen abgeschnittenen Journal-Block.")
        strref = _read_u32(payload, start)
        location_flag = payload[start + 0x0B]
        text = None
        # 0xFF means an internal TLK reference. External TOH text is left
        # unresolved until we inspect a real EET save and add TOH V2 support.
        if tlk_path is not None and location_flag == 0xFF:
            text = read_tlk_string(tlk_path, strref)
        entries.append(
            {
                "index": index,
                "strref": strref,
                "time_seconds": _read_u32(payload, start + 0x04),
                "chapter": payload[start + 0x08],
                "read_by": payload[start + 0x09],
                "section": payload[start + 0x0A],
                "location_flag": location_flag,
                "text": text,
            }
        )
    return entries


def parse_game_v20(payload: bytes, tlk_path: Path | None = None) -> JsonObject:
    """Parse the chronology-relevant subset of GAME V2.0 / BALDUR.GAM."""
    if len(payload) < 0xA4:
        raise EetError("BALDUR.GAM ist zu klein.")
    if payload[:4] != b"GAME" or payload[4:8] != b"V2.0":
        signature = payload[:8].decode("ascii", errors="replace")
        raise EetError(f"Nicht unterstütztes GAM-Format: {signature!r}")

    party_offset = _read_u32(payload, 0x20)
    party_count = _read_u32(payload, 0x24)
    global_offset = _read_u32(payload, 0x38)
    global_count = _read_u32(payload, 0x3C)
    journal_count = _read_u32(payload, 0x4C)
    journal_offset = _read_u32(payload, 0x50)

    party = [
        _parse_party_member(payload, party_offset + index * NPC_STRUCT_SIZE_V20, index)
        for index in range(party_count)
    ]
    current_area = _decode_fixed(payload[0x58:0x60])
    active_member = _read_u16(payload, 0x1C)
    if active_member != 0xFFFF and active_member < len(party):
        current_area = party[active_member].get("current_area") or current_area

    return {
        "game_time": _read_u32(payload, 0x08),
        "party_gold": _read_u32(payload, 0x18),
        "party_reputation": _read_u32(payload, 0x54),
        "main_area": _decode_fixed(payload[0x40:0x48]),
        "current_area": current_area,
        "current_worldmap": _decode_fixed(payload[0x8C:0x94]),
        "current_campaign": _decode_fixed(payload[0x94:0x9C]),
        "party": party,
        "global_variables": _parse_globals(payload, global_offset, global_count),
        "journal_entries": _parse_journal(payload, journal_offset, journal_count, tlk_path),
    }


def build_eet_snapshot(
    save_path: Path,
    *,
    game_assets: EetGameAssets | None = None,
) -> JsonObject:
    baldurgam = resolve_baldur_gam(save_path)
    payload = baldurgam.read_bytes()
    parsed = parse_game_v20(payload, game_assets.dialog_tlk if game_assets else None)
    stat = baldurgam.stat()
    return {
        "schema_version": 1,
        "kind": "wachterfeder-eet-snapshot",
        "source_name": baldurgam.parent.name,
        "source_file": baldurgam.name,
        "source_size": stat.st_size,
        "source_modified_utc": datetime.fromtimestamp(
            stat.st_mtime, tz=timezone.utc
        ).isoformat(),
        "sha256": sha256_file(baldurgam),
        "inspected_utc": datetime.now(tz=timezone.utc).isoformat(),
        "metadata": {
            "game_time": parsed["game_time"],
            "party_gold": parsed["party_gold"],
            "party_reputation": parsed["party_reputation"],
            "main_area": parsed["main_area"],
            "current_area": parsed["current_area"],
            "current_worldmap": parsed["current_worldmap"],
            "current_campaign": parsed["current_campaign"],
            "party_count": len(parsed["party"]),
            "journal_count": len(parsed["journal_entries"]),
        },
        "party": parsed["party"],
        "global_variable_count": len(parsed["global_variables"]),
        "global_variables": parsed["global_variables"],
        "journal_entries": parsed["journal_entries"],
        "local_assets": {
            "language": game_assets.language if game_assets else None,
            "weidu_available": bool(game_assets and game_assets.weidu),
        },
        "warnings": [
            "Dialogpfade werden im EET-MVP noch nicht rekonstruiert.",
            "Journaltexte mit externen TOH-Verweisen bleiben vorerst ohne Text.",
        ],
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
            "change": "added" if old is _MISSING else "removed" if new is _MISSING else "changed",
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
            "change": "added" if old is _MISSING else "removed" if new is _MISSING else "changed",
        }
    return changes


def _party_key(item: Mapping[str, Any]) -> str:
    return str(item.get("resource") or item.get("name") or item.get("index"))


def _party_changes(previous: JsonObject | None, current: JsonObject) -> JsonObject:
    old_party = {
        _party_key(item): item
        for item in (previous or {}).get("party", [])
        if isinstance(item, Mapping)
    }
    new_party = {
        _party_key(item): item
        for item in current.get("party", [])
        if isinstance(item, Mapping)
    }
    added = [dict(new_party[key]) for key in sorted(set(new_party) - set(old_party))]
    removed = [dict(old_party[key]) for key in sorted(set(old_party) - set(new_party))]
    changed: JsonObject = {}
    for key in sorted(set(old_party) & set(new_party)):
        delta = _field_changes(old_party[key], new_party[key])
        if delta:
            changed[key] = delta
    return {"added": added, "removed": removed, "changed": changed}


def _journal_identity(item: Mapping[str, Any]) -> tuple[int, int, int, int]:
    return (
        int(item.get("strref", -1)),
        int(item.get("time_seconds", -1)),
        int(item.get("chapter", -1)),
        int(item.get("section", -1)),
    )


def _new_journal_entries(previous: JsonObject | None, current: JsonObject) -> list[JsonObject]:
    old = {
        _journal_identity(item)
        for item in (previous or {}).get("journal_entries", [])
        if isinstance(item, Mapping)
    }
    return [
        dict(item)
        for item in current.get("journal_entries", [])
        if isinstance(item, Mapping) and _journal_identity(item) not in old
    ]


def build_eet_delta(previous: JsonObject | None, current: JsonObject) -> JsonObject:
    metadata_changes = _field_changes(
        (previous or {}).get("metadata"), current.get("metadata")
    )
    global_changes = _global_changes(previous, current)
    party_changes = _party_changes(previous, current)
    new_journal = _new_journal_entries(previous, current)
    initial = previous is None
    party_change_count = (
        len(party_changes["added"])
        + len(party_changes["removed"])
        + len(party_changes["changed"])
    )
    has_changes = bool(
        initial or metadata_changes or global_changes or party_change_count or new_journal
    )
    return {
        "schema_version": 1,
        "kind": "wachterfeder-eet-delta",
        "created_utc": datetime.now(tz=timezone.utc).isoformat(),
        "initial_snapshot": initial,
        "previous_save_sha256": (previous or {}).get("sha256"),
        "current_save_sha256": current.get("sha256"),
        "summary": {
            "has_changes": has_changes,
            "metadata_changes": len(metadata_changes),
            "changed_globals": len(global_changes),
            "party_changes": party_change_count,
            "new_journal_entries": len(new_journal),
        },
        "current_state": {
            "current_area": (current.get("metadata") or {}).get("current_area"),
            "party_gold": (current.get("metadata") or {}).get("party_gold"),
            "party_reputation": (current.get("metadata") or {}).get("party_reputation"),
            "party_count": (current.get("metadata") or {}).get("party_count"),
            "current_campaign": (current.get("metadata") or {}).get("current_campaign"),
        },
        "changes": {
            "metadata": metadata_changes,
            "global_variables": global_changes,
            "party": party_changes,
            "new_journal_entries": new_journal,
        },
        "notes": [
            "Das EET-Delta enthält nur Änderungen gegenüber der letzten erfolgreichen Auswertung.",
            "Dialogpfade werden in diesem MVP noch nicht als sicher rekonstruiert.",
        ],
    }


def _read_json(path: Path) -> JsonObject | None:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (FileNotFoundError, OSError, json.JSONDecodeError):
        return None
    return payload if isinstance(payload, dict) else None


def _write_json(payload: JsonObject, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def analyse_eet_save(
    save_path: Path,
    *,
    game_path: Path,
    language: str = "de_DE",
    root: Path | None = None,
) -> EetAnalysisResult:
    root = (root or Path(__file__).resolve().parents[2]).expanduser().resolve()
    local_root = root / ".wachterfeder" / "eet"
    assets = resolve_eet_game_assets(game_path, language)
    baldurgam = resolve_baldur_gam(save_path)
    current = build_eet_snapshot(baldurgam, game_assets=assets)

    snapshot_path = local_root / "eet.snapshot.json"
    delta_path = local_root / "eet.delta.json"
    previous = _read_json(snapshot_path)
    delta = build_eet_delta(previous, current)

    stamp = datetime.fromtimestamp(baldurgam.stat().st_mtime).strftime("%Y%m%d-%H%M%S")
    history_delta_path = local_root / "history" / f"{stamp}-{current['sha256'][:8]}.delta.json"
    _write_json(current, snapshot_path)
    _write_json(delta, delta_path)
    _write_json(delta, history_delta_path)

    config = {
        "schema_version": 1,
        "game_root": str(assets.game_root),
        "language": assets.language,
    }
    _write_json(config, local_root / "config.json")

    summary = delta["summary"]
    return EetAnalysisResult(
        baldurgam=baldurgam,
        snapshot_path=snapshot_path,
        delta_path=delta_path,
        history_delta_path=history_delta_path,
        initial_snapshot=bool(delta["initial_snapshot"]),
        has_changes=bool(summary["has_changes"]),
        current_area=str(delta["current_state"].get("current_area") or "Unbekannt"),
        party_members=int(delta["current_state"].get("party_count") or 0),
        changed_globals=int(summary["changed_globals"]),
        new_journal_entries=int(summary["new_journal_entries"]),
        party_changes=int(summary["party_changes"]),
        weidu_available=assets.weidu is not None,
    )


def _cmd_paths(_: argparse.Namespace) -> int:
    for path in candidate_eet_save_roots():
        print(f"[{'gefunden' if path.is_dir() else 'nicht gefunden'}] {path}")
    newest = newest_eet_save()
    print(f"\nNeuester EET-Spielstand: {newest}" if newest else "\nKein EET-Spielstand gefunden.")
    return 0


def _cmd_inspect(args: argparse.Namespace) -> int:
    result = analyse_eet_save(
        Path(args.save),
        game_path=Path(args.game_path),
        language=args.language,
        root=Path(args.root) if args.root else None,
    )
    print(f"BALDUR.GAM: {result.baldurgam}")
    print(f"Gebiet:      {result.current_area}")
    print(f"Party:       {result.party_members}")
    print(f"Globals Δ:   {result.changed_globals}")
    print(f"Journal Δ:   {result.new_journal_entries}")
    print(f"Snapshot:    {result.snapshot_path}")
    print(f"Delta:       {result.delta_path}")
    print(f"WeiDU:       {'gefunden' if result.weidu_available else 'noch nicht erkannt'}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Wächterfeder-Adapter für Baldur's Gate EET")
    sub = parser.add_subparsers(dest="command", required=True)

    paths = sub.add_parser("paths", help="übliche EET-Speicherorte prüfen")
    paths.set_defaults(func=_cmd_paths)

    inspect = sub.add_parser("inspect", help="EET-Spielstand analysieren und Delta erzeugen")
    inspect.add_argument("--save", required=True, help="Save-Ordner oder BALDUR.GAM")
    inspect.add_argument("--game-path", required=True, help="EET/BG2EE-Spielordner oder Unterordner")
    inspect.add_argument("--language", default="de_DE")
    inspect.add_argument("--root", default=None, help="Repository-Stamm für Tests")
    inspect.set_defaults(func=_cmd_inspect)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main())
