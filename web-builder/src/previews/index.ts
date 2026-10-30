// Anteprime delle mod: draw(fb, t) disegna lo schermo 128x64 (0/1) al tempo t in secondi.
// Sono illustrazioni delle pagine vere, disegnate con forme e font nostri. Un'anteprima si puo'
// sostituire con fotogrammi catturati dall'emulatore: registry["mod"] = fromFrames(frames, fps).

import { fill, measure, text, W, type Fb } from "../oled.ts";
import * as dualMono from "./dual-mono.ts";
import * as fx3 from "./fx3.ts";
import * as masterComp from "./master-comp.ts";
import * as perfFx from "./perf-fx.ts";
import * as readableValues from "./readable-values.ts";

export type Draw = (fb: Fb, t: number) => void;

export const registry: Record<string, Draw> = {
  "readable-values": readableValues.draw,
  "master-comp": masterComp.draw,
  "fx3": fx3.draw,
  "perf-fx": perfFx.draw,
  "dual-mono": dualMono.draw,
};

/** Fotogrammi grezzi (128*64 byte 0/1 ciascuno), ripetuti in ciclo. */
export function fromFrames(frames: Uint8Array[], fps: number): Draw {
  return (f, t) => f.set(frames[Math.floor(t * fps) % frames.length]);
}

function wrap(s: string, width: number): string[] {
  const lines: string[] = [];
  let cur = "";
  for (const w of s.split(/\s+/).filter(Boolean)) {
    const next = cur ? cur + " " + w : w;
    if (measure(next) <= width || !cur) cur = next;
    else { lines.push(cur); cur = w; }
  }
  if (cur) lines.push(cur);
  return lines;
}

/** Mod senza anteprima: il titolo in testo a pixel, con un cursore. */
export function titleCard(title: string, tag = "MOD"): Draw {
  const lines = wrap(title.toUpperCase(), 116).slice(0, 4);
  return (f, t) => {
    text(f, 4, 4, tag);
    fill(f, 4 + measure(tag) + 3, 6, 20, 1);
    const y0 = 32 - Math.floor((lines.length * 9) / 2);
    lines.forEach((l, i) => text(f, 6, y0 + i * 9, l));
    const last = lines[lines.length - 1] ?? "";
    if (Math.floor(t * 2) % 2 === 0) fill(f, Math.min(W - 6, 6 + measure(last) + 2), y0 + (lines.length - 1) * 9, 3, 5);
  };
}

export const previewFor = (name: string, title: string, tag?: string): Draw => registry[name] ?? titleCard(title, tag);
