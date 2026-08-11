#!/usr/bin/env python3
"""Enhanced four-game Wächterfeder UI with the CK3 research improvements."""
from __future__ import annotations

import json
import tkinter as tk

try:
    import tools.wachterfeder.multi_gui4 as ui
    from tools.wachterfeder.ck3_enhanced import analyse_ck3_save, find_rakaly
except ModuleNotFoundError:  # Direct execution from tools/wachterfeder.
    import multi_gui4 as ui
    from ck3_enhanced import analyse_ck3_save, find_rakaly

# The inherited CK3 tab resolves these names from the multi_gui4 module at run
# time. Swap in the enhanced adapter without duplicating the whole four-tab UI.
ui.analyse_ck3_save = analyse_ck3_save
ui.find_rakaly = find_rakaly


class EnhancedFourGameWachterfederApp(ui.FourGameWachterfederApp):
    def _ck3_done(self, result) -> None:
        self.ck3_result = result
        self.ck3_run.configure(state="normal", text="CK3 erneut auswerten")
        depth = "Tiefe Analyse aktiv" if result.deep_analysis else "Metadatenmodus (Rakaly noch nicht gefunden)"

        current = {}
        try:
            payload = json.loads(result.delta_path.read_text(encoding="utf-8"))
            if isinstance(payload, dict) and isinstance(payload.get("current_state"), dict):
                current = payload["current_state"]
        except (OSError, json.JSONDecodeError):
            pass

        heir = current.get("primary_heir_name") or current.get("primary_heir_id")
        top = current.get("top_vassal_watch")
        top_line = ""
        if isinstance(top, dict) and top.get("name"):
            ratio = top.get("power_score_ratio")
            ratio_text = f" · Machtwert-Anteil ca. {float(ratio) * 100:.1f}%" if isinstance(ratio, (int, float)) else ""
            top_line = f"\nVasallen-Watch: {top['name']} · {top.get('attention', 'unbekannt')}{ratio_text}"

        self.ck3_status.set(
            f"Fertig: {result.save_file.name}\n"
            f"{ui.delta_state(result.initial_snapshot, result.has_changes)}\n"
            f"{depth}\n\n"
            f"Version: {result.game_version or 'unbekannt'}\n"
            f"Herrscher: {result.player_name or 'noch nicht tief aufgelöst'}\n"
            f"Primärtitel: {result.primary_title or 'noch nicht tief aufgelöst'}\n"
            f"Primärerbe: {heir or 'noch nicht aufgelöst'}\n"
            f"Familienmitglieder im Beobachtungsring: {result.family_members}\n"
            f"Direkte Vasallen: {result.vassals}"
            f"{top_line}\n"
            f"Timeline-/Event-Kandidaten Δ: {result.event_changes}\n\n"
            f"Snapshot: {result.snapshot_path}\nDelta: {result.delta_path}\n\n"
            "Rakaly wird nach erfolgreicher Auswahl lokal gemerkt. Eventregel: Exakte Optionen nur, "
            "wenn Save oder späterer Runtime-Logger sie eindeutig belegt."
        )


def main() -> int:
    window = tk.Tk()
    EnhancedFourGameWachterfederApp(window)
    window.mainloop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
