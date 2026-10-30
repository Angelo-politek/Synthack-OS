import { BASE_MODS, resolve, STOCK_SHA256, type ModSpec, type Progress } from "./core/build.ts";
import { sha256hex } from "./core/sha256.ts";
import { cleanName, NAME_MAX, splashPixels } from "./core/splash.ts";
import { localMods, removeLocal, type LocalMod } from "./local.ts";
import { reveal } from "./logo.ts";
import { info, modUrl, specs as repoSpecs, type Card } from "./mods.ts";
import { previewFor } from "./previews/index.ts";
import { mount, type Screen } from "./screen.ts";
import type { Reply, Request } from "./worker.ts";

const OUT = "synthack.syx";
const OS_VERS = Object.keys(STOCK_SHA256);
const $ = <T extends HTMLElement = HTMLElement>(id: string): T => document.getElementById(id) as T;
const el = <K extends keyof HTMLElementTagNameMap>(tag: K, cls = "", txt = ""): HTMLElementTagNameMap[K] => {
  const e = document.createElement(tag);
  if (cls) e.className = cls;
  if (txt) e.textContent = txt;
  return e;
};

let stock: ArrayBuffer | null = null;
let busy = false;
let urls: string[] = [];
let locals: LocalMod[] = [];
let screens: Screen[] = [];
const chosen = new Set<string>();
const seen = new Set<string>();             // mod gia' mostrate: la scelta iniziale vale una volta sola

const allSpecs = (): Record<string, ModSpec> => ({ ...repoSpecs, ...Object.fromEntries(locals.map((m) => [m.name, m.spec])) });
const cardOf = (n: string): Card | undefined => info[n] ?? locals.find((m) => m.name === n)?.card;
const titleOf = (n: string): string => cardOf(n)?.title ?? n;

// ---- tessere

interface Entry { name: string; card: Card; local: boolean }

function entries(kind: Card["kind"]): Entry[] {
  const repo = Object.keys(info).filter((n) => info[n].kind === kind)
    .sort((a, b) => info[a].title.localeCompare(info[b].title))
    .map((name) => ({ name, card: info[name], local: false }));
  return [...repo, ...locals.filter((m) => m.card.kind === kind).map((m) => ({ name: m.name, card: m.card, local: true }))];
}

function plusTile(href: string, title: string, line: string): HTMLElement {
  const a = el("a", "tile plus");
  a.href = href;
  a.append(el("span", "plus-mark", "+"), el("span", "tile-title", title), el("span", "tile-sum", line));
  return a;
}

function tile(e: Entry, i: number): HTMLElement {
  const art = el("article", "tile");
  art.style.setProperty("--i", String(i));
  art.dataset.name = e.name;
  const screen = el("div", "tile-screen");
  const box = el("div", "oled");
  screen.append(box);
  const body = el("div", "tile-body");
  const h = el("h4", "tile-title", e.card.title);
  h.id = `t-${e.name}`;
  body.append(h);
  if (e.local) body.append(el("span", "badge", "local — not in the official list"));
  const sum = el("p", "tile-sum", e.card.summary);
  sum.title = e.card.summary;
  body.append(sum);

  const foot = el("div", "tile-foot");
  const sw = el("label", "switch");
  const cb = el("input");
  cb.type = "checkbox";
  cb.value = e.name;
  cb.setAttribute("aria-describedby", h.id);
  if (!seen.has(e.name)) {
    seen.add(e.name);
    if (!e.local) chosen.add(e.name);           // le mod del repo partono incluse, quelle locali no
  }
  cb.checked = chosen.has(e.name);
  art.classList.toggle("on", cb.checked);
  cb.addEventListener("change", () => {
    if (cb.checked) chosen.add(e.name);
    else chosen.delete(e.name);
    art.classList.toggle("on", cb.checked);
    update();
  });
  sw.append(cb, el("span", "knob"), el("span", "", "Include"));
  foot.append(sw);
  if (e.local) {
    const rm = el("button", "link danger", "Remove");
    rm.type = "button";
    rm.setAttribute("aria-label", `Remove ${e.card.title} from this browser`);
    rm.addEventListener("click", () => {
      removeLocal(e.name);
      chosen.delete(e.name);
      seen.delete(e.name);
      renderTiles();
    });
    foot.append(rm);
  } else {
    const a = el("a", "readme", "README ↗");
    a.href = modUrl(e.name);
    a.rel = "noopener";
    a.target = "_blank";
    a.setAttribute("aria-label", `${e.card.title} README on GitHub (new tab)`);
    foot.append(a);
  }
  art.append(screen, body, foot);
  queueMicrotask(() => screens.push(mount(box, previewFor(e.name, e.card.title, e.card.kind === "machine" ? "MACHINE" : "MOD"),
    `Illustration of the ${e.card.title} screen`)));
  return art;
}

