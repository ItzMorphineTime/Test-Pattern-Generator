"""Tests for the black & burst sync test generator."""

from __future__ import annotations

import numpy as np
import pytest

from projgen.core import burst
from projgen.core.config import BurstConfig, ProjectConfig


def _cfg(fps=30.0, duration=2.0, width=192, height=108, **kw) -> BurstConfig:
    cfg = BurstConfig()
    cfg.output.width, cfg.output.height = width, height
    cfg.output.fps, cfg.output.duration = fps, duration
    for key, value in kw.items():
        setattr(cfg, key, value)
    return cfg


def _centre(box):
    left, upper, right, lower = box
    return (upper + lower) // 2, (left + right) // 2  # (row, col)


# --- timing -----------------------------------------------------------------
def test_regions_cycle_in_thirds_at_30fps():
    regions = [burst.frame_at(i, 30).region for i in range(30)]
    assert regions == [0] * 10 + [1] * 10 + [2] * 10


def test_region_split_spreads_uneven_frame_counts():
    assert burst.region_split(30) == (10, 10, 10)
    assert burst.region_split(24) == (8, 8, 8)
    assert burst.region_split(25) == (9, 8, 8)
    assert burst.region_split(60) == (20, 20, 20)


def test_background_alternates_black_white_each_second():
    whites = [burst.frame_at(i, 30).white for i in (0, 29, 30, 59, 60)]
    assert whites == [False, False, True, True, False]


def test_ntsc_rates_count_whole_frames_per_second():
    assert burst.frames_per_second(29.97) == 30
    assert burst.frame_at(30, 29.97).second == 1


# --- rendering --------------------------------------------------------------
def test_only_the_active_region_is_visible():
    r = burst.BurstRenderer(_cfg())
    red, green, blue = (_centre(b) for b in r.boxes)

    first = r.render(0)  # black second, red third
    assert tuple(first[2, 2]) == (0, 0, 0)
    assert tuple(first[red]) == (255, 0, 0)
    assert tuple(first[green]) == (0, 0, 0)
    assert tuple(first[blue]) == (0, 0, 0)

    mid = r.render(15)  # black second, green third
    assert tuple(mid[red]) == (0, 0, 0)
    assert tuple(mid[green]) == (0, 255, 0)

    late = r.render(25)  # blue third
    assert tuple(late[blue]) == (0, 0, 255)

    white = r.render(35)  # white second, red third again
    assert tuple(white[2, 2]) == (255, 255, 255)
    assert tuple(white[red]) == (255, 0, 0)
    assert tuple(white[green]) == (255, 255, 255)


def test_regions_are_evenly_spaced_across_the_top():
    r = burst.BurstRenderer(_cfg(width=1920, height=1080))
    widths = [right - left for left, _, right, _ in r.boxes]
    gaps = [r.boxes[k + 1][0] - r.boxes[k][2] for k in range(2)]
    assert max(widths) - min(widths) <= 1
    assert max(gaps) - min(gaps) <= 1
    assert r.boxes[0][0] == pytest.approx(1920 - r.boxes[2][2], abs=2)  # symmetric


def test_counter_changes_every_frame_below_the_regions():
    r = burst.BurstRenderer(_cfg())
    a, b = r.render(0), r.render(1)  # same background and region
    changed_rows = np.nonzero((a != b).any(axis=(1, 2)))[0]
    assert changed_rows.size > 0
    assert changed_rows.min() > max(box[3] for box in r.boxes)


def test_text_ink_contrasts_with_the_background():
    r = burst.BurstRenderer(_cfg())
    black_second = r.render(3)
    white_second = r.render(33)
    text_rows = slice(max(box[3] for box in r.boxes) + 1, None)
    assert (black_second[text_rows] == 255).all(axis=2).any()  # white ink
    assert (white_second[text_rows] == 0).all(axis=2).any()    # black ink


