// Markdown di content/ in HTML, al build di Vite (nessun parser nella pagina): id dei titoli come su GitHub,
// indice dei titoli h2/h3, link relativi verso le pagine del sito o verso il repository.

import { Marked, type Tokens } from "marked";

const REPO = "https://github.com/Angelo-politek/Synthack-OS/blob/main/web-builder/content/";
const PAGES: Record<string, string> = { "users.md": "users.html", "modders.md": "modders.html", "create-mod.md": "create-mod.html" };

export interface Rendered {
  html: string;
  toc: { depth: number; id: string; text: string }[];
}

export const escapeHtml = (s: string): string =>
  s.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;");

export function slug(s: string): string {
  return s.toLowerCase().replace(/<[^>]+>/g, "").replace(/[^\p{L}\p{N}\s_-]/gu, "").trim().replace(/\s/g, "-");
}

function href(h: string): string {
  if (/^([a-z]+:|#|\/)/i.test(h)) return h;
  const [path, frag = ""] = h.split("#");
  const file = path.replace(/^\.\//, "");
  if (PAGES[file]) return PAGES[file] + (frag ? "#" + frag : "");
  if (!path) return h;
  return new URL(h, REPO).href;
}

/** aliases: id in piu' su un titolo (es. "machines" -> "machine" per create-mod.html#machine). */
export function renderMarkdown(src: string, aliases: Record<string, string> = {}): Rendered {
  const toc: Rendered["toc"] = [];
  const seen = new Map<string, number>();
  const md = new Marked({
    gfm: true,
    renderer: {
      heading(t: Tokens.Heading): string {
        const inner = this.parser.parseInline(t.tokens);
        let id = slug(t.text);
        const n = seen.get(id) ?? 0;
        seen.set(id, n + 1);
        if (n) id += "-" + n;
        if (t.depth === 2 || t.depth === 3) toc.push({ depth: t.depth, id, text: inner.replace(/<[^>]+>/g, "") });
        const alias = aliases[id] ? `<span id="${aliases[id]}" class="anchor"></span>` : "";
        return `${alias}<h${t.depth} id="${id}"><a class="hash" href="#${id}" aria-hidden="true" tabindex="-1">#</a>${inner}</h${t.depth}>\n`;
      },
      link(t: Tokens.Link): string {
        const to = href(t.href);
        const ext = /^https?:/.test(to) ? ' rel="noopener"' : "";
        const title = t.title ? ` title="${escapeHtml(t.title)}"` : "";
        return `<a href="${escapeHtml(to)}"${title}${ext}>${this.parser.parseInline(t.tokens)}</a>`;
      },
    },
  });
  const html = md.parse(src, { async: false }) as string;
  return { html: html.replace(/<table>/g, '<div class="table"><table>').replace(/<\/table>/g, "</table></div>"), toc };
}

export function tocHtml(toc: Rendered["toc"]): string {
  if (!toc.length) return "";
  return `<ol>${toc.map((h) => `<li class="d${h.depth}"><a href="#${h.id}">${h.text}</a></li>`).join("")}</ol>`;
}
