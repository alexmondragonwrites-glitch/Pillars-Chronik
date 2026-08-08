from __future__ import annotations

import struct
import unittest
import zlib

from tools.wachterfeder.eet_save_resources import (
    actor_talk_delta,
    parse_area_actor_talks,
    parse_area_variables,
    parse_cre_summary,
    parse_sav_v1,
)


def _put_text(buf: bytearray, offset: int, size: int, text: str) -> None:
    raw = text.encode("ascii")[:size]
    buf[offset : offset + size] = raw + b"\x00" * (size - len(raw))


def make_cre(name_ref: int = 42, death: str = "TESTNPC", dialog: str = "TESTDLG") -> bytes:
    cre = bytearray(0x300)
    cre[:8] = b"CRE V1.0"
    struct.pack_into("<i", cre, 0x08, name_ref)
    struct.pack_into("<i", cre, 0x0C, name_ref)
    struct.pack_into("<I", cre, 0x18, 1234)
    struct.pack_into("<h", cre, 0x24, 7)
    struct.pack_into("<h", cre, 0x26, 11)
    _put_text(cre, 0x34, 8, "TESTM")
    _put_text(cre, 0x3C, 8, "TESTL")
    cre[0x234] = 3
    cre[0x237] = 2
    cre[0x238] = 11
    cre[0x23A] = 18
    cre[0x23B] = 10
    cre[0x23C] = 18
    cre[0x23D] = 16
    cre[0x23E] = 18
    struct.pack_into("<I", cre, 0x244, 0x02000000)
    cre[0x272] = 3
    cre[0x273] = 1
    cre[0x27B] = 0x32
    _put_text(cre, 0x280, 32, death)
    _put_text(cre, 0x2CC, 8, dialog)
    return bytes(cre)


def make_area() -> bytes:
    area = bytearray(0x800)
    area[:8] = b"AREAV1.0"
    actor_offset = 0x100
    variable_offset = 0x500
    struct.pack_into("<I", area, 0x54, actor_offset)
    struct.pack_into("<H", area, 0x58, 1)
    struct.pack_into("<I", area, 0x88, variable_offset)
    struct.pack_into("<I", area, 0x8C, 1)

    _put_text(area, actor_offset, 32, "testnpc")
    struct.pack_into("<I", area, actor_offset + 0x44, 3)
    cre = make_cre()
    cre_offset = 0x180
    struct.pack_into("<I", area, actor_offset + 0x88, cre_offset)
    struct.pack_into("<I", area, actor_offset + 0x8C, len(cre))
    area[cre_offset : cre_offset + len(cre)] = cre

    _put_text(area, variable_offset, 32, "QUEST_STAGE")
    struct.pack_into("<i", area, variable_offset + 0x28, 4)
    return bytes(area)


class EetSaveResourceTests(unittest.TestCase):
    def test_cre_summary_reads_character_progression(self) -> None:
        summary = parse_cre_summary(make_cre(), resolve_strref=lambda ref: "Sephira" if ref == 42 else None)
        self.assertEqual(summary["name"], "Sephira")
        self.assertEqual(summary["experience"], 1234)
        self.assertEqual(summary["levels"], [3, 0, 0])
        self.assertEqual(summary["class_name"], "Mage")
        self.assertEqual(summary["race_name"], "Half-Elf")
        self.assertEqual(summary["alignment_name"], "Chaotic Neutral")
        self.assertEqual(summary["kit_name"], "Enchanter")
        self.assertEqual(summary["dialog"], "TESTDLG")

    def test_sav_archive_and_area_state(self) -> None:
        area = make_area()
        name = b"BG3402.are\x00"
        compressed = zlib.compress(area)
        sav = bytearray(b"SAV V1.0")
        sav += struct.pack("<I", len(name)) + name
        sav += struct.pack("<II", len(area), len(compressed)) + compressed

        resources = parse_sav_v1(bytes(sav))
        self.assertIn("BG3402.are", resources)
        self.assertEqual(parse_area_variables(resources["BG3402.are"])["QUEST_STAGE"], 4)
        actors = parse_area_actor_talks(resources["BG3402.are"], resolve_strref=lambda _: "Keldath")
        self.assertEqual(actors[0]["name"], "testnpc")
        self.assertEqual(actors[0]["talk_count"], 3)
        self.assertEqual(actors[0]["dialog"], "TESTDLG")

    def test_actor_talk_delta_only_reports_increases(self) -> None:
        previous = {"actor_talks": {"BG3402": [{"name": "Keldath", "death_variable": "KELDDA", "talk_count": 2}]}}
        current = {"actor_talks": {"BG3402": [{"name": "Keldath", "death_variable": "KELDDA", "dialog": "KELDDA", "talk_count": 5}]}}
        delta = actor_talk_delta(previous, current)
        self.assertEqual(delta, [{"area": "BG3402", "actor": "Keldath", "dialog": "KELDDA", "from": 2, "to": 5}])


if __name__ == "__main__":
    unittest.main()
