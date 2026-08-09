from __future__ import annotations

import unittest

from tools.wachterfeder.eet_session_runtime import _party_runtime_changes, _save_telemetry


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

    def test_v7_save_telemetry_detects_boot_and_dialogue_choice(self) -> None:
        previous = {
            "global_variables": {
                "WF_RUNTIME_VERSION": 7,
                "WF_RUNTIME_BOOT_SEQ": 1,
                "WF_DIALOG_HOOK": 1,
                "WF_DIALOG_SEQ": 4,
            }
        }
        current = {
            "global_variables": {
                "WF_RUNTIME_VERSION": 7,
                "WF_RUNTIME_BOOT_SEQ": 2,
                "WF_DIALOG_HOOK": 1,
                "WF_DIALOG_SEQ": 5,
                "WF_DIALOG_ARGC": 2,
                "WF_DLG_A1_NUM": 1,
                "WF_DLG_A1": 3,
                "WF_DLG_A2_NUM": 1,
                "WF_DLG_A2": 7,
                "WF_DLG_A3_NUM": 0,
                "WF_DLG_A3": 0,
                "WF_DLG_A4_NUM": 0,
                "WF_DLG_A4": 0,
                "WF_DIALOG_TICKS": 12345,
            }
        }
        report, events = _save_telemetry(previous, current)
        self.assertTrue(report["runtime_active"])
        self.assertTrue(report["booted_since_previous"])
        self.assertTrue(report["dialog_hook_available"])
        self.assertEqual(report["dialog_choices_since_previous"], 1)
        self.assertEqual([event["event"] for event in events], ["runtime_start", "dialogue_choice"])
        choice = events[1]
        self.assertEqual(choice["arg1"], 3)
        self.assertEqual(choice["arg2"], 7)
        self.assertIsNone(choice["arg3"])

    def test_v7_save_telemetry_marks_last_choice_when_multiple_happened(self) -> None:
        previous = {"global_variables": {"WF_DIALOG_SEQ": 2}}
        current = {
            "global_variables": {
                "WF_RUNTIME_VERSION": 7,
                "WF_RUNTIME_BOOT_SEQ": 1,
                "WF_DIALOG_HOOK": 1,
                "WF_DIALOG_SEQ": 5,
                "WF_DIALOG_ARGC": 1,
                "WF_DLG_A1_NUM": 1,
                "WF_DLG_A1": 9,
            }
        }
        report, events = _save_telemetry(previous, current)
        self.assertEqual(report["dialog_choices_since_previous"], 3)
        choice = [event for event in events if event["event"] == "dialogue_choice"][0]
        self.assertTrue(choice["last_choice_only"])
        self.assertEqual(choice["choices_since_previous"], 3)


if __name__ == "__main__":
    unittest.main()
