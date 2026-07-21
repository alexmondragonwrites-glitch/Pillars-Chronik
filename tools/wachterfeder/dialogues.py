#!/usr/bin/env python3
"""Read Pillars of Eternity conversation graphs and join them with save snapshots.

This module only reads user-owned local game assets. It does not write extracted
conversation text or game resources into the repository.
"""
from __future__ import annotations

import argparse
import json
import xml.etree.ElementTree as ET
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Iterable, Sequence

XSI_TYPE = "{http://www.w3.org/2001/XMLSchema-instance}type"


class DialogueError(RuntimeError):
    """Expected user-facing dialogue import error."""


@dataclass(frozen=True)
class ScriptCall:
    phase: str
    name: str
    parameters: list[str]


@dataclass(frozen=True)
class DialogueNode:
    node_id: int
    node_type: str
    package_id: int | None
    comments: str
    links_to: list[int]
    is_question: bool | None
    speaker_guid: str | None
    listener_guid: str | None
    conditions: list[ScriptCall]
    scripts: list[ScriptCall]
    text: str | None = None
    female_text: str | None = None


@dataclass(frozen=True)
class ConversationGraph:
    name: str
    path: str
    next_node_id: int | None
    nodes: dict[int, DialogueNode]


@dataclass(frozen=True)
class MarkedConversationReport:
    conversation: str
    source_path: str
    marked_node_ids: list[int]
    missing_node_ids: list[int]
    marked_nodes: list[DialogueNode]
    played_edges: list[tuple[int, int]]
    entry_candidates: list[int]
    exit_candidates: list[int]
    deterministic_edges: list[tuple[int, int]]
    ambiguous_branches: dict[int, list[int]]
    story_scripts: list[ScriptCall]


def _parse_bool(value: str | None) -> bool | None:
    if value is None:
        return None
    normalized = value.strip().casefold()
    if normalized == "true":
        return True
    if normalized == "false":
        return False
    return None


def _parse_int(value: str | None) -> int | None:
    if value is None or not value.strip():
        return None
    try:
        return int(value)
    except ValueError:
        return None


def _script_calls(parent: ET.Element | None, phase: str) -> list[ScriptCall]:
    if parent is None:
        return []
    calls: list[ScriptCall] = []
    for script in parent.findall(".//ScriptCall"):
        name = script.findtext("./Data/FullName") or ""
        params = [element.text or "" for element in script.findall("./Data/Parameters/string")]
        calls.append(ScriptCall(phase=phase, name=name, parameters=params))
    return calls


def parse_stringtable(path: Path) -> dict[int, tuple[str | None, str | None]]:
    """Parse a PoE .stringtable using tolerant tag matching."""
    try:
        root = ET.parse(path).getroot()
    except (ET.ParseError, OSError) as exc:
        raise DialogueError(f"Stringtable konnte nicht gelesen werden: {path}: {exc}") from exc

    result: dict[int, tuple[str | None, str | None]] = {}
    for entry in root.findall(".//Entry"):
        node_id = _parse_int(entry.findtext("ID"))
        if node_id is None:
            continue
        default = entry.findtext("DefaultText")
        female = entry.findtext("FemaleText")
        result[node_id] = (default, female)
    return result


def parse_conversation(
    path: Path,
    strings: dict[int, tuple[str | None, str | None]] | None = None,
) -> ConversationGraph:
    """Parse one .conversation XML graph."""
    try:
        root = ET.parse(path).getroot()
    except (ET.ParseError, OSError) as exc:
        raise DialogueError(f"Dialogdatei konnte nicht gelesen werden: {path}: {exc}") from exc

    nodes: dict[int, DialogueNode] = {}
    nodes_parent = root.find("Nodes")
    if nodes_parent is None:
        raise DialogueError(f"Keine Nodes in Dialogdatei gefunden: {path}")

    strings = strings or {}
    for element in list(nodes_parent):
        node_id = _parse_int(element.findtext("NodeID"))
        if node_id is None:
            continue
        links_parent = element.find("Links")
        links: list[int] = []
        if links_parent is not None:
            for link in links_parent.findall("./FlowChartLink"):
                target = _parse_int(link.findtext("ToNodeID"))
                if target is not None:
                    links.append(target)

        conditions = _script_calls(element.find("Conditionals"), "Condition")
        scripts: list[ScriptCall] = []
        for phase in ("OnEnterScripts", "OnExitScripts", "OnUpdateScripts"):
            scripts.extend(_script_calls(element.find(phase), phase))

        text, female_text = strings.get(node_id, (None, None))
        nodes[node_id] = DialogueNode(
            node_id=node_id,
            node_type=element.attrib.get(XSI_TYPE, element.tag),
            package_id=_parse_int(element.findtext("PackageID")),
            comments=element.findtext("Comments") or "",
            links_to=links,
            is_question=_parse_bool(element.findtext("IsQuestionNode")),
            speaker_guid=element.findtext("SpeakerGuid"),
            listener_guid=element.findtext("ListenerGuid"),
            conditions=conditions,
            scripts=scripts,
            text=text,
            female_text=female_text,
        )

    return ConversationGraph(
        name=path.name,
        path=str(path),
        next_node_id=_parse_int(root.findtext("NextNodeID")),
        nodes=nodes,
    )


