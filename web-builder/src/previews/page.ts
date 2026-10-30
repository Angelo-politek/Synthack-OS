// Pagina di parametri disegnata come illustrazione: intestazione, due file di 4 caselle (etichetta,
// manopola o barra, valore). Forme e font sono nostri.

import { circle, dots, fill, hline, inverse, line, rect, text, type Fb } from "../oled.ts";

export interface Slot {
  label: string;
  value?: string;
  kind?: "knob" | "bar" | "bipolar" | "text" | "empty";
  pos?: number;              // 0..1
}

export function header(f: Fb, left: string, right = ""): void {
  text(f, 1, 0, left);
  if (right) text(f, 126, 0, right, 2);
  dots(f, 0, 127, 6);
}

export function knob(f: Fb, cx: number, cy: number, pos: number, r = 5): void {
  circle(f, cx, cy, r);
  const a = (0.75 + 1.5 * Math.min(1, Math.max(0, pos))) * Math.PI;   // da 225 gradi in senso orario
  line(f, cx, cy, cx + Math.cos(a) * (r - 1), cy + Math.sin(a) * (r - 1));
}

export function bar(f: Fb, x: number, y: number, w: number, pos: number, bipolar = false): void {
  rect(f, x, y, w, 5);
  const inner = w - 2, p = Math.min(1, Math.max(0, pos));
  if (!bipolar) fill(f, x + 1, y + 1, Math.round(inner * p), 3);
  else {
    const c = x + 1 + Math.floor(inner / 2), e = x + 1 + Math.round(inner * p);
    fill(f, Math.min(c, e), y + 1, Math.abs(e - c) + 1, 3);
  }
}

export function label(f: Fb, cx: number, y: number, s: string, focus = false): void {
  if (focus) inverse(f, cx, y, s, 1);
  else text(f, cx, y, s, 1);
}

export function slot(f: Fb, col: number, y0: number, s: Slot, focus = false): void {
  const cx = col * 32 + 16;
  if (s.kind === "empty") {
    hline(f, cx - 2, cx + 2, y0 + 12);
    return;
  }
  label(f, cx, y0, s.label, focus);
  const kind = s.kind ?? "knob", pos = s.pos ?? 0;
  if (kind === "knob") knob(f, cx, y0 + 12, pos);
  else if (kind === "bar" || kind === "bipolar") bar(f, cx - 12, y0 + 10, 25, pos, kind === "bipolar");
  else if (kind === "text" && s.value) text(f, cx, y0 + 10, s.value, 1);
  if (s.value && kind !== "text") text(f, cx, y0 + 19, s.value, 1);
}

export const ROW1 = 9, ROW2 = 37;

export function page(f: Fb, slots: Slot[], focus = -1): void {
  slots.forEach((s, i) => slot(f, i % 4, i < 4 ? ROW1 : ROW2, s, i === focus));
}

/** Fase di un ciclo: indice del passo e frazione, per animazioni a scatti. */
export function step(t: number, period: number, n: number): [number, number] {
  const k = Math.floor(t / period);
  return [((k % n) + n) % n, t / period - k];
}
