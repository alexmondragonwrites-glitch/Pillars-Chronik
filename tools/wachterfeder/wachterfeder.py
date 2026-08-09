#!/usr/bin/env python3
"""Read-only inspection helpers for Pillars of Eternity savegames.

The tool never writes to the original save. It inventories the archive, parses
saveinfo.xml, extracts a conservative subset of player stats and global values
from MobileObjects.save, and reconstructs the ConversationManager's
MarkedAsRead bit arrays.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import sys
import zipfile
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable, Sequence
from xml.etree import ElementTree

SAVE_SUFFIXES = (".savegame", ".zip")
IMPORTANT_MEMBERS = {
    "MobileObjects.save",
    "WorldMap.save",
    "Global.save",
    "screenshot.png",
    "saveinfo.xml",
}

PROPERTY_PREFIX = b"\x06\x01\x11\x01\x01\x01"
VALUE_PREFIX = b"\x06\x01\x11\x01"
GLOBAL_ENTRY_PATTERN = re.compile(
    rb"\x06\x01\x11\x01\x03\x01(.)(.{1,255}?)"
    rb"\x06\x01\x11\x01\x06\x01(.{4})",
    re.S,
)
CONVERSATION_PATH_PATTERN = re.compile(
    rb"data/conversations/[A-Za-z0-9_./-]+\.conversation"
)


class WachterfederError(RuntimeError):
    """Expected user-facing error."""


@dataclass(frozen=True)
class ArchiveMember:
    name: str
    size: int
    compressed_size: int
    crc32: str
    important: bool


@dataclass(frozen=True)
class SaveMetadata:
    player_name: str | None
    map_name: str | None
    scene_title: str | None
    chapter: int | None
    realtime_play_duration_seconds: int | None
    playtime_seconds: int | None
    trial_of_iron: bool | None
    real_timestamp: str | None
    session_id: str | None
    save_version: int | None
    difficulty: str | None
    active_packages: str | None
    tactical_mode: str | None


@dataclass(frozen=True)
class PlayerSnapshot:
    name: str
    level: int | None
    experience: int | None
    base_attributes: dict[str, int]
    persisted_skills: dict[str, int]
    serialized_talents: list[str]
    enum_codes: dict[str, int]


@dataclass(frozen=True)
class ConversationReadState:
    path: str
    node_capacity: int
    marked_node_ids: list[int]
    version: int


@dataclass(frozen=True)
class SaveSnapshot:
    schema_version: int
    source_name: str
    source_size: int
    source_modified_utc: str
    sha256: str
    inspected_utc: str
    archive_format: str
    archive_members: list[ArchiveMember]
    metadata: SaveMetadata | None
    player: PlayerSnapshot | None
    global_variable_count: int
    global_variables: dict[str, int]
    marked_conversations: list[ConversationReadState]
    warnings: list[str]


def candidate_save_directories(home: Path | None = None) -> list[Path]:
    home = home or Path.home()
    candidates = [home / "Saved Games" / "Pillars of Eternity"]
    onedrive = os.environ.get("OneDrive")
    if onedrive:
        candidates.append(Path(onedrive) / "Saved Games" / "Pillars of Eternity")
    unique: list[Path] = []
    seen: set[str] = set()
    for path in candidates:
        key = str(path).casefold()
        if key not in seen:
            seen.add(key)
            unique.append(path)
    return unique


def iter_savegames(directory: Path) -> Iterable[Path]:
    if not directory.is_dir():
        return
    for path in directory.rglob("*"):
        if path.is_file() and path.suffix.casefold() in SAVE_SUFFIXES:
            yield path


def newest_savegame(directories: Sequence[Path]) -> Path | None:
    saves = [path for directory in directories for path in iter_savegames(directory)]
    return max(saves, key=lambda path: path.stat().st_mtime, default=None)


def sha256_file(path: Path, chunk_size: int = 1024 * 1024) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(chunk_size):
            digest.update(chunk)
    return digest.hexdigest()


def copy_read_only(source: Path, workspace: Path) -> Path:
    source = source.expanduser().resolve()
    if not source.is_file():
        raise WachterfederError(f"Speicherstand nicht gefunden: {source}")
    digest = sha256_file(source)
    target_dir = workspace.expanduser().resolve() / digest[:12]
    target_dir.mkdir(parents=True, exist_ok=True)
    target = target_dir / source.name
    if not target.exists():
        shutil.copy2(source, target)
        target.chmod(0o444)
    return target


def _optional_int(value: str | None) -> int | None:
    return int(value) if value not in (None, "") else None


def _optional_bool(value: str | None) -> bool | None:
    if value is None:
        return None
    lowered = value.casefold()
    if lowered == "true":
        return True
    if lowered == "false":
        return False
    return None


def parse_saveinfo_xml(payload: bytes) -> SaveMetadata:
    root = ElementTree.fromstring(payload.decode("utf-8-sig"))
    values = {
        element.attrib.get("name"): element.attrib.get("value")
        for element in root.findall(".//Simple")
    }
    return SaveMetadata(
        player_name=values.get("PlayerName"),
        map_name=values.get("MapName"),
        scene_title=values.get("SceneTitle"),
        chapter=_optional_int(values.get("Chapter")),
        realtime_play_duration_seconds=_optional_int(
            values.get("RealtimePlayDurationSeconds")
        ),
        playtime_seconds=_optional_int(values.get("PlaytimeSeconds")),
        trial_of_iron=_optional_bool(values.get("TrialOfIron")),
        real_timestamp=values.get("RealTimestamp"),
        session_id=values.get("SessionID"),
        save_version=_optional_int(values.get("SaveVersion")),
        difficulty=values.get("Difficulty"),
        active_packages=values.get("ActivePackages"),
        tactical_mode=values.get("TacticalMode"),
    )


def _read_named_int(data: bytes, start: int, end: int, name: str) -> int | None:
    encoded = name.encode("utf-8")
    if len(encoded) > 127:
        return None
    marker = PROPERTY_PREFIX + bytes([len(encoded)]) + encoded + VALUE_PREFIX
    position = data.find(marker, start, end)
    if position < 0:
        return None
    value_start = position + len(marker)
    if value_start + 6 > end or data[value_start + 1] != 0x01:
        return None
    return int.from_bytes(data[value_start + 2 : value_start + 6], "little", signed=True)


def _extract_ascii_tokens(data: bytes, start: int, end: int, prefix: str) -> list[str]:
    pattern = re.compile(rb"[A-Za-z0-9_./+-]{4,180}")
    seen: set[str] = set()
    result: list[str] = []
    for match in pattern.finditer(data, start, end):
        token = match.group().decode("ascii", errors="ignore")
        if token.startswith(prefix) and token not in seen:
            seen.add(token)
            result.append(token)
    return result


def parse_player_snapshot(data: bytes, player_name: str | None) -> PlayerSnapshot | None:
    if not player_name:
        return None
    name_position = data.find(player_name.encode("utf-8"))
    if name_position < 0:
        return None
    component_start = data.rfind(b"CharacterStats", 0, name_position)
    component_end = data.find(b"PlayerInventory", name_position)
    if component_start < 0 or component_end < 0:
        return None

    attribute_names = [
        "BaseMight",
        "BaseConstitution",
        "BaseDexterity",
        "BasePerception",
        "BaseIntellect",
        "BaseResolve",
    ]
    skill_names = [
        "AthleticsSkill",
        "LoreSkill",
        "MechanicsSkill",
        "SurvivalSkill",
        "StealthSkill",
    ]
    enum_names = [
        "Gender",
        "CharacterRace",
        "CharacterSubrace",
        "CharacterCulture",
        "CharacterClass",
        "CharacterBackground",
    ]

    attributes = {
        name: value
        for name in attribute_names
        if (value := _read_named_int(data, component_start, component_end, name))
        is not None
    }
    skills = {
        name: value
        for name in skill_names
        if (value := _read_named_int(data, component_start, component_end, name))
        is not None
    }
    enum_codes = {
        name: value
        for name in enum_names
        if (value := _read_named_int(data, component_start, component_end, name))
        is not None
    }
    talents = _extract_ascii_tokens(data, component_start, component_end, "TLN_")
    return PlayerSnapshot(
        name=player_name,
        level=_read_named_int(data, component_start, component_end, "Level"),
        experience=_read_named_int(data, component_start, component_end, "Experience"),
        base_attributes=attributes,
        persisted_skills=skills,
        serialized_talents=talents,
        enum_codes=enum_codes,
    )


def parse_global_variables(data: bytes) -> dict[str, int]:
    variables: dict[str, int] = {}
    for match in GLOBAL_ENTRY_PATTERN.finditer(data):
        declared_length = match.group(1)[0]
        raw_name = match.group(2)
        if len(raw_name) != declared_length:
            continue
        try:
            name = raw_name.decode("utf-8")
        except UnicodeDecodeError:
            continue
        if not re.fullmatch(r"[A-Za-z0-9_()\-]+", name):
            continue
        if not (
            name.startswith(("b_", "n_", "s_", "f_"))
            or re.fullmatch(r"[bn][A-Z][A-Za-z0-9_]+", name)
            or re.fullmatch(r"\d{4}_Found", name)
        ):
            continue
        variables[name] = int.from_bytes(match.group(3), "little", signed=True)
    return dict(sorted(variables.items()))


def _extract_conversation_pairs(
    data: bytes, start: int, end: int
) -> list[tuple[str, int]]:
    pairs: list[tuple[str, int]] = []
    region = data[start:end]
    for match in CONVERSATION_PATH_PATTERN.finditer(region):
        absolute_start = start + match.start()
        absolute_end = start + match.end()
        path = match.group().decode("ascii")
        prefix = data[absolute_start - 6 : absolute_start]
        suffix = data[absolute_end : absolute_end + 5]
        if (
            len(prefix) == 6
            and prefix[0] == 0x06
            and prefix[5] == len(path)
            and len(suffix) == 5
            and suffix[0] == 0x09
        ):
            value_object_id = int.from_bytes(suffix[1:5], "little", signed=True)
            pairs.append((path, value_object_id))
    return pairs


def parse_marked_conversations(data: bytes) -> list[ConversationReadState]:
    start = data.find(b"ConversationManager")
    end = data.find(b"NodeCyclePositions", start)
    if start < 0 or end < 0:
        return []

    pairs = _extract_conversation_pairs(data, start, end)
    if not pairs:
        return []
    referenced_ids = {value_id for _, value_id in pairs}
    metadata_id = pairs[0][1]

    bit_arrays: dict[int, tuple[int, int, int]] = {}
    class_name = data.find(b"System.Collections.BitArray", start, end)
    member_name = data.find(b"m_array", class_name, end)
    class_start = data.rfind(
        b"\x04" + metadata_id.to_bytes(4, "little", signed=True), start, member_name
    )
    version_name = data.find(b"_version", class_start, end)
    first_reference = data.find(b"\x09", version_name, end)
    if min(class_start, version_name, first_reference) < 0:
        return []

    first_array_id = int.from_bytes(
        data[first_reference + 1 : first_reference + 5], "little", signed=True
    )
    first_length = int.from_bytes(
        data[first_reference + 5 : first_reference + 9], "little", signed=True
    )
    first_version = int.from_bytes(
        data[first_reference + 9 : first_reference + 13], "little", signed=True
    )
    bit_arrays[metadata_id] = (first_array_id, first_length, first_version)

    class_pattern = re.compile(
        rb"\x01(.{4})"
        + re.escape(metadata_id.to_bytes(4, "little", signed=True))
        + rb"\x09(.{4})(.{4})(.{4})",
        re.S,
    )
    for match in class_pattern.finditer(data, first_reference + 13, end):
        object_id = int.from_bytes(match.group(1), "little", signed=True)
        if object_id not in referenced_ids:
            continue
        bit_arrays[object_id] = (
            int.from_bytes(match.group(2), "little", signed=True),
            int.from_bytes(match.group(3), "little", signed=True),
            int.from_bytes(match.group(4), "little", signed=True),
        )

    primitive_arrays: dict[int, list[int]] = {}
    position = first_reference
    while True:
        record = data.find(b"\x0f", position, end)
        if record < 0:
            break
        if record + 10 <= end:
            object_id = int.from_bytes(data[record + 1 : record + 5], "little", signed=True)
            count = int.from_bytes(data[record + 5 : record + 9], "little", signed=True)
            primitive_type = data[record + 9]
            payload_end = record + 10 + count * 4
            if 0 <= count < 10000 and primitive_type == 0x08 and payload_end <= end:
                primitive_arrays[object_id] = [
                    int.from_bytes(
                        data[record + 10 + index * 4 : record + 14 + index * 4],
                        "little",
                        signed=False,
                    )
                    for index in range(count)
                ]
                position = payload_end
                continue
        position = record + 1

    conversations: list[ConversationReadState] = []
    for path, value_object_id in pairs:
        bit_meta = bit_arrays.get(value_object_id)
        if not bit_meta:
            continue
        array_object_id, capacity, version = bit_meta
        integers = primitive_arrays.get(array_object_id)
        if integers is None or capacity < 0:
            continue
        marked_nodes = [
            node_id
            for node_id in range(capacity)
            if node_id // 32 < len(integers)
            and integers[node_id // 32] & (1 << (node_id % 32))
        ]
        conversations.append(
            ConversationReadState(
                path=path,
                node_capacity=capacity,
                marked_node_ids=marked_nodes,
                version=version,
            )
        )
    return conversations


def inspect_savegame(path: Path) -> SaveSnapshot:
    path = path.expanduser().resolve()
    if not path.is_file():
        raise WachterfederError(f"Speicherstand nicht gefunden: {path}")

    stat = path.stat()
    warnings: list[str] = []
    members: list[ArchiveMember] = []
    archive_format = "unknown"
    metadata: SaveMetadata | None = None
    player: PlayerSnapshot | None = None
    global_variables: dict[str, int] = {}
    marked_conversations: list[ConversationReadState] = []

    try:
        with zipfile.ZipFile(path, "r") as archive:
            archive_format = "zip"
            bad_member = archive.testzip()
            if bad_member:
                warnings.append(f"CRC-Prüfung fehlgeschlagen: {bad_member}")
            for item in archive.infolist():
                normalized_name = Path(item.filename).name
                members.append(
                    ArchiveMember(
                        name=item.filename,
                        size=item.file_size,
                        compressed_size=item.compress_size,
                        crc32=f"{item.CRC:08x}",
                        important=normalized_name in IMPORTANT_MEMBERS,
                    )
                )

            names = {Path(item.filename).name: item.filename for item in archive.infolist()}
            if "saveinfo.xml" in names:
                try:
                    metadata = parse_saveinfo_xml(archive.read(names["saveinfo.xml"]))
                except (ElementTree.ParseError, UnicodeDecodeError, ValueError) as exc:
                    warnings.append(f"saveinfo.xml konnte nicht gelesen werden: {exc}")
            else:
                warnings.append("saveinfo.xml wurde im Archiv nicht gefunden.")

            if "MobileObjects.save" in names:
                mobile_objects = archive.read(names["MobileObjects.save"])
                player = parse_player_snapshot(
                    mobile_objects, metadata.player_name if metadata else None
                )
                global_variables = parse_global_variables(mobile_objects)
                marked_conversations = parse_marked_conversations(mobile_objects)
                if player is None:
                    warnings.append("Spielerprofil konnte nicht konservativ extrahiert werden.")
                if not marked_conversations:
                    warnings.append("Keine MarkedAsRead-Dialogzustände erkannt.")
            else:
                warnings.append("MobileObjects.save wurde im Archiv nicht gefunden.")
    except zipfile.BadZipFile:
        warnings.append(
            "Das Format konnte mit Pythons ZIP-Leser nicht geöffnet werden. "
            "Die Originaldatei wurde nicht verändert."
        )

    return SaveSnapshot(
        schema_version=2,
        source_name=path.name,
        source_size=stat.st_size,
        source_modified_utc=datetime.fromtimestamp(
            stat.st_mtime, tz=timezone.utc
        ).isoformat(),
        sha256=sha256_file(path),
        inspected_utc=datetime.now(tz=timezone.utc).isoformat(),
        archive_format=archive_format,
        archive_members=members,
        metadata=metadata,
        player=player,
        global_variable_count=len(global_variables),
        global_variables=global_variables,
        marked_conversations=marked_conversations,
        warnings=warnings,
    )


def write_snapshot(snapshot: SaveSnapshot, output: Path) -> None:
    output = output.expanduser().resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        json.dumps(asdict(snapshot), ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def cmd_paths(_: argparse.Namespace) -> int:
    directories = candidate_save_directories()
    for directory in directories:
        status = "gefunden" if directory.is_dir() else "nicht gefunden"
        print(f"[{status}] {directory}")
    newest = newest_savegame(directories)
    print(f"\nNeuester Speicherstand: {newest}" if newest else "\nKein Save gefunden.")
    return 0


def cmd_snapshot(args: argparse.Namespace) -> int:
    source = Path(args.savegame)
    working_copy = copy_read_only(source, Path(args.workspace))
    snapshot = inspect_savegame(working_copy)
    output = Path(args.output) if args.output else working_copy.with_suffix(
        working_copy.suffix + ".snapshot.json"
    )
    write_snapshot(snapshot, output)
    print(f"Arbeitskopie: {working_copy}")
    print(f"Snapshot:     {output.resolve()}")
    print(f"SHA-256:      {snapshot.sha256}")
    print(f"Archivformat: {snapshot.archive_format}")
    print(f"Dateien:      {len(snapshot.archive_members)}")
    if snapshot.metadata:
        print(
            f"Spielstand:    {snapshot.metadata.player_name} · "
            f"{snapshot.metadata.scene_title} · {snapshot.metadata.difficulty}"
        )
    if snapshot.player:
        print(
            f"Charakter:     Level {snapshot.player.level} · "
            f"XP {snapshot.player.experience}"
        )
    print(f"Globale Werte:{snapshot.global_variable_count:>7}")
    print(f"Dialogdateien:{len(snapshot.marked_conversations):>7}")
    print(
        "Markierte Nodes:"
        f"{sum(len(item.marked_node_ids) for item in snapshot.marked_conversations):>6}"
    )
    for warning in snapshot.warnings:
        print(f"Warnung:      {warning}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="wachterfeder",
        description="Read-only Werkzeug für Pillars-of-Eternity-Spielstände",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)
    paths_parser = subparsers.add_parser(
        "paths", help="bekannte Windows-Speicherordner anzeigen"
    )
    paths_parser.set_defaults(func=cmd_paths)
    snapshot_parser = subparsers.add_parser(
        "snapshot", help="Arbeitskopie und JSON-Inventar erzeugen"
    )
    snapshot_parser.add_argument("savegame", help="Pfad zur .savegame-Datei")
    snapshot_parser.add_argument(
        "--workspace",
        default=".wachterfeder/cache",
        help="lokaler Arbeitsordner (Standard: .wachterfeder/cache)",
    )
    snapshot_parser.add_argument("--output", help="optionaler Zielpfad")
    snapshot_parser.set_defaults(func=cmd_snapshot)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        return int(args.func(args))
    except (OSError, WachterfederError) as exc:
        print(f"Fehler: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
