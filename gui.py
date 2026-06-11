# ------------------------
# gui.py
# ------------------------
"""
Tkinter GUI for the DynaMix Lottery Forecasting System.

Behavior:
- Prints a Markdown forecast table to:
  1) the GUI "Messages" box, and
  2) the launching console (stdout),
  even when CSV/HTML export is disabled.

The table shows the first forecast step (t+1) for each selected model.
If a model only produced a value for the selected target series, the other TS cells show "-".

Training window:
- Adds GUI controls for a row-based training window (rounds/rows).
- Applies the window consistently across all selected models during GUI forecasting:
    * Disabled or 0 => full history (legacy behavior)
    * Enabled and N>0 => last N rows only
- Also updates Constants.TRAINING_WINDOW_ROUNDS at runtime for consistency with
  downstream modules that read it (e.g., dynamix_core).
"""

from __future__ import annotations

import logging
import os
import queue
import sys
import threading
import traceback
from decimal import Decimal, ROUND_HALF_UP
from pathlib import Path
from types import ModuleType
from typing import Any, Dict, Optional, List, Tuple

import tkinter as tk
from tkinter import ttk, messagebox, filedialog

import numpy as np
import pandas as pd


# ----------------------------------------------------------------------
# sys.path bootstrapping for new layout
#   repo_root/
#     gui.py
#     src/dynamix/...
# ----------------------------------------------------------------------
REPO_ROOT = Path(__file__).resolve().parent
SRC_DIR = REPO_ROOT / "src"
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))
if SRC_DIR.exists() and str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))


# ----------------------------------------------------------------------
# Project imports (new src/dynamix layout)
# ----------------------------------------------------------------------
try:
    # Preferred new layout
    from src.dynamix import constants as C  # type: ignore
    from src.dynamix import data_utils as DU  # type: ignore
    from src.dynamix import pce_narx as PCE  # type: ignore
except Exception:
    # Fallback: allow running if user uses flat layout in repo root
    import constants as C  # type: ignore
    import data_utils as DU  # type: ignore
    import pce_narx as PCE  # type: ignore


# Try to import DynaMix core pipeline
try:
    from src.dynamix import dynamix_core as DCore  # type: ignore
    HAS_DYNAMIX_CORE = True
except Exception:
    try:
        import dynamix_core as DCore  # type: ignore
        HAS_DYNAMIX_CORE = True
    except Exception:
        DCore = None  # type: ignore
        HAS_DYNAMIX_CORE = False

# Try to import Darts core pipeline
DartCore: Optional[ModuleType]
try:
    from src.dynamix import darts_core as _DartCore  # type: ignore
    DartCore = _DartCore
    HAS_DARTS_CORE = True
except Exception:
    try:
        import darts_core as _DartCore  # type: ignore
        DartCore = _DartCore
        HAS_DARTS_CORE = True
    except Exception:
        DartCore = None
        HAS_DARTS_CORE = False

# Try to import Plotting utilities
try:
    from src.dynamix import plotting as Plotting  # type: ignore
    HAS_PLOTTING = True
except Exception:
    try:
        import plotting as Plotting  # type: ignore
        HAS_PLOTTING = True
    except Exception:
        Plotting = None  # type: ignore
        HAS_PLOTTING = False


# ----------------------------------------------------------------------
# Logging setup
# ----------------------------------------------------------------------
def _configure_logging() -> None:
    """
    Configure root logger according to Constants.py.
    """
    try:
        DU.ensure_output_dirs()
    except Exception:
        # GUI can still run without ensuring dirs
        pass

    handlers: List[logging.Handler] = []

    try:
        log_file_path = Path(getattr(C, "LOG_FILE", REPO_ROOT / "Output" / "Logs" / "gui.log"))
        log_file_path.parent.mkdir(parents=True, exist_ok=True)
        file_handler = logging.FileHandler(log_file_path, encoding="utf-8")
        handlers.append(file_handler)
    except Exception:
        # If file logging fails, fall back to console logging
        setattr(C, "LOG_TO_CONSOLE", True)

    if bool(getattr(C, "LOG_TO_CONSOLE", True)):
        console_handler = logging.StreamHandler()
        handlers.append(console_handler)

    logging.basicConfig(
        level=getattr(C, "LOG_LEVEL", logging.INFO),
        format=getattr(C, "LOG_FORMAT", "%(asctime)s [%(levelname)s] %(name)s: %(message)s"),
        datefmt=getattr(C, "LOG_DATE_FORMAT", "%Y-%m-%d %H:%M:%S"),
        handlers=handlers if handlers else None,
    )


_configure_logging()
log = logging.getLogger(__name__)


