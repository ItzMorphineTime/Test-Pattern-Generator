"""Optional overlays composited on top of the base pattern.

* Tracking / scanning lines — evenly spaced lines that sweep across the frame.
  Motion uses an integer number of sweeps per loop, so it stays seamless.
* Number grid — a static grid of labelled cells, rendered once with Pillow and
  alpha-composited onto every frame.
* Image / logo — a custom picture positioned and scaled on the canvas, with
  optional seamless effects (grow & shrink, fade, spin).
"""

from __future__ import annotations

import math
import os
from functools import lru_cache

import numpy as np
from PIL import Image, ImageDraw, ImageFont

from .config import (
    GridConfig,
    ImageConfig,
    ImageEffect,
    LabelMode,
    LineGroupConfig,
    LineStyle,
)


def _rgb_u8(color) -> np.ndarray:
    return np.array([round(c * 255) for c in color], dtype=np.float32)


def _draw_line(alpha: np.ndarray, coords: np.ndarray, center: float,
               cfg: LineGroupConfig, wrap_length: int | None) -> None:
    """Accumulate one line's coverage into ``alpha`` (in place, taking the max)."""
    dist = np.abs(coords - center)
    if wrap_length is not None:  # continuous scroll wraps around the edges
        dist = np.minimum(dist, wrap_length - dist)
    if cfg.style is LineStyle.SOFT:
        sigma = max(cfg.thickness * 0.6, 1.0)
        line = np.exp(-(dist / sigma) ** 2)
    else:
        half = max(cfg.thickness / 2.0, 0.5)
        # 1px anti-aliased shoulder keeps thin lines from shimmering.
        line = np.clip(half + 0.5 - dist, 0.0, 1.0)
    np.maximum(alpha, line, out=alpha)


def _sweep_count(cfg: LineGroupConfig) -> int:
    """Whole number of there-and-back sweeps (round half up; 0 means static)."""
    if cfg.speed <= 0:
        return 0
    return max(1, int(cfg.speed + 0.5))


def _line_alpha_1d(length: int, cfg: LineGroupConfig, frame_index: int,
                   total_frames: int) -> np.ndarray:
    """Coverage in ``[0, 1]`` along one axis for a group of moving lines.

    Loop toggle **on** (``seamless``): the lines ping-pong and the clip is a
    complete out-and-back — frame 0 and the final frame both sit at the start
    position (a whole number of sweeps over the ``N - 1`` frame span). Lines
    bounce off the edges rather than wrapping.

    Loop toggle **off**: the lines scroll continuously in one direction at the
    exact ``speed`` (wrapping around the edges); the motion does not return.
    """
    coords = np.arange(length, dtype=np.float32)
    count = max(1, cfg.count)
    span = 1.0 / count
    alpha = np.zeros(length, dtype=np.float32)

    if cfg.seamless:
        sweeps = _sweep_count(cfg)
        denom = max(1, total_frames - 1)  # so the final frame returns to start
        phase = (frame_index / denom) * sweeps
        if cfg.direction < 0:
            phase += 0.5  # start from the opposite side
        # Triangle wave 0 -> 1 -> 0 over each sweep (there and back).
        tri = 1.0 - abs(1.0 - 2.0 * (phase % 1.0)) if sweeps else 0.0
        max_index = max(1, length - 1)
        for k in range(count):
            center = (k * span + span * tri) * max_index
            _draw_line(alpha, coords, center, cfg, wrap_length=None)
    else:
        travel = (frame_index * cfg.speed * cfg.direction) / max(1, total_frames)
        for k in range(count):
            center = ((k * span + travel) % 1.0) * length
            _draw_line(alpha, coords, center, cfg, wrap_length=length)

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


# ---------------------------------------------------------------------------
# Image / logo overlay
# ---------------------------------------------------------------------------
@lru_cache(maxsize=8)
def _load_image(path: str, mtime: float) -> Image.Image:
    """Load and cache a source image as RGBA (mtime busts the cache on edits)."""
    del mtime  # cache key only
    with Image.open(path) as img:
        return img.convert("RGBA")


