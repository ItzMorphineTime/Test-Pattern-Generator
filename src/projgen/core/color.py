"""Vectorised colour helpers (no per-pixel Python loops)."""

from __future__ import annotations

import numpy as np


def hsv_to_rgb(hsv: np.ndarray) -> np.ndarray:
    """Convert an HSV array to RGB, float in ``[0, 1]``.

    ``hsv`` has shape ``(..., 3)``.  Hue wraps modulo 1.  This mirrors the
    standard colorsys algorithm but runs on the whole array at once.
    """
    hsv = np.asarray(hsv, dtype=np.float32)
    h = np.mod(hsv[..., 0], 1.0) * 6.0
    s = np.clip(hsv[..., 1], 0.0, 1.0)
    v = np.clip(hsv[..., 2], 0.0, 1.0)

    i = np.floor(h).astype(np.int64)
    f = h - i
    p = v * (1.0 - s)
    q = v * (1.0 - s * f)
    t = v * (1.0 - s * (1.0 - f))
    i = i % 6

    r = np.select([i == 0, i == 1, i == 2, i == 3, i == 4, i == 5],
                  [v, q, p, p, t, v])
    g = np.select([i == 0, i == 1, i == 2, i == 3, i == 4, i == 5],
                  [t, v, v, q, p, p])
    b = np.select([i == 0, i == 1, i == 2, i == 3, i == 4, i == 5],
                  [p, p, t, v, v, q])
    return np.stack([r, g, b], axis=-1).astype(np.float32)


def to_u8(rgb_float: np.ndarray) -> np.ndarray:
    """Convert float RGB in ``[0, 1]`` to ``uint8`` with rounding."""
    return np.clip(np.rint(np.asarray(rgb_float) * 255.0), 0, 255).astype(np.uint8)
