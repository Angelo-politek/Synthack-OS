// SPDX-License-Identifier: GPL-2.0-or-later
// Samples page helpers: waveform peaks, SAMP body <-> samples, and the voice CPU memory the boot plan gives each
// sample (mods/long-samples/pool.c, ls_plan: 64 MB of 2 KB pages, stock blob first, then one table page and each
// long sample in the Syntakt's order until the memory is full).

import type { Entry } from "./hzfs.ts";

export const PAGE = 2048;
export const POOL_PAGES = 0x400_0000 / PAGE;               // 64 MB on CPU #2

/** the largest |sample| of each of `columns` equal parts of `s` */
export function peaks(s: Float32Array, columns: number): Float32Array {
  const out = new Float32Array(columns);
  if (!s.length) return out;
  for (let c = 0; c < columns; c++) {
    const a = Math.floor(c * s.length / columns), b = Math.max(a + 1, Math.floor((c + 1) * s.length / columns));
    let p = 0;
    for (let i = a; i < b && i < s.length; i++) p = Math.max(p, Math.abs(s[i]));
    out[c] = p;
  }
  return out;
}

/** the samples of a SAMP body (64-byte header, PCM16BE), as -1..1 */
export function bodySamples(body: Uint8Array): Float32Array {
  const dv = new DataView(body.buffer, body.byteOffset, body.byteLength), n = Math.max(0, (body.length - 64) >> 1);
  const out = new Float32Array(n);
  for (let i = 0; i < n; i++) out[i] = dv.getInt16(64 + 2 * i) / 32768;
  return out;
}

/** stock blob bytes as the OS builds it (0x40082334): a 4-byte length per slot, then the slot's PCM16 */
export function stockBytes(slotLengths: number[]): number {
  return slotLengths.reduce((t, len) => t + (len > 64 ? 4 + (len - 64) : 0), 0);
}

export interface Usage {
  stockPages: number;
  files: { e: Entry; pages: number; loads: boolean }[];
  freePages: number;
}

/** the voice CPU memory at the next boot, for the long samples in the Syntakt's order */
export function usage(stock: number, order: Entry[]): Usage {
  const stockPages = Math.ceil(stock / PAGE);
  let used = stockPages + 1, full = false;                  // +1: the table page
  const files = order.slice(0, 64).map((e) => {
    const pages = Math.ceil(e.bytes / PAGE), loads = !full && used + pages <= POOL_PAGES;
    if (loads) used += pages; else full = true;
    return { e, pages, loads };
  });
  for (const e of order.slice(64)) files.push({ e, pages: Math.ceil(e.bytes / PAGE), loads: false });
  return { stockPages, files, freePages: Math.max(0, POOL_PAGES - used) };
}

export const mib = (bytes: number) => `${(bytes / 2 ** 20).toFixed(bytes < 10 * 2 ** 20 ? 2 : 1)} MiB`;
