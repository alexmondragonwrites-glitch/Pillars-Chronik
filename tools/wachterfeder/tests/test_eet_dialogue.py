from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from tools.wachterfeder.eet_dialogue import (
    _split_conversation_event,
    _weidu_relative_output,
    parse_weidu_dialogue,
    resolve_dialogue_event,
)


DIALOGUE = r'''
BEGIN ~KELDDA~

IF ~NumTimesTalkedTo(5)~ THEN BEGIN 0
  SAY ~Ihr seid wieder da.~
  IF ~~ THEN REPLY ~Ich helfe Euch.~
    DO ~SetGlobal("KELDDAQUEST","GLOBAL",2)~ GOTO 1
  IF ~~ THEN REPLY ~Noch nicht.~ GOTO 2
END

IF ~~ THEN BEGIN 1
  SAY ~Dann sei es so.~
  IF ~~ THEN EXIT
END

IF ~~ THEN BEGIN 2
  SAY ~Kommt später wieder.~
  IF ~~ THEN EXIT
END
'''

TORLO_DIALOGUE = r'''
BEGIN ~TORLO~

IF ~~ THEN BEGIN 0
  SAY ~Seid bitte ein bisschen leiser.~
  IF ~~ THEN REPLY ~Fische fangen?~ GOTO 1
  IF ~~ THEN REPLY ~Ich mache so viel Lärm, wie ich will.~ GOTO 2
  IF ~~ THEN REPLY ~Entschuldigung.~ GOTO 3
END

IF ~~ THEN BEGIN 1
  SAY ~Ich habe vorher in der Mine gearbeitet.~
  IF ~~ THEN EXIT
END

IF ~~ THEN BEGIN 2
  SAY ~Hoffentlich fangt Ihr Euch einen Egel ein.~
  IF ~~ THEN EXIT
END

IF ~~ THEN BEGIN 3
  SAY ~Danke.~
  IF ~~ THEN EXIT
END
'''


class EetDialogueTests(unittest.TestCase):
    def test_parse_weidu_dialogue_builds_states_and_replies(self) -> None:
        graph = parse_weidu_dialogue(DIALOGUE)
        self.assertEqual(graph["dialog"], "KELDDA")
        self.assertEqual(graph["state_count"], 3)
        first = graph["states"][0]
        self.assertEqual(first["say"], "Ihr seid wieder da.")
        self.assertEqual(len(first["transitions"]), 2)
        self.assertEqual(first["transitions"][0]["reply"], "Ich helfe Euch.")
        self.assertEqual(first["transitions"][0]["actions"]["globals"][0]["name"], "KELDDAQUEST")

    def test_unique_observable_global_change_confirms_reply(self) -> None:
        graph = parse_weidu_dialogue(DIALOGUE)
        event = {"actor": "keldda", "dialog": "KELDDA", "area": "BG3402", "from": 5, "to": 6}
        delta = {
            "changes": {
                "global_variables": {
                    "KELDDAQUEST": {"from": 1, "to": 2, "change": "changed"}
                },
                "new_journal_entries": [],
            }
        }
        resolved = resolve_dialogue_event(event, graph, delta)
        self.assertEqual(resolved["confidence"], "high")
        self.assertEqual(resolved["confirmed_reply"], "Ich helfe Euch.")
        self.assertEqual(resolved["entry_states"], ["0"])
        self.assertEqual(resolved["candidates"][0]["state"], "0")

    def test_talk_counter_without_unique_effect_does_not_confirm_reply(self) -> None:
        graph = parse_weidu_dialogue(DIALOGUE)
        event = {"actor": "keldda", "dialog": "KELDDA", "area": "BG3402", "from": 5, "to": 6}
        delta = {"changes": {"global_variables": {}, "new_journal_entries": []}}
        resolved = resolve_dialogue_event(event, graph, delta)
        self.assertEqual(resolved["confidence"], "medium")
        self.assertIsNone(resolved["confirmed_reply"])
        self.assertEqual(resolved["candidate_count"], 2)
        self.assertTrue(all(item["state"] == "0" for item in resolved["candidates"]))

    def test_unconditional_first_state_excludes_followup_states(self) -> None:
        graph = parse_weidu_dialogue(TORLO_DIALOGUE)
        event = {"actor": "None", "dialog": "TORLO", "area": "BG4200", "from": 3, "to": 4}
        delta = {"changes": {"global_variables": {}, "new_journal_entries": []}}
        resolved = resolve_dialogue_event(event, graph, delta)
        self.assertEqual(resolved["entry_states"], ["0"])
        self.assertEqual(resolved["candidate_count"], 3)
        self.assertTrue(all(item["state"] == "0" for item in resolved["candidates"]))
        self.assertEqual(
            [item["reply"] for item in resolved["candidates"]],
            ["Fische fangen?", "Ich mache so viel Lärm, wie ich will.", "Entschuldigung."],
        )

    def test_multi_talk_jump_is_split_into_individual_conversations(self) -> None:
        event = {"actor": "None", "dialog": "TORLO", "area": "BG4200", "from": 3, "to": 6}
        split = _split_conversation_event(event)
        self.assertEqual([(item["from"], item["to"]) for item in split], [(3, 4), (4, 5), (5, 6)])
        self.assertEqual([item["sequence_index"] for item in split], [1, 2, 3])
        self.assertTrue(all(item["sequence_count"] == 3 for item in split))
        self.assertTrue(all(item["aggregate_from"] == 3 and item["aggregate_to"] == 6 for item in split))

    def test_weidu_output_is_relative_to_game_root(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            game_root = Path(temporary).resolve()
            out = game_root / ".wachterfeder-eet-dialog-test" / "TORLO.d"
            argument = _weidu_relative_output(out, game_root)
            self.assertFalse(Path(argument).is_absolute())
            self.assertNotIn(":", argument)
            self.assertTrue(argument.endswith("TORLO.d"))


if __name__ == "__main__":
    unittest.main()
