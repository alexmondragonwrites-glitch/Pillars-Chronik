#!/usr/bin/env python3
"""Tabbed Windows UI for the three Wächterfeder game modules."""
from __future__ import annotations

import os
import threading
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, font as tkfont, messagebox, ttk

try:
    from tools.wachterfeder.desktop import newest_local_save, repository_root
    from tools.wachterfeder.eet import EetError, analyse_eet_save, newest_eet_save
    from tools.wachterfeder.expanded_desktop import analyse_savegame as analyse_pillars_save
    from tools.wachterfeder.local_game import LocalGameError, read_local_config
    from tools.wachterfeder.rogue_trader import (
        RogueTraderError,
        analyse_rogue_trader_save,
        newest_rogue_trader_save,
    )
    from tools.wachterfeder.wachterfeder import WachterfederError
except ModuleNotFoundError:  # Direct execution from tools/wachterfeder.
    from desktop import newest_local_save, repository_root
    from eet import EetError, analyse_eet_save, newest_eet_save
    from expanded_desktop import analyse_savegame as analyse_pillars_save
    from local_game import LocalGameError, read_local_config
    from rogue_trader import RogueTraderError, analyse_rogue_trader_save, newest_rogue_trader_save
    from wachterfeder import WachterfederError

GAME_TABS = ("Pillars of Eternity", "Baldur's Gate EET", "Rogue Trader")

DEFAULT_PILLARS_PATHS = (
    Path(r"E:\SteamLibrary\steamapps\common\Pillars of Eternity"),
    Path(r"C:\Program Files (x86)\Steam\steamapps\common\Pillars of Eternity"),
    Path(r"C:\Program Files\Steam\steamapps\common\Pillars of Eternity"),
)

DEFAULT_EET_PATHS = (
    Path(r"E:\SteamLibrary\steamapps\common\Baldur's Gate II Enhanced Edition"),
    Path(r"C:\Program Files (x86)\Steam\steamapps\common\Baldur's Gate II Enhanced Edition"),
    Path(r"C:\Program Files\Steam\steamapps\common\Baldur's Gate II Enhanced Edition"),
)


def delta_state(initial_snapshot: bool, has_changes: bool) -> str:
    if initial_snapshot:
        return "Erste Vergleichsbasis erstellt"
    if has_changes:
        return "Änderungen seit der letzten Auswertung erkannt"
    return "Keine neuen Änderungen"


