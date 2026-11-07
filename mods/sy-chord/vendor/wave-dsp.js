// WAV decoding and single-cycle conditioning for the SY CHORD wave bank tool.
// Pure functions, no dependencies, no I/O: runs in a browser and in Node (ES module).
// Nothing here knows anything about firmware; it only turns user audio into a
// 256-sample, band-limited, phase-aligned cycle that syntakt-fw.js can write.

export const MIN_HARMONICS = 8;
export const MAX_HARMONICS = 127; // 256 samples per cycle -> Nyquist is harmonic 128
export const DEFAULT_HARMONICS = 40;
export const CYCLE_LEN = 256;

// ---- WAV decoding ------------------------------------------------------------------

const FMT_PCM = 0x0001, FMT_FLOAT = 0x0003, FMT_EXTENSIBLE = 0xfffe;

function fourcc(view, off) {
  return String.fromCharCode(view.getUint8(off), view.getUint8(off + 1), view.getUint8(off + 2), view.getUint8(off + 3));
}

/**
 * Decode a RIFF/WAVE buffer. Only the first channel is returned.
 * Supports PCM 8/16/24/32-bit integer, 32/64-bit IEEE float and WAVE_FORMAT_EXTENSIBLE.
 * @param {ArrayBuffer|Uint8Array} buffer
 * @returns {{sampleRate:number, channels:number, bitsPerSample:number, samples:Float64Array}}
 */
export function decodeWav(buffer) {
  const bytes = buffer instanceof Uint8Array ? buffer : new Uint8Array(buffer);
  const view = new DataView(bytes.buffer, bytes.byteOffset, bytes.byteLength);
  if (bytes.byteLength < 12) throw new Error("not a WAV file: shorter than a RIFF header");
  if (fourcc(view, 0) !== "RIFF") throw new Error("not a WAV file: missing RIFF header");
  if (fourcc(view, 8) !== "WAVE") throw new Error("not a WAV file: RIFF form is not WAVE");

  let fmt = null, dataOff = -1, dataLen = 0;
  let pos = 12;
  while (pos + 8 <= bytes.byteLength) {
    const id = fourcc(view, pos);
    const size = view.getUint32(pos + 4, true);
    const body = pos + 8;
    if (id === "fmt ") {
      if (size < 16 || body + 16 > bytes.byteLength) throw new Error("malformed WAV: fmt chunk is too short");
      let format = view.getUint16(body, true);
      const channels = view.getUint16(body + 2, true);
      const sampleRate = view.getUint32(body + 4, true);
      const blockAlign = view.getUint16(body + 12, true);
      const bits = view.getUint16(body + 14, true);
      if (format === FMT_EXTENSIBLE) {
        if (size < 40 || body + 26 > bytes.byteLength) {
          throw new Error("malformed WAV: WAVE_FORMAT_EXTENSIBLE without an extension block");
        }
        format = view.getUint16(body + 24, true); // first field of the sub-format GUID
      }
      fmt = { format, channels, sampleRate, blockAlign, bits };
    } else if (id === "data") {
      dataOff = body;
      dataLen = Math.min(size, bytes.byteLength - body);
    }
    pos = body + size + (size & 1); // chunks are word aligned; odd sizes carry a pad byte
  }
  if (!fmt) throw new Error("malformed WAV: no fmt chunk");
  if (dataOff < 0) throw new Error("malformed WAV: no data chunk");
  if (fmt.channels < 1) throw new Error("malformed WAV: zero channels");
  if (fmt.format !== FMT_PCM && fmt.format !== FMT_FLOAT) {
    throw new Error("unsupported WAV encoding (format 0x" + fmt.format.toString(16) +
      "): only uncompressed PCM and IEEE float are supported");
  }
  if (fmt.format === FMT_PCM && ![8, 16, 24, 32].includes(fmt.bits)) {
    throw new Error("unsupported PCM sample size: " + fmt.bits + " bits (expected 8, 16, 24 or 32)");
  }
  if (fmt.format === FMT_FLOAT && ![32, 64].includes(fmt.bits)) {
    throw new Error("unsupported float sample size: " + fmt.bits + " bits (expected 32 or 64)");
  }
  const bytesPerSample = fmt.bits >> 3;
  const stride = fmt.blockAlign > 0 ? fmt.blockAlign : bytesPerSample * fmt.channels;
  const frames = Math.floor(dataLen / stride);
  if (frames < 1) throw new Error("WAV file contains no audio frames");

  const out = new Float64Array(frames);
  for (let i = 0; i < frames; i++) {
    const o = dataOff + i * stride; // first channel only
    if (fmt.format === FMT_FLOAT) {
      out[i] = fmt.bits === 32 ? view.getFloat32(o, true) : view.getFloat64(o, true);
    } else if (fmt.bits === 8) {
      out[i] = (view.getUint8(o) - 128) / 128;
    } else if (fmt.bits === 16) {
      out[i] = view.getInt16(o, true) / 32768;
    } else if (fmt.bits === 24) {
      const v = view.getUint8(o) | (view.getUint8(o + 1) << 8) | (view.getUint8(o + 2) << 16);
      out[i] = ((v & 0x800000) ? v - 0x1000000 : v) / 8388608;
    } else {
      out[i] = view.getInt32(o, true) / 2147483648;
    }
  }
  return { sampleRate: fmt.sampleRate, channels: fmt.channels, bitsPerSample: fmt.bits, samples: out };
}

