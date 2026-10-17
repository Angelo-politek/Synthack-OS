// aPLib-variant codec (LZ77 + interlaced Elias-gamma) as used by Elektron OS containers.
//
// Ported byte-for-byte from aplib.c / aplib.h of mischa85's elektron-firmware-tool
// (Marcel Bierling), MIT licensed - the same code that produced the images proven on
// hardware. The stream format, the offset bias, the far threshold, the last-offset
// reuse marker, the end-of-stream marker and the packer's cost-optimal parse with hash
// chains are all reproduced exactly, so streams produced here decode in the C depacker
// and vice versa. Verified against that tool's own output in test/aplib.test.mjs.
//
// Pure functions, no dependencies; runs in browsers and in Node (ES module).
// Never ships or fetches firmware: every byte comes from the file the user supplies.
//
// A "section" is the 8-byte header [u32 stream length BE][u32 stream byte-sum BE]
// followed by the compressed stream. depack() takes a whole section, pack() returns one.

/** Offset bias: off = rawoff - BIAS; a raw offset equal to the bias is the end marker. */
export const OFFSET_BIAS = 767;
/** Gamma value that selects last-offset reuse (R0) instead of an offset field. */
export const REUSE_GAMMA = 2;
/** off > this: the match gets a +1 length bonus and its minimum length is 3. */
export const FAR_THRESHOLD = 3328;
/** Minimum match length (3 when off > FAR_THRESHOLD). */
export const MIN_MATCH = 2;
/** Section-header bytes before the stream. */
export const SECT_HDR = 8;
/** Cost of a literal in bits: 1 control bit + 8 data bits. */
const LIT_BITS = 9;
/** Farthest back a match may reference - the envelope Elektron's own packer stays in. */
export const MAX_OFFSET = 1 << 20;
export const LEVEL_MIN = 0;
export const LEVEL_MAX = 3;
export const LEVEL_DEFAULT = LEVEL_MAX;

const HBITS = 17, HSIZE = 1 << HBITS, MAX_MATCH = 2048, COST_INF = 0xffffffff;
/** Effort presets: how many match candidates to examine per position. */
const LEVELS = [16, 64, 256, 2048];
/** Guard against a corrupt stream that would expand without bound (the C code is
 *  bounded by the caller's scratch buffer instead). */
const DEFAULT_MAX_OUT = 1 << 28;

const asBytes = (x) => (x instanceof Uint8Array ? x : new Uint8Array(x));
const be32 = (a, o) => ((a[o] << 24) | (a[o + 1] << 16) | (a[o + 2] << 8) | a[o + 3]) >>> 0;
const wr32 = (a, o, v) => { a[o] = v >>> 24; a[o + 1] = (v >>> 16) & 255; a[o + 2] = (v >>> 8) & 255; a[o + 3] = v & 255; };

/** The header's second field: the 32-bit wrapping sum of the stream bytes. */
export function streamSum(bytes) {
  const b = asBytes(bytes);
  let acc = 0;
  for (let i = 0; i < b.length; i++) acc = (acc + b[i]) >>> 0;
  return acc;
}

/** Read the 8-byte section header. Throws if it is inconsistent with the section. */
export function readHeader(section) {
  const sec = asBytes(section);
  if (sec.length < SECT_HDR) throw new Error(`aplib: section is ${sec.length} bytes, shorter than the ${SECT_HDR}-byte header`);
  const length = be32(sec, 0), sum = be32(sec, 4);
  if (length > sec.length - SECT_HDR) throw new Error(`aplib: header declares a ${length}-byte stream but only ${sec.length - SECT_HDR} bytes follow the header`);
  const stream = sec.subarray(SECT_HDR, SECT_HDR + length);
  const calc = streamSum(stream);
  if (calc !== sum) throw new Error(`aplib: stream byte-sum mismatch (header ${sum}, computed ${calc})`);
  return { length, sum, stream };
}

// ---- depacker -----------------------------------------------------------------------

/* The bit reader of aplib.c: an 8-bit tag byte, MSB first, with a sentinel bit marking
 * when the tag is used up. Input exhaustion sets `err` there and ends the stream; here
 * it throws, which is the same thing for a caller that does not allow truncation. */
