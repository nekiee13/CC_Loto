# ------------------------
# src/dynamix/device.py
# ------------------------
"""
Compute/execution-device helpers shared by the model adapters and the GUI.

Kept import-light: presence of ``torch`` is checked with ``importlib`` (no import), and ``torch``
is only imported when a real CUDA check is required. ``resolve_darts_accelerator`` is pure so the
"only use GPU if one is actually available" guard is testable without torch/darts installed.
"""
from __future__ import annotations

import importlib.util


def _torch_installed() -> bool:
    try:
        return importlib.util.find_spec("torch") is not None
    except Exception:
        return False


def gpu_available() -> bool:
    """True only if torch is importable AND a CUDA device is present."""
    if not _torch_installed():
        return False
    try:
        import torch  # noqa: PLC0415

        return bool(torch.cuda.is_available())
    except Exception:
        return False


def resolve_darts_accelerator(force_gpu: bool, gpu_is_available: bool) -> str:
    """Return ``"gpu"`` only when GPU is *requested* and *available*; otherwise ``"cpu"``.

    Pure (availability is passed in), so it is unit-testable without torch/darts. This is the guard
    that stops ``DARTS_FORCE_GPU=True`` from crashing on a machine with no GPU.
    """
    return "gpu" if (bool(force_gpu) and bool(gpu_is_available)) else "cpu"


def describe_device() -> str:
    """Human-friendly label for the active compute device (for the GUI status panel)."""
    if not _torch_installed():
        return "CPU (models not installed)"
    return "GPU (CUDA)" if gpu_available() else "CPU"
