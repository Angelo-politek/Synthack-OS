// fx3: pagina 2 del tab REVERB (FX3). TYPE scorre CHOR, FLNG, PHSR, CRSH; nomi e testi delle altre
// manopole come in mods/fx3/fx3.c (curve di make_patch.py, valori di partenza tdef per tipo).

import { type Fb } from "../oled.ts";
import { header, page, step, type Slot } from "./page.ts";

const TYPES = ["CHOR", "FLNG", "PHSR", "CRSH"];
const LONG = ["Chorus", "Flanger", "Phaser", "Crusher"];
const NAMES = [["SPD", "DEP", "TIME", "FDBK", "WID"], ["SPD", "DEP", "TIME", "FDBK", "WID"],
  ["SPD", "DEP", "FREQ", "FDBK", "WID"], ["SRR", "BITS", "DRV", "-", "-"]];
const TDEF = [[60, 64, 64, 0, 64], [60, 64, 64, 64, 64], [60, 64, 64, 64, 64], [0, 0, 0, 0, 0]];

const rateC = (v: number): number => Math.round(1000 * 0.05 * 200 ** (v / 127));   // mHz
const rateF = (v: number): number => Math.round(1000 * 0.02 * 250 ** (v / 127));
const depC = (v: number): number => Math.round(1000 * 8 * (v / 127) ** 2);          // us
const timeC = (v: number): number => Math.round(1000 * (1 + 29 * (v / 127) ** 1.5));
const depF = (v: number): number => Math.round(1000 * 4 * (v / 127) ** 2);
const timeF = (v: number): number => Math.round(1000 * (0.1 + 7.9 * (v / 127) ** 2));
const freqP = (v: number): number => Math.round(100 * 40 ** (v / 127));

function fixed(n: number, d: number, unit: string): string {
  const p = 10 ** d;
  return d ? `${Math.floor(n / p)}.${String(n % p).padStart(d, "0")}${unit}` : `${n}${unit}`;
}
const hzM = (m: number): string => (m < 9995 ? fixed(Math.floor((m + 5) / 10), 2, "Hz") : fixed(Math.floor((m + 50) / 100), 1, ""));
const msU = (us: number): string => us < 995 ? fixed(Math.floor((us + 5) / 10), 2, "ms")
  : us < 9950 ? fixed(Math.floor((us + 50) / 100), 1, "ms") : fixed(Math.floor((us + 500) / 1000), 0, "ms");
const hz = (h: number): string => h < 995 ? fixed(h, 0, "Hz")
  : h < 9950 ? fixed(Math.floor((h + 50) / 100), 1, "kHz") : fixed(Math.floor((h + 500) / 1000), 0, "kHz");
const sgn = (x: number, unit: string): string => (x ? (x < 0 ? "-" : "+") : "") + fixed(Math.abs(x), 0, unit);
const q = (a: number, v: number): number => Math.floor((a * v + 63) / 127);

export function texts(t: number, v: number[]): string[] {
  const [spd, dep, del, fb, wid] = v;
  if (t === 3) return [hz(Math.floor(24000 / (1 + q(31, spd)))), `${16 - q(15, dep)}bit`, fixed(q(240, del), 1, "dB"), "-", "-"];
  const m = t === 1 ? 95 : 90, x = (fb - 64) * m, r = Math.min(m, Math.floor((Math.abs(x) + 31) / 63));
  return [
    hzM(t === 0 ? rateC(spd) : rateF(spd)),
    t === 2 ? fixed(q(60, dep), 1, "oct") : msU(t === 0 ? depC(dep) : depF(dep)),
    t === 2 ? hz(freqP(del)) : msU(t === 0 ? timeC(del) : timeF(del)),
    t === 0 ? fixed(q(90, fb), 0, "%") : sgn(x < 0 ? -r : r, "%"),
    t === 2 ? fixed(q(100, wid), 0, "%") : fixed(q(180, wid), 0, "deg"),
  ];
}

const volTxt = (v: number): string => (v ? (40 * Math.log10(v / 127)).toFixed(1) + "dB" : "-inf");

export function draw(f: Fb, t: number): void {
  const [type, u] = step(t, 3.2, 4);
  const v = [...TDEF[type]];
  if (type < 3) v[0] = Math.min(127, v[0] + Math.round(30 * Math.sin(Math.PI * u)));   // SPD che gira
  else v[1] = Math.round(10 * Math.sin(Math.PI * u));                                    // BITS
  const tx = texts(type, v);
  const knob = (i: number): Slot => (NAMES[type][i] === "-" ? { label: "", kind: "empty" }
    : { label: NAMES[type][i], value: tx[i], kind: i === 3 && type ? "bipolar" : "knob", pos: v[i] / 127 });
  header(f, "FX3", LONG[type].toUpperCase());
  page(f, [
    { label: "TYPE", value: TYPES[type], kind: "text" }, knob(0), knob(1), knob(2),
    knob(3), knob(4), { label: "DEL", value: volTxt(0), kind: "bar", pos: 0 }, { label: "REV", value: volTxt(80), kind: "bar", pos: 80 / 127 },
  ], u < 0.25 ? 0 : type < 3 ? 1 : 2);
}
