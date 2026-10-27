// Trasporto SysEx dei .syx Elektron moderni (pacchetti da 126 byte, 8-in-7): port di transport.c di
// elektron-firmware-tool (Marcel Bierling, MIT). Solo il formato della Syntakt; i trasporti legacy
// (Machinedrum, Monomachine, Octatrack) non servono qui.
//   marcatore (14 B): 00 20 3C dev 00 7F 01|02 <7 B info>
//   dati (126 B):     00 20 3C dev 00 7E blk[2] seq <116 B 8-in-7 = 101 B> checksum

const PKT = 126, HDR = 9, ENC_PAY = 116, DEC_PER_PKT = 101, CKSUM_OFF = 125, MARKER = 14;
const CMD_DATA = 0x7e, CMD_MARKER = 0x7f;
export const PREAMBLE = 8;   // flusso decodificato: [dimensione del contenitore][checksum del contenuto]

export interface Transport {
  device: number;
  stream: Uint8Array;           // preambolo + contenitore (+ riempimento dell'ultimo pacchetto)
  ndata: number;
  pktOk: number;
  pktBad: number;
  base: number;                 // seme del checksum (info[0] del marcatore iniziale)
  markerInfo: Uint8Array | null;
}

function* messages(buf: Uint8Array): Generator<Uint8Array> {
  let pos = 0;
  while (pos < buf.length) {
    if (buf[pos] !== 0xf0) { pos++; continue; }
    let j = pos + 1;
    while (j < buf.length && buf[j] !== 0xf7) j++;
    if (j >= buf.length) return;
    yield buf.subarray(pos + 1, j);
    pos = j + 1;
  }
}

/** Somma a 7 bit di body[6..124], ogni byte in XOR con (base + indice), piu' base. */
export function blockChecksum(body: Uint8Array, base: number): number {
  let acc = 0;
  for (let i = 0; i < CKSUM_OFF - 6; i++) acc += body[6 + i] ^ ((base + i) & 0xff);
  return (base + acc) & 0x7f;
}

export function decode(buf: Uint8Array): Transport {
  const cnt = new Map<number, number>();
  let device = 0;
  for (const m of messages(buf)) {
    if (m.length > 3 && !device) device = m[3];
    if (m.length > 5 && m.length < 512 && m[5] === CMD_DATA) cnt.set(m.length, (cnt.get(m.length) ?? 0) + 1);
  }
  let pkt = 0, best = 0;
  for (const [L, c] of [...cnt].sort((a, b) => a[0] - b[0]))
    if (L >= 16 && c > best) { best = c; pkt = L; }
  if (pkt !== PKT) throw new Error("not a modern Elektron OS .syx (unexpected packet size)");

  const stream = new Uint8Array(Math.ceil(buf.length * DEC_PER_PKT / PKT) + DEC_PER_PKT);
  let dpos = 0, ndata = 0, pktOk = 0, pktBad = 0, ckbase = 0, haveBase = false;
  for (const m of messages(buf)) {
    if (m.length === PKT && m[5] === CMD_DATA) {
      ndata++;
      for (let k = HDR; k < HDR + ENC_PAY; k += 8) {
        const ms = m[k], nd = Math.min(HDR + ENC_PAY - k - 1, 7);
        for (let n = 0; n < nd; n++) stream[dpos++] = m[k + 1 + n] | ((ms >> (6 - n)) & 1 ? 0x80 : 0);
      }
      if (haveBase) {
        if (blockChecksum(m, ckbase) === m[CKSUM_OFF]) pktOk++;
        else pktBad++;
      }
    } else if (m.length > 7) {
      ckbase = m[7];
      haveBase = true;
    }
  }
  let base = 0, markerInfo: Uint8Array | null = null;
  for (const m of messages(buf))
    if (m.length >= MARKER && m[5] === CMD_MARKER) {
      base = m[7];
      markerInfo = m.slice(7, 14);
      break;
    }
  return { device, stream: stream.slice(0, dpos), ndata, pktOk, pktBad, base, markerInfo };
}

/** Numero di pacchetti dichiarato dal marcatore iniziale. */
export function declaredPackets(t: Transport): number | null {
  const i = t.markerInfo;
  return i ? (i[4] << 14) | (i[5] << 7) | i[6] : null;
}

function marker(dev: number, kind: number, base: number, npkt: number, tmpl: Uint8Array | null): Uint8Array {
  const m = new Uint8Array(MARKER);
  m.set([0x00, 0x20, 0x3c, dev, 0x00, CMD_MARKER, kind]);
  m.set(tmpl ?? [0x10, 0x00, 0x01, 0x72, 0x01, 0x06, 0x6b], 7);
  m[7] = base;
  m[11] = (npkt >> 14) & 0x7f;
  m[12] = (npkt >> 7) & 0x7f;
  m[13] = npkt & 0x7f;
  return m;
}

/** Preambolo + contenitore -> .syx, con dispositivo, seme e marcatori presi dall'originale. */
export function encode(container: Uint8Array, preamble: Uint8Array, dev: number, base: number,
                       markerInfo: Uint8Array | null): Uint8Array {
  const total = PREAMBLE + container.length;
  const npkt = Math.floor(total / DEC_PER_PKT) + 1;            // sempre un ultimo pacchetto, anche vuoto
  const stream = new Uint8Array(npkt * DEC_PER_PKT);
  stream.set(preamble);
  stream.set(container, PREAMBLE);
  const out = new Uint8Array(2 * (MARKER + 2) + npkt * (PKT + 2));
  let o = 0;
  const emit = (body: Uint8Array): void => {
    out[o++] = 0xf0;
    out.set(body, o);
    o += body.length;
    out[o++] = 0xf7;
  };
  const startBlock = markerInfo ? (markerInfo[1] << 7) | markerInfo[2] : 1;
  const startSeq = markerInfo ? markerInfo[3] : 0x72;
  emit(marker(dev, 0x01, base, npkt, markerInfo));
  const p = new Uint8Array(PKT);
  for (let k = 0; k < npkt; k++) {
    const cum = startSeq + k, block = startBlock + (cum >> 7);
    p.fill(0);
    p.set([0x00, 0x20, 0x3c, dev, 0x00, CMD_DATA, (block >> 7) & 0x7f, block & 0x7f, cum & 0x7f]);
    let q = HDR;
    for (let i = k * DEC_PER_PKT, end = i + DEC_PER_PKT; i < end; i += 7) {
      const nd = Math.min(end - i, 7);
      let ms = 0;
      for (let n = 0; n < nd; n++) if (stream[i + n] & 0x80) ms |= 1 << (6 - n);
      p[q++] = ms;
      for (let n = 0; n < nd; n++) p[q++] = stream[i + n] & 0x7f;
    }
    p[CKSUM_OFF] = blockChecksum(p, base);
    emit(p);
  }
  emit(marker(dev, 0x02, base, npkt, markerInfo));
  return out;
}
