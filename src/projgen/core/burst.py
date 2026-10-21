"""Black & burst sync test pattern.

Every frame shows its frame number and second number. The background alternates
black and white each second, and three evenly spaced regions across the top of
the canvas cycle red -> green -> blue, each visible for a third of a second
(fps / 3 frames), so the colour cycle stays in step with the background flip.

Seconds are counted in whole frames -- ``round(fps)`` frames per second, like
non-drop-frame timecode -- so 29.97 fps counts 30 frames to the second. When the
frame count doesn't divide by three, the extra frames go to the earlier colours
(25 fps -> 9/8/8).
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Iterator

import numpy as np
from PIL import Image, ImageDraw

from . import encoder
from .config import BurstConfig
from .encoder import CancelFn, ProgressFn
from .overlays import BrandMark, load_font

REGION_COLOURS = ((255, 0, 0), (0, 255, 0), (0, 0, 255))
BLACK = (0, 0, 0)
WHITE = (255, 255, 255)


def frames_per_second(fps: float) -> int:
    """Whole frames counted as one second (timecode style)."""
    return max(1, round(fps))


@dataclass(frozen=True)
class BurstFrame:
    index: int            # 0-based frame index
    second: int           # 0-based second index
    frame_in_second: int  # 0-based position within the second
    region: int           # visible region: 0 red, 1 green, 2 blue
    white: bool           # white background this second


@dataclass(frozen=True)
class CounterLine:
    prefix: str           # "FRAME " or "SECOND "
    pad: int              # digits shown, zero-padded
    x: float              # left edge of the line
    y: float              # vertical middle of the line
    prefix_width: float
    width: float          # whole line: prefix plus pad fixed-width digit cells


def frame_at(index: int, fps: float) -> BurstFrame:
    n = frames_per_second(fps)
    second, within = divmod(index, n)
    return BurstFrame(index, second, within, min(2, within * 3 // n), second % 2 == 1)


def region_split(fps: float) -> tuple[int, int, int]:
    """Frames each colour region is shown for within one second."""
    n = frames_per_second(fps)
    counts = [0, 0, 0]
    for within in range(n):
        counts[min(2, within * 3 // n)] += 1
    return counts[0], counts[1], counts[2]


def validate(cfg: BurstConfig) -> list[str]:
    problems = encoder.validate(cfg)
    if frames_per_second(cfg.output.fps) < 3:
        problems.append("Frame rate must be at least 3 fps so each colour region "
                        "gets a frame.")
    return problems


def png_frames_dir(cfg: BurstConfig) -> Path | None:
    """Folder for the extra PNG frames, or None when not requested or redundant."""
    if not cfg.export_png or encoder.get_preset(cfg).is_sequence:
        return None
    video = encoder.resolve_output_path(cfg)
    return video.with_name(f"{video.stem}_frames")


class BurstRenderer:
    """Renders black & burst frames for a fixed :class:`BurstConfig`.

    The six background/region combinations, each carrying the Morph brand mark,
    are drawn once and cached; each frame copies its base and adds the counters.
    """

    def __init__(self, cfg: BurstConfig):
        self.cfg = cfg
        self.width = cfg.output.width
        self.height = cfg.output.height
        self.fps = cfg.output.fps
        self.total = cfg.total_frames()
        self.boxes = self._layout_regions()
        self.brand_mark = BrandMark(self.width, self.height)

        last = frame_at(self.total - 1, self.fps)
        self._frame_pad = max(4, len(str(last.index + cfg.start_number)))
        self._second_pad = max(2, len(str(last.second + cfg.start_number)))
        self._layout_text()
        self._bases: dict[tuple[bool, int], Image.Image] = {}

    # -- layout ----------------------------------------------------------
    def _layout_regions(self) -> list[tuple[int, int, int, int]]:
        """Three equal boxes across the top, with equal gaps around and between."""
        w, h = self.width, self.height
        gap = max(0.0, min(self.cfg.region_gap, 0.2)) * w
        box_w = max(1.0, (w - 4 * gap) / 3)
        box_h = max(1.0, min(self.cfg.region_height, 0.9) * h)
        top = min(gap, max(0.0, h - box_h))
        boxes = []
        for k in range(3):
            x0 = gap + k * (box_w + gap)
            left, upper = round(x0), round(top)
            right = max(left, round(x0 + box_w) - 1)
            lower = max(upper, round(top + box_h) - 1)
            boxes.append((left, upper, right, lower))
        return boxes

    def _layout_text(self) -> None:
        """Size the counters to fit below the regions and fix their positions.

        Digits are drawn one per fixed-width cell (the width of the widest
        digit), because the brand font's figures are proportional; with
        constant-width lines centred once, the counters never shift or wobble
        as the numbers change.
        """
        w, h = self.width, self.height
        margin = max(1, round(0.03 * h))
        area_top = max(box[3] for box in self.boxes) + 1 + margin
        area_bottom = self.brand_mark.top - margin  # the counters never reach the mark
        avail = max(1, area_bottom - area_top)
        lines = (("FRAME ", self._frame_pad), ("SECOND ", self._second_pad))

        def measure(size):
            font = load_font(size, None)
            ascent, descent = font.getmetrics()
            line_h = ascent + descent
            digit_w = max(font.getlength(d) for d in "0123456789")
            widths = [font.getlength(prefix) + pad * digit_w for prefix, pad in lines]
            return font, line_h, round(0.25 * line_h), digit_w, widths

        size = max(6, round(self.cfg.text_size * h))
        for _ in range(4):
            _, line_h, line_gap, _, widths = measure(size)
            scale = min(1.0, 0.9 * w / max(1.0, max(widths)),
                        0.9 * avail / max(1, 2 * line_h + line_gap))
            if scale >= 0.99 or size <= 6:
                break
            size = max(6, int(size * scale))

        font, line_h, line_gap, digit_w, widths = measure(size)
        self.font = font
        self.font_size = size
        self.digit_width = digit_w
        centre_y = (area_top + area_bottom) / 2
        offset = (line_h + line_gap) / 2
        self.counter_lines = [
            CounterLine(prefix, pad, (w - width) / 2, y, font.getlength(prefix), width)
            for (prefix, pad), width, y in zip(lines, widths, (centre_y - offset, centre_y + offset))
        ]

    # -- rendering -------------------------------------------------------
    def labels(self, frame: BurstFrame) -> tuple[str, str]:
        start = self.cfg.start_number
        return (f"FRAME {frame.index + start:0{self._frame_pad}d}",
                f"SECOND {frame.second + start:0{self._second_pad}d}")

    def _base(self, white: bool, region: int) -> Image.Image:
        key = (white, region)
        base = self._bases.get(key)
        if base is None:
            base = Image.new("RGB", (self.width, self.height), WHITE if white else BLACK)
            ImageDraw.Draw(base).rectangle(self.boxes[region], fill=REGION_COLOURS[region])
            self.brand_mark.paste(base)
            self._bases[key] = base
        return base

    def render(self, index: int) -> np.ndarray:
        frame = frame_at(index, self.fps)
        img = self._base(frame.white, frame.region).copy()
        draw = ImageDraw.Draw(img)
        ink = BLACK if frame.white else WHITE
        start = self.cfg.start_number
        for line, number in zip(self.counter_lines, (frame.index + start, frame.second + start)):
            draw.text((line.x, line.y), line.prefix, font=self.font, fill=ink, anchor="lm")
            for i, digit in enumerate(f"{number:0{line.pad}d}"):
                cell_centre = line.x + line.prefix_width + (i + 0.5) * self.digit_width
                draw.text((cell_centre, line.y), digit, font=self.font, fill=ink, anchor="mm")
        return np.array(img)

    def iter_frames(self) -> Iterator[np.ndarray]:
        for i in range(self.total):
            yield self.render(i)


def encode_burst(cfg: BurstConfig, progress: ProgressFn | None = None,
                 cancel: CancelFn | None = None) -> Path:
    """Render and encode the burst test; return the main output path.

    With ``export_png`` on (and a video format), every frame is also written as
    a PNG to :func:`png_frames_dir`, named after its burned-in frame number.
    """
    problems = validate(cfg)
    if problems:
        raise encoder.DimensionError(" ".join(problems))
    renderer = BurstRenderer(cfg)
    frames = renderer.iter_frames()
    png_dir = png_frames_dir(cfg)
    if png_dir is not None:
        frames = encoder.tee_png_frames(frames, png_dir, renderer.total, cfg.start_number)
    return encoder.encode_frames(cfg.output, frames, renderer.total, progress, cancel,
                                 sequence_start=cfg.start_number)
