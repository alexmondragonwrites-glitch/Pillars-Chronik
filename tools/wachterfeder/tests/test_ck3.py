from __future__ import annotations

import io
import os
import tempfile
import time
import unittest
import zipfile
from pathlib import Path

from tools.wachterfeder.ck3 import (
    build_ck3_delta,
    build_ck3_snapshot,
    candidate_ck3_save_roots,
    inspect_ck3_envelope,
    newest_ck3_save,
    normalize_ck3_state,
)


def make_ck3(path: Path, *, meta: bytes = b"1.19.0.4\x00Jarl Haraldr", gamestate: bytes = b"binary") -> None:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("meta", meta)
        archive.writestr("gamestate", gamestate)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"SAV01059521d32f00000000\n" + buffer.getvalue())


def synthetic_state() -> dict:
    return {
        "date": "867.1.1",
        "currently_played_characters": [1],
        "living": {
            "1": {
                "first_name": "Haraldr",
                "dynasty_house": 100,
                "culture": 200,
                "faith": 300,
                "traits": [11, 12],
                "family_data": {"primary_spouse": 2, "child": [3]},
                "landed_data": {"strength": 2200, "succession": [3]},
            },
            "2": {"first_name": "Ragnhildr", "family_data": {"child": [3]}},
            "3": {"first_name": "Eirikr", "family_data": {}},
            "4": {
                "first_name": "Ketill",
                "family_data": {},
                "landed_data": {"strength": 900, "vassal_power_value": 0.3, "is_powerful_vassal": True},
            },
        },
        "landed_titles": {
            "landed_titles": {
                "10": {"key": "d_vikin", "holder": 1},
                "11": {"key": "c_oslo", "holder": 1, "de_facto_liege": 10},
                "12": {"key": "c_foldafylki", "holder": 4, "de_facto_liege": 10},
            }
        },
        "played_character": [{"character": 1, "important_decisions": ["decision_test"]}],
        "triggered_bookmark_events": {"bookmark.1": 1},
        "stories": {"active": {"story-1": {"owner": 1, "type": "sample_story"}}},
        "important_action_manager": {"active": {"action-1": {"actor": 1, "type": "sample_action"}}},
        "character_memory_manager": {"memory-1": {"owner": 1, "type": "wedding", "date": "867.1.2"}},
        "wars": {"active_wars": {"war-1": {"attacker": 1, "defender": 99}}},
    }


class Ck3AdapterTests(unittest.TestCase):
    def test_candidate_root_and_newest_save(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            home = Path(temporary)
            root = home / "Documents" / "Paradox Interactive" / "Crusader Kings III" / "save games"
            older = root / "older.ck3"
            newer = root / "newer.ck3"
            make_ck3(older)
            make_ck3(newer)
            now = time.time()
            os.utime(older, (now - 100, now - 100))
            os.utime(newer, (now, now))
            self.assertIn(root, candidate_ck3_save_roots(home))
            self.assertEqual(newest_ck3_save([root]), newer)

    def test_reads_ck3_envelope_without_touching_save(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            save = Path(temporary) / "test.ck3"
            make_ck3(save, meta=b"meta-data", gamestate=b"game-state" * 20)
            before = save.read_bytes()
            envelope = inspect_ck3_envelope(save)
            self.assertTrue(envelope["compressed"])
            self.assertEqual(set(envelope["members"]), {"meta", "gamestate"})
            self.assertEqual(envelope["meta_size"], len(b"meta-data"))
            self.assertEqual(save.read_bytes(), before)

    def test_normalizes_player_family_vassals_wars_and_events(self) -> None:
        state = normalize_ck3_state(synthetic_state())
        self.assertEqual(state["player"]["name"], "Haraldr")
        self.assertEqual(state["primary_title"]["key"], "d_vikin")
        self.assertEqual(state["family"]["spouses"][0]["name"], "Ragnhildr")
        self.assertEqual(state["family"]["children"][0]["name"], "Eirikr")
        self.assertEqual(state["realm"]["vassal_count"], 1)
        self.assertEqual(state["realm"]["vassals"][0]["name"], "Ketill")
        self.assertEqual(state["wars"][0]["id"], "war-1")
        self.assertIn("bookmark.1", state["events"]["persistent_event_keys"])
        self.assertEqual(state["events"]["player_memories"][0]["type"], "wedding")

    def test_delta_creates_semantic_timeline_candidates(self) -> None:
        old_state = normalize_ck3_state(synthetic_state())
        newer = synthetic_state()
        newer["living"]["5"] = {"first_name": "Astrid", "family_data": {}}
        newer["living"]["1"]["family_data"]["child"].append(5)
        new_state = normalize_ck3_state(newer)
        previous = {"sha256": "old", "state": old_state}
        current = {"sha256": "new", "deep_analysis": True, "fallback_metadata": {}, "state": new_state}
        delta = build_ck3_delta(previous, current)
        events = delta["changes"]["timeline_candidates"]
        self.assertTrue(delta["summary"]["has_changes"])
        self.assertTrue(any(item["type"] == "family_change" and item["change"] == "added" for item in events))

    def test_snapshot_falls_back_cleanly_without_rakaly(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            save = root / "test.ck3"
            make_ck3(save)
            snapshot = build_ck3_snapshot(save, root=root)
            self.assertEqual(snapshot["kind"], "wachterfeder-ck3-snapshot")
            self.assertFalse(snapshot["deep_analysis"])
            self.assertTrue(snapshot["envelope"]["compressed"])
            self.assertFalse(snapshot["rakaly"]["available"])


if __name__ == "__main__":
    unittest.main()
