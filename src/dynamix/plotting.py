# ------------------------
# src/dynamix/plotting.py
# ------------------------
"""
Plotting and export utilities for the DynaMix Lottery Forecasting System.

Responsibilities (per README, SRS, and architectural analysis):

- Generate interactive Plotly HTML plots combining:
    * Historical values for a selected TS_n.
    * Model forecasts (DynaMix or PCE-NARX) for the same TS_n.
    * Optional prediction intervals if provided (PCE_Lower / PCE_Upper).
- Export forecast-related data to CSV under Output\\Graphs.
- Use centralized configuration from constants.py.

Public API
----------
export_forecast_plot_and_csv(
    history_df: pd.DataFrame,
    forecast_df: pd.DataFrame,
    target_col: str,
    model_label: str,
) -> Tuple[pathlib.Path, pathlib.Path]

The GUI and dynamix_core / pce_narx call this function to create both
the HTML plot and the CSV file for the selected target series.
"""

from __future__ import annotations

import logging
from datetime import datetime
from pathlib import Path
from typing import Tuple

import numpy as np
import pandas as pd
import plotly.graph_objects as go

# ----------------------------------------------------------------------
# Robust imports after refactor to src/dynamix package
# ----------------------------------------------------------------------
try:
    from . import constants as C  # type: ignore
    from . import data_utils as DU  # type: ignore
except Exception:  # pragma: no cover
    import constants as C  # type: ignore
    import data_utils as DU  # type: ignore

log = logging.getLogger(__name__)


# ----------------------------------------------------------------------
# Mode helpers
# ----------------------------------------------------------------------
def _is_event_mode() -> bool:
    try:
        return str(getattr(C, "INDEX_MODE", "calendar")).lower().strip() == "event"
    except Exception:
        return False


# ----------------------------------------------------------------------
# Helpers
# ----------------------------------------------------------------------
def _ensure_output_dirs() -> None:
    """
    Ensure that Output/Graphs and related directories exist.
    """
    # Canonical dir creation lives in data_utils
    try:
        DU.ensure_output_dirs()
    except Exception:
        log.exception("Failed to ensure base output directories via data_utils.ensure_output_dirs().")

    # Ensure Graphs in case caller bypassed ensure_output_dirs or Constants changed
    try:
        Path(getattr(C, "OUTPUT_GRAPHS_DIR")).mkdir(parents=True, exist_ok=True)
    except Exception:
        log.exception("Failed to ensure OUTPUT_GRAPHS_DIR exists.")


def _normalize_indices_for_mode(
    history: pd.DataFrame,
    forecast: pd.DataFrame,
) -> Tuple[pd.DataFrame, pd.DataFrame]:
    """
    Normalize indices for plotting and CSV export based on INDEX_MODE.

    Calendar mode:
      - enforce DatetimeIndex for both history and forecast

    Event mode:
      - preserve indices as-is (EventID/RangeIndex/ForecastStep)
      - do NOT coerce to datetime
    """
    history2 = history.copy()
    forecast2 = forecast.copy()

    if not _is_event_mode():
        # Calendar mode: enforce datetime identity
        if not isinstance(history2.index, pd.DatetimeIndex):
            history2.index = pd.to_datetime(history2.index, errors="coerce")
        if not isinstance(forecast2.index, pd.DatetimeIndex):
            forecast2.index = pd.to_datetime(forecast2.index, errors="coerce")

        history2 = history2.dropna(axis=0, how="all")
        forecast2 = forecast2.dropna(axis=0, how="all")

        history2.sort_index(inplace=True)
        forecast2.sort_index(inplace=True)
        return history2, forecast2

    # Event mode: preserve ordering and index type; ensure stable ordering only
    try:
        preserve = bool(getattr(C, "EVENT_PRESERVE_FILE_ORDER", True))
    except Exception:
        preserve = True

    if not preserve:
        # If not preserving, sorting by index is the safest generic behavior
        try:
            history2 = history2.sort_index()
        except Exception:
            pass
        try:
            forecast2 = forecast2.sort_index()
        except Exception:
            pass

    history2 = history2.dropna(axis=0, how="all")
    forecast2 = forecast2.dropna(axis=0, how="all")
    return history2, forecast2


def _to_event_x_values(idx: pd.Index) -> np.ndarray:
    """
    Convert an index to numeric x-values suitable for Plotly in event mode.

    Preference:
      1) numeric-like index values
      2) fallback to 0..N-1 position
    """
    try:
        if isinstance(idx, pd.RangeIndex):
            return idx.to_numpy()

        s = pd.Series(idx.to_list(), dtype="object")
        vals = pd.to_numeric(s, errors="coerce")
        arr = vals.to_numpy(dtype=float, copy=False)
        if np.isfinite(arr).all():
            return arr
    except Exception:
        pass

    return np.arange(len(idx), dtype=float)


