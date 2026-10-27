// Variante aPLib delle sezioni Elektron: port di aplib.c di elektron-firmware-tool (Marcel Bierling, MIT).
// Stessi errori e stesse scelte del compressore: a parita' di livello l'uscita e' identica byte per byte.
// Ogni flusso ha davanti [u32 lunghezza BE][u32 somma dei byte BE].

export const SECT_HDR = 8;
const BIAS = 767;        // off = grezzo - BIAS; grezzo == BIAS -> fine del flusso
const REUSE = 2;         // gamma che riusa l'ultima distanza
const FAR = 3328;        // oltre: +1 di lunghezza, corrispondenza minima 3
const MIN_MATCH = 2;
const LIT_BITS = 9;
const MAX_OFFSET = 1 << 20;
const MAX_MATCH = 2048;
const HBITS = 17, HSIZE = 1 << HBITS;
const LEVELS = [16, 64, 256, 2048];
const SCRATCH_CAP = 64 << 20;   // come il tool: tetto dell'uscita di una sezione

/** Decomprime una sezione (intestazione compresa). null dove il tool C ritorna (size_t)-1. */
export function depack(src: Uint8Array, allowTrunc: boolean): Uint8Array | null {
  if (src.length < SECT_HDR) return null;
  let ip = SECT_HDR, tag = 0, err = false;
  const iend = src.length;
  let out = new Uint8Array(Math.min(SCRATCH_CAP, Math.max(1 << 16, src.length * 4)));
  let op = 0, lastOff = 1;

  const read = (): number => {
    if (ip >= iend) { err = true; return 0; }
    return src[ip++];
  };
  const bit = (): number => {
    tag = (tag << 1) >>> 0;
    if ((tag & 0xff) === 0) {
      const by = read();
      tag = ((by << 1) | 1) >>> 0;
      return (by >> 7) & 1;
    }
    return (tag >>> 8) & 1;
  };
  const gamma = (): number => {
    let v = 1;
    for (;;) {
      v = ((v << 1) + bit()) >>> 0;
      if (bit()) break;
      if (err) break;
      if (v > 0x02000000) { err = true; break; }
    }
    return v;
  };
  const room = (n: number): boolean => {
    if (op + n <= out.length) return true;
    if (op + n > SCRATCH_CAP) return false;
    let cap = out.length;
    while (cap < op + n) cap *= 2;
    const nb = new Uint8Array(Math.min(cap, SCRATCH_CAP));
    nb.set(out.subarray(0, op));
    out = nb;
    return true;
  };

  for (;;) {
    if (err) { if (allowTrunc) break; return null; }
    if (bit()) {
      if (!room(1)) return null;
      if (ip >= iend) { if (allowTrunc) break; return null; }
      out[op++] = src[ip++];
      continue;
    }
    const g = gamma();
    let off: number;
    if (g === REUSE) {
      off = lastOff;
    } else {
      off = (((g << 8) >>> 0) + read()) >>> 0;     // uint32 come in C: il marcatore di fine ci conta
      if (err) { if (allowTrunc) break; return null; }
      if (off === BIAS) break;
      off = (off - BIAS) >>> 0;
      lastOff = off;
    }
    const ba = bit(), bb = bit();
    const sl = 2 * ba + bb;
    let L = sl ? sl : (gamma() + 2) >>> 0;
    if (err) { if (allowTrunc) break; return null; }
    if (off > FAR) L += 1;
    let n = L + 1;
    if (off === 0 || op < off) return null;
    if (!room(n)) return null;
    let cp = op - off;
    while (n--) out[op++] = out[cp++];
  }
  if (op === 0 && !allowTrunc) return null;
  return out.slice(0, op);
}

/** Margine minimo di decompressione all'avvio (tools/build/bootcheck.py, stessa aritmetica senza
 * troncamenti a 32 bit): il bootstrap decomprime da 0x40200000 verso 0x40000400. */
