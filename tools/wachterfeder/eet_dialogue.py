#!/usr/bin/env python3
"""Read-only EET dialogue resolver backed by the locally installed WeiDU.

Wächterfeder never ships or commits game dialogue assets. For a dialogue that
actually changed between two saves, this module asks the user's own modded EET
installation to decompile the effective DLG into temporary WeiDU D text, parses
its finite-state transitions, and compares observable transition effects with
the save delta.

Only a unique transition with matching evidence may expose a confirmed reply.
Ambiguous paths remain candidates with an explicit confidence level.
"""
from __future__ import annotations

import re
import subprocess
import tempfile
from pathlib import Path
from typing import Any, Mapping

try:
    from tools.wachterfeder.eet import EetError, resolve_eet_game_assets
except ModuleNotFoundError:  # direct execution
    from eet import EetError, resolve_eet_game_assets

JsonObject = dict[str, Any]

_STATE_RE = re.compile(
    r"(?ms)^\s*IF\s+~(?P<trigger>.*?)~\s+THEN\s+BEGIN\s+(?P<label>\S+)\s*(?P<body>.*?)(?=^\s*END\s*$)"
)
_TRANSITION_RE = re.compile(r"(?ms)^\s*IF\s+~(?P<trigger>.*?)~\s+THEN\s+(?P<body>.*?)(?=^\s*IF\s+~|\Z)")
_SET_GLOBAL_RE = re.compile(
    r"SetGlobal\(\s*\"(?P<name>[^\"]+)\"\s*,\s*\"(?P<scope>[^\"]+)\"\s*,\s*(?P<value>-?\d+)\s*\)",
    re.IGNORECASE,
)
_INCREMENT_GLOBAL_RE = re.compile(
    r"IncrementGlobal\(\s*\"(?P<name>[^\"]+)\"\s*,\s*\"(?P<scope>[^\"]+)\"\s*,\s*(?P<value>-?\d+)\s*\)",
    re.IGNORECASE,
)
_TALK_TRIGGER_RE = re.compile(r"NumTimesTalkedTo\(\s*(?P<count>\d+)\s*\)", re.IGNORECASE)


def _clean_text(text: str | None) -> str | None:
    if text is None:
        return None
    return re.sub(r"\s+", " ", text).strip()


def _literal_after(keyword: str, text: str) -> str | None:
    match = re.search(rf"\b{re.escape(keyword)}\b\s+~(?P<value>.*?)~", text, re.IGNORECASE | re.DOTALL)
    return _clean_text(match.group("value")) if match else None


def _all_journals(text: str) -> list[JsonObject]:
    result: list[JsonObject] = []
    pattern = re.compile(
        r"\b(?P<kind>SOLVED_JOURNAL|UNSOLVED_JOURNAL|JOURNAL)\b\s+~(?P<value>.*?)~",
        re.IGNORECASE | re.DOTALL,
    )
    for match in pattern.finditer(text):
        result.append({"kind": match.group("kind").upper(), "text": _clean_text(match.group("value"))})
    return result


def _transition_target(text: str) -> JsonObject:
    extern = re.search(r"\bEXTERN\s+(?P<dialog>\S+)\s+(?P<state>\S+)", text, re.IGNORECASE)
    if extern:
        return {"kind": "extern", "dialog": extern.group("dialog"), "state": extern.group("state")}
    goto = re.search(r"\bGOTO\s+(?P<state>\S+)", text, re.IGNORECASE)
    if goto:
        return {"kind": "goto", "state": goto.group("state")}
    if re.search(r"\bEXIT\b", text, re.IGNORECASE):
        return {"kind": "exit"}
    return {"kind": "unknown"}


def _observable_actions(text: str) -> JsonObject:
    globals_: list[JsonObject] = []
    for match in _SET_GLOBAL_RE.finditer(text):
        globals_.append(
            {
                "op": "set",
                "name": match.group("name"),
                "scope": match.group("scope").upper(),
                "value": int(match.group("value")),
            }
        )
    for match in _INCREMENT_GLOBAL_RE.finditer(text):
        globals_.append(
            {
                "op": "increment",
                "name": match.group("name"),
                "scope": match.group("scope").upper(),
                "value": int(match.group("value")),
            }
        )
    return {"globals": globals_, "journals": _all_journals(text)}


