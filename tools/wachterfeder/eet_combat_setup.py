#!/usr/bin/env python3
"""Convenience setup for the optional EET EEex combat logger."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Sequence

from tools.wachterfeder.eet_combat_logger import install_logger, logger_status, uninstall_logger


def repository_root() -> Path:
    return Path(__file__).resolve().parents[2]


def _config(root: Path) -> dict:
    path = root / ".wachterfeder" / "eet" / "config.json"
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return value if isinstance(value, dict) else {}


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Wächterfeder EET Combat-Logger lokal verwalten")
    parser.add_argument("command", choices=("install", "status", "uninstall"), nargs="?", default="install")
    parser.add_argument("--game-path", default=None)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    root = repository_root()
    config = _config(root)
    game_text = args.game_path or config.get("game_root")
    if not game_text:
        print("Kein lokaler EET-Spielordner gespeichert.")
        print("Öffne zuerst Wächterfeder > Baldur's Gate EET und führe einmal eine Auswertung aus.")
        print("Alternativ: python tools\\wachterfeder\\eet_combat_setup.py install --game-path <BG2EE-Ordner>")
        return 2

    game = Path(str(game_text))
    try:
        if args.command == "install":
            status = install_logger(game, root=root)
        elif args.command == "uninstall":
            status = uninstall_logger(game, root=root)
        else:
            status = logger_status(game, root=root)
    except Exception as exc:
        print(f"Combat-Logger konnte nicht eingerichtet werden: {exc}")
        return 2

    print(f"EEex:   {'erkannt' if status.eeex_available else 'nicht erkannt'}")
    print(f"Logger: {'installiert' if status.installed else 'nicht installiert'}")
    print(f"Script: {status.script_path}")
    print(f"Log:    {status.log_path}")
    if args.command == "install" and status.installed:
        print("\nFertig. EET weiterhin über InfinityLoader.exe starten.")
        print("Vor der nächsten Spielsitzung einmal Wächterfeder > Baldur's Gate EET auswerten, damit der Combat-Log-Cursor gesetzt wird.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