export function depackMargin(stream: Uint8Array): { size: number; margin: number } {
  const base = 0x4020_0000 - 0x4000_0400;
  const n = stream.length;
  let ip = SECT_HDR, op = 0, tag = 0, lastOff = 1, worst = Infinity;
  const byte = (): number => {
    if (ip >= n) throw RangeError();
    return stream[ip++];
  };
  const bit = (): number => {
    tag = (tag << 1) & 0xffff;
    if (!(tag & 0xff)) {
      const by = byte();
      tag = (by << 1) | 1;
      return by >> 7;
    }
    return (tag >> 8) & 1;
  };
  const gamma = (): number => {
    let v = 1;
    for (;;) {
      v = v * 2 + bit();
      if (bit()) return v;
    }
  };
  try {
    while (ip < n) {
      if (bit()) {
        ip += 1;
        op += 1;
      } else {
        const g = gamma();
        let off: number;
        if (g === REUSE) {
          off = lastOff;
        } else {
          off = g * 256 + byte();
          if (off === BIAS) break;
          off -= BIAS;
          lastOff = off;
        }
        let sl = 2 * bit();
        sl += bit();
        let length = sl ? sl : gamma() + 2;
        if (off > FAR) length += 1;
        op += length + 1;
      }
      const m = base + ip - op;
      if (m < worst) worst = m;
    }
  } catch (e) {
    if (!(e instanceof RangeError)) throw e;   // fine del flusso senza marcatore
  }
  return { size: op, margin: worst };
}

function gammaCost(v: number): number {
  return 2 * (31 - Math.clz32(v));
}

function matchCost(off: number, L: number, last: number): number {
  let b = 1 + (off === last ? 2 : gammaCost((off + BIAS) >>> 8) + 8);
  const Lb = L - 1 - (off > FAR ? 1 : 0);
  b += Lb <= 3 ? 2 : 2 + gammaCost(Lb - 2);
  return b;
}

class BitWriter {
  o: Uint8Array;
  n = SECT_HDR;
  private tagpos = -1;
  private tagbits = 0;

  constructor(cap: number) {
    this.o = new Uint8Array(cap);
  }

  private grow(): void {
    const nb = new Uint8Array(this.o.length * 2);
    nb.set(this.o);
    this.o = nb;
  }

  bit(b: number): void {
    if (this.tagbits === 0) {
      if (this.n >= this.o.length) this.grow();
      this.tagpos = this.n;
      this.o[this.n++] = 0;
      this.tagbits = 8;
    }
    if (b) this.o[this.tagpos] |= 1 << (this.tagbits - 1);
    this.tagbits--;
  }

  byte(v: number): void {
    if (this.n >= this.o.length) this.grow();
    this.o[this.n++] = v;
  }

  gamma(v: number): void {
    const nb = 32 - Math.clz32(v);
    for (let i = nb - 2; i >= 0; i--) {
      this.bit((v >>> i) & 1);
      this.bit(i === 0 ? 1 : 0);
    }
  }
}

