from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from tools.wachterfeder.expansion_assets import (
    build_expanded_dialogue_report,
    discover_asset_packages,
)


def conversation_xml(node_id: int) -> str:
    return f'''<?xml version="1.0" encoding="utf-8"?>
<ConversationData xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance">
  <NextNodeID>{node_id + 1}</NextNodeID>
  <Nodes>
    <FlowChartNode xsi:type="TalkNode">
      <NodeID>{node_id}</NodeID><PackageID>1</PackageID><Links/><Comments/>
      <IsQuestionNode>false</IsQuestionNode><SpeakerGuid>npc</SpeakerGuid>
      <ListenerGuid>player</ListenerGuid><Conditionals/><OnEnterScripts/>
      <OnExitScripts/><OnUpdateScripts/>
    </FlowChartNode>
  </Nodes>
</ConversationData>'''


def stringtable_xml(node_id: int, text: str) -> str:
    return f'''<?xml version="1.0" encoding="utf-8"?>
<StringTableFile><Entries><Entry><ID>{node_id}</ID>
<DefaultText>{text}</DefaultText><FemaleText/></Entry></Entries></StringTableFile>'''


class ExpansionAssetTests(unittest.TestCase):
    def _make_package(
        self,
        pillars_data: Path,
        package_name: str,
        area: str,
        node_id: int,
        text: str,
    ) -> tuple[Path, Path]:
        data_root = pillars_data / package_name
        conversation = data_root / "conversations" / area / "sample.conversation"
        stringtable = (
            data_root
            / "localized"
            / "de"
            / "text"
            / "conversations"
            / area
            / "sample.stringtable"
        )
        conversation.parent.mkdir(parents=True, exist_ok=True)
        stringtable.parent.mkdir(parents=True, exist_ok=True)
        conversation.write_text(conversation_xml(node_id), encoding="utf-8")
        stringtable.write_text(stringtable_xml(node_id, text), encoding="utf-8")
        return conversation, stringtable

    def test_discovers_all_installed_expansion_packages(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            game_root = Path(temporary) / "Pillars of Eternity"
            pillars_data = game_root / "PillarsOfEternity_Data"
            self._make_package(pillars_data, "data", "07_gilded_vale", 1, "Basis")
            self._make_package(pillars_data, "data_expansion1", "px1_test", 2, "Eins")
            self._make_package(pillars_data, "data_expansion2", "px2_test", 3, "Zwei")
            self._make_package(pillars_data, "data_expansion4", "px4_test", 4, "Vier")

            _, packages = discover_asset_packages(game_root, "de")

            self.assertEqual(
                [package.name for package in packages],
                ["data", "data_expansion1", "data_expansion2", "data_expansion4"],
            )
            self.assertTrue(all(package.stringtable_root for package in packages))

    def test_uses_matching_expansion_graph_and_stringtable(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            game_root = Path(temporary) / "Pillars of Eternity"
            pillars_data = game_root / "PillarsOfEternity_Data"
            self._make_package(pillars_data, "data", "shared", 1, "Falsches Paket")
            expansion_graph, expansion_strings = self._make_package(
                pillars_data,
                "data_expansion2",
                "shared",
                42,
                "Die Weiße Mark",
            )

            _, packages = discover_asset_packages(game_root, "de")
            snapshot = {
                "sha256": "abc",
                "marked_conversations": [
                    {
                        "path": "data_expansion2/conversations/shared/sample.conversation",
                        "marked_node_ids": [42],
                    }
                ],
            }

            report = build_expanded_dialogue_report(snapshot, packages)

            self.assertEqual(report["matched_conversations"], 1)
            self.assertEqual(report["unresolved_conversations"], [])
            dialogue = report["conversations"][0]
            self.assertEqual(dialogue["source_package"], "data_expansion2")
            self.assertEqual(Path(dialogue["source_path"]).resolve(), expansion_graph.resolve())
            self.assertEqual(
                Path(dialogue["stringtable_path"]).resolve(),
                expansion_strings.resolve(),
            )
            self.assertEqual(dialogue["marked_nodes"][0]["text"], "Die Weiße Mark")


if __name__ == "__main__":
    unittest.main()