# ----------------------------------------------------------------------
# Helpers: formatting + rounding
# ----------------------------------------------------------------------
def _is_event_mode() -> bool:
    try:
        return str(getattr(C, "INDEX_MODE", "calendar")).lower().strip() == "event"
    except Exception:
        return False


def _round_half_up(value: float) -> int:
    """Beginner-friendly rounding used for GUI display."""
    try:
        if value is None or (isinstance(value, float) and (np.isnan(value) or np.isinf(value))):
            return 0
        d = Decimal(str(float(value)))
        return int(d.to_integral_value(rounding=ROUND_HALF_UP))
    except Exception:
        return 0


def _format_markdown_table(headers: List[str], rows: List[List[Any]]) -> str:
    """Create a Markdown table string without external dependencies."""
    str_rows: List[List[str]] = [[str(x) for x in r] for r in rows]
    widths = [len(h) for h in headers]
    for r in str_rows:
        for i, cell in enumerate(r):
            if i < len(widths):
                widths[i] = max(widths[i], len(cell))

    def fmt_row(cells: List[str]) -> str:
        padded = [cells[i].ljust(widths[i]) for i in range(len(headers))]
        return "| " + " | ".join(padded) + " |"

    header_line = fmt_row(headers)
    sep_line = "| " + " | ".join("-" * w for w in widths) + " |"
    data_lines = [fmt_row(r) for r in str_rows]
    return "\n".join([header_line, sep_line] + data_lines) + "\n"


def _format_forecast_index_label(idx0: Any, index_name: Optional[str] = None) -> str:
    """
    Mode-aware formatting for the first forecast index element.
    """
    if _is_event_mode():
        name = index_name or ""
        try:
            val_str = str(idx0)
        except Exception:
            val_str = "N/A"
        lname = name.lower() if isinstance(name, str) else ""
        if "forecast" in lname and "step" in lname:
            return f"Step={val_str}"
        if isinstance(val_str, str) and val_str.isdigit():
            return f"EventID={val_str}"
        return val_str

    # Calendar mode
    try:
        return idx0.strftime(getattr(C, "DATE_FORMAT", "%d/%m/%Y"))
    except Exception:
        try:
            return idx0.isoformat() if hasattr(idx0, "isoformat") else str(idx0)
        except Exception:
            return "N/A"


def _extract_first_step_values(
    forecast_df: pd.DataFrame,
    ts_columns: List[str],
) -> Tuple[Dict[str, float], Optional[str]]:
    """Extract first forecast step values + a mode-aware index label."""
    values: Dict[str, float] = {}
    if forecast_df is None or forecast_df.empty:
        return values, None

    row0 = forecast_df.iloc[0]
    for ts in ts_columns:
        if ts in forecast_df.columns:
            try:
                values[ts] = float(row0[ts])
            except Exception:
                pass

    idx_label: Optional[str] = None
    try:
        idx0 = forecast_df.index[0]
        idx_name = getattr(forecast_df.index, "name", None)
        idx_label = _format_forecast_index_label(idx0, str(idx_name) if idx_name is not None else None)
    except Exception:
        idx_label = None

    return values, idx_label


def _apply_training_window(ts_df: pd.DataFrame, window_rounds: int) -> pd.DataFrame:
    """Row-based training window."""
    if ts_df is None or ts_df.empty:
        return ts_df
    w = int(window_rounds)
    if w <= 0:
        return ts_df
    if len(ts_df) <= w:
        return ts_df
    return ts_df.tail(w).copy()


def _open_folder(path: Path) -> None:
    try:
        path = path.resolve()
        if not path.exists():
            path.mkdir(parents=True, exist_ok=True)

        if os.name == "nt":
            os.startfile(path)  # type: ignore[attr-defined]
            return

        if os.name == "posix":
            for cmd in ("xdg-open", "open"):
                try:
                    import subprocess

                    subprocess.Popen([cmd, str(path)])
                    return
                except Exception:
                    continue

        messagebox.showinfo("Open Folder", f"Folder path: {path}")
    except Exception:
        log.exception("Failed to open folder in file explorer.")
        messagebox.showerror("Error", f"Failed to open folder:\n{path}")


