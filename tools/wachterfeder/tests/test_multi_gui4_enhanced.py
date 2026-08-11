from __future__ import annotations

import unittest

import tools.wachterfeder.multi_gui4 as base_ui
from tools.wachterfeder import ck3_enhanced_runtime
import tools.wachterfeder.multi_gui4_enhanced as enhanced_ui


class EnhancedFourGameUiTests(unittest.TestCase):
    def test_ck3_adapter_is_patched_into_four_game_shell(self) -> None:
        self.assertIs(base_ui.analyse_ck3_save, ck3_enhanced_runtime.analyse_ck3_save)
        self.assertIs(base_ui.find_rakaly, ck3_enhanced_runtime.find_rakaly)
        self.assertTrue(issubclass(enhanced_ui.EnhancedFourGameWachterfederApp, base_ui.FourGameWachterfederApp))


if __name__ == "__main__":
    unittest.main()
