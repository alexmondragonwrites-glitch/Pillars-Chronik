#!/usr/bin/env python3
"""Install the optional Wächterfeder EEex save-telemetry observer.

V7 no longer relies on native UI diagnostics, CLUAConsole logging, or direct
file I/O from Lua. The installed ``M_WFLOG.lua`` writes only namespaced WF_*
integer GLOBAL values into the next save. The normal EET save parser reads
those values afterwards. Legacy log-reader helpers remain for old snapshots.
"""
from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Sequence

try:
    from tools.wachterfeder.eet import EetError, resolve_eet_game_assets
except ModuleNotFoundError:  # direct execution from tools/wachterfeder
    from eet import EetError, resolve_eet_game_assets

JsonObject = dict[str, Any]
LOGGER_MARKER = "WACHTERFEDER_EET_COMBAT_LOGGER_V1"
LOGGER_CURRENT_MARKER = "WACHTERFEDER_EET_SAVE_TELEMETRY_V7"
LOGGER_SCRIPT_NAME = "M_WFLOG.lua"
ENGINE_LOG_NAME = "Wachterfeder-runtime.log"  # legacy V3-V6 file
TEMPLATE_RELATIVE = Path("tools/wachterfeder/eeex/M_WFLOG.lua.template")
LOG_PREFIX = "WFLOG|"


@dataclass(frozen=True)
class CombatLoggerStatus:
    eeex_available: bool
    installed: bool
    up_to_date: bool
    runtime_active: bool
    script_path: Path
    log_path: Path


def repository_root() -> Path:
    return Path(__file__).resolve().parents[2]


def runtime_log_path(root: Path | None = None, *, game_root: Path | None = None) -> Path:
    """Return the legacy runtime-log path kept for backward compatibility."""
    if game_root is not None:
        return game_root.expanduser().resolve() / ENGINE_LOG_NAME
    root = (root or repository_root()).expanduser().resolve()
    return root / ".wachterfeder" / "eet" / "runtime" / "combat.jsonl"


def _script_path(game_root: Path) -> Path:
    return game_root / "override" / LOGGER_SCRIPT_NAME


def _eeex_available(game_root: Path) -> bool:
    return (game_root / "EEex.dll").is_file() and (game_root / "InfinityLoader.exe").is_file()


def _runtime_has_heartbeat(log_path: Path) -> bool:
    """Legacy V3-V6 heartbeat detector. V7 activity is proved by save globals."""
    try:
        if not log_path.is_file() or log_path.stat().st_size <= 0:
            return False
        text = log_path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return False
    return LOG_PREFIX in text and '"event":"runtime_start"' in text


def logger_status(game_path: Path, *, root: Path | None = None, language: str = "de_DE") -> CombatLoggerStatus:
    assets = resolve_eet_game_assets(game_path, language)
    script = _script_path(assets.game_root)
    installed = False
    up_to_date = False
    try:
        content = script.read_text(encoding="utf-8", errors="replace")
        installed = LOGGER_MARKER in content
        up_to_date = installed and LOGGER_CURRENT_MARKER in content
    except OSError:
        pass
    log_path = runtime_log_path(root, game_root=assets.game_root)
    return CombatLoggerStatus(
        eeex_available=_eeex_available(assets.game_root),
        installed=installed,
        up_to_date=up_to_date,
        # V7 intentionally has no live file heartbeat. Activity is confirmed
        # after saving, via WF_RUNTIME_VERSION / WF_RUNTIME_BOOT_SEQ.
        runtime_active=False,
        script_path=script,
        log_path=log_path,
    )


def _render_template(log_path: Path, *, root: Path) -> str:
    template = (root / TEMPLATE_RELATIVE).read_text(encoding="utf-8")
    # Placeholder replacement is retained so old/custom templates remain
    # installable, although the V7 template contains no log path.
    portable = log_path.resolve().as_posix()
    return template.replace("__WACHTERFEDER_LOG_PATH__", portable)


def install_logger(game_path: Path, *, root: Path | None = None, language: str = "de_DE") -> CombatLoggerStatus:
    root = (root or repository_root()).expanduser().resolve()
    assets = resolve_eet_game_assets(game_path, language)
    if not _eeex_available(assets.game_root):
        raise EetError(
            "EEex wurde im EET-Spielordner nicht erkannt. Erwartet werden EEex.dll und InfinityLoader.exe."
        )

    script = _script_path(assets.game_root)
    if script.exists():
        existing = script.read_text(encoding="utf-8", errors="replace")
        if LOGGER_MARKER not in existing:
            raise EetError(
                f"{script.name} existiert bereits und gehört nicht eindeutig zu Wächterfeder. Datei bleibt unangetastet."
            )

    log_path = runtime_log_path(root, game_root=assets.game_root)
    script.parent.mkdir(parents=True, exist_ok=True)
    script.write_text(_render_template(log_path, root=root), encoding="utf-8")

    # Remove the obsolete Wächterfeder-owned V3-V6 log so the UI cannot mistake
    # stale bytes for current V7 activity.
    try:
        if log_path.exists():
            log_path.unlink()
    except OSError:
        pass

    status = logger_status(assets.game_root, root=root, language=language)
    if not status.up_to_date:
        raise EetError(
            "Die EEex-Save-Telemetrie wurde geschrieben, aber V7 konnte danach nicht bestätigt werden."
        )
    return status


