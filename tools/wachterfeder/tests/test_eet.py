from __future__ import annotations

import json
import struct
import tempfile
import unittest
from pathlib import Path

from tools.wachterfeder.eet import (
    analyse_eet_save,
    build_eet_delta,
    build_eet_snapshot,
    parse_game_v20,
    read_tlk_string,
    resolve_eet_game_assets,
)


def _put_fixed(payload: bytearray, offset: int, size: int, text: str) -> None:
    encoded = text.encode("ascii")[:size]
    payload[offset : offset + size] = encoded.ljust(size, b"\x00")


def make_tlk(path: Path, strings: list[str]) -> None:
    encoded = [item.encode("utf-8") for item in strings]
    entry_count = len(encoded)
    string_offset = 0x12 + entry_count * 0x1A
    payload = bytearray(string_offset + sum(len(item) for item in encoded))
    payload[:4] = b"TLK "
    payload[4:8] = b"V1  "
    struct.pack_into("<H", payload, 0x08, 0)
    struct.pack_into("<I", payload, 0x0A, entry_count)
    struct.pack_into("<I", payload, 0x0E, string_offset)

    cursor = 0
    for index, raw in enumerate(encoded):
        entry = 0x12 + index * 0x1A
        struct.pack_into("<H", payload, entry, 1)
        struct.pack_into("<I", payload, entry + 0x12, cursor)
        struct.pack_into("<I", payload, entry + 0x16, len(raw))
        start = string_offset + cursor
        payload[start : start + len(raw)] = raw
        cursor += len(raw)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(payload)


def make_gam(
    path: Path,
    *,
    gold: int = 123,
    reputation: int = 100,
    globals_: dict[str, int] | None = None,
    party: list[tuple[str, str, str]] | None = None,
    journal: list[tuple[int, int, int, int]] | None = None,
) -> None:
    globals_ = globals_ or {"EET_TEST": 1, "QUEST_STATE": 2}
    party = party or [
        ("CHARBASE", "Serin", "AR1200"),
        ("MINSC", "Minsc", "AR1200"),
    ]
    journal = journal or [(1, 3600, 1, 1)]

    party_offset = 0x100
    globals_offset = party_offset + len(party) * 0x160
    journal_offset = globals_offset + len(globals_) * 0x54
    size = max(0x600, journal_offset + len(journal) * 0x0C + 0x40)
    payload = bytearray(size)
    payload[:4] = b"GAME"
    payload[4:8] = b"V2.0"
    struct.pack_into("<I", payload, 0x08, 900)
    struct.pack_into("<I", payload, 0x18, gold)
    struct.pack_into("<H", payload, 0x1C, 0)
    struct.pack_into("<I", payload, 0x20, party_offset)
    struct.pack_into("<I", payload, 0x24, len(party))
    struct.pack_into("<I", payload, 0x38, globals_offset)
    struct.pack_into("<I", payload, 0x3C, len(globals_))
    _put_fixed(payload, 0x40, 8, "AR0602")
    struct.pack_into("<I", payload, 0x4C, len(journal))
    struct.pack_into("<I", payload, 0x50, journal_offset)
    struct.pack_into("<I", payload, 0x54, reputation)
    _put_fixed(payload, 0x58, 8, "AR1000")
    _put_fixed(payload, 0x8C, 8, "WORLDMAP")
    _put_fixed(payload, 0x94, 8, "BG1")

    for index, (resource, name, area) in enumerate(party):
        start = party_offset + index * 0x160
        struct.pack_into("<H", payload, start + 0x02, index)
        struct.pack_into("<I", payload, start + 0x04, 0x1000 + index * 0x100)
        struct.pack_into("<I", payload, start + 0x08, 0x200)
        _put_fixed(payload, start + 0x0C, 8, resource)
        _put_fixed(payload, start + 0x18, 8, area)
        struct.pack_into("<H", payload, start + 0x20, 100 + index)
        struct.pack_into("<H", payload, start + 0x22, 200 + index)
        _put_fixed(payload, start + 0xC0, 32, name)
        struct.pack_into("<I", payload, start + 0xE0, index + 1)

    for index, (name, value) in enumerate(globals_.items()):
        start = globals_offset + index * 0x54
        _put_fixed(payload, start, 32, name)
        struct.pack_into("<H", payload, start + 0x20, 1)
        struct.pack_into("<i", payload, start + 0x28, value)

    for index, (strref, time_seconds, chapter, section) in enumerate(journal):
        start = journal_offset + index * 0x0C
        struct.pack_into("<I", payload, start, strref)
        struct.pack_into("<I", payload, start + 0x04, time_seconds)
        payload[start + 0x08] = chapter
        payload[start + 0x09] = 1
        payload[start + 0x0A] = section
        payload[start + 0x0B] = 0xFF

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(payload)


