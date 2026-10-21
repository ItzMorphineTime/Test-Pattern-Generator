/**
 * Page controller: keeps the form, the shareable URL, the preview and the
 * download buttons in sync.
 */

import {
  canSaveToFolder,
  exportFramesZip,
  fitsInZip,
  frameFileName,
  framePng,
  saveFramesToFolder,
} from './frames.js';
import { BurstRenderer, loadFonts } from './renderer.js';
import { fileBase, fromQuery, normalise, summary, toQuery, validate } from './settings.js';
import { downloadBlob, formatBytes } from './util.js';
import { encodeMp4, findEncoderConfig } from './video.js';

const PREVIEW_MAX = 1280; // longest preview edge in canvas pixels

const $ = (id) => document.getElementById(id);

// Settings key -> [form field id, display scale]; percentages are shown x100.
const FIELDS = {
  width: ['width', 1],
  height: ['height', 1],
  fps: ['fps', 1],
  duration: ['duration', 1],
  regionHeight: ['region-height', 100],
  regionGap: ['region-gap', 100],
  textSize: ['text-size', 100],
  startNumber: ['start-number', 1],
};

const preview = $('preview');
const previewCtx = preview.getContext('2d', { alpha: false });

const state = {
  settings: fromQuery(location.search),
  renderer: null,
  frame: 0,
  playing: false,
  playStart: 0,
  playFrom: 0,
  exporting: null, // AbortController of the running export
  canVideo: false,
  videoCheck: 0,
};

// -- settings ------------------------------------------------------------
function readForm() {
  const raw = {};
  for (const [key, [id, scale]] of Object.entries(FIELDS)) {
    const value = $(id).value;
    // A field cleared mid-edit keeps its current value rather than jumping.
    raw[key] = value === '' ? state.settings[key] : Number(value) / scale;
  }
  return normalise(raw);
}

function writeForm(settings) {
  for (const [key, [id, scale]] of Object.entries(FIELDS)) {
    $(id).value = String(Number((settings[key] * scale).toFixed(3)));
  }
  const size = `${settings.width}x${settings.height}`;
  const presets = $('resolution-preset');
  presets.value = [...presets.options].some((option) => option.value === size) ? size : 'custom';
}

function applySettings(settings, { syncForm = false } = {}) {
  state.settings = settings;
  if (syncForm) writeForm(settings);
  history.replaceState(null, '', toQuery(settings) || location.pathname);
  $('summary').textContent = summary(settings);
  const { errors, notes } = validate(settings);
  $('problems').replaceChildren(...errors.map((text) => listItem(text)),
    ...notes.map((text) => listItem(text, 'note')));
  rebuildPreview();
  refreshDownloads();
}

function listItem(text, className) {
  const item = document.createElement('li');
  item.textContent = text;
  if (className) item.className = className;
  return item;
}

// -- preview ---------------------------------------------------------------
function rebuildPreview() {
  const s = state.settings;
  const scale = Math.min(1, PREVIEW_MAX / Math.max(s.width, s.height));
  const view = {
    ...s,
    width: Math.max(2, Math.round(s.width * scale)),
    height: Math.max(2, Math.round(s.height * scale)),
  };
  preview.width = view.width;
  preview.height = view.height;
  state.renderer = new BurstRenderer(view, previewCtx);
  $('scrub').max = String(state.renderer.total - 1);
  state.frame = Math.min(state.frame, state.renderer.total - 1);
  if (state.playing) restartClock();
  drawPreview();
}

function drawPreview() {
  const frame = state.renderer.draw(previewCtx, state.frame);
  const start = state.settings.startNumber;
  $('scrub').value = String(state.frame);
  $('readout').textContent = `Frame ${frame.index + start} / ${state.renderer.total - 1 + start}`;
}

function setPlaying(on) {
  if (on === state.playing) return;
  state.playing = on;
  $('play').textContent = on ? 'Pause' : 'Play';
  $('play').setAttribute('aria-pressed', String(on));
  if (on) {
    restartClock();
    requestAnimationFrame(tick);
  }
}

function restartClock() {
  state.playStart = performance.now();
  state.playFrom = state.frame;
}

function tick(now) {
  if (!state.playing) return;
  const elapsed = Math.max(0, Math.floor(((now - state.playStart) / 1000) * state.settings.fps));
  const next = (state.playFrom + elapsed) % state.renderer.total;
  if (next !== state.frame) {
    state.frame = next;
    drawPreview();
  }
  requestAnimationFrame(tick);
}

function stepFrame(delta) {
  setPlaying(false);
  const total = state.renderer.total;
  state.frame = (state.frame + delta + total) % total;
  drawPreview();
}

// -- downloads -------------------------------------------------------------
function updateButtons() {
  const busy = Boolean(state.exporting);
  const blocked = validate(state.settings).errors.length > 0;
  const zipOk = fitsInZip(state.settings);
  $('download-mp4').disabled = busy || blocked || !state.canVideo;
  $('download-zip').disabled = busy || blocked || !zipOk;
  $('download-zip').title = zipOk ? '' : 'Too many frames for one ZIP; save them to a folder instead.';
  $('save-folder').disabled = busy || blocked;
  $('download-frame').disabled = busy || blocked;
}

