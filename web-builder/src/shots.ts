// Schermate nelle pagine di documentazione: <figure data-screen="<mod>/<scena>"> prodotte al build dai
// marcatori <!-- @screen:mod/scena --> del Markdown (src/site/markdown.ts). Ogni figura anima i fotogrammi
// veri della scena (frames/<mod>.json) in un OLED come quello delle tessere.

import { load } from "./previews/frames.ts";
import { fromFrames } from "./previews/index.ts";
import { mount } from "./screen.ts";

for (const fig of document.querySelectorAll<HTMLElement>("figure[data-screen]")) {
  const id = fig.dataset.screen ?? "";
  const [mod, scene] = id.split("/");
  const box = fig.querySelector<HTMLElement>(".oled");
  if (!box) continue;
  void load(mod).then((clip) => {
    const frames = clip?.scenes[scene];
    if (!clip || !frames?.length) {
      fig.hidden = true;
      return;
    }
    const caption = fig.querySelector("figcaption")?.textContent ?? id;
    mount(box, fromFrames(frames, clip.fps), `Syntakt screen: ${caption}`);
  });
}
