"""Frame assembly: combine the base pattern with any enabled overlays.

The public surface is :func:`render_frame` (one frame, used by the live preview)
and :func:`iter_frames` (a generator over the whole loop, used by the encoder).
"""

from __future__ import annotations

from typing import Iterator

import numpy as np

from . import overlays, pattern
from .config import ProjectConfig


class FrameRenderer:
    """Renders frames for a fixed :class:`ProjectConfig`.

    Caches the static grid overlay so its (relatively expensive) text rasterising
    happens once, not per frame.
    """

    def __init__(self, config: ProjectConfig, font_family: str | None = None):
        self.config = config
        self.font_family = font_family
        self._grid_overlay: np.ndarray | None = None
        if config.grid.enabled:
            self._grid_overlay = overlays.build_grid_overlay(
                config.grid, config.output.width, config.output.height, font_family
            )
        self._image_overlay: overlays.ImageOverlay | None = None
        if config.image.enabled:
            overlay = overlays.ImageOverlay(
                config.image, config.output.width, config.output.height
            )
            self._image_overlay = overlay if overlay.loaded else None

    def render(self, frame_index: int) -> np.ndarray:
        cfg = self.config
        w, h = cfg.output.width, cfg.output.height
        n = cfg.total_frames()

        if cfg.color_loop.enabled:
            frame = pattern.colour_loop_frame(cfg.color_loop, w, h, frame_index, n)
        else:
            frame = pattern.solid_frame(w, h)

        if cfg.h_lines.enabled:
            frame = overlays.apply_lines(frame, cfg.h_lines, frame_index, n, "h")
        if cfg.v_lines.enabled:
            frame = overlays.apply_lines(frame, cfg.v_lines, frame_index, n, "v")

        if self._image_overlay is not None:
            layer = self._image_overlay.layer(frame_index, n)
            if layer is not None:
                frame = overlays.composite_rgba(frame, layer)

        if self._grid_overlay is not None:
            frame = overlays.composite_rgba(frame, self._grid_overlay)
        return frame

    def iter_frames(self) -> Iterator[np.ndarray]:
        for i in range(self.config.total_frames()):
            yield self.render(i)


def render_frame(config: ProjectConfig, frame_index: int,
                 font_family: str | None = None) -> np.ndarray:
    """Convenience one-shot renderer (rebuilds any grid overlay each call)."""
    return FrameRenderer(config, font_family).render(frame_index)


def iter_frames(config: ProjectConfig,
                font_family: str | None = None) -> Iterator[np.ndarray]:
    yield from FrameRenderer(config, font_family).iter_frames()
