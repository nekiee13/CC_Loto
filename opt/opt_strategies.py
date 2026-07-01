# -----------------------
# opt/opt_strategies.py
# -----------------------
from __future__ import annotations

import math
import random
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


def compute_portfolio_economics(
    tickets: List[Ticket],
    true_ticket: Ticket,
    *,
    payout_by_hits: Dict[int, float],
    ticket_cost_eur: float,
) -> Dict[str, float]:
    """Pure economics of one draw's portfolio against the realized truth.

    Each ticket pays out according to its OWN realized hit count; cost is one
    ``ticket_cost_eur`` per ticket. The single source of payout math for every strategy
    loop and the EV/ROI scoreboard (no duplication).

    Returns ``{gross_eur, cost_eur, net_eur, best_hits}`` where
    ``net_eur == gross_eur - cost_eur`` and ``best_hits`` is the max hits over the
    portfolio (0 if empty).
    """
    gross = 0.0
    best_hits = 0
    for t in tickets:
        h = realized_hits(t, true_ticket)
        if h > best_hits:
            best_hits = h
        gross += float(payout_by_hits.get(h, 0.0))
    cost = float(len(tickets)) * float(ticket_cost_eur)
    return {
        "gross_eur": float(gross),
        "cost_eur": float(cost),
        "net_eur": float(gross - cost),
        "best_hits": int(best_hits),
    }


def build_value_pools_from_grid(
    grid: pd.DataFrame, ts_list: List[str], steps: Optional[List[int]] = None
) -> Dict[str, List[int]]:
    """Per-position pools of observed ``true`` values, drawn from TRAIN steps only.

    Returns ``{ts: [observed_value, ...]}`` keeping duplicates so a uniform draw from the pool
    reproduces the empirical (frequency-weighted) distribution. Restrict to TRAIN ``steps`` to
    keep the baseline leakage-safe (never sample from EVAL truth).
    """
    df = grid
    if steps is not None:
        df = df[df["dataset_index"].isin(list(steps))]
    pools: Dict[str, List[int]] = {}
    for ts in ts_list:
        vals = df[df["ts"] == ts]["true"]
        pools[ts] = [int(v) for v in vals.tolist()]
    return pools


def sample_random_ticket(
    rng: random.Random, value_pools: Dict[str, List[int]], ts_list: List[str]
) -> Ticket:
    """Sample one ticket, choosing each position uniformly from its observed-value pool."""
    return tuple(int(rng.choice(value_pools[ts])) for ts in ts_list)


def random_ticket_baseline(
    cfg: OptConfig,
    value_pools: Dict[str, List[int]],
    *,
    seed: int,
    n_tickets: int,
    n_draws: int,
) -> Dict[str, float]:
    """Seeded random-portfolio control: the fair negative-EV baseline a strategy must beat.

    For each of ``n_draws`` simulated draws, a "true" ticket and ``n_tickets`` portfolio
    tickets are sampled from the same per-position pools, then scored with the E1.1 economics.
    The aggregate (summed over draws) shares the economics keys plus ``draws``/``n_tickets`` and
    a per-draw mean. Deterministic given ``seed``.
    """
    rng = random.Random(int(seed))
    ts_list = list(cfg.ts_list)
    gross = 0.0
    cost = 0.0
    net = 0.0
    best_hits = 0
    best_hits_per_draw: List[int] = []
    for _ in range(int(n_draws)):
        true_ticket = sample_random_ticket(rng, value_pools, ts_list)
        tickets = [sample_random_ticket(rng, value_pools, ts_list) for _ in range(int(n_tickets))]
        econ = compute_portfolio_economics(
            tickets,
            true_ticket,
            payout_by_hits=cfg.payout_by_hits,
            ticket_cost_eur=cfg.ticket_cost_eur,
        )
        gross += econ["gross_eur"]
        cost += econ["cost_eur"]
        net += econ["net_eur"]
        bh = int(econ["best_hits"])
        best_hits_per_draw.append(bh)
        best_hits = max(best_hits, bh)
    n = int(n_draws)
    return {
        "gross_eur": float(gross),
        "cost_eur": float(cost),
        "net_eur": float(net),
        "best_hits": int(best_hits),
        "best_hits_per_draw": best_hits_per_draw,
        "draws": int(n),
        "n_tickets": int(n_tickets),
        "avg_net_per_draw": float(net / n) if n > 0 else 0.0,
    }


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

        econ = compute_portfolio_economics(
            tickets,
            true_ticket,
            payout_by_hits=cfg.payout_by_hits,
            ticket_cost_eur=cfg.ticket_cost_eur,
        )
        step_profit = float(econ["net_eur"])
        max_hits = int(econ["best_hits"])

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

        econ = compute_portfolio_economics(
            tickets,
            true_ticket,
            payout_by_hits=cfg.payout_by_hits,
            ticket_cost_eur=cfg.ticket_cost_eur,
        )
        step_profit = float(econ["net_eur"])
        max_hits = int(econ["best_hits"])

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

        econ = compute_portfolio_economics(
            tickets,
            true_ticket,
            payout_by_hits=cfg.payout_by_hits,
            ticket_cost_eur=cfg.ticket_cost_eur,
        )
        step_profit = float(econ["net_eur"])
        max_hits = int(econ["best_hits"])
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


