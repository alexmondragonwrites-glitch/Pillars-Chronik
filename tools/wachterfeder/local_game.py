#!/usr/bin/env python3
"""Resolve user-owned local Pillars of Eternity assets.

Only paths are stored. Game resources and extracted dialogue text stay outside Git.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

DEFAULT_CONFIG_PATH = Path(".wachterfeder/config.json")
CONFIG_SCHEMA_VERSION = 1


class LocalGameError(RuntimeError):
    """Expected error while locating or configuring local game assets."""


@dataclass(frozen=True)
class LocalGameAssets:
    data_root: Path
    conversation_root: Path
    stringtable_root: Path
    language: str


def _unique_paths(paths: list[Path]) -> list[Path]:
    result: list[Path] = []
    seen: set[str] = set()
    for path in paths:
        key = str(path).casefold()
        if key not in seen:
            seen.add(key)
            result.append(path)
    return result


def candidate_data_roots(path: Path) -> list[Path]:
    """Return plausible ``PillarsOfEternity_Data/data`` roots for any path inside it."""
    path = path.expanduser().resolve()
    candidates = [
        path / "PillarsOfEternity_Data" / "data",
        path / "data",
        path,
    ]

    for ancestor in (path, *path.parents):
        if (
            ancestor.name.casefold() == "data"
            and ancestor.parent.name.casefold() == "pillarsofeternity_data"
        ):
            candidates.append(ancestor)
        candidates.append(ancestor / "PillarsOfEternity_Data" / "data")

    return _unique_paths(candidates)


def resolve_local_assets(path: Path, language: str = "de") -> LocalGameAssets:
    """Resolve conversation and localized text folders from an installation path.

    ``path`` may be the game root, ``PillarsOfEternity_Data/data`` itself, or a
    deeper folder such as ``localized/de/text/conversations``.
    """
    language = language.strip().casefold()
    if not language:
        raise LocalGameError("Die Sprache darf nicht leer sein.")

    checked: list[Path] = []
    for data_root in candidate_data_roots(path):
        checked.append(data_root)
        conversation_root = data_root / "conversations"
        stringtable_root = data_root / "localized" / language / "text" / "conversations"
        if conversation_root.is_dir() and stringtable_root.is_dir():
            return LocalGameAssets(
                data_root=data_root,
                conversation_root=conversation_root,
                stringtable_root=stringtable_root,
                language=language,
            )

    rendered = "\n".join(f"- {candidate}" for candidate in checked[:12])
    raise LocalGameError(
        "Die lokalen Pillars-Dialogdaten wurden nicht gefunden. Geprüft wurden:\n"
        f"{rendered}\n"
        "Erwartet werden die Ordner 'conversations' und "
        f"'localized/{language}/text/conversations'."
    )


def write_local_config(
    assets: LocalGameAssets,
    config_path: Path = DEFAULT_CONFIG_PATH,
) -> Path:
    """Persist only the local data path and language in an ignored JSON file."""
    config_path = config_path.expanduser().resolve()
    config_path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "schema_version": CONFIG_SCHEMA_VERSION,
        "data_root": str(assets.data_root),
        "language": assets.language,
    }
    config_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return config_path


def read_local_config(config_path: Path = DEFAULT_CONFIG_PATH) -> LocalGameAssets:
    """Read and validate a local Wächterfeder game-path configuration."""
    config_path = config_path.expanduser().resolve()
    if not config_path.is_file():
        raise LocalGameError(
            f"Lokale Konfiguration nicht gefunden: {config_path}\n"
            "Führe zuerst 'local_dialogues.py configure <Pillars-Pfad>' aus."
        )

    try:
        payload = json.loads(config_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise LocalGameError(
            f"Lokale Konfiguration konnte nicht gelesen werden: {config_path}: {exc}"
        ) from exc

    if payload.get("schema_version") != CONFIG_SCHEMA_VERSION:
        raise LocalGameError(
            f"Nicht unterstützte Konfigurationsversion in {config_path}."
        )

    data_root = payload.get("data_root")
    language = payload.get("language", "de")
    if not isinstance(data_root, str) or not data_root.strip():
        raise LocalGameError(f"Ungültiger data_root in {config_path}.")
    if not isinstance(language, str):
        raise LocalGameError(f"Ungültige Sprache in {config_path}.")

    return resolve_local_assets(Path(data_root), language)
