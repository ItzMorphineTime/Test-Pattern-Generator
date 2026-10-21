/**
 * Frame timing for the black & burst sync test.
 *
 * Mirrors the desktop app (projgen/core/burst.py) so both tools produce the
 * same sequence: a "second" is round(fps) whole frames, like non-drop-frame
 * timecode (29.97 fps counts 30), and each colour region is shown for a third
 * of the second, with spare frames going to the earlier colours (25 fps -> 9/8/8).
 */

/** Python-style round(): exact halves go to the nearest even integer. */
export function roundHalfEven(x) {
  const r = Math.round(x);
  return Math.abs(x % 1) === 0.5 && r % 2 !== 0 ? r - 1 : r;
}

/** Whole frames counted as one second. */
export function framesPerSecond(fps) {
  return Math.max(1, roundHalfEven(fps));
}

export function totalFrames(duration, fps) {
  return Math.max(1, roundHalfEven(duration * fps));
}

/** Where frame `index` falls: its second, the visible region, and the background. */
export function frameAt(index, fps) {
  const n = framesPerSecond(fps);
  const second = Math.floor(index / n);
  const within = index - second * n;
  return {
    index,
    second,
    frameInSecond: within,
    region: Math.min(2, Math.floor((within * 3) / n)), // 0 red, 1 green, 2 blue
    white: second % 2 === 1,
  };
}

/** Frames each colour region is shown for within one second. */
export function regionSplit(fps) {
  const n = framesPerSecond(fps);
  const counts = [0, 0, 0];
  for (let within = 0; within < n; within++) {
    counts[Math.min(2, Math.floor((within * 3) / n))] += 1;
  }
  return counts;
}

/** Zero-padding width for numbered frame files. */
export function frameFilePad(total, start = 0) {
  return Math.max(4, String(total + start).length);
}

const NTSC = [
  [23.976, 24000, 1001],
  [29.97, 30000, 1001],
  [59.94, 60000, 1001],
];

/** The frame rate as an exact fraction {num, den}, snapping to NTSC rates. */
export function fpsFraction(fps) {
  for (const [nominal, num, den] of NTSC) {
    if (Math.abs(fps - nominal) < 0.01) return { num, den };
  }
  if (Math.abs(fps - Math.round(fps)) < 1e-6) return { num: Math.round(fps), den: 1 };
  return limitDenominator(fps, 100000);
}

/** Closest fraction with a denominator up to `maxDen` (continued fractions). */
function limitDenominator(x, maxDen) {
  let h0 = 0, k0 = 1, h1 = 1, k1 = 0;
  let value = x;
  for (let i = 0; i < 64; i++) {
    const a = Math.floor(value);
    const h2 = a * h1 + h0;
    const k2 = a * k1 + k0;
    if (k2 > maxDen) break;
    [h0, k0, h1, k1] = [h1, k1, h2, k2];
    const rest = value - a;
    if (rest < 1e-9) break;
    value = 1 / rest;
  }
  return { num: h1, den: k1 };
}
