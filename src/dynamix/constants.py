# --------------
# src/dynamix/constants.py
# --------------
"""
Central configuration for the DynaMix Lottery Forecasting System.

Post-refactor layout assumptions
--------------------------------
- This module lives at: src/dynamix/constants.py
- Repo root contains entrypoints (run_cli.py, orchestrator.py, stat.py, run_tests.py, etc.)
- Data file may live at repo root (DATA.csv) OR be overridden by env/CLI in data_utils.

Key design objectives
---------------------
- Support INDEX_MODE="event" for duplicate dates and strict row/event semantics.
- Keep all filesystem paths anchored to REPO_ROOT (not src/), so moving code into src/
  does not break input/output paths.
- Provide explicit OUTPUT_REPORTS_DIR for consistent reporting/export locations.
- Keep backward-compatible aliases where historically referenced by older modules/tests.
"""

from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import List


# ----------------------------------------------------------------------
# 0. Repository path resolution
# ----------------------------------------------------------------------
# This file is expected at: <REPO_ROOT>/src/dynamix/constants.py
# Therefore:
#   MODULE_DIR = <REPO_ROOT>/src/dynamix
#   SRC_DIR    = <REPO_ROOT>/src
#   REPO_ROOT  = <REPO_ROOT>
MODULE_DIR: Path = Path(__file__).resolve().parent
SRC_DIR: Path = MODULE_DIR.parent
REPO_ROOT: Path = SRC_DIR.parent

# Compatibility alias (older code may expect PROJECT_ROOT)
PROJECT_ROOT: Path = REPO_ROOT


# ----------------------------------------------------------------------
# 1. Project and filesystem layout
# ----------------------------------------------------------------------

# Main data and repository locations
DATA_FILE: Path = REPO_ROOT / "DATA.csv"
DYNAMIX_REPO_DIR: Path = REPO_ROOT / "DynaMix-python"

# Output directories
OUTPUT_DIR: Path = REPO_ROOT / "Output"
OUTPUT_REPORTS_DIR: Path = OUTPUT_DIR / "Reports"
OUTPUT_GRAPHS_DIR: Path = OUTPUT_REPORTS_DIR / "Graphs"  # prefer Reports/Graphs now
OUTPUT_LOGS_DIR: Path = OUTPUT_DIR / "Logs"
OUTPUT_STATS_DIR: Path = OUTPUT_DIR / "Stats"

# Compatibility aliases (some older modules may still refer to these)
OUTPUT_PLOTS_DIR: Path = OUTPUT_GRAPHS_DIR

# Model cache
MODEL_CACHE_DIR: Path = REPO_ROOT / "model_cache"
MODEL_CACHE_ENABLED: bool = True

# Parallelism defaults (used by stat.py; can be overridden)
STATS_MAX_WORKERS: int = 7


# ----------------------------------------------------------------------
# 1b. Optional environment overrides (safe, non-breaking)
# ----------------------------------------------------------------------
# You can override these in PowerShell/CMD without editing code:
#   set DYNAMIX_DATA_FILE=F:\path\to\DATA.csv
#   set DYNAMIX_OUTPUT_DIR=F:\path\to\Output
#   set DYNAMIX_MODEL_CACHE_DIR=F:\path\to\model_cache
_env_data = os.environ.get("DYNAMIX_DATA_FILE", "").strip()
if _env_data:
    DATA_FILE = Path(_env_data)

_env_out = os.environ.get("DYNAMIX_OUTPUT_DIR", "").strip()
if _env_out:
    OUTPUT_DIR = Path(_env_out)
    OUTPUT_REPORTS_DIR = OUTPUT_DIR / "Reports"
    OUTPUT_GRAPHS_DIR = OUTPUT_REPORTS_DIR / "Graphs"
    OUTPUT_LOGS_DIR = OUTPUT_DIR / "Logs"
    OUTPUT_STATS_DIR = OUTPUT_DIR / "Stats"
    OUTPUT_PLOTS_DIR = OUTPUT_GRAPHS_DIR

_env_cache = os.environ.get("DYNAMIX_MODEL_CACHE_DIR", "").strip()
if _env_cache:
    MODEL_CACHE_DIR = Path(_env_cache)


# ----------------------------------------------------------------------
# 2. Data and time-series configuration
# ----------------------------------------------------------------------

DATE_COL: str = "Date"
DATE_FORMAT: str = "%d/%m/%Y"

TS_COLUMNS: List[str] = [f"TS_{i}" for i in range(1, 8)]
EXPECTED_NUM_SERIES: int = 7

# "event"    = index is event-number-based (allows duplicate dates, strict row sequence)
# "calendar" = strictly date-based (enforces daily frequency, deduplicates dates)
INDEX_MODE: str = "event"


