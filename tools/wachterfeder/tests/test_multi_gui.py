from __future__ import annotations

import unittest

from tools.wachterfeder.multi_gui import GAME_TABS, delta_state


class MultiGuiTests(unittest.TestCase):
    def test_three_game_tabs_are_registered(self) -> None:
        self.assertEqual(
            GAME_TABS,
            ("Pillars of Eternity", "Baldur's Gate EET", "Rogue Trader"),
        )

    def test_delta_state_labels(self) -> None:
        self.assertEqual(delta_state(True, True), "Erste Vergleichsbasis erstellt")
        self.assertEqual(
            delta_state(False, True),
            "Änderungen seit der letzten Auswertung erkannt",
        )
        self.assertEqual(delta_state(False, False), "Keine neuen Änderungen")


if __name__ == "__main__":
    unittest.main()
