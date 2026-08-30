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


def test_lines_final_frame_returns_to_start():
    # With the loop toggle on, the last rendered frame matches the first.
    cfg = _tiny()
    cfg.color_loop.enabled = False
    cfg.h_lines.enabled = True
    cfg.h_lines.count = 2
    cfg.h_lines.speed = 3
    r = FrameRenderer(cfg)
    n = cfg.total_frames()
    assert np.array_equal(r.render(0), r.render(n - 1))


def test_lines_ping_pong_returns_to_start_and_moves_between():
    cfg = _tiny()
    cfg.color_loop.enabled = False
    cfg.h_lines.enabled = True
    cfg.h_lines.count = 1
    cfg.h_lines.speed = 1
    r = FrameRenderer(cfg)
    n = cfg.total_frames()
    start, middle, end = r.render(0), r.render(n // 2), r.render(n - 1)
    assert np.array_equal(start, end)          # complete out-and-back
    assert not np.array_equal(start, middle)   # actually moves away in between


def test_seamless_rounds_fractional_speed_and_still_returns():
    cfg = _tiny()
    cfg.color_loop.enabled = False
    cfg.h_lines.enabled = True
    cfg.h_lines.count = 1
    cfg.h_lines.speed = 2.4  # rounds to 2 whole sweeps
    cfg.h_lines.seamless = True
    r = FrameRenderer(cfg)
    assert np.array_equal(r.render(0), r.render(cfg.total_frames() - 1))


def test_free_mode_scrolls_and_does_not_ping_pong():
    cfg = _tiny()
    cfg.color_loop.enabled = False
    cfg.h_lines.enabled = True
    cfg.h_lines.count = 1
    cfg.h_lines.speed = 2.4
    cfg.h_lines.seamless = False
    r = FrameRenderer(cfg)
    n = cfg.total_frames()
    # continuous scroll: the last frame does not return to the start
    assert not np.array_equal(r.render(0), r.render(n - 1))
    # and the midpoint is not a mirror of a ping-pong (monotonic scroll)
    assert not np.array_equal(r.render(1), r.render(n - 1))


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


# --- image / logo overlay -------------------------------------------------
def _logo(tmp_path):
    from PIL import Image

    path = tmp_path / "logo.png"
    img = Image.new("RGBA", (24, 16), (255, 0, 0, 255))
    img.save(path)
    return str(path)


def _image_cfg(tmp_path, **kw):
    from projgen.core.config import ImageEffect  # noqa: F401 (re-export guard)

    cfg = _tiny()
    cfg.color_loop.enabled = False
    cfg.image.enabled = True
    cfg.image.path = _logo(tmp_path)
    for k, v in kw.items():
        setattr(cfg.image, k, v)
    return cfg


def test_static_image_is_composited(tmp_path):
    cfg = _image_cfg(tmp_path)
    frame = FrameRenderer(cfg).render(0)
    assert (frame[..., 0] > 200).any()  # red logo pixels present
    assert np.array_equal(frame, FrameRenderer(cfg).render(5))  # static


def test_image_effects_return_to_start_and_animate(tmp_path):
    from projgen.core.config import ImageEffect

    for effect in (ImageEffect.PULSE, ImageEffect.FADE, ImageEffect.SPIN,
                   ImageEffect.BOUNCE):
        cfg = _image_cfg(tmp_path, effect=effect, effect_cycles=1,
                         effect_amount=0.5)
        r = FrameRenderer(cfg)
        n = cfg.total_frames()
        start, middle, end = r.render(0), r.render(n // 2), r.render(n - 1)
        assert np.array_equal(start, end), effect       # final frame == first
        assert not np.array_equal(start, middle), effect  # visibly animates


def test_bounce_starts_at_configured_position(tmp_path):
    from projgen.core.config import ImageEffect

    cfg = _image_cfg(tmp_path, pos_x=0.3, pos_y=0.6, scale=0.2)
    static = FrameRenderer(cfg).render(0)
    cfg.image.effect = ImageEffect.BOUNCE
    bounced = FrameRenderer(cfg).render(0)
    assert np.array_equal(static, bounced)  # frame 0 sits at the configured spot


def test_image_layer_order_relative_to_grid(tmp_path):
    cfg = _image_cfg(tmp_path, scale=4.0)  # red logo covers the whole canvas
    cfg.grid.enabled = True
    cfg.grid.rows = cfg.grid.cols = 2
    cfg.grid.line_color = (0.0, 1.0, 0.0)
    cfg.grid.line_opacity = 1.0
    cfg.grid.show_labels = False

    def has_green(frame):
        return bool(((frame[..., 1] > 200) & (frame[..., 0] < 100)).any())

    behind = FrameRenderer(cfg).render(0)
    assert has_green(behind)  # grid lines drawn over the image

    cfg.image.above_grid = True
    above = FrameRenderer(cfg).render(0)
    assert not has_green(above)  # image hides the grid


def test_missing_image_file_is_reported(tmp_path):
    cfg = _tiny()
    cfg.image.enabled = True
    cfg.image.path = str(tmp_path / "nope.png")
    problems = encoder.validate(cfg)
    assert any("not found" in p for p in problems)


def test_missing_image_render_is_graceful(tmp_path):
    cfg = _tiny()
    cfg.image.enabled = True
    cfg.image.path = str(tmp_path / "nope.png")
    FrameRenderer(cfg).render(0)  # must not raise


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
