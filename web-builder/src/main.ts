import { resolve, STOCK_SHA256 } from "./core/build.ts";
import { sha256hex } from "./core/sha256.ts";
import { info, specs } from "./mods.ts";
import type { Reply, Request } from "./worker.ts";

const REPO = "https://github.com/Angelo-politek/Synthack-OS/tree/main/mods/";
const OUT = "synthack.syx";
const $ = <T extends HTMLElement>(id: string): T => document.getElementById(id) as T;

let stock: ArrayBuffer | null = null;
let busy = false;
let urls: string[] = [];

const features = Object.keys(info).filter((n) => info[n].kind === "feature").sort((a, b) => info[a].title.localeCompare(info[b].title));

function renderMods(): void {
  const ul = $("mods");
  for (const name of features) {
    const li = document.createElement("li");
    li.innerHTML = `<label><input type="checkbox" value="${name}" checked>
      <span><strong></strong> <a target="_blank" rel="noopener">details</a><br><small></small></span></label>`;
    li.querySelector("strong")!.textContent = info[name].title;
    li.querySelector("small")!.textContent = info[name].summary;
    li.querySelector("a")!.href = REPO + name;
    ul.append(li);
  }
  ul.addEventListener("change", update);
}

function chosen(): string[] {
  return [...document.querySelectorAll<HTMLInputElement>("#mods input:checked")].map((i) => i.value);
}

function update(): void {
  const mods = chosen();
  const added = mods.length ? resolve(mods, specs).added : [];
  $("deps").textContent = added.length ? "Added automatically: " + added.map((n) => info[n]?.title ?? n).join(", ") + "." : "";
  ($("build") as HTMLButtonElement).disabled = busy || !stock || !mods.length;
}

async function loadStock(f: File): Promise<void> {
  const status = $("stock-status");
  stock = null;
  status.className = "status";
  status.textContent = "Checking…";
  const buf = await f.arrayBuffer();
  const sha = sha256hex(new Uint8Array(buf));
  const version = Object.keys(STOCK_SHA256).find((v) => STOCK_SHA256[v] === sha);
  if (version) {
    stock = buf;
    status.classList.add("good");
    status.textContent = `${f.name}: stock Syntakt OS ${version}, verified.`;
  } else {
    status.classList.add("bad");
    status.textContent = `${f.name} is not the stock Syntakt OS 1.41 (different SHA-256). Use the file from elektron.se, not a modified one.`;
  }
  $("drop-text").textContent = f.name;
  update();
}

const STAGES = { check: "Checking the stock OS", patch: "Applying the mods", compress: "Compressing the OS", verify: "Verifying the result" };

function runBuild(): void {
  if (!stock || busy) return;
  busy = true;
  update();
  urls.forEach(URL.revokeObjectURL);
  urls = [];
  $("result").hidden = true;
  $("error").hidden = true;
  $("progress").hidden = false;
  const bar = $("bar") as HTMLProgressElement, stage = $("stage");
  bar.removeAttribute("value");
  const worker = new Worker(new URL("./worker.ts", import.meta.url), { type: "module" });
  const done = (): void => {
    worker.terminate();
    busy = false;
    $("progress").hidden = true;
    update();
  };
  worker.onmessage = (e: MessageEvent<Reply>) => {
    const r = e.data;
    if (r.kind === "progress") {
      const p = r.progress;
      stage.textContent = STAGES[p.stage] + (p.total ? ` ${Math.floor((100 * p.done!) / p.total)}%` : "…");
      if (p.total) bar.value = (100 * p.done!) / p.total;
      else bar.removeAttribute("value");
    } else if (r.kind === "done") {
      const syx = URL.createObjectURL(new Blob([r.syx as Uint8Array<ArrayBuffer>], { type: "application/octet-stream" }));
      const json = URL.createObjectURL(new Blob([JSON.stringify(r.manifest, null, 2) + "\n"], { type: "application/json" }));
      urls = [syx, json];
      const a = $("dl-syx") as HTMLAnchorElement, j = $("dl-json") as HTMLAnchorElement;
      a.href = syx;
      a.download = OUT;
      j.href = json;
      j.download = OUT.replace(/\.syx$/, ".json");
      const log = $("log");
      log.replaceChildren(...r.log.map((l) => Object.assign(document.createElement("li"), { textContent: l })));
      $("result").hidden = false;
      done();
    } else {
      $("error").textContent = "Build failed: " + r.message;
      $("error").hidden = false;
      done();
    }
  };
  worker.onerror = (e) => {
    $("error").textContent = "Build failed: " + e.message;
    $("error").hidden = false;
    done();
  };
  const msg: Request = { stock: stock.slice(0), mods: chosen(), specs, outName: OUT };
  worker.postMessage(msg);
}

renderMods();
update();
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
