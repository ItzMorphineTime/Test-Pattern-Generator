/**
 * Generator settings: defaults, limits, validation, shareable URL parameters,
 * and derived values (the summary line and download file names).
 */

import { framesPerSecond, regionSplit, totalFrames } from './timing.js';

export const DEFAULTS = Object.freeze({
  width: 1920,
  height: 1080,
  fps: 30,
  duration: 10, // seconds
  regionHeight: 0.25, // fraction of the canvas height
  regionGap: 0.04, // fraction of the canvas width
  textSize: 0.12, // fraction of the canvas height
  startNumber: 0, // number shown on the first frame and second
});

/** [min, max] per setting; values outside the range are clamped. */
export const LIMITS = Object.freeze({
  width: [16, 8192],
  height: [16, 8192],
  fps: [1, 240],
  duration: [0.1, 3600],
  regionHeight: [0.05, 0.6],
  regionGap: [0, 0.2],
  textSize: [0.02, 0.4],
  startNumber: [0, 1],
});

const INTEGERS = new Set(['width', 'height', 'startNumber']);
const PERCENTAGES = new Set(['regionHeight', 'regionGap', 'textSize']);
const QUERY_KEYS = {
  width: 'w',
  height: 'h',
  fps: 'fps',
  duration: 'dur',
  regionHeight: 'rh',
  regionGap: 'gap',
  textSize: 'text',
  startNumber: 'start',
};

/** A complete, in-range settings object; missing or invalid values use defaults. */
export function normalise(raw = {}) {
  const out = {};
  for (const [key, fallback] of Object.entries(DEFAULTS)) {
    let value = Number(raw[key]);
    if (raw[key] === undefined || raw[key] === '' || !Number.isFinite(value)) value = fallback;
    if (INTEGERS.has(key)) value = Math.round(value);
    const [lo, hi] = LIMITS[key];
    out[key] = Math.min(hi, Math.max(lo, value));
  }
  return out;
}

/** Settings from a URL query string such as "?w=3840&h=2160&fps=60". */
export function fromQuery(search) {
  const params = new URLSearchParams(search);
  const raw = {};
  for (const [key, name] of Object.entries(QUERY_KEYS)) {
    if (!params.has(name)) continue;
    const value = Number(params.get(name));
    raw[key] = PERCENTAGES.has(key) ? value / 100 : value;
  }
  return normalise(raw);
}

/** A query string holding only the settings that differ from the defaults. */
export function toQuery(settings) {
  const params = new URLSearchParams();
  for (const [key, name] of Object.entries(QUERY_KEYS)) {
    if (settings[key] === DEFAULTS[key]) continue;
    const value = PERCENTAGES.has(key) ? settings[key] * 100 : settings[key];
    params.set(name, trim(value));
  }
  const query = params.toString();
  return query ? `?${query}` : '';
}

/** Blocking errors, plus notes about formats that won't be available. */
export function validate(settings) {
  const errors = [];
  const notes = [];
  if (framesPerSecond(settings.fps) < 3) {
    errors.push('Frame rate must be at least 3 fps so each colour region gets a frame.');
  }
  if (settings.width % 2 || settings.height % 2) {
    notes.push('MP4 video needs an even width and height; PNG frames work at any size.');
  }
  return { errors, notes };
}

export function summary(settings) {
  const frames = totalFrames(settings.duration, settings.fps);
  const [red, green, blue] = regionSplit(settings.fps);
  return `${frames.toLocaleString('en-US')} frames · ${trim(settings.duration)} s · ` +
    `R/G/B shown ${red}/${green}/${blue} frames each second`;
}

/** Download name stem, e.g. "black_burst_1920x1080_30fps_10s". */
export function fileBase(settings) {
  return `black_burst_${settings.width}x${settings.height}_` +
    `${trim(settings.fps)}fps_${trim(settings.duration)}s`;
}

/** Shortest decimal form: 10 -> "10", 29.970000001 -> "29.97". */
function trim(value) {
  return String(Number(value.toFixed(3)));
}
