#!/usr/bin/env python3
"""Small Tk desktop interface for Wächterfeder."""
from __future__ import annotations

import os
import threading
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

try:
    from tools.wachterfeder.desktop import (
        DesktopAnalysisResult,
        analyse_savegame,
        newest_local_save,
        repository_root,
    )
    from tools.wachterfeder.local_game import LocalGameError, read_local_config
    from tools.wachterfeder.wachterfeder import WachterfederError
except ModuleNotFoundError:  # Direct execution from tools/wachterfeder.
    from desktop import (
        DesktopAnalysisResult,
        analyse_savegame,
        newest_local_save,
        repository_root,
    )
    from local_game import LocalGameError, read_local_config
    from wachterfeder import WachterfederError


DEFAULT_GAME_PATHS = (
    Path(r"E:\SteamLibrary\steamapps\common\Pillars of Eternity"),
    Path(r"C:\Program Files (x86)\Steam\steamapps\common\Pillars of Eternity"),
    Path(r"C:\Program Files\Steam\steamapps\common\Pillars of Eternity"),
)


class WachterfederApp:
    def __init__(self, window: tk.Tk) -> None:
        self.window = window
        self.root_path = repository_root()
        self.result: DesktopAnalysisResult | None = None
        self.save_var = tk.StringVar()
        self.game_var = tk.StringVar()
        self.status_var = tk.StringVar(value="Bereit. Wähle einen Spielstand aus.")
        self.open_folder_var = tk.BooleanVar(value=True)

        self._configure_window()
        self._build_ui()
        self._load_defaults()

    def _configure_window(self) -> None:
        self.window.title("Wächterfeder")
        self.window.geometry("820x560")
        self.window.minsize(720, 500)
        self.window.option_add("*Font", "Segoe UI 10")

        style = ttk.Style(self.window)
        try:
            style.theme_use("vista")
        except tk.TclError:
            pass
        style.configure("Title.TLabel", font=("Segoe UI Semibold", 22))
        style.configure("Subtitle.TLabel", font=("Segoe UI", 10))
        style.configure("Primary.TButton", font=("Segoe UI Semibold", 12), padding=12)
        style.configure("Section.TLabelframe", padding=12)

    def _build_ui(self) -> None:
        outer = ttk.Frame(self.window, padding=22)
        outer.pack(fill="both", expand=True)

        ttk.Label(outer, text="Wächterfeder", style="Title.TLabel").pack(anchor="w")
        ttk.Label(
            outer,
            text="Serins Spielstand mit einem Klick lesen, lokalisieren und archivieren.",
            style="Subtitle.TLabel",
        ).pack(anchor="w", pady=(2, 18))

        save_box = ttk.LabelFrame(outer, text="1. Spielstand", style="Section.TLabelframe")
        save_box.pack(fill="x", pady=(0, 12))
        save_row = ttk.Frame(save_box)
        save_row.pack(fill="x")
        ttk.Entry(save_row, textvariable=self.save_var).pack(side="left", fill="x", expand=True)
        ttk.Button(save_row, text="Durchsuchen", command=self._browse_save).pack(side="left", padx=(8, 0))
        ttk.Button(save_box, text="Neueste Speicherung verwenden", command=self._select_newest).pack(anchor="w", pady=(8, 0))

        game_box = ttk.LabelFrame(outer, text="2. Lokale Pillars-Installation", style="Section.TLabelframe")
        game_box.pack(fill="x", pady=(0, 12))
        game_row = ttk.Frame(game_box)
        game_row.pack(fill="x")
        ttk.Entry(game_row, textvariable=self.game_var).pack(side="left", fill="x", expand=True)
        ttk.Button(game_row, text="Ordner wählen", command=self._browse_game).pack(side="left", padx=(8, 0))
        ttk.Label(
            game_box,
            text="Der Pfad wird nur lokal in .wachterfeder/config.json gespeichert.",
        ).pack(anchor="w", pady=(8, 0))

        action_box = ttk.Frame(outer)
        action_box.pack(fill="x", pady=(4, 14))
        self.run_button = ttk.Button(
            action_box,
            text="Serin auswerten",
            style="Primary.TButton",
            command=self._start_analysis,
        )
        self.run_button.pack(side="left", fill="x", expand=True)
        self.open_button = ttk.Button(
            action_box,
            text="Ergebnisordner öffnen",
            command=self._open_result_folder,
            state="disabled",
        )
        self.open_button.pack(side="left", padx=(10, 0))

        ttk.Checkbutton(
            outer,
            text="Ergebnisordner nach erfolgreicher Auswertung öffnen",
            variable=self.open_folder_var,
        ).pack(anchor="w", pady=(0, 12))

        status_box = ttk.LabelFrame(outer, text="Status", style="Section.TLabelframe")
        status_box.pack(fill="both", expand=True)
        self.status_label = ttk.Label(
            status_box,
            textvariable=self.status_var,
            justify="left",
            anchor="nw",
            wraplength=735,
        )
        self.status_label.pack(fill="both", expand=True)

    def _load_defaults(self) -> None:
        newest = newest_local_save()
        if newest:
            self.save_var.set(str(newest))

        config = self.root_path / ".wachterfeder" / "config.json"
        try:
            assets = read_local_config(config)
            self.game_var.set(str(assets.data_root))
            return
        except (OSError, LocalGameError):
            pass

        for candidate in DEFAULT_GAME_PATHS:
            if candidate.is_dir():
                self.game_var.set(str(candidate))
                return

    def _browse_save(self) -> None:
        current = Path(self.save_var.get()).parent if self.save_var.get() else Path.home()
        selected = filedialog.askopenfilename(
            title="Pillars-Spielstand auswählen",
            initialdir=current if current.is_dir() else Path.home(),
            filetypes=(("Pillars-Spielstände", "*.savegame"), ("Alle Dateien", "*.*")),
        )
        if selected:
            self.save_var.set(selected)

    def _browse_game(self) -> None:
        current = Path(self.game_var.get()) if self.game_var.get() else Path.home()
        selected = filedialog.askdirectory(
            title="Pillars-Ordner oder conversations-Ordner auswählen",
            initialdir=current if current.is_dir() else Path.home(),
        )
        if selected:
            self.game_var.set(selected)

    def _select_newest(self) -> None:
        newest = newest_local_save()
        if newest is None:
            messagebox.showwarning(
                "Kein Spielstand gefunden",
                "Im üblichen Windows-Speicherordner wurde kein .savegame gefunden.",
            )
            return
        self.save_var.set(str(newest))
        self.status_var.set(f"Neuester Spielstand ausgewählt:\n{newest}")

    def _start_analysis(self) -> None:
        save_text = self.save_var.get().strip()
        game_text = self.game_var.get().strip()
        if not save_text:
            messagebox.showerror("Spielstand fehlt", "Bitte wähle einen .savegame-Spielstand aus.")
            return
        if not game_text and not (self.root_path / ".wachterfeder" / "config.json").is_file():
            messagebox.showerror("Pillars-Ordner fehlt", "Bitte wähle einmal deine lokale Pillars-Installation aus.")
            return

        self.run_button.configure(state="disabled", text="Wächterfeder liest …")
        self.open_button.configure(state="disabled")
        self.status_var.set("Arbeitskopie erstellen, Save lesen und deutsche Dialoge zuordnen …")
        worker = threading.Thread(
            target=self._run_analysis,
            args=(Path(save_text), Path(game_text) if game_text else None),
            daemon=True,
        )
        worker.start()

    def _run_analysis(self, savegame: Path, game_path: Path | None) -> None:
        try:
            result = analyse_savegame(
                savegame,
                game_path=game_path,
                language="de",
                root=self.root_path,
            )
        except (OSError, LocalGameError, WachterfederError, ValueError) as exc:
            self.window.after(0, self._analysis_failed, str(exc))
            return
        except Exception as exc:  # Keep the desktop UI recoverable for unexpected parser errors.
            self.window.after(0, self._analysis_failed, f"Unerwarteter Fehler: {exc}")
            return
        self.window.after(0, self._analysis_succeeded, result)

    def _analysis_failed(self, message: str) -> None:
        self.run_button.configure(state="normal", text="Serin auswerten")
        self.status_var.set(f"Auswertung fehlgeschlagen:\n{message}")
        messagebox.showerror("Wächterfeder konnte den Save nicht lesen", message)

    def _analysis_succeeded(self, result: DesktopAnalysisResult) -> None:
        self.result = result
        self.run_button.configure(state="normal", text="Serin erneut auswerten")
        self.open_button.configure(state="normal")
        warning_text = ""
        if result.warnings:
            warning_text = "\n\nHinweise:\n- " + "\n- ".join(result.warnings)
        self.status_var.set(
            f"Fertig: {result.player_name} · {result.scene_title} · {result.difficulty}\n\n"
            f"Dialoge zugeordnet: {result.matched_conversations}\n"
            f"Nicht gefunden: {result.unresolved_conversations}\n"
            f"Markierte Nodes: {result.marked_nodes}\n\n"
            f"Aktueller Report:\n{result.report_path}\n\n"
            f"Historische Kopie:\n{result.history_report_path}"
            f"{warning_text}"
        )
        if self.open_folder_var.get():
            self._open_result_folder()

    def _open_result_folder(self) -> None:
        folder = self.result.report_path.parent if self.result else self.root_path / ".wachterfeder"
        folder.mkdir(parents=True, exist_ok=True)
        try:
            os.startfile(folder)  # type: ignore[attr-defined]
        except (AttributeError, OSError) as exc:
            messagebox.showerror("Ordner konnte nicht geöffnet werden", str(exc))


def main() -> int:
    window = tk.Tk()
    WachterfederApp(window)
    window.mainloop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
