#!/usr/bin/env python3
"""Unified Wächterfeder UI with optional EEex runtime and dialogue analysis."""
from __future__ import annotations

import json
import sys
import tkinter as tk
from pathlib import Path
from tkinter import messagebox, ttk

REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
if str(REPOSITORY_ROOT) not in sys.path:
    sys.path.insert(0, str(REPOSITORY_ROOT))

import tools.wachterfeder.unified_gui as gui_module
from tools.wachterfeder.eet import EetError
from tools.wachterfeder.eet_combat_logger import install_logger, logger_status, uninstall_logger
from tools.wachterfeder.eet_session_runtime import analyse_session

gui_module.analyse_session = analyse_session


class UnifiedWachterfederApp(gui_module.UnifiedWachterfederApp):
    def _build_eet_tab(self, tab: ttk.Frame) -> None:
        super()._build_eet_tab(tab)
        self.eet_logger_status_var = tk.StringVar(value="EEex-Runtime wird geprüft …")
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
        self.eet_logger_install_button = ttk.Button(
            controls,
            text="Runtime-Logger installieren",
            command=self._install_eet_logger,
        )
        self.eet_logger_install_button.pack(side="left")
        ttk.Button(controls, text="Status prüfen", command=self._refresh_eet_logger_status).pack(side="left", padx=(8, 0))
        ttk.Button(controls, text="Runtime-Logger entfernen", command=self._uninstall_eet_logger).pack(side="left", padx=(8, 0))

    def _load_defaults(self) -> None:
        super()._load_defaults()
        self._refresh_eet_logger_status()

    def _refresh_eet_logger_status(self) -> None:
        game = self.eet_game_var.get().strip()
        if not game:
            self.eet_logger_status_var.set("EEex-Runtime: erst EET/BG2EE-Spielordner auswählen.")
            if hasattr(self, "eet_logger_install_button"):
                self.eet_logger_install_button.configure(text="Runtime-Logger installieren")
            return
        try:
            status = logger_status(Path(game), root=self.root_path, language="de_DE")
        except (OSError, EetError, ValueError) as exc:
            self.eet_logger_status_var.set(f"EEex-Runtime: {exc}")
            return

        if status.installed and status.up_to_date:
            logger_state = "aktuell"
            button_text = "Runtime-Logger neu installieren"
        elif status.installed:
            logger_state = "VERALTET · Aktualisierung erforderlich"
            button_text = "Runtime-Logger aktualisieren"
        else:
            logger_state = "nicht installiert"
            button_text = "Runtime-Logger installieren"

        if status.runtime_active:
            runtime_state = "Heartbeat empfangen"
        elif status.log_path.is_file() and status.log_path.stat().st_size > 0:
            runtime_state = "Log da, aber kein V3-Heartbeat"
        else:
            runtime_state = "wartet auf InfinityLoader-Start"

        self.eet_logger_status_var.set(
            f"EEex: {'erkannt' if status.eeex_available else 'nicht erkannt'} · "
            f"Runtime-Logger: {logger_state} · {runtime_state}"
        )
        if hasattr(self, "eet_logger_install_button"):
            self.eet_logger_install_button.configure(text=button_text)

    def _install_eet_logger(self) -> None:
        game = self.eet_game_var.get().strip()
        if not game:
            messagebox.showerror("Spielordner fehlt", "Bitte zuerst den EET/BG2EE-Spielordner auswählen.")
            return
        try:
            status = install_logger(Path(game), root=self.root_path, language="de_DE")
        except (OSError, EetError, ValueError) as exc:
            messagebox.showerror("Runtime-Logger konnte nicht installiert werden", str(exc))
            self._refresh_eet_logger_status()
            return
        self._refresh_eet_logger_status()
        messagebox.showinfo(
            "Runtime-Logger aktualisiert",
            f"Wächterfeder Runtime-Logger V3 wurde bestätigt:\n{status.script_path}\n\n"
            f"Runtime-Datei:\n{status.log_path}\n\n"
            "EET jetzt über InfinityLoader.exe starten. Danach sollte der Status 'Heartbeat empfangen' anzeigen.",
        )

    def _uninstall_eet_logger(self) -> None:
        game = self.eet_game_var.get().strip()
        if not game:
            return
        if not messagebox.askyesno("Runtime-Logger entfernen", "Das lokale Wächterfeder-EEex-Script wirklich entfernen?"):
            return
        try:
            uninstall_logger(Path(game), root=self.root_path, language="de_DE")
        except (OSError, EetError, ValueError) as exc:
            messagebox.showerror("Runtime-Logger konnte nicht entfernt werden", str(exc))
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
                f"\nSave-Gespräche: {int(summary.get('party_conversations', 0) or 0)}"
                f"\nLive-Dialogwahlen: {int(summary.get('live_dialogue_choices', 0) or 0)}"
                f"\nDialogpfade sicher: {int(summary.get('dialogue_high_confidence', 0) or 0)}"
                f" · mittel: {int(summary.get('dialogue_medium_confidence', 0) or 0)}"
                f"\nCombat-Events: {int(summary.get('combat_events', 0) or 0)}"
                f" · Schaden: {int(summary.get('combat_damage_total', 0) or 0)}"
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