# ----------------------------------------------------------------------
# Main GUI application
# ----------------------------------------------------------------------
class DynaMixLotteryApp:
    def __init__(self, root: tk.Tk) -> None:
        self.root = root
        self.root.title(getattr(C, "GUI_TITLE", "DynaMix Lottery Forecasting System"))
        self.root.minsize(int(getattr(C, "GUI_MIN_WIDTH", 900)), int(getattr(C, "GUI_MIN_HEIGHT", 650)))

        try:
            self.root.option_add("*Font", getattr(C, "GUI_DEFAULT_FONT", "SegoeUI 10"))
        except Exception:
            pass

        self.ts_array: Optional[np.ndarray] = None
        self.date_index: Optional[pd.DatetimeIndex] = None
        self.ts_df: Optional[pd.DataFrame] = None

        self.gui_queue: "queue.Queue[tuple]" = queue.Queue()

        self.progress_var = tk.DoubleVar(value=0.0)
        self.status_var = tk.StringVar(value="Ready.")
        self.data_info_var = tk.StringVar(value="No dataset loaded.")

        display_names = list(getattr(C, "GUI_SERIES_DISPLAY_NAMES", ["TS_1", "TS_2", "TS_3", "TS_4", "TS_5", "TS_6", "TS_7"]))
        self.selected_series_var = tk.StringVar(value=display_names[0])
        self.fh_var = tk.IntVar(value=int(getattr(C, "GUI_DEFAULT_FORECAST_HORIZON", 1)))

        # Training window (GUI-controlled)
        try:
            _c_tw = int(getattr(C, "TRAINING_WINDOW_ROUNDS", 0) or 0)
        except Exception:
            _c_tw = 0
        self.training_window_enabled_var = tk.BooleanVar(value=bool(_c_tw > 0))
        self.training_window_rounds_var = tk.IntVar(value=int(_c_tw if _c_tw > 0 else 104))

        # Model selection
        self.use_dynamix_var = tk.BooleanVar(value=bool(HAS_DYNAMIX_CORE))
        self.use_pce_var = tk.BooleanVar(value=bool(getattr(C, "PCE_ENABLED", True)))
        self.use_darts_var = tk.BooleanVar(value=bool(getattr(C, "DARTS_ENABLED", True) and HAS_DARTS_CORE))

        self._forecast_thread: Optional[threading.Thread] = None
        self._forecast_running: bool = False

        self._build_menu()
        self._build_gui()

        # Important: this is one of the methods Pylance was claiming "unknown"
        self.root.after(100, self._process_gui_queue)

        log.info("GUI started.")

    # ------------------------------------------------------------------
    # Menu and layout
    # ------------------------------------------------------------------
    def _build_menu(self) -> None:
        menubar = tk.Menu(self.root)
        file_menu = tk.Menu(menubar, tearoff=False)
        file_menu.add_command(label="Load DATA.csv...", command=self.on_load_data)
        file_menu.add_separator()
        file_menu.add_command(label="Exit", command=self.on_close)
        menubar.add_cascade(label="File", menu=file_menu)

        tools_menu = tk.Menu(menubar, tearoff=False)
        tools_menu.add_command(label="Open Graphs Folder", command=self.on_open_graphs_folder)
        tools_menu.add_command(label="Open Logs Folder", command=self.on_open_logs_folder)
        tools_menu.add_separator()
        tools_menu.add_command(label="Clear Model Cache", command=self.on_clear_model_cache)
        menubar.add_cascade(label="Tools", menu=tools_menu)

        help_menu = tk.Menu(menubar, tearoff=False)
        help_menu.add_command(label="About", command=self.on_about)
        menubar.add_cascade(label="Help", menu=help_menu)

        self.root.config(menu=menubar)

    def _build_gui(self) -> None:
        top_frame = ttk.Frame(self.root, padding=10)
        top_frame.pack(side=tk.TOP, fill=tk.X)

        ttk.Button(top_frame, text="Load DATA.csv", command=self.on_load_data).pack(side=tk.LEFT)
        ttk.Label(top_frame, textvariable=self.data_info_var).pack(side=tk.LEFT, padx=10)

        config_frame = ttk.LabelFrame(self.root, text="Forecast Configuration", padding=10)
        config_frame.pack(side=tk.TOP, fill=tk.X, padx=10, pady=5)

        # Series selection
        series_frame = ttk.Frame(config_frame)
        series_frame.pack(side=tk.TOP, fill=tk.X, pady=2)
        ttk.Label(series_frame, text="Target series (TS_n):").pack(side=tk.LEFT)

        series_values = list(getattr(C, "GUI_SERIES_DISPLAY_NAMES", ["TS_1", "TS_2", "TS_3", "TS_4", "TS_5", "TS_6", "TS_7"]))
        ttk.Combobox(
            series_frame,
            textvariable=self.selected_series_var,
            values=series_values,
            state="readonly",
            width=10,
        ).pack(side=tk.LEFT, padx=5)

        # Horizon
        horizon_frame = ttk.Frame(config_frame)
        horizon_frame.pack(side=tk.TOP, fill=tk.X, pady=2)
        ttk.Label(horizon_frame, text="Forecast horizon (steps):").pack(side=tk.LEFT)
        ttk.Spinbox(
            horizon_frame,
            from_=1,
            to=int(getattr(C, "GUI_MAX_FORECAST_HORIZON", 50)),
            textvariable=self.fh_var,
            width=6,
        ).pack(side=tk.LEFT, padx=5)

        # Training window
        tw_frame = ttk.LabelFrame(config_frame, text="Training Window (row-based)", padding=8)
        tw_frame.pack(side=tk.TOP, fill=tk.X, pady=6)

        tw_row1 = ttk.Frame(tw_frame)
        tw_row1.pack(side=tk.TOP, fill=tk.X, pady=2)
        ttk.Checkbutton(
            tw_row1,
            text="Use training window (last N rounds/rows)",
            variable=self.training_window_enabled_var,
            command=self._on_training_window_toggle,
        ).pack(side=tk.LEFT, anchor=tk.W)

        tw_row2 = ttk.Frame(tw_frame)
        tw_row2.pack(side=tk.TOP, fill=tk.X, pady=2)
        ttk.Label(tw_row2, text="Training window (rounds):").pack(side=tk.LEFT)
        self.tw_spin = ttk.Spinbox(
            tw_row2,
            from_=0,
            to=1000000,
            textvariable=self.training_window_rounds_var,
            width=8,
        )
        self.tw_spin.pack(side=tk.LEFT, padx=5)
        ttk.Label(
            tw_row2,
            text="0 means no window (full history). Applies to all selected models in GUI.",
        ).pack(side=tk.LEFT, padx=8)

        self._sync_training_window_widget_state()

        # Models
        model_frame = ttk.Frame(config_frame)
        model_frame.pack(side=tk.TOP, fill=tk.X, pady=5)

        ttk.Checkbutton(
            model_frame,
            text="Use DynaMix zero-shot (ALRNN/LSTM/GRU)",
            variable=self.use_dynamix_var,
            state=tk.NORMAL if HAS_DYNAMIX_CORE else tk.DISABLED,
        ).pack(side=tk.TOP, anchor=tk.W)

        ttk.Checkbutton(
            model_frame,
            text="Use PCE-NARX (Sparse NAR)",
            variable=self.use_pce_var,
            state=tk.NORMAL if bool(getattr(C, "PCE_ENABLED", True)) else tk.DISABLED,
        ).pack(side=tk.TOP, anchor=tk.W)

        ttk.Checkbutton(
            model_frame,
            text=f"Use Darts (Default: {getattr(C, 'DARTS_MODEL_TYPE', 'Configured')})",
            variable=self.use_darts_var,
            state=tk.NORMAL if HAS_DARTS_CORE and bool(getattr(C, "DARTS_ENABLED", True)) else tk.DISABLED,
        ).pack(side=tk.TOP, anchor=tk.W)

        # Buttons
        buttons_frame = ttk.Frame(self.root, padding=10)
        buttons_frame.pack(side=tk.TOP, fill=tk.X)

        self.run_btn = ttk.Button(buttons_frame, text="Run Forecast", command=self.on_run_forecast)
        self.run_btn.pack(side=tk.LEFT)

        ttk.Button(buttons_frame, text="Open Graphs Folder", command=self.on_open_graphs_folder).pack(side=tk.LEFT, padx=5)
        ttk.Button(buttons_frame, text="Exit", command=self.on_close).pack(side=tk.RIGHT)

        # Log box
        log_frame = ttk.LabelFrame(self.root, text="Messages", padding=5)
        log_frame.pack(side=tk.TOP, fill=tk.BOTH, expand=True, padx=10, pady=5)

        self.log_text = tk.Text(log_frame, wrap="word", height=15, bg="white")
        self.log_text.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        scrollbar = ttk.Scrollbar(log_frame, command=self.log_text.yview)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        self.log_text.configure(yscrollcommand=scrollbar.set)

        # Status bar
        status_frame = ttk.Frame(self.root, relief=tk.SUNKEN, padding=(5, 2))
        status_frame.pack(side=tk.BOTTOM, fill=tk.X)

        ttk.Label(status_frame, textvariable=self.status_var, anchor=tk.W).pack(side=tk.LEFT, fill=tk.X, expand=True)
        ttk.Progressbar(
            status_frame,
            variable=self.progress_var,
            mode="determinate",
            length=220,
        ).pack(side=tk.RIGHT, padx=5)

        # Informational warnings
        if not HAS_DYNAMIX_CORE:
            self._log_to_gui("Warning: dynamix_core not found. DynaMix model disabled.\n")
        if not HAS_PLOTTING:
            self._log_to_gui("Warning: plotting not found. Plot export disabled.\n")
        if not HAS_DARTS_CORE:
            self._log_to_gui("Warning: darts_core or libraries missing. Darts disabled.\n")

    def _on_training_window_toggle(self) -> None:
        self._sync_training_window_widget_state()

    def _sync_training_window_widget_state(self) -> None:
        enabled = bool(self.training_window_enabled_var.get())
        state = "normal" if enabled else "disabled"
        try:
            self.tw_spin.configure(state=state)
        except Exception:
            pass

    # ------------------------------------------------------------------
    # Menu actions
    # ------------------------------------------------------------------
    def on_load_data(self) -> None:
        try:
            default_path = Path(getattr(C, "DATA_FILE", REPO_ROOT / "DATA.csv"))
            if default_path.is_file():
                use_default = messagebox.askyesno(
                    "Load DATA.csv",
                    f"Use default data file?\n\n{default_path}",
                    parent=self.root,
                )
            else:
                use_default = False

            if use_default:
                csv_path = default_path
            else:
                file_path = filedialog.askopenfilename(
                    title="Select lottery dataset (CSV)",
                    filetypes=[("CSV Files", "*.csv"), ("All Files", "*.*")],
                    initialdir=str(default_path.parent),
                )
                if not file_path:
                    return
                csv_path = Path(file_path)

            self._set_status("Loading dataset...")
            ts_array, date_index, ts_df = DU.load_lottery_data(csv_path)

            self.ts_array = ts_array
            self.date_index = date_index
            self.ts_df = ts_df

            info = f"Loaded {ts_df.shape[0]} rows, {ts_df.shape[1]} series"
            if isinstance(date_index, pd.DatetimeIndex) and len(date_index) > 0:
                info += f", {date_index[0].date()} → {date_index[-1].date()}"
            self.data_info_var.set(info)
            self._log_to_gui(info + "\n")
            self._set_status("Dataset loaded successfully.")
        except Exception as exc:
            log.exception("Error while loading dataset.")
            messagebox.showerror("Error", f"Failed to load dataset:\n{exc}")
            self._set_status("Failed to load dataset.")

    def on_run_forecast(self) -> None:
        if self._forecast_running:
            messagebox.showinfo("Forecast", "Forecast is already running.")
            return

        if self.ts_df is None:
            messagebox.showwarning("Forecast", "No dataset loaded. Please load DATA.csv first.")
            return

        target_series = str(self.selected_series_var.get())
        if target_series not in self.ts_df.columns:
            messagebox.showerror("Forecast", f"Target series '{target_series}' not found in data.")
            return

        try:
            fh = int(self.fh_var.get())
        except Exception:
            messagebox.showerror("Forecast", "Forecast horizon must be an integer.")
            return

        max_fh = int(getattr(C, "GUI_MAX_FORECAST_HORIZON", 50))
        if fh <= 0 or fh > max_fh:
            messagebox.showerror("Forecast", f"Forecast horizon must be between 1 and {max_fh}.")
            return

        # Training window validation
        tw_enabled = bool(self.training_window_enabled_var.get())
        try:
            tw_rounds = int(self.training_window_rounds_var.get())
        except Exception:
            messagebox.showerror("Forecast", "Training window (rounds) must be an integer.")
            return
        if tw_rounds < 0:
            messagebox.showerror("Forecast", "Training window (rounds) must be >= 0.")
            return

        effective_window = int(tw_rounds) if (tw_enabled and tw_rounds > 0) else 0

        # Update Constants at runtime for consistency
        try:
            C.TRAINING_WINDOW_ROUNDS = int(effective_window)
        except Exception:
            pass

        use_dynamix = bool(self.use_dynamix_var.get() and HAS_DYNAMIX_CORE)
        use_pce = bool(self.use_pce_var.get() and bool(getattr(C, "PCE_ENABLED", True)))
        use_darts = bool(self.use_darts_var.get() and bool(getattr(C, "DARTS_ENABLED", True)) and HAS_DARTS_CORE)

        if not use_dynamix and not use_pce and not use_darts:
            messagebox.showwarning("Forecast", "No model selected. Enable DynaMix, PCE-NARX, or Darts.")
            return

        self._forecast_running = True
        self.run_btn.config(state=tk.DISABLED)
        self._set_status("Running forecast...")
        self.progress_var.set(0.0)

        args: Dict[str, Any] = {
            "target_series": target_series,
            "fh": fh,
            "use_dynamix": use_dynamix,
            "use_pce": use_pce,
            "use_darts": use_darts,
            "training_window_enabled": bool(tw_enabled),
            "training_window_rounds": int(tw_rounds),
            "effective_training_window": int(effective_window),
        }

        self._forecast_thread = threading.Thread(target=self._run_forecast_worker, args=(args,), daemon=True)
        self._forecast_thread.start()

    def on_open_graphs_folder(self) -> None:
        _open_folder(Path(getattr(C, "OUTPUT_GRAPHS_DIR", REPO_ROOT / "Output" / "Graphs")))

    def on_open_logs_folder(self) -> None:
        _open_folder(Path(getattr(C, "OUTPUT_LOGS_DIR", REPO_ROOT / "Output" / "Logs")))

    def on_clear_model_cache(self) -> None:
        try:
            cache_dir = Path(getattr(C, "MODEL_CACHE_DIR", REPO_ROOT / "Output" / "ModelCache"))
            if not cache_dir.exists():
                messagebox.showinfo("Model Cache", "Model cache directory does not exist.")
                return

            confirm = messagebox.askyesno(
                "Clear Model Cache",
                f"Delete all files in model cache?\n\n{cache_dir}",
                icon=messagebox.WARNING,
            )
            if not confirm:
                return

            import shutil

            shutil.rmtree(cache_dir)
            cache_dir.mkdir(parents=True, exist_ok=True)
            self._log_to_gui(f"Model cache cleared: {cache_dir}\n")
            self._set_status("Model cache cleared.")
        except Exception as exc:
            log.exception("Failed to clear model cache.")
            messagebox.showerror("Error", f"Failed to clear model cache:\n{exc}")

    def on_about(self) -> None:
        app_name = str(getattr(C, "APP_NAME", "DynaMix Lottery Forecasting System"))
        msg = (
            f"{app_name}\n\n"
            "A multivariate time-series forecasting application using:\n"
            "- DynaMix zero-shot models (ALRNN / LSTM / GRU)\n"
            "- Sparse PCE-NARX forecaster\n"
            "- Darts Deep Learning (N-BEATS, Transformer, etc.)\n\n"
            "Dataset:\n"
            "  Date, TS_1..TS_7 (dd/mm/yyyy)\n"
            "Output:\n"
            "  HTML + CSV in Output/Graphs (if enabled)\n"
        )
        messagebox.showinfo("About", msg)

    def on_close(self) -> None:
        if self._forecast_running:
            if not messagebox.askyesno("Exit", "A forecast is still running. Do you really want to exit?"):
                return
        self.root.destroy()

    # ------------------------------------------------------------------
    # Background worker
    # ------------------------------------------------------------------
    def _run_forecast_worker(self, args: Dict[str, Any]) -> None:
        target_series: str = str(args["target_series"])
        fh: int = int(args["fh"])
        use_dynamix: bool = bool(args["use_dynamix"])
        use_pce: bool = bool(args["use_pce"])
        use_darts: bool = bool(args["use_darts"])
        tw_enabled: bool = bool(args.get("training_window_enabled", False))
        effective_window: int = int(args.get("effective_training_window", 0))

        ts_df_full = self.ts_df
        if ts_df_full is None:
            self.gui_queue.put(("log", "Internal error: dataset not loaded.\n"))
            self.gui_queue.put(("finished",))
            return

        ts_df = _apply_training_window(ts_df_full, effective_window)
        ts_cols: List[str] = list(getattr(C, "TS_COLUMNS", [])) or list(ts_df_full.columns)

        table_predictions: Dict[str, Dict[str, int]] = {}
        model_first_dates: Dict[str, str] = {}

        total_models = int(use_dynamix) + int(use_pce) + int(use_darts)
        model_index = 0

        # Emit training window info once
        if tw_enabled and effective_window > 0:
            self.gui_queue.put(("log", f"Training window (GUI): ENABLED, last {effective_window} rows.\n"))
        else:
            self.gui_queue.put(("log", "Training window (GUI): DISABLED (full history).\n"))

        if effective_window > 0:
            self.gui_queue.put(("log", f"History length: full={len(ts_df_full)} rows, windowed={len(ts_df)} rows.\n"))

        try:
            # -----------------
            # DynaMix
            # -----------------
            if use_dynamix:
                model_index += 1
                model_label = "DynaMix"
                self.gui_queue.put(("status", f"Running {model_label} forecast ({model_index}/{total_models})..."))
                self.gui_queue.put(("log", f"Starting {model_label} forecast for {target_series}, fh={fh}\n"))

                def progress_cb_dm(step: int, total: int) -> None:
                    self.gui_queue.put(("progress_model", model_label, step, total, model_index, total_models))

                if not HAS_DYNAMIX_CORE or DCore is None:
                    self.gui_queue.put(("log", "dynamix_core not available. Skipping DynaMix forecast.\n"))
                else:
                    try:
                        result = DCore.run_dynamix_forecast(  # type: ignore[attr-defined]
                            ts_df=ts_df,
                            target_col=target_series,
                            forecast_horizon=fh,
                            progress_callback=progress_cb_dm,
                        )
                        if isinstance(result, dict):
                            forecast_df = result.get("forecast_df")
                            if isinstance(forecast_df, pd.DataFrame) and not forecast_df.empty:
                                vals, idx_str = _extract_first_step_values(forecast_df, ts_cols)
                                table_predictions[model_label] = {k: _round_half_up(v) for k, v in vals.items()}
                                if idx_str:
                                    model_first_dates[model_label] = idx_str

                            html_path = result.get("html_path")
                            csv_path = result.get("csv_path")
                            if html_path or csv_path:
                                msg = "DynaMix outputs saved:\n"
                                if html_path:
                                    msg += f"  HTML: {html_path}\n"
                                if csv_path:
                                    msg += f"  CSV : {csv_path}\n"
                                self.gui_queue.put(("log", msg))

                        self.gui_queue.put(("log", "DynaMix forecast completed.\n"))
                    except Exception:
                        err = traceback.format_exc()
                        log.error("Error in DynaMix forecast:\n%s", err)
                        self.gui_queue.put(("log", f"Error during DynaMix forecast:\n{err}\n"))

            # -----------------
            # PCE-NARX
            # -----------------
            if use_pce and bool(getattr(C, "PCE_ENABLED", True)):
                model_index += 1
                model_label = "PCE"
                self.gui_queue.put(("status", f"Running PCE-NARX forecast ({model_index}/{total_models})..."))
                self.gui_queue.put(("log", f"Starting PCE-NARX forecast for {target_series}, fh={fh}\n"))

                def progress_cb_pce(step: int, total: int) -> None:
                    self.gui_queue.put(("progress_model", "PCE-NARX", step, total, model_index, total_models))

                try:
                    forecast_df = PCE.predict_pce_narx(
                        data=ts_df,
                        target_col=target_series,
                        forecast_horizon=fh,
                        progress_callback=progress_cb_pce,
                    )

                    if forecast_df is None or forecast_df.empty:
                        self.gui_queue.put(("log", "PCE-NARX: No forecast produced.\n"))
                    else:
                        pred_val: Optional[float] = None
                        try:
                            if "PCE_Pred" in forecast_df.columns:
                                pred_val = float(forecast_df["PCE_Pred"].iloc[0])
                        except Exception:
                            pred_val = None

                        if pred_val is not None:
                            table_predictions.setdefault(model_label, {})
                            table_predictions[model_label][target_series] = _round_half_up(pred_val)

                        # Optional export (only if plotting module is available)
                        if HAS_PLOTTING and Plotting is not None and bool(getattr(C, "EXPORT_ENABLED", True)):
                            try:
                                html_path, csv_path = Plotting.export_forecast_plot_and_csv(  # type: ignore[attr-defined]
                                    history_df=ts_df,
                                    forecast_df=forecast_df,
                                    target_col=target_series,
                                    model_label="PCE-NARX",
                                )
                                msg = "PCE-NARX outputs saved:\n"
                                msg += f"  HTML: {html_path}\n"
                                msg += f"  CSV : {csv_path}\n"
                                self.gui_queue.put(("log", msg))
                            except Exception:
                                err = traceback.format_exc()
                                log.error("Error exporting PCE-NARX:\n%s", err)
                                self.gui_queue.put(("log", f"Error while exporting PCE-NARX results:\n{err}\n"))

                        try:
                            idx0 = forecast_df.index[0]
                            model_first_dates[model_label] = idx0.isoformat() if hasattr(idx0, "isoformat") else str(idx0)
                        except Exception:
                            pass

                        self.gui_queue.put(("log", "PCE-NARX forecast completed.\n"))
                except Exception:
                    err = traceback.format_exc()
                    log.error("Error in PCE-NARX forecast:\n%s", err)
                    self.gui_queue.put(("log", f"Error during PCE-NARX forecast:\n{err}\n"))

            # -----------------
            # Darts
            # -----------------
            if use_darts and bool(getattr(C, "DARTS_ENABLED", True)):
                model_index += 1
                darts_model_type = str(getattr(C, "DARTS_MODEL_TYPE", "NBEATS"))
                model_label = darts_model_type

                self.gui_queue.put(("status", f"Running Darts-{model_label} forecast ({model_index}/{total_models})..."))
                self.gui_queue.put(("log", f"Starting Darts-{model_label} forecast for {target_series}, fh={fh}\n"))

                if not HAS_DARTS_CORE or DartCore is None:
                    self.gui_queue.put(("log", "darts_core not available or missing libs. Skipping Darts forecast.\n"))
                else:
                    try:
                        result = DartCore.run_darts_forecast(  # type: ignore[attr-defined]
                            ts_df=ts_df,
                            target_col=target_series,
                            forecast_horizon=fh,
                            model_type=darts_model_type,
                        )

                        if isinstance(result, dict):
                            forecast_df = result.get("forecast_df")
                            if isinstance(forecast_df, pd.DataFrame) and not forecast_df.empty:
                                vals, idx_str = _extract_first_step_values(forecast_df, ts_cols)
                                table_predictions[model_label] = {k: _round_half_up(v) for k, v in vals.items()}
                                if idx_str:
                                    model_first_dates[model_label] = idx_str

                            html_path = result.get("html_path")
                            csv_path = result.get("csv_path")
                            if html_path or csv_path:
                                msg = f"Darts-{model_label} outputs saved:\n"
                                if html_path:
                                    msg += f"  HTML: {html_path}\n"
                                if csv_path:
                                    msg += f"  CSV : {csv_path}\n"
                                self.gui_queue.put(("log", msg))

                        self.gui_queue.put(("log", f"Darts-{model_label} forecast completed.\n"))
                    except Exception:
                        err = traceback.format_exc()
                        log.error("Error in Darts forecast:\n%s", err)
                        self.gui_queue.put(("log", f"Error during Darts forecast:\n{err}\n"))

            # -----------------
            # Always print Markdown summary table (GUI + console)
            # -----------------
            if table_predictions:
                headers = ["Model"] + ts_cols
                rows: List[List[Any]] = []

                preferred_order = ["DynaMix", "PCE", "GRU", "LSTM", "TCN", "NBEATS", "Transformer", "TFT"]
                present_models = list(table_predictions.keys())
                ordered_models = [m for m in preferred_order if m in present_models] + [
                    m for m in present_models if m not in preferred_order
                ]

                for model in ordered_models:
                    preds = table_predictions.get(model, {})
                    row_vals: List[Any] = [preds.get(ts, "-") for ts in ts_cols]
                    rows.append([model] + row_vals)

                md = _format_markdown_table(headers, rows)

                meta_lines: List[str] = []
                meta_lines.append("Forecast (first step):")
                meta_lines.append(f"- Target series: {target_series}")
                meta_lines.append(f"- Horizon: {fh} (table shows t+1)")
                if tw_enabled and effective_window > 0:
                    meta_lines.append(f"- Training window: last {effective_window} rounds (rows)")
                else:
                    meta_lines.append("- Training window: disabled (full history)")

                any_date = None
                for m in ordered_models:
                    if m in model_first_dates:
                        any_date = model_first_dates[m]
                        break
                if any_date:
                    meta_lines.append(
                        f"- Forecast {'step/id' if _is_event_mode() else 'date'} (t+1): {any_date}"
                    )

                meta = "\n".join(meta_lines) + "\n\n"
                self.gui_queue.put(("mdtable", meta + md))
            else:
                self.gui_queue.put(("mdtable", "No forecast values were produced by the selected models.\n"))

        finally:
            self.gui_queue.put(("finished",))
            self._forecast_running = False

    # ------------------------------------------------------------------
    # Queue processing and helpers
    # ------------------------------------------------------------------
    def _process_gui_queue(self) -> None:
        try:
            while True:
                item = self.gui_queue.get_nowait()
                if not item:
                    continue

                kind = item[0]

                if kind == "log":
                    self._log_to_gui(str(item[1]))

                elif kind == "mdtable":
                    self._log_to_gui(str(item[1]))
                    try:
                        print(item[1], flush=True)
                    except Exception:
                        pass

                elif kind == "status":
                    self._set_status(str(item[1]))

                elif kind == "progress_model":
                    _kind, model_label, step, total, model_idx, model_count = item
                    step_i = int(step)
                    total_i = int(total)
                    model_idx_i = int(model_idx)
                    model_count_i = int(model_count)

                    if total_i <= 0:
                        fraction = 0.0
                    else:
                        model_frac = step_i / float(total_i)
                        overall_frac = (model_idx_i - 1 + model_frac) / float(max(1, model_count_i))
                        fraction = max(0.0, min(1.0, overall_frac))

                    self.progress_var.set(fraction * 100.0)
                    self.status_var.set(f"{model_label} progress: {step_i}/{total_i} (model {model_idx_i}/{model_count_i})")

                elif kind == "finished":
                    self.run_btn.config(state=tk.NORMAL)
                    if not self._forecast_running:
                        self._set_status("Forecast(s) completed.")
                        self.progress_var.set(100.0)

                self.gui_queue.task_done()

        except queue.Empty:
            pass

        self.root.after(int(getattr(C, "GUI_PROGRESS_UPDATE_INTERVAL_MS", 100)), self._process_gui_queue)

    def _log_to_gui(self, msg: str) -> None:
        if not msg.endswith("\n"):
            msg += "\n"
        self.log_text.insert(tk.END, msg)
        self.log_text.see(tk.END)

    def _set_status(self, text: str) -> None:
        self.status_var.set(text)


# ----------------------------------------------------------------------
# Entry point
# ----------------------------------------------------------------------
def main() -> None:
    root = tk.Tk()
    app = DynaMixLotteryApp(root)
    root.protocol("WM_DELETE_WINDOW", app.on_close)
    root.mainloop()


if __name__ == "__main__":
    main()