/** Build a mono 32-bit float WAV file from `samples`. Used for the "export frames" feature. */
export function encodeWavFloat32(samples, sampleRate = 48000) {
  const n = samples.length;
  const bytes = new Uint8Array(44 + n * 4);
  const view = new DataView(bytes.buffer);
  const tag = (off, s) => { for (let i = 0; i < 4; i++) view.setUint8(off + i, s.charCodeAt(i)); };
  tag(0, "RIFF"); view.setUint32(4, 36 + n * 4, true); tag(8, "WAVE");
  tag(12, "fmt "); view.setUint32(16, 16, true);
  view.setUint16(20, FMT_FLOAT, true); view.setUint16(22, 1, true);
  view.setUint32(24, sampleRate, true); view.setUint32(28, sampleRate * 4, true);
  view.setUint16(32, 4, true); view.setUint16(34, 32, true);
  tag(36, "data"); view.setUint32(40, n * 4, true);
  for (let i = 0; i < n; i++) view.setFloat32(44 + 4 * i, samples[i], true);
  return bytes;
}

// ---- single-cycle conditioning -----------------------------------------------------

/**
 * Project `samples` (treated as exactly one cycle) onto harmonics 1..H.
 * Returns cosine/sine coefficients such that
 *   f(t) = sum_n a[n]*cos(2*pi*n*t) + b[n]*sin(2*pi*n*t),  t in cycles.
 * Index 0 is unused: DC is deliberately never computed and therefore dropped.
 */
export function dftHarmonics(samples, H) {
  const N = samples.length;
  const a = new Float64Array(H + 1), b = new Float64Array(H + 1);
  for (let n = 1; n <= H; n++) {
    const w = (2 * Math.PI * n) / N;
    let sc = 0, ss = 0;
    for (let i = 0; i < N; i++) {
      const p = w * i;
      sc += samples[i] * Math.cos(p);
      ss += samples[i] * Math.sin(p);
    }
    a[n] = (2 / N) * sc;
    b[n] = (2 / N) * ss;
  }
  return { a, b };
}

/** Magnitude of each harmonic, |A_n| = hypot(a_n, b_n). Handy for tests and for the UI. */
export function harmonicMagnitudes(samples, H) {
  const { a, b } = dftHarmonics(samples, H);
  const m = new Float64Array(H + 1);
  for (let n = 1; n <= H; n++) m[n] = Math.hypot(a[n], b[n]);
  return m;
}

/** Evaluate the harmonic series at time `t`, expressed in cycles. */
export function evalSeries(a, b, t) {
  let y = 0;
  const w = 2 * Math.PI * t;
  for (let n = 1; n < a.length; n++) y += a[n] * Math.cos(w * n) + b[n] * Math.sin(w * n);
  return y;
}

const GRID = 4096; // fine grid for the zero-crossing search

/** Shortest distance between two positions on a cycle of length 1. */
function circDist(x, y) {
  const d = Math.abs(x - y) % 1;
  return d > 0.5 ? 1 - d : d;
}