function renderTiles(): void {
  screens.forEach((s) => s.dispose());
  screens = [];
  const r = localMods(repoSpecs);
  locals = r.mods;
  for (const n of [...chosen]) if (!cardOf(n)) chosen.delete(n);
  const prob = $("local-problems");
  prob.hidden = !r.problems.length;
  prob.textContent = r.problems.join(" ");

  const mods = $("mod-tiles");
  mods.replaceChildren(plusTile("./create-mod.html", "Create your mod", "Write a mod, try it here, send a pull request."),
    ...entries("feature").map(tile));

  const machines = entries("machine");
  const mt = $("machine-tiles");
  mt.replaceChildren(...machines.map(tile));
  if (!machines.some((m) => !m.local)) {
    const empty = el("div", "tile empty");
    empty.append(el("span", "tile-title", "No machines yet"));
    const p = el("p", "tile-sum");
    p.append("The first machines are being prepared by contributors. Follow them or join in on ");
    const a = el("a", "", "GitHub");
    a.href = "https://github.com/Angelo-politek/Synthack-OS/issues/1";
    a.rel = "noopener";
    p.append(a, ".");
    empty.append(p);
    mt.append(empty);
  }
  mt.append(plusTile("./create-mod.html#machine", "Add your machine", "A new synth machine on the sound engine."));
  update();
}

// ---- stato, dipendenze, riepilogo

function update(): void {
  const mods = [...chosen];
  let deps = "";
  try {
    const added = resolve([...BASE_MODS, ...mods], allSpecs()).added;
    if (added.length) deps = "Added automatically: " + added.map(titleOf).join(", ") + ".";
  } catch (e) {
    deps = e instanceof Error ? e.message : String(e);
  }
  $("deps").textContent = deps;
  const list = mods.map(titleOf);
  $("summary").textContent = `Boot splash${list.length ? " + " + list.join(", ") : " only (no mods selected)"}.`;
  $<HTMLButtonElement>("build").disabled = busy || !stock;
  $("build-hint").textContent = stock ? "A build takes 30 to 60 seconds and runs on this computer."
    : "Choose your stock OS in step 1 first.";
}

async function loadStock(f: File): Promise<void> {
  const status = $("stock-status");
  stock = null;
  status.className = "status";
  status.textContent = "Checking…";
  let buf: ArrayBuffer;
  try {
    buf = await f.arrayBuffer();
  } catch (e) {
    status.classList.add("bad");
    status.textContent = `✗ ${f.name} could not be read: ${e instanceof Error ? e.message : String(e)}`;
    update();
    return;
  }
  const sha = sha256hex(new Uint8Array(buf));
  const version = Object.keys(STOCK_SHA256).find((v) => STOCK_SHA256[v] === sha);
  if (version) {
    stock = buf;
    status.classList.add("good");
    status.textContent = `✓ ${f.name}: stock Syntakt OS ${version}, verified.`;
  } else {
    status.classList.add("bad");
    status.textContent = `✗ ${f.name} is not the stock Syntakt OS ${OS_VERS.join(" or ")} (different SHA-256). Use the file from elektron.se, not a modified one.`;
  }
  $("drop-text").textContent = f.name;
  $("drop").classList.toggle("ok", !!version);
  update();
}

// ---- schermata d'avvio

function bootScreen(): void {
  const input = $<HTMLInputElement>("name"), note = $("name-note");
  input.maxLength = NAME_MAX;
  const draw = (name: string) => {
    const px = splashPixels(name);
    return (f: Uint8Array) => f.set(px);
  };
  const scr = mount($("boot-screen"), draw(""), "SyntHack boot screen");
  const upd = (): void => {
    const name = cleanName(input.value);
    scr.redraw(draw(name));
    $("boot-screen").querySelector("canvas")?.setAttribute("aria-label", `SyntHack boot screen${name ? " with the name " + name : ""}`);
    note.textContent = !input.value.trim() ? `Letters, digits, “.” and “-”, up to ${NAME_MAX}, shown in capitals.`
      : name ? `Shown as: ${name}` : "None of these characters can be shown: the plain logo will be used.";
  };
  input.addEventListener("input", upd);
  upd();
}

