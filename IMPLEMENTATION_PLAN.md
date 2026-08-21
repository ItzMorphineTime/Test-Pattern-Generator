# Projection Test-Pattern Generator — Implementation Plan

Standalone desktop app (`.exe`) that generates seamless, loopable test patterns for
projection mapping, exports them to any common video format, and overlays optional
horizontal/vertical tracking lines and number grids.

---

## 1. Analysis of the existing Blender script

`BlenderSimpleProjectionColourLoop.py` is a Blender 5.x add-on that:

1. Builds a scene: an **orthographic camera** pointed at a **flat plane** sized to the
   output aspect ratio.
2. Gives the plane an **emission material** whose colour is an HSV combine node where
   `hue = fract(UV.x + (frame-1)/total_frames)`, `sat = 0.88`, `val = 0.9`.
3. Configures FFmpeg output (codec/container negotiation with fallbacks for Blender
   version differences) and renders the animation to a video file.

### What it does well
- **The seamless-loop math is correct.** Over `N` frames, time runs `0 → (N-1)/N`; the
  hypothetical frame `N+1` equals frame `1` because `fract(1.0) == fract(0.0)`. Clean.
- **Robust codec/container negotiation** — it defensively probes Blender's RNA enums so
  it survives across Blender versions. Most of that complexity exists *only because*
  Blender's FFmpeg surface keeps changing.
- **Even-dimension guard** for H.264/H.265/MPEG-4 (required for `yuv420p`).

### Core problem: Blender is the wrong engine for a 2D task
The output is a **1-D hue gradient scrolling along X**. Rendering this through a full 3D
DCC engine means:

| Cost of the Blender approach | Consequence |
|---|---|
| ~1–4 GB Blender install is a hard runtime dependency | Cannot ship as a small standalone app |
| GPU/EEVEE render pipeline for flat colour | Slow, non-deterministic across GPUs/drivers |
| Colour management surprises | It sets `Standard` view transform **and** a `Medium High Contrast` look — the look re-grades the colours, so exported hues are not the pure HSV values intended (a latent bug) |
| Overlays (lines, grids, text) require shader-node graphs | Adding features means node plumbing, not code |
| No live preview | Every tweak needs a full render to evaluate |

### Other observations / latent issues
- Saturation `0.88` and value `0.9` are **hard-coded** with no UI.
- `fps_base = integer_fps / frame_rate` handles fractional fps (e.g. 23.976) — worth
  preserving in the port.
- Only one pattern (scrolling hue). No lines, no grids, no direction/speed control.
- Output correctness depends on Blender's colour pipeline being exactly right.

### Conclusion
**Drop Blender entirely.** Generate frames directly as NumPy arrays and encode with a
bundled FFmpeg. This removes the giant dependency, makes output pixel-exact and
deterministic, enables a live preview, and turns "add an overlay" into "add a function".

---

## 2. Target architecture

Pure, testable core; thin UI and CLI on top; one encoder boundary.

```
projgen/
├── core/
│   ├── config.py        # dataclasses for all settings + JSON preset load/save
│   ├── color.py         # vectorized HSV->RGB, palette helpers
│   ├── pattern.py       # base pattern frame generators (colour loop, etc.)
│   ├── overlays.py      # scan/tracking lines + number grid (compositated on frames)
│   ├── loop.py          # seamless timing helpers (phase from frame index)
│   ├── render.py        # frame iterator: params -> generator[np.ndarray]
│   └── encoder.py       # FFmpeg wrapper, format presets, even-dim enforcement
├── ui/
│   ├── app.py           # PySide6 main window, controls, live preview
│   ├── preview.py       # QImage preview widget (downscaled, throttled)
│   └── render_worker.py # QThread: runs render+encode off the UI thread, progress/cancel
├── cli.py               # argparse headless mode (batch / scripting / CI)
├── assets/
│   └── fonts/DejaVuSansMono.ttf   # bundled for number grid (open license)
├── __main__.py          # entry point: GUI if no args, CLI if args
├── pyproject.toml
└── build/
    ├── projgen.spec     # PyInstaller spec
    └── installer.iss    # (optional) Inno Setup installer
```

**Design rule:** `core/` never imports UI or FFmpeg-specific types. A frame is always an
`np.uint8` array of shape `(H, W, 3)` (or `(H, W, 4)` when alpha is needed). Everything is
a pure function of `(config, frame_index, total_frames)`, which makes the whole thing
unit-testable and deterministic.

---

## 3. Technology choices (with rationale)

