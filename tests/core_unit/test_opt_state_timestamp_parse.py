# -----------------------
# tests/core_unit/test_opt_state_timestamp_parse.py
# -----------------------
import unittest

from tests._util import seed_everything


class TestOptStateTimestampParse(unittest.TestCase):
    def setUp(self) -> None:
        seed_everything(12345)

    def test_try_parse_opt_timestamp(self) -> None:
        from opt.opt_state import _try_parse_opt_timestamp  # type: ignore

        ts = _try_parse_opt_timestamp("opt_20250102_030405")
        self.assertIsNotNone(ts)

        ts2 = _try_parse_opt_timestamp("not_an_opt_dir")
        self.assertIsNone(ts2)
