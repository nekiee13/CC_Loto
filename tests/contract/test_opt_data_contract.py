# -----------------------
# tests/contract/test_opt_data_contract.py
# -----------------------
from __future__ import annotations

import unittest

import pandas as pd

from tests._cfg import TestOptConfig
from tests._typing import as_opt_config
from tests._util import TempOutputRoot, seed_everything
from tests._builders import SyntheticGridSpec, make_synthetic_statgrid, write_statgrid_run_shards


class TestOptDataContract(unittest.TestCase):
    def setUp(self) -> None:
        seed_everything(12345)

    def test_load_statgrid_run_enforces_required_cols_and_types(self) -> None:
        with TempOutputRoot() as root:
            spec = SyntheticGridSpec(n_steps=6)
            df = make_synthetic_statgrid(spec)

            exports_dir = root / "Output" / "Reports" / "Exports" / "StatGrid"
            run_id = "testrun_contract_001"
            write_statgrid_run_shards(df, exports_dir / run_id, parts=2)

            cfg0 = TestOptConfig(exports_dir=str(exports_dir), ts_list=list(spec.ts_list))
            cfg = as_opt_config(cfg0)

            from opt.opt_data import load_statgrid_run, REQUIRED_COLS  # type: ignore

            grid = load_statgrid_run(cfg, run_id)
            self.assertFalse(grid.empty)
            self.assertTrue(REQUIRED_COLS.issubset(set(grid.columns)))

            # Validate dtypes after coercion
            self.assertTrue(pd.api.types.is_integer_dtype(grid["dataset_index"]))
            self.assertTrue(pd.api.types.is_integer_dtype(grid["rounding_id"]))
            self.assertTrue(pd.api.types.is_integer_dtype(grid["rounded"]))
            self.assertTrue(pd.api.types.is_integer_dtype(grid["true"]))
            self.assertTrue(pd.api.types.is_integer_dtype(grid["hit"]))
            self.assertTrue(pd.api.types.is_float_dtype(grid["pred"]))
            self.assertTrue(pd.api.types.is_float_dtype(grid["abs_err"]))

    def test_missing_required_cols_raises(self) -> None:
        with TempOutputRoot() as root:
            spec = SyntheticGridSpec(n_steps=3)
            df = make_synthetic_statgrid(spec)

            df = df.drop(columns=["abs_err"])

            exports_dir = root / "Output" / "Reports" / "Exports" / "StatGrid"
            run_id = "testrun_contract_002"
            write_statgrid_run_shards(df, exports_dir / run_id, parts=1)

            cfg0 = TestOptConfig(exports_dir=str(exports_dir), ts_list=list(spec.ts_list))
            cfg = as_opt_config(cfg0)

            from opt.opt_data import load_statgrid_run  # type: ignore

            with self.assertRaises(ValueError):
                _ = load_statgrid_run(cfg, run_id)

    def test_empty_grid_raises(self) -> None:
        with TempOutputRoot() as root:
            exports_dir = root / "Output" / "Reports" / "Exports" / "StatGrid"
            run_id = "testrun_contract_003"
            run_dir = exports_dir / run_id
            run_dir.mkdir(parents=True, exist_ok=True)

            empty = pd.DataFrame(
                columns=[
                    "dataset_index",
                    "ts",
                    "model",
                    "rounding_id",
                    "rounded",
                    "true",
                    "hit",
                    "pred",
                    "abs_err",
                ]
            )
            p = run_dir / "grid_part_000.csv.gz"
            empty.to_csv(p, index=False, compression="gzip", encoding="utf-8")

            cfg0 = TestOptConfig(exports_dir=str(exports_dir), ts_list=["TS_1", "TS_2", "TS_3", "TS_4", "TS_5", "TS_6", "TS_7"])
            cfg = as_opt_config(cfg0)

            from opt.opt_data import load_statgrid_run  # type: ignore

            with self.assertRaises(ValueError):
                _ = load_statgrid_run(cfg, run_id)


if __name__ == "__main__":
    unittest.main()