# ----------------------------------------------------------------------
# Event-mode identity and ordering policy
# ----------------------------------------------------------------------
# In INDEX_MODE="event", timestamps are metadata and are NOT a stable identity.
# Each row is one unique event, identified by EventID (0..N-1) in dataset order.
EVENT_ID_COL: str = "EventID"
EVENT_INDEX_NAME: str = "EventID"
EVENT_DATE_COL: str = DATE_COL

# Ordering rules for event mode:
EVENT_PRESERVE_FILE_ORDER: bool = True
EVENT_SORT_BY_DATE_IF_NO_EVENT_ID: bool = False

# Forecast horizon index naming for event mode (t+1..t+H).
FORECAST_STEP_INDEX_NAME: str = "ForecastStep"
EVENT_FORECAST_ANCHOR_TO_LAST_EVENT_ID: bool = True

# Frequency used ONLY if INDEX_MODE="calendar"
FREQ: str = "D"
ALLOW_MISSING_DAYS: bool = True

# Global minimum history for core forecasting (GUI/CLI)
MIN_HISTORY_LENGTH: int = 200


# ----------------------------------------------------------------------
# TS domain validation (lottery integrity)
# ----------------------------------------------------------------------
TS_REQUIRE_INTEGERS: bool = True
TS_INTEGER_TOL: float = 1e-6
TS_COERCE_FLOATS_TO_INT: bool = True


# ----------------------------------------------------------------------
# 3. Global forecast configuration
# ----------------------------------------------------------------------
FH: int = 1
FH_MAX: int = 30
MAX_FORECAST_TIME_SECONDS: int = 20


# ----------------------------------------------------------------------
# 4. DynaMix model configuration (ALRNN / LSTM / GRU)
# ----------------------------------------------------------------------
try:
    import torch  # type: ignore

    DYNAMIX_DEVICE: str = "cuda" if torch.cuda.is_available() else "cpu"
except Exception:
    DYNAMIX_DEVICE = "cpu"

CONTEXT_MAX_STEPS: int = 2048
DYNAMIX_STANDARDIZE: bool = False
DYNAMIX_PREPROCESSING_METHOD: str = "pos_embedding"
DYNAMIX_FIT_NONSTATIONARY: bool = False

# HF model identifier (3D ALRNN family)
DYNAMIX_HF_MODEL_NAME: str = "dynamix-3d-alrnn-v1.0"

MODEL_NAME_ALRNN: str = "ALRNN"
MODEL_NAME_LSTM: str = "LSTM"
MODEL_NAME_GRU: str = "GRU"

# Max usable dimensions per architecture
ALRNN_MAX_DIMS: int = 1
LSTM_MAX_DIMS: int = 3
GRU_MAX_DIMS: int = 100

DYNAMIX_MODEL_FAMILY: str = "dynamix_zero_shot"


# ----------------------------------------------------------------------
# 5. Sparse PCE-NARX configuration
# ----------------------------------------------------------------------
PCE_ENABLED: bool = True
PCE_TARGET_COL: str = "TS_1"
PCE_FREQ: str = FREQ
PCE_LAGS: int = 5
PCE_MIN_SAMPLES: int = 50
PCE_POLY_DEGREE: int = 2
PCE_LASSO_ALPHAS = [1e-4, 1e-3, 1e-2]
PCE_LASSO_CV_FOLDS: int = 3
PCE_FH: int = FH
PCE_Z_SCORE: float = 1.645
PCE_RANDOM_STATE: int = 42

# Important: PCE backtesting is univariate (no exogenous TS by default)
PCE_USE_OTHER_TS_AS_EXOG: bool = False

# Enforce strict row-based semantics for PCE.
PCE_STRICT_ROW_INDEX: bool = True


# ----------------------------------------------------------------------
# 6. Darts configuration
# ----------------------------------------------------------------------
DARTS_ENABLED: bool = True
DARTS_MODEL_TYPE: str = "NBEATS"
DARTS_INPUT_CHUNK_LENGTH: int = 12
DARTS_OUTPUT_CHUNK_LENGTH: int = FH

# Training epochs
DARTS_N_EPOCHS: int = 150
# Backward-compat alias: some wrappers read DARTS_EPOCHS
DARTS_EPOCHS: int = DARTS_N_EPOCHS

DARTS_DEVICE: str = DYNAMIX_DEVICE

# Force FALSE to ensure independence of variables (global setting)
DARTS_USE_MULTIVARIATE: bool = False

# Event-mode Darts policy (row-based index)
DARTS_STRICT_ROW_INDEX: bool = True


