#!/usr/bin/env python3
"""Unified Wächterfeder UI with optional EEex runtime combat ingestion."""
from __future__ import annotations

import sys
import tkinter as tk
from pathlib import Path

# When Python executes this file by path (the normal Windows .bat launcher),
# sys.path starts in tools/wachterfeder instead of at the repository root.
# Add the checkout root explicitly so package imports behave exactly like
# ``python -m ...`` and the GitHub test environment.
REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
if str(REPOSITORY_ROOT) not in sys.path:
    sys.path.insert(0, str(REPOSITORY_ROOT))

import tools.wachterfeder.unified_gui as gui_module
from tools.wachterfeder.eet_session_runtime import analyse_session

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
