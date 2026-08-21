"""Base pattern frame generators.

A generator maps ``(config, frame_index, total_frames)`` to an ``(H, W, 3)``
``uint8`` array.  Functions here are pure and deterministic, which makes them
trivial to unit-test and to reason about for seamlessness.
"""

from __future__ import annotations

import numpy as np

from .color import hsv_to_rgb, to_u8
from .config import Axis, ColorLoopConfig
from .loop import phase


def colour_loop_frame(
    cfg: ColorLoopConfig,
    width: int,
    height: int,
    frame_index: int,
    total_frames: int,
) -> np.ndarray:
    """Scrolling HSV hue gradient — the seamless colour loop.

    Reproduces the original Blender add-on: hue advances along the chosen axis and
    scrolls by the loop phase so the last frame joins cleanly back to the first.
    """
    p = phase(frame_index, total_frames)

    if cfg.axis is Axis.X:
        coord = np.linspace(0.0, 1.0, width, endpoint=False, dtype=np.float32)
    else:
        coord = np.linspace(0.0, 1.0, height, endpoint=False, dtype=np.float32)

    hue = np.mod(coord * cfg.hue_cycles * cfg.direction + p, 1.0)
    line_hsv = np.empty((hue.shape[0], 3), dtype=np.float32)
    line_hsv[:, 0] = hue
    line_hsv[:, 1] = cfg.saturation
    line_hsv[:, 2] = cfg.value
    line_rgb = to_u8(hsv_to_rgb(line_hsv))  # (len, 3)

    if cfg.axis is Axis.X:
        frame = np.broadcast_to(line_rgb[np.newaxis, :, :], (height, width, 3))
    else:
        frame = np.broadcast_to(line_rgb[:, np.newaxis, :], (height, width, 3))
    return np.ascontiguousarray(frame)


def solid_frame(width: int, height: int, color=(0, 0, 0)) -> np.ndarray:
    """A flat colour frame (used when the colour loop is disabled)."""
    frame = np.empty((height, width, 3), dtype=np.uint8)
    frame[:, :] = np.asarray(color, dtype=np.uint8)
    return frame
