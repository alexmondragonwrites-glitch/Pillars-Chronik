from __future__ import annotations

import json
import os
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest import mock

from tools.wachterfeder.rogue_trader import (
    RogueTraderError,
    analyse_rogue_trader_save,
    build_rogue_trader_snapshot,
    candidate_rogue_trader_save_roots,
    newest_rogue_trader_save,
)


def make_save(path: Path, *, quest_state: int = 1, area: str = "Bridge") -> Path:
    with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr(
            "header.json",
            json.dumps(
                {
                    "SaveName": "Test Run",
                    "AreaName": area,
                    "Version": "1.0",
                    "UnrelatedSecret": "do-not-copy-me",
                }
            ),
        )
        archive.writestr(
            "player.json",
            json.dumps(
                {
                    "m_QuestState": {"MainQuest": quest_state},
                    "Conviction": {"IconoclastLevel": 2},
                    "Party": [{"CompanionName": "Abelard", "Level": 4}],
                    "Inventory": {"Credits": 99},
                }
            ),
        )
        archive.writestr("header.png", b"not-a-real-png")
    return path


class RogueTraderAdapterTests(unittest.TestCase):
    def test_candidate_paths_include_release_folder(self) -> None:
        with mock.patch.dict(os.environ, {"USERPROFILE": r"C:\Users\Alex"}, clear=False):
            paths = candidate_rogue_trader_save_roots(Path(r"C:\Users\Alex"))
        rendered = [str(path) for path in paths]
        self.assertTrue(any("Warhammer 40000 Rogue Trader" in item for item in rendered))
        self.assertTrue(all(item.endswith("Saved Games") for item in rendered))

    def test_snapshot_is_compact_probe(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            save = make_save(Path(temporary) / "run.zks")
            snapshot = build_rogue_trader_snapshot(save)

            self.assertEqual(snapshot["kind"], "wachterfeder-rogue-trader-snapshot")
            self.assertEqual(snapshot["archive"]["member_count"], 3)
            self.assertEqual(snapshot["archive"]["json_document_count"], 2)
            self.assertIn("player.json::m_QuestState.MainQuest", snapshot["signals"]["items"])
            self.assertIn("header.json::AreaName", snapshot["signals"]["items"])

            serialised = json.dumps(snapshot, ensure_ascii=False)
            self.assertNotIn("do-not-copy-me", serialised)
            self.assertIn("UnrelatedSecret", serialised)

    def test_analyse_writes_current_snapshot_and_delta(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            save = make_save(root / "run.zks", quest_state=1)
            first = analyse_rogue_trader_save(save, root=root)

            self.assertTrue(first.initial_snapshot)
            self.assertTrue(first.snapshot_path.is_file())
            self.assertTrue(first.delta_path.is_file())

            make_save(save, quest_state=2, area="Footfall")
            second = analyse_rogue_trader_save(save, root=root)
            self.assertFalse(second.initial_snapshot)
            self.assertGreaterEqual(second.changed_signals, 2)

            delta = json.loads(second.delta_path.read_text(encoding="utf-8"))
            quest = delta["changes"]["signals"]["player.json::m_QuestState.MainQuest"]
            self.assertEqual(quest["from"]["value"], 1)
            self.assertEqual(quest["to"]["value"], 2)
            self.assertEqual(
                len(list((root / ".wachterfeder" / "rogue-trader").glob("*.snapshot.json"))),
                1,
            )

    def test_corrupt_save_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            save = Path(temporary) / "broken.zks"
            save.write_bytes(b"not a zip")
            with self.assertRaises(RogueTraderError):
                build_rogue_trader_snapshot(save)

    def test_newest_save(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            first = make_save(root / "a.zks")
            second = make_save(root / "b.zks")
            os.utime(first, (100, 100))
            os.utime(second, (200, 200))
            self.assertEqual(newest_rogue_trader_save([root]), second)


if __name__ == "__main__":
    unittest.main()