def _infer_forecast_value_series(
    forecast_df: pd.DataFrame,
    target_col: str,
) -> Tuple[pd.Series, str]:
    """
    Determine which column in forecast_df represents the main forecast
    series to plot for the target.

    For DynaMix forecasts:
        - forecast_df is multivariate with columns TS_1..TS_7.
        - We use forecast_df[target_col].

    For PCE-NARX forecasts:
        - forecast_df usually has columns ["PCE_Pred", "PCE_Lower", "PCE_Upper"].
        - We use forecast_df["PCE_Pred"].

    Returns
    -------
    (series, label_suffix)
    """
    if target_col in forecast_df.columns:
        return forecast_df[target_col], ""

    if "PCE_Pred" in forecast_df.columns:
        return forecast_df["PCE_Pred"], " (PCE_Pred)"

    numeric_cols = forecast_df.select_dtypes(include=[np.number]).columns
    if len(numeric_cols) == 0:
        raise ValueError("No numeric forecast column found for plotting.")
    col = str(numeric_cols[0])
    log.warning(
        "Target column '%s' and 'PCE_Pred' not found in forecast_df. Using column '%s' as fallback.",
        target_col,
        col,
    )
    return forecast_df[col], f" ({col})"


def _build_combined_csv(
    history_df: pd.DataFrame,
    forecast_df: pd.DataFrame,
) -> pd.DataFrame:
    """
    Build a combined CSV-friendly DataFrame that includes both historical
    and forecast data, with a 'Segment' column marking origin.

    Calendar mode:
      - union by datetime index, with *_hist and *_fcast suffixes.

    Event mode:
      - concatenate history then forecast with explicit Event axis column.
    """
    if not _is_event_mode():
        history = history_df.copy()
        forecast = forecast_df.copy()

        if not isinstance(history.index, pd.DatetimeIndex):
            history.index = pd.to_datetime(history.index, errors="coerce")
        if not isinstance(forecast.index, pd.DatetimeIndex):
            forecast.index = pd.to_datetime(forecast.index, errors="coerce")

        all_index = history.index.union(forecast.index).sort_values()

        history = history.reindex(all_index)
        forecast = forecast.reindex(all_index)

        combined = pd.concat({"history": history, "forecast": forecast}, axis=1)

        new_cols = []
        for top, bottom in combined.columns:
            suffix = "_hist" if top == "history" else ("_fcast" if top == "forecast" else "")
            name = f"{bottom}{suffix}" if bottom is not None else f"{top}{suffix}"
            new_cols.append(name)
        combined.columns = new_cols

        in_hist = history.notna().any(axis=1)
        in_fore = forecast.notna().any(axis=1)

        segment = pd.Series(index=all_index, dtype="object")
        segment.loc[in_hist & ~in_fore] = "History"
        segment.loc[~in_hist & in_fore] = "Forecast"
        segment.loc[in_hist & in_fore] = "History+Forecast"

        combined.insert(0, "Segment", segment)
        return combined

    # Event mode
    event_index_name = str(getattr(C, "EVENT_INDEX_NAME", getattr(C, "EVENT_ID_COL", "EventID")) or "EventID")

    hist = history_df.copy()
    fcast = forecast_df.copy()

    hist_event = pd.Series(hist.index.to_list(), name=event_index_name, dtype="object")
    fcast_event = pd.Series(fcast.index.to_list(), name=event_index_name, dtype="object")

    hist_reset = hist.reset_index(drop=True)
    hist_reset.insert(0, event_index_name, hist_event.to_list())
    hist_reset.insert(0, "Segment", ["History"] * len(hist_reset))

    fcast_reset = fcast.reset_index(drop=True)
    fcast_reset.insert(0, event_index_name, fcast_event.to_list())
    fcast_reset.insert(0, "Segment", ["Forecast"] * len(fcast_reset))

    combined = pd.concat([hist_reset, fcast_reset], axis=0, ignore_index=True)

    # Best-effort ordering: if numeric-like, sort by EventID then Segment
    try:
        ev_num = pd.to_numeric(combined[event_index_name], errors="coerce")
        if ev_num.notna().all():
            combined["_ev_sort"] = ev_num.astype(float)
            combined = combined.sort_values(by=["_ev_sort", "Segment"], kind="stable")
            combined = combined.drop(columns=["_ev_sort"])
    except Exception:
        pass

    return combined