| Concern | Recommendation | Why / alternatives |
|---|---|---|
| Frame generation | **NumPy** | Vectorized; a 1080p frame is a trivial array op. |
| Text (number grid) | **Pillow (PIL)** + bundled TTF | `ImageDraw.text`; composite onto the NumPy frame. |
| Video encoding | **PyAV** (FFmpeg bindings) | Direct control of container, codec, pixel format, CRF/bitrate, fps (incl. fractional). Alt: `imageio-ffmpeg` (simpler API, bundles a static `ffmpeg.exe`) — easier packaging, less control. **Pick PyAV**, fall back to piping frames to a bundled `ffmpeg` binary if a codec isn't compiled in. |
| GUI | **PySide6 (Qt)** | Best live-preview story (`QImage`), native look, `QThread` for background render, mature. Alt: `customtkinter` (much smaller exe, weaker preview) or `DearPyGui` (GPU preview, less standard). **Pick PySide6**; note it adds ~40–60 MB to the build. |
| Packaging | **PyInstaller** (onedir) | Reliable on Windows; onedir starts faster and makes bundling the FFmpeg binary + font straightforward. Alt: Nuitka (smaller/faster, trickier). |
| Installer (optional) | **Inno Setup** | Produces a familiar Windows installer + Start-menu entry. |

Everything above is cross-platform, so a macOS/Linux build is a later `.spec` variant, not
a rewrite.

---

## 4. Feature spec

### 4.1 Base pattern — seamless colour loop (port of current behaviour)
Reproduce the existing look exactly, then expose what was hard-coded.

Per-pixel hue, given normalized x `u ∈ [0,1)` and frame phase `p = frame / N`:

```python
# color.py — vectorized, no per-pixel Python loop
def colour_loop_frame(cfg, frame_idx, total_frames):
    u = np.linspace(0.0, 1.0, cfg.width, endpoint=False)          # (W,)
    phase = frame_idx / total_frames                               # seamless: p in [0, (N-1)/N]
    hue = np.mod(u * cfg.hue_cycles * cfg.direction + phase, 1.0)  # (W,)
    hsv = np.empty((cfg.width, 3), np.float32)
    hsv[:, 0], hsv[:, 1], hsv[:, 2] = hue, cfg.saturation, cfg.value
    row = hsv_to_rgb_u8(hsv)                                       # (W,3) uint8
    return np.broadcast_to(row, (cfg.height, cfg.width, 3)).copy() # (H,W,3)
```

New exposed controls: `saturation`, `value`, `hue_cycles` (how many full rainbows across
the width), `direction` (±1), and gradient **axis** (X or Y). Default values reproduce the
original (`sat 0.88`, `val 0.9`, 1 cycle, X axis).

### 4.2 Optional tracking / scanning lines
Bright lines that sweep across the frame — used to check projector latency, tearing, edge
alignment, and mapping seams.

Independent **horizontal** and **vertical** toggles, each with:
- `count` — number of evenly spaced lines on screen at once
- `thickness` (px), `color` (RGB, default white), `opacity`
- `speed` — sweeps per loop; making it an **integer** keeps the whole video seamless
- `direction` (±1)
- `style` — solid | soft (anti-aliased/gaussian falloff)

Position of a moving line at frame `f`: `pos = fract(f * speed / N + offset) * extent`.
Because `speed` is an integer number of sweeps per `N` frames, line motion loops perfectly
in lockstep with the colour cycle. Implementation is a vectorized additive/alpha composite
over the base frame — no text, no fonts.

### 4.3 Optional number grid
Overlay a grid that labels regions — invaluable for calling out "the artifact is in cell
D7" during projection alignment.

Controls:
- `rows`, `cols`
- `line_color`, `line_thickness`, `line_opacity` (the grid lines themselves; optional)
- `label_mode` — `sequential` (0,1,2…), `row-col` (`R1C1`), `coords` (pixel origin of
  cell), or `alpha-num` (`A1`, `B2`…)
- `font_size` (px or auto-fit to cell), `font_color`, `label_anchor` (center / corner)
- `show_cell_index` toggle, optional per-cell background for legibility

Rendered once with Pillow onto a transparent RGBA layer (grid + text are **static** unless
labels animate), cached, and alpha-composited onto every frame — so the font/text cost is
paid once, not per frame.

### 4.4 Export / video formats
A **preset picker** plus advanced overrides. Presets map to `(container, codec, pixel
format, quality)`:

| Preset | Container | Codec | Pixel fmt | Quality knob |
|---|---|---|---|---|
| H.264 MP4 (web/default) | mp4 | libx264 | yuv420p | CRF |
| H.265 MP4 (smaller) | mp4 | libx265 | yuv420p | CRF |
| VP9 WebM | webm | libvpx-vp9 | yuv420p | CRF |
| AV1 MP4/MKV | mp4/mkv | libaom-av1/svt-av1 | yuv420p | CRF |
| ProRes MOV (edit) | mov | prores_ks | yuv422p10 | profile |
| Lossless FFV1 MKV | mkv | ffv1 | rgb/yuv | lossless |
| Image sequence | — | PNG/TIFF | rgb(a) | lossless |

Rules carried over/added:
- **Even-dimension enforcement** for `yuv420p` codecs (warn + offer auto-round).
- Fractional fps via `fps_base` equivalent (PyAV `Fraction` time base) — e.g. 23.976.
- `duration` and `fps` → `N = round(duration * fps)`, exactly one loop (like the original).
- Colour written as pure sRGB 8-bit (or 10-bit for ProRes); **no view-transform re-grade**
  — fixes the latent "Medium High Contrast" issue.

