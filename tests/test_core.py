"""Unit tests for the render core (no GUI, fast)."""

from __future__ import annotations

import colorsys

import numpy as np
import pytest

from projgen.core import encoder, overlays
from projgen.core.color import hsv_to_rgb, to_u8
from projgen.core.config import (
    Axis,
    LabelMode,
    LineStyle,
    ProjectConfig,
)
from projgen.core.render import FrameRenderer


def _tiny(**kw) -> ProjectConfig:
    cfg = ProjectConfig()
    cfg.output.width, cfg.output.height = 64, 48
    cfg.output.duration, cfg.output.fps = 2.0, 25.0
    for k, v in kw.items():
        section, attr = k.split(".")
        setattr(getattr(cfg, section), attr, v)
    return cfg


# --- colour ---------------------------------------------------------------
def test_hsv_matches_colorsys():
    for h in np.linspace(0, 1, 13, endpoint=False):
        for s in (0.0, 0.5, 0.88, 1.0):
            for v in (0.2, 0.9, 1.0):
                ref = np.array(colorsys.hsv_to_rgb(h, s, v))
                got = hsv_to_rgb(np.array([[h, s, v]]))[0]
                assert np.allclose(got, ref, atol=1e-5), (h, s, v, got, ref)


def test_to_u8_rounds_and_clips():
    out = to_u8(np.array([-0.1, 0.0, 0.5, 1.0, 1.5]))
    assert out.tolist() == [0, 0, 128, 255, 255]


# --- seamlessness ---------------------------------------------------------
def test_colour_loop_is_seamless():
    r = FrameRenderer(_tiny())
    n = r.config.total_frames()
    assert np.array_equal(r.render(0), r.render(n))  # wrap frame == first frame


def test_colour_loop_axis_y_varies_down_not_across():
    r = FrameRenderer(_tiny(**{"color_loop.axis": Axis.Y}))
    frame = r.render(3)
    assert np.array_equal(frame[:, 0, :], frame[:, -1, :])  # rows constant across x
    assert not np.array_equal(frame[0, 0, :], frame[-1, 0, :])  # differs down y


def test_integer_speed_lines_are_seamless():
    cfg = _tiny()
    cfg.color_loop.enabled = False
    cfg.h_lines.enabled = True
    cfg.h_lines.count = 2
    cfg.h_lines.speed = 3
    r = FrameRenderer(cfg)
    n = cfg.total_frames()
    assert np.array_equal(r.render(0), r.render(n))


def test_lines_ping_pong_return_to_start():
    cfg = _tiny()
    cfg.color_loop.enabled = False
    cfg.h_lines.enabled = True
    cfg.h_lines.count = 1
    cfg.h_lines.speed = 1
    r = FrameRenderer(cfg)
    n = cfg.total_frames()
    start, middle, end = r.render(0), r.render(n // 2), r.render(n)
    assert np.array_equal(start, end)          # one whole sweep returns to start
    assert not np.array_equal(start, middle)   # and actually moves away in between


def test_seamless_rounds_fractional_speed_and_still_loops():
    cfg = _tiny()
    cfg.color_loop.enabled = False
    cfg.h_lines.enabled = True
    cfg.h_lines.count = 1
    cfg.h_lines.speed = 2.4  # rounds to 2 whole sweeps
    cfg.h_lines.seamless = True
    r = FrameRenderer(cfg)
    assert np.array_equal(r.render(0), r.render(cfg.total_frames()))


def test_free_mode_uses_raw_speed_and_need_not_loop():
    cfg = _tiny()
    cfg.color_loop.enabled = False
    cfg.h_lines.enabled = True
    cfg.h_lines.count = 1
    cfg.h_lines.speed = 2.4
    cfg.h_lines.seamless = False
    r = FrameRenderer(cfg)
    assert not np.array_equal(r.render(0), r.render(cfg.total_frames()))


def test_soft_and_solid_lines_render_without_error():
    for style in (LineStyle.SOLID, LineStyle.SOFT):
        cfg = _tiny()
        cfg.v_lines.enabled = True
        cfg.v_lines.style = style
        FrameRenderer(cfg).render(1)


# --- grid -----------------------------------------------------------------
def test_grid_overlay_shape_and_alpha():
    cfg = _tiny()
    cfg.grid.enabled = True
    cfg.grid.rows, cfg.grid.cols = 3, 4
    overlay = overlays.build_grid_overlay(cfg.grid, cfg.output.width, cfg.output.height)
    assert overlay.shape == (cfg.output.height, cfg.output.width, 4)
    assert overlay[..., 3].max() > 0  # something was drawn


@pytest.mark.parametrize(
    "mode,row,col,expected",
    [
        (LabelMode.SEQUENTIAL, 0, 0, "0"),
        (LabelMode.SEQUENTIAL, 1, 2, "6"),  # row*cols+col with cols=4
        (LabelMode.ROW_COL, 0, 0, "R1C1"),
        (LabelMode.ALPHA_NUM, 0, 0, "A1"),
        (LabelMode.ALPHA_NUM, 2, 26, "AA3"),
    ],
)
def test_cell_labels(mode, row, col, expected):
    assert overlays.cell_label(mode, row, col, 4, 10.0, 10.0) == expected


# --- config ---------------------------------------------------------------
def test_config_json_roundtrip_preserves_enums_and_tuples():
    cfg = _tiny()
    cfg.grid.enabled = True
    cfg.grid.label_mode = LabelMode.ROW_COL
    cfg.h_lines.color = (0.1, 0.2, 0.3)
    cfg.color_loop.axis = Axis.Y
    restored = ProjectConfig.from_json(cfg.to_json())
    assert restored.grid.label_mode is LabelMode.ROW_COL
    assert restored.color_loop.axis is Axis.Y
    assert restored.h_lines.color == (0.1, 0.2, 0.3)
    assert restored.total_frames() == cfg.total_frames()


def test_config_ignores_unknown_keys():
    data = ProjectConfig().to_dict()
    data["output"]["some_future_field"] = 123
    restored = ProjectConfig.from_dict(data)  # must not raise
    assert restored.output.width == 1920


# --- validation -----------------------------------------------------------
def test_odd_dimensions_rejected_for_yuv420():
    cfg = _tiny(**{"output.width": 65, "output.preset": "h264_mp4"})
    problems = encoder.validate(cfg)
    assert any("even" in p for p in problems)


def test_fractional_fps_snaps_to_ntsc():
    assert encoder.fps_fraction(23.976).denominator == 1001
    assert encoder.fps_fraction(25).denominator == 1
