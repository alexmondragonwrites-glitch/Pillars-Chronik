from __future__ import annotations

import unittest

import tools.wachterfeder.multi_gui4 as base_ui
from tools.wachterfeder import ck3_refined
import tools.wachterfeder.multi_gui4_refined as refined_ui


class RefinedFourGameUiTests(unittest.TestCase):
    def test_refined_ck3_adapter_is_patched_into_four_game_shell(self) -> None:
        self.assertIs(base_ui.analyse_ck3_save, ck3_refined.analyse_ck3_save)
        self.assertIs(base_ui.find_rakaly, ck3_refined.find_rakaly)
        self.assertTrue(
            issubclass(
                refined_ui.RefinedFourGameWachterfederApp,
                refined_ui.enhanced_ui.EnhancedFourGameWachterfederApp,
            )
        )


if __name__ == "__main__":
    unittest.main()
