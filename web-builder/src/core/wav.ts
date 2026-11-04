// SPDX-License-Identifier: GPL-2.0-or-later
// WAV -> SAMP body (64-byte header + PCM16BE mono 48 kHz): port of read_wav, resample, to_pcm16be and samp_body of
// Synfact's long_samples.py (GSM1980). PCM 8/16/24/32 bit, float 32, extensible; channels mixed to mono; 4-point
// Hermite to 48 kHz (no anti-alias filter, as Synfact: prepare sources above 48 kHz with a proper resampler).

export const RATE = 48000;

export function readWav(data: Uint8Array): { rate: number; mono: Float32Array } {
  const dv = new DataView(data.buffer, data.byteOffset, data.byteLength);
  const tag4 = (o: number) => String.fromCharCode(...data.subarray(o, o + 4));
  if (tag4(0) !== "RIFF" || tag4(8) !== "WAVE") throw new Error("not a RIFF/WAVE file");
  let fmt: DataView | null = null, pcm: Uint8Array | null = null;
  for (let pos = 12; pos + 8 <= data.length;) {
    const id = tag4(pos), size = dv.getUint32(pos + 4, true);
    if (pos + 8 + size > data.length) throw new Error("truncated WAV chunk");
    if (id === "fmt ") fmt = new DataView(data.buffer, data.byteOffset + pos + 8, size);
    else if (id === "data") pcm = data.subarray(pos + 8, pos + 8 + size);
    pos += 8 + size + (size & 1);
  }
  if (!fmt || !pcm || fmt.byteLength < 16) throw new Error("missing fmt or data chunk");
  let tag = fmt.getUint16(0, true);
  const channels = fmt.getUint16(2, true), rate = fmt.getUint32(4, true), bits = fmt.getUint16(14, true);
  if (tag === 0xfffe) {
    if (fmt.byteLength < 40) throw new Error("truncated extensible WAV format");
    tag = fmt.getUint16(24, true);
  }
  if (channels < 1 || channels > 32 || rate < 1 || rate > 768000 || ![8, 16, 24, 32].includes(bits)) {
    throw new Error("invalid WAV rate/channels/width");
  }
  const width = bits / 8, frames = Math.floor(pcm.length / (width * channels));
  const p = new DataView(pcm.buffer, pcm.byteOffset, pcm.byteLength);
  let get: (o: number) => number;
  if (tag === 1 && bits === 16) get = (o) => p.getInt16(o, true) / 32768;
  else if (tag === 1 && bits === 32) get = (o) => p.getInt32(o, true) / 2147483648;
  else if (tag === 3 && bits === 32) get = (o) => p.getFloat32(o, true);
  else if (tag === 1 && bits === 8) get = (o) => (p.getUint8(o) - 128) / 128;
  else if (tag === 1 && bits === 24) get = (o) => ((p.getUint8(o) | p.getUint8(o + 1) << 8 | p.getInt8(o + 2) << 16)) / 8388608;
  else throw new Error(`unsupported WAV format tag ${tag} / ${bits} bit`);
  const mono = new Float32Array(frames);
  for (let i = 0; i < frames; i++) {
    let s = 0;
    for (let c = 0; c < channels; c++) s += get((i * channels + c) * width);
    mono[i] = s / channels;
  }
  return { rate, mono };
}

export function resample(s: Float32Array, rate: number): Float32Array {
  if (rate === RATE || !s.length) return s;
  const step = rate / RATE, n = s.length, out = new Float32Array(Math.floor(n * RATE / rate));
  for (let i = 0; i < out.length; i++) {
    const x = i * step, j = Math.floor(x), t = x - j;
    const y0 = j ? s[j - 1] : s[0], y1 = s[j], y2 = j + 1 < n ? s[j + 1] : s[n - 1], y3 = j + 2 < n ? s[j + 2] : s[n - 1];
    const c1 = 0.5 * (y2 - y0), c2 = y0 - 2.5 * y1 + 2 * y2 - 0.5 * y3, c3 = 0.5 * (y3 - y0) + 1.5 * (y1 - y2);
    out[i] = ((c3 * t + c2) * t + c1) * t + y1;
  }
  return out;
}

/** SAMP body: 'SAMP', frames at +8, name (16 bytes, latin-1) at +12, then PCM16BE */
export function sampBody(mono48: Float32Array, name: string): Uint8Array {
  const out = new Uint8Array(64 + 2 * mono48.length), dv = new DataView(out.buffer);
  out.set([0x53, 0x41, 0x4d, 0x50], 0);
  dv.setUint32(8, mono48.length);
  for (let k = 0; k < 16 && k < name.length; k++) out[12 + k] = name.charCodeAt(k) < 256 ? name.charCodeAt(k) : 0x3f;
  for (let i = 0; i < mono48.length; i++) {
    // Python round(): halves to even
    const v = mono48[i] * 32768, r = Math.round(v), q = Math.abs(v % 1) === 0.5 && r % 2 ? r - 1 : r;
    dv.setInt16(64 + 2 * i, Math.max(-32768, Math.min(32767, q)));
  }
  return out;
}

export function wavBody(data: Uint8Array, name: string): Uint8Array {
  const { rate, mono } = readWav(data);
  return sampBody(resample(mono, rate), name);
}

/** a name for the catalogue: the file name without extension, at most 32 UTF-8 bytes, unique in used */
export function catalogueName(file: string, used: Set<string>): string {
  const enc = new TextEncoder();
  let base = file.replace(/\.[^.]*$/, "").trim();
  while (enc.encode(base).length > 32) base = base.slice(0, -1).trimEnd();
  let out = base, n = 2;
  while (used.has(out)) {
    const tail = `~${n++}`;
    let stem = base;
    while (enc.encode(stem + tail).length > 32) stem = stem.slice(0, -1);
    out = stem.trimEnd() + tail;
  }
  used.add(out);
  return out;
}