class ImageOverlay:
    """Renders a custom image/logo layer for each frame.

    Effects animate over the ``N - 1`` frame span with whole cycles, so the
    final rendered frame returns to the starting state — the same seamless
    convention the tracking lines use.  A static image (no effect) is rendered
    once and cached.
    """

    def __init__(self, cfg: ImageConfig, width: int, height: int):
        self.cfg = cfg
        self.width = width
        self.height = height
        self._source: Image.Image | None = None
        self._static_layer: np.ndarray | None = None
        if cfg.enabled and cfg.path and os.path.isfile(cfg.path):
            try:
                self._source = _load_image(cfg.path, os.path.getmtime(cfg.path))
            except OSError:
                self._source = None

    @property
    def loaded(self) -> bool:
        return self._source is not None

    # -- per-frame parameters -------------------------------------------
    def _phase(self, frame_index: int, total_frames: int) -> float:
        span = max(1, total_frames - 1)  # final frame returns to the start
        cycles = max(0, int(self.cfg.effect_cycles))
        return (frame_index / span) * cycles

    def _size_factor(self, phase: float) -> float:
        if self.cfg.effect is ImageEffect.PULSE:
            return max(0.05, 1.0 + self.cfg.effect_amount * math.sin(2 * math.pi * phase))
        return 1.0

    def _alpha_factor(self, phase: float) -> float:
        if self.cfg.effect is ImageEffect.FADE:
            dip = 0.5 - 0.5 * math.cos(2 * math.pi * phase)
            return 1.0 - min(1.0, self.cfg.effect_amount) * dip
        return 1.0

    def _angle(self, phase: float) -> float:
        if self.cfg.effect is ImageEffect.SPIN:
            return -360.0 * phase
        return 0.0

    @staticmethod
    def _axis_bounce(t: float, cycles: int, extent: float, start: float) -> float:
        """Triangle-wave position along one axis, bouncing between the edges.

        ``extent`` is the image's size as a fraction of the axis; the centre
        travels within ``[extent/2, 1 - extent/2]``. The phase offset makes the
        motion start from the configured position, and whole ``cycles`` return
        it there on the final frame.
        """
        lo, hi = extent / 2.0, 1.0 - extent / 2.0
        if hi <= lo:  # image fills the axis; nowhere to travel
            return 0.5
        u0 = min(1.0, max(0.0, (start - lo) / (hi - lo)))
        phase = cycles * t + u0 / 2.0
        tri = 1.0 - abs(1.0 - 2.0 * (phase % 1.0))
        return lo + (hi - lo) * tri

    def _bounce_pos(self, t: float) -> tuple[float, float]:
        cfg = self.cfg
        src = self._source
        sw = min(1.0, max(0.0, cfg.scale))
        sh = min(1.0, sw * (src.height / src.width) * (self.width / self.height))
        cycles = max(1, int(cfg.effect_cycles))
        # Different whole cycle counts per axis criss-cross the path diagonally
        # (screensaver style) while both still return to the start.
        return (self._axis_bounce(t, cycles, sw, cfg.pos_x),
                self._axis_bounce(t, cycles + 1, sh, cfg.pos_y))

    # -- rendering -------------------------------------------------------
    def layer(self, frame_index: int, total_frames: int) -> np.ndarray | None:
        """The ``(H, W, 4)`` uint8 layer for this frame, or None if unloaded."""
        if self._source is None:
            return None
        if self.cfg.effect is ImageEffect.NONE:
            if self._static_layer is None:
                self._static_layer = self._render(1.0, 1.0, 0.0)
            return self._static_layer
        if self.cfg.effect is ImageEffect.BOUNCE:
            t = frame_index / max(1, total_frames - 1)
            return self._render(1.0, 1.0, 0.0, pos=self._bounce_pos(t))
        phase = self._phase(frame_index, total_frames)
        return self._render(self._size_factor(phase), self._alpha_factor(phase),
                            self._angle(phase))

    def _render(self, size_factor: float, alpha_factor: float, angle: float,
                pos: tuple[float, float] | None = None) -> np.ndarray:
        cfg = self.cfg
        src = self._source
        pos_x, pos_y = pos if pos is not None else (cfg.pos_x, cfg.pos_y)
        target_w = max(1, round(self.width * cfg.scale * size_factor))
        target_h = max(1, round(target_w * src.height / src.width))
        img = src.resize((target_w, target_h), Image.LANCZOS)
        if angle:
            img = img.rotate(angle, expand=True, resample=Image.BICUBIC)

        canvas = Image.new("RGBA", (self.width, self.height), (0, 0, 0, 0))
        left = round(pos_x * self.width - img.width / 2)
        top = round(pos_y * self.height - img.height / 2)
        canvas.paste(img, (left, top), img)

        layer = np.asarray(canvas).copy()
        opacity = np.clip(cfg.opacity * alpha_factor, 0.0, 1.0)
        if opacity < 1.0:
            layer[..., 3] = (layer[..., 3].astype(np.float32) * opacity).astype(np.uint8)
        return layer
