from __future__ import annotations

import copy
import tempfile
import unittest
from pathlib import Path

from tools.wachterfeder.ck3_enhanced import (
    build_ck3_delta,
    clean_ck3_text,
    find_rakaly,
    normalize_ck3_state,
    remember_rakaly,
)
from tools.wachterfeder.ck3_enhanced_runtime import build_ck3_delta as build_migration_safe_delta
from tools.wachterfeder.tests.test_ck3 import synthetic_state


class Ck3EnhancedTests(unittest.TestCase):
    def test_cleans_ck3_control_codes_from_war_name(self) -> None:
        raw = (
            "\x15ONCLICK:TITLE,6336 \x15TOOLTIP:LANDED_TITLE,6336 \x15L; "
            "Masandaranisch\x15!\x15!\x15!er Anspruch auf "
            "\x15ONCLICK:TITLE,6335 \x15TOOLTIP:LANDED_TITLE,6335 \x15L; "
            "Emirat von Tabaristan\x15!\x15!\x15!"
        )
        self.assertEqual(
            clean_ck3_text(raw),
            "Masandaranischer Anspruch auf Emirat von Tabaristan",
        )

    def test_nested_memory_database_yields_real_memory_not_wrapper(self) -> None:
        raw = synthetic_state()
        raw["character_memory_manager"] = {
            "database": {
                "1": {
                    "memory-42": {
                        "owner": 1,
                        "type": "wedding",
                        "date": "867.1.2",
                    }
                }
            }
        }
        state = normalize_ck3_state(raw)
        memories = state["events"]["player_memories"]
        self.assertEqual(len(memories), 1)
        self.assertEqual(memories[0]["id"], "memory-42")
        self.assertEqual(memories[0]["type"], "wedding")
        self.assertNotEqual(memories[0]["id"], "database")

    def test_adds_succession_and_vassal_watch_analysis(self) -> None:
        state = normalize_ck3_state(synthetic_state())
        succession = state["analysis"]["succession"]
        self.assertEqual(succession["primary_heir"]["id"], "3")
        self.assertEqual(succession["primary_heir"]["name"], "Eirikr")
        watch = state["analysis"]["vassal_watchlist"]
        self.assertEqual(watch[0]["name"], "Ketill")
        self.assertEqual(watch[0]["attention"], "medium")

    def test_delta_is_compact_and_builds_semantic_timeline(self) -> None:
        old_raw = synthetic_state()
        old_state = normalize_ck3_state(old_raw)

        new_raw = copy.deepcopy(old_raw)
        new_raw["date"] = "868.2.1"
        new_raw["living"]["5"] = {
            "first_name": "Astrid",
            "birth": "868.1.20",
            "family_data": {},
        }
        new_raw["living"]["1"]["family_data"]["child"].append(5)
        new_raw["living"]["1"]["landed_data"]["succession"] = [5, 3]
        new_raw["wars"]["active_wars"]["war-2"] = {
            "attacker": 1,
            "defender": 98,
            "name": "Testkrieg",
        }
        new_state = normalize_ck3_state(new_raw)

        previous = {"sha256": "old", "state": old_state}
        current = {
            "sha256": "new",
            "deep_analysis": True,
            "fallback_metadata": {},
            "state": new_state,
        }
        delta = build_ck3_delta(previous, current)
        types = {item["type"] for item in delta["changes"]["timeline_candidates"]}

        self.assertTrue(delta["summary"]["compact_delta"])
        self.assertIn("child_added", types)
        self.assertIn("succession_changed", types)
        self.assertIn("war_observed_started", types)
        self.assertNotIn("state", delta["changes"])
        self.assertIn("headline_state", delta["changes"])
        self.assertEqual(delta["current_state"]["primary_heir_name"], "Astrid")

    def test_schema_migration_does_not_invent_timeline_events(self) -> None:
        old_raw = synthetic_state()
        old_state = normalize_ck3_state(old_raw)

        new_raw = copy.deepcopy(old_raw)
        new_raw["character_memory_manager"] = {
            "database": {
                "1": {
                    "memory-42": {
                        "owner": 1,
                        "type": "wedding",
                        "date": "867.1.2",
                    }
                }
            }
        }
        new_state = normalize_ck3_state(new_raw)

        previous = {"schema_version": 1, "sha256": "old", "state": old_state}
        current = {
            "schema_version": 2,
            "sha256": "new",
            "deep_analysis": True,
            "fallback_metadata": {},
            "state": new_state,
        }
        delta = build_migration_safe_delta(previous, current)

        self.assertEqual(delta["summary"]["schema_migration"], {"from": 1, "to": 2})
        self.assertEqual(delta["summary"]["headline_state_changes"], 0)
        self.assertEqual(delta["summary"]["timeline_candidates"], 0)
        self.assertEqual(delta["changes"]["headline_state"], {})
        self.assertEqual(delta["changes"]["timeline_candidates"], [])
        self.assertFalse(delta["initial_snapshot"])

    def test_remembers_selected_rakaly_locally(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            rakaly = root / "rakaly.exe"
            rakaly.write_bytes(b"stub")
            remember_rakaly(root, rakaly)
            self.assertEqual(find_rakaly(root=root), rakaly.resolve())
            self.assertTrue((root / ".wachterfeder" / "ck3" / "config.json").is_file())


if __name__ == "__main__":
    unittest.main()
