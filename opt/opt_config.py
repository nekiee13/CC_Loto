# -----------------------
# opt/opt_config.py
# -----------------------
from __future__ import annotations

import argparse
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Any, Dict, List, Optional, Set


def _default_ts_list() -> List[str]:
    return ["TS_1", "TS_2", "TS_3", "TS_4", "TS_5", "TS_6", "TS_7"]


def _default_payouts() -> Dict[int, float]:
    return {0: 0.0, 1: 0.0, 2: 0.0, 3: 10.0, 4: 50.0, 5: 2000.0, 6: 50000.0, 7: 1000000.0}


def _default_bandit_arms() -> List[Dict[str, Any]]:
    return [
        {"name": "A_k3_m10_b200_H3", "max_overlap_k": 3, "shortlist_m": 10, "beam": 200, "hit_threshold": 3},
        {"name": "B_k2_m10_b200_H3", "max_overlap_k": 2, "shortlist_m": 10, "beam": 200, "hit_threshold": 3},
        {"name": "C_k3_m12_b250_H3", "max_overlap_k": 3, "shortlist_m": 12, "beam": 250, "hit_threshold": 3},
        {"name": "D_k4_m12_b250_H3", "max_overlap_k": 4, "shortlist_m": 12, "beam": 250, "hit_threshold": 3},
        {"name": "E_k3_m10_b200_H4", "max_overlap_k": 3, "shortlist_m": 10, "beam": 200, "hit_threshold": 4},
    ]


def _norm_action(v: str) -> str:
    v = (v or "").strip().lower()
    return v if v in {"optimize", "forecast"} else "optimize"


def _norm_slice_mode(v: str) -> str:
    v = (v or "").strip().lower()
    return v if v in {"pos", "index"} else "pos"


