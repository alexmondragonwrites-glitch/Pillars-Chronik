from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from tools.wachterfeder.dialogues import (
    build_dialogue_report,
    build_marked_report,
    parse_conversation,
    parse_stringtable,
)

CONVERSATION = '''<?xml version="1.0" encoding="utf-8"?>
<ConversationData xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance">
  <NextNodeID>4</NextNodeID>
  <Nodes>
    <FlowChartNode xsi:type="TalkNode"><NodeID>0</NodeID><PackageID>1</PackageID><Links><FlowChartLink><ToNodeID>1</ToNodeID></FlowChartLink></Links><Comments/><IsQuestionNode>true</IsQuestionNode><SpeakerGuid>npc</SpeakerGuid><ListenerGuid>player</ListenerGuid><Conditionals><Components/></Conditionals><OnEnterScripts/><OnExitScripts/><OnUpdateScripts/></FlowChartNode>
    <FlowChartNode xsi:type="PlayerResponseNode"><NodeID>1</NodeID><PackageID>1</PackageID><Links><FlowChartLink><ToNodeID>2</ToNodeID></FlowChartLink><FlowChartLink><ToNodeID>3</ToNodeID></FlowChartLink></Links><Comments/><IsQuestionNode>false</IsQuestionNode><Conditionals><Components/></Conditionals><OnEnterScripts><ScriptCall><Data><FullName>Void DispositionAddPoints(Axis, Strength)</FullName><Parameters><string>Benevolent</string><string>Minor</string></Parameters></Data></ScriptCall></OnEnterScripts><OnExitScripts/><OnUpdateScripts/></FlowChartNode>
    <FlowChartNode xsi:type="TalkNode"><NodeID>2</NodeID><PackageID>1</PackageID><Links/><Comments/><IsQuestionNode>false</IsQuestionNode><Conditionals><Components/></Conditionals><OnEnterScripts/><OnExitScripts/><OnUpdateScripts/></FlowChartNode>
    <FlowChartNode xsi:type="TalkNode"><NodeID>3</NodeID><PackageID>1</PackageID><Links/><Comments/><IsQuestionNode>false</IsQuestionNode><Conditionals><Components/></Conditionals><OnEnterScripts/><OnExitScripts/><OnUpdateScripts/></FlowChartNode>
  </Nodes>
</ConversationData>'''

STRINGTABLE = '''<?xml version="1.0" encoding="utf-8"?>
<StringTableFile><Entries><Entry><ID>0</ID><DefaultText>Hallo.</DefaultText><FemaleText/></Entry><Entry><ID>1</ID><DefaultText>Ich helfe.</DefaultText><FemaleText/></Entry></Entries></StringTableFile>'''


class DialogueTests(unittest.TestCase):
    def test_parses_graph_and_strings(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            conversation = root / "sample.conversation"
            strings = root / "sample.stringtable"
            conversation.write_text(CONVERSATION, encoding="utf-8")
            strings.write_text(STRINGTABLE, encoding="utf-8")

            graph = parse_conversation(
                conversation,
                parse_stringtable(strings),
            )

            self.assertEqual(graph.nodes[0].links_to, [1])
            self.assertEqual(graph.nodes[0].text, "Hallo.")
            self.assertEqual(graph.nodes[1].node_type, "PlayerResponseNode")

    def test_reports_deterministic_and_ambiguous_edges(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            conversation = Path(tmp) / "sample.conversation"
            conversation.write_text(CONVERSATION, encoding="utf-8")
            graph = parse_conversation(conversation)

            report = build_marked_report(graph, [0, 1, 2, 3, 99])

            self.assertIn((0, 1), report.deterministic_edges)
            self.assertEqual(report.ambiguous_branches[1], [2, 3])
            self.assertEqual(report.missing_node_ids, [99])
            self.assertTrue(
                any("DispositionAddPoints" in script.name for script in report.story_scripts)
            )

    def test_joins_snapshot_by_basename(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            conversation = root / "07_gilded_vale" / "sample.conversation"
            conversation.parent.mkdir()
            conversation.write_text(CONVERSATION, encoding="utf-8")
            snapshot = {
                "sha256": "abc",
                "marked_conversations": [
                    {
                        "path": "data/conversations/07_gilded_vale/sample.conversation",
                        "marked_node_ids": [0, 1],
                    }
                ],
            }

            report = build_dialogue_report(snapshot, root)

            self.assertEqual(report["matched_conversations"], 1)
            self.assertEqual(
                report["conversations"][0]["marked_node_ids"],
                [0, 1],
            )


if __name__ == "__main__":
    unittest.main()