def parse_weidu_dialogue(text: str, *, dialog: str | None = None) -> JsonObject:
    """Parse the subset of decompiled WeiDU D needed for chronology inference."""
    begin = re.search(r"\bBEGIN\s+~?(?P<dialog>[A-Za-z0-9_#.-]+)~?", text, re.IGNORECASE)
    dialog_name = (dialog or (begin.group("dialog") if begin else "")).upper()
    states: list[JsonObject] = []
    for state_match in _STATE_RE.finditer(text):
        body = state_match.group("body")
        transitions: list[JsonObject] = []
        for index, transition_match in enumerate(_TRANSITION_RE.finditer(body)):
            transition_body = transition_match.group("body").strip()
            transitions.append(
                {
                    "index": index,
                    "trigger": _clean_text(transition_match.group("trigger")) or "",
                    "reply": _literal_after("REPLY", transition_body),
                    "actions": _observable_actions(transition_body),
                    "target": _transition_target(transition_body),
                }
            )
        states.append(
            {
                "label": state_match.group("label"),
                "trigger": _clean_text(state_match.group("trigger")) or "",
                "say": _literal_after("SAY", body),
                "transitions": transitions,
            }
        )
    return {"dialog": dialog_name, "state_count": len(states), "states": states}


def _weidu_relative_output(output: Path, game_root: Path) -> str:
    """Return a WeiDU-safe relative output path.

    Current Windows WeiDU builds can interpret an absolute ``C:\\...`` output
    path as ``./C:/...`` and fail with ``Unix.EINVAL``. Keeping the temporary
    directory inside the game root lets us pass a plain relative path while the
    files are still ephemeral and removed immediately after parsing.
    """
    try:
        relative = output.resolve().relative_to(game_root.resolve())
    except ValueError as exc:
        raise EetError("Temporäre WeiDU-Ausgabe liegt nicht innerhalb des Spielordners.") from exc
    return relative.as_posix()


def decompile_dialogue(
    dialog: str,
    *,
    game_path: Path,
    language: str = "de_DE",
    timeout: int = 30,
) -> JsonObject:
    """Decompile one effective DLG through local WeiDU without retaining raw D text."""
    resref = re.sub(r"[^A-Za-z0-9_#.-]", "", str(dialog or "")).strip()
    if not resref:
        raise EetError("Leerer Dialog-ResRef kann nicht aufgelöst werden.")
    assets = resolve_eet_game_assets(game_path, language)
    if assets.weidu is None:
        raise EetError("WeiDU wurde im EET-Spielordner nicht gefunden.")

    # WeiDU's Windows path handling for --out does not reliably accept drive-
    # qualified absolute paths. Create the temporary directory below the game
    # root and pass only a relative POSIX-style path to WeiDU.
    with tempfile.TemporaryDirectory(prefix=".wachterfeder-eet-dialog-", dir=assets.game_root) as temporary:
        out = Path(temporary) / f"{resref}.d"
        out_argument = _weidu_relative_output(out, assets.game_root)
        command = [
            str(assets.weidu),
            "--noautoupdate",
            "--nofrom",
            f"{resref}.dlg",
            "--out",
            out_argument,
            "--text",
        ]
        completed = subprocess.run(
            command,
            cwd=assets.game_root,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout,
            check=False,
        )
        if completed.returncode != 0 or not out.is_file():
            detail = (completed.stderr or completed.stdout or "WeiDU lieferte keine D-Datei.").strip()
            raise EetError(f"Dialog {resref} konnte nicht dekompiliert werden: {detail[-600:]}")
        return parse_weidu_dialogue(out.read_text(encoding="utf-8", errors="replace"), dialog=resref)


def _changed_globals(delta: Mapping[str, Any]) -> Mapping[str, Any]:
    changes = delta.get("changes", {})
    if not isinstance(changes, Mapping):
        return {}
    globals_ = changes.get("global_variables", {})
    return globals_ if isinstance(globals_, Mapping) else {}


def _new_journal_texts(delta: Mapping[str, Any]) -> list[str]:
    changes = delta.get("changes", {})
    if not isinstance(changes, Mapping):
        return []
    entries = changes.get("new_journal_entries", [])
    if not isinstance(entries, list):
        return []
    return [
        _clean_text(str(item.get("text") or "")) or ""
        for item in entries
        if isinstance(item, Mapping) and item.get("text")
    ]


