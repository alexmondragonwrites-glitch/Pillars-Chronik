#!/usr/bin/env python3
"""Unified desktop UI for Pillars of Eternity and Baldur's Gate EET."""
from __future__ import annotations

import json
import os
import threading
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, font as tkfont, messagebox, ttk

try:
    from tools.wachterfeder.desktop import DesktopAnalysisResult, newest_local_save, repository_root
    from tools.wachterfeder.eet import EetError
    from tools.wachterfeder.eet_session import (
        EetSessionResult,
        analyse_session,
        candidate_save_roots as eet_candidate_save_roots,
        newest_save as newest_eet_save,
    )
    from tools.wachterfeder.expanded_desktop import analyse_savegame as analyse_pillars_save
    from tools.wachterfeder.local_game import LocalGameError, read_local_config
    from tools.wachterfeder.wachterfeder import WachterfederError
except ModuleNotFoundError:  # direct execution
    from desktop import DesktopAnalysisResult, newest_local_save, repository_root
    from eet import EetError
    from eet_session import EetSessionResult, analyse_session, candidate_save_roots as eet_candidate_save_roots, newest_save as newest_eet_save
    from expanded_desktop import analyse_savegame as analyse_pillars_save
    from local_game import LocalGameError, read_local_config
    from wachterfeder import WachterfederError


DEFAULT_PILLARS_GAME_PATHS = (
    Path(r"E:\SteamLibrary\steamapps\common\Pillars of Eternity"),
    Path(r"C:\Program Files (x86)\Steam\steamapps\common\Pillars of Eternity"),
    Path(r"C:\Program Files\Steam\steamapps\common\Pillars of Eternity"),
)


