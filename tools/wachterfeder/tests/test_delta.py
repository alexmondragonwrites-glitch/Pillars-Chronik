from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from tools.wachterfeder.delta import build_analysis_delta, store_analysis_artifacts


class DeltaTests(unittest.TestCase):
    def test_delta_contains_only_new_nodes_and_changed_values(self) -> None:
        previous_snapshot = {
            "sha256": "old",
            "metadata": {"scene_title": "Goldtal", "map_name": "AR_0705"},
            "player": {"level": 3, "experience": 3213},
            "global_variables": {"b_found_perly": 0, "unchanged": 1},
            "marked_conversations": [
                {
                    "path": "data/conversations/perly.conversation",
                    "marked_node_ids": [1],
                }
            ],
        }
        current_snapshot = {
            "sha256": "new",
            "metadata": {"scene_title": "Höhle", "map_name": "AR_0723"},
            "player": {"level": 3, "experience": 3789},
            "global_variables": {"b_found_perly": 1, "unchanged": 1},
            "marked_conversations": [
                {
                    "path": "data/conversations/perly.conversation",
                    "marked_node_ids": [1, 2],
                }
            ],
        }
        previous_report = {
            "matched_conversations": 1,
            "unresolved_conversations": [],
            "conversations": [
                {
                    "conversation": "perly.conversation",
                    "source_package": "data",
                    "marked_node_ids": [1],
                    "marked_nodes": [{"node_id": 1, "text": "Alt"}],
                    "played_edges": [],
                    "deterministic_edges": [],
                    "ambiguous_branches": {},
                    "story_scripts": [],
                }
            ],
        }
        current_report = {
            "matched_conversations": 1,
            "unresolved_conversations": [],
            "conversations": [
                {
                    "conversation": "perly.conversation",
                    "source_package": "data",
                    "marked_node_ids": [1, 2],
                    "marked_nodes": [
                        {"node_id": 1, "text": "Alt"},
                        {"node_id": 2, "text": "Neu"},
                    ],
                    "played_edges": [[1, 2]],
                    "deterministic_edges": [[1, 2]],
                    "ambiguous_branches": {},
                    "story_scripts": [],
                }
            ],
        }

        delta = build_analysis_delta(
            previous_snapshot,
            current_snapshot,
            previous_report,
            current_report,
            language="de",
        )

        self.assertFalse(delta["initial_snapshot"])
        self.assertEqual(delta["summary"]["changed_globals"], 1)
        self.assertEqual(delta["summary"]["new_dialogue_nodes"], 1)
        dialogue = delta["dialogue_changes"]["conversations"][0]
        self.assertEqual(dialogue["new_node_ids"], [2])
        self.assertEqual(
            [node["node_id"] for node in dialogue["new_nodes"]],
            [2],
        )
        self.assertNotIn("source_path", dialogue)
        self.assertNotIn("stringtable_path", dialogue)

    def test_store_migrates_legacy_report_and_writes_delta_history(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            local_root = Path(temporary) / ".wachterfeder"
            local_root.mkdir(parents=True)
            previous_snapshot = {
                "sha256": "old",
                "metadata": {},
                "player": {},
                "global_variables": {},
                "marked_conversations": [],
            }
            previous_report = {
                "matched_conversations": 0,
                "unresolved_conversations": [],
                "conversations": [],
            }
            (local_root / "serin.snapshot.json").write_text(
                json.dumps(previous_snapshot),
                encoding="utf-8",
            )
            legacy = local_root / "serin-dialoge-de.json"
            legacy.write_text(json.dumps(previous_report), encoding="utf-8")
            current_snapshot = {**previous_snapshot, "sha256": "new"}
            current_report = dict(previous_report)

            artifacts = store_analysis_artifacts(
                current_snapshot,
                current_report,
                local_root=local_root,
                history_key="test",
                language="de",
            )

            self.assertTrue(artifacts.snapshot_path.is_file())
            self.assertTrue(artifacts.delta_path.is_file())
            self.assertTrue(artifacts.history_delta_path.is_file())
            self.assertTrue(artifacts.state_report_path.is_file())
            self.assertFalse(legacy.exists())
            delta = json.loads(
                artifacts.delta_path.read_text(encoding="utf-8")
            )
            self.assertFalse(delta["initial_snapshot"])
            self.assertEqual(delta["current_save_sha256"], "new")


if __name__ == "__main__":
    unittest.main()
