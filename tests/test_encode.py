"""A fast end-to-end encode smoke test per format preset."""

from __future__ import annotations

import os

import pytest

from projgen.core import encoder
from projgen.core.config import ProjectConfig


def _small(preset: str, out_dir) -> ProjectConfig:
    cfg = ProjectConfig()
    cfg.output.width, cfg.output.height = 96, 64
    cfg.output.duration, cfg.output.fps = 0.4, 25.0  # ~10 frames
    cfg.output.preset = preset
    cfg.grid.enabled = True
    cfg.grid.rows, cfg.grid.cols = 2, 3
    cfg.h_lines.enabled = True
    cfg.output.output_path = os.path.join(str(out_dir), f"clip_{preset}")
    return cfg


@pytest.mark.parametrize("preset", sorted(encoder.FORMAT_PRESETS))
def test_encode_each_preset(preset, tmp_path):
    cfg = _small(preset, tmp_path)
    written = encoder.encode(cfg)
    assert written.exists()
    if written.is_dir():
        assert any(written.iterdir())
    else:
        assert written.stat().st_size > 0


def test_progress_and_cancel(tmp_path):
    cfg = _small("png_sequence", tmp_path)
    seen = []
    encoder.encode(cfg, progress=lambda d, t: seen.append((d, t)),
                   cancel=lambda: len(seen) >= 3)
    assert len(seen) == 3  # stopped early
