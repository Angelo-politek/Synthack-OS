// Indice laterale: evidenzia il titolo della sezione che si sta leggendo.

export function spy(toc: HTMLElement): void {
  const links = new Map<string, HTMLAnchorElement>();
  toc.querySelectorAll<HTMLAnchorElement>("a[href^='#']").forEach((a) => links.set(decodeURIComponent(a.hash.slice(1)), a));
  const heads = [...links.keys()].map((id) => document.getElementById(id)).filter((h): h is HTMLElement => !!h);
  if (!heads.length) return;
  const set = (): void => {
    let cur = heads[0];
    for (const h of heads) if (h.getBoundingClientRect().top < 120) cur = h;
    links.forEach((a, id) => (id === cur.id ? a.setAttribute("aria-current", "location") : a.removeAttribute("aria-current")));
  };
  let pending = false;
  addEventListener("scroll", () => {
    if (pending) return;
    pending = true;
    requestAnimationFrame(() => {
      pending = false;
      set();
    });
  }, { passive: true });
  set();
}