def _score_transition(
    state: Mapping[str, Any],
    transition: Mapping[str, Any],
    *,
    event: Mapping[str, Any],
    changed_globals: Mapping[str, Any],
    new_journals: list[str],
) -> JsonObject:
    score = 0
    evidence: list[JsonObject] = []
    conflicts: list[JsonObject] = []
    actions = transition.get("actions", {}) if isinstance(transition.get("actions"), Mapping) else {}
    for action in actions.get("globals", []) if isinstance(actions.get("globals"), list) else []:
        if not isinstance(action, Mapping) or str(action.get("scope", "")).upper() != "GLOBAL":
            continue
        name = str(action.get("name") or "")
        change = changed_globals.get(name)
        if not isinstance(change, Mapping):
            continue
        after = change.get("to")
        if action.get("op") == "set":
            if after == action.get("value"):
                score += 4
                evidence.append({"kind": "global", "name": name, "to": after})
            else:
                conflicts.append({"kind": "global", "name": name, "expected": action.get("value"), "observed": after})
        elif action.get("op") == "increment":
            before = change.get("from")
            try:
                matches = int(after) - int(before) == int(action.get("value"))
            except (TypeError, ValueError):
                matches = False
            if matches:
                score += 4
                evidence.append({"kind": "global_increment", "name": name, "by": action.get("value")})

    for journal in actions.get("journals", []) if isinstance(actions.get("journals"), list) else []:
        if not isinstance(journal, Mapping):
            continue
        wanted = _clean_text(str(journal.get("text") or "")) or ""
        if wanted and wanted in new_journals:
            score += 4
            evidence.append({"kind": "journal", "text": wanted})

    talk_match = _TALK_TRIGGER_RE.search(str(state.get("trigger") or ""))
    if talk_match:
        expected = int(talk_match.group("count"))
        try:
            observed = int(event.get("from", -1))
        except (TypeError, ValueError):
            observed = -1
        if expected == observed:
            score += 2
            evidence.append({"kind": "talk_count", "value": observed})

    return {
        "state": state.get("label"),
        "state_text": state.get("say"),
        "transition": transition.get("index"),
        "reply": transition.get("reply"),
        "target": transition.get("target"),
        "score": score,
        "evidence": evidence,
        "conflicts": conflicts,
    }


def resolve_dialogue_event(event: Mapping[str, Any], graph: Mapping[str, Any], delta: Mapping[str, Any]) -> JsonObject:
    changed_globals = _changed_globals(delta)
    new_journals = _new_journal_texts(delta)
    candidates: list[JsonObject] = []
    for state in graph.get("states", []) if isinstance(graph.get("states"), list) else []:
        if not isinstance(state, Mapping):
            continue
        for transition in state.get("transitions", []) if isinstance(state.get("transitions"), list) else []:
            if not isinstance(transition, Mapping):
                continue
            candidate = _score_transition(
                state,
                transition,
                event=event,
                changed_globals=changed_globals,
                new_journals=new_journals,
            )
            if not candidate["conflicts"]:
                candidates.append(candidate)

    candidates.sort(key=lambda item: int(item.get("score", 0)), reverse=True)
    top_score = int(candidates[0].get("score", 0)) if candidates else 0
    top = [item for item in candidates if int(item.get("score", 0)) == top_score]
    if top_score >= 4 and len(top) == 1:
        confidence = "high"
        confirmed_reply = top[0].get("reply")
    elif top_score >= 2:
        confidence = "medium"
        confirmed_reply = None
    else:
        confidence = "low"
        confirmed_reply = None

    return {
        "actor": event.get("actor"),
        "area": event.get("area"),
        "dialog": event.get("dialog") or graph.get("dialog"),
        "from": event.get("from"),
        "to": event.get("to"),
        "confidence": confidence,
        "confirmed_reply": confirmed_reply,
        "candidate_count": len(top) if top_score > 0 else len(candidates),
        "candidates": top[:5] if top_score > 0 else candidates[:5],
    }


def resolve_delta_dialogues(
    delta: Mapping[str, Any],
    *,
    game_path: Path,
    language: str = "de_DE",
) -> JsonObject:
    """Resolve changed persistent NPC/party talks against local effective DLGs."""
    changes = delta.get("changes", {})
    if not isinstance(changes, Mapping):
        changes = {}
    events: list[Mapping[str, Any]] = []
    for key in ("npc_conversations", "party_conversations"):
        value = changes.get(key, [])
        if isinstance(value, list):
            events.extend(item for item in value if isinstance(item, Mapping) and item.get("dialog"))

    assets = resolve_eet_game_assets(game_path, language)
    report: JsonObject = {
        "weidu_available": assets.weidu is not None,
        "events_considered": len(events),
        "high_confidence": 0,
        "medium_confidence": 0,
        "low_confidence": 0,
        "resolved": [],
        "errors": [],
    }
    if assets.weidu is None:
        return report

    cache: dict[str, JsonObject] = {}
    for event in events:
        dialog = str(event.get("dialog") or "").upper()
        try:
            if dialog not in cache:
                cache[dialog] = decompile_dialogue(dialog, game_path=assets.game_root, language=language)
            resolved = resolve_dialogue_event(event, cache[dialog], delta)
        except (OSError, subprocess.SubprocessError, EetError) as exc:
            report["errors"].append({"actor": event.get("actor"), "dialog": dialog, "error": str(exc)})
            continue
        confidence = str(resolved.get("confidence") or "low")
        report[f"{confidence}_confidence"] = int(report.get(f"{confidence}_confidence", 0)) + 1
        report["resolved"].append(resolved)
    return report
