"""Configuration model for a test-pattern project.

Everything the generator needs is captured in :class:`ProjectConfig`, a plain
dataclass tree that serialises to/from JSON.  The same object drives the GUI, the
CLI, and the render pipeline, which keeps behaviour identical across entry points.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field, fields, is_dataclass
from enum import Enum
from pathlib import Path
from typing import Any


class Axis(str, Enum):
    """Direction along which the colour gradient runs."""

    X = "x"
    Y = "y"


class LineStyle(str, Enum):
    SOLID = "solid"
    SOFT = "soft"


class LabelMode(str, Enum):
    SEQUENTIAL = "sequential"  # 0, 1, 2, ...
    ROW_COL = "row_col"        # R1C1
    COORDS = "coords"          # pixel origin of the cell
    ALPHA_NUM = "alpha_num"    # A1, B2, ...


class ImageEffect(str, Enum):
    NONE = "none"
    PULSE = "pulse"  # grow & shrink
    FADE = "fade"    # opacity breathe
    SPIN = "spin"    # rotate


RGB = tuple[float, float, float]


@dataclass
class OutputConfig:
    width: int = 1920
    height: int = 1080
    fps: float = 25.0
    duration: float = 10.0  # seconds; the loop completes exactly once
    preset: str = "h264_mp4"
    # Optional advanced overrides (None -> use preset default).
    crf: int | None = None
    bitrate: str | None = None  # e.g. "12M"
    output_path: str = "output/colour_loop"


@dataclass
class ColorLoopConfig:
    enabled: bool = True
    saturation: float = 0.88
    value: float = 0.9
    hue_cycles: float = 1.0  # number of full rainbows across the axis
    direction: int = 1       # +1 / -1
    axis: Axis = Axis.X


@dataclass
class LineGroupConfig:
    """A set of evenly spaced tracking/scanning lines (horizontal or vertical)."""

    enabled: bool = False
    count: int = 1
    thickness: int = 4  # pixels
    color: RGB = (1.0, 1.0, 1.0)
    opacity: float = 1.0
    speed: float = 1.0   # sweeps per loop
    direction: int = 1   # +1 / -1
    style: LineStyle = LineStyle.SOLID
    # When True the sweep count is rounded to a whole number so the line motion
    # loops perfectly with the video. When False, `speed` is used as-is (free
    # motion that need not return to its start).
    seamless: bool = True


@dataclass
class GridConfig:
    enabled: bool = False
    rows: int = 8
    cols: int = 8
    line_color: RGB = (1.0, 1.0, 1.0)
    line_thickness: int = 2
    line_opacity: float = 0.6
    show_lines: bool = True
    show_labels: bool = True
    label_mode: LabelMode = LabelMode.ALPHA_NUM
    font_size: int = 0  # 0 -> auto-fit to cell
    font_color: RGB = (1.0, 1.0, 1.0)
    label_opacity: float = 1.0
    cell_background: bool = False  # dark pad behind labels for legibility


@dataclass
class ImageConfig:
    """A custom image/logo composited onto the pattern."""

    enabled: bool = False
    path: str = ""
    pos_x: float = 0.5   # centre position as a fraction of the canvas width
    pos_y: float = 0.5   # centre position as a fraction of the canvas height
    scale: float = 0.25  # rendered image width as a fraction of the canvas width
    opacity: float = 1.0
    effect: ImageEffect = ImageEffect.NONE
    effect_cycles: int = 1     # whole cycles per loop -> returns to start
    effect_amount: float = 0.3  # effect strength, 0..1


@dataclass
class ProjectConfig:
    output: OutputConfig = field(default_factory=OutputConfig)
    color_loop: ColorLoopConfig = field(default_factory=ColorLoopConfig)
    h_lines: LineGroupConfig = field(default_factory=LineGroupConfig)
    v_lines: LineGroupConfig = field(default_factory=LineGroupConfig)
    grid: GridConfig = field(default_factory=GridConfig)
    image: ImageConfig = field(default_factory=ImageConfig)

    # -- derived ---------------------------------------------------------
    def total_frames(self) -> int:
        """Whole frame count for exactly one loop (minimum one frame)."""
        return max(1, round(float(self.output.duration) * float(self.output.fps)))

    # -- serialisation ---------------------------------------------------
    def to_dict(self) -> dict[str, Any]:
        return _to_jsonable(self)

    def to_json(self, indent: int = 2) -> str:
        return json.dumps(self.to_dict(), indent=indent)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ProjectConfig":
        return _from_dict(cls, data)

    @classmethod
    def from_json(cls, text: str) -> "ProjectConfig":
        return cls.from_dict(json.loads(text))

    def save(self, path: str | Path) -> None:
        Path(path).write_text(self.to_json(), encoding="utf-8")

    @classmethod
    def load(cls, path: str | Path) -> "ProjectConfig":
        return cls.from_json(Path(path).read_text(encoding="utf-8"))


# ---------------------------------------------------------------------------
# (De)serialisation helpers — enum-aware, tuple-preserving, forgiving of
# unknown keys so older/newer preset files still load.
# ---------------------------------------------------------------------------
def _to_jsonable(obj: Any) -> Any:
    if is_dataclass(obj):
        return {f.name: _to_jsonable(getattr(obj, f.name)) for f in fields(obj)}
    if isinstance(obj, Enum):
        return obj.value
    if isinstance(obj, tuple):
        return list(obj)
    return obj


def _from_dict(cls: type, data: dict[str, Any]) -> Any:
    kwargs: dict[str, Any] = {}
    type_hints = {f.name: f.type for f in fields(cls)}
    for f in fields(cls):
        if f.name not in data:
            continue
        kwargs[f.name] = _coerce(type_hints[f.name], data[f.name])
    return cls(**kwargs)


def _coerce(hint: Any, value: Any) -> Any:
    # Dataclass field types may arrive as strings under `from __future__`.
    if isinstance(hint, str):
        hint = _RESOLVE.get(hint, hint)
    if is_dataclass(hint):
        return _from_dict(hint, value)
    if isinstance(hint, type) and issubclass(hint, Enum):
        return hint(value)
    if hint in (RGB, "RGB") and isinstance(value, (list, tuple)):
        return tuple(float(v) for v in value)
    if isinstance(hint, str) and hint.startswith("tuple") and isinstance(value, list):
        return tuple(value)
    return value


_RESOLVE = {
    "OutputConfig": OutputConfig,
    "ColorLoopConfig": ColorLoopConfig,
    "LineGroupConfig": LineGroupConfig,
    "GridConfig": GridConfig,
    "ImageConfig": ImageConfig,
    "Axis": Axis,
    "LineStyle": LineStyle,
    "LabelMode": LabelMode,
    "ImageEffect": ImageEffect,
}