@dataclass(frozen=True)
class OptConfig:
    # Paths
    output_dir: Path = Path("Output")
    reports_dir: Path = Path("Output") / "Reports"
    exports_dir: Path = Path("Output") / "Reports" / "Exports" / "StatGrid"
    opt_dir: Path = Path("Output") / "Reports" / "Optimization"
    state_dir: Path = Path("Output") / "Reports" / "Optimization" / "State"
    diag_dir: Path = Path("Output") / "Reports" / "Optimization" / "Diagnostics"
    diag_history_dir: Path = Path("Output") / "Reports" / "Optimization" / "Diagnostics" / "history"
    graphs_dir: Path = Path("Output") / "Reports" / "Optimization" / "Graphs"

    # Action
    action: str = "optimize"  # optimize|forecast

    # Run identifiers
    grid_run_id: str = "latest"

    # Slicing
    slice_mode: str = "pos"  # pos|index
    train_frac: Optional[float] = 0.8
    train_end_step: Optional[int] = None
    eval_start_step: Optional[int] = None
    eval_end_step: Optional[int] = None

    # Lottery & TS
    ts_list: List[str] = field(default_factory=_default_ts_list)

    # Economics
    ticket_cost_eur: float = 2.0
    payout_by_hits: Dict[int, float] = field(default_factory=_default_payouts)

    # Ticket policy
    max_tickets_per_draw: int = 5
    enforce_exact_k_tickets: bool = True
    max_overlap_k: int = 3

    # Candidate pool
    shortlist_m: int = 10
    beam: int = 200

    # Objective
    hit_threshold: int = 3

    # Conditional model
    model_type: str = "logreg_calibrated"
    abs_err_bins: int = 10
    rank_bins: int = 10
    freq_bins: int = 10
    gap_bins: int = 10

    # Cooccurrence (ticket-level)
    use_pair_triple_compat: bool = True
    pair_weight: float = 0.05
    triple_weight: float = 0.02

    # Calibration diagnostics
    calibration_bins: int = 10
    reliability_plot_title: str = "Reliability Plot (q_any vs empirical success)"

    # Resume
    resume: str = "none"  # none|latest|<path>|<dir>
    opt_run_id: str = ""
    seed: int = 123

    # Optimizers to run (only used when action=optimize)
    optimizer: str = "all"  # all|greedy|milp|bandit|evo

    # MILP
    milp_max_pool: int = 500

    # Bandit
    bandit_arms: List[Dict[str, Any]] = field(default_factory=_default_bandit_arms)

    # Evolutionary
    evo_generations: int = 25
    evo_pop_size: int = 22
    evo_fitness_sample_max_steps: int = 120

    # Progress reporting
    progress_every: int = 25
    progress_show_eta: bool = True
    quiet: bool = False

    # Versioning
    code_version: str = "2026-01-01_action_forecast_v2"

    @property
    def n_positions(self) -> int:
        return int(len(self.ts_list))

    def with_grid_run_id(self, run_id: str) -> "OptConfig":
        return replace(self, grid_run_id=str(run_id))

    def config_identity(self) -> Dict[str, Any]:
        """
        Deterministic identity used for resume validation.

        Notes:
        - action is intentionally NOT part of identity because a single run folder
          may be used for both optimize and forecast.
        - slice_mode IS part of identity so resume cannot silently change semantics.
        """
        return {
            "code_version": self.code_version,
            "ts_list": self.ts_list,
            "ticket_cost_eur": float(self.ticket_cost_eur),
            "payout_by_hits": self.payout_by_hits,
            "max_tickets_per_draw": int(self.max_tickets_per_draw),
            "enforce_exact_k_tickets": bool(self.enforce_exact_k_tickets),
            "conditional_model": {
                "type": self.model_type,
                "abs_err_bins": int(self.abs_err_bins),
                "rank_bins": int(self.rank_bins),
                "freq_bins": int(self.freq_bins),
                "gap_bins": int(self.gap_bins),
            },
            "cooccurrence": {
                "use_pair_triple_compat": bool(self.use_pair_triple_compat),
                "pair_weight": float(self.pair_weight),
                "triple_weight": float(self.triple_weight),
            },
            "calibration_bins": int(self.calibration_bins),
            "milp_max_pool": int(self.milp_max_pool),
            "bandit_arms": self.bandit_arms,
            "evo": {
                "evo_generations": int(self.evo_generations),
                "evo_pop_size": int(self.evo_pop_size),
                "evo_fitness_sample_max_steps": int(self.evo_fitness_sample_max_steps),
            },
            "slice_mode": str(self.slice_mode).lower().strip(),
        }

    def base_strategy_params(self) -> Dict[str, Any]:
        return {
            "shortlist_m": int(self.shortlist_m),
            "beam": int(self.beam),
            "max_overlap_k": int(self.max_overlap_k),
            "hit_threshold": int(self.hit_threshold),
        }

    def which_optimizers(self) -> Set[str]:
        o = str(self.optimizer).lower().strip()
        if o == "all":
            return {"greedy", "milp", "bandit", "evo"}
        return {o}


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="Lottery portfolio optimization + next-step forecast (conditional probability + calibration)."
    )

    # action
    p.add_argument(
        "--action",
        type=str,
        default="optimize",
        choices=["optimize", "forecast"],
        help="Run mode: optimize (backtest/selection on eval slice) or forecast (generate next-step tickets).",
    )

    # grid run provenance
    p.add_argument(
        "--run-id",
        type=str,
        default="latest",
        help="StatGrid run id folder name under Output/Reports/Exports/StatGrid, or 'latest'.",
    )

    # optimize strategy selection (ignored for --action forecast; kept for CLI consistency)
    p.add_argument("--optimizer", type=str, default="all", choices=["all", "greedy", "milp", "bandit", "evo"])

    # resume / run folder control
    p.add_argument("--resume", type=str, default="none", help="none|latest|<path-to-state.pkl.gz>|<state-dir>")
    p.add_argument("--opt-run-id", type=str, default="", help="Optional optimization run id for new runs.")

    # slicing
    p.add_argument(
        "--slice-mode",
        type=str,
        default="pos",
        choices=["pos", "index"],
        help="Interpret slicing steps as positional indices (pos) or literal dataset_index values (index).",
    )
    p.add_argument("--train-frac", type=float, default=0.8)
    p.add_argument("--train-end-step", type=int, default=None)
    p.add_argument("--eval-start-step", type=int, default=None)
    p.add_argument("--eval-end-step", type=int, default=None)

    # policy / search
    p.add_argument("--max-tickets", type=int, default=5)
    p.add_argument("--enforce-exact-k", type=str, default="on", choices=["on", "off"])
    p.add_argument("--max-overlap-k", type=int, default=3)
    p.add_argument("--shortlist-m", type=int, default=10)
    p.add_argument("--beam", type=int, default=200)
    p.add_argument("--hit-threshold", type=int, default=3)

    # conditional model bins
    p.add_argument("--abs-err-bins", type=int, default=10)
    p.add_argument("--rank-bins", type=int, default=10)
    p.add_argument("--freq-bins", type=int, default=10)
    p.add_argument("--gap-bins", type=int, default=10)

    # cooccurrence
    p.add_argument("--cooc", type=str, default="on", choices=["on", "off"])
    p.add_argument("--pair-weight", type=float, default=0.05)
    p.add_argument("--triple-weight", type=float, default=0.02)

    # evo
    p.add_argument("--evo-generations", type=int, default=25)
    p.add_argument("--evo-pop-size", type=int, default=22)

    # misc
    p.add_argument("--seed", type=int, default=123)

    # progress reporting (used by opt_strategies + Orchestrator)
    p.add_argument(
        "--progress-every",
        type=int,
        default=25,
        help="Print progress line every N eval steps per optimizer stage.",
    )
    p.add_argument(
        "--no-eta",
        action="store_true",
        help="Disable ETA estimation in progress reporting.",
    )
    p.add_argument(
        "--quiet",
        action="store_true",
        help="Reduce console output (still writes reports/files).",
    )

    return p.parse_args()