# ----------------------------------------------------------------------
# Evolutionary hyper-strategy search (E6.2)
# ----------------------------------------------------------------------
# Genes searched by the GA: the four strategy hyperparameters that shape the candidate pool and
# the portfolio selection. All are positive integers within config-derived bounds.
_EVO_GENES: Tuple[str, ...] = ("max_overlap_k", "shortlist_m", "beam", "hit_threshold")


def _evo_bounds(cfg: OptConfig) -> Dict[str, Tuple[int, int]]:
    n_ts = max(2, len(list(cfg.ts_list)))
    return {
        "max_overlap_k": (1, n_ts),
        "shortlist_m": (2, 20),
        "beam": (25, 400),
        "hit_threshold": (2, n_ts),
    }


def _evo_clamp(params: Dict[str, int], bounds: Dict[str, Tuple[int, int]]) -> Dict[str, int]:
    out: Dict[str, int] = {}
    for g in _EVO_GENES:
        lo, hi = bounds[g]
        out[g] = int(max(lo, min(hi, int(params[g]))))
    return out


def _evo_key(params: Dict[str, int]) -> Tuple[int, int, int, int]:
    return tuple(int(params[g]) for g in _EVO_GENES)  # type: ignore[return-value]


def _eval_params_over_eval(
    cfg: OptConfig,
    engine: ConditionalProbEngine,
    grid: pd.DataFrame,
    eval_steps: List[int],
    params: Dict[str, int],
) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]], float]:
    """Score one hyperparameter set over EVAL via the greedy portfolio selection.

    This is the shared fitness/eval for the evolutionary search — the same per-step computation
    the greedy/bandit strategies run. Returns ``(rows, diag_rows, fitness)`` where fitness is the
    total EVAL ``net_eur`` (ranks identically to E1 ``edge_eur``, since the random baseline is a
    genome-independent constant), with summed ``q_any`` as an infinitesimal deterministic tiebreak.
    """
    rows: List[Dict[str, Any]] = []
    diag_rows: List[Dict[str, Any]] = []
    total_net = 0.0
    total_qany = 0.0
    mk = int(params["max_overlap_k"])
    sm = int(params["shortlist_m"])
    bm = int(params["beam"])
    ht = int(params["hit_threshold"])

    for idx in (int(x) for x in eval_steps):
        step_df = grid[grid["dataset_index"] == idx]
        if step_df.empty:
            continue
        true_ticket = _true_ticket_from_step(step_df, cfg.ts_list)
        shortlists = engine.build_shortlists_for_step(step_df, shortlist_m=sm)
        pool = engine.build_ticket_pool_beam(shortlists, beam=bm)
        tickets, q_list, q_any = select_portfolio_greedy(
            cfg, engine, pool, shortlists,
            max_tickets=int(cfg.max_tickets_per_draw), max_overlap_k=mk, hit_threshold=ht,
        )
        econ = compute_portfolio_economics(
            tickets, true_ticket, payout_by_hits=cfg.payout_by_hits, ticket_cost_eur=cfg.ticket_cost_eur,
        )
        step_profit = float(econ["net_eur"])
        max_hits = int(econ["best_hits"])
        total_net += step_profit
        total_qany += float(q_any)

        rows.append({"dataset_index": idx, "tickets": int(len(tickets)), "profit": step_profit, "max_hits": max_hits})
        diag_rows.append(
            {
                "optimizer": "evolutionary",
                "dataset_index": idx,
                "tickets_count": int(len(tickets)),
                "tickets": tickets_to_str(tickets),
                "q_per_ticket": list_to_str(q_list),
                "q_any": float(q_any),
                "hit_threshold": ht,
                "realized_max_hits": int(max_hits),
                "success_ge_H": int(1 if max_hits >= ht else 0),
                "profit": float(step_profit),
                "arm": "",
            }
        )

    fitness = float(total_net) + 1e-9 * float(total_qany)
    return rows, diag_rows, float(fitness)


