#!/usr/bin/env python3
"""Install and read the optional Wächterfeder EEex combat logger.

The logger is intentionally tiny and local-only. It installs one ``M_*.lua``
file into the EET override folder and writes runtime data below the ignored
``.wachterfeder/eet/runtime`` directory. It never changes savegame state.
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
LOGGER_CURRENT_MARKER = "WACHTERFEDER_EEEX_SAFE_LOGGING_V2"
LOGGER_SCRIPT_NAME = "M_WFLOG.lua"
TEMPLATE_RELATIVE = Path("tools/wachterfeder/eeex/M_WFLOG.lua.template")
LOG_PREFIX = "WFLOG|"


@dataclass(frozen=True)
class CombatLoggerStatus:
    eeex_available: bool
    installed: bool
    up_to_date: bool
    script_path: Path
    log_path: Path


def repository_root() -> Path:
    return Path(__file__).resolve().parents[2]


def runtime_log_path(root: Path | None = None) -> Path:
    root = (root or repository_root()).expanduser().resolve()
    return root / ".wachterfeder" / "eet" / "runtime" / "combat.jsonl"


def _script_path(game_root: Path) -> Path:
    return game_root / "override" / LOGGER_SCRIPT_NAME


def _eeex_available(game_root: Path) -> bool:
    return (game_root / "EEex.dll").is_file() and (game_root / "InfinityLoader.exe").is_file()


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
    return CombatLoggerStatus(
        eeex_available=_eeex_available(assets.game_root),
        installed=installed,
        up_to_date=up_to_date,
        script_path=script,
        log_path=runtime_log_path(root),
    )


def _render_template(log_path: Path, *, root: Path) -> str:
    template = (root / TEMPLATE_RELATIVE).read_text(encoding="utf-8")
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

    log_path = runtime_log_path(root)
    log_path.parent.mkdir(parents=True, exist_ok=True)
    log_path.touch(exist_ok=True)
    script.parent.mkdir(parents=True, exist_ok=True)
    # Reinstalling is intentionally an in-place upgrade of Wächterfeder's own
    # script. This is how fixes to the Lua runtime logger reach an existing setup.
    script.write_text(_render_template(log_path, root=root), encoding="utf-8")
    status = logger_status(assets.game_root, root=root, language=language)
    if not status.up_to_date:
        raise EetError(
            "Der Combatlogger wurde geschrieben, aber die aktuelle Logger-Version konnte danach nicht bestätigt werden."
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
    """Return a JSON payload and whether the line belongs to Wächterfeder.

    EEex Minimal does not necessarily expose Lua's ``io`` library. In that
    environment the Lua logger uses CLUAConsole logging, which can include
    unrelated engine lines and formatting around our message. Only text after
    the unique ``WFLOG|`` marker is parsed. Bare JSON remains supported for
    older logger versions that wrote directly via ``io.open``.
    """
    text = _decode_log_line(raw_line).strip()
    if not text:
        return None, False
    marker = text.find(LOG_PREFIX)
    if marker >= 0:
        return text[marker + len(LOG_PREFIX) :].strip(), True
    if text.startswith("{"):
        return text, True
    return None, False


def read_new_events(log_path: Path, start_offset: int) -> tuple[list[JsonObject], JsonObject]:
    try:
        size = log_path.stat().st_size
    except OSError:
        return [], {"exists": False, "cursor": 0, "size": 0, "malformed_lines": 0}

    offset = max(0, int(start_offset or 0))
    # Engine logging may recreate/truncate the log on a new game launch.
    if offset > size:
        offset = 0

    events: list[JsonObject] = []
    malformed = 0
    with log_path.open("rb") as handle:
        handle.seek(offset)
        payload = handle.read()
        cursor = handle.tell()

    for raw_line in payload.splitlines():
        json_text, belongs_to_wachterfeder = _json_payload_from_log_line(raw_line)
        if not belongs_to_wachterfeder:
            # CLUAConsole may put unrelated engine messages into the same file.
            # They are intentionally ignored rather than counted as logger errors.
            continue
        if not json_text:
            malformed += 1
            continue
        try:
            item = json.loads(json_text)
        except json.JSONDecodeError:
            malformed += 1
            continue
        if isinstance(item, dict):
            events.append(item)
        else:
            malformed += 1

    metadata = log_metadata(log_path)
    metadata["cursor"] = cursor
    metadata["malformed_lines"] = malformed
    return events, metadata


def summarise_events(events: list[JsonObject]) -> JsonObject:
    damage_events = [item for item in events if item.get("event") == "damage"]
    return {
        "events": len(events),
        "damage_events": len(damage_events),
        "damage_total": sum(int(item.get("damage") or 0) for item in damage_events),
        "lethal_candidates": sum(1 for item in damage_events if item.get("lethal_candidate") is True),
        "logger_errors": sum(1 for item in events if item.get("event") == "logger_error"),
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Wächterfeder EEex Combat-Logger")
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
        print(f"Wächterfeder Combat-Logger: {exc}")
        return 2

    print(f"EEex:   {'erkannt' if status.eeex_available else 'nicht erkannt'}")
    if status.installed:
        logger_text = "aktuell" if status.up_to_date else "veraltet"
    else:
        logger_text = "nicht installiert"
    print(f"Logger: {logger_text}")
    print(f"Script: {status.script_path}")
    print(f"Log:    {status.log_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
