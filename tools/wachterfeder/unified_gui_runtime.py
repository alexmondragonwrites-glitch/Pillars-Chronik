#!/usr/bin/env python3
"""Unified Wächterfeder UI with optional EEex runtime combat ingestion."""
from __future__ import annotations

import tkinter as tk

try:
    import tools.wachterfeder.unified_gui as gui_module
    from tools.wachterfeder.eet_session_runtime import analyse_session
except ModuleNotFoundError:  # direct execution from tools/wachterfeder
    import unified_gui as gui_module
    from eet_session_runtime import analyse_session

# unified_gui resolves this module-global function when the EET worker starts.
gui_module.analyse_session = analyse_session
UnifiedWachterfederApp = gui_module.UnifiedWachterfederApp


def main() -> int:
    window = tk.Tk()
    UnifiedWachterfederApp(window)
    window.mainloop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
