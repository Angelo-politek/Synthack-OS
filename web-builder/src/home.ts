// Home: lo schermo grande che scorre le schermate vere delle mod, e il catalogo delle mod per gruppo.

import { STOCK_SHA256 } from "./core/build.ts";
import { splashPixels } from "./core/splash.ts";
import { GROUPS, groupOf, info, modUrl, type Card } from "./mods.ts";
import { captions, load } from "./previews/frames.ts";
import { fromFrames, type Draw } from "./previews/index.ts";
import { mount } from "./screen.ts";

const $ = <T extends HTMLElement = HTMLElement>(id: string): T => document.getElementById(id) as T;
const el = <K extends keyof HTMLElementTagNameMap>(tag: K, cls = "", txt = ""): HTMLElementTagNameMap[K] => {
  const e = document.createElement(tag);
  if (cls) e.className = cls;
  if (txt) e.textContent = txt;
  return e;
};

document.querySelectorAll(".os-ver").forEach((e) => (e.textContent = Object.keys(STOCK_SHA256).join(" / ")));

// ---- schermo grande: lo splash, poi ogni scena catturata dall'emulatore, con la sua didascalia

interface Slide { draw: Draw; seconds: number; caption: string }

async function hero(): Promise<void> {
  const px = splashPixels("");
  const slides: Slide[] = [{ draw: (f) => f.set(px), seconds: 2.5, caption: "Boot screen: SyntHack after the official intro" }];
  const scr = mount($("hero-oled"), slides[0].draw, "The Syntakt screen with SyntHack mods");
  const cap = $("hero-caption");
  const mods = [...new Set(Object.keys(captions).map((id) => id.split("/")[0]))].filter((m) => m !== "splash" && info[m]);
  for (const m of mods) {
    const clip = await load(m);
    if (!clip) continue;
    for (const [scene, frames] of Object.entries(clip.scenes)) {
      if (!frames.length) continue;
      slides.push({ draw: fromFrames(frames, clip.fps), seconds: Math.min(8, Math.max(3, frames.length / clip.fps)),
                    caption: `${info[m].title}: ${captions[`${m}/${scene}`] ?? scene}` });
    }
  }
  if (matchMedia("(prefers-reduced-motion: reduce)").matches || slides.length < 2) return;
  let k = 0, t0 = performance.now() / 1000;
  const cur = (): Slide => slides[k];
  // ogni scena riparte dal suo primo fotogramma: il tempo passato alla scena e' quello dall'ingresso
  scr.redraw((f) => cur().draw(f, Math.max(0, performance.now() / 1000 - t0)));
  const next = (): void => {
    k = (k + 1) % slides.length;
    t0 = performance.now() / 1000;
    cap.textContent = cur().caption;
    setTimeout(next, cur().seconds * 1000);
  };
  cap.textContent = cur().caption;
  setTimeout(next, cur().seconds * 1000);
}

// ---- catalogo

function card(name: string, c: Card): HTMLElement {
  const a = el("a", "cat-card");
  a.href = modUrl(name);
  a.rel = "noopener";
  const head = el("div", "cat-head");
  head.append(el("h4", "cat-title", c.title), el("span", `badge ${c.status}`, c.status));
  a.append(head, el("p", "cat-sum", c.summary));
  return a;
}

function catalog(): void {
  const box = $("catalog");
  const names = Object.keys(info).sort((a, b) => info[a].title.localeCompare(info[b].title));
  const groups: { title: string; note: string; list: string[] }[] = [
    ...GROUPS.map((g) => ({ title: g.title, note: g.note,
                            list: names.filter((n) => info[n].kind === "feature" && groupOf(n) === g.id) })),
    { title: "Machines", note: "Synth machines with their own code on the sound engine.",
      list: names.filter((n) => info[n].kind === "machine") },
  ];
  for (const g of groups) {
    if (!g.list.length) continue;
    const head = el("div", "group-head");
    head.append(el("h3", "group-title", g.title));
    if (g.note) head.append(el("span", "group-note", g.note));
    const grid = el("div", "cat-grid");
    grid.append(...g.list.map((n) => card(n, info[n])));
    box.append(head, grid);
  }
}

catalog();
void hero();
