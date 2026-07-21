import json
import tempfile
import unittest
import zipfile
from pathlib import Path

from tools.wachterfeder.desktop import analyse_savegame


class DesktopPipelineTests(unittest.TestCase):
    def test_analysis_writes_current_and_historical_reports(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            game_root = root / "Pillars of Eternity"
            data_root = game_root / "PillarsOfEternity_Data" / "data"
            (data_root / "conversations").mkdir(parents=True)
            (data_root / "localized" / "de" / "text" / "conversations").mkdir(
                parents=True
            )

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
                result = analyse_savegame(
                    savegame,
                    game_path=game_root,
                    root=root,
                )

                self.assertEqual(result.player_name, "Serin Ashwyn")
                self.assertEqual(result.scene_title, "Testgebiet")
                self.assertEqual(result.matched_conversations, 0)
                self.assertEqual(result.unresolved_conversations, 0)
                self.assertTrue(result.snapshot_path.is_file())
                self.assertTrue(result.report_path.is_file())
                self.assertTrue(result.history_snapshot_path.is_file())
                self.assertTrue(result.history_report_path.is_file())
                self.assertTrue((root / ".wachterfeder" / "config.json").is_file())

                report = json.loads(result.report_path.read_text(encoding="utf-8"))
                self.assertEqual(report["matched_conversations"], 0)
                self.assertEqual(report["unresolved_conversations"], [])
            finally:
                # The production cache copy is deliberately read-only.
                for path in root.rglob("*"):
                    if path.is_file():
                        path.chmod(0o666)


if __name__ == "__main__":
    unittest.main()
