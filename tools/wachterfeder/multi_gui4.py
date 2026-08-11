#!/usr/bin/env python3
"""Four-tab Windows UI for Wächterfeder, extending the three-game shell with CK3."""
from __future__ import annotations

import threading
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

try:
    from tools.wachterfeder.ck3 import Ck3Error, analyse_ck3_save, find_rakaly, newest_ck3_save
    from tools.wachterfeder.multi_gui import MultiWachterfederApp, delta_state
except ModuleNotFoundError:  # Direct execution from tools/wachterfeder.
    from ck3 import Ck3Error, analyse_ck3_save, find_rakaly, newest_ck3_save
    from multi_gui import MultiWachterfederApp, delta_state


class FourGameWachterfederApp(MultiWachterfederApp):
    def __init__(self, window: tk.Tk) -> None:
        self.ck3_save = tk.StringVar(master=window)
        self.ck3_rakaly = tk.StringVar(master=window)
        self.ck3_status = tk.StringVar(
            master=window,
            value="Bereit. Familie, Vasallen, Titel, Kriege und persistente Event-Signale können ausgewertet werden.",
        )
        self.ck3_result = None
        super().__init__(window)

    def _configure_window(self) -> None:
        super()._configure_window()
        self.window.geometry("940x720")
        self.window.minsize(800, 620)

    def _build_ui(self) -> None:
        outer = ttk.Frame(self.window, padding=18)
        outer.pack(fill="both", expand=True)
        ttk.Label(outer, text="Wächterfeder", style="Title.TLabel").pack(anchor="w")
        ttk.Label(
            outer,
            text="Vier Spiele, dieselbe Feder: Vollstand lesen, Änderungen als kompaktes Delta sichern.",
            style="Subtitle.TLabel",
        ).pack(anchor="w", pady=(2, 12))

        notebook = ttk.Notebook(outer)
        notebook.pack(fill="both", expand=True)
        pillars_tab = ttk.Frame(notebook, padding=14)
        eet_tab = ttk.Frame(notebook, padding=14)
        rt_tab = ttk.Frame(notebook, padding=14)
        ck3_tab = ttk.Frame(notebook, padding=14)
        notebook.add(pillars_tab, text="Pillars of Eternity")
        notebook.add(eet_tab, text="Baldur's Gate EET")
        notebook.add(rt_tab, text="Rogue Trader")
        notebook.add(ck3_tab, text="Crusader Kings III")
        self._build_pillars_tab(pillars_tab)
        self._build_eet_tab(eet_tab)
        self._build_rt_tab(rt_tab)
        self._build_ck3_tab(ck3_tab)

    def _build_ck3_tab(self, tab: ttk.Frame) -> None:
        ttk.Label(
            tab,
            text=(
                "CK3 wird read-only ausgewertet. Ohne Rakaly liest Wächterfeder Save-Envelope und Metadaten; "
                "mit Rakaly zusätzlich Familie, Titel, direkte Vasallen, Kriege und persistente Event-Signale."
            ),
            wraplength=840,
        ).pack(anchor="w", pady=(0, 12))

        save_box = ttk.LabelFrame(tab, text="1. CK3-Spielstand", style="Section.TLabelframe")
        save_box.pack(fill="x", pady=(0, 10))
        self._path_row(save_box, self.ck3_save, ".ck3 wählen", self._browse_ck3_save)
        ttk.Button(save_box, text="Neueste Speicherung verwenden", command=self._newest_ck3).pack(anchor="w", pady=(8, 0))

        parser_box = ttk.LabelFrame(tab, text="2. Optional: Rakaly für tiefe Analyse", style="Section.TLabelframe")
        parser_box.pack(fill="x", pady=(0, 10))
        self._path_row(parser_box, self.ck3_rakaly, "rakaly.exe wählen", self._browse_rakaly)
        ttk.Label(
            parser_box,
            text="Ohne Rakaly bleibt der Save lesbar, aber Familie/Vasallen/Events werden noch nicht tief aufgelöst.",
        ).pack(anchor="w", pady=(8, 0))

        actions = ttk.Frame(tab)
        actions.pack(fill="x")
        self.ck3_run = ttk.Button(actions, text="CK3 auswerten", style="Primary.TButton", command=self._start_ck3)
        self.ck3_run.pack(side="left", fill="x", expand=True)
        ttk.Button(actions, text="Ergebnisordner öffnen", command=lambda: self._open_result("ck3")).pack(side="left", padx=(8, 0))
        self._status_box(tab, self.ck3_status)

    def _load_defaults(self) -> None:
        super()._load_defaults()
        newest = newest_ck3_save()
        if newest:
            self.ck3_save.set(str(newest))
        rakaly = find_rakaly(root=self.root_path)
        if rakaly:
            self.ck3_rakaly.set(str(rakaly))

    def _browse_ck3_save(self) -> None:
        selected = filedialog.askopenfilename(
            title="Crusader-Kings-III-Spielstand auswählen",
            filetypes=(("CK3-Spielstände", "*.ck3"), ("Alle Dateien", "*.*")),
        )
        if selected:
            self.ck3_save.set(selected)

    def _browse_rakaly(self) -> None:
        selected = filedialog.askopenfilename(
            title="rakaly.exe auswählen",
            filetypes=(("Rakaly", "rakaly.exe"), ("Programme", "*.exe"), ("Alle Dateien", "*.*")),
        )
        if selected:
            self.ck3_rakaly.set(selected)

    def _newest_ck3(self) -> None:
        save = newest_ck3_save()
        if save:
            self.ck3_save.set(str(save))
        else:
            messagebox.showwarning("Kein Save gefunden", "Kein CK3-.ck3 im üblichen Ordner gefunden.")

    def _start_ck3(self) -> None:
        if not self.ck3_save.get().strip():
            messagebox.showerror("Spielstand fehlt", "Bitte einen CK3-.ck3-Spielstand auswählen.")
            return
        self.ck3_run.configure(state="disabled", text="Wächterfeder liest …")
        self.ck3_status.set("CK3-Save wird read-only geprüft und mit dem letzten Snapshot verglichen …")
        threading.Thread(target=self._run_ck3, daemon=True).start()

    def _run_ck3(self) -> None:
        try:
            rakaly_text = self.ck3_rakaly.get().strip()
            result = analyse_ck3_save(
                Path(self.ck3_save.get()),
                rakaly_path=Path(rakaly_text) if rakaly_text else None,
                root=self.root_path,
            )
        except (OSError, Ck3Error, ValueError) as exc:
            self.window.after(0, self._failed, "ck3", str(exc))
            return
        except Exception as exc:
            self.window.after(0, self._failed, "ck3", f"Unerwarteter Fehler: {exc}")
            return
        self.window.after(0, self._ck3_done, result)

    def _ck3_done(self, result) -> None:
        self.ck3_result = result
        self.ck3_run.configure(state="normal", text="CK3 erneut auswerten")
        depth = "Tiefe Analyse aktiv" if result.deep_analysis else "Metadatenmodus (Rakaly noch nicht gefunden)"
        self.ck3_status.set(
            f"Fertig: {result.save_file.name}\n"
            f"{delta_state(result.initial_snapshot, result.has_changes)}\n"
            f"{depth}\n\n"
            f"Version: {result.game_version or 'unbekannt'}\n"
            f"Herrscher: {result.player_name or 'noch nicht tief aufgelöst'}\n"
            f"Primärtitel: {result.primary_title or 'noch nicht tief aufgelöst'}\n"
            f"Familienmitglieder im Beobachtungsring: {result.family_members}\n"
            f"Direkte Vasallen: {result.vassals}\n"
            f"Timeline-/Event-Kandidaten Δ: {result.event_changes}\n\n"
            f"Snapshot: {result.snapshot_path}\nDelta: {result.delta_path}\n\n"
            "Eventregel: Exakte Optionen nur, wenn Save oder späterer Runtime-Logger sie eindeutig belegt."
        )

    def _failed(self, game: str, message: str) -> None:
        if game == "ck3":
            self.ck3_run.configure(state="normal", text="CK3 auswerten")
            self.ck3_status.set(f"Auswertung fehlgeschlagen:\n{message}")
            messagebox.showerror("Wächterfeder konnte den CK3-Save nicht lesen", message)
            return
        super()._failed(game, message)

    def _open_result(self, game: str) -> None:
        if game == "ck3":
            folder = self.ck3_result.delta_path.parent if self.ck3_result is not None else self.root_path / ".wachterfeder" / "ck3"
            folder.mkdir(parents=True, exist_ok=True)
            try:
                import os
                os.startfile(str(folder))  # type: ignore[attr-defined]
            except (AttributeError, OSError) as exc:
                messagebox.showerror("Ordner konnte nicht geöffnet werden", str(exc))
            return
        super()._open_result(game)


def main() -> int:
    window = tk.Tk()
    FourGameWachterfederApp(window)
    window.mainloop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
