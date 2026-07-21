from __future__ import annotations

import json
import os
import tempfile
import unittest
import zipfile
from pathlib import Path

from tools.wachterfeder.wachterfeder import (
    candidate_save_directories,
    copy_read_only,
    inspect_savegame,
    newest_savegame,
    write_snapshot,
)


class WachterfederTests(unittest.TestCase):
    def test_candidate_directory_uses_saved_games(self) -> None:
        home = Path("C:/Users/Alex")
        candidates = candidate_save_directories(home)
        self.assertEqual(
            candidates[0], home / "Saved Games" / "Pillars of Eternity"
        )

    def test_inspects_zip_save_without_modifying_source(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "serin.savegame"
            with zipfile.ZipFile(source, "w") as archive:
                archive.writestr("MobileObjects.save", b"binary-placeholder")
                archive.writestr("Screenshot.png", b"png-placeholder")

            original = source.read_bytes()
            copied = copy_read_only(source, root / "workspace")
            snapshot = inspect_savegame(copied)

            self.assertEqual(source.read_bytes(), original)
            self.assertEqual(snapshot.archive_format, "zip")
            self.assertEqual(len(snapshot.archive_members), 2)
            self.assertTrue(
                any(
                    member.name == "MobileObjects.save" and member.important
                    for member in snapshot.archive_members
                )
            )
            self.assertEqual(snapshot.warnings, [])

    def test_writes_machine_readable_snapshot(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "serin.savegame"
            with zipfile.ZipFile(source, "w") as archive:
                archive.writestr("MobileObjects.save", b"data")

            snapshot = inspect_savegame(source)
            output = root / "snapshot.json"
            write_snapshot(snapshot, output)
            payload = json.loads(output.read_text(encoding="utf-8"))

            self.assertEqual(payload["schema_version"], 1)
            self.assertEqual(payload["source_name"], "serin.savegame")
            self.assertEqual(payload["archive_format"], "zip")

    def test_finds_newest_save_in_numeric_subfolder(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            older = root / "old.savegame"
            newer_dir = root / "123456789"
            newer_dir.mkdir()
            newer = newer_dir / "new.savegame"
            older.write_bytes(b"old")
            newer.write_bytes(b"new")
            older.touch()
            newer.touch()
            older_mtime = older.stat().st_mtime - 10
            os.utime(older, (older_mtime, older_mtime))

            self.assertEqual(newest_savegame([root]), newer)


if __name__ == "__main__":
    unittest.main()
