#!/usr/bin/env python3
"""Warhammer 40,000: Rogue Trader adapter for Wächterfeder.

The adapter is deliberately conservative and read-only. Rogue Trader save files
use the ``.zks`` extension and are treated as archives. Until a real user save
has been mapped, the adapter does not pretend to know Owlcat's full internal
schema. Instead it validates the archive, fingerprints its members, probes JSON
shapes, and extracts a bounded set of chronology-relevant scalar signals.

This gives us useful deltas immediately while keeping the module resilient to
patches and DLC changes. Once a real save is available, stable field mappings
can be layered on top without replacing the archive/delta machinery.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import zipfile
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

JsonObject = dict[str, Any]
_MISSING = object()
MAX_JSON_MEMBER_BYTES = 64 * 1024 * 1024
MAX_TOP_LEVEL_KEYS = 200
MAX_INTERESTING_PATHS_PER_DOCUMENT = 300
MAX_SIGNALS = 1500
MAX_SIGNAL_STRING = 512
MAX_JSON_WALK_NODES = 50_000

INTERESTING_TERMS = (
    "quest",
    "objective",
    "etude",
    "conviction",
    "dogmatic",
    "iconoclast",
    "heretic",
    "reputation",
    "faction",
    "companion",
    "party",
    "dialog",
    "answer",
    "choice",
    "romance",
    "relationship",
    "area",
    "location",
    "chapter",
    "career",
    "archetype",
    "level",
    "experience",
    "profitfactor",
    "profit_factor",
    "ship",
    "colony",
)


class RogueTraderError(RuntimeError):
    """Expected, user-facing Rogue Trader adapter error."""


@dataclass(frozen=True)
class RogueTraderAnalysisResult:
    save_file: Path
    snapshot_path: Path
    delta_path: Path
    history_delta_path: Path
    initial_snapshot: bool
    has_changes: bool
    archive_members: int
    json_documents: int
    changed_members: int
    changed_signals: int


def sha256_file(path: Path, chunk_size: int = 1024 * 1024) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(chunk_size):
            digest.update(chunk)
    return digest.hexdigest()


def candidate_rogue_trader_save_roots(home: Path | None = None) -> list[Path]:
    """Return common Rogue Trader save roots on Windows.

    Owlcat's Windows data lives below ``AppData/LocalLow/Owlcat Games``. The
    released game has used the long product folder name; the shorter ``WH 40000
    RT`` name is also probed because Owlcat's modification tooling uses it.
    """
    home = home or Path.home()
    appdata = home / "AppData" / "LocalLow" / "Owlcat Games"
    env_profile = os.environ.get("USERPROFILE")
    bases = [appdata]
    if env_profile:
        profile_base = Path(env_profile) / "AppData" / "LocalLow" / "Owlcat Games"
        if profile_base != appdata:
            bases.append(profile_base)

    names = ("Warhammer 40000 Rogue Trader", "WH 40000 RT")
    candidates = [base / name / "Saved Games" for base in bases for name in names]

    unique: list[Path] = []
    seen: set[str] = set()
    for path in candidates:
        key = str(path).casefold()
        if key not in seen:
            seen.add(key)
            unique.append(path)
    return unique


def newest_rogue_trader_save(save_roots: Sequence[Path] | None = None) -> Path | None:
    roots = list(save_roots or candidate_rogue_trader_save_roots())
    saves: list[Path] = []
    for root in roots:
        if not root.is_dir():
            continue
        saves.extend(path for path in root.rglob("*.zks") if path.is_file())
    return max(saves, key=lambda path: path.stat().st_mtime, default=None)


def resolve_rogue_trader_save(path: Path) -> Path:
    path = path.expanduser().resolve()
    if path.is_file() and path.suffix.casefold() == ".zks":
        return path
    if path.is_dir():
        matches = [item for item in path.rglob("*.zks") if item.is_file()]
        if matches:
            return max(matches, key=lambda item: item.stat().st_mtime)
    raise RogueTraderError(f"Kein Rogue-Trader-.zks-Spielstand gefunden: {path}")


def _safe_json_load(raw: bytes, member_name: str) -> Any:
    try:
        text = raw.decode("utf-8-sig")
        return json.loads(text)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise RogueTraderError(f"JSON in {member_name} konnte nicht gelesen werden: {exc}") from exc


def _json_type(value: Any) -> str:
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "boolean"
    if isinstance(value, int) and not isinstance(value, bool):
        return "integer"
    if isinstance(value, float):
        return "number"
    if isinstance(value, str):
        return "string"
    if isinstance(value, list):
        return "array"
    if isinstance(value, Mapping):
        return "object"
    return type(value).__name__


def _path_matches(path: str) -> bool:
    folded = path.casefold()
    return any(term in folded for term in INTERESTING_TERMS)


def _normalise_scalar(value: Any) -> Any:
    if isinstance(value, str):
        return value if len(value) <= MAX_SIGNAL_STRING else value[:MAX_SIGNAL_STRING] + "…"
    if value is None or isinstance(value, (bool, int, float)):
        return value
    return None


def _walk_json(
    value: Any,
    prefix: str = "",
    depth: int = 0,
    _budget: list[int] | None = None,
) -> Iterable[tuple[str, Any]]:
    """Yield bounded-path JSON nodes without recursively exploding huge saves."""
    if _budget is None:
        _budget = [MAX_JSON_WALK_NODES]
    if depth > 12 or _budget[0] <= 0:
        return
    if isinstance(value, Mapping):
        for key in sorted(value, key=lambda item: str(item)):
            if _budget[0] <= 0:
                return
            child = value[key]
            path = f"{prefix}.{key}" if prefix else str(key)
            _budget[0] -= 1
            yield path, child
            yield from _walk_json(child, path, depth + 1, _budget)
    elif isinstance(value, list):
        # Schema probing only needs a representative prefix. Scalar changes in
        # long arrays are usually noisy and are better handled by stable field
        # mappings once we have a real save.
        for index, child in enumerate(value[:25]):
            if _budget[0] <= 0:
                return
            path = f"{prefix}[{index}]"
            _budget[0] -= 1
            yield path, child
            yield from _walk_json(child, path, depth + 1, _budget)


def _describe_document(member_name: str, value: Any, size: int) -> JsonObject:
    top_level_keys: list[str] = []
    if isinstance(value, Mapping):
        top_level_keys = [str(key) for key in list(value.keys())[:MAX_TOP_LEVEL_KEYS]]

    interesting_paths: list[JsonObject] = []
    for path, node in _walk_json(value):
        if not _path_matches(path):
            continue
        interesting_paths.append({"path": path, "type": _json_type(node)})
        if len(interesting_paths) >= MAX_INTERESTING_PATHS_PER_DOCUMENT:
            break

    return {
        "member": member_name,
        "size": size,
        "root_type": _json_type(value),
        "top_level_keys": top_level_keys,
        "interesting_paths": interesting_paths,
        "interesting_paths_truncated": len(interesting_paths) >= MAX_INTERESTING_PATHS_PER_DOCUMENT,
    }


def _collect_signals(documents: Mapping[str, Any]) -> JsonObject:
    signals: JsonObject = {}
    for member_name in sorted(documents):
        value = documents[member_name]
        for path, node in _walk_json(value):
            if len(signals) >= MAX_SIGNALS:
                return signals
            if not _path_matches(path):
                continue
            scalar = _normalise_scalar(node)
            if scalar is None and node is not None:
                continue
            signals[f"{member_name}::{path}"] = {
                "type": _json_type(node),
                "value": scalar,
            }
    return signals


def _archive_snapshot(save_file: Path) -> tuple[list[JsonObject], list[JsonObject], JsonObject]:
    try:
        archive = zipfile.ZipFile(save_file, "r")
    except (OSError, zipfile.BadZipFile) as exc:
        raise RogueTraderError(f"Ungültiger oder nicht lesbarer .zks-Spielstand: {save_file}") from exc

    with archive:
        bad_member = archive.testzip()
        if bad_member:
            raise RogueTraderError(f"CRC-Prüfung fehlgeschlagen: {bad_member}")

        members: list[JsonObject] = []
        documents: dict[str, Any] = {}
        descriptions: list[JsonObject] = []
        for info in sorted(archive.infolist(), key=lambda item: item.filename.casefold()):
            if info.is_dir():
                continue
            members.append(
                {
                    "name": info.filename,
                    "size": info.file_size,
                    "compressed_size": info.compress_size,
                    "crc32": f"{info.CRC:08x}",
                }
            )
            if not info.filename.casefold().endswith(".json"):
                continue
            if info.file_size > MAX_JSON_MEMBER_BYTES:
                descriptions.append(
                    {
                        "member": info.filename,
                        "size": info.file_size,
                        "root_type": "skipped",
                        "top_level_keys": [],
                        "interesting_paths": [],
                        "warning": "JSON-Datei ist größer als das sichere Probe-Limit.",
                    }
                )
                continue
            value = _safe_json_load(archive.read(info), info.filename)
            documents[info.filename] = value
            descriptions.append(_describe_document(info.filename, value, info.file_size))

    return members, descriptions, _collect_signals(documents)


def build_rogue_trader_snapshot(save_path: Path) -> JsonObject:
    save_file = resolve_rogue_trader_save(save_path)
    members, documents, signals = _archive_snapshot(save_file)
    stat = save_file.stat()
    return {
        "schema_version": 1,
        "kind": "wachterfeder-rogue-trader-snapshot",
        "source_name": save_file.stem,
        "source_file": save_file.name,
        "source_size": stat.st_size,
        "source_modified_utc": datetime.fromtimestamp(stat.st_mtime, tz=timezone.utc).isoformat(),
        "sha256": sha256_file(save_file),
        "inspected_utc": datetime.now(tz=timezone.utc).isoformat(),
        "archive": {
            "member_count": len(members),
            "json_document_count": len(documents),
            "members": members,
        },
        "probe": {
            "json_documents": documents,
            "purpose": "Schema-Probe bis ein echter Rogue-Trader-Save stabil kartiert ist.",
        },
        "signals": {
            "count": len(signals),
            "truncated": len(signals) >= MAX_SIGNALS,
            "items": signals,
        },
        "warnings": [
            "Der Rogue-Trader-Adapter ist vorbereitet, aber noch nicht gegen einen echten Nutzer-Save validiert.",
            "Interessante Signale sind heuristische Kandidaten und noch keine bestätigten Story-Ereignisse.",
            "Rohinhalte großer JSON-Dateien werden absichtlich nicht in den Snapshot kopiert.",
        ],
    }


def _read_json(path: Path) -> JsonObject | None:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (FileNotFoundError, OSError, json.JSONDecodeError):
        return None
    return value if isinstance(value, dict) else None


def _write_json(payload: JsonObject, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _member_map(snapshot: JsonObject | None) -> dict[str, JsonObject]:
    archive = (snapshot or {}).get("archive") or {}
    members = archive.get("members") if isinstance(archive, Mapping) else []
    return {
        str(item.get("name")): dict(item)
        for item in members or []
        if isinstance(item, Mapping) and item.get("name")
    }


def _member_changes(previous: JsonObject | None, current: JsonObject) -> JsonObject:
    old = _member_map(previous)
    new = _member_map(current)
    added = [new[name] for name in sorted(set(new) - set(old))]
    removed = [old[name] for name in sorted(set(old) - set(new))]
    changed: JsonObject = {}
    for name in sorted(set(old) & set(new)):
        before = old[name]
        after = new[name]
        if before.get("crc32") == after.get("crc32") and before.get("size") == after.get("size"):
            continue
        changed[name] = {
            "from": {"size": before.get("size"), "crc32": before.get("crc32")},
            "to": {"size": after.get("size"), "crc32": after.get("crc32")},
        }
    return {"added": added, "removed": removed, "changed": changed}


def _signal_items(snapshot: JsonObject | None) -> Mapping[str, Any]:
    signals = (snapshot or {}).get("signals") or {}
    items = signals.get("items") if isinstance(signals, Mapping) else {}
    return items if isinstance(items, Mapping) else {}


def _signal_changes(previous: JsonObject | None, current: JsonObject) -> JsonObject:
    old = _signal_items(previous)
    new = _signal_items(current)
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


def build_rogue_trader_delta(previous: JsonObject | None, current: JsonObject) -> JsonObject:
    members = _member_changes(previous, current)
    signals = _signal_changes(previous, current)
    initial = previous is None
    member_change_count = len(members["added"]) + len(members["removed"]) + len(members["changed"])
    has_changes = bool(initial or member_change_count or signals)
    archive = current.get("archive") or {}
    signal_block = current.get("signals") or {}
    return {
        "schema_version": 1,
        "kind": "wachterfeder-rogue-trader-delta",
        "created_utc": datetime.now(tz=timezone.utc).isoformat(),
        "initial_snapshot": initial,
        "previous_save_sha256": (previous or {}).get("sha256"),
        "current_save_sha256": current.get("sha256"),
        "summary": {
            "has_changes": has_changes,
            "archive_member_changes": member_change_count,
            "signal_changes": len(signals),
        },
        "current_state": {
            "save_name": current.get("source_name"),
            "archive_members": archive.get("member_count") if isinstance(archive, Mapping) else None,
            "json_documents": archive.get("json_document_count") if isinstance(archive, Mapping) else None,
            "tracked_signals": signal_block.get("count") if isinstance(signal_block, Mapping) else None,
        },
        "changes": {
            "archive_members": members,
            "signals": signals,
        },
        "notes": [
            "Das Delta enthält nur Änderungen gegenüber dem letzten erfolgreichen Rogue-Trader-Snapshot.",
            "Signaländerungen sind bis zur Real-Save-Kartierung Kandidaten, keine automatisch behaupteten Story-Fakten.",
        ],
    }


def analyse_rogue_trader_save(save_path: Path, *, root: Path | None = None) -> RogueTraderAnalysisResult:
    root = (root or Path(__file__).resolve().parents[2]).expanduser().resolve()
    local_root = root / ".wachterfeder" / "rogue-trader"
    save_file = resolve_rogue_trader_save(save_path)
    current = build_rogue_trader_snapshot(save_file)

    snapshot_path = local_root / "rogue-trader.snapshot.json"
    delta_path = local_root / "rogue-trader.delta.json"
    previous = _read_json(snapshot_path)
    delta = build_rogue_trader_delta(previous, current)

    stamp = datetime.fromtimestamp(save_file.stat().st_mtime).strftime("%Y%m%d-%H%M%S")
    history_delta_path = local_root / "history" / f"{stamp}-{current['sha256'][:8]}.delta.json"
    _write_json(current, snapshot_path)
    _write_json(delta, delta_path)
    _write_json(delta, history_delta_path)

    summary = delta["summary"]
    archive = current["archive"]
    return RogueTraderAnalysisResult(
        save_file=save_file,
        snapshot_path=snapshot_path,
        delta_path=delta_path,
        history_delta_path=history_delta_path,
        initial_snapshot=bool(delta["initial_snapshot"]),
        has_changes=bool(summary["has_changes"]),
        archive_members=int(archive["member_count"]),
        json_documents=int(archive["json_document_count"]),
        changed_members=int(summary["archive_member_changes"]),
        changed_signals=int(summary["signal_changes"]),
    )


def _cmd_paths(_: argparse.Namespace) -> int:
    for path in candidate_rogue_trader_save_roots():
        print(f"[{'gefunden' if path.is_dir() else 'nicht gefunden'}] {path}")
    newest = newest_rogue_trader_save()
    print(f"\nNeuester Rogue-Trader-Spielstand: {newest}" if newest else "\nKein Rogue-Trader-Spielstand gefunden.")
    return 0


def _cmd_inspect(args: argparse.Namespace) -> int:
    result = analyse_rogue_trader_save(Path(args.save), root=Path(args.root) if args.root else None)
    print(f"Save:        {result.save_file}")
    print(f"Dateien:     {result.archive_members}")
    print(f"JSON:        {result.json_documents}")
    print(f"Dateien Δ:   {result.changed_members}")
    print(f"Signale Δ:   {result.changed_signals}")
    print(f"Snapshot:    {result.snapshot_path}")
    print(f"Delta:       {result.delta_path}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Wächterfeder-Adapter für Warhammer 40,000: Rogue Trader")
    sub = parser.add_subparsers(dest="command", required=True)

    paths = sub.add_parser("paths", help="übliche Rogue-Trader-Speicherorte prüfen")
    paths.set_defaults(func=_cmd_paths)

    inspect = sub.add_parser("inspect", help="Rogue-Trader-Spielstand prüfen und Delta erzeugen")
    inspect.add_argument("--save", required=True, help=".zks-Spielstand oder Ordner mit Spielständen")
    inspect.add_argument("--root", default=None, help="Repository-Stamm für Tests")
    inspect.set_defaults(func=_cmd_inspect)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main())
