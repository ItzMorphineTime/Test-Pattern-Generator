/**
 * Draws black & burst frames onto a 2D canvas.
 */

import { counterLabels, counterLayout, counterPads, REGION_COLOURS, regionBoxes } from './layout.js';
import { frameAt, totalFrames } from './timing.js';

// Montserrat is the Morph brand typeface (bundled, see css/style.css);
// system fonts stand in if it can't load.
const FONT_FAMILY = 'Montserrat, "Segoe UI", "Helvetica Neue", Helvetica, Arial, sans-serif';
const FONT_WEIGHT = 600;

const fontFor = (size) => `${FONT_WEIGHT} ${size}px ${FONT_FAMILY}`;

/**
 * Wait for the brand font, so text is measured and drawn in Montserrat rather
 * than a fallback that would change the layout part-way through an export.
 */
export async function loadFonts() {
  if (typeof document === 'undefined' || !document.fonts) return;
  try {
    await document.fonts.load(fontFor(100), 'FRAME SECOND 0123456789');
  } catch {
    // Fall back to the system fonts in FONT_FAMILY.
  }
}

/** A detached canvas and its opaque 2D context. */
export function createCanvas(width, height) {
  const canvas = document.createElement('canvas');
  canvas.width = width;
  canvas.height = height;
  return { canvas, ctx: canvas.getContext('2d', { alpha: false }) };
}

export class BurstRenderer {
  /** `ctx` measures the counter text; frames can be drawn to any same-sized context. */
  constructor(settings, ctx) {
    this.settings = settings;
    this.width = settings.width;
    this.height = settings.height;
    this.total = totalFrames(settings.duration, settings.fps);
    this.boxes = regionBoxes(settings.width, settings.height, settings.regionHeight, settings.regionGap);
    this.pads = counterPads(this.total, settings.fps, settings.startNumber);
    this.text = counterLayout({
      width: settings.width,
      height: settings.height,
      textSize: settings.textSize,
      boxes: this.boxes,
      pads: this.pads,
      measure: (text, size) => measure(ctx, text, size),
    });
    this.font = fontFor(this.text.fontSize);
  }

  /** Draw frame `index` and return its timing details. */
  draw(ctx, index) {
    const frame = frameAt(index, this.settings.fps);
    const [paper, ink] = frame.white ? ['#ffffff', '#000000'] : ['#000000', '#ffffff'];
    ctx.fillStyle = paper;
    ctx.fillRect(0, 0, this.width, this.height);

    const [left, top, right, bottom] = this.boxes[frame.region];
    ctx.fillStyle = REGION_COLOURS[frame.region];
    ctx.fillRect(left, top, right - left + 1, bottom - top + 1);

    ctx.fillStyle = ink;
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