def uninstall_logger(game_path: Path, *, root: Path | None = None, language: str = "de_DE") -> CombatLoggerStatus:
    root = (root or repository_root()).expanduser().resolve()
    assets = resolve_eet_game_assets(game_path, language)
    script = _script_path(assets.game_root)
    if script.exists():
        content = script.read_text(encoding="utf-8", errors="replace")
        if LOGGER_MARKER not in content:
            raise EetError(
                f"{script.name} ist keine eindeutig erkennbare Wächterfeder-Datei und wird nicht gelöscht."
            )
        script.unlink()
    log_path = runtime_log_path(root, game_root=assets.game_root)
    try:
        if log_path.exists():
            log_path.unlink()
    except OSError:
        pass
    return logger_status(assets.game_root, root=root, language=language)


def log_metadata(log_path: Path) -> JsonObject:
    try:
        stat = log_path.stat()
    except OSError:
        return {"exists": False, "cursor": 0, "size": 0}
    return {
        "exists": True,
        "cursor": stat.st_size,
        "size": stat.st_size,
        "modified_ns": stat.st_mtime_ns,
    }


def _decode_log_line(raw_line: bytes) -> str:
    try:
        return raw_line.decode("utf-8")
    except UnicodeDecodeError:
        return raw_line.decode("cp1252", errors="replace")


def _json_payload_from_log_line(raw_line: bytes) -> tuple[str | None, bool]:
    text = _decode_log_line(raw_line).strip()
    if not text:
        return None, False
    marker = text.find(LOG_PREFIX)
    if marker >= 0:
        return text[marker + len(LOG_PREFIX) :].strip(), True
    if text.startswith("{"):
        return text, True
    return None, False


def _event_identity(item: JsonObject) -> tuple[Any, ...]:
    schema = item.get("schema_version")
    seq = item.get("seq")
    event = item.get("event")
    if seq is not None:
        return (schema, seq, event)
    return (json.dumps(item, ensure_ascii=False, sort_keys=True),)


def read_new_events(log_path: Path, start_offset: int) -> tuple[list[JsonObject], JsonObject]:
    """Read legacy V3-V6 runtime lines when an old log still exists."""
    try:
        size = log_path.stat().st_size
    except OSError:
        return [], {"exists": False, "cursor": 0, "size": 0, "malformed_lines": 0}

    offset = max(0, int(start_offset or 0))
    if offset > size:
        offset = 0

    events: list[JsonObject] = []
    seen: set[tuple[Any, ...]] = set()
    malformed = 0
    with log_path.open("rb") as handle:
        handle.seek(offset)
        payload = handle.read()
        cursor = handle.tell()

    for raw_line in payload.splitlines():
        json_text, belongs_to_wachterfeder = _json_payload_from_log_line(raw_line)
        if not belongs_to_wachterfeder:
            continue
        if not json_text:
            malformed += 1
            continue
        try:
            item = json.loads(json_text)
        except json.JSONDecodeError:
            malformed += 1
            continue
        if not isinstance(item, dict):
            malformed += 1
            continue
        identity = _event_identity(item)
        if identity in seen:
            continue
        seen.add(identity)
        events.append(item)

    metadata = log_metadata(log_path)
    metadata["cursor"] = cursor
    metadata["malformed_lines"] = malformed
    return events, metadata


def summarise_events(events: list[JsonObject]) -> JsonObject:
    damage_events = [item for item in events if item.get("event") == "damage"]
    dialogue_events = [item for item in events if item.get("event") == "dialogue_choice"]
    runtime_starts = [item for item in events if item.get("event") == "runtime_start"]
    return {
        "events": len(events),
        "damage_events": len(damage_events),
        "damage_total": sum(int(item.get("damage") or 0) for item in damage_events),
        "lethal_candidates": sum(1 for item in damage_events if item.get("lethal_candidate") is True),
        "dialogue_choices": len(dialogue_events),
        "runtime_starts": len(runtime_starts),
        "logger_errors": sum(1 for item in events if item.get("event") == "logger_error"),
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Wächterfeder EEex Save-Telemetrie")
    sub = parser.add_subparsers(dest="command", required=True)
    for name in ("install", "status", "uninstall"):
        item = sub.add_parser(name)
        item.add_argument("--game-path", required=True)
        item.add_argument("--language", default="de_DE")
        item.add_argument("--root", default=None)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    root = Path(args.root).resolve() if args.root else None
    game = Path(args.game_path)
    try:
        if args.command == "install":
            status = install_logger(game, root=root, language=args.language)
        elif args.command == "uninstall":
            status = uninstall_logger(game, root=root, language=args.language)
        else:
            status = logger_status(game, root=root, language=args.language)
    except (OSError, EetError) as exc:
        print(f"Wächterfeder EEex-Telemetrie: {exc}")
        return 2

    print(f"EEex:      {'erkannt' if status.eeex_available else 'nicht erkannt'}")
    if status.installed:
        telemetry_text = "aktuell" if status.up_to_date else "veraltet"
    else:
        telemetry_text = "nicht installiert"
    print(f"Telemetrie: {telemetry_text}")
    print("Aktivität: wird nach dem nächsten Speichern über WF_* GLOBALs geprüft")
    print(f"Script:    {status.script_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
