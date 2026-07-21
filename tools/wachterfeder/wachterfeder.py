#!/usr/bin/env python3
"""Read-only inspection helpers for Pillars of Eternity savegames.

The MVP deliberately does not deserialize MobileObjects.save yet. It discovers
common save locations, creates immutable working copies, calculates hashes and
writes a machine-readable inventory of the save archive.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import sys
import zipfile
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable, Sequence

SAVE_SUFFIXES = (".savegame", ".zip")
IMPORTANT_MEMBERS = {
    "MobileObjects.save",
    "WorldMap.save",
    "Global.save",
    "Screenshot.png",
    "SaveGameInfo",
}


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
class SaveSnapshot:
    schema_version: int
    source_name: str
    source_size: int
    source_modified_utc: str
    sha256: str
    inspected_utc: str
    archive_format: str
    archive_members: list[ArchiveMember]
    warnings: list[str]


def candidate_save_directories(home: Path | None = None) -> list[Path]:
    """Return likely save directories without requiring them to exist."""
    home = home or Path.home()
    candidates = [home / "Saved Games" / "Pillars of Eternity"]

    # Some Windows setups redirect known folders into OneDrive.
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
    """Yield savegame-like files, including Game Pass numeric subfolders."""
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
    """Copy a save into a hash-addressed workspace and make the copy read-only."""
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


def inspect_savegame(path: Path) -> SaveSnapshot:
    path = path.expanduser().resolve()
    if not path.is_file():
        raise WachterfederError(f"Speicherstand nicht gefunden: {path}")

    stat = path.stat()
    warnings: list[str] = []
    members: list[ArchiveMember] = []
    archive_format = "unknown"

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
    except zipfile.BadZipFile:
        warnings.append(
            "Das Format konnte mit Pythons ZIP-Leser nicht geöffnet werden. "
            "Die Originaldatei wurde nicht verändert; für diesen Build wird "
            "voraussichtlich ein 7-Zip/LZMA-Adapter benötigt."
        )

    member_names = {Path(member.name).name for member in members}
    if members and "MobileObjects.save" not in member_names:
        warnings.append("MobileObjects.save wurde im Archiv nicht gefunden.")

    return SaveSnapshot(
        schema_version=1,
        source_name=path.name,
        source_size=stat.st_size,
        source_modified_utc=datetime.fromtimestamp(
            stat.st_mtime, tz=timezone.utc
        ).isoformat(),
        sha256=sha256_file(path),
        inspected_utc=datetime.now(tz=timezone.utc).isoformat(),
        archive_format=archive_format,
        archive_members=members,
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
    if newest:
        print(f"\nNeuester Speicherstand: {newest}")
    else:
        print("\nKein .savegame in den bekannten Ordnern gefunden.")
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
    snapshot_parser.add_argument(
        "--output", help="optionaler Zielpfad für das JSON-Inventar"
    )
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