class UnifiedWachterfederApp:
    def __init__(self, window: tk.Tk) -> None:
        self.window = window
        self.root_path = repository_root()
        self.pillars_result: DesktopAnalysisResult | None = None
        self.eet_result: EetSessionResult | None = None

        self.pillars_save_var = tk.StringVar()
        self.pillars_game_var = tk.StringVar()
        self.pillars_status_var = tk.StringVar(value="Bereit.")

        self.eet_save_var = tk.StringVar()
        self.eet_save_root_var = tk.StringVar()
        self.eet_game_var = tk.StringVar()
        self.eet_status_var = tk.StringVar(value="Bereit.")

        self.open_folder_var = tk.BooleanVar(value=True)
        self._configure_window()
        self._build_ui()
        self._load_defaults()

    def _configure_window(self) -> None:
        self.window.title("Wächterfeder · RPG-Chronik")
        self.window.geometry("940x720")
        self.window.minsize(820, 620)
        for name in ("TkDefaultFont", "TkTextFont", "TkMenuFont", "TkHeadingFont"):
            try:
                tkfont.nametofont(name).configure(family="Segoe UI", size=10)
            except tk.TclError:
                pass
        style = ttk.Style(self.window)
        try:
            style.theme_use("vista")
        except tk.TclError:
            pass
        style.configure("Title.TLabel", font=("Segoe UI Semibold", 22))
        style.configure("Primary.TButton", font=("Segoe UI Semibold", 11), padding=11)
        style.configure("Section.TLabelframe", padding=12)

    def _build_ui(self) -> None:
        outer = ttk.Frame(self.window, padding=20)
        outer.pack(fill="both", expand=True)
        ttk.Label(outer, text="Wächterfeder", style="Title.TLabel").pack(anchor="w")
        ttk.Label(
            outer,
            text="Eine Chronikmaschine, zwei Welten: Pillars of Eternity und Baldur's Gate EET.",
        ).pack(anchor="w", pady=(2, 14))

        notebook = ttk.Notebook(outer)
        notebook.pack(fill="both", expand=True)
        pillars_tab = ttk.Frame(notebook, padding=14)
        eet_tab = ttk.Frame(notebook, padding=14)
        notebook.add(pillars_tab, text="Pillars of Eternity")
        notebook.add(eet_tab, text="Baldur's Gate EET")
        self._build_pillars_tab(pillars_tab)
        self._build_eet_tab(eet_tab)

        ttk.Checkbutton(
            outer,
            text="Ergebnisordner nach erfolgreicher Auswertung öffnen",
            variable=self.open_folder_var,
        ).pack(anchor="w", pady=(12, 0))

    def _entry_row(self, parent: ttk.Frame, variable: tk.StringVar, browse_text: str, command) -> None:
        row = ttk.Frame(parent)
        row.pack(fill="x")
        ttk.Entry(row, textvariable=variable).pack(side="left", fill="x", expand=True)
        ttk.Button(row, text=browse_text, command=command).pack(side="left", padx=(8, 0))

    def _build_pillars_tab(self, tab: ttk.Frame) -> None:
        save_box = ttk.LabelFrame(tab, text="1. Pillars-Spielstand", style="Section.TLabelframe")
        save_box.pack(fill="x", pady=(0, 10))
        self._entry_row(save_box, self.pillars_save_var, "Datei wählen", self._browse_pillars_save)
        ttk.Button(save_box, text="Neueste Speicherung", command=self._select_newest_pillars).pack(anchor="w", pady=(8, 0))

        game_box = ttk.LabelFrame(tab, text="2. Pillars-Installation", style="Section.TLabelframe")
        game_box.pack(fill="x", pady=(0, 10))
        self._entry_row(game_box, self.pillars_game_var, "Ordner wählen", self._browse_pillars_game)
        ttk.Label(game_box, text="Nur lokal unter .wachterfeder/config.json gespeichert.").pack(anchor="w", pady=(7, 0))

        actions = ttk.Frame(tab)
        actions.pack(fill="x", pady=(2, 10))
        self.pillars_run_button = ttk.Button(actions, text="Pillars auswerten", style="Primary.TButton", command=self._start_pillars)
        self.pillars_run_button.pack(side="left", fill="x", expand=True)
        ttk.Button(actions, text="Ergebnisordner", command=lambda: self._open_folder(self.root_path / ".wachterfeder")).pack(side="left", padx=(8, 0))

        box = ttk.LabelFrame(tab, text="Status", style="Section.TLabelframe")
        box.pack(fill="both", expand=True)
        ttk.Label(box, textvariable=self.pillars_status_var, justify="left", anchor="nw", wraplength=820).pack(fill="both", expand=True)

    def _build_eet_tab(self, tab: ttk.Frame) -> None:
        root_box = ttk.LabelFrame(tab, text="1. EET-Saveordner", style="Section.TLabelframe")
        root_box.pack(fill="x", pady=(0, 10))
        self._entry_row(root_box, self.eet_save_root_var, "Ordner wählen", self._browse_eet_save_root)
        ttk.Label(root_box, text="Enthält Slots wie 000000001-Quick-Save; der neueste BALDUR.GAM wird automatisch gewählt.").pack(anchor="w", pady=(7, 0))

        save_box = ttk.LabelFrame(tab, text="2. Aktueller Save-Slot", style="Section.TLabelframe")
        save_box.pack(fill="x", pady=(0, 10))
        self._entry_row(save_box, self.eet_save_var, "Slot wählen", self._browse_eet_save)
        ttk.Button(save_box, text="Neuesten Save-Slot verwenden", command=self._select_newest_eet).pack(anchor="w", pady=(8, 0))

        game_box = ttk.LabelFrame(tab, text="3. EET/BG2EE-Installation", style="Section.TLabelframe")
        game_box.pack(fill="x", pady=(0, 10))
        self._entry_row(game_box, self.eet_game_var, "Ordner wählen", self._browse_eet_game)
        ttk.Label(game_box, text="Benötigt chitin.key und dialog.tlk. Pfad bleibt ausschließlich lokal.").pack(anchor="w", pady=(7, 0))

        actions = ttk.Frame(tab)
        actions.pack(fill="x", pady=(2, 10))
        self.eet_run_button = ttk.Button(actions, text="Baldur's Gate auswerten", style="Primary.TButton", command=self._start_eet)
        self.eet_run_button.pack(side="left", fill="x", expand=True)
        ttk.Button(actions, text="Ergebnisordner", command=lambda: self._open_folder(self.root_path / ".wachterfeder" / "eet")).pack(side="left", padx=(8, 0))

        combat = ttk.LabelFrame(tab, text="Kampfprotokoll", style="Section.TLabelframe")
        combat.pack(fill="x", pady=(0, 10))
        ttk.Label(
            combat,
            text=("Save-Deltas können Kämpfe indirekt über XP, HP, Gebiets- und Actor-Zustände zeigen. "
                  "Ein vollständiges zeilenweises Kampfprotokoll wird vom Save nicht dauerhaft mitgeführt. "
                  "Für echte Live-Kampfzeilen ist ein optionaler Laufzeit-Logger vorgesehen."),
            wraplength=820,
            justify="left",
        ).pack(anchor="w")

        box = ttk.LabelFrame(tab, text="Status", style="Section.TLabelframe")
        box.pack(fill="both", expand=True)
        ttk.Label(box, textvariable=self.eet_status_var, justify="left", anchor="nw", wraplength=820).pack(fill="both", expand=True)

    def _load_defaults(self) -> None:
        newest = newest_local_save()
        if newest:
            self.pillars_save_var.set(str(newest))
        config = self.root_path / ".wachterfeder" / "config.json"
        try:
            assets = read_local_config(config)
            self.pillars_game_var.set(str(assets.data_root))
        except (OSError, LocalGameError):
            for candidate in DEFAULT_PILLARS_GAME_PATHS:
                if candidate.is_dir():
                    self.pillars_game_var.set(str(candidate))
                    break

        eet_config = self.root_path / ".wachterfeder" / "eet" / "config.json"
        try:
            data = json.loads(eet_config.read_text(encoding="utf-8"))
            if data.get("game_root"):
                self.eet_game_var.set(str(data["game_root"]))
            if data.get("save_root"):
                self.eet_save_root_var.set(str(data["save_root"]))
        except (OSError, json.JSONDecodeError):
            pass
        if not self.eet_save_root_var.get():
            for candidate in eet_candidate_save_roots():
                if candidate.is_dir():
                    self.eet_save_root_var.set(str(candidate))
                    break
        self._select_newest_eet(silent=True)

    def _browse_pillars_save(self) -> None:
        selected = filedialog.askopenfilename(title="Pillars-Spielstand", filetypes=(("Pillars Save", "*.savegame"), ("Alle Dateien", "*.*")))
        if selected:
            self.pillars_save_var.set(selected)

    def _browse_pillars_game(self) -> None:
        selected = filedialog.askdirectory(title="Pillars-Installation")
        if selected:
            self.pillars_game_var.set(selected)

    def _select_newest_pillars(self) -> None:
        newest = newest_local_save()
        if newest:
            self.pillars_save_var.set(str(newest))
        else:
            messagebox.showwarning("Kein Save", "Kein Pillars-Spielstand gefunden.")

    def _browse_eet_save_root(self) -> None:
        selected = filedialog.askdirectory(title="EET save-Ordner")
        if selected:
            self.eet_save_root_var.set(selected)
            self._select_newest_eet(silent=True)

    def _browse_eet_save(self) -> None:
        initial = self.eet_save_root_var.get() or str(Path.home())
        selected = filedialog.askdirectory(title="EET Save-Slot auswählen", initialdir=initial)
        if selected:
            self.eet_save_var.set(selected)

    def _browse_eet_game(self) -> None:
        selected = filedialog.askdirectory(title="EET/BG2EE-Spielordner")
        if selected:
            self.eet_game_var.set(selected)

    def _newest_in_root(self, root: Path) -> Path | None:
        if not root.is_dir():
            return None
        games = [path for path in root.rglob("BALDUR.GAM") if path.is_file()]
        latest = max(games, key=lambda path: path.stat().st_mtime, default=None)
        return latest.parent if latest else None

    def _select_newest_eet(self, silent: bool = False) -> None:
        root_text = self.eet_save_root_var.get().strip()
        latest = self._newest_in_root(Path(root_text)) if root_text else newest_eet_save()
        if latest:
            self.eet_save_var.set(str(latest))
            if not root_text:
                self.eet_save_root_var.set(str(latest.parent))
            self.eet_status_var.set(f"Neuester Save-Slot:\n{latest}")
        elif not silent:
            messagebox.showwarning("Kein EET-Save", "Kein BALDUR.GAM unter dem gewählten save-Ordner gefunden.")

    def _start_pillars(self) -> None:
        save = self.pillars_save_var.get().strip()
        game = self.pillars_game_var.get().strip()
        if not save:
            messagebox.showerror("Save fehlt", "Bitte einen Pillars-Spielstand auswählen.")
            return
        self.pillars_run_button.configure(state="disabled", text="Pillars wird gelesen …")
        self.pillars_status_var.set("Save, Dialoge und Delta werden ausgewertet …")
        threading.Thread(target=self._run_pillars, args=(Path(save), Path(game) if game else None), daemon=True).start()

    def _run_pillars(self, save: Path, game: Path | None) -> None:
        try:
            result = analyse_pillars_save(save, game_path=game, language="de", root=self.root_path)
        except (OSError, LocalGameError, WachterfederError, ValueError) as exc:
            self.window.after(0, self._pillars_failed, str(exc))
            return
        except Exception as exc:
            self.window.after(0, self._pillars_failed, f"Unerwarteter Fehler: {exc}")
            return
        self.window.after(0, self._pillars_succeeded, result)

    def _pillars_failed(self, message: str) -> None:
        self.pillars_run_button.configure(state="normal", text="Pillars auswerten")
        self.pillars_status_var.set(f"Fehler:\n{message}")
        messagebox.showerror("Pillars-Auswertung fehlgeschlagen", message)

    def _pillars_succeeded(self, result: DesktopAnalysisResult) -> None:
        self.pillars_result = result
        self.pillars_run_button.configure(state="normal", text="Pillars erneut auswerten")
        delta_state = "Erste Vergleichsbasis" if result.initial_snapshot else "Keine Änderungen" if not result.has_changes else "Neue Änderungen erkannt"
        self.pillars_status_var.set(
            f"{result.player_name} · {result.scene_title} · {result.difficulty}\n{delta_state}\n\n"
            f"Neue Gespräche: {result.new_conversations}\nNeue Dialogknoten: {result.new_dialogue_nodes}\n"
            f"Geänderte Variablen: {result.changed_globals}\n\nDelta:\n{result.delta_path}"
        )
        if self.open_folder_var.get():
            self._open_folder(result.delta_path.parent)

    def _start_eet(self) -> None:
        save = self.eet_save_var.get().strip()
        game = self.eet_game_var.get().strip()
        if not save:
            messagebox.showerror("Save fehlt", "Bitte einen EET-Save-Slot auswählen.")
            return
        if not game:
            messagebox.showerror("Spielordner fehlt", "Bitte einmal die EET/BG2EE-Installation auswählen.")
            return
        self.eet_run_button.configure(state="disabled", text="EET wird gelesen …")
        self.eet_status_var.set("BALDUR.GAM + BALDUR.SAV, Party, Globals, Journal und Gebietszustände werden verglichen …")
        threading.Thread(target=self._run_eet, args=(Path(save), Path(game)), daemon=True).start()

    def _run_eet(self, save: Path, game: Path) -> None:
        try:
            result = analyse_session(save_path=save, game_path=game, language="de_DE", root=self.root_path)
            self._remember_eet_paths(game, save.parent)
        except (OSError, EetError, ValueError) as exc:
            self.window.after(0, self._eet_failed, str(exc))
            return
        except Exception as exc:
            self.window.after(0, self._eet_failed, f"Unerwarteter Fehler: {exc}")
            return
        self.window.after(0, self._eet_succeeded, result)

    def _remember_eet_paths(self, game: Path, save_root: Path) -> None:
        path = self.root_path / ".wachterfeder" / "eet" / "config.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        current = {}
        try:
            current = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            pass
        current.update({"schema_version": 3, "game_root": str(game.resolve()), "save_root": str(save_root.resolve()), "language": "de_DE"})
        path.write_text(json.dumps(current, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    def _eet_failed(self, message: str) -> None:
        self.eet_run_button.configure(state="normal", text="Baldur's Gate auswerten")
        self.eet_status_var.set(f"Fehler:\n{message}")
        messagebox.showerror("EET-Auswertung fehlgeschlagen", message)

    def _eet_succeeded(self, result: EetSessionResult) -> None:
        self.eet_result = result
        self.eet_run_button.configure(state="normal", text="Baldur's Gate erneut auswerten")
        delta_state = "Erste Vergleichsbasis" if result.initial_snapshot else "Keine Änderungen" if not result.has_changes else "Neue Änderungen erkannt"
        self.eet_status_var.set(
            f"Gebiet {result.current_area} · Party {result.party_members}\n{delta_state}\n\n"
            f"Geänderte GLOBALs: {result.changed_globals}\n"
            f"Geänderte Gebietsvariablen: {result.changed_area_variables}\n"
            f"Neue Journal-Einträge: {result.new_journal_entries}\n"
            f"Neue NPC-Gespräche: {result.npc_conversations}\n"
            f"Party-Fortschritt: {result.party_progression_changes}\n\n"
            f"Delta:\n{result.delta_path}"
        )
        if self.open_folder_var.get():
            self._open_folder(result.delta_path.parent)

    def _open_folder(self, folder: Path) -> None:
        folder.mkdir(parents=True, exist_ok=True)
        try:
            os.startfile(folder)  # type: ignore[attr-defined]
        except (AttributeError, OSError) as exc:
            messagebox.showerror("Ordner konnte nicht geöffnet werden", str(exc))


def main() -> int:
    window = tk.Tk()
    UnifiedWachterfederApp(window)
    window.mainloop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