def run_evolutionary(
    cfg: OptConfig,
    opt_run_id: str,
    state: Dict[str, Any],
    grid: pd.DataFrame,
    engine: ConditionalProbEngine,
    eval_steps: List[int],
    train_steps: List[int],
) -> StrategyResult:
    """Seeded genetic algorithm over ``{max_overlap_k, shortlist_m, beam, hit_threshold}`` (E6.2).

    Fitness is the EVAL portfolio economics (:func:`_eval_params_over_eval`). Selection (tournament),
    crossover (uniform per-gene), and mutation (per-gene resample) are all driven by a single
    ``random.Random(cfg.seed)``, and every genome's evaluation is deterministic, so the whole search
    is reproducible under ``seed``. The best genome is carried across generations (elitism) and the
    returned best is taken over every genome evaluated, so it is never worse than the initial
    population's best. The winning genome's per-step run populates ``diag_rows``/``summary`` (keyed
    ``optimizer="evolutionary"``) exactly like the other strategies.

    The search is bounded (``evo_generations`` x ``evo_pop_size``, memoized), so it runs in one call
    and caches its whole result in state for idempotent resume.
    """
    stage_name = "evo"
    st = state.setdefault("stages", {}).setdefault(stage_name, {"done": False})

    if st.get("done") and st.get("best_params") is not None:
        state["stages"][stage_name] = st
        return StrategyResult(state=state, summary=dict(st["summary"]), diag_rows=list(st["diag_rows"]))

    bounds = _evo_bounds(cfg)
    rng = random.Random(int(cfg.seed))
    pop_size = max(2, int(getattr(cfg, "evo_pop_size", 22)))
    generations = max(1, int(getattr(cfg, "evo_generations", 25)))
    tournament_k = min(3, pop_size)

    # genome key -> (rows, diag_rows, fitness); memoizes the expensive EVAL pass.
    cache: Dict[Tuple[int, int, int, int], Tuple[List[Dict[str, Any]], List[Dict[str, Any]], float]] = {}

    def evaluate(params: Dict[str, int]) -> float:
        key = _evo_key(params)
        hit = cache.get(key)
        if hit is None:
            hit = _eval_params_over_eval(cfg, engine, grid, eval_steps, params)
            cache[key] = hit
        return hit[2]

    def random_genome() -> Dict[str, int]:
        return _evo_clamp({g: rng.randint(*bounds[g]) for g in _EVO_GENES}, bounds)

    def tournament() -> Dict[str, int]:
        contenders = rng.sample(population, tournament_k) if len(population) >= tournament_k else list(population)
        best_c = contenders[0]
        best_f = evaluate(best_c)
        for c in contenders[1:]:
            f = evaluate(c)
            if f > best_f or (f == best_f and _evo_key(c) < _evo_key(best_c)):
                best_c, best_f = c, f
        return dict(best_c)

    def crossover(p1: Dict[str, int], p2: Dict[str, int]) -> Dict[str, int]:
        return {g: (p1[g] if rng.random() < 0.5 else p2[g]) for g in _EVO_GENES}

    def mutate(child: Dict[str, int]) -> Dict[str, int]:
        out = dict(child)
        for g in _EVO_GENES:
            if rng.random() < 0.3:
                lo, hi = bounds[g]
                out[g] = rng.randint(lo, hi)
        return _evo_clamp(out, bounds)

    def argbest() -> Tuple[Dict[str, int], float]:
        best_k: Optional[Tuple[int, int, int, int]] = None
        best_f = float("-inf")
        for k, (_, _, fit) in cache.items():
            if fit > best_f or (fit == best_f and (best_k is None or k < best_k)):
                best_f, best_k = fit, k
        assert best_k is not None
        return dict(zip(_EVO_GENES, best_k)), float(best_f)

    # Generation 0: the configured defaults (so "initial best" is well-defined) plus random genomes.
    seed_params = _evo_clamp({g: int(getattr(cfg, g)) for g in _EVO_GENES}, bounds)
    population: List[Dict[str, int]] = [seed_params] + [random_genome() for _ in range(pop_size - 1)]

    _p(f"[OPT][{stage_name}] start: GA pop={pop_size} gens={generations} eval_steps={len(eval_steps)}", cfg=cfg)
    t_stage_start = time.monotonic()
    t_last_print = 0.0

    for p in population:
        evaluate(p)
    initial_best_params, initial_best_fitness = argbest()

    for gen in range(generations):
        elite, _ = argbest()
        next_pop: List[Dict[str, int]] = [dict(elite)]
        while len(next_pop) < pop_size:
            child = mutate(crossover(tournament(), tournament()))
            next_pop.append(child)
        population = next_pop
        for p in population:
            evaluate(p)
        t_last_print = _progress_report(
            cfg=cfg, stage_name=stage_name, pos_done=gen + 1, pos_total=generations,
            t_stage_start=t_stage_start, t_last_print=t_last_print, force=False,
        )

    _progress_report(
        cfg=cfg, stage_name=stage_name, pos_done=generations, pos_total=generations,
        t_stage_start=t_stage_start, t_last_print=t_last_print, force=True,
    )

    best_params, best_fitness = argbest()
    rows, diag_rows, _ = cache[_evo_key(best_params)]

    summary = eval_summary(rows, cfg)
    summary["best_params"] = dict(best_params)
    summary["best_fitness"] = float(best_fitness)
    summary["initial_best_params"] = dict(initial_best_params)
    summary["initial_best_fitness"] = float(initial_best_fitness)
    summary["generations"] = int(generations)
    summary["pop_size"] = int(pop_size)
    summary["evaluations"] = int(len(cache))

    st["done"] = True
    st["best_params"] = dict(best_params)
    st["rows"] = rows
    st["diag_rows"] = diag_rows
    st["summary"] = summary
    state["stages"][stage_name] = st
    return StrategyResult(state=state, summary=summary, diag_rows=diag_rows)
