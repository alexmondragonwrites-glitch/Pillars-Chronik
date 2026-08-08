from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from tools.wachterfeder.eet_combat_logger import (
    ENGINE_LOG_NAME,
    LOGGER_CURRENT_MARKER,
    LOGGER_MARKER,
    LOG_PREFIX,
    install_logger,
    logger_status,
    read_new_events,
    summarise_events,
    uninstall_logger,
)
from tools.wachterfeder.eet_session_runtime import _augment_runtime


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
            f"-- {LOGGER_MARKER}\n-- {LOGGER_CURRENT_MARKER}\nlocal WF_LOG_PATH = [[__WACHTERFEDER_LOG_PATH__]]\n",
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
            self.assertFalse(status.runtime_active)
            self.assertTrue(status.script_path.is_file())
            self.assertEqual(status.log_path, game.resolve() / ENGINE_LOG_NAME)
            self.assertTrue(status.log_path.is_file())
            self.assertEqual(status.log_path.stat().st_size, 0)
            script_text = status.script_path.read_text(encoding="utf-8")
            self.assertIn(LOGGER_MARKER, script_text)
            self.assertIn(LOGGER_CURRENT_MARKER, script_text)
            self.assertIn(status.log_path.resolve().as_posix(), script_text)
            self.assertNotIn("__WACHTERFEDER_LOG_PATH__", script_text)

            status.log_path.write_text(
                LOG_PREFIX + '{"schema_version":6,"event":"runtime_start","seq":1}\n',
                encoding="utf-8",
            )
            heartbeat_status = logger_status(game, root=root)
            self.assertTrue(heartbeat_status.runtime_active)

            status = uninstall_logger(game, root=root)
            self.assertFalse(status.installed)
            self.assertFalse(status.up_to_date)
            self.assertFalse(status.runtime_active)
            self.assertFalse((game / "override" / "M_WFLOG.lua").exists())
            self.assertFalse((game / ENGINE_LOG_NAME).exists())

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
            self.assertFalse(status.runtime_active)

    def test_reader_accepts_prefixed_engine_lines_and_ignores_noise(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            log = Path(temporary) / ENGINE_LOG_NAME
            log.write_text("old engine output\n", encoding="utf-8")
            offset = log.stat().st_size
            with log.open("a", encoding="utf-8") as handle:
                handle.write('Some engine prefix ' + LOG_PREFIX + '{"schema_version":6,"event":"runtime_start","seq":1}\n')
                handle.write('ordinary unrelated engine line\n')
                handle.write(LOG_PREFIX + '{"schema_version":6,"event":"damage","seq":2,"damage":5,"lethal_candidate":true}\n')
                handle.write(LOG_PREFIX + '{"schema_version":6,"event":"dialogue_choice","seq":3,"arg1":"2"}\n')

            events, metadata = read_new_events(log, offset)
            self.assertEqual(len(events), 3)
            self.assertEqual(metadata["malformed_lines"], 0)
            summary = summarise_events(events)
            self.assertEqual(summary["damage_total"], 5)
            self.assertEqual(summary["lethal_candidates"], 1)
            self.assertEqual(summary["runtime_starts"], 1)
            self.assertEqual(summary["dialogue_choices"], 1)

    def test_reader_deduplicates_print_and_infinity_log_echoes(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            log = Path(temporary) / ENGINE_LOG_NAME
            line = LOG_PREFIX + '{"schema_version":6,"event":"runtime_start","seq":1}\n'
            log.write_text(line + line, encoding="utf-8")
            events, metadata = read_new_events(log, 0)
            self.assertEqual(len(events), 1)
            self.assertEqual(events[0]["event"], "runtime_start")
            self.assertEqual(metadata["malformed_lines"], 0)

    def test_reader_keeps_legacy_bare_json_support(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            log = Path(temporary) / "combat.jsonl"
            log.write_text('{"event":"damage","damage":3}\nnot-json\n', encoding="utf-8")
            events, metadata = read_new_events(log, 0)
            self.assertEqual(len(events), 1)
            self.assertEqual(events[0]["damage"], 3)
            self.assertEqual(metadata["malformed_lines"], 0)

    def test_real_template_has_visible_diagnostics_and_observes_dialogue(self) -> None:
        template = Path(__file__).resolve().parents[1] / "eeex" / "M_WFLOG.lua.template"
        text = template.read_text(encoding="utf-8")
        self.assertIn(LOGGER_CURRENT_MARKER, text)
        self.assertNotIn("io.open", text)
        self.assertIn("CLUAConsole:new()", text)
        self.assertIn("WF_CONSOLE_SOURCE = source", text)
        self.assertIn('wf_try_prepare_console(console, "constructed_CLUAConsole")', text)
        self.assertIn("console:LogSet(WF_LOG_PATH)", text)
        self.assertIn("console:LogMessages()", text)
        self.assertIn("Infinity_DisplayString", text)
        self.assertIn('wf_diag("Lua-Datei geladen")', text)
        self.assertIn("Dialogwahl erkannt | arg1=", text)
        self.assertIn("EEex initialisiert | Dialog-Hook=", text)
        self.assertIn("Infinity_SelectDialogueOption", text)
        self.assertIn('wf_emit("dialogue_choice"', text)
        self.assertIn('wf_emit("runtime_start"', text)
        self.assertIn("EEex_Sprite_Hook_OnDamageEffectDone", text)
        self.assertIn("EEex_GameState_AddInitializedListener", text)
        self.assertIn("log_ready", text)
        self.assertIn("console_source", text)

    def test_runtime_augmentation_splits_combat_and_dialogue_events(self) -> None:
        delta = {"summary": {"has_changes": False}, "changes": {}, "notes": []}
        events = [
            {"event": "runtime_start", "logger": "V6", "console_source": "constructed_CLUAConsole"},
            {
                "event": "damage",
                "source": "Kivan",
                "target": "Hobgoblin",
                "damage": 9,
                "lethal_candidate": True,
            },
            {"event": "dialogue_choice", "arg1": "2", "selected_character": "Sephira"},
        ]
        _augment_runtime(delta, events, initial_runtime_baseline=False)
        self.assertTrue(delta["summary"]["has_changes"])
        self.assertEqual(delta["summary"]["combat_damage_total"], 9)
        self.assertEqual(delta["summary"]["live_dialogue_choices"], 1)
        self.assertEqual(delta["summary"]["runtime_starts"], 1)
        self.assertEqual(delta["changes"]["combat_log"][0]["source"], "Kivan")
        self.assertEqual(delta["changes"]["live_dialogue_choices"][0]["arg1"], "2")


if __name__ == "__main__":
    unittest.main()
