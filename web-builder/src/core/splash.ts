// Splash d'avvio con il nome di chi costruisce: come named_splash in tools/build/build.py (stessi byte).
// Il logo sta nella prima patch di mods/splash/patch.json; il layout dice dove e con che orientamento.

import font from "../../../tools/splash/font3x5.json" with { type: "json" };
import splashSpec from "../../../mods/splash/patch.json" with { type: "json" };
import type { ModSpec } from "./build.ts";

export const W = 128, H = 64;
export const NAME_MAX = 20;
const FONT = font as Record<string, string[]>;

interface Layout { logo_offset: number; logo_len: number; name_y: number; flip: string }

/** Maiuscole, solo i caratteri del font, al massimo NAME_MAX (come render.clean_name). */
export function cleanName(s: string): string {
  return [...s.toUpperCase()].filter((c) => c in FONT && c !== "v").join("").slice(0, NAME_MAX).trim();
}

// pixel 0/1 per righe, y verso il basso; nel framebuffer: per colonne, byte = x*8 + y/8, bit = 7 - y%8
function fromFb(fb: Uint8Array): Uint8Array {
  const px = new Uint8Array(W * H);
  for (let x = 0; x < W; x++)
    for (let y = 0; y < H; y++) if (fb[x * 8 + (y >> 3)] & (0x80 >> (y & 7))) px[y * W + x] = 1;
  return px;
}

function toFb(px: Uint8Array): Uint8Array {
  const fb = new Uint8Array(W * H / 8);
  for (let y = 0; y < H; y++)
    for (let x = 0; x < W; x++) if (px[y * W + x]) fb[x * 8 + (y >> 3)] |= 0x80 >> (y & 7);
  return fb;
}

function flip(px: Uint8Array, how: string): Uint8Array {
  const out = new Uint8Array(W * H);
  for (let y = 0; y < H; y++)
    for (let x = 0; x < W; x++)
      out[y * W + x] = px[(how.includes("v") ? H - 1 - y : y) * W + (how.includes("h") ? W - 1 - x : x)];
  return out;
}

function drawName(px: Uint8Array, name: string, y0: number): void {
  name = cleanName(name);
  if (!name) return;
  const x0 = (W - (name.length * 4 - 1)) >> 1;
  [...name].forEach((c, i) =>
    FONT[c].forEach((row, r) => [...row].forEach((p, k) => {
      const x = x0 + i * 4 + k, y = y0 + r;
      if (p === "#" && x >= 0 && x < W && y >= 0 && y < H) px[y * W + x] = 1;
    })));
}

function logoOf(spec: ModSpec): { lay: Layout; bytes: Uint8Array; data: Uint8Array } {
  const lay = spec.layout as unknown as Layout;
  const data = Uint8Array.from(spec.patches[0].hex!.match(/../g)!.map((h) => parseInt(h, 16)));
  return { lay, data, bytes: data.subarray(lay.logo_offset, lay.logo_offset + lay.logo_len) };
}

/** Lo schermo all'avvio (128*64 valori 0/1, per righe), con il nome se c'e'. */
export function splashPixels(name = "", spec: ModSpec = splashSpec as ModSpec): Uint8Array {
  const { lay, bytes } = logoOf(spec);
  const px = flip(fromFb(bytes), lay.flip);
  drawName(px, name, lay.name_y);
  return px;
}

/** La mod splash con il nome ridisegnato nel logo; senza nome la restituisce com'e'. */
export function namedSplash(spec: ModSpec, name: string): ModSpec {
  if (!cleanName(name)) return spec;
  const { lay, data } = logoOf(spec);
  data.set(toFb(flip(splashPixels(name, spec), lay.flip)), lay.logo_offset);
  let hex = "";
  for (const b of data) hex += b.toString(16).padStart(2, "0");
  return { ...spec, patches: [{ ...spec.patches[0], hex }, ...spec.patches.slice(1)] };
}
