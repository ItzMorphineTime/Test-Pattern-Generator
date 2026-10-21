"""Video/image-sequence encoding via PyAV (FFmpeg).

Format presets map a friendly name to a concrete ``(container, codec, pixel
format, quality)`` combination.  :func:`encode_frames` feeds any stream of RGB
frames into the chosen codec, reporting progress and honouring a cancel request;
:func:`encode` wires it to the colour-loop renderer.

Helpers that take a ``config`` accept anything with an ``output`` attribute
(:class:`ProjectConfig` or :class:`BurstConfig`).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from fractions import Fraction
from pathlib import Path
from typing import Callable, Iterable, Iterator

import av
import numpy as np
from PIL import Image

from .config import OutputConfig, ProjectConfig
from .render import iter_frames

ProgressFn = Callable[[int, int], None]
CancelFn = Callable[[], bool]


@dataclass(frozen=True)
class FormatPreset:
    key: str
    label: str
    extension: str          # ".mp4" for video; "" for an image sequence dir
    codec: str              # PyAV codec name, or "png"/"tiff" for sequences
    pix_fmt: str
    quality_kind: str       # "crf" | "bitrate" | "profile" | "lossless" | "image"
    default_crf: int = 20
    container: str | None = None   # force a muxer; None -> infer from extension
    options: dict = field(default_factory=dict)
    is_sequence: bool = False

    @property
    def requires_even(self) -> bool:
        return self.pix_fmt in {"yuv420p", "yuvj420p", "nv12"}


FORMAT_PRESETS: dict[str, FormatPreset] = {
    "h264_mp4": FormatPreset(
        "h264_mp4", "H.264 MP4 (web / default)", ".mp4", "libx264", "yuv420p",
        "crf", default_crf=18, options={"preset": "medium"},
    ),
    "h265_mp4": FormatPreset(
        "h265_mp4", "H.265 / HEVC MP4 (smaller)", ".mp4", "libx265", "yuv420p",
        "crf", default_crf=22, options={"preset": "medium", "tag": "hvc1"},
    ),
    "vp9_webm": FormatPreset(
        "vp9_webm", "VP9 WebM", ".webm", "libvpx-vp9", "yuv420p",
        "crf", default_crf=30, options={"b": "0", "deadline": "good"},
    ),
    "av1_mp4": FormatPreset(
        "av1_mp4", "AV1 MP4 (SVT-AV1)", ".mp4", "libsvtav1", "yuv420p",
        "crf", default_crf=30, options={"preset": "8"},
    ),
    "prores_mov": FormatPreset(
        "prores_mov", "ProRes 422 HQ MOV (editing)", ".mov", "prores_ks",
        "yuv422p10le", "profile", options={"profile": "3"},
    ),
    "ffv1_mkv": FormatPreset(
        "ffv1_mkv", "Lossless FFV1 MKV (archival)", ".mkv", "ffv1", "yuv444p",
        "lossless", options={"level": "3"},
    ),
    "png_sequence": FormatPreset(
        "png_sequence", "PNG image sequence", "", "png", "rgb24",
        "image", is_sequence=True,
    ),
}

DEFAULT_PRESET = "h264_mp4"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
_NTSC = {23.976: Fraction(24000, 1001),
         29.97: Fraction(30000, 1001),
         59.94: Fraction(60000, 1001)}


def fps_fraction(fps: float) -> Fraction:
    """Best-fit rational frame rate, snapping to common NTSC rates."""
    for nominal, frac in _NTSC.items():
        if abs(fps - nominal) < 0.01:
            return frac
    if abs(fps - round(fps)) < 1e-6:
        return Fraction(int(round(fps)), 1)
    return Fraction(fps).limit_denominator(100000)


def preset_for(output: OutputConfig) -> FormatPreset:
    return FORMAT_PRESETS.get(output.preset, FORMAT_PRESETS[DEFAULT_PRESET])


def output_path_for(output: OutputConfig) -> Path:
    """Full output path with the correct extension (or directory for sequences)."""
    preset = preset_for(output)
    base = Path(output.output_path)
    if preset.is_sequence:
        return base  # treated as a directory
    if base.suffix.lower() != preset.extension:
        base = base.with_suffix(preset.extension)
    return base


def get_preset(config) -> FormatPreset:
    return preset_for(config.output)


def resolve_output_path(config) -> Path:
    return output_path_for(config.output)


class DimensionError(ValueError):
    """Raised when the resolution is invalid for the selected codec."""


def validate(config) -> list[str]:
    """Return a list of human-readable problems (empty if the config is valid)."""
    problems: list[str] = []
    output = config.output
    preset = preset_for(output)
    w, h = output.width, output.height
    if w < 2 or h < 2:
        problems.append("Width and height must be at least 2 pixels.")
    if preset.requires_even and (w % 2 or h % 2):
        problems.append(
            f"{preset.label} needs even width and height (got {w}x{h})."
        )
    if output.fps <= 0:
        problems.append("Frame rate must be positive.")
    if output.duration <= 0:
        problems.append("Duration must be positive.")
    img = getattr(config, "image", None)
    if img is not None and img.enabled and img.path and not Path(img.path).is_file():
        problems.append(f"Image/logo file not found: {img.path}")
    return problems


# ---------------------------------------------------------------------------
# Encoding
# ---------------------------------------------------------------------------
def _stream_options(output: OutputConfig, preset: FormatPreset) -> dict:
    opts = dict(preset.options)
    if preset.quality_kind == "crf":
        crf = output.crf if output.crf is not None else preset.default_crf
        opts["crf"] = str(crf)
    return opts


def encode(
    config: ProjectConfig,
    progress: ProgressFn | None = None,
    cancel: CancelFn | None = None,
    font_family: str | None = None,
) -> Path:
    """Render and encode the whole colour loop; return the written path.

    ``progress(done, total)`` is called after each frame; ``cancel()`` returning
    True stops early (a partial file may remain).
    """
    problems = validate(config)
    if problems:
        raise DimensionError(" ".join(problems))
    frames = iter_frames(config, font_family)
    return encode_frames(config.output, frames, config.total_frames(), progress, cancel)


def encode_frames(
    output: OutputConfig,
    frames: Iterable[np.ndarray],
    total: int,
    progress: ProgressFn | None = None,
    cancel: CancelFn | None = None,
    sequence_start: int = 0,
) -> Path:
    """Encode ``total`` RGB frames with ``output``'s format; return the written path.

    ``sequence_start`` is the number in the first image-sequence file name.
    """
    preset = preset_for(output)
    out_path = output_path_for(output)
    if preset.is_sequence:
        return _encode_sequence(frames, out_path, total, preset, progress, cancel,
                                sequence_start)
    return _encode_video(output, frames, out_path, total, preset, progress, cancel)


def frame_file_pad(total: int, start: int = 0) -> int:
    """Zero-padding width for numbered frame files."""
    return max(4, len(str(total + start)))


def tee_png_frames(frames: Iterable[np.ndarray], out_dir: Path, total: int,
                   start: int = 0) -> Iterator[np.ndarray]:
    """Pass frames through unchanged while also saving each one as a PNG."""
    out_dir.mkdir(parents=True, exist_ok=True)
    pad = frame_file_pad(total, start)
    for i, frame_np in enumerate(frames):
        Image.fromarray(frame_np).save(out_dir / f"frame_{start + i:0{pad}d}.png")
        yield frame_np


def _encode_video(output: OutputConfig, frames, out_path: Path, total: int,
                  preset: FormatPreset, progress: ProgressFn | None,
                  cancel: CancelFn | None) -> Path:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    rate = fps_fraction(output.fps)

    container = av.open(str(out_path), mode="w", format=preset.container)
    try:
        stream = container.add_stream(preset.codec, rate=rate)
        stream.width = output.width
        stream.height = output.height
        stream.pix_fmt = preset.pix_fmt
        stream.options = _stream_options(output, preset)
        if output.bitrate:
            stream.bit_rate = _parse_bitrate(output.bitrate)

        for i, frame_np in enumerate(frames):
            if cancel and cancel():
                break
            video_frame = av.VideoFrame.from_ndarray(frame_np, format="rgb24")
            video_frame.pts = i
            for packet in stream.encode(video_frame):
                container.mux(packet)
            if progress:
                progress(i + 1, total)

        for packet in stream.encode():  # flush
            container.mux(packet)
    finally:
        container.close()
    return out_path


def _encode_sequence(frames: Iterable[np.ndarray], out_dir: Path, total: int,
                     preset: FormatPreset, progress: ProgressFn | None,
                     cancel: CancelFn | None, start: int = 0) -> Path:
    out_dir.mkdir(parents=True, exist_ok=True)
    ext = "png" if preset.codec == "png" else "tiff"
    pad = frame_file_pad(total, start)
    for i, frame_np in enumerate(frames):
        if cancel and cancel():
            break
        Image.fromarray(frame_np).save(out_dir / f"frame_{start + i:0{pad}d}.{ext}")
        if progress:
            progress(i + 1, total)
    return out_dir


def _parse_bitrate(text: str) -> int:
    text = text.strip().upper()
    mult = 1
    if text.endswith("K"):
        mult, text = 1_000, text[:-1]
    elif text.endswith("M"):
        mult, text = 1_000_000, text[:-1]
    return int(float(text) * mult)
