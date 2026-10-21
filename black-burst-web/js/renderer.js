/**
 * Draws black & burst frames onto a 2D canvas.
 */

import {
  counterLabels,
  counterLayout,
  counterPads,
  markBox,
  markVariant,
  REGION_COLOURS,
  regionBoxes,
  relativeLuminance,
} from './layout.js';
import { frameAt, totalFrames } from './timing.js';

// Montserrat is the Morph brand typeface (bundled, see css/style.css);
// system fonts stand in if it can't load.
const FONT_FAMILY = 'Montserrat, "Segoe UI", "Helvetica Neue", Helvetica, Arial, sans-serif';
const FONT_WEIGHT = 600;
const MONOGRAM_URLS = {
  dark: new URL('../assets/brand/morph-monogram-dark@2x.png', import.meta.url), // white M
  light: new URL('../assets/brand/morph-monogram-light@2x.png', import.meta.url), // black M
};

const fontFor = (size) => `${FONT_WEIGHT} ${size}px ${FONT_FAMILY}`;

let monograms = null; // { dark, light } decoded images

/**
 * Load the brand font and both Morph monograms before rendering, so every
 * frame is laid out in Montserrat and carries the mark. A missing font falls
 * back to system fonts; a missing monogram is an error, since every output
 * must carry the mark.
 */
export async function loadAssets() {
  await Promise.all([loadFont(), loadMonograms()]);
}

async function loadFont() {
  if (typeof document === 'undefined' || !document.fonts) return;
  try {
    await document.fonts.load(fontFor(100), 'FRAME SECOND 0123456789');
  } catch {
    // Fall back to the system fonts in FONT_FAMILY.
  }
}

async function loadMonograms() {
  if (monograms) return;
  const loaded = await Promise.all(Object.entries(MONOGRAM_URLS).map(async ([variant, url]) => {
    const image = new Image();
    image.src = url.href;
    try {
      await image.decode();
    } catch {
      throw new Error('Couldn’t load the Morph monogram that every frame carries. Reload the page to try again.');
    }
    return [variant, image];
  }));
  monograms = Object.fromEntries(loaded);
}

/** `image` scaled to `width` x `height`, halving first for a smooth result. */
function scaled(image, width, height) {
  let source = image;
  let w = image.naturalWidth;
  let h = image.naturalHeight;
  while (w / 2 >= width && h / 2 >= height) {
    w = Math.round(w / 2);
    h = Math.round(h / 2);
    source = drawScaled(source, w, h);
  }
  return drawScaled(source, width, height);
}

function drawScaled(source, width, height) {
  const canvas = document.createElement('canvas');
  canvas.width = width;
  canvas.height = height;
  const ctx = canvas.getContext('2d');
  ctx.imageSmoothingEnabled = true;
  ctx.imageSmoothingQuality = 'high';
  ctx.drawImage(source, 0, 0, width, height);
  return canvas;
}

/** A detached canvas and its opaque 2D context. */
export function createCanvas(width, height) {
  const canvas = document.createElement('canvas');
  canvas.width = width;
  canvas.height = height;
  return { canvas, ctx: canvas.getContext('2d', { alpha: false }) };
}

export class BurstRenderer {
  /**
   * `ctx` measures the counter text; frames can be drawn to any same-sized
   * context. Call `loadAssets()` first.
   */
  constructor(settings, ctx) {
    if (!monograms) throw new Error('Load the brand assets (loadAssets) before rendering.');
    this.settings = settings;
    this.width = settings.width;
    this.height = settings.height;
    this.total = totalFrames(settings.duration, settings.fps);
    this.boxes = regionBoxes(settings.width, settings.height, settings.regionHeight, settings.regionGap);
    this.pads = counterPads(this.total, settings.fps, settings.startNumber);
    this.mark = markBox(settings.width, settings.height);
    this.markImages = {
      dark: scaled(monograms.dark, this.mark.w, this.mark.h),
      light: scaled(monograms.light, this.mark.w, this.mark.h),
    };
    this.markVariants = new Map(); // "white:region" -> 'dark' | 'light'
    this.text = counterLayout({
      width: settings.width,
      height: settings.height,
      textSize: settings.textSize,
      boxes: this.boxes,
      pads: this.pads,
      measure: (text, size) => measure(ctx, text, size),
      bottomLimit: this.mark.y, // the counters never reach the mark
    });
    this.font = fontFor(this.text.fontSize);
  }

  /** Draw frame `index` and return its timing details. */
  draw(ctx, index) {
    const frame = frameAt(index, this.settings.fps);
    this.drawBackground(ctx, frame);

    // The Morph monogram, shown as supplied: never recoloured, stretched or faded.
    ctx.drawImage(this.markImages[this.variantFor(frame)], this.mark.x, this.mark.y);

    ctx.fillStyle = frame.white ? '#000000' : '#ffffff';
    ctx.font = this.font;
    ctx.textBaseline = 'middle';
    const start = this.settings.startNumber;
    const numbers = [frame.index + start, frame.second + start];
    this.text.lines.forEach((line, i) => {
      ctx.textAlign = 'left';
      ctx.fillText(line.prefix, line.x, line.y);
      ctx.textAlign = 'center';
      const digits = String(numbers[i]).padStart(line.pad, '0');
      for (let k = 0; k < digits.length; k++) {
        ctx.fillText(digits[k], line.x + line.prefixWidth + (k + 0.5) * this.text.digitWidth, line.y);
      }
    });
    return frame;
  }

  /** The background and the visible colour region: everything the mark sits on. */
  drawBackground(ctx, frame) {
    ctx.fillStyle = frame.white ? '#ffffff' : '#000000';
    ctx.fillRect(0, 0, this.width, this.height);
    const [left, top, right, bottom] = this.boxes[frame.region];
    ctx.fillStyle = REGION_COLOURS[frame.region];
    ctx.fillRect(left, top, right - left + 1, bottom - top + 1);
  }

  /**
   * The monogram that contrasts with the pixels behind the mark on this
   * frame. Those pixels depend only on the background and the visible region,
   * so each of the six combinations is rendered and measured once.
   */
  variantFor(frame) {
    const key = `${frame.white}:${frame.region}`;
    let variant = this.markVariants.get(key);
    if (!variant) {
      const { x, y, w, h } = this.mark;
      const { ctx } = createCanvas(w, h);
      ctx.translate(-x, -y);
      this.drawBackground(ctx, frame);
      variant = markVariant(relativeLuminance(ctx.getImageData(0, 0, w, h).data));
      this.markVariants.set(key, variant);
    }
    return variant;
  }

  /** The two counter lines as text, e.g. ["FRAME 0042", "SECOND 01"]. */
  labels(index) {
    return counterLabels(frameAt(index, this.settings.fps), this.settings.startNumber, this.pads);
  }
}

function measure(ctx, text, size) {
  ctx.font = fontFor(size);
  const metrics = ctx.measureText(text);
  return {
    width: metrics.width,
    ascent: metrics.fontBoundingBoxAscent ?? size * 0.92,
    descent: metrics.fontBoundingBoxDescent ?? size * 0.24,
  };
}
