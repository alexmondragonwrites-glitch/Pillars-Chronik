from __future__ import annotations

import unittest

from tools.wachterfeder.eet_session_runtime import _party_runtime_changes


class EetSessionRuntimeTests(unittest.TestCase):
    def test_party_hp_and_talk_changes_are_detected(self) -> None:
        previous = {
            "party": [
                {
                    "name": "Branwen",
                    "talk_count": 1,
                    "current_area": "BG3402",
                    "resource": "*RANWE",
                    "character": {
                        "death_variable": "BRANWEN",
                        "dialog": "BRANWJ",
                        "hit_points": {"current": 14, "maximum": 23},
                    },
                }
            ]
        }
        current = {
            "party": [
                {
                    "name": "Branwen",
                    "talk_count": 2,
                    "current_area": "BG4200",
                    "resource": "*RANWE",
                    "character": {
                        "death_variable": "BRANWEN",
                        "dialog": "BRANWJ",
                        "hit_points": {"current": 18, "maximum": 23},
                    },
                }
            ]
        }
        hp, talks = _party_runtime_changes(previous, current)
        self.assertEqual(hp["BRANWEN"]["delta"], 4)
        self.assertEqual(talks[0]["dialog"], "BRANWJ")
        self.assertEqual(talks[0]["from"], 1)
        self.assertEqual(talks[0]["to"], 2)

    def test_none_death_variable_falls_back_to_resource_identity(self) -> None:
        previous = {
            "party": [
                {
                    "name": "Sephira",
                    "talk_count": 0,
                    "resource": "*HARBASE",
                    "character": {
                        "death_variable": "None",
                        "dialog": "",
                        "hit_points": {"current": 14, "maximum": 14},
                    },
                }
            ]
        }
        current = {
            "party": [
                {
                    "name": "Sephira",
                    "talk_count": 0,
                    "resource": "*HARBASE",
                    "character": {
                        "death_variable": "None",
                        "dialog": "",
                        "hit_points": {"current": 10, "maximum": 14},
                    },
                }
            ]
        }
        hp, talks = _party_runtime_changes(previous, current)
        self.assertEqual(hp["*HARBASE"]["delta"], -4)
        self.assertEqual(talks, [])


if __name__ == "__main__":
    unittest.main()
