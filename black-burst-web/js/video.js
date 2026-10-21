/**
 * MP4 (H.264) export with WebCodecs.
 *
 * Each frame is rendered and handed to the encoder with an exact timestamp.
 * Nothing is captured in real time, so no frames are dropped or doubled,
 * which matters for a sync test.
 */

import { Mp4Writer } from './mp4.js';
import { BurstRenderer, createCanvas, loadAssets } from './renderer.js';
import { fpsFraction, framesPerSecond } from './timing.js';
import { makeYielder } from './util.js';

// H.264 levels: [level_idc, max macroblocks per second, max frame size in macroblocks].
const LEVELS = [
  [30, 40500, 1620], [31, 108000, 3600], [32, 216000, 5120],
  [40, 245760, 8192], [42, 522240, 8704],
  [50, 589824, 22080], [51, 983040, 36864], [52, 2073600, 36864],
  [60, 4177920, 139264], [61, 8355840, 139264], [62, 16711680, 139264],
];
const PROFILES = ['6400', '4D00', '42E0']; // High, Main, Constrained Baseline

/** Target bits per pixel per frame for each quality setting. */
export const QUALITY = { standard: 0.08, high: 0.15, maximum: 0.3 };

/** H.264 codec strings to try, best profile first, at the lowest level that fits. */
export function h264Codecs(width, height, fps) {
  const macroblocks = Math.ceil(width / 16) * Math.ceil(height / 16);
  const level = LEVELS.find(([, maxRate, maxSize]) => macroblocks <= maxSize && macroblocks * fps <= maxRate);
  if (!level) return [];
  const hex = level[0].toString(16).toUpperCase().padStart(2, '0');
  return PROFILES.map((profile) => `avc1.${profile}${hex}`);
}

export function encoderConfig(codec, settings, quality = 'standard') {
  const bitsPerPixel = QUALITY[quality] ?? QUALITY.standard;
  const bitrate = settings.width * settings.height * settings.fps * bitsPerPixel;
  return {
    codec,
    width: settings.width,
    height: settings.height,
    bitrate: Math.round(Math.min(150e6, Math.max(1e6, bitrate))),
    framerate: settings.fps,
    latencyMode: 'quality',
    avc: { format: 'avc' }, // length-prefixed NAL units, as MP4 stores them
  };
}

/** The first H.264 configuration this browser can encode, or the reason none works. */
export async function findEncoderConfig(settings, quality) {
  if (typeof VideoEncoder === 'undefined') {
    return { config: null, reason: 'This browser can’t encode video. Use a current Chrome, Edge or Safari, or download PNG frames instead.' };
  }
  if (settings.width % 2 || settings.height % 2) {
    return { config: null, reason: 'MP4 video needs an even width and height.' };
  }
  for (const codec of h264Codecs(settings.width, settings.height, settings.fps)) {
    const config = encoderConfig(codec, settings, quality);
    try {
      if ((await VideoEncoder.isConfigSupported(config)).supported) return { config, reason: null };
    } catch {
      // Try the next profile.
    }
  }
  return {
    config: null,
    reason: `This browser can’t encode H.264 at ${settings.width}×${settings.height}, ${settings.fps} fps.`,
  };
}

/**
 * Encode the whole test to an MP4 Blob. `onProgress(done, total)` reports each
 * frame; aborting `signal` stops the export with an AbortError.
 */
export async function encodeMp4(settings, { quality = 'standard', onProgress, signal } = {}) {
  const { config, reason } = await findEncoderConfig(settings, quality);
  if (!config) throw new Error(reason);

  await loadAssets();
  const { canvas, ctx } = createCanvas(settings.width, settings.height);
  const renderer = new BurstRenderer(settings, ctx);
  const { num, den } = fpsFraction(settings.fps);
  const frameMicros = (den * 1e6) / num;
  const writer = new Mp4Writer(settings);
  let failure = null;

  const encoder = new VideoEncoder({
    output(chunk, metadata) {
      try {
        const decoderConfig = metadata?.decoderConfig;
        if (decoderConfig?.description) writer.setDescription(decoderConfig.description);
        if (decoderConfig?.colorSpace) writer.setColorSpace(decoderConfig.colorSpace);
        const data = new Uint8Array(chunk.byteLength);
        chunk.copyTo(data);
        writer.addSample(data, chunk.type === 'key', Math.round(chunk.timestamp / frameMicros));
      } catch (error) {
        failure ??= error;
      }
    },
    error(error) {
      failure ??= error;
    },
  });

  try {
    encoder.configure(config);
    const keyInterval = framesPerSecond(settings.fps); // a key frame every second
    const yieldToBrowser = makeYielder();
    for (let i = 0; i < renderer.total; i++) {
      signal?.throwIfAborted();
      if (failure) throw failure;
      renderer.draw(ctx, i);
      const frame = new VideoFrame(canvas, {
        timestamp: Math.round(i * frameMicros),
        duration: Math.round(frameMicros),
      });
      encoder.encode(frame, { keyFrame: i % keyInterval === 0 });
      frame.close();
      await drain(encoder, 4);
      onProgress?.(i + 1, renderer.total);
      await yieldToBrowser();
    }
    await encoder.flush();
    if (failure) throw failure;
  } finally {
    if (encoder.state !== 'closed') encoder.close();
  }

  if (writer.sampleCount !== renderer.total) {
    throw new Error(`The encoder returned ${writer.sampleCount} of ${renderer.total} frames. Please try again.`);
  }
  return writer.finish();
}

/** Wait until the encoder's input queue is short, so frames don't pile up in memory. */
async function drain(encoder, maxQueued) {
  while (encoder.encodeQueueSize > maxQueued) {
    await new Promise((resolve) => {
      // Older WebCodecs builds have no 'dequeue' event, so also poll.
      const done = () => {
        clearTimeout(timer);
        encoder.removeEventListener?.('dequeue', done);
        resolve();
      };
      const timer = setTimeout(done, 20);
      encoder.addEventListener?.('dequeue', done);
    });
  }
}
