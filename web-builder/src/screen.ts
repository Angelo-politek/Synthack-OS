// Schermi OLED nella pagina: un solo ciclo di animazione a 15 fotogrammi al secondo, solo per gli
// schermi visibili; con prefers-reduced-motion un fotogramma fisso.

import { Oled } from "./oled.ts";
import type { Draw } from "./previews/index.ts";

const FPS = 15, STILL_T = 1.6;
const reduced = matchMedia("(prefers-reduced-motion: reduce)");

export interface Screen {
  redraw(draw?: Draw): void;
  dispose(): void;
}

interface Item { oled: Oled; draw: Draw; box: HTMLElement; visible: boolean }

const items = new Map<Element, Item>();
let raf = 0, last = 0;
const start = performance.now();

function paint(it: Item, t: number): void {
  it.oled.fb.fill(0);
  it.draw(it.oled.fb, t);
  it.oled.render();
}

const now = (): number => (reduced.matches ? STILL_T : (performance.now() - start) / 1000);

function frame(ts: number): void {
  raf = 0;
  if (reduced.matches) return;
  if (ts - last >= 1000 / FPS - 2) {
    last = ts;
    const t = now();
    for (const it of items.values()) if (it.visible) paint(it, t);
  }
  schedule();
}

function schedule(): void {
  if (!raf && !reduced.matches && [...items.values()].some((i) => i.visible)) raf = requestAnimationFrame(frame);
}

const io = new IntersectionObserver((entries) => {
  for (const e of entries) {
    const it = items.get(e.target);
    if (!it) continue;
    it.visible = e.isIntersecting;
    if (it.visible) paint(it, now());
  }
  schedule();
}, { rootMargin: "100px" });

const ro = new ResizeObserver((entries) => {
  for (const e of entries) {
    const it = items.get(e.target);
    if (it && it.oled.fit(e.contentRect.width)) paint(it, now());
  }
});

reduced.addEventListener("change", () => {
  for (const it of items.values()) paint(it, now());
  schedule();
});

/** Mette uno schermo in box (che ne decide la larghezza). label: testo alternativo dell'immagine. */
export function mount(box: HTMLElement, draw: Draw, label: string): Screen {
  const canvas = document.createElement("canvas");
  canvas.setAttribute("role", "img");
  canvas.setAttribute("aria-label", label);
  box.append(canvas);
  const it: Item = { oled: new Oled(canvas), draw, box, visible: false };
  items.set(box, it);
  it.oled.fit(box.clientWidth || 256);
  paint(it, now());
  io.observe(box);
  ro.observe(box);
  return {
    redraw(d?: Draw) {
      if (d) it.draw = d;
      paint(it, now());
    },
    dispose() {
      io.unobserve(box);
      ro.unobserve(box);
      items.delete(box);
      canvas.remove();
    },
  };
}
