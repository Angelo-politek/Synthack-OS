// Logo ASCII: comparsa a colonne con qualche carattere disturbato, poi un breve glitch ogni tanto.
// Con prefers-reduced-motion il logo resta fermo. Il testo vero resta nel <pre> (e nell'aria-label).

const NOISE = "/\\_|<>=+*#%";

export function reveal(pre: HTMLElement): void {
  if (matchMedia("(prefers-reduced-motion: reduce)").matches) return;
  const final = pre.textContent ?? "";
  const lines = final.split("\n"), width = Math.max(...lines.map((l) => l.length));
  const rnd = (): string => NOISE[Math.floor(Math.random() * NOISE.length)];
  const t0 = performance.now(), DUR = 1100;
  const frame = (now: number): void => {
    const k = Math.min(1, (now - t0) / DUR), edge = Math.floor(k * (width + 6));
    pre.textContent = lines.map((l) => [...l].map((c, x) => {
      if (c === " " || x < edge - 6) return c;
      if (x < edge) return Math.random() < 0.5 ? rnd() : c;
      return " ";
    }).join("")).join("\n");
    if (k < 1) requestAnimationFrame(frame);
    else {
      pre.textContent = final;
      pre.classList.add("lit");
      setTimeout(() => glitch(pre), 2500);
    }
  };
  requestAnimationFrame(frame);
}

function glitch(pre: HTMLElement): void {
  pre.classList.add("glitch");
  setTimeout(() => pre.classList.remove("glitch"), 260);
  setTimeout(() => glitch(pre), 6000 + Math.random() * 6000);
}
