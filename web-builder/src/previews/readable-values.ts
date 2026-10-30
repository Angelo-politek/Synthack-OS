// readable-values: pagina FILTER di una traccia digitale, inviluppo e valori nelle unita' della mod.
// Testi stampati da rv.c nell'emulatore (harness di tests/test_readable_values.py) per i valori
// 0 10 20 32 40 48 64 80 96 110 127; FREQ con la formula del README (4.918 Hz * e^(0.065542 * FREQ)).

import { line, text, type Fb } from "../oled.ts";
import { bar, header, knob, label, step } from "./page.ts";

const ATK = ["0.7ms", "22ms", "55ms", "120ms", "186ms", "280ms", "602ms", "1.25s", "2.55s", "4.74s", "10.0s"];
const DEC = ["0.0ms", "64ms", "163ms", "357ms", "555ms", "837ms", "1.80s", "3.75s", "7.66s", "14.2s", "INF"];
const SUS = ["0%", "8%", "16%", "25%", "31%", "38%", "50%", "63%", "76%", "87%", "100%"];

export function freqText(v: number): string {
  const hz = 4.918 * Math.exp(0.065542 * v);
  if (hz < 10) return hz.toFixed(1) + "Hz";
  if (hz < 1000) return Math.round(hz) + "Hz";
  if (hz < 9995) return (hz / 1000).toFixed(2) + "k";
  return (hz / 1000).toFixed(1) + "k";
}

const ms = (s: string): number => (s === "INF" ? Infinity : parseFloat(s) * (s.endsWith("ms") ? 1 : 1000));
const width = (s: string): number => (ms(s) === Infinity ? 30 : 5 + 22 * Math.min(1, Math.log10(1 + ms(s)) / 4));

/** Tratto esponenziale da (x0, y0) verso y1 su w pixel; inf: resta piatto. */
function curve(f: Fb, x0: number, y0: number, w: number, y1: number, inf: boolean): void {
  let py = y0;
  for (let i = 1; i <= w; i++) {
    const ny = inf ? y0 : y0 + (y1 - y0) * (1 - Math.exp((-4 * i) / w));
    line(f, x0 + i - 1, py, x0 + i, ny);
    py = ny;
  }
}

const BASE = [2, 5, 6, 4];                      // ATK 55ms, DEC 837ms, SUS 50%, REL 555ms
const ease = (u: number): number => (1 - Math.cos(2 * Math.PI * u)) / 2;

export function draw(f: Fb, t: number): void {
  const [focus, u] = step(t, 3, 5);
  const idx = BASE.map((b, i) => (i === focus ? b + Math.round(3 * ease(u)) : b));
  const fv = focus === 4 ? 64 + Math.round(40 * ease(u)) : 64;
  const a = ATK[idx[0]], d = DEC[idx[1]], s = SUS[idx[2]], r = DEC[idx[3]];

  header(f, "FILTER", "T1");
  const top = 9, bot = 24, lev = bot - Math.round(((bot - top) * parseInt(s)) / 100);
  const wa = width(a), wd = width(d), wr = width(r), ws = Math.max(8, 119 - wa - wd - wr);
  let x = 4;
  line(f, x, bot, x + wa, top);
  x += wa;
  curve(f, x, top, wd, lev, d === "INF");
  const sy = d === "INF" ? top : lev;
  x += wd;
  line(f, x, sy, x + ws, sy);
  x += ws;
  curve(f, x, sy, Math.min(wr, 124 - x), bot, r === "INF");

  ["ATK", "DEC", "SUS", "REL"].forEach((l, i) => label(f, i * 32 + 16, 27, l, i === focus));
  [a, d, s, r].forEach((v, i) => text(f, i * 32 + 16, 34, v, 1));

  const y = 42;
  ["FREQ", "RESO", "TYPE", "ENV"].forEach((l, i) => label(f, i * 32 + 16, y, l, i === 0 && focus === 4));
  knob(f, 16, y + 11, fv / 127, 4);
  text(f, 16, y + 17, freqText(fv), 1);
  knob(f, 48, y + 11, 40 / 127, 4);
  text(f, 48, y + 17, "40", 1);
  text(f, 80, y + 11, "LP2", 1);
  bar(f, 100, y + 11, 25, 0.68, true);
}