def build_config(args: argparse.Namespace) -> OptConfig:
    action = _norm_action(getattr(args, "action", "optimize"))
    slice_mode = _norm_slice_mode(getattr(args, "slice_mode", "pos"))

    return OptConfig(
        # action
        action=str(action),

        # provenance
        grid_run_id=str(args.run_id),
        optimizer=str(args.optimizer),

        # resume/run id
        resume=str(args.resume),
        opt_run_id=str(args.opt_run_id),

        # slicing
        slice_mode=str(slice_mode),
        train_frac=float(args.train_frac) if args.train_frac is not None else None,
        train_end_step=args.train_end_step,
        eval_start_step=args.eval_start_step,
        eval_end_step=args.eval_end_step,

        # policy / search
        max_tickets_per_draw=int(args.max_tickets),
        enforce_exact_k_tickets=(str(args.enforce_exact_k).lower() == "on"),
        max_overlap_k=int(args.max_overlap_k),
        shortlist_m=int(args.shortlist_m),
        beam=int(args.beam),
        hit_threshold=int(args.hit_threshold),

        # conditional model bins
        abs_err_bins=int(args.abs_err_bins),
        rank_bins=int(args.rank_bins),
        freq_bins=int(args.freq_bins),
        gap_bins=int(args.gap_bins),

        # cooccurrence
        use_pair_triple_compat=(str(args.cooc).lower() == "on"),
        pair_weight=float(args.pair_weight),
        triple_weight=float(args.triple_weight),

        # evo
        evo_generations=int(args.evo_generations),
        evo_pop_size=int(args.evo_pop_size),

        # misc
        seed=int(args.seed),

        # progress reporting
        progress_every=int(args.progress_every),
        progress_show_eta=(not bool(args.no_eta)),
        quiet=bool(args.quiet),
    )