def test_labels_and_numbering_start():
    r0 = burst.BurstRenderer(_cfg())
    assert r0.labels(burst.frame_at(0, 30)) == ("FRAME 0000", "SECOND 00")
    assert r0.labels(burst.frame_at(45, 30)) == ("FRAME 0045", "SECOND 01")
    r1 = burst.BurstRenderer(_cfg(start_number=1))
    assert r1.labels(burst.frame_at(0, 30)) == ("FRAME 0001", "SECOND 01")


def test_text_shrinks_to_fit_a_portrait_canvas():
    tall = burst.BurstRenderer(_cfg(width=108, height=192, text_size=0.3))
    for line in tall.counter_lines:
        assert line.x >= 0 and line.x + line.width <= 108
    tall.render(0)  # must not raise


def test_counters_do_not_shift_when_digits_change_width():
    # "1" is much narrower than "4" in the brand font; fixed-width digit cells
    # keep the "FRAME " prefix pixel-identical across these frames.
    r = burst.BurstRenderer(_cfg(width=640, height=360))
    line = r.counter_lines[0]
    rows = slice(round(line.y - r.font_size), round(line.y + r.font_size))
    cols = slice(round(line.x), round(line.x + line.prefix_width) - 2)
    one, four = r.render(1), r.render(4)  # same background and region
    assert np.array_equal(one[rows, cols], four[rows, cols])
    assert not np.array_equal(one, four)  # but the digits did change


# --- export -----------------------------------------------------------------
def test_validation_requires_three_frames_per_second():
    assert any("3 fps" in p for p in burst.validate(_cfg(fps=2)))
    assert burst.validate(_cfg()) == []


def test_video_export_with_png_frames(tmp_path):
    cfg = _cfg(duration=0.5, width=64, height=48, export_png=True)
    cfg.output.output_path = str(tmp_path / "sync")
    written = burst.encode_burst(cfg)
    assert written.suffix == ".mp4" and written.stat().st_size > 0
    pngs = sorted(p.name for p in (tmp_path / "sync_frames").iterdir())
    assert len(pngs) == 15
    assert pngs[0] == "frame_0000.png" and pngs[-1] == "frame_0014.png"


def test_png_names_follow_the_numbering_start(tmp_path):
    cfg = _cfg(duration=0.2, width=64, height=48, start_number=1)
    cfg.output.preset = "png_sequence"
    cfg.output.output_path = str(tmp_path / "frames")
    burst.encode_burst(cfg)
    names = sorted(p.name for p in (tmp_path / "frames").iterdir())
    assert names[0] == "frame_0001.png" and len(names) == 6


def test_png_option_is_not_duplicated_for_sequence_output(tmp_path):
    cfg = _cfg(export_png=True)
    cfg.output.preset = "png_sequence"
    assert burst.png_frames_dir(cfg) is None


def test_cli_burst_mode_routes_output_flags_and_renders(tmp_path):
    from projgen import cli

    args = cli.build_parser().parse_args(
        ["--burst", "--width", "64", "--height", "48", "--fps", "25",
         "--duration", "0.4", "--burst-png", "--burst-start", "1",
         "-o", str(tmp_path / "sync")])
    cfg = cli.config_from_args(args)
    assert cfg.burst.output.fps == 25 and cfg.burst.output.width == 64
    assert cfg.output.width == 1920  # colour loop output untouched

    assert cli.main(["--burst", "--width", "64", "--height", "48", "--fps", "25",
                     "--duration", "0.4", "--burst-png", "--burst-start", "1",
                     "-o", str(tmp_path / "sync")]) == 0
    assert (tmp_path / "sync.mp4").is_file()
    names = sorted(p.name for p in (tmp_path / "sync_frames").iterdir())
    assert names[0] == "frame_0001.png" and len(names) == 10


def test_burst_settings_round_trip_through_presets():
    project = ProjectConfig()
    project.burst.start_number = 1
    project.burst.export_png = True
    project.burst.region_height = 0.3
    restored = ProjectConfig.from_json(project.to_json())
    assert restored.burst.start_number == 1
    assert restored.burst.export_png is True
    assert restored.burst.region_height == 0.3
    assert restored.burst.output.fps == 30.0
    assert restored.burst.output.output_path == "output/black_burst"
