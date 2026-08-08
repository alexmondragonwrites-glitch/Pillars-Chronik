from __future__ import annotations

import unittest

from tools.wachterfeder.eet_dialogue import parse_weidu_dialogue, resolve_dialogue_event


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
        self.assertEqual(resolved["candidates"][0]["state"], "0")

    def test_talk_counter_without_unique_effect_does_not_confirm_reply(self) -> None:
        graph = parse_weidu_dialogue(DIALOGUE)
        event = {"actor": "keldda", "dialog": "KELDDA", "area": "BG3402", "from": 5, "to": 6}
        delta = {"changes": {"global_variables": {}, "new_journal_entries": []}}
        resolved = resolve_dialogue_event(event, graph, delta)
        self.assertEqual(resolved["confidence"], "medium")
        self.assertIsNone(resolved["confirmed_reply"])


if __name__ == "__main__":
    unittest.main()
