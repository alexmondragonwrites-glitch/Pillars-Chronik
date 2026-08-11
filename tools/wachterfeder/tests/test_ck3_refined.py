from __future__ import annotations

import copy
import unittest

from tools.wachterfeder.ck3_refined import normalize_ck3_state
from tools.wachterfeder.tests.test_ck3 import synthetic_state


class Ck3RefinedTests(unittest.TestCase):
    def real_like_state(self) -> dict:
        raw = copy.deepcopy(synthetic_state())
        raw["date"] = "875.2.13"
        raw["living"]["1"]["faith"] = 67
        raw["living"]["1"]["landed_data"]["vassal_power_value"] = 1000
        raw["living"]["4"]["faith"] = 67
        raw["living"]["4"]["landed_data"]["succession"] = [1]

        raw["living"]["99"] = {
            "first_name": "Muhammad",
            "faith": 67,
            "family_data": {},
            "landed_data": {"strength": 3000, "vassal_power_value": 2500},
        }
        raw["landed_titles"]["landed_titles"]["10"]["de_facto_liege"] = 20
        raw["landed_titles"]["landed_titles"]["20"] = {
            "key": "d_tabaristan",
            "holder": 99,
        }

        raw["living"]["5"] = {
            "first_name": "Nawid_Test",
            "faith": 76,
            "family_data": {},
            "landed_data": {"strength": 100, "vassal_power_value": 80},
        }
        raw["landed_titles"]["landed_titles"]["13"] = {
            "key": "b_lahij",
            "holder": 5,
            "de_facto_liege": 10,
        }

        raw["wars"]["active_wars"]["war-1"] = {
            "name": "Anspruch auf Tabaristan",
            "start_date": "873.11.13",
            "attacker": {
                "participants": [{"character": 1, "casualties": 520}],
                "casualties": {"attrition": 195},
            },
            "defender": {
                "participants": [{"character": 99, "casualties": 176}],
                "casualties": {"attrition": 248},
            },
            "casus_belli": {
                "type": "claim_cb",
                "attacker": 1,
                "defender": 99,
                "claimant": 1,
                "targeted_titles": [20],
            },
        }
        raw["character_memory_manager"] = {
            "database": {
                "1": {
                    "memory-7": {
                        "type": "war_won",
                        "end_date": "1198.2.23",
                        "participants": {"loser": 99, "winner": 1},
                    }
                }
            }
        }
        return raw

    def test_future_memory_end_date_is_not_claimed_as_event_date(self) -> None:
        state = normalize_ck3_state(self.real_like_state())
        memory = state["events"]["player_memories"][0]
        temporal = memory["temporal_evidence"]
        self.assertEqual(memory["type"], "war_won")
        self.assertEqual(temporal["raw_end_date"], "1198.2.23")
        self.assertTrue(temporal["raw_end_date_is_future"])
        self.assertEqual(
            temporal["event_date_status"],
            "im Save nicht eindeutig als Ereignisdatum belegt",
        )
        self.assertEqual(memory["participant_details"]["winner"]["name"], "Haraldr")
        self.assertEqual(memory["participant_details"]["loser"]["name"], "Muhammad")

    def test_war_against_liege_is_resolved(self) -> None:
        state = normalize_ck3_state(self.real_like_state())
        context = state["analysis"]["wars"][0]
        self.assertEqual(context["role"], "attacker")
        self.assertEqual(context["opponent"]["name"], "Muhammad")
        self.assertTrue(context["against_liege"])
        self.assertEqual(context["casus_belli_type"], "claim_cb")
        self.assertEqual(context["target_titles"][0]["key"], "d_tabaristan")
        self.assertEqual(context["player_side_observation"]["recorded_participant_casualties"], 520)
        self.assertEqual(context["player_side_observation"]["recorded_attrition"], 195)
        self.assertTrue(state["analysis"]["liege_context"]["at_war_with_liege"])

    def test_vassal_succession_is_highlighted_without_overpromising(self) -> None:
        state = normalize_ck3_state(self.real_like_state())
        rows = state["analysis"]["inheritance_opportunities"]
        ketill = next(item for item in rows if item["vassal_name"] == "Ketill")
        self.assertEqual(ketill["player_succession_position"], 1)
        self.assertIn("keine Garantie", ketill["note"])

    def test_faith_difference_alone_does_not_raise_attention(self) -> None:
        state = normalize_ck3_state(self.real_like_state())
        row = next(item for item in state["analysis"]["vassal_watchlist"] if item["id"] == "5")
        self.assertEqual(row["display_name"], "Nawid Test")
        self.assertEqual(row["attention"], "low")
        self.assertIn("abweichender Glaube", row["context_flags"])
        self.assertNotIn("abweichender Glaube", row["reasons"])


if __name__ == "__main__":
    unittest.main()