### 4.5 Config presets (app-level)
All settings live in one `@dataclass` tree serializable to JSON. Save/Load lets users keep
a "projector A alignment" preset and re-render on demand. This same JSON is what the CLI
consumes.

---

## 5. UI/UX outline (PySide6)

- **Left panel — controls**, grouped: *Output* (size, fps, duration, format preset,
  path), *Colour Loop* (sat/val/cycles/axis/direction), *Tracking Lines* (H/V groups),
  *Number Grid*, *Presets* (save/load JSON).
- **Center — live preview**: renders a single frame at the current scrub position,
  downscaled to fit and throttled (debounced) so dragging sliders stays responsive. A
  **scrub slider** moves through `0…N-1` so users can eyeball seamlessness (compare first
  and last frame).
- **Bottom — Export bar**: format summary, `Export` button, progress bar, `Cancel`.
- Rendering/encoding runs in a `QThread` (`render_worker.py`) emitting `progress(int)` and
  `finished(path)` / `error(msg)`; the UI never blocks.
- Inline validation (even-dimension warning, unwritable path, missing codec) shown before
  export starts.

---

## 6. CLI / headless mode

Same core, no Qt. Enables batch renders, CI smoke tests, and scripting.

```bash
projgen --preset h264_mp4 --width 1920 --height 1080 --fps 25 --duration 10 \
        --hlines 3 --vlines 0 --grid 8x8 --grid-labels alpha-num \
        --out ./colour_loop.mp4
projgen --config projectorA.json --out ./out.mp4     # render from a saved preset
```

`__main__.py`: launch GUI when invoked with no arguments, CLI when arguments are present.

---

## 7. Packaging to `.exe`

1. **Freeze env** in `pyproject.toml`: `numpy`, `pillow`, `av`, `pyside6` (+ `imageio-ffmpeg`
   as the fallback binary source).
2. **Bundle the FFmpeg binary** so the app is self-contained even if PyAV lacks a codec:
   ship `ffmpeg.exe` (from `imageio-ffmpeg.get_ffmpeg_exe()` or an LGPL/GPL build) as
   PyInstaller data; resolve its path at runtime via `sys._MEIPASS`.
3. **Bundle the font** (`assets/fonts/DejaVuSansMono.ttf`) as data.
4. **PyInstaller** (`build/projgen.spec`): `--onedir --windowed`, `datas` for ffmpeg + font,
   `hiddenimports` for PySide6/av plugins, exclude unused Qt modules to trim size.
5. **Smoke test the exe**: run the CLI path headless inside the frozen build in CI.
6. **(Optional) Inno Setup** installer + Start-menu shortcut; note code-signing to avoid
   SmartScreen warnings (out of scope for v1).

Runtime asset resolution helper:
```python
def asset_path(*parts):
    base = getattr(sys, "_MEIPASS", os.path.dirname(__file__))
    return os.path.join(base, "assets", *parts)
```

---

## 8. Testing

- **Seamlessness test**: assert wrap frame `N` (computed at `phase=1.0`) equals frame `0`
  for the colour loop and for integer-speed tracking lines.
- **Golden-frame hashes**: hash a few frames at fixed configs; guards against regressions.
- **HSV→RGB** parity against `colorsys`/`matplotlib` reference on a sample of hues.
- **Even-dimension guard** and fractional-fps math unit tests.
- **Encoder round-trip**: encode a short clip per preset, re-open with PyAV, assert frame
  count, resolution, and pixel format.
- **CLI smoke test** wired into CI and re-run against the frozen exe.

---

## 9. Milestones

1. **M1 — Core parity (no UI):** `config`, `color`, `pattern` (colour loop), `loop`,
   `render`, `encoder` with H.264 MP4. CLI renders a clip matching the current script's
   look. Seamlessness + golden tests green.
2. **M2 — Formats:** all export presets, even-dim + fractional-fps handling, image
   sequence output.
3. **M3 — Overlays:** tracking lines (H/V) and number grid, with seamless line motion.
4. **M4 — GUI:** PySide6 window, live preview + scrub, threaded export with progress/cancel,
   preset save/load.
5. **M5 — Packaging:** PyInstaller onedir build, bundled ffmpeg + font, CI exe smoke test,
   optional installer.

## 10. Risks / decisions to confirm
- **PyAV vs bundled-ffmpeg-pipe**: PyAV is cleaner but codec availability depends on the
  wheel's FFmpeg build; the bundled-binary fallback de-risks this. (Recommend shipping both.)
- **GUI framework size**: PySide6 gives the best preview but the largest exe (~80–120 MB
  onedir). If a small binary matters more than preview polish, swap to `customtkinter`.
- **Licensing**: shipping a GPL FFmpeg build makes the bundle GPL; an LGPL build (no x264/x265
  linked in) needs those as separate binaries. Decide the FFmpeg build before v1 release.
```
