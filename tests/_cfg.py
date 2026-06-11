# -----------------------
# tests/_cfg.py
# -----------------------
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List


@dataclass
class TestOptConfig:
    # --- StatGrid / opt_data ---
    exports_dir: str
    ts_list: List[str] = field(default_factory=lambda: ["TS_1","TS_2","TS_3","TS_4","TS_5","TS_6","TS_7"])

    # --- directories (Path; required by opt_state/opt_diagnostics) ---
    opt_dir: Path = Path(".")
    state_dir: Path = Path(".")
    diag_dir: Path = Path(".")
    diag_history_dir: Path = Path(".")
    graphs_dir: Path = Path(".")

    # --- resume / run identity ---
    resume: str = "none"
    opt_run_id: str = ""  # if empty and resume=none, load_state_or_init builds one

    # --- deterministic config identity ---
    code_version: str = "test"
    seed: int = 12345

    # --- calibration / diagnostics ---
    calibration_bins: int = 10
    reliability_plot_title: str = "DynaMix Reliability"

    # --- feature binning (used by opt_engine -> opt_features) ---
    abs_err_bins: int = 5
    rank_bins: int = 5
    freq_bins: int = 5
    gap_bins: int = 5

    # --- ticket policy / economics (used by strategies) ---
    max_tickets_per_draw: int = 3
    enforce_exact_k_tickets: bool = True
    ticket_cost_eur: float = 1.0
    payout_by_hits: Dict[int, float] = field(default_factory=lambda: {
        0: 0.0, 1: 0.0, 2: 0.0, 3: 5.0, 4: 20.0, 5: 100.0, 6: 1000.0, 7: 100000.0
    })

    # --- progress/reporting ---
    quiet: bool = True
    progress_every: int = 999999
    progress_show_eta: bool = False

    # --- MILP pool limit ---
    milp_max_pool: int = 250

    # --- bandit ---
    bandit_arms: List[Dict[str, Any]] = field(default_factory=lambda: [
        {"name": "A", "max_overlap_k": 2, "shortlist_m": 6, "beam": 50, "hit_threshold": 3},
        {"name": "B", "max_overlap_k": 1, "shortlist_m": 5, "beam": 40, "hit_threshold": 3},
    ])

    # --- compatibility ---
    use_pair_triple_compat: bool = False
    pair_weight: float = 0.0
    triple_weight: float = 0.0

    def config_identity(self) -> Dict[str, Any]:
        """
        Deterministic identity used for resume gating.
        """
        return {
            "code_version": self.code_version,
            "seed": int(self.seed),
            "ts_list": list(self.ts_list),
            "bins": {
                "abs_err_bins": int(self.abs_err_bins),
                "rank_bins": int(self.rank_bins),
                "freq_bins": int(self.freq_bins),
                "gap_bins": int(self.gap_bins),
            },
            "ticket_policy": {
                "max_tickets_per_draw": int(self.max_tickets_per_draw),
                "enforce_exact_k_tickets": bool(self.enforce_exact_k_tickets),
            },
            "compat": {
                "use_pair_triple_compat": bool(self.use_pair_triple_compat),
                "pair_weight": float(self.pair_weight),
                "triple_weight": float(self.triple_weight),
            },
            "calibration_bins": int(self.calibration_bins),
        }

    def base_strategy_params(self) -> Dict[str, Any]:
        return {"shortlist_m": 6, "beam": 50, "max_overlap_k": 2, "hit_threshold": 3}
