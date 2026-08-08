from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from tools.wachterfeder.eet_combat_logger import (
    LOGGER_CURRENT_MARKER,
    LOGGER_MARKER,
    LOG_PREFIX,
    install_logger,
    logger_status,
    read_new_events,
    runtime_log_path,
    summarise_events,
    uninstall_logger,
)
from tools.wachterfeder.eet_session_runtime import _augment_combat


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
            f"-- {LOGGER_MARKER}\n-- {LOGGER_CURRENT_MARKER}\nlocal LOG = [[__WACHTERFEDER_LOG_PATH__]]\n",
            encoding="utf-8",
        )

    def test_install_and_uninstall_logger_are_local_and_reversible(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            game = self._make_game(root)
            self._make_template(root)

            status = install_logger(game, root=root)
            self.assertTrue(status.installed)
            self.assertTrue(status.up_to_date)
            self.assertTrue(status.eeex_available)
            self.assertTrue(status.script_path.is_file())
            self.assertIn(LOGGER_MARKER, status.script_path.read_text(encoding="utf-8"))
            self.assertIn(LOGGER_CURRENT_MARKER, status.script_path.read_text(encoding="utf-8"))
            self.assertIn(runtime_log_path(root).as_posix(), status.script_path.read_text(encoding="utf-8"))

            status = uninstall_logger(game, root=root)
            self.assertFalse(status.installed)
            self.assertFalse(status.up_to_date)
            self.assertFalse((game / "override" / "M_WFLOG.lua").exists())

    def test_status_marks_legacy_logger_as_outdated(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            game = self._make_game(root)
            script = game / "override" / "M_WFLOG.lua"
            script.parent.mkdir(parents=True)
            script.write_text(f"-- {LOGGER_MARKER}\nlocal file = io.open('x', 'a')\n", encoding="utf-8")
            status = logger_status(game, root=root)
            self.assertTrue(status.installed)
            self.assertFalse(status.up_to_date)

    def test_reader_accepts_prefixed_clua_lines_and_ignores_engine_noise(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            log = Path(temporary) / "combat.jsonl"
            log.write_text("old engine output\n", encoding="utf-8")
            offset = log.stat().st_size
            with log.open("a", encoding="utf-8") as handle:
                handle.write('Some engine prefix ' + LOG_PREFIX + '{"event":"damage","damage":7,"lethal_candidate":false}\n')
                handle.write('ordinary unrelated engine line\n')
                handle.write(LOG_PREFIX + '{"event":"damage","damage":5,"lethal_candidate":true}\n')

            events, metadata = read_new_events(log, offset)
            self.assertEqual(len(events), 2)
            self.assertEqual(metadata["malformed_lines"], 0)
            summary = summarise_events(events)
            self.assertEqual(summary["damage_total"], 12)
            self.assertEqual(summary["lethal_candidates"], 1)

    def test_reader_keeps_legacy_bare_json_support(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            log = Path(temporary) / "combat.jsonl"
            log.write_text('{"event":"damage","damage":3}\nnot-json\n', encoding="utf-8")
            events, metadata = read_new_events(log, 0)
            self.assertEqual(len(events), 1)
            self.assertEqual(events[0]["damage"], 3)
            # Unprefixed engine/noise lines are ignored rather than treated as logger corruption.
            self.assertEqual(metadata["malformed_lines"], 0)

    def test_real_template_does_not_assume_lua_io_exists(self) -> None:
        template = Path(__file__).resolve().parents[1] / "eeex" / "M_WFLOG.lua.template"
        text = template.read_text(encoding="utf-8")
        self.assertIn(LOGGER_CURRENT_MARKER, text)
        self.assertIn('type(io) == "table"', text)
        self.assertIn("C:LogSet(WF_LOG_PATH)", text)
        self.assertIn("C:LogMessages()", text)
        self.assertIn("Infinity_Log", text)
        self.assertIn("pcall(function() wf_append", text)

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
        _augment_combat(delta, events, initial_runtime_baseline=False)
        self.assertTrue(delta["summary"]["has_changes"])
        self.assertEqual(delta["summary"]["combat_damage_total"], 9)
        self.assertEqual(delta["changes"]["combat_log"][0]["source"], "Kivan")


if __name__ == "__main__":
    unittest.main()
