# -----------------------
# opt/opt_engine.py
# -----------------------
from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any, Dict, List, Tuple, Optional

import numpy as np
import pandas as pd

from .opt_config import OptConfig
from .opt_features import (
    TruthHistoryTables,
    compute_candidate_features_for_step,
    _canonical_pair,
    _canonical_triple,
)

# sklearn (required for conditional model)
from sklearn.linear_model import LogisticRegression
from sklearn.calibration import CalibratedClassifierCV

Ticket = Tuple[int, ...]  # general (TS count fixed by cfg.ts_list)


@dataclass(frozen=True)
class CandidateKey:
    ts: str
    model: str
    rounding_id: int
    value: int


@dataclass
class TSShortlistItem:
    value: int
    model: str
    rounding_id: int
    pred: float
    abs_err: float
    p_hit: float


@dataclass
class EngineFitInfo:
    n_train_rows: int
    features: List[str]


class ConditionalProbEngine:
    """
    Learns P(hit | features) on TRAIN only, then scores candidates per step.

    Candidate-level features:
      abs_err_bin, rank_bin, consensus_count,
      freq_global_bin, freq_ts_bin,
      gap_global_bin, gap_ts_bin,
      parity, low_high, pred_minus_rounded, pred_minus_rounded_abs

    Ticket-level adjustment (optional):
      pair/triple compatibility multiplier from TRAIN truth co-occurrence.

    Fallback behavior (requested):
      If a TS has no candidates in a step, the engine falls back to a historical
      candidate source (TRAIN truth frequency tables) and records an event.
      The caller can read events via consume_fallback_events().
    """

    def __init__(self, cfg: OptConfig, tables: TruthHistoryTables) -> None:
        self.cfg = cfg
        self.tables = tables
        self.model: Optional[CalibratedClassifierCV] = None
        self.feature_cols: List[str] = []
        self.fit_info: Optional[EngineFitInfo] = None
        self._fallback_events: List[Dict[str, Any]] = []

    def consume_fallback_events(self) -> List[Dict[str, Any]]:
        """
        Returns and clears fallback events accumulated since last call.
        """
        out = list(self._fallback_events)
        self._fallback_events.clear()
        return out

    def fit_on_train(self, grid: pd.DataFrame, train_steps: List[int]) -> None:
        train_df = grid[grid["dataset_index"].isin(train_steps)].copy()
        if train_df.empty:
            raise ValueError("TRAIN slice empty; cannot fit conditional model.")

        # Build features step-wise to get rank/consensus properly
        feat_rows: List[pd.DataFrame] = []
        for idx in sorted({int(x) for x in train_steps}):
            step_df = train_df[train_df["dataset_index"] == int(idx)]
            if step_df.empty:
                continue
            f = compute_candidate_features_for_step(
                step_df,
                ts_list=self.cfg.ts_list,
                tables=self.tables,
                abs_err_bins=self.cfg.abs_err_bins,
                rank_bins=self.cfg.rank_bins,
                freq_bins=self.cfg.freq_bins,
                gap_bins=self.cfg.gap_bins,
            )
            feat_rows.append(f)

        if not feat_rows:
            raise ValueError("No TRAIN steps produced feature rows; cannot fit conditional model.")

        df = pd.concat(feat_rows, axis=0, ignore_index=True)

        # Ensure hit is present and numeric
        if "hit" not in df.columns:
            raise ValueError("TRAIN dataframe missing 'hit' column required to fit model.")
        df["hit"] = pd.to_numeric(df["hit"], errors="coerce").fillna(0).astype(int)
        y = df["hit"].astype(int).to_numpy()

        # Feature columns (deterministic order)
        cols = [
            "abs_err_bin",
            "rank_bin",
            "consensus_count",
            "freq_global_bin",
            "freq_ts_bin",
            "gap_global_bin",
            "gap_ts_bin",
            "parity",
            "low_high",
            "pred_minus_rounded",
            "pred_minus_rounded_abs",
        ]
        missing = [c for c in cols if c not in df.columns]
        if missing:
            raise ValueError(f"Missing engineered feature columns: {missing}")

        X = df[cols].astype(float).to_numpy()

        # Base model + isotonic calibration via CV (TRAIN only)
        base = LogisticRegression(
            max_iter=400,
            solver="lbfgs",
            n_jobs=None,
        )
        cal = CalibratedClassifierCV(base, method="isotonic", cv=3)
        cal.fit(X, y)

        self.model = cal
        self.feature_cols = cols
        self.fit_info = EngineFitInfo(n_train_rows=int(len(df)), features=cols)

    def _predict_candidate_p(self, feat_df: pd.DataFrame) -> np.ndarray:
        if self.model is None:
            raise RuntimeError("Engine not fitted.")
        X = feat_df[self.feature_cols].astype(float).to_numpy()
        p = self.model.predict_proba(X)[:, 1]
        return np.clip(p, 1e-9, 1.0 - 1e-9)

    def _fallback_value_for_ts(self, ts: str) -> int:
        """
        Historical fallback candidate source:
          - chooses the most frequent TRAIN truth value for this TS if available
          - otherwise chooses most frequent global TRAIN truth value
          - otherwise 0
        """
        # TS-specific most frequent
        best_v: Optional[int] = None
        best_c = -1
        for (k_ts, v), c in self.tables.ts_value_counts.items():
            if str(k_ts) != str(ts):
                continue
            if int(c) > best_c:
                best_c = int(c)
                best_v = int(v)
        if best_v is not None:
            return int(best_v)

        # Global most frequent
        best_v2: Optional[int] = None
        best_c2 = -1
        for v, c in self.tables.global_value_counts.items():
            if int(c) > best_c2:
                best_c2 = int(c)
                best_v2 = int(v)
        if best_v2 is not None:
            return int(best_v2)

        return 0

    def build_shortlists_for_step(self, step_df: pd.DataFrame, shortlist_m: int) -> Dict[str, List[TSShortlistItem]]:
        """
        Builds per-TS shortlists. If a TS has no candidates in the step, falls back to
        a historical candidate value (TRAIN truth frequency tables) and records an event.
        """
        out: Dict[str, List[TSShortlistItem]] = {ts: [] for ts in self.cfg.ts_list}
        if step_df.empty:
            # No step data: force fallbacks for every TS (caller can decide to skip the step)
            for ts in self.cfg.ts_list:
                fb = self._fallback_value_for_ts(ts)
                out[ts] = [
                    TSShortlistItem(
                        value=int(fb),
                        model="FALLBACK_TRAIN_FREQ",
                        rounding_id=0,
                        pred=float(fb),
                        abs_err=1e9,
                        p_hit=1e-9,
                    )
                ]
                self._fallback_events.append(
                    {"ts": ts, "reason": "step_df_empty", "fallback_source": "train_truth_frequency", "fallback_value": int(fb)}
                )
            return out

        f = compute_candidate_features_for_step(
            step_df,
            ts_list=self.cfg.ts_list,
            tables=self.tables,
            abs_err_bins=self.cfg.abs_err_bins,
            rank_bins=self.cfg.rank_bins,
            freq_bins=self.cfg.freq_bins,
            gap_bins=self.cfg.gap_bins,
        )

        # Predict
        p_hat = self._predict_candidate_p(f)
        f = f.copy()
        f["p_hit"] = p_hat

        for ts in self.cfg.ts_list:
            sub = f[f["ts"] == ts].copy()
            if sub.empty:
                # Fallback candidate source + record event
                fb = self._fallback_value_for_ts(ts)
                out[ts] = [
                    TSShortlistItem(
                        value=int(fb),
                        model="FALLBACK_TRAIN_FREQ",
                        rounding_id=0,
                        pred=float(fb),
                        abs_err=1e9,
                        p_hit=1e-9,
                    )
                ]
                self._fallback_events.append(
                    {
                        "ts": ts,
                        "reason": "no_candidates_for_ts_in_step",
                        "fallback_source": "train_truth_frequency",
                        "fallback_value": int(fb),
                    }
                )
                continue

            # Pylance-safe: never call fillna on a scalar; always operate on Series
            if "abs_err" in sub.columns:
                sub["abs_err"] = pd.to_numeric(sub["abs_err"], errors="coerce").fillna(0.0).astype(float)
            else:
                sub["abs_err"] = 0.0

            # Rank by p_hit desc, abs_err asc
            sub = sub.sort_values(by=["p_hit", "abs_err"], ascending=[False, True], kind="stable")

            # Keep unique values (best per value)
            uniq: Dict[int, TSShortlistItem] = {}
            for _, r in sub.iterrows():
                v = int(r["rounded"])
                if v in uniq:
                    continue
                item = TSShortlistItem(
                    value=int(v),
                    model=str(r.get("model", "")),
                    rounding_id=int(r.get("rounding_id", 0)),
                    pred=float(r.get("pred", float(v))),
                    abs_err=float(r.get("abs_err", 0.0)),
                    p_hit=float(r.get("p_hit", 1e-9)),
                )
                uniq[v] = item
                if len(uniq) >= int(shortlist_m):
                    break

            out[ts] = list(uniq.values())

        return out

    def build_ticket_pool_beam(self, shortlists: Dict[str, List[TSShortlistItem]], beam: int) -> List[Tuple[Ticket, float]]:
        """
        Build candidate tickets via beam search on log p_hit.

        With the fallback behavior implemented in build_shortlists_for_step(),
        shortlists should always contain at least one candidate per TS.
        If a TS is still missing (caller provided incomplete dict), we will
        force a fallback here too and record it.
        """
        ts_list = self.cfg.ts_list

        # Ensure every TS has at least one option (safety net)
        for ts in ts_list:
            if not shortlists.get(ts):
                fb = self._fallback_value_for_ts(ts)
                shortlists[ts] = [
                    TSShortlistItem(
                        value=int(fb),
                        model="FALLBACK_TRAIN_FREQ",
                        rounding_id=0,
                        pred=float(fb),
                        abs_err=1e9,
                        p_hit=1e-9,
                    )
                ]
                self._fallback_events.append(
                    {"ts": ts, "reason": "missing_shortlist_key", "fallback_source": "train_truth_frequency", "fallback_value": int(fb)}
                )

        beam_list: List[Tuple[List[int], float]] = [([], 0.0)]
        for ts in ts_list:
            nxt: List[Tuple[List[int], float]] = []
            opts = shortlists[ts]
            for partial, log_s in beam_list:
                for opt in opts:
                    p = max(float(opt.p_hit), 1e-12)
                    nxt.append((partial + [int(opt.value)], log_s + math.log(p)))
            nxt.sort(key=lambda x: x[1], reverse=True)
            beam_list = nxt[: max(1, int(beam))]

        out: List[Tuple[Ticket, float]] = []
        for vals, log_s in beam_list:
            if len(vals) != len(ts_list):
                continue
            out.append((tuple(int(x) for x in vals), float(log_s)))

        # Dedupe by best score
        best: Dict[Ticket, float] = {}
        for t, s in out:
            if t not in best or s > best[t]:
                best[t] = s
        return sorted(best.items(), key=lambda x: x[1], reverse=True)

    @staticmethod
    def overlap_positions(a: Ticket, b: Ticket) -> int:
        n = min(len(a), len(b))
        return sum(1 for i in range(n) if int(a[i]) == int(b[i]))

    @staticmethod
    def poisson_binomial_prob_ge(ps: List[float], H: int) -> float:
        n = len(ps)
        H = int(H)
        # P(hits >= H): certain for H <= 0, impossible for H > n (can't exceed n positions).
        if H <= 0:
            return 1.0
        if H > n:
            return 0.0
        dp = [0.0] * (n + 1)
        dp[0] = 1.0
        for p in ps:
            ndp = dp[:]
            for k in range(n - 1, -1, -1):
                ndp[k + 1] += dp[k] * p
                ndp[k] *= (1.0 - p)
            dp = ndp
        return float(sum(dp[H:]))

    def ticket_position_ps(self, ticket: Ticket, shortlists: Dict[str, List[TSShortlistItem]]) -> List[float]:
        ps: List[float] = []
        for i, ts in enumerate(self.cfg.ts_list):
            v = int(ticket[i])
            p = 1e-9
            for opt in shortlists.get(ts, []):
                if int(opt.value) == v:
                    p = max(p, float(opt.p_hit))
                    break
            ps.append(float(np.clip(p, 1e-9, 1.0 - 1e-9)))
        return ps

    def compatibility_log_bonus(self, ticket: Ticket) -> float:
        """
        Ticket-level compatibility using TRAIN truth co-occurrence counts.
        Uses additive log bonus:
          pair_weight * sum log(1+count_pair)
        and triple_weight similarly.
        """
        if not self.cfg.use_pair_triple_compat:
            return 0.0

        ts_list = self.cfg.ts_list
        bonus = 0.0

        for i in range(len(ts_list)):
            for j in range(i + 1, len(ts_list)):
                key = _canonical_pair(ts_list[i], int(ticket[i]), ts_list[j], int(ticket[j]))
                c = int(self.tables.pair_counts.get(key, 0))
                bonus += float(self.cfg.pair_weight) * math.log(1.0 + float(c))

        for i in range(len(ts_list)):
            for j in range(i + 1, len(ts_list)):
                for k in range(j + 1, len(ts_list)):
                    key = _canonical_triple(
                        (ts_list[i], int(ticket[i])),
                        (ts_list[j], int(ticket[j])),
                        (ts_list[k], int(ticket[k])),
                    )
                    c = int(self.tables.triple_counts.get(key, 0))
                    bonus += float(self.cfg.triple_weight) * math.log(1.0 + float(c))

        return float(bonus)

    def score_ticket_q(self, ticket: Ticket, shortlists: Dict[str, List[TSShortlistItem]], H: int) -> float:
        ps = self.ticket_position_ps(ticket, shortlists)
        q = self.poisson_binomial_prob_ge(ps, H)
        bonus = self.compatibility_log_bonus(ticket)
        q2 = float(q * math.exp(bonus))
        return float(np.clip(q2, 1e-9, 1.0 - 1e-9))

    def portfolio_q_any(self, qs: List[float]) -> float:
        surv = 1.0
        for q in qs:
            surv *= (1.0 - float(q))
        return float(1.0 - surv)

    def fill_to_k_deterministic(self, ranked: List[Ticket], max_tickets: int, max_overlap_k: int) -> List[Ticket]:
        chosen: List[Ticket] = []

        def can_add(t: Ticket, k: int) -> bool:
            if t in chosen:
                return False
            return all(self.overlap_positions(t, c) <= int(k) for c in chosen)

        for t in ranked:
            if len(chosen) >= int(max_tickets):
                break
            if can_add(t, max_overlap_k):
                chosen.append(t)

        if not self.cfg.enforce_exact_k_tickets:
            return chosen

        if len(chosen) < int(max_tickets):
            for k_relax in range(int(max_overlap_k) + 1, len(self.cfg.ts_list) + 1):
                for t in ranked:
                    if len(chosen) >= int(max_tickets):
                        break
                    if can_add(t, k_relax):
                        chosen.append(t)
                if len(chosen) >= int(max_tickets):
                    break

        if len(chosen) < int(max_tickets):
            for t in ranked:
                if len(chosen) >= int(max_tickets):
                    break
                if t not in chosen:
                    chosen.append(t)

        return chosen[: int(max_tickets)]
