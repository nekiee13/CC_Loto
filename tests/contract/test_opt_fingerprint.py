# -----------------------
# tests/contract/test_opt_fingerprint.py
# -----------------------
from __future__ import annotations

import unittest

import pandas as pd

from tests._cfg import TestOptConfig
from tests._typing import as_opt_config
from tests._util import TempOutputRoot, seed_everything
from tests._builders import SyntheticGridSpec, make_synthetic_statgrid, write_statgrid_run_shards


class TestOptFingerprint(unittest.TestCase):
    def setUp(self) -> None:
        seed_everything(12345)

    def test_fingerprint_deterministic(self) -> None:
        with TempOutputRoot() as root:
            spec = SyntheticGridSpec(n_steps=10)
            df = make_synthetic_statgrid(spec)

            exports_dir = root / "Output" / "Reports" / "Exports" / "StatGrid"
            run_id = "testrun_fp_001"
            write_statgrid_run_shards(df, exports_dir / run_id, parts=2)

            cfg0 = TestOptConfig(exports_dir=str(exports_dir), ts_list=list(spec.ts_list))
            cfg = as_opt_config(cfg0)

            from opt.opt_data import load_statgrid_run, compute_grid_fingerprint  # type: ignore

            g1 = load_statgrid_run(cfg, run_id)
            g2 = load_statgrid_run(cfg, run_id)

            fp1 = compute_grid_fingerprint(g1, ts_list=cfg0.ts_list, sample_steps=3)
            fp2 = compute_grid_fingerprint(g2, ts_list=cfg0.ts_list, sample_steps=3)

            self.assertEqual(fp1["steps_hash"], fp2["steps_hash"])
            self.assertEqual(fp1["schema_hash"], fp2["schema_hash"])
            self.assertEqual(fp1["sample_true_hash"], fp2["sample_true_hash"])

    def test_sample_true_inconsistency_affects_hash(self) -> None:
        spec = SyntheticGridSpec(n_steps=12)
        df = make_synthetic_statgrid(spec)

        df2 = df.copy()
        mask = (df2["dataset_index"] == 1) & (df2["ts"] == "TS_1")
        bad = df2[mask].iloc[:1].copy()
        if not bad.empty:
            bad.loc[:, "true"] = int(bad["true"].iloc[0]) + 999
            df2 = pd.concat([df2, bad], axis=0, ignore_index=True)

        with TempOutputRoot() as root:
            exports_dir = root / "Output" / "Reports" / "Exports" / "StatGrid"
            run_id_a = "testrun_fp_002a"
            run_id_b = "testrun_fp_002b"

            write_statgrid_run_shards(df, exports_dir / run_id_a, parts=2)
            write_statgrid_run_shards(df2, exports_dir / run_id_b, parts=2)

            cfg0 = TestOptConfig(exports_dir=str(exports_dir), ts_list=list(spec.ts_list))
            cfg = as_opt_config(cfg0)

            from opt.opt_data import load_statgrid_run, compute_grid_fingerprint  # type: ignore

            ga = load_statgrid_run(cfg, run_id_a)
            gb = load_statgrid_run(cfg, run_id_b)

            fpa = compute_grid_fingerprint(ga, ts_list=cfg0.ts_list, sample_steps=3)
            fpb = compute_grid_fingerprint(gb, ts_list=cfg0.ts_list, sample_steps=3)

            self.assertNotEqual(fpa["sample_true_hash"], fpb["sample_true_hash"])


if __name__ == "__main__":
    unittest.main()
