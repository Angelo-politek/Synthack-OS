// Schermate vere delle mod: fotogrammi disegnati dal codice dell'OS nell'emulatore (tools/emu/screens.py),
// un file per mod in frames/<mod>.json, caricato solo quando serve. Formato: fotogrammi distinti in base64
// (righe dall'alto, 16 byte per riga, bit 7 = pixel a sinistra) e, per scena, coppie [indice, ripetizioni].
// frames/index.json: id "<mod>/<scena>" -> didascalia.

import index from "./frames/index.json";
import type { Fb } from "../oled.ts";

export const captions: Record<string, string> = index;

interface FramesFile {
  fps: number;
  w: number;
  h: number;
  scenes: Record<string, [number, number][]>;
  frames: string[];
}

export interface Clip {
  fps: number;
  scenes: Record<string, Fb[]>;                // fotogrammi in ordine (stessi oggetti per le ripetizioni)
}

const files = import.meta.glob<FramesFile>(["./frames/*.json", "!./frames/index.json"], { import: "default" });
const cache = new Map<string, Promise<Clip | null>>();

/** base64 -> 128x64 byte 0/1, righe dall'alto (formato di oled.ts). */
export function unpack(b64: string, w = 128, h = 64): Fb {
  const raw = atob(b64), out = new Uint8Array(w * h);
  for (let i = 0; i < out.length; i++) out[i] = (raw.charCodeAt(i >> 3) >> (7 - (i & 7))) & 1;
  return out;
}

export function decode(f: FramesFile): Clip {
  const frames = f.frames.map((b) => unpack(b, f.w, f.h));
  const scenes: Record<string, Fb[]> = {};
  for (const [name, seq] of Object.entries(f.scenes))
    scenes[name] = seq.flatMap(([i, n]) => Array<Fb>(n).fill(frames[i]));
  return { fps: f.fps, scenes };
}

/** Fotogrammi di una mod, o null se non ce ne sono. */
export function load(mod: string): Promise<Clip | null> {
  let p = cache.get(mod);
  if (!p) {
    const get = files[`./frames/${mod}.json`];
    p = get ? get().then(decode) : Promise.resolve(null);
    cache.set(mod, p);
  }
  return p;
}
