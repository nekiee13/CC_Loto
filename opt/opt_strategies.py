# -----------------------
# opt/opt_strategies.py
# -----------------------
from __future__ import annotations

import math
import time
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
import pandas as pd

from .opt_config import OptConfig
from .opt_engine import ConditionalProbEngine, Ticket

# Optional MILP
try:
    import pulp  # type: ignore

    HAS_PULP = True
except Exception:
    pulp = None  # type: ignore
    HAS_PULP = False


@dataclass
class StrategyResult:
    state: Dict[str, Any]
    summary: Dict[str, Any]
    diag_rows: List[Dict[str, Any]]


def _p(msg: str, *, cfg: OptConfig) -> None:
    """Console print with flush; honors cfg.quiet."""
    if bool(getattr(cfg, "quiet", False)):
        return
    print(msg, flush=True)


def _fmt_hms(seconds: float) -> str:
    s = max(0.0, float(seconds))
    hh = int(s // 3600)
    mm = int((s % 3600) // 60)
    ss = int(s % 60)
    if hh > 0:
        return f"{hh:d}:{mm:02d}:{ss:02d}"
    return f"{mm:d}:{ss:02d}"


def _progress_report(
    *,
    cfg: OptConfig,
    stage_name: str,
    pos_done: int,
    pos_total: int,
    t_stage_start: float,
    t_last_print: float,
    force: bool = False,
) -> float:
    """Emit a progress line every cfg.progress_every iterations (or when forced).

    Returns:
        new_last_print_time
    """
    every = int(getattr(cfg, "progress_every", 25) or 25)
    every = max(1, every)

    now = time.monotonic()
    should_print = force or (pos_done <= 1) or (pos_done >= pos_total) or (pos_done % every == 0)
    if not should_print:
        return t_last_print

    pct = (100.0 * float(pos_done) / float(max(1, pos_total)))
    elapsed = now - t_stage_start

    eta_s: Optional[float] = None
    if bool(getattr(cfg, "progress_show_eta", True)) and pos_done > 0 and pos_total > 0:
        rate = elapsed / float(max(1, pos_done))
        remaining = float(max(0, pos_total - pos_done))
        eta_s = rate * remaining

    if eta_s is None:
        _p(
            f"[OPT][{stage_name}] progress: {pos_done}/{pos_total} ({pct:5.1f}%) | elapsed={_fmt_hms(elapsed)}",
            cfg=cfg,
        )
    else:
        _p(
            f"[OPT][{stage_name}] progress: {pos_done}/{pos_total} ({pct:5.1f}%) | elapsed={_fmt_hms(elapsed)} | eta={_fmt_hms(eta_s)}",
            cfg=cfg,
        )

    return now


def ticket_to_str(t: Ticket) -> str:
    return "-".join(str(int(x)) for x in t)


def tickets_to_str(tickets: List[Ticket]) -> str:
    return " | ".join(ticket_to_str(t) for t in tickets)


def list_to_str(xs: List[float], precision: int = 6) -> str:
    return "[" + ",".join(f"{float(x):.{precision}f}" for x in xs) + "]"


def realized_hits(ticket: Ticket, true_ticket: Ticket) -> int:
    n = min(len(ticket), len(true_ticket))
    return int(sum(1 for i in range(n) if int(ticket[i]) == int(true_ticket[i])))


def eval_summary(per_draw_rows: List[Dict[str, Any]], cfg: OptConfig) -> Dict[str, Any]:
    df = pd.DataFrame(per_draw_rows).sort_values("dataset_index").reset_index(drop=True)
    if df.empty:
        return {"error": "no rows"}

    df["cum_profit"] = df["profit"].cumsum()
    df["cum_max"] = df["cum_profit"].cummax()
    df["drawdown"] = df["cum_profit"] - df["cum_max"]

    total_cost = float((df["tickets"].astype(float) * float(cfg.ticket_cost_eur)).sum())
    total_profit = float(df["profit"].sum())
    roi_total = (total_profit / total_cost) if total_cost > 0 else 0.0

    return {
        "rows": int(len(df)),
        "total_profit": float(total_profit),
        "total_cost": float(total_cost),
        "roi_total": float(roi_total),
        "avg_profit_per_draw": float(df["profit"].mean()),
        "worst_drawdown": float(df["drawdown"].min()),
        "avg_tickets_per_draw": float(df["tickets"].mean()),
        "max_hits_observed": int(df["max_hits"].max()),
    }


def select_portfolio_greedy(
    cfg: OptConfig,
    engine: ConditionalProbEngine,
    ticket_pool: List[Tuple[Ticket, float]],
    shortlists: Dict[str, List[Any]],
    *,
    max_tickets: int,
    max_overlap_k: int,
    hit_threshold: int,
) -> Tuple[List[Ticket], List[float], float]:
    if not ticket_pool:
        return [], [], 0.0

    scored: List[Tuple[Ticket, float, float]] = []
    for t, logp in ticket_pool:
        q = engine.score_ticket_q(t, shortlists, hit_threshold)
        scored.append((t, float(logp), float(q)))

    scored.sort(key=lambda x: (x[2], x[1]), reverse=True)

    # greedy overlap-filtered seed (kept for readability/debugging; final selection uses deterministic fill)
    chosen_seed: List[Ticket] = []
    for t, _, _ in scored:
        if len(chosen_seed) >= int(max_tickets):
            break
        if all(engine.overlap_positions(t, c) <= int(max_overlap_k) for c in chosen_seed):
            chosen_seed.append(t)

    ranked_all = [t for (t, _, _) in scored]
    tickets = engine.fill_to_k_deterministic(ranked_all, max_tickets=max_tickets, max_overlap_k=max_overlap_k)

    q_list = [engine.score_ticket_q(t, shortlists, hit_threshold) for t in tickets]
    q_any = engine.portfolio_q_any(q_list)

    return tickets, q_list, float(q_any)


def select_milp_sum_q(
    cfg: OptConfig,
    engine: ConditionalProbEngine,
    ticket_pool: List[Tuple[Ticket, float]],
    shortlists: Dict[str, List[Any]],
    *,
    max_tickets: int,
    max_overlap_k: int,
    hit_threshold: int,
) -> Tuple[List[Ticket], List[float], float]:
    if not HAS_PULP or pulp is None or not ticket_pool:
        return select_portfolio_greedy(
            cfg,
            engine,
            ticket_pool,
            shortlists,
            max_tickets=max_tickets,
            max_overlap_k=max_overlap_k,
            hit_threshold=hit_threshold,
        )

    pool = ticket_pool[: min(len(ticket_pool), int(cfg.milp_max_pool))]
    n = len(pool)
    qvals = [engine.score_ticket_q(pool[i][0], shortlists, hit_threshold) for i in range(n)]

    prob = pulp.LpProblem("ticket_select", pulp.LpMaximize)
    x = [pulp.LpVariable(f"x_{i}", cat=pulp.LpBinary) for i in range(n)]
    prob += pulp.lpSum(qvals[i] * x[i] for i in range(n))
    prob += pulp.lpSum(x) <= int(max_tickets)

    for i in range(n):
        ti = pool[i][0]
        for j in range(i + 1, n):
            tj = pool[j][0]
            if engine.overlap_positions(ti, tj) > int(max_overlap_k):
                prob += x[i] + x[j] <= 1

    prob.solve(pulp.PULP_CBC_CMD(msg=False))

    chosen: List[Ticket] = []
    for i in range(n):
        v = x[i].value()
        if v is not None and float(v) > 0.5:
            chosen.append(pool[i][0])

    # Deterministic fill
    ranked = chosen[:] + [t for (t, _) in ticket_pool if t not in chosen]
    tickets = engine.fill_to_k_deterministic(ranked, max_tickets=max_tickets, max_overlap_k=max_overlap_k)
    q_list = [engine.score_ticket_q(t, shortlists, hit_threshold) for t in tickets]
    q_any = engine.portfolio_q_any(q_list)
    return tickets, q_list, float(q_any)


def _true_ticket_from_step(step_df: pd.DataFrame, ts_list: List[str]) -> Ticket:
    return tuple(int(step_df[step_df["ts"] == ts]["true"].iloc[0]) for ts in ts_list)


def run_greedy(
    cfg: OptConfig,
    opt_run_id: str,
    state: Dict[str, Any],
    grid: pd.DataFrame,
    engine: ConditionalProbEngine,
    eval_steps: List[int],
) -> StrategyResult:
    stage_name = "greedy"
    st = state.setdefault("stages", {}).setdefault(stage_name, {"next_pos": 0, "rows": [], "diag_rows": []})
    next_pos = int(st.get("next_pos", 0))
    rows = list(st.get("rows", []))
    diag_rows = list(st.get("diag_rows", []))

    base = cfg.base_strategy_params()

    n_total = len(eval_steps)
    t_stage_start = time.monotonic()
    t_last_print = 0.0
    _p(f"[OPT][{stage_name}] start: resuming_pos={next_pos} | eval_steps={n_total}", cfg=cfg)

    for pos in range(next_pos, n_total):
        idx = int(eval_steps[pos])
        step_df = grid[grid["dataset_index"] == idx]
        if step_df.empty:
            st["next_pos"] = pos + 1
            continue

        true_ticket = _true_ticket_from_step(step_df, cfg.ts_list)

        shortlists = engine.build_shortlists_for_step(step_df, shortlist_m=int(base["shortlist_m"]))
        pool = engine.build_ticket_pool_beam(shortlists, beam=int(base["beam"]))

        tickets, q_list, q_any = select_portfolio_greedy(
            cfg,
            engine,
            pool,
            shortlists,
            max_tickets=int(cfg.max_tickets_per_draw),
            max_overlap_k=int(base["max_overlap_k"]),
            hit_threshold=int(base["hit_threshold"]),
        )

        profits: List[float] = []
        hits_list: List[int] = []
        for t in tickets:
            h = realized_hits(t, true_ticket)
            hits_list.append(h)
            profits.append(float(cfg.payout_by_hits.get(h, 0.0)) - float(cfg.ticket_cost_eur))

        step_profit = float(sum(profits))
        max_hits = int(max(hits_list) if hits_list else 0)

        rows.append({"dataset_index": idx, "tickets": int(len(tickets)), "profit": step_profit, "max_hits": max_hits})
        diag_rows.append(
            {
                "optimizer": stage_name,
                "dataset_index": idx,
                "tickets_count": int(len(tickets)),
                "tickets": tickets_to_str(tickets),
                "q_per_ticket": list_to_str(q_list),
                "q_any": float(q_any),
                "hit_threshold": int(base["hit_threshold"]),
                "realized_max_hits": int(max_hits),
                "success_ge_H": int(1 if max_hits >= int(base["hit_threshold"]) else 0),
                "profit": float(step_profit),
                "arm": "",
            }
        )

        st["next_pos"] = pos + 1
        st["rows"] = rows
        st["diag_rows"] = diag_rows

        t_last_print = _progress_report(
            cfg=cfg,
            stage_name=stage_name,
            pos_done=pos + 1,
            pos_total=n_total,
            t_stage_start=t_stage_start,
            t_last_print=t_last_print,
            force=False,
        )

    _progress_report(
        cfg=cfg,
        stage_name=stage_name,
        pos_done=n_total,
        pos_total=n_total,
        t_stage_start=t_stage_start,
        t_last_print=t_last_print,
        force=True,
    )

    state["stages"][stage_name] = st
    summary = eval_summary(rows, cfg)
    return StrategyResult(state=state, summary=summary, diag_rows=diag_rows)


def run_milp(
    cfg: OptConfig,
    opt_run_id: str,
    state: Dict[str, Any],
    grid: pd.DataFrame,
    engine: ConditionalProbEngine,
    eval_steps: List[int],
) -> StrategyResult:
    stage_name = "milp"
    st = state.setdefault("stages", {}).setdefault(stage_name, {"next_pos": 0, "rows": [], "diag_rows": []})
    next_pos = int(st.get("next_pos", 0))
    rows = list(st.get("rows", []))
    diag_rows = list(st.get("diag_rows", []))

    base = cfg.base_strategy_params()

    n_total = len(eval_steps)
    t_stage_start = time.monotonic()
    t_last_print = 0.0

    note = ""
    if not HAS_PULP:
        note = "pulp not installed; MILP will fall back to greedy."
    _p(
        f"[OPT][{stage_name}] start: resuming_pos={next_pos} | eval_steps={n_total}" + (f" | {note}" if note else ""),
        cfg=cfg,
    )

    for pos in range(next_pos, n_total):
        idx = int(eval_steps[pos])
        step_df = grid[grid["dataset_index"] == idx]
        if step_df.empty:
            st["next_pos"] = pos + 1
            continue

        true_ticket = _true_ticket_from_step(step_df, cfg.ts_list)
        shortlists = engine.build_shortlists_for_step(step_df, shortlist_m=int(base["shortlist_m"]))
        pool = engine.build_ticket_pool_beam(shortlists, beam=int(base["beam"]))

        tickets, q_list, q_any = select_milp_sum_q(
            cfg,
            engine,
            pool,
            shortlists,
            max_tickets=int(cfg.max_tickets_per_draw),
            max_overlap_k=int(base["max_overlap_k"]),
            hit_threshold=int(base["hit_threshold"]),
        )

        profits: List[float] = []
        hits_list: List[int] = []
        for t in tickets:
            h = realized_hits(t, true_ticket)
            hits_list.append(h)
            profits.append(float(cfg.payout_by_hits.get(h, 0.0)) - float(cfg.ticket_cost_eur))

        step_profit = float(sum(profits))
        max_hits = int(max(hits_list) if hits_list else 0)

        rows.append({"dataset_index": idx, "tickets": int(len(tickets)), "profit": step_profit, "max_hits": max_hits})
        diag_rows.append(
            {
                "optimizer": stage_name,
                "dataset_index": idx,
                "tickets_count": int(len(tickets)),
                "tickets": tickets_to_str(tickets),
                "q_per_ticket": list_to_str(q_list),
                "q_any": float(q_any),
                "hit_threshold": int(base["hit_threshold"]),
                "realized_max_hits": int(max_hits),
                "success_ge_H": int(1 if max_hits >= int(base["hit_threshold"]) else 0),
                "profit": float(step_profit),
                "arm": "",
            }
        )

        st["next_pos"] = pos + 1
        st["rows"] = rows
        st["diag_rows"] = diag_rows

        t_last_print = _progress_report(
            cfg=cfg,
            stage_name=stage_name,
            pos_done=pos + 1,
            pos_total=n_total,
            t_stage_start=t_stage_start,
            t_last_print=t_last_print,
            force=False,
        )

    _progress_report(
        cfg=cfg,
        stage_name=stage_name,
        pos_done=n_total,
        pos_total=n_total,
        t_stage_start=t_stage_start,
        t_last_print=t_last_print,
        force=True,
    )

    state["stages"][stage_name] = st
    summary = eval_summary(rows, cfg)
    if not HAS_PULP:
        summary["note"] = "MILP requested but pulp not installed; fell back to greedy selection."
    return StrategyResult(state=state, summary=summary, diag_rows=diag_rows)


def run_bandit(
    cfg: OptConfig,
    opt_run_id: str,
    state: Dict[str, Any],
    grid: pd.DataFrame,
    engine: ConditionalProbEngine,
    eval_steps: List[int],
) -> StrategyResult:
    stage_name = "bandit"
    st = state.setdefault("stages", {}).setdefault(
        stage_name, {"next_pos": 0, "rows": [], "diag_rows": [], "alpha": {}, "beta": {}}
    )
    next_pos = int(st.get("next_pos", 0))
    rows = list(st.get("rows", []))
    diag_rows = list(st.get("diag_rows", []))

    rng = np.random.RandomState(int(cfg.seed))
    arms = cfg.bandit_arms
    alpha = dict(st.get("alpha", {}))
    beta = dict(st.get("beta", {}))
    for a in arms:
        alpha.setdefault(a["name"], 1.0)
        beta.setdefault(a["name"], 1.0)

    def choose_arm() -> Dict[str, Any]:
        best = arms[0]
        best_s = -1.0
        for a in arms:
            s = float(rng.beta(float(alpha[a["name"]]), float(beta[a["name"]])))
            if s > best_s:
                best_s = s
                best = a
        return best

    n_total = len(eval_steps)
    t_stage_start = time.monotonic()
    t_last_print = 0.0
    _p(f"[OPT][{stage_name}] start: resuming_pos={next_pos} | eval_steps={n_total} | arms={len(arms)}", cfg=cfg)

    for pos in range(next_pos, n_total):
        idx = int(eval_steps[pos])
        step_df = grid[grid["dataset_index"] == idx]
        if step_df.empty:
            st["next_pos"] = pos + 1
            continue

        arm = choose_arm()

        true_ticket = _true_ticket_from_step(step_df, cfg.ts_list)
        shortlists = engine.build_shortlists_for_step(step_df, shortlist_m=int(arm["shortlist_m"]))
        pool = engine.build_ticket_pool_beam(shortlists, beam=int(arm["beam"]))

        tickets, q_list, q_any = select_portfolio_greedy(
            cfg,
            engine,
            pool,
            shortlists,
            max_tickets=int(cfg.max_tickets_per_draw),
            max_overlap_k=int(arm["max_overlap_k"]),
            hit_threshold=int(arm["hit_threshold"]),
        )

        profits: List[float] = []
        hits_list: List[int] = []
        for t in tickets:
            h = realized_hits(t, true_ticket)
            hits_list.append(h)
            profits.append(float(cfg.payout_by_hits.get(h, 0.0)) - float(cfg.ticket_cost_eur))

        step_profit = float(sum(profits))
        max_hits = int(max(hits_list) if hits_list else 0)
        success = bool(max_hits >= int(arm["hit_threshold"]))
        if success:
            alpha[arm["name"]] = float(alpha[arm["name"]]) + 1.0
        else:
            beta[arm["name"]] = float(beta[arm["name"]]) + 1.0

        rows.append(
            {"dataset_index": idx, "tickets": int(len(tickets)), "profit": step_profit, "max_hits": max_hits, "arm": arm["name"]}
        )
        diag_rows.append(
            {
                "optimizer": stage_name,
                "dataset_index": idx,
                "tickets_count": int(len(tickets)),
                "tickets": tickets_to_str(tickets),
                "q_per_ticket": list_to_str(q_list),
                "q_any": float(q_any),
                "hit_threshold": int(arm["hit_threshold"]),
                "realized_max_hits": int(max_hits),
                "success_ge_H": int(1 if success else 0),
                "profit": float(step_profit),
                "arm": arm["name"],
            }
        )

        st["next_pos"] = pos + 1
        st["rows"] = rows
        st["diag_rows"] = diag_rows
        st["alpha"] = alpha
        st["beta"] = beta

        t_last_print = _progress_report(
            cfg=cfg,
            stage_name=stage_name,
            pos_done=pos + 1,
            pos_total=n_total,
            t_stage_start=t_stage_start,
            t_last_print=t_last_print,
            force=False,
        )

    _progress_report(
        cfg=cfg,
        stage_name=stage_name,
        pos_done=n_total,
        pos_total=n_total,
        t_stage_start=t_stage_start,
        t_last_print=t_last_print,
        force=True,
    )

    state["stages"][stage_name] = st
    summary = eval_summary(rows, cfg)
    summary["final_arm_posteriors"] = {k: {"alpha": float(alpha[k]), "beta": float(beta[k])} for k in alpha}
    return StrategyResult(state=state, summary=summary, diag_rows=diag_rows)


def run_evolutionary(
    cfg: OptConfig,
    opt_run_id: str,
    state: Dict[str, Any],
    grid: pd.DataFrame,
    engine: ConditionalProbEngine,
    eval_steps: List[int],
    train_steps: List[int],
) -> StrategyResult:
    """Evolutionary search (currently deterministic stub) with full eval progress.

    Current behavior (kept intentionally conservative/resume-safe):
      - Stores a 'best' record in state, but does not modify cfg weights (cfg is frozen).
      - Runs an evaluation pass identical to greedy using the current cfg weights.
    """
    stage_name = "evo"
    st = state.setdefault("stages", {}).setdefault(
        stage_name, {"done": False, "best": None, "diag_rows": [], "rows": [], "next_pos": 0}
    )

    if st.get("done", False) and st.get("best") is not None:
        best = st["best"]
    else:
        best = {"pair_weight": float(cfg.pair_weight), "triple_weight": float(cfg.triple_weight), "score": 0.0}
        st["best"] = best
        st["done"] = True

    next_pos = int(st.get("next_pos", 0))
    rows = list(st.get("rows", []))
    diag_rows = list(st.get("diag_rows", []))

    base = cfg.base_strategy_params()

    n_total = len(eval_steps)
    t_stage_start = time.monotonic()
    t_last_print = 0.0
    _p(f"[OPT][{stage_name}] start: resuming_pos={next_pos} | eval_steps={n_total}", cfg=cfg)

    for pos in range(next_pos, n_total):
        idx = int(eval_steps[pos])
        step_df = grid[grid["dataset_index"] == idx]
        if step_df.empty:
            st["next_pos"] = pos + 1
            continue

        true_ticket = _true_ticket_from_step(step_df, cfg.ts_list)
        shortlists = engine.build_shortlists_for_step(step_df, shortlist_m=int(base["shortlist_m"]))
        pool = engine.build_ticket_pool_beam(shortlists, beam=int(base["beam"]))

        tickets, q_list, q_any = select_portfolio_greedy(
            cfg,
            engine,
            pool,
            shortlists,
            max_tickets=int(cfg.max_tickets_per_draw),
            max_overlap_k=int(base["max_overlap_k"]),
            hit_threshold=int(base["hit_threshold"]),
        )

        profits: List[float] = []
        hits_list: List[int] = []
        for t in tickets:
            h = realized_hits(t, true_ticket)
            hits_list.append(h)
            profits.append(float(cfg.payout_by_hits.get(h, 0.0)) - float(cfg.ticket_cost_eur))

        step_profit = float(sum(profits))
        max_hits = int(max(hits_list) if hits_list else 0)

        rows.append({"dataset_index": idx, "tickets": int(len(tickets)), "profit": step_profit, "max_hits": max_hits})
        diag_rows.append(
            {
                "optimizer": "evolutionary",
                "dataset_index": idx,
                "tickets_count": int(len(tickets)),
                "tickets": tickets_to_str(tickets),
                "q_per_ticket": list_to_str(q_list),
                "q_any": float(q_any),
                "hit_threshold": int(base["hit_threshold"]),
                "realized_max_hits": int(max_hits),
                "success_ge_H": int(1 if max_hits >= int(base["hit_threshold"]) else 0),
                "profit": float(step_profit),
                "arm": "",
            }
        )

        st["next_pos"] = pos + 1
        st["rows"] = rows
        st["diag_rows"] = diag_rows

        t_last_print = _progress_report(
            cfg=cfg,
            stage_name=stage_name,
            pos_done=pos + 1,
            pos_total=n_total,
            t_stage_start=t_stage_start,
            t_last_print=t_last_print,
            force=False,
        )

    _progress_report(
        cfg=cfg,
        stage_name=stage_name,
        pos_done=n_total,
        pos_total=n_total,
        t_stage_start=t_stage_start,
        t_last_print=t_last_print,
        force=True,
    )

    state["stages"][stage_name] = st
    summary = eval_summary(rows, cfg)
    summary["best_weights"] = best
    return StrategyResult(state=state, summary=summary, diag_rows=diag_rows)
