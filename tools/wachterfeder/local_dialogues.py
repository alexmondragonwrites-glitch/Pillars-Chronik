#!/usr/bin/env python3
"""Use local Pillars assets to build dialogue reports without committing them."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Sequence

try:
    from tools.wachterfeder.dialogues import build_dialogue_report
    from tools.wachterfeder.local_game import (
        DEFAULT_CONFIG_PATH,
        LocalGameError,
        read_local_config,
        resolve_local_assets,
        write_local_config,
    )
except ModuleNotFoundError:  # Direct execution from tools/wachterfeder.
    from dialogues import build_dialogue_report
    from local_game import (
        DEFAULT_CONFIG_PATH,
        LocalGameError,
        read_local_config,
        resolve_local_assets,
        write_local_config,
    )


def _config_path(value: str) -> Path:
    return Path(value)


def cmd_configure(args: argparse.Namespace) -> int:
    assets = resolve_local_assets(Path(args.path), args.language)
    config_path = write_local_config(assets, args.config)
    print(f"Konfiguration: {config_path}")
    print(f"Dialoggraphen: {assets.conversation_root}")
    print(f"Texte ({assets.language}): {assets.stringtable_root}")
    print("Spielressourcen bleiben lokal und werden nicht kopiert.")
    return 0


def cmd_status(args: argparse.Namespace) -> int:
    assets = read_local_config(args.config)
    print(f"Datenordner:   {assets.data_root}")
    print(f"Dialoggraphen: {assets.conversation_root}")
    print(f"Texte ({assets.language}): {assets.stringtable_root}")
    return 0


def cmd_report(args: argparse.Namespace) -> int:
    if args.game_path:
        assets = resolve_local_assets(Path(args.game_path), args.language)
        if args.remember:
            write_local_config(assets, args.config)
    else:
        assets = read_local_config(args.config)

    snapshot_path = args.snapshot.expanduser().resolve()
    if not snapshot_path.is_file():
        raise LocalGameError(f"Snapshot nicht gefunden: {snapshot_path}")

    try:
        snapshot = json.loads(snapshot_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise LocalGameError(
            f"Snapshot konnte nicht gelesen werden: {snapshot_path}: {exc}"
        ) from exc

    report = build_dialogue_report(
        snapshot,
        assets.conversation_root,
        assets.stringtable_root,
    )
    output = args.output.expanduser().resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )

    print(f"Dialogreport: {output}")
    print(f"Zugeordnet:   {report['matched_conversations']}")
    print(f"Nicht gefunden: {len(report['unresolved_conversations'])}")
    print(f"Lokalisierung: {assets.language}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="local_dialogues",
        description=(
            "Lokale Pillars-Dialogdaten verwenden, ohne Spielressourcen ins Git zu kopieren"
        ),
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    configure = subparsers.add_parser(
        "configure",
        help="lokalen Installationspfad speichern",
    )
    configure.add_argument(
        "path",
        help=(
            "Spielordner oder ein Unterordner darin, z. B. "
            r"E:\SteamLibrary\steamapps\common\Pillars of Eternity"
        ),
    )
    configure.add_argument("--language", default="de", help="Sprache, Standard: de")
    configure.add_argument(
        "--config",
        type=_config_path,
        default=DEFAULT_CONFIG_PATH,
        help="lokale Konfigurationsdatei",
    )
    configure.set_defaults(func=cmd_configure)

    status = subparsers.add_parser("status", help="lokale Pfade prüfen")
    status.add_argument(
        "--config",
        type=_config_path,
        default=DEFAULT_CONFIG_PATH,
        help="lokale Konfigurationsdatei",
    )
    status.set_defaults(func=cmd_status)

    report = subparsers.add_parser(
        "report",
        help="Save-Snapshot mit lokalen Dialogen verbinden",
    )
    report.add_argument("snapshot", type=Path, help="Wächterfeder-Snapshot JSON")
    report.add_argument("--output", type=Path, required=True, help="lokale Ausgabedatei")
    report.add_argument(
        "--config",
        type=_config_path,
        default=DEFAULT_CONFIG_PATH,
        help="lokale Konfigurationsdatei",
    )
    report.add_argument(
        "--game-path",
        help="optionaler Pfad statt der gespeicherten Konfiguration",
    )
    report.add_argument("--language", default="de", help="Sprache für --game-path")
    report.add_argument(
        "--remember",
        action="store_true",
        help="--game-path nach erfolgreicher Prüfung lokal speichern",
    )
    report.set_defaults(func=cmd_report)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        return int(args.func(args))
    except (OSError, LocalGameError) as exc:
        print(f"Fehler: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
