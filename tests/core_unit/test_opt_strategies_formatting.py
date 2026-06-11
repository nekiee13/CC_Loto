# -----------------------
# tests/core_unit/test_opt_strategies_formatting.py
# -----------------------
import unittest

from tests._util import seed_everything


class TestOptStrategiesFormatting(unittest.TestCase):
    def setUp(self) -> None:
        seed_everything(12345)

    def test_fmt_hms(self) -> None:
        from opt.opt_strategies import _fmt_hms  # type: ignore

        self.assertEqual(_fmt_hms(0.0), "0:00")
        self.assertEqual(_fmt_hms(59.0), "0:59")
        self.assertEqual(_fmt_hms(61.0), "1:01")
        self.assertEqual(_fmt_hms(3661.0), "1:01:01")
