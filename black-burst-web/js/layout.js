/**
 * Layout maths for the black & burst frame (no canvas, so it is unit-testable):
 * where the three colour regions sit and how the counters are sized and placed.
 * Matches the desktop renderer.
 */

import { frameAt, roundHalfEven } from './timing.js';

export const REGION_COLOURS = ['#ff0000', '#00ff00', '#0000ff'];

const clamp = (x, lo, hi) => Math.min(hi, Math.max(lo, x));

/**
 * Three equal boxes across the top, with equal gaps around and between.
 * Each box is [left, top, right, bottom] in inclusive pixel coordinates.
 */
export function regionBoxes(width, height, regionHeight, regionGap) {
  const gap = clamp(regionGap, 0, 0.2) * width;
  const boxW = Math.max(1, (width - 4 * gap) / 3);
  const boxH = Math.max(1, Math.min(regionHeight, 0.9) * height);
  const top = Math.min(gap, Math.max(0, height - boxH));
  const boxes = [];
  for (let k = 0; k < 3; k++) {
    const x0 = gap + k * (boxW + gap);
    const left = roundHalfEven(x0);
    const upper = roundHalfEven(top);
    boxes.push([
      left,
      upper,
      Math.max(left, roundHalfEven(x0 + boxW) - 1),
      Math.max(upper, roundHalfEven(top + boxH) - 1),
    ]);
  }
  return boxes;
}

/** Zero-padding so the counters keep a constant width for the whole video. */
export function counterPads(total, fps, startNumber) {
  const last = frameAt(total - 1, fps);
  return {
    framePad: Math.max(4, String(last.index + startNumber).length),
    secondPad: Math.max(2, String(last.second + startNumber).length),
  };
}

export function counterLabels(frame, startNumber, pads) {
  return [
    `FRAME ${String(frame.index + startNumber).padStart(pads.framePad, '0')}`,
    `SECOND ${String(frame.second + startNumber).padStart(pads.secondPad, '0')}`,
  ];
}

/**
 * Size the two counter lines to fit below the regions and fix their positions.
 *
 * `measure(text, size)` returns `{width, ascent, descent}` for the font at
 * `size` px. Each line is left-anchored where its widest possible label would
 * be centred, so the text never shifts as the numbers change. Positions are
 * the vertical middle of each line.
 */
export function counterLayout({ width, height, textSize, boxes, pads, measure }) {
  const margin = Math.max(1, roundHalfEven(0.03 * height));
  const areaTop = Math.max(...boxes.map((box) => box[3])) + 1 + margin;
  const areaBottom = height - margin;
  const avail = Math.max(1, areaBottom - areaTop);
  const widestFrame = 'FRAME ' + '8'.repeat(pads.framePad);
  const widestSecond = 'SECOND ' + '8'.repeat(pads.secondPad);

  const metrics = (size) => {
    const f = measure(widestFrame, size);
    const s = measure(widestSecond, size);
    const lineH = f.ascent + f.descent;
    return { frameW: f.width, secondW: s.width, lineH, lineGap: roundHalfEven(0.25 * lineH) };
  };

  let size = Math.max(6, roundHalfEven(textSize * height));
  for (let i = 0; i < 4; i++) {
    const m = metrics(size);
    const widest = Math.max(m.frameW, m.secondW);
    const scale = Math.min(1, (0.9 * width) / Math.max(1, widest),
      (0.9 * avail) / Math.max(1, 2 * m.lineH + m.lineGap));
    if (scale >= 0.99 || size <= 6) break;
    size = Math.max(6, Math.floor(size * scale));
  }

  const m = metrics(size);
  const centreY = (areaTop + areaBottom) / 2;
  const offset = (m.lineH + m.lineGap) / 2;
  return {
    fontSize: size,
    frame: { x: (width - m.frameW) / 2, y: centreY - offset },
    second: { x: (width - m.secondW) / 2, y: centreY + offset },
  };
}
