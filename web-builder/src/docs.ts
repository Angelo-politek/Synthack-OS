import { spy } from "./toc.ts";

const toc = document.querySelector<HTMLElement>(".toc");
if (toc) spy(toc);
