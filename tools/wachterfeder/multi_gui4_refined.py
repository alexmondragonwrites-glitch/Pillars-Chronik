#!/usr/bin/env python3
"""Four-game Wächterfeder UI with CK3 real-save refinements."""
from __future__ import annotations

import json
import tkinter as tk

try:
    import tools.wachterfeder.multi_gui4 as base_ui
    import tools.wachterfeder.multi_gui4_enhanced as enhanced_ui
    from tools.wachterfeder.ck3_refined import analyse_ck3_save, find_rakaly
except ModuleNotFoundError:  # Direct execution from tools/wachterfeder.
    import multi_gui4 as base_ui
    import multi_gui4_enhanced as enhanced_ui
    from ck3_refined import analyse_ck3_save, find_rakaly

# The inherited _run_ck3 resolves these globals from multi_gui4 at runtime.
base_ui.analyse_ck3_save = analyse_ck3_save
base_ui.find_rakaly = find_rakaly


class RefinedFourGameWachterfederApp(enhanced_ui.EnhancedFourGameWachterfederApp):
    def _ck3_done(self, result) -> None:
        super()._ck3_done(result)
        try:
            snapshot = json.loads(result.snapshot_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return
        state = snapshot.get("state") if isinstance(snapshot, dict) else None
        analysis = state.get("analysis") if isinstance(state, dict) else None
        if not isinstance(analysis, dict):
            return

        lines: list[str] = []
        liege = analysis.get("liege_context")
        if isinstance(liege, dict) and liege.get("liege_name"):
            ratio = liege.get("player_strength_ratio_to_liege")
            ratio_text = f" · eigener gespeicherter strength-Wert {float(ratio) * 100:.1f}% des Lehnsherrn" if isinstance(ratio, (int, float)) else ""
            war_text = " · aktuell im Krieg gegeneinander" if liege.get("at_war_with_liege") else ""
            lines.append(f"Lehnsherr: {liege['liege_name']}{ratio_text}{war_text}")

        inheritance = analysis.get("inheritance_opportunities")
        if isinstance(inheritance, list) and inheritance:
            names = [str(item.get("vassal_name")) for item in inheritance if isinstance(item, dict) and item.get("vassal_name")]
            if names:
                lines.append("Aktuell in Vasallen-Nachfolge: " + ", ".join(names[:4]))

        wars = analysis.get("wars")
        if isinstance(wars, list) and wars:
            first = wars[0] if isinstance(wars[0], dict) else None
            if first:
                opponent = first.get("opponent")
                opponent_name = opponent.get("name") if isinstance(opponent, dict) else None
                role = first.get("role") or "Teilnehmer"
                if opponent_name:
                    lines.append(f"Aktiver Krieg: {role} gegen {opponent_name} · {first.get('name') or 'unbenannt'}")

        if lines:
            self.ck3_status.set(self.ck3_status.get() + "\n\nStrategischer Kontext:\n" + "\n".join(lines))


def main() -> int:
    window = tk.Tk()
    RefinedFourGameWachterfederApp(window)
    window.mainloop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
