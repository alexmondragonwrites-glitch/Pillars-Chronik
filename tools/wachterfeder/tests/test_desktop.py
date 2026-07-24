import json
import tempfile
import unittest
import zipfile
from pathlib import Path

from tools.wachterfeder.desktop import analyse_savegame


class DesktopPipelineTests(unittest.TestCase):
    def test_analysis_writes_current_snapshot_and_compact_delta(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            game_root = root / "Pillars of Eternity"
            data_root = game_root / "PillarsOfEternity_Data" / "data"
            (data_root / "conversations").mkdir(parents=True)
            (
                data_root
                / "localized"
                / "de"
                / "text"
                / "conversations"
            ).mkdir(parents=True)

            savegame = root / "quicksave.savegame"
            saveinfo = """<?xml version="1.0" encoding="utf-8"?>
<Root>
  <Simple name="PlayerName" value="Serin Ashwyn" />
  <Simple name="MapName" value="AR_TEST" />
  <Simple name="SceneTitle" value="Testgebiet" />
  <Simple name="Difficulty" value="Hard" />
</Root>
"""
            with zipfile.ZipFile(savegame, "w") as archive:
                archive.writestr("saveinfo.xml", saveinfo)
                archive.writestr("MobileObjects.save", b"")

            try:
                first = analyse_savegame(
                    savegame,
                    game_path=game_root,
                    root=root,
                )

                self.assertEqual(first.player_name, "Serin Ashwyn")
                self.assertEqual(first.scene_title, "Testgebiet")
                self.assertEqual(first.matched_conversations, 0)
                self.assertEqual(first.unresolved_conversations, 0)
                self.assertTrue(first.initial_snapshot)
                self.assertTrue(first.snapshot_path.is_file())
                self.assertTrue(first.delta_path.is_file())
                self.assertTrue(first.history_delta_path.is_file())
                self.assertTrue(first.state_report_path.is_file())
                self.assertTrue(
                    (root / ".wachterfeder" / "config.json").is_file()
                )

                delta = json.loads(
                    first.delta_path.read_text(encoding="utf-8")
                )
                self.assertTrue(delta["initial_snapshot"])
                self.assertEqual(
                    delta["dialogue_changes"]["new_conversations"],
                    [],
                )

                second = analyse_savegame(
                    savegame,
                    game_path=game_root,
                    root=root,
                )
                self.assertFalse(second.initial_snapshot)
                self.assertFalse(second.has_changes)
                second_delta = json.loads(
                    second.delta_path.read_text(encoding="utf-8")
                )
                self.assertFalse(second_delta["summary"]["has_changes"])
            finally:
                # The production cache copy is deliberately read-only.
                for path in root.rglob("*"):
                    if path.is_file():
                        path.chmod(0o666)


if __name__ == "__main__":
    unittest.main()
