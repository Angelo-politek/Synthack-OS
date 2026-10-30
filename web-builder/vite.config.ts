import { existsSync, readFileSync } from "node:fs";
import { basename, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { defineConfig, type Plugin } from "vite";
import { escapeHtml, renderMarkdown, tocHtml } from "./src/site/markdown.ts";

const ROOT = fileURLToPath(new URL(".", import.meta.url));
const CONTENT = resolve(ROOT, "content");
const PAGES = ["index", "create-mod", "users", "modders"];

function read(file: string): string | null {
  return existsSync(file) ? readFileSync(file, "utf8") : null;
}

const MISSING = '<p class="note">This page is being written. Meanwhile, see the '
  + '<a href="https://github.com/Angelo-politek/Synthack-OS">repository on GitHub</a>.</p>';

// Pagine statiche: intestazione e piede comuni, Markdown di content/ reso al build.
//   <!-- @header -->  <!-- @footer -->
//   <!-- @doc:users.md -->      indice + articolo
//   <!-- @md:create-mod.md -->  solo articolo (l'indice va in <!-- @toc:create-mod.md -->)
//   <!-- @text:agent-prompt.md -->  testo grezzo, per un <pre>
function site(): Plugin {
  return {
    name: "synthack-site",
    configureServer(server) {
      server.watcher.add([CONTENT, resolve(ROOT, "src/partials")]);
      server.watcher.on("change", (f) => {
        if (f.startsWith(CONTENT) || f.includes("partials")) server.ws.send({ type: "full-reload" });
      });
    },
    transformIndexHtml(html, ctx) {
      const page = basename(ctx.filename, ".html");
      const header = readFileSync(resolve(ROOT, "src/partials/header.html"), "utf8")
        .replace(`data-page="${page}"`, `data-page="${page}" aria-current="page"`);
      const md = (f: string) => {
        const src = read(resolve(CONTENT, f));
        return src === null ? null : renderMarkdown(src, { machines: "machine" });
      };
      return html
        .replace("<!-- @header -->", header)
        .replace("<!-- @footer -->", readFileSync(resolve(ROOT, "src/partials/footer.html"), "utf8"))
        .replace(/<!-- @doc:([\w.-]+) -->/g, (_, f: string) => {
          const r = md(f);
          if (!r) return `<article class="prose">${MISSING}</article>`;
          const toc = tocHtml(r.toc);
          return (toc ? `<nav class="toc" aria-label="On this page"><p class="toc-title">On this page</p>${toc}</nav>` : "")
            + `<article class="prose">${r.html}</article>`;
        })
        .replace(/<!-- @md:([\w.-]+) -->/g, (_, f: string) => md(f)?.html ?? MISSING)
        .replace(/<!-- @toc:([\w.-]+) -->/g, (_, f: string) => tocHtml(md(f)?.toc ?? []))
        .replace(/<!-- @text:([\w.-]+) -->/g, (_, f: string) => escapeHtml((read(resolve(CONTENT, f)) ?? "").trim()));
    },
  };
}

// base relativa: il sito funziona da qualsiasi percorso (GitHub Pages, file locale servito)
export default defineConfig({
  base: "./",
  plugins: [site()],
  server: { fs: { allow: [".."] } },     // mods/ sta fuori da web-builder/
  build: {
    target: "es2022",
    rollupOptions: { input: Object.fromEntries(PAGES.map((p) => [p, resolve(ROOT, p + ".html")])) },
  },
  worker: { format: "es" },
});