async function refreshDownloads() {
  updateButtons();
  const check = ++state.videoCheck;
  const { config, reason } = await findEncoderConfig(state.settings, $('quality').value);
  if (check !== state.videoCheck) return; // superseded by a newer change
  state.canVideo = Boolean(config);
  $('video-note').textContent = config
    ? `MP4 video: H.264 at about ${(config.bitrate / 1e6).toFixed(1)} Mbit/s.`
    : reason;
  updateButtons();
}

function setStatus(text, isError = false) {
  $('status').textContent = text;
  $('status').classList.toggle('error', isError);
}

async function runExport(label, job) {
  if (state.exporting) return;
  const controller = new AbortController();
  state.exporting = controller;
  $('progress').value = 0;
  $('progress-text').textContent = '';
  $('progress-row').hidden = false;
  updateButtons();
  setStatus(`${label}…`);
  try {
    const message = await job({
      signal: controller.signal,
      onProgress(done, total) {
        $('progress').max = total;
        $('progress').value = done;
        $('progress-text').textContent = `${done.toLocaleString('en-US')} / ${total.toLocaleString('en-US')}`;
      },
    });
    setStatus(message);
  } catch (error) {
    if (error?.name === 'AbortError') {
      setStatus('Cancelled.');
    } else {
      console.error(error);
      setStatus(error?.message || String(error), true);
    }
  } finally {
    state.exporting = null;
    $('progress-row').hidden = true;
    updateButtons();
  }
}

$('download-mp4').addEventListener('click', () => runExport('Encoding video', async (options) => {
  const settings = state.settings;
  const blob = await encodeMp4(settings, { ...options, quality: $('quality').value });
  const name = `${fileBase(settings)}.mp4`;
  downloadBlob(blob, name);
  return `Saved ${name} (${formatBytes(blob.size)}).`;
}));

$('download-zip').addEventListener('click', () => runExport('Rendering PNG frames', async (options) => {
  const settings = state.settings;
  const blob = await exportFramesZip(settings, options);
  const name = `${fileBase(settings)}_frames.zip`;
  downloadBlob(blob, name);
  return `Saved ${name} (${formatBytes(blob.size)}).`;
}));

$('save-folder').addEventListener('click', async () => {
  if (state.exporting) return;
  let parent;
  try {
    // Must run straight from the click, before anything else awaits.
    parent = await window.showDirectoryPicker({ id: 'black-burst-frames', mode: 'readwrite' });
  } catch (error) {
    if (error?.name !== 'AbortError') setStatus(error?.message || String(error), true);
    return;
  }
  await runExport('Saving PNG frames', async (options) => {
    const settings = state.settings;
    const name = `${fileBase(settings)}_frames`;
    const folder = await parent.getDirectoryHandle(name, { create: true });
    await saveFramesToFolder(settings, folder, options);
    return `Saved the frames to ${parent.name}/${name}.`;
  });
});

$('download-frame').addEventListener('click', () => runExport('Rendering frame', async () => {
  const settings = state.settings;
  const blob = await framePng(settings, state.frame);
  const name = `${fileBase(settings)}_${frameFileName(state.frame, settings)}`;
  downloadBlob(blob, name);
  return `Saved ${name}.`;
}));

$('cancel').addEventListener('click', () => state.exporting?.abort());
$('quality').addEventListener('change', refreshDownloads);

// -- wiring ------------------------------------------------------------------
let pendingInput = 0;
const form = $('settings');
form.addEventListener('input', (event) => {
  if (event.target.id === 'resolution-preset') return; // handled on change
  clearTimeout(pendingInput);
  pendingInput = setTimeout(() => applySettings(readForm()), 150);
});
form.addEventListener('change', (event) => {
  if (event.target.id === 'resolution-preset' && event.target.value !== 'custom') {
    const [width, height] = event.target.value.split('x');
    $('width').value = width;
    $('height').value = height;
  }
  clearTimeout(pendingInput);
  applySettings(readForm(), { syncForm: true });
});
form.addEventListener('submit', (event) => event.preventDefault());

$('play').addEventListener('click', () => setPlaying(!state.playing));
$('scrub').addEventListener('input', (event) => {
  setPlaying(false);
  state.frame = Number(event.target.value);
  drawPreview();
});

document.addEventListener('keydown', (event) => {
  if (event.target.closest?.('input, select, textarea, button')) return;
  if (event.key === ' ') setPlaying(!state.playing);
  else if (event.key === 'ArrowRight') stepFrame(1);
  else if (event.key === 'ArrowLeft') stepFrame(-1);
  else return;
  event.preventDefault();
});

$('copy-link').addEventListener('click', async () => {
  try {
    await navigator.clipboard.writeText(location.href);
    setStatus('Link copied. Anyone opening it gets these settings.');
  } catch {
    setStatus(`Copy this link: ${location.href}`);
  }
});

window.addEventListener('beforeunload', (event) => {
  if (state.exporting) event.preventDefault(); // warn before losing a running export
});

$('save-folder').hidden = !canSaveToFolder();
writeForm(state.settings);
await loadFonts(); // so the first preview is laid out in the brand font
applySettings(state.settings);
