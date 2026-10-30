// master-comp: pagina SYN della FX track. Testi con le formule di mods/master-comp/make_patch.py
// (unit_tables); il misuratore GR segue colpi simulati: barra piena = nessuna riduzione, vuota a -18 dB.

import { type Fb } from "../oled.ts";
import { header, page, step } from "./page.ts";

const RAT = ["OFF", "1.5:1", "2:1", "3:1", "4:1", "6:1", "8:1", "16:1", "20:1"];
const RATIO = [1, 1.5, 2, 3, 4, 6, 8, 16, 20];

export function msText(t: number): string {
  if (t < 10) return t.toFixed(1) + "ms";
  if (t < 1000) return Math.round(t) + "ms";
  return (t / 1000).toFixed(1) + "s";
}
const db = (x: number, plus = false): string => {
  const r = Math.round(x) || 0;
  return `${plus && r > 0 ? "+" : ""}${r}dB`;
};
const thr = (i: number): number => (60 * (i << 8)) / 32768 - 60;
const atk = (i: number): number => 0.1 + 99.9 * (i / 127) ** 2;
const rel = (i: number): number => 10 + 1990 * (i / 127) ** 2.5;
const mup = (i: number): number => (24.08 * (i << 8)) / 32768;
const rat = (i: number): number => Math.min(8, Math.floor(((i << 8) + 0xfe0 / 2) / 0xfe0));

const THR_STEPS = [64, 76, 90];                  // -30dB, -24dB, -18dB
const A = 20, R = 64, M = 32, RT = 63;           // 2.6ms, 369ms, +6dB, 4:1

export function draw(f: Fb, t: number): void {
  const [k] = step(t, 4, THR_STEPS.length);
  const ti = THR_STEPS[k], th = thr(ti), ratio = RATIO[rat(RT)];
  // colpo ogni mezzo secondo a -6 dB di picco: riduzione = eccesso * (1 - 1/rapporto), rilascio esponenziale
  const since = t % 0.5, peak = -6 - 4 * Math.floor((t / 0.5) % 2);
  const over = Math.max(0, peak - th) * (1 - 1 / ratio);
  const gr = Math.min(18, over * Math.exp((-since * 1000) / rel(R)) * Math.min(1, since / 0.004 + 0.3));
  header(f, "FX SYN", "COMP");
  page(f, [
    { label: "THR", value: db(th), pos: ti / 127 },
    { label: "ATK", value: msText(atk(A)), pos: A / 127 },
    { label: "REL", value: msText(rel(R)), pos: R / 127 },
    { label: "MUP", value: db(mup(M), true), pos: M / 127 },
    { label: "RAT", value: RAT[rat(RT)], kind: "text" },
    { label: "GR", value: db(-gr), kind: "bar", pos: 1 - gr / 18 },
    { label: "COMP", value: "ON", kind: "text" },
    { label: "DRIVE", value: "0", pos: 0 },
  ], (t % 4) < 1.2 ? 0 : 5);
}
