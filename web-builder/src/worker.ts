// La build gira qui, fuori dal thread della pagina: la compressione della sezione 3 dura decine di secondi.

import { build, type ModSpec, type Progress } from "./core/build.ts";

export interface Request {
  stock: ArrayBuffer;
  mods: string[];
  specs: Record<string, ModSpec>;
  outName: string;
}

export type Reply =
  | { kind: "progress"; progress: Progress }
  | { kind: "done"; syx: Uint8Array; manifest: object; log: string[] }
  | { kind: "error"; message: string };

const post = (r: Reply, transfer: Transferable[] = []): void => self.postMessage(r, { transfer });

self.onmessage = (e: MessageEvent<Request>) => {
  const { stock, mods, specs, outName } = e.data;
  let last = -1;
  try {
    const r = build(new Uint8Array(stock), mods, specs, outName, (p) => {
      const pct = p.total ? Math.floor((100 * p.done!) / p.total) : -1;
      if (p.stage !== "compress" || pct !== last) post({ kind: "progress", progress: p });
      last = pct;
    });
    post({ kind: "done", syx: r.syx, manifest: r.manifest, log: r.log }, [r.syx.buffer]);
  } catch (err) {
    post({ kind: "error", message: err instanceof Error ? err.message : String(err) });
  }
};
