#!/usr/bin/env python3
"""Python-3.14-kompatibler Starter für die Wächterfeder-Oberfläche."""
from __future__ import annotations

import tkinter as tk
from tkinter import font as tkfont, ttk

try:
    import tools.wachterfeder.gui as gui_module
    from tools.wachterfeder.desktop import DesktopAnalysisResult
    from tools.wachterfeder.expanded_desktop import analyse_savegame
except ModuleNotFoundError:  # Direkter Start aus tools/wachterfeder.
    import gui as gui_module
    from desktop import DesktopAnalysisResult
    from expanded_desktop import analyse_savegame

# Die bestehende Oberfläche greift zur Laufzeit auf dieses Modulattribut zu.
# So liest die UI alle Pakete und erzeugt dennoch nur kompakte Nutzerausgaben.
gui_module.analyse_savegame = analyse_savegame
WachterfederApp = gui_module.WachterfederApp


class CompatibleWachterfederApp(WachterfederApp):
    """Verwendet Tk-Namensschriften und zeigt die kompakte Delta-Ausgabe."""

    def _configure_window(self) -> None:
        self.window.title("Wächterfeder")
        self.window.geometry("820x590")
        self.window.minsize(720, 520)

        for font_name in (
            "TkDefaultFont",
            "TkTextFont",
            "TkMenuFont",
            "TkHeadingFont",
            "TkCaptionFont",
            "TkSmallCaptionFont",
        ):
            try:
                tkfont.nametofont(font_name).configure(
                    family="Segoe UI", size=10
                )
            except tk.TclError:
                pass

        style = ttk.Style(self.window)
        try:
            style.theme_use("vista")
        except tk.TclError:
            pass
        style.configure("Title.TLabel", font=("Segoe UI Semibold", 22))
        style.configure("Subtitle.TLabel", font=("Segoe UI", 10))
        style.configure(
            "Primary.TButton",
            font=("Segoe UI Semibold", 12),
            padding=12,
        )
        style.configure("Section.TLabelframe", padding=12)

    def _analysis_succeeded(self, result: DesktopAnalysisResult) -> None:
        self.result = result
        self.run_button.configure(state="normal", text="Serin erneut auswerten")
        self.open_button.configure(state="normal")
        warning_text = ""
        if result.warnings:
            warning_text = "\n\nHinweise:\n- " + "\n- ".join(result.warnings)

        delta_state = (
            "Erste Vergleichsbasis erstellt"
            if result.initial_snapshot
            else "Keine neuen Änderungen"
            if not result.has_changes
            else "Änderungen seit dem letzten Save erkannt"
        )
        self.status_var.set(
            f"Fertig: {result.player_name} · {result.scene_title} · "
            f"{result.difficulty}\n"
            f"{delta_state}\n\n"
            f"Neue Gespräche: {result.new_conversations}\n"
            f"Neue Dialogknoten: {result.new_dialogue_nodes}\n"
            f"Geänderte Spielvariablen: {result.changed_globals}\n"
            f"Dialoge insgesamt zugeordnet: {result.matched_conversations}\n"
            f"Nicht gefunden: {result.unresolved_conversations}\n\n"
            f"Vollständiger aktueller Stand:\n{result.snapshot_path}\n\n"
            f"Nur neu seit dem letzten Save:\n{result.delta_path}\n\n"
            f"Historisches Delta:\n{result.history_delta_path}"
            f"{warning_text}"
        )
        if self.open_folder_var.get():
            self._open_result_folder()


def main() -> int:
    window = tk.Tk()
    CompatibleWachterfederApp(window)
    window.mainloop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
