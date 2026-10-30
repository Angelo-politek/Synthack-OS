// perf-fx: pagina Mod A (M1-M4 = effetti dei tasti 13-16, valori di default) e, sotto, i 16 tasti trig:
// lo step suonato (pieno) e la posizione reale del pattern (punto), che riprende a tempo al rilascio.
// Logica dei segmenti come mods/perf-fx/perf.c: ripete o inverte il segmento dello step appena suonato,
// HALF raddoppia ogni step dentro 8 step.

import { fill, hline, rect, text, type Fb } from "../oled.ts";
import { header, label } from "./page.ts";

const FX = ["1/16", "1/8", "R1/4", "HALF"];
const LEN = [1, 2, 4, 8];
const STEP = 0.125;                             // 120 BPM, sedicesimi
const SEG = 8;                                  // step per fase: libero, tasto 13, libero, tasto 14, ...

export function played(real: number): { key: number; step: number } {
  const phase = Math.floor(real / SEG) % 8, key = phase % 2 ? (phase - 1) / 2 : -1;
  if (key < 0) return { key, step: real % 16 };
  const anchor = Math.floor(real / SEG) * SEG - 1, k = real - anchor - 1, L = LEN[key];
  const start = Math.floor((((anchor % 16) + 16) % 16) / L) * L;
  const off = key === 2 ? L - 1 - (k % L) : key === 3 ? Math.floor(k / 2) % L : k % L;
  return { key, step: (start + off) % 16 };
}

export function draw(f: Fb, t: number): void {
  const real = Math.floor(t / STEP);
  const { key, step } = played(real);
  header(f, "PERF FX", "MOD A");
  for (let i = 0; i < 4; i++) {
    label(f, i * 32 + 16, 10, "M" + (i + 1), i === key);
    text(f, i * 32 + 16, 18, FX[i], 1);
  }
  text(f, 1, 30, key < 0 ? "FUNC+15: MOD A" : `HOLD ${13 + key}: ${FX[key]}`);
  for (let i = 0; i < 16; i++) {
    const x = 1 + i * 8, y = 40;
    if (i === step) fill(f, x, y, 6, 8);
    else rect(f, x, y, 6, 8);
    if (i === real % 16) fill(f, x + 2, y + 10, 2, 2);
  }
  hline(f, 97, 126, 53);                        // tasti 13-16
  if (key >= 0) fill(f, 1 + (12 + key) * 8, 52, 6, 3);
  text(f, 126, 57, "13-16", 2);
}
