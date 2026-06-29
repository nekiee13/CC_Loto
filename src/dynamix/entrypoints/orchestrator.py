# -----------------------
# orchestrator.py
# -----------------------
from __future__ import annotations

import json
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import pandas as pd

from opt.opt_config import build_config, parse_args
from opt.opt_data import compute_grid_fingerprint, list_run_ids, load_statgrid_run, resolve_slices
from opt.opt_diagnostics import (
    ensure_dirs,
    write_calibration_current_and_history,
    write_diagnostics_current_and_history,
    write_final_summary,
)
from opt.opt_engine import ConditionalProbEngine, Ticket
from opt.opt_features import build_truth_history_tables
from opt.opt_state import load_state_or_init, save_state, validate_resume_or_fail

# Strategy runners (optimize action)
from opt.opt_strategies import (
    run_bandit,
    run_evolutionary,
    run_greedy,
    run_milp,
    build_value_pools_from_grid,
    random_ticket_baseline,
)

# Forecast selection helpers (forecast action)
from opt.opt_strategies import (
    select_milp_sum_q,
    select_portfolio_greedy,
    tickets_to_str,
    list_to_str,
)

# Option B: build next-step candidate grid inside Orchestrator by reusing the forecast-collection
# logic (extracted to dynamix.candidate_grid in E4). If the environment lacks some forecast
# models, the collector logs warnings and continues best-effort.
from dynamix import data_utils as DU  # type: ignore
from dynamix.candidate_grid import (  # type: ignore
    collect_model_forecasts_for_step,
    build_candidate_grid_rows,
)


