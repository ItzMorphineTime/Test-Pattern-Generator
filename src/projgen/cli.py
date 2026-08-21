"""Headless command-line interface.

Renders a project to a video/image sequence without a GUI — for batch jobs,
scripting, and CI.  Any options given override values loaded from ``--config``.
"""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

from .core import encoder
from .core.config import Axis, LabelMode, LineStyle, ProjectConfig


def _parse_color(text: str) -> tuple[float, float, float]:
    text = text.strip()
    if text.startswith("#"):
        text = text[1:]
        r, g, b = (int(text[i:i + 2], 16) for i in (0, 2, 4))
    else:
        r, g, b = (int(p) for p in text.split(","))
    return (r / 255.0, g / 255.0, b / 255.0)


def _parse_grid(text: str) -> tuple[int, int]:
    rows, cols = text.lower().split("x")
    return int(rows), int(cols)


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="projgen",
        description="Generate seamless projection-mapping test patterns.",
    )
    p.add_argument("--config", type=Path, help="Load a saved preset (.json) as the base.")
    p.add_argument("--save-config", type=Path, help="Write the resolved config and exit.")
    p.add_argument("--out", "-o", help="Output path (extension added to match the format).")
    p.add_argument("--list-presets", action="store_true", help="List format presets and exit.")

    out = p.add_argument_group("output")
    out.add_argument("--preset", choices=sorted(encoder.FORMAT_PRESETS), help="Video format.")
    out.add_argument("--width", type=int)
    out.add_argument("--height", type=int)
    out.add_argument("--fps", type=float)
    out.add_argument("--duration", type=float, help="Seconds (one seamless loop).")
    out.add_argument("--crf", type=int, help="Quality (lower = better) for CRF codecs.")
    out.add_argument("--bitrate", help="Target bitrate, e.g. 12M (overrides CRF).")

    cl = p.add_argument_group("colour loop")
    cl.add_argument("--no-color", action="store_true", help="Disable the colour loop.")
    cl.add_argument("--saturation", type=float)
    cl.add_argument("--value", type=float)
    cl.add_argument("--hue-cycles", type=float)
    cl.add_argument("--direction", type=int, choices=(-1, 1))
    cl.add_argument("--axis", choices=("x", "y"))

    for tag, name in (("h", "horizontal"), ("v", "vertical")):
        g = p.add_argument_group(f"{name} tracking lines")
        g.add_argument(f"--{tag}lines", type=int, metavar="COUNT",
                       help=f"Enable {name} lines with COUNT lines.")
        g.add_argument(f"--{tag}line-thickness", type=int)
        g.add_argument(f"--{tag}line-speed", type=float, help="Sweeps per loop.")
        g.add_argument(f"--{tag}line-color", type=_parse_color, metavar="R,G,B|#hex")
        g.add_argument(f"--{tag}line-opacity", type=float)
        g.add_argument(f"--{tag}line-style", choices=("solid", "soft"))
        g.add_argument(f"--{tag}line-free", action="store_true",
                       help="Disable seamless looping (use the exact speed).")

    gr = p.add_argument_group("number grid")
    gr.add_argument("--grid", type=_parse_grid, metavar="ROWSxCOLS",
                    help="Enable a grid, e.g. 8x8.")
    gr.add_argument("--grid-labels", choices=[m.value for m in LabelMode])
    gr.add_argument("--grid-font-size", type=int, help="0 = auto-fit.")
    gr.add_argument("--grid-no-lines", action="store_true")
    gr.add_argument("--grid-no-labels", action="store_true")
    gr.add_argument("--grid-cell-bg", action="store_true", help="Dark pad behind labels.")
    return p


def config_from_args(args: argparse.Namespace) -> ProjectConfig:
    cfg = ProjectConfig.load(args.config) if args.config else ProjectConfig()

    o = cfg.output
    for attr in ("preset", "width", "height", "fps", "duration", "crf", "bitrate"):
        val = getattr(args, attr)
        if val is not None:
            setattr(o, attr, val)
    if args.out:
        o.output_path = args.out

    cl = cfg.color_loop
    if args.no_color:
        cl.enabled = False
    for src, dst in (("saturation", "saturation"), ("value", "value"),
                     ("hue_cycles", "hue_cycles"), ("direction", "direction")):
        val = getattr(args, src)
        if val is not None:
            setattr(cl, dst, val)
    if args.axis:
        cl.axis = Axis(args.axis)

    for tag, group in (("h", cfg.h_lines), ("v", cfg.v_lines)):
        count = getattr(args, f"{tag}lines")
        if count is not None:
            group.enabled = count > 0
            group.count = max(1, count)
        for attr, dst in (("thickness", "thickness"), ("speed", "speed"),
                          ("color", "color"), ("opacity", "opacity")):
            val = getattr(args, f"{tag}line_{attr}")
            if val is not None:
                setattr(group, dst, val)
        style = getattr(args, f"{tag}line_style")
        if style:
            group.style = LineStyle(style)
        if getattr(args, f"{tag}line_free"):
            group.seamless = False

    g = cfg.grid
    if args.grid is not None:
        g.enabled = True
        g.rows, g.cols = args.grid
    if args.grid_labels:
        g.label_mode = LabelMode(args.grid_labels)
    if args.grid_font_size is not None:
        g.font_size = args.grid_font_size
    if args.grid_no_lines:
        g.show_lines = False
    if args.grid_no_labels:
        g.show_labels = False
    if args.grid_cell_bg:
        g.cell_background = True
    return cfg


def _progress(done: int, total: int) -> None:
    pct = 100.0 * done / max(1, total)
    bar = "#" * int(pct / 4)
    sys.stdout.write(f"\r  [{bar:<25}] {done}/{total} ({pct:5.1f}%)")
    sys.stdout.flush()


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)

    if args.list_presets:
        for key, preset in FORMAT_PRESETS_SORTED():
            print(f"  {key:14} {preset.label}")
        return 0

    cfg = config_from_args(args)

    if args.save_config:
        cfg.save(args.save_config)
        print(f"Saved config to {args.save_config}")
        return 0

    problems = encoder.validate(cfg)
    if problems:
        print("Invalid configuration:", file=sys.stderr)
        for msg in problems:
            print(f"  - {msg}", file=sys.stderr)
        return 2

    preset = encoder.get_preset(cfg)
    out = encoder.resolve_output_path(cfg)
    print(f"Rendering {cfg.total_frames()} frames -> {out} [{preset.label}]")
    start = time.time()
    try:
        written = encoder.encode(cfg, progress=_progress)
    except Exception as exc:  # noqa: BLE001 - surface any encode failure to the user
        print(f"\nError: {exc}", file=sys.stderr)
        return 1
    print(f"\nDone in {time.time() - start:.1f}s -> {written}")
    return 0


def FORMAT_PRESETS_SORTED():
    return sorted(encoder.FORMAT_PRESETS.items())


if __name__ == "__main__":
    raise SystemExit(main())
