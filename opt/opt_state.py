# -----------------------
# opt/opt_state.py
# -----------------------
from __future__ import annotations

import gzip
import json
import os
import pickle
import re
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from .opt_config import OptConfig


_OPT_NAME_RE = re.compile(r"^opt_(\d{8})_(\d{6})$")


def _atomic_write_text(path: Path, text: str, encoding: str = "utf-8") -> None:
    # Robust even if caller forgets to create parent dirs
    path.parent.mkdir(parents=True, exist_ok=True)

    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(text, encoding=encoding)
    os.replace(str(tmp), str(path))


def _state_paths(cfg: OptConfig, opt_run_id: str) -> Tuple[Path, Path]:
    d = cfg.state_dir / opt_run_id
    d.mkdir(parents=True, exist_ok=True)
    return d / "state.pkl.gz", d / "state.json"


def save_state(cfg: OptConfig, opt_run_id: str, state: Dict[str, Any]) -> None:
    pkl_path, json_path = _state_paths(cfg, opt_run_id)
    state["updated_at"] = datetime.now().isoformat(timespec="seconds")

    raw = pickle.dumps(state, protocol=pickle.HIGHEST_PROTOCOL)
    tmp_pkl = str(pkl_path) + ".tmp"
    with gzip.open(tmp_pkl, "wb") as f:
        f.write(raw)
    os.replace(tmp_pkl, str(pkl_path))

    # Sidecar meta (safe to read without unpickling)
    config_identity = state.get("config_identity", {})
    meta = {
        "opt_run_id": opt_run_id,
        "created_at": state.get("created_at"),
        "updated_at": state.get("updated_at"),
        "grid_run_id": state.get("grid_run_id"),
        "grid_fingerprint": state.get("grid_fingerprint", {}),
        "slice": state.get("slice", {}),
        # keep both keys for compatibility/readability
        "config_identity": config_identity,
        "config": config_identity,
        "stages": sorted(list((state.get("stages") or {}).keys())),
        "results_keys": sorted(list((state.get("results") or {}).keys())),
        "resuming": bool(state.get("resuming", False)),
    }
    _atomic_write_text(json_path, json.dumps(meta, indent=2), encoding="utf-8")


def _load_state_from_path(p: Path) -> Dict[str, Any]:
    with gzip.open(p, "rb") as f:
        return pickle.loads(f.read())


def _try_parse_opt_timestamp(name: str) -> Optional[datetime]:
    """
    If name matches opt_YYYYMMDD_HHMMSS, parse to datetime; else return None.
    """
    m = _OPT_NAME_RE.match(name)
    if not m:
        return None
    ymd, hms = m.group(1), m.group(2)
    try:
        return datetime.strptime(ymd + hms, "%Y%m%d%H%M%S")
    except Exception:
        return None


def _find_latest_opt_state_dir(cfg: OptConfig) -> Optional[Path]:
    root = cfg.state_dir
    if not root.exists():
        return None

    dirs = [d for d in root.iterdir() if d.is_dir()]
    if not dirs:
        return None

    # Prefer timestamp parsing from canonical names; otherwise fall back to mtime.
    parsed: List[Tuple[datetime, Path]] = []
    unparsed: List[Path] = []

    for d in dirs:
        ts = _try_parse_opt_timestamp(d.name)
        if ts is not None:
            parsed.append((ts, d))
        else:
            unparsed.append(d)

    if parsed:
        parsed.sort(key=lambda t: t[0])
        return parsed[-1][1]

    # If none match canonical naming, fall back to mtime.
    unparsed.sort(key=lambda x: x.stat().st_mtime)
    return unparsed[-1]


def load_state_or_init(
    cfg: OptConfig,
    grid_run_id: str,
    grid_fingerprint: Dict[str, Any],
    slice_info: Dict[str, Any],
) -> Tuple[str, Dict[str, Any]]:
    resume_raw = str(cfg.resume).strip()
    resume_key = resume_raw.lower()

    if resume_key == "none":
        opt_run_id = cfg.opt_run_id.strip() or f"opt_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        state: Dict[str, Any] = {
            "resuming": False,
            "opt_run_id": opt_run_id,
            "created_at": datetime.now().isoformat(timespec="seconds"),
            "updated_at": datetime.now().isoformat(timespec="seconds"),
            "grid_run_id": grid_run_id,
            "grid_fingerprint": grid_fingerprint,
            "slice": slice_info,
            "config_identity": cfg.config_identity(),
            "seed": int(cfg.seed),
            "stages": {},  # per optimizer stage substates
            "results": {},
            "notes": [],
        }
        save_state(cfg, opt_run_id, state)
        return opt_run_id, state

    # Resume: resolve state.pkl.gz
    if resume_key == "latest":
        d = _find_latest_opt_state_dir(cfg)
        if d is None:
            raise FileNotFoundError(f"No optimization state dirs under: {cfg.state_dir}")
        p = d / "state.pkl.gz"
        if not p.exists():
            raise FileNotFoundError(f"Missing state.pkl.gz in: {d}")
        state = _load_state_from_path(p)
        state["resuming"] = True
        opt_run_id = d.name
    else:
        rp = Path(resume_raw)
        if rp.is_dir():
            p = rp / "state.pkl.gz"
            if not p.exists():
                raise FileNotFoundError(f"Resume dir missing state.pkl.gz: {p}")
            state = _load_state_from_path(p)
            state["resuming"] = True
            opt_run_id = rp.name
        elif rp.is_file() and rp.name.endswith(".pkl.gz"):
            state = _load_state_from_path(rp)
            state["resuming"] = True
            opt_run_id = rp.parent.name
        else:
            raise FileNotFoundError(f"Resume target not found: {cfg.resume}")

    # Strict validation here to avoid caller forgetting
    validate_resume_or_fail(
        loaded_state=state,
        grid_run_id=grid_run_id,
        grid_fingerprint=grid_fingerprint,
        config_identity=cfg.config_identity(),
        slice_info=slice_info,
    )

    return opt_run_id, state


def validate_resume_or_fail(
    loaded_state: Dict[str, Any],
    *,
    grid_run_id: str,
    grid_fingerprint: Dict[str, Any],
    config_identity: Dict[str, Any],
    slice_info: Dict[str, Any],
) -> None:
    if str(loaded_state.get("grid_run_id")) != str(grid_run_id):
        raise RuntimeError(
            f"Resume refused: grid_run_id mismatch ({loaded_state.get('grid_run_id')} vs {grid_run_id})."
        )

    fp0 = loaded_state.get("grid_fingerprint", {})
    for k in ["steps_hash", "schema_hash", "sample_true_hash", "n_steps"]:
        if str(fp0.get(k)) != str(grid_fingerprint.get(k)):
            raise RuntimeError(f"Resume refused: grid fingerprint mismatch at {k}.")

    cfg0 = loaded_state.get("config_identity", {})
    if json.dumps(cfg0, sort_keys=True) != json.dumps(config_identity, sort_keys=True):
        raise RuntimeError("Resume refused: config identity mismatch.")

    sl0 = loaded_state.get("slice", {})
    if json.dumps(sl0, sort_keys=True) != json.dumps(slice_info, sort_keys=True):
        raise RuntimeError("Resume refused: slice mismatch.")
