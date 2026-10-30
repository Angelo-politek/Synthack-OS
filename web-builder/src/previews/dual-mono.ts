// dual-mono: con EXTERNAL IN = mono, External Mixer = IN L e la nuova pagina IN R del tab MIXER, ognuna
// con livello e mandate proprie. Testi: mandate DEL/REV come readable-values ((v/32768)^2 in dB),
// FX3 come la tabella VOL_TXT di fx3 ((v/127)^2 in dB, un decimale).

import { type Fb } from "../oled.ts";
import { header, page, step, type Slot } from "./page.ts";

export function sendText(v: number): string {           // v: 0..0x7F00
  if (!v) return "-inf";
  const x = 40 * Math.log10(v / 32768), a = Math.abs(x);
  const s = Math.round(a * 10) >= 100 ? String(Math.round(a)) : (Math.round(a * 10) / 10).toFixed(1);
  return (x < 0 && s !== "0.0" ? "-" : "") + s + "dB";
}
const fx3Text = (v: number): string => (v ? (40 * Math.log10(v / 127)).toFixed(1) + "dB" : "-inf");

const SIDES = [
  { name: "EXT MIXER", side: "IN L", lev: 100, del: 0x4000, rev: 0x2800, fx3: 90 },
  { name: "MIXER", side: "IN R", lev: 72, del: 0, rev: 0x5a80, fx3: 60 },
];

export function draw(f: Fb, t: number): void {
  const [p, u] = step(t, 3.5, 2);
  const s = SIDES[p];
  const focus = u < 0.3 ? 0 : u < 0.55 ? 4 : u < 0.8 ? 5 : 6;
  const wob = Math.round(6 * Math.sin(Math.PI * u));
  const del = focus === 4 ? s.del + wob * 0x400 : s.del, rev = focus === 5 ? s.rev + wob * 0x300 : s.rev;
  const fx3 = focus === 6 ? s.fx3 + wob : s.fx3;
  const empty: Slot = { label: "", kind: "empty" };
  header(f, s.name, s.side);
  page(f, [
    { label: s.side, kind: "bar", pos: s.lev / 127 }, empty, empty, empty,
    { label: "DEL", value: sendText(Math.max(0, del)), kind: "bar", pos: Math.max(0, del) / 0x7f00 },
    { label: "REV", value: sendText(rev), kind: "bar", pos: rev / 0x7f00 },
    { label: "FX3", value: fx3Text(fx3), kind: "bar", pos: fx3 / 127 },
    p === 0 ? { label: "FX", kind: "bar", pos: 0 } : empty,
  ], focus);
}