class EetAdapterTests(unittest.TestCase):
    def test_reads_tlk_and_game_v20(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            tlk = root / "dialog.tlk"
            gam = root / "BALDUR.GAM"
            make_tlk(tlk, ["Null", "Minsc wurde gefunden."])
            make_gam(gam)

            self.assertEqual(read_tlk_string(tlk, 1), "Minsc wurde gefunden.")
            parsed = parse_game_v20(gam.read_bytes(), tlk)

            self.assertEqual(parsed["party_gold"], 123)
            self.assertEqual(parsed["party_reputation"], 100)
            self.assertEqual(parsed["current_area"], "AR1200")
            self.assertEqual([item["name"] for item in parsed["party"]], ["Serin", "Minsc"])
            self.assertEqual(parsed["global_variables"]["QUEST_STATE"], 2)
            self.assertEqual(parsed["journal_entries"][0]["text"], "Minsc wurde gefunden.")

    def test_delta_contains_only_changed_state(self) -> None:
        previous = {
            "sha256": "old",
            "metadata": {"party_gold": 100, "current_area": "AR1000", "party_count": 1},
            "party": [{"index": 0, "resource": "CHARBASE", "name": "Serin", "current_area": "AR1000"}],
            "global_variables": {"QUEST": 1, "UNCHANGED": 7},
            "journal_entries": [{"strref": 1, "time_seconds": 10, "chapter": 1, "section": 1}],
        }
        current = {
            "sha256": "new",
            "metadata": {"party_gold": 90, "current_area": "AR1200", "party_count": 2},
            "party": [
                {"index": 0, "resource": "CHARBASE", "name": "Serin", "current_area": "AR1200"},
                {"index": 1, "resource": "MINSC", "name": "Minsc", "current_area": "AR1200"},
            ],
            "global_variables": {"QUEST": 2, "UNCHANGED": 7},
            "journal_entries": [
                {"strref": 1, "time_seconds": 10, "chapter": 1, "section": 1},
                {"strref": 2, "time_seconds": 20, "chapter": 1, "section": 1, "text": "Neu"},
            ],
        }

        delta = build_eet_delta(previous, current)

        self.assertFalse(delta["initial_snapshot"])
        self.assertEqual(delta["summary"]["changed_globals"], 1)
        self.assertEqual(delta["changes"]["global_variables"]["QUEST"]["from"], 1)
        self.assertNotIn("UNCHANGED", delta["changes"]["global_variables"])
        self.assertEqual(delta["summary"]["new_journal_entries"], 1)
        self.assertEqual(delta["changes"]["party"]["added"][0]["name"], "Minsc")

    def test_resolves_eet_assets_and_writes_snapshot_delta(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            game = root / "EET"
            save = root / "save" / "000000001-Test"
            (game / "chitin.key").parent.mkdir(parents=True, exist_ok=True)
            (game / "chitin.key").write_bytes(b"KEY ")
            (game / "setup-eet.exe").write_bytes(b"fake")
            tlk = game / "lang" / "de_DE" / "dialog.tlk"
            make_tlk(tlk, ["Null", "Erster Eintrag", "Zweiter Eintrag"])
            make_gam(save / "BALDUR.GAM")

            assets = resolve_eet_game_assets(game, "de_DE")
            self.assertEqual(assets.game_root, game.resolve())
            self.assertIsNotNone(assets.weidu)

            first = analyse_eet_save(save, game_path=game, root=root)
            self.assertTrue(first.initial_snapshot)
            self.assertTrue(first.snapshot_path.is_file())
            self.assertTrue(first.delta_path.is_file())

            make_gam(
                save / "BALDUR.GAM",
                gold=321,
                globals_={"EET_TEST": 1, "QUEST_STATE": 3},
                journal=[(1, 3600, 1, 1), (2, 7200, 1, 1)],
            )
            second = analyse_eet_save(save, game_path=game, root=root)
            self.assertFalse(second.initial_snapshot)
            self.assertEqual(second.changed_globals, 1)
            self.assertEqual(second.new_journal_entries, 1)

            delta = json.loads(second.delta_path.read_text(encoding="utf-8"))
            self.assertEqual(delta["changes"]["global_variables"]["QUEST_STATE"]["to"], 3)
            self.assertEqual(delta["changes"]["new_journal_entries"][0]["text"], "Zweiter Eintrag")

    def test_build_snapshot_does_not_embed_local_paths(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            game = root / "EET"
            save = root / "Save"
            (game / "chitin.key").parent.mkdir(parents=True, exist_ok=True)
            (game / "chitin.key").write_bytes(b"KEY ")
            tlk = game / "lang" / "de_DE" / "dialog.tlk"
            make_tlk(tlk, ["Null", "Eintrag"])
            make_gam(save / "BALDUR.GAM")
            assets = resolve_eet_game_assets(game)

            snapshot = build_eet_snapshot(save, game_assets=assets)
            serialised = json.dumps(snapshot, ensure_ascii=False)
            self.assertNotIn(str(game.resolve()), serialised)
            self.assertEqual(snapshot["local_assets"]["language"], "de_DE")


if __name__ == "__main__":
    unittest.main()
