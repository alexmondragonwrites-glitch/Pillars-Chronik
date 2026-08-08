#!/usr/bin/env python3
"""Real-session EET adapter for Wächterfeder.

This layer treats BALDUR.GAM and BALDUR.SAV as one read-only save snapshot.
It enriches party members from their embedded CRE records and compares global
and area variables, journal entries and persistent NPC talk counters between
sessions. Exact dialogue choices remain a separate resolver step.
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

from tools.wachterfeder.eet import (
    EetError,
    parse_game_v20,
    resolve_baldur_gam,
    resolve_eet_game_assets,
)
from tools.wachterfeder.eet_save_resources import (
    actor_talk_delta,
    collect_sav_state,
    enrich_party_from_embedded_cre,
)

JsonObject = dict[str, Any]
_MISSING = object()


@dataclass(frozen=True)
class EetSessionResult:
    snapshot_path: Path
    delta_path: Path
    history_delta_path: Path
    initial_snapshot: bool
    has_changes: bool
    current_area: str
    party_members: int
    changed_globals: int
    changed_area_variables: int
    new_journal_entries: int
    npc_conversations: int
    party_progression_changes: int


class TlkTable:
    """Small in-memory TLK V1 reader so one session never rereads dialog.tlk."""

    def __init__(self, path: Path):
        self.path = path
        self.payload = path.read_bytes()
        if len(self.payload) < 0x12 or self.payload[:4] != b"TLK ":
            raise EetError(f"Ungültige dialog.tlk: {path}")
        self.count = struct.unpack_from("<I", self.payload, 0x0A)[0]
        self.strings_offset = struct.unpack_from("<I", self.payload, 0x0E)[0]
        self.cache: dict[int, str | None] = {}

    def get(self, strref: int) -> str | None:
        if strref in self.cache:
            return self.cache[strref]
        if strref < 0 or strref >= self.count:
            self.cache[strref] = None
            return None
        entry = 0x12 + strref * 0x1A
        if entry + 0x1A > len(self.payload):
            self.cache[strref] = None
            return None
        relative = struct.unpack_from("<I", self.payload, entry + 0x12)[0]
        length = struct.unpack_from("<I", self.payload, entry + 0x16)[0]
        start = self.strings_offset + relative
        end = start + length
        if start < 0 or end > len(self.payload):
            self.cache[strref] = None
            return None
        raw = self.payload[start:end].split(b"\x00", 1)[0]
        try:
            text = raw.decode("utf-8")
        except UnicodeDecodeError:
            text = raw.decode("cp1252", errors="replace")
        self.cache[strref] = text
        return text


def _find_sibling(path: Path, filename: str) -> Path | None:
    for candidate in path.parent.iterdir():
        if candidate.is_file() and candidate.name.casefold() == filename.casefold():
            return candidate
    return None


def _bundle_hash(gam_payload: bytes, sav_payload: bytes | None) -> str:
    digest = hashlib.sha256()
    digest.update(b"BALDUR.GAM\0")
    digest.update(gam_payload)
    if sav_payload is not None:
        digest.update(b"\0BALDUR.SAV\0")
        digest.update(sav_payload)
    return digest.hexdigest()


def _file_hash(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _normalise_reputation(raw: int) -> int | float:
    value = raw / 10
    return int(value) if value.is_integer() else value


def _resolve_journal_texts(entries: list[JsonObject], tlk: TlkTable) -> list[JsonObject]:
    resolved: list[JsonObject] = []
    for item in entries:
        entry = dict(item)
        if int(entry.get("location_flag", -1)) == 0xFF:
            entry["text"] = tlk.get(int(entry.get("strref", -1)))
        resolved.append(entry)
    return resolved


def build_session_snapshot(save_path: Path, *, game_path: Path, language: str = "de_DE") -> JsonObject:
    assets = resolve_eet_game_assets(game_path, language)
    gam_path = resolve_baldur_gam(save_path)
    sav_path = _find_sibling(gam_path, "BALDUR.SAV")
    gam_payload = gam_path.read_bytes()
    sav_payload = sav_path.read_bytes() if sav_path else None
    tlk = TlkTable(assets.dialog_tlk)

    parsed = parse_game_v20(gam_payload, None)
    parsed["journal_entries"] = _resolve_journal_texts(parsed["journal_entries"], tlk)
    party = enrich_party_from_embedded_cre(
        gam_payload,
        parsed["party"],
        resolve_strref=tlk.get,
    )
    sav_state: JsonObject = {}
    warnings = [
        "Exakte gewählte Dialogantworten werden noch nicht als sicher rekonstruiert."
    ]
    if sav_path is not None:
        sav_state = collect_sav_state(sav_path, resolve_strref=None)
        if sav_state.get("has_default_toh"):
            warnings.append(
                "DEFAULT.toh ist vorhanden; externe benutzerdefinierte Journaltexte werden noch nicht aufgelöst."
            )
    else:
        warnings.append("BALDUR.SAV wurde neben BALDUR.GAM nicht gefunden.")

    raw_reputation = int(parsed["party_reputation"])
    globals_ = parsed["global_variables"]
    stat = gam_path.stat()
    source_files: JsonObject = {
        "BALDUR.GAM": {
            "size": len(gam_payload),
            "sha256": _file_hash(gam_payload),
        }
    }
    if sav_payload is not None:
        source_files["BALDUR.SAV"] = {
            "size": len(sav_payload),
            "sha256": _file_hash(sav_payload),
        }

    return {
        "schema_version": 2,
        "kind": "wachterfeder-eet-snapshot",
        "source_name": gam_path.parent.name,
        "source_modified_utc": datetime.fromtimestamp(stat.st_mtime, tz=timezone.utc).isoformat(),
        "sha256": _bundle_hash(gam_payload, sav_payload),
        "source_files": source_files,
        "inspected_utc": datetime.now(tz=timezone.utc).isoformat(),
        "metadata": {
            "game_time": parsed["game_time"],
            "party_gold": parsed["party_gold"],
            "party_reputation": _normalise_reputation(raw_reputation),
            "party_reputation_raw": raw_reputation,
            "main_area": parsed["main_area"],
            "current_area": parsed["current_area"],
            "current_worldmap": parsed["current_worldmap"],
            "current_campaign": parsed["current_campaign"],
            "chapter": globals_.get("CHAPTER"),
            "party_count": len(party),
            "journal_count": len(parsed["journal_entries"]),
            "saved_area_count": len((sav_state or {}).get("actor_talks", {}))
            if sav_state
            else 0,
            "sav_resource_count": int((sav_state or {}).get("resource_count", 0)),
        },
        "party": party,
        "global_variable_count": len(globals_),
        "global_variables": globals_,
        "journal_entries": parsed["journal_entries"],
        "save_resources": sav_state,
        "local_assets": {
            "language": assets.language,
            "weidu_available": assets.weidu is not None,
        },
        "warnings": warnings,
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


def _mapping_changes(previous: Mapping[str, Any] | None, current: Mapping[str, Any] | None) -> JsonObject:
    return _field_changes(previous or {}, current or {})


def _party_key(item: Mapping[str, Any]) -> str:
    character = item.get("character") if isinstance(item.get("character"), Mapping) else {}
    return str(
        character.get("death_variable")
        or character.get("dialog")
        or item.get("resource")
        or item.get("name")
        or item.get("index")
    )


def _party_roster(previous: JsonObject | None, current: JsonObject) -> JsonObject:
    old = {
        _party_key(item): item
        for item in (previous or {}).get("party", [])
        if isinstance(item, Mapping)
    }
    new = {
        _party_key(item): item
        for item in current.get("party", [])
        if isinstance(item, Mapping)
    }
    return {
        "added": [new[key].get("name") or key for key in sorted(set(new) - set(old))],
        "removed": [old[key].get("name") or key for key in sorted(set(old) - set(new))],
    }


def _progression_view(item: Mapping[str, Any]) -> JsonObject:
    character = item.get("character") if isinstance(item.get("character"), Mapping) else {}
    return {
        "name": item.get("name"),
        "experience": character.get("experience"),
        "levels": character.get("levels"),
        "maximum_hit_points": (character.get("hit_points") or {}).get("maximum")
        if isinstance(character.get("hit_points"), Mapping)
        else None,
        "attributes": character.get("attributes"),
        "class_name": character.get("class_name"),
        "kit_name": character.get("kit_name"),
    }


def _party_progression(previous: JsonObject | None, current: JsonObject) -> JsonObject:
    old = {
        _party_key(item): item
        for item in (previous or {}).get("party", [])
        if isinstance(item, Mapping)
    }
    new = {
        _party_key(item): item
        for item in current.get("party", [])
        if isinstance(item, Mapping)
    }
    changes: JsonObject = {}
    for key in sorted(set(old) & set(new)):
        diff = _field_changes(_progression_view(old[key]), _progression_view(new[key]))
        if diff:
            changes[key] = {
                "name": new[key].get("name") or key,
                "changes": diff,
            }
    return changes


def _journal_identity(item: Mapping[str, Any]) -> tuple[int, int, int, int]:
    return (
        int(item.get("strref", -1)),
        int(item.get("time_seconds", -1)),
        int(item.get("chapter", -1)),
        int(item.get("section", -1)),
    )


def _new_journal(previous: JsonObject | None, current: JsonObject) -> list[JsonObject]:
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


def _area_variables(snapshot: JsonObject | None) -> Mapping[str, Any]:
    resources = (snapshot or {}).get("save_resources", {})
    if not isinstance(resources, Mapping):
        return {}
    variables = resources.get("area_variables", {})
    return variables if isinstance(variables, Mapping) else {}


def build_session_delta(previous: JsonObject | None, current: JsonObject) -> JsonObject:
    initial = previous is None
    metadata = _field_changes((previous or {}).get("metadata"), current.get("metadata"))
    globals_delta = _mapping_changes(
        (previous or {}).get("global_variables", {}),
        current.get("global_variables", {}),
    )
    area_delta = _field_changes(_area_variables(previous), _area_variables(current))
    roster = _party_roster(previous, current)
    progression = _party_progression(previous, current)
    journal = _new_journal(previous, current)
    talks = [] if initial else actor_talk_delta(
        (previous or {}).get("save_resources", {}),
        current.get("save_resources", {}),
    )
    roster_count = len(roster["added"]) + len(roster["removed"])
    has_changes = bool(
        initial
        or metadata
        or globals_delta
        or area_delta
        or roster_count
        or progression
        or journal
        or talks
    )
    state = current.get("metadata", {})
    return {
        "schema_version": 2,
        "kind": "wachterfeder-eet-delta",
        "created_utc": datetime.now(tz=timezone.utc).isoformat(),
        "initial_snapshot": initial,
        "previous_save_sha256": (previous or {}).get("sha256"),
        "current_save_sha256": current.get("sha256"),
        "summary": {
            "has_changes": has_changes,
            "metadata_changes": len(metadata),
            "changed_globals": len(globals_delta),
            "changed_area_variables": len(area_delta),
            "party_roster_changes": roster_count,
            "party_progression_changes": len(progression),
            "new_journal_entries": len(journal),
            "npc_conversations": len(talks),
        },
        "current_state": {
            "current_area": state.get("current_area"),
            "current_campaign": state.get("current_campaign"),
            "chapter": state.get("chapter"),
            "party_gold": state.get("party_gold"),
            "party_reputation": state.get("party_reputation"),
            "party_count": state.get("party_count"),
        },
        "changes": {
            "metadata": metadata,
            "global_variables": globals_delta,
            "area_variables": area_delta,
            "party_roster": roster,
            "party_progression": progression,
            "new_journal_entries": journal,
            "npc_conversations": talks,
        },
        "notes": [
            "NPC-Gespräche bedeuten: der persistente NumTimesTalkedTo-Zähler dieses Actors ist seit dem vorherigen Save gestiegen.",
            "Das belegt eine neue Interaktion, aber noch nicht automatisch die exakt gewählte Dialogantwort.",
        ],
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


def candidate_save_roots(home: Path | None = None) -> list[Path]:
    home = home or Path.home()
    document_roots = [home / "Documents"]
    onedrive = os.environ.get("OneDrive")
    if onedrive:
        document_roots.append(Path(onedrive) / "Documents")
    game_folders = (
        "Baldur's Gate - Enhanced Edition Trilogy",
        "Baldur's Gate II - Enhanced Edition",
    )
    result: list[Path] = []
    seen: set[str] = set()
    for documents in document_roots:
        for game in game_folders:
            for kind in ("save", "mpsave"):
                path = documents / game / kind
                key = str(path).casefold()
                if key not in seen:
                    seen.add(key)
                    result.append(path)
    return result


def newest_save() -> Path | None:
    candidates: list[Path] = []
    for root in candidate_save_roots():
        if not root.is_dir():
            continue
        for gam in root.rglob("BALDUR.GAM"):
            if gam.is_file():
                candidates.append(gam)
    latest = max(candidates, key=lambda path: path.stat().st_mtime, default=None)
    return latest.parent if latest else None


def _config_path(root: Path) -> Path:
    return root / ".wachterfeder" / "eet" / "config.json"


def configure(game_path: Path, *, root: Path, language: str) -> JsonObject:
    assets = resolve_eet_game_assets(game_path, language)
    config = {
        "schema_version": 2,
        "game_root": str(assets.game_root),
        "language": assets.language,
    }
    _write_json(config, _config_path(root))
    return config


def analyse_session(
    *,
    save_path: Path | None,
    game_path: Path | None,
    language: str = "de_DE",
    root: Path | None = None,
) -> EetSessionResult:
    root = (root or Path(__file__).resolve().parents[2]).expanduser().resolve()
    local_root = root / ".wachterfeder" / "eet"
    config = _read_json(_config_path(root)) or {}
    resolved_game = game_path or (Path(str(config["game_root"])) if config.get("game_root") else None)
    if resolved_game is None:
        raise EetError("EET-Spielpfad fehlt. Zuerst 'configure' ausführen oder --game-path angeben.")
    resolved_save = save_path or newest_save()
    if resolved_save is None:
        raise EetError("Kein EET-Spielstand gefunden. --save kann einen Saveordner explizit angeben.")

    current = build_session_snapshot(resolved_save, game_path=resolved_game, language=language)
    snapshot_path = local_root / "eet.snapshot.json"
    delta_path = local_root / "eet.delta.json"
    previous = _read_json(snapshot_path)
    delta = build_session_delta(previous, current)
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    history_delta_path = local_root / "history" / f"{stamp}-{current['sha256'][:8]}.delta.json"
    _write_json(current, snapshot_path)
    _write_json(delta, delta_path)
    _write_json(delta, history_delta_path)
    configure(resolved_game, root=root, language=language)

    summary = delta["summary"]
    state = delta["current_state"]
    return EetSessionResult(
        snapshot_path=snapshot_path,
        delta_path=delta_path,
        history_delta_path=history_delta_path,
        initial_snapshot=bool(delta["initial_snapshot"]),
        has_changes=bool(summary["has_changes"]),
        current_area=str(state.get("current_area") or "Unbekannt"),
        party_members=int(state.get("party_count") or 0),
        changed_globals=int(summary["changed_globals"]),
        changed_area_variables=int(summary["changed_area_variables"]),
        new_journal_entries=int(summary["new_journal_entries"]),
        npc_conversations=int(summary["npc_conversations"]),
        party_progression_changes=int(summary["party_progression_changes"]),
    )


def _cmd_configure(args: argparse.Namespace) -> int:
    root = Path(args.root).resolve() if args.root else Path(__file__).resolve().parents[2]
    config = configure(Path(args.game_path), root=root, language=args.language)
    print(f"EET-Spielordner gespeichert: {config['game_root']}")
    print(f"Sprache: {config['language']}")
    return 0


def _cmd_paths(_: argparse.Namespace) -> int:
    for path in candidate_save_roots():
        print(f"[{'gefunden' if path.is_dir() else 'nicht gefunden'}] {path}")
    latest = newest_save()
    print(f"\nNeuester EET-Spielstand: {latest}" if latest else "\nKein EET-Spielstand gefunden.")
    return 0


def _cmd_inspect(args: argparse.Namespace) -> int:
    result = analyse_session(
        save_path=Path(args.save) if args.save else None,
        game_path=Path(args.game_path) if args.game_path else None,
        language=args.language,
        root=Path(args.root) if args.root else None,
    )
    print(f"Gebiet:        {result.current_area}")
    print(f"Party:         {result.party_members}")
    print(f"Globals Δ:     {result.changed_globals}")
    print(f"Gebietsvars Δ: {result.changed_area_variables}")
    print(f"Journal Δ:     {result.new_journal_entries}")
    print(f"NPC-Gespräche: {result.npc_conversations}")
    print(f"Fortschritt Δ: {result.party_progression_changes}")
    print(f"Snapshot:      {result.snapshot_path}")
    print(f"Delta:         {result.delta_path}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Wächterfeder für Baldur's Gate EET Sessions")
    sub = parser.add_subparsers(dest="command", required=True)

    paths = sub.add_parser("paths", help="EET-Saveordner suchen")
    paths.set_defaults(func=_cmd_paths)

    configure_parser = sub.add_parser("configure", help="lokalen EET-Spielordner speichern")
    configure_parser.add_argument("game_path")
    configure_parser.add_argument("--language", default="de_DE")
    configure_parser.add_argument("--root", default=None)
    configure_parser.set_defaults(func=_cmd_configure)

    inspect = sub.add_parser("inspect", help="neuesten oder angegebenen EET-Save auswerten")
    inspect.add_argument("--save", default=None)
    inspect.add_argument("--game-path", default=None)
    inspect.add_argument("--language", default="de_DE")
    inspect.add_argument("--root", default=None)
    inspect.set_defaults(func=_cmd_inspect)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        return int(args.func(args))
    except EetError as exc:
        print(f"Wächterfeder EET: {exc}")
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
