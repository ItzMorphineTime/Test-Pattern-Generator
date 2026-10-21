/**
 * PNG frame export: a single frame, every frame bundled into a ZIP, or every
 * frame written straight into a folder (File System Access API, Chromium).
 * Files are named after their burned-in frame number.
 */

import { BurstRenderer, createCanvas, loadAssets } from './renderer.js';
import { frameFilePad, totalFrames } from './timing.js';
import { canvasToBlob, makeYielder } from './util.js';
import { MAX_ZIP_ENTRIES, ZipWriter } from './zip.js';

export function frameFileName(index, settings) {
  const pad = frameFilePad(totalFrames(settings.duration, settings.fps), settings.startNumber);
  return `frame_${String(index + settings.startNumber).padStart(pad, '0')}.png`;
}

export function canSaveToFolder() {
  return typeof window !== 'undefined' && 'showDirectoryPicker' in window;
}

export function fitsInZip(settings) {
  return totalFrames(settings.duration, settings.fps) <= MAX_ZIP_ENTRIES;
}

export async function framePng(settings, index) {
  await loadAssets();
  const { canvas, ctx } = createCanvas(settings.width, settings.height);
  new BurstRenderer(settings, ctx).draw(ctx, index);
  return canvasToBlob(canvas);
}

export async function exportFramesZip(settings, options) {
  if (!fitsInZip(settings)) {
    throw new Error('That’s more frames than a ZIP can hold (65,535). Save to a folder instead, or shorten the test.');
  }
  const zip = new ZipWriter();
  await eachFrame(settings, async (name, png) => zip.add(name, new Uint8Array(await png.arrayBuffer())), options);
  return zip.finish();
}

/** Write every frame into `folder`, a FileSystemDirectoryHandle. */
export async function saveFramesToFolder(settings, folder, options) {
  await eachFrame(settings, async (name, png) => {
    const file = await folder.getFileHandle(name, { create: true });
    const writable = await file.createWritable();
    await writable.write(png);
    await writable.close();
  }, options);
}

async function eachFrame(settings, save, { onProgress, signal } = {}) {
  await loadAssets();
  const { canvas, ctx } = createCanvas(settings.width, settings.height);
  const renderer = new BurstRenderer(settings, ctx);
  const yieldToBrowser = makeYielder();
  for (let i = 0; i < renderer.total; i++) {
    signal?.throwIfAborted();
    renderer.draw(ctx, i);
    await save(frameFileName(i, settings), await canvasToBlob(canvas));
    onProgress?.(i + 1, renderer.total);
    await yieldToBrowser();
  }
}
