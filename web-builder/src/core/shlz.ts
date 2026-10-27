// SHLZ, l'LZ77 dell'area mod: port di tools/build/lz.py (stesso flusso, byte per byte).
// "SHLZ", lunghezza decompressa (u32 BE), lunghezza del flusso (u32 BE), poi gettoni:
//   0xxxxxxx        -> seguono x+1 byte letterali (1..128)
//   1lllllll hi lo  -> copia l+3 byte (3..130) da distanza (hi<<8|lo) (1..65535) all'indietro

const MIN = 3, MAX_LEN = 130, MAX_LIT = 128, WINDOW = 0xffff;

export function compress(data: Uint8Array): Uint8Array {
  const n = data.length;
  const out: number[] = [];
  let lits: number[] = [];
  const heads = new Map<number, number[]>();
  const key = (k: number): number => (data[k] << 16) | (data[k + 1] << 8) | data[k + 2];

  const flush = (): void => {
    for (let k = 0; k < lits.length; k += MAX_LIT) {
      const chunk = lits.slice(k, k + MAX_LIT);
      out.push(chunk.length - 1, ...chunk);
    }
    lits = [];
  };

  let i = 0;
  while (i < n) {
    let bestLen = 0, bestOff = 0;
    if (i + MIN <= n) {
      const cand = heads.get(key(i)) ?? [];
      for (let c = cand.length - 1; c >= Math.max(0, cand.length - 64); c--) {   // i candidati piu' vicini
        const j = cand[c];
        if (i - j > WINDOW) break;
        let L = MIN;
        while (L < MAX_LEN && i + L < n && data[j + L] === data[i + L]) L++;
        if (L > bestLen) {
          bestLen = L;
          bestOff = i - j;
          if (L === MAX_LEN) break;
        }
      }
    }
    const step = bestLen >= MIN ? bestLen : 1;
    for (let k = i, e = Math.min(i + step, n - MIN + 1); k < e; k++) {
      const h = key(k);
      const l = heads.get(h);
      if (l) l.push(k);
      else heads.set(h, [k]);
    }
    if (bestLen >= MIN) {
      flush();
      out.push(0x80 | (bestLen - MIN), bestOff >> 8, bestOff & 0xff);
    } else {
      lits.push(data[i]);
    }
    i += step;
  }
  flush();
  const res = new Uint8Array(12 + out.length);
  res.set([0x53, 0x48, 0x4c, 0x5a]);
  const dv = new DataView(res.buffer);
  dv.setUint32(4, n);
  dv.setUint32(8, out.length);
  res.set(out, 12);
  return res;
}

export function decompress(blob: Uint8Array): Uint8Array {
  if (blob[0] !== 0x53 || blob[1] !== 0x48 || blob[2] !== 0x4c || blob[3] !== 0x5a) throw new Error("not an SHLZ stream");
  const dv = new DataView(blob.buffer, blob.byteOffset, blob.byteLength);
  const n = dv.getUint32(4), clen = dv.getUint32(8);
  const src = blob.subarray(12, 12 + clen);
  const out = new Uint8Array(n);
  let o = 0, i = 0;
  while (o < n) {
    const c = src[i++];
    if (c === undefined) throw new Error("SHLZ: truncated stream");
    if (c & 0x80) {
      const L = (c & 0x7f) + MIN, off = (src[i] << 8) | src[i + 1];
      i += 2;
      if (!(off > 0 && off <= o) || o + L > n) throw new Error("SHLZ: invalid distance");
      for (let k = 0; k < L; k++, o++) out[o] = out[o - off];
    } else {
      if (o + c + 1 > n || i + c + 1 > src.length) throw new Error("SHLZ: inconsistent lengths");
      out.set(src.subarray(i, i + c + 1), o);
      o += c + 1;
      i += c + 1;
    }
  }
  if (i !== clen) throw new Error("SHLZ: inconsistent lengths");
  return out;
}