# ----------------------------------------------------------------------
# Public API
# ----------------------------------------------------------------------
def export_forecast_plot_and_csv(
    history_df: pd.DataFrame,
    forecast_df: pd.DataFrame,
    target_col: str,
    model_label: str,
) -> Tuple[Path, Path]:
    """
    Creates an interactive Plotly HTML plot and a CSV file for the selected target series.
    """
    _ensure_output_dirs()

    if history_df is None or history_df.empty:
        raise ValueError("export_forecast_plot_and_csv: history_df is empty.")
    if forecast_df is None or forecast_df.empty:
        raise ValueError("export_forecast_plot_and_csv: forecast_df is empty.")
    if target_col not in history_df.columns:
        raise ValueError(f"export_forecast_plot_and_csv: target_col '{target_col}' not found in history_df.")

    history, forecast = _normalize_indices_for_mode(history_df, forecast_df)
    forecast_target_series, label_suffix = _infer_forecast_value_series(forecast, target_col)

    fig = go.Figure()

    if _is_event_mode():
        x_hist = _to_event_x_values(history.index)
        x_fcast = _to_event_x_values(forecast.index)

        fig.add_trace(
            go.Scatter(
                x=x_hist,
                y=history[target_col],
                mode="lines",
                name=f"{target_col} (history)",
            )
        )
        fig.add_trace(
            go.Scatter(
                x=x_fcast,
                y=forecast_target_series,
                mode="lines+markers",
                name=f"{target_col}{label_suffix} [{model_label}]",
            )
        )
    else:
        fig.add_trace(
            go.Scatter(
                x=history.index,
                y=history[target_col],
                mode="lines",
                name=f"{target_col} (history)",
            )
        )
        fig.add_trace(
            go.Scatter(
                x=forecast.index,
                y=forecast_target_series,
                mode="lines+markers",
                name=f"{target_col}{label_suffix} [{model_label}]",
            )
        )

    # Optional prediction interval band (PCE-NARX)
    if "PCE_Lower" in forecast.columns and "PCE_Upper" in forecast.columns:
        x_pi = _to_event_x_values(forecast.index) if _is_event_mode() else forecast.index

        fig.add_trace(
            go.Scatter(
                x=x_pi,
                y=forecast["PCE_Upper"],
                mode="lines",
                line=dict(width=0),
                name="Upper bound",
                showlegend=False,
            )
        )
        fig.add_trace(
            go.Scatter(
                x=x_pi,
                y=forecast["PCE_Lower"],
                mode="lines",
                line=dict(width=0),
                fill="tonexty",
                name="Prediction interval",
                opacity=0.2,
                showlegend=True,
            )
        )

    fig.update_layout(
        title=f"{model_label} forecast for {target_col}",
        xaxis_title=("Event" if _is_event_mode() else "Date"),
        yaxis_title="Value",
        template=str(getattr(C, "PLOTLY_TEMPLATE", "plotly_white")),
        showlegend=bool(getattr(C, "PLOTLY_SHOW_LEGEND", True)),
        width=int(getattr(C, "PLOTLY_WIDTH", 1200)),
        height=int(getattr(C, "PLOTLY_HEIGHT", 600)),
    )

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    safe_series_name = str(target_col).replace(" ", "_").replace("/", "_")

    html_name = str(
        getattr(C, "HTML_FILENAME_PATTERN", "{series}_dynamix_forecast_{timestamp}.html")
    ).format(series=safe_series_name, timestamp=timestamp)

    csv_name = str(
        getattr(C, "CSV_FILENAME_PATTERN", "{series}_forecast_{timestamp}.csv")
    ).format(series=safe_series_name, timestamp=timestamp)

    output_graphs_dir = Path(getattr(C, "OUTPUT_GRAPHS_DIR"))
    html_path = output_graphs_dir / html_name
    csv_path = output_graphs_dir / csv_name

    # Save HTML
    fig.write_html(str(html_path), include_plotlyjs="cdn", full_html=True)
    log.info("Forecast HTML saved to: %s", html_path)

    # Save CSV
    combined_df = _build_combined_csv(history, forecast)
    if not _is_event_mode():
        combined_df = combined_df.reset_index().rename(columns={"index": str(getattr(C, "DATE_COL", "Date"))})

    combined_df.to_csv(
        csv_path,
        sep=str(getattr(C, "CSV_SEPARATOR", ",")),
        decimal=str(getattr(C, "CSV_DECIMAL", ".")),
        encoding=str(getattr(C, "CSV_ENCODING", "utf-8-sig")),
        index=False,
    )
    log.info("Forecast CSV saved to: %s", csv_path)

    return html_path, csv_path
