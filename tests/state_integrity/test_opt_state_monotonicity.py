# -----------------------
# tests/state_integrity/test_opt_state_monotonicity.py
# -----------------------
from __future__ import annotations

import unittest
from pathlib import Path
from typing import Any, Dict

from tests._util import TempOutputRoot, seed_everything
from tests._cfg import TestOptConfig
from tests._typing import as_opt_config


class TestOptStateMonotonicity(unittest.TestCase):
    def setUp(self) -> None:
        seed_everything(12345)

    def _make_cfg(self, root: Path) -> TestOptConfig:
        exports_dir = root / "Output" / "Reports" / "Exports" / "StatGrid"
        opt_dir = root / "Output" / "Reports" / "Optimization"
        state_dir = opt_dir / "State"
        diag_dir = opt_dir / "Diagnostics"
        diag_history_dir = diag_dir / "history"
        graphs_dir = opt_dir / "Graphs"

        for d in [exports_dir, opt_dir, state_dir, diag_dir, diag_history_dir, graphs_dir]:
            d.mkdir(parents=True, exist_ok=True)

        return TestOptConfig(
            exports_dir=str(exports_dir),
            ts_list=["TS_1", "TS_2", "TS_3", "TS_4", "TS_5", "TS_6", "TS_7"],
            opt_dir=opt_dir,
            state_dir=state_dir,
            diag_dir=diag_dir,
            diag_history_dir=diag_history_dir,
            graphs_dir=graphs_dir,
            resume="none",
            opt_run_id="",
            code_version="qa-test",
            seed=12345,
        )

    def test_save_state_writes_files_and_next_pos_monotonic(self) -> None:
        with TempOutputRoot() as root:
            cfg0 = self._make_cfg(root)
            cfg = as_opt_config(cfg0)

            from opt.opt_state import save_state  # type: ignore

            opt_run_id = "opt_20990101_000000"
            state: Dict[str, Any] = {
                "resuming": False,
                "opt_run_id": opt_run_id,
                "created_at": "2099-01-01T00:00:00",
                "updated_at": "2099-01-01T00:00:00",
                "grid_run_id": "grid_20990101_000000",
                "grid_fingerprint": {"steps_hash": "a", "schema_hash": "b", "sample_true_hash": "c", "n_steps": 12},
                "slice": {"slice_mode": "pos", "train_end_step_pos": 8},
                "config_identity": cfg0.config_identity(),
                "seed": int(cfg0.seed),
                "stages": {"greedy": {"next_pos": 0, "rows": [], "diag_rows": []}},
                "results": {},
                "notes": [],
            }

            save_state(cfg, opt_run_id, state)

            pkl_path = cfg0.state_dir / opt_run_id / "state.pkl.gz"
            json_path = cfg0.state_dir / opt_run_id / "state.json"
            self.assertTrue(pkl_path.exists())
            self.assertTrue(json_path.exists())

            state["stages"]["greedy"]["next_pos"] = 3
            save_state(cfg, opt_run_id, state)
            state["stages"]["greedy"]["next_pos"] = 5
            save_state(cfg, opt_run_id, state)

            self.assertGreaterEqual(int(state["stages"]["greedy"]["next_pos"]), 5)

    def test_load_state_or_init_none_and_latest(self) -> None:
        with TempOutputRoot() as root:
            cfg0 = self._make_cfg(root)
            cfg = as_opt_config(cfg0)

            from opt.opt_state import load_state_or_init, save_state  # type: ignore

            grid_run_id = "grid_20990101_000001"
            grid_fingerprint = {"steps_hash": "a", "schema_hash": "b", "sample_true_hash": "c", "n_steps": 12}
            slice_info = {"slice_mode": "pos", "train_end_step_pos": 8, "eval_start_step_pos": 9, "eval_end_step_pos": 12}

            cfg0.resume = "none"
            opt_run_id, state = load_state_or_init(cfg, grid_run_id, grid_fingerprint, slice_info)
            self.assertFalse(bool(state.get("resuming", False)))
            self.assertEqual(str(state.get("grid_run_id")), grid_run_id)

            state.setdefault("stages", {}).setdefault("greedy", {"next_pos": 0, "rows": [], "diag_rows": []})
            state["stages"]["greedy"]["next_pos"] = 2
            save_state(cfg, opt_run_id, state)

            cfg0.resume = "latest"
            opt_run_id2, state2 = load_state_or_init(cfg, grid_run_id, grid_fingerprint, slice_info)
            self.assertTrue(bool(state2.get("resuming", False)))
            self.assertEqual(str(state2.get("grid_run_id")), grid_run_id)
            self.assertEqual(str(opt_run_id2), str(opt_run_id))
            self.assertEqual(int(state2["stages"]["greedy"]["next_pos"]), 2)


if __name__ == "__main__":
    unittest.main()
