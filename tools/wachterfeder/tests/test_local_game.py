from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from tools.wachterfeder.local_game import (
    read_local_config,
    resolve_local_assets,
    write_local_config,
)


class LocalGameTests(unittest.TestCase):
    def _make_installation(self, root: Path) -> tuple[Path, Path, Path]:
        game_root = root / "Pillars of Eternity"
        data_root = game_root / "PillarsOfEternity_Data" / "data"
        conversations = data_root / "conversations" / "07_gilded_vale"
        strings = (
            data_root
            / "localized"
            / "de"
            / "text"
            / "conversations"
            / "07_gilded_vale"
        )
        conversations.mkdir(parents=True)
        strings.mkdir(parents=True)
        return game_root, conversations, strings

    def test_resolves_from_game_root(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            game_root, conversations, strings = self._make_installation(Path(tmp))

            assets = resolve_local_assets(game_root, "de")

            self.assertEqual(assets.conversation_root, conversations.parent)
            self.assertEqual(assets.stringtable_root, strings.parent)

    def test_resolves_from_localized_conversations_folder(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            _, conversations, strings = self._make_installation(Path(tmp))

            assets = resolve_local_assets(strings.parent, "de")

            self.assertEqual(assets.conversation_root, conversations.parent)
            self.assertEqual(assets.stringtable_root, strings.parent)

    def test_config_roundtrip_stores_only_path_and_language(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            game_root, conversations, strings = self._make_installation(root)
            config_path = root / ".wachterfeder" / "config.json"
            assets = resolve_local_assets(game_root, "de")

            write_local_config(assets, config_path)
            restored = read_local_config(config_path)
            payload = json.loads(config_path.read_text(encoding="utf-8"))

            self.assertEqual(restored.conversation_root, conversations.parent)
            self.assertEqual(restored.stringtable_root, strings.parent)
            self.assertEqual(
                set(payload),
                {"schema_version", "data_root", "language"},
            )


if __name__ == "__main__":
    unittest.main()