def _fmt_hms(seconds: float) -> str:
    s = max(0.0, float(seconds))
    hh = int(s // 3600)
    mm = int((s % 3600) // 60)
    ss = int(s % 60)
    if hh > 0:
        return f"{hh:d}:{mm:02d}:{ss:02d}"
    return f"{mm:d}:{ss:02d}"


def _print_header(cfg) -> None:
    action = getattr(cfg, "action", "optimize")
    print("[OPT] =============================================================", flush=True)
    print("[OPT] Orchestrator starting", flush=True)
    print(f"[OPT] action={action} | optimizer={cfg.optimizer} | resume={cfg.resume} | run_id={cfg.grid_run_id}", flush=True)
    if hasattr(cfg, "slice_mode"):
        print(f"[OPT] slice_mode={cfg.slice_mode}", flush=True)
    print("[OPT] =============================================================", flush=True)


def _print_slice_summary(slice_info: Dict[str, Any]) -> None:
    train_steps = slice_info.get("train_steps_dataset_index", []) or []
    eval_steps = slice_info.get("eval_steps_dataset_index", []) or []
    mode = slice_info.get("slice_mode", "pos")

    def _first_last(xs: List[int]) -> str:
        if not xs:
            return "first=NA last=NA"
        return f"first={int(xs[0])} last={int(xs[-1])}"

    print(f"[OPT] Slice resolved (mode={mode}):", flush=True)
    print(f"      TRAIN steps: {len(train_steps):,d} | {_first_last(train_steps)}", flush=True)
    print(f"      EVAL  steps: {len(eval_steps):,d} | {_first_last(eval_steps)}", flush=True)


def _print_scoreboard_verdict(diag_df, baseline: Dict[str, Any], cfg) -> None:
    """Print the honest EV/ROI + calibration verdict (E1.4). Skipped under --quiet.

    The same numbers are always persisted to summary_current.json regardless of this print.
    """
    if bool(getattr(cfg, "quiet", False)):
        return
    from opt.opt_diagnostics import build_strategy_scoreboard

    board = build_strategy_scoreboard(
        diag_df, baseline=baseline, n_bins=int(getattr(cfg, "calibration_bins", 10))
    )
    if not board:
        return

    print("", flush=True)
    print("[OPT] ===== SCOREBOARD (honest verdict on EVAL) =====", flush=True)
    print(
        "[OPT] strategy        net_eur  baseline   edge_eur   >=H rate  base_rate  q_any ECE",
        flush=True,
    )
    for opt in sorted(board.keys()):
        r = board[opt]
        verdict = "EDGE" if r["edge_eur"] > 0.0 else "no edge"
        print(
            f"[OPT] {opt:<12} {r['net_eur']:9.2f} {r['baseline_net_eur']:9.2f} "
            f"{r['edge_eur']:10.2f}  {r['realized_ge_H_rate']:8.3f} {r['base_rate_ge_H']:9.3f} "
            f"{r['qany_ece']:9.4f}  [{verdict}]",
            flush=True,
        )
    print("[OPT] ('edge_eur = net_eur - baseline_net_eur'; positive ⇒ beat the random control)", flush=True)


def _print_slice_interpretation(*, slice_info: Dict[str, Any], cfg, steps_all: List[int]) -> None:
    """
    Explicitly show how raw CLI slicing flags were interpreted.

    Examples required:
      - “train_end interpreted as position=509 ⇒ dataset_index=558”
      - “eval_start interpreted as position=510 ⇒ dataset_index=559”
    """
    mode = str(slice_info.get("slice_mode", "pos")).lower().strip()
    steps = [int(x) for x in steps_all]

    def idx_at_pos_1based(p: int) -> str:
        if 1 <= int(p) <= len(steps):
            return str(int(steps[int(p) - 1]))
        return "OUT_OF_RANGE"

    def idx_ge(v: int) -> str:
        return f"dataset_index>= {int(v)}"

    def idx_le(v: int) -> str:
        return f"dataset_index<= {int(v)}"

    lines: List[str] = []
    if getattr(cfg, "train_end_step", None) is not None:
        if mode == "pos":
            p = int(slice_info.get("train_end_step_pos", 0))
            lines.append(f"      train_end interpreted as position={p} ⇒ dataset_index={idx_at_pos_1based(p)}")
        else:
            lines.append(f"      train_end interpreted as index={int(cfg.train_end_step)} ⇒ {idx_le(int(cfg.train_end_step))}")

    if getattr(cfg, "eval_start_step", None) is not None:
        if mode == "pos":
            p = int(slice_info.get("eval_start_step_pos", 0))
            lines.append(f"      eval_start interpreted as position={p} ⇒ dataset_index={idx_at_pos_1based(p)}")
        else:
            lines.append(f"      eval_start interpreted as index={int(cfg.eval_start_step)} ⇒ {idx_ge(int(cfg.eval_start_step))}")

    if getattr(cfg, "eval_end_step", None) is not None:
        if mode == "pos":
            p = int(slice_info.get("eval_end_step_pos", 0))
            lines.append(f"      eval_end interpreted as position={p} ⇒ dataset_index={idx_at_pos_1based(p)}")
        else:
            lines.append(f"      eval_end interpreted as index={int(cfg.eval_end_step)} ⇒ {idx_le(int(cfg.eval_end_step))}")

    if lines:
        print("[OPT] Slice interpretation:", flush=True)
        for ln in lines:
            print(ln, flush=True)


def _resolve_latest_grid_run_id(cfg) -> Tuple[str, Any]:
    """
    Resolve cfg.grid_run_id (supports 'latest') and return:
      (run_id_resolved, cfg_updated)
    """
    run_id = str(cfg.grid_run_id)
    if run_id.lower().strip() != "latest":
        return run_id, cfg

    ids = list_run_ids(cfg)
    if not ids:
        raise FileNotFoundError(f"No StatGrid runs found under: {cfg.exports_dir}")
    run_id = ids[-1]
    cfg2 = cfg.with_grid_run_id(run_id)
    return run_id, cfg2


def _fit_engine_from_grid(
    *,
    cfg,
    run_id: str,
    grid: pd.DataFrame,
    train_steps: List[int],
) -> Tuple[ConditionalProbEngine, Any]:
    """
    Build leakage-safe truth tables on TRAIN only and fit ConditionalProbEngine.
    Returns (engine, truth_tables).
    """
    print("[OPT] Building truth history tables (TRAIN only, leakage-safe)...", flush=True)
    t_truth = time.monotonic()
    truth_tables = build_truth_history_tables(
        grid=grid,
        ts_list=cfg.ts_list,
        steps_ordered=sorted([int(x) for x in train_steps]),
    )
    print(
        f"[OPT] Truth tables built: n_steps={truth_tables.n_steps} (elapsed={_fmt_hms(time.monotonic() - t_truth)})",
        flush=True,
    )

    print("[OPT] Fitting conditional probability model on TRAIN...", flush=True)
    t_fit = time.monotonic()
    engine = ConditionalProbEngine(cfg, truth_tables)
    engine.fit_on_train(grid, train_steps=train_steps)
    print(f"[OPT] Model fit complete (elapsed={_fmt_hms(time.monotonic() - t_fit)})", flush=True)
    return engine, truth_tables


def _build_next_step_candidate_grid_via_stat(
    *,
    cfg,
    forecast_horizon: int = 1,
) -> Tuple[pd.DataFrame, int, int]:
    """
    Option B: Build a next-step candidate grid inside Orchestrator, without StatGrid.

    Returns:
      (step_df, forecast_dataset_index, n_obs)

    Notes:
      - Uses DU.load_lottery_data() to load current DATA.csv-backed ts_df
      - Forecasts only the next step (dataset_index = n_obs)
      - Produces rows compatible with StatGrid schema subset required by optimizer:
            dataset_index, ts, model, rounding_id, pred, rounded, true, hit, abs_err
      - Because truth is unknown for next step:
            true=0, hit=0, abs_err=0 (tie-breaker safe)
    """
    # Load current data (user manually updates DATA.csv over time)
    _arr, _dates, ts_df = DU.load_lottery_data()  # type: ignore[attr-defined]
    if not isinstance(ts_df, pd.DataFrame) or ts_df.empty:
        raise ValueError("DU.load_lottery_data() returned empty ts_df; cannot forecast.")

    try:
        ts_df = ts_df.sort_index()
    except Exception:
        pass

    # Ensure columns
    for ts in cfg.ts_list:
        if ts not in ts_df.columns:
            raise ValueError(f"DATA is missing required TS column: {ts}")

    n_obs = int(ts_df.shape[0])
    forecast_dataset_index = n_obs  # next step index position (consistent with Stat.py exporter)

    # History is all existing observations (exclusive of unknown future row)
    history_df = ts_df[cfg.ts_list].copy()

    # Use the forecast collector (best-effort; may skip models if unavailable).
    # executor=None => sequential execution in-process; 1 step only, so acceptable and avoids multiprocessing pitfalls.
    model_forecasts, worker_errors = collect_model_forecasts_for_step(
        history_df=history_df,
        executor=None,
        forecast_horizon=int(forecast_horizon),
    )

    if worker_errors:
        # Keep it explicit but non-fatal; forecast is best-effort.
        print(f"[OPT][forecast] WARNING: worker_errors={len(worker_errors)} (some models may have failed).", flush=True)

    # Dummy "true" row (unknown for next step). Must provide TS keys.
    true_row = pd.Series({ts: 0 for ts in cfg.ts_list})

    # Build candidate grid rows (ensures rounding modes consistent with StatGrid exports).
    # Many fields are not used by optimizer; still helpful for debugging.
    rows = build_candidate_grid_rows(
        run_id="forecast",
        export_mode="forecast",
        model_forecasts=model_forecasts,
        true_row=true_row,
        dataset_index=int(forecast_dataset_index),
        step_num=int(forecast_dataset_index),
        step_date="N/A",
        effective_window=0,
    )

    step_df = pd.DataFrame(rows)
    if step_df.empty:
        raise ValueError("Forecast candidate grid is empty. No model produced forecasts for required TS columns.")

    # Force required columns/types
    needed = ["dataset_index", "ts", "model", "rounding_id", "pred", "rounded", "true", "hit", "abs_err"]
    missing = [c for c in needed if c not in step_df.columns]
    if missing:
        raise ValueError(f"Forecast candidate grid missing required columns: {missing}")

    # Coerce types
    step_df["dataset_index"] = pd.to_numeric(step_df["dataset_index"], errors="coerce").fillna(forecast_dataset_index).astype(int)
    step_df["rounding_id"] = pd.to_numeric(step_df["rounding_id"], errors="coerce").fillna(0).astype(int)
    step_df["rounded"] = pd.to_numeric(step_df["rounded"], errors="coerce").fillna(0).astype(int)
    step_df["true"] = pd.to_numeric(step_df["true"], errors="coerce").fillna(0).astype(int)
    step_df["hit"] = pd.to_numeric(step_df["hit"], errors="coerce").fillna(0).astype(int)
    step_df["pred"] = pd.to_numeric(step_df["pred"], errors="coerce").astype(float)
    step_df["abs_err"] = pd.to_numeric(step_df["abs_err"], errors="coerce").fillna(0.0).astype(float)
    step_df["ts"] = step_df["ts"].astype(str)
    step_df["model"] = step_df["model"].astype(str)

    return step_df, int(forecast_dataset_index), int(n_obs)


def _forecast_tickets(
    *,
    cfg,
    engine: ConditionalProbEngine,
    step_df: pd.DataFrame,
    forecast_dataset_index: int,
) -> Dict[str, Any]:
    """
    Use the already-fit ConditionalProbEngine to generate up to N tickets for the next step.

    Selection policy:
      - Prefer MILP sum(Q) if pulp is available; otherwise greedy.
      - N defaults to cfg.max_tickets_per_draw (typically 5).
    """
    base = cfg.base_strategy_params()
    shortlist_m = int(base.get("shortlist_m", 10))
    beam = int(base.get("beam", 200))
    max_overlap_k = int(base.get("max_overlap_k", 3))
    hit_threshold = int(base.get("hit_threshold", 3))
    max_tickets = int(getattr(cfg, "max_tickets_per_draw", getattr(cfg, "max_tickets", 5)) or 5)

    # Build shortlists/pool
    shortlists = engine.build_shortlists_for_step(step_df, shortlist_m=shortlist_m)
    pool = engine.build_ticket_pool_beam(shortlists, beam=beam)

    # Selection (MILP preferred, auto-fallback to greedy if pulp missing)
    tickets, q_list, q_any = select_milp_sum_q(
        cfg,
        engine,
        pool,
        shortlists,
        max_tickets=max_tickets,
        max_overlap_k=max_overlap_k,
        hit_threshold=hit_threshold,
    )

    out = {
        "forecast_dataset_index": int(forecast_dataset_index),
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "max_tickets": int(max_tickets),
        "max_overlap_k": int(max_overlap_k),
        "shortlist_m": int(shortlist_m),
        "beam": int(beam),
        "hit_threshold": int(hit_threshold),
        "tickets_count": int(len(tickets)),
        "tickets": [list(map(int, t)) for t in tickets],
        "tickets_str": tickets_to_str(tickets),
        "q_per_ticket": [float(x) for x in q_list],
        "q_per_ticket_str": list_to_str([float(x) for x in q_list]),
        "q_any": float(q_any),
        "note": "Ticket selection uses MILP-sum(Q) when pulp is available; otherwise falls back to greedy.",
    }
    return out


def _write_forecast_report(
    *,
    cfg,
    opt_run_id: str,
    report: Dict[str, Any],
) -> Path:
    """
    Persist forecast output under the optimizer state directory, which already exists and is run-scoped.
    """
    d = Path(cfg.state_dir) / str(opt_run_id)
    d.mkdir(parents=True, exist_ok=True)
    p = d / "forecast.json"
    p.write_text(json.dumps(report, indent=2), encoding="utf-8")
    return p


def _run_optimize(cfg) -> None:
    t0 = time.monotonic()

    ensure_dirs(cfg)

    # Resolve grid run id
    t1 = time.monotonic()
    run_id, cfg = _resolve_latest_grid_run_id(cfg)
    print(f"[OPT] Grid run id resolved: {run_id} (elapsed={_fmt_hms(time.monotonic() - t1)})", flush=True)

    # Load grid
    t_load = time.monotonic()
    print(f"[OPT] Loading StatGrid: {cfg.exports_dir / run_id}", flush=True)
    grid = load_statgrid_run(cfg, run_id)
    print(
        f"[OPT] Grid loaded: rows={len(grid):,d} cols={len(grid.columns):,d} (elapsed={_fmt_hms(time.monotonic() - t_load)})",
        flush=True,
    )

    # Order steps
    t_steps = time.monotonic()
    steps_all = sorted(pd.unique(grid["dataset_index"]).tolist())
    if not steps_all:
        raise ValueError("Grid has no steps (dataset_index unique empty).")
    print(
        f"[OPT] Steps discovered: n_steps={len(steps_all):,d} min={int(steps_all[0])} max={int(steps_all[-1])} (elapsed={_fmt_hms(time.monotonic() - t_steps)})",
        flush=True,
    )

    # Resolve slices
    t_slice = time.monotonic()
    slice_info = resolve_slices(
        steps_all,
        train_frac=cfg.train_frac,
        train_end_step=cfg.train_end_step,
        eval_start_step=cfg.eval_start_step,
        eval_end_step=cfg.eval_end_step,
        slice_mode=getattr(cfg, "slice_mode", "pos"),
    )
    _print_slice_summary(slice_info)
    _print_slice_interpretation(slice_info=slice_info, cfg=cfg, steps_all=[int(x) for x in steps_all])
    print(f"[OPT] Slicing elapsed={_fmt_hms(time.monotonic() - t_slice)}", flush=True)

    train_steps = slice_info["train_steps_dataset_index"]
    eval_steps = slice_info["eval_steps_dataset_index"]
    if not eval_steps:
        raise ValueError("Evaluation slice is empty. Adjust slicing arguments.")

    # Fingerprint for resume safety
    print("[OPT] Computing grid fingerprint...", flush=True)
    t_fp = time.monotonic()
    grid_fp = compute_grid_fingerprint(grid, cfg.ts_list)
    print(
        f"[OPT] Fingerprint computed: n_steps={grid_fp.get('n_steps')} (elapsed={_fmt_hms(time.monotonic() - t_fp)})",
        flush=True,
    )

    # Resume or init opt state
    print("[OPT] Loading/initializing optimizer state...", flush=True)
    t_state = time.monotonic()
    opt_run_id, state = load_state_or_init(cfg, run_id, grid_fp, slice_info)
    print(
        f"[OPT] opt_run_id={opt_run_id} | resuming={bool(state.get('resuming', False))} (elapsed={_fmt_hms(time.monotonic() - t_state)})",
        flush=True,
    )

    # Extra safety validation (redundant but explicit)
    if state.get("resuming", False):
        validate_resume_or_fail(
            loaded_state=state,
            grid_run_id=run_id,
            grid_fingerprint=grid_fp,
            config_identity=cfg.config_identity(),
            slice_info=slice_info,
        )

    # Fit engine
    engine, _truth_tables = _fit_engine_from_grid(cfg=cfg, run_id=run_id, grid=grid, train_steps=train_steps)

    # Save baseline params into state (deterministic)
    state.setdefault("strategy", {})
    state["strategy"]["base_params"] = cfg.base_strategy_params()
    save_state(cfg, opt_run_id, state)
    print("[OPT] State checkpoint saved after training.", flush=True)

    want = sorted(list(cfg.which_optimizers()))
    print(f"[OPT] Optimizers selected: {want}", flush=True)
    print("[OPT] ------------------ Strategy execution begins ------------------", flush=True)

    t_exec = time.monotonic()

    all_diag_rows: List[Dict[str, Any]] = []
    results: Dict[str, Any] = {}

    if "greedy" in want:
        print("[OPT] Running: greedy", flush=True)
        res = run_greedy(cfg, opt_run_id, state, grid, engine, eval_steps)
        results["greedy"] = res.summary
        all_diag_rows.extend(res.diag_rows)
        state = res.state
        save_state(cfg, opt_run_id, state)
        print("[OPT] greedy done + checkpoint saved", flush=True)

    if "milp" in want:
        print("[OPT] Running: milp", flush=True)
        res = run_milp(cfg, opt_run_id, state, grid, engine, eval_steps)
        results["milp"] = res.summary
        all_diag_rows.extend(res.diag_rows)
        state = res.state
        save_state(cfg, opt_run_id, state)
        print("[OPT] milp done + checkpoint saved", flush=True)

    if "bandit" in want:
        print("[OPT] Running: bandit", flush=True)
        res = run_bandit(cfg, opt_run_id, state, grid, engine, eval_steps)
        results["bandit"] = res.summary
        all_diag_rows.extend(res.diag_rows)
        state = res.state
        save_state(cfg, opt_run_id, state)
        print("[OPT] bandit done + checkpoint saved", flush=True)

    if "evo" in want:
        print("[OPT] Running: evo", flush=True)
        res = run_evolutionary(cfg, opt_run_id, state, grid, engine, eval_steps, train_steps)
        results["evolutionary"] = res.summary
        all_diag_rows.extend(res.diag_rows)
        state = res.state
        save_state(cfg, opt_run_id, state)
        print("[OPT] evo done + checkpoint saved", flush=True)

    print(f"[OPT] Strategy execution finished (elapsed={_fmt_hms(time.monotonic() - t_exec)})", flush=True)

    # Persist diagnostics + calibration reports
    print("[OPT] Writing diagnostics (current + history)...", flush=True)
    t_rep = time.monotonic()
    diag_df = write_diagnostics_current_and_history(cfg, opt_run_id, run_id, all_diag_rows)

    print("[OPT] Writing calibration report (current + history)...", flush=True)
    calib_df = write_calibration_current_and_history(cfg, opt_run_id, run_id, diag_df)
    print(f"[OPT] Reports written (elapsed={_fmt_hms(time.monotonic() - t_rep)})", flush=True)

    # Random-ticket control baseline (E1.2): the fair -EV reference the strategies must beat.
    # Pools are drawn from TRAIN truth only (leakage-safe); evaluated over the EVAL draws.
    value_pools = build_value_pools_from_grid(grid, list(cfg.ts_list), steps=train_steps)
    baseline = random_ticket_baseline(
        cfg,
        value_pools,
        seed=int(cfg.seed),
        n_tickets=int(cfg.max_tickets_per_draw),
        n_draws=int(len(eval_steps)),
    )

    # Final summary
    print("[OPT] Writing final summary...", flush=True)
    t_sum = time.monotonic()
    write_final_summary(
        cfg, opt_run_id, run_id, grid_fp, slice_info, results, diag_df, calib_df,
        baseline=baseline,
    )
    print(f"[OPT] Final summary done (elapsed={_fmt_hms(time.monotonic() - t_sum)})", flush=True)

    _print_scoreboard_verdict(diag_df, baseline, cfg)

    print("[OPT] Done.", flush=True)
    print(f"[OPT] Results keys: {sorted(list(results.keys()))}", flush=True)
    print(results, flush=True)
    print(f"[OPT] Total elapsed={_fmt_hms(time.monotonic() - t0)}", flush=True)


def _run_forecast(cfg) -> None:
    """
    Forecast action:
      - Loads latest StatGrid (or explicit run_id)
      - Fits ConditionalProbEngine on TRAIN slice (no leakage)
      - Builds next-step candidate grid internally (Option B) using Stat.py forecasting
      - Generates up to 5 positional tickets (cfg.max_tickets_per_draw)
      - Writes forecast.json under state_dir/<opt_run_id>/
    """
    t0 = time.monotonic()
    ensure_dirs(cfg)

    # Resolve grid run id
    t1 = time.monotonic()
    run_id, cfg = _resolve_latest_grid_run_id(cfg)
    print(f"[OPT] Grid run id resolved: {run_id} (elapsed={_fmt_hms(time.monotonic() - t1)})", flush=True)

    # Load grid (needed to fit conditional model and compute truth history)
    t_load = time.monotonic()
    print(f"[OPT] Loading StatGrid: {cfg.exports_dir / run_id}", flush=True)
    grid = load_statgrid_run(cfg, run_id)
    print(
        f"[OPT] Grid loaded: rows={len(grid):,d} cols={len(grid.columns):,d} (elapsed={_fmt_hms(time.monotonic() - t_load)})",
        flush=True,
    )

    # Steps
    steps_all = sorted(pd.unique(grid["dataset_index"]).tolist())
    if not steps_all:
        raise ValueError("Grid has no steps (dataset_index unique empty).")
    print(
        f"[OPT] Steps discovered: n_steps={len(steps_all):,d} min={int(steps_all[0])} max={int(steps_all[-1])}",
        flush=True,
    )

    # Resolve slices: For forecast, eval slice may be empty; we primarily need TRAIN.
    slice_info = resolve_slices(
        steps_all,
        train_frac=cfg.train_frac,
        train_end_step=cfg.train_end_step,
        eval_start_step=cfg.eval_start_step,
        eval_end_step=cfg.eval_end_step,
        slice_mode=getattr(cfg, "slice_mode", "pos"),
    )
    _print_slice_summary(slice_info)
    _print_slice_interpretation(slice_info=slice_info, cfg=cfg, steps_all=[int(x) for x in steps_all])

    train_steps = slice_info.get("train_steps_dataset_index", []) or []
    if not train_steps:
        raise ValueError("TRAIN slice is empty. Adjust slicing arguments for forecast.")

    # Fingerprint (still useful for state provenance)
    print("[OPT] Computing grid fingerprint...", flush=True)
    grid_fp = compute_grid_fingerprint(grid, cfg.ts_list)

    # State: allow resume/latest so forecast can attach to an existing run folder
    print("[OPT] Loading/initializing optimizer state...", flush=True)
    opt_run_id, state = load_state_or_init(cfg, run_id, grid_fp, slice_info)
    print(
        f"[OPT] opt_run_id={opt_run_id} | resuming={bool(state.get('resuming', False))}",
        flush=True,
    )

    # If resuming, validate identity
    if state.get("resuming", False):
        validate_resume_or_fail(
            loaded_state=state,
            grid_run_id=run_id,
            grid_fingerprint=grid_fp,
            config_identity=cfg.config_identity(),
            slice_info=slice_info,
        )

    # Fit engine on TRAIN
    engine, _truth_tables = _fit_engine_from_grid(cfg=cfg, run_id=run_id, grid=grid, train_steps=[int(x) for x in train_steps])

    # Build next-step candidate grid (Option B) from current DATA.csv
    print("[OPT][forecast] Building next-step candidate grid from DATA.csv (Option B)...", flush=True)
    t_cg = time.monotonic()
    step_df, forecast_dataset_index, n_obs = _build_next_step_candidate_grid_via_stat(cfg=cfg, forecast_horizon=1)
    print(
        f"[OPT][forecast] Candidate grid built for dataset_index={forecast_dataset_index} (n_obs={n_obs}) "
        f"rows={len(step_df):,d} (elapsed={_fmt_hms(time.monotonic() - t_cg)})",
        flush=True,
    )

    # Generate tickets
    print("[OPT][forecast] Selecting tickets...", flush=True)
    t_sel = time.monotonic()
    report = _forecast_tickets(cfg=cfg, engine=engine, step_df=step_df, forecast_dataset_index=forecast_dataset_index)
    print(f"[OPT][forecast] Ticket selection done (elapsed={_fmt_hms(time.monotonic() - t_sel)})", flush=True)

    # Attach provenance
    report["grid_run_id"] = str(run_id)
    report["opt_run_id"] = str(opt_run_id)
    report["grid_fingerprint"] = grid_fp
    report["slice_info"] = slice_info
    report["config_identity"] = cfg.config_identity()
    report["base_params"] = cfg.base_strategy_params()

    # Persist report under state dir
    out_path = _write_forecast_report(cfg=cfg, opt_run_id=opt_run_id, report=report)

    # Also checkpoint state with a note
    state.setdefault("forecast", {})
    state["forecast"]["last_forecast_dataset_index"] = int(forecast_dataset_index)
    state["forecast"]["last_forecast_at"] = datetime.now().isoformat(timespec="seconds")
    state["forecast"]["forecast_report_path"] = str(out_path)
    save_state(cfg, opt_run_id, state)

    # Console output (operator-friendly)
    print("[OPT][forecast] -------------------------------------------------------------", flush=True)
    print(f"[OPT][forecast] NEXT STEP dataset_index={forecast_dataset_index}", flush=True)
    print(f"[OPT][forecast] tickets_count={report['tickets_count']} max_tickets={report['max_tickets']}", flush=True)
    print(f"[OPT][forecast] tickets: {report['tickets_str']}", flush=True)
    print(f"[OPT][forecast] q_any={report['q_any']:.6f} | q_per_ticket={report['q_per_ticket_str']}", flush=True)
    print(f"[OPT][forecast] report_path={out_path}", flush=True)
    print("[OPT][forecast] -------------------------------------------------------------", flush=True)
    print(f"[OPT] Total elapsed={_fmt_hms(time.monotonic() - t0)}", flush=True)


def main() -> None:
    args = parse_args()
    cfg = build_config(args)

    _print_header(cfg)

    action = str(getattr(cfg, "action", "optimize") or "optimize").strip().lower()
    if action not in {"optimize", "forecast"}:
        raise ValueError("--action must be one of: optimize, forecast")

    if action == "forecast":
        _run_forecast(cfg)
    else:
        _run_optimize(cfg)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n[OPT] Interrupted.", flush=True)
        sys.exit(130)
