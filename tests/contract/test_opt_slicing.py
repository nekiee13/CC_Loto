# -----------------------
# tests/contract/test_opt_slicing.py
# -----------------------
import unittest

from tests._util import seed_everything


class TestOptSlicing(unittest.TestCase):
    def setUp(self) -> None:
        seed_everything(12345)

    def test_pos_mode_off_by_one(self) -> None:
        from opt.opt_data import resolve_slices  # type: ignore

        steps = [10, 20, 30, 40, 50]
        out = resolve_slices(
            steps,
            train_frac=None,
            train_end_step=3,     # 1-based position => 10,20,30
            eval_start_step=4,    # => 40
            eval_end_step=5,      # => 50
            slice_mode="pos",
        )
        self.assertEqual(out["train_steps_dataset_index"], [10, 20, 30])
        self.assertEqual(out["eval_steps_dataset_index"], [40, 50])

    def test_index_mode_inclusive_bounds(self) -> None:
        from opt.opt_data import resolve_slices  # type: ignore

        steps = [10, 20, 30, 40, 50]
        out = resolve_slices(
            steps,
            train_frac=None,
            train_end_step=30,     # dataset_index <= 30
            eval_start_step=40,    # dataset_index >= 40
            eval_end_step=50,      # dataset_index <= 50
            slice_mode="index",
        )
        self.assertEqual(out["train_steps_dataset_index"], [10, 20, 30])
        self.assertEqual(out["eval_steps_dataset_index"], [40, 50])

    def test_train_frac_behavior(self) -> None:
        from opt.opt_data import resolve_slices  # type: ignore

        steps = list(range(1, 11))  # 10 steps
        out = resolve_slices(
            steps,
            train_frac=0.8,
            train_end_step=None,
            eval_start_step=None,
            eval_end_step=None,
            slice_mode="pos",
        )
        self.assertEqual(len(out["train_steps_dataset_index"]), 8)
        self.assertEqual(len(out["eval_steps_dataset_index"]), 2)