function decode(stream, maxOut, stats) {
  let ip = 0, tag = 0;
  const iend = stream.length;
  const fail = (why) => { throw new Error(`aplib: malformed stream at byte ${ip} of ${iend}: ${why}`); };
  const gbRead = () => {
    if (ip >= iend) fail("input ended before the end-of-stream marker");
    return stream[ip++];
  };
  const getbit = () => {
    tag = (tag << 1) & 0x1ffff;
    if ((tag & 0xff) === 0) {
      const by = gbRead();
      tag = ((by << 1) | 1) >>> 0;
      return (by >> 7) & 1;
    }
    return (tag >> 8) & 1;
  };
  const getgamma = () => {
    let v = 1;
    for (;;) {
      v = ((v << 1) + getbit()) >>> 0;
      if (getbit()) break;
      if (v > 0x02000000) fail("Elias-gamma value out of range");
    }
    return v;
  };

  let cap = Math.max(1024, Math.min(maxOut, iend * 4));
  let out = new Uint8Array(cap), op = 0;
  const grow = (n) => {
    if (op + n <= out.length) return;
    if (op + n > maxOut) throw new Error(`aplib: decoded output exceeds the ${maxOut}-byte limit; the stream is not a valid aPLib stream`);
    let c = out.length;
    while (c < op + n) c *= 2;
    if (c > maxOut) c = maxOut;
    const nb = new Uint8Array(c);
    nb.set(out.subarray(0, op));
    out = nb;
  };

  let lastOff = 1;
  for (;;) {
    if (getbit()) { // literal
      grow(1);
      out[op++] = gbRead();
      if (stats) stats.literals++;
      continue;
    }
    const g = getgamma();
    let off;
    if (g === REUSE_GAMMA) {
      off = lastOff;
      if (stats) stats.reuses++;
    } else {
      // The raw offset is computed in uint32: a value below the bias wraps to something
      // near UINT32_MAX instead of going negative, and the "off > bytes written" test
      // below rejects it. Do not turn this into a signed subtraction without a check.
      off = ((((g << 8) >>> 0) + gbRead()) >>> 0);
      if (off === OFFSET_BIAS) break; // end of stream
      off = (off - OFFSET_BIAS) >>> 0;
      lastOff = off;
    }
    const ba = getbit(), bb = getbit();
    const sl = 2 * ba + bb;
    let L = sl ? sl : getgamma() + 2;
    if (off > FAR_THRESHOLD) L += 1;
    const n = L + 1;
    if (off === 0 || op < off) fail(`match offset ${off} reaches before the start of the output (${op} bytes so far)`);
    grow(n);
    if (stats) {
      stats.matches++;
      if (off > stats.maxOffset) stats.maxOffset = off;
      if (n > stats.maxLength) stats.maxLength = n;
    }
    let cp = op - off;
    for (let k = 0; k < n; k++) out[op++] = out[cp++]; // byte-wise: the copy may overlap
  }
  if (stats) { stats.trailing = iend - ip; stats.length = op; }
  return out.subarray(0, op).slice();
}

/**
 * Decompress a whole section (8-byte header + stream), like the C `ap_depack`.
 * The header length and byte-sum are verified first, so a damaged stream is rejected
 * rather than silently decoded into garbage; any malformed stream throws.
 * @param {Uint8Array} section
 * @param {{maxOut?: number}} [opts] - safety limit on the decoded size (default 256 MiB)
 * @returns {Uint8Array}
 */
export function depack(section, opts = {}) {
  const sec = asBytes(section);
  const { length, stream } = readHeader(sec);
  // A zero-length stream is what pack() writes for empty input; the C depacker reports
  // it as 0 bytes to a truncation-tolerant caller, which is how the tool calls it.
  if (length === 0) return new Uint8Array(0);
  return decode(stream, opts.maxOut ?? DEFAULT_MAX_OUT, null);
}

/** Decode a section for inspection: token counts and the largest offset it uses. */
export function streamStats(section, opts = {}) {
  const sec = asBytes(section);
  const { length, stream } = readHeader(sec);
  const stats = { literals: 0, matches: 0, reuses: 0, maxOffset: 0, maxLength: 0, trailing: 0, length: 0 };
  if (length === 0) return stats;
  decode(stream, opts.maxOut ?? DEFAULT_MAX_OUT, stats);
  return stats;
}

// ---- packer -------------------------------------------------------------------------

