# Black & Burst — sync test generator (web)

Make a black & burst sync test video, or its individual frames, entirely in the
browser. Nothing is installed and nothing is uploaded.

**Live:** <https://itzmorphinetime.github.io/Test-Pattern-Generator/>

Each frame shows its frame and second number. The background alternates black and
white every second, and three evenly spaced regions across the top cycle red → green →
blue, each shown for a third of the second (fps / 3 frames). It is the browser
counterpart of the *Black & Burst* tab in the desktop app in this repository, and
follows the same timing rules exactly.

## Features

- **Live preview** with play/pause, a frame scrubber, and arrow-key stepping.
- **Downloads**
  - **MP4 video** (H.264), encoded frame by frame with WebCodecs. Every frame gets an
    exact timestamp, so none are dropped or doubled. Three quality levels.
  - **PNG frames as a ZIP**, named after their burned-in numbers (`frame_0000.png`…).
  - **PNG frames straight into a folder** (Chrome and Edge), with no size limits.
  - **The current frame** as a single PNG.
- **Settings:** resolution (with presets), frame rate (including 23.976, 29.97 and
  59.94), duration, region height and spacing, counter size, and numbering from 0
  (timecode style) or 1.
- **Shareable links:** the address bar always holds the current settings, for example
  `?w=3840&h=2160&fps=59.94`. Use **Copy link to these settings** to send a setup to
  someone else.

## Timing rules

| Rule | Detail |
|---|---|
| A second | `round(fps)` whole frames, like non-drop-frame timecode (29.97 fps counts 30) |
| Background | Black on even seconds (0, 2, …), white on odd seconds |
| Colour regions | The region for frame `f` of an `n`-frame second is `⌊3f / n⌋`; uneven rates give the spare frames to the earlier colours (25 fps → 9/8/8) |
| Counters | Digits sit in fixed-width cells, so the text never shifts as the numbers change |
| Brand mark | The Morph monogram, bottom-right at 5% of the frame width: the white M on black seconds, the black M on white ones. The counters always sit above it |

The PNG frames are pixel-exact. H.264's 4:2:0 colour conversion shifts the pure
colours by a level or two (red comes out as 253,0,0); use the PNG frames when you
need exact values.

## Browser support

| Feature | Needs | Works in |
|---|---|---|
| Preview, PNG frames (ZIP), single frame | Canvas | Any modern browser |
| MP4 video | WebCodecs H.264 encoding | Current Chrome, Edge and Safari |
| Save frames to a folder | File System Access API | Chrome and Edge |

The page checks for each capability and explains when one isn't available.

## Run it locally

ES modules need to be served over HTTP; opening `index.html` from disk won't work.
From this folder:

```bash
python -m http.server 8000
```

Then open <http://localhost:8000>.

## Tests

The pure modules (timing, layout, settings, the ZIP and MP4 writers) have unit tests
that run on Node 20 or newer, with no packages to install:

```bash
node --test
```

## Deploying to GitHub Pages

This repository deploys the folder with `.github/workflows/pages.yml` whenever
`black-burst-web/` changes on `master`, after the unit tests pass. One-time setup:
in the repository's **Settings → Pages**, set **Source** to **GitHub Actions**.
(GitHub Pages needs a public repository, or a paid plan for private ones.)

To host it as its own repository instead, copy this folder's contents to the new
repository's root and enable Pages with **Deploy from a branch** (the root folder).
There is no build step, and `.nojekyll` stops GitHub's Jekyll from processing the
files.

## How it works

| File | Role |
|---|---|
| `js/timing.js` | Frame timing, matching the desktop app (including Python-style rounding) |
| `js/layout.js` | Region boxes, counter layout, and the brand mark's position and variant (pure maths, unit-tested) |
| `js/renderer.js` | Draws frames on a canvas |
| `js/video.js` | WebCodecs H.264 encoding, with profile and level selection |
| `js/mp4.js` | A minimal fast-start MP4 writer, including reordered (B-frame) streams |
| `js/frames.js`, `js/zip.js` | PNG frames as a ZIP or into a folder |
| `js/settings.js` | Defaults, validation, and shareable URL settings |
| `js/main.js` | The page controller |

## Brand

Styled to the Morph Brand System V2: Morph Black, Studio White, Signal Red for motion
and Pivot Gold for the one decisive action, set in Montserrat. The page follows the
visitor's light or dark system setting, using the brand's tokens for each mode.

Every frame you download, as video or PNG, carries the Morph monogram in its
bottom-right corner. The renderer measures the pixels behind the mark and picks the
variant that contrasts with them, following the brand's rule: the dark-background
monogram (white M) over dark pixels, the light one (black M) over light pixels. The
choice is the mean WCAG relative luminance of those pixels, switching at 0.179, where
black and white contrast equally. The artwork is shown as supplied, never recoloured,
stretched or faded.

## Licences

The code is MIT-licensed (see `LICENSE`). Montserrat is distributed under the SIL Open
Font License (`assets/fonts/OFL.txt`). The Morph name and logos in `assets/brand/`
belong to Morph and aren't covered by the MIT licence.
