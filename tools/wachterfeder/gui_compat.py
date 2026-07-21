#!/usr/bin/env python3
"""Python-3.14-kompatibler Starter für die Wächterfeder-Oberfläche."""
from __future__ import annotations

import tkinter as tk
from tkinter import font as tkfont, ttk

try:
    import tools.wachterfeder.gui as gui_module
    from tools.wachterfeder.expansion_assets import analyse_savegame
except ModuleNotFoundError:  # Direkter Start aus tools/wachterfeder.
    import gui as gui_module
    from expansion_assets import analyse_savegame

# Die bestehende Oberfläche greift zur Laufzeit auf dieses Modulattribut zu.
# So bleibt die UI klein, während die Analyse Grundspiel und Erweiterungen liest.
gui_module.analyse_savegame = analyse_savegame
WachterfederApp = gui_module.WachterfederApp


class CompatibleWachterfederApp(WachterfederApp):
    """Verwendet Tk-Namensschriften statt einer mehrteiligen Font-Zeichenkette."""

    def _configure_window(self) -> None:
        self.window.title("Wächterfeder")
        self.window.geometry("820x560")
        self.window.minsize(720, 500)

        for font_name in (
            "TkDefaultFont",
            "TkTextFont",
            "TkMenuFont",
            "TkHeadingFont",
            "TkCaptionFont",
            "TkSmallCaptionFont",
        ):
            try:
                tkfont.nametofont(font_name).configure(family="Segoe UI", size=10)
            except tk.TclError:
                pass

        style = ttk.Style(self.window)
        try:
            style.theme_use("vista")
        except tk.TclError:
            pass
        style.configure("Title.TLabel", font=("Segoe UI Semibold", 22))
        style.configure("Subtitle.TLabel", font=("Segoe UI", 10))
        style.configure("Primary.TButton", font=("Segoe UI Semibold", 12), padding=12)
        style.configure("Section.TLabelframe", padding=12)


def main() -> int:
    window = tk.Tk()
    CompatibleWachterfederApp(window)
    window.mainloop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