# ----------------------------------------------------------------------
# 7. Plotting and export configuration
# ----------------------------------------------------------------------
PLOTLY_TEMPLATE: str = "plotly_white"
PLOTLY_SHOW_LEGEND: bool = True
PLOTLY_WIDTH: int = 1200
PLOTLY_HEIGHT: int = 600

# CSV Parsing / Export settings
CSV_DECIMAL: str = "."
CSV_SEPARATOR: str = ","
CSV_ENCODING: str = "utf-8-sig"

HTML_FILENAME_PATTERN: str = "{series}_dynamix_forecast_{timestamp}.html"
CSV_FILENAME_PATTERN: str = "{series}_forecast_{timestamp}.csv"

# Export switches (general)
EXPORT_ENABLED: bool = False


# ----------------------------------------------------------------------
# 8. GUI configuration
# ----------------------------------------------------------------------
APP_NAME: str = "DynaMix Lottery Forecasting System"
GUI_TITLE: str = APP_NAME
GUI_MIN_WIDTH: int = 900
GUI_MIN_HEIGHT: int = 600
GUI_FONT_FAMILY: str = "Segoe UI"
GUI_FONT_SIZE: int = 10
GUI_DEFAULT_FONT = (GUI_FONT_FAMILY, GUI_FONT_SIZE)
GUI_BG_COLOR: str = "#f0f0f0"
GUI_FG_COLOR: str = "#000000"
GUI_BUTTON_BG: str = "#e0e0e0"
GUI_BUTTON_FG: str = "#000000"
GUI_STATUS_BAR_HEIGHT: int = 22
GUI_PROGRESS_UPDATE_INTERVAL_MS: int = 50
GUI_DEFAULT_FORECAST_HORIZON: int = FH
GUI_MAX_FORECAST_HORIZON: int = FH_MAX
GUI_SERIES_DISPLAY_NAMES = TS_COLUMNS


# ----------------------------------------------------------------------
# 9. Logging & Misc
# ----------------------------------------------------------------------
LOG_FILE: Path = OUTPUT_LOGS_DIR / "dynamix_app.log"
LOG_LEVEL: int = logging.INFO
LOG_FORMAT: str = "%(asctime)s [%(levelname)s] %(name)s: %(message)s"
LOG_DATE_FORMAT: str = "%Y-%m-%d %H:%M:%S"
LOG_TO_CONSOLE: bool = True
DEBUG_MODE: bool = False
STRICT_VALIDATION: bool = True


# ----------------------------------------------------------------------
# 10. Stat / Backtesting defaults
# ----------------------------------------------------------------------
# History requirement for statistics; can be lower than global MIN_HISTORY_LENGTH
STATS_MIN_HISTORY: int = 50
STATS_PROGRESS_EVERY_STEPS: int = 1
STATS_CHECKPOINT_EVERY_STEPS: int = 10

# Optional switches to reduce runtime of stats
STATS_ENABLE_DYNAMIX: bool = True
STATS_ENABLE_PCE: bool = True
STATS_ENABLE_DARTS: bool = True

# Multi-hit and overlay witness settings
STATS_MULTI_HIT_THRESHOLD: int = 3

STATS_RECORD_OVERLAY_WITNESSES: bool = True
STATS_OVERLAY_MIN_HITS_TO_RECORD: int = 4
STATS_OVERLAY_STORE_ALL_HITS: bool = True
STATS_OVERLAY_MAX_CANDIDATES_PER_TS: int = 20

# Error capturing
STATS_STORE_RECENT_ERRORS: bool = True
STATS_RECENT_ERRORS_CAP: int = 200

# Candidate-grid export defaults (stat.py uses these)
STATS_EXPORT_GRID: bool = True
STATS_EXPORT_FLUSH_EVERY_STEPS: int = STATS_CHECKPOINT_EVERY_STEPS
# Optional explicit run id; leave None for auto
STATS_EXPORT_RUN_ID = None


# ----------------------------------------------------------------------
# 10b. Training window (rolling-origin training slice control)
# ----------------------------------------------------------------------
"""
TRAINING_WINDOW_ROUNDS controls how much recent history is used as the training
set during rolling-origin backtests (stat.py) and any other iterative training loops.

Interpretation (rounds == rows of the cleaned ts_df):

- TRAINING_WINDOW_ROUNDS = 0:
    No window. Use all available history up to the current step.

- TRAINING_WINDOW_ROUNDS = N (N > 0):
    Use only the last N rows (rounds) of history for training at each step.
"""
TRAINING_WINDOW_ROUNDS: int = 235
TRAINING_WINDOW_ENFORCE_MIN: bool = True
TRAINING_WINDOW_MAX_ROUNDS: int = 0