/* Bit writer: a tag byte is emitted when needed and its bits filled MSB first. */
function writer(cap) {
  return { o: new Uint8Array(cap), n: SECT_HDR, tagpos: -1, tagbits: 0 };
}
function ensure(w, extra) {
  if (w.n + extra <= w.o.length) return;
  let c = w.o.length || 64;
  while (c < w.n + extra) c *= 2;
  const nb = new Uint8Array(c);
  nb.set(w.o.subarray(0, w.n));
  w.o = nb;
}
function putBit(w, bit) {
  if (w.tagbits === 0) {
    ensure(w, 1);
    w.tagpos = w.n;
    w.o[w.n++] = 0;
    w.tagbits = 8;
  }
  if (bit) w.o[w.tagpos] |= 1 << (w.tagbits - 1);
  w.tagbits--;
}
function putByte(w, v) {
  ensure(w, 1);
  w.o[w.n++] = v & 0xff;
}
function putGamma(w, v) {
  const nb = 32 - Math.clz32(v);
  for (let i = nb - 2; i >= 0; i--) {
    putBit(w, (v >>> i) & 1);
    putBit(w, i === 0 ? 1 : 0);
  }
}
function putLiteral(w, b) {
  putBit(w, 1);
  putByte(w, b);
}
/** Bits an Elias-gamma code for v occupies. */
const gammaCost = (v) => 2 * (31 - Math.clz32(v));
/** Bits a match costs: control bit + offset field (or the R0 marker) + length field. */
function matchCost(off, L, lastOff) {
  let b = 1 + (off === lastOff ? 2 : gammaCost((off + OFFSET_BIAS) >>> 8) + 8);
  const Lb = L - 1 - (off > FAR_THRESHOLD ? 1 : 0);
  b += Lb <= 3 ? 2 : 2 + gammaCost(Lb - 2);
  return b;
}
function putMatch(w, off, matchlen, lastOff) {
  putBit(w, 0);
  if (off === lastOff) {
    putGamma(w, REUSE_GAMMA);
  } else {
    const raw = off + OFFSET_BIAS;
    putGamma(w, raw >>> 8);
    putByte(w, raw & 0xff);
    lastOff = off;
  }
  const bonus = off > FAR_THRESHOLD ? 1 : 0;
  const Lbase = matchlen - 1 - bonus;
  if (Lbase <= 3) {
    putBit(w, (Lbase >>> 1) & 1);
    putBit(w, Lbase & 1);
  } else {
    putBit(w, 0);
    putBit(w, 0);
    putGamma(w, Lbase - 2);
  }
  return lastOff;
}

const hash2 = (d, i) => ((d[i] << 8) ^ d[i + 1]) & (HSIZE - 1);

/** Common-prefix length of data[a..] and data[b..], capped. */
function matchRun(d, a, b, cap) {
  let l = 0;
  while (l < cap && d[a + l] === d[b + l]) l++;
  return l;
}

/**
 * Compress `raw` into a section (8-byte header + stream), like the C `ap_pack`.
 * The parse is chosen by the same cost-optimal forward DP over the same hash-chain
 * candidates, so the result matches the C tool's size to the byte for a given level.
 * @param {Uint8Array} raw
 * @param {number} [level] - 0..3, how many candidates per position (16/64/256/2048)
 * @param {(fraction: number) => void} [onProgress] - called now and then with 0..1 while parsing,
 *   and once with 1 at the end; it never changes the output
 * @returns {Uint8Array} header + stream
 */
