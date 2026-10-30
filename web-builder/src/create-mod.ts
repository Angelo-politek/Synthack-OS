import { addLocal, localMods, removeLocal } from "./local.ts";
import { specs as repoSpecs } from "./mods.ts";
import { spy } from "./toc.ts";

const $ = <T extends HTMLElement = HTMLElement>(id: string): T => document.getElementById(id) as T;
const KIND_NOTE: Record<string, string> = {
  feature: "in Create your OS → Mods",
  machine: "in Create your OS → Machines",
  infra: "not shown as a tile: added automatically when another mod requires it",
  test: "hidden from the list (test mod)",
};

// pannelli vicino ai paragrafi che ne parlano, se il testo ha quei titoli
$("try-it-here")?.before($("prompt"));
$("submit-it")?.before($("load"));

// indice dai titoli h2 della colonna, pannelli compresi
const toc = $("toc");
for (const h of document.querySelectorAll<HTMLElement>("#doc-main h2[id]")) {
  const li = document.createElement("li"), a = document.createElement("a");
  li.className = "d2";
  a.href = "#" + h.id;
  a.textContent = h.textContent?.replace(/^#/, "") ?? "";
  li.append(a);
  toc.append(li);
}
spy(toc.parentElement!);
if (location.hash) document.getElementById(decodeURIComponent(location.hash.slice(1)))?.scrollIntoView();

// ---- copia del prompt

$("copy").addEventListener("click", async () => {
  const text = $("prompt-text").textContent ?? "", status = $("copy-status");
  try {
    await navigator.clipboard.writeText(text);
    status.textContent = "Copied to the clipboard.";
  } catch {
    const sel = getSelection(), range = document.createRange();
    range.selectNodeContents($("prompt-text"));
    sel?.removeAllRanges();
    sel?.addRange(range);
    status.textContent = "Copy blocked by the browser: the prompt is selected, press Ctrl+C (or ⌘C).";
  }
});

// ---- mod locali

function renderList(): void {
  const { mods, problems } = localMods(repoSpecs), ul = $("local-list");
  ul.replaceChildren();
  if (!mods.length) ul.append(Object.assign(document.createElement("li"), { className: "empty", textContent: "None yet." }));
  for (const m of mods) {
    const li = document.createElement("li");
    const head = document.createElement("div");
    head.className = "local-head";
    const b = document.createElement("strong");
    b.textContent = m.card.title;
    const meta = document.createElement("span");
    meta.className = "mono small";
    meta.textContent = `${m.name} · ${m.card.kind} · ${m.spec.patches.length} patch${m.spec.patches.length === 1 ? "" : "es"}`;
    const rm = document.createElement("button");
    rm.type = "button";
    rm.className = "link danger";
    rm.textContent = "Remove";
    rm.setAttribute("aria-label", `Remove ${m.card.title} from this browser`);
    rm.addEventListener("click", () => {
      removeLocal(m.name);
      $("mod-status").textContent = `${m.card.title} removed from this browser.`;
      $("mod-status").className = "status";
      renderList();
    });
    head.append(b, meta, rm);
    const note = document.createElement("p");
    note.className = "hint";
    note.textContent = (m.card.summary ? m.card.summary + " " : "") + `Shown ${KIND_NOTE[m.card.kind] ?? ""}.`;
    li.append(head, note);
    ul.append(li);
  }
  const p = $("local-problems");
  p.hidden = !problems.length;
  p.textContent = problems.join(" ");
}

async function load(f: File): Promise<void> {
  const status = $("mod-status");
  status.className = "status";
  status.textContent = "Checking…";
  try {
    if (f.size > 4 << 20) throw new Error("the file is larger than 4 MB: is it really a patch.json?");
    const m = addLocal(await f.text(), repoSpecs);
    status.className = "status good";
    status.replaceChildren(`✓ ${m.card.title} (${m.name}) loaded. It is shown ${KIND_NOTE[m.card.kind]}, only in this browser. `);
    if (m.card.kind === "feature" || m.card.kind === "machine") {
      const a = document.createElement("a");
      a.href = `./index.html#step-${m.card.kind === "machine" ? "machines" : "mods"}`;
      a.textContent = "Open Create your OS →";
      status.append(a);
    }
  } catch (e) {
    status.className = "status bad";
    status.textContent = `✗ ${f.name} can't be used: ${e instanceof Error ? e.message : String(e)}`;
  }
  renderList();
}

$("mod-file").addEventListener("change", (e) => {
  const input = e.target as HTMLInputElement, f = input.files?.[0];
  if (f) void load(f);
  input.value = "";
});
const drop = $("mod-drop");
drop.addEventListener("dragover", (e) => {
  e.preventDefault();
  drop.classList.add("over");
});
drop.addEventListener("dragleave", () => drop.classList.remove("over"));
drop.addEventListener("drop", (e) => {
  e.preventDefault();
  drop.classList.remove("over");
  const f = e.dataTransfer?.files[0];
  if (f) void load(f);
});
addEventListener("storage", renderList);
renderList();