// ---- build

const STAGES: Progress["stage"][] = ["check", "patch", "compress", "verify"];
const LABEL = { check: "Checking the stock OS", patch: "Applying the mods", compress: "Compressing the OS", verify: "Verifying the result" };

function showStage(p: Progress): void {
  const k = STAGES.indexOf(p.stage);
  document.querySelectorAll<HTMLElement>("#stages li").forEach((li, i) => {
    li.className = i < k ? "done" : i === k ? "now" : "";
  });
  const pct = p.total ? Math.floor((100 * p.done!) / p.total) : null;
  document.querySelector("#stages .pct")!.textContent = p.stage === "compress" && pct !== null ? `${pct}%` : "";
  const overall = [0, 4, 8, 96][k] + (p.stage === "compress" && pct !== null ? 0.88 * pct : 0);
  $("bar-fill").style.width = `${Math.max(2, overall)}%`;
  if (p.stage !== "compress" || pct === null || pct % 10 === 0) $("stage").textContent = LABEL[p.stage] + (pct !== null ? ` ${pct}%` : "…");
}

function runBuild(): void {
  if (!stock || busy) return;
  busy = true;
  update();
  urls.forEach(URL.revokeObjectURL);
  urls = [];
  $("result").hidden = true;
  $("error").hidden = true;
  $("progress").hidden = false;
  showStage({ stage: "check" });
  const worker = new Worker(new URL("./worker.ts", import.meta.url), { type: "module" });
  const done = (): void => {
    worker.terminate();
    busy = false;
    $("progress").hidden = true;
    update();
  };
  const fail = (msg: string): void => {
    $("error").textContent = "Build failed: " + msg;
    $("error").hidden = false;
    done();
  };
  worker.onmessage = (e: MessageEvent<Reply>) => {
    const r = e.data;
    if (r.kind === "progress") showStage(r.progress);
    else if (r.kind === "done") {
      const syx = URL.createObjectURL(new Blob([r.syx as Uint8Array<ArrayBuffer>], { type: "application/octet-stream" }));
      const json = URL.createObjectURL(new Blob([JSON.stringify(r.manifest, null, 2) + "\n"], { type: "application/json" }));
      urls = [syx, json];
      const a = $<HTMLAnchorElement>("dl-syx"), j = $<HTMLAnchorElement>("dl-json");
      a.href = syx;
      a.download = OUT;
      j.href = json;
      j.download = OUT.replace(/\.syx$/, ".json");
      const sha = (r.manifest as { output_sha256?: string }).output_sha256;
      $("sha").textContent = sha ? `SHA-256 ${sha}` : "";
      $("log").replaceChildren(...r.log.map((l) => el("li", "", l)));
      $("result").hidden = false;
      done();
      $("result").scrollIntoView({ behavior: "smooth", block: "nearest" });
    } else fail(r.message);
  };
  worker.onerror = (e) => fail(e.message);
  const name = cleanName($<HTMLInputElement>("name").value);
  const msg: Request = { stock: stock.slice(0), mods: [...chosen], specs: allSpecs(), outName: OUT, splashName: name || undefined };
  worker.postMessage(msg);
}

// ---- avvio

document.querySelectorAll(".os-ver").forEach((e) => (e.textContent = OS_VERS.join(" / ")));
document.querySelectorAll(".os-file").forEach((e) => (e.textContent = OS_VERS.map((v) => `Syntakt_OS${v}.syx`).join(" or ")));
reveal($("logo"));
bootScreen();
renderTiles();
window.addEventListener("storage", (e) => {
  if (e.key === null || e.key.startsWith("synthack.")) renderTiles();
});
$("stock").addEventListener("change", (e) => {
  const f = (e.target as HTMLInputElement).files?.[0];
  if (f) void loadStock(f);
});
const drop = $("drop");
drop.addEventListener("dragover", (e) => {
  e.preventDefault();
  drop.classList.add("over");
});
drop.addEventListener("dragleave", () => drop.classList.remove("over"));
drop.addEventListener("drop", (e) => {
  e.preventDefault();
  drop.classList.remove("over");
  const f = e.dataTransfer?.files[0];
  if (f) void loadStock(f);
});
$("build").addEventListener("click", runBuild);