def find_conversation(root: Path, save_path: str) -> Path | None:
    """Resolve a saved game conversation path against a local asset folder."""
    relative_parts = Path(save_path.replace("\\", "/")).parts
    candidates = [
        root.joinpath(*relative_parts),
        root / Path(save_path).name,
    ]
    for candidate in candidates:
        if candidate.is_file():
            return candidate
    matches = list(root.rglob(Path(save_path).name))
    return matches[0] if len(matches) == 1 else None


def find_stringtable(root: Path | None, conversation_name: str) -> Path | None:
    if root is None:
        return None
    target = Path(conversation_name).with_suffix(".stringtable").name
    direct = root / target
    if direct.is_file():
        return direct
    matches = list(root.rglob(target))
    return matches[0] if len(matches) == 1 else None


def _is_story_script(script: ScriptCall) -> bool:
    name = script.name.casefold()
    markers = (
        "globalvalue",
        "quest",
        "disposition",
        "reputation",
        "addtoparty",
        "removefromparty",
        "giveitem",
        "removeitem",
        "setishostile",
        "teamrelationship",
        "startcutscene",
        "unlockpresentstoryitem",
        "experience",
        "kill",
        "destroy",
        "teleport",
        "worldmap",
    )
    return any(marker in name for marker in markers)


def build_marked_report(
    graph: ConversationGraph,
    marked_ids: Iterable[int],
) -> MarkedConversationReport:
    marked = sorted(set(int(node_id) for node_id in marked_ids))
    marked_set = set(marked)
    present = [node_id for node_id in marked if node_id in graph.nodes]
    missing = [node_id for node_id in marked if node_id not in graph.nodes]

    edges: list[tuple[int, int]] = []
    incoming: dict[int, set[int]] = {node_id: set() for node_id in present}
    outgoing: dict[int, list[int]] = {node_id: [] for node_id in present}
    for node_id in present:
        node = graph.nodes[node_id]
        for target in node.links_to:
            if target in marked_set and target in graph.nodes:
                edges.append((node_id, target))
                outgoing[node_id].append(target)
                incoming.setdefault(target, set()).add(node_id)

    entry_candidates = sorted(node_id for node_id in present if not incoming.get(node_id))
    exit_candidates = sorted(node_id for node_id in present if not outgoing.get(node_id))
    deterministic = sorted(
        (node_id, targets[0])
        for node_id, targets in outgoing.items()
        if len(targets) == 1
    )
    ambiguous = {
        node_id: sorted(targets)
        for node_id, targets in outgoing.items()
        if len(targets) > 1
    }

    story_scripts: list[ScriptCall] = []
    seen_scripts: set[tuple[str, str, tuple[str, ...]]] = set()
    for node_id in present:
        for script in graph.nodes[node_id].scripts:
            key = (script.phase, script.name, tuple(script.parameters))
            if _is_story_script(script) and key not in seen_scripts:
                seen_scripts.add(key)
                story_scripts.append(script)

    return MarkedConversationReport(
        conversation=graph.name,
        source_path=graph.path,
        marked_node_ids=present,
        missing_node_ids=missing,
        marked_nodes=[graph.nodes[node_id] for node_id in present],
        played_edges=sorted(edges),
        entry_candidates=entry_candidates,
        exit_candidates=exit_candidates,
        deterministic_edges=deterministic,
        ambiguous_branches=ambiguous,
        story_scripts=story_scripts,
    )


def build_dialogue_report(
    snapshot: dict,
    conversation_root: Path,
    stringtable_root: Path | None = None,
) -> dict:
    reports: list[MarkedConversationReport] = []
    unresolved: list[str] = []
    for item in snapshot.get("marked_conversations", []):
        save_path = str(item.get("path", ""))
        conversation_path = find_conversation(conversation_root, save_path)
        if conversation_path is None:
            unresolved.append(save_path)
            continue
        string_path = find_stringtable(stringtable_root, conversation_path.name)
        strings = parse_stringtable(string_path) if string_path else None
        graph = parse_conversation(conversation_path, strings)
        reports.append(build_marked_report(graph, item.get("marked_node_ids", [])))

    return {
        "schema_version": 1,
        "save_sha256": snapshot.get("sha256"),
        "conversation_root": str(conversation_root.resolve()),
        "stringtable_root": str(stringtable_root.resolve()) if stringtable_root else None,
        "matched_conversations": len(reports),
        "unresolved_conversations": unresolved,
        "localized_text_available": stringtable_root is not None,
        "conversations": [asdict(report) for report in reports],
    }


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="PoE-Dialoggraphen mit einem Wächterfeder-Snapshot verbinden"
    )
    parser.add_argument("snapshot", type=Path, help="Wächterfeder-Snapshot JSON")
    parser.add_argument(
        "conversation_root",
        type=Path,
        help="Ordner mit .conversation-Dateien",
    )
    parser.add_argument(
        "--stringtable-root",
        type=Path,
        help="optionaler Ordner mit .stringtable-Dateien",
    )
    parser.add_argument(
        "--output",
        type=Path,
        required=True,
        help="Zielpfad des Dialogreports",
    )
    args = parser.parse_args(argv)

    snapshot = json.loads(args.snapshot.read_text(encoding="utf-8"))
    report = build_dialogue_report(
        snapshot,
        args.conversation_root,
        args.stringtable_root,
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(f"Dialogreport: {args.output.resolve()}")
    print(f"Zugeordnet:  {report['matched_conversations']}")
    print(f"Nicht gefunden: {len(report['unresolved_conversations'])}")
    print(f"Texte: {'ja' if report['localized_text_available'] else 'nein'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
