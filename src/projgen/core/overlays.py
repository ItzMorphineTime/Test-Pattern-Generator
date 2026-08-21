"""Optional overlays composited on top of the base pattern.

* Tracking / scanning lines — evenly spaced lines that sweep across the frame.
  Motion uses an integer number of sweeps per loop, so it stays seamless.
* Number grid — a static grid of labelled cells, rendered once with Pillow and
  alpha-composited onto every frame.
"""

from __future__ import annotations

from functools import lru_cache

import numpy as np
from PIL import Image, ImageDraw, ImageFont

from .config import GridConfig, LabelMode, LineGroupConfig, LineStyle


def _rgb_u8(color) -> np.ndarray:
    return np.array([round(c * 255) for c in color], dtype=np.float32)


def _line_alpha_1d(length: int, cfg: LineGroupConfig, frame_index: int,
                   total_frames: int) -> np.ndarray:
    """Coverage in ``[0, 1]`` along one axis for a group of moving lines.

    The lines ping-pong: one "sweep" moves them across and back to the start, so
    a whole number of sweeps returns exactly to the starting position (seamless).
    Lines bounce off the edges rather than wrapping around them.
    """
    coords = np.arange(length, dtype=np.float32)
    # A whole number of sweeps per loop guarantees the there-and-back motion
    # returns to its start on the wrap frame; free mode uses the raw speed.
    sweeps = round(cfg.speed) if cfg.seamless else cfg.speed
    t = frame_index / max(1, total_frames)
    phase = sweeps * t
    if cfg.direction < 0:
        phase += 0.5  # start from the opposite side
    # Triangle wave in [0, 1]: 0 -> 1 -> 0 over each sweep (there and back).
    tri = 1.0 - abs(1.0 - 2.0 * (phase % 1.0))

    count = max(1, cfg.count)
    span = 1.0 / count
    max_index = max(1, length - 1)
    alpha = np.zeros(length, dtype=np.float32)
    for k in range(count):
        center = (k * span + span * tri) * max_index
        dist = np.abs(coords - center)  # non-wrapping: bounce at the edges
        if cfg.style is LineStyle.SOFT:
            sigma = max(cfg.thickness * 0.6, 1.0)
            line = np.exp(-(dist / sigma) ** 2)
        else:
            half = max(cfg.thickness / 2.0, 0.5)
            # 1px anti-aliased shoulder keeps thin lines from shimmering.
            line = np.clip(half + 0.5 - dist, 0.0, 1.0)
        alpha = np.maximum(alpha, line)

    return np.clip(alpha * cfg.opacity, 0.0, 1.0)


def apply_lines(frame: np.ndarray, cfg: LineGroupConfig, frame_index: int,
                total_frames: int, orientation: str) -> np.ndarray:
    """Composite a horizontal (``'h'``) or vertical (``'v'``) line group.

    ``orientation='h'`` draws full-width lines that move vertically; ``'v'`` draws
    full-height lines that move horizontally.  Returns a new ``uint8`` frame.
    """
    if not cfg.enabled or cfg.count < 1 or cfg.opacity <= 0.0:
        return frame

    height, width = frame.shape[:2]
    color = _rgb_u8(cfg.color)
    out = frame.astype(np.float32)

    if orientation == "h":
        alpha = _line_alpha_1d(height, cfg, frame_index, total_frames)[:, None, None]
    else:
        alpha = _line_alpha_1d(width, cfg, frame_index, total_frames)[None, :, None]

    out += (color[None, None, :] - out) * alpha
    return np.clip(out, 0, 255).astype(np.uint8)


# ---------------------------------------------------------------------------
# Number grid
# ---------------------------------------------------------------------------
@lru_cache(maxsize=8)
def _load_font(size: int, family: str | None) -> ImageFont.ImageFont:
    size = max(6, int(size))
    if family:
        try:
            return ImageFont.truetype(family, size)
        except OSError:
            pass
    try:
        return ImageFont.load_default(size=size)  # Pillow >= 10.1: scalable
    except TypeError:  # very old Pillow
        return ImageFont.load_default()


def _column_letters(index: int) -> str:
    """0 -> A, 25 -> Z, 26 -> AA (spreadsheet-style)."""
    result = ""
    n = index + 1
    while n > 0:
        n, rem = divmod(n - 1, 26)
        result = chr(65 + rem) + result
    return result


def cell_label(mode: LabelMode, row: int, col: int, cols: int,
               cell_w: float, cell_h: float) -> str:
    if mode is LabelMode.SEQUENTIAL:
        return str(row * cols + col)
    if mode is LabelMode.ROW_COL:
        return f"R{row + 1}C{col + 1}"
    if mode is LabelMode.COORDS:
        return f"{int(col * cell_w)},{int(row * cell_h)}"
    return f"{_column_letters(col)}{row + 1}"  # ALPHA_NUM


def build_grid_overlay(cfg: GridConfig, width: int, height: int,
                       font_family: str | None = None) -> np.ndarray:
    """Render the (static) grid + labels to an ``(H, W, 4)`` uint8 RGBA array."""
    img = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)

    rows, cols = max(1, cfg.rows), max(1, cfg.cols)
    cell_w = width / cols
    cell_h = height / rows

    if cfg.show_lines and cfg.line_opacity > 0.0:
        lc = tuple(int(round(c * 255)) for c in cfg.line_color)
        line_rgba = (*lc, int(round(cfg.line_opacity * 255)))
        w = max(1, cfg.line_thickness)
        for c in range(cols + 1):
            x = round(c * cell_w)
            draw.line([(x, 0), (x, height)], fill=line_rgba, width=w)
        for r in range(rows + 1):
            y = round(r * cell_h)
            draw.line([(0, y), (width, y)], fill=line_rgba, width=w)

    if cfg.show_labels and cfg.label_opacity > 0.0:
        size = cfg.font_size or max(8, int(min(cell_w, cell_h) * 0.3))
        font = _load_font(size, font_family)
        fc = tuple(int(round(c * 255)) for c in cfg.font_color)
        font_rgba = (*fc, int(round(cfg.label_opacity * 255)))
        for r in range(rows):
            for c in range(cols):
                text = cell_label(cfg.label_mode, r, c, cols, cell_w, cell_h)
                cx = (c + 0.5) * cell_w
                cy = (r + 0.5) * cell_h
                if cfg.cell_background:
                    bbox = draw.textbbox((cx, cy), text, font=font, anchor="mm")
                    pad = max(2, size // 6)
                    draw.rectangle(
                        [bbox[0] - pad, bbox[1] - pad, bbox[2] + pad, bbox[3] + pad],
                        fill=(0, 0, 0, 150),
                    )
                draw.text((cx, cy), text, font=font, fill=font_rgba, anchor="mm")

    return np.asarray(img)


def composite_rgba(frame: np.ndarray, overlay_rgba: np.ndarray) -> np.ndarray:
    """Alpha-composite an ``(H, W, 4)`` overlay over an ``(H, W, 3)`` uint8 frame."""
    alpha = overlay_rgba[..., 3:4].astype(np.float32) / 255.0
    rgb = overlay_rgba[..., :3].astype(np.float32)
    out = frame.astype(np.float32) * (1.0 - alpha) + rgb * alpha
    return np.clip(out, 0, 255).astype(np.uint8)
