from __future__ import annotations

import json
import os
import tempfile
import unittest
import zipfile
from pathlib import Path

from tools.wachterfeder import wachterfeder as wf


def int_property(name: str, value: int, type_code: int = 0x0B) -> bytes:
    raw = name.encode("utf-8")
    return (
        wf.PROPERTY_PREFIX
        + bytes([len(raw)])
        + raw
        + wf.VALUE_PREFIX
        + bytes([type_code, 0x01])
        + value.to_bytes(4, "little", signed=True)
    )


def minimal_saveinfo() -> bytes:
    return b'''<Complex name="Root"><Properties>
    <Simple name="PlayerName" value="Serin Ashwyn" />
    <Simple name="MapName" value="AR_0704_Valewood" />
    <Simple name="SceneTitle" value="Talholz" />
    <Simple name="Chapter" value="1" />
    <Simple name="RealtimePlayDurationSeconds" value="10" />
    <Simple name="PlaytimeSeconds" value="20" />
    <Simple name="TrialOfIron" value="False" />
    <Simple name="SaveVersion" value="2" />
    <Simple name="Difficulty" value="Hard" />
    </Properties></Complex>'''


def minimal_mobile_objects() -> bytes:
    player = (
        b"CharacterStats"
        + b"Serin Ashwyn"
        + int_property("Level", 2)
        + int_property("Experience", 1568)
        + int_property("BaseMight", 14)
        + int_property("AthleticsSkill", 3)
        + b"TLN_Ancient_Memory"
        + b"PlayerInventory"
    )
    global_name = b"n_Heodan_State"
    global_entry = (
        b"\x06\x01\x11\x01\x03\x01"
        + bytes([len(global_name)])
        + global_name
        + b"\x06\x01\x11\x01\x06\x01"
        + (5).to_bytes(4, "little", signed=True)
    )
    path = b"data/conversations/07_gilded_vale/test.conversation"
    conversation = (
        b"ConversationManager"
        + b"\x06"
        + (5).to_bytes(4, "little", signed=True)
        + bytes([len(path)])
        + path
        + b"\x09"
        + (6).to_bytes(4, "little", signed=True)
        + b"\x04"
        + (6).to_bytes(4, "little", signed=True)
        + b"System.Collections.BitArray"
        + b"m_array"
        + b"m_length"
        + b"_version"
        + b"\x09"
        + (64).to_bytes(4, "little", signed=True)
        + (8).to_bytes(4, "little", signed=True)
        + (1).to_bytes(4, "little", signed=True)
        + b"\x0f"
        + (64).to_bytes(4, "little", signed=True)
        + (1).to_bytes(4, "little", signed=True)
        + b"\x08"
        + (0b10100101).to_bytes(4, "little", signed=False)
        + b"NodeCyclePositions"
    )
    return player + global_entry + conversation


class WachterfederTests(unittest.TestCase):
    def test_candidate_directory_uses_saved_games(self) -> None:
        home = Path("C:/Users/Alex")
        candidates = wf.candidate_save_directories(home)
        self.assertEqual(
            candidates[0], home / "Saved Games" / "Pillars of Eternity"
        )

    def test_inspects_zip_save_without_modifying_source(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "serin.savegame"
            with zipfile.ZipFile(source, "w") as archive:
                archive.writestr("MobileObjects.save", minimal_mobile_objects())
                archive.writestr("saveinfo.xml", minimal_saveinfo())
                archive.writestr("screenshot.png", b"png-placeholder")

            original = source.read_bytes()
            copied = wf.copy_read_only(source, root / "workspace")
            try:
                snapshot = wf.inspect_savegame(copied)

                self.assertEqual(source.read_bytes(), original)
                self.assertEqual(snapshot.archive_format, "zip")
                self.assertEqual(snapshot.metadata.scene_title, "Talholz")
                self.assertEqual(snapshot.player.level, 2)
                self.assertEqual(snapshot.player.experience, 1568)
                self.assertEqual(snapshot.global_variables["n_Heodan_State"], 5)
                self.assertEqual(
                    snapshot.marked_conversations[0].marked_node_ids,
                    [0, 2, 5, 7],
                )
                self.assertEqual(snapshot.warnings, [])
            finally:
                copied.chmod(0o666)

    def test_writes_machine_readable_snapshot(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "serin.savegame"
            with zipfile.ZipFile(source, "w") as archive:
                archive.writestr("MobileObjects.save", minimal_mobile_objects())
                archive.writestr("saveinfo.xml", minimal_saveinfo())

            snapshot = wf.inspect_savegame(source)
            output = root / "snapshot.json"
            wf.write_snapshot(snapshot, output)
            payload = json.loads(output.read_text(encoding="utf-8"))

            self.assertEqual(payload["schema_version"], 2)
            self.assertEqual(payload["source_name"], "serin.savegame")
            self.assertEqual(
                payload["player"]["serialized_talents"],
                ["TLN_Ancient_Memory"],
            )

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
            self.assertEqual(wf.newest_savegame([root]), newer)

    def test_parse_saveinfo_handles_utf8_bom(self) -> None:
        metadata = wf.parse_saveinfo_xml(b"\xef\xbb\xbf" + minimal_saveinfo())
        self.assertEqual(metadata.player_name, "Serin Ashwyn")
        self.assertFalse(metadata.trial_of_iron)


if __name__ == "__main__":
    unittest.main()
