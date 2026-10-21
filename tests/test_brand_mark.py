"""The Morph monogram appears on every generated frame, in whichever variant
contrasts with the pixels behind it."""

from __future__ import annotations

import av
import numpy as np
import pytest
from PIL import Image

from projgen.core import burst, encoder, overlays
from projgen.core.config import BurstConfig, ProjectConfig
from projgen.core.render import FrameRenderer


def mark_variant_in(frame: np.ndarray) -> str | None:
    """Which monogram variant a frame carries (every opaque pixel must match)."""
    height, width = frame.shape[:2]
    mark = overlays.BrandMark(width, height)
    left, top, right, bottom = mark.box
    region = frame[top:bottom, left:right]
    for variant, image in mark.images.items():
        rgba = np.asarray(image)
        opaque = rgba[..., 3] == 255
        if opaque.any() and np.array_equal(region[opaque], rgba[..., :3][opaque]):
            return variant
    return None


def solid(rgb, size=(8, 8)) -> np.ndarray:
    return np.full((*size, 3), rgb, dtype=np.uint8)


# --- placement --------------------------------------------------------------
def test_mark_sits_bottom_right_at_a_twentieth_of_the_width():
    assert overlays.brand_mark_box(1920, 1080) == (1792, 977, 96, 71)
    left, top, w, h = overlays.brand_mark_box(3840, 2160)
    assert (w, 3840 - left - w, 2160 - top - h) == (192, 65, 65)


def test_mark_is_capped_on_very_wide_frames_and_keeps_its_shape():
    _, _, w, h = overlays.brand_mark_box(3840, 540)
    assert h <= round(0.08 * 540)
    assert h / w == pytest.approx(overlays.MONOGRAM_ASPECT, rel=0.03)


@pytest.mark.parametrize("variant", ["dark", "light"])
def test_monogram_assets_match_the_declared_aspect(variant):
    with Image.open(overlays.MONOGRAMS[variant]) as img:
        assert img.height / img.width == pytest.approx(overlays.MONOGRAM_ASPECT)


# --- variant choice ----------------------------------------------------------
@pytest.mark.parametrize("rgb,expected", [
    ((0, 0, 0), "dark"),          # white M on black
    ((255, 255, 255), "light"),   # black M on white
    ((230, 220, 30), "light"),    # yellow is bright
    ((30, 40, 220), "dark"),      # blue is dark
    ((128, 128, 128), "light"),   # mid grey sits just above the crossover
    ((100, 100, 100), "dark"),
])
def test_variant_gives_the_m_more_contrast(rgb, expected):
    assert overlays.mark_variant(overlays.relative_luminance(solid(rgb))) == expected


def test_burst_marks_follow_the_black_and_white_seconds():
    cfg = BurstConfig()
    cfg.output.width, cfg.output.height, cfg.output.duration = 640, 360, 2
    r = burst.BurstRenderer(cfg)
    assert [mark_variant_in(r.render(i)) for i in (0, 15, 29)] == ["dark"] * 3
    assert [mark_variant_in(r.render(i)) for i in (30, 45, 59)] == ["light"] * 3


def test_colour_loop_mark_follows_the_pixels_behind_it(tmp_path):
    cfg = ProjectConfig()
    cfg.output.width, cfg.output.height = 320, 180
    cfg.color_loop.enabled = False  # black background
    assert mark_variant_in(FrameRenderer(cfg).render(0)) == "dark"

    white = tmp_path / "white.png"
    Image.new("RGBA", (16, 16), (255, 255, 255, 255)).save(white)
    cfg.image.enabled, cfg.image.path, cfg.image.scale = True, str(white), 4.0
    assert mark_variant_in(FrameRenderer(cfg).render(0)) == "light"


def test_mark_applies_to_read_only_frames():
    frame = np.broadcast_to(np.zeros((1, 3), np.uint8), (180, 320, 3))  # a read-only view
    marked = overlays.BrandMark(320, 180).apply(frame)
    assert mark_variant_in(marked) == "dark"
    assert not frame.any()  # the view itself is untouched


def test_scrolling_colour_loop_switches_variant_as_the_colours_pass():
    cfg = ProjectConfig()
    cfg.output.width, cfg.output.height, cfg.output.duration, cfg.output.fps = 320, 180, 2, 25
    r = FrameRenderer(cfg)
    variants = {mark_variant_in(r.render(i)) for i in range(0, cfg.total_frames(), 2)}
    assert variants == {"dark", "light"}


# --- layout around the mark --------------------------------------------------
def test_counters_stay_clear_of_the_mark_at_the_largest_size():
    cfg = BurstConfig()
    cfg.text_size = 0.4
    r = burst.BurstRenderer(cfg)
    line_height = sum(r.font.getmetrics())
    for line in r.counter_lines:
        assert line.y + line_height / 2 <= r.brand_mark.top


@pytest.mark.parametrize("rows,cols,cell_background,lifted", [
    (8, 8, False, True),   # the default grid: the corner label must be lifted
    (6, 10, True, True),
    (4, 4, False, False),  # big cells: the label already clears the mark
])
def test_grid_labels_are_lifted_clear_of_the_mark(rows, cols, cell_background, lifted):
    cfg = ProjectConfig().grid
    cfg.enabled, cfg.rows, cfg.cols = True, rows, cols
    cfg.show_lines = False  # only labels on the overlay
    cfg.cell_background = cell_background
    mark = overlays.BrandMark(1920, 1080)
    plain = overlays.build_grid_overlay(cfg, 1920, 1080)
    clear = overlays.build_grid_overlay(cfg, 1920, 1080, avoid=mark.box)

    left, top, right, bottom = mark.box
    assert not clear[top:bottom, left:right, 3].any()  # nothing hidden under the mark

    moved = (clear[..., 3] > 0) & (plain[..., 3] == 0)  # where a lifted label now sits
    ys, _ = np.nonzero(moved)
    assert bool(ys.size) is lifted
    if lifted:  # still centred within the bottom-right cell, so it names that cell
        assert (ys.min() + ys.max()) / 2 >= 1080 - 1080 // rows


# --- exported files ---------------------------------------------------------------
@pytest.mark.parametrize("generator", ["colour_loop", "burst"])
def test_exported_png_frames_carry_the_mark(tmp_path, generator):
    cfg = BurstConfig() if generator == "burst" else ProjectConfig()
    cfg.output.width, cfg.output.height, cfg.output.duration = 320, 180, 0.2
    cfg.output.preset = "png_sequence"
    cfg.output.output_path = str(tmp_path / "frames")
    if generator == "burst":
        burst.encode_burst(cfg)
    else:
        encoder.encode(cfg)
    files = sorted((tmp_path / "frames").iterdir())
    assert files
    for path in files:
        assert mark_variant_in(np.array(Image.open(path).convert("RGB"))) is not None


def test_exported_video_carries_the_matching_mark(tmp_path):
    cfg = BurstConfig()
    cfg.output.width, cfg.output.height, cfg.output.duration = 640, 360, 2
    cfg.output.output_path = str(tmp_path / "sync")
    path = burst.encode_burst(cfg)
    r = burst.BurstRenderer(cfg)
    left, top, right, bottom = r.brand_mark.box
    with av.open(str(path)) as container:
        for i, frame in enumerate(container.decode(video=0)):
            decoded = frame.to_ndarray(format="rgb24")[top:bottom, left:right].astype(int)
            expected = r.render(i)[top:bottom, left:right].astype(int)
            assert np.abs(decoded - expected).mean() < 12  # lossy, but the right mark
