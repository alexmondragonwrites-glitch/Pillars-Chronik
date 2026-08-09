from __future__ import annotations

import json
import struct
import tempfile
import unittest
import zlib
from pathlib import Path

from tools.wachterfeder.eet_session import analyse_session, build_session_delta
from tools.wachterfeder.tests.test_eet import make_gam, make_tlk
from tools.wachterfeder.tests.test_eet_save_resources import make_area


def make_sav(path: Path, area: bytes) -> None:
    name = b"BG3402.are\x00"
    compressed = zlib.compress(area)
    payload = bytearray(b"SAV V1.0")
    payload += struct.pack("<I", len(name)) + name
    payload += struct.pack("<II", len(area), len(compressed)) + compressed
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(payload)


def area_with_talk_count(count: int, variable_value: int) -> bytes:
    area = bytearray(make_area())
    actor_offset = struct.unpack_from("<I", area, 0x54)[0]
    variable_offset = struct.unpack_from("<I", area, 0x88)[0]
    struct.pack_into("<I", area, actor_offset + 0x44, count)
    struct.pack_into("<i", area, variable_offset + 0x28, variable_value)
    return bytes(area)


class EetSessionTests(unittest.TestCase):
    def test_real_session_snapshot_and_delta_use_gam_and_sav(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            game = root / "EET"
            save = root / "Documents" / "Baldur's Gate - Enhanced Edition Trilogy" / "save" / "0001-Test"
            (game / "chitin.key").parent.mkdir(parents=True, exist_ok=True)
            (game / "chitin.key").write_bytes(b"KEY ")
            (game / "setup-eet.exe").write_bytes(b"fake")
            tlk = game / "lang" / "de_DE" / "dialog.tlk"
            make_tlk(tlk, ["Null", "Erster Eintrag", "Zweiter Eintrag"])
            make_gam(save / "BALDUR.GAM", reputation=140, globals_={"CHAPTER": 2, "QUEST": 1})
            make_sav(save / "BALDUR.SAV", area_with_talk_count(2, 1))

            first = analyse_session(save_path=save, game_path=game, root=root)
            self.assertTrue(first.initial_snapshot)
            snapshot = json.loads(first.snapshot_path.read_text(encoding="utf-8"))
            self.assertEqual(snapshot["metadata"]["party_reputation"], 14)
            self.assertEqual(snapshot["metadata"]["chapter"], 2)
            self.assertEqual(snapshot["save_resources"]["resource_count"], 1)
            self.assertIn("BALDUR.SAV", snapshot["source_files"])

            make_gam(
                save / "BALDUR.GAM",
                reputation=150,
                globals_={"CHAPTER": 2, "QUEST": 2},
                journal=[(1, 3600, 1, 1), (2, 7200, 2, 1)],
            )
            make_sav(save / "BALDUR.SAV", area_with_talk_count(5, 4))
            second = analyse_session(save_path=save, game_path=game, root=root)
            self.assertFalse(second.initial_snapshot)
            self.assertEqual(second.changed_globals, 1)
            self.assertEqual(second.changed_area_variables, 1)
            self.assertEqual(second.new_journal_entries, 1)
            self.assertEqual(second.npc_conversations, 1)

            delta = json.loads(second.delta_path.read_text(encoding="utf-8"))
            self.assertEqual(delta["current_state"]["party_reputation"], 15)
            self.assertEqual(delta["changes"]["global_variables"]["QUEST"]["to"], 2)
            self.assertEqual(delta["changes"]["area_variables"]["BG3402.QUEST_STAGE"]["to"], 4)
            self.assertEqual(delta["changes"]["npc_conversations"][0]["from"], 2)
            self.assertEqual(delta["changes"]["npc_conversations"][0]["to"], 5)

    def test_initial_delta_does_not_report_old_talk_counters_as_new(self) -> None:
        current = {
            "sha256": "new",
            "metadata": {},
            "party": [],
            "global_variables": {},
            "journal_entries": [],
            "save_resources": {
                "actor_talks": {"BG3402": [{"name": "Keldath", "talk_count": 5}]},
                "area_variables": {},
            },
        }
        delta = build_session_delta(None, current)
        self.assertTrue(delta["initial_snapshot"])
        self.assertEqual(delta["summary"]["npc_conversations"], 0)


if __name__ == "__main__":
    unittest.main()