class MultiWachterfederApp:
    def __init__(self, window: tk.Tk) -> None:
        self.window = window
        self.root_path = repository_root()

        self.pillars_save = tk.StringVar()
        self.pillars_game = tk.StringVar()
        self.pillars_status = tk.StringVar(value="Bereit.")
        self.pillars_result = None

        self.eet_save = tk.StringVar()
        self.eet_game = tk.StringVar()
        self.eet_status = tk.StringVar(value="Bereit.")
        self.eet_result = None

        self.rt_save = tk.StringVar()
        self.rt_status = tk.StringVar(value="Bereit. Das Modul ist für Real-Save-Kartierung vorbereitet.")
        self.rt_result = None

        self._configure_window()
        self._build_ui()
        self._load_defaults()

    def _configure_window(self) -> None:
        self.window.title("Wächterfeder")
        self.window.geometry("900x680")
        self.window.minsize(780, 600)

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
        style.configure("Primary.TButton", font=("Segoe UI Semibold", 11), padding=10)
        style.configure("Section.TLabelframe", padding=12)

    def _build_ui(self) -> None:
        outer = ttk.Frame(self.window, padding=18)
        outer.pack(fill="both", expand=True)

        ttk.Label(outer, text="Wächterfeder", style="Title.TLabel").pack(anchor="w")
        ttk.Label(
            outer,
            text="Drei Spiele, dieselbe Feder: Vollstand lesen, Änderungen als kompaktes Delta sichern.",
            style="Subtitle.TLabel",
        ).pack(anchor="w", pady=(2, 12))

        notebook = ttk.Notebook(outer)
        notebook.pack(fill="both", expand=True)

        pillars_tab = ttk.Frame(notebook, padding=14)
        eet_tab = ttk.Frame(notebook, padding=14)
        rt_tab = ttk.Frame(notebook, padding=14)
        notebook.add(pillars_tab, text=GAME_TABS[0])
        notebook.add(eet_tab, text=GAME_TABS[1])
        notebook.add(rt_tab, text=GAME_TABS[2])

        self._build_pillars_tab(pillars_tab)
        self._build_eet_tab(eet_tab)
        self._build_rt_tab(rt_tab)

    @staticmethod
    def _path_row(parent: ttk.Frame, variable: tk.StringVar, button_text: str, command) -> None:
        row = ttk.Frame(parent)
        row.pack(fill="x")
        ttk.Entry(row, textvariable=variable).pack(side="left", fill="x", expand=True)
        ttk.Button(row, text=button_text, command=command).pack(side="left", padx=(8, 0))

    @staticmethod
    def _status_box(parent: ttk.Frame, variable: tk.StringVar) -> None:
        box = ttk.LabelFrame(parent, text="Status", style="Section.TLabelframe")
        box.pack(fill="both", expand=True, pady=(12, 0))
        ttk.Label(box, textvariable=variable, justify="left", anchor="nw", wraplength=800).pack(
            fill="both", expand=True
        )

    def _build_pillars_tab(self, tab: ttk.Frame) -> None:
        save_box = ttk.LabelFrame(tab, text="1. Pillars-Spielstand", style="Section.TLabelframe")
        save_box.pack(fill="x", pady=(0, 10))
        self._path_row(save_box, self.pillars_save, "Durchsuchen", self._browse_pillars_save)
        ttk.Button(save_box, text="Neueste Speicherung verwenden", command=self._newest_pillars).pack(
            anchor="w", pady=(8, 0)
        )

        game_box = ttk.LabelFrame(tab, text="2. Lokale Pillars-Installation", style="Section.TLabelframe")
        game_box.pack(fill="x", pady=(0, 10))
        self._path_row(game_box, self.pillars_game, "Ordner wählen", self._browse_pillars_game)

        actions = ttk.Frame(tab)
        actions.pack(fill="x")
        self.pillars_run = ttk.Button(
            actions, text="Pillars auswerten", style="Primary.TButton", command=self._start_pillars
        )
        self.pillars_run.pack(side="left", fill="x", expand=True)
        ttk.Button(actions, text="Ergebnisordner öffnen", command=lambda: self._open_result("pillars")).pack(
            side="left", padx=(8, 0)
        )
        self._status_box(tab, self.pillars_status)

    def _build_eet_tab(self, tab: ttk.Frame) -> None:
        save_box = ttk.LabelFrame(tab, text="1. EET-Spielstand", style="Section.TLabelframe")
        save_box.pack(fill="x", pady=(0, 10))
        self._path_row(save_box, self.eet_save, "Saveordner wählen", self._browse_eet_save)
        ttk.Button(save_box, text="Neueste Speicherung verwenden", command=self._newest_eet).pack(
            anchor="w", pady=(8, 0)
        )

        game_box = ttk.LabelFrame(tab, text="2. EET/BG2EE-Installation", style="Section.TLabelframe")
        game_box.pack(fill="x", pady=(0, 10))
        self._path_row(game_box, self.eet_game, "Ordner wählen", self._browse_eet_game)

        actions = ttk.Frame(tab)
        actions.pack(fill="x")
        self.eet_run = ttk.Button(
            actions, text="EET auswerten", style="Primary.TButton", command=self._start_eet
        )
        self.eet_run.pack(side="left", fill="x", expand=True)
        ttk.Button(actions, text="Ergebnisordner öffnen", command=lambda: self._open_result("eet")).pack(
            side="left", padx=(8, 0)
        )
        self._status_box(tab, self.eet_status)

    def _build_rt_tab(self, tab: ttk.Frame) -> None:
        ttk.Label(
            tab,
            text=(
                "Vorbereiteter Rogue-Trader-Adapter. Er prüft .zks-Saves read-only und erzeugt bereits "
                "Snapshot + Delta; Storyfelder werden mit deinem ersten echten Save präzise kartiert."
            ),
            wraplength=810,
        ).pack(anchor="w", pady=(0, 12))

        save_box = ttk.LabelFrame(tab, text="Rogue-Trader-Spielstand", style="Section.TLabelframe")
        save_box.pack(fill="x", pady=(0, 10))
        self._path_row(save_box, self.rt_save, ".zks wählen", self._browse_rt_save)
        ttk.Button(save_box, text="Neueste Speicherung verwenden", command=self._newest_rt).pack(
            anchor="w", pady=(8, 0)
        )

        actions = ttk.Frame(tab)
        actions.pack(fill="x")
        self.rt_run = ttk.Button(
            actions, text="Rogue Trader auswerten", style="Primary.TButton", command=self._start_rt
        )
        self.rt_run.pack(side="left", fill="x", expand=True)
        ttk.Button(actions, text="Ergebnisordner öffnen", command=lambda: self._open_result("rt")).pack(
            side="left", padx=(8, 0)
        )
        self._status_box(tab, self.rt_status)

    def _load_defaults(self) -> None:
        newest = newest_local_save()
        if newest:
            self.pillars_save.set(str(newest))
        try:
            assets = read_local_config(self.root_path / ".wachterfeder" / "config.json")
            self.pillars_game.set(str(assets.data_root))
        except (OSError, LocalGameError):
            for candidate in DEFAULT_PILLARS_PATHS:
                if candidate.is_dir():
                    self.pillars_game.set(str(candidate))
                    break

        newest = newest_eet_save()
        if newest:
            self.eet_save.set(str(newest))
        for candidate in DEFAULT_EET_PATHS:
            if candidate.is_dir():
                self.eet_game.set(str(candidate))
                break

        newest = newest_rogue_trader_save()
        if newest:
            self.rt_save.set(str(newest))

    def _browse_pillars_save(self) -> None:
        selected = filedialog.askopenfilename(
            title="Pillars-Spielstand auswählen",
            filetypes=(("Pillars-Spielstände", "*.savegame"), ("Alle Dateien", "*.*")),
        )
        if selected:
            self.pillars_save.set(selected)

    def _browse_pillars_game(self) -> None:
        selected = filedialog.askdirectory(title="Pillars-Installation auswählen")
        if selected:
            self.pillars_game.set(selected)

    def _browse_eet_save(self) -> None:
        selected = filedialog.askdirectory(title="EET-Saveordner auswählen")
        if selected:
            self.eet_save.set(selected)

    def _browse_eet_game(self) -> None:
        selected = filedialog.askdirectory(title="EET/BG2EE-Installation auswählen")
        if selected:
            self.eet_game.set(selected)

    def _browse_rt_save(self) -> None:
        selected = filedialog.askopenfilename(
            title="Rogue-Trader-Spielstand auswählen",
            filetypes=(("Rogue-Trader-Spielstände", "*.zks"), ("Alle Dateien", "*.*")),
        )
        if selected:
            self.rt_save.set(selected)

    def _newest_pillars(self) -> None:
        save = newest_local_save()
        if save:
            self.pillars_save.set(str(save))
        else:
            messagebox.showwarning("Kein Save gefunden", "Kein Pillars-.savegame im üblichen Ordner gefunden.")

    def _newest_eet(self) -> None:
        save = newest_eet_save()
        if save:
            self.eet_save.set(str(save))
        else:
            messagebox.showwarning("Kein Save gefunden", "Kein EET-Spielstand im üblichen Ordner gefunden.")

    def _newest_rt(self) -> None:
        save = newest_rogue_trader_save()
        if save:
            self.rt_save.set(str(save))
        else:
            messagebox.showwarning("Kein Save gefunden", "Kein Rogue-Trader-.zks im üblichen Ordner gefunden.")

    def _start_pillars(self) -> None:
        if not self.pillars_save.get().strip():
            messagebox.showerror("Spielstand fehlt", "Bitte einen Pillars-Spielstand auswählen.")
            return
        self.pillars_run.configure(state="disabled", text="Wächterfeder liest …")
        self.pillars_status.set("Pillars-Save und Dialogpakete werden ausgewertet …")
        threading.Thread(target=self._run_pillars, daemon=True).start()

    def _run_pillars(self) -> None:
        try:
            game = self.pillars_game.get().strip()
            result = analyse_pillars_save(
                Path(self.pillars_save.get()),
                game_path=Path(game) if game else None,
                language="de",
                root=self.root_path,
            )
        except (OSError, LocalGameError, WachterfederError, ValueError) as exc:
            self.window.after(0, self._failed, "pillars", str(exc))
            return
        except Exception as exc:
            self.window.after(0, self._failed, "pillars", f"Unerwarteter Fehler: {exc}")
            return
        self.window.after(0, self._pillars_done, result)

    def _pillars_done(self, result) -> None:
        self.pillars_result = result
        self.pillars_run.configure(state="normal", text="Pillars erneut auswerten")
        self.pillars_status.set(
            f"Fertig: {result.player_name} · {result.scene_title} · {result.difficulty}\n"
            f"{delta_state(result.initial_snapshot, result.has_changes)}\n\n"
            f"Neue Gespräche: {result.new_conversations}\n"
            f"Neue Dialogknoten: {result.new_dialogue_nodes}\n"
            f"Geänderte Spielvariablen: {result.changed_globals}\n\n"
            f"Snapshot: {result.snapshot_path}\nDelta: {result.delta_path}"
        )

    def _start_eet(self) -> None:
        if not self.eet_save.get().strip() or not self.eet_game.get().strip():
            messagebox.showerror("Pfad fehlt", "Bitte EET-Spielstand und EET/BG2EE-Installation auswählen.")
            return
        self.eet_run.configure(state="disabled", text="Wächterfeder liest …")
        self.eet_status.set("BALDUR.GAM, Journal und Änderungen werden ausgewertet …")
        threading.Thread(target=self._run_eet, daemon=True).start()

    def _run_eet(self) -> None:
        try:
            result = analyse_eet_save(
                Path(self.eet_save.get()),
                game_path=Path(self.eet_game.get()),
                language="de_DE",
                root=self.root_path,
            )
        except (OSError, EetError, ValueError) as exc:
            self.window.after(0, self._failed, "eet", str(exc))
            return
        except Exception as exc:
            self.window.after(0, self._failed, "eet", f"Unerwarteter Fehler: {exc}")
            return
        self.window.after(0, self._eet_done, result)

    def _eet_done(self, result) -> None:
        self.eet_result = result
        self.eet_run.configure(state="normal", text="EET erneut auswerten")
        self.eet_status.set(
            f"Fertig: Gebiet {result.current_area} · Party {result.party_members}\n"
            f"{delta_state(result.initial_snapshot, result.has_changes)}\n\n"
            f"Globals Δ: {result.changed_globals}\nJournal Δ: {result.new_journal_entries}\n"
            f"Party Δ: {result.party_changes}\n\n"
            f"Snapshot: {result.snapshot_path}\nDelta: {result.delta_path}"
        )

    def _start_rt(self) -> None:
        if not self.rt_save.get().strip():
            messagebox.showerror("Spielstand fehlt", "Bitte einen Rogue-Trader-.zks-Spielstand auswählen.")
            return
        self.rt_run.configure(state="disabled", text="Wächterfeder liest …")
        self.rt_status.set(".zks wird read-only geprüft und mit dem letzten Snapshot verglichen …")
        threading.Thread(target=self._run_rt, daemon=True).start()

    def _run_rt(self) -> None:
        try:
            result = analyse_rogue_trader_save(Path(self.rt_save.get()), root=self.root_path)
        except (OSError, RogueTraderError, ValueError) as exc:
            self.window.after(0, self._failed, "rt", str(exc))
            return
        except Exception as exc:
            self.window.after(0, self._failed, "rt", f"Unerwarteter Fehler: {exc}")
            return
        self.window.after(0, self._rt_done, result)

    def _rt_done(self, result) -> None:
        self.rt_result = result
        self.rt_run.configure(state="normal", text="Rogue Trader erneut auswerten")
        self.rt_status.set(
            f"Fertig: {result.save_file.name}\n"
            f"{delta_state(result.initial_snapshot, result.has_changes)}\n\n"
            f"Archivdateien: {result.archive_members}\n"
            f"JSON-Dokumente: {result.json_documents}\n"
            f"Geänderte Archivdateien: {result.changed_members}\n"
            f"Interessante Signale Δ: {result.changed_signals}\n\n"
            f"Snapshot: {result.snapshot_path}\nDelta: {result.delta_path}\n\n"
            "Hinweis: Die Signalnamen werden mit dem ersten echten Save noch präzise auf Owlcat-Felder gemappt."
        )

    def _failed(self, game: str, message: str) -> None:
        if game == "pillars":
            self.pillars_run.configure(state="normal", text="Pillars auswerten")
            self.pillars_status.set(f"Auswertung fehlgeschlagen:\n{message}")
        elif game == "eet":
            self.eet_run.configure(state="normal", text="EET auswerten")
            self.eet_status.set(f"Auswertung fehlgeschlagen:\n{message}")
        else:
            self.rt_run.configure(state="normal", text="Rogue Trader auswerten")
            self.rt_status.set(f"Auswertung fehlgeschlagen:\n{message}")
        messagebox.showerror("Wächterfeder konnte den Save nicht lesen", message)

    def _open_result(self, game: str) -> None:
        result = {
            "pillars": self.pillars_result,
            "eet": self.eet_result,
            "rt": self.rt_result,
        }[game]
        if result is not None:
            folder = result.delta_path.parent
        else:
            suffix = {"pillars": "", "eet": "eet", "rt": "rogue-trader"}[game]
            folder = self.root_path / ".wachterfeder" / suffix
        folder.mkdir(parents=True, exist_ok=True)
        try:
            os.startfile(str(folder))  # type: ignore[attr-defined]
        except (AttributeError, OSError) as exc:
            messagebox.showerror("Ordner konnte nicht geöffnet werden", str(exc))


def main() -> int:
    window = tk.Tk()
    MultiWachterfederApp(window)
    window.mainloop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
