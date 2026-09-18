# Projection Test-Pattern Generator — Project Write-up

*18 September 2026 · Joseph Loe*

## Purpose

A standalone desktop app that generates seamless, loopable test-pattern videos for
projection mapping: a smoothly scrolling colour loop with optional horizontal/vertical
tracking lines, labelled number grids, and a custom image/logo overlay, exported to any
common video format.

The project began as a Blender add-on (`BlenderSimpleProjectionColourLoop.py`) that
rendered a scrolling hue gradient through Blender's full 3D engine. That worked, but it
demanded a multi-gigabyte Blender install, a GPU render pipeline, and shader-node plumbing
for every new feature — all for what is fundamentally a 2D pattern. The goal of the
rewrite: a single portable `.exe` with no dependencies for end users, pixel-exact
deterministic output, a live preview, and room to grow features in plain code.

The patterns themselves serve real projection work: the colour loop reveals seams and
blending problems, tracking lines expose latency and tearing, and the number grid lets a
crew call out exact regions during alignment ("the artifact is in cell D7").

## How it was made

The decisive step was an analysis of the original add-on that concluded Blender was the
wrong engine for a 2D task. Every frame is really just pixel math, so the rewrite
generates frames directly as NumPy arrays and encodes them with FFmpeg — no 3D engine, no
GPU dependency, and overlays become ordinary functions instead of shader-node graphs.

| Layer | Technology | Why |
| --- | --- | --- |
| Frame generation | NumPy + Pillow | Vectorised HSV maths; text and image compositing |
| Video encoding | PyAV (bundled FFmpeg) | Seven format presets from H.264 to lossless FFV1, no external binaries |
| Desktop GUI | PySide6 (Qt) | Live scrubbable preview, threaded export, dark theme |
| Headless CLI | argparse | Batch renders and CI smoke tests from the same core |
| Packaging | PyInstaller (one file) | Single portable executable per platform |

It was built entirely with Claude Code in the desktop app, starting from a written
implementation plan (kept updated in the repo) and landing as 17 incremental commits. The
process each round: implement, run the 34-test suite, verify the GUI offscreen with
rendered screenshots, rebuild the frozen `.exe`, and smoke-test it — then hand it over for
real use, with reported issues driving the next round. The codebase is about 2,400 lines:
~950 in the pure render core, ~975 of GUI, ~235 of CLI, plus tests and packaging.

Two bugs were only found by measuring rather than reading: Windows Explorer showed the
default icon in small/details views because Pillow stored every icon size as PNG (small
sizes must be BMP), and PySide6 silently flattens str-based enum members to plain strings
in combo boxes — which had disabled the image effects, the colour-loop axis switch, soft
line style, and grid label modes all at once.

## How long it took to make

About 5–6 hours of hands-on session time, spread over two afternoons — measured from the
17 commit timestamps in the git history.

| Date | Session | What landed |
| --- | --- | --- |
| 21 Aug 2026 (14:03–14:22) | First build, ~20 min of commits | Implementation plan, full v1: render core, 7-format encoder, CLI, PySide6 GUI, test suite, PyInstaller packaging, README |
| 21 Aug 2026 (16:02–17:45) | Same afternoon, refinement | App icon, resizable sidebar, seamless/ping-pong line motion, macOS build spec, several `.exe` rebuilds |
| 30 Aug 2026 (15:31–16:04) | Second session, ~1½ h | New icon artwork, preview-fidelity fix, image/logo overlay with five effects incl. screensaver bounce, grid layering, Qt enum-flattening bug fix |
| 18 Sep 2026 | — | This write-up |

The striking number is the first row: the working v1 — app, formats, tests, and a
buildable single-file executable — went from empty repo to committed in under half an
hour. The remaining time went where it always goes: hands-on feedback, UX polish, platform
quirks, and rebuilds. Not counted: my own testing between sessions and a brief icon
experiment on 22 Aug.

## How long it would have taken without AI

A reasoned estimate, not a measurement: roughly 2–4 weeks of full-time solo work (80–160
hours) for a developer comfortable in Python but not already expert in every layer —
against ~6 hours actual, i.e. somewhere in the range of 15–25× faster.

The multiplier comes less from typing speed than from breadth. The project crosses four
specialist domains — vectorised imaging maths, FFmpeg/PyAV codec configuration, Qt desktop
development, and PyInstaller packaging — and each normally carries days of
documentation-reading and trial-and-error on its own (codec/container/pixel-format
matrices, Qt threading and stylesheet subcontrols, frozen-app resource paths). On top sit
the trap-door bugs: PNG-in-ICO breaking Explorer's small icons and PySide6 flattening
enums to strings are the kind of silent failures that routinely cost a lone developer a
day each to even locate.

Assumptions behind the estimate: one developer; the same scope actually shipped (not a
trimmed MVP); includes writing the 34 tests and both platform build pipelines; excludes
learning Python itself. An expert already fluent in all four domains might land nearer 1–2
weeks — still an order of magnitude slower than the assisted build.

## Current status

Working and in use on Windows: the 123 MB single-file `ProjectionTestPatternGenerator.exe`
builds clean, all 34 tests pass, and every feature below ships in the current build.

- Seamless colour loop — saturation, value, hue cycles, axis, direction; mathematically
  verified to wrap without a seam
- Tracking lines — independent horizontal/vertical groups; loop mode ping-pongs and
  returns to the start frame, free mode scrolls continuously
- Number grid — alpha-numeric, sequential, row/col, or pixel-coordinate labels, with
  styling and label pads
- Image/logo overlay — position, scale, opacity, behind/above-grid layering, and five
  modes: static, grow & shrink, fade, spin, screensaver bounce
- Export — H.264, H.265, VP9, AV1, ProRes, lossless FFV1, or PNG sequence, with a live
  scrubbable preview, threaded export, and JSON presets; GUI and headless CLI share one
  core

Known caveats: the macOS binary is not yet produced — the spec, `.icns`, and
`build_mac.sh` are committed, but PyInstaller cannot cross-compile, so it needs one run on
a Mac. The executable is unsigned (Windows SmartScreen warns on first launch), Explorer
sometimes shows a stale cached icon after rebuilds, and in loop mode line speed rounds to
whole sweeps by design. The repo also still carries a few leftover icon-experiment files
in `src/`.

## Future plans

Near-term, already scoped in the implementation plan:

- [ ] Produce the macOS build — run `bash packaging/build_mac.sh` on a Mac; outputs a
  single-file binary and a `.app` bundle
- [ ] GitHub Actions CI — build and smoke-test both platform executables on every release
- [ ] Code-signing (and notarisation on macOS) to remove the SmartScreen / Gatekeeper
  friction
- [ ] Optional Inno Setup installer with a Start-menu entry
- [ ] Repo housekeeping — clear the leftover icon experiments from `src/`

Candidate features beyond that, in rough priority order: additional calibration patterns
(checkerboard, convergence crosshatch, focus charts, grey ramps), a bundled preset library
for common venue setups, batch-rendering several presets in one run, and 10-bit output for
the formats that support it. None are committed yet — the pattern so far has been to let
real projection sessions decide what earns a place next.

Decision pending: whether the FFmpeg build shipped inside the executable is GPL-encumbered
(x264/x265) — worth settling before distributing binaries publicly.
