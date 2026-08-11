from __future__ import annotations

import unittest

from tools.wachterfeder.ck3 import Ck3AnalysisResult
from tools.wachterfeder.multi_gui4 import FourGameWachterfederApp


class MultiGui4Tests(unittest.TestCase):
    def test_four_game_shell_imports_without_creating_window(self) -> None:
        self.assertEqual(FourGameWachterfederApp.__name__, "FourGameWachterfederApp")
        self.assertTrue(hasattr(Ck3AnalysisResult, "__dataclass_fields__"))


if __name__ == "__main__":
    unittest.main()
