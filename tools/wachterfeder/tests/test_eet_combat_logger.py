from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from tools.wachterfeder.eet_combat_logger import (
    LOGGER_MARKER,
    install_logger,
    read_new_events,
    runtime_log_path,
    summarise_events,
    uninstall_logger,
)
from tools.wachterfeder.eet_session_runtime import _augment_delta


class EetCombatLoggerTests(unittest.TestCase):
    def _make_game(self, root: Path) -> Path:
        game = root / "BG2EE"
        (game / "lang" / "de_DE").mkdir(parents=True)
        (game / "chitin.key").write_bytes(b"KEY ")
        (game / "lang" / "de_DE" / "dialog.tlk").write_bytes(b"TLK V1  ")
        (game / "EEex.dll").write_bytes(b"eeex")
        (game / "InfinityLoader.exe").write_bytes(b"loader")
        return game

    def _make_template(self, root: Path) -> None:
        template = root / "tools" / "wachterfeder" / "eeex" / "M_WFLOG.lua.template"
        template.parent.mkdir(parents=True)
        template.write_text(
            f"-- {LOGGER_MARKER}\nlocal LOG = [[__WACHTERFEDER_LOG_PATH__]]\n",
            encoding="utf-8",
        )

    def test_install_and_uninstall_logger_are_local_and_reversible(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            game = self._make_game(root)
            self._make_template(root)

            status = install_logger(game, root=root)
            self.assertTrue(status.installed)
            self.assertTrue(status.eeex_available)
            self.assertTrue(status.script_path.is_file())
            self.assertIn(LOGGER_MARKER, status.script_path.read_text(encoding="utf-8"))
            self.assertIn(runtime_log_path(root).as_posix(), status.script_path.read_text(encoding="utf-8"))

            status = uninstall_logger(game, root=root)
            self.assertFalse(status.installed)
            self.assertFalse((game / "override" / "M_WFLOG.lua").exists())

    def test_reader_returns_only_appended_valid_json_lines(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            log = Path(temporary) / "combat.jsonl"
            log.write_text('{"event":"old"}\n', encoding="utf-8")
            offset = log.stat().st_size
            with log.open("a", encoding="utf-8") as handle:
                handle.write('{"event":"damage","damage":7,"lethal_candidate":false}\n')
                handle.write('not-json\n')
                handle.write('{"event":"damage","damage":5,"lethal_candidate":true}\n')

            events, metadata = read_new_events(log, offset)
            self.assertEqual(len(events), 2)
            self.assertEqual(metadata["malformed_lines"], 1)
            summary = summarise_events(events)
            self.assertEqual(summary["damage_total"], 12)
            self.assertEqual(summary["lethal_candidates"], 1)

    def test_delta_augmentation_keeps_combat_events_compact(self) -> None:
        delta = {"summary": {"has_changes": False}, "changes": {}, "notes": []}
        events = [
            {
                "event": "damage",
                "source": "Kivan",
                "target": "Hobgoblin",
                "damage": 9,
                "lethal_candidate": True,
            }
        ]
        updated = _augment_delta(delta, events, initial_runtime_baseline=False)
        self.assertTrue(updated["summary"]["has_changes"])
        self.assertEqual(updated["summary"]["combat_damage_total"], 9)
        self.assertEqual(updated["changes"]["combat_log"][0]["source"], "Kivan")


if __name__ == "__main__":
    unittest.main()