/**
 * Turn an arbitrary single-cycle waveform into a 256-sample cycle that is
 * band-limited to `harmonics` partials and starts at a rising zero crossing.
 * The result is NOT normalised: writeFrame() in syntakt-fw.js removes DC and scales,
 * and it forces y[0] = 0 -- which is why the phase alignment below has to be exact,
 * otherwise that forced zero would be a step discontinuity in the cycle.
 *
 * @param {ArrayLike<number>} samples one full cycle, any length >= 8
 * @param {{harmonics?:number}} opts
 * @returns {{cycle:Float64Array, report:{inputLength:number, harmonicsKept:number,
 *            discardedEnergyPct:number, peakBefore:number, shiftFraction:number}}}
 */
export function conditionCycle(samples, opts = {}) {
  const N = samples.length;
  if (!(N >= 8)) throw new Error("a cycle needs at least 8 samples, got " + N);
  const want = Math.round(opts.harmonics ?? DEFAULT_HARMONICS);
  if (!Number.isFinite(want) || want < 1) throw new Error("harmonics must be a positive number");
  const H = Math.max(1, Math.min(want, MAX_HARMONICS, Math.floor(N / 2) - 1));

  let mean = 0;
  for (let i = 0; i < N; i++) {
    if (!Number.isFinite(samples[i])) throw new Error("input contains a non-finite sample at index " + i);
    mean += samples[i];
  }
  mean /= N;
  let peakBefore = 0, total = 0, peakAbs = 0;
  for (let i = 0; i < N; i++) {
    const d = samples[i] - mean;
    if (Math.abs(d) > peakBefore) peakBefore = Math.abs(d);
    if (Math.abs(samples[i]) > peakAbs) peakAbs = Math.abs(samples[i]);
    total += d * d;
  }
  // A constant does not survive rounding as an exact constant, so compare against the
  // signal level: anything this far below it is noise, and writeFrame would amplify it.
  if (!(peakBefore > 0) || peakBefore <= 1e-9 * peakAbs) {
    throw new Error("input is silent: a cycle must contain more than a constant");
  }

  const { a, b } = dftHarmonics(samples, H);
  let kept = 0, maxAmp = 0;
  for (let n = 1; n <= H; n++) {
    kept += a[n] * a[n] + b[n] * b[n];
    maxAmp = Math.max(maxAmp, Math.hypot(a[n], b[n]));
  }
  if (maxAmp <= 1e-9 * peakBefore) {
    throw new Error("nothing is left below harmonic " + H + ": raise the band limit");
  }
  kept *= N / 2; // Parseval, with DC already excluded from both sides
  const discardedEnergyPct = total > 0 ? Math.min(100, Math.max(0, (1 - kept / total) * 100)) : 0;

  // Where the fundamental a1*cos + b1*sin = A1*sin(2*pi*t + phi) rises through zero.
  const A1 = Math.hypot(a[1], b[1]);
  const phi = A1 > 0 ? Math.atan2(a[1], b[1]) : 0;
  let target = (-phi / (2 * Math.PI)) % 1;
  if (target < 0) target += 1;

  // Rising zero crossings of the whole band-limited series on a fine grid,
  // then the one closest to `target`.
  const g = new Float64Array(GRID);
  for (let j = 0; j < GRID; j++) g[j] = evalSeries(a, b, j / GRID);
  let bestJ = -1, bestD = Infinity;
  for (let j = 0; j < GRID; j++) {
    const nxt = (j + 1) % GRID;
    if (g[j] <= 0 && g[nxt] > 0) {
      const d = circDist((j + 0.5) / GRID, target);
      if (d < bestD) { bestD = d; bestJ = j; }
    }
  }
  let shift = 0;
  if (bestJ >= 0) {
    // Refine by bisection: the bracket [lo, hi] always keeps f(lo) <= 0 < f(hi).
    let lo = bestJ / GRID, hi = (bestJ + 1) / GRID;
    for (let it = 0; it < 80 && hi - lo > 1e-15; it++) {
      const mid = (lo + hi) / 2;
      if (evalSeries(a, b, mid) > 0) hi = mid; else lo = mid;
    }
    shift = (lo + hi) / 2;
    if (shift >= 1) shift -= 1;
  }

  const cycle = new Float64Array(CYCLE_LEN);
  for (let i = 0; i < CYCLE_LEN; i++) cycle[i] = evalSeries(a, b, i / CYCLE_LEN + shift);
  cycle[0] = 0; // zero by construction up to rounding; make it exact

  return {
    cycle,
    report: {
      inputLength: N,
      harmonicsKept: H,
      discardedEnergyPct,
      peakBefore,
      shiftFraction: shift,
    },
  };
}