export function pack(raw, level = LEVEL_DEFAULT, onProgress = null) {
  const data = asBytes(raw);
  const len = data.length;
  let lv = level | 0;
  if (lv < LEVEL_MIN) lv = LEVEL_MIN;
  if (lv > LEVEL_MAX) lv = LEVEL_MAX;
  const maxChain = LEVELS[lv];

  if (len === 0) return new Uint8Array(SECT_HDR); // length 0, sum 0

  const w = writer(len + (len >>> 1) + 256);

  const head = new Int32Array(HSIZE).fill(-1);
  const prev = new Int32Array(len);
  const cost = new Uint32Array(len + 1).fill(COST_INF);
  const lo = new Uint32Array(len + 1);
  const from = new Int32Array(len + 1);
  const toff = new Uint32Array(len + 1);
  const tlen = new Uint32Array(len + 1); // 0 => literal
  cost[0] = 0;
  lo[0] = 1;
  from[0] = -1;

  for (let i = 0; i < len; i++) {
    if (onProgress && (i & 0xffff) === 0) onProgress(i / len);
    const bi = cost[i];
    if (bi === COST_INF) continue;
    const loi = lo[i];
    let cap = len - i;
    if (cap > MAX_MATCH) cap = MAX_MATCH;

    // literal
    if (bi + LIT_BITS < cost[i + 1]) {
      cost[i + 1] = bi + LIT_BITS;
      lo[i + 1] = loi;
      from[i + 1] = i;
      toff[i + 1] = 0;
      tlen[i + 1] = 0;
    }

    if (i + 1 < len) {
      if (i >= loi) { // last-offset reuse costs no offset field
        const rl = matchRun(data, i - loi, i, cap);
        const mn = loi > FAR_THRESHOLD ? MIN_MATCH + 1 : MIN_MATCH;
        const base = 1 + 2; // control bit + R0 gamma
        const bonus = loi > FAR_THRESHOLD ? 1 : 0;
        for (let cl = mn; cl <= rl; cl++) {
          const Lb = cl - 1 - bonus;
          const nc = bi + base + (Lb <= 3 ? 2 : 2 + gammaCost(Lb - 2));
          const pos = i + cl;
          if (nc < cost[pos]) {
            cost[pos] = nc;
            lo[pos] = loi;
            from[pos] = i;
            toff[pos] = loi;
            tlen[pos] = cl;
          }
        }
      }
      let j = head[hash2(data, i)];
      let chain = maxChain;
      let pm = 1;
      while (j >= 0 && chain-- > 0) {
        const off = i - j;
        // Chains run newest-first, so everything past here is further away still.
        if (off > MAX_OFFSET) break;
        // A candidate cannot beat the incumbent unless it matches at pm too, so one
        // byte rejects most of them without a full scan. Search cost only: this never
        // changes which match wins, so the output is unaffected.
        if (pm >= cap) break;
        if (data[j + pm] !== data[i + pm]) { j = prev[j]; continue; }
        const l = matchRun(data, j, i, cap);
        if (l > pm) {
          const far = off > FAR_THRESHOLD;
          const mn = far ? MIN_MATCH + 1 : MIN_MATCH;
          const start = pm + 1 > mn ? pm + 1 : mn;
          const base = 1 + (off === loi ? 2 : gammaCost((off + OFFSET_BIAS) >>> 8) + 8);
          const bonus = far ? 1 : 0;
          for (let cl = start; cl <= l; cl++) {
            const Lb = cl - 1 - bonus;
            const nc = bi + base + (Lb <= 3 ? 2 : 2 + gammaCost(Lb - 2));
            const pos = i + cl;
            if (nc < cost[pos]) {
              cost[pos] = nc;
              lo[pos] = off;
              from[pos] = i;
              toff[pos] = off;
              tlen[pos] = cl;
            }
          }
          pm = l;
          if (l >= cap) break;
        }
        j = prev[j];
      }
    }
    if (i + 1 < len) {
      const h = hash2(data, i);
      prev[i] = head[h];
      head[h] = i;
    }
  }

  let npos = 0;
  for (let j = len; j > 0; j = from[j]) npos++;
  const path = new Uint32Array(npos || 1);
  {
    let k = npos;
    for (let j = len; j > 0; j = from[j]) path[--k] = j;
  }

  let lastOff = 1;
  for (let k = 0; k < npos; k++) {
    const pos = path[k];
    const src = from[pos];
    if (tlen[pos] === 0) putLiteral(w, data[src]);
    else lastOff = putMatch(w, toff[pos], tlen[pos], lastOff);
  }

  // End of stream: a match whose raw offset field decodes to OFFSET_BIAS. The depacker
  // computes off = (gamma << 8) + byte in uint32, so the wrap is deliberate:
  // (0x1000002 << 8) + 0xFF truncates to 0x2FF == 767. Plain gamma 2 cannot be used
  // because the depacker reads that as the last-offset-reuse marker instead.
  putBit(w, 0);
  putGamma(w, 0x1000002);
  putByte(w, 0xff);

  const out = w.o.subarray(0, w.n).slice();
  const streamLen = w.n - SECT_HDR;
  wr32(out, 0, streamLen);
  wr32(out, 4, streamSum(out.subarray(SECT_HDR)));
  if (onProgress) onProgress(1);
  return out;
}
