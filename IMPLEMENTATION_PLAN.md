# Projection Test-Pattern Generator — Implementation Plan

Standalone desktop app (`.exe`) that generates seamless, loopable test patterns for
projection mapping, exports them to any common video format, and overlays optional
horizontal/vertical tracking lines and number grids. A second tool generates a black &
burst sync test video (M7).

---

## 0. Build status (living)

| Milestone | Status |
|---|---|
| M1 — Core render parity (config, colour loop, seamless loop) | ✅ done |
| M2 — Export formats (7 presets via PyAV) | ✅ done |
| M3 — Overlays (tracking lines + number grid) | ✅ done |
| M4 — PySide6 GUI (live preview, threaded export, presets) | ✅ done |
| M5 — Packaging (single-file PyInstaller exe) + README | ✅ done |
| M6 — Post-review refinements (see below) | ✅ done |
| M7 — Black & Burst sync test tool (second tab + `--burst` CLI) | ✅ done |
| M8 — Black & Burst web app (`black-burst-web/`, GitHub Pages) | ✅ done |
| M9 — Morph brand applied to both apps | ✅ done |

**M6 refinements (from first hands-on review):**
- **Resizable control panel** — the left sidebar is now a splitter pane (min width, not
  fixed) and the panel reserves right-hand margin so the scrollbar no longer overlaps fields.
- **Line motion gated on the loop toggle** — *Loop seamlessly* **on**: the lines ping-pong
  and the clip is a complete out-and-back, with the final rendered frame landing back on the
  start position (sweeps mapped across the `N-1` frame span). *Off*: the lines scroll
  continuously in one direction (wrapping at the edges) at the exact `speed` and do not
  return. `speed` is a float; in loop mode it rounds to whole there-and-back sweeps.
- **Spin-box step buttons** styled with explicit geometry so they sit flush at the field's
  right edge and stay clickable (previously overlapped the text).
- **Windows small/details icon** — icon `.ico` small sizes are stored as BMP/DIB (not PNG),
  which Windows Explorer's small and details views require, so they no longer fall back to
  the default icon.
- **Image / logo overlay** — a custom picture composited onto the pattern, with centre
  position (%), scale (% of canvas width), opacity, a grid-layer control (behind or on top
  of the number grid), and optional effects: grow & shrink (pulse), fade, spin, and bounce
  (screensaver-style diagonal drift that reflects off the edges, starting from the
  configured position; x and y run different whole cycle counts so the path criss-crosses).
  Effects run whole cycles across the `N-1` frame span, so the final frame returns to the
  start (same convention as the lines). Exposed in the GUI group *Image / Logo* and via
  `--image*` CLI flags; missing files fail validation.
- **Qt enum flattening fix** — PySide6's QVariant flattens str-mixin enum members to plain
  strings when stored as combo-box data, which silently broke every enum-driven setting set
  from the GUI (image effects rendered static, the colour-loop axis stuck on vertical, soft
  line style fell back to solid, grid label modes stuck on alpha-numeric). Fixed centrally:
  `_set` coerces values back to the field's enum type, and the render core compares enums
  with `==` so plain-string configs also work. Locked in by a string-tolerance test.
- **Faithful preview scaling** — pixel-based sizes (fixed grid font size, grid/tracking
  line thicknesses) are scaled by the preview's downscale factor, so the preview matches
  the final render proportionally.
- **App icon source** — regenerated from `src/JLoe.png` (replaces the earlier artwork).
- **Cross-platform builds** — one spec builds Windows (`.exe`) and macOS (single-file
  binary **and** `.app` bundle) with the right icon per platform (`.ico` / `.icns`).
  Built via `packaging/build.ps1` (Windows) or `packaging/build_mac.sh` (macOS).
- **App icon** — bundled at `src/projgen/assets/` and embedded into the executable and used
  for the window/taskbar. (Windows Explorer may cache the old exe icon after a rebuild.)

**M7 — Black & Burst sync test (`core/burst.py`, `ui/burst_page.py`):**
- **Pattern** — every frame shows `FRAME nnnn` / `SECOND nn`; the background is black on
  even seconds and white on odd ones (ink inverts to stay readable); three equal regions,
  evenly spaced across the top, show red → green → blue, one at a time, each for a third
  of the second, so the colour cycle stays in step with the flip.
- **Timing rules** — a "second" is `round(fps)` frames, like non-drop-frame timecode, so
  29.97 fps counts 30. The region for frame `f` within a second of `n` frames is
  `3f // n`, which spreads uneven rates as evenly as possible (25 fps → 9/8/8). Below
  3 fps a colour would never show, so validation rejects it.
- **Counters** — size is a fraction of canvas height but auto-shrinks to fit the width
  and the space under the regions; each line is left-anchored at the position that centres
  its widest possible label, so text never shifts between frames. Numbering starts at 0
  (timecode style) or 1.
- **Export** — any format preset. *Also export every frame as a PNG* tees frames into a
  `<name>_frames/` folder during the same encode pass, named by the burned-in frame number;
  it's disabled for the PNG-sequence format, which already does that. PNG frames are
  pixel-exact; lossy 4:2:0 formats shift pure colours by a level or two.
- **Architecture** — the encoder now takes any frame stream (`encode_frames`); the GUI's
  export bar, output-settings group, page layout, and render worker were extracted into
  shared pieces so both tabs behave identically. `BurstConfig` is nested in
  `ProjectConfig`, so presets save both tabs; Load/Save Preset moved to the tab bar
  (and, in M9, into the branded header).