/** Comprime una sezione intera (intestazione compresa). Livello 0..3: 3 come elektron-firmware-tool -l 3. */
export function pack(data: Uint8Array, level = 3, progress?: (done: number, total: number) => void): Uint8Array {
  const len = data.length;
  if (len === 0) return new Uint8Array(SECT_HDR);
  const maxChain = LEVELS[Math.max(0, Math.min(3, level))];
  const COST_INF = 0xffffffff;

  const head = new Int32Array(HSIZE).fill(-1);
  const prev = new Int32Array(len);
  const cost = new Uint32Array(len + 1).fill(COST_INF);
  const lo = new Uint32Array(len + 1);
  const from = new Int32Array(len + 1);
  const toff = new Uint32Array(len + 1);
  const tlen = new Uint32Array(len + 1);   // 0 = letterale
  cost[0] = 0;
  lo[0] = 1;
  from[0] = -1;

  for (let i = 0; i < len; i++) {
    if (progress && (i & 0xffff) === 0) progress(i, len);
    if (cost[i] === COST_INF) continue;
    const bi = cost[i], loi = lo[i];
    const cap = Math.min(len - i, MAX_MATCH);
    let nc = bi + LIT_BITS;
    if (nc < cost[i + 1]) {
      cost[i + 1] = nc; lo[i + 1] = loi; from[i + 1] = i; toff[i + 1] = 0; tlen[i + 1] = 0;
    }
    if (i + 1 < len) {
      if (i >= loi) {                                  // riuso dell'ultima distanza: niente campo distanza
        let rl = 0;
        while (rl < cap && data[i - loi + rl] === data[i + rl]) rl++;
        const mn = loi > FAR ? MIN_MATCH + 1 : MIN_MATCH;
        for (let cl = mn; cl <= rl; cl++) {
          nc = bi + matchCost(loi, cl, loi);
          if (nc < cost[i + cl]) {
            cost[i + cl] = nc; lo[i + cl] = loi; from[i + cl] = i; toff[i + cl] = loi; tlen[i + cl] = cl;
          }
        }
      }
      let j = head[((data[i] << 8) ^ data[i + 1]) & (HSIZE - 1)];
      let chain = maxChain, pm = 1;
      while (j >= 0 && chain--) {
        const off = i - j;
        if (off > MAX_OFFSET) break;                   // catene dal piu' vicino: oltre e' piu' lontano
        if (pm >= cap) break;
        if (data[j + pm] !== data[i + pm]) {
          j = prev[j];
          continue;
        }
        let l = 0;
        while (l < cap && data[j + l] === data[i + l]) l++;
        if (l > pm) {
          const mn = off > FAR ? MIN_MATCH + 1 : MIN_MATCH;
          for (let cl = Math.max(pm + 1, mn); cl <= l; cl++) {
            nc = bi + matchCost(off, cl, loi);
            if (nc < cost[i + cl]) {
              cost[i + cl] = nc; lo[i + cl] = off; from[i + cl] = i; toff[i + cl] = off; tlen[i + cl] = cl;
            }
          }
          pm = l;
          if (l >= cap) break;
        }
        j = prev[j];
      }
      const h = ((data[i] << 8) ^ data[i + 1]) & (HSIZE - 1);
      prev[i] = head[h];
      head[h] = i;
    }
  }
  progress?.(len, len);

  let npos = 0;
  for (let j = len; j > 0; j = from[j]) npos++;
  const path = new Uint32Array(npos);
  for (let j = len, k = npos; j > 0; j = from[j]) path[--k] = j;

  const w = new BitWriter(len + (len >>> 1) + 256);
  let last = 1;
  for (let k = 0; k < npos; k++) {
    const pos = path[k];
    if (tlen[pos] === 0) {
      w.bit(1);
      w.byte(data[from[pos]]);
      continue;
    }
    const off = toff[pos];
    w.bit(0);
    if (off === last) {
      w.gamma(REUSE);
    } else {
      const raw = off + BIAS;
      w.gamma(raw >>> 8);
      w.byte(raw & 0xff);
      last = off;
    }
    const Lbase = tlen[pos] - 1 - (off > FAR ? 1 : 0);
    if (Lbase <= 3) {
      w.bit(Lbase >> 1);
      w.bit(Lbase & 1);
    } else {
      w.bit(0);
      w.bit(0);
      w.gamma(Lbase - 2);
    }
  }
  // fine: distanza grezza (0x1000002 << 8) + 0xFF, che in uint32 vale 0x2FF == BIAS
  w.bit(0);
  w.gamma(0x1000002);
  w.byte(0xff);

  const out = w.o.slice(0, w.n);
  let sum = 0;
  for (let k = SECT_HDR; k < out.length; k++) sum = (sum + out[k]) >>> 0;
  const dv = new DataView(out.buffer);
  dv.setUint32(0, out.length - SECT_HDR);
  dv.setUint32(4, sum);
  return out;
}
