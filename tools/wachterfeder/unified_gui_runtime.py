#!/usr/bin/env python3
"""Unified Wächterfeder UI with optional EEex runtime and dialogue analysis."""
from __future__ import annotations

import json
import sys
import tkinter as tk
from pathlib import Path
from tkinter import messagebox, ttk

# When Python executes this file by path (the normal Windows .bat launcher),
# sys.path starts in tools/wachterfeder instead of at the repository root.
REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
if str(REPOSITORY_ROOT) not in sys.path:
    sys.path.insert(0, str(REPOSITORY_ROOT))

import tools.wachterfeder.unified_gui as gui_module
from tools.wachterfeder.eet import EetError
from tools.wachterfeder.eet_combat_logger import install_logger, logger_status, uninstall_logger
from tools.wachterfeder.eet_session_runtime import analyse_session

# unified_gui resolves this module-global function when the EET worker starts.
gui_module.analyse_session = analyse_session


class UnifiedWachterfederApp(gui_module.UnifiedWachterfederApp):
    def _build_eet_tab(self, tab: ttk.Frame) -> None:
        super()._build_eet_tab(tab)
        self.eet_logger_status_var = tk.StringVar(value="EEex-Logger wird geprüft …")
        combat_box = None
        for child in tab.winfo_children():
            try:
                if isinstance(child, ttk.LabelFrame) and str(child.cget("text")) == "Kampfprotokoll":
                    combat_box = child
                    break
            except tk.TclError:
                continue
        if combat_box is None:
            return

        ttk.Separator(combat_box, orient="horizontal").pack(fill="x", pady=(10, 8))
        ttk.Label(combat_box, textvariable=self.eet_logger_status_var, justify="left").pack(anchor="w")
        controls = ttk.Frame(combat_box)
        controls.pack(fill="x", pady=(7, 0))
        ttk.Button(controls, text="Combatlogger installieren", command=self._install_eet_logger).pack(side="left")
        ttk.Button(controls, text="Status prüfen", command=self._refresh_eet_logger_status).pack(side="left", padx=(8, 0))
        ttk.Button(controls, text="Logger entfernen", command=self._uninstall_eet_logger).pack(side="left", padx=(8, 0))

    def _load_defaults(self) -> None:
        super()._load_defaults()
        self._refresh_eet_logger_status()

    def _refresh_eet_logger_status(self) -> None:
        game = self.eet_game_var.get().strip()
        if not game:
            self.eet_logger_status_var.set("EEex-Logger: erst EET/BG2EE-Spielordner auswählen.")
            return
        try:
            status = logger_status(Path(game), root=self.root_path, language="de_DE")
        except (OSError, EetError, ValueError) as exc:
            self.eet_logger_status_var.set(f"EEex-Logger: {exc}")
            return
        log_state = "Log vorhanden" if status.log_path.is_file() else "noch kein Log"
        self.eet_logger_status_var.set(
            f"EEex: {'erkannt' if status.eeex_available else 'nicht erkannt'} · "
            f"Wächterfeder-Logger: {'installiert' if status.installed else 'nicht installiert'} · {log_state}"
        )

    def _install_eet_logger(self) -> None:
        game = self.eet_game_var.get().strip()
        if not game:
            messagebox.showerror("Spielordner fehlt", "Bitte zuerst den EET/BG2EE-Spielordner auswählen.")
            return
        try:
            status = install_logger(Path(game), root=self.root_path, language="de_DE")
        except (OSError, EetError, ValueError) as exc:
            messagebox.showerror("Combatlogger konnte nicht installiert werden", str(exc))
            self._refresh_eet_logger_status()
            return
        self._refresh_eet_logger_status()
        messagebox.showinfo(
            "Combatlogger installiert",
            f"Wächterfeder hat nur sein eigenes EEex-Script installiert:\n{status.script_path}\n\n"
            "EET weiterhin über InfinityLoader.exe starten.",
        )

    def _uninstall_eet_logger(self) -> None:
        game = self.eet_game_var.get().strip()
        if not game:
            return
        if not messagebox.askyesno("Combatlogger entfernen", "Das lokale Wächterfeder-EEex-Script wirklich entfernen?"):
            return
        try:
            uninstall_logger(Path(game), root=self.root_path, language="de_DE")
        except (OSError, EetError, ValueError) as exc:
            messagebox.showerror("Combatlogger konnte nicht entfernt werden", str(exc))
        self._refresh_eet_logger_status()

    def _browse_eet_game(self) -> None:
        super()._browse_eet_game()
        self._refresh_eet_logger_status()

    def _eet_succeeded(self, result) -> None:
        super()._eet_succeeded(result)
        delta = {}
        try:
            delta = json.loads(result.delta_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            pass
        summary = delta.get("summary", {}) if isinstance(delta, dict) else {}
        if isinstance(summary, dict):
            extra = (
                f"\nHP-Änderungen: {int(summary.get('party_hit_point_changes', 0) or 0)}"
                f"\nParty-Gespräche: {int(summary.get('party_conversations', 0) or 0)}"
                f"\nDialogpfade sicher: {int(summary.get('dialogue_high_confidence', 0) or 0)}"
                f" · mittel: {int(summary.get('dialogue_medium_confidence', 0) or 0)}"
                f"\nCombat-Events: {int(summary.get('combat_events', 0) or 0)}"
            )
            self.eet_status_var.set(self.eet_status_var.get() + extra)
        self._refresh_eet_logger_status()



def main() -> int:
    window = tk.Tk()
    UnifiedWachterfederApp(window)
    window.mainloop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