**M8 — Black & Burst web app (`black-burst-web/`):**
- **Standalone and static** — plain HTML, CSS and ES modules; no build step, no
  dependencies, nothing uploaded. Serves from GitHub Pages via
  `.github/workflows/pages.yml` (unit tests gate each deployment), or from any static host.
- **Same output as the desktop tool** — `timing.js` and `layout.js` mirror `burst.py`,
  down to Python's round-half-to-even, and are unit-tested against the desktop app's
  values (for example the 1920×1080 region boxes).
- **Frame-accurate MP4** — WebCodecs H.264 with explicit timestamps (no real-time
  capture, so no dropped or doubled frames), choosing the lowest H.264 level that fits
  and the best profile the browser supports. A minimal fast-start MP4 writer
  (`mp4.js`) stores exact NTSC timing (30000/1001) and maps reordered (B-frame) streams
  to display order with signed composition offsets. Cross-checked by muxing libx264
  streams with and without B-frames and decoding them with FFmpeg.
- **PNG frames** — a stored ZIP (`zip.js`), or written straight into a folder with the
  File System Access API where available; named by burned-in frame number.
- **Verified end to end** — MP4s and ZIPs exported in the browser were decoded with
  FFmpeg / Python: exact frame counts and rates, and every frame's background and
  region match the desktop timing rules (30 fps and the uneven 25 fps split).

**M9 — Morph brand (Morph Brand System V2, `Morph Brand Assets/`):**
- **Colour roles** — Morph Black and Studio White carry structure; Signal Red carries
  motion (progress, focus rings, the active tab, the played part of the scrubber,
  accent rules); Pivot Gold marks the single decisive action per page (Export / Download
  MP4), with Morph Black text (10.89:1). States the brand doesn't define (hover, borders,
  secondary text in dark mode) use tints of brand colours, not new hues.
- **Desktop** — dark mode, as the brand directs for control surfaces; a header with the
  Morph wordmark at its minimum width and 24 px clear space; the app icon is
  `morph-app-icon-dark`, rendered from the SVG into `.ico` (BMP small sizes) and
  `.icns`; Montserrat registered with Qt; chevron images for stylesheet arrows.
- **Web** — the brand's own CSS token names, light mode by default and dark mode when the
  system prefers it; the wordmark variant for each mode; the Morph favicon and app icon;
  red small text only where it meets contrast (dark mode uses white eyebrows and red rules).
- **Typography** — Montserrat (OFL, bundled from local copies) for both interfaces and
  for burned-in text in every generator. Its figures are proportional, so counters draw
  digits in fixed-width cells; text never shifts as numbers change.
- The pattern colours themselves (pure R/G/B, black, white, the hue loop) are test
  signals and stay unbranded. Only the logo files the apps use are committed; the full
  brand folder (including its PDFs) stays out of the repository.

**Decisions settled during implementation (differ from the first-pass plan):**
- **Single-file executable** (`--onefile`) per request, not onedir. Trade-off: slightly
  slower first launch (self-extract) for one portable `.exe`.
- **AV1 uses `libsvtav1`** (fast, present in the PyAV FFmpeg build); `libaom-av1` is not
  compiled in.
- **No vendored TTF.** Pillow 11's scalable `ImageFont.load_default(size=)` supplies the
  grid font, so there is no `assets/fonts/` folder and no font-licensing question. A system
  font family can still be passed as an override.
- **FFmpeg is not a separate bundled binary** — PyAV already ships the FFmpeg shared
  libraries, and PyInstaller collects them, so codecs work in the frozen app out of the box.
- Package lives under `src/projgen/`; packaging assets under `packaging/`.

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
| AV1 MP4 | mp4 | libsvtav1 | yuv420p | CRF |
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

1. ✅ **M1 — Core parity (no UI):** `config`, `color`, `pattern` (colour loop), `loop`,
   `render`. CLI renders a clip matching the current script's look. Seamlessness tests green.
2. ✅ **M2 — Formats:** `encoder` with all seven export presets, even-dim + fractional/NTSC
   fps handling, image-sequence output, CRF/bitrate overrides.
3. ✅ **M3 — Overlays:** tracking lines (H/V) and number grid, with seamless line motion.
4. ✅ **M4 — GUI:** PySide6 window, live preview + scrub, threaded export with
   progress/cancel, preset save/load.
5. ✅ **M5 — Packaging:** single-file PyInstaller exe (FFmpeg libs collected from PyAV);
   README with build instructions. *Optional follow-ups: code-signing, Inno Setup installer,
   GitHub Actions CI to build + smoke-test the exe.*

## 10. Risks / decisions to confirm
- **PyAV vs bundled-ffmpeg-pipe**: PyAV is cleaner but codec availability depends on the
  wheel's FFmpeg build; the bundled-binary fallback de-risks this. (Recommend shipping both.)
- **GUI framework size**: PySide6 gives the best preview but the largest exe (~80–120 MB
  onedir). If a small binary matters more than preview polish, swap to `customtkinter`.
- **Licensing**: shipping a GPL FFmpeg build makes the bundle GPL; an LGPL build (no x264/x265
  linked in) needs those as separate binaries. Decide the FFmpeg build before v1 release.
```
