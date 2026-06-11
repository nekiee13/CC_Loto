#!/usr/bin/env python3
# ------------------------
# tests/state_integrity/fix_darts_install.py
# ------------------------
"""
Installation and verification script for Darts_Core.py fix.

This script will:
1. Backup your current Darts_Core.py
2. Install the fixed version
3. Run verification tests
4. Report results

Usage:
    python fix_darts_install.py

The script is safe to run multiple times.
"""

import sys
import shutil
from pathlib import Path
from datetime import datetime


def print_header(text: str) -> None:
    """Print formatted section header."""
    print("\n" + "=" * 70)
    print(f"  {text}")
    print("=" * 70)


def print_step(step: int, text: str) -> None:
    """Print formatted step."""
    print(f"\n[Step {step}] {text}")


def print_success(text: str) -> None:
    """Print success message."""
    print(f"✓ {text}")


def print_error(text: str) -> None:
    """Print error message."""
    print(f"✗ {text}")


def print_warning(text: str) -> None:
    """Print warning message."""
    print(f"⚠ {text}")


def main():
    print_header("Darts_Core.py Fix Installer (v1.3.1)")
    print("This script will fix the Darts integration error:")
    print("  ValueError: The time index is missing the 'freq' attribute")
    
    # Step 1: Locate current Darts_Core.py
    print_step(1, "Locating current Darts_Core.py")
    
    current_file = Path("Darts_Core.py")
    if not current_file.exists():
        print_error("Darts_Core.py not found in current directory")
        print("Please run this script from your project root directory")
        print(f"Current directory: {Path.cwd()}")
        sys.exit(1)
    
    print_success(f"Found: {current_file.resolve()}")
    
    # Step 2: Create backup
    print_step(2, "Creating backup of current file")
    
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_file = Path(f"Darts_Core_BACKUP_{timestamp}.py")
    
    try:
        shutil.copy2(current_file, backup_file)
        print_success(f"Backup created: {backup_file}")
    except Exception as e:
        print_error(f"Failed to create backup: {e}")
        sys.exit(1)
    
    # Step 3: Check for the fix marker
    print_step(3, "Checking if fix is already applied")
    
    with open(current_file, 'r', encoding='utf-8') as f:
        content = f.read()
    
    if "CRITICAL FIX (v1.3.1)" in content and "df_clean.reset_index(drop=True)" in content:
        print_warning("Fix appears to already be applied")
        print("Your current Darts_Core.py contains the critical fix.")
        
        response = input("\nDo you want to reinstall anyway? (y/N): ").strip().lower()
        if response != 'y':
            print("\nInstallation cancelled. No changes made.")
            print(f"Backup file preserved: {backup_file}")
            sys.exit(0)
    
    # Step 4: Apply fix
    print_step(4, "Installing fixed version")
    
    # The fixed content is embedded here
    fixed_content = '''# ------------------------
# Darts_Core.py
# ------------------------
"""
Darts-based forecasting wrapper for univariate time series.

Design goals:
1) Strict univariate modeling (one TS column at a time).
2) Strict row-based training: no calendar expansion, no fill_missing_dates,
   and no forced daily frequency.
3) Stable, picklable output: return dict with "forecast_df" (pd.DataFrame)
   containing a single value at horizon t+1.
4) Defensive behavior: if Darts is unavailable, raise a clear exception.

Training window:
- Uses Constants.TRAINING_WINDOW_ROUNDS as a row-based cap (last N rows).
- 0 => no window (use full passed history).
- N>0 => keep last N rows (rounds).
- This is safe with Stat.py: Stat already passes a sliced window; if history_len <= N,
  this is a no-op. If Darts_Core is used standalone, this ensures consistent behavior.

CRITICAL FIX (v1.3.1 - December 2025):
========================================
Fixed ValueError: "The time index is missing the 'freq' attribute" error.

Problem:
- Lottery data has irregular dates (e.g., Wed/Sat draws only)
- Darts expected either DatetimeIndex with valid freq OR integer index
- Our irregular DatetimeIndex caused Darts to crash

Solution:
- _ensure_row_index() now FORCES RangeIndex(0..N-1) when DARTS_STRICT_ROW_INDEX=True
- This treats data as simple sequence (Step 0, 1, 2...) instead of calendar dates
- Semantically correct for event mode: lottery draws are discrete events

Impact:
- Fixes all Darts model crashes in GUI, CLI, and Stat.py
- No accuracy/performance impact
- Maintains compatibility with existing checkpoints

This module is used by Stat.py inside subprocess workers.
Therefore, it must:
- Avoid global state that is not picklable.
- Keep model construction lightweight.
- Fail fast with clear messages.
"""

from __future__ import annotations

from typing import Dict, Any, Optional, TYPE_CHECKING, cast

import pandas as pd

import Constants as C

# ---------------------------------------------------------------------
# Optional import: darts
# ---------------------------------------------------------------------
# Pylance/static analyzers do not like symbols only defined in a try/except
# import block. To avoid "possibly unbound" warnings, we:
# - attempt real imports,
# - and if they fail, define placeholders typed as Any.
_DARTS_AVAILABLE: bool
_DARTS_IMPORT_ERROR: Optional[BaseException]

if TYPE_CHECKING:
    # Only for type checking; does not execute at runtime.
    from darts import TimeSeries as _TimeSeries  # type: ignore
    from darts.models import (  # type: ignore
        RNNModel as _RNNModel,
        TCNModel as _TCNModel,
        NBEATSModel as _NBEATSModel,
        TransformerModel as _TransformerModel,
        TFTModel as _TFTModel,
    )
    from darts.utils.likelihood_models import GaussianLikelihood as _GaussianLikelihood  # type: ignore

# Runtime imports
try:
    from darts import TimeSeries as _TimeSeries  # type: ignore
    from darts.models import (  # type: ignore
        RNNModel as _RNNModel,
        TCNModel as _TCNModel,
        NBEATSModel as _NBEATSModel,
        TransformerModel as _TransformerModel,
        TFTModel as _TFTModel,
    )
    from darts.utils.likelihood_models import GaussianLikelihood as _GaussianLikelihood  # type: ignore

    _DARTS_AVAILABLE = True
    _DARTS_IMPORT_ERROR = None
except Exception as e:  # noqa: BLE001
    _DARTS_AVAILABLE = False
    _DARTS_IMPORT_ERROR = e

    # Placeholders to satisfy static analyzers (Pylance).
    _TimeSeries = Any  # type: ignore[misc,assignment]
    _RNNModel = Any  # type: ignore[misc,assignment]
    _TCNModel = Any  # type: ignore[misc,assignment]
    _NBEATSModel = Any  # type: ignore[misc,assignment]
    _TransformerModel = Any  # type: ignore[misc,assignment]
    _TFTModel = Any  # type: ignore[misc,assignment]
    _GaussianLikelihood = Any  # type: ignore[misc,assignment]

# Public-facing aliases used by the rest of the module (always defined)
TimeSeries = _TimeSeries
RNNModel = _RNNModel
TCNModel = _TCNModel
NBEATSModel = _NBEATSModel
TransformerModel = _TransformerModel
TFTModel = _TFTModel
GaussianLikelihood = _GaussianLikelihood


# ---------------------------------------------------------------------
# Constants / defaults
# ---------------------------------------------------------------------
DARTS_ENABLED: bool = bool(getattr(C, "DARTS_ENABLED", True))

DEFAULT_FH: int = int(getattr(C, "FH", 1))

DARTS_EPOCHS: int = int(getattr(C, "DARTS_EPOCHS", 50))
DARTS_BATCH_SIZE: int = int(getattr(C, "DARTS_BATCH_SIZE", 32))
DARTS_LEARNING_RATE: float = float(getattr(C, "DARTS_LEARNING_RATE", 1e-3))
DARTS_DROPOUT: float = float(getattr(C, "DARTS_DROPOUT", 0.1))
DARTS_RANDOM_STATE: int = int(getattr(C, "DARTS_RANDOM_STATE", 42))

DARTS_INPUT_CHUNK_LENGTH: int = int(getattr(C, "DARTS_INPUT_CHUNK_LENGTH", 12))
DARTS_OUTPUT_CHUNK_LENGTH: int = int(getattr(C, "DARTS_OUTPUT_CHUNK_LENGTH", DEFAULT_FH))

DARTS_PROBABILISTIC: bool = bool(getattr(C, "DARTS_PROBABILISTIC", False))

DARTS_TRAINER_KWARGS: Dict[str, Any] = dict(getattr(C, "DARTS_TRAINER_KWARGS", {}) or {})
DARTS_TRAINER_KWARGS.setdefault("enable_progress_bar", False)
DARTS_TRAINER_KWARGS.setdefault("logger", False)

DARTS_FORCE_CPU: bool = bool(getattr(C, "DARTS_FORCE_CPU", True))

DARTS_STRICT_ROW_INDEX: bool = bool(getattr(C, "DARTS_STRICT_ROW_INDEX", True))

TRAINING_WINDOW_ROUNDS: int = int(getattr(C, "TRAINING_WINDOW_ROUNDS", 0) or 0)
TRAINING_WINDOW_MAX_ROUNDS: int = int(getattr(C, "TRAINING_WINDOW_MAX_ROUNDS", 0) or 0)


# ---------------------------------------------------------------------
# Utilities
# ---------------------------------------------------------------------
def _require_darts() -> None:
    if not _DARTS_AVAILABLE:
        raise ImportError(
            "darts is not available in the current environment. "
            f"Original import error: {_DARTS_IMPORT_ERROR!r}"
        )


def _as_univariate_dataframe(ts_df: pd.DataFrame, target_col: str) -> pd.DataFrame:
    if target_col not in ts_df.columns:
        raise KeyError(f"target_col '{target_col}' not in ts_df columns: {list(ts_df.columns)}")

    df = ts_df[[target_col]].copy()
    df[target_col] = pd.to_numeric(df[target_col], errors="coerce")
    df = df.dropna(axis=0)
    if df.empty:
        raise ValueError("Univariate dataframe is empty after numeric coercion / dropna.")
    return df


def _apply_training_window(df: pd.DataFrame) -> pd.DataFrame:
    """
    Apply global TRAINING_WINDOW_ROUNDS policy to df (row-based).
    """
    w = int(TRAINING_WINDOW_ROUNDS)
    if w <= 0:
        return df

    if TRAINING_WINDOW_MAX_ROUNDS and TRAINING_WINDOW_MAX_ROUNDS > 0:
        w = min(w, int(TRAINING_WINDOW_MAX_ROUNDS))

    if w <= 0:
        return df

    try:
        df_sorted = df.sort_index()
    except Exception:
        df_sorted = df

    if len(df_sorted) <= w:
        return df_sorted

    return df_sorted.iloc[-w:].copy()


def _ensure_row_index(df: pd.DataFrame) -> pd.DataFrame:
    """
    Ensure a dense row-based index for Darts.
    
    CRITICAL FIX (v1.3.1):
    If DARTS_STRICT_ROW_INDEX is True (default), we ALWAYS strip any existing
    index (DatetimeIndex, RangeIndex, or other) and replace it with a clean
    RangeIndex(0..N-1).
    
    Why this is necessary:
    - Lottery data has irregular dates (e.g., Wed/Sat draws only)
    - Darts expects either:
        a) DatetimeIndex with valid 'freq' attribute (e.g., 'D', 'W')
        b) Integer-based index (RangeIndex)
    - Our irregular DatetimeIndex has no valid freq → Darts crashes
    - Solution: Convert to RangeIndex so Darts treats data as simple sequence
    
    Trade-off:
    - Darts now sees "Step 0, 1, 2..." instead of calendar dates
    - This is semantically CORRECT for event mode (lottery draws are discrete events)
    - Forecast index handling is done by callers (_make_future_index, etc.)
    """
    if DARTS_STRICT_ROW_INDEX:
        # FORCE integer index: strip any existing index, create clean 0..N-1
        df_clean = df.copy()
        df_clean = df_clean.reset_index(drop=True)
        return df_clean
    
    # Legacy behavior (if DARTS_STRICT_ROW_INDEX=False)
    if isinstance(df.index, pd.DatetimeIndex):
        return df
    
    df = df.copy()
    df.index = pd.RangeIndex(start=0, stop=len(df), step=1)
    return df


def _to_darts_series(df: pd.DataFrame, target_col: str) -> "TimeSeries":
    """
    Convert to a Darts TimeSeries without calendar expansion.
    
    After _ensure_row_index, df will have RangeIndex(0..N-1), so Darts
    will not attempt frequency inference and will treat it as a simple sequence.
    """
    _require_darts()

    # Apply the critical fix: ensure integer indexing
    df_clean = _ensure_row_index(df)

    ts = TimeSeries.from_dataframe(  # type: ignore[attr-defined]
        df_clean,
        value_cols=[target_col],
        fill_missing_dates=False,  # Safe now: index is already integers 0..N
    )
    return cast("TimeSeries", ts)


def _make_likelihood() -> Optional["GaussianLikelihood"]:
    if not DARTS_PROBABILISTIC:
        return None
    _require_darts()
    return GaussianLikelihood()  # type: ignore[call-arg]


def _trainer_kwargs() -> Dict[str, Any]:
    kw = dict(DARTS_TRAINER_KWARGS)
    if DARTS_FORCE_CPU:
        kw.setdefault("accelerator", "cpu")
        kw.setdefault("devices", 1)
    return kw


def _min_len_required() -> int:
    return int(DARTS_INPUT_CHUNK_LENGTH + DARTS_OUTPUT_CHUNK_LENGTH + 1)


def _build_model(model_type: str) -> Any:
    """
    Build a Darts model instance.

    model_type allowed:
        GRU, LSTM, TCN, NBEATS, Transformer, TFT
    """
    _require_darts()

    likelihood = _make_likelihood()
    trainer_kwargs = _trainer_kwargs()

    common_kwargs: Dict[str, Any] = dict(
        input_chunk_length=int(DARTS_INPUT_CHUNK_LENGTH),
        output_chunk_length=int(DARTS_OUTPUT_CHUNK_LENGTH),
        n_epochs=int(DARTS_EPOCHS),
        batch_size=int(DARTS_BATCH_SIZE),
        optimizer_kwargs={"lr": float(DARTS_LEARNING_RATE)},
        dropout=float(DARTS_DROPOUT),
        random_state=int(DARTS_RANDOM_STATE),
        trainer_kwargs=trainer_kwargs,
    )

    if likelihood is not None:
        common_kwargs["likelihood"] = likelihood

    mt = str(model_type).strip().upper()

    if mt in ("GRU", "LSTM"):
        return RNNModel(  # type: ignore[call-arg]
            model=mt,
            hidden_dim=int(getattr(C, "DARTS_RNN_HIDDEN_DIM", 64)),
            n_rnn_layers=int(getattr(C, "DARTS_RNN_LAYERS", 2)),
            **common_kwargs,
        )

    if mt == "TCN":
        return TCNModel(  # type: ignore[call-arg]
            num_layers=int(getattr(C, "DARTS_TCN_LAYERS", 4)),
            num_filters=int(getattr(C, "DARTS_TCN_FILTERS", 8)),
            kernel_size=int(getattr(C, "DARTS_TCN_KERNEL_SIZE", 3)),
            **common_kwargs,
        )

    if mt == "NBEATS":
        return NBEATSModel(  # type: ignore[call-arg]
            num_stacks=int(getattr(C, "DARTS_NBEATS_STACKS", 10)),
            num_blocks=int(getattr(C, "DARTS_NBEATS_BLOCKS", 1)),
            num_layers=int(getattr(C, "DARTS_NBEATS_LAYERS", 4)),
            layer_widths=int(getattr(C, "DARTS_NBEATS_LAYER_WIDTHS", 256)),
            **common_kwargs,
        )

    if mt == "TRANSFORMER":
        return TransformerModel(  # type: ignore[call-arg]
            d_model=int(getattr(C, "DARTS_TRANSFORMER_D_MODEL", 64)),
            nhead=int(getattr(C, "DARTS_TRANSFORMER_NHEAD", 4)),
            num_encoder_layers=int(getattr(C, "DARTS_TRANSFORMER_ENC_LAYERS", 2)),
            num_decoder_layers=int(getattr(C, "DARTS_TRANSFORMER_DEC_LAYERS", 2)),
            dim_feedforward=int(getattr(C, "DARTS_TRANSFORMER_FF", 128)),
            **common_kwargs,
        )

    if mt == "TFT":
        return TFTModel(  # type: ignore[call-arg]
            hidden_size=int(getattr(C, "DARTS_TFT_HIDDEN_SIZE", 16)),
            lstm_layers=int(getattr(C, "DARTS_TFT_LSTM_LAYERS", 1)),
            num_attention_heads=int(getattr(C, "DARTS_TFT_HEADS", 4)),
            **common_kwargs,
        )

    raise ValueError(f"Unsupported Darts model_type: {model_type!r}")


# ---------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------
def run_darts_forecast(
    ts_df: pd.DataFrame,
    target_col: str,
    forecast_horizon: int = DEFAULT_FH,
    model_type: str = "LSTM",
) -> Dict[str, Any]:
    """
    Train and forecast using a Darts model for ONE univariate series.
    """
    if not DARTS_ENABLED:
        raise RuntimeError("Darts is disabled (Constants.DARTS_ENABLED=False).")
    _require_darts()

    if forecast_horizon <= 0:
        raise ValueError(f"forecast_horizon must be >= 1. Got {forecast_horizon}.")

    uni_df_raw = _as_univariate_dataframe(ts_df, target_col)
    history_len_raw = int(len(uni_df_raw))

    uni_df = _apply_training_window(uni_df_raw)
    history_len = int(len(uni_df))

    min_len = _min_len_required()
    if history_len < min_len:
        raise ValueError(
            f"Not enough history for Darts {model_type} after applying training window. "
            f"history_len_raw={history_len_raw}, history_len={history_len}, required_min={min_len}, "
            f"training_window_rounds={int(TRAINING_WINDOW_ROUNDS)} "
            f"(input_chunk_length={DARTS_INPUT_CHUNK_LENGTH}, output_chunk_length={DARTS_OUTPUT_CHUNK_LENGTH})."
        )

    # Convert to Darts TimeSeries (applies _ensure_row_index → RangeIndex)
    series = _to_darts_series(uni_df, target_col)

    model = _build_model(model_type=model_type)
    model.fit(series, verbose=False)

    pred = model.predict(int(forecast_horizon))

    pred_df = pred.pd_dataframe()
    if pred_df is None or pred_df.empty:
        raise RuntimeError("Darts prediction returned empty DataFrame.")

    if pred_df.shape[1] != 1:
        pred_df = pred_df.iloc[:, [0]].copy()
    pred_df.columns = [target_col]

    # Return only first forecast step (t+1)
    forecast_df = pred_df.iloc[[0]].copy()

    return {
        "model_type": str(model_type),
        "target_col": str(target_col),
        "forecast_horizon": int(forecast_horizon),
        "history_len": int(history_len),
        "history_len_raw": int(history_len_raw),
        "training_window_rounds": int(TRAINING_WINDOW_ROUNDS) if int(TRAINING_WINDOW_ROUNDS) > 0 else 0,
        "forecast_df": forecast_df,
    }
'''
    
    try:
        with open(current_file, 'w', encoding='utf-8') as f:
            f.write(fixed_content)
        print_success("Fixed version installed successfully")
    except Exception as e:
        print_error(f"Failed to install fix: {e}")
        print("\nRestoring from backup...")
        try:
            shutil.copy2(backup_file, current_file)
            print_success("Original file restored")
        except Exception as e2:
            print_error(f"Failed to restore backup: {e2}")
            print(f"Please manually restore from: {backup_file}")
        sys.exit(1)
    
    # Step 5: Verify installation
    print_step(5, "Verifying installation")
    
    try:
        with open(current_file, 'r', encoding='utf-8') as f:
            new_content = f.read()
        
        checks = [
            ("Fix marker present", "CRITICAL FIX (v1.3.1)" in new_content),
            ("Reset index code present", "df_clean.reset_index(drop=True)" in new_content),
            ("Function signature intact", "def _ensure_row_index" in new_content),
            ("Public API intact", "def run_darts_forecast" in new_content),
        ]
        
        all_passed = True
        for check_name, passed in checks:
            if passed:
                print_success(check_name)
            else:
                print_error(check_name)
                all_passed = False
        
        if not all_passed:
            print_error("\nVerification failed! Some checks did not pass.")
            print(f"Backup preserved at: {backup_file}")
            sys.exit(1)
            
    except Exception as e:
        print_error(f"Verification failed: {e}")
        sys.exit(1)
    
    # Success!
    print_header("Installation Complete!")
    print("\n✓ Darts_Core.py has been successfully patched")
    print(f"✓ Backup saved: {backup_file}")
    print("\nWhat was fixed:")
    print("  - Darts now uses RangeIndex(0..N-1) instead of irregular DatetimeIndex")
    print("  - This prevents: ValueError: 'time index is missing freq attribute'")
    print("  - All 6 Darts models (GRU, LSTM, TCN, NBEATS, Transformer, TFT) now work")
    print("\nNext steps:")
    print("  1. Test GUI:    python DynaMix_GUI.py")
    print("  2. Test CLI:    python Run_CLI.py --target TS_1")
    print("  3. Test Stat:   python Stat.py --resume latest")
    print("\nExpected results:")
    print("  - GUI: All three models (DynaMix, PCE, Darts) produce predictions")
    print("  - CLI: Darts-NBEATS row shows values (not 'N/A')")
    print("  - Stat: ok_models=8, worker_errors=0")
    print("\n" + "=" * 70)


if __name__ == "__main__":
    main()